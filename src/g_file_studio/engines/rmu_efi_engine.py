from __future__ import annotations

import copy
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.services.id_rule_service import IdRule


EARTH_DEVREF = "#NariPd_Earth.pwbh.icn.g:NariPd_Earth"
NORMAL_DEVREF = "#NariPd_Normal.pwbh.icn.g:NariPd_Normal"

_SUPPORTED_SIDES = {"left", "top"}
# Distances in this module use the G file's own x/y coordinate units.
# They are NOT screen pixels: zooming the viewer changes screen pixels but must
# not change the saved geometry.
#
# Placement is frame-first:
#   1) place NariPd_Normal from the near RMU frame edge;
#   2) then reposition NariPd_Earth from the Normal icon;
#   3) keep the two icons visually centre-aligned.
#
# The supplied Jeddah drawings contain manually-authored left-side pairs where
# Normal.x -> Earth.x is 27 G units.  With the requested 5-unit visible gap,
# the rendered Normal footprint along the placement axis is therefore 22 G
# units.  This calibrated footprint is used for both confirmed layouts.
_DEFAULT_NORMAL_EARTH_GAP_PX = 5.0
_DEFAULT_FRAME_MARGIN_PX = 10.0
_NORMAL_VISIBLE_AXIS_SPAN_G = 22.0
_LEFT_NORMAL_EARTH_Y_OFFSET = 7.0
_TOP_NORMAL_EARTH_X_OFFSET = 5.0


@dataclass
class RmuEfiFileResult:
    file_name: str
    detected_rmus: int = 0
    already_present: int = 0
    added: int = 0
    skipped_no_earth: int = 0
    skipped_unsupported_side: int = 0
    skipped_insufficient_space: int = 0
    rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RmuEfiBatchResult:
    files: list[RmuEfiFileResult] = field(default_factory=list)

    @property
    def detected_rmus(self) -> int:
        return sum(item.detected_rmus for item in self.files)

    @property
    def already_present(self) -> int:
        return sum(item.already_present for item in self.files)

    @property
    def added(self) -> int:
        return sum(item.added for item in self.files)

    @property
    def skipped_no_earth(self) -> int:
        return sum(item.skipped_no_earth for item in self.files)

    @property
    def skipped_unsupported_side(self) -> int:
        return sum(item.skipped_unsupported_side for item in self.files)

    @property
    def skipped_insufficient_space(self) -> int:
        return sum(item.skipped_insufficient_space for item in self.files)


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _float_attr(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name) or default)
    except (TypeError, ValueError):
        return default


def _center(element: ET.Element) -> tuple[float, float]:
    x = _float_attr(element, "x")
    y = _float_attr(element, "y")
    w = _float_attr(element, "w")
    h = _float_attr(element, "h")
    return x + w / 2.0, y + h / 2.0


def _inside_frame(element: ET.Element, frame: ET.Element, tolerance: float = 2.0) -> bool:
    cx, cy = _center(element)
    x = _float_attr(frame, "x")
    y = _float_attr(frame, "y")
    w = _float_attr(frame, "w")
    h = _float_attr(frame, "h")
    return x - tolerance <= cx <= x + w + tolerance and y - tolerance <= cy <= y + h + tolerance


def _is_rmu_frame(frame: ET.Element, layer_children: list[ET.Element]) -> bool:
    """Recognize the dashed RMU cabinet frame from its contents, not just its size.

    Jeddah drawings use two visual layouts: a vertical-bus cabinet (Earth on the
    left-middle) and a horizontal-bus cabinet (Earth on the top-middle).  Both have
    a dashed rect and contain a BusDis plus multiple CBreakerDis elements.
    """
    if _local_name(frame.tag) != "rect":
        return False
    if str(frame.get("ls") or "").strip() != "2":
        return False
    w = _float_attr(frame, "w")
    h = _float_attr(frame, "h")
    if not (180.0 <= w <= 280.0 and 180.0 <= h <= 280.0):
        return False

    bus_count = 0
    breaker_count = 0
    for element in layer_children:
        if not _inside_frame(element, frame, tolerance=4.0):
            continue
        tag = _local_name(element.tag)
        if tag == "BusDis":
            bus_count += 1
        elif tag == "CBreakerDis":
            breaker_count += 1
    return bus_count >= 1 and breaker_count >= 2


