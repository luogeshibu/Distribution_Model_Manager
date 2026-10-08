from __future__ import annotations

import math
import os
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from g_file_studio.engines.frame_engine import (
    Box,
    FrameError,
    GFS_FRAME_COMPONENT_ATTRIBUTE,
    GFS_FRAME_ROLE_ATTRIBUTE,
    GFS_FRAME_TEMPLATE_ATTRIBUTE,
    GFS_FRAME_TYPE_ATTRIBUTE,
    GFS_FRAME_TYPE_BUILTIN,
    GFS_FRAME_TYPE_CUSTOM,
    _shift_custom_template_components,
    boxes_intersect,
    identify_outer_frame_lines,
    line_endpoints,
    parse_d_points,
    parse_number,
    read_canvas_size,
    require_single_direct_layer,
    set_line_geometry,
    shift_element,
)


class MarginAdjustmentError(RuntimeError):
    """图形边距调整错误。"""


class UnsupportedExistingFrameError(MarginAdjustmentError):
    """检测到非内置图框时使用的用户可读错误。"""


@dataclass(frozen=True)
class ExistingFrame:
    outer_lines: dict[str, ET.Element]
    frame_box: Box
    components: tuple[ET.Element, ...]
    left_margin: float
    top_margin: float
    right_margin: float
    bottom_margin: float
    detection_mode: str = "marked"


@dataclass(frozen=True)
class FrameRemovalResult:
    """Result of removing an already-present drawing frame before replacement."""

    removed_count: int = 0
    detection_modes: tuple[str, ...] = ()

    @property
    def had_existing_frame(self) -> bool:
        return self.removed_count > 0


@dataclass(frozen=True)
class MarginAdjustmentResult:
    output_path: Path
    had_existing_frame: bool
    old_canvas_width: int
    old_canvas_height: int
    new_canvas_width: int
    new_canvas_height: int
    body_left_margin: float
    body_top_margin: float
    body_right_margin: float
    body_bottom_margin: float
    frame_left_margin: float | None = None
    frame_top_margin: float | None = None
    frame_right_margin: float | None = None
    frame_bottom_margin: float | None = None
    frame_detection_mode: str | None = None
    removed_existing_frame_count: int = 0
    removed_existing_frame_modes: tuple[str, ...] = ()


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _combine_boxes(boxes: Iterable[Box]) -> Box | None:
    values = list(boxes)
    if not values:
        return None
    return Box(
        min(box.left for box in values),
        min(box.top for box in values),
        max(box.right for box in values),
        max(box.bottom for box in values),
    )


LINE_LIKE_TAGS = {
    "connectline",
    "line",
    "bus",
    "busdis",
    "feedline",
    "flowline",
    "polyline",
    "lwpolyline",
}


