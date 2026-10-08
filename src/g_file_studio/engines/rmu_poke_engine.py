from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.engines.id_engine import direct_layers, local_name
from g_file_studio.engines.rmu_identification_engine import RmuIdentificationResult


_RMU_DETAIL_SUFFIX = ".com.pic.g"
_LEGACY_RMU_DETAIL_SUFFIX = ".sln.pic.g"
_RMU_DETAIL_SUFFIX_RE = re.compile(r"\.(?:sln|com)\.pic\.g$", re.IGNORECASE)


@dataclass(frozen=True)
class _Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass
class SmartRmuPokeChange:
    rmu_name: str
    rect_id: str
    poke_id: str
    target_file: str
    action: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class SmartRmuPokeRecord:
    rmu_name: str
    rect_id: str = ""
    name_text_id: str = ""
    poke_id: str = ""
    target_file: str = ""
    action: str = "skipped"
    reason: str = ""


@dataclass
class SmartRmuPokeResult:
    file_path: Path
    intelligent_rmu_count: int = 0
    eligible_rmu_count: int = 0
    added_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    skipped_count: int = 0
    changes: list[SmartRmuPokeChange] = field(default_factory=list)
    records: list[SmartRmuPokeRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Confirmed from the user's working G-file Poke examples.  Newly created Pokes
# use the invisible style (fm=0 / ls=0) so they provide a hit area without
# painting over the RMU.  The object is deliberately placed at the back of the
# Layer; RMU devices and the cabinet name remain above it.
_CANONICAL_POKE_ATTRS: dict[str, str] = {
    "LevelEnd": "16", "LevelStart": "0",
    **{f"PlaneState{i}": ("1" if i == 0 else "0") for i in range(50)},
    "Pos": "0", "RectStyle": "0", "ShadowType": "0", "Style": "",
    "af": "2147483647", "af2": "2147483647", "af3": "2147483647", "af4": "2147483647",
    "aliasType": "", "app": "", "clip": "false", "devref": "", "domain": "",
    "eventRegister": "", "fc": "0,255,0", "fcc": "#00ff00", "fm": "0",
    "isDisplay": "1", "lc": "0,0,255", "lcc": "#0000ff", "ls": "0", "lw": "1",
    "onMouseHoverEnterAction": "", "onMouseHoverLeaveAction": "",
    "onMouseLeftDoubleClickAciton": "", "onMouseLeftOneClickAction": "",
    "onMouseRightDoubleClickAction": "", "onMouseRightOneClickAction": "",
    "opacity": "1", "p_AssFlag": "128", "p_DyColorFlag": "0", "p_EngcodeString": "",
    "p_FatherObjId": "", "p_Hint": "", "p_ProcName": "", "p_RectStyle": "0",
    "p_SelfDefString": "", "p_ShowModeMask": "3", "p_SubPos": "0", "rain_bow": "0",
    "rotate": "0", "switchapp": "1", "switchappflag": "1",
    "tfr": "rotate(0) scale(1,1)", "trend_color": "0",
}


def _float(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name, default))
    except (TypeError, ValueError):
        return default


def _box(element: ET.Element) -> _Box | None:
    w = _float(element, "w")
    h = _float(element, "h")
    if w <= 0 or h <= 0:
        return None
    x = _float(element, "x")
    y = _float(element, "y")
    return _Box(x, y, x + w, y + h)


def _number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _logical_g_stem(file_name: str) -> str:
    """Return the logical part before .sln.pic, ignoring upload copy suffixes."""
    match = re.match(r"^(.*)\.sln\.pic(?:\(\d+\))?\.g$", file_name, flags=re.I)
    if match:
        return match.group(1)
    match = re.match(r"^(.*?)(?:\(\d+\))?\.g$", file_name, flags=re.I)
    return match.group(1) if match else Path(file_name).stem


def _parse_auto_main_parts(source_file: Path) -> dict[str, str]:
    """Legacy strict four-part parser retained for pre-v2.18.69 templates."""
    stem = _logical_g_stem(source_file.name)
    parts = stem.split("-")
    if (
        len(parts) != 4
        or any(not part for part in parts)
        or not re.fullmatch(r"\d+", parts[-1])
    ):
        raise ValueError(
            f"主图文件名 {source_file.name!r} 不符合旧版区域模板要求。"
            "应为‘区域-区域-站点-馈线号.sln.pic.g’，例如 JED-NTH-ABH-03.sln.pic.g。"
        )
    region1, region2, station, feeder = parts
    return {
        "region1": region1,
        "region2": region2,
        "station": station,
        "feeder": feeder,
    }


