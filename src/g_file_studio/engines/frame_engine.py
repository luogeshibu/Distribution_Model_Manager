#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给已经合并完成的 .g（XML）文件添加 SLD 图框。

目录结构（均相对于本脚本所在目录）：

    add_g_drawing_frame.py
    drawing_frame_config.json
    template_g_files/
        SLD-Drawing-Frame-Template.sln.pic.g
    input_g_files/
        JED-CTL-ADF.sln.pic.g
    output_g_files/
        JED-CTL-ADF.sln.pic.g

处理内容：
1. 读取 template_g_files 中的固定图框模板。
2. 遍历 input_g_files 中所有以 .g 结尾的文件。
3. 根据目标 G.w/width 和 G.h/height 调整最外层矩形图框，四边距默认 50。
4. 左上角标题默认取目标文件名中 .sln.pic.g 前面的部分。
5. Draw / Approve / Issue 的姓名和日期从 JSON 配置读取。
6. 右下角标题栏保持模板原有尺寸与布局，移动到目标画布右下角。
7. 为模板图元重新分配唯一 ID，避免与目标文件冲突。
8. 把模板 Layer 下的图元追加到目标文件唯一 Layer 中。
9. 输出到 output_g_files，文件名与输入文件保持一致。

只使用 Python 标准库，无需安装第三方包。
"""

from __future__ import annotations

import copy
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple

from g_file_studio.engines.id_engine import (
    generate_unique_id as generate_pattern_unique_id,
    infer_element_id_patterns as infer_direct_id_patterns,
    local_name as id_local_name,
)


# =============================================================================
# 用户可修改配置
# =============================================================================

# 固定目录名：都位于本脚本所在目录下。
TEMPLATE_FOLDER_NAME = "template_g_files"
INPUT_FOLDER_NAME = "input_g_files"
OUTPUT_FOLDER_NAME = "output_g_files"

# 推荐的模板文件名。
TEMPLATE_FILE_NAME = "SLD-Drawing-Frame-Template.sln.pic.g"

# 人员和日期配置文件。
CONFIG_FILE_NAME = "drawing_frame_config.json"

# 最外层矩形图框距离 G 画布四边的距离。
FRAME_MARGIN_LEFT = 50
FRAME_MARGIN_TOP = 50
FRAME_MARGIN_RIGHT = 50
FRAME_MARGIN_BOTTOM = 50

# 模板文件本身的原始外框位置。目标边距可由 App 修改，但模板识别仍按原始 50 处理。
TEMPLATE_FRAME_MARGIN_LEFT = 50
TEMPLATE_FRAME_MARGIN_TOP = 50
TEMPLATE_FRAME_MARGIN_RIGHT = 50
TEMPLATE_FRAME_MARGIN_BOTTOM = 50

# 输出文件名保持与输入文件一致。
# 需要添加后缀时，可改为 "-WITH-FRAME"。
OUTPUT_NAME_SUFFIX = ""

# 只处理以 .g 结尾的文件，大小写不敏感。
INPUT_EXTENSION = ".g"

# 是否覆盖 output_g_files 中已经存在的同名文件。
OVERWRITE_OUTPUT = True

# 文本自动缩小时允许的最小字号。
MIN_TEXT_FONT_SIZE = 10

# 已知包含图元 ID 引用的属性。
REFERENCE_ATTRIBUTES = ("link", "node_area", "p_FatherObjId")

# 位置属性。平移图框组件时只修改这些属性。
X_POSITION_ATTRIBUTES = ("x", "x1", "x2", "cx", "mergex")
Y_POSITION_ATTRIBUTES = ("y", "y1", "y2", "cy", "mergey")

# d 属性中坐标点格式，例如：50,50 1870,50
D_POINT_PATTERN = re.compile(
    r"(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*"
    r"(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
)

# 引用属性中的纯数字 token。
ID_TOKEN_PATTERN = re.compile(r"(?<!\d)(\d+)(?!\d)")

# G File Studio 写入的图框身份标记。
# 使用普通 XML 属性，目标编辑器会忽略未知属性；程序则可以可靠地区分
# 内置图框与客户自定义图框，避免仅凭几何关系误判。
GFS_FRAME_TYPE_ATTRIBUTE = "gfs_frame_type"
GFS_FRAME_TEMPLATE_ATTRIBUTE = "gfs_frame_template"
GFS_FRAME_COMPONENT_ATTRIBUTE = "gfs_frame_component"
GFS_FRAME_ROLE_ATTRIBUTE = "gfs_frame_role"
GFS_FRAME_TYPE_BUILTIN = "builtin"
GFS_FRAME_TYPE_CUSTOM = "custom"
DEFAULT_BUILTIN_TEMPLATE_ID = "default_sld_frame"


class FrameError(RuntimeError):
    """图框处理错误。"""


@dataclass(frozen=True)
class Box:
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


@dataclass(frozen=True)
class PersonRow:
    name: str
    date: str


@dataclass(frozen=True)
class FileFrameConfig:
    title: str
    draw: PersonRow
    approve: PersonRow
    issue: PersonRow


# =============================================================================
# 基础数值与 XML 工具
# =============================================================================


def parse_number(value: Optional[str], *, default: Optional[float] = None) -> float:
    if value is None or str(value).strip() == "":
        if default is None:
            raise ValueError("缺少数值")
        return default
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"无效数值：{value!r}") from exc


def format_number(value: float) -> str:
    """尽可能输出整数，避免 50.0。"""
    if not math.isfinite(value):
        raise ValueError(f"非有限数值：{value}")
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", "-0.0"} else text


def require_single_direct_layer(root: ET.Element, source_name: str) -> ET.Element:
    layers = [child for child in list(root) if child.tag == "Layer"]
    if len(layers) != 1:
        raise FrameError(
            f"{source_name} 的 G 根节点必须且只能有一个直属 Layer，实际为 {len(layers)} 个。"
        )
    return layers[0]


def read_canvas_size(root: ET.Element, source_name: str) -> Tuple[int, int]:
    width_values: List[float] = []
    height_values: List[float] = []

    for attr in ("w", "width"):
        if root.get(attr) not in (None, ""):
            width_values.append(parse_number(root.get(attr)))
    for attr in ("h", "height"):
        if root.get(attr) not in (None, ""):
            height_values.append(parse_number(root.get(attr)))

    if not width_values or not height_values:
        raise FrameError(f"{source_name} 的 G 根节点缺少 w/width 或 h/height。")

    width = int(round(max(width_values)))
    height = int(round(max(height_values)))
    if width <= 0 or height <= 0:
        raise FrameError(f"{source_name} 的画布尺寸无效：{width} × {height}")
    return width, height


def parse_d_points(d_value: str) -> List[Tuple[float, float]]:
    return [
        (parse_number(match.group("x")), parse_number(match.group("y")))
        for match in D_POINT_PATTERN.finditer(d_value or "")
    ]


def shift_d_value(d_value: str, dx: float, dy: float) -> str:
    if not d_value:
        return d_value

    def replace(match: re.Match[str]) -> str:
        x = parse_number(match.group("x")) + dx
        y = parse_number(match.group("y")) + dy
        return f"{format_number(x)},{format_number(y)}"

    return D_POINT_PATTERN.sub(replace, d_value)


def shift_element(element: ET.Element, dx: float, dy: float) -> None:
    """平移元素及其全部子元素的位置坐标。"""
    for node in element.iter():
        for attr in X_POSITION_ATTRIBUTES:
            value = node.get(attr)
            if value not in (None, ""):
                node.set(attr, format_number(parse_number(value) + dx))

        for attr in Y_POSITION_ATTRIBUTES:
            value = node.get(attr)
            if value not in (None, ""):
                node.set(attr, format_number(parse_number(value) + dy))

        if node.get("d") not in (None, ""):
            node.set("d", shift_d_value(node.get("d", ""), dx, dy))


def element_box(element: ET.Element) -> Optional[Box]:
    """根据 x/y/w/h、端点和 d 坐标估算元素边界。"""
    xs: List[float] = []
    ys: List[float] = []

    x = element.get("x")
    y = element.get("y")
    w = element.get("w") or element.get("width")
    h = element.get("h") or element.get("height")

    if x not in (None, ""):
        xv = parse_number(x)
        xs.append(xv)
        if w not in (None, ""):
            xs.append(xv + parse_number(w))
    if y not in (None, ""):
        yv = parse_number(y)
        ys.append(yv)
        if h not in (None, ""):
            ys.append(yv + parse_number(h))

    for attr in ("x1", "x2", "cx", "mergex"):
        if element.get(attr) not in (None, ""):
            xs.append(parse_number(element.get(attr)))
    for attr in ("y1", "y2", "cy", "mergey"):
        if element.get(attr) not in (None, ""):
            ys.append(parse_number(element.get(attr)))

    for px, py in parse_d_points(element.get("d", "")):
        xs.append(px)
        ys.append(py)

    if not xs or not ys:
        return None
    return Box(min(xs), min(ys), max(xs), max(ys))


def boxes_intersect(a: Box, b: Box, tolerance: float = 0.0) -> bool:
    return not (
        a.right < b.left - tolerance
        or a.left > b.right + tolerance
        or a.bottom < b.top - tolerance
        or a.top > b.bottom + tolerance
    )


def line_endpoints(element: ET.Element) -> Optional[Tuple[float, float, float, float]]:
    if element.get("x1") not in (None, "") and element.get("y1") not in (None, ""):
        if element.get("x2") not in (None, "") and element.get("y2") not in (None, ""):
            return (
                parse_number(element.get("x1")),
                parse_number(element.get("y1")),
                parse_number(element.get("x2")),
                parse_number(element.get("y2")),
            )

    points = parse_d_points(element.get("d", ""))
    if len(points) >= 2:
        return (*points[0], *points[-1])
    return None


def set_line_geometry(
    element: ET.Element,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> None:
    """同步修改 line 的 x/y/w/h、端点和 d。"""
    element.set("x1", format_number(x1))
    element.set("y1", format_number(y1))
    element.set("x2", format_number(x2))
    element.set("y2", format_number(y2))
    element.set("d", f"{format_number(x1)},{format_number(y1)} {format_number(x2)},{format_number(y2)}")

    horizontal = abs(y1 - y2) <= 1e-9
    vertical = abs(x1 - x2) <= 1e-9

    # 模板 line 的选择框在主方向长度上会额外增加约 6。
    line_box_padding = 6.0
    if horizontal:
        element.set("x", format_number(min(x1, x2)))
        element.set("y", format_number(y1))
        element.set("w", format_number(abs(x2 - x1) + line_box_padding))
        element.set("h", format_number(line_box_padding))
    elif vertical:
        element.set("x", format_number(x1))
        element.set("y", format_number(min(y1, y2)))
        element.set("w", format_number(line_box_padding))
        element.set("h", format_number(abs(y2 - y1) + line_box_padding))
    else:
        element.set("x", format_number(min(x1, x2)))
        element.set("y", format_number(min(y1, y2)))
        element.set("w", format_number(abs(x2 - x1) + line_box_padding))
        element.set("h", format_number(abs(y2 - y1) + line_box_padding))


# =============================================================================
# 配置文件
# =============================================================================


def derive_title_from_filename(filename: str) -> str:
    lower = filename.lower()
    suffix = ".sln.pic.g"
    if lower.endswith(suffix):
        return filename[: -len(suffix)]
    if lower.endswith(".g"):
        return filename[:-2]
    return Path(filename).stem


def load_json_config(config_path: Path) -> Mapping[str, object]:
    if not config_path.exists():
        raise FrameError(
            f"找不到配置文件：{config_path}\n"
            "请把 drawing_frame_config.json 放在脚本同级目录。"
        )
    try:
        with config_path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise FrameError(f"配置文件 JSON 格式错误：{exc}") from exc

    if not isinstance(data, dict):
        raise FrameError("配置文件根节点必须是 JSON 对象。")
    return data


def deep_merge_dict(base: Mapping[str, object], override: Mapping[str, object]) -> Dict[str, object]:
    result: Dict[str, object] = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge_dict(
                result[key],  # type: ignore[arg-type]
                value,
            )
        else:
            result[key] = copy.deepcopy(value)
    return result


def require_text(value: object, field_name: str, *, allow_empty: bool = True) -> str:
    if value is None:
        return "" if allow_empty else _raise_field(field_name)
    if not isinstance(value, (str, int, float)):
        raise FrameError(f"配置项 {field_name} 必须是字符串或数字。")
    text = str(value).strip()
    if not text and not allow_empty:
        _raise_field(field_name)
    return text


def _raise_field(field_name: str) -> str:
    raise FrameError(f"配置项 {field_name} 不能为空。")


def parse_person_row(config: Mapping[str, object], key: str) -> PersonRow:
    value = config.get(key, {})
    if not isinstance(value, dict):
        raise FrameError(f"配置项 {key} 必须是对象，包含 name 和 date。")
    return PersonRow(
        name=require_text(value.get("name", ""), f"{key}.name"),
        date=require_text(value.get("date", ""), f"{key}.date"),
    )


def resolve_file_config(
    all_config: Mapping[str, object],
    input_filename: str,
) -> FileFrameConfig:
    default = all_config.get("default", {})
    files = all_config.get("files", {})

    if not isinstance(default, dict):
        raise FrameError("配置项 default 必须是对象。")
    if not isinstance(files, dict):
        raise FrameError("配置项 files 必须是对象。")

    title_key = derive_title_from_filename(input_filename)
    override: Mapping[str, object] = {}

    exact_value = files.get(input_filename)
    title_value = files.get(title_key)
    if exact_value is not None:
        if not isinstance(exact_value, dict):
            raise FrameError(f"files.{input_filename} 必须是对象。")
        override = exact_value
    elif title_value is not None:
        if not isinstance(title_value, dict):
            raise FrameError(f"files.{title_key} 必须是对象。")
        override = title_value

    merged = deep_merge_dict(default, override)
    configured_title = require_text(merged.get("title", ""), "title")
    final_title = configured_title or title_key

    return FileFrameConfig(
        title=final_title,
        draw=parse_person_row(merged, "draw"),
        approve=parse_person_row(merged, "approve"),
        issue=parse_person_row(merged, "issue"),
    )


# =============================================================================
# 模板识别与图框调整
# =============================================================================


def identify_outer_frame_lines(
    elements: Sequence[ET.Element],
    template_width: int,
    template_height: int,
) -> Tuple[Dict[str, ET.Element], Box]:
    """自动识别模板中构成最大外框的四条轴对齐 line。

    不依赖固定的 50 像素模板边距，因此内置模板升级或客户模板采用其他
    原始边距时仍可识别。外框线应当是模板中跨度最大的水平/垂直线之一。
    """
    horizontals: List[Tuple[ET.Element, float, float, float, float]] = []
    verticals: List[Tuple[ET.Element, float, float, float, float]] = []

    for element in elements:
        if element.tag.lower() != "line":
            continue
        points = line_endpoints(element)
        if points is None:
            continue
        x1, y1, x2, y2 = points
        if abs(y1 - y2) <= 1e-6 and abs(x2 - x1) > 1e-6:
            left, right = sorted((x1, x2))
            horizontals.append((element, left, right, (y1 + y2) / 2.0, right - left))
        elif abs(x1 - x2) <= 1e-6 and abs(y2 - y1) > 1e-6:
            top, bottom = sorted((y1, y2))
            verticals.append((element, (x1 + x2) / 2.0, top, bottom, bottom - top))

    if len(horizontals) < 2 or len(verticals) < 2:
        raise FrameError("模板中无法识别完整的四条矩形外框线。")

    max_h_span = max(item[4] for item in horizontals)
    max_v_span = max(item[4] for item in verticals)
    min_h_span = max(20.0, max_h_span * 0.70, template_width * 0.30)
    min_v_span = max(20.0, max_v_span * 0.70, template_height * 0.30)

    long_h = [item for item in horizontals if item[4] >= min_h_span]
    long_v = [item for item in verticals if item[4] >= min_v_span]
    if len(long_h) < 2 or len(long_v) < 2:
        raise FrameError("模板中的外框线跨度不足，无法识别完整矩形外框。")

    top_item = min(long_h, key=lambda item: (item[3], -item[4]))
    bottom_item = max(long_h, key=lambda item: (item[3], item[4]))
    left_item = min(long_v, key=lambda item: (item[1], -item[4]))
    right_item = max(long_v, key=lambda item: (item[1], item[4]))

    found = {
        "top": top_item[0],
        "right": right_item[0],
        "bottom": bottom_item[0],
        "left": left_item[0],
    }
    if len({id(value) for value in found.values()}) != 4:
        raise FrameError("模板最外层四条边框线识别结果发生重复。")

    frame = Box(
        left=left_item[1],
        top=top_item[3],
        right=right_item[1],
        bottom=bottom_item[3],
    )
    if frame.width <= 0 or frame.height <= 0:
        raise FrameError("模板外框尺寸无效。")

    tolerance = max(12.0, min(template_width, template_height) * 0.02)
    corner_checks = (
        abs(top_item[1] - frame.left),
        abs(top_item[2] - frame.right),
        abs(bottom_item[1] - frame.left),
        abs(bottom_item[2] - frame.right),
        abs(left_item[2] - frame.top),
        abs(left_item[3] - frame.bottom),
        abs(right_item[2] - frame.top),
        abs(right_item[3] - frame.bottom),
    )
    if max(corner_checks) > tolerance:
        raise FrameError(
            "模板中识别到的四条长线不能组成闭合矩形外框，请检查客户模板。"
        )
    return found, frame


def _shift_custom_template_components(
    elements: Sequence[ET.Element],
    outer_lines: Mapping[str, ET.Element],
    old_frame: Box,
    new_frame: Box,
) -> None:
    """按最近的水平/垂直边锚定客户模板组件并整体平移。

    只改变组件坐标，不修改文字、属性内容、字体、颜色、线宽或组件尺寸。
    左上组件跟随左/上边，右下签字栏跟随右/下边。
    """
    outer_ids = {id(element) for element in outer_lines.values()}
    for element in elements:
        if id(element) in outer_ids:
            continue
        box = element_box(element)
        if box is None:
            continue

        left_gap = abs(box.left - old_frame.left)
        right_gap = abs(old_frame.right - box.right)
        top_gap = abs(box.top - old_frame.top)
        bottom_gap = abs(old_frame.bottom - box.bottom)

        dx = (new_frame.left - old_frame.left) if left_gap <= right_gap else (
            new_frame.right - old_frame.right
        )
        dy = (new_frame.top - old_frame.top) if top_gap <= bottom_gap else (
            new_frame.bottom - old_frame.bottom
        )
        shift_element(element, dx, dy)

def identify_rectangles(elements: Sequence[ET.Element]) -> Tuple[ET.Element, ET.Element]:
    rects = [element for element in elements if element.tag.lower() == "rect"]
    if len(rects) < 2:
        raise FrameError("模板中至少需要两个 rect：左上标题框和右下信息框。")

    boxed: List[Tuple[ET.Element, Box]] = []
    for rect in rects:
        box = element_box(rect)
        if box is not None:
            boxed.append((rect, box))

    if len(boxed) < 2:
        raise FrameError("模板 rect 缺少有效坐标。")

    title_rect = min(boxed, key=lambda item: item[1].left + item[1].top)[0]
    info_rect = max(boxed, key=lambda item: item[1].right + item[1].bottom)[0]
    if title_rect is info_rect:
        raise FrameError("无法区分左上标题框和右下信息框。")
    return title_rect, info_rect


def identify_title_text(elements: Sequence[ET.Element], title_rect: ET.Element) -> ET.Element:
    rect_box = element_box(title_rect)
    if rect_box is None:
        raise FrameError("左上标题框坐标无效。")

    candidates: List[ET.Element] = []
    for element in elements:
        if element.tag != "Text":
            continue
        box = element_box(element)
        if box is not None and boxes_intersect(box, rect_box, tolerance=2.0):
            candidates.append(element)

    if not candidates:
        raise FrameError("模板左上标题框中找不到 Text 元素。")
    # 标题字体通常最大。
    return max(candidates, key=lambda e: parse_number(e.get("fs"), default=0))


def identify_info_block_elements(
    elements: Sequence[ET.Element],
    info_rect: ET.Element,
    *,
    excluded_elements: Sequence[ET.Element] = (),
) -> List[ET.Element]:
    """识别右下签字栏组件，并明确排除四条外框线。"""
    info_box = element_box(info_rect)
    if info_box is None:
        raise FrameError("右下信息框坐标无效。")

    excluded_ids = {id(item) for item in excluded_elements}
    result: List[ET.Element] = []
    for element in elements:
        if id(element) in excluded_ids:
            continue
        box = element_box(element)
        if box is None:
            continue
        if boxes_intersect(box, info_box, tolerance=4.0):
            result.append(element)

    if info_rect not in result:
        result.append(info_rect)
    return result


def set_builtin_component_roles(
    outer_lines: Mapping[str, ET.Element],
    title_group: Sequence[ET.Element],
    info_group: Sequence[ET.Element],
) -> None:
    """给输出内置图框写入明确组件角色，便于后续可靠识别。"""
    roles = {
        "top": "outer_top",
        "right": "outer_right",
        "bottom": "outer_bottom",
        "left": "outer_left",
    }
    outer_ids = {id(item) for item in outer_lines.values()}
    for side, element in outer_lines.items():
        element.set(GFS_FRAME_ROLE_ATTRIBUTE, roles[side])
    for element in title_group:
        if id(element) not in outer_ids:
            element.set(GFS_FRAME_ROLE_ATTRIBUTE, "title_block")
    for element in info_group:
        if id(element) not in outer_ids:
            element.set(GFS_FRAME_ROLE_ATTRIBUTE, "info_block")


def validate_outer_frame_geometry(
    outer_lines: Mapping[str, ET.Element],
    frame: Box,
    canvas_width: float,
    canvas_height: float,
    *,
    tolerance: float = 0.001,
) -> None:
    """输出前强制确认四条外框线闭合且没有超出画布。"""
    expected = {
        "top": (frame.left, frame.top, frame.right, frame.top),
        "right": (frame.right, frame.top, frame.right, frame.bottom),
        "bottom": (frame.right, frame.bottom, frame.left, frame.bottom),
        "left": (frame.left, frame.bottom, frame.left, frame.top),
    }
    for side, expected_points in expected.items():
        actual = line_endpoints(outer_lines[side])
        if actual is None:
            raise FrameError(f"内置图框适配失败：{side} 边框缺少有效端点。")
        if any(abs(a - b) > tolerance for a, b in zip(actual, expected_points)):
            raise FrameError(
                f"内置图框适配失败：{side} 边框未形成闭合矩形。"
                f"期望 {expected_points}，实际 {actual}。"
            )
        for x, y in ((actual[0], actual[1]), (actual[2], actual[3])):
            if (
                x < -tolerance
                or y < -tolerance
                or x > canvas_width + tolerance
                or y > canvas_height + tolerance
            ):
                raise FrameError(
                    f"内置图框适配失败：{side} 边框端点 ({x}, {y}) "
                    f"超出画布 {canvas_width}×{canvas_height}。"
                )


def fit_text_in_cell(
    text_element: ET.Element,
    text: str,
    cell: Box,
    *,
    horizontal_padding: float = 4.0,
    min_font_size: int = MIN_TEXT_FONT_SIZE,
) -> None:
    """更新 Text.ts，并在不改变单元格的情况下居中与必要缩小。"""
    text_element.set("ts", text)

    original_font = int(round(parse_number(text_element.get("fs"), default=20)))
    available_width = max(1.0, cell.width - horizontal_padding * 2)
    available_height = max(1.0, cell.height - 2.0)

    def estimated_width(font_size: int) -> float:
        # 对英文字母、数字、横线和下划线使用保守估算。
        return max(1, len(text)) * font_size * 0.56

    font_size = original_font
    while font_size > min_font_size and (
        estimated_width(font_size) > available_width or font_size * 1.1 > available_height
    ):
        font_size -= 1

    text_width = min(available_width, estimated_width(font_size))
    text_height = min(available_height, max(1.0, font_size * 1.1))
    x = cell.center_x - text_width / 2.0
    y = cell.center_y - text_height / 2.0

    text_element.set("fs", format_number(font_size))
    if "p_FontHeight" in text_element.attrib:
        text_element.set("p_FontHeight", format_number(font_size))
    if "p_FontWidth" in text_element.attrib:
        text_element.set("p_FontWidth", format_number(font_size))
    text_element.set("w", format_number(text_width))
    text_element.set("h", format_number(text_height))
    text_element.set("x", format_number(x))
    text_element.set("y", format_number(y))


def cluster_text_rows(text_elements: Sequence[ET.Element]) -> List[List[ET.Element]]:
    sorted_texts = sorted(
        text_elements,
        key=lambda e: (parse_number(e.get("y"), default=0), parse_number(e.get("x"), default=0)),
    )
    rows: List[List[ET.Element]] = []
    tolerance = 5.0

    for element in sorted_texts:
        y = parse_number(element.get("y"), default=0)
        if not rows:
            rows.append([element])
            continue
        previous_y = sum(parse_number(item.get("y"), default=0) for item in rows[-1]) / len(rows[-1])
        if abs(y - previous_y) <= tolerance:
            rows[-1].append(element)
        else:
            rows.append([element])

    for row in rows:
        row.sort(key=lambda e: parse_number(e.get("x"), default=0))
    return rows


def update_info_block_texts(
    info_elements: Sequence[ET.Element],
    info_rect: ET.Element,
    config: FileFrameConfig,
) -> None:
    info_box = element_box(info_rect)
    if info_box is None:
        raise FrameError("右下信息框坐标无效。")

    texts = [element for element in info_elements if element.tag == "Text"]
    rows = [row for row in cluster_text_rows(texts) if len(row) >= 4]
    if len(rows) != 3:
        raise FrameError(
            f"右下信息框应识别出 3 行、每行至少 4 个 Text，实际识别到 {len(rows)} 行。"
        )

    rows.sort(key=lambda row: parse_number(row[0].get("y"), default=0))
    values = (config.draw, config.approve, config.issue)

    # 通过竖向分隔线确定列边界；若识别失败，则使用每行文本当前位置估算。
    vertical_xs: List[float] = []
    for element in info_elements:
        if element.tag.lower() != "line":
            continue
        endpoints = line_endpoints(element)
        if endpoints is None:
            continue
        x1, y1, x2, y2 = endpoints
        if abs(x1 - x2) <= 1e-9 and abs(y2 - y1) > 5:
            if info_box.left - 3 <= x1 <= info_box.right + 3:
                vertical_xs.append(x1)

    boundaries = sorted({round(x, 6) for x in vertical_xs} | {round(info_box.left, 6), round(info_box.right, 6)})
    if len(boundaries) < 5:
        # 模板正常情况下有左边、3 个内部分隔线、右边，共 5 条边界。
        # 使用首行文本中心点的中点作为降级列边界。
        first = rows[0][:4]
        centers = [element_box(item).center_x for item in first if element_box(item) is not None]
        if len(centers) != 4:
            raise FrameError("无法识别右下信息框的列边界。")
        boundaries = [info_box.left]
        for left_center, right_center in zip(centers, centers[1:]):
            boundaries.append((left_center + right_center) / 2.0)
        boundaries.append(info_box.right)

    # 只取最左、最右及中间三个主要边界。
    if len(boundaries) > 5:
        # 选择最接近模板四列布局的 5 条边界：两端 + 中间按顺序取三条。
        middle = boundaries[1:-1]
        if len(middle) >= 3:
            step = (len(middle) - 1) / 2.0
            selected = [middle[0], middle[round(step)], middle[-1]]
            boundaries = [boundaries[0], *sorted(set(selected)), boundaries[-1]]
    if len(boundaries) != 5:
        raise FrameError(f"右下信息框列边界数量异常：{boundaries}")

    for row_elements, row_value in zip(rows, values):
        four = row_elements[:4]
        # 第 1、3 格标签 Draw/Approve/Issue 和 Date 保持模板不变。
        name_cell = Box(boundaries[1], info_box.top, boundaries[2], info_box.bottom)
        date_cell = Box(boundaries[3], info_box.top, boundaries[4], info_box.bottom)

        # 使用当前行文字中心确定该行的垂直范围。
        row_centers = [element_box(item).center_y for item in four if element_box(item) is not None]
        row_center = sum(row_centers) / len(row_centers)
        row_height = info_box.height / 3.0
        row_top = row_center - row_height / 2.0
        row_bottom = row_center + row_height / 2.0

        fit_text_in_cell(
            four[1],
            row_value.name,
            Box(name_cell.left, row_top, name_cell.right, row_bottom),
        )
        fit_text_in_cell(
            four[3],
            row_value.date,
            Box(date_cell.left, row_top, date_cell.right, row_bottom),
        )


def prepare_template_elements(
    template_root: ET.Element,
    target_width: int,
    target_height: int,
    config: FileFrameConfig,
    *,
    edit_content: bool = True,
) -> List[ET.Element]:
    template_width, template_height = read_canvas_size(template_root, "图框模板")
    template_layer = require_single_direct_layer(template_root, "图框模板")
    elements = [copy.deepcopy(element) for element in list(template_layer)]

    # 必须在修改任何坐标前固定识别组件身份。旧实现先移动右边框，再按
    # 几何相交识别签字栏；当目标右边框恰好落在签字栏左边界时，右边框
    # 会被当作签字栏再次移动，造成右侧边框错位。
    outer_lines, old_frame = identify_outer_frame_lines(
        elements, template_width, template_height
    )

    target_left = float(FRAME_MARGIN_LEFT)
    target_top = float(FRAME_MARGIN_TOP)
    target_right = float(target_width - FRAME_MARGIN_RIGHT)
    target_bottom = float(target_height - FRAME_MARGIN_BOTTOM)
    new_frame = Box(target_left, target_top, target_right, target_bottom)

    if new_frame.width <= 0 or new_frame.height <= 0:
        raise FrameError(
            f"目标画布 {target_width}×{target_height} 太小，无法放置当前配置的图框边距。"
        )

    if not edit_content:
        # 客户模板只调整几何：先移动非外框组件，最后单独重设四条边。
        _shift_custom_template_components(elements, outer_lines, old_frame, new_frame)
        set_line_geometry(outer_lines["top"], target_left, target_top, target_right, target_top)
        set_line_geometry(outer_lines["right"], target_right, target_top, target_right, target_bottom)
        set_line_geometry(outer_lines["bottom"], target_right, target_bottom, target_left, target_bottom)
        set_line_geometry(outer_lines["left"], target_left, target_bottom, target_left, target_top)
        validate_outer_frame_geometry(
            outer_lines, new_frame, target_width, target_height
        )
        return elements

    # 内置模板：在原始模板坐标中识别标题区和签字栏，并明确排除外框线。
    title_rect, info_rect = identify_rectangles(elements)
    title_text = identify_title_text(elements, title_rect)
    outer_values = list(outer_lines.values())
    outer_ids = {id(value) for value in outer_values}
    info_elements = identify_info_block_elements(
        elements,
        info_rect,
        excluded_elements=outer_values,
    )

    title_rect_box = element_box(title_rect)
    if title_rect_box is None:
        raise FrameError("模板左上标题框坐标无效。")
    title_group = [
        element
        for element in elements
        if id(element) not in outer_ids
        and (box := element_box(element)) is not None
        and boxes_intersect(box, title_rect_box, tolerance=4.0)
    ]
    set_builtin_component_roles(outer_lines, title_group, info_elements)

    desired_title_left = target_left + (title_rect_box.left - old_frame.left)
    desired_title_top = target_top + (title_rect_box.top - old_frame.top)
    title_dx = desired_title_left - title_rect_box.left
    title_dy = desired_title_top - title_rect_box.top
    for element in title_group:
        shift_element(element, title_dx, title_dy)

    shifted_title_box = element_box(title_rect)
    if shifted_title_box is None:
        raise FrameError("移动后的标题框坐标无效。")
    fit_text_in_cell(
        title_text,
        config.title,
        shifted_title_box,
        horizontal_padding=12.0,
    )

    info_box = element_box(info_rect)
    if info_box is None:
        raise FrameError("模板右下信息框坐标无效。")
    gap_right = old_frame.right - info_box.right
    gap_bottom = old_frame.bottom - info_box.bottom
    desired_info_right = target_right - gap_right
    desired_info_bottom = target_bottom - gap_bottom
    info_dx = desired_info_right - info_box.right
    info_dy = desired_info_bottom - info_box.bottom
    for element in info_elements:
        shift_element(element, info_dx, info_dy)
    update_info_block_texts(info_elements, info_rect, config)

    # 最后单独设置外框。外框永远不会进入标题或签字栏组件集合。
    set_line_geometry(outer_lines["top"], target_left, target_top, target_right, target_top)
    set_line_geometry(outer_lines["right"], target_right, target_top, target_right, target_bottom)
    set_line_geometry(outer_lines["bottom"], target_right, target_bottom, target_left, target_bottom)
    set_line_geometry(outer_lines["left"], target_left, target_bottom, target_left, target_top)
    validate_outer_frame_geometry(
        outer_lines, new_frame, target_width, target_height
    )
    return elements


# =============================================================================
# ID 去重和引用更新
# =============================================================================


def collect_used_ids_and_tokens(layer: ET.Element) -> Set[str]:
    used: Set[str] = set()
    for element in layer.iter():
        element_id = element.get("id")
        if element_id:
            used.add(element_id)
        for attr in REFERENCE_ATTRIBUTES:
            value = element.get(attr, "")
            used.update(ID_TOKEN_PATTERN.findall(value))
    return used


def allocate_template_ids(
    elements: Sequence[ET.Element],
    used_ids: Set[str],
    target_layer: ET.Element | None = None,
) -> Dict[str, str]:
    """为模板元素分配唯一 ID。

    新生成 ID 必须优先使用“ID 检查与修复”中的全局已确认模板；
    同类型按当前最大合法完整 ID + 1 分配。只有确实没有模板的类型才
    保留旧版推断逻辑，且随后会由业务层提示用户补充模板。
    """
    from g_file_studio.services.id_rule_service import IdRuleService

    target_patterns = (
        infer_direct_id_patterns(list(target_layer))
        if target_layer is not None
        else {}
    )
    template_patterns = infer_direct_id_patterns(elements)
    rules = IdRuleService().load_rules()
    mapping: Dict[str, str] = {}
    seeds: Dict[str, str | None] = {}

    if target_layer is not None:
        for node in target_layer.iter():
            tag = id_local_name(node.tag)
            rule = rules.get(tag)
            value = (node.get("id") or "").strip()
            if rule is not None and rule.enabled and rule.verified and rule.matches(value):
                current = seeds.get(tag)
                if current is None or int(value) > int(current):
                    seeds[tag] = value

    for element in elements:
        for node in element.iter():
            old_id = (node.get("id") or "").strip()
            if not old_id or old_id in mapping:
                continue
            tag = id_local_name(node.tag)
            rule = rules.get(tag)
            if rule is not None and rule.enabled and rule.verified:
                candidate = rule.build_after(seeds.get(tag))
                while candidate in used_ids:
                    candidate = rule.build_after(candidate)
                seeds[tag] = candidate
                new_id = candidate
            else:
                pattern = target_patterns.get(tag) or template_patterns.get(tag)
                new_id = generate_pattern_unique_id(old_id, used_ids, pattern)
            mapping[old_id] = new_id
            used_ids.add(new_id)
    return mapping


def remap_reference_value(value: str, mapping: Mapping[str, str]) -> str:
    if not value:
        return value

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        return mapping.get(token, token)

    return ID_TOKEN_PATTERN.sub(replace, value)


def apply_id_mapping(elements: Sequence[ET.Element], mapping: Mapping[str, str]) -> None:
    for element in elements:
        for node in element.iter():
            old_id = node.get("id")
            if old_id in mapping:
                node.set("id", mapping[old_id])
            for attr in REFERENCE_ATTRIBUTES:
                if node.get(attr) not in (None, ""):
                    node.set(attr, remap_reference_value(node.get(attr, ""), mapping))


def validate_unique_element_ids(layer: ET.Element, source_name: str) -> None:
    seen: Set[str] = set()
    duplicates: Set[str] = set()
    for element in layer.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        if element_id in seen:
            duplicates.add(element_id)
        seen.add(element_id)
    if duplicates:
        values = ", ".join(sorted(duplicates)[:20])
        raise FrameError(f"{source_name} 图框添加后仍存在重复 ID：{values}")


# =============================================================================
# 单文件和批量处理
# =============================================================================


def make_output_filename(input_name: str) -> str:
    if not OUTPUT_NAME_SUFFIX:
        return input_name

    lower = input_name.lower()
    compound_suffix = ".sln.pic.g"
    if lower.endswith(compound_suffix):
        return input_name[: -len(compound_suffix)] + OUTPUT_NAME_SUFFIX + compound_suffix
    if lower.endswith(".g"):
        return input_name[:-2] + OUTPUT_NAME_SUFFIX + ".g"
    return input_name + OUTPUT_NAME_SUFFIX


def process_one_file(
    input_path: Path,
    output_path: Path,
    template_tree: ET.ElementTree,
    all_config: Mapping[str, object],
    *,
    edit_content: bool = True,
) -> None:
    try:
        target_tree = ET.parse(input_path)
    except ET.ParseError as exc:
        raise FrameError(f"目标文件 XML 解析失败：{input_path.name}：{exc}") from exc

    target_root = target_tree.getroot()
    if target_root.tag != "G":
        raise FrameError(f"{input_path.name} 的根节点不是 G。")

    target_layer = require_single_direct_layer(target_root, input_path.name)
    width, height = read_canvas_size(target_root, input_path.name)
    file_config = resolve_file_config(all_config, input_path.name)

    # v2.18.147: “图框添加”本身就是用户对目标模板的明确选择。
    # 因此不再叠加/保留旧图框，也不再因为旧图框来源不同而阻断；
    # 先强制移除可检测到的已有图框，再以当前选择模板作为唯一权威图框。
    # 使用函数内导入避免 margin_engine -> frame_engine 的模块级循环依赖。
    from g_file_studio.engines.margin_engine import remove_existing_frame_for_replacement

    replacement = remove_existing_frame_for_replacement(
        target_root,
        target_layer,
        width,
        height,
    )
    if replacement.removed_count:
        modes = ", ".join(replacement.detection_modes) or "detected"
        print(
            f"  已强制移除已有图框：{replacement.removed_count} 个组件（{modes}）；"
            "将使用当前选择模板重新添加。"
        )

    template_elements = prepare_template_elements(
        template_tree.getroot(),
        target_width=width,
        target_height=height,
        config=file_config,
        edit_content=edit_content,
    )

    used_ids = collect_used_ids_and_tokens(target_layer)
    id_mapping = allocate_template_ids(template_elements, used_ids, target_layer)
    apply_id_mapping(template_elements, id_mapping)

    frame_type = GFS_FRAME_TYPE_BUILTIN if edit_content else GFS_FRAME_TYPE_CUSTOM
    target_root.set(GFS_FRAME_TYPE_ATTRIBUTE, frame_type)
    target_root.set(
        GFS_FRAME_TEMPLATE_ATTRIBUTE,
        DEFAULT_BUILTIN_TEMPLATE_ID if edit_content else "custom",
    )
    for ordinal, element in enumerate(template_elements):
        element.set(GFS_FRAME_TYPE_ATTRIBUTE, frame_type)
        element.set(GFS_FRAME_COMPONENT_ATTRIBUTE, str(ordinal))
        target_layer.append(element)

    validate_unique_element_ids(target_layer, input_path.name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not OVERWRITE_OUTPUT:
        raise FrameError(f"输出文件已存在且不允许覆盖：{output_path}")

    try:
        ET.indent(target_tree, space="    ")
    except AttributeError:
        pass
    target_tree.write(output_path, encoding="utf-8", xml_declaration=True)

    # 写出后重新解析一次，确保 XML 完整。
    try:
        ET.parse(output_path)
    except ET.ParseError as exc:
        raise FrameError(f"输出文件写出后校验失败：{output_path.name}：{exc}") from exc

    print(f"处理完成：{input_path.name}")
    if edit_content:
        print(f"  模式：内置模板（已更新标题与签字栏）")
        print(f"  标题：{file_config.title}")
        print(f"  Draw：{file_config.draw.name} / {file_config.draw.date}")
        print(f"  Approve：{file_config.approve.name} / {file_config.approve.date}")
        print(f"  Issue：{file_config.issue.name} / {file_config.issue.date}")
    else:
        print("  模式：客户自定义模板（仅调整图框几何，不修改任何内容）")
    print(f"  画布：{width} × {height}")
    print(f"  输出：{output_path}")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    template_dir = script_dir / TEMPLATE_FOLDER_NAME
    input_dir = script_dir / INPUT_FOLDER_NAME
    output_dir = script_dir / OUTPUT_FOLDER_NAME
    config_path = script_dir / CONFIG_FILE_NAME
    template_path = template_dir / TEMPLATE_FILE_NAME

    print("SLD 图框添加工具")
    print(f"脚本目录：{script_dir}")
    print(f"模板文件：{template_path}")
    print(f"输入目录：{input_dir}")
    print(f"输出目录：{output_dir}")
    print(f"配置文件：{config_path}")
    print(
        "图框边距："
        f"左={FRAME_MARGIN_LEFT}，上={FRAME_MARGIN_TOP}，"
        f"右={FRAME_MARGIN_RIGHT}，下={FRAME_MARGIN_BOTTOM}"
    )

    if not template_path.is_file():
        raise FrameError(
            f"找不到图框模板：{template_path}\n"
            f"请把模板重命名为 {TEMPLATE_FILE_NAME} 并放入 {TEMPLATE_FOLDER_NAME}。"
        )
    if not input_dir.is_dir():
        raise FrameError(f"找不到输入目录：{input_dir}")

    all_config = load_json_config(config_path)

    try:
        template_tree = ET.parse(template_path)
    except ET.ParseError as exc:
        raise FrameError(f"模板 XML 解析失败：{exc}") from exc

    if template_tree.getroot().tag != "G":
        raise FrameError("图框模板的根节点不是 G。")

    input_files = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() == INPUT_EXTENSION
    )
    if not input_files:
        raise FrameError(f"{input_dir} 中没有找到以 {INPUT_EXTENSION} 结尾的文件。")

    output_dir.mkdir(parents=True, exist_ok=True)
    success_count = 0
    errors: List[str] = []

    for input_path in input_files:
        output_path = output_dir / make_output_filename(input_path.name)
        try:
            process_one_file(
                input_path=input_path,
                output_path=output_path,
                template_tree=template_tree,
                all_config=all_config,
            )
            success_count += 1
        except Exception as exc:  # 单个文件失败时继续处理其他文件。
            message = f"{input_path.name}：{exc}"
            errors.append(message)
            print(f"处理失败：{message}", file=sys.stderr)

    print("\n处理汇总：")
    print(f"  成功：{success_count}")
    print(f"  失败：{len(errors)}")
    if errors:
        for message in errors:
            print(f"  - {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FrameError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
