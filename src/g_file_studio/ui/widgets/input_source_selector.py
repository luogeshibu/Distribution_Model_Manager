from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from g_file_studio.models import InputMode
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.widgets.path_row import PathRow
from g_file_studio.ui.widgets.remote_g_source import RemoteGSourceWidget
from g_file_studio.ui.widgets.wheel_safe_combo_box import WheelSafeComboBox


class InputSourceSelector(QWidget):
    """本地单文件/目录/SSH只读远程文件输入选择器。"""

    modeChanged = Signal(str)
    pathChanged = Signal(str)

    def __init__(
        self,
        *,
        default_directory: Path | None = None,
        default_mode: InputMode = InputMode.DIRECTORY,
        file_filter: str = "G Files (*.sln.pic.g *.g)",
        single_label: str = "单个 G 文件",
        directory_label: str = "G 文件目录",
        file_tooltip: str = "选择一个 G 文件。",
        directory_tooltip: str = "选择包含一个或多个 G 文件的目录。",
        settings_prefix: str = "common",
        settings_service: UserSettingsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_prefix = settings_prefix
        self.settings_service = settings_service or UserSettingsService()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("输入方式"))
        self.mode_combo = WheelSafeComboBox()
        self.mode_combo.addItem(single_label, InputMode.SINGLE_FILE.value)
        self.mode_combo.addItem(directory_label, InputMode.DIRECTORY.value)
        self.mode_combo.addItem("SSH 远程 G 文件（只读）", InputMode.REMOTE_SSH.value)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        default_dir = default_directory or (default_workspace() / "input")
        self.file_row = PathRow(
            directory=False,
            file_filter=file_filter,
            dialog_title="选择单个 G 文件",
            recent_directory_key=f"recent_paths/{settings_prefix}/single_file_directory",
            persistent_path_key=f"{settings_prefix}/single_file_path",
            location_name="单个 G 文件",
            settings_service=self.settings_service,
        )
        self.dir_row = PathRow(
            directory=True,
            dialog_title="选择 G 文件目录",
            recent_directory_key=f"recent_paths/{settings_prefix}/input_directory",
            persistent_path_key=f"{settings_prefix}/directory_path",
            default_path=default_dir,
            location_name="G 文件输入目录",
            settings_service=self.settings_service,
        )
        self.remote = RemoteGSourceWidget(
            settings_prefix=settings_prefix,
            settings_service=self.settings_service,
        )
        self.file_row.set_tooltip(file_tooltip)
        self.dir_row.set_tooltip(directory_tooltip)
        self.source_container = QWidget()
        self.source_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        source_layout = QVBoxLayout(self.source_container)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(0)
        source_layout.addWidget(self.file_row)
        source_layout.addWidget(self.dir_row)
        source_layout.addWidget(self.remote)
        root.addWidget(self.source_container)

        saved_mode = self.settings_service.get_value(f"{settings_prefix}/input_mode", default_mode.value)
        try:
            initial_mode = InputMode(saved_mode)
        except ValueError:
            initial_mode = default_mode

        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.file_row.pathChanged.connect(self.pathChanged)
        self.dir_row.pathChanged.connect(self.pathChanged)
        self.remote.prepared.connect(self.pathChanged)
        self.set_mode(initial_mode, persist=False)

    def _apply_mode_visibility(self, mode: InputMode) -> None:
        """Only the active source widget participates in layout sizing.

        This avoids the tall SSH file table reserving blank space while a local
        file/directory source is selected.
        """
        self.file_row.setVisible(mode == InputMode.SINGLE_FILE)
        self.dir_row.setVisible(mode == InputMode.DIRECTORY)
        self.remote.setVisible(mode == InputMode.REMOTE_SSH)
        # Let the parent layout own the width. Calling adjustSize() here can
        # shrink the local path row to its sizeHint after hiding the SSH panel.
        self.source_container.updateGeometry()
        self.updateGeometry()

    def _mode_changed(self, *_args: object) -> None:
        mode = self.mode()
        self._apply_mode_visibility(mode)
        self.settings_service.set_value(f"{self.settings_prefix}/input_mode", mode.value)
        self.modeChanged.emit(mode.value)
        self.pathChanged.emit(str(self.path()))

    def mode(self) -> InputMode:
        return InputMode(str(self.mode_combo.currentData()))

    def path(self) -> Path:
        mode = self.mode()
        if mode == InputMode.SINGLE_FILE:
            return self.file_row.path()
        if mode == InputMode.DIRECTORY:
            return self.dir_row.path()
        return self.remote.cache_dir()

    def prepare_for_processing(self, *, log=None, progress=None) -> Path:
        if self.mode() == InputMode.REMOTE_SSH:
            return self.remote.prepare_selected(log=log, progress=progress)
        return self.path()

    def set_mode(self, mode: InputMode, *, persist: bool = True) -> None:
        target = self.mode_combo.findData(mode.value)
        if target >= 0:
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(target)
            self.mode_combo.blockSignals(False)
        self._apply_mode_visibility(mode)
        if persist:
            self.settings_service.set_value(f"{self.settings_prefix}/input_mode", mode.value)

    def persist_current(self) -> None:
        self.settings_service.set_value(f"{self.settings_prefix}/input_mode", self.mode().value)
        if self.mode() == InputMode.SINGLE_FILE:
            self.file_row.persist_valid_path()
        elif self.mode() == InputMode.DIRECTORY:
            self.dir_row.persist_valid_path()
        else:
            self.remote.persist()

    def persist_all_text(self) -> None:
        self.file_row.persist_current_text()
        self.dir_row.persist_current_text()
        self.remote.persist()
        self.settings_service.set_value(f"{self.settings_prefix}/input_mode", self.mode().value)