def extract_batch_feeder(source_file: Path) -> str:
    """Extract FEEDER from the final numeric token before ``.sln.pic.g``.

    Batch Poke naming is the only mode that validates the source filename.  The
    site prefix may contain any number of ``-`` separated parts; the stable
    contract is simply ``...-<digits>.sln.pic.g``.  This keeps the feature usable
    at sites whose area/station prefix differs from Jeddah.
    """
    stem = _logical_g_stem(source_file.name)
    match = re.fullmatch(r".+-(\d+)", stem)
    if not match:
        raise ValueError(
            f"批处理 Poke 无法从主图文件名 {source_file.name!r} 提取 FEEDER。"
            "批处理要求文件名以‘-纯数字.sln.pic.g’结束，例如 JED-NTH-ABH-03.sln.pic.g。"
            "当前文件只跳过智能 RMU Poke；同批其他文件和本文件其他 RMU 操作继续处理。"
        )
    return match.group(1)


def _clean_rule(rule: str, *, label: str) -> str:
    value = (rule or "").strip().strip('"').strip("'")
    if not value:
        raise ValueError(f"{label}为空。")
    # ahref stores a filename only.  If a user pasted a path, keep the basename.
    value = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not value:
        raise ValueError(f"{label}为空。")
    return value


def _validate_ahref_filename(value: str, *, label: str = "Poke ahref") -> str:
    # Existing saved templates and old Pokes may still contain .sln.pic.g.
    # Normalize only the RMU detail target suffix; station-jump targets use a
    # separate engine and remain .sln.pic.g.
    if _RMU_DETAIL_SUFFIX_RE.search(value):
        value = _RMU_DETAIL_SUFFIX_RE.sub(_RMU_DETAIL_SUFFIX, value)
    if "/" in value or "\\" in value or re.search(r'[<>:"|?*]', value):
        raise ValueError(f"{label} 生成了非法文件名：{value!r}")
    if not value.lower().endswith(_RMU_DETAIL_SUFFIX):
        raise ValueError(f"{label} 必须以 {_RMU_DETAIL_SUFFIX} 结尾：{value!r}")
    return value


def render_single_rmu_rule(rule: str, rmu_name: str) -> str:
    """Render single-file/fixed naming without inspecting the source G filename.

    Accepted user forms:
      * ``JED-NTH-ABH-AH303-RMU.sln.pic.g``
      * ``JED-NTH-ABH-AH303-{RMU}.sln.pic.g``
      * a real sample such as ``JED-NTH-ABH-AH303-34661.sln.pic.g``
      * a fixed prefix such as ``JED-NTH-ABH-AH303``
    """
    value = _clean_rule(rule, label="单文件详情图规则")
    name = (rmu_name or "").strip()
    if not name:
        raise ValueError("RMU 名称为空，无法生成详情图文件名。")

    if re.search(r"\{rmu\}", value, flags=re.I):
        rendered = re.sub(r"\{rmu\}", name, value, flags=re.I)
    elif re.search(r"(?:^|-)RMU(?:\.sln\.pic\.g)?$", value, flags=re.I):
        if _RMU_DETAIL_SUFFIX_RE.search(value):
            rendered = re.sub(r"RMU(?=\.(?:sln|com)\.pic\.g$)", name, value, flags=re.I)
        else:
            rendered = re.sub(r"RMU$", name, value, flags=re.I) + _RMU_DETAIL_SUFFIX
    elif _RMU_DETAIL_SUFFIX_RE.search(value):
        # A concrete sample filename: the final '-' token is the sample RMU.
        match = re.fullmatch(r"(.+)-([^-]+)\.(?:sln|com)\.pic\.g", value, flags=re.I)
        if not match:
            raise ValueError(
                "单文件完整样例应类似 JED-NTH-ABH-AH303-34661.sln.pic.g，"
                "程序会把最后一段样例 RMU 替换为当前识别到的 RMU。"
            )
        rendered = f"{match.group(1)}-{name}{_RMU_DETAIL_SUFFIX}"
    else:
        # Fixed prefix form, e.g. JED-NTH-ABH-AH303.
        rendered = f"{value.rstrip('-')}-{name}{_RMU_DETAIL_SUFFIX}"
    return _validate_ahref_filename(rendered, label="单文件 Poke ahref")


