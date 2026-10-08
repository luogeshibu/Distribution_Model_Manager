from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

REFERENCE_LIST_ATTRIBUTES = ("link", "node_area")
REFERENCE_SINGLE_ATTRIBUTES = ("p_FatherObjId",)


def local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def unique_in_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


@dataclass(frozen=True)
class ElementIdPattern:
    """同类元素主流 ID 格式：前缀 + 固定宽度顺序号。"""

    tag: str
    prefix: str
    total_length: int

    @property
    def sequence_width(self) -> int:
        return self.total_length - len(self.prefix)

    @property
    def max_sequence(self) -> int:
        return 10**self.sequence_width - 1

    def matches(self, value: str) -> bool:
        return (
            value.isdigit()
            and len(value) == self.total_length
            and value.startswith(self.prefix)
        )

    def build(self, sequence: int) -> str:
        if self.sequence_width <= 0:
            raise ValueError(f"<{self.tag}> 的 ID 前缀长度不能大于或等于总位数。")
        if sequence < 0 or sequence > self.max_sequence:
            raise ValueError(
                f"<{self.tag}> 的 {self.total_length} 位 ID 空间已用尽："
                f"前缀 {self.prefix!r}，最大顺序号 {self.max_sequence}。"
            )
        return f"{self.prefix}{sequence:0{self.sequence_width}d}"


@dataclass(frozen=True)
class DuplicateIdGroup:
    value: str
    count: int
    tags: tuple[str, ...]


@dataclass
class IdInspectionResult:
    file_path: Path
    direct_element_count: int = 0
    element_with_id_count: int = 0
    unique_id_count: int = 0
    duplicate_groups: list[DuplicateIdGroup] = field(default_factory=list)
    duplicate_element_count: int = 0
    layer_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def has_duplicates(self) -> bool:
        return bool(self.duplicate_groups)


@dataclass
class IdRepairResult:
    inspection_before: IdInspectionResult
    output_path: Path | None = None
    changed_element_ids: int = 0
    final_duplicate_count: int = 0
    changes: list[tuple[str, str, str]] = field(default_factory=list)
    pattern_sources: dict[str, ElementIdPattern] = field(default_factory=dict)


def direct_layers(root: ET.Element) -> list[ET.Element]:
    return [child for child in list(root) if local_name(child.tag) == "Layer"]


def direct_layer_elements(root: ET.Element) -> list[ET.Element]:
    return [element for layer in direct_layers(root) for element in list(layer)]


def _longest_zero_run_start(value: str) -> int | None:
    best_start: int | None = None
    best_length = 0
    index = 1
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


def infer_element_id_patterns(elements: Iterable[ET.Element]) -> dict[str, ElementIdPattern]:
    """从给定元素本身的 ID 中按标签推断主流格式，不递归进入子元素。"""
    grouped: dict[str, list[str]] = {}
    for element in elements:
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
    pattern: ElementIdPattern | None,
) -> str:
    """优先按同类主流格式分配；无法推断时沿用原 ID 递增规则。"""
    if old_id.isdigit():
        if pattern is not None:
            if pattern.matches(old_id):
                sequence = int(old_id[len(pattern.prefix) :]) + 1
            else:
                # 短 ID 或其他异常格式尽量保留其数值含义。
                sequence = int(old_id[-pattern.sequence_width :])

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
        number = int(old_id) + 1
        while True:
            candidate = str(number).zfill(width)
            if candidate not in blocked_ids:
                return candidate
            number += 1

    counter = 1
    while True:
        candidate = f"{old_id}_{counter}"
        if candidate not in blocked_ids:
            return candidate
        counter += 1


def _iter_layer_nodes(layer: ET.Element) -> Iterator[ET.Element]:
    for child in list(layer):
        yield child
        yield from child.iterfind(".//*")