def _node_box(node: ET.Element) -> Box | None:
    """计算单个 XML 节点的真实可见边界。

    线状图元的 ``w``/``h`` 在部分 G 文件中是绘图工具内部参数，并不代表
    实际可见尺寸。例如 ConnectLine 可能带有 ``w="5000"``，但真正的线段
    只有几十像素。此类图元必须优先使用 ``d`` 或端点坐标计算边界，不能
    使用 ``x + w`` / ``y + h``。
    """
    tag = _local_name(node.tag).lower()

    numeric: dict[str, float] = {}
    for name in (
        "x", "y", "x1", "y1", "x2", "y2", "cx", "cy",
        "mergex", "mergey", "w", "h", "width", "height", "rx", "ry",
    ):
        raw = node.get(name)
        if raw not in (None, ""):
            try:
                numeric[name] = parse_number(raw)
            except ValueError as exc:
                raise MarginAdjustmentError(
                    f"元素 <{_local_name(node.tag)}> 的 {name} 不是有效数字：{raw!r}"
                ) from exc

    # 线状图元只采用真实路径点或端点。禁止让 ConnectLine.w=5000 等内部参数
    # 扩大画布边界。
    if tag in LINE_LIKE_TAGS:
        d_points = parse_d_points(node.get("d", ""))
        if d_points:
            xs = [x for x, _ in d_points]
            ys = [y for _, y in d_points]
            return Box(min(xs), min(ys), max(xs), max(ys))

        if all(name in numeric for name in ("x1", "y1", "x2", "y2")):
            return Box(
                min(numeric["x1"], numeric["x2"]),
                min(numeric["y1"], numeric["y2"]),
                max(numeric["x1"], numeric["x2"]),
                max(numeric["y1"], numeric["y2"]),
            )

        # 极少数退化线状图元没有 d 和完整端点，此时只把 x/y 当成一个可见点，
        # 仍然不能使用 w/h。
        if "x" in numeric and "y" in numeric:
            return Box(numeric["x"], numeric["y"], numeric["x"], numeric["y"])
        return None

    xs: list[float] = []
    ys: list[float] = []

    for name in ("x", "x1", "x2", "cx", "mergex"):
        if name in numeric:
            xs.append(numeric[name])
    for name in ("y", "y1", "y2", "cy", "mergey"):
        if name in numeric:
            ys.append(numeric[name])

    width = numeric.get("w", numeric.get("width"))
    height = numeric.get("h", numeric.get("height"))
    if "x" in numeric and width is not None:
        xs.append(numeric["x"] + width)
    if "y" in numeric and height is not None:
        ys.append(numeric["y"] + height)
    if "mergex" in numeric and width is not None:
        xs.append(numeric["mergex"] + width)
    if "mergey" in numeric and height is not None:
        ys.append(numeric["mergey"] + height)
    if "cx" in numeric and "rx" in numeric:
        xs.extend((numeric["cx"] - numeric["rx"], numeric["cx"] + numeric["rx"]))
    if "cy" in numeric and "ry" in numeric:
        ys.extend((numeric["cy"] - numeric["ry"], numeric["cy"] + numeric["ry"]))

    for x, y in parse_d_points(node.get("d", "")):
        xs.append(x)
        ys.append(y)

    if not xs or not ys:
        return None
    return Box(min(xs), min(ys), max(xs), max(ys))


def subtree_box(element: ET.Element) -> Box | None:
    return _combine_boxes(
        box
        for node in element.iter()
        if (box := _node_box(node)) is not None
    )


def elements_box(elements: Iterable[ET.Element]) -> Box | None:
    return _combine_boxes(
        box
        for element in elements
        if (box := subtree_box(element)) is not None
    )


def _frame_is_canvas_outer(frame: Box, width: int, height: int) -> bool:
    """避免把普通设备矩形或表格误判为画布外框。"""
    if frame.width < width * 0.55 or frame.height < height * 0.55:
        return False
    tolerance_x = max(20.0, width * 0.03)
    tolerance_y = max(20.0, height * 0.03)
    margins = (
        frame.left,
        frame.top,
        width - frame.right,
        height - frame.bottom,
    )
    if any(value < -max(tolerance_x, tolerance_y) for value in margins):
        return False
    return (
        frame.left <= width * 0.25 + tolerance_x
        and width - frame.right <= width * 0.25 + tolerance_x
        and frame.top <= height * 0.25 + tolerance_y
        and height - frame.bottom <= height * 0.25 + tolerance_y
    )


def _make_existing_frame(
    outer_lines: dict[str, ET.Element],
    frame_box: Box,
    components: Sequence[ET.Element],
    canvas_width: int,
    canvas_height: int,
    *,
    detection_mode: str,
) -> ExistingFrame:
    return ExistingFrame(
        outer_lines=outer_lines,
        frame_box=frame_box,
        components=tuple(components),
        left_margin=frame_box.left,
        top_margin=frame_box.top,
        right_margin=canvas_width - frame_box.right,
        bottom_margin=canvas_height - frame_box.bottom,
        detection_mode=detection_mode,
    )


