#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
合并多个 XML 格式的 .sln.pic.g 文件。

当前规则：
1. 文件名前面的内容可以任意命名，但后缀必须是 .sln.pic.g。
2. App 可由用户自由定义文件顺序；未指定时才按名称自然排序。
3. 每个文件必须只有一个直属 Layer；内置图框会在内存副本中移除后参与合并，非内置图框禁止参与。
4. 合并前删除负坐标图元并清理相关真实引用，再统一取整位置坐标。
5. 用户顺序中的第一个文件完整作为基准，后续文件只复制 Layer 子图元。
6. 只识别标签名严格等于 <Bus> 的有效非零长度水平母线（不把 <BusDis> 当作 Bus）；有 Bus 时使用最顶部 Bus 对齐，没有 Bus 时使用最高图元 Y 对齐。
7. 相邻输入图按真实坐标边界严格保持指定水平间隔。
8. 处理重复 ID、虚拟拓扑 ID，并同步更新 link、node_area、p_FatherObjId。
9. 最终统一处理四周边距、根节点尺寸和 XML 合法性校验。
"""

from __future__ import annotations

import argparse
import copy
from collections import Counter
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Callable, Iterable, Iterator

from g_file_studio.engines.frame_engine import (
    GFS_FRAME_COMPONENT_ATTRIBUTE,
    GFS_FRAME_TEMPLATE_ATTRIBUTE,
    GFS_FRAME_TYPE_ATTRIBUTE,
)
from g_file_studio.engines.merge_frame_inspector import (
    FRAME_BUILTIN,
    FRAME_NONE,
    FRAME_UNSUPPORTED,
    MergeFrameInspectionError,
    inspect_merge_frame,
)


# ============================================================================
# 用户可修改配置
# 只需要修改下面这些值，然后直接运行脚本即可。
# 所有数值必须是大于或等于 0 的整数。
# ============================================================================

# 相邻两个馈线图形实际边界之间的水平间隔。
# 例如可修改为：300、400、500。
FEEDER_GAP = 300

# 每个馈线图的最小占用宽度；不包含 FEEDER_GAP。
FEEDER_MIN_WIDTH = 1000

# 最终合并图形与画布四个边框之间的实际边距。
LEFT_MARGIN = 300
TOP_MARGIN = 300
RIGHT_MARGIN = 300
BOTTOM_MARGIN = 300

# 输入、输出目录名称。目录都位于本脚本所在目录下。
INPUT_FOLDER_NAME = "input_g_files"
OUTPUT_FOLDER_NAME = "output_g_files"

# 只处理以 .sln.pic.g 结尾的文件。
INPUT_FILE_PATTERN = "*.sln.pic.g"

# ============================================================================
# 以下为程序逻辑，一般不需要修改。
# ============================================================================


# 匹配 d 属性中的坐标点，例如：903,625、-12.5,30.25。
POINT_PATTERN = re.compile(
    r"(?P<x>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?P<comma>\s*,\s*)"
    r"(?P<y>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
)

# 需要做水平平移的位置属性。
HORIZONTAL_POSITION_ATTRS = ("x", "x1", "x2", "cx", "mergex")

# 需要做垂直平移的位置属性。
VERTICAL_POSITION_ATTRS = ("y", "y1", "y2", "cy", "mergey")

# 明确包含图元 ID 引用的属性。
REFERENCE_LIST_ATTRS = ("link", "node_area")
REFERENCE_SINGLE_ATTRS = ("p_FatherObjId",)


@dataclass(frozen=True)
class GFileInfo:
    path: Path
    order: int
    display_name: str


@dataclass
class NegativeCoordinateCleanupResult:
    # 因自身坐标含负数而直接删除的根图元数量。
    removed_root_elements: int = 0
    # 连同被删除根图元的后代，一共移除的 XML 图元数量。
    removed_total_elements: int = 0
    # 被移除的非空图元 ID 数量。
    removed_element_ids: int = 0
    # 从 link/node_area 中删除的失效引用分组数量。
    removed_reference_groups: int = 0
    # 被清空的 p_FatherObjId 数量。
    cleared_single_references: int = 0


@dataclass
class ParsedGFile:
    info: GFileInfo
    tree: ET.ElementTree
    root: ET.Element
    layer: ET.Element
    root_height: Decimal
    root_width: Decimal
    alignment_y: Decimal
    alignment_mode: str
    min_x: Decimal
    min_y: Decimal
    max_x: Decimal
    max_y: Decimal
    negative_cleanup: NegativeCoordinateCleanupResult
    rounded_coordinate_attributes: int
    frame_kind: str = FRAME_NONE
    frame_detection_mode: str = "none"
    removed_builtin_frame_elements: int = 0
    removed_builtin_frame_ids: int = 0
    removed_builtin_frame_references: int = 0


@dataclass(frozen=True)
class MergeCandidateInspection:
    info: GFileInfo
    eligible: bool
    status: str
    frame_kind: str
    frame_detection_mode: str = "none"
    alignment_mode: str = ""
    alignment_y: Decimal | None = None
    error: str = ""


class UnsupportedMergeFrameError(ValueError):
    """检测到客户或来源不明图框，禁止参与合并。"""


@dataclass
class IdUpdateResult:
    # 真正写在元素 id="..." 上且被修改的数量。
    changed_element_ids: int = 0
    # link/node_area/p_FatherObjId 中发生映射的不同 ID token 数量。
    changed_reference_tokens: int = 0
    # 单个源文件 Layer 自身重复的元素 ID 数量。
    source_internal_duplicates: int = 0
    # 源文件中只出现在引用里、没有同名 XML 图元的拓扑节点 ID 数量。
    virtual_reference_tokens: int = 0


@dataclass(frozen=True)
class ElementIdPattern:
    """从当前单个 G 文件的同类元素中推断出的 ID 格式。"""

    tag: str
    prefix: str
    total_length: int

    @property
    def sequence_width(self) -> int:
        return self.total_length - len(self.prefix)

    @property
    def max_sequence(self) -> int:
        return 10 ** self.sequence_width - 1

    def matches(self, value: str) -> bool:
        return (
            value.isdigit()
            and len(value) == self.total_length
            and value.startswith(self.prefix)
        )

    def build(self, sequence: int) -> str:
        if sequence < 0 or sequence > self.max_sequence:
            raise ValueError(
                f"<{self.tag}> 的 {self.total_length} 位 ID 空间已用尽："
                f"前缀 {self.prefix!r}，最大顺序号 {self.max_sequence}。"
            )
        return f"{self.prefix}{sequence:0{self.sequence_width}d}"


def confirmed_id_patterns() -> dict[str, ElementIdPattern]:
    """读取全局已确认 ID 模板；新生成 ID 一律以此为最高优先级。"""
    from g_file_studio.services.id_rule_service import IdRuleService

    patterns: dict[str, ElementIdPattern] = {}
    for rule in IdRuleService().load_rules().values():
        if rule.enabled and rule.verified:
            patterns[rule.tag] = ElementIdPattern(rule.tag, rule.prefix, rule.total_length)
    return patterns


def apply_confirmed_id_patterns(patterns: dict[str, ElementIdPattern]) -> dict[str, ElementIdPattern]:
    merged = dict(patterns)
    merged.update(confirmed_id_patterns())
    return merged


def local_name(tag: object) -> str:
    """去掉 XML 命名空间，只保留标签名。"""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def parse_decimal(value: str, context: str) -> Decimal:
    """将 XML 数字安全转换为 Decimal。"""
    try:
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{context} 不是有效数字：{value!r}") from exc


def try_decimal(value: str | None) -> Decimal | None:
    """尝试转换数字，失败时返回 None。"""
    if value is None:
        return None
    try:
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None


def format_decimal(value: Decimal) -> str:
    """避免输出科学计数法和无意义的 .0。"""
    if value == value.to_integral_value():
        return str(value.to_integral_value())

    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def round_to_integer(value: Decimal) -> Decimal:
    """
    使用统一规则取整：四舍五入，遇到 .5 时向远离 0 的方向取整。

    示例：
        10.4  -> 10
        10.5  -> 11
        -10.4 -> -10
        -10.5 -> -11
    """
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def format_integer(value: Decimal) -> str:
    """按统一规则取整并输出不带小数点的字符串。"""
    return str(round_to_integer(value))


def _natural_sort_key(text: str) -> tuple[object, ...]:
    """按文件名自然排序，使 file2 排在 file10 前面。"""
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", text)
    )


def _display_name_from_path(path: Path) -> str:
    suffix = ".sln.pic.g"
    if path.name.lower().endswith(suffix):
        return path.name[: -len(suffix)]
    return path.stem


def parse_filename(path: Path, order: int = 1) -> GFileInfo:
    """仅校验固定后缀，不解析站点、馈线号或其他命名内容。"""
    if not path.name.lower().endswith(".sln.pic.g"):
        raise ValueError(
            f"不支持的输入文件名：{path.name}\n"
            "参与合并的文件必须以 .sln.pic.g 结尾；文件名前面的内容可以任意命名。"
        )
    return GFileInfo(
        path=path,
        order=order,
        display_name=_display_name_from_path(path),
    )


def discover_files(
    input_dir: Path,
    pattern: str = "*.sln.pic.g",
    ordered_file_names: Iterable[str] | None = None,
    *,
    allow_subset: bool = False,
) -> list[GFileInfo]:
    """发现输入文件，并按用户顺序或默认自然排序返回。

    ``ordered_file_names`` 只接收文件名，不接收目录，且每个文件只能出现一次。
    默认要求完整包含输入目录中的全部 ``.sln.pic.g`` 文件；当
    ``allow_subset=True`` 时，允许只选择目录中的一部分文件参与合并。
    """
    if not input_dir.is_dir():
        raise NotADirectoryError(f"输入目录不存在：{input_dir}")

    all_files = [path for path in input_dir.iterdir() if path.is_file()]
    invalid_g_files = [
        path
        for path in all_files
        if path.suffix.lower() == ".g" and not path.name.lower().endswith(".sln.pic.g")
    ]
    if invalid_g_files:
        details = "\n".join(
            f"  - {path.name}"
            for path in sorted(invalid_g_files, key=lambda item: _natural_sort_key(item.name))
        )
        raise ValueError(
            "输入目录中存在后缀不是 .sln.pic.g 的 G 文件。请移出或重命名后再合并：\n"
            f"{details}"
        )

    natural_candidates = sorted(
        (path for path in all_files if path.name.lower().endswith(".sln.pic.g")),
        key=lambda path: _natural_sort_key(path.name),
    )
    if not natural_candidates:
        raise FileNotFoundError(
            f"目录中未找到以 .sln.pic.g 结尾的文件：{input_dir}"
        )

    if ordered_file_names is None:
        candidates = natural_candidates
    else:
        requested = [str(name).strip() for name in ordered_file_names]
        if not requested:
            candidates = natural_candidates
        else:
            for name in requested:
                if not name or Path(name).name != name:
                    raise ValueError(
                        f"合并顺序中包含无效文件名：{name!r}。顺序项只能填写文件名。"
                    )
                if not name.lower().endswith(".sln.pic.g"):
                    raise ValueError(
                        f"合并顺序中的文件必须以 .sln.pic.g 结尾：{name}"
                    )

            normalized = [name.casefold() for name in requested]
            duplicate_names = sorted(
                {name for name in normalized if normalized.count(name) > 1}
            )
            if duplicate_names:
                raise ValueError(
                    "合并顺序中存在重复文件："
                    + ", ".join(duplicate_names)
                )

            candidate_map = {path.name.casefold(): path for path in natural_candidates}
            requested_set = set(normalized)
            missing = [name for name in requested if name.casefold() not in candidate_map]
            omitted = [
                path.name
                for path in natural_candidates
                if path.name.casefold() not in requested_set
            ]
            if missing or (omitted and not allow_subset):
                messages: list[str] = []
                if missing:
                    messages.append(
                        "顺序列表中找不到这些文件：\n"
                        + "\n".join(f"  - {name}" for name in missing)
                    )
                if omitted and not allow_subset:
                    messages.append(
                        "顺序列表遗漏了这些输入文件：\n"
                        + "\n".join(f"  - {name}" for name in omitted)
                    )
                raise ValueError("\n\n".join(messages))

            candidates = [candidate_map[name.casefold()] for name in requested]

    return [parse_filename(path, order=index) for index, path in enumerate(candidates, 1)]


def create_xml_parser() -> ET.XMLParser:
    """保留 XML 注释。"""
    return ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))


def parse_xml(path: Path) -> ET.ElementTree:
    try:
        return ET.parse(path, parser=create_xml_parser())
    except ET.ParseError as exc:
        raise ValueError(f"XML 解析失败：{path}\n{exc}") from exc


def get_only_layer(root: ET.Element, filename: str) -> ET.Element:
    """每个文件必须且只能有一个直属 Layer。"""
    layers = [child for child in list(root) if local_name(child.tag) == "Layer"]
    if len(layers) != 1:
        raise ValueError(
            f"文件 {filename} 应当只有一个直属 Layer，实际找到 {len(layers)} 个"
        )
    return layers[0]


def get_root_dimension(
    root: ET.Element,
    short_name: str,
    long_name: str,
    filename: str,
) -> Decimal:
    """
    h/height 或 w/width 表示同一尺寸。
    若二者同时存在但不同，取较大值，避免缩小画布。
    """
    values: list[Decimal] = []
    for name in (short_name, long_name):
        raw = root.get(name)
        if raw is not None:
            values.append(parse_decimal(raw, f"文件 {filename} 的 G.{name}"))

    if not values:
        raise ValueError(
            f"文件 {filename} 的 G 根节点缺少 {short_name}/{long_name} 属性"
        )
    return max(values)


def iter_graph_elements(children_or_layer: Iterable[ET.Element] | ET.Element) -> Iterator[ET.Element]:
    """遍历 Layer 下的全部图元及其后代，不返回 Layer 本身。"""
    if isinstance(children_or_layer, ET.Element):
        roots = list(children_or_layer)
    else:
        roots = list(children_or_layer)

    for root in roots:
        yield root
        yield from root.iterfind(".//*")


def parse_d_points(d_value: str) -> list[tuple[Decimal, Decimal]]:
    """读取 d 属性中所有 x,y 点。"""
    points: list[tuple[Decimal, Decimal]] = []
    for match in POINT_PATTERN.finditer(d_value):
        points.append(
            (
                parse_decimal(match.group("x"), "d 属性中的 x"),
                parse_decimal(match.group("y"), "d 属性中的 y"),
            )
        )
    return points

def element_has_negative_coordinate(element: ET.Element, filename: str) -> bool:
    """
    判断一个图元自身是否包含负数坐标。

    只检查明确表示“位置”的属性和 d 路径坐标，不检查：
      w/h、width/height、rx/ry、rotate、tfr、颜色和状态值。
    因此 tfr="rotate(-0.0)" 不会被误判。
    """
    tag = local_name(element.tag)
    for attr in (*HORIZONTAL_POSITION_ATTRS, *VERTICAL_POSITION_ATTRS):
        raw = element.get(attr)
        if raw is None:
            continue
        value = try_decimal(raw)
        if value is None:
            raise ValueError(
                f"文件 {filename} 中 <{tag}> 的 {attr} 不是有效数字：{raw!r}"
            )
        if value < 0:
            return True

    d_value = element.get("d")
    if d_value:
        for point_x, point_y in parse_d_points(d_value):
            if point_x < 0 or point_y < 0:
                return True

    return False


def collect_subtree_nonempty_ids(element: ET.Element) -> set[str]:
    """收集某个待删除元素及其全部后代的非空 id。"""
    result: set[str] = set()
    for current in element.iter():
        value = current.get("id")
        if value is not None and value.strip():
            result.add(value.strip())
    return result


def count_subtree_graph_elements(element: ET.Element) -> int:
    """统计某个元素子树中的真实 XML 元素数量，不计注释。"""
    return sum(1 for current in element.iter() if local_name(current.tag))


def remove_reference_groups_to_ids(value: str, removed_ids: set[str]) -> tuple[str, int]:
    """从 link/node_area 中删除目标 ID 已被移除的分组。"""
    if not value or not removed_ids:
        return value, 0

    kept_groups: list[str] = []
    removed_count = 0
    for group in value.split(";"):
        parts = group.split(",", 2)
        if len(parts) >= 3 and parts[2].strip() in removed_ids:
            removed_count += 1
            continue
        kept_groups.append(group)

    return ";".join(kept_groups), removed_count


def remove_negative_coordinate_elements(
    layer: ET.Element,
    filename: str,
) -> NegativeCoordinateCleanupResult:
    """
    删除坐标含负数的图元，并清理其他保留图元中对它们的引用。

    本函数必须在任何平移之前执行，确保源文件原本存在的负坐标不会被后续
    X/Y 偏移掩盖。只检查明确的位置坐标和 d 路径，不检查尺寸、旋转、颜色等。
    """
    result = NegativeCoordinateCleanupResult()
    removed_ids: set[str] = set()

    def recurse(parent: ET.Element) -> None:
        for child in list(parent):
            if not local_name(child.tag):
                continue

            if element_has_negative_coordinate(child, filename):
                result.removed_root_elements += 1
                result.removed_total_elements += count_subtree_graph_elements(child)
                removed_ids.update(collect_subtree_nonempty_ids(child))
                parent.remove(child)
                continue

            recurse(child)

    recurse(layer)

    # 若同一个 ID 在保留元素中仍然存在（源文件本身重复 ID），不能清理该 ID 的引用。
    remaining_ids = set(collect_ids(layer))
    truly_removed_ids = removed_ids - remaining_ids
    result.removed_element_ids = len(truly_removed_ids)

    if truly_removed_ids:
        for element in iter_graph_elements(layer):
            for attr in REFERENCE_LIST_ATTRS:
                value = element.get(attr)
                if value is None:
                    continue
                new_value, removed_count = remove_reference_groups_to_ids(
                    value,
                    truly_removed_ids,
                )
                if removed_count:
                    element.set(attr, new_value)
                    result.removed_reference_groups += removed_count

            for attr in REFERENCE_SINGLE_ATTRS:
                value = element.get(attr)
                if value and value.strip() in truly_removed_ids:
                    element.set(attr, "")
                    result.cleared_single_references += 1

    return result


def get_bus_line(element: ET.Element) -> tuple[Decimal, Decimal, Decimal, Decimal] | None:
    """提取 Bus 的 x1,y1,x2,y2；缺失时尝试读取 d 的前两个点。"""
    x1 = try_decimal(element.get("x1"))
    y1 = try_decimal(element.get("y1"))
    x2 = try_decimal(element.get("x2"))
    y2 = try_decimal(element.get("y2"))

    if None not in (x1, y1, x2, y2):
        return x1, y1, x2, y2  # type: ignore[return-value]

    d_value = element.get("d")
    if d_value:
        points = parse_d_points(d_value)
        if len(points) >= 2:
            return points[0][0], points[0][1], points[1][0], points[1][1]

    return None


def find_top_horizontal_bus_y(layer: ET.Element, filename: str) -> Decimal | None:
    """查找最上面的有效非零长度水平 <Bus>；严格排除 <BusDis>。"""
    candidates: list[tuple[Decimal, Decimal, str]] = []

    for element in iter_graph_elements(layer):
        if local_name(element.tag) != "Bus":
            continue

        line = get_bus_line(element)
        if line is None:
            continue

        x1, y1, x2, y2 = line
        horizontal_span = abs(x2 - x1)
        vertical_delta = abs(y2 - y1)
        if horizontal_span > 0 and vertical_delta <= Decimal("0.000001"):
            candidates.append((min(y1, y2), horizontal_span, element.get("id", "")))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], -item[1]))
    return candidates[0][0]




def _unique_reference_groups(values: list[str]) -> str:
    """Merge semicolon-separated reference groups while preserving order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        for group in value.split(";"):
            group = group.strip()
            if group and group not in seen:
                seen.add(group)
                result.append(group)
    return ";".join(result)