def collect_reference_tokens(layer: ET.Element) -> set[str]:
    tokens: set[str] = set()
    for element in _iter_layer_nodes(layer):
        for attribute in REFERENCE_LIST_ATTRIBUTES:
            value = element.get(attribute)
            if not value:
                continue
            for group in value.split(";"):
                parts = group.split(",", 2)
                if len(parts) >= 3:
                    token = parts[2].strip()
                    if token:
                        tokens.add(token)
        for attribute in REFERENCE_SINGLE_ATTRIBUTES:
            token = (element.get(attribute) or "").strip()
            if token:
                tokens.add(token)
    return tokens


def inspect_tree_ids(tree: ET.ElementTree, file_path: Path) -> IdInspectionResult:
    root = tree.getroot()
    layers = direct_layers(root)
    if not layers:
        raise ValueError(f"文件 {file_path.name} 的 G 根节点下没有直属 Layer。")

    elements = [element for layer in layers for element in list(layer)]
    ids = [
        value
        for element in elements
        if (value := (element.get("id") or "").strip())
    ]
    counter = Counter(ids)
    tags_by_id: dict[str, list[str]] = {}
    for element in elements:
        value = (element.get("id") or "").strip()
        if value:
            tags_by_id.setdefault(value, []).append(local_name(element.tag))

    groups = [
        DuplicateIdGroup(
            value=value,
            count=count,
            tags=tuple(tags_by_id.get(value, [])),
        )
        for value, count in sorted(counter.items())
        if count > 1
    ]
    return IdInspectionResult(
        file_path=file_path,
        direct_element_count=len(elements),
        element_with_id_count=len(ids),
        unique_id_count=len(counter),
        duplicate_groups=groups,
        duplicate_element_count=sum(group.count - 1 for group in groups),
        layer_count=len(layers),
    )


def inspect_file_ids(file_path: Path) -> IdInspectionResult:
    try:
        tree = ET.parse(file_path)
    except ET.ParseError as exc:
        raise ValueError(f"XML 解析失败：{file_path.name}：{exc}") from exc
    return inspect_tree_ids(tree, file_path)


def repair_tree_duplicate_ids(
    tree: ET.ElementTree,
    file_path: Path,
) -> IdRepairResult:
    """只修复单个 G 文件内部直属 Layer 图元的重复 ID。"""
    before = inspect_tree_ids(tree, file_path)
    root = tree.getroot()
    layers = direct_layers(root)
    all_direct_elements = [element for layer in layers for element in list(layer)]
    patterns = infer_element_id_patterns(all_direct_elements)

    blocked: set[str] = {
        value
        for element in all_direct_elements
        if (value := (element.get("id") or "").strip())
    }
    for layer in layers:
        blocked.update(collect_reference_tokens(layer))

    seen: set[str] = set()
    changes: list[tuple[str, str, str]] = []
    changed = 0
    for element in all_direct_elements:
        old_id = (element.get("id") or "").strip()
        if not old_id:
            continue
        if old_id not in seen:
            seen.add(old_id)
            continue

        tag = local_name(element.tag)
        new_id = generate_unique_id(old_id, blocked | seen, patterns.get(tag))
        element.set("id", new_id)
        blocked.add(new_id)
        seen.add(new_id)
        changed += 1
        changes.append((tag, old_id, new_id))

    after = inspect_tree_ids(tree, file_path)
    return IdRepairResult(
        inspection_before=before,
        changed_element_ids=changed,
        final_duplicate_count=len(after.duplicate_groups),
        changes=changes,
        pattern_sources=patterns,
    )


def repair_file_duplicate_ids(input_path: Path, output_path: Path) -> IdRepairResult:
    try:
        tree = ET.parse(input_path)
    except ET.ParseError as exc:
        raise ValueError(f"XML 解析失败：{input_path.name}：{exc}") from exc

    result = repair_tree_duplicate_ids(tree, input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    temporary = output_path.with_name(output_path.name + ".tmp")
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    ET.parse(temporary)
    temporary.replace(output_path)
    result.output_path = output_path
    return result