def _detect_marked_builtin_frame(
    layer: ET.Element,
    canvas_width: int,
    canvas_height: int,
) -> ExistingFrame | None:
    components = [
        element
        for element in list(layer)
        if element.get(GFS_FRAME_TYPE_ATTRIBUTE) == GFS_FRAME_TYPE_BUILTIN
    ]
    if not components:
        return None

    try:
        outer_lines, frame_box = identify_outer_frame_lines(
            components,
            canvas_width,
            canvas_height,
        )
    except (FrameError, ValueError) as exc:
        raise MarginAdjustmentError(
            "文件带有 G File Studio 内置图框标记，但图框结构已损坏或不完整。"
            "请重新添加内置图框后再处理。"
        ) from exc

    if not _frame_is_canvas_outer(frame_box, canvas_width, canvas_height):
        raise MarginAdjustmentError(
            "文件带有 G File Studio 内置图框标记，但图框已不在画布外围。"
            "请重新添加内置图框后再处理。"
        )

    return _make_existing_frame(
        outer_lines,
        frame_box,
        components,
        canvas_width,
        canvas_height,
        detection_mode="marker",
    )


def _center_inside(inner: Box, outer: Box, tolerance: float = 0.0) -> bool:
    return (
        outer.left - tolerance <= inner.center_x <= outer.right + tolerance
        and outer.top - tolerance <= inner.center_y <= outer.bottom + tolerance
    )


def _legacy_builtin_components(
    elements: Sequence[ET.Element],
    outer_lines: dict[str, ET.Element],
    frame_box: Box,
) -> tuple[ET.Element, ...] | None:
    """识别 v2.2.0 及更早版本写入、尚未带身份标记的内置图框。

    这是严格的结构指纹匹配，不再使用“从外框开始无限几何连通扩散”。
    因此主体馈线即使与图框接触，也不会被误归类为图框组件。
    """
    outer_ids = {id(element) for element in outer_lines.values()}

    rect_candidates: list[tuple[ET.Element, Box]] = []
    for element in elements:
        if _local_name(element.tag).lower() != "rect":
            continue
        box = subtree_box(element)
        if box is not None:
            rect_candidates.append((element, box))

    title_rects = [
        (element, box)
        for element, box in rect_candidates
        if abs(box.left - (frame_box.left + 10.0)) <= 20.0
        and abs(box.top - (frame_box.top + 10.0)) <= 20.0
        and 250.0 <= box.width <= 360.0
        and 40.0 <= box.height <= 90.0
    ]
    info_rects = [
        (element, box)
        for element, box in rect_candidates
        if abs(frame_box.right - box.right) <= 25.0
        and abs(frame_box.bottom - box.bottom) <= 25.0
        and 300.0 <= box.width <= 420.0
        and 70.0 <= box.height <= 135.0
    ]
    if len(title_rects) != 1 or len(info_rects) != 1:
        return None

    title_rect, title_box = title_rects[0]
    info_rect, info_box = info_rects[0]
    if title_rect is info_rect:
        return None

    title_texts: list[ET.Element] = []
    title_pokes: list[ET.Element] = []
    info_texts: list[ET.Element] = []
    info_lines: list[ET.Element] = []

    for element in elements:
        if id(element) in outer_ids or element in {title_rect, info_rect}:
            continue
        box = subtree_box(element)
        if box is None:
            continue
        tag = _local_name(element.tag)

        if tag == "Text" and boxes_intersect(box, title_box, tolerance=3.0):
            if _center_inside(box, title_box, tolerance=3.0):
                title_texts.append(element)
                continue
        if tag.lower() == "poke" and boxes_intersect(box, title_box, tolerance=4.0):
            if abs(box.width - title_box.width) <= 20.0 and abs(box.height - title_box.height) <= 20.0:
                title_pokes.append(element)
                continue
        if tag == "Text" and boxes_intersect(box, info_box, tolerance=3.0):
            if _center_inside(box, info_box, tolerance=5.0):
                info_texts.append(element)
                continue
        if tag.lower() == "line" and boxes_intersect(box, info_box, tolerance=4.0):
            endpoints = line_endpoints(element)
            if endpoints is not None:
                x1, y1, x2, y2 = endpoints
                tolerance = 8.0
                if all(
                    (
                        info_box.left - tolerance <= x <= info_box.right + tolerance
                        and info_box.top - tolerance <= y <= info_box.bottom + tolerance
                    )
                    for x, y in ((x1, y1), (x2, y2))
                ):
                    info_lines.append(element)

    # 当前内置模板的稳定结构：1 个标题文字、1 个 poke、
    # 右下信息栏 12 个文字和 5 条分隔线。
    if not (
        len(title_texts) == 1
        and len(title_pokes) == 1
        and len(info_texts) == 12
        and len(info_lines) == 5
    ):
        return None

    already_selected = {
        id(element)
        for element in (
            *outer_lines.values(),
            title_rect,
            title_texts[0],
            title_pokes[0],
            info_rect,
            *info_texts,
            *info_lines,
        )
    }

    # 某些旧版内置模板还会保留 1 个左上 logo image，
    # 以及 4 个重合的微小 ConnectLine 模板辅助点。它们同样属于图框，
    # 不能参与主体边界计算。
    optional_images: list[ET.Element] = []
    optional_connect_lines: list[ET.Element] = []
    for element in elements:
        if id(element) in already_selected:
            continue
        box = subtree_box(element)
        if box is None:
            continue
        tag = _local_name(element.tag).lower()
        if (
            tag == "image"
            and frame_box.left <= box.left <= frame_box.left + 700.0
            and abs(box.top - (frame_box.top + 10.0)) <= 25.0
            and 80.0 <= box.width <= 320.0
            and 35.0 <= box.height <= 100.0
        ):
            optional_images.append(element)
        elif (
            tag == "connectline"
            and box.width <= 12.0
            and box.height <= 12.0
            and abs(box.center_x - (frame_box.left + 383.0)) <= 24.0
            and abs(box.center_y - (frame_box.top + 483.0)) <= 24.0
        ):
            optional_connect_lines.append(element)

    if len(optional_images) > 1:
        return None
    if len(optional_connect_lines) == 4:
        centers_x = [subtree_box(element).center_x for element in optional_connect_lines]  # type: ignore[union-attr]
        centers_y = [subtree_box(element).center_y for element in optional_connect_lines]  # type: ignore[union-attr]
        if max(centers_x) - min(centers_x) > 8.0 or max(centers_y) - min(centers_y) > 8.0:
            optional_connect_lines = []
    else:
        # 该区域出现零散 ConnectLine 时按主体元素处理；只有严格的 4 点重合结构
        # 才认定为旧版内置模板辅助点。
        optional_connect_lines = []

    components = [
        *outer_lines.values(),
        title_rect,
        title_texts[0],
        title_pokes[0],
        info_rect,
        *info_texts,
        *info_lines,
        *optional_images,
        *optional_connect_lines,
    ]
    if len({id(element) for element in components}) != len(components):
        return None

    counts = Counter(_local_name(element.tag).lower() for element in components)
    expected = Counter({"text": 13, "line": 9, "rect": 2, "poke": 1})
    if optional_images:
        expected["image"] = 1
    if optional_connect_lines:
        expected["connectline"] = 4
    if counts != expected:
        return None
    return tuple(components)