def _nearest_supported_side(earth: ET.Element, frame: ET.Element) -> str:
    ecx, ecy = _center(earth)
    fx = _float_attr(frame, "x")
    fy = _float_attr(frame, "y")
    fw = _float_attr(frame, "w")
    fh = _float_attr(frame, "h")
    distances = {
        "left": abs(ecx - fx),
        "top": abs(ecy - fy),
        "right": abs((fx + fw) - ecx),
        "bottom": abs((fy + fh) - ecy),
    }
    return min(distances, key=distances.get)


def _neutral_normal_template(layer_children: list[ET.Element]) -> ET.Element:
    """Return a neutral EFI Normal icon template.

    Prefer a business-neutral NariPd_Normal already present in the same drawing.
    If none exists, use the canonical visual attributes observed in the Jeddah G
    drawings.  Business identity fields are intentionally not invented.
    """
    normals = [
        element
        for element in layer_children
        if _local_name(element.tag) == "pwbh" and str(element.get("devref") or "") == NORMAL_DEVREF
    ]
    for element in normals:
        if not str(element.get("keyid1") or "").strip() and str(element.get("p_ReportType1") or "0") in {"", "0"}:
            return copy.deepcopy(element)
    if normals:
        clone = copy.deepcopy(normals[0])
        for key in (
            "keyid1",
            "app",
            "app1",
            "voltype1",
        ):
            clone.attrib.pop(key, None)
        clone.set("state1", "")
        clone.set("p_ReportType1", "0")
        return clone

    return ET.Element(
        "pwbh",
        {
            "p_AssFlag": "128",
            "rain_bow": "0",
            "onMouseHoverLeaveAction": "",
            "switchappflag": "1",
            "p_EngcodeString": "",
            "opacity": "1",
            "af": "2147483647",
            "clip": "false",
            "LevelEnd": "16",
            "state1": "",
            "onMouseLeftDoubleClickAciton": "",
            "switchapp": "1",
            "h": "36",
            "af4": "2147483647",
            "onMouseRightDoubleClickAction": "",
            "devref": NORMAL_DEVREF,
            "trend_color": "0",
            "p_ReportType1": "0",
            "eventRegister": "",
            "af3": "2147483647",
            "p_SelfDefString": "",
            "key_name1": "",
            "p_NameString": "",
            "onMouseRightOneClickAction": "",
            "ShadowType": "0",
            "p_DyColorFlag": "0",
            "onMouseLeftOneClickAction": "",
            "af2": "2147483647",
            "onMouseHoverEnterAction": "",
            "p_FatherObjId": "",
            "isDisplay": "1",
            "tfr": "rotate(0) scale(2,2)",
            "composeType": "GIcon",
            "LevelStart": "0",
            "p_ShowModeMask": "3",
            "aliasType": "",
            "w": "36",
        },
    )


def _max_valid_id(layer_children: list[ET.Element], rule: IdRule) -> str | None:
    values = [
        str(element.get("id") or "")
        for element in layer_children
        if _local_name(element.tag) == "pwbh" and rule.matches(str(element.get("id") or ""))
    ]
    return max(values, key=int) if values else None


def _frame_label(frame: ET.Element, layer_children: list[ET.Element]) -> str:
    fx = _float_attr(frame, "x")
    fy = _float_attr(frame, "y")
    fw = _float_attr(frame, "w")
    # RMU title is normally immediately above the frame.  Use it only for the report.
    candidates: list[tuple[float, str]] = []
    for element in layer_children:
        if _local_name(element.tag) != "Text":
            continue
        text = str(element.get("ts") or "").strip()
        if not text:
            continue
        cx, cy = _center(element)
        if fx - 40 <= cx <= fx + fw + 40 and fy - 120 <= cy <= fy + 20:
            candidates.append((abs(cx - (fx + fw / 2.0)) + abs(cy - fy), text))
    return min(candidates)[1] if candidates else ""


