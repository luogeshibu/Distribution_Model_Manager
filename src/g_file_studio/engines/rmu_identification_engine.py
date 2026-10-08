from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from g_file_studio.engines.id_engine import direct_layer_elements, local_name
from g_file_studio.engines.poke_text_rules import text_instance_key


RMU_NAME_MAX_DISTANCE = 200.0


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
class RmuIdentification:
    rect_id: str
    name: str
    name_text_id: str
    name_position: str
    rmu_type: str
    l_count: int
    t_count: int
    smart_count: int
    confidence: str
    rect_x: float
    rect_y: float
    rect_w: float
    rect_h: float
    smart_source: str = ""
    type_source: str = ""
    text_yq_type: str = ""
    devref_type: str = ""
    type_cross_check: str = "N/A"
    type_validation_status: str = "WARN"
    type_cross_note: str = ""
    name_text_key: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class RmuIdentificationResult:
    file_path: Path
    cabinet_count: int = 0
    named_count: int = 0
    typed_count: int = 0
    ambiguous_name_count: int = 0
    items: list[RmuIdentification] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GlobalTextOwner:
    """Global nearest equipment owner for one static Text label."""

    target_key: str
    text: ET.Element
    distance: float


_Y_LABEL_RE = re.compile(r"^Y\s*(\d+)$", re.I)
_Q_LABEL_RE = re.compile(r"^Q\s*(\d+)$", re.I)
_FIXED_RMU_NAME_EXCLUSIONS = (
    "SMART",
    "SMR",
    "SFI",
    "NOP",
    "N.O.P",
    "N-O-P",
    "N_O_P",
    "DAS/OK",
    "DAS",
    "OK",
)


def _float(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name, default))
    except (TypeError, ValueError):
        return default


def _box(element: ET.Element) -> _Box | None:
    width = _float(element, "w")
    height = _float(element, "h")
    if width <= 0 or height <= 0:
        return None
    left = _float(element, "x")
    top = _float(element, "y")
    return _Box(left, top, left + width, top + height)


def _point_to_box_distance(x: float, y: float, box: _Box) -> float:
    dx = max(box.left - x, 0.0, x - box.right)
    dy = max(box.top - y, 0.0, y - box.bottom)
    return (dx * dx + dy * dy) ** 0.5


def assign_global_text_owners(
    texts: list[ET.Element],
    targets: list[tuple[str, ET.Element]],
    *,
    target_anchors: dict[str, tuple[tuple[float, float], ...]] | None = None,
    score_adjuster: Callable[[ET.Element, str, float], float] | None = None,
) -> dict[int, GlobalTextOwner]:
    """Assign each static Text to its nearest equipment target globally.

    This is shared by RMU recognition and the complete G-content inventory.
    Callers provide only real equipment targets; topology and presentation objects
    must be filtered before calling.  An exact geometric tie is left unassigned
    instead of guessed.  Electrical anchor points can be supplied for symbols
    whose XML bounding box is larger than the rendered device body.  An optional
    score adjuster can add a caller-owned semantic tie-breaker (for example a
    learned Text color convention) without changing the raw distance reported to
    the caller.
    """
    valid_targets: list[tuple[str, _Box]] = []
    for target_key, target in targets:
        target_box = _box(target)
        if target_box is not None:
            valid_targets.append((str(target_key), target_box))
    if not valid_targets:
        return {}

    owners: dict[int, GlobalTextOwner] = {}
    for text in texts:
        text_box = _box(text)
        if text_box is None:
            continue
        distances: list[tuple[float, float, str]] = []
        for target_key, target_box in valid_targets:
            anchors = (target_anchors or {}).get(target_key)
            if anchors:
                raw_distance = min(
                    _point_to_box_distance(x, y, text_box)
                    for x, y in anchors
                )
            else:
                raw_distance = _point_to_box_distance(
                    text_box.center_x,
                    text_box.center_y,
                    target_box,
                )
            adjusted_distance = (
                score_adjuster(text, target_key, raw_distance)
                if score_adjuster is not None
                else raw_distance
            )
            distances.append((adjusted_distance, raw_distance, target_key))
        # A caller may use color/character conventions as a soft tie-breaker, but
        # a clearly nearer graphical device must remain the owner.  The bounded
        # 48-unit window still lets learned styles resolve adjacent labels without
        # allowing a distant same-color target to steal a name.
        if score_adjuster is not None:
            nearest_raw_distance = min(item[1] for item in distances)
            distances = [
                item for item in distances
                if item[1] <= nearest_raw_distance + 48.0
            ]
        distances.sort(key=lambda item: (item[0], item[1], item[2]))
        best_score, best_distance, best_target = distances[0]
        if len(distances) > 1 and abs(best_score - distances[1][0]) <= 1e-6:
            continue
        owners[id(text)] = GlobalTextOwner(
            target_key=best_target,
            text=text,
            distance=round(best_distance, 6),
        )
    return owners


def _center_inside(element: ET.Element, outer: _Box, tolerance: float = 0.5) -> bool:
    box = _box(element)
    if box is None:
        return False
    return (
        outer.left - tolerance <= box.center_x <= outer.right + tolerance
        and outer.top - tolerance <= box.center_y <= outer.bottom + tolerance
    )


def _classify_switch_by_devref(element: ET.Element) -> str | None:
    """仅按图元文件名/devref 识别 L/T，用于与柜内 Y/Q 文字交叉校验。"""
    if local_name(element.tag) != "CBreakerDis":
        return None
    devref = re.sub(r"[^A-Z0-9]+", "_", (element.get("devref") or "").upper())
    if any(token in devref for token in ("LOAD_BREAKER", "LOADBREAKERSWITCH", "RMU_LBS")):
        return "L"
    if any(token in devref for token in ("CIRCUIT_BREAKER", "CIRCUITBREAKER", "RMU_BRK")):
        return "T"
    return None


def _classify_switch(element: ET.Element) -> str | None:
    """Compatibility wrapper using only the graphical icon reference."""
    return _classify_switch_by_devref(element)


def _is_smart_device(element: ET.Element) -> bool:
    devref = (element.get("devref") or "").upper()
    if "NON-SMART" in devref or "NO-SMART" in devref:
        return False
    return "SMART" in devref or "RMU_LBS_S" in devref or "RMU_BRK_S" in devref


def _is_green_name_text(element: ET.Element) -> bool:
    """判断 Text 是否为绿色。绿色仅用于多候选柜名消歧，不再作为硬条件。"""
    lcc = (element.get("lcc") or "").strip().lower()
    lc = re.sub(r"\s+", "", (element.get("lc") or "").strip())
    return lcc == "#00ff00" or lc == "0,255,0"