def _detect_legacy_builtin_frame(
    layer: ET.Element,
    canvas_width: int,
    canvas_height: int,
) -> ExistingFrame | None:
    elements = list(layer)
    try:
        outer_lines, frame_box = identify_outer_frame_lines(
            elements,
            canvas_width,
            canvas_height,
        )
    except (FrameError, ValueError):
        return None

    if not _frame_is_canvas_outer(frame_box, canvas_width, canvas_height):
        return None
    components = _legacy_builtin_components(elements, outer_lines, frame_box)
    if components is None:
        return None
    return _make_existing_frame(
        outer_lines,
        frame_box,
        components,
        canvas_width,
        canvas_height,
        detection_mode="legacy_builtin_fingerprint",
    )


def detect_existing_frame(
    layer: ET.Element,
    canvas_width: int,
    canvas_height: int,
) -> ExistingFrame | None:
    """只返回可以安全自动调整的 G File Studio 内置图框。"""
    return (
        _detect_marked_builtin_frame(layer, canvas_width, canvas_height)
        or _detect_legacy_builtin_frame(layer, canvas_width, canvas_height)
    )




_FRAME_DECORATION_TAGS = {"line", "rect", "text", "poke", "image"}


def _box_inside(box: Box, outer: Box, tolerance: float = 0.0) -> bool:
    return (
        box.left >= outer.left - tolerance
        and box.top >= outer.top - tolerance
        and box.right <= outer.right + tolerance
        and box.bottom <= outer.bottom + tolerance
    )