def render_batch_rmu_rule(source_file: Path, rule: str, rmu_name: str) -> str:
    """Render batch naming; FEEDER is always derived from each source filename.

    The simplest rule is a fixed prefix such as ``JED-NTH-ABH-AH3``.  The engine
    automatically appends ``FEEDER-RMU.sln.pic.g``.  Advanced/site-specific
    patterns can use ``{FEEDER}`` and ``{RMU}``, case-insensitively.
    """
    feeder = extract_batch_feeder(source_file)
    value = _clean_rule(rule, label="批处理详情图规则")
    name = (rmu_name or "").strip()
    if not name:
        raise ValueError("RMU 名称为空，无法生成详情图文件名。")

    fields = [item.lower() for item in re.findall(r"\{([A-Za-z0-9_]+)\}", value)]
    if not fields:
        # User supplies only the stable site/feeder prefix part, e.g. ...-AH3.
        prefix = _RMU_DETAIL_SUFFIX_RE.sub("", value).rstrip("-")
        rendered = f"{prefix}{feeder}-{name}{_RMU_DETAIL_SUFFIX}"
        return _validate_ahref_filename(rendered, label="批处理 Poke ahref")

    allowed = {"feeder", "rmu", "region1", "region2", "station"}
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise ValueError("批处理详情图规则包含未知字段：" + ", ".join("{" + item + "}" for item in unknown))
    if "feeder" not in fields or "rmu" not in fields:
        raise ValueError("批处理模板必须同时包含 {FEEDER} 和 {RMU}，避免不同馈线或不同 RMU 生成相同 ahref。")

    values = {"feeder": feeder, "rmu": name}
    if set(fields) & {"region1", "region2", "station"}:
        values.update(_parse_auto_main_parts(source_file))

    def replace(match: re.Match[str]) -> str:
        return values[match.group(1).lower()]

    rendered = re.sub(r"\{([A-Za-z0-9_]+)\}", replace, value)
    return _validate_ahref_filename(rendered, label="批处理 Poke ahref")


def template_uses_facname(rule: str) -> bool:
    """Return True when the user template explicitly asks for FACNAME."""
    value = _clean_rule(rule, label="智能 RMU Poke ahref 模板")
    return bool(re.search(r"\{facname\}", value, flags=re.I)) or bool(
        re.search(r"(?<![A-Za-z0-9])FACNAME(?![A-Za-z0-9])", value, flags=re.I)
    )


def render_facname_rmu_rule(rule: str, fac_name: str, rmu_name: str) -> str:
    """Render the user-specified ahref template using only FACNAME and RMU.

    This is the v2.18.70 authoritative naming path used by the standalone RMU
    Poke module for both single-file and batch processing.  No part of the
    source filename is parsed or guessed.  The user controls every literal part
    of the output filename and only marks the positions that should be replaced.

    Supported placeholders (case-insensitive):
      * ``{FACNAME}`` or standalone ``FACNAME`` (optional)
      * ``{RMU}`` or standalone ``RMU`` (required)

    FACNAME is optional so a single-file rule may hard-code a known value such
    as ``AH303`` and then only replace RMU. When the template does not contain
    FACNAME, the caller does not need the source G to expose facName at all.
    RMU is mandatory because one source file may contain multiple intelligent
    cabinets and every generated ahref must remain unique per RMU.
    """
    value = _clean_rule(rule, label="智能 RMU Poke ahref 模板")
    name = (rmu_name or "").strip()
    fac = (fac_name or "").strip()
    if not name:
        raise ValueError("RMU 名称为空，无法生成详情图文件名。")
    if re.search(r'[<>:"/\\|?*]', name):
        raise ValueError(f"RMU 名称含 Windows 文件名非法字符：{name!r}")

    fields = [item.lower() for item in re.findall(r"\{([A-Za-z0-9_]+)\}", value)]
    unknown = sorted(set(fields) - {"facname", "rmu"})
    if unknown:
        raise ValueError(
            "Poke ahref 模板只支持 {FACNAME} 和 {RMU}，发现未知字段："
            + ", ".join("{" + item + "}" for item in unknown)
        )

    has_rmu = bool(re.search(r"\{rmu\}", value, flags=re.I)) or bool(
        re.search(r"(?<![A-Za-z0-9])RMU(?![A-Za-z0-9])", value, flags=re.I)
    )
    if not has_rmu:
        raise ValueError(
            "Poke ahref 模板必须指定 RMU 位置，请使用 {RMU}（推荐）或独立的 RMU 字段。"
        )

    has_facname = bool(re.search(r"\{facname\}", value, flags=re.I)) or bool(
        re.search(r"(?<![A-Za-z0-9])FACNAME(?![A-Za-z0-9])", value, flags=re.I)
    )
    if has_facname:
        if not fac:
            raise ValueError(
                "当前 G 文件根节点 facName 为空，无法替换模板中的 {FACNAME}。"
            )
        if re.search(r'[<>:"/\\|?*]', fac):
            raise ValueError(f"G 根节点 facName 含 Windows 文件名非法字符：{fac!r}")

    rendered = re.sub(r"\{facname\}", fac, value, flags=re.I)
    rendered = re.sub(r"\{rmu\}", name, rendered, flags=re.I)
    rendered = re.sub(
        r"(?<![A-Za-z0-9])FACNAME(?![A-Za-z0-9])", fac, rendered, flags=re.I
    )
    rendered = re.sub(
        r"(?<![A-Za-z0-9])RMU(?![A-Za-z0-9])", name, rendered, flags=re.I
    )
    return _validate_ahref_filename(rendered, label="智能 RMU Poke ahref")


