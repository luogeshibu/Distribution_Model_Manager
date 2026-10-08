from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


ENCODING_RE = re.compile(br"<\?xml[^>]*encoding=[\"']([^\"']+)[\"']", re.I)
DEVREF_RE = re.compile(r"#([^:]+):")
DEVREF_FULL_RE = re.compile(r"^#([^:]+):(.*)$")
POINT_RE = re.compile(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class IconDefinition:
    path: Path
    file_name: str
    element_tag: str
    element_id: str
    width: float
    height: float
    align_center: tuple[float, float]
    pins: tuple[tuple[float, float], ...]
    pin_ids: tuple[str, ...]
    # zenon pin ``id`` is a drawing-element identifier and may legitimately
    # change between symbol-library versions. ``index`` is the stronger logical
    # port identity when it is present and unique on both OLD and NEW symbols.
    pin_indices: tuple[str, ...] = ()


@dataclass(frozen=True)
class IconUpgradeRule:
    # file_name remains the OLD referenced file name for backward compatibility.
    file_name: str
    old: IconDefinition
    new: IconDefinition
    new_reference_name: str = ""

    @property
    def old_file_name(self) -> str:
        return self.old.file_name

    @property
    def new_file_name(self) -> str:
        return self.new.file_name


@dataclass
class IconPairAnalysis:
    rules: dict[str, IconUpgradeRule] = field(default_factory=dict)
    missing_old: list[str] = field(default_factory=list)
    missing_new: list[str] = field(default_factory=list)
    incompatible: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.missing_old and not self.missing_new and not self.incompatible and bool(self.rules)


@dataclass
class IconUpgradeResult:
    upgraded_instances: int = 0
    adjusted_lines: int = 0
    already_new_instances: int = 0
    skipped_unknown_size: int = 0
    changed_instance_ids: list[str] = field(default_factory=list)
    changed_line_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _local_name(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return float(default)


def _number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return ("%.6f" % value).rstrip("0").rstrip(".")


def _decode_xml(raw: bytes) -> str:
    match = ENCODING_RE.search(raw[:512])
    declared = match.group(1).decode("ascii", "ignore") if match else "utf-8"
    candidates = [declared]
    if declared.lower().replace("-", "") in {"gbk", "gb2312"}:
        candidates.append("gb18030")
    candidates.extend(["utf-8", "gb18030", "gbk"])
    tried: set[str] = set()
    for encoding in candidates:
        key = encoding.lower()
        if key in tried:
            continue
        tried.add(key)
        try:
            text = raw.decode(encoding)
            return re.sub(
                r"(<\?xml\b[^>]*\bencoding=)[\"'][^\"']+[\"']",
                r'\1"utf-8"',
                text,
                count=1,
                flags=re.I,
            )
        except (LookupError, UnicodeDecodeError):
            continue
    raise ValueError("无法识别图元 G 文件编码。")


def _parse_icon_root(path: Path) -> ET.Element:
    raw = path.read_bytes()
    text = _decode_xml(raw)
    try:
        return ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise ValueError(f"{path.name} XML 解析失败：{exc}") from exc


def parse_icon_definition(path: Path) -> IconDefinition:
    path = Path(path)
    root = _parse_icon_root(path)
    candidates: list[tuple[int, ET.Element, list[ET.Element]]] = []
    for element in root.iter():
        if "AlignCenter" not in element.attrib or "w" not in element.attrib or "h" not in element.attrib:
            continue
        pins = [child for child in element.iter() if _local_name(child.tag).lower() == "pin"]
        candidates.append((len(pins), element, pins))
    if not candidates:
        raise ValueError(f"{path.name} 未找到包含 w/h/AlignCenter 的图元主体。")

    # 优先选择含端口最多的主体；无端口图元则选择第一个有效主体。
    candidates.sort(key=lambda item: item[0], reverse=True)
    _pin_count, body, pin_elements = candidates[0]
    align_text = (body.get("AlignCenter") or "").strip()
    match = POINT_RE.fullmatch(align_text)
    if not match:
        raise ValueError(f"{path.name} 的 AlignCenter 无法解析：{align_text!r}")
    align = (float(match.group(1)), float(match.group(2)))
    pins = tuple((_float(pin.get("cx")), _float(pin.get("cy"))) for pin in pin_elements)
    pin_ids = tuple((pin.get("id") or "").strip() for pin in pin_elements)
    pin_indices = tuple((pin.get("index") or "").strip() for pin in pin_elements)
    return IconDefinition(
        path=path,
        file_name=path.name,
        element_tag=_local_name(body.tag),
        element_id=(body.get("id") or "").strip(),
        width=_float(body.get("w")),
        height=_float(body.get("h")),
        align_center=align,
        pins=pins,
        pin_ids=pin_ids,
        pin_indices=pin_indices,
    )


def _index_unique(paths: list[Path], side: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    duplicates: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        key = path.name
        if key in result and result[key].resolve(strict=False) != path.resolve(strict=False):
            duplicates.append(key)
        result[key] = path
    if duplicates:
        names = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"{side}图元中存在重复文件名：{names}。请每种图元只保留一份。")
    return result


def _reference_name_from_file_name(file_name: str) -> str:
    """Derive the usual object name used after ':' in a devref.

    zenon symbol libraries normally use the library file stem as the referenced
    object name. Keep the rule intentionally small and deterministic; same-name
    upgrades preserve the original devref verbatim.
    """
    lower = file_name.lower()
    suffixes = (".zwjddz.icn.g", ".zwk.icn.g", ".zt.icn.g", ".icn.g", ".g")
    for suffix in suffixes:
        if lower.endswith(suffix):
            return file_name[: -len(suffix)]
    return Path(file_name).stem


def _pin_direction_signature(
    pin: tuple[float, float],
    align_center: tuple[float, float],
    *,
    epsilon: float = 1e-6,
) -> str | None:
    """Classify a pin by its direction from AlignCenter."""
    dx = pin[0] - align_center[0]
    dy = pin[1] - align_center[1]
    if abs(dx) <= epsilon and abs(dy) <= epsilon:
        return None
    if abs(dx) <= epsilon:
        return "S" if dy > 0 else "N"
    if abs(dy) <= epsilon:
        return "E" if dx > 0 else "W"
    ratio = abs(dx / dy)
    if ratio <= 0.41421356237:
        return "S" if dy > 0 else "N"
    if ratio >= 2.41421356237:
        return "E" if dx > 0 else "W"
    if dx > 0 and dy > 0:
        return "SE"
    if dx > 0 and dy < 0:
        return "NE"
    if dx < 0 and dy > 0:
        return "SW"
    return "NW"


def _normalize_new_by_geometry(
    old: IconDefinition,
    new: IconDefinition,
) -> IconDefinition | None:
    """Reorder NEW pins to OLD order only when direction mapping is unique."""
    if not old.pins or len(old.pins) != len(new.pins):
        return None
    old_signatures = tuple(_pin_direction_signature(pin, old.align_center) for pin in old.pins)
    new_signatures = tuple(_pin_direction_signature(pin, new.align_center) for pin in new.pins)
    if (
        any(signature is None for signature in old_signatures)
        or any(signature is None for signature in new_signatures)
        or len(set(old_signatures)) != len(old_signatures)
        or len(set(new_signatures)) != len(new_signatures)
        or set(old_signatures) != set(new_signatures)
    ):
        return None
    new_by_signature = {signature: pin for signature, pin in zip(new_signatures, new.pins)}
    return IconDefinition(
        path=new.path,
        file_name=new.file_name,
        element_tag=new.element_tag,
        element_id=new.element_id,
        width=new.width,
        height=new.height,
        align_center=new.align_center,
        pins=tuple(new_by_signature[signature] for signature in old_signatures),
        pin_ids=old.pin_ids,
        pin_indices=old.pin_indices,
    )


def _normalize_pair(old: IconDefinition, new: IconDefinition) -> tuple[IconDefinition, list[str]]:
    reasons: list[str] = []
    if old.element_tag != new.element_tag:
        reasons.append(f"标签 {old.element_tag} → {new.element_tag}")
    if len(old.pins) != len(new.pins):
        reasons.append(f"端口数 {len(old.pins)} → {len(new.pins)}")
    if old.width <= 0 or old.height <= 0 or new.width <= 0 or new.height <= 0:
        reasons.append("宽高必须大于 0")

    normalized_new = new
    if len(old.pins) == 1 and len(new.pins) == 1:
        normalized_new = IconDefinition(
            path=new.path, file_name=new.file_name, element_tag=new.element_tag,
            element_id=new.element_id, width=new.width, height=new.height,
            align_center=new.align_center, pins=new.pins, pin_ids=old.pin_ids,
            pin_indices=old.pin_indices,
        )
    elif old.pins:
        # IMPORTANT: a pin's XML ``id`` is not necessarily its logical/electrical
        # identity. Real zenon library revisions often renumber drawing element
        # ids while keeping the electrical pin ``index`` stable. Prefer a complete,
        # unique index mapping; only fall back to id when indices are unavailable.
        old_indices_ok = (
            len(old.pin_indices) == len(old.pins)
            and all(old.pin_indices)
            and len(set(old.pin_indices)) == len(old.pin_indices)
        )
        new_indices_ok = (
            len(new.pin_indices) == len(new.pins)
            and all(new.pin_indices)
            and len(set(new.pin_indices)) == len(new.pin_indices)
        )
        if old_indices_ok and new_indices_ok and set(old.pin_indices) == set(new.pin_indices):
            new_by_index = {
                pin_index: pin for pin_index, pin in zip(new.pin_indices, new.pins)
            }
            normalized_new = IconDefinition(
                path=new.path,
                file_name=new.file_name,
                element_tag=new.element_tag,
                element_id=new.element_id,
                width=new.width,
                height=new.height,
                align_center=new.align_center,
                pins=tuple(new_by_index[pin_index] for pin_index in old.pin_indices),
                pin_ids=old.pin_ids,
                pin_indices=old.pin_indices,
            )
        elif (
            all(old.pin_ids)
            and all(new.pin_ids)
            and len(set(old.pin_ids)) == len(old.pin_ids)
            and len(set(new.pin_ids)) == len(new.pin_ids)
            and set(old.pin_ids) == set(new.pin_ids)
        ):
            new_by_id = {pin_id: pin for pin_id, pin in zip(new.pin_ids, new.pins)}
            normalized_new = IconDefinition(
                path=new.path,
                file_name=new.file_name,
                element_tag=new.element_tag,
                element_id=new.element_id,
                width=new.width,
                height=new.height,
                align_center=new.align_center,
                pins=tuple(new_by_id[pin_id] for pin_id in old.pin_ids),
                pin_ids=old.pin_ids,
                pin_indices=old.pin_indices,
            )
        else:
            geometry_normalized = _normalize_new_by_geometry(old, new)
            if geometry_normalized is not None:
                normalized_new = geometry_normalized
            elif old_indices_ok and new_indices_ok:
                reasons.append(
                    "新旧 pin index 集合不同、pin id 也不能建立唯一对应，且按 AlignCenter 的端口几何方向仍有歧义，无法确认端口关系"
                )
            elif not all(old.pin_ids) or not all(new.pin_ids):
                reasons.append(
                    "pin index 不完整，且存在缺少 id 的 pin，无法可靠建立新旧端口对应"
                )
            elif len(set(old.pin_ids)) != len(old.pin_ids) or len(set(new.pin_ids)) != len(new.pin_ids):
                reasons.append(
                    "pin index 不能唯一对应，且 pin id 存在重复，无法可靠建立端口对应"
                )
            else:
                reasons.append(
                    "新旧 pin index/id 均无法建立唯一对应，无法确认端口关系"
                )
    return normalized_new, reasons


def analyze_icon_mappings(pairs: list[tuple[Path, Path]]) -> IconPairAnalysis:
    """Analyze explicit OLD -> NEW symbol mappings.

    Unlike the legacy same-filename pairing, the two files may have different
    names. Rules are indexed by the OLD file name because that is what appears in
    the main G devref before upgrade.
    """
    analysis = IconPairAnalysis()
    seen_old: dict[str, Path] = {}
    for raw_old, raw_new in pairs:
        old_path = Path(raw_old)
        new_path = Path(raw_new)
        old_key = old_path.name
        previous = seen_old.get(old_key)
        if previous is not None and previous.resolve(strict=False) != old_path.resolve(strict=False):
            analysis.incompatible.append(f"{old_key}：同一旧图元文件名映射了多个来源，无法按 devref 唯一识别")
            continue
        if old_key in analysis.rules:
            analysis.incompatible.append(f"{old_key}：同一旧图元不能同时映射到多个新图元")
            continue
        seen_old[old_key] = old_path
        try:
            old = parse_icon_definition(old_path)
            new = parse_icon_definition(new_path)
            normalized_new, reasons = _normalize_pair(old, new)
            if reasons:
                analysis.incompatible.append(
                    f"{old.file_name} → {new.file_name}：" + "；".join(reasons)
                )
                continue
            analysis.rules[old_key] = IconUpgradeRule(
                old_key,
                old,
                normalized_new,
                _reference_name_from_file_name(new.file_name),
            )
        except Exception as exc:
            analysis.incompatible.append(f"{old_path.name} → {new_path.name}：{exc}")
    return analysis


def icon_definition_identity(path: Path) -> tuple[str, str] | None:
    """Return the stable XML identity used for safe cross-name pairing."""
    try:
        definition = parse_icon_definition(Path(path))
    except Exception:
        return None
    if not definition.element_tag or not definition.element_id:
        return None
    return definition.element_tag, definition.element_id


def suggest_icon_pairs(
    old_items: dict[str, Path], new_items: dict[str, Path]
) -> dict[str, tuple[str, str]]:
    """Suggest only deterministic OLD -> NEW mappings.

    First pair exact basenames.  For the remaining files, pair by the parsed
    symbol body ``(XML tag, body id)`` only when that identity occurs exactly
    once on both sides.  Ambiguous identities are intentionally left unmatched.
    The return value maps ``old_key -> (new_key, method)``.
    """
    suggestions: dict[str, tuple[str, str]] = {}

    for key in sorted(set(old_items) & set(new_items)):
        suggestions[key] = (key, "完全同名")

    remaining_old = {key: path for key, path in old_items.items() if key not in suggestions}
    used_new = {new_key for new_key, _method in suggestions.values()}
    remaining_new = {key: path for key, path in new_items.items() if key not in used_new}

    old_by_identity: dict[tuple[str, str], list[str]] = {}
    new_by_identity: dict[tuple[str, str], list[str]] = {}
    for key, path in remaining_old.items():
        identity = icon_definition_identity(path)
        if identity is not None:
            old_by_identity.setdefault(identity, []).append(key)
    for key, path in remaining_new.items():
        identity = icon_definition_identity(path)
        if identity is not None:
            new_by_identity.setdefault(identity, []).append(key)

    for identity, old_keys in old_by_identity.items():
        new_keys = new_by_identity.get(identity, [])
        if len(old_keys) == 1 and len(new_keys) == 1:
            suggestions[old_keys[0]] = (new_keys[0], "图元类型 + 主体 ID")

    return suggestions


def analyze_icon_pairs(old_paths: list[Path], new_paths: list[Path]) -> IconPairAnalysis:
    """Legacy same-filename auto-pairing retained for old settings/tests."""
    old_map = _index_unique(old_paths, "旧")
    new_map = _index_unique(new_paths, "新")
    analysis = IconPairAnalysis(
        missing_old=sorted(set(new_map) - set(old_map)),
        missing_new=sorted(set(old_map) - set(new_map)),
    )
    pairs = [(old_map[name], new_map[name]) for name in sorted(set(old_map) & set(new_map))]
    mapped = analyze_icon_mappings(pairs)
    analysis.rules.update(mapped.rules)
    analysis.incompatible.extend(mapped.incompatible)
    return analysis

def rotated(point: tuple[float, float], width: float, height: float, degrees: int) -> tuple[float, float]:
    """Return a main-G local coordinate after zenon icon rotation.

    For 90/270-degree instances zenon keeps the original unrotated ``x/y/w/h``
    box and rotates the symbol around the centre of that box.  When ``w != h``
    the rotated visual bounding box therefore needs a half-size centring offset.
    Omitting that offset produces the exact 1-pixel residual seen with the real
    28x30 LBS and 30x28 external-ground-disconnector symbols.
    """
    x, y = point
    rotation = degrees % 360
    if rotation == 0:
        return x, y
    if rotation == 180:
        return width - x, height - y
    if rotation in (90, 270):
        # Keep rotation centred in the original w/h box.  The offset can be a
        # half-unit for odd size differences, so retain float precision here.
        center_delta = (width - height) / 2.0
        if rotation == 90:
            return height - y + center_delta, x - center_delta
        return y + center_delta, width - x - center_delta
    raise ValueError(f"不支持的旋转角度：{degrees}")


def _points_from_d(value: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in POINT_RE.findall(value or "")]


def _element_by_id(root: ET.Element) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for element in root.iter():
        object_id = (element.get("id") or "").strip()
        if object_id:
            result[object_id] = element
    return result


def _axis_aligned(points: list[tuple[float, float]], tolerance: float = 1e-6) -> str | None:
    """Return H/V only for an originally straight two-point ConnectLine.

    The G drawings use many one-pixel grid coordinates.  A symbol rotation can make
    the mathematically transformed pin land one pixel off the existing row/column
    even though the original connection was intentionally horizontal/vertical.
    That rounding residual must not turn a straight wire into a diagonal segment.
    """

    if len(points) != 2:
        return None
    (x1, y1), (x2, y2) = points
    if abs(y1 - y2) <= tolerance and abs(x1 - x2) > tolerance:
        return "H"
    if abs(x1 - x2) <= tolerance and abs(y1 - y2) > tolerance:
        return "V"
    return None


def _consensus_small_shift(values: list[float], *, max_shift: float = 2.0, tolerance: float = 0.25) -> float:
    """Return a conservative common correction for axis-aligned connections.

    Only small, mutually consistent corrections are accepted.  This targets the
    1-pixel rotation/grid residual seen in real Jeddah G files without allowing a
    questionable node_area/link reference to drag the whole device away from its
    AlignCenter-based position.
    """

    if not values:
        return 0.0
    low = min(values)
    high = max(values)
    if high - low > tolerance:
        return 0.0
    shift = sum(values) / len(values)
    if abs(shift) > max_shift:
        return 0.0
    return shift


def _preserve_axis_aligned_connections(
    *,
    new_x: float,
    new_y: float,
    definition: IconDefinition,
    rotation: int,
    links: list[tuple[str, str, str]],
    by_id: dict[str, ET.Element],
) -> tuple[float, float]:
    """Nudge the upgraded device so existing H/V wires stay H/V.

    AlignCenter remains the primary placement rule.  For a verified horizontal
    ConnectLine we may apply only a tiny Y correction; for a verified vertical line
    only a tiny X correction.  The moved line endpoint can then still land on the
    *real* new pin while the original straight-line direction is preserved.

    This is especially important for 90/270-degree symbols where integer pixel
    rotation/renderer conventions can leave a one-pixel perpendicular residual.
    """

    x_shifts: list[float] = []
    y_shifts: list[float] = []
    for pin_index, endpoint_index, line_id in links:
        try:
            pin_number = int(pin_index)
            endpoint_number = int(endpoint_index)
        except ValueError:
            continue
        if pin_number < 0 or pin_number >= len(definition.pins) or endpoint_number not in (0, 1):
            continue
        line = by_id.get(line_id)
        if line is None:
            continue
        points = _points_from_d(line.get("d") or "")
        axis = _axis_aligned(points)
        if axis is None:
            continue
        pin = rotated(definition.pins[pin_number], definition.width, definition.height, rotation)
        expected_x = new_x + pin[0]
        expected_y = new_y + pin[1]
        actual_x, actual_y = points[endpoint_number]
        if axis == "H":
            y_shifts.append(actual_y - expected_y)
        else:
            x_shifts.append(actual_x - expected_x)

    return (
        new_x + _consensus_small_shift(x_shifts),
        new_y + _consensus_small_shift(y_shifts),
    )


def apply_icon_upgrade(tree: ET.ElementTree, rules: dict[str, IconUpgradeRule]) -> IconUpgradeResult:
    root = tree.getroot()
    elements = list(root.iter())
    by_id = _element_by_id(root)
    reverse_links: dict[str, list[tuple[str, str, str]]] = {}

    for candidate in elements:
        line_id = (candidate.get("id") or "").strip()
        points = _points_from_d(candidate.get("d") or "")
        if not line_id or len(points) != 2:
            continue
        for link in (candidate.get("node_area") or "").split(";"):
            fields = link.split(",")
            if len(fields) != 3:
                continue
            endpoint_index, pin_index, object_id = fields
            reverse_links.setdefault(object_id, []).append((pin_index, endpoint_index, line_id))

    result = IconUpgradeResult()
    line_points: dict[str, dict[int, tuple[float, float]]] = {}

    for element in elements:
        devref = element.get("devref") or ""
        match = DEVREF_RE.search(devref)
        if not match:
            continue
        file_name = match.group(1)
        rule = rules.get(file_name)
        if rule is None:
            continue
        current_w = _float(element.get("w"))
        current_h = _float(element.get("h"))
        same_target_file = rule.old.file_name == rule.new.file_name
        old_size_match = abs(current_w - rule.old.width) < 1e-6 and abs(current_h - rule.old.height) < 1e-6
        new_size_match = abs(current_w - rule.new.width) < 1e-6 and abs(current_h - rule.new.height) < 1e-6
        geometry_changed = (
            abs(rule.old.width - rule.new.width) >= 1e-6
            or abs(rule.old.height - rule.new.height) >= 1e-6
            or rule.old.align_center != rule.new.align_center
            or rule.old.pins != rule.new.pins
        )
        object_id = (element.get("id") or "").strip()
        links: list[tuple[str, str, str]] = []
        for link in (element.get("node_area") or "").split(";"):
            fields = link.split(",")
            if len(fields) == 3:
                links.append((fields[0], fields[1], fields[2]))
        if object_id:
            links.extend(reverse_links.get(object_id, []))
        links = list(set(links))

        rotation = int(round(_float(element.get("rotate"), 0.0)))

        def _pin_fit(definition: IconDefinition) -> tuple[float, int]:
            total = 0.0
            count = 0
            base_x = _float(element.get("x"))
            base_y = _float(element.get("y"))
            for pin_index, endpoint_index, line_id in links:
                try:
                    pin_number = int(pin_index)
                    endpoint_number = int(endpoint_index)
                except ValueError:
                    continue
                if pin_number < 0 or pin_number >= len(definition.pins) or endpoint_number not in (0, 1):
                    continue
                line = by_id.get(line_id)
                if line is None:
                    continue
                points = _points_from_d(line.get("d") or "")
                if len(points) != 2:
                    continue
                pin = rotated(definition.pins[pin_number], definition.width, definition.height, rotation)
                expected = (base_x + pin[0], base_y + pin[1])
                actual = points[endpoint_number]
                total += (actual[0] - expected[0]) ** 2 + (actual[1] - expected[1]) ** 2
                count += 1
            return total, count

        # Different-file mappings are always OLD while the main devref still points
        # at the old library. Same-file upgrades use size first, then linked pin
        # geometry when old/new sizes are identical. This makes repeated runs
        # idempotent even when only AlignCenter/pins changed.
        if not old_size_match:
            if same_target_file and new_size_match:
                result.already_new_instances += 1
                continue
            result.skipped_unknown_size += 1
            result.warnings.append(
                f"图元 ID {element.get('id') or '<无ID>'} 引用 {file_name}，当前尺寸 "
                f"{_number(current_w)}×{_number(current_h)} 与旧标准 "
                f"{_number(rule.old.width)}×{_number(rule.old.height)} 不一致，已跳过；"
                f"目标为 {rule.new.file_name} {_number(rule.new.width)}×{_number(rule.new.height)}。"
            )
            continue

        if same_target_file and new_size_match:
            if not geometry_changed:
                result.already_new_instances += 1
                continue
            old_score, old_count = _pin_fit(rule.old)
            new_score, new_count = _pin_fit(rule.new)
            if new_count and old_count and new_score + 1e-6 < old_score:
                result.already_new_instances += 1
                continue
            if not old_count and rule.old.pins:
                result.skipped_unknown_size += 1
                result.warnings.append(
                    f"图元 ID {element.get('id') or '<无ID>'} 的旧/新图元尺寸相同但几何不同，"
                    "且找不到可验证连接端点，无法安全判断当前版本，已跳过。"
                )
                continue

        old_align = rotated(rule.old.align_center, rule.old.width, rule.old.height, rotation)
        new_align = rotated(rule.new.align_center, rule.new.width, rule.new.height, rotation)
        new_x = _float(element.get("x")) + old_align[0] - new_align[0]
        new_y = _float(element.get("y")) + old_align[1] - new_align[1]
        # Keep the existing orthogonal wiring as a hard visual/electrical constraint
        # when the AlignCenter transform differs from the drawing grid by only a
        # tiny amount.  We move the device, not the opposite end of the wire, so
        # the new endpoint still lands on the real target pin without creating a
        # 1-pixel diagonal ConnectLine.
        new_x, new_y = _preserve_axis_aligned_connections(
            new_x=new_x,
            new_y=new_y,
            definition=rule.new,
            rotation=rotation,
            links=links,
            by_id=by_id,
        )
        element.set("x", _number(new_x))
        element.set("y", _number(new_y))
        element.set("w", _number(rule.new.width))
        element.set("h", _number(rule.new.height))
        if rule.old.file_name != rule.new.file_name:
            # Explicit OLD → NEW mapping means the target library/object is the new
            # symbol. zenon libraries conventionally expose the object name from the
            # icon file stem; same-file upgrades never rewrite devref.
            element.set("devref", f"#{rule.new.file_name}:{rule.new_reference_name}")
        result.upgraded_instances += 1
        if object_id:
            result.changed_instance_ids.append(object_id)

        for pin_index, endpoint_index, line_id in links:
            try:
                pin_number = int(pin_index)
                endpoint_number = int(endpoint_index)
            except ValueError:
                result.warnings.append(f"图元 ID {object_id} 的连接引用无法解析：{pin_index},{endpoint_index},{line_id}")
                continue
            if pin_number < 0 or pin_number >= len(rule.new.pins):
                result.warnings.append(
                    f"图元 ID {object_id} 的端口索引 {pin_number} 超出 {file_name} 新图元端口范围，已跳过该连接。"
                )
                continue
            if endpoint_number not in (0, 1):
                result.warnings.append(f"连接线 {line_id} 的端点索引 {endpoint_number} 不是 0/1，已跳过。")
                continue
            pin = rotated(rule.new.pins[pin_number], rule.new.width, rule.new.height, rotation)
            line_points.setdefault(line_id, {})[endpoint_number] = (new_x + pin[0], new_y + pin[1])

    for line_id, endpoints in line_points.items():
        line = by_id.get(line_id)
        if line is None:
            raise ValueError(f"图元升级需要修改连接线 {line_id}，但当前 G 文件中找不到该 ID。")
        points = _points_from_d(line.get("d") or "")
        if len(points) != 2:
            raise ValueError(f"连接线 {line_id} 不是两点线段，无法按已验证算法安全适配。")
        for endpoint_index, point in endpoints.items():
            points[endpoint_index] = point
        (x1, y1), (x2, y2) = points
        line.set("d", f"{_number(x1)},{_number(y1)} {_number(x2)},{_number(y2)}")
        line.set("x", _number(min(x1, x2) - 3))
        line.set("y", _number(min(y1, y2) - 3))
        line.set("w", _number(abs(x1 - x2) + 6))
        line.set("h", _number(abs(y1 - y2) + 6))
        for name, value in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
            if name in line.attrib:
                line.set(name, _number(value))
        result.adjusted_lines += 1
        result.changed_line_ids.append(line_id)

    return result