def _box_near_outer_edge(box: Box, outer: Box, tolerance: float) -> bool:
    if not _box_inside(box, outer, tolerance=tolerance):
        return False
    return min(
        abs(box.left - outer.left),
        abs(box.top - outer.top),
        abs(outer.right - box.right),
        abs(outer.bottom - box.bottom),
    ) <= tolerance


def _unknown_outer_frame_components(
    layer: ET.Element,
    canvas_width: int,
    canvas_height: int,
) -> tuple[tuple[ET.Element, ...], str] | None:
    """Best-effort identification of an unmarked outer drawing frame.

    This path is intentionally used only by explicit frame *replacement* workflows.
    It never runs in ordinary margin adjustment.  Electrical tags are not candidates;
    only generic drawing-decoration tags near a canvas-scale outer frame are removed.
    """

    elements = list(layer)
    frame_box: Box | None = None
    seeds: list[ET.Element] = []
    mode = ""

    try:
        outer_lines, candidate_box = identify_outer_frame_lines(
            elements,
            canvas_width,
            canvas_height,
        )
    except (FrameError, ValueError):
        outer_lines = {}
        candidate_box = None
    if candidate_box is not None and _frame_is_canvas_outer(
        candidate_box,
        canvas_width,
        canvas_height,
    ):
        frame_box = candidate_box
        seeds.extend(outer_lines.values())
        mode = "unknown_outer_lines"

    if frame_box is None:
        rect_candidates: list[tuple[float, ET.Element, Box]] = []
        for element in elements:
            if _local_name(element.tag).lower() != "rect":
                continue
            box = subtree_box(element)
            if box is None or not _frame_is_canvas_outer(box, canvas_width, canvas_height):
                continue
            rect_candidates.append((box.width * box.height, element, box))
        if rect_candidates:
            _, outer_rect, frame_box = max(rect_candidates, key=lambda item: item[0])
            seeds.append(outer_rect)
            mode = "unknown_outer_rect"

    if frame_box is None:
        return None

    edge_tolerance = max(30.0, min(frame_box.width, frame_box.height) * 0.035)
    selected_ids = {id(element) for element in seeds}

    # First select peripheral generic rectangles that look like title/info blocks.
    peripheral_rects: list[tuple[ET.Element, Box]] = []
    for element in elements:
        if id(element) in selected_ids or _local_name(element.tag).lower() != "rect":
            continue
        box = subtree_box(element)
        if box is None or not _box_inside(box, frame_box, tolerance=edge_tolerance):
            continue
        if box.width >= frame_box.width * 0.9 and box.height >= frame_box.height * 0.9:
            continue
        aspect = max(box.width, box.height) / max(1.0, min(box.width, box.height))
        if aspect < 1.8:
            continue
        if _box_near_outer_edge(box, frame_box, edge_tolerance):
            peripheral_rects.append((element, box))
            selected_ids.add(id(element))

    # Pull in generic drawing furniture that belongs to those peripheral blocks or
    # sits immediately on the frame edge.  FeedLine/ConnectLine/BusDis/device tags
    # are deliberately excluded from this fallback to avoid deleting live topology.
    for element in elements:
        if id(element) in selected_ids:
            continue
        tag = _local_name(element.tag).lower()
        if tag not in _FRAME_DECORATION_TAGS:
            continue
        box = subtree_box(element)
        if box is None or not _box_inside(box, frame_box, tolerance=edge_tolerance):
            continue
        inside_peripheral_block = any(
            _center_inside(box, rect_box, tolerance=6.0)
            or boxes_intersect(box, rect_box, tolerance=4.0)
            for _, rect_box in peripheral_rects
        )
        if inside_peripheral_block:
            selected_ids.add(id(element))
        elif tag != "text" and _box_near_outer_edge(box, frame_box, edge_tolerance):
            selected_ids.add(id(element))

    selected = tuple(element for element in elements if id(element) in selected_ids)
    return (selected, mode) if selected else None


