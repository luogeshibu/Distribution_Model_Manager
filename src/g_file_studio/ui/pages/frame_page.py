from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from g_file_studio.models import FrameSettings, PersonSettings, TemplateMode
from g_file_studio.processors.frame_processor import add_drawing_frames
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
    PersonEditor,
    TaskPanel,
    TemplateSelector,
)


class FramePage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        help_title, help_html = APP_HELP["frame"]
        super().__init__(
            "图框添加",
            "支持为单个 G 文件或整个目录批量添加并适配 SLD 图框。",
            help_title,
            help_html,
            parent,
        )
        self.banner = InfoBanner(
            "输入可以是单个 G 文件，也可以是 G 文件目录。输出文件保持源文件名不变并写入输出目录；"
            "当前选择模板作为最终权威图框，检测到已有图框时直接删除并重新添加，不叠加、不再要求人工先删除。"
        )
        self.layout.addWidget(self.banner)

        path_box = QGroupBox("输入与输出")
        path_layout = QVBoxLayout(path_box)
        path_layout.setContentsMargins(12, 18, 12, 12)
        path_layout.setSpacing(10)
        self.source = InputSourceSelector(
            default_directory=default_workspace() / "merged",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一个需要进行图框添加的 G 文件。",
            directory_tooltip="选择包含多个待进行图框添加的 G 文件目录；程序只扫描目录第一层。",
            settings_prefix="frame",
            settings_service=self.user_settings,
        )
        path_layout.addWidget(self.source)

        output_form = QFormLayout()
        output_form.setHorizontalSpacing(16)
        output_form.setVerticalSpacing(10)
        self.output_path = PathRow(
            directory=True,
            dialog_title="选择图框添加输出目录",
            recent_directory_key="recent_paths/frame/output_directory",
            persistent_path_key="frame/output_directory",
            default_path=default_workspace() / "output",
            location_name="图框添加输出目录",
            settings_service=self.user_settings,
        )
        self.output_path.set_tooltip(FIELD_HELP["output_dir"])
        configure_managed_output(self.output_path, "frame")
        output_form.addRow(HelpLabel("输出目录（workspace，只读）", "输出由程序统一管理。每次运行创建独立 workspace 目录，仅保留 30 天；需要长期保存请自行复制。"), self.output_path)
        path_layout.addLayout(output_form)
        self.layout.addWidget(path_box)

        template_box = QGroupBox("图框模板")
        template_layout = QVBoxLayout(template_box)
        template_layout.setContentsMargins(12, 18, 12, 12)
        self.template_selector = TemplateSelector(
            settings_prefix="frame",
            settings_service=self.user_settings,
        )
        self.template_selector.modeChanged.connect(self._template_mode_changed)
        template_layout.addWidget(self.template_selector)
        self.layout.addWidget(template_box)

        self.title_box = QGroupBox("内置模板：标题与签字栏")
        title_form = QFormLayout(self.title_box)
        title_form.setHorizontalSpacing(16)
        title_form.setVerticalSpacing(10)
        self.title = QLineEdit()
        self.title.setPlaceholderText("留空时取输入文件名，例如 JED-CTL-ADF")
        self.title.setToolTip(FIELD_HELP["title"])
        self.draw_editor = PersonEditor("Draw")
        self.approve_editor = PersonEditor("Approve")
        self.issue_editor = PersonEditor("Issue")
        title_form.addRow(HelpLabel("左上标题", FIELD_HELP["title"]), self.title)
        title_form.addRow(HelpLabel("Draw", FIELD_HELP["draw"]), self.draw_editor)
        title_form.addRow(HelpLabel("Approve", FIELD_HELP["approve"]), self.approve_editor)
        title_form.addRow(HelpLabel("Issue", FIELD_HELP["issue"]), self.issue_editor)
        self.layout.addWidget(self.title_box)

        layout_box = QGroupBox("图框与输出参数")
        layout_form = QFormLayout(layout_box)
        layout_form.setHorizontalSpacing(16)
        layout_form.setVerticalSpacing(10)
        self.left, self.top, self.right, self.bottom = [self.spin(50) for _ in range(4)]
        for widget in (self.left, self.top, self.right, self.bottom):
            widget.setToolTip(FIELD_HELP["frame_margin"])
        layout_form.addRow(HelpLabel("图框左边距", FIELD_HELP["frame_margin"]), self.left)
        layout_form.addRow(HelpLabel("图框上边距", FIELD_HELP["frame_margin"]), self.top)
        layout_form.addRow(HelpLabel("图框右边距", FIELD_HELP["frame_margin"]), self.right)
        layout_form.addRow(HelpLabel("图框下边距", FIELD_HELP["frame_margin"]), self.bottom)
        self.layout.addWidget(layout_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始图框添加")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)
        self._template_mode_changed(self.template_selector.mode().value)

    @staticmethod
    def spin(value: int) -> IntegerInput:
        return IntegerInput(value=value, minimum=0, maximum=100000)

    def _template_mode_changed(self, mode_value: str) -> None:
        builtin = TemplateMode(mode_value) == TemplateMode.BUILTIN
        self.title_box.setEnabled(builtin)
        if builtin:
            self.banner.set_text(
                "内置模板会按四边距调整外框，并修改左上标题和 Draw/Approve/Issue 信息。"
                "如果源 G 已有图框，会先强制删除旧图框再用当前内置模板覆盖。输出保持源文件名不变。"
            )
        else:
            self.banner.set_text(
                "客户自定义模板会按四边距调整外框长度和组件位置，但不会修改任何文字、姓名、日期、字体、颜色或表格内容。"
                "如果源 G 已有图框，会先强制删除旧图框再用当前选择模板覆盖。输出保持源文件名不变。"
            )

    def settings(self) -> FrameSettings:
        return FrameSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=self.output_path.path(),
            template_file=self.template_selector.resolved_template_path(),
            template_mode=self.template_selector.mode(),
            builtin_template_id=self.template_selector.builtin_template_id(),
            title=self.title.text().strip(),
            draw=PersonSettings(name=self.draw_editor.name(), date=self.draw_editor.date()),
            approve=PersonSettings(name=self.approve_editor.name(), date=self.approve_editor.date()),
            issue=PersonSettings(name=self.issue_editor.name(), date=self.issue_editor.date()),
            frame_left=self.left.value(),
            frame_top=self.top.value(),
            frame_right=self.right.value(),
            frame_bottom=self.bottom.value(),
            output_suffix="",
            append_timestamp=False,
        )

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()
        self.template_selector.persist_current()

    @staticmethod
    def _same_path(left, right) -> bool:
        try:
            return left.resolve(strict=False) == right.resolve(strict=False)
        except OSError:
            return str(left.absolute()) == str(right.absolute())

    def _confirm_existing_outputs(self, settings: FrameSettings) -> FrameSettings | None:
        files = discover_g_inputs(settings.source_path, settings.input_mode)
        conflicts = []
        for source in files:
            target = settings.output_dir / source.name
            if self._same_path(source, target):
                QMessageBox.critical(
                    self,
                    "输出目录不能与源文件位置相同",
                    f"图框添加现在保持源文件名不变。\n\n源文件：{source}\n目标文件：{target}\n\n"
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
            f"{examples}\n\n图框添加会保持源文件名不变。请选择本次处理方式。"
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
        if not validate_input_source(self, self.source, display_name="图框添加输入"):
            return
        # Managed workspace output is disposable and recreated on demand.
        if not self.template_selector.validate_selection():
            return
        self.source.persist_current()
        run_dir = begin_managed_run(self.output_path, "frame", "add-frame")
        self.template_selector.persist_current()
        settings = self._confirm_existing_outputs(self.settings())
        if settings is None:
            return
        self.task.start(
            lambda log, progress: add_drawing_frames(settings, log, progress),
            settings.output_dir,
        )
