from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, Sequence

from g_file_studio.engines.frame_engine import (
    Box,
    FrameError,
    GFS_FRAME_COMPONENT_ATTRIBUTE,
    GFS_FRAME_TEMPLATE_ATTRIBUTE,
    GFS_FRAME_TYPE_ATTRIBUTE,
    GFS_FRAME_TYPE_BUILTIN,
    GFS_FRAME_TYPE_CUSTOM,
    identify_outer_frame_lines,
    line_endpoints,
    parse_d_points,
    parse_number,
)

FRAME_NONE = "none"
FRAME_BUILTIN = "builtin"
FRAME_UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class MergeFrameInspection:
    """合并输入文件的图框识别结果。"""

    kind: str
    components: tuple[ET.Element, ...] = ()
    detection_mode: str = "none"
    reason: str = ""

    @property
    def has_frame(self) -> bool:
        return self.kind != FRAME_NONE

    @property
    def is_builtin(self) -> bool:
        return self.kind == FRAME_BUILTIN

    @property
    def is_unsupported(self) -> bool:
        return self.kind == FRAME_UNSUPPORTED


class MergeFrameInspectionError(RuntimeError):
    """图框结构已损坏，无法安全用于合并。"""


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _combine_boxes(boxes: Iterable[Box]) -> Box | None:
    values = list(boxes)
    if not values:
        return None
    return Box(
        min(item.left for item in values),
        min(item.top for item in values),
        max(item.right for item in values),
        max(item.bottom for item in values),
    )


def _node_box(node: ET.Element) -> Box | None:
    xs: list[float] = []
    ys: list[float] = []
    numeric: dict[str, float] = {}

    for name in (
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "mergex",
        "mergey",
        "w",
        "h",
        "width",
        "height",
        "rx",
        "ry",
    ):
        raw = node.get(name)
        if raw in (None, ""):
            continue
        try:
            numeric[name] = parse_number(raw)
        except ValueError:
            return None

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


def _subtree_box(element: ET.Element) -> Box | None:
    return _combine_boxes(
        box for node in element.iter() if (box := _node_box(node)) is not None
    )


def _center_inside(inner: Box, outer: Box, tolerance: float = 0.0) -> bool:
    return (
        outer.left - tolerance <= inner.center_x <= outer.right + tolerance
        and outer.top - tolerance <= inner.center_y <= outer.bottom + tolerance
    )


def _frame_is_canvas_outer(frame: Box, width: float, height: float) -> bool:
    if width <= 0 or height <= 0:
        return False
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


def _large_outer_rect(
    elements: Sequence[ET.Element],
    canvas_width: float,
    canvas_height: float,
) -> ET.Element | None:
    candidates: list[tuple[float, ET.Element]] = []
    for element in elements:
        if _local_name(element.tag).lower() not in {"rect", "rectangle"}:
            continue
        box = _subtree_box(element)
        if box is None or not _frame_is_canvas_outer(box, canvas_width, canvas_height):
            continue
        candidates.append((box.width * box.height, element))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _marked_builtin_components(
    root: ET.Element,
    layer: ET.Element,
    canvas_width: float,
    canvas_height: float,
) -> tuple[ET.Element, ...] | None:
    root_type = root.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower()
    elements = list(layer)
    marked = [
        element
        for element in elements
        if element.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower()
        == GFS_FRAME_TYPE_BUILTIN
        or (
            root_type == GFS_FRAME_TYPE_BUILTIN
            and bool(element.get(GFS_FRAME_COMPONENT_ATTRIBUTE, "").strip())
        )
    ]
    if root_type != GFS_FRAME_TYPE_BUILTIN and not marked:
        return None
    if not marked:
        raise MergeFrameInspectionError(
            "文件声明为 G File Studio 内置图框，但没有找到带标记的图框组件。"
        )
    try:
        _, frame_box = identify_outer_frame_lines(marked, canvas_width, canvas_height)
    except (FrameError, ValueError) as exc:
        raise MergeFrameInspectionError(
            "文件带有 G File Studio 内置图框标记，但四条外框线已损坏或不完整。"
        ) from exc
    if not _frame_is_canvas_outer(frame_box, canvas_width, canvas_height):
        raise MergeFrameInspectionError(
            "文件带有 G File Studio 内置图框标记，但图框不在画布外围。"
        )
    return tuple(marked)