def remove_existing_frame_for_replacement(
    root: ET.Element,
    layer: ET.Element,
    canvas_width: int,
    canvas_height: int,
) -> FrameRemovalResult:
    """Remove any detected existing frame so the selected template can be authoritative.

    The caller has already made an explicit frame-template choice.  Therefore marked
    G File Studio frames, legacy built-in frames, and detectable unmarked canvas-scale
    frames are removed without prompting.  Ordinary margin adjustment remains
    conservative unless it explicitly opts into this helper.
    """

    removed_ids: set[int] = set()
    modes: list[str] = []

    # G File Studio writes these attributes onto every inserted component.  Include
    # component/role markers as recovery paths for partially edited files.
    marked = [
        element
        for element in list(layer)
        if element.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower()
        in {GFS_FRAME_TYPE_BUILTIN, GFS_FRAME_TYPE_CUSTOM}
        or element.get(GFS_FRAME_COMPONENT_ATTRIBUTE) not in (None, "")
        or element.get(GFS_FRAME_ROLE_ATTRIBUTE) not in (None, "")
    ]
    if marked:
        modes.append("gfs_marked")
        removed_ids.update(id(element) for element in marked)

    # If markers are absent (old versions), use the strict legacy built-in fingerprint.
    if not removed_ids:
        try:
            legacy = _detect_legacy_builtin_frame(layer, canvas_width, canvas_height)
        except (MarginAdjustmentError, FrameError, ValueError):
            legacy = None
        if legacy is not None:
            modes.append(legacy.detection_mode)
            removed_ids.update(id(element) for element in legacy.components)

    # Unknown/customer frames are allowed only on explicit replacement paths.  Use a
    # conservative decoration-only fallback around a canvas-scale outer border.
    remaining_layer = ET.Element("Layer")
    for element in list(layer):
        if id(element) not in removed_ids:
            remaining_layer.append(element)
    unknown = _unknown_outer_frame_components(
        remaining_layer,
        canvas_width,
        canvas_height,
    )
    if unknown is not None:
        components, mode = unknown
        if components:
            modes.append(mode)
            removed_ids.update(id(element) for element in components)

    if removed_ids:
        for element in list(layer):
            if id(element) in removed_ids:
                layer.remove(element)

    # Never leave stale frame identity on the root; the replacement stage will set it.
    root.attrib.pop(GFS_FRAME_TYPE_ATTRIBUTE, None)
    root.attrib.pop(GFS_FRAME_TEMPLATE_ATTRIBUTE, None)

    return FrameRemovalResult(
        removed_count=len(removed_ids),
        detection_modes=tuple(dict.fromkeys(modes)),
    )


def _has_canvas_outer_frame(
    root: ET.Element,
    layer: ET.Element,
    canvas_width: int,
    canvas_height: int,
) -> bool:
    """检测是否存在任意已有图框，用于阻止未知/客户图框自动处理。"""
    root_type = root.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower()
    if root_type == GFS_FRAME_TYPE_CUSTOM:
        return True
    if any(
        element.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower() == GFS_FRAME_TYPE_CUSTOM
        for element in list(layer)
    ):
        return True

    elements = list(layer)
    try:
        _, frame_box = identify_outer_frame_lines(elements, canvas_width, canvas_height)
    except (FrameError, ValueError):
        frame_box = None
    if frame_box is not None and _frame_is_canvas_outer(frame_box, canvas_width, canvas_height):
        return True

    # 兼容由单个大 rect 表示的客户图框。
    for element in elements:
        if _local_name(element.tag).lower() != "rect":
            continue
        box = subtree_box(element)
        if box is not None and _frame_is_canvas_outer(box, canvas_width, canvas_height):
            return True
    return False


def _set_canvas_size(root: ET.Element, width: int, height: int) -> None:
    for name in ("w", "width"):
        root.set(name, str(int(width)))
    for name in ("h", "height"):
        root.set(name, str(int(height)))


def _output_name(input_name: str, suffix: str) -> str:
    if not suffix:
        return input_name
    compound = ".sln.pic.g"
    lower = input_name.lower()
    if lower.endswith(compound):
        return input_name[: -len(compound)] + suffix + compound
    if lower.endswith(".g"):
        return input_name[:-2] + suffix + ".g"
    return input_name + suffix



def _pixel_envelope(box: Box) -> Box:
    """返回覆盖全部可见图形的整数像素边界。"""
    return Box(
        left=float(math.floor(box.left + 1e-9)),
        top=float(math.floor(box.top + 1e-9)),
        right=float(math.ceil(box.right - 1e-9)),
        bottom=float(math.ceil(box.bottom - 1e-9)),
    )


