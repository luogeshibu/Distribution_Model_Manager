from __future__ import annotations

import math
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.engines.color_engine import ColorChangeResult, ColorRule, apply_line_colors
from g_file_studio.engines.id_engine import direct_layer_elements, local_name
from g_file_studio.engines.rmu_identification_engine import identify_rmus, parse_name_exclusions
from g_file_studio.engines.rmu_group_engine import (
    _find_channel_status_for_rect,
    _rmu_rects_by_bus_tag,
    _single_layer,
)
from g_file_studio.engines.rmu_name_style_engine import (
    RmuNameColorResult as JeddahRmuNameColorResult,
    _Box as _RmuNameBox,
    _find_exact_name_text,
    _set_text_white,
    apply_rmu_name_white,
)


@dataclass
class JeddahRmuNameStandardResult(JeddahRmuNameColorResult):
    """Jeddah-only RMU-name visual standardization result."""

    font_size_changed_count: int = 0
    position_changed_count: int = 0


def _set_jeddah_rmu_name_geometry(
    text: ET.Element,
    rect_box: _RmuNameBox,
    *,
    font_size: float = 50.0,
    top_gap: float = 10.0,
) -> tuple[bool, bool]:
    """Apply only the Jeddah RMU-name typography/placement rule.

    The already-recognized name Text is resized to font size 50 and centered above
    the RMU top frame with a 10-unit clear gap between the Text bounding box and the
    frame.  No RMU recognition or business attributes are changed.
    """

    old_fs = _number(text.get("fs"), 0.0)
    old_w = _number(text.get("w"), 0.0)
    old_h = _number(text.get("h"), 0.0)

    # Preserve the existing Text box proportions when the source has a valid font
    # size.  This keeps long/short cabinet names centered consistently after sizing.
    if old_fs > 0 and old_w > 0:
        new_w = old_w * font_size / old_fs
    elif old_w > 0:
        new_w = old_w
    else:
        new_w = max(font_size, len((text.get("ts") or "").strip()) * font_size * 0.55)

    if old_fs > 0 and old_h > 0:
        new_h = old_h * font_size / old_fs
    elif old_h > 0:
        new_h = old_h
    else:
        new_h = font_size

    font_changed = False
    for key in ("fs", "p_FontWidth", "p_FontHeight"):
        desired = _format_number(font_size)
        if (text.get(key) or "") != desired:
            text.set(key, desired)
            font_changed = True

    desired_w = _format_number(new_w)
    desired_h = _format_number(new_h)
    if (text.get("w") or "") != desired_w:
        text.set("w", desired_w)
        font_changed = True
    if (text.get("h") or "") != desired_h:
        text.set("h", desired_h)
        font_changed = True

    desired_x = rect_box.center_x - new_w / 2.0
    desired_y = rect_box.top - top_gap - new_h
    position_changed = False
    desired_x_text = _format_number(desired_x)
    desired_y_text = _format_number(desired_y)
    if (text.get("x") or "") != desired_x_text:
        text.set("x", desired_x_text)
        position_changed = True
    if (text.get("y") or "") != desired_y_text:
        text.set("y", desired_y_text)
        position_changed = True

    return font_changed, position_changed