def _normalize_excluded_name(value: str) -> str:
    """Normalize one user-specified RMU-name exclusion for exact matching."""
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def parse_name_exclusions(raw: str) -> tuple[str, ...]:
    """Parse comma/semicolon/newline separated exact RMU-name exclusions.

    Matching is whole-string, case-insensitive, and ignores surrounding/repeated
    whitespace.  It deliberately does NOT use substring matching, so excluding
    ``SFI`` will not exclude a legitimate name such as ``SFI-1201``.
    """
    values = re.split(r"[,;，；\n\r]+", raw or "")
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", value.strip())
        key = _normalize_excluded_name(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return tuple(unique)


def parse_intelligent_markers(raw: str) -> tuple[str, ...]:
    """Parse user-configured intelligent-RMU Text markers.

    Values are comma/semicolon/newline separated and matched as whole Text
    values, case-insensitively.  SMART/SMR remain the default for backward
    compatibility.  The same marker values are automatically excluded from RMU
    name candidates so a marker such as NEWSMART cannot become a cabinet name.
    """
    values = re.split(r"[,;，；\n\r]+", raw or "")
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = re.sub(r"\s+", " ", value.strip())
        key = _normalize_excluded_name(cleaned)
        if cleaned and key and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return tuple(unique) if unique else ("SMART", "SMR")


def _valid_name_text(element: ET.Element, excluded_names: frozenset[str] = frozenset()) -> bool:
    """柜名候选的基础过滤。

    名称颜色不是硬条件。这里仅排除明确属于柜内设备/状态的短标签，
    其余数字、字母数字、带连字符的名称均允许参与距离匹配。
    用户配置的排除项只做完整字符串匹配，不做包含/模糊匹配。
    """
    value = (element.get("ts") or "").strip()
    if not value or not any(ch.isalnum() for ch in value):
        return False
    if _normalize_excluded_name(value) in excluded_names:
        return False
    compact = re.sub(r"\s+", "", value).upper()
    if _Y_LABEL_RE.fullmatch(compact) or _Q_LABEL_RE.fullmatch(compact):
        return False
    if compact in {"SMART", "SMR", "G", "I"}:
        return False
    return True


def _candidate_for_position(text: ET.Element, rect: _Box, position: str) -> tuple[float, float] | None:
    """Return (edge gap, perpendicular-axis offset) for one selected direction.

    The direction is a hard user constraint.  This deliberately mirrors the
    proven DMM RMU label geometry: 200 G-units maximum edge distance and 20
    G-units projection tolerance.  A Text may overlap the frame edge by up to
    20 units, but its center must still be on the requested side.
    """
    box = _box(text)
    if box is None:
        return None

    max_distance = RMU_NAME_MAX_DISTANCE
    edge_tolerance = 20.0

    if position == "top":
        gap = rect.top - box.bottom
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_y < rect.top
            and rect.left - edge_tolerance <= box.center_x <= rect.right + edge_tolerance
        ):
            return max(0.0, gap), abs(box.center_x - rect.center_x)
    elif position == "bottom":
        gap = box.top - rect.bottom
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_y > rect.bottom
            and rect.left - edge_tolerance <= box.center_x <= rect.right + edge_tolerance
        ):
            return max(0.0, gap), abs(box.center_x - rect.center_x)
    elif position == "left":
        gap = rect.left - box.right
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_x < rect.left
            and rect.top - edge_tolerance <= box.center_y <= rect.bottom + edge_tolerance
        ):
            return max(0.0, gap), abs(box.center_y - rect.center_y)
    elif position == "right":
        gap = box.left - rect.right
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_x > rect.right
            and rect.top - edge_tolerance <= box.center_y <= rect.bottom + edge_tolerance
        ):
            return max(0.0, gap), abs(box.center_y - rect.center_y)
    return None


def _candidate_score(
    item: tuple[float, float, str, str, str, bool],
    positions: tuple[str, ...],
) -> float:
    gap, axis_offset, position, _value, _text_id, _green = item
    # DMM-style geometry: edge distance dominates; axis offset only nudges the
    # choice.  Direction order is only a deterministic exact-tie breaker.
    return gap + axis_offset * 0.08 + positions.index(position) * 0.0001


def _all_candidates_for_rect(
    texts: list[ET.Element],
    rect: _Box,
    positions: tuple[str, ...],
    excluded_names: frozenset[str] = frozenset(),
) -> list[tuple[float, float, str, str, str, bool]]:
    """Collect candidates only from explicitly selected directions.

    The same Text can geometrically touch two selected directions near a corner;
    keep only its best direction for this cabinet so it still counts as ONE
    candidate name.
    """
    best_by_text: dict[str, tuple[float, float, str, str, str, bool]] = {}
    for text in texts:
        if not _valid_name_text(text, excluded_names):
            continue
        value = (text.get("ts") or "").strip()
        # Ownership is per concrete XML Text object, never per displayed value
        # and never dependent on an XML id being globally unique.  Therefore two
        # separate Text objects containing the same value (for example 000000)
        # remain two independent name candidates.
        text_key = f"__text_object_{id(text)}"
        green = _is_green_name_text(text)
        for position in positions:
            metric = _candidate_for_position(text, rect, position)
            if metric is None:
                continue
            item = (metric[0], metric[1], position, value, text_key, green)
            current = best_by_text.get(text_key)
            if current is None or _candidate_score(item, positions) < _candidate_score(current, positions):
                best_by_text[text_key] = item
    return list(best_by_text.values())


def _name_candidates_for_rect(
    texts: list[ET.Element],
    rect: _Box,
    positions: tuple[str, ...],
    excluded_names: frozenset[str] = frozenset(),
) -> list[tuple[float, float, str, str, str, bool]]:
    """Compatibility helper: candidates from selected directions only."""
    return _all_candidates_for_rect(texts, rect, positions, excluded_names)


def _assign_names_globally(
    texts: list[ET.Element],
    cabinets: list[tuple[str, _Box]],
    positions: tuple[str, ...],
    excluded_names: frozenset[str] = frozenset(),
) -> dict[str, tuple[str, str, str, list[str]]]:
    """Assign RMU names with strict direction and one-owner rules.

    This follows the reference Distribution Model Manager behaviour supplied by
    the user:
      1. inspect ONLY user-selected directions;
      2. one Text belongs to the nearest eligible RMU cabinet for that direction;
      3. if an RMU owns exactly one candidate, use it regardless of color;
      4. if it owns multiple candidates, choose the nearest GREEN candidate when
         any green candidate exists; otherwise choose the nearest candidate.
    No unselected direction and no metadata fallback participates.
    """
    rect_map = dict(cabinets)
    per_rect_raw: dict[str, list[tuple[float, float, str, str, str, bool]]] = {
        rect_id: _all_candidates_for_rect(texts, rect, positions, excluded_names)
        for rect_id, rect in cabinets
    }

    # Resolve one owner for every Text.  A candidate label cannot be reused by a
    # neighbouring cabinet.  Ownership is purely geometric; color never changes
    # ownership and is used only after ownership when an RMU has multiple names.
    owners: dict[str, tuple[str, float, tuple[float, float, str, str, str, bool]]] = {}
    for rect_id, items in per_rect_raw.items():
        for item in items:
            text_key = item[4]
            score = _candidate_score(item, positions)
            current = owners.get(text_key)
            if current is None or (score, rect_id) < (current[1], current[0]):
                owners[text_key] = (rect_id, score, item)

    owned_by_rect: dict[str, list[tuple[float, float, str, str, str, bool]]] = {
        rect_id: [] for rect_id, _rect in cabinets
    }
    for rect_id, _score, item in owners.values():
        owned_by_rect.setdefault(rect_id, []).append(item)

    result: dict[str, tuple[str, str, str, list[str]]] = {}
    for rect_id, _rect in cabinets:
        candidates = owned_by_rect.get(rect_id, [])
        candidates.sort(key=lambda item: (_candidate_score(item, positions), item[3], item[4]))
        if not candidates:
            result[rect_id] = ("", "", "未识别", [])
            continue

        warnings: list[str] = []
        if len(candidates) == 1:
            chosen = candidates[0]
            confidence = "高"
        else:
            greens = [item for item in candidates if item[5]]
            if greens:
                chosen = min(greens, key=lambda item: (_candidate_score(item, positions), item[3], item[4]))
                warnings.append("指定方向内存在多个柜名候选，按绿色优先选择")
            else:
                chosen = candidates[0]
                warnings.append("指定方向内存在多个柜名候选且无绿色名称，按最近位置选择")
            confidence = "中"

        _gap, _axis_offset, position, value, _text_key, _green = chosen
        result[rect_id] = (value, position, confidence, warnings)

    return result