def _validate_manual_detail_prefix(prefix: str) -> str:
    """Legacy compatibility for pre-v2.18.69 saved prefix/sample values."""
    value = _clean_rule(prefix, label="Poke 详情图前缀")
    if re.search(r'[<>:"/\\|?*]', value):
        raise ValueError(f"Poke 详情图前缀含 Windows 文件名非法字符：{value!r}")
    parts = value.split("-")
    if len(parts) != 4 or any(not part for part in parts) or not re.fullmatch(r"AH3\d+", parts[-1], flags=re.I):
        raise ValueError(
            "Poke 详情图前缀不符合旧版要求，应为‘区域-区域-站点-AH3+馈线号’，"
            "例如 JED-NTH-ABH-AH303。"
        )
    return value


def build_rmu_detail_prefix(source_file: Path, target_override: str = "") -> str:
    """Legacy automatic prefix helper retained for API/tests compatibility."""
    override = (target_override or "").strip()
    if override and "{" not in override:
        sample = override.replace("\\", "/").rsplit("/", 1)[-1].strip().strip('"').strip("'")
        match = re.fullmatch(r"(.+)-([^-]+)\.(?:sln|com)\.pic\.g", sample, flags=re.I)
        if match:
            return _validate_manual_detail_prefix(match.group(1))
        return _validate_manual_detail_prefix(sample)

    parts = _parse_auto_main_parts(source_file)
    return f"{parts['region1']}-{parts['region2']}-{parts['station']}-AH3{parts['feeder']}"


_CUSTOM_TEMPLATE_FIELDS = frozenset({"region1", "region2", "station", "feeder", "rmu"})


def _render_custom_detail_template(source_file: Path, template: str, rmu_name: str) -> str:
    """Legacy v2.18.68 custom-template renderer."""
    value = (template or "").strip().strip('"').strip("'")
    if not value:
        raise ValueError("自定义 Poke ahref 模板为空。")
    if "{rmu}" not in value:
        raise ValueError("自定义 Poke ahref 模板必须包含 {rmu}。")
    fields = set(re.findall(r"\{([A-Za-z0-9_]+)\}", value))
    unknown = sorted(fields - _CUSTOM_TEMPLATE_FIELDS)
    if unknown:
        raise ValueError("自定义 Poke ahref 模板包含未知字段：" + ", ".join("{" + item + "}" for item in unknown))
    values = {"rmu": rmu_name}
    if fields & {"region1", "region2", "station", "feeder"}:
        values.update(_parse_auto_main_parts(source_file))
    rendered = value.format(**values)
    return _validate_ahref_filename(rendered, label="自定义 Poke ahref")


def build_rmu_detail_filename(
    source_file: Path,
    fac_name_or_rmu_name: str,
    rmu_name: str | None = None,
    *,
    target_override: str = "",
    naming_mode: str = "",
    naming_rule: str = "",
) -> str:
    """Build one intelligent-RMU detail-view ahref.

    v2.18.69 modes:
      * ``single``: use the user-specified fixed rule/sample and do not validate
        the source G filename at all.
      * ``batch``: validate/extract FEEDER from each source G filename and apply
        the batch rule independently for every file.

    ``target_override`` preserves the v2.18.68 API for older callers/tests.
    """
    name = (rmu_name if rmu_name is not None else fac_name_or_rmu_name or "").strip()
    if not name:
        raise ValueError("RMU 名称为空，无法生成详情图文件名。")
    if re.search(r'[<>:"/\\|?*]', name):
        raise ValueError(f"RMU 名称含 Windows 文件名非法字符：{name!r}")

    mode = (naming_mode or "").strip().lower()
    if mode == "database_prefix":
        prefix = (fac_name_or_rmu_name or "").strip() if rmu_name is not None else ""
        if not prefix:
            raise ValueError("数据库馈线完整名称为空，无法生成智能 RMU Poke ahref。")
        if re.search(r'[<>:"/\\|?*]', prefix):
            raise ValueError(f"数据库馈线完整名称含 Windows 文件名非法字符：{prefix!r}")
        return _validate_ahref_filename(f"{prefix}-{name}{_RMU_DETAIL_SUFFIX}", label="智能 RMU Poke ahref")
    if mode == "facname_template":
        # Legacy/manual compatibility path.
        fac = (fac_name_or_rmu_name or "").strip() if rmu_name is not None else ""
        return render_facname_rmu_rule(naming_rule, fac, name)
    if mode == "single":
        return render_single_rmu_rule(naming_rule, name)
    if mode == "batch":
        return render_batch_rmu_rule(source_file, naming_rule, name)
    if mode:
        raise ValueError(f"未知 Poke ahref 命名模式：{naming_mode!r}")

    # Legacy behavior for older internal/API calls.
    override = (target_override or "").strip()
    if "{" in override:
        return _render_custom_detail_template(source_file, override, name)
    prefix = build_rmu_detail_prefix(source_file, override)
    return f"{prefix}-{name}{_RMU_DETAIL_SUFFIX}"


def _find_layer_for_rect(root: ET.Element, rect_id: str) -> ET.Element | None:
    for layer in direct_layers(root):
        for element in layer.iter():
            if local_name(element.tag) == "rect" and (element.get("id") or "").strip() == rect_id:
                return layer
    return None