def apply_jeddah_rmu_name_standard_to_tree(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    name_exclusions: str = "",
    font_size: int = 50,
    top_gap: int = 10,
    identification=None,
) -> JeddahRmuNameStandardResult:
    """Apply the Jeddah RMU-name presentation rule to an already parsed tree.

    This batch-oriented entry point is deliberately logic-equivalent to
    :func:`apply_jeddah_rmu_name_standard`; it only avoids an extra XML parse/write
    round-trip when the caller is already processing the same tree in memory.
    Standalone callers keep using the path wrapper below unchanged.
    """

    file_path = Path(file_path)
    all_name_positions = ("top",)
    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
            name_positions=all_name_positions,
            name_resolution_mode="selected_direction",
            smart_in_type=True,
            excluded_name_values=parse_name_exclusions(name_exclusions),
        )
    result = JeddahRmuNameStandardResult(
        file_path=file_path,
        identified_rmu_count=identification.cabinet_count,
        named_rmu_count=identification.named_count,
    )

    elements = direct_layer_elements(tree.getroot())
    texts = [element for element in elements if local_name(element.tag) == "Text"]
    used_text_keys: set[str] = set()

    for item in identification.items:
        if not item.name:
            continue
        rect_box = _RmuNameBox(
            item.rect_x,
            item.rect_y,
            item.rect_x + item.rect_w,
            item.rect_y + item.rect_h,
        )
        text = _find_exact_name_text(
            texts,
            name=item.name,
            rect_box=rect_box,
            preferred_position=item.name_position,
            allowed_positions=all_name_positions,
            used_text_keys=used_text_keys,
        )
        if text is None:
            result.warnings.append(
                f"{file_path.name}: RMU {item.name} 已识别，但未定位到可安全标准化的同名 Text。"
            )
            continue

        result.matched_name_text_count += 1
        if _set_text_white(text):
            result.changed_name_text_count += 1
        font_changed, position_changed = _set_jeddah_rmu_name_geometry(
            text,
            rect_box,
            font_size=float(font_size),
            top_gap=float(top_gap),
        )
        if font_changed:
            result.font_size_changed_count += 1
        if position_changed:
            result.position_changed_count += 1
    return result


def apply_jeddah_rmu_name_standard(
    source_path: Path,
    output_path: Path,
    *,
    name_exclusions: str = "",
    font_size: int = 50,
    top_gap: int = 10,
) -> JeddahRmuNameStandardResult:
    """Jeddah-only path wrapper kept for standalone behaviour compatibility."""

    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(source_path)
    result = apply_jeddah_rmu_name_standard_to_tree(
        tree,
        source_path,
        name_exclusions=name_exclusions,
        font_size=font_size,
        top_gap=top_gap,
    )
    changed = (
        result.changed_name_text_count
        or result.font_size_changed_count
        or result.position_changed_count
    )
    if changed:
        if hasattr(ET, "indent"):
            ET.indent(tree, space="    ")
        tmp = output_path.with_name(output_path.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        ET.parse(tmp)
        os.replace(tmp, output_path)
    else:
        shutil.copy2(source_path, output_path)
    return result


@dataclass
class JeddahSmrSmartReplacementResult:
    file_path: Path
    smr_text_count: int = 0
    matched_rmu_count: int = 0
    replaced_count: int = 0
    existing_smart_cleanup_count: int = 0
    smr_text_removed_count: int = 0
    cbreaker_smart_devref_changed_count: int = 0
    frame_red_changed_count: int = 0
    warnings: list[str] = field(default_factory=list)




@dataclass
class JeddahBusDisBlueResult:
    file_path: Path
    scanned_count: int = 0
    eligible_count: int = 0
    changed_count: int = 0
    linked_count: int = 0
    keyid_fallback_count: int = 0
    skipped_count: int = 0


def apply_jeddah_busdis_blue(
    tree: ET.ElementTree,
    file_path: Path,
) -> JeddahBusDisBlueResult:
    """Paint Jeddah distribution ``BusDis`` conductors blue conservatively.

    A BusDis is eligible when it has normal topology references (``link`` or
    ``node_area``).  Some site drawings have a valid distribution bus whose
    topology references are missing; in that case a non-empty ``keyid`` is the
    explicit fallback authority requested by the Jeddah workflow.  BusDis
    objects with neither relation evidence nor keyid are left untouched.

    Only line color is standardized (``lc/lcc``).  Fill/status colors, geometry,
    IDs and references are never changed.
    """

    result = JeddahBusDisBlueResult(file_path=Path(file_path))
    for element in direct_layer_elements(tree.getroot()):
        if local_name(element.tag) != "BusDis":
            continue
        result.scanned_count += 1
        has_relation = bool((element.get("link") or "").strip() or (element.get("node_area") or "").strip())
        has_keyid = bool((element.get("keyid") or "").strip())
        if not has_relation and not has_keyid:
            result.skipped_count += 1
            continue
        result.eligible_count += 1
        if has_relation:
            result.linked_count += 1
        else:
            result.keyid_fallback_count += 1
        changed = (element.get("lc") or "") != "0,0,255" or (element.get("lcc") or "").upper() != "#0000FF"
        element.set("lc", "0,0,255")
        element.set("lcc", "#0000FF")
        if changed:
            result.changed_count += 1
    return result

def apply_jeddah_feedline_solid(
    tree: ET.ElementTree,
    file_path: Path,
) -> ColorChangeResult:
    """Jeddah-only adapter: render every direct Layer <FeedLine> as solid.

    The actual style mutation is delegated to the existing color/style engine.
    This Jeddah adapter does not change that engine or duplicate its rules.  It
    changes only the ``ls`` attribute (solid -> ls=1); line color and every
    other FeedLine attribute remain untouched.
    """

    return apply_line_colors(
        tree,
        Path(file_path),
        [
            ColorRule(
                element_tag="FeedLine",
                display_name="馈线",
                color="#000000",  # required by the existing rule object; color is not applied
                line_style="solid",
                change_color=False,
            )
        ],
    )


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _box(element: ET.Element) -> tuple[float, float, float, float] | None:
    w = _number(element.get("w"))
    h = _number(element.get("h"))
    if w <= 0 or h <= 0:
        return None
    x = _number(element.get("x"))
    y = _number(element.get("y"))
    return x, y, x + w, y + h


def _point_to_box_distance(x: float, y: float, rect_box: tuple[float, float, float, float]) -> float:
    left, top, right, bottom = rect_box
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    return math.hypot(dx, dy)


def _find_rect_for_identification(rects: list[ET.Element], item) -> ET.Element | None:
    by_id = [rect for rect in rects if (rect.get("id") or "").strip() == (item.rect_id or "").strip()]
    candidates = by_id or rects
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda rect: (
            abs(_number(rect.get("x")) - item.rect_x)
            + abs(_number(rect.get("y")) - item.rect_y)
            + abs(_number(rect.get("w")) - item.rect_w)
            + abs(_number(rect.get("h")) - item.rect_h),
            (rect.get("id") or ""),
        ),
    )


