from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from g_file_studio.engines.id_engine import (
    _longest_zero_run_start, collect_reference_tokens, direct_layer_elements,
    infer_element_id_patterns, inspect_tree_ids, local_name,
)
from g_file_studio.services.id_rule_service import IdRule


@dataclass(frozen=True)
class ObservedIdFormat:
    tag: str
    sample_count: int
    sample_ids: tuple[str, ...]
    prefix: str | None = None
    total_length: int | None = None  # 兼容旧接口，仅用于候选提示


@dataclass
class IdRuleScanResult:
    file_path: Path
    observed: dict[str, ObservedIdFormat] = field(default_factory=dict)
    new_rule_candidates: list[ObservedIdFormat] = field(default_factory=list)
    changed_formats: list[ObservedIdFormat] = field(default_factory=list)
    unknown_uninferable: list[ObservedIdFormat] = field(default_factory=list)
    matched_tags: list[str] = field(default_factory=list)
    type_max_ids: dict[str, str] = field(default_factory=dict)


@dataclass
class StrictIdRepairResult:
    changed_element_ids: int = 0
    changes: list[tuple[str, str, str]] = field(default_factory=list)
    final_duplicate_count: int = 0


@dataclass
class ServerIdRuleSyncResult:
    """从服务器 G 文件样本同步 ID 规则的结果。"""

    rules: dict[str, IdRule]
    candidates: dict[str, "ServerIdRuleCandidate"] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    file_count: int = 0
    element_count: int = 0


@dataclass
class ServerIdRuleCandidate:
    """一个元素类型在所选样本中的主流规则及其统计证据。"""

    tag: str
    prefix: str
    total_length: int
    count: int
    total_ids: int
    file_count: int
    other_formats: dict[str, int] = field(default_factory=dict)
    sample_ids: tuple[str, ...] = ()


def candidate_review_policy(
    candidate: ServerIdRuleCandidate,
    current: IdRule | None,
) -> tuple[bool, str]:
    """Return default selection and comparison text for scan confirmation.

    Equivalent existing rules remain visible but default to unchecked. New rules
    and changed prefix/length candidates default to checked so the user can
    explicitly confirm them.
    """
    if current is None:
        return True, "新增规则：当前本机尚未建立，建议确认后加入"
    if current.prefix == candidate.prefix and current.total_length == candidate.total_length:
        return False, "已有一致：与当前规则相同，默认不重复加入"
    return (
        True,
        "⚠ 与当前规则不一致，请确认："
        f"当前 {current.prefix} + {current.total_length} 位 → "
        f"扫描 {candidate.prefix} + {candidate.total_length} 位",
    )


def _observed_by_tag(tree: ET.ElementTree) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for element in direct_layer_elements(tree.getroot()):
        value = (element.get("id") or "").strip()
        if value:
            grouped[local_name(element.tag)].append(value)
    return grouped


def _suggest_prefix(values: list[str]) -> str | None:
    """只给未知类型一个保守候选；最终必须由用户确认。

    固定前缀不能仅靠一组连续 ID 精确推断，因此候选最多取共同前缀，
    若共同前缀过长则不自动推断，避免把流水部分误当类型前缀。
    """
    digits = [v for v in values if v.isdigit()]
    if len(digits) < 2:
        return None
    common = digits[0]
    for value in digits[1:]:
        i = 0
        limit = min(len(common), len(value))
        while i < limit and common[i] == value[i]:
            i += 1
        common = common[:i]
        if not common:
            return None
    # 连续流水很容易形成很长共同前缀，超过 3 位时不自动猜。
    return common if 1 <= len(common) <= 3 else None