def _assign_names_local_top(
    texts: list[ET.Element],
    cabinets: list[tuple[str, _Box]],
    excluded_names: frozenset[str] = frozenset(),
    positions: tuple[str, ...] = ("top",),
) -> dict[str, tuple[str, str, str, list[str], str, str]]:
    """Assign names by independent RMU-frame directional-band matching.

    RMU names are a property of the validated RMU frame, not of the nearest
    arbitrary equipment symbol in the whole drawing.  Build candidates for
    each frame directly from the narrow ``top`` geometry and resolve conflicts
    only between RMU frames.  This preserves the one-concrete-Text/one-device
    rule without allowing transformers, feeders, lines, or other symbols to
    claim an RMU name first.
    """
    positions = tuple(position for position in positions if position in _NAME_POSITIONS) or ("top",)
    per_rect_raw: dict[str, list[tuple[float, float, str, str, str, bool]]] = {
        rect_id: _all_candidates_for_rect(texts, rect, positions, excluded_names)
        for rect_id, rect in cabinets
    }

    # A name Text may geometrically fall in the top band of two neighbouring
    # frames.  It still belongs to exactly one RMU: the frame with the smaller
    # top-band score wins.  No non-RMU element participates in this decision.
    owners: dict[str, tuple[str, float, tuple[float, float, str, str, str, bool]]] = {}
    for rect_id, items in per_rect_raw.items():
        for item in items:
            text_key = item[4]
            score = _candidate_score(item, positions)
            current = owners.get(text_key)
            if current is None or (score, rect_id) < (current[1], current[0]):
                owners[text_key] = (rect_id, score, item)

    owned_by_rect: dict[str, list[tuple[float, float, str, str, str, bool]]] = {
        rect_id: [] for rect_id, _rect in cabinets
    }
    for rect_id, _score, item in owners.values():
        owned_by_rect.setdefault(rect_id, []).append(item)

    text_by_key = {f"__text_object_{id(text)}": text for text in texts}
    result: dict[str, tuple[str, str, str, list[str], str, str]] = {}
    for rect_id, _rect in cabinets:
        candidates = owned_by_rect.get(rect_id, [])
        candidates.sort(key=lambda item: (_candidate_score(item, positions), item[3], item[4]))
        if not candidates:
            result[rect_id] = ("", "", "未识别", [], "", "")
            continue

        warnings: list[str] = []
        if len(candidates) == 1:
            chosen = candidates[0]
            confidence = "高"
        else:
            # The selected direction is a hard constraint. Color is intentionally
            # not a tie-breaker here; the nearest candidate wins.
            chosen = candidates[0]
            warnings.append("环网柜框指定方向存在多个名称候选，按最近位置选择")
            confidence = "中"

        _gap, _axis_offset, position, value, text_key, _green = chosen
        name_text_id = (text_by_key.get(text_key).get("id") or "").strip() if text_by_key.get(text_key) is not None else ""
        result[rect_id] = (value, position, confidence, warnings, name_text_id, text_instance_key(text_by_key[text_key]) if text_by_key.get(text_key) is not None else "")

    return result




_NAME_POSITIONS = ("top", "right", "bottom", "left")
_AUTO_NAME_POSITIONS = _NAME_POSITIONS


@dataclass(frozen=True)
class _AutoNameCandidate:
    rect_id: str
    text_key: str
    value: str
    position: str
    gap: float
    axis_offset: float
    pattern: str
    color: str
    green: bool
    text_center_x: float
    text_center_y: float
    cabinet_center_x: float
    cabinet_center_y: float

    @property
    def geometry_score(self) -> float:
        return self.gap + self.axis_offset * 0.08


def _auto_name_pattern(value: str) -> str:
    """Return a compact lexical style signature for cluster learning.

    Examples: ``29521 -> #``, ``AK-900841 -> AK-#``, ``K-00018 -> K-#``.
    The signature is deliberately learned from the current cluster instead of
    being hard-coded to a site/prefix.
    """
    compact = re.sub(r"\s+", "", (value or "").strip()).upper()
    return re.sub(r"\d+", "#", compact)


def _auto_color_key(text: ET.Element) -> str:
    lcc = (text.get("lcc") or "").strip().lower()
    if lcc:
        return lcc
    lc = re.sub(r"\s+", "", (text.get("lc") or "").strip())
    return lc.lower()


def _valid_auto_name_text(
    element: ET.Element,
    excluded_names: frozenset[str] = frozenset(),
) -> bool:
    """Stricter candidate filter used only by automatic RMU-name resolution.

    Direction/color are not hard requirements.  We only remove labels that are
    clearly internal/status annotations so a cluster can learn its own external
    name style (numeric, AK-*, etc.).
    """
    if not _valid_name_text(element, excluded_names):
        return False
    value = (element.get("ts") or "").strip()
    if re.fullmatch(r"\(\s*\d+\s*\)", value):
        return False
    compact = re.sub(r"\s+", "", value).upper()
    alnum = re.sub(r"[^A-Z0-9]+", "", compact)
    if alnum in {"NOP", "FC", "F", "SMART", "SMR", "BUS", "NORMAL", "EARTH"}:
        return False
    if re.fullmatch(r"[YQ]\d+D?", alnum):
        return False
    return True


def _candidate_for_auto_position(
    text: ET.Element,
    rect: _Box,
    position: str,
) -> tuple[float, float] | None:
    """All-direction RMU candidate geometry for auto-layout mode.

    Unlike the legacy selected-direction matcher, this does not encode a site
    direction.  The four sides are evaluated symmetrically, then a cabinet
    cluster chooses the best repeated layout.
    """
    box = _box(text)
    if box is None:
        return None

    base = max(rect.width, rect.height)
    max_distance = RMU_NAME_MAX_DISTANCE
    projection_tolerance = max(60.0, min(140.0, base * 0.45))
    edge_tolerance = 45.0

    if position == "top":
        gap = rect.top - box.bottom
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_y < rect.top
            and rect.left - projection_tolerance <= box.center_x <= rect.right + projection_tolerance
        ):
            return max(0.0, gap), abs(box.center_x - rect.center_x)
    elif position == "bottom":
        gap = box.top - rect.bottom
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_y > rect.bottom
            and rect.left - projection_tolerance <= box.center_x <= rect.right + projection_tolerance
        ):
            return max(0.0, gap), abs(box.center_x - rect.center_x)
    elif position == "left":
        gap = rect.left - box.right
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_x < rect.left
            and rect.top - projection_tolerance <= box.center_y <= rect.bottom + projection_tolerance
        ):
            return max(0.0, gap), abs(box.center_y - rect.center_y)
    elif position == "right":
        gap = box.left - rect.right
        if (
            -edge_tolerance <= gap <= max_distance
            and box.center_x > rect.right
            and rect.top - projection_tolerance <= box.center_y <= rect.bottom + projection_tolerance
        ):
            return max(0.0, gap), abs(box.center_y - rect.center_y)
    return None