def _find_name_element(
    root: ET.Element,
    rmu_name: str,
    rect_box: _Box,
    name_text_id: str = "",
) -> ET.Element | None:
    """Find the exact visible RMU name text nearest this RMU rect.

    RMU identity/name selection itself remains delegated to identify_rmus(); this
    helper only locates the already-recognized name Text so the Poke click area
    can precisely wrap the cabinet name rather than the whole cabinet.  The
    lookup repeats the same fixed rule: only Text above the top frame edge is
    eligible, and the nearest candidate wins.  This is important when the same
    rendered value appears more than once in one drawing.
    """
    # Prefer the exact Text selected by RMU identification when an XML id is
    # available.  This preserves concrete-Text ownership even when equal text
    # content appears more than once in the same drawing.
    wanted_id = (name_text_id or "").strip()
    if wanted_id:
        for element in root.iter():
            if local_name(element.tag) != "Text":
                continue
            if (element.get("id") or "").strip() != wanted_id:
                continue
            if (element.get("ts") or "").strip() != rmu_name:
                continue
            if _box(element) is not None:
                return element

    candidates: list[tuple[float, ET.Element]] = []
    for element in root.iter():
        if local_name(element.tag) != "Text":
            continue
        if (element.get("ts") or "").strip() != rmu_name:
            continue
        box = _box(element)
        if box is None:
            continue
        gap = rect_box.top - box.bottom
        if not (
            -20.0 <= gap <= 120.0
            and box.center_y < rect_box.top
            and rect_box.left - 20.0 <= box.center_x <= rect_box.right + 20.0
        ):
            continue
        score = max(0.0, gap) + abs(box.center_x - rect_box.center_x) * 0.08
        candidates.append((score, element))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) <= 1e-6:
        return None
    return candidates[0][1]


def _intersects(a: _Box, b: _Box) -> bool:
    return not (a.right <= b.left or b.right <= a.left or a.bottom <= b.top or b.bottom <= a.top)


def _contains_center(container: _Box, inner: _Box) -> bool:
    cx = (inner.left + inner.right) / 2.0
    cy = (inner.top + inner.bottom) / 2.0
    return container.left <= cx <= container.right and container.top <= cy <= container.bottom


def _area(box: _Box) -> float:
    return max(0.0, box.width) * max(0.0, box.height)


def _overlap_area(a: _Box, b: _Box) -> float:
    left = max(a.left, b.left)
    top = max(a.top, b.top)
    right = min(a.right, b.right)
    bottom = min(a.bottom, b.bottom)
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _candidate_related_pokes(
    layer: ET.Element,
    *,
    target_file: str,
    rmu_name: str,
    name_box: _Box,
) -> list[ET.Element]:
    """Return only RMU-name-related pokes for this intelligent cabinet.

    Unrelated Pokes are ignored. Existing RMU Pokes are recognized primarily by
    same-layer target match or by geometric overlap/containment with the RMU
    name text box.
    """
    matches: list[ET.Element] = []
    seen: set[int] = set()
    target_key = target_file.casefold()
    name_key = rmu_name.casefold()

    def add_candidate(element: ET.Element) -> None:
        key = id(element)
        if key not in seen:
            matches.append(element)
            seen.add(key)

    for element in layer:
        if local_name(element.tag) != 'poke':
            continue
        if (element.get('gfs_device_poke') or '') == '1' or (element.get('gfs_station_poke') or '') == '1':
            continue
        if (element.get('ahref') or '').strip().casefold() == target_key:
            add_candidate(element)
            continue
        if (element.get('gfs_rmu_name') or '').strip().casefold() == name_key:
            add_candidate(element)
            continue
        poke_box = _box(element)
        if poke_box is None:
            continue
        if _intersects(poke_box, name_box) or _contains_center(poke_box, name_box):
            add_candidate(element)
    return matches


def _choose_primary_poke(
    candidates: list[ET.Element],
    *,
    target_file: str,
    name_box: _Box,
) -> ET.Element:
    target_key = target_file.casefold()

    def score(element: ET.Element) -> tuple[float, float, str]:
        poke_box = _box(element) or name_box
        exact_target = 0.0 if (element.get('ahref') or '').strip().casefold() == target_key else 1.0
        overlap_penalty = -_overlap_area(poke_box, name_box)
        area_penalty = abs(_area(poke_box) - _area(name_box))
        elem_id = (element.get('id') or '')
        return (exact_target, overlap_penalty + area_penalty * 1e-6, elem_id)

    return sorted(candidates, key=score)[0]


def _all_used_ids(root: ET.Element) -> set[str]:
    return {
        value
        for element in root.iter()
        if (value := (element.get("id") or "").strip())
    }