def _top_horizontal_bus_candidates(layer: ET.Element) -> list[tuple[ET.Element, Decimal, Decimal, Decimal]]:
    """Return top horizontal Bus candidates with geometry (element, min_x, max_x, y)."""
    candidates: list[tuple[ET.Element, Decimal, Decimal, Decimal]] = []
    for element in iter_graph_elements(layer):
        if local_name(element.tag) != "Bus":
            continue
        line = get_bus_line(element)
        if line is None:
            continue
        x1, y1, x2, y2 = line
        if abs(y2 - y1) > Decimal("0.000001") or abs(x2 - x1) <= Decimal("0.000001"):
            continue
        candidates.append((element, min(x1, x2), max(x1, x2), (y1 + y2) / Decimal("2")))
    if not candidates:
        return []
    top_y = min(item[3] for item in candidates)
    tolerance = Decimal("1")
    return [item for item in candidates if abs(item[3] - top_y) <= tolerance]


def _horizontal_main_bus_candidates(layer: ET.Element) -> list[tuple[ET.Element, Decimal, Decimal, Decimal]]:
    """Return all non-degenerate horizontal Bus bars eligible for main-bus processing.

    Small-size residual Bus elements are no longer filtered here. They are handled
    centrally by the independent abnormal-small-element module.
    """
    candidates: list[tuple[ET.Element, Decimal, Decimal, Decimal]] = []
    for element in iter_graph_elements(layer):
        if local_name(element.tag) != "Bus":
            continue
        line = get_bus_line(element)
        if line is None:
            continue
        x1, y1, x2, y2 = line
        if abs(y2 - y1) > Decimal("0.000001"):
            continue
        if abs(x2 - x1) <= Decimal("0.000001"):
            continue
        candidates.append((element, min(x1, x2), max(x1, x2), (y1 + y2) / Decimal("2")))
    return candidates


def _bus_span(item: tuple[ET.Element, Decimal, Decimal, Decimal]) -> Decimal:
    return item[2] - item[1]


def _select_main_bus_candidates(
    layer: ET.Element,
    mode: str,
    filename: str,
) -> list[tuple[ET.Element, Decimal, Decimal, Decimal]]:
    """Select exactly the Bus bars relevant to the requested single/double-bus mode.

    * single: only the highest (minimum-Y) real horizontal Bus is relevant;
    * double: the highest Bus plus the nearest lower, parallel Bus whose length is
      approximately the same and whose horizontal projection substantially overlaps.

    All other Bus elements are ignored by this optional feature. Small-size Bus
    cleanup is intentionally delegated to the independent anomaly-detection module.
    """
    mode = (mode or "single").strip().lower()
    if mode not in {"single", "double"}:
        raise ValueError(f"{filename}：未知主母线类型 {mode!r}，只能选择单母线或双母线。")

    buses = _horizontal_main_bus_candidates(layer)
    if not buses:
        raise ValueError(f"{filename}：未找到有效水平 <Bus>，不能使用主母线处理。")

    # Highest Bus; if several are effectively on the same Y, take the longest as the
    # representative.  Per-file SLD input should normally expose one such Bus.
    buses_sorted = sorted(buses, key=lambda item: (item[3], -_bus_span(item), item[1]))
    top_y = buses_sorted[0][3]
    same_top = [item for item in buses_sorted if abs(item[3] - top_y) <= Decimal("1")]
    top = max(same_top, key=_bus_span)
    if mode == "single":
        return [top]

    top_span = _bus_span(top)
    second_candidates: list[tuple[Decimal, Decimal, tuple[ET.Element, Decimal, Decimal, Decimal]]] = []
    for item in buses_sorted:
        if item is top:
            continue
        y = item[3]
        if y <= top[3] + Decimal("1"):
            continue
        span = _bus_span(item)
        if top_span <= 0 or span <= 0:
            continue
        # "长度大致一样": allow 20% deviation.  Also require at least 60% horizontal
        # overlap relative to the shorter Bus so unrelated internal buses cannot be
        # mistaken for the second main bus.
        ratio = span / top_span
        if ratio < Decimal("0.8") or ratio > Decimal("1.2"):
            continue
        overlap = max(Decimal("0"), min(top[2], item[2]) - max(top[1], item[1]))
        shorter = min(top_span, span)
        if shorter <= 0 or overlap / shorter < Decimal("0.6"):
            continue
        second_candidates.append((y - top[3], abs(span - top_span), item))

    if not second_candidates:
        raise ValueError(
            f"{filename}：已选择双母线，但在最高母线同方向下方未找到长度大致相同的第二条有效水平 <Bus>。"
        )
    second_candidates.sort(key=lambda row: (row[0], row[1], row[2][1]))
    return [top, second_candidates[0][2]]