def _verify_exact_requested_margins(
    body_box: Box,
    canvas_width: int,
    canvas_height: int,
    requested: tuple[int, int, int, int],
    *,
    source_name: str,
) -> tuple[float, float, float, float]:
    """按整数像素外包边界严格验证四边距。"""
    pixel_box = _pixel_envelope(body_box)
    actual = (
        pixel_box.left,
        pixel_box.top,
        float(canvas_width) - pixel_box.right,
        float(canvas_height) - pixel_box.bottom,
    )
    labels = ("左", "上", "右", "下")
    for value, expected, label in zip(actual, requested, labels):
        if abs(value - float(expected)) > 1e-6:
            raise MarginAdjustmentError(
                f"{source_name} 的最终主体{label}边距验证失败："
                f"期望 {expected}，实际 {value:g}。"
            )
    return actual


def _reparse_and_verify_output(
    path: Path,
    *,
    requested: tuple[int, int, int, int],
    excluded_element_ids: frozenset[str] = frozenset(),
) -> tuple[float, float, float, float]:
    """重新解析临时输出，防止写出后坐标或画布尺寸发生偏差。"""
    tree = ET.parse(path)
    root = tree.getroot()
    layer = require_single_direct_layer(root, path.name)
    width, height = read_canvas_size(root, path.name)

    detected_frame = detect_existing_frame(layer, width, height)
    frame_components = (
        {id(element) for element in detected_frame.components}
        if detected_frame is not None
        else set()
    )
    body_elements = [
        element
        for element in list(layer)
        if id(element) not in frame_components
        and element.get("id", "") not in excluded_element_ids
    ]
    body_box = elements_box(body_elements)
    if body_box is None:
        raise MarginAdjustmentError(f"{path.name} 写出后无法重新识别主体图形。")
    return _verify_exact_requested_margins(
        body_box,
        width,
        height,
        requested,
        source_name=path.name,
    )