def _nearest_unused_smr(
    smr_texts: list[ET.Element],
    rect: ET.Element,
    used_ids: set[int],
) -> ET.Element | None:
    rect_box = _box(rect)
    if rect_box is None:
        return None
    candidates: list[tuple[float, str, ET.Element]] = []
    for text in smr_texts:
        if id(text) in used_ids:
            continue
        text_box = _box(text)
        if text_box is None:
            continue
        cx = (text_box[0] + text_box[2]) / 2.0
        cy = (text_box[1] + text_box[3]) / 2.0
        candidates.append(
            (
                _point_to_box_distance(cx, cy, rect_box),
                (text.get("id") or ""),
                text,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2]


def _set_frame_red(rect: ET.Element) -> bool:
    changed = rect.get("lc") != "255,0,0" or (rect.get("lcc") or "").upper() != "#FF0000"
    rect.set("lc", "255,0,0")
    rect.set("lcc", "#FF0000")
    return changed


def _set_frame_white(rect: ET.Element) -> bool:
    """Force only the RMU frame line color to the Jeddah NORMAL white."""

    changed = rect.get("lc") != "255,255,255" or (rect.get("lcc") or "").upper() != "#FFFFFF"
    rect.set("lc", "255,255,255")
    rect.set("lcc", "#FFFFFF")
    return changed


_SMART_STYLE_KEYS = (
    "ffT", "p_BoldFontFlag", "p_FontWidth", "p_FontHeight", "fs", "ff",
    "bold", "italic", "p_ItalicFontFlag", "lc", "lcc", "fc", "fcc",
    "horizontal", "wm", "fm", "lw", "ls", "opacity", "ShadowType",
    "p_DyColorFlag", "rotate", "tfr",
)


def _apply_smart_text_style(text: ET.Element, reference: ET.Element | None, rect: ET.Element) -> None:
    if reference is not None:
        for key in _SMART_STYLE_KEYS:
            value = reference.get(key)
            if value is not None:
                text.set(key, value)
        width = max(1.0, _number(reference.get("w"), 63.0))
        height = max(1.0, _number(reference.get("h"), 21.0))
    else:
        text.set("ff", "Arial")
        text.set("bold", "false")
        text.set("italic", "false")
        text.set("p_BoldFontFlag", "0")
        text.set("p_ItalicFontFlag", "0")
        text.set("lc", "255,0,0")
        text.set("lcc", "#ff0000")
        text.set("fc", "0,255,0")
        text.set("horizontal", "1")
        text.set("wm", "1")
        text.set("lw", "1")
        text.set("ls", "1")
        width = 63.0
        height = 21.0

    # Jeddah requirement: SMART text size is always 20, even if a reference text
    # happens to use a different size.
    text.set("fs", "20")
    text.set("p_FontWidth", "20")
    text.set("p_FontHeight", "20")
    text.set("ts", "SMART")
    text.set("w", _format_number(width))
    text.set("h", _format_number(height))

    rect_box = _box(rect)
    if rect_box is None:
        return
    left, top, right, _bottom = rect_box
    x = left + ((right - left) - width) / 2.0
    # Existing Jeddah SMART labels sit centered horizontally on the top band/edge
    # of the RMU rectangle.  Keep the same placement convention.
    text.set("x", _format_number(x))
    text.set("y", _format_number(top))


def _center_inside_rect(element: ET.Element, rect: ET.Element) -> bool:
    element_box = _box(element)
    rect_box = _box(rect)
    if element_box is None or rect_box is None:
        return False
    cx = (element_box[0] + element_box[2]) / 2.0
    cy = (element_box[1] + element_box[3]) / 2.0
    left, top, right, bottom = rect_box
    return left <= cx <= right and top <= cy <= bottom


def _smart_text_inside_rmu(smart_texts: list[ET.Element], rect: ET.Element) -> ET.Element | None:
    """Return a SMART label whose center belongs to this RMU.

    Jeddah drawings do not always place the SMART marker on the top band; some valid
    cabinets place it near the lower-right area.  The site rule is therefore simply
    "SMART inside this RMU frame".  Requiring the label center to be inside the
    frame keeps the association conservative without depending on a specific vertical
    placement.
    """

    rect_box = _box(rect)
    if rect_box is None:
        return None
    left, top, right, bottom = rect_box
    candidates: list[tuple[float, float, str, ET.Element]] = []
    for text in smart_texts:
        text_box = _box(text)
        if text_box is None:
            continue
        cx = (text_box[0] + text_box[2]) / 2.0
        cy = (text_box[1] + text_box[3]) / 2.0
        if left <= cx <= right and top <= cy <= bottom:
            candidates.append((abs(cx - (left + right) / 2.0), cy, text.get("id") or "", text))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    return candidates[0][3]


def _remove_direct_element(root: ET.Element, target: ET.Element) -> bool:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                parent.remove(child)
                return True
    return False


@dataclass
class JeddahSmartFrameAuditResult:
    file_path: Path
    scanned_rmu_count: int = 0
    smart_rmu_count: int = 0
    frame_red_changed_count: int = 0
    warnings: list[str] = field(default_factory=list)


def ensure_jeddah_smart_rmu_frames_red(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    identification=None,
) -> JeddahSmartFrameAuditResult:
    """Force every recognized Jeddah SMART RMU frame to red.

    This Jeddah-only consistency pass intentionally uses the same SMART ownership
    rule as the device audit: a cabinet is SMART when the center of its own
    ``Text[ts=SMART]`` belongs to the recognized RMU rectangle.  The SMART Text does
    not need to be fully contained by the frame; this avoids false negatives when a
    valid label extends one or two drawing units across the edge.  Shared RMU
    enhancement/recognition algorithms are not modified.
    """

    file_path = Path(file_path)
    result = JeddahSmartFrameAuditResult(file_path=file_path)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    smart_texts = [
        element for element in elements
        if local_name(element.tag) == "Text"
        and (element.get("ts") or "").strip().upper() == "SMART"
    ]
    if not smart_texts:
        return result

    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
        name_positions=("top", "bottom", "left", "right"),
        smart_in_type=True,
    )
    result.scanned_rmu_count = len(identification.items)
    for item in identification.items:
        rect = _find_rect_for_identification(rects, item)
        if rect is None:
            result.warnings.append(
                f"{file_path.name}: RMU rect {item.rect_id or '<无ID>'} 未定位到实际 rect，跳过 SMART 红框一致性检查。"
            )
            continue
        if _smart_text_inside_rmu(smart_texts, rect) is None:
            continue
        result.smart_rmu_count += 1
        if _set_frame_red(rect):
            result.frame_red_changed_count += 1

    return result