def _auto_candidates_for_rect(
    texts: list[ET.Element],
    rect_id: str,
    rect: _Box,
    excluded_names: frozenset[str],
) -> list[_AutoNameCandidate]:
    candidates: list[_AutoNameCandidate] = []
    for text in texts:
        if not _valid_auto_name_text(text, excluded_names):
            continue
        box = _box(text)
        if box is None:
            continue
        value = (text.get("ts") or "").strip()
        # Keep repeated equal strings independent.  The object identity is the
        # ownership key; the rendered value is only the name content.
        text_key = f"__text_object_{id(text)}"
        pattern = _auto_name_pattern(value)
        color = _auto_color_key(text)
        green = _is_green_name_text(text)
        for position in _AUTO_NAME_POSITIONS:
            metric = _candidate_for_auto_position(text, rect, position)
            if metric is None:
                continue
            candidates.append(_AutoNameCandidate(
                rect_id=rect_id,
                text_key=text_key,
                value=value,
                position=position,
                gap=metric[0],
                axis_offset=metric[1],
                pattern=pattern,
                color=color,
                green=green,
                text_center_x=box.center_x,
                text_center_y=box.center_y,
                cabinet_center_x=rect.center_x,
                cabinet_center_y=rect.center_y,
            ))
    return candidates


def _median(values: list[float], default: float) -> float:
    if not values:
        return default
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _axis_bands(
    cabinets: list[tuple[str, _Box]],
    axis: str,
) -> list[tuple[list[str], float]]:
    if not cabinets:
        return []
    if axis == "x":
        coords = [(rect.center_x, rect_id) for rect_id, rect in cabinets]
        size = _median([rect.width for _rect_id, rect in cabinets], 220.0)
    else:
        coords = [(rect.center_y, rect_id) for rect_id, rect in cabinets]
        size = _median([rect.height for _rect_id, rect in cabinets], 220.0)
    tolerance = max(35.0, min(110.0, size * 0.40))
    coords.sort()
    groups: list[list[tuple[float, str]]] = []
    for coord, rect_id in coords:
        if not groups:
            groups.append([(coord, rect_id)])
            continue
        current_mean = sum(value for value, _rid in groups[-1]) / len(groups[-1])
        if abs(coord - current_mean) <= tolerance:
            groups[-1].append((coord, rect_id))
        else:
            groups.append([(coord, rect_id)])
    result: list[tuple[list[str], float]] = []
    for group in groups:
        if len(group) < 2:
            continue
        vals = [value for value, _rid in group]
        spread = max(vals) - min(vals)
        result.append(([rid for _value, rid in group], spread))
    return result


def _auto_cluster_cabinets(cabinets: list[tuple[str, _Box]]) -> list[list[str]]:
    """Create non-overlapping repeated-layout RMU clusters.

    Long aligned columns beat shorter cross-rows (MAK sample); long aligned rows
    beat incidental short columns (ABHA-style rows).  Remaining cabinets become
    singletons and use the local all-direction fallback.
    """
    if len(cabinets) <= 1:
        return [[rect_id] for rect_id, _rect in cabinets]

    proposals: list[tuple[int, float, str, list[str]]] = []
    for axis in ("x", "y"):
        for ids, spread in _axis_bands(cabinets, axis):
            proposals.append((len(ids), spread, axis, ids))
    # Larger repeated patterns are stronger evidence; tighter alignment breaks ties.
    proposals.sort(key=lambda row: (-row[0], row[1], row[2], tuple(row[3])))

    assigned: set[str] = set()
    clusters: list[list[str]] = []
    for _size, _spread, _axis, ids in proposals:
        remaining = [rid for rid in ids if rid not in assigned]
        if len(remaining) < 2:
            continue
        clusters.append(remaining)
        assigned.update(remaining)
    for rect_id, _rect in cabinets:
        if rect_id not in assigned:
            clusters.append([rect_id])
            assigned.add(rect_id)
    return clusters


def _style_rank(
    style: tuple[str, str],
    candidates: list[_AutoNameCandidate],
    cluster_size: int,
) -> tuple[int, int, int, int, float, float, str, str]:
    pattern, color = style
    matched = [item for item in candidates if item.pattern == pattern and item.color == color]
    covered = {item.rect_id for item in matched}
    pattern_covered = {item.rect_id for item in candidates if item.pattern == pattern}
    green_covered = len({item.rect_id for item in matched if item.green})
    green_bonus = 1 if green_covered else 0
    avg_gap = sum(item.gap for item in matched) / max(1, len(matched))
    avg_axis = sum(item.axis_offset for item in matched) / max(1, len(matched))
    # Coverage is authoritative.  When repeated styles cover the same RMUs,
    # green is a strong disambiguation signal (ABHA AK-* vs K-*/A-* labels); the
    # dominant-style selector below only lets it override a one-cabinet coverage
    # advantage, so a sparse green annotation cannot dominate a mixed drawing.
    return (
        len(covered),
        green_covered,
        green_bonus,
        len(pattern_covered),
        -avg_gap,
        -avg_axis,
        pattern,
        color,
    )