def _allocate_poke_id(root: ET.Element, used_ids: set[str]) -> str:
    valid: list[int] = []
    for element in root.iter():
        if local_name(element.tag) != "poke":
            continue
        value = (element.get("id") or "").strip()
        if value.isdigit() and len(value) == 8 and value.startswith("17"):
            valid.append(int(value))
    candidate = (max(valid) + 1) if valid else 17000001
    while str(candidate) in used_ids or not str(candidate).startswith("17") or len(str(candidate)) != 8:
        candidate += 1
        if candidate > 17999999:
            raise ValueError("<poke> ID 17xxxxxx 可用范围已耗尽。")
    value = str(candidate)
    used_ids.add(value)
    return value


_RMU_POKE_DYNAMIC_ATTRS = frozenset({
    "id", "ahref", "x", "y", "w", "h", "gfs_rmu_poke", "gfs_rmu_name",
    "gfs_rmu_text_id",
})
_FRAME_POKE_METADATA = frozenset({
    "gfs_frame_role", "gfs_frame_component", "gfs_frame_type"
})


def _new_poke(root: ET.Element, poke_id: str) -> ET.Element:
    """Create an RMU Poke from the dedicated RMU canonical attributes only.

    Do not clone an arbitrary existing ``<poke>`` from the drawing.  Station
    overview files can contain title-block/frame Pokes whose runtime attributes
    (for example ``Pos=2`` and ``gfs_frame_*`` metadata) are not valid for an
    RMU jump.  Copying such an object produced Pokes with a correct ``ahref``
    but an invalid click behaviour.
    """
    poke = ET.Element("poke", dict(_CANONICAL_POKE_ATTRS))
    poke.set("id", poke_id)
    return poke


def _repair_contaminated_rmu_poke(poke: ET.Element) -> bool:
    """Reset a previously mis-cloned frame/title Poke to the RMU baseline.

    v2.18.96 could copy a title-block Poke when creating a new RMU jump.  Such
    objects are identifiable by ``gfs_frame_*`` metadata.  Preserve only the
    RMU-specific dynamic fields and rebuild all runtime/style attributes from
    the dedicated RMU canonical set, so re-running Poke processing repairs
    already affected G files as well as preventing new contamination.
    """
    if not any(key in poke.attrib for key in _FRAME_POKE_METADATA):
        return False

    dynamic = {key: poke.get(key, "") for key in _RMU_POKE_DYNAMIC_ATTRS if key in poke.attrib}
    desired = dict(_CANONICAL_POKE_ATTRS)
    desired.update(dynamic)
    if poke.attrib == desired:
        return False
    poke.attrib.clear()
    poke.attrib.update(desired)
    return True


def _ensure_jump_attributes(
    poke: ET.Element,
    *,
    target_file: str,
    rmu_name: str,
    box: _Box,
    name_text_id: str = "",
) -> bool:
    changed = _repair_contaminated_rmu_poke(poke)
    desired = {
        "ahref": target_file,
        # RMU jump Pokes are normal drawing Pokes, never title/frame objects.
        "Pos": "0",
        "switchapp": "1",
        "switchappflag": "1",
        "p_ShowModeMask": "3",
        "PlaneState0": "1",
        "isDisplay": "1",
        "opacity": "1",
        # Poke line color is normalized to blue.  The G file stores the same line
        # color in both the numeric lc field and the hexadecimal lcc field.
        "lc": "0,0,255",
        "lcc": "#0000ff",
        # User-confirmed G-property mapping: Rectangular appearance = Invisible.
        # Keep both duplicated fields synchronized for old/new editor builds.
        "RectStyle": "0",
        "p_RectStyle": "0",
        "x": _number(box.left),
        "y": _number(box.top),
        "w": _number(box.width),
        "h": _number(box.height),
        "gfs_rmu_poke": "1",
        "gfs_rmu_name": rmu_name,
        "gfs_rmu_text_id": (name_text_id or "").strip(),
    }
    # Even for older files that only carry one stray frame marker, do not leave
    # title-block metadata attached to an RMU jump object.
    for key in _FRAME_POKE_METADATA:
        if key in poke.attrib:
            poke.attrib.pop(key, None)
            changed = True
    for key, value in desired.items():
        if poke.get(key) != value:
            poke.set(key, value)
            changed = True
    return changed


def _move_poke_to_background(layer: ET.Element, poke: ET.Element) -> bool:
    """Place RMU Poke in the Layer's Poke background band.

    The user's working examples place Poke objects before normal drawing objects.
    This keeps the click region behind the RMU name/devices instead of painting or
    intercepting them as a front-layer object.
    """
    children = list(layer)
    if poke not in children:
        # New object: insert after any existing leading Pokes.
        insert_at = 0
        while insert_at < len(children) and local_name(children[insert_at].tag) == "poke":
            insert_at += 1
        layer.insert(insert_at, poke)
        return True

    old_index = children.index(poke)
    # Desired position is inside the leading contiguous Poke band.
    leading_end = 0
    while leading_end < len(children) and local_name(children[leading_end].tag) == "poke":
        leading_end += 1
    if old_index < leading_end:
        return False
    layer.remove(poke)
    layer.insert(leading_end, poke)
    return True