@dataclass
class JeddahNormalFrameAuditResult:
    file_path: Path
    scanned_rmu_count: int = 0
    normal_rmu_count: int = 0
    frame_white_changed_count: int = 0
    warnings: list[str] = field(default_factory=list)


def ensure_jeddah_normal_rmu_frames_white(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    identification=None,
) -> JeddahNormalFrameAuditResult:
    """Force every recognized Jeddah RMU without its own SMART label to white.

    This pass runs after Jeddah SMR -> SMART conversion.  Classification is therefore
    intentionally literal and cabinet-local: if no ``Text[ts=SMART]`` center belongs
    to the recognized RMU rectangle, that cabinet is NORMAL and its frame line must be
    white.  Device SMART/NORMAL replacement remains the responsibility of the active
    server-standard profile pass; this function changes only the frame line color.
    """

    file_path = Path(file_path)
    result = JeddahNormalFrameAuditResult(file_path=file_path)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    smart_texts = [
        element for element in elements
        if local_name(element.tag) == "Text"
        and (element.get("ts") or "").strip().upper() == "SMART"
    ]

    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
        name_positions=("top", "bottom", "left", "right"),
        smart_in_type=True,
    )
    result.scanned_rmu_count = len(identification.items)
    for item in identification.items:
        rect = _find_rect_for_identification(rects, item)
        if rect is None:
            result.warnings.append(
                f"{file_path.name}: RMU rect {item.rect_id or '<无ID>'} 未定位到实际 rect，跳过 NORMAL 白框一致性检查。"
            )
            continue
        if _smart_text_inside_rmu(smart_texts, rect) is not None:
            continue
        result.normal_rmu_count += 1
        if _set_frame_white(rect):
            result.frame_white_changed_count += 1

    return result