def _legacy_builtin_components_by_geometry(
    elements: Sequence[ET.Element],
    outer_lines: dict[str, ET.Element],
    frame_box: Box,
) -> tuple[ET.Element, ...] | None:
    """只使用几何结构识别旧版内置图框，不检查任何文字内容。

    稳定结构指纹：
      * 四条画布外框线；
      * 左上 300×60 左右的标题矩形及同尺寸 poke；
      * 右下 350×97 左右的信息矩形；
      * 信息矩形内部 2 条水平线和 3 条垂直线。

    Text 的 ts、Draw、Approve、Issue、标题、姓名和日期都不参与识别。
    """
    outer_ids = {id(item) for item in outer_lines.values()}

    rects: list[tuple[ET.Element, Box]] = []
    for element in elements:
        if _local_name(element.tag).lower() not in {"rect", "rectangle"}:
            continue
        box = _subtree_box(element)
        if box is not None:
            rects.append((element, box))

    title_rects = [
        (element, box)
        for element, box in rects
        if abs(box.left - (frame_box.left + 10.0)) <= 14.0
        and abs(box.top - (frame_box.top + 10.0)) <= 14.0
        and 280.0 <= box.width <= 320.0
        and 50.0 <= box.height <= 70.0
    ]
    info_rects = [
        (element, box)
        for element, box in rects
        if abs(frame_box.right - box.right) <= 14.0
        and abs(frame_box.bottom - box.bottom) <= 14.0
        and 330.0 <= box.width <= 370.0
        and 85.0 <= box.height <= 110.0
    ]
    if len(title_rects) != 1 or len(info_rects) != 1:
        return None

    title_rect, title_box = title_rects[0]
    info_rect, info_box = info_rects[0]

    title_pokes: list[ET.Element] = []
    info_lines: list[ET.Element] = []
    horizontal_lines = 0
    vertical_lines = 0

    for element in elements:
        if id(element) in outer_ids or element in {title_rect, info_rect}:
            continue
        tag = _local_name(element.tag).lower()
        box = _subtree_box(element)
        if box is None:
            continue

        if tag == "poke":
            if (
                abs(box.center_x - title_box.center_x) <= 8.0
                and abs(box.center_y - title_box.center_y) <= 8.0
                and abs(box.width - title_box.width) <= 12.0
                and abs(box.height - title_box.height) <= 12.0
            ):
                title_pokes.append(element)
            continue

        if tag != "line":
            continue
        endpoints = line_endpoints(element)
        if endpoints is None:
            continue
        x1, y1, x2, y2 = endpoints
        tolerance = 6.0
        if not all(
            info_box.left - tolerance <= x <= info_box.right + tolerance
            and info_box.top - tolerance <= y <= info_box.bottom + tolerance
            for x, y in ((x1, y1), (x2, y2))
        ):
            continue
        span_x = abs(x2 - x1)
        span_y = abs(y2 - y1)
        if span_y <= 1.0 and span_x >= info_box.width * 0.80:
            horizontal_lines += 1
            info_lines.append(element)
        elif span_x <= 1.0 and span_y >= info_box.height * 0.80:
            vertical_lines += 1
            info_lines.append(element)

    if len(title_pokes) != 1:
        return None
    if len(info_lines) != 5 or horizontal_lines != 2 or vertical_lines != 3:
        return None

    selected_ids = {
        id(item)
        for item in (
            *outer_lines.values(),
            title_rect,
            title_pokes[0],
            info_rect,
            *info_lines,
        )
    }
    components: list[ET.Element] = [
        *outer_lines.values(),
        title_rect,
        title_pokes[0],
        info_rect,
        *info_lines,
    ]

    # 收集标题块和签字栏内部的全部组件，但不读取任何文字值。
    for element in elements:
        if id(element) in selected_ids:
            continue
        box = _subtree_box(element)
        if box is None:
            continue
        if _center_inside(box, title_box, tolerance=4.0) or _center_inside(
            box, info_box, tolerance=5.0
        ):
            components.append(element)
            selected_ids.add(id(element))

    # 内置模板左上角可选 Logo，只按尺寸与位置识别。
    logo_candidates: list[ET.Element] = []
    for element in elements:
        if id(element) in selected_ids:
            continue
        if _local_name(element.tag).lower() != "image":
            continue
        box = _subtree_box(element)
        if box is None:
            continue
        if (
            frame_box.left + 250.0 <= box.left <= frame_box.left + 420.0
            and abs(box.top - (frame_box.top + 10.0)) <= 18.0
            and 150.0 <= box.width <= 260.0
            and 45.0 <= box.height <= 80.0
        ):
            logo_candidates.append(element)
    if len(logo_candidates) > 1:
        return None
    components.extend(logo_candidates)
    selected_ids.update(id(item) for item in logo_candidates)

    # 兼容旧模板中 4 个重合的微小 ConnectLine 辅助点。
    helper_candidates: list[ET.Element] = []
    for element in elements:
        if id(element) in selected_ids:
            continue
        if _local_name(element.tag).lower() != "connectline":
            continue
        box = _subtree_box(element)
        if box is None:
            continue
        if (
            box.width <= 12.0
            and box.height <= 12.0
            and abs(box.center_x - (frame_box.left + 383.0)) <= 24.0
            and abs(box.center_y - (frame_box.top + 483.0)) <= 24.0
        ):
            helper_candidates.append(element)
    if len(helper_candidates) == 4:
        components.extend(helper_candidates)
    elif helper_candidates:
        return None

    return tuple(components)


