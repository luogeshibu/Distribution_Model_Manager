from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any

from g_file_studio.engines.id_engine import direct_layers, local_name
from g_file_studio.engines.rmu_identification_engine import RmuIdentificationResult
from g_file_studio.engines.poke_text_rules import is_red_text, text_instance_key
from g_file_studio.engines.rmu_poke_engine import (
    _Box,
    _allocate_poke_id,
    _all_used_ids,
    _box,
    _move_poke_to_background,
    _new_poke,
    _number,
)


# Station-jump labels are intentionally kept stricter than ordinary drawing
# text.  A confirmed label is a compact ``STATION-SUFFIX`` or
# ``STATION SUFFIX`` string containing both letters and digits. Requiring
# exactly one separator prevents long equipment/design labels from becoming
# station-jump candidates merely because they end in digits.
_STATION_LABEL_RE = re.compile(
    r"^\s*(?P<station>[A-Za-z0-9][A-Za-z0-9_]*)\s*(?:[-–—]|\s)\s*(?P<suffix>[A-Za-z0-9][A-Za-z0-9_]*)\s*$"
)

# A station label is commonly followed by the standard RMU name on the
# next/previous line, for example ``ANS2-44`` + ``(35033)``. Only a
# parenthesized pure-number label is allowed to become a locate target; a
# plain number or a number with a suffix is never used.
_PARENTHESIZED_RMU_LABEL_RE = re.compile(
    r"^[\(（]\s*(?P<label>[0-9]+)\s*[\)）]$",
)

# 站点跳转使用的相邻环网柜名称，超过该距离就不能作为 locateLabel。
RMU_ADJACENT_NAME_MAX_DISTANCE = 100.0


# Canonical station-jump Poke properties copied from the user-provided
# JM2-J2 reference Poke (id=17001493) in JED-CTL-AJWD-15.sln.pic(2).g.
# Geometry (id/x/y/w/h), ahref and G File Studio metadata remain dynamic;
# every other Poke property below is normalized exactly to the reference.
_STATION_JUMP_POKE_REFERENCE_ATTRS: dict[str, str] = {
    'PlaneState19': '0',
    'PlaneState42': '0',
    'clip': 'false',
    'PlaneState7': '0',
    'af': '2147483647',
    'PlaneState8': '0',
    'PlaneState45': '0',
    'PlaneState40': '0',
    'fc': '100,100,100',
    'ShadowType': '0',
    'isDisplay': '1',
    'PlaneState9': '0',
    'PlaneState23': '0',
    'p_FatherObjId': '',
    'PlaneState30': '0',
    'PlaneState14': '0',
    'PlaneState48': '0',
    'lw': '1',
    'ls': '1',
    'PlaneState38': '0',
    'PlaneState36': '0',
    'PlaneState0': '1',
    'PlaneState37': '0',
    'p_EngcodeString': '',
    'lcc': '#000000',
    'PlaneState33': '0',
    'af4': '2147483647',
    'tfr': 'rotate(0) scale(1,1)',
    'p_RectStyle': '1',
    'onMouseLeftDoubleClickAciton': '',
    'PlaneState32': '0',
    'PlaneState6': '0',
    'PlaneState44': '0',
    'RectStyle': '1',
    'onMouseRightOneClickAction': '',
    'PlaneState49': '0',
    'PlaneState31': '0',
    'lc': '0,0,0',
    'switchapp': '1',
    'PlaneState25': '0',
    'PlaneState4': '0',
    'PlaneState17': '0',
    'fm': '1',
    'PlaneState12': '0',
    'aliasType': '',
    'onMouseHoverLeaveAction': '',
    'PlaneState47': '0',
    'PlaneState39': '0',
    'PlaneState46': '0',
    'LevelEnd': '16',
    'p_DyColorFlag': '0',
    'onMouseLeftOneClickAction': '',
    'PlaneState20': '0',
    'onMouseHoverEnterAction': '',
    'PlaneState27': '0',
    'p_ShowModeMask': '3',
    'rotate': '0',
    'PlaneState15': '0',
    'PlaneState21': '0',
    'PlaneState3': '0',
    'eventRegister': '',
    'PlaneState5': '0',
    'switchappflag': '1',
    'p_SelfDefString': '',
    'fcc': '#646464',
    'PlaneState29': '0',
    'af3': '2147483647',
    'trend_color': '0',
    'PlaneState10': '0',
    'PlaneState28': '0',
    'onMouseRightDoubleClickAction': '',
    'PlaneState41': '0',
    'PlaneState34': '0',
    'opacity': '1',
    'af2': '2147483647',
    'PlaneState1': '0',
    'PlaneState16': '0',
    'PlaneState18': '0',
    'PlaneState26': '0',
    'p_AssFlag': '128',
    'PlaneState24': '0',
    'rain_bow': '0',
    'PlaneState2': '0',
    'PlaneState11': '0',
    'PlaneState13': '0',
    'LevelStart': '0',
    'PlaneState35': '0',
    'PlaneState43': '0',
    'PlaneState22': '0',
    'devref': '',
}