@dataclass
class JeddahSmartDeviceAuditResult:
    file_path: Path
    scanned_rmu_count: int = 0
    smart_rmu_count: int = 0
    cbreaker_smart_devref_changed_count: int = 0
    geometry_adjusted_count: int = 0
    warnings: list[str] = field(default_factory=list)


def ensure_jeddah_smart_rmu_devices(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    identification=None,
) -> JeddahSmartDeviceAuditResult:
    """Audit SMART RMUs without changing any device symbol.

    The old Jeddah-only implementation hard-coded several vendor filenames and
    changed CBreakerDis elements before the authoritative site profile ran.  That
    bypassed the server standard and could also alter geometry.  Device replacement
    is now performed by ``apply_smart_profile_to_tree`` from the visible SMART/SMR
    cabinet marker and the active server profile.  This compatibility entry point
    remains as a read-only audit for existing batch-report fields.
    """

    file_path = Path(file_path)
    result = JeddahSmartDeviceAuditResult(file_path=file_path)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    smart_texts = [
        element for element in elements
        if local_name(element.tag) == "Text"
        and (element.get("ts") or "").strip().upper() == "SMART"
    ]
    if not smart_texts:
        return result

    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
        name_positions=("top", "bottom", "left", "right"),
        smart_in_type=True,
    )
    result.scanned_rmu_count = len(identification.items)
    for item in identification.items:
        rect = _find_rect_for_identification(rects, item)
        if rect is None:
            result.warnings.append(
                f"{file_path.name}: RMU rect {item.rect_id or '<无ID>'} 未定位到实际 rect，跳过 SMART 图元检查。"
            )
            continue
        if _smart_text_inside_rmu(smart_texts, rect) is None:
            continue
        result.smart_rmu_count += 1

    return result

