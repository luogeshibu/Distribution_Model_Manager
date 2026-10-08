from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.widgets.help_widgets import set_secondary


class PathRow(QWidget):
    """带完整路径恢复、手动输入保存和最近目录记忆的路径选择行。"""

    pathChanged = Signal(str)

    def __init__(
        self,
        *,
        directory: bool = True,
        file_filter: str = "All Files (*)",
        browse_help: str = "",
        dialog_title: str = "",
        recent_directory_key: str = "",
        persistent_path_key: str = "",
        default_path: str | Path | None = None,
        location_name: str = "目录",
        settings_service: UserSettingsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.directory = directory
        self.file_filter = file_filter
        self.dialog_title = dialog_title or ("选择目录" if directory else "选择文件")
        self.recent_directory_key = recent_directory_key
        self.persistent_path_key = persistent_path_key
        self.location_name = location_name
        self.settings_service = settings_service or UserSettingsService()
        self.default_path = Path(default_path).expanduser() if default_path else None
        self._missing_restored_path: Path | None = None

        self.edit = QLineEdit()
        self.edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(self.pathChanged)
        self.edit.editingFinished.connect(self.persist_current_text)

        self.button = QPushButton("浏览…")
        set_secondary(self.button)
        default_help = "选择目录" if directory else "选择文件"
        self.button.setToolTip(browse_help or default_help)
        self.button.setStatusTip(self.button.toolTip())
        self.button.clicked.connect(self.browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

        self._restore_initial_path()

    def _restore_initial_path(self) -> None:
        missing: Path | None = None
        restored: Path | None = None
        if self.persistent_path_key:
            result = self.settings_service.restore_path(
                self.persistent_path_key,
                expect="directory" if self.directory else "file",
            )
            restored = result.path
            missing = result.missing_path

        # A remembered path is only a convenience hint.  It may legitimately
        # disappear after workspace cleanup, moving the portable application, changing
        # drive letters, or deleting an old user folder.  restore_path() has already
        # removed the stale persistent value, so never interrupt page/application
        # startup with a modal warning.  Fall back to the current page default instead.
        if missing is not None:
            recent = self.settings_service.get_path(self.recent_directory_key) if self.recent_directory_key else None
            if recent is not None and not recent.is_dir():
                self.settings_service.clear(self.recent_directory_key)
            self._missing_restored_path = None
        else:
            self._missing_restored_path = None

        if restored is not None:
            self.edit.setText(str(restored))
        elif self.default_path is not None:
            self.edit.setText(str(self.default_path))

    def _current_hint(self) -> Path | None:
        text = self.edit.text().strip()
        if not text:
            if self._missing_restored_path is not None:
                return self.settings_service.closest_existing_directory(self._missing_restored_path)
            return self.default_path
        return self.settings_service.closest_existing_directory(Path(text).expanduser())

    def _dialog_start_directory(self) -> Path:
        resolved = self.settings_service.resolve_directory(
            self.recent_directory_key,
            fallback=self._current_hint(),
        )
        # Missing recent browse directories are also non-fatal.  The settings service
        # clears the stale value and resolves the closest valid fallback automatically.
        return resolved.directory

    def browse(self) -> None:
        start_path = self._dialog_start_directory()

        if self.directory:
            selected = QFileDialog.getExistingDirectory(
                self,
                self.dialog_title,
                str(start_path),
                QFileDialog.Option.ShowDirsOnly,
            )
        else:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                self.dialog_title,
                str(start_path),
                self.file_filter,
            )
        if not selected:
            return

        selected_path = Path(selected).expanduser()
        self._missing_restored_path = None
        self.edit.setText(str(selected_path))
        self.persist_current_text()
        recent_directory = selected_path if self.directory else selected_path.parent
        if self.recent_directory_key:
            self.settings_service.set_directory(
                self.recent_directory_key,
                recent_directory,
            )

    def persist_current_text(self) -> None:
        """保存用户浏览、手动输入或粘贴的完整路径。"""
        if not self.persistent_path_key:
            return
        text = self.edit.text().strip()
        if text:
            path = Path(text).expanduser()
            self.settings_service.set_path(self.persistent_path_key, path)
            if self.recent_directory_key:
                if self.directory and path.is_dir():
                    self.settings_service.set_directory(self.recent_directory_key, path)
                elif not self.directory and path.is_file():
                    self.settings_service.set_directory(self.recent_directory_key, path.parent)
                elif path.parent.exists() and path.parent.is_dir():
                    self.settings_service.set_directory(self.recent_directory_key, path.parent)
        else:
            self.settings_service.clear(self.persistent_path_key)

    def persist_valid_path(self) -> None:
        """执行前在路径已验证的情况下保存完整路径和最近目录。"""
        path = self.path()
        if self.persistent_path_key:
            self.settings_service.set_path(self.persistent_path_key, path)
        if self.recent_directory_key:
            recent = path if self.directory else path.parent
            self.settings_service.set_directory(self.recent_directory_key, recent)

    def path(self) -> Path:
        return Path(self.edit.text().strip()).expanduser()

    def set_path(self, path: Path | str, *, persist: bool = False) -> None:
        self.edit.setText(str(path))
        if persist:
            self.persist_current_text()

    def set_default_path(self, path: Path | str) -> None:
        """仅在当前没有恢复值和没有用户输入时设置默认路径。"""
        self.default_path = Path(path).expanduser()
        if not self.edit.text().strip():
            self.edit.setText(str(self.default_path))

    def set_tooltip(self, text: str) -> None:
        self.edit.setToolTip(text)
        self.edit.setStatusTip(text)
        self.button.setToolTip(text)
        self.button.setStatusTip(text)
