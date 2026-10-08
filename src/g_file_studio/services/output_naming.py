from __future__ import annotations

from datetime import datetime
from pathlib import Path

COMPOUND_G_SUFFIX = ".sln.pic.g"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def make_task_timestamp(now: datetime | None = None) -> str:
    """返回用于同一批任务的本地时间戳。"""
    return (now or datetime.now()).strftime(TIMESTAMP_FORMAT)


def strip_g_suffix(filename: str) -> tuple[str, str]:
    """拆分 G 文件名，优先识别复合后缀 .sln.pic.g。"""
    lower = filename.lower()
    if lower.endswith(COMPOUND_G_SUFFIX):
        return filename[: -len(COMPOUND_G_SUFFIX)], filename[-len(COMPOUND_G_SUFFIX) :]
    if lower.endswith(".g"):
        return filename[:-2], filename[-2:]
    return filename, ""


def marked_output_name(
    input_name: str,
    marker: str,
    timestamp: str,
    *,
    append_timestamp: bool = True,
) -> str:
    """根据原文件名、输出标记和任务时间戳生成安全输出名。"""
    stem, suffix = strip_g_suffix(input_name)
    marker = marker.strip()
    timestamp = timestamp.strip()

    parts = [stem]
    if marker:
        parts.append(marker)
    if append_timestamp and timestamp:
        # marker 通常以 '-' 开头；时间戳始终用单个 '-' 与前面内容分隔。
        if parts[-1].endswith("-"):
            parts.append(timestamp)
        else:
            parts.append("-" + timestamp)
    return "".join(parts) + suffix


def normalize_merge_output_name(value: str) -> str:
    """把用户手工输入的合并文件名统一补全为 .sln.pic.g。"""
    value = value.strip()
    if not value:
        return ""
    lower = value.lower()
    if lower.endswith(COMPOUND_G_SUFFIX):
        return value
    if lower.endswith(".sln.pic"):
        return value + ".g"
    if lower.endswith(".g"):
        value = value[:-2]
    return value + COMPOUND_G_SUFFIX


def default_merge_output_name(timestamp: str) -> str:
    return f"MERGED-{timestamp}{COMPOUND_G_SUFFIX}"


def default_merge_output_path(output_dir: Path, timestamp: str) -> Path:
    return Path(output_dir) / default_merge_output_name(timestamp)