@dataclass
class JeddahExactTextRemovalResult:
    file_path: Path
    matched_count: int = 0
    removed_count: int = 0


def remove_jeddah_ht_texts(
    tree: ET.ElementTree,
    file_path: Path,
) -> JeddahExactTextRemovalResult:
    """Remove the exact Jeddah-only ``H.T`` Text marker.

    This is intentionally a narrow site-specific rule: only direct Layer ``Text``
    elements whose trimmed text equals ``H.T`` (case-insensitive) are removed.
    Text containing ``H.T`` as only a substring is not touched.  Shared Text/RMU
    processing engines are not changed.
    """

    file_path = Path(file_path)
    result = JeddahExactTextRemovalResult(file_path=file_path)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    targets = [
        element
        for element in elements
        if local_name(element.tag) == "Text"
        and (element.get("ts") or "").strip().upper() == "H.T"
    ]
    result.matched_count = len(targets)
    for text in targets:
        if _remove_direct_element(root, text):
            result.removed_count += 1
    return result


@dataclass
class JeddahChannelStatusRemovalResult:
    file_path: Path
    scanned_rmu_count: int = 0
    matched_status_count: int = 0
    removed_status_count: int = 0


def remove_jeddah_channel_status_points(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    identification=None,
) -> JeddahChannelStatusRemovalResult:
    """Delete Jeddah RMU ``channel_status`` red points.

    The association logic is intentionally delegated to the existing RMU red-status
    positioning implementation: the same BusDis RMU pairing and the same
    ``channel_status`` Status lookup are used.  Before pairing, this function now
    obtains the authoritative RMU rectangle IDs from ``identify_rmus()`` so a plain
    ``BusDis`` rectangle cannot be treated as an RMU accidentally.  The Jeddah-only
    difference is the final action: the matched Status element is removed instead
    of repositioned.
    """

    file_path = Path(file_path)
    result = JeddahChannelStatusRemovalResult(file_path=file_path)
    layer = _single_layer(tree, file_path)
    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
        name_positions=("top",),
        smart_in_type=True,
    )
    validated_rmu_rect_ids = {
        item.rect_id for item in identification.items if item.rect_id
    }
    pairs = _rmu_rects_by_bus_tag(layer, "BusDis", validated_rmu_rect_ids)
    result.scanned_rmu_count = len(pairs)
    claimed: set[int] = set()
    targets: list[ET.Element] = []
    for rect, bus in pairs:
        status = _find_channel_status_for_rect(layer, rect, bus, claimed)
        if status is None:
            continue
        claimed.add(id(status))
        result.matched_status_count += 1
        targets.append(status)

    for status in targets:
        if _remove_direct_element(layer, status):
            result.removed_status_count += 1
    return result

@dataclass
class JeddahDuplicateSmartCleanupResult:
    file_path: Path
    scanned_rmu_count: int = 0
    duplicate_rmu_count: int = 0
    smart_text_removed_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class JeddahAdjacentMeasurementCleanupResult:
    file_path: Path
    value_text_count: int = 0
    measurement_text_count: int = 0
    adjacent_pair_count: int = 0
    removed_text_count: int = 0


def _smart_texts_inside_rmu(smart_texts: list[ET.Element], rect: ET.Element) -> list[ET.Element]:
    """Return all SMART labels whose centers belong to one RMU, in XML order.

    The whole cabinet interior is checked because valid Jeddah SMART markers may be
    located near the bottom-right as well as on the top band.  XML order is preserved
    so duplicate cleanup keeps the original/first label unchanged.
    """

    rect_box = _box(rect)
    if rect_box is None:
        return []
    left, top, right, bottom = rect_box
    matches: list[ET.Element] = []
    for text in smart_texts:
        text_box = _box(text)
        if text_box is None:
            continue
        cx = (text_box[0] + text_box[2]) / 2.0
        cy = (text_box[1] + text_box[3]) / 2.0
        if left <= cx <= right and top <= cy <= bottom:
            matches.append(text)
    return matches