def inspect_main_bus_metadata(path: Path, mode: str = "single") -> dict[str, object]:
    """Inspect only the Bus bar(s) selected by the user's single/double-bus choice.

    facID/facName are deliberately ignored.  Filename differences are UI warnings
    only.  The hard requirement is that every selected Bus has a non-empty keyid.
    """
    tree = parse_xml(path)
    root = tree.getroot()
    if local_name(root.tag) != "G":
        raise ValueError(f"{path.name}：根节点不是 G。")
    layer = get_only_layer(root, path.name)
    try:
        selected = _select_main_bus_candidates(layer, mode, path.name)
    except ValueError as exc:
        return {"path": path, "buses": [], "keyids": [], "reason": str(exc)}

    metadata_buses: list[dict[str, object]] = []
    missing: list[str] = []
    for element, min_x, max_x, y in selected:
        bus_id = (element.get("id") or "").strip()
        keyid = (element.get("keyid") or "").strip()
        if not keyid:
            missing.append(bus_id or "(无ID)")
            continue
        metadata_buses.append({
            "id": bus_id,
            "keyid": keyid,
            "y": y,
            "min_x": min_x,
            "max_x": max_x,
            "span": max_x - min_x,
        })

    if missing:
        return {
            "path": path,
            "buses": metadata_buses,
            "keyids": [str(item["keyid"]) for item in metadata_buses],
            "reason": "选定主母线缺少 keyid 属性或 keyid 为空，Bus ID：" + ", ".join(missing[:20]),
        }

    keyids = [str(item["keyid"]) for item in metadata_buses]
    if mode == "double" and len(set(keyids)) != 2:
        return {
            "path": path,
            "buses": metadata_buses,
            "keyids": keyids,
            "reason": "双母线模式要求两条主母线分别具有独立 keyid，禁止把两条母线识别成同一母线。",
        }
    return {"path": path, "buses": metadata_buses, "keyids": keyids, "reason": ""}


def validate_main_bus_keyid_sequence(paths: list[Path], mode: str = "single") -> list[dict[str, object]]:
    """Validate selected main-bus keyids and require each keyid block to be contiguous."""
    metadata = [inspect_main_bus_metadata(path, mode) for path in paths]
    invalid = [item for item in metadata if item.get("reason")]
    if invalid:
        details = "；".join(f"{Path(item['path']).name}：{item['reason']}" for item in invalid[:10])
        raise ValueError("主母线合并不可用：" + details)

    positions: dict[str, list[int]] = {}
    for index, item in enumerate(metadata):
        for keyid in item.get("keyids", []):
            positions.setdefault(str(keyid), []).append(index)

    interrupted: list[str] = []
    for keyid, indexes in positions.items():
        if indexes and indexes != list(range(indexes[0], indexes[-1] + 1)):
            interrupted.append(keyid)
    if interrupted:
        lines = [
            "馈线排序不准确，母线 keyid 被阻断。必须把包含同一 keyid 的馈线连续排列后才能使用主母线合并。",
            "请按下面的文件名和顺序调整馈线列表：",
        ]
        for keyid in interrupted:
            indexes = positions[keyid]
            lines.append(f"keyid={keyid}：")
            for index in indexes:
                item = metadata[index]
                bus_matches = [
                    bus for bus in item.get("buses", [])
                    if str(bus.get("keyid", "")) == keyid
                ]
                if bus_matches:
                    for bus in bus_matches:
                        bus_label = "上母线"
                        if mode == "double" and len(item.get("buses", [])) > 1:
                            ordered = sorted(item.get("buses", []), key=lambda b: b.get("y", Decimal("0")))
                            try:
                                bus_label = "上母线" if ordered.index(bus) == 0 else "下母线"
                            except ValueError:
                                bus_label = "主母线"
                        lines.append(
                            f"  第 {index + 1} 个：{Path(item['path']).name}；{bus_label}；"
                            f"Bus XML ID={bus.get('id') or '(无ID)'}；Y={bus.get('y')}"
                        )
                else:
                    lines.append(f"  第 {index + 1} 个：{Path(item['path']).name}")

            first, last = indexes[0], indexes[-1]
            blockers = [
                (i, metadata[i]) for i in range(first + 1, last)
                if keyid not in [str(value) for value in metadata[i].get("keyids", [])]
            ]
            if blockers:
                lines.append("  中间阻断文件：")
                for index, item in blockers:
                    other_keyids = ", ".join(str(v) for v in item.get("keyids", [])) or "(无 keyid)"
                    lines.append(
                        f"    第 {index + 1} 个：{Path(item['path']).name}；该文件主母线 keyid={other_keyids}"
                    )
        raise ValueError("\n".join(lines))
    return metadata


def _set_line_points(element: ET.Element, points: list[tuple[Decimal, Decimal]]) -> None:
    """Update a line-like element after moving one endpoint.

    G line geometry uses a 3-unit visual padding around the actual points.  Preserve
    that convention while updating d and any explicit endpoint attributes.
    """
    if len(points) < 2:
        return
    element.set("d", " ".join(f"{format_integer(x)},{format_integer(y)}" for x, y in points))
    if "x1" in element.attrib:
        element.set("x1", format_integer(points[0][0]))
    if "y1" in element.attrib:
        element.set("y1", format_integer(points[0][1]))
    if "x2" in element.attrib:
        element.set("x2", format_integer(points[-1][0]))
    if "y2" in element.attrib:
        element.set("y2", format_integer(points[-1][1]))
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    if "x" in element.attrib:
        element.set("x", format_integer(min_x - Decimal("3")))
    if "y" in element.attrib:
        element.set("y", format_integer(min_y - Decimal("3")))
    if "w" in element.attrib:
        element.set("w", format_integer(max_x - min_x + Decimal("6")))
    if "h" in element.attrib:
        element.set("h", format_integer(max_y - min_y + Decimal("6")))


def _move_bus_to_y_with_attached_lines(
    layer: ET.Element,
    bus: ET.Element,
    target_y: Decimal,
    *,
    endpoint_tolerance: Decimal = Decimal("2"),
) -> int:
    """Move one horizontal Bus and stretch line endpoints attached to its old row.

    Only endpoints geometrically touching the Bus span are moved; devices and the rest
    of the feeder are left in place.  Returns the number of line endpoints adjusted.
    """
    bus_line = get_bus_line(bus)
    if bus_line is None:
        return 0
    x1, old_y1, x2, old_y2 = bus_line
    old_y = (old_y1 + old_y2) / Decimal("2")
    if abs(target_y - old_y) <= Decimal("0.000001"):
        return 0
    min_x, max_x = min(x1, x2), max(x1, x2)

    adjusted = 0
    for element in iter_graph_elements(layer):
        if element is bus:
            continue
        tag = local_name(element.tag)
        if tag not in {"ConnectLine", "FeedLine", "line"}:
            continue
        raw_d = element.get("d")
        if not raw_d:
            continue
        points = parse_d_points(raw_d)
        if len(points) < 2:
            continue
        changed = False
        for idx in (0, len(points) - 1):
            px, py = points[idx]
            if min_x - endpoint_tolerance <= px <= max_x + endpoint_tolerance and abs(py - old_y) <= endpoint_tolerance:
                points[idx] = (px, target_y)
                changed = True
                adjusted += 1
        if changed:
            _set_line_points(element, points)

    bus.set("x1", format_integer(x1))
    bus.set("y1", format_integer(target_y))
    bus.set("x2", format_integer(x2))
    bus.set("y2", format_integer(target_y))
    bus.set("d", f"{format_integer(x1)},{format_integer(target_y)} {format_integer(x2)},{format_integer(target_y)}")
    if "y" in bus.attrib:
        bus.set("y", format_integer(target_y - Decimal("3")))
    if "h" in bus.attrib:
        bus.set("h", "6")
    return adjusted


