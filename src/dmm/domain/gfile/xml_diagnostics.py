#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import codecs
import re
from pathlib import Path
from typing import Optional, Tuple


class GFileXmlParseError(RuntimeError):
    """Known source-file error: the G file cannot be parsed as valid XML."""


_XML_ENCODING_RE = re.compile(
    br"<\?xml\b[^>]*?\bencoding\s*=\s*['\"]\s*([^'\"\s>]+)\s*['\"]",
    re.IGNORECASE,
)


def _declared_encoding(data: bytes) -> str:
    """Read only the ASCII XML declaration; never guess an alternative encoding."""
    head = data[:1024]
    match = _XML_ENCODING_RE.search(head)
    if not match:
        return "未声明"
    try:
        return match.group(1).decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return match.group(1).decode("ascii", errors="replace")


def _error_position(exc: BaseException) -> Tuple[Optional[int], Optional[int]]:
    position = getattr(exc, "position", None)
    if (
        isinstance(position, tuple)
        and len(position) == 2
        and all(isinstance(v, int) for v in position)
    ):
        return position[0], position[1]
    return None, None


def _line_bytes(data: bytes, line_no: Optional[int]) -> bytes:
    if not line_no or line_no < 1:
        return b""
    # splitlines() is intentionally byte based so invalid source bytes are preserved.
    lines = data.splitlines()
    if line_no > len(lines):
        return b""
    return lines[line_no - 1]


def _hex_window(raw_line: bytes, column: Optional[int], radius: int = 24) -> str:
    if not raw_line:
        return ""
    if column is None:
        start, end = 0, min(len(raw_line), radius * 2)
    else:
        # Expat's column is character-oriented.  For diagnostics only, treating it
        # as a byte offset gives a useful nearby window without modifying parsing.
        center = max(0, min(int(column), len(raw_line)))
        start = max(0, center - radius)
        end = min(len(raw_line), center + radius)
    return raw_line[start:end].hex(" ").upper()


def _preview_with_declared_encoding(raw_line: bytes, encoding: str) -> str:
    if not raw_line:
        return ""
    if not encoding or encoding == "未声明":
        return raw_line.decode("ascii", errors="replace")[:240]
    try:
        codecs.lookup(encoding)
    except LookupError:
        return "<XML 声明中的编码名称无法被 Python 识别>"
    # Replacement is used only for the human-readable diagnostic preview.
    # It is never fed back into ElementTree and is not a compatibility fallback.
    try:
        return raw_line.decode(encoding, errors="replace")[:240]
    except Exception:
        return "<无法按 XML 声明编码生成诊断预览>"


def _strict_declared_decode_check(data: bytes, encoding: str) -> str:
    if not encoding or encoding == "未声明":
        return (
            "编码一致性检查：XML 未声明 encoding，无法执行声明编码一致性检查。"
        )
    try:
        codecs.lookup(encoding)
    except LookupError:
        return (
            f"编码一致性检查：失败；XML 声明了未知/不支持的编码 {encoding!r}。"
        )

    try:
        data.decode(encoding, errors="strict")
        return (
            f"编码一致性检查：文件字节可以按声明编码 {encoding!r} 严格解码；"
            "因此更可能是 XML 语法或非法 XML 字符问题。"
        )
    except UnicodeDecodeError as err:
        prefix = data[: err.start]
        byte_line = prefix.count(b"\n") + 1
        last_nl = prefix.rfind(b"\n")
        byte_col = err.start - (last_nl + 1)
        bad = data[err.start : min(len(data), err.end + 8)]
        return (
            f"编码一致性检查：失败；文件声明编码={encoding!r}，但原始字节无法按该编码严格解码。\n"
            f"  首个解码错误：byte_offset={err.start}, 约第{byte_line}行/第{byte_col}字节列，"
            f"reason={err.reason}\n"
            f"  错误附近原始字节(HEX)：{bad.hex(' ').upper()}"
        )
    except Exception as err:
        return f"编码一致性检查：执行失败：{type(err).__name__}: {err}"


def build_gfile_xml_error(path: str | Path, exc: BaseException) -> GFileXmlParseError:
    """Create a detailed, non-repairing diagnostic for an invalid G XML file.

    Important: this function does NOT attempt GBK/GB18030/other fallback parsing,
    does NOT rewrite the XML declaration, and does NOT alter the source file.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except Exception as read_exc:
        return GFileXmlParseError(
            "G_FILE_XML_INVALID：G 文件 XML 解析失败，同时无法读取原始文件进行诊断。\n"
            f"文件：{path}\n"
            f"解析器错误：{type(exc).__name__}: {exc}\n"
            f"诊断读取错误：{type(read_exc).__name__}: {read_exc}"
        )

    encoding = _declared_encoding(data)
    line_no, column = _error_position(exc)
    raw_line = _line_bytes(data, line_no)
    preview = _preview_with_declared_encoding(raw_line, encoding)
    hex_window = _hex_window(raw_line, column)
    consistency = _strict_declared_decode_check(data, encoding)

    location = (
        f"第 {line_no} 行，第 {column} 列"
        if line_no is not None and column is not None
        else "解析器未提供明确行/列"
    )

    lines = [
        "G_FILE_XML_INVALID：源 G 文件不是可按其 XML 声明正常解析的合法 XML，任务已停止。",
        f"文件：{path.name}",
        f"完整路径：{path}",
        f"文件大小：{len(data)} bytes",
        f"XML 声明编码：{encoding}",
        f"解析器错误：{type(exc).__name__}: {exc}",
        f"错误位置：{location}",
        consistency,
    ]
    if preview:
        lines.append(f"错误行预览（仅按声明编码用于诊断，不参与解析）：{preview}")
    if hex_window:
        lines.append(f"错误位置附近原始字节(HEX)：{hex_window}")

    lines.extend([
        "判断：该 G 文件可能存在“XML encoding 声明与实际字节不一致”、混合编码、非法字节，"
        "或其他不符合 XML 规范的字符/语法。",
        "程序处理策略：严格 XML 解析；不会自动尝试 GBK/GB18030 等其他编码，"
        "不会自动转码、替换非法字符或修改源 G 文件。",
        "处理建议：请从源系统重新导出该 G 文件，确保整个文件使用单一且与 XML declaration 一致的编码；"
        "如需人工修复，建议统一保存为 UTF-8 并保持 <?xml ... encoding=\"utf-8\"?> 一致，"
        "确认文件可被标准 XML 解析器打开后再重新执行模型校验。",
    ])
    return GFileXmlParseError("\n".join(lines))