def remove_duplicate_smart_labels_in_rmus(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    identification=None,
) -> JeddahDuplicateSmartCleanupResult:
    """Jeddah-only cleanup for duplicate SMART labels in distribution RMUs.

    Every RMU returned by the existing read-only RMU identification engine is
    checked.  If more than one direct ``Text[ts=SMART]`` belongs to the same RMU,
    the first label in the original XML order is preserved and only the later
    duplicates are removed.  A single SMART label is never moved or restyled.
    """

    file_path = Path(file_path)
    result = JeddahDuplicateSmartCleanupResult(file_path=file_path)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    smart_texts = [
        element
        for element in elements
        if local_name(element.tag) == "Text"
        and (element.get("ts") or "").strip().upper() == "SMART"
    ]
    if not smart_texts:
        return result

    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
        name_positions=("top", "bottom", "left", "right"),
        smart_in_type=True,
    )
    result.scanned_rmu_count = len(identification.items)
    removed_ids: set[int] = set()
    for item in identification.items:
        rect = _find_rect_for_identification(rects, item)
        if rect is None:
            result.warnings.append(
                f"{file_path.name}: RMU rect {item.rect_id or '<无ID>'} 未定位到实际 rect，跳过 SMART 重复检查。"
            )
            continue
        candidates = [
            text for text in _smart_texts_inside_rmu(smart_texts, rect)
            if id(text) not in removed_ids
        ]
        if len(candidates) <= 1:
            continue
        result.duplicate_rmu_count += 1
        # Preserve the first/original SMART Text exactly as-is.  Only later
        # duplicates are removed; this also honors the Jeddah rule that an
        # existing SMART marker must not be rewritten or repositioned.
        for duplicate in candidates[1:]:
            if _remove_direct_element(root, duplicate):
                removed_ids.add(id(duplicate))
                result.smart_text_removed_count += 1

    return result

def _vertical_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _horizontal_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    return max(b[0] - a[2], a[0] - b[2], 0.0)


def remove_jeddah_adjacent_measurement_texts(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    max_horizontal_gap: float = 10.0,
) -> JeddahAdjacentMeasurementCleanupResult:
    """Remove the exact adjacent ``2000.00`` + ``UPDATED_MEASURMENT`` pair.

    Both strings must be separate direct Layer Text elements, exact after trimming
    (case-insensitive for ``UPDATED_MEASURMENT``), on the same visual line and
    horizontally touching/near-touching.  The two Text elements are removed only
    as a one-to-one adjacent pair.  Matching strings elsewhere in the drawing are
    left untouched when they are not adjacent.
    """

    file_path = Path(file_path)
    result = JeddahAdjacentMeasurementCleanupResult(file_path=file_path)
    root = tree.getroot()
    texts = [e for e in direct_layer_elements(root) if local_name(e.tag) == "Text"]
    values = [e for e in texts if (e.get("ts") or "").strip() == "2000.00"]
    measurements = [
        e for e in texts
        if (e.get("ts") or "").strip().upper() == "UPDATED_MEASURMENT"
    ]
    result.value_text_count = len(values)
    result.measurement_text_count = len(measurements)

    used_measurements: set[int] = set()
    pairs: list[tuple[ET.Element, ET.Element]] = []
    for value in values:
        value_box = _box(value)
        if value_box is None:
            continue
        candidates: list[tuple[float, float, str, ET.Element]] = []
        for measurement in measurements:
            if id(measurement) in used_measurements:
                continue
            measurement_box = _box(measurement)
            if measurement_box is None:
                continue
            gap = _horizontal_gap(value_box, measurement_box)
            if gap > max_horizontal_gap:
                continue
            overlap = _vertical_overlap(value_box, measurement_box)
            min_height = min(value_box[3] - value_box[1], measurement_box[3] - measurement_box[1])
            if min_height <= 0 or overlap < min_height * 0.5:
                continue
            center_delta = abs(
                ((value_box[1] + value_box[3]) / 2.0)
                - ((measurement_box[1] + measurement_box[3]) / 2.0)
            )
            candidates.append((gap, center_delta, measurement.get("id") or "", measurement))
        if not candidates:
            continue
        candidates.sort(key=lambda row: (row[0], row[1], row[2]))
        measurement = candidates[0][3]
        used_measurements.add(id(measurement))
        pairs.append((value, measurement))

    result.adjacent_pair_count = len(pairs)
    for value, measurement in pairs:
        if _remove_direct_element(root, value):
            result.removed_text_count += 1
        if _remove_direct_element(root, measurement):
            result.removed_text_count += 1
    return result