def scan_tree_against_rules(tree: ET.ElementTree, file_path: Path, rules: dict[str, IdRule]) -> IdRuleScanResult:
    grouped = _observed_by_tag(tree)
    inferred = infer_element_id_patterns(direct_layer_elements(tree.getroot()))
    result = IdRuleScanResult(file_path=file_path)

    for tag, values in sorted(grouped.items()):
        unique_values = list(dict.fromkeys(values))
        rule = rules.get(tag)
        pattern = inferred.get(tag)
        suggestion = pattern.prefix if pattern is not None else _suggest_prefix(unique_values)
        observed = ObservedIdFormat(
            tag=tag, sample_count=len(values), sample_ids=tuple(unique_values[:8]),
            prefix=suggestion, total_length=pattern.total_length if pattern is not None else None,
        )
        result.observed[tag] = observed
        if rule is None:
            if suggestion is None:
                result.unknown_uninferable.append(observed)
            else:
                result.new_rule_candidates.append(observed)
            continue

        valid = [value for value in values if rule.matches(value)]
        invalid = [value for value in values if not rule.matches(value)]
        if valid:
            result.type_max_ids[tag] = str(max(int(value) for value in valid))
        if invalid:
            result.changed_formats.append(ObservedIdFormat(
                tag=tag, sample_count=len(invalid),
                sample_ids=tuple(dict.fromkeys(invalid)), prefix=suggestion,
                total_length=pattern.total_length if pattern is not None else None,
            ))
        else:
            result.matched_tags.append(tag)
    return result


def scan_file_against_rules(file_path: Path, rules: dict[str, IdRule]) -> IdRuleScanResult:
    try:
        tree = ET.parse(file_path)
    except ET.ParseError as exc:
        raise ValueError(f"XML 解析失败：{file_path.name}：{exc}") from exc
    return scan_tree_against_rules(tree, file_path, rules)


def infer_server_id_rules(
    file_paths: list[Path],
    existing_rules: dict[str, IdRule],
    progress: Callable[[int], None] | None = None,
) -> ServerIdRuleSyncResult:
    """从用户选中的 G 文件样本推断候选 ID 规则。

    这里跨所选文件聚合同一 XML 元素类型后再推断，避免单个文件样本过少。
    结果只是候选，必须经过用户逐类确认后才能加入规则；无法稳定推断的类型
    不会自动创建规则。
    """
    all_elements: list[ET.Element] = []
    observed_by_tag: dict[str, list[str]] = defaultdict(list)
    files_by_tag: dict[str, set[str]] = defaultdict(set)
    parsed_files = 0
    for file_path in file_paths:
        try:
            tree = ET.parse(file_path)
        except ET.ParseError as exc:
            raise ValueError(f"XML 解析失败：{Path(file_path).name}：{exc}") from exc
        elements = direct_layer_elements(tree.getroot())
        parsed_files += 1
        all_elements.extend(elements)
        for element in elements:
            value = (element.get("id") or "").strip()
            if value:
                tag = local_name(element.tag)
                observed_by_tag[tag].append(value)
                files_by_tag[tag].add(Path(file_path).name)
        if progress:
            progress(round(parsed_files * 100 / max(len(file_paths), 1)))

    patterns = infer_element_id_patterns(all_elements)
    rules = dict(existing_rules)
    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    unresolved: list[str] = []
    candidates: dict[str, ServerIdRuleCandidate] = {}

    for tag in sorted(observed_by_tag):
        pattern = patterns.get(tag)
        if pattern is None:
            unresolved.append(tag)
            continue
        values = observed_by_tag[tag]
        candidate_rule = IdRule(tag, pattern.prefix, pattern.total_length)
        matching = [value for value in values if candidate_rule.matches(value)]
        other_formats: dict[str, int] = defaultdict(int)
        for value in values:
            if candidate_rule.matches(value):
                continue
            start = _longest_zero_run_start(value) if value.isdigit() else None
            hint = f"{value[:start]}+{len(value)}位" if start is not None else f"未知前缀+{len(value)}位"
            other_formats[hint] += 1
        candidates[tag] = ServerIdRuleCandidate(
            tag=tag,
            prefix=pattern.prefix,
            total_length=pattern.total_length,
            count=len(matching),
            total_ids=len(values),
            file_count=len(files_by_tag[tag]),
            other_formats=dict(sorted(other_formats.items(), key=lambda item: (-item[1], item[0]))),
            sample_ids=tuple(dict.fromkeys(values[:8])),
        )
        candidate = IdRule(
            tag=tag,
            prefix=pattern.prefix,
            total_length=pattern.total_length,
            enabled=True,
            verified=True,
            note="选中 G 文件样本统计候选；须经用户确认后加入规则",
        )
        previous = rules.get(tag)
        if previous is None:
            added.append(tag)
        elif previous.prefix == candidate.prefix and previous.total_length == candidate.total_length:
            unchanged.append(tag)
        else:
            updated.append(tag)
        rules[tag] = candidate

    return ServerIdRuleSyncResult(
        rules=rules,
        candidates=candidates,
        added=added,
        updated=updated,
        unchanged=unchanged,
        unresolved=unresolved,
        file_count=parsed_files,
        element_count=len(all_elements),
    )


