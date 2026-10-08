from __future__ import annotations

"""Report-only internationalization.

This module deliberately does not participate in business decisions. It only chooses
how already-computed report values are rendered, based on the same saved language
setting used by the UI.
"""

import re

from g_file_studio.services.user_settings_service import UserSettingsService

LANG_EN = "en_US"


def report_language() -> str:
    try:
        return UserSettingsService().get_value("general/language", "zh_CN").strip() or "zh_CN"
    except Exception:
        return "zh_CN"


def report_is_english() -> bool:
    return report_language() == LANG_EN


_EXACT = {
    "高": "High",
    "中": "Medium",
    "低": "Low",
    "待确认": "Pending Confirmation",
    "未识别": "Unrecognized",
    "正常": "Normal",
    "已修复": "Repaired",
    "未配置模板": "Template Not Configured",
    "格式不符": "Format Mismatch",
    "重复 ID": "Duplicate ID",
    "处理失败": "Processing Failed",
    "已删除": "Deleted",
    "未处理": "Not Processed",
    "无": "None",
    "重复": "Duplicate",
    "格式": "Format",
    "完全一致": "Fully Matched",
    "柜型不一致": "Cabinet Type Mismatch",
    "智能属性不一致": "Smart Attribute Mismatch",
    "图形缺失": "Missing in Graphic",
    "台账缺失": "Missing in Ledger",
    "台账名称重复": "Duplicate Ledger Name",
    "图形名称重复": "Duplicate Graphic Name",
    "图形柜名未识别": "Graphic RMU Name Unrecognized",
    "指定方向内存在多个柜名候选，按绿色优先选择": "Multiple RMU-name candidates exist in the selected direction; the green text was preferred.",
    "指定方向内存在多个柜名候选且无绿色名称，按最近位置选择": "Multiple RMU-name candidates exist in the selected direction and none is green; the nearest text was selected.",
    "柜内 Y 标签不是从 Y1 开始连续递增": "Y labels inside the cabinet are not consecutive starting from Y1.",
    "柜内 Q 标签不是从 Q1 开始连续递增": "Q labels inside the cabinet are not consecutive starting from Q1.",
    "Y 标签序号不连续": "Y label numbering is not consecutive",
    "Q 标签序号不连续": "Q label numbering is not consecutive",
    "柜型交叉校验失败": "Cabinet type cross-check failed",
    "Y/Q 文字和 devref 均无法识别柜型": "Neither Y/Q text nor devref can determine the cabinet type.",
    "尚未加入模板，且样本不足以可靠推断格式": "The element type is not yet in the template and the samples are insufficient to infer the format reliably.",
    "不符合当前模板": "Does not match the current template",
    "执行修复时将严格按当前模板强制更新这些 ID。": "During repair, these IDs will be force-updated according to the current template.",
    "全局强制约束已关闭：这些已有格式不符 ID 将保留不变。": "Global strict enforcement is disabled: existing IDs with format mismatches will remain unchanged.",
    "未发现模板格式异常或重复 ID": "No template-format issues or duplicate IDs were found.",
    "尚未加入模板": "Not yet in the template",
    "组合": "Group",
    "取消组合": "Ungroup",
}

_REPLACEMENTS = (
    ("，两种识别结果一致", ", and both recognition methods agree"),
    (" 与 ", " differs from "),
    (" 不一致", ""),
    ("；", "; "),
    ("，", ", "),
)


def report_text(value: object) -> str:
    """Translate a computed report display value without changing the source value."""
    text = "" if value is None else str(value)
    if not report_is_english() or not text:
        return text
    exact = _EXACT.get(text)
    if exact is not None:
        return exact

    patterns: list[tuple[str, str]] = [
        (r"^未识别到 Y 名称，L 使用 devref 图元文件名回退计数 (\d+)$", r"Y names were not recognized; L count falls back to devref symbol filenames: \1"),
        (r"^未识别到 Q 名称，T 使用 devref 图元文件名回退计数 (\d+)$", r"Q names were not recognized; T count falls back to devref symbol filenames: \1"),
        (r"^Y/Q=(.+)，devref=(.+)，两种识别结果一致$", r"Y/Q=\1, devref=\2; both recognition methods agree"),
        (r"^Y/Q=(.+) 与 devref=(.+) 不一致$", r"Y/Q=\1 differs from devref=\2"),
        (r"^仅识别到 Y/Q 文字类型 (.+)，devref 信息不足，无法双源交叉校验$", r"Only Y/Q text type \1 was recognized; devref information is insufficient for a two-source cross-check."),
        (r"^仅识别到 devref 类型 (.+)，Y/Q 文字不足，使用 devref 回退$", r"Only devref type \1 was recognized; Y/Q text is insufficient, so devref fallback is used."),
        (r"^已交叉校验 ([LT](?:/[LT])?) 类计数一致$", r"Cross-checked \1 category count(s): consistent"),
        (r"^Y 缺失，L 使用 devref 回退 (\d+)L$", r"Y is missing; L falls back to devref: \1L"),
        (r"^Q 缺失，T 使用 devref 回退 (\d+)T$", r"Q is missing; T falls back to devref: \1T"),
        (r"^Y=(\d+)L 缺少对应 devref L 证据$", r"Y=\1L has no corresponding devref L evidence"),
        (r"^Q=(\d+)T 缺少对应 devref T 证据$", r"Q=\1T has no corresponding devref T evidence"),
        (r"^Y=(\d+)L 与 devref L=(\d+)L 不一致$", r"Y=\1L differs from devref L=\2L"),
        (r"^Q=(\d+)T 与 devref T=(\d+)T 不一致$", r"Q=\1T differs from devref T=\2T"),
        (r"^rect ID (.+) 未找到指定方向且距离足够近的柜名。$", r"rect ID \1: no RMU name was found in the selected direction within the allowed distance."),
        (r"^尚未加入模板；候选前缀 (.+)（需人工确认）$", r"Not yet in the template; candidate prefix \1 (manual confirmation required)."),
        (r"^模板要求前缀 (.+)、总位数 (\d+)(.*)$", r"Template requires prefix \1 and total length \2\3"),
        (r"^出现 (\d+) 次$", r"Occurs \1 times"),
    ]
    for pattern, replacement in patterns:
        if re.match(pattern, text):
            return re.sub(pattern, replacement, text)

    # Compound ledger/result/detail values can contain Chinese semicolon separators.
    if "；" in text:
        parts = [part.strip() for part in text.split("；")]
        translated_parts = [report_text(part) for part in parts]
        if all(part for part in translated_parts):
            return "; ".join(translated_parts)

    # Translate known fragments in warning/detail strings while preserving IDs,
    # filenames, XML tags, numeric values and other technical tokens verbatim.
    fragment_map = {
        "柜型交叉校验失败": "Cabinet type cross-check failed",
        "Y 标签序号不连续": "Y label numbering is not consecutive",
        "Q 标签序号不连续": "Q label numbering is not consecutive",
        "未识别": "Unrecognized",
        "待确认": "Pending Confirmation",
        "高": "High",
        "中": "Medium",
        "低": "Low",
    }
    rendered = text
    for source, target in fragment_map.items():
        rendered = rendered.replace(source, target)
    for source, target in _REPLACEMENTS:
        rendered = rendered.replace(source, target)
    return rendered