def _dominant_style_for_direction(
    candidates: list[_AutoNameCandidate],
    cluster_size: int,
) -> tuple[tuple[str, str] | None, tuple[int, int, int, int, float, float, str, str]]:
    styles = {(item.pattern, item.color) for item in candidates if item.pattern}
    if not styles:
        return None, (0, 0, 0, 0, float("-inf"), float("-inf"), "", "")
    ranked = sorted(
        ((_style_rank(style, candidates, cluster_size), style) for style in styles),
        key=lambda row: row[0],
        reverse=True,
    )
    best_rank, best_style = ranked[0]

    # In ABHA drawings the green AK-* Text is the cabinet identity while nearby
    # white T-*/A-* Text describes another electrical object.  Coverage remains
    # the primary signal, but a green style that covers most cabinets is allowed
    # to beat a competing style that wins by only one cabinet.  This also handles
    # a direction with two or three candidates per cabinet without treating every
    # nearby Text as another RMU name.
    green_styles = [
        row for row in ranked
        if any(
            item.green and (item.pattern, item.color) == row[1]
            for item in candidates
        )
    ]
    if green_styles:
        green_rank, green_style = green_styles[0]
        green_support = green_rank[1]
        required_green_support = max(2, (cluster_size + 1) // 2)
        if (
            green_support >= required_green_support
            and green_rank[0] + 1 >= best_rank[0]
        ):
            return green_style, green_rank
    return best_style, best_rank


def _assign_cluster_direction(
    cluster_ids: list[str],
    all_candidates: dict[str, list[_AutoNameCandidate]],
    used_texts: set[str] | None = None,
    common_position: str | None = None,
) -> tuple[str | None, tuple[str, str] | None, dict[str, _AutoNameCandidate], dict[str, int]]:
    """Infer one repeated side/style and assign one Text to one RMU."""
    cluster_size = len(cluster_ids)
    direction_options: list[
        tuple[tuple[int, int, int, int, float, float, str, str], str, tuple[str, str] | None, list[_AutoNameCandidate]]
    ] = []
    for position in _AUTO_NAME_POSITIONS:
        directional = [
            item
            for rect_id in cluster_ids
            for item in all_candidates.get(rect_id, [])
            if item.position == position
        ]
        style, rank = _dominant_style_for_direction(directional, cluster_size)
        direction_options.append((rank, position, style, directional))

    direction_options.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best_rank, position, dominant_style, directional = direction_options[0]
    min_support = max(2, (cluster_size + 1) // 2)
    if common_position:
        common_option = next(
            (option for option in direction_options if option[1] == common_position),
            None,
        )
        # A strong whole-drawing direction is a prior, not a hard rule.  Use it
        # when the local cluster has comparable evidence; a genuinely different
        # local layout is still allowed to win.
        if (
            common_option is not None
            and common_option[0][0] >= min_support
            and common_option[0][0] + 1 >= best_rank[0]
        ):
            best_rank, position, dominant_style, directional = common_option
    if best_rank[0] < min_support:
        return None, None, {}, {}

    preferred_pattern = dominant_style[0] if dominant_style else ""
    already_used = used_texts or set()

    def fallback_level(item: _AutoNameCandidate) -> int:
        if dominant_style and (item.pattern, item.color) == dominant_style:
            return 0
        if preferred_pattern and item.pattern == preferred_pattern:
            return 1
        return 2

    # Build one edge per (cabinet, Text) pair.  When a repeated cluster has a
    # dominant name style, unrelated styles are deliberately not allowed to fill
    # a missing cabinet: a feeder label such as FRD-43 must not become an RMU
    # name merely because it is nearby.
    pair_candidates: dict[tuple[str, str], _AutoNameCandidate] = {}
    for item in directional:
        if item.text_key in already_used:
            continue
        level = fallback_level(item)
        if dominant_style and level >= 2:
            continue
        key = (item.rect_id, item.text_key)
        current = pair_candidates.get(key)
        if current is None or (
            fallback_level(item), item.geometry_score, item.value, item.text_key
        ) < (
            fallback_level(current), current.geometry_score, current.value, current.text_key
        ):
            pair_candidates[key] = item

    if not pair_candidates:
        return position, dominant_style, {}, {}

    axis_is_vertical = position in {"top", "bottom"}

    def cabinet_coordinate(item: _AutoNameCandidate) -> float:
        return item.cabinet_center_y if axis_is_vertical else item.cabinet_center_x

    def text_coordinate(item: _AutoNameCandidate) -> float:
        return item.text_center_y if axis_is_vertical else item.text_center_x

    # For a vertical stack, this creates the essential top-to-bottom order.  For
    # a horizontal row, the same code operates left-to-right.  The dynamic
    # program below may skip cabinets and extra Text labels, but it can never
    # cross two accepted name assignments.
    ordered_cabinets = sorted(
        cluster_ids,
        key=lambda rect_id: (
            min(
                cabinet_coordinate(item)
                for (candidate_rect_id, _text_key), item in pair_candidates.items()
                if candidate_rect_id == rect_id
            )
            if any(candidate_rect_id == rect_id for candidate_rect_id, _text_key in pair_candidates)
            else float("inf"),
            rect_id,
        ),
    )
    ordered_text_keys = sorted(
        {text_key for _rect_id, text_key in pair_candidates},
        key=lambda text_key: (
            min(text_coordinate(item) for (candidate_rect_id, candidate_key), item in pair_candidates.items() if candidate_key == text_key),
            text_key,
        ),
    )

    from functools import lru_cache

    @lru_cache(maxsize=None)
    def solve(cabinet_index: int, text_index: int) -> tuple[tuple[int, int, float], tuple[tuple[str, str], ...]]:
        if cabinet_index >= len(ordered_cabinets) or text_index >= len(ordered_text_keys):
            return (0, 0, 0.0), ()

        options = [
            solve(cabinet_index + 1, text_index),
            solve(cabinet_index, text_index + 1),
        ]
        pair = (ordered_cabinets[cabinet_index], ordered_text_keys[text_index])
        item = pair_candidates.get(pair)
        if item is not None:
            next_score, next_pairs = solve(cabinet_index + 1, text_index + 1)
            level = fallback_level(item)
            options.append((
                (
                    next_score[0] + 1,
                    next_score[1] + (2 - level),
                    next_score[2] - item.geometry_score,
                ),
                ((item.rect_id, item.text_key),) + next_pairs,
            ))
        # Matching count is the primary objective, then repeated style evidence,
        # then geometric distance.  Option order makes equal ties deterministic.
        return max(options, key=lambda option: option[0])

    _score, pairs = solve(0, 0)
    assigned: dict[str, _AutoNameCandidate] = {}
    fallback_levels: dict[str, int] = {}
    for rect_id, text_key in pairs:
        item = pair_candidates[(rect_id, text_key)]
        assigned[rect_id] = item
        fallback_levels[rect_id] = fallback_level(item)
    return position, dominant_style, assigned, fallback_levels


def _learn_common_layout_direction(
    cabinets: list[tuple[str, _Box]],
    all_candidates: dict[str, list[_AutoNameCandidate]],
) -> str | None:
    """Learn a strong drawing-level RMU name direction as a soft prior.

    Repeated cabinets often use one drafting convention even when their columns
    are separated far enough to become different local clusters.  The prior is
    enabled only when one direction covers a clear majority, so mixed-layout
    drawings continue to be resolved independently per cluster.
    """
    cabinet_count = len(cabinets)
    if cabinet_count < 2:
        return None
    options: list[tuple[tuple[int, int, int, int, float, float, str, str], str]] = []
    all_ids = [rect_id for rect_id, _rect in cabinets]
    for position in _AUTO_NAME_POSITIONS:
        directional = [
            item
            for rect_id in all_ids
            for item in all_candidates.get(rect_id, [])
            if item.position == position
        ]
        _style, rank = _dominant_style_for_direction(directional, cabinet_count)
        options.append((rank, position))
    options.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best_rank, best_position = options[0]
    second_rank = options[1][0]
    required_support = max(2, (cabinet_count + 1) // 2)
    if best_rank[0] < required_support:
        return None
    if best_rank[0] < second_rank[0] + 1:
        return None
    return best_position


def _assign_singletons_auto(
    rect_ids: list[str],
    all_candidates: dict[str, list[_AutoNameCandidate]],
    used_texts: set[str],
) -> tuple[dict[str, _AutoNameCandidate], dict[str, str]]:
    assigned: dict[str, _AutoNameCandidate] = {}
    confidence: dict[str, str] = {}
    for rect_id in rect_ids:
        candidates = [item for item in all_candidates.get(rect_id, []) if item.text_key not in used_texts]
        if not candidates:
            continue
        # No cluster style is available.  Green remains a useful weak signal for
        # multi-line ABHA-style labels; otherwise pure geometry wins across all four sides.
        greens = [item for item in candidates if item.green]
        pool = greens if greens else candidates
        pool.sort(key=lambda item: (item.geometry_score, item.position, item.value, item.text_key))
        chosen = pool[0]
        assigned[rect_id] = chosen
        used_texts.add(chosen.text_key)
        confidence[rect_id] = "中" if len(candidates) > 1 else "高"
    return assigned, confidence


def _assign_names_auto_cluster(
    texts: list[ET.Element],
    cabinets: list[tuple[str, _Box]],
    excluded_names: frozenset[str] = frozenset(),
) -> dict[str, tuple[str, str, str, list[str]]]:
    """Legacy automatic RMU name resolver retained for compatibility.

    It learns repeated layout per RMU cluster (TOP/RIGHT/BOTTOM/LEFT), then learns
    the dominant text style within that cluster and performs one-to-one matching.
    No site direction is required.  Single/irregular cabinets fall back to an
    all-direction local resolver.
    """
    all_candidates = {
        rect_id: _auto_candidates_for_rect(texts, rect_id, rect, excluded_names)
        for rect_id, rect in cabinets
    }
    result: dict[str, tuple[str, str, str, list[str]]] = {
        rect_id: ("", "", "未识别", []) for rect_id, _rect in cabinets
    }
    used_texts: set[str] = set()
    ordered_cluster_ids: set[str] = set()
    clusters = _auto_cluster_cabinets(cabinets)
    common_position = _learn_common_layout_direction(cabinets, all_candidates)

    # Strong repeated-layout clusters first; singletons/irregular remnants later.
    for cluster_ids in [cluster for cluster in clusters if len(cluster) >= 2]:
        position, _style, assigned, fallback_levels = _assign_cluster_direction(
            cluster_ids,
            all_candidates,
            used_texts,
            common_position,
        )
        if position is None:
            continue
        ordered_cluster_ids.update(cluster_ids)
        for rect_id, item in assigned.items():
            if item.text_key in used_texts:
                continue
            used_texts.add(item.text_key)
            level = fallback_levels.get(rect_id, 2)
            confidence = "高" if level == 0 else "中"
            result[rect_id] = (item.value, position, confidence, [])

    unresolved = [
        rect_id
        for rect_id, _rect in cabinets
        if not result[rect_id][0] and rect_id not in ordered_cluster_ids
    ]
    singleton_assigned, singleton_confidence = _assign_singletons_auto(unresolved, all_candidates, used_texts)
    for rect_id, item in singleton_assigned.items():
        result[rect_id] = (
            item.value,
            item.position,
            singleton_confidence.get(rect_id, "中"),
            [],
        )
    return result


_GLOBAL_TOPOLOGY_ONLY_TAGS = {
    "ConnectLine", "FeedLine", "BusDis", "Bus", "ACLine", "line",
    "Text", "DText", "Status", "rect", "ellipse", "image", "Layer", "G",
    "Group", "Merge", "Theme", "pwbh", "poke",
}


def _globally_owned_rmu_name_texts(
    texts: list[ET.Element],
    elements: list[ET.Element],
    valid_cabinets: list[tuple[ET.Element, _Box]],
    excluded_names: frozenset[str],
) -> list[ET.Element]:
    """Keep only Texts whose nearest global equipment target is an RMU.

    RMU name recognition must compete with every other real equipment symbol in
    the drawing.  Internal RMU symbols are excluded from the competing targets;
    their Y/Q labels describe components, while the cabinet frame owns the outer
    cabinet name.  ConnectLine, FeedLine, BusDis and Bus are never targets.
    """
    target_pairs: list[tuple[str, ET.Element]] = []
    rmu_target_keys: set[str] = set()
    for index, (rect, _rect_box) in enumerate(valid_cabinets):
        rect_id = rect.get("id") or f"__rect_{index}"
        target_key = f"rmu:{index}:{rect_id}"
        target_pairs.append((target_key, rect))
        rmu_target_keys.add(target_key)

    for element in elements:
        tag = local_name(element.tag)
        if tag in _GLOBAL_TOPOLOGY_ONLY_TAGS or not (element.get("devref") or "").strip():
            continue
        if _box(element) is None:
            continue
        # A recognized RMU is a composite target; its internal device symbols do
        # not compete for the external cabinet-name Text.
        if any(_center_inside(element, rect_box) for _rect, rect_box in valid_cabinets):
            continue
        target_pairs.append((f"device:{id(element)}", element))

    candidates = [
        text for text in texts
        if _valid_name_text(text, excluded_names)
    ]
    if not candidates or not target_pairs:
        return texts

    owners = assign_global_text_owners(candidates, target_pairs)
    return [
        text for text in candidates
        if (owner := owners.get(id(text))) is not None
        and owner.target_key in rmu_target_keys
    ]


def _cluster_rmu_name_texts(
    texts: list[ET.Element],
    valid_cabinets: list[tuple[ET.Element, _Box]],
    excluded_names: frozenset[str],
) -> list[ET.Element]:
    """Return the full outer-label pool for repeated-layout RMU matching.

    A nearest-frame pre-filter is correct for isolated cabinets but is unsafe for
    a vertical stack: the label of a lower cabinet can be geometrically closer to
    the upper frame.  Auto-cluster must see both labels so its learned direction
    and top-to-bottom one-to-one assignment can resolve the pair together.
    Texts inside a cabinet remain excluded because they are component/status text,
    not the external cabinet name.
    """
    rect_boxes = [rect_box for _rect, rect_box in valid_cabinets]
    return [
        text for text in texts
        if _valid_name_text(text, excluded_names)
        and _box(text) is not None
        and not any(_center_inside(text, rect_box) for rect_box in rect_boxes)
    ]

def _find_name(
    texts: list[ET.Element],
    rect: _Box,
    positions: tuple[str, ...],
    excluded_names: frozenset[str] = frozenset(),
) -> tuple[str, str, str, list[str]]:
    """Compatibility wrapper used by focused unit tests/single-cabinet callers."""
    matches = _assign_names_globally(texts, [("__single__", rect)], positions, excluded_names)
    return matches["__single__"]


def _label_counts(inside_texts: list[ET.Element]) -> tuple[int, int, set[str], set[str]]:
    y_labels: set[str] = set()
    q_labels: set[str] = set()
    for item in inside_texts:
        value = (item.get("ts") or "").strip().upper().replace(" ", "")
        if _Y_LABEL_RE.fullmatch(value):
            y_labels.add(value)
        elif _Q_LABEL_RE.fullmatch(value):
            q_labels.add(value)
    return len(y_labels), len(q_labels), y_labels, q_labels


def _label_sequence_ok(labels: set[str], prefix: str) -> bool:
    if not labels:
        return True
    numbers = sorted(int(re.sub(r"\D", "", label)) for label in labels)
    return numbers == list(range(1, len(numbers) + 1))


def _type_string(l_count: int, t_count: int) -> str:
    return f"{l_count}L{t_count}T" if (l_count or t_count) else ""


def identify_rmus(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    name_positions: tuple[str, ...] = ("top",),
    name_resolution_mode: str = "selected_direction",
    smart_in_type: bool = False,
    excluded_name_values: tuple[str, ...] = (),
    intelligent_marker_values: tuple[str, ...] = ("SMART", "SMR"),
    excluded_name_text_keys: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> RmuIdentificationResult:
    """识别环网柜名称、L/T 柜型及 SMART 状态，不修改 XML。

    环网柜识别固定要求有效 rect 框内同时存在 BusDis、CBreakerDis、
    ZhaiWaiJieDiDaoZha。名称只在调用方选择的方向限定区域内查找，并只在
    环网柜外框之间一对一分配；未选择的方向不参与候选。RMU 框的强制识别
    规则不受名称方向选择影响。

    共同规则：
    1. 必须存在环网柜 rect，且框内同时具有 BusDis、CBreakerDis、ZhaiWaiJieDiDaoZha。
    2. 环网柜名称只来自图上的可见 Text；不使用 keyid、key_name、p_NameString
       或其他模型关联字段作为名称来源或回退。
    3. 柜型第一来源为框内 Y1/Y2/... 与 Q1/Q2/...：Y 数量=L，Q 数量=T，并检查序号连续性。
       第二来源仅按 CBreakerDis.devref 图元文件名：Load_Breaker*=L，Circuit_Breaker*=T。
       L/T 按类别分别交叉校验：已同时存在的类别计数不一致才 FAIL；某一类 Y/Q 完全缺失时
       使用 devref 对应类别回退并标记 WARN（证据不完整），不再因为完整字符串如 2L0T/2L1T 不同而误判 FAIL。
    4. 柜型始终只输出 nLmT；用户配置的智能标记 Text 在统计层统一归类为“智能环网柜”，不追加到柜型字符串。
       智能标记在全图有效 RMU 集合中做最近归属，每个标记只允许归属一个 RMU；标记无需完全落在柜框内。
       默认标记为 SMART / SMR，可扩展为 NEWSMART、SMART-SE 等任意完整 Text。

    smart_in_type 参数为了兼容现有设置保留；现在表示是否统计智能环网柜。
    """
    requested_mode = (name_resolution_mode or "selected_direction").strip().lower()
    if requested_mode not in {"selected_direction", "auto_cluster"}:
        raise ValueError(f"未知 RMU 柜名识别模式：{name_resolution_mode}")
    selected_positions = tuple(
        position for position in name_positions if position in _NAME_POSITIONS
    ) or ("top",)
    intelligent_markers = tuple(
        value for value in intelligent_marker_values if _normalize_excluded_name(value)
    ) or ("SMART", "SMR")
    marker_key_to_source = {
        _normalize_excluded_name(value): re.sub(r"\s+", " ", value.strip()).upper()
        for value in intelligent_markers
        if _normalize_excluded_name(value)
    }
    excluded_names = frozenset(
        key
        for value in (*excluded_name_values, *_FIXED_RMU_NAME_EXCLUSIONS, *intelligent_markers)
        if (key := _normalize_excluded_name(value))
    )

    elements = direct_layer_elements(tree.getroot())
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    # Device/RMU names are static drawing labels.  DText is reserved for
    # dynamic measurements and must be handled only by a later association
    # stage, never as a name candidate.
    texts = [element for element in elements if local_name(element.tag) == "Text"]
    switches = [element for element in elements if local_name(element.tag) == "CBreakerDis"]
    buses = [element for element in elements if local_name(element.tag) == "BusDis"]
    grounds = [element for element in elements if local_name(element.tag) == "ZhaiWaiJieDiDaoZha"]

    result = RmuIdentificationResult(file_path=file_path)

    # First determine the complete cabinet set.  Every RMU caller uses the same
    # strict frame-local name rule; no caller may fall back to global equipment
    # ownership or topology-based name inference.
    valid_cabinets: list[tuple[ET.Element, _Box]] = []
    for rect in rects:
        rect_box = _box(rect)
        if rect_box is None or rect_box.width < 100 or rect_box.height < 100:
            continue
        inside_switches = [item for item in switches if _center_inside(item, rect_box)]
        inside_bus = [item for item in buses if _center_inside(item, rect_box)]
        inside_ground = [item for item in grounds if _center_inside(item, rect_box)]
        if not inside_bus or not inside_switches or not inside_ground:
            continue
        valid_cabinets.append((rect, rect_box))

    cabinet_boxes = [((rect.get("id") or f"__rect_{index}"), rect_box)
                     for index, (rect, rect_box) in enumerate(valid_cabinets)]
    # Poke processing can reserve a concrete Text for another jump role.
    # Exclusion is intentionally limited to cabinet-name resolution: the full
    # Text pool is still used for Y/Q type labels and SMART markers.
    reserved_name_text_keys = set(excluded_name_text_keys or ())
    name_texts = [
        text for text in texts
        if text_instance_key(text) not in reserved_name_text_keys
    ]
    name_assignments = _assign_names_local_top(
        name_texts,
        cabinet_boxes,
        excluded_names,
        selected_positions,
    )

    # User-configured intelligent markers are global RMU markers. They are not
    # required to be fully inside a cabinet frame: a label may sit on / slightly
    # outside the frame. Each marker is assigned to exactly ONE nearest valid RMU.
    marker_sources_by_rect: dict[str, set[str]] = {}
    if smart_in_type and valid_cabinets:
        marker_texts = [
            item for item in tree.getroot().iter()
            if local_name(item.tag) == "Text"
            and _normalize_excluded_name(item.get("ts") or "") in marker_key_to_source
        ]
        for marker in marker_texts:
            marker_box = _box(marker)
            if marker_box is None:
                result.warnings.append(
                    f"智能标记 {(marker.get('ts') or '').strip().upper()} "
                    f"Text ID {(marker.get('id') or '<无ID>')} 缺少有效几何坐标，未参与 RMU 归属。"
                )
                continue
            candidates: list[tuple[float, float, str]] = []
            for cabinet_index, (rect, rect_box) in enumerate(valid_cabinets):
                key = rect.get("id") or f"__rect_{cabinet_index}"
                edge_distance = _point_to_box_distance(marker_box.center_x, marker_box.center_y, rect_box)
                center_distance = (
                    (marker_box.center_x - rect_box.center_x) ** 2
                    + (marker_box.center_y - rect_box.center_y) ** 2
                ) ** 0.5
                candidates.append((edge_distance, center_distance, key))
            if not candidates:
                continue
            # Distance to frame is authoritative. Center distance breaks ordinary
            # overlap/touch ties. If two RMUs remain geometrically identical after
            # both comparisons, the data is ambiguous: skip instead of guessing,
            # so one marker can never be attributed to two cabinets.
            candidates.sort(key=lambda item: (item[0], item[1], item[2]))
            chosen_edge, chosen_center, chosen_key = candidates[0]
            if len(candidates) > 1:
                next_edge, next_center, next_key = candidates[1]
                if abs(chosen_edge - next_edge) <= 1e-6 and abs(chosen_center - next_center) <= 1e-6:
                    result.warnings.append(
                        f"智能标记 {(marker.get('ts') or '').strip().upper()} "
                        f"Text ID {(marker.get('id') or '<无ID>')} 与 RMU {chosen_key}/{next_key} "
                        f"几何距离完全相同，无法唯一归属；为避免一个标记属于两个 RMU，已跳过该标记。"
                    )
                    continue
            marker_key = _normalize_excluded_name(marker.get("ts") or "")
            source = marker_key_to_source.get(marker_key, (marker.get("ts") or "").strip().upper())
            marker_sources_by_rect.setdefault(chosen_key, set()).add(source)

    for index, (rect, rect_box) in enumerate(valid_cabinets):
        rect_key = rect.get("id") or f"__rect_{index}"
        inside_switches = [item for item in switches if _center_inside(item, rect_box)]
        inside_buses = [item for item in buses if _center_inside(item, rect_box)]
        inside_texts = [item for item in texts if _center_inside(item, rect_box)]
        y_count, q_count, y_labels, q_labels = _label_counts(inside_texts)
        devref_l = sum(1 for item in inside_switches if _classify_switch_by_devref(item) == "L")
        devref_t = sum(1 for item in inside_switches if _classify_switch_by_devref(item) == "T")

        warnings: list[str] = []
        y_sequence_ok = _label_sequence_ok(y_labels, "Y")
        q_sequence_ok = _label_sequence_ok(q_labels, "Q")
        if not y_sequence_ok:
            warnings.append("柜内 Y 标签不是从 Y1 开始连续递增")
        if not q_sequence_ok:
            warnings.append("柜内 Q 标签不是从 Q1 开始连续递增")

        text_yq_type = _type_string(y_count, q_count)
        devref_type = _type_string(devref_l, devref_t)

        # 最终柜型仍以 Y/Q 文字为主；某一类文字完全缺失时，才使用 devref 对应类别补齐。
        l_count = y_count if y_count > 0 else devref_l
        t_count = q_count if q_count > 0 else devref_t
        if y_count == 0 and devref_l:
            warnings.append(f"未识别到 Y 名称，L 使用 devref 图元文件名回退计数 {devref_l}")
        if q_count == 0 and devref_t:
            warnings.append(f"未识别到 Q 名称，T 使用 devref 图元文件名回退计数 {devref_t}")

        if y_count and q_count:
            type_source = "TEXT_YQ"
        elif (y_count or q_count) and (devref_l or devref_t):
            type_source = "TEXT_YQ+DEVREF_FALLBACK"
        elif devref_l or devref_t:
            type_source = "DEVREF"
        else:
            type_source = "UNKNOWN"

        # v2.18.131: cross-check L/T per category instead of comparing the raw
        # full type string when one Y/Q category is completely absent.  A missing
        # category that is successfully filled from devref is incomplete evidence
        # (WARN), not a genuine conflict (FAIL).  A category that is present in
        # both sources but has different counts remains a hard FAIL.
        has_text_y = y_count > 0
        has_text_q = q_count > 0
        has_devref_l = devref_l > 0
        has_devref_t = devref_t > 0

        comparable_categories: list[str] = []
        mismatch_details: list[str] = []
        fallback_details: list[str] = []
        incomplete_details: list[str] = []

        if has_text_y and has_devref_l:
            comparable_categories.append("L")
            if y_count != devref_l:
                mismatch_details.append(f"Y={y_count}L 与 devref L={devref_l}L 不一致")
        elif has_text_y and not has_devref_l:
            incomplete_details.append(f"Y={y_count}L 缺少对应 devref L 证据")
        elif not has_text_y and has_devref_l:
            fallback_details.append(f"Y 缺失，L 使用 devref 回退 {devref_l}L")

        if has_text_q and has_devref_t:
            comparable_categories.append("T")
            if q_count != devref_t:
                mismatch_details.append(f"Q={q_count}T 与 devref T={devref_t}T 不一致")
        elif has_text_q and not has_devref_t:
            incomplete_details.append(f"Q={q_count}T 缺少对应 devref T 证据")
        elif not has_text_q and has_devref_t:
            fallback_details.append(f"Q 缺失，T 使用 devref 回退 {devref_t}T")

        if not y_sequence_ok:
            mismatch_details.append("Y 标签序号不连续")
        if not q_sequence_ok:
            mismatch_details.append("Q 标签序号不连续")

        if mismatch_details:
            type_cross_check = "NO"
            type_validation_status = "FAIL"
            type_cross_note = "；".join(mismatch_details)
            warnings.append(type_cross_note)
        elif has_text_y and has_text_q and has_devref_l and has_devref_t:
            # Both categories have complete two-source evidence and agree.
            type_cross_check = "YES"
            type_validation_status = "PASS"
            type_cross_note = f"Y/Q={text_yq_type}，devref={devref_type}，两种识别结果一致"
        elif text_yq_type and devref_type:
            # At least one Y/Q category is absent or one corresponding devref
            # category is missing.  Keep the resolved final type, but explicitly
            # report that only a partial cross-check was possible.
            type_cross_check = "PARTIAL" if comparable_categories else "N/A"
            type_validation_status = "WARN"
            details = []
            if comparable_categories:
                details.append("已交叉校验 " + "/".join(comparable_categories) + " 类计数一致")
            details.extend(fallback_details)
            details.extend(incomplete_details)
            type_cross_note = "；".join(details) or (
                f"Y/Q={text_yq_type}，devref={devref_type}，仅能进行部分双源交叉校验"
            )
            warnings.append(type_cross_note)
        elif text_yq_type:
            type_cross_check = "N/A"
            type_validation_status = "WARN"
            type_cross_note = f"仅识别到 Y/Q 文字类型 {text_yq_type}，devref 信息不足，无法双源交叉校验"
            warnings.append(type_cross_note)
        elif devref_type:
            type_cross_check = "N/A"
            type_validation_status = "WARN"
            type_cross_note = f"仅识别到 devref 类型 {devref_type}，Y/Q 文字不足，使用 devref 回退"
            warnings.append(type_cross_note)
        else:
            type_cross_check = "NO"
            type_validation_status = "FAIL"
            type_cross_note = "Y/Q 文字和 devref 均无法识别柜型"
            warnings.append(type_cross_note)

        name, position, confidence, name_warnings, name_text_id, name_text_key = name_assignments.get(
            rect_key, ("", "", "未识别", [], "", "")
        )
        warnings.extend(name_warnings)
        smart_count = 0
        smart_source = ""
        if smart_in_type:
            marker_sources = marker_sources_by_rect.get(rect_key, set())
            smart_device = any(_is_smart_device(item) for item in inside_switches)
            source_order = [marker_key_to_source[_normalize_excluded_name(value)] for value in intelligent_markers]
            sources = [source for source in source_order if source in marker_sources]
            # Preserve the historical SMART-device fallback only when no configured
            # visible marker was assigned to this cabinet.
            if smart_device and not sources:
                sources.append("SMART_DEVICE")
            smart_source = " + ".join(sources)
            smart_count = 1 if sources else 0

        rmu_type = _type_string(l_count, t_count)
        if warnings and confidence == "高":
            confidence = "中"

        result.items.append(RmuIdentification(
            rect_id=(rect.get("id") or "").strip(),
            name=name,
            name_text_id=name_text_id,
            name_position=position,
            rmu_type=rmu_type,
            l_count=l_count,
            t_count=t_count,
            smart_count=smart_count,
            smart_source=smart_source,
            type_source=type_source,
            text_yq_type=text_yq_type,
            devref_type=devref_type,
            type_cross_check=type_cross_check,
            type_validation_status=type_validation_status,
            type_cross_note=type_cross_note,
            name_text_key=name_text_key,
            confidence=confidence,
            rect_x=rect_box.left,
            rect_y=rect_box.top,
            rect_w=rect_box.width,
            rect_h=rect_box.height,
            warnings=warnings,
        ))

    result.cabinet_count = len(result.items)
    result.named_count = sum(1 for item in result.items if item.name)
    result.typed_count = sum(1 for item in result.items if item.l_count or item.t_count)
    result.ambiguous_name_count = sum(1 for item in result.items if item.confidence == "待确认")
    for item in result.items:
        if not item.name:
            result.warnings.append(f"rect ID {item.rect_id or '<无ID>'} 未找到指定方向且距离足够近的柜名。")
        for warning in item.warnings:
            result.warnings.append(f"rect ID {item.rect_id or '<无ID>'}：{warning}")
    return result
