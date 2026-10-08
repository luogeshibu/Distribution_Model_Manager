from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QRadioButton,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
)

from g_file_studio.models import (
    BasicOutputConflictAction,
    RmuAction,
    RmuStatusPosition,
)
from g_file_studio.processors.basic_processor import process_basic
from g_file_studio.processors.common import discover_g_inputs
from g_file_studio.services.output_naming import make_task_timestamp
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output, update_run_status
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP, FIELD_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_existing_directory, validate_input_source
from g_file_studio.ui.widgets import (
    BasicRulesEditor,
    ColorRuleRow,
    HelpLabel,
    InfoBanner,
    InputSourceSelector,
    IconUpgradeEditor,
    IntegerInput,
    PathRow,
    TaskPanel,
    WheelSafeComboBox,
)


class BasicPage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        help_title, help_html = APP_HELP["basic"]
        super().__init__(
            "基础处理",
            "支持处理单个 G 文件或整个目录；勾选需要的规则后统一点击“开始基础处理”。",
            help_title,
            help_html,
            parent,
        )

        self.layout.addWidget(
            InfoBanner(
                "输入可以是单个 G 文件，也可以是 G 文件目录。属性替换、元素删除、"
                "同类图元版本升级以及线路与母线样式修改，"
                "都在点击“开始基础处理”后统一执行。ID 检查/修复已移到全局“ID 检查与修复”模块。"
                "图元及电气 Pin 的标准检查/纠正统一在“服务器图元更新检查”模块执行。目录模式下每个文件独立处理。"
            )
        )

        path_box = QGroupBox("输入与输出")
        path_layout = QVBoxLayout(path_box)
        path_layout.setContentsMargins(12, 18, 12, 12)
        path_layout.setSpacing(10)

        self.source = InputSourceSelector(
            default_directory=default_workspace() / "input",
            file_filter="G Files (*.sln.pic.g *.g)",
            file_tooltip="选择一个需要执行基础处理的 G 文件。",
            directory_tooltip="选择包含多个待处理 G 文件的目录；程序只扫描目录第一层。",
            settings_prefix="basic",
            settings_service=self.user_settings,
        )
        path_layout.addWidget(self.source)

        output_form = QFormLayout()
        output_form.setHorizontalSpacing(16)
        output_form.setVerticalSpacing(10)
        self.output_path = PathRow(
            directory=True,
            dialog_title="选择基础处理输出目录",
            recent_directory_key="recent_paths/basic/output_directory",
            persistent_path_key="basic/output_directory",
            default_path=default_workspace() / "processed",
            location_name="基础处理输出目录",
            settings_service=self.user_settings,
        )
        self.output_path.set_tooltip(FIELD_HELP["output_dir"])
        configure_managed_output(self.output_path, "basic")
        output_form.addRow(HelpLabel("输出目录（workspace，只读）", "输出由程序统一管理。每次运行创建独立 workspace 目录，仅保留 30 天；需要长期保存请自行复制。"), self.output_path)
        path_layout.addLayout(output_form)
        self.layout.addWidget(path_box)

        rules_box = QGroupBox("通用处理规则")
        rules_layout = QVBoxLayout(rules_box)
        rules_layout.setContentsMargins(12, 18, 12, 12)
        rules_layout.setSpacing(12)
        self.rules_editor = BasicRulesEditor()
        self.rules_editor.set_input_dir(self.source.path())
        self.source.pathChanged.connect(self.rules_editor.set_input_dir)
        self.rules_editor.scanRequested.connect(self._scan_rules_schema)
        self.source.remote.selectionChanged.connect(self._remote_schema_selection_changed)
        rules_layout.addWidget(self.rules_editor)
        self.layout.addWidget(rules_box)

        self._build_graphic_merge_options()
        self._build_color_options()
        self._build_icon_upgrade_options()
        self._restore_options()

        self.task = TaskPanel()
        self.task.run_button.setText("开始基础处理")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)


    def _remote_schema_selection_changed(self) -> None:
        """远程勾选变化时不主动访问服务器，只提示需要重新扫描。"""
        if self.source.mode().value != "remote_ssh":
            return
        count = len(self.source.remote.selected_files())
        if count:
            self.rules_editor.scan_status.setText(
                f"已选择 {count} 个服务器 G 文件；点击“扫描元素与属性”后将只读下载到 workspace 并生成下拉选项"
            )
        else:
            self.rules_editor.scan_status.setText("请先在 SSH 文件列表中选择一个或多个 G 文件")

    def _scan_rules_schema(self) -> None:
        """为通用规则扫描准备当前输入源。

        SSH 模式必须先通过 SFTP GET 把当前所选文件下载到本地 workspace 快照，
        BasicRulesEditor 只扫描这个本地快照，绝不直接读取或修改服务器文件。
        """
        try:
            if self.source.mode().value == "remote_ssh":
                self.rules_editor.scan_status.setText("正在只读下载所选服务器 G 文件到 workspace，并扫描元素与属性……")
                # Remote preparation now downloads in a worker while a nested Qt
                # event loop keeps the window responsive; do not force the whole
                # application into a wait-cursor state.
                local_snapshot = self.source.prepare_for_processing()
                self.rules_editor.set_input_dir(local_snapshot)
            else:
                self.rules_editor.set_input_dir(self.source.path())
            self.rules_editor.refresh_schema()
        except Exception as exc:
            self.rules_editor.scan_status.setText(f"扫描元素与属性失败：{exc}")
            QMessageBox.warning(self, "扫描元素与属性失败", str(exc))

    def _build_rmu_options(self) -> None:
        box = QGroupBox("环网柜图元处理")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)
        description = QLabel(
            "“组合所有环网柜”会将每个直属 <rect> 作为环网柜外框，只组合完整位于矩形框内部的直属图元；"
            "任何部分位于框外的连接线、状态图标和文字都不会进入组合。"
            "“取消所有环网柜组合”会删除成员中含 <rect> 的 <Merge> 头元素，并把 rect 外框移动到柜内设备之前，"
            "使外框位于设备下层；坐标、ID、引用和业务属性不变，其他业务 Merge 不受影响。"
        )
        description.setWordWrap(True)
        description.setObjectName("mutedText")
        layout.addWidget(description)

        options = QHBoxLayout()
        options.setSpacing(12)
        self.rmu_action_group = QButtonGroup(self)
        self.rmu_action_group.setExclusive(True)
        self.rmu_none = QRadioButton("不处理环网柜组合")
        self.rmu_group = QRadioButton("组合所有环网柜")
        self.rmu_ungroup = QRadioButton("取消所有环网柜组合")
        self.rmu_none.setToolTip("保持文件现有 Merge 结构不变。")
        self.rmu_group.setToolTip(
            "单文件模式处理所选文件；目录模式处理第一层全部 G 文件。每个 rect 对应一个 Merge，只组合框内图元。"
        )
        self.rmu_ungroup.setToolTip(
            "删除所有成员中包含 rect 的环网柜 Merge，保留全部成员，并把 rect 调整到柜内设备下层；不删除其他业务 Merge。"
        )
        for button in (self.rmu_none, self.rmu_group, self.rmu_ungroup):
            button.setProperty("optionChoice", True)
            self.rmu_action_group.addButton(button)
            options.addWidget(button)
        options.addStretch(1)
        layout.addLayout(options)

        enhancement_title = QLabel("环网柜增强操作（可多选）")
        enhancement_title.setObjectName("sectionCaption")
        layout.addWidget(enhancement_title)

        self.rmu_smart_frame_color = ColorRuleRow(
            "含 SMART 的环网柜外框",
            "rect + Text[ts=SMART]",
            "#00A651",
        )
        self.rmu_smart_frame_color.enabled_box.setText(
            "修改含 SMART 的环网柜外框颜色"
        )
        self.rmu_smart_frame_color.enabled_box.setToolTip(
            "只识别框内存在 ts=SMART 的 Text 的直属 rect，并修改该 rect 的静态边框色 "
            "lc 和 lcc；SMART 字体颜色以及不含 SMART 的其他环网柜外框均保持不变。"
        )
        layout.addWidget(self.rmu_smart_frame_color)

        # 增强操作按竖列展示；每项仍是独立复选框，可按需多选。
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(10)
        self.rmu_reposition_channel_status = QCheckBox(
            "移动环网柜红色状态点（channel_status）"
        )
        self.rmu_reposition_channel_status.setProperty("optionChoice", True)
        self.rmu_reposition_channel_status.setToolTip(
            "只处理带 BusDis 的环网柜中 devref 指向 channel_status 的 <Status> 红色状态点。"
            "仅移动该状态点本身，不移动环网柜、母线、设备、标题、连接线或其他图元。"
        )
        self.rmu_channel_status_position = WheelSafeComboBox()
        self.rmu_channel_status_position.setFixedWidth(135)
        for position in RmuStatusPosition:
            self.rmu_channel_status_position.addItem(position.label, position.value)
        self.rmu_channel_status_position.setToolTip(
            "可选择矩形框内四个角或四条边的中点；默认左下角，与示意图中的目标位置一致。"
        )
        self.rmu_channel_status_margin = IntegerInput(5, 0, 1000)
        self.rmu_channel_status_margin.setFixedWidth(90)
        self.rmu_channel_status_margin.setToolTip(
            "状态点与所选矩形框边之间的内边距，默认 5 像素。"
        )
        status_position_label = QLabel("框内位置")
        status_position_label.setObjectName("mutedText")
        status_margin_label = QLabel("距边")
        status_margin_label.setObjectName("mutedText")
        status_margin_unit = QLabel("像素")
        status_margin_unit.setObjectName("mutedText")
        status_row.addWidget(self.rmu_reposition_channel_status)
        status_row.addWidget(status_position_label)
        status_row.addWidget(self.rmu_channel_status_position)
        status_row.addWidget(status_margin_label)
        status_row.addWidget(self.rmu_channel_status_margin)
        status_row.addWidget(status_margin_unit)
        status_row.addStretch(1)
        layout.addLayout(status_row)
        self.rmu_reposition_channel_status.toggled.connect(
            self.rmu_channel_status_position.setEnabled
        )
        self.rmu_reposition_channel_status.toggled.connect(
            self.rmu_channel_status_margin.setEnabled
        )

        self.rmu_remove_bus_frame = QCheckBox(
            "删除带 Bus 的环网柜外框，并将最近标题放到母线上方"
        )
        self.rmu_remove_bus_frame.setProperty("optionChoice", True)
        self.rmu_remove_bus_frame.setToolTip(
            "识别 rect 框内的 Bus，删除该 rect 及对应环网柜 Merge；寻找距离母线最近的业务标题 Text，移动到母线上方并水平居中。"
        )
        layout.addWidget(self.rmu_remove_bus_frame)
        self.layout.addWidget(box)


    def _build_rmu_identification_options(self) -> None:
        box = QGroupBox("环网柜名称与柜型识别")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)

        description = QLabel(
            "直接解析 G 文件，不使用 OCR。只有 rect 框内同时存在 BusDis、CBreakerDis 和 ZhaiWaiJieDiDaoZha 才认定为环网柜；"
            "柜名只从环网柜框正上方的 Text 中选择，并且同一个 Text 只能分配给一个环网柜。柜型优先按 Y1/Y2/... 与 Q1/Q2/... 名称计数，名称无法判断时才回退到设备 devref。"
            "柜型始终输出如 2L1T、3L1T；SMART 单独识别成一列，不参与柜型字符串。"
        )
        description.setWordWrap(True)
        description.setObjectName("mutedText")
        layout.addWidget(description)

        self.identify_rmu = QCheckBox("启用环网柜名称与柜型识别")
        self.identify_rmu.setProperty("optionChoice", True)
        layout.addWidget(self.identify_rmu)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("柜名位置："))
        self.rmu_name_top = QCheckBox("上方")
        self.rmu_name_bottom = QCheckBox("下方")
        self.rmu_name_left = QCheckBox("左侧")
        self.rmu_name_right = QCheckBox("右侧")
        self.rmu_name_top.setChecked(True)
        for item in (self.rmu_name_top, self.rmu_name_bottom, self.rmu_name_left, self.rmu_name_right):
            item.setProperty("optionChoice", True)
            name_row.addWidget(item)
        self.rmu_name_top.setText("上方（固定）")
        self.rmu_name_top.setEnabled(False)
        for item in (self.rmu_name_bottom, self.rmu_name_left, self.rmu_name_right):
            item.setChecked(False)
            item.setEnabled(False)
        name_row.addStretch(1)
        layout.addLayout(name_row)

        self.rmu_smart_in_type = QCheckBox("识别 SMART（单独列，不参与柜型）")
        self.rmu_smart_in_type.setProperty("optionChoice", True)
        self.rmu_smart_in_type.setToolTip(
            "启用后在识别结果/CSV 的 SMART 列输出 1 或 0；CabinetType 始终只输出 2L1T、3L1T 等 L/T 柜型。"
        )
        layout.addWidget(self.rmu_smart_in_type)

        for item in (self.rmu_name_bottom, self.rmu_name_left, self.rmu_name_right, self.rmu_smart_in_type):
            item.setEnabled(False)
            self.identify_rmu.toggled.connect(item.setEnabled)

        self.layout.addWidget(box)


    def _build_graphic_merge_options(self) -> None:
        box = QGroupBox("图形组合处理")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(9)

        description = QLabel(
            "这是整个 G 文件级的组合清理，不只针对环网柜。启用后删除 Layer 中全部 <Merge>，"
            "并将识别到的 RMU 外框 <rect> 移到柜内设备之前，使外框位于设备底层。"
            "除删除 Merge 和调整 rect 的 XML 顺序外，不修改任何设备属性、坐标、ID、keyid、devref 或 tfr。"
        )
        description.setWordWrap(True)
        description.setObjectName("mutedText")
        layout.addWidget(description)

        self.remove_all_graphic_merges = QCheckBox("彻底取消图形组合（删除全部 <Merge>，并将 RMU 外框置底）")
        self.remove_all_graphic_merges.setProperty("optionChoice", True)
        self.remove_all_graphic_merges.setToolTip(
            "输出文件中删除全部 Layer 直属 Merge；原文件不修改。RMU 外框只调整 XML 前后顺序，不修改任何属性。"
        )
        layout.addWidget(self.remove_all_graphic_merges)
        self.layout.addWidget(box)

    def _build_color_options(self) -> None:
        box = QGroupBox("线路与母线样式")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(9)
        description = QLabel(
            "按元素标签统一调整线路与母线样式。颜色仅修改 lc/lcc；线型仅修改 ls：实线=1、虚线=2。"
            "颜色勾选与线型选择彼此独立；线型选择‘保持原样’时不会修改 ls。不会修改填充色、线宽 lw、坐标、ID 或引用。"
        )
        description.setWordWrap(True)
        description.setObjectName("mutedText")
        layout.addWidget(description)

        self.feedline_color = ColorRuleRow("馈线", "FeedLine")
        self.connectline_color = ColorRuleRow("连接线", "ConnectLine")
        self.busdis_color = ColorRuleRow("配网母线", "BusDis")
        self.bus_color = ColorRuleRow("主网母线", "Bus")
        for row in (
            self.feedline_color,
            self.connectline_color,
            self.busdis_color,
            self.bus_color,
        ):
            layout.addWidget(row)
        self.layout.addWidget(box)

    def _build_icon_upgrade_options(self) -> None:
        box = QGroupBox("同类图元版本升级")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(10)

        description = QLabel(
            "这里只处理同一设备语义/同一 XML 类型的图元版本升级，例如旧版 LBS → 新版 LBS、旧版 Circuit Breaker → 新版 Circuit Breaker。"
            "OLD 与 NEW 两侧都支持两种来源：可以从本地批量添加 G 文件，也可以直接从主程序“图元管理”已桥接到本机 AppData 的图元缓存中选择；从服务器选择不会再次访问 SSH。"
            "文件名不要求一致，自动无法确认时可使用‘手动配对…’明确指定 OLD → NEW。"
            "程序读取双方 w/h、AlignCenter 和 pin(cx,cy)，并在升级时更新 devref 与几何；XML 类型或端口结构不兼容时禁止执行。"
            "处理时保持电气对齐锚点绝对位置不变，并按 zenon 中心旋转坐标计算真实 pin，不修改设备 ID、keyid、node_area 或拓扑关系。"
            "注意：SMART 图元用到 NORMAL、NORMAL 图元用到 SMART 这类情况属于‘图元类型/变体使用错误’，不是版本升级；应先在‘服务器图元更新检查’中发现并告警，由对应纠正流程处理。"
        )
        description.setWordWrap(True)
        description.setObjectName("mutedText")
        layout.addWidget(description)

        self.upgrade_icon_geometry = QCheckBox("启用同类图元版本升级")
        self.upgrade_icon_geometry.setProperty("optionChoice", True)
        self.upgrade_icon_geometry.setToolTip(
            "只处理主 G 中 devref 命中 OLD 映射且当前几何可确认属于旧标准的实例；"
            "已经符合新标准的实例会跳过，无法安全判定的自定义尺寸/几何会告警并跳过。"
        )
        layout.addWidget(self.upgrade_icon_geometry)

        self.icon_upgrade_editor = IconUpgradeEditor(self.user_settings)
        self.icon_upgrade_editor.setEnabled(False)
        self.upgrade_icon_geometry.toggled.connect(self.icon_upgrade_editor.setEnabled)
        layout.addWidget(self.icon_upgrade_editor)
        self.layout.addWidget(box)

    def _restore_options(self) -> None:
        self.remove_all_graphic_merges.setChecked(
            self.user_settings.get_bool("basic/remove_all_graphic_merges", False)
        )
        self.upgrade_icon_geometry.setChecked(
            self.user_settings.get_bool("basic/upgrade_icon_geometry", False)
        )
        self.icon_upgrade_editor.setEnabled(self.upgrade_icon_geometry.isChecked())

        color_rows = {
            "feedline": self.feedline_color,
            "connectline": self.connectline_color,
            "busdis": self.busdis_color,
            "bus": self.bus_color,
        }
        for key, row in color_rows.items():
            row.set_color(self.user_settings.get_value(f"basic/colors/{key}", "#0000FF"))
            row.set_enabled(
                self.user_settings.get_bool(f"basic/colors/{key}_enabled", False)
            )
            row.set_line_style(
                self.user_settings.get_value(f"basic/styles/{key}_line_style", "keep")
            )

    def save_state(self) -> None:
        self.source.persist_all_text()
        self.output_path.persist_current_text()
        self._persist_options()

    def _persist_options(self) -> None:
        self.user_settings.set_value(
            "basic/remove_all_graphic_merges", self.remove_all_graphic_merges.isChecked()
        )
        self.user_settings.set_value(
            "basic/upgrade_icon_geometry", self.upgrade_icon_geometry.isChecked()
        )
        color_rows = {
            "feedline": self.feedline_color,
            "connectline": self.connectline_color,
            "busdis": self.busdis_color,
            "bus": self.bus_color,
        }
        for key, row in color_rows.items():
            self.user_settings.set_value(f"basic/colors/{key}", row.color())
            self.user_settings.set_value(
                f"basic/colors/{key}_enabled", row.is_enabled()
            )
            self.user_settings.set_value(
                f"basic/styles/{key}_line_style", row.line_style()
            )

    def _validate_common_paths(self) -> bool:
        if not validate_input_source(self, self.source, display_name="基础处理输入"):
            return False
        # Managed workspace output is disposable and recreated when a run begins.
        self.source.persist_current()
        return True

    def _selected_rmu_action(self) -> RmuAction:
        if self.rmu_group.isChecked():
            return RmuAction.GROUP
        if self.rmu_ungroup.isChecked():
            return RmuAction.UNGROUP
        return RmuAction.NONE

    @staticmethod
    def _same_path(left: Path, right: Path) -> bool:
        return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(
            str(right.resolve(strict=False))
        )

    def _resolve_output_policy(self) -> tuple[BasicOutputConflictAction, str] | None:
        # workspace/runs 为每次任务创建独立目录，所以无需通过后缀或时间戳避让。
        # 所有一对一处理后的 G 文件必须与源文件同名。
        return BasicOutputConflictAction.OVERWRITE, ""

    def _settings(self):
        settings = self.rules_editor.build_settings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=self.output_path.path(),
        )
        return settings.model_copy(
            update={
                "upgrade_icon_geometry": self.upgrade_icon_geometry.isChecked(),
                "old_icon_files": self.icon_upgrade_editor.old_paths(),
                "new_icon_files": self.icon_upgrade_editor.new_paths(),
                "icon_upgrade_pairs": self.icon_upgrade_editor.pairs(),
                "remove_all_graphic_merges": self.remove_all_graphic_merges.isChecked(),
                "lower_rmu_rects_after_merge_cleanup": True,
                "change_feedline_color": self.feedline_color.is_enabled(),
                "feedline_color": self.feedline_color.color(),
                "feedline_line_style": self.feedline_color.line_style(),
                "change_connectline_color": self.connectline_color.is_enabled(),
                "connectline_color": self.connectline_color.color(),
                "connectline_line_style": self.connectline_color.line_style(),
                "change_busdis_color": self.busdis_color.is_enabled(),
                "busdis_color": self.busdis_color.color(),
                "busdis_line_style": self.busdis_color.line_style(),
                "change_bus_color": self.bus_color.is_enabled(),
                "bus_color": self.bus_color.color(),
                "bus_line_style": self.bus_color.line_style(),
            }
        )

    def run(self) -> None:
        if not self._validate_common_paths():
            return
        run_dir = begin_managed_run(self.output_path, "basic", "process")
        if self.upgrade_icon_geometry.isChecked():
            ok, message = self.icon_upgrade_editor.validate_for_run()
            if not ok:
                QMessageBox.warning(self, "同类图元版本升级检查未通过", message)
                return
        try:
            policy = self._resolve_output_policy()
        except Exception as exc:
            QMessageBox.warning(self, "输出检查失败", str(exc))
            return
        if policy is None:
            return

        action, timestamp = policy
        self._persist_options()
        settings = self._settings().model_copy(
            update={
                "output_conflict_action": action,
                "task_timestamp": timestamp,
            }
        )
        self.task.start(
            lambda log, progress: process_basic(settings, log, progress),
            settings.output_dir,
        )
