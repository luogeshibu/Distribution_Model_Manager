from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QGroupBox, QMessageBox, QVBoxLayout

from g_file_studio.models import MarginSettings
from g_file_studio.processors.margin_processor import adjust_graph_margins
from g_file_studio.processors.common import discover_g_inputs
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output, update_run_status
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP, FIELD_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_existing_directory, validate_input_source
from g_file_studio.ui.widgets import (
    HelpLabel,
    InfoBanner,
    InputSourceSelector,
    IntegerInput,
    PathRow,
    TaskPanel,
)


class MarginPage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        help_title, help_html = APP_HELP["margin"]
        super().__init__(
            "图形边距调整",
            "把主体图形整体移动到指定四边距；内置图框自动同步调整，其他图框要求先删除。",
            help_title,
            help_html,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "默认主体图形距离画布左、上、右、下各 500。输出文件保持源文件名不变并写入输出目录；仅当图框可确认是 G File Studio 内置图框时，程序才会排除图框组件并同步调整；检测到其他图框时会停止并提示先删除图框。内置图框文字与业务内容完全不修改。"
            )
        )

        path_box = QGroupBox("输入与输出")
        path_layout = QVBoxLayout(path_box)
        path_layout.setContentsMargins(12, 18, 12, 12)
        path_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "merged",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一个需要调整主体图形边距的 G 文件。",
            directory_tooltip="选择包含多个 G 文件的目录；程序只扫描目录第一层。",
            settings_prefix="margin",
            settings_service=self.user_settings,
        )
        path_layout.addWidget(self.source)

        output_form = QFormLayout()
        self.output_path = PathRow(
            directory=True,
            dialog_title="选择图形边距调整输出目录",
            recent_directory_key="recent_paths/margin/output_directory",
            persistent_path_key="margin/output_directory",
            default_path=default_workspace() / "output",
            location_name="图形边距调整输出目录",
            settings_service=self.user_settings,
        )
        self.output_path.set_tooltip(FIELD_HELP["output_dir"])
        configure_managed_output(self.output_path, "margin")
        output_form.addRow(HelpLabel("输出目录（workspace，只读）", "输出由程序统一管理。每次运行创建独立 workspace 目录，仅保留 30 天；需要长期保存请自行复制。"), self.output_path)
        path_layout.addLayout(output_form)
        self.layout.addWidget(path_box)

        parameter_box = QGroupBox("主体图形边距")
        parameter_form = QFormLayout(parameter_box)
        parameter_form.setHorizontalSpacing(16)
        parameter_form.setVerticalSpacing(10)
        self.left = self.spin(500)
        self.top = self.spin(500)
        self.right = self.spin(500)
        self.bottom = self.spin(500)
        for widget in (self.left, self.top, self.right, self.bottom):
            widget.setToolTip(FIELD_HELP["content_margin"])
        parameter_form.addRow(HelpLabel("图形左边距", FIELD_HELP["content_margin"]), self.left)
        parameter_form.addRow(HelpLabel("图形上边距", FIELD_HELP["content_margin"]), self.top)
        parameter_form.addRow(HelpLabel("图形右边距", FIELD_HELP["content_margin"]), self.right)
        parameter_form.addRow(HelpLabel("图形下边距", FIELD_HELP["content_margin"]), self.bottom)
        self.layout.addWidget(parameter_box)

        self.layout.addWidget(
            InfoBanner(
                "已有图框处理规则：G File Studio 内置图框会保留并同步调整；客户图框或无法确认来源的图框不会自动处理，程序会提示先删除图框。内置图框中的标题、Draw、Approve、Issue、日期、字体、颜色、线宽和表格内容保持不变。"
            )
        )

        self.task = TaskPanel()
        self.task.run_button.setText("开始调整图形边距")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)

    @staticmethod
    def spin(value: int) -> IntegerInput:
        return IntegerInput(value=value, minimum=0, maximum=100000)

    def settings(self) -> MarginSettings:
        return MarginSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=self.output_path.path(),
            left_margin=self.left.value(),
            top_margin=self.top.value(),
            right_margin=self.right.value(),
            bottom_margin=self.bottom.value(),
            preserve_existing_frame=True,
            output_suffix="",
            append_timestamp=False,
        )

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()

    @staticmethod
    def _same_path(left, right) -> bool:
        try:
            return left.resolve(strict=False) == right.resolve(strict=False)
        except OSError:
            return str(left.absolute()) == str(right.absolute())

    def _confirm_existing_outputs(self, settings: MarginSettings) -> MarginSettings | None:
        files = discover_g_inputs(settings.source_path, settings.input_mode)
        conflicts = []
        for source in files:
            target = settings.output_dir / source.name
            if self._same_path(source, target):
                QMessageBox.critical(
                    self,
                    "输出目录不能与源文件位置相同",
                    f"图形边距调整现在保持源文件名不变。\n\n源文件：{source}\n目标文件：{target}\n\n"
                    "为避免覆盖原始 G 文件，请选择其他输出目录。",
                )
                return None
            if target.exists():
                conflicts.append(target)

        if not conflicts:
            return settings.model_copy(update={"overwrite": True})

        examples = "\n".join(f"• {path.name}" for path in conflicts[:6])
        if len(conflicts) > 6:
            examples += f"\n• 其余 {len(conflicts) - 6} 个同名文件……"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("输出目录存在同名文件")
        box.setText(f"检测到 {len(conflicts)} 个同名输出文件。")
        box.setInformativeText(
            f"{examples}\n\n图形边距调整会保持源文件名不变。请选择本次处理方式。"
        )
        overwrite_button = box.addButton("覆盖同名文件", QMessageBox.ButtonRole.DestructiveRole)
        skip_button = box.addButton("跳过同名文件", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = box.addButton("取消任务", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(skip_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite_button:
            return settings.model_copy(update={"overwrite": True})
        if clicked is skip_button:
            return settings.model_copy(update={"overwrite": False})
        if clicked is cancel_button:
            return None
        return None

    def run(self) -> None:
        if not validate_input_source(self, self.source, display_name="图形边距调整输入"):
            return
        # Managed workspace output is disposable and recreated on demand.
        self.source.persist_current()
        run_dir = begin_managed_run(self.output_path, "margin", "adjust")
        settings = self._confirm_existing_outputs(self.settings())
        if settings is None:
            return
        self.task.start(
            lambda log, progress: adjust_graph_margins(settings, log, progress),
            settings.output_dir,
        )