def add_rmu_efi_normal_icons(
    tree: ET.ElementTree,
    *,
    file_name: str,
    pwbh_id_rule: IdRule,
    normal_earth_gap_px: float = _DEFAULT_NORMAL_EARTH_GAP_PX,
    frame_margin_px: float = _DEFAULT_FRAME_MARGIN_PX,
) -> RmuEfiFileResult:
    root = tree.getroot()
    layer = next((element for element in root.iter() if _local_name(element.tag) == "Layer"), None)
    if layer is None:
        raise ValueError(f"G 文件没有 <Layer>：{file_name}")

    children = list(layer)
    frames = [element for element in children if _is_rmu_frame(element, children)]
    result = RmuEfiFileResult(file_name=file_name, detected_rmus=len(frames))
    template = _neutral_normal_template(children)
    current_max = _max_valid_id(children, pwbh_id_rule)

    # Process in document order and refresh the child list after each insertion so
    # duplicate prevention also holds within this run.
    for frame in frames:
        children = list(layer)
        # Existing EFI Normal is an absolute no-op for this module.  Check it
        # before Earth or any other layout analysis so an already-correct RMU is
        # never classified, moved, rewritten, or otherwise touched.
        normals = [
            element
            for element in children
            if _local_name(element.tag) == "pwbh"
            and str(element.get("devref") or "") == NORMAL_DEVREF
            and _inside_frame(element, frame)
        ]
        if normals:
            result.already_present += 1
            result.rows.append({
                "file": file_name,
                "rmu": _frame_label(frame, children),
                "frame_id": str(frame.get("id") or ""),
                "result": "ALREADY_PRESENT_NO_CHANGE",
                "detail": f"框内已存在 {NORMAL_DEVREF}；本环网柜不进入 Earth/位置处理，保持原样",
            })
            continue

        earths = [
            element
            for element in children
            if _local_name(element.tag) == "pwbh"
            and str(element.get("devref") or "") == EARTH_DEVREF
            and _inside_frame(element, frame)
        ]
        if not earths:
            result.skipped_no_earth += 1
            result.rows.append({
                "file": file_name,
                "rmu": _frame_label(frame, children),
                "frame_id": str(frame.get("id") or ""),
                "result": "SKIPPED_NO_EARTH",
                "detail": "环网柜缺少 Normal，但框内未找到 NariPd_Earth.pwbh.icn.g；未修改",
            })
            continue

        # The Jeddah drawings have exactly the two layouts supplied by the user.
        # If multiple Earth icons ever occur, select the one closest to a supported
        # frame side so the behavior remains deterministic.
        supported_earths = [
            earth for earth in earths if _nearest_supported_side(earth, frame) in _SUPPORTED_SIDES
        ]
        if not supported_earths:
            result.skipped_unsupported_side += 1
            result.rows.append({
                "file": file_name,
                "rmu": _frame_label(frame, children),
                "frame_id": str(frame.get("id") or ""),
                "result": "SKIPPED_UNSUPPORTED_SIDE",
                "detail": "Earth 不在左边中点或上边中点附近，未猜测新增位置",
            })
            continue

        earth = min(
            supported_earths,
            key=lambda item: (
                min(
                    abs(_center(item)[0] - _float_attr(frame, "x")),
                    abs(_center(item)[1] - _float_attr(frame, "y")),
                ),
                str(item.get("id") or ""),
            ),
        )
        side = _nearest_supported_side(earth, frame)
        ecx, ecy = _center(earth)
        fx = _float_attr(frame, "x")
        fy = _float_attr(frame, "y")
        nw = _float_attr(template, "w", 36.0) or 36.0
        nh = _float_attr(template, "h", 36.0) or 36.0

        # Distances are strict G-coordinate distances.  The RMU frame is the
        # primary reference: Normal is placed first from the near frame edge.
        # Earth is then repositioned from Normal so the requested edge-to-edge
        # gap is preserved.  We never compromise the frame margin in order to
        # keep the old Earth position.
        earth_x = _float_attr(earth, "x")
        earth_y = _float_attr(earth, "y")
        requested_gap = max(0.0, float(normal_earth_gap_px))
        requested_margin = max(0.0, float(frame_margin_px))

        if side == "left":
            normal_x = fx + requested_margin
            # Keep the established visual-centre calibration on the Y axis.
            normal_y = earth_y + _LEFT_NORMAL_EARTH_Y_OFFSET
            target_earth_x = normal_x + _NORMAL_VISIBLE_AXIS_SPAN_G + requested_gap
            target_earth_y = normal_y - _LEFT_NORMAL_EARTH_Y_OFFSET
        elif side == "top":
            normal_y = fy + requested_margin
            # Keep the established visual-centre calibration on the X axis.
            normal_x = earth_x + _TOP_NORMAL_EARTH_X_OFFSET
            target_earth_y = normal_y + _NORMAL_VISIBLE_AXIS_SPAN_G + requested_gap
            target_earth_x = normal_x - _TOP_NORMAL_EARTH_X_OFFSET
        else:
            result.skipped_unsupported_side += 1
            continue

        # Keep both icon reference boxes inside the RMU frame.  If the user's
        # two requested distances physically do not fit in the cabinet, skip
        # rather than silently shrinking either distance.
        fw = _float_attr(frame, "w")
        fh = _float_attr(frame, "h")
        ew = _float_attr(earth, "w", 30.0) or 30.0
        eh = _float_attr(earth, "h", 30.0) or 30.0
        if side == "left":
            fits = (
                fx <= normal_x <= fx + fw
                and fx <= target_earth_x
                and target_earth_x + ew <= fx + fw + 1e-9
            )
        else:
            fits = (
                fy <= normal_y <= fy + fh
                and fy <= target_earth_y
                and target_earth_y + eh <= fy + fh + 1e-9
            )
        if not fits:
            result.skipped_insufficient_space += 1
            result.rows.append({
                "file": file_name,
                "rmu": _frame_label(frame, children),
                "frame_id": str(frame.get("id") or ""),
                "result": "SKIPPED_INSUFFICIENT_SPACE",
                "detail": (
                    f"{side} 布局无法同时满足：EFI-柜框={_number(requested_margin)} G单位、"
                    f"Normal-Earth={_number(requested_gap)} G单位；未缩小参数、未移动其他设备"
                ),
            })
            continue

        normal = copy.deepcopy(template)
        current_max = pwbh_id_rule.build_after(current_max)
        normal.set("id", current_max)
        normal.set("devref", NORMAL_DEVREF)
        normal.set("x", _number(normal_x))
        normal.set("y", _number(normal_y))
        normal.set("w", _number(nw))
        normal.set("h", _number(nh))
        normal.set("tfr", "rotate(0) scale(2,2)")
        normal.attrib.pop("rotate", None)
        # Never clone a business identity into the newly added EFI visual icon.
        for key in ("keyid1", "app", "app1", "voltype1"):
            normal.attrib.pop(key, None)
        normal.set("state1", "")
        normal.set("p_ReportType1", "0")

        # Earth is deliberately placed after Normal.  Only its geometry moves;
        # its ID, business attributes and devref remain unchanged.
        earth.set("x", _number(target_earth_x))
        earth.set("y", _number(target_earth_y))

        earth_index = list(layer).index(earth)
        layer.insert(earth_index, normal)
        result.added += 1
        result.rows.append({
            "file": file_name,
            "rmu": _frame_label(frame, list(layer)),
            "frame_id": str(frame.get("id") or ""),
            "result": "ADDED",
            "detail": (
                f"Earth {earth.get('id','')} 原方向={side}；新增 Normal {current_max}；"
                f"Normal x/y=({_number(normal_x)},{_number(normal_y)})；"
                f"Earth 新 x/y=({_number(target_earth_x)},{_number(target_earth_y)})；"
                f"参数：Normal-Earth={_number(requested_gap)} G单位，EFI-柜框={_number(requested_margin)} G单位；"
                f"Normal 可见轴向占位={_number(_NORMAL_VISIBLE_AXIS_SPAN_G)} G单位；"
                "先以柜框定位 Normal，再由 Normal 定位 Earth，并使用现场校准做视觉中心对齐"
            ),
        })

    return result


def write_tree_atomic(tree: ET.ElementTree, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    temporary = output_path.with_name(output_path.name + ".tmp")
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    ET.parse(temporary)
    os.replace(temporary, output_path)