def replace_jeddah_smr_with_smart(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    identification=None,
) -> JeddahSmrSmartReplacementResult:
    """Jeddah-only SMR -> SMART visual normalization.

    SMR is mandatory-normalized to SMART without changing the shared RMU engine:

    1. If the matched RMU already contains its own SMART label, remove only
       the external SMR Text and force the cabinet frame to red.  The existing SMART
       label and cabinet devices are left untouched.
    2. If the cabinet has no SMART label, convert the matched SMR Text to a top-centred
       SMART label (font size 20) and force the frame to red. Device devref correctness
       is handled by the following fixed SMART-device standardization pass, so the same
       rule is used for both pre-existing SMART cabinets and newly converted SMR cabinets.

    Existing RMU identification remains read-only and unchanged.
    """

    file_path = Path(file_path)
    result = JeddahSmrSmartReplacementResult(file_path=file_path)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    smr_texts = [
        element for element in elements
        if local_name(element.tag) == "Text" and (element.get("ts") or "").strip().upper() == "SMR"
    ]
    smart_references = [
        element for element in elements
        if local_name(element.tag) == "Text" and (element.get("ts") or "").strip().upper() == "SMART"
    ]
    result.smr_text_count = len(smr_texts)
    if not smr_texts:
        return result

    if identification is None:
        identification = identify_rmus(
            tree,
            file_path,
        name_positions=("top", "bottom", "left", "right"),
        smart_in_type=True,
    )
    smr_items = [item for item in identification.items if "SMR" in (item.smart_source or "").upper()]
    if not smr_items:
        result.warnings.append(
            f"{file_path.name}: 发现 {len(smr_texts)} 个 SMR Text，但现有 RMU 识别未匹配到有效环网柜。"
        )
        return result

    used_text_ids: set[int] = set()
    for item in smr_items:
        rect = _find_rect_for_identification(rects, item)
        if rect is None:
            result.warnings.append(
                f"{file_path.name}: SMR 对应 RMU rect {item.rect_id or '<无ID>'} 未定位到实际 rect。"
            )
            continue
        smr_text = _nearest_unused_smr(smr_texts, rect, used_text_ids)
        if smr_text is None:
            result.warnings.append(
                f"{file_path.name}: RMU rect {item.rect_id or '<无ID>'} 已识别为 SMR，但未找到可处理的 SMR Text。"
            )
            continue
        used_text_ids.add(id(smr_text))
        result.matched_rmu_count += 1

        if _set_frame_red(rect):
            result.frame_red_changed_count += 1

        existing_smart = _smart_text_inside_rmu(smart_references, rect)
        if existing_smart is not None:
            # The cabinet already has the correct in-frame SMART marker.  The user
            # explicitly requested only two actions for this case: delete SMR and
            # make the frame red.  Do not duplicate/reposition SMART and do not alter
            # CBreakerDis devrefs here.
            if _remove_direct_element(root, smr_text):
                result.smr_text_removed_count += 1
            result.existing_smart_cleanup_count += 1
            continue

        # No SMART marker exists inside this SMR cabinet. Reuse the SMR Text object so
        # its XML id remains unique, but visually/semantically convert it to SMART.
        # Prefer a SMART label from another cabinet as the style reference.
        reference = smart_references[0] if smart_references else None
        _apply_smart_text_style(smr_text, reference, rect)
        result.replaced_count += 1

    return result