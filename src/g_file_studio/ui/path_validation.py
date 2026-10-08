from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from g_file_studio.models import InputMode
from g_file_studio.ui.widgets.input_source_selector import InputSourceSelector


def _warn(parent: QWidget, title: str, message: str) -> bool:
    QMessageBox.warning(parent, title, message)
    return False


def validate_input_source(
    parent: QWidget,
    source: InputSourceSelector,
    *,
    display_name: str = "输入",
    require_compound_suffix: bool = False,
    log=None,
    progress=None,
) -> bool:
    if source.mode() == InputMode.REMOTE_SSH:
        try:
            path = source.prepare_for_processing(log=log, progress=progress)
        except Exception as exc:
            return _warn(parent, "SSH 远程输入准备失败", str(exc))
        return validate_existing_directory(parent, path, f"{display_name}远程快照目录")

    path = source.path()
    if source.mode() == InputMode.SINGLE_FILE:
        if not path.exists():
            return _warn(
                parent,
                f"{display_name}文件不存在",
                f"{display_name}文件不存在：\n{path}\n\n请重新选择文件。",
            )
        if not path.is_file():
            return _warn(
                parent,
                f"{display_name}路径无效",
                f"当前路径不是文件：\n{path}\n\n请重新选择文件。",
            )
        expected = ".sln.pic.g" if require_compound_suffix else ".g"
        if require_compound_suffix:
            valid = path.name.lower().endswith(expected)
        else:
            valid = path.suffix.lower() == expected
        if not valid:
            return _warn(
                parent,
                "文件后缀无效",
                f"输入文件必须以 {expected} 结尾：\n{path.name}",
            )
        return True

    return validate_existing_directory(parent, path, f"{display_name}目录")


def validate_existing_directory(parent: QWidget, path: Path, display_name: str) -> bool:
    if not path.exists():
        return _warn(
            parent,
            f"{display_name}不存在",
            f"{display_name}不存在：\n{path}\n\n请重新选择。",
        )
    if not path.is_dir():
        return _warn(
            parent,
            f"{display_name}无效",
            f"{display_name}不是有效目录：\n{path}\n\n请重新选择。",
        )
    return True