def _next_id_for_rule(tag: str, rule: IdRule, elements: list[ET.Element], blocked: set[str]) -> str:
    """同类型取当前最大完整 ID + 1；不补空号、不共享跨类型流水。"""
    valid_ids: list[int] = []
    for element in elements:
        if local_name(element.tag) != tag:
            continue
        value = (element.get("id") or "").strip()
        if rule.matches(value):
            valid_ids.append(int(value))
    candidate = rule.build_after(max(valid_ids) if valid_ids else None)
    while candidate in blocked:
        candidate = rule.build_after(candidate)
    return candidate



@dataclass
class StrictIdNormalizeResult:
    changed_element_ids: int = 0
    format_fixed_count: int = 0
    duplicate_fixed_count: int = 0
    changes: list[tuple[str, str, str, str]] = field(default_factory=list)
    final_duplicate_count: int = 0


def _replace_reference_token(value: str, mapping: dict[str, str]) -> str:
    groups = []
    for group in value.split(";"):
        parts = group.split(",", 2)
        if len(parts) >= 3:
            token = parts[2].strip()
            if token in mapping:
                parts[2] = mapping[token]
                group = ",".join(parts)
        groups.append(group)
    return ";".join(groups)


def normalize_tree_ids_strict(tree: ET.ElementTree, file_path: Path, rules: dict[str, IdRule], *, repair_invalid_formats: bool = True) -> StrictIdNormalizeResult:
    """强制把已配置类型的元素 ID 规范到用户确认模板。

    - 格式不符合模板：分配同类型当前最大合法完整 ID + 1；
    - 重复 ID：保留第一处，后续重复元素重新分配；
    - 唯一旧 ID 被改写时，同步更新 link/node_area/p_FatherObjId 引用；
    - 未配置模板的类型不擅自生成新 ID；若其自身发生重复则报错。
    """
    elements = direct_layer_elements(tree.getroot())
    original_counts: dict[str, int] = defaultdict(int)
    for element in elements:
        value = (element.get("id") or "").strip()
        if value:
            original_counts[value] += 1

    blocked = {value for element in elements if (value := (element.get("id") or "").strip())}
    for layer in [child for child in list(tree.getroot()) if local_name(child.tag) == "Layer"]:
        blocked.update(collect_reference_tokens(layer))

    # 每种类型从“当前合法最大 ID”向后分配；本次分配后持续更新。
    next_seed: dict[str, str | None] = {}
    for tag, rule in rules.items():
        vals = [
            (element.get("id") or "").strip()
            for element in elements
            if local_name(element.tag) == tag and rule.matches((element.get("id") or "").strip())
        ]
        next_seed[tag] = str(max(map(int, vals))) if vals else None

    result = StrictIdNormalizeResult()
    seen: set[str] = set()
    unique_mapping: dict[str, str] = {}

    def allocate(tag: str, rule: IdRule) -> str:
        seed = next_seed.get(tag)
        candidate = rule.build_after(seed)
        while candidate in blocked or candidate in seen:
            candidate = rule.build_after(candidate)
        next_seed[tag] = candidate
        blocked.add(candidate)
        return candidate

    for element in elements:
        old_id = (element.get("id") or "").strip()
        if not old_id:
            continue
        tag = local_name(element.tag)
        rule = rules.get(tag)
        duplicate = old_id in seen
        invalid = repair_invalid_formats and rule is not None and rule.enabled and rule.verified and not rule.matches(old_id)

        if duplicate and (rule is None or not rule.enabled or not rule.verified):
            raise ValueError(
                f"发现重复 ID {old_id}，元素 <{tag}> 没有已启用且已确认的 ID 模板；"
                "请先在‘ID 检查与修复’模块中确认规则。"
            )
        if not duplicate and not invalid:
            seen.add(old_id)
            continue
        if rule is None or not rule.enabled or not rule.verified:
            # 未知类型的唯一 ID 不擅自修改。
            seen.add(old_id)
            continue

        new_id = allocate(tag, rule)
        element.set("id", new_id)
        seen.add(new_id)
        result.changed_element_ids += 1
        reason = "重复" if duplicate else "格式"
        if duplicate:
            result.duplicate_fixed_count += 1
        if invalid:
            result.format_fixed_count += 1
        result.changes.append((tag, old_id, new_id, reason))
        # 只有原 ID 在输入中唯一时，引用目标才是无歧义的，可以安全全量替换。
        if original_counts.get(old_id, 0) == 1:
            unique_mapping[old_id] = new_id

    if unique_mapping:
        for layer in [child for child in list(tree.getroot()) if local_name(child.tag) == "Layer"]:
            for node in [layer, *list(layer.iter())]:
                for attr in ("link", "node_area"):
                    value = node.get(attr)
                    if value:
                        node.set(attr, _replace_reference_token(value, unique_mapping))
                value = (node.get("p_FatherObjId") or "").strip()
                if value in unique_mapping:
                    node.set("p_FatherObjId", unique_mapping[value])

    after = inspect_tree_ids(tree, file_path)
    result.final_duplicate_count = len(after.duplicate_groups)
    return result