def normalize_selected_main_bus_rows(
    layer: ET.Element,
    selected_keyids: set[str],
    *,
    tolerance: Decimal = Decimal("1"),
) -> tuple[dict[str, Decimal], list[dict[str, object]]]:
    """Normalize minority Y offsets within each selected keyid group.

    The highest feeder alignment row is already fixed before this function runs.  For
    every selected keyid, the dominant Y is chosen by exact integer-mode; ties fall back
    to the median.  Minority Bus rows are moved to that Y and attached line endpoints
    are stretched accordingly.
    """
    grouped: dict[str, list[tuple[ET.Element, Decimal, Decimal, Decimal]]] = {}
    for item in _horizontal_main_bus_candidates(layer):
        keyid = (item[0].get("keyid") or "").strip()
        if keyid in selected_keyids:
            grouped.setdefault(keyid, []).append(item)

    targets: dict[str, Decimal] = {}
    changes: list[dict[str, object]] = []
    for keyid, rows in grouped.items():
        if not rows:
            continue
        integer_ys = [int(row[3].to_integral_value()) for row in rows]
        counts = Counter(integer_ys)
        max_count = max(counts.values())
        modes = sorted(y for y, count in counts.items() if count == max_count)
        if len(modes) == 1:
            target_y = Decimal(modes[0])
        else:
            ordered = sorted(row[3] for row in rows)
            target_y = ordered[len(ordered) // 2]
        targets[keyid] = target_y

        for bus, _min_x, _max_x, current_y in rows:
            if abs(current_y - target_y) <= tolerance:
                # Even a one-pixel minority is normalized so merge geometry becomes exact.
                if abs(current_y - target_y) <= Decimal("0.000001"):
                    continue
            endpoints = _move_bus_to_y_with_attached_lines(layer, bus, target_y)
            changes.append({
                "keyid": keyid,
                "bus_id": (bus.get("id") or "").strip(),
                "from_y": current_y,
                "to_y": target_y,
                "adjusted_endpoints": endpoints,
            })
    return targets, changes


def merge_aligned_top_buses(
    layer: ET.Element,
    filename: str,
    selected_keyid_y: dict[str, Decimal] | None = None,
) -> dict[str, object]:
    """Merge only validated main-bus rows, grouped by keyid.

    ``selected_keyid_y`` is built from the per-file single/double-bus inspection after
    feeder alignment.  It prevents unrelated Bus elements from joining merely because
    they happen to reuse a keyid.  Different keyids are never merged.
    """
    buses = _horizontal_main_bus_candidates(layer)
    if selected_keyid_y is not None:
        buses = [
            item for item in buses
            if (item[0].get("keyid") or "").strip() in selected_keyid_y
            and abs(item[3] - selected_keyid_y[(item[0].get("keyid") or "").strip()]) <= Decimal("1")
        ]
    if not buses:
        return {"changed": False, "bus_count": 0, "removed": 0, "groups": []}

    keyed: list[tuple[ET.Element, Decimal, Decimal, Decimal, str]] = []
    for element, min_x, max_x, y in buses:
        keyid = (element.get("keyid") or "").strip()
        if not keyid:
            # Non-selected/unrelated buses do not participate; selected buses were
            # already hard-validated before entering merge_g_files.
            continue
        keyed.append((element, min_x, max_x, y, keyid))

    grouped: dict[str, list[tuple[ET.Element, Decimal, Decimal, Decimal, str]]] = {}
    key_order: list[str] = []
    for item in keyed:
        keyid = item[4]
        if keyid not in grouped:
            grouped[keyid] = []
            key_order.append(keyid)
        grouped[keyid].append(item)

    parent_map = {child: parent for parent in layer.iter() for child in list(parent)}
    total_removed = 0
    removed_id_map: dict[str, str] = {}
    summaries: list[dict[str, object]] = []

    for keyid in key_order:
        run = grouped[keyid]
        y_values = sorted({item[3] for item in run})
        if len(y_values) > 1:
            raise ValueError(
                f"{filename}：keyid={keyid} 的母线没有处在同一水平线上，禁止合并。"
                " 请先确认馈线垂直对齐和母线层级一致。"
            )

        if len(run) == 1:
            element, min_x, max_x, y, _ = run[0]
            summaries.append({
                "keyid": keyid, "bus_count": 1, "removed": 0,
                "keeper_id": (element.get("id") or "").strip(),
                "min_x": min_x, "max_x": max_x, "y": y,
            })
            continue

        run = sorted(run, key=lambda item: (item[1], item[2]))
        keeper, _kx1, _kx2, merged_y, _ = run[0]
        keeper_id = (keeper.get("id") or "").strip()
        if not keeper_id:
            raise ValueError(f"{filename}：keyid={keyid} 的水平主母线缺少 id，无法合并。")
        min_x = min(item[1] for item in run)
        max_x = max(item[2] for item in run)
        old_ids = [((item[0].get("id") or "").strip()) for item in run[1:]]
        old_ids = [value for value in old_ids if value]
        id_map = {old_id: keeper_id for old_id in old_ids}
        update_reference_attributes(list(layer), id_map)
        removed_id_map.update(id_map)

        node_groups = _unique_reference_groups([item[0].get("node_area", "") for item in run])
        link_groups = _unique_reference_groups([item[0].get("link", "") for item in run])
        if node_groups:
            keeper.set("node_area", node_groups)
        elif "node_area" in keeper.attrib:
            keeper.set("node_area", "")
        if link_groups:
            keeper.set("link", link_groups)
        elif "link" in keeper.attrib:
            keeper.set("link", "")

        keeper.set("x1", format_integer(min_x))
        keeper.set("y1", format_integer(merged_y))
        keeper.set("x2", format_integer(max_x))
        keeper.set("y2", format_integer(merged_y))
        keeper.set("d", f"{format_integer(min_x)},{format_integer(merged_y)} {format_integer(max_x)},{format_integer(merged_y)}")
        keeper.set("x", format_integer(min_x - Decimal("3")))
        keeper.set("y", format_integer(merged_y - Decimal("3")))
        keeper.set("w", format_integer(max_x - min_x + Decimal("6")))
        keeper.set("h", "6")

        removed = 0
        for element, *_ in run[1:]:
            parent = parent_map.get(element)
            if parent is None:
                raise ValueError(f"{filename}：无法定位待删除主母线 id={element.get('id', '')} 的父节点。")
            parent.remove(element)
            removed += 1
        total_removed += removed
        summaries.append({
            "keyid": keyid, "bus_count": len(run), "removed": removed,
            "keeper_id": keeper_id, "min_x": min_x, "max_x": max_x, "y": merged_y,
        })

    return {
        "changed": total_removed > 0,
        "bus_count": len(buses),
        "removed": total_removed,
        "removed_id_map": removed_id_map,
        "groups": summaries,
    }

def merge_explicit_bus_elements(
    layer: ET.Element,
    buses: list[ET.Element],
    filename: str,
    group_label: str,
    lane_label: str,
) -> dict[str, object]:
    """Merge one user-defined group of Bus elements, without using keyid."""
    if not buses:
        return {"removed": 0, "removed_id_map": {}, "keeper_id": ""}
    rows = []
    for bus in buses:
        line = get_bus_line(bus)
        if line is None:
            raise ValueError(f"{filename}：{group_label} {lane_label} 包含无法读取的 Bus id={bus.get('id','')}。")
        x1,y1,x2,y2=line
        if abs(y2-y1) > Decimal("0.000001"):
            raise ValueError(f"{filename}：{group_label} {lane_label} 的 Bus id={bus.get('id','')} 不是水平母线。")
        rows.append((bus,min(x1,x2),max(x1,x2),(y1+y2)/Decimal("2")))
    ys={row[3] for row in rows}
    if len(ys) != 1:
        raise ValueError(f"{filename}：{group_label} {lane_label} 自动校正后仍未处于同一水平线上。")
    rows.sort(key=lambda r:(r[1],r[2]))
    keeper=rows[0][0]
    keeper_id=(keeper.get("id") or "").strip()
    if not keeper_id:
        raise ValueError(f"{filename}：{group_label} {lane_label} 的保留 Bus 缺少 id。")
    min_x=min(r[1] for r in rows); max_x=max(r[2] for r in rows); y=rows[0][3]
    old_ids=[(r[0].get("id") or "").strip() for r in rows[1:]]
    id_map={old:keeper_id for old in old_ids if old}
    update_reference_attributes(list(layer), id_map)
    node_groups=_unique_reference_groups([r[0].get("node_area","") for r in rows])
    link_groups=_unique_reference_groups([r[0].get("link","") for r in rows])
    if node_groups: keeper.set("node_area",node_groups)
    elif "node_area" in keeper.attrib: keeper.set("node_area","")
    if link_groups: keeper.set("link",link_groups)
    elif "link" in keeper.attrib: keeper.set("link","")
    keeper.set("x1",format_integer(min_x)); keeper.set("y1",format_integer(y))
    keeper.set("x2",format_integer(max_x)); keeper.set("y2",format_integer(y))
    keeper.set("d",f"{format_integer(min_x)},{format_integer(y)} {format_integer(max_x)},{format_integer(y)}")
    keeper.set("x",format_integer(min_x-Decimal("3"))); keeper.set("y",format_integer(y-Decimal("3")))
    keeper.set("w",format_integer(max_x-min_x+Decimal("6"))); keeper.set("h","6")
    parent_map={child:parent for parent in layer.iter() for child in list(parent)}
    removed=0
    for bus,*_ in rows[1:]:
        parent=parent_map.get(bus)
        if parent is None: raise ValueError(f"{filename}：无法定位待删除 Bus id={bus.get('id','')} 的父节点。")
        parent.remove(bus); removed+=1
    return {"removed":removed,"removed_id_map":id_map,"keeper_id":keeper_id,"min_x":min_x,"max_x":max_x,"y":y}


def resolve_alignment_y(layer: ET.Element, filename: str) -> tuple[Decimal, str]:
    """优先使用顶部有效水平 <Bus>；没有 <Bus> 时使用整张图最高元素的 Y。"""
    bus_y = find_top_horizontal_bus_y(layer, filename)
    if bus_y is not None:
        return bus_y, "顶部水平 <Bus>"

    _min_x, min_y, _max_x, _max_y = get_position_coordinate_extents(layer, filename)
    return min_y, "最高图元（未找到有效水平 <Bus>）"


def contains_outer_frame(
    root: ET.Element,
    layer: ET.Element,
    filename: str,
) -> bool:
    """识别接近画布四周、覆盖大部分画布的外框线或大矩形。"""
    width = get_root_dimension(root, "w", "width", filename)
    height = get_root_dimension(root, "h", "height", filename)
    if width <= 0 or height <= 0:
        return False

    edge_x = max(Decimal("100"), width * Decimal("0.08"))
    edge_y = max(Decimal("100"), height * Decimal("0.08"))
    min_horizontal_span = width * Decimal("0.70")
    min_vertical_span = height * Decimal("0.70")

    top = right = bottom = left = False

    for element in iter_graph_elements(layer):
        tag = local_name(element.tag).lower()

        if tag in {"rect", "rectangle"}:
            x = try_decimal(element.get("x"))
            y = try_decimal(element.get("y"))
            w = try_decimal(element.get("w") or element.get("width"))
            h = try_decimal(element.get("h") or element.get("height"))
            if None not in (x, y, w, h):
                assert x is not None and y is not None and w is not None and h is not None
                if (
                    w >= min_horizontal_span
                    and h >= min_vertical_span
                    and x <= edge_x
                    and y <= edge_y
                    and width - (x + w) <= edge_x
                    and height - (y + h) <= edge_y
                ):
                    return True

        if tag != "line":
            continue
        endpoints = get_bus_line(element)
        if endpoints is None:
            continue
        x1, y1, x2, y2 = endpoints
        horizontal = abs(y2 - y1) <= Decimal("0.000001")
        vertical = abs(x2 - x1) <= Decimal("0.000001")

        if horizontal and abs(x2 - x1) >= min_horizontal_span:
            y = min(y1, y2)
            if y <= edge_y:
                top = True
            if height - y <= edge_y:
                bottom = True

        if vertical and abs(y2 - y1) >= min_vertical_span:
            x = min(x1, x2)
            if x <= edge_x:
                left = True
            if width - x <= edge_x:
                right = True

    return top and right and bottom and left


def validate_no_outer_frame(root: ET.Element, layer: ET.Element, filename: str) -> None:
    if contains_outer_frame(root, layer, filename):
        raise ValueError(
            f"文件 {filename} 检测到接近画布四周的外框架图。\n"
            "参与馈线图合并的输入文件不能包含无法安全处理的外框、左上标题块或右下签字栏；"
            "请使用未添加图框的原始馈线图。"
        )


def _remove_builtin_frame_for_merge(
    root: ET.Element,
    layer: ET.Element,
    components: Iterable[ET.Element],
) -> tuple[int, int, int]:
    """从内存中的合并副本移除内置图框，并清理失效引用。

    源文件不会被修改。返回：删除直属组件数、真正删除的 ID 数、清理引用数。
    """
    component_ids = {id(element) for element in components}
    direct_children = list(layer)
    targets = [element for element in direct_children if id(element) in component_ids]
    if not targets:
        raise ValueError("已识别内置图框，但没有找到可从 Layer 移除的直属图框组件。")

    removed_ids: set[str] = set()
    for element in targets:
        removed_ids.update(collect_subtree_nonempty_ids(element))
        layer.remove(element)

    remaining_ids = set(collect_ids(layer))
    truly_removed_ids = removed_ids - remaining_ids
    cleaned_references = 0
    if truly_removed_ids:
        for element in iter_graph_elements(layer):
            for attr in REFERENCE_LIST_ATTRS:
                value = element.get(attr)
                if value is None:
                    continue
                new_value, removed_count = remove_reference_groups_to_ids(
                    value, truly_removed_ids
                )
                if removed_count:
                    element.set(attr, new_value)
                    cleaned_references += removed_count

            for attr in REFERENCE_SINGLE_ATTRS:
                value = element.get(attr)
                if value and value.strip() in truly_removed_ids:
                    element.set(attr, "")
                    cleaned_references += 1

    # 输出基准文件不能继续携带“已有图框”身份标记。
    for attr in (
        GFS_FRAME_TYPE_ATTRIBUTE,
        GFS_FRAME_TEMPLATE_ATTRIBUTE,
        GFS_FRAME_COMPONENT_ATTRIBUTE,
    ):
        root.attrib.pop(attr, None)

    return len(targets), len(truly_removed_ids), cleaned_references


def _prepare_frame_for_merge(
    root: ET.Element,
    layer: ET.Element,
    root_width: Decimal,
    root_height: Decimal,
    filename: str,
) -> tuple[str, str, int, int, int]:
    """分类图框；内置图框从内存副本移除，其他图框拒绝合并。"""
    try:
        inspection = inspect_merge_frame(
            root,
            layer,
            float(root_width),
            float(root_height),
        )
    except MergeFrameInspectionError as exc:
        raise UnsupportedMergeFrameError(
            f"文件 {filename} 的内置图框结构异常，不能安全参与合并：\n{exc}"
        ) from exc

    if inspection.kind == FRAME_UNSUPPORTED:
        raise UnsupportedMergeFrameError(
            f"文件 {filename} 检测到非 G File Studio 内置图框，不能参与合并。\n"
            f"原因：{inspection.reason or '图框来源或结构无法确认。'}"
        )

    if inspection.kind == FRAME_BUILTIN:
        removed_count, removed_ids, cleaned_references = _remove_builtin_frame_for_merge(
            root, layer, inspection.components
        )
        return (
            FRAME_BUILTIN,
            inspection.detection_mode,
            removed_count,
            removed_ids,
            cleaned_references,
        )

    return FRAME_NONE, inspection.detection_mode, 0, 0, 0


def inspect_merge_candidate(info: GFileInfo) -> MergeCandidateInspection:
    """完整检查一个候选文件，供加载列表和模糊查询对话框使用。"""
    try:
        parsed = parse_g_file(info)
    except UnsupportedMergeFrameError as exc:
        return MergeCandidateInspection(
            info=info,
            eligible=False,
            status="非内置图框（禁止合并）",
            frame_kind=FRAME_UNSUPPORTED,
            error=str(exc),
        )
    except Exception as exc:
        return MergeCandidateInspection(
            info=info,
            eligible=False,
            status="检查失败",
            frame_kind="invalid",
            error=str(exc),
        )

    if parsed.frame_kind == FRAME_BUILTIN:
        status = "内置图框（合并时自动移除）"
    else:
        status = "正常"
    return MergeCandidateInspection(
        info=info,
        eligible=True,
        status=status,
        frame_kind=parsed.frame_kind,
        frame_detection_mode=parsed.frame_detection_mode,
        alignment_mode=parsed.alignment_mode,
        alignment_y=parsed.alignment_y,
    )


def inspect_merge_candidates(
    input_dir: Path,
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[MergeCandidateInspection]:
    """按自然顺序加载并检查目录中的全部候选文件。"""
    infos = discover_files(input_dir)
    total = len(infos)
    results: list[MergeCandidateInspection] = []
    for index, info in enumerate(infos, 1):
        if progress_callback is not None:
            progress_callback(index - 1, total, info.path.name)
        results.append(inspect_merge_candidate(info))
        if progress_callback is not None:
            progress_callback(index, total, info.path.name)
    return results


def get_graph_extents(
    children_or_layer: Iterable[ET.Element] | ET.Element,
    filename: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    计算图形内容的最小/最大 X、Y 边界。

    综合考虑：
      x/y、x1/y1、x2/y2、cx/cy、mergex/mergey、d
      x+w、y+h、cx±rx、cy±ry、mergex+w、mergey+h
    """
    x_values: list[Decimal] = []
    y_values: list[Decimal] = []

    for element in iter_graph_elements(children_or_layer):
        tag = local_name(element.tag)

        numeric: dict[str, Decimal] = {}
        for attr in (
            "x", "y", "x1", "y1", "x2", "y2", "cx", "cy",
            "mergex", "mergey", "w", "h", "rx", "ry",
        ):
            raw = element.get(attr)
            if raw is None:
                continue
            value = try_decimal(raw)
            if value is None:
                raise ValueError(
                    f"文件 {filename} 中 <{tag}> 的 {attr} 不是有效数字：{raw!r}"
                )
            numeric[attr] = value

        for attr in ("x", "x1", "x2", "cx", "mergex"):
            if attr in numeric:
                x_values.append(numeric[attr])

        for attr in ("y", "y1", "y2", "cy", "mergey"):
            if attr in numeric:
                y_values.append(numeric[attr])

        if "x" in numeric and "w" in numeric:
            x_values.append(numeric["x"] + numeric["w"])
        if "y" in numeric and "h" in numeric:
            y_values.append(numeric["y"] + numeric["h"])
        if "cx" in numeric and "rx" in numeric:
            x_values.extend((numeric["cx"] - numeric["rx"], numeric["cx"] + numeric["rx"]))
        if "cy" in numeric and "ry" in numeric:
            y_values.extend((numeric["cy"] - numeric["ry"], numeric["cy"] + numeric["ry"]))
        if "mergex" in numeric and "w" in numeric:
            x_values.append(numeric["mergex"] + numeric["w"])
        if "mergey" in numeric and "h" in numeric:
            y_values.append(numeric["mergey"] + numeric["h"])

        d_value = element.get("d")
        if d_value:
            for point_x, point_y in parse_d_points(d_value):
                x_values.append(point_x)
                y_values.append(point_y)

    if not x_values:
        raise ValueError(f"文件 {filename} 的 Layer 中没有找到可计算的 X 坐标")
    if not y_values:
        raise ValueError(f"文件 {filename} 的 Layer 中没有找到可计算的 Y 坐标")

    return min(x_values), min(y_values), max(x_values), max(y_values)


def get_position_coordinate_extents(
    children_or_layer: Iterable[ET.Element] | ET.Element,
    filename: str,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    只根据“位置坐标值”计算最小/最大 X、Y。

    用于：
      - 相邻馈线严格间隔；
      - 最终上、左、右、下边距；
      - G.w/width 和 G.h/height。

    这里不把 w/h、rx/ry 当作坐标，因为用户规则明确以最小/最大 x、y
    坐标值为基准。
    """
    x_values: list[Decimal] = []
    y_values: list[Decimal] = []

    for element in iter_graph_elements(children_or_layer):
        tag = local_name(element.tag)

        for attr in HORIZONTAL_POSITION_ATTRS:
            raw = element.get(attr)
            if raw is None:
                continue
            value = try_decimal(raw)
            if value is None:
                raise ValueError(
                    f"文件 {filename} 中 <{tag}> 的 {attr} 不是有效数字：{raw!r}"
                )
            x_values.append(value)

        for attr in VERTICAL_POSITION_ATTRS:
            raw = element.get(attr)
            if raw is None:
                continue
            value = try_decimal(raw)
            if value is None:
                raise ValueError(
                    f"文件 {filename} 中 <{tag}> 的 {attr} 不是有效数字：{raw!r}"
                )
            y_values.append(value)

        d_value = element.get("d")
        if d_value:
            for point_x, point_y in parse_d_points(d_value):
                x_values.append(point_x)
                y_values.append(point_y)

    if not x_values:
        raise ValueError(f"文件 {filename} 的 Layer 中没有找到可计算的 X 坐标")
    if not y_values:
        raise ValueError(f"文件 {filename} 的 Layer 中没有找到可计算的 Y 坐标")

    return min(x_values), min(y_values), max(x_values), max(y_values)


def get_graph_bounds(
    children_or_layer: Iterable[ET.Element] | ET.Element,
    filename: str,
) -> tuple[Decimal, Decimal]:
    """兼容原有调用：仅返回最大 X 和最大 Y。"""
    _min_x, _min_y, max_x, max_y = get_graph_extents(
        children_or_layer,
        filename,
    )
    return max_x, max_y


def ceiling_to_integer(value: Decimal) -> Decimal:
    """向正无穷方向取整，用于保证边距不会小于配置值。"""
    return value.to_integral_value(rounding=ROUND_CEILING)

def shift_d_value(d_value: str, offset_x: Decimal, offset_y: Decimal) -> str:
    """将 d 属性中的每个坐标点同时做 X/Y 平移。"""
    def replace_point(match: re.Match[str]) -> str:
        old_x = parse_decimal(match.group("x"), "d 属性中的 x")
        old_y = parse_decimal(match.group("y"), "d 属性中的 y")
        return (
            f"{format_decimal(old_x + offset_x)}"
            f"{match.group('comma')}"
            f"{format_decimal(old_y + offset_y)}"
        )

    return POINT_PATTERN.sub(replace_point, d_value)


def shift_graph_elements(
    children: Iterable[ET.Element],
    offset_x: Decimal,
    offset_y: Decimal,
) -> None:
    """平移复制出来的全部图元。"""
    for element in iter_graph_elements(children):
        tag = local_name(element.tag)

        for attr in HORIZONTAL_POSITION_ATTRS:
            if attr not in element.attrib:
                continue
            old_value = parse_decimal(
                element.attrib[attr], f"<{tag}> 的 {attr} 属性"
            )
            element.set(attr, format_decimal(old_value + offset_x))

        for attr in VERTICAL_POSITION_ATTRS:
            if attr not in element.attrib:
                continue
            old_value = parse_decimal(
                element.attrib[attr], f"<{tag}> 的 {attr} 属性"
            )
            element.set(attr, format_decimal(old_value + offset_y))

        if "d" in element.attrib:
            element.set(
                "d",
                shift_d_value(element.attrib["d"], offset_x, offset_y),
            )


def normalize_position_coordinates_to_integers(
    children_or_layer: Iterable[ET.Element] | ET.Element,
) -> int:
    """
    将最终 Layer 中的全部位置坐标统一取整。

    为保证同一图元的包围框、端点和实际路径一致，必须同时处理：
      x/y、x1/y1、x2/y2、cx/cy、mergex/mergey，以及 d 中全部点。

    返回实际发生变化的属性数量，便于日志检查。
    """
    changed_count = 0
    position_attrs = (*HORIZONTAL_POSITION_ATTRS, *VERTICAL_POSITION_ATTRS)

    for element in iter_graph_elements(children_or_layer):
        tag = local_name(element.tag)

        for attr in position_attrs:
            raw_value = element.get(attr)
            if raw_value is None:
                continue

            old_value = parse_decimal(raw_value, f"<{tag}> 的 {attr} 属性")
            new_value = format_integer(old_value)
            if new_value != raw_value.strip():
                changed_count += 1
            element.set(attr, new_value)

        d_value = element.get("d")
        if d_value is not None:
            def replace_point(match: re.Match[str]) -> str:
                old_x = parse_decimal(match.group("x"), "d 属性中的 x")
                old_y = parse_decimal(match.group("y"), "d 属性中的 y")
                return (
                    f"{format_integer(old_x)}"
                    f"{match.group('comma')}"
                    f"{format_integer(old_y)}"
                )

            new_d = POINT_PATTERN.sub(replace_point, d_value)
            if new_d != d_value:
                changed_count += 1
            element.set("d", new_d)

    return changed_count


def collect_ids(children_or_layer: Iterable[ET.Element] | ET.Element) -> list[str]:
    """按 XML 顺序收集 Layer 中所有非空的图元 id。"""
    result: list[str] = []
    for element in iter_graph_elements(children_or_layer):
        value = element.get("id")
        if value is not None and value.strip():
            result.append(value.strip())
    return result


def unique_in_order(values: Iterable[str]) -> list[str]:
    """保持首次出现顺序去重。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_reference_ids(value: str) -> list[str]:
    """从 link/node_area 中提取每个分组的第三项 ID。"""
    refs: list[str] = []
    for group in value.split(";"):
        parts = group.split(",", 2)
        if len(parts) >= 3 and parts[2].strip():
            refs.append(parts[2].strip())
    return refs


def collect_reference_ids(
    children_or_layer: Iterable[ET.Element] | ET.Element,
) -> list[str]:
    """按 XML 顺序收集已知引用属性中的所有非空 ID。"""
    result: list[str] = []
    for element in iter_graph_elements(children_or_layer):
        for attr in REFERENCE_LIST_ATTRS:
            value = element.get(attr)
            if value:
                result.extend(extract_reference_ids(value))

        for attr in REFERENCE_SINGLE_ATTRS:
            value = element.get(attr)
            if value and value.strip():
                result.append(value.strip())
    return result


def collect_identifier_tokens(
    children_or_layer: Iterable[ET.Element] | ET.Element,
) -> list[str]:
    """
    收集一个 Layer 的完整 ID 命名空间。

    不仅包含元素自身 id，也包含 link/node_area 等引用中的 ID。
    后者可能是没有对应 XML 元素的“虚拟拓扑节点 ID”。
    """
    return unique_in_order(
        [
            *collect_ids(children_or_layer),
            *collect_reference_ids(children_or_layer),
        ]
    )


def _longest_zero_run_start(value: str) -> int | None:
    """返回数字串中最长连续 0 段的起点；并列时取最靠左的一段。"""
    best_start: int | None = None
    best_length = 0
    index = 1  # 第 1 位必须属于类型编号，避免得到空前缀。
    while index < len(value):
        if value[index] != "0":
            index += 1
            continue
        end = index
        while end < len(value) and value[end] == "0":
            end += 1
        run_length = end - index
        if run_length >= 2 and run_length > best_length:
            best_start = index
            best_length = run_length
        index = end
    return best_start


def infer_element_id_patterns(
    children_or_layer: Iterable[ET.Element] | ET.Element,
) -> dict[str, ElementIdPattern]:
    """
    仅依据当前单个 G 文件中的同类 XML 元素推断 ID 规则。

    规则模型为：ID = 类型前缀 + 固定宽度顺序号。先取同类元素中使用
    最多的总位数，再从多数样本的补零区间推断前缀。该逻辑不依赖外部
    JSON，也不会主动改写唯一且有效的旧 ID；仅在产生新 ID 时使用。
    """
    grouped: dict[str, list[str]] = {}
    # G 文件的业务图元 ID 位于直属 Layer 子元素上。推断同类格式时只统计
    # 这些直属图元，避免内部辅助节点干扰前缀和总位数判断。
    if isinstance(children_or_layer, ET.Element):
        pattern_elements = list(children_or_layer)
    else:
        pattern_elements = list(children_or_layer)
    for element in pattern_elements:
        value = (element.get("id") or "").strip()
        if not value.isdigit():
            continue
        grouped.setdefault(local_name(element.tag), []).append(value)

    patterns: dict[str, ElementIdPattern] = {}
    for tag, raw_values in grouped.items():
        values = unique_in_order(raw_values)
        if len(values) < 2:
            continue

        length_counter = Counter(len(value) for value in values)
        dominant_length = max(
            length_counter,
            key=lambda length: (length_counter[length], length),
        )
        dominant = [value for value in values if len(value) == dominant_length]
        if len(dominant) < 2:
            continue

        # 多数工业图元 ID 形如“类型前缀 + 若干补零 + 顺序号”。取每个
        # 样本中最长补零段的起点，再以出现最多的位置作为前缀边界。
        start_counter = Counter(
            start
            for value in dominant
            if (start := _longest_zero_run_start(value)) is not None
        )

        prefix: str | None = None
        if start_counter:
            prefix_length, occurrence = max(
                start_counter.items(),
                key=lambda item: (item[1], -item[0]),
            )
            prefix_counter = Counter(value[:prefix_length] for value in dominant)
            candidate_prefix, prefix_occurrence = prefix_counter.most_common(1)[0]
            required = max(2, math.ceil(len(dominant) * 0.5))
            if occurrence >= required and prefix_occurrence >= required:
                prefix = candidate_prefix

        if prefix is None:
            # 降级：取同长度样本的公共前缀，并把末尾的补零剥离。
            common = dominant[0]
            for value in dominant[1:]:
                limit = min(len(common), len(value))
                index = 0
                while index < limit and common[index] == value[index]:
                    index += 1
                common = common[:index]
                if not common:
                    break
            common = common.rstrip("0")
            if common and len(common) < dominant_length:
                prefix = common

        if not prefix or len(prefix) >= dominant_length:
            continue

        patterns[tag] = ElementIdPattern(
            tag=tag,
            prefix=prefix,
            total_length=dominant_length,
        )

    return patterns


def generate_unique_id(
    old_id: str,
    blocked_ids: set[str],
    pattern: ElementIdPattern | None = None,
) -> str:
    """
    生成唯一 ID。

    若当前文件能够从同类元素推断规则，则新 ID 必须保持该类型的前缀
    和固定总位数；否则沿用 v2.4.0 的原 ID 向上递增逻辑。
    非数字 ID 使用 _1、_2……后缀。
    """
    if old_id.isdigit():
        if pattern is not None:
            # 全局模板语义：同类型当前最大合法完整 ID + 1，不补空号。
            matching = [
                int(value) for value in blocked_ids
                if isinstance(value, str) and pattern.matches(value)
            ]
            if matching:
                sequence = int(str(max(matching))[len(pattern.prefix):]) + 1
            elif pattern.matches(old_id):
                sequence = int(old_id[len(pattern.prefix):]) + 1
            else:
                sequence = 1

            while sequence <= pattern.max_sequence:
                candidate = pattern.build(sequence)
                if candidate not in blocked_ids:
                    return candidate
                sequence += 1

            raise ValueError(
                f"无法为 <{pattern.tag}> 分配新的 {pattern.total_length} 位唯一 ID："
                f"前缀 {pattern.prefix!r} 的编号空间已用尽。"
            )

        width = len(old_id)
        candidate_number = int(old_id) + 1
        while True:
            candidate = str(candidate_number).zfill(width)
            if candidate not in blocked_ids:
                return candidate
            candidate_number += 1

    counter = 1
    while True:
        candidate = f"{old_id}_{counter}"
        if candidate not in blocked_ids:
            return candidate
        counter += 1


def update_list_reference(value: str, id_map: dict[str, str]) -> str:
    """
    更新 link/node_area。

    格式通常为：0,0,30000126;1,0,100000129
    只替换每个分组中的第三项 ID，不修改前两项端点信息。
    """
    groups = value.split(";")
    updated_groups: list[str] = []

    for group in groups:
        parts = group.split(",", 2)
        if len(parts) < 3:
            updated_groups.append(group)
            continue

        original_ref = parts[2]
        stripped_ref = original_ref.strip()
        new_ref = id_map.get(stripped_ref)
        if new_ref is None:
            updated_groups.append(group)
            continue

        leading = original_ref[: len(original_ref) - len(original_ref.lstrip())]
        trailing = original_ref[len(original_ref.rstrip()) :]
        parts[2] = f"{leading}{new_ref}{trailing}"
        updated_groups.append(",".join(parts))

    return ";".join(updated_groups)


def update_single_reference(value: str, id_map: dict[str, str]) -> str:
    """更新 p_FatherObjId 这类单一 ID 引用。"""
    stripped = value.strip()
    if not stripped or stripped not in id_map:
        return value

    leading = value[: len(value) - len(value.lstrip())]
    trailing = value[len(value.rstrip()) :]
    return f"{leading}{id_map[stripped]}{trailing}"


def update_reference_attributes(
    children: Iterable[ET.Element],
    id_map: dict[str, str],
) -> None:
    """根据旧 ID → 新 ID 映射更新所有已知引用属性。"""
    if not id_map:
        return

    for element in iter_graph_elements(children):
        for attr in REFERENCE_LIST_ATTRS:
            value = element.get(attr)
            if value:
                element.set(attr, update_list_reference(value, id_map))

        for attr in REFERENCE_SINGLE_ATTRS:
            value = element.get(attr)
            if value:
                element.set(attr, update_single_reference(value, id_map))


def remap_source_identifier_namespace(
    children: Iterable[ET.Element],
    used_tokens: set[str],
    blocked_tokens: set[str],
) -> tuple[IdUpdateResult, set[str]]:
    """
    将一个后续馈线的完整 ID 命名空间安全并入最终文件。

    这里必须同时考虑两类 ID：
    1. 元素自身的 id；
    2. link/node_area/p_FatherObjId 中引用的 ID。

    第二类中可能有“虚拟拓扑节点 ID”，它们在源文件中没有同名 XML
    图元，但仍然承担多个对象之间的拓扑关联。若它们与其他馈线的元素 ID
    或虚拟 ID 重复，也必须整体重新映射，否则合并后可能错误串联。

    返回：
      - 修改统计；
      - 原本确实指向源文件内部 XML 图元的目标 ID（映射后），用于最终校验。
    """
    result = IdUpdateResult()
    direct_children = list(children)
    elements = list(iter_graph_elements(direct_children))
    patterns = apply_confirmed_id_patterns(infer_element_id_patterns(direct_children))

    element_ids = [
        element.get("id", "").strip()
        for element in elements
        if element.get("id") and element.get("id", "").strip()
    ]
    element_id_set = set(element_ids)
    reference_ids = collect_reference_ids(children)
    reference_id_set = set(reference_ids)

    result.virtual_reference_tokens = len(reference_id_set - element_id_set)

    # 同一个 token 无论出现在元素 id 还是引用中，都使用同一份映射。
    source_tokens = unique_in_order([*element_ids, *reference_ids])
    token_map: dict[str, str] = {}
    token_patterns: dict[str, ElementIdPattern] = {}
    for element in elements:
        element_id = (element.get("id") or "").strip()
        if not element_id or element_id in token_patterns:
            continue
        pattern = patterns.get(local_name(element.tag))
        if pattern is not None:
            token_patterns[element_id] = pattern

    for old_token in source_tokens:
        if old_token in used_tokens:
            new_token = generate_unique_id(
                old_token,
                blocked_tokens | used_tokens,
                token_patterns.get(old_token),
            )
        else:
            new_token = old_token

        token_map[old_token] = new_token
        used_tokens.add(new_token)
        blocked_tokens.add(new_token)

    result.changed_reference_tokens = sum(
        1
        for token in reference_id_set
        if token_map.get(token, token) != token
    )

    # 修改元素自身 ID。若源 Layer 自身已有重复元素 ID，第一处使用统一映射，
    # 后续重复元素单独生成新 ID；原始引用仍指向第一处，避免凭空猜测。
    source_seen: set[str] = set()
    for element in elements:
        old_id_raw = element.get("id")
        if old_id_raw is None or not old_id_raw.strip():
            continue

        old_id = old_id_raw.strip()
        if old_id in source_seen:
            result.source_internal_duplicates += 1
            new_id = generate_unique_id(
                old_id,
                blocked_tokens | used_tokens,
                patterns.get(local_name(element.tag)),
            )
            element.set("id", new_id)
            used_tokens.add(new_id)
            blocked_tokens.add(new_id)
            result.changed_element_ids += 1
            continue

        source_seen.add(old_id)
        new_id = token_map[old_id]
        if new_id != old_id:
            element.set("id", new_id)
            result.changed_element_ids += 1

    # 对全部 token 应用同一映射，包括没有对应 XML 图元的虚拟拓扑节点 ID。
    update_reference_attributes(children, token_map)

    # 只有源文件中本来就存在同名 XML 图元的引用，才要求最终能找到目标。
    required_target_ids = {
        token_map[ref_id]
        for ref_id in reference_id_set
        if ref_id in element_id_set
    }
    return result, required_target_ids


def normalize_base_layer_duplicate_ids(
    layer: ET.Element,
    blocked_ids: set[str],
) -> IdUpdateResult:
    """
    基准图原则上完全不修改。
    仅当基准 Layer 自身已存在重复 ID 时，为后续重复项生成唯一 ID。
    """
    result = IdUpdateResult()
    seen: set[str] = set()
    patterns = apply_confirmed_id_patterns(infer_element_id_patterns(layer))

    for element in iter_graph_elements(layer):
        old_id_raw = element.get("id")
        if old_id_raw is None or not old_id_raw.strip():
            continue
        old_id = old_id_raw.strip()

        if old_id not in seen:
            seen.add(old_id)
            continue

        result.source_internal_duplicates += 1
        new_id = generate_unique_id(
            old_id,
            blocked_ids | seen,
            patterns.get(local_name(element.tag)),
        )
        element.set("id", new_id)
        blocked_ids.add(new_id)
        seen.add(new_id)
        result.changed_element_ids += 1

    # 基准图内部重复 ID 的引用在原始文件中存在歧义，维持指向第一处 ID。
    return result


def validate_final_layer(
    layer: ET.Element,
    required_target_ids: set[str],
) -> tuple[int, int, int, int]:
    """
    校验最终 Layer。

    硬性要求：
    - 所有 XML 图元 id 唯一；
    - 原来确实指向源文件内部 XML 图元的引用，映射后仍能找到目标。

    link/node_area 中只存在于引用、没有同名 XML 元素的 ID 被视为
    “虚拟拓扑节点 ID”。这种结构在原始 .g 文件中本来就大量存在，
    因此允许保留，不再误判为错误。
    """
    ids = collect_ids(layer)
    counter = Counter(ids)
    duplicates = sorted(
        id_value for id_value, count in counter.items() if count > 1
    )
    if duplicates:
        preview = ", ".join(duplicates[:20])
        raise ValueError(f"最终 Layer 仍存在重复图元 ID：{preview}")

    id_set = set(ids)
    missing_required = sorted(required_target_ids - id_set)
    if missing_required:
        preview = ", ".join(missing_required[:30])
        raise ValueError(
            "合并后有原本指向真实图元的引用失效，目标 ID："
            f"{preview}"
        )

    reference_ids = collect_reference_ids(layer)
    virtual_reference_occurrences = [
        ref_id for ref_id in reference_ids if ref_id not in id_set
    ]
    virtual_reference_unique = set(virtual_reference_occurrences)

    return (
        len(ids),
        len(id_set),
        len(virtual_reference_unique),
        len(virtual_reference_occurrences),
    )


def parse_g_file(info: GFileInfo) -> ParsedGFile:
    """解析输入文件，检查外框并完成负坐标清理、取整和对齐基准识别。"""
    tree = parse_xml(info.path)
    root = tree.getroot()

    if local_name(root.tag) != "G":
        raise ValueError(
            f"文件 {info.path.name} 的根节点不是 G，而是 {root.tag!r}"
        )

    layer = get_only_layer(root, info.path.name)
    root_height = get_root_dimension(root, "h", "height", info.path.name)
    root_width = get_root_dimension(root, "w", "width", info.path.name)

    # 内置图框会从内存副本中安全移除后参与合并；客户或未知图框禁止参与。
    (
        frame_kind,
        frame_detection_mode,
        removed_builtin_frame_elements,
        removed_builtin_frame_ids,
        removed_builtin_frame_references,
    ) = _prepare_frame_for_merge(
        root,
        layer,
        root_width,
        root_height,
        info.path.name,
    )

    negative_cleanup = remove_negative_coordinate_elements(
        layer,
        f"{info.path.name}（原始坐标清理）",
    )
    rounded_coordinate_attributes = normalize_position_coordinates_to_integers(layer)

    alignment_y, alignment_mode = resolve_alignment_y(layer, info.path.name)
    min_x, min_y, max_x, max_y = get_position_coordinate_extents(
        layer,
        info.path.name,
    )

    return ParsedGFile(
        info=info,
        tree=tree,
        root=root,
        layer=layer,
        root_height=root_height,
        root_width=root_width,
        alignment_y=alignment_y,
        alignment_mode=alignment_mode,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        negative_cleanup=negative_cleanup,
        rounded_coordinate_attributes=rounded_coordinate_attributes,
        frame_kind=frame_kind,
        frame_detection_mode=frame_detection_mode,
        removed_builtin_frame_elements=removed_builtin_frame_elements,
        removed_builtin_frame_ids=removed_builtin_frame_ids,
        removed_builtin_frame_references=removed_builtin_frame_references,
    )


def merge_g_files(
    infos: list[GFileInfo],
    output_path: Path,
    gap: Decimal,
    left_margin: Decimal,
    top_margin: Decimal,
    right_margin: Decimal,
    bottom_margin: Decimal,
    feeder_min_width: Decimal = Decimal("1000"),
    merge_main_bus: bool = False,
    main_bus_mode: str = "single",
    main_bus_groups: list[list[str]] | None = None,
) -> None:
    parsed_files = [parse_g_file(info) for info in infos]

    main_bus_groups = [list(group) for group in (main_bus_groups or [])]
    manual_bus_elements: dict[str, list[ET.Element]] = {}
    if merge_main_bus:
        ordered_names = [info.path.name for info in infos]
        name_to_index = {name: idx for idx, name in enumerate(ordered_names)}
        seen: set[str] = set()
        for group_no, group in enumerate(main_bus_groups, 1):
            if len(group) < 2:
                raise ValueError(f"母线组 {group_no} 至少需要 2 个馈线文件。")
            if any(name not in name_to_index for name in group):
                raise ValueError(f"母线组 {group_no} 包含不在当前合并列表中的文件。")
            if any(name in seen for name in group):
                raise ValueError(f"母线组 {group_no} 中存在已经属于其他组的馈线。")
            positions = sorted(name_to_index[name] for name in group)
            if positions != list(range(positions[0], positions[-1] + 1)):
                raise ValueError(f"母线组 {group_no} 的馈线必须在当前合并顺序中连续。")
            seen.update(group)

        # 只校验人工分组内的文件能否按单/双母线模式识别有效水平 Bus。
        grouped_names = {name for group in main_bus_groups for name in group}
        for item in parsed_files:
            if item.info.path.name not in grouped_names:
                continue
            selected = _select_main_bus_candidates(item.layer, main_bus_mode, item.info.path.name)
            manual_bus_elements[item.info.path.name] = [row[0] for row in selected]

    # 当前顺序中的第一个文件完整作为输出基础。它在合并阶段不单独移动；
    # 最后会与整个合并图一起做统一的上/左边距平移。
    base = parsed_files[0]
    output_tree = base.tree
    output_root = base.root
    target_layer = base.layer
    base_alignment_y = base.alignment_y

    # 预留所有清理后输入文件的完整 ID token（元素 ID + 引用/虚拟节点 ID）。
    blocked_tokens: set[str] = set()
    for item in parsed_files:
        blocked_tokens.update(collect_identifier_tokens(item.layer))

    base_fix = normalize_base_layer_duplicate_ids(target_layer, blocked_tokens)
    base_element_ids = set(collect_ids(target_layer))
    base_reference_ids = set(collect_reference_ids(target_layer))
    used_tokens = base_element_ids | base_reference_ids

    # 只校验原本确实指向 XML 图元的引用；虚拟拓扑节点无需同名元素。
    required_target_ids: set[str] = base_element_ids & base_reference_ids

    base_min_x, base_min_y, current_max_x, current_max_y = (
        get_position_coordinate_extents(target_layer, base.info.path.name)
    )

    # 每个馈线图都有一个“占用宽度”：max(实际宽度, 默认单线图宽度)。
    # 用户设置的 gap 始终额外加在相邻占用区之间，不计入默认单线图宽度。
    base_actual_width = current_max_x - base_min_x
    base_slot_width = max(base_actual_width, feeder_min_width)
    current_slot_right = base_min_x + base_slot_width

    # 保存各输入图的占用区范围，用于最终验证“默认宽度 + 用户间隔”。
    input_ranges: list[tuple[int, Decimal, Decimal]] = [
        (base.info.order, base_min_x, current_slot_right)
    ]

    print("处理顺序（App 用户顺序；未指定时按文件名自然排序）：")
    for item in parsed_files:
        print(f"  {item.info.order}. {item.info.path.name}")

    print("\n源文件预处理：")
    for item in parsed_files:
        cleanup = item.negative_cleanup
        frame_message = (
            f"，移除内置图框直属组件 {item.removed_builtin_frame_elements} 个"
            if item.frame_kind == FRAME_BUILTIN
            else ""
        )
        print(
            f"  文件 {item.info.order}: "
            f"删除负坐标根图元 {cleanup.removed_root_elements} 个，"
            f"累计删除元素 {cleanup.removed_total_elements} 个，"
            f"清理引用分组 {cleanup.removed_reference_groups} 个，"
            f"取整坐标属性 {item.rounded_coordinate_attributes} 个"
            f"{frame_message}"
        )

    print("\n基准图：")
    print(f"  文件：{base.info.path.name}")
    print(f"  对齐基准：{base.alignment_mode}")
    print(f"  基准 Y：{format_integer(base_alignment_y)}")
    print(f"  合并阶段 X 偏移：0")
    print(f"  合并阶段 Y 偏移：0")
    print(
        "  原始清理后坐标范围："
        f"minX={format_integer(base_min_x)}，"
        f"minY={format_integer(base_min_y)}，"
        f"maxX={format_integer(current_max_x)}，"
        f"maxY={format_integer(current_max_y)}"
    )
    if base_fix.changed_element_ids:
        print(
            f"  基准 Layer 原本存在 {base_fix.source_internal_duplicates} 个重复 ID，"
            f"已修改 {base_fix.changed_element_ids} 个"
        )

    total_changed_element_ids = base_fix.changed_element_ids
    total_changed_reference_tokens = 0

    for source in parsed_files[1:]:
        # 后续文件只复制唯一 Layer 下的直接子元素。
        copied_children = [copy.deepcopy(child) for child in list(source.layer)]

        # 人工母线分组必须引用“即将写入目标 Layer 的副本”，而不是源树对象。
        if merge_main_bus and source.info.path.name in manual_bus_elements:
            pseudo_layer = ET.Element("Layer")
            pseudo_layer.extend(copied_children)
            selected_copies = _select_main_bus_candidates(pseudo_layer, main_bus_mode, source.info.path.name)
            manual_bus_elements[source.info.path.name] = [row[0] for row in selected_copies]

        id_result, source_required_targets = remap_source_identifier_namespace(
            copied_children,
            used_tokens=used_tokens,
            blocked_tokens=blocked_tokens,
        )
        required_target_ids.update(source_required_targets)
        total_changed_element_ids += id_result.changed_element_ids
        total_changed_reference_tokens += id_result.changed_reference_tokens

        source_min_x, source_min_y, source_max_x, source_max_y = (
            get_position_coordinate_extents(copied_children, source.info.path.name)
        )

        # 仅把标签名严格等于 Bus 的有效非零长度水平母线作为母线，BusDis 不参与。
        # 没有有效水平 Bus 时使用该文件所有位置坐标中的最小 Y（最高图元）。
        # 所有输入图最终都与第一张基准图的统一对齐 Y 对齐。
        offset_y = base_alignment_y - source.alignment_y

        # 水平布局按“馈线占用区”排列：每张馈线至少占 feeder_min_width；
        # 若实际宽度更大则按实际宽度。用户 gap 额外加在占用区之间。
        offset_x = current_slot_right + gap - source_min_x

        # 输入坐标、gap、母线 Y 都已整数化，因此偏移也是整数。
        shift_graph_elements(copied_children, offset_x, offset_y)

        shifted_min_x, shifted_min_y, shifted_max_x, shifted_max_y = (
            get_position_coordinate_extents(copied_children, source.info.path.name)
        )

        slot_gap = shifted_min_x - current_slot_right
        if slot_gap != gap:
            raise ValueError(
                f"输入图 {source.info.order} 占用区间隔计算失败："
                f"目标 {format_integer(gap)}，实际 {format_decimal(slot_gap)}"
            )
        actual_graph_gap = shifted_min_x - current_max_x

        for child in copied_children:
            target_layer.append(child)

        source_actual_width = shifted_max_x - shifted_min_x
        source_slot_width = max(source_actual_width, feeder_min_width)
        source_slot_right = shifted_min_x + source_slot_width
        input_ranges.append(
            (source.info.order, shifted_min_x, source_slot_right)
        )
        current_max_x = max(current_max_x, shifted_max_x)
        current_slot_right = source_slot_right
        current_max_y = max(current_max_y, shifted_max_y)

        print(f"\n输入图 {source.info.order}：")
        print(f"  文件：{source.info.path.name}")
        print(f"  本图对齐基准：{source.alignment_mode}")
        print(f"  原对齐基准 Y：{format_integer(source.alignment_y)}")
        print(f"  目标基准 Y：{format_integer(base_alignment_y)}")
        print(f"  X 偏移：{format_integer(offset_x)}")
        print(f"  Y 偏移：{format_integer(offset_y)}")
        print(f"  默认单线图宽度：{format_integer(feeder_min_width)}")
        print(f"  本图实际宽度：{format_integer(source_actual_width)}")
        print(f"  本图占用宽度：{format_integer(source_slot_width)}")
        print(f"  与前一占用区间隔：{format_integer(slot_gap)}")
        print(f"  图形实际边界间隔：{format_integer(actual_graph_gap)}")
        print(
            "  移动后坐标范围："
            f"minX={format_integer(shifted_min_x)}，"
            f"minY={format_integer(shifted_min_y)}，"
            f"maxX={format_integer(shifted_max_x)}，"
            f"maxY={format_integer(shifted_max_y)}"
        )
        print(
            "  发生冲突并修改的图元 ID 数量："
            f"{id_result.changed_element_ids}"
        )
        print(
            "  发生冲突并重新映射的引用 ID token 数量："
            f"{id_result.changed_reference_tokens}"
        )
        print(
            "  源文件虚拟拓扑节点 ID 数量："
            f"{id_result.virtual_reference_tokens}（允许无同名 XML 图元）"
        )

    if merge_main_bus:
        lane_count = 2 if main_bus_mode == "double" else 1
        total_removed = 0
        removed_bus_map: dict[str, str] = {}
        summaries: list[dict[str, object]] = []
        print("\n主母线人工分组合并：")
        if not main_bus_groups:
            print("  未设置人工母线组；所有馈线主母线保持独立。")
        for group_no, group in enumerate(main_bus_groups, 1):
            print(f"  组{group_no}：{group[0]} ～ {group[-1]}（{len(group)} 个馈线）")
            for lane in range(lane_count):
                buses = [manual_bus_elements[name][lane] for name in group]
                rows = []
                for bus in buses:
                    line = get_bus_line(bus)
                    if line is None:
                        raise ValueError(f"母线组 {group_no} 中 Bus id={bus.get('id','')} 已无法读取几何。")
                    x1, y1, x2, y2 = line
                    rows.append((bus, min(x1,x2), max(x1,x2), (y1+y2)/Decimal("2")))
                integer_ys = [int(row[3].to_integral_value()) for row in rows]
                counts = Counter(integer_ys)
                max_count = max(counts.values())
                modes = sorted(y for y,c in counts.items() if c == max_count)
                target_y = Decimal(modes[0]) if len(modes) == 1 else sorted(row[3] for row in rows)[len(rows)//2]
                changes = []
                for bus, _min_x, _max_x, current_y in rows:
                    if abs(current_y-target_y) > Decimal("0.000001"):
                        endpoints = _move_bus_to_y_with_attached_lines(target_layer, bus, target_y)
                        changes.append((bus, current_y, endpoints))
                lane_label = "上母线" if lane == 0 else "下母线"
                if changes:
                    print(f"    {lane_label}：多数/中位基准 Y={format_integer(target_y)}，自动校正 {len(changes)} 条")
                    for bus, old_y, endpoints in changes:
                        print(f"      {bus.get('id') or '(无ID)'}：Y {format_integer(old_y)} -> {format_integer(target_y)}；连接端点 {endpoints} 个")
                result = merge_explicit_bus_elements(target_layer, buses, output_path.name, f"组{group_no}", lane_label)
                total_removed += int(result.get("removed", 0))
                removed_bus_map.update(result.get("removed_id_map", {}))
                summaries.append(result)
                print(f"    {lane_label}：{len(buses)} 条 -> 1 条；保留 Bus ID={result.get('keeper_id')}；删除 {result.get('removed',0)} 条")
        if removed_bus_map:
            required_target_ids = {removed_bus_map.get(target_id, target_id) for target_id in required_target_ids}
            print(f"  共删除多余 Bus：{total_removed} 条；相关引用已改接到各人工分组保留 Bus。")
            print("  keyid 不参与分组判断；保留 Bus 继续保留其自身原有属性。")

    # 完成全部对齐和水平排列后，再统一处理上边距和左边距。
    # 整体平移不会改变对齐关系和输入图之间的间隔。
    before_min_x, before_min_y, before_max_x, before_max_y = (
        get_position_coordinate_extents(target_layer, output_path.name)
    )
    canvas_shift_x = left_margin - before_min_x
    canvas_shift_y = top_margin - before_min_y

    shift_graph_elements(
        list(target_layer),
        canvas_shift_x,
        canvas_shift_y,
    )

    final_min_x, final_min_y, final_max_x, final_max_y = (
        get_position_coordinate_extents(target_layer, output_path.name)
    )

    if final_min_x != left_margin or final_min_y != top_margin:
        raise ValueError(
            "最终上/左边距校验失败："
            f"minX={format_decimal(final_min_x)}，"
            f"目标左边距={format_integer(left_margin)}；"
            f"minY={format_decimal(final_min_y)}，"
            f"目标上边距={format_integer(top_margin)}"
        )

    # 所有输入图都增加同一个最终 Y 偏移，因此对齐基准仍保持一致。
    expected_final_alignment_y = base_alignment_y + canvas_shift_y
    final_alignment_y, final_alignment_mode = resolve_alignment_y(
        target_layer, output_path.name
    )
    if final_alignment_y != expected_final_alignment_y:
        raise ValueError(
            f"最终对齐校验失败：期望 Y={format_decimal(expected_final_alignment_y)}，"
            f"实际 Y={format_decimal(final_alignment_y)}"
        )

    # 最后处理右边框和下边框。
    final_width = final_max_x + right_margin
    final_height = final_max_y + bottom_margin

    output_root.set("w", format_integer(final_width))
    output_root.set("width", format_integer(final_width))
    output_root.set("h", format_integer(final_height))
    output_root.set("height", format_integer(final_height))

    actual_left_margin = final_min_x
    actual_top_margin = final_min_y
    actual_right_margin = final_width - final_max_x
    actual_bottom_margin = final_height - final_max_y

    # 校验最终全部位置坐标均为整数且不存在负数。
    final_rounded_changes = normalize_position_coordinates_to_integers(
        target_layer
    )
    if final_rounded_changes != 0:
        raise ValueError(
            "最终文件仍出现非整数位置坐标，已拒绝输出；"
            f"检测到 {final_rounded_changes} 个需要再次取整的属性"
        )

    for element in iter_graph_elements(target_layer):
        if element_has_negative_coordinate(element, output_path.name):
            raise ValueError(
                f"最终 Layer 中仍存在负坐标图元："
                f"<{local_name(element.tag)}> id={element.get('id', '')!r}"
            )

    # 最终重新验证每两个相邻馈线“占用区”的用户间隔。全图统一平移不影响间隔。
    for index in range(1, len(input_ranges)):
        previous_order, _previous_min, previous_max = input_ranges[index - 1]
        current_order, current_min, _current_max = input_ranges[index]
        measured_gap = current_min - previous_max
        if measured_gap != gap:
            raise ValueError(
                f"输入图 {previous_order} 与 {current_order} 的占用区间隔不是 "
                f"{format_integer(gap)}，实际为 {format_decimal(measured_gap)}"
            )

    (
        final_id_count,
        final_unique_count,
        virtual_reference_unique_count,
        virtual_reference_occurrence_count,
    ) = validate_final_layer(target_layer, required_target_ids)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(ET, "indent"):
        ET.indent(output_tree, space="    ")

    output_tree.write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )

    # 写出后重新解析，确保 XML 合法。
    parse_xml(output_path)

    print("\n最终结果：")
    print(f"  最终 Layer 图元 ID 数量：{final_id_count}")
    print(f"  最终唯一 ID 数量：{final_unique_count}")
    print(f"  总计重新编号图元 ID：{total_changed_element_ids}")
    print(
        "  总计重新映射引用 ID token："
        f"{total_changed_reference_tokens}"
    )
    print(
        "  最终虚拟拓扑节点 ID："
        f"{virtual_reference_unique_count} 个唯一值，"
        f"{virtual_reference_occurrence_count} 次引用（允许）"
    )
    print(
        "  全图最终统一平移："
        f"X={format_integer(canvas_shift_x)}，"
        f"Y={format_integer(canvas_shift_y)}"
    )
    print(
        "  最终内容坐标范围："
        f"minX={format_integer(final_min_x)}，"
        f"minY={format_integer(final_min_y)}，"
        f"maxX={format_integer(final_max_x)}，"
        f"maxY={format_integer(final_max_y)}"
    )
    print(
        "  最终实际边距："
        f"左={format_integer(actual_left_margin)}，"
        f"上={format_integer(actual_top_margin)}，"
        f"右={format_integer(actual_right_margin)}，"
        f"下={format_integer(actual_bottom_margin)}"
    )
    print(f"  最终对齐基准：{final_alignment_mode}")
    print(f"  最终对齐基准 Y：{format_integer(final_alignment_y)}")
    print(f"  默认单线图宽度：{format_integer(feeder_min_width)}")
    print(f"  相邻馈线用户间隔：{format_integer(gap)}")
    print(f"  人工分组合并主母线：{'是' if merge_main_bus else '否'}")
    if merge_main_bus:
        print(f"  主母线类型：{'双母线' if main_bus_mode == 'double' else '单母线'}")
    print(f"  G.w / G.width：{format_integer(final_width)}")
    print(f"  G.h / G.height：{format_integer(final_height)}")
    print(f"  输出文件：{output_path.resolve()}")

def build_default_output_path(output_dir: Path, infos: list[GFileInfo]) -> Path:
    """文件名无法推断站点时，使用稳定的默认输出名称。"""
    return output_dir / "MERGED.sln.pic.g"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            f"读取脚本同级 {INPUT_FOLDER_NAME} 目录中以 .sln.pic.g 结尾的文件，"
            f"按指定顺序合并单 Layer，并将结果输出到同级 {OUTPUT_FOLDER_NAME}。"
            "馈线间隔和四边距请直接修改脚本开头的用户配置常量。"
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            "可选的输出文件名，例如 MERGED.sln.pic.g；"
            f"无论是否指定，都输出到脚本同级的 {OUTPUT_FOLDER_NAME} 目录"
        ),
    )
    return parser.parse_args()


def require_nonnegative_integer(value: Decimal, option_name: str) -> Decimal:
    if value < 0:
        raise ValueError(f"{option_name} 不能小于 0")
    if value != value.to_integral_value():
        raise ValueError(f"{option_name} 必须是整数，当前值：{format_decimal(value)}")
    return value


def main() -> int:
    args = parse_args()

    try:
        # 输入、输出目录都固定在脚本文件所在目录下，
        # 因此从任意 PowerShell/CMD 路径启动脚本都能找到正确目录。
        script_dir = Path(__file__).resolve().parent
        input_dir = script_dir / INPUT_FOLDER_NAME
        output_dir = script_dir / OUTPUT_FOLDER_NAME

        if not input_dir.is_dir():
            raise NotADirectoryError(
                f"输入目录不存在：{input_dir}\n"
                f"请在脚本同级目录创建 {INPUT_FOLDER_NAME}，并放入待处理的 .g 文件。"
            )

        # 输出目录不存在时自动创建。
        output_dir.mkdir(parents=True, exist_ok=True)

        # 从脚本开头的用户配置区域读取数值。
        gap = require_nonnegative_integer(
            parse_decimal(str(FEEDER_GAP), "FEEDER_GAP"),
            "FEEDER_GAP",
        )
        feeder_min_width = require_nonnegative_integer(
            parse_decimal(str(FEEDER_MIN_WIDTH), "FEEDER_MIN_WIDTH"),
            "FEEDER_MIN_WIDTH",
        )
        left_margin = require_nonnegative_integer(
            parse_decimal(str(LEFT_MARGIN), "LEFT_MARGIN"),
            "LEFT_MARGIN",
        )
        top_margin = require_nonnegative_integer(
            parse_decimal(str(TOP_MARGIN), "TOP_MARGIN"),
            "TOP_MARGIN",
        )
        right_margin = require_nonnegative_integer(
            parse_decimal(str(RIGHT_MARGIN), "RIGHT_MARGIN"),
            "RIGHT_MARGIN",
        )
        bottom_margin = require_nonnegative_integer(
            parse_decimal(str(BOTTOM_MARGIN), "BOTTOM_MARGIN"),
            "BOTTOM_MARGIN",
        )

        print("当前用户配置：")
        print(f"  默认单线图宽度：{format_integer(feeder_min_width)}")
        print(f"  相邻馈线间隔：{format_integer(gap)}")
        print(
            "  最终画布边距："
            f"左={format_integer(left_margin)}，"
            f"上={format_integer(top_margin)}，"
            f"右={format_integer(right_margin)}，"
            f"下={format_integer(bottom_margin)}"
        )
        print(f"  输入目录：{input_dir}")
        print(f"  输出目录：{output_dir}")

        # 固定只读取输入目录下所有以 .g 结尾的文件。
        # 目录中的 .py、.txt、.xml 等其他文件不会参与处理。
        infos = discover_files(input_dir, INPUT_FILE_PATTERN)

        if args.output:
            output_name = Path(args.output).name
            if not output_name.lower().endswith(".g"):
                output_name += ".g"
            output_path = output_dir / output_name
        else:
            output_path = build_default_output_path(output_dir, infos)

        merge_g_files(
            infos=infos,
            output_path=output_path,
            gap=gap,
            feeder_min_width=feeder_min_width,
            left_margin=left_margin,
            top_margin=top_margin,
            right_margin=right_margin,
            bottom_margin=bottom_margin,
        )
        return 0

    except Exception as exc:
        print(f"\n错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