def apply_smart_rmu_pokes(
    tree: ET.ElementTree,
    file_path: Path,
    identification: RmuIdentificationResult,
    *,
    target_override: str = "",
    naming_mode: str = "",
    naming_rule: str = "",
    database_prefixes: dict[str, str] | None = None,
    database_resolution_errors: dict[str, str] | None = None,
) -> SmartRmuPokeResult:
    """Add/update Poke jump regions for intelligent RMUs identified upstream.

    This function never decides what is an RMU and never decides whether it is
    SMART/SMR.  It consumes the existing identify_rmus(..., smart_in_type=True)
    result as the sole source of truth.
    """
    result = SmartRmuPokeResult(file_path=file_path)
    root = tree.getroot()
    mode = (naming_mode or "").strip().lower()
    needs_facname = mode == "facname_template" and template_uses_facname(naming_rule)
    fac_name = (root.get("facName") or "").strip() if needs_facname else ""
    database_prefix = (naming_rule or "").strip() if mode == "database_prefix" else ""
    per_rmu_prefixes = {str(k).strip().casefold(): str(v).strip() for k, v in (database_prefixes or {}).items()}
    per_rmu_errors = {str(k).strip().casefold(): str(v).strip() for k, v in (database_resolution_errors or {}).items()}
    intelligent = [item for item in identification.items if bool(item.smart_count)]
    result.intelligent_rmu_count = len(intelligent)
    if not intelligent:
        return result

    # Legacy/manual modes can be validated once for the whole file.  The
    # database_rmu_name mode is intentionally per-cabinet: each RMU can belong
    # to a different feeder, so one failed DB lookup must not block the others.
    if mode != "database_rmu_name":
        try:
            for item in intelligent:
                name = (item.name or "").strip()
                if name:
                    build_rmu_detail_filename(
                        file_path,
                        (database_prefix if mode == "database_prefix" else fac_name) if mode in {"database_prefix", "facname_template"} else name,
                        name if mode in {"database_prefix", "facname_template"} else None,
                        target_override=target_override, naming_mode=naming_mode, naming_rule=naming_rule,
                    )
        except ValueError as exc:
            result.skipped_count = len(intelligent)
            reason = f"Poke ahref 命名预检查失败：{exc}"
            result.warnings.append(reason)
            for item in intelligent:
                result.records.append(SmartRmuPokeRecord(
                    rmu_name=(item.name or "").strip(),
                    rect_id=item.rect_id or "",
                    name_text_id=item.name_text_id,
                    action="skipped",
                    reason=reason,
                ))
            return result

    name_counts = Counter((item.name or "").strip().casefold() for item in intelligent if (item.name or "").strip())
    used_ids = _all_used_ids(root)

    # Existing jump targets are matched case-insensitively.  A duplicate target
    # is unsafe because one detail filename must resolve to one RMU only.
    pokes_by_target: dict[str, list[ET.Element]] = {}
    for element in root.iter():
        if local_name(element.tag) != "poke":
            continue
        target = (element.get("ahref") or "").strip()
        if target:
            pokes_by_target.setdefault(target.casefold(), []).append(element)

    for item in intelligent:
        name = (item.name or "").strip()
        if not name:
            result.skipped_count += 1
            reason = f"rect ID {item.rect_id or '<无ID>'} 已识别为智能 RMU，但柜名未识别，无法生成 Poke 跳转。"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name="",
                rect_id=item.rect_id or "",
                name_text_id=item.name_text_id,
                action="skipped",
                reason=reason,
            ))
            continue
        if name_counts[name.casefold()] > 1:
            result.skipped_count += 1
            reason = f"智能 RMU 柜名 {name!r} 在同一文件中重复，目标详情图文件名无法唯一，已跳过 Poke。"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name=name,
                rect_id=item.rect_id or "",
                name_text_id=item.name_text_id,
                action="skipped",
                reason=reason,
            ))
            continue
        if not item.rect_id:
            result.skipped_count += 1
            reason = f"智能 RMU {name!r} 缺少 rect ID，无法安全定位 Poke 所属 Layer。"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name=name,
                rect_id=item.rect_id or "",
                name_text_id=item.name_text_id,
                action="skipped",
                reason=reason,
            ))
            continue

        rect_box = _Box(item.rect_x, item.rect_y, item.rect_x + item.rect_w, item.rect_y + item.rect_h)
        if rect_box.width <= 0 or rect_box.height <= 0:
            result.skipped_count += 1
            reason = f"智能 RMU {name!r} 的 rect 几何无效，已跳过 Poke。"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name=name, rect_id=item.rect_id, action="skipped", reason=reason,
                name_text_id=item.name_text_id,
            ))
            continue
        layer = _find_layer_for_rect(root, item.rect_id)
        if layer is None:
            result.skipped_count += 1
            reason = f"智能 RMU {name!r}（rect {item.rect_id}）无法定位所属 Layer，已跳过 Poke。"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name=name,
                rect_id=item.rect_id,
                name_text_id=item.name_text_id,
                action="skipped",
                reason=reason,
            ))
            continue
        try:
            if mode == "database_rmu_name":
                lookup_key = name.casefold()
                if lookup_key in per_rmu_errors:
                    raise LookupError(per_rmu_errors[lookup_key])
                prefix = per_rmu_prefixes.get(lookup_key, "")
                if not prefix:
                    raise LookupError(
                        f"数据库未根据 RMU 名称 {name!r} 解析到所属馈线完整业务名。"
                    )
                target_file = build_rmu_detail_filename(
                    file_path,
                    prefix,
                    name,
                    naming_mode="database_prefix",
                    naming_rule=prefix,
                )
            else:
                target_file = build_rmu_detail_filename(
                    file_path,
                    (database_prefix if mode == "database_prefix" else fac_name) if mode in {"database_prefix", "facname_template"} else name,
                    name if mode in {"database_prefix", "facname_template"} else None,
                    target_override=target_override, naming_mode=naming_mode, naming_rule=naming_rule,
                )
        except (ValueError, LookupError) as exc:
            result.skipped_count += 1
            reason = f"智能 RMU {name!r}：{exc}"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name=name,
                rect_id=item.rect_id,
                name_text_id=item.name_text_id,
                action="skipped",
                reason=reason,
            ))
            continue

        name_element = _find_name_element(root, name, rect_box, item.name_text_id)
        name_box = _box(name_element) if name_element is not None else None
        if name_box is None:
            result.skipped_count += 1
            reason = f"智能 RMU {name!r} 未能唯一定位柜名 Text，无法安全生成只包住柜名的 Poke。"
            result.warnings.append(reason)
            result.records.append(SmartRmuPokeRecord(
                rmu_name=name,
                rect_id=item.rect_id,
                name_text_id=item.name_text_id,
                target_file=target_file,
                action="skipped",
                reason=reason,
            ))
            continue

        related_pokes = _candidate_related_pokes(layer, target_file=target_file, rmu_name=name, name_box=name_box)
        for poke in list(related_pokes):
            current_target = (poke.get('ahref') or '').strip()
            if current_target:
                pokes_by_target.get(current_target.casefold(), []).remove(poke)
                if not pokes_by_target.get(current_target.casefold()):
                    pokes_by_target.pop(current_target.casefold(), None)

        result.eligible_rmu_count += 1
        if related_pokes:
            poke = _choose_primary_poke(related_pokes, target_file=target_file, name_box=name_box)
            removed = 0
            for extra in related_pokes:
                if extra is poke:
                    continue
                layer.remove(extra)
                removed += 1
            changed = _ensure_jump_attributes(
                poke,
                target_file=target_file,
                rmu_name=name,
                box=name_box,
                name_text_id=item.name_text_id,
            )
            moved = _move_poke_to_background(layer, poke)
            pokes_by_target.setdefault(target_file.casefold(), []).append(poke)
            if removed:
                result.warnings.append(f"智能 RMU {name!r} 发现 {removed + 1} 个相关 Poke，已删除多余 {removed} 个，仅保留 1 个。")
            action = "updated" if (changed or moved or removed) else "unchanged"
            if action == "updated":
                result.updated_count += 1
            else:
                result.unchanged_count += 1
        else:
            poke_id = _allocate_poke_id(root, used_ids)
            poke = _new_poke(root, poke_id)
            _ensure_jump_attributes(
                poke,
                target_file=target_file,
                rmu_name=name,
                box=name_box,
                name_text_id=item.name_text_id,
            )
            _move_poke_to_background(layer, poke)
            pokes_by_target.setdefault(target_file.casefold(), []).append(poke)
            result.added_count += 1
            action = "added"

        result.changes.append(SmartRmuPokeChange(
            rmu_name=name,
            rect_id=item.rect_id,
            poke_id=(poke.get("id") or "").strip(),
            target_file=target_file,
            action=action,
            x=name_box.left,
            y=name_box.top,
            w=name_box.width,
            h=name_box.height,
        ))
        if action == "added":
            reason = "公共 RMU 识别成功，未找到可复用 Poke，已新增并写入目标 ahref。"
        elif action == "updated":
            reason = "公共 RMU 识别成功，已复用现有 Poke 并更新目标/Line Color/几何或清理重复 Poke。"
        else:
            reason = "公共 RMU 识别成功，现有 Poke 已符合目标，无需修改。"
        result.records.append(SmartRmuPokeRecord(
            rmu_name=name,
            rect_id=item.rect_id,
            name_text_id=item.name_text_id,
            poke_id=(poke.get("id") or "").strip(),
            target_file=target_file,
            action=action,
            reason=reason,
        ))

    return result