def repair_tree_duplicates_strict(tree: ET.ElementTree, file_path: Path, rules: dict[str, IdRule]) -> StrictIdRepairResult:
    """严格按已确认前缀模板修复重复 ID；未知/异常类型禁止生成新 ID。"""
    before = inspect_tree_ids(tree, file_path)
    elements = direct_layer_elements(tree.getroot())
    blocked = {value for element in elements if (value := (element.get("id") or "").strip())}
    for layer in [child for child in list(tree.getroot()) if local_name(child.tag) == "Layer"]:
        blocked.update(collect_reference_tokens(layer))

    seen: set[str] = set()
    result = StrictIdRepairResult()
    for element in elements:
        old_id = (element.get("id") or "").strip()
        if not old_id:
            continue
        if old_id not in seen:
            seen.add(old_id)
            continue
        tag = local_name(element.tag)
        rule = rules.get(tag)
        if rule is None or not rule.enabled or not rule.verified:
            raise ValueError(
                f"发现重复 ID {old_id}，元素 <{tag}> 没有已启用且已确认的 ID 模板；"
                "请先在‘ID 规则模板’模块中确认规则。"
            )
        new_id = _next_id_for_rule(tag, rule, elements, blocked | seen)
        element.set("id", new_id)
        blocked.add(new_id)
        seen.add(new_id)
        result.changed_element_ids += 1
        result.changes.append((tag, old_id, new_id))

    after = inspect_tree_ids(tree, file_path)
    result.final_duplicate_count = len(after.duplicate_groups)
    return result