@dataclass
class StationPokeChange:
    label_text: str
    station_key: str
    station_full_name: str
    text_id: str
    poke_id: str
    target_file: str
    action: str
    confidence: str
    adjacent_rmu_names: str = ""
    recognition_source: str = ""
    removed_duplicates: int = 0
    locate_label: str = ""


@dataclass
class StationPokeRecord:
    label_text: str
    station_key: str
    station_full_name: str = ""
    adjacent_rmu_names: str = ""
    text_id: str = ""
    poke_id: str = ""
    target_file: str = ""
    action: str = "skipped"
    confidence: str = ""
    recognition_source: str = ""
    reason: str = ""
    locate_label: str = ""
    current_station: bool = False


@dataclass
class StationPokeResult:
    file_path: Path
    scanned_text_count: int = 0
    candidate_count: int = 0
    eligible_count: int = 0
    added_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    removed_duplicate_count: int = 0
    skipped_count: int = 0
    classification_excluded_count: int = 0
    changes: list[StationPokeChange] = field(default_factory=list)
    records: list[StationPokeRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def extract_rmu_locate_label(label: str) -> str:
    """Return a standard RMU locate label from a nearby drawing Text.

    Only the drawing convention ``(14020)``/``（14020）`` is accepted. Plain
    numbers and labels with a suffix are intentionally rejected because they
    can be ordinary operating annotations rather than a locate target.
    """
    value = re.sub(r"\s+", " ", str(label or "").strip())
    match = _PARENTHESIZED_RMU_LABEL_RE.fullmatch(value)
    if match is None:
        return ""
    return match.group("label")


def _is_parenthesized_rmu_label(label: str) -> bool:
    value = re.sub(r"\s+", " ", str(label or "").strip())
    return _PARENTHESIZED_RMU_LABEL_RE.fullmatch(value) is not None


def _is_standard_rmu_label_text(element: ET.Element, locate_label: str) -> bool:
    """Reject compact operating annotations such as the yellow ``240``.

    The parenthesized syntax is the hard boundary. Presentation attributes are
    deliberately not used to turn a plain number into a locate target.
    """
    raw = re.sub(r"\s+", " ", str(element.get("ts") or "").strip())
    return _is_parenthesized_rmu_label(raw) and bool(locate_label)


def extract_station_key(label: str) -> str:
    """Extract the station business key from a terminal label.

    Examples: DHN-40 -> DHN, BWD2-49 -> BWD2, FEL 03 -> FEL,
    JM2-J2 -> JM2, 5MR-23 -> 5MR.  The trailing drawing-side token is
    deliberately ignored by the database lookup and ahref generation.
    """
    value = re.sub(r"\s+", " ", str(label or "").strip())
    match = _STATION_LABEL_RE.fullmatch(value)
    if not match:
        return ""
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        return ""
    station = re.sub(r"\s+", " ", match.group("station").strip(" -–—"))
    # Avoid classifying device labels such as Y-1 / Q-1 as stations.
    letters = sum(ch.isalpha() for ch in station)
    if letters < 2:
        return ""
    return station


def extract_interval_locate_label(label: str) -> str:
    """Build an interval locate label from a station terminal label.

    When a station terminal has no adjacent RMU name, labels such as
    ``RDS-09`` and ``DHN-40`` identify the interval directly.  The station
    overview uses the corresponding ``AH3`` prefix: ``AH309`` and ``AH340``.
    Keep the suffix exactly as drawn so leading zeroes are preserved.
    """
    value = re.sub(r"\s+", " ", str(label or "").strip())
    match = _STATION_LABEL_RE.fullmatch(value)
    if match is None:
        return ""
    suffix = match.group("suffix").strip()
    if not suffix.isdigit():
        return ""
    return f"AH3{suffix}"


def build_station_target_file(station_full_name: str, locate_label: str = "") -> str:
    """Build the station overview ahref, optionally focusing on a remote RMU."""
    target = f"{str(station_full_name or '').strip()}.sln.pic.g"
    # ``extract_rmu_locate_label`` validates drawing Text such as ``(35033)``.
    # The station matcher stores the already-normalized value as ``35033``;
    # accept that internal form here so the query is not silently discarded.
    raw_locate = str(locate_label or "").strip()
    locate = extract_rmu_locate_label(raw_locate)
    if not locate and re.fullmatch(r"\d+", raw_locate):
        locate = raw_locate
    # Interval fallback labels are already normalized as AH3 + numeric suffix
    # (for example RDS-09 -> AH309). Keep this form when building the ahref.
    if not locate and re.fullmatch(r"AH3\d+", raw_locate, flags=re.IGNORECASE):
        locate = raw_locate.upper()
    if locate:
        target += f"?locateLabel={locate}&&scaleFlag=true"
    return target


def _center(box: _Box) -> tuple[float, float]:
    return ((box.left + box.right) / 2.0, (box.top + box.bottom) / 2.0)


def _contains(outer: _Box, inner: _Box, tolerance: float = 3.0) -> bool:
    cx, cy = _center(inner)
    return (
        outer.left - tolerance <= cx <= outer.right + tolerance
        and outer.top - tolerance <= cy <= outer.bottom + tolerance
    )


def _intersection_area(a: _Box, b: _Box) -> float:
    width = max(0.0, min(a.right, b.right) - max(a.left, b.left))
    height = max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
    return width * height


def _overlap_ratio_text(container: _Box, text: _Box) -> float:
    area = max(text.width * text.height, 1.0)
    return _intersection_area(container, text) / area


def _is_inside_rmu(text_box: _Box, identification: RmuIdentificationResult) -> bool:
    cx, cy = _center(text_box)
    for item in identification.items:
        left = item.rect_x
        top = item.rect_y
        right = left + item.rect_w
        bottom = top + item.rect_h
        if left <= cx <= right and top <= cy <= bottom:
            return True
    return False


def _rmu_locate_label_score(station_box: _Box, label_box: _Box) -> tuple[float, float, float] | None:
    """Score a likely standard RMU label adjacent to a station label.

    RMU labels in the source drawings are laid out immediately above/below
    (and occasionally beside) the station terminal.  Require directional
    adjacency and alignment rather than using unrestricted nearest-text
    matching, which could steal a feeder/device number from the drawing.
    """
    max_gap = RMU_ADJACENT_NAME_MAX_DISTANCE
    alignment_limit = max(45.0, min(100.0, max(station_box.width, label_box.width) * 0.75))
    station_cx, station_cy = _center(station_box)
    label_cx, label_cy = _center(label_box)

    # Text bounding boxes in exported G files can overlap by a few units even
    # when the rendered labels are visibly stacked.  Use center direction and
    # allow a small edge overlap instead of requiring strict box separation.
    overlap_tolerance = 20.0
    if label_cy < station_cy and label_box.bottom <= station_box.top + overlap_tolerance:
        gap = max(0.0, station_box.top - label_box.bottom)
        alignment = abs(label_cx - station_cx)
        direction = 0.0
    elif label_cy > station_cy and label_box.top >= station_box.bottom - overlap_tolerance:
        gap = max(0.0, label_box.top - station_box.bottom)
        alignment = abs(label_cx - station_cx)
        direction = 0.0
    elif label_cx < station_cx and label_box.right <= station_box.left + overlap_tolerance:
        gap = max(0.0, station_box.left - label_box.right)
        alignment = abs(label_cy - station_cy)
        direction = 1.0
    elif label_cx > station_cx and label_box.left >= station_box.right - overlap_tolerance:
        gap = max(0.0, label_box.left - station_box.right)
        alignment = abs(label_cy - station_cy)
        direction = 1.0
    else:
        return None

    if gap > max_gap or alignment > alignment_limit:
        return None
    # Prefer the normal vertical layout, then the smallest edge gap and best
    # alignment.  The final distance makes ties deterministic for dense text.
    distance = math.hypot(station_cx - label_cx, station_cy - label_cy)
    if distance > RMU_ADJACENT_NAME_MAX_DISTANCE:
        return None
    return direction, gap + alignment * 0.01, distance


def _find_station_rmu_locate_label(layer: ET.Element, station_text: ET.Element) -> str:
    candidates = _station_rmu_locate_label_candidates(layer, station_text)
    # The effective station locate target is always singular.  If several
    # valid parenthesized RMU labels are within the 100-unit neighborhood,
    # select the physically nearest one rather than rejecting the station.
    return candidates[0][1] if candidates else ""


def _station_rmu_locate_label_candidates(
    layer: ET.Element,
    station_text: ET.Element,
) -> list[tuple[tuple[float, float, float], str]]:
    """Find the standard RMU name paired with one station terminal Text."""
    station_box = _box(station_text)
    if station_box is None:
        return []
    candidates: list[tuple[tuple[float, float, float], str]] = []
    for element in list(layer):
        if element is station_text or local_name(element.tag) != "Text":
            continue
        locate_label = extract_rmu_locate_label(element.get("ts") or "")
        if not locate_label:
            continue
        if not _is_standard_rmu_label_text(element, locate_label):
            continue
        label_box = _box(element)
        if label_box is None:
            continue
        score = _rmu_locate_label_score(station_box, label_box)
        if score is not None:
            candidates.append((score, locate_label))
    if not candidates:
        return []
    # Candidate score = (direction preference, gap/alignment score, Euclidean
    # distance).  For station -> adjacent-RMU association the business rule is
    # explicit: when several parenthesized RMU names are valid, the nearest
    # one wins.  Direction/alignment only break exact distance ties.
    candidates.sort(key=lambda item: (item[0][2], item[0][0], item[0][1], item[1]))
    return candidates


def _has_explicit_background_color(element: ET.Element) -> bool:
    """Return whether an element explicitly carries a visible fill color."""
    fill_mode = (element.get("fm") or "").strip().casefold()
    if fill_mode in {"0", "false", "none", "transparent"}:
        return False
    for attribute in ("fcc", "fc", "fill", "fillColor", "background", "bgcolor"):
        value = (element.get(attribute) or "").strip().casefold()
        if value and value not in {"none", "transparent", "null"}:
            return True
    return False


def _colored_background_contains(
    layer: ET.Element,
    text_box: _Box,
    related_pokes: list[ET.Element] | None = None,
) -> bool:
    """Require a colored background object to support a station label.

    The supplied drawings use a gray colored ``poke`` behind the station Text.
    A compact colored rect/roundrect/ellipse is also supported for drawings
    that store the background as a shape.  The Text element's own ``fc/fcc``
    attributes never count as that background; the background must be a separate
    visible filled object. Geometry alone or an uncolored legacy Poke is not
    sufficient.
    """
    candidates = list(related_pokes or []) + list(layer)
    seen: set[int] = set()
    for element in candidates:
        marker = id(element)
        if marker in seen:
            continue
        seen.add(marker)
        tag = local_name(element.tag).casefold()
        if tag == "poke" and (
            (element.get("gfs_rmu_poke") or "") == "1"
            or (element.get("gfs_device_poke") or "") == "1"
        ):
            continue
        if tag not in {"poke", "rect", "roundrect", "ellipse"}:
            continue
        if not _has_explicit_background_color(element):
            continue
        box = _box(element)
        if box is None or box.width <= 0 or box.height <= 0:
            # A metadata-linked existing station Poke is still a valid
            # background even if an old file omitted its geometry attributes.
            if tag == "poke" and element in (related_pokes or []):
                return True
            continue
        if box.width > 500 or box.height > 160:
            continue
        if _contains(box, text_box, tolerance=6.0) or _overlap_ratio_text(box, text_box) >= 0.55:
            return True
    return False

def _related_station_pokes(layer: ET.Element, text_box: _Box, station_key: str, text_id: str) -> list[ET.Element]:
    candidates: list[ET.Element] = []
    for element in list(layer):
        if local_name(element.tag) != "poke":
            continue
        if (element.get("gfs_rmu_poke") or "") == "1" or (element.get("gfs_device_poke") or "") == "1":
            continue
        if text_id and (element.get("gfs_station_text_id") or "") == text_id:
            candidates.append(element)
            continue
        box = _box(element)
        if box is None:
            continue
        if _contains(box, text_box, tolerance=6.0) or _overlap_ratio_text(box, text_box) >= 0.35:
            candidates.append(element)
    # Keep identity uniqueness while preserving XML order.
    result: list[ET.Element] = []
    seen: set[int] = set()
    for item in candidates:
        marker = id(item)
        if marker not in seen:
            seen.add(marker)
            result.append(item)
    return result


def _choose_primary_poke(pokes: list[ET.Element], text_box: _Box, station_key: str, text_id: str) -> ET.Element:
    tcx, tcy = _center(text_box)

    def score(element: ET.Element) -> tuple[float, float, float, str]:
        metadata = 0.0
        if text_id and (element.get("gfs_station_text_id") or "") == text_id:
            metadata -= 3.0
        box = _box(element)
        if box is None:
            return (metadata + 20.0, 20.0, math.inf, element.get("id") or "")
        contains_penalty = 0.0 if _contains(box, text_box, tolerance=6.0) else 1.0
        overlap_penalty = 1.0 - min(1.0, _overlap_ratio_text(box, text_box))
        pcx, pcy = _center(box)
        distance = math.hypot(pcx - tcx, pcy - tcy)
        return (metadata + contains_penalty, overlap_penalty, distance, element.get("id") or "")

    return min(pokes, key=score)


def _ensure_station_attributes(
    poke: ET.Element,
    *,
    target_file: str,
    station_key: str,
    text_id: str,
    text_box: _Box,
    preserve_geometry: bool,
) -> bool:
    """Normalize one station-jump Poke to the JM2-J2 reference properties.

    The reference's non-geometric Poke attributes are copied exactly. The
    current object's id/geometry are preserved when reusing an existing Poke;
    a newly created Poke uses the detected station-label geometry. ahref and
    G File Studio metadata are dynamic by definition.
    """
    old = dict(poke.attrib)
    poke_id = (poke.get("id") or "").strip()
    if preserve_geometry:
        x = poke.get("x") or _number(text_box.left)
        y = poke.get("y") or _number(text_box.top)
        w = poke.get("w") or _number(text_box.width)
        h = poke.get("h") or _number(text_box.height)
    else:
        x = _number(text_box.left)
        y = _number(text_box.top)
        w = _number(text_box.width)
        h = _number(text_box.height)

    desired = dict(_STATION_JUMP_POKE_REFERENCE_ATTRS)
    desired.update({
        "id": poke_id,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "ahref": target_file,
        "gfs_station_poke": "1",
        "gfs_station_name": station_key,
        "gfs_station_text_id": text_id,
    })

    # Remove unrelated legacy attributes so a station-jump Poke has the same
    # complete property set as the JM2-J2 reference, plus dynamic fields.
    if old != desired:
        poke.attrib.clear()
        poke.attrib.update(desired)
        return True
    return False


def _logical_source_stem(file_path: Path) -> str:
    """Source filename used only as a self-jump safety check, never for naming."""
    name = file_path.name
    match = re.match(r"^(.*)\.sln\.pic(?:\(\d+\))?\.g$", name, flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.match(r"^(.*?)(?:\(\d+\))?\.g$", name, flags=re.I)
    return (match.group(1) if match else file_path.stem).strip()


def apply_station_pokes(
    tree: ET.ElementTree,
    file_path: Path,
    identification: RmuIdentificationResult,
    *,
    current_station_name: str,
    station_resolver: Callable[[str], Any],
    allow_same_station_terminals: bool = False,
    classification_marker_entries: tuple[object, ...] | list[object] = (),
    excluded_text_keys: set[str] | frozenset[str] | tuple[str, ...] = (),
) -> StationPokeResult:
    """Create/update station-jump Pokes such as DHN-40 -> JED-CTL-DHN.

    Station recognition uses only the station Text graphic constraints: the
    label must contain both letters and digits, have a colored background, and
    the station-name Text itself must NOT be red.  A Text already owned by an
    RMU/device Poke branch is excluded so one concrete Text can never serve two
    Poke roles.
    Line geometry and connection references are not used. Database resolution
    remains the existing SUBSTATION.NAME ->
    SUBAREA_ID -> SUBCONTROLAREA.NAME chain.  A nearby parenthesized
    pure-number Text within 100 drawing units is used as ``locateLabel``. If
    several valid parenthesized RMU names are found, only the nearest one is
    selected. If no RMU name is available, a numeric station suffix such as
    ``RDS-09`` falls back to the interval locate label ``AH309``.
    """
    result = StationPokeResult(file_path=file_path)
    root = tree.getroot()
    used_ids = _all_used_ids(root)
    resolver_cache: dict[str, Any] = {}
    current_key = (current_station_name or "").strip().casefold()
    reserved_text_keys = set(excluded_text_keys or ())

    for layer in direct_layers(root):
        for text in list(layer):
            if local_name(text.tag) != "Text":
                continue
            result.scanned_text_count += 1
            label = (text.get("ts") or "").strip()
            station_key = extract_station_key(label)
            if not station_key:
                continue
            text_box = _box(text)
            if text_box is None:
                continue
            text_id = (text.get("id") or "").strip()
            text_key = text_instance_key(text)
            if text_key in reserved_text_keys:
                result.candidate_count += 1
                result.skipped_count += 1
                result.classification_excluded_count += 1
                reason = (
                    f"站点跳转候选 {label!r} 的 Text ID={text_id or '<无ID>'} "
                    "已被 RMU 或 AR/LBS/SEC 设备名称占用；同一个 Text 只能属于一种 Poke 角色。"
                )
                result.records.append(StationPokeRecord(
                    label_text=label,
                    station_key=station_key,
                    text_id=text_id,
                    action="skipped",
                    recognition_source="text_ownership",
                    reason=reason,
                ))
                continue
            if is_red_text(text):
                result.candidate_count += 1
                result.skipped_count += 1
                reason = (
                    f"站点跳转候选 {label!r} 的名称 Text 为红色；"
                    "红色 Text 只用于 AR/LBS/SEC 设备名称，不能作为站点跳转名称。"
                )
                result.records.append(StationPokeRecord(
                    label_text=label,
                    station_key=station_key,
                    text_id=text_id,
                    action="skipped",
                    recognition_source="text_color",
                    reason=reason,
                ))
                continue
            if _is_inside_rmu(text_box, identification):
                continue
            related = _related_station_pokes(layer, text_box, station_key, text_id)
            locate_candidates = _station_rmu_locate_label_candidates(layer, text)
            # Final station-jump target may carry one and only one RMU locate
            # label.  The candidate list is already ordered by physical
            # distance, so multiple nearby RMU labels collapse to the nearest.
            locate_candidate_count = len(locate_candidates)
            selected_locate = locate_candidates[0][1] if locate_candidates else ""
            adjacent_rmu_names = f"({selected_locate})" if selected_locate else ""
            colored_background = _colored_background_contains(
                layer,
                text_box,
                related_pokes=related,
            )
            locate_source = ""
            if selected_locate:
                locate_label = selected_locate
                locate_source = "rmu_name"
            else:
                locate_label = extract_interval_locate_label(label)
                if locate_label:
                    locate_source = "station_interval"
            # Same-station labels are normally local feeder titles and remain
            # protected. A pre-existing Poke with one proven locateLabel is
            # the narrow exception: it is an explicit navigation target, not
            # a guessed new self-jump.
            same_station_terminal = bool(
                allow_same_station_terminals
                and related
                and colored_background
                and locate_label
                # The explicit RMU-name locate value is the only safe exception
                # for a current-station terminal.  An interval fallback must not
                # re-enable a self-jump merely because the label ends in digits.
                and locate_source == "rmu_name"
            )
            if current_key and station_key.casefold() == current_key and not same_station_terminal:
                continue

            result.candidate_count += 1

            if not colored_background:
                result.skipped_count += 1
                reason = (
                    f"站点跳转候选 {label!r} 缺少明确的彩色背景，"
                    "约束条件不满足，不创建或更新站点跳转 Poke。"
                )
                result.warnings.append(reason)
                result.records.append(StationPokeRecord(
                    label_text=label,
                    station_key=station_key,
                    adjacent_rmu_names=adjacent_rmu_names,
                    text_id=text_id,
                    poke_id=(related[0].get("id") or "").strip() if related else "",
                    action="skipped",
                    confidence="HIGH" if related else "",
                    recognition_source="background_color",
                    reason=reason,
                ))
                continue

            if related:
                confidence = "HIGH"
                recognition_source = "existing_poke"
            else:
                confidence = "MEDIUM"
                recognition_source = "background_color"
            if locate_source == "station_interval":
                recognition_source = "station_interval"

            cache_key = station_key.casefold()
            try:
                context = resolver_cache.get(cache_key)
                if context is None:
                    context = station_resolver(station_key)
                    resolver_cache[cache_key] = context
            except Exception as exc:
                result.skipped_count += 1
                reason = f"站点跳转候选 {label!r} 提取变电站 {station_key!r} 后数据库校验失败：{exc}"
                result.warnings.append(reason)
                result.records.append(StationPokeRecord(
                    label_text=label,
                    station_key=station_key,
                    adjacent_rmu_names=adjacent_rmu_names,
                    text_id=text_id,
                    action="skipped",
                    confidence=confidence,
                    recognition_source=recognition_source,
                    reason=reason,
                ))
                continue

            station_full_name = str(getattr(context, "station_full_name", "") or "").strip()
            if not station_full_name:
                result.skipped_count += 1
                reason = f"变电站 {station_key!r} 未解析到完整站名，已跳过。"
                result.warnings.append(reason)
                result.records.append(StationPokeRecord(
                    label_text=label,
                    station_key=station_key,
                    adjacent_rmu_names=adjacent_rmu_names,
                    text_id=text_id,
                    action="skipped",
                    confidence=confidence,
                    recognition_source=recognition_source,
                    current_station=True,
                    reason=reason,
                ))
                continue
            # facID is not required.  As a safety-only self-jump filter, compare
            # the DB-resolved station full name with the source filename stem.
            # This never constructs a target name from the filename; it only
            # prevents local feeder titles such as AJWD-16 inside
            # JED-CTL-AJWD-16.sln.pic.g from being mistaken for a remote station.
            source_stem = _logical_source_stem(file_path).casefold()
            station_full_key = station_full_name.casefold()
            if (
                source_stem == station_full_key or source_stem.startswith(station_full_key + "-")
            ) and not same_station_terminal:
                result.skipped_count += 1
                reason = (
                    f"站点跳转候选 {label!r} 数据库解析为本图当前变电站 {station_full_name!r}，"
                    "属于本地站/馈线标题，不创建对端变电站跳转。"
                )
                result.records.append(StationPokeRecord(
                    label_text=label,
                    station_key=station_key,
                    adjacent_rmu_names=adjacent_rmu_names,
                    station_full_name=station_full_name,
                    text_id=text_id,
                    action="skipped",
                    confidence=confidence,
                    recognition_source=recognition_source,
                    reason=reason,
                ))
                continue

            target_file = build_station_target_file(station_full_name, locate_label)
            result.eligible_count += 1

            if related:
                poke = _choose_primary_poke(related, text_box, station_key, text_id)
                removed = 0
                for extra in related:
                    if extra is poke:
                        continue
                    layer.remove(extra)
                    removed += 1
                result.removed_duplicate_count += removed
                changed = _ensure_station_attributes(
                    poke,
                    target_file=target_file,
                    station_key=station_key,
                    text_id=text_id,
                    text_box=text_box,
                    preserve_geometry=True,
                )
                moved = _move_poke_to_background(layer, poke)
                action = "updated" if (changed or moved or removed) else "unchanged"
                if action == "updated":
                    result.updated_count += 1
                else:
                    result.unchanged_count += 1
                if removed:
                    result.warnings.append(
                        f"站点跳转 {label!r} 发现 {removed + 1} 个相关 Poke，已删除多余 {removed} 个，仅保留 1 个。"
                    )
            else:
                poke_id = _allocate_poke_id(root, used_ids)
                poke = _new_poke(root, poke_id)
                _ensure_station_attributes(
                    poke,
                    target_file=target_file,
                    station_key=station_key,
                    text_id=text_id,
                    text_box=text_box,
                    preserve_geometry=False,
                )
                _move_poke_to_background(layer, poke)
                action = "added"
                result.added_count += 1

            result.changes.append(StationPokeChange(
                label_text=label,
                station_key=station_key,
                station_full_name=station_full_name,
                adjacent_rmu_names=adjacent_rmu_names,
                text_id=text_id,
                poke_id=(poke.get("id") or "").strip(),
                target_file=target_file,
                action=action,
                confidence=confidence,
                recognition_source=recognition_source,
                removed_duplicates=(removed if related else 0),
                locate_label=locate_label,
            ))
            if action == "added":
                reason = "未找到可复用的站点跳转 Poke，已根据结构识别结果新增并写入跳转。"
            elif action == "updated":
                reason = "已复用现有站点跳转 Poke，并更新目标/Line Color/元数据或清理重复 Poke。"
            else:
                reason = "现有站点跳转 Poke 已符合目标，无需修改。"
            if related and removed:
                reason += f" 同时删除重复 Poke {removed} 个。"
            if locate_label:
                if locate_source == "station_interval":
                    reason += f" 未找到相邻环网柜名，按站点间隔 {label} 生成 locateLabel={locate_label}。"
                else:
                    if locate_candidate_count > 1:
                        reason += (
                            f" 100 范围内识别到 {locate_candidate_count} 个括号环网柜名候选，"
                            f"已取距离最近的 ({locate_label}) 并写入 locateLabel。"
                        )
                    else:
                        reason += f" 已识别相邻环网柜名 ({locate_label})，并写入 locateLabel。"
            result.records.append(StationPokeRecord(
                label_text=label,
                station_key=station_key,
                station_full_name=station_full_name,
                adjacent_rmu_names=adjacent_rmu_names,
                text_id=text_id,
                poke_id=(poke.get("id") or "").strip(),
                target_file=target_file,
                action=action,
                confidence=confidence,
                recognition_source=recognition_source,
                reason=reason,
                locate_label=locate_label,
            ))

    return result