def inspect_merge_frame(
    root: ET.Element,
    layer: ET.Element,
    canvas_width: float,
    canvas_height: float,
) -> MergeFrameInspection:
    """识别合并输入中的图框。

    * G File Studio 内置图框：返回全部图框组件，合并前可安全移除；
    * 客户/未知图框：返回 unsupported，禁止参与合并；
    * 无图框：返回 none。
    """
    elements = list(layer)
    root_type = root.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower()
    element_types = {
        element.get(GFS_FRAME_TYPE_ATTRIBUTE, "").strip().lower()
        for element in elements
        if element.get(GFS_FRAME_TYPE_ATTRIBUTE)
    }

    if root_type == GFS_FRAME_TYPE_CUSTOM or GFS_FRAME_TYPE_CUSTOM in element_types:
        return MergeFrameInspection(
            kind=FRAME_UNSUPPORTED,
            detection_mode="custom_marker",
            reason="检测到客户自定义图框标记。",
        )

    marked = _marked_builtin_components(
        root, layer, canvas_width, canvas_height
    )
    if marked is not None:
        return MergeFrameInspection(
            kind=FRAME_BUILTIN,
            components=marked,
            detection_mode="builtin_marker",
            reason="检测到 G File Studio 内置图框标记。",
        )

    try:
        outer_lines, frame_box = identify_outer_frame_lines(
            elements, canvas_width, canvas_height
        )
    except (FrameError, ValueError):
        outer_lines = None
        frame_box = None

    if frame_box is not None and _frame_is_canvas_outer(
        frame_box, canvas_width, canvas_height
    ):
        legacy_components = _legacy_builtin_components_by_geometry(
            elements, outer_lines or {}, frame_box
        )
        if legacy_components is not None:
            return MergeFrameInspection(
                kind=FRAME_BUILTIN,
                components=legacy_components,
                detection_mode="legacy_builtin_geometry",
                reason="通过内置模板几何结构识别到旧版内置图框。",
            )
        return MergeFrameInspection(
            kind=FRAME_UNSUPPORTED,
            detection_mode="unknown_outer_lines",
            reason="检测到画布外框，但其几何结构不是 G File Studio 内置图框。",
        )

    if _large_outer_rect(elements, canvas_width, canvas_height) is not None:
        return MergeFrameInspection(
            kind=FRAME_UNSUPPORTED,
            detection_mode="unknown_outer_rect",
            reason="检测到覆盖画布的大矩形图框，但不是 G File Studio 内置图框。",
        )

    return MergeFrameInspection(kind=FRAME_NONE)


__all__ = [
    "FRAME_NONE",
    "FRAME_BUILTIN",
    "FRAME_UNSUPPORTED",
    "MergeFrameInspection",
    "MergeFrameInspectionError",
    "inspect_merge_frame",
]