def adjust_one_file(
    input_path: Path,
    output_path: Path,
    *,
    left_margin: int = 500,
    top_margin: int = 500,
    right_margin: int = 500,
    bottom_margin: int = 500,
    preserve_existing_frame: bool = True,
    force_remove_existing_frame: bool = False,
) -> MarginAdjustmentResult:
    """调整主体图形边距。

    默认仍只对可确认的内置图框执行自动同步调整；显式 replacement 工作流
    可通过 force_remove_existing_frame=True 先删除旧图框，再仅按主体图形计算边距。
    """
    try:
        tree = ET.parse(input_path)
    except ET.ParseError as exc:
        raise MarginAdjustmentError(f"XML 解析失败：{input_path.name}：{exc}") from exc

    root = tree.getroot()
    if _local_name(root.tag) != "G":
        raise MarginAdjustmentError(f"{input_path.name} 的根节点不是 G。")

    layer = require_single_direct_layer(root, input_path.name)
    old_width, old_height = read_canvas_size(root, input_path.name)
    removal_result = FrameRemovalResult()
    if force_remove_existing_frame:
        removal_result = remove_existing_frame_for_replacement(
            root,
            layer,
            old_width,
            old_height,
        )

    direct_elements = list(layer)

    existing_frame = (
        detect_existing_frame(layer, old_width, old_height)
        if preserve_existing_frame and not force_remove_existing_frame
        else None
    )
    if (
        preserve_existing_frame
        and not force_remove_existing_frame
        and existing_frame is None
        and _has_canvas_outer_frame(
            root,
            layer,
            old_width,
            old_height,
        )
    ):
        raise UnsupportedExistingFrameError(
            "检测到已有图框，但该图框不是 G File Studio 内置图框，"
            "程序无法安全区分图框组件和主体图形。\n\n"
            "请先在图形编辑器中删除现有图框，再执行“图形边距调整”。"
        )

    frame_ids = {id(element) for element in existing_frame.components} if existing_frame else set()
    frame_xml_ids = (
        frozenset(
            element.get("id", "")
            for element in existing_frame.components
            if element.get("id", "")
        )
        if existing_frame is not None
        else frozenset()
    )
    body_elements = [element for element in direct_elements if id(element) not in frame_ids]
    body_before = elements_box(body_elements)
    if body_before is None:
        if existing_frame is not None:
            raise MarginAdjustmentError(
                f"{input_path.name} 已识别为内置图框，但图框之外没有找到主体图形。"
            )
        raise MarginAdjustmentError(
            f"{input_path.name} 中没有找到可用于边距调整的主体图形。"
        )

    body_before_pixels = _pixel_envelope(body_before)
    dx = float(left_margin) - body_before_pixels.left
    dy = float(top_margin) - body_before_pixels.top
    for element in body_elements:
        shift_element(element, dx, dy)

    body_after = elements_box(body_elements)
    if body_after is None:
        raise MarginAdjustmentError("主体图形平移后无法重新计算边界。")

    body_after_pixels = _pixel_envelope(body_after)
    new_width = int(body_after_pixels.right + float(right_margin))
    new_height = int(body_after_pixels.bottom + float(bottom_margin))
    if new_width <= 0 or new_height <= 0:
        raise MarginAdjustmentError(f"计算得到的画布尺寸无效：{new_width} × {new_height}")

    frame_margins: tuple[float, float, float, float] | None = None
    if existing_frame is not None:
        new_frame = Box(
            left=existing_frame.left_margin,
            top=existing_frame.top_margin,
            right=new_width - existing_frame.right_margin,
            bottom=new_height - existing_frame.bottom_margin,
        )
        if new_frame.width <= 0 or new_frame.height <= 0:
            raise MarginAdjustmentError(
                "调整后的画布太小，无法保留原有内置图框四边距。"
            )

        outer = existing_frame.outer_lines
        set_line_geometry(outer["top"], new_frame.left, new_frame.top, new_frame.right, new_frame.top)
        set_line_geometry(outer["right"], new_frame.right, new_frame.top, new_frame.right, new_frame.bottom)
        set_line_geometry(outer["bottom"], new_frame.right, new_frame.bottom, new_frame.left, new_frame.bottom)
        set_line_geometry(outer["left"], new_frame.left, new_frame.bottom, new_frame.left, new_frame.top)
        _shift_custom_template_components(
            existing_frame.components,
            outer,
            existing_frame.frame_box,
            new_frame,
        )
        frame_margins = (
            new_frame.left,
            new_frame.top,
            new_width - new_frame.right,
            new_height - new_frame.bottom,
        )

    _set_canvas_size(root, new_width, new_height)

    final_body = elements_box(body_elements)
    if final_body is None:
        raise MarginAdjustmentError("无法验证最终主体图形边界。")
    requested = (left_margin, top_margin, right_margin, bottom_margin)
    actual_margins = _verify_exact_requested_margins(
        final_body,
        new_width,
        new_height,
        requested,
        source_name=input_path.name,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    try:
        if hasattr(ET, "indent"):
            ET.indent(tree, space="    ")
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
        _reparse_and_verify_output(
            tmp_path,
            requested=requested,
            excluded_element_ids=frame_xml_ids,
        )
        os.replace(tmp_path, output_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return MarginAdjustmentResult(
        output_path=output_path,
        had_existing_frame=existing_frame is not None,
        old_canvas_width=old_width,
        old_canvas_height=old_height,
        new_canvas_width=new_width,
        new_canvas_height=new_height,
        body_left_margin=actual_margins[0],
        body_top_margin=actual_margins[1],
        body_right_margin=actual_margins[2],
        body_bottom_margin=actual_margins[3],
        frame_left_margin=frame_margins[0] if frame_margins else None,
        frame_top_margin=frame_margins[1] if frame_margins else None,
        frame_right_margin=frame_margins[2] if frame_margins else None,
        frame_bottom_margin=frame_margins[3] if frame_margins else None,
        frame_detection_mode=existing_frame.detection_mode if existing_frame else None,
        removed_existing_frame_count=removal_result.removed_count,
        removed_existing_frame_modes=removal_result.detection_modes,
    )


def make_output_path(output_dir: Path, input_path: Path, suffix: str) -> Path:
    return output_dir / _output_name(input_path.name, suffix)
