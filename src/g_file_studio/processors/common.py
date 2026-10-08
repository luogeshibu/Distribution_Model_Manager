from __future__ import annotations

import contextlib
import io
import sys
from collections.abc import Callable
from pathlib import Path

from g_file_studio.models import InputMode

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int], None]


class CallbackWriter(io.TextIOBase):
    def __init__(self, callback: LogCallback) -> None:
        self.callback = callback
        self._buffer = ""

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.callback(line)
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            self.callback(self._buffer.rstrip())
        self._buffer = ""


def redirect_safe_callback(callback: LogCallback) -> LogCallback:
    """返回可在 stdout/stderr 重定向期间安全调用的日志回调。"""

    original_stdout = sys.stdout
    original_stderr = sys.stderr

    def safe(line: str) -> None:
        with contextlib.redirect_stdout(original_stdout), contextlib.redirect_stderr(
            original_stderr
        ):
            callback(line)

    return safe


def discover_g_inputs(
    source_path: Path,
    input_mode: InputMode,
    *,
    compound_suffix_only: bool = False,
) -> list[Path]:
    """按输入模式发现 G 文件。

    单文件模式只处理用户选择的那个文件；目录模式只扫描目录第一层，不递归。
    compound_suffix_only=True 时要求文件名以 .sln.pic.g 结尾，否则只要求 .g。
    """

    source_path = Path(source_path)

    def valid(path: Path) -> bool:
        if not path.is_file():
            return False
        if compound_suffix_only:
            return path.name.lower().endswith(".sln.pic.g")
        return path.suffix.lower() == ".g"

    if input_mode == InputMode.SINGLE_FILE:
        if not source_path.is_file():
            raise FileNotFoundError(f"输入文件不存在：{source_path}")
        if not valid(source_path):
            expected = ".sln.pic.g" if compound_suffix_only else ".g"
            raise ValueError(f"输入文件必须以 {expected} 结尾：{source_path.name}")
        return [source_path]

    if not source_path.is_dir():
        raise NotADirectoryError(f"输入目录不存在：{source_path}")

    files = sorted(
        (path for path in source_path.iterdir() if valid(path)),
        key=lambda path: path.name.casefold(),
    )
    if not files:
        expected = ".sln.pic.g" if compound_suffix_only else ".g"
        raise FileNotFoundError(f"输入目录中没有以 {expected} 结尾的文件：{source_path}")
    return files


def enforce_confirmed_id_rules(output_path: Path, log: LogCallback = print) -> dict[str, int]:
    """对处理后的 G 文件强制应用用户确认的 ID 模板。

    仅对已经存在确认规则的 XML 类型做格式规范；未知类型不擅自分配新 ID。
    若未知类型存在重复 ID，则规范化引擎会报错，要求用户先在 ID 模块建立模板。
    """
    import os
    import xml.etree.ElementTree as ET
    from g_file_studio.engines.id_rule_engine import normalize_tree_ids_strict
    from g_file_studio.services.id_rule_service import IdRuleService

    from g_file_studio.services.user_settings_service import UserSettingsService

    strict_existing = UserSettingsService().get_bool("id_rules/global_strict", True)
    if not strict_existing:
        log(
            f"[ID 模板] {output_path.name}：全局强制约束已关闭，保留已有格式不符 ID；"
            "新生成 ID 仍由各业务模块按已确认模板分配。"
        )
        return {"changed": 0, "format_fixed": 0, "duplicate_fixed": 0}

    tree = ET.parse(output_path)
    rules = IdRuleService().load_rules()
    result = normalize_tree_ids_strict(tree, output_path, rules, repair_invalid_formats=True)
    if result.changed_element_ids:
        if hasattr(ET, "indent"):
            ET.indent(tree, space="    ")
        tmp = output_path.with_name(output_path.name + ".idtmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        ET.parse(tmp)
        os.replace(tmp, output_path)
        log(
            f"[ID 模板] {output_path.name}：按已确认规则强制规范 ID {result.changed_element_ids} 个"
            f"（格式 {result.format_fixed_count}，重复 {result.duplicate_fixed_count}）。"
        )
        for tag, old_id, new_id, reason in result.changes[:30]:
            log(f"  - <{tag}> {old_id} → {new_id}（{reason}）")
        if len(result.changes) > 30:
            log(f"  - 其余 {len(result.changes) - 30} 个变更省略。")
    else:
        log(f"[ID 模板] {output_path.name}：所有已配置类型 ID 均符合模板。")
    return {
        "changed": result.changed_element_ids,
        "format_fixed": result.format_fixed_count,
        "duplicate_fixed": result.duplicate_fixed_count,
    }
