from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.models import TemplateMode
from g_file_studio.services.template_service import (
    BuiltinTemplate,
    TemplateServiceError,
    export_builtin_template,
    get_builtin_template,
    load_builtin_templates,
)
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.widgets.help_widgets import set_secondary
from g_file_studio.ui.widgets.path_row import PathRow
from g_file_studio.ui.widgets.wheel_safe_combo_box import WheelSafeComboBox


class TemplateSelector(QWidget):
    """内置模板/客户自定义模板选择器，持久保存模式和完整模板路径。"""

    modeChanged = Signal(str)
    templateChanged = Signal(str)

    def __init__(
        self,
        *,
        settings_prefix: str = "frame",
        settings_service: UserSettingsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_prefix = settings_prefix
        self.settings_service = settings_service or UserSettingsService()
        self._templates: dict[str, BuiltinTemplate] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.builtin_option = QCheckBox("使用程序内置模板")
        self.custom_option = QCheckBox("使用客户自定义模板")
        for option in (self.builtin_option, self.custom_option):
            option.setProperty("optionChoice", True)
            self.mode_group.addButton(option)
            mode_row.addWidget(option)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        builtin_row = QHBoxLayout()
        self.builtin_combo = WheelSafeComboBox()
        self.builtin_combo.setToolTip("选择随 App 一起发布的内置图框模板。")
        self.version_label = QLabel()
        self.version_label.setObjectName("mutedText")
        self.export_button = QPushButton("导出内置模板")
        set_secondary(self.export_button)
        self.export_button.setToolTip("把当前内置模板复制到外部文件，便于查看或修改。")
        builtin_row.addWidget(self.builtin_combo, 1)
        builtin_row.addWidget(self.version_label)
        builtin_row.addWidget(self.export_button)
        root.addLayout(builtin_row)

        self.custom_path = PathRow(
            directory=False,
            file_filter="SLD G Files (*.sln.pic.g);;G Files (*.g)",
            dialog_title="选择客户自定义图框模板",
            recent_directory_key=f"recent_paths/{settings_prefix}/custom_template_directory",
            persistent_path_key=f"{settings_prefix}/custom_template_path",
            location_name="客户自定义图框模板",
            settings_service=self.settings_service,
        )
        self.custom_path.set_tooltip(
            "选择客户自己的图框模板。程序只调整外框尺寸和组件位置，不修改模板中的任何文字或签字信息。"
        )
        root.addWidget(self.custom_path)

        self.note = QLabel()
        self.note.setObjectName("mutedText")
        self.note.setWordWrap(True)
        root.addWidget(self.note)

        self.builtin_option.toggled.connect(self._update_mode)
        self.custom_option.toggled.connect(self._update_mode)
        self.builtin_combo.currentIndexChanged.connect(self._builtin_changed)
        self.custom_path.pathChanged.connect(self.templateChanged)
        self.export_button.clicked.connect(self.export_current_builtin)

        self._load_templates()
        self._restore_selection()
        self._update_mode(save=False)

    def _load_templates(self) -> None:
        try:
            default_id, templates = load_builtin_templates()
        except TemplateServiceError as exc:
            QMessageBox.critical(self, "内置模板错误", str(exc))
            return

        self._templates = {item.template_id: item for item in templates}
        self.builtin_combo.blockSignals(True)
        self.builtin_combo.clear()
        default_index = 0
        for index, item in enumerate(templates):
            self.builtin_combo.addItem(item.name, item.template_id)
            if item.template_id == default_id:
                default_index = index
        self.builtin_combo.setCurrentIndex(default_index)
        self.builtin_combo.blockSignals(False)
        self._builtin_changed(save=False)

    def _restore_selection(self) -> None:
        saved_id = self.settings_service.get_value(
            f"{self.settings_prefix}/builtin_template_id",
            "",
        )
        if saved_id:
            index = self.builtin_combo.findData(saved_id)
            if index >= 0:
                self.builtin_combo.setCurrentIndex(index)

        saved_mode = self.settings_service.get_value(
            f"{self.settings_prefix}/template_mode",
            TemplateMode.BUILTIN.value,
        )
        try:
            mode = TemplateMode(saved_mode)
        except ValueError:
            mode = TemplateMode.BUILTIN
        self.builtin_option.setChecked(mode == TemplateMode.BUILTIN)
        self.custom_option.setChecked(mode == TemplateMode.CUSTOM)
        self._builtin_changed(save=False)

    def _builtin_changed(self, *_args: object, save: bool = True) -> None:
        item = self.current_builtin_template()
        if item is None:
            self.version_label.setText("")
            return
        self.version_label.setText(f"版本 {item.version}")
        self.builtin_combo.setToolTip(item.description or item.name)
        if save:
            self.settings_service.set_value(
                f"{self.settings_prefix}/builtin_template_id",
                item.template_id,
            )
        self.templateChanged.emit(str(item.path))

    def _update_mode(self, *_args: object, save: bool = True) -> None:
        builtin = self.builtin_option.isChecked()
        self.builtin_combo.setEnabled(builtin)
        self.version_label.setEnabled(builtin)
        self.export_button.setEnabled(builtin)
        self.custom_path.setEnabled(not builtin)
        if builtin:
            self.note.setText(
                "内置模板：会按四边距调整外框，并允许修改左上标题和 Draw/Approve/Issue 信息。"
            )
        else:
            self.note.setText(
                "客户模板：会按四边距调整外框和锚定组件位置，但不会修改任何文字、姓名、日期、字体、颜色或表格内容。"
            )
        if save:
            self.settings_service.set_value(
                f"{self.settings_prefix}/template_mode",
                self.mode().value,
            )
        self.modeChanged.emit(self.mode().value)
        self.templateChanged.emit(str(self.resolved_template_path()))

    def mode(self) -> TemplateMode:
        return TemplateMode.BUILTIN if self.builtin_option.isChecked() else TemplateMode.CUSTOM

    def builtin_template_id(self) -> str:
        return str(self.builtin_combo.currentData() or "default_sld_frame")

    def current_builtin_template(self) -> BuiltinTemplate | None:
        return self._templates.get(self.builtin_template_id())

    def resolved_template_path(self) -> Path:
        if self.mode() == TemplateMode.CUSTOM:
            return self.custom_path.path()
        item = self.current_builtin_template()
        return item.path if item is not None else get_builtin_template().path

    def persist_current(self) -> None:
        self.settings_service.set_value(
            f"{self.settings_prefix}/template_mode",
            self.mode().value,
        )
        self.settings_service.set_value(
            f"{self.settings_prefix}/builtin_template_id",
            self.builtin_template_id(),
        )
        self.custom_path.persist_current_text()
        if self.mode() == TemplateMode.CUSTOM and self.custom_path.path().is_file():
            self.custom_path.persist_valid_path()

    def export_current_builtin(self) -> None:
        item = self.current_builtin_template()
        if item is None:
            return

        key = f"recent_paths/{self.settings_prefix}/export_template_directory"
        resolved = self.settings_service.resolve_directory(key)
        # A missing previous export directory is only a stale convenience setting.
        # resolve_directory() clears it and provides a valid fallback; do not interrupt
        # the user with a warning before opening the save dialog.
        suggested = resolved.directory / item.file_name
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "导出内置图框模板",
            str(suggested),
            "SLD G Files (*.sln.pic.g);;G Files (*.g)",
        )
        if not destination:
            return
        try:
            exported = export_builtin_template(item.template_id, Path(destination))
        except (OSError, TemplateServiceError) as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.settings_service.set_directory(key, exported.parent)
        QMessageBox.information(self, "导出成功", f"内置模板已导出到：\n{exported}")

    def validate_selection(self) -> bool:
        path = self.resolved_template_path()
        if not path.is_file():
            QMessageBox.warning(
                self,
                "模板无效",
                f"图框模板不存在：\n{path}\n\n请重新选择模板，或恢复使用程序内置模板。",
            )
            return False
        self.persist_current()
        return True
