from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from g_file_studio.models import MergeSettings
from g_file_studio.engines import merge_engine
from g_file_studio.processors.merge_processor import merge_feeders
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.database_service import OracleDatabaseService
from g_file_studio.services.remote_symbol_library import DEFAULT_REMOTE_SYMBOL_ROOT, RemoteSymbolLibraryService
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output, update_run_status
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP, FIELD_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_existing_directory
from g_file_studio.ui.table_layout import configure_responsive_table
from g_file_studio.ui.widgets import (
    FileOrderEditor,
    HelpLabel,
    InfoBanner,
    IntegerInput,
    PathRow,
    TaskPanel,
    RemoteGSourceWidget,
    TemplateSelector,
    WheelSafeComboBox,
)


class MergePage(BasePage):
    def __init__(self, user_settings: UserSettingsService, parent=None) -> None:
        self.user_settings = user_settings
        self.database_service = OracleDatabaseService(user_settings)
        help_title, help_html = APP_HELP["merge"]
        super().__init__(
            "馈线图合并",
            "按用户选择顺序合并多个馈线 G 图，完成垂直对齐、冲突 ID 处理和画布计算。",
            help_title,
            help_html,
            parent,
        )
        self.layout.addWidget(
            InfoBanner(
                "输入文件名不解析站点或馈线号。先加载目录，再使用模糊查询选择或全选文件并导入顺序列表；第一行是合并基准。G File Studio 内置图框会在合并前自动移除，客户或来源不明的图框禁止参与。垂直对齐只识别有效水平 <Bus>，不会把 <BusDis> 当作 Bus；无 Bus 时使用最高图元。"
            )
        )

        path_box = QGroupBox("输入与输出")
        path_layout = QVBoxLayout(path_box)
        source_mode_row = QHBoxLayout()
        source_mode_row.addWidget(HelpLabel("输入方式", "本地目录或 SSH/SFTP 只读远程 G 文件。远程模式只允许读取和下载，不会修改服务器文件。"))
        self.input_mode_combo = WheelSafeComboBox()
        self.input_mode_combo.addItem("本地 G 文件目录", "local")
        self.input_mode_combo.addItem("SSH 远程 G 文件（只读）", "ssh")
        saved_merge_mode = str(self.user_settings.get_value("merge/input_source_mode", "local"))
        idx = self.input_mode_combo.findData(saved_merge_mode)
        self.input_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        source_mode_row.addWidget(self.input_mode_combo)
        source_mode_row.addStretch(1)
        path_layout.addLayout(source_mode_row)

        self.local_input_page = QWidget()
        local_form = QFormLayout(self.local_input_page)
        local_form.setContentsMargins(0, 0, 0, 0)
        self.input_path = PathRow(
            directory=True,
            dialog_title="选择待合并 G 文件目录",
            recent_directory_key="recent_paths/merge/input_directory",
            persistent_path_key="merge/input_directory",
            default_path=default_workspace() / "processed",
            location_name="馈线图合并输入目录",
            settings_service=self.user_settings,
        )
        self.input_path.set_tooltip(FIELD_HELP["merge_input_dir"])
        local_form.addRow(HelpLabel("输入目录", FIELD_HELP["merge_input_dir"]), self.input_path)
        path_layout.addWidget(self.local_input_page)

        self.remote_source = RemoteGSourceWidget(
            settings_prefix="merge",
            settings_service=self.user_settings,
        )
        path_layout.addWidget(self.remote_source)

        self.output_path = PathRow(
            directory=True,
            dialog_title="选择合并结果输出目录",
            recent_directory_key="recent_paths/merge/output_directory",
            persistent_path_key="merge/output_directory",
            default_path=default_workspace() / "merged",
            location_name="馈线图合并输出目录",
            settings_service=self.user_settings,
        )
        self.output_path.set_tooltip(FIELD_HELP["output_dir"])
        configure_managed_output(self.output_path, "merge")
        output_row = QFormLayout()
        output_row.addRow(HelpLabel("输出目录（workspace，只读）", "馈线合并结果只能写入 G File Studio 的 workspace 运行目录，路径不可修改。处理完成后请点击“打开本次运行目录”查看或复制文件；运行目录自动保留 30 天。"), self.output_path)
        path_layout.addLayout(output_row)

        self.output_name = QLineEdit()
        self.output_name.setPlaceholderText("留空自动生成 MERGED-时间戳.sln.pic.g；也可手动输入名称")
        self.output_name.setToolTip(FIELD_HELP["output_name"])
        self.layout.addWidget(path_box)

        order_box = QGroupBox("输入文件与合并顺序")
        order_form = QFormLayout(order_box)
        order_form.setContentsMargins(12, 18, 12, 12)
        self.file_order = FileOrderEditor()
        self.file_order.set_input_dir(self._active_input_dir())
        # The host DMM theme uses a saturated native-blue selection color for
        # QTableWidget rows.  In the feeder-merge order list that made selected
        # file names difficult to read.  Keep the selection obvious but use a
        # light, high-contrast green highlight local to this module.
        self.file_order.table.setObjectName("mergeFileOrderTable")
        self.file_order.table.setStyleSheet(
            "QTableWidget#mergeFileOrderTable { selection-background-color:#DDF4EB; selection-color:#123B32; }"
            "QTableWidget#mergeFileOrderTable::item:selected { background:#DDF4EB; color:#123B32; border-top:1px solid #79BBA5; border-bottom:1px solid #79BBA5; }"
            "QTableWidget#mergeFileOrderTable::item:selected:!active { background:#E8F7F2; color:#123B32; }"
        )
        order_form.addRow(self.file_order)
        self.layout.addWidget(order_box)

        settings_box = QGroupBox("布局参数")
        settings_form = QFormLayout(settings_box)
        settings_form.setHorizontalSpacing(16)
        settings_form.setVerticalSpacing(10)
        self.gap = self.spin(300)
        self.feeder_min_width = self.spin(1000)
        self.merge_main_bus = QCheckBox("启用主网母线处理")
        self.merge_main_bus.setObjectName("mergeMainBusToggle")
        self.merge_main_bus.setToolTip("启用后必须选择单母线或双母线。只检查所选主母线；异常短线 Bus 不再在这里过滤，请统一使用“异常小尺寸图元检测”模块处理。")
        # Give the main-bus option a persistent selected state instead of relying
        # on the small checkbox indicator alone.  This is presentation-only.
        self.merge_main_bus.setStyleSheet(
            "QCheckBox#mergeMainBusToggle { background:#F8FBFA; border:1px solid #BFD4CD; border-radius:8px; padding:7px 10px; color:#29464D; font-weight:650; }"
            "QCheckBox#mergeMainBusToggle:hover { border-color:#64AA93; background:#F1F9F6; }"
            "QCheckBox#mergeMainBusToggle:checked { background:#DFF3EA; border:2px solid #0B7A5A; color:#075B45; font-weight:750; }"
            "QCheckBox#mergeMainBusToggle::indicator { width:20px; height:20px; }"
        )
        self.main_bus_mode = "single"
        self.main_bus_mode_button = QPushButton("母线类型：未选择")
        self.main_bus_mode_button.setEnabled(False)
        self.main_bus_mode_button.setToolTip("点击选择单母线或双母线；勾选主网母线处理时也会自动弹出选择。")
        self.main_bus_mode_button.clicked.connect(self._choose_main_bus_mode)
        self.main_bus_groups: list[list[str]] = []
        self.main_bus_group_button = QPushButton("设置母线分组")
        self.main_bus_group_button.setEnabled(False)
        self.main_bus_group_button.setToolTip("按当前馈线顺序人工指定哪些连续馈线共用一组主母线；未分组馈线保持独立。")
        self.main_bus_group_button.clicked.connect(self._edit_main_bus_groups)
        self._refresh_main_bus_visual_state()
        bus_row = QWidget()
        bus_row_layout = QHBoxLayout(bus_row)
        bus_row_layout.setContentsMargins(0, 0, 0, 0)
        bus_row_layout.setSpacing(10)
        bus_row_layout.addWidget(self.merge_main_bus)
        bus_row_layout.addWidget(self.main_bus_mode_button)
        bus_row_layout.addWidget(self.main_bus_group_button)
        bus_row_layout.addStretch(1)
        self.left = self.spin(300)
        self.top = self.spin(300)
        self.right = self.spin(300)
        self.bottom = self.spin(300)
        self.gap.setToolTip(FIELD_HELP["feeder_gap"])
        for widget in (self.left, self.top, self.right, self.bottom):
            widget.setToolTip(FIELD_HELP["merge_margin"])
        settings_form.addRow(HelpLabel("默认单线图宽度", "每个馈线图的最小占用宽度。实际宽度小于该值时按该值预留；实际宽度超过该值时使用实际宽度。该宽度不包含相邻馈线间隔。"), self.feeder_min_width)
        settings_form.addRow(HelpLabel("主母线处理", "启用后先选择单母线或双母线，再人工设置母线分组。程序不再使用 keyid 判断分组；只有同一人工分组内、且在当前馈线顺序中连续的文件才会共用母线。未分组馈线保持独立。"), bus_row)
        settings_form.addRow(HelpLabel("相邻图形间隔", FIELD_HELP["feeder_gap"]), self.gap)
        settings_form.addRow(HelpLabel("左边距", FIELD_HELP["merge_margin"]), self.left)
        settings_form.addRow(HelpLabel("上边距", FIELD_HELP["merge_margin"]), self.top)
        settings_form.addRow(HelpLabel("右边距", FIELD_HELP["merge_margin"]), self.right)
        settings_form.addRow(HelpLabel("下边距", FIELD_HELP["merge_margin"]), self.bottom)
        self.layout.addWidget(settings_box)

        post_box = QGroupBox("合并后处理")
        post_layout = QVBoxLayout(post_box)
        post_layout.setContentsMargins(12, 18, 12, 12)
        post_layout.setSpacing(9)
        self.add_poke_after_merge = QCheckBox("合并完成后自动添加 Poke 跳转")
        self.add_poke_after_merge.setProperty("optionChoice", True)
        self.add_poke_after_merge.setChecked(
            self.user_settings.get_bool("merge/add_poke_after_merge", True)
        )
        self.add_poke_after_merge.setToolTip(
            "默认开启。馈线合并完成后自动复用现有 Poke 跳转模块，对最终合并图执行 RMU、AR/LBS/SEC 设备和站点跳转 Poke。"
            "处理顺序为：馈线合并 → Poke 跳转 → 可选图框。"
        )
        post_layout.addWidget(self.add_poke_after_merge)
        self.add_frame_after_merge = QCheckBox("合并完成后自动添加图框")
        self.add_frame_after_merge.setProperty("optionChoice", True)
        self.add_frame_after_merge.setChecked(
            self.user_settings.get_bool("merge/add_frame_after_merge", False)
        )
        self.add_frame_after_merge.setToolTip(
            "默认关闭。开启后先完成馈线合并，再复用现有“图框添加”处理器对最终合并结果添加图框；不会改变原馈线合并算法。"
        )
        post_layout.addWidget(self.add_frame_after_merge)
        self.merge_frame_selector = TemplateSelector(
            settings_prefix="merge/frame",
            settings_service=self.user_settings,
        )
        self.merge_frame_selector.setEnabled(self.add_frame_after_merge.isChecked())
        post_layout.addWidget(self.merge_frame_selector)
        frame_note = InfoBanner(
            "合并后处理顺序固定为：馈线合并 → Poke 跳转 → 图框。Poke 默认开启并直接复用现有 Poke 模块的 RMU、AR/LBS/SEC、站点跳转规则；"
            "图框仍为可选后处理，开启时使用所选模板，图框四边距沿用图框添加模块默认值 50。"
        )
        post_layout.addWidget(frame_note)
        self.layout.addWidget(post_box)

        output_name_box = QGroupBox("输出文件")
        output_name_form = QFormLayout(output_name_box)
        output_name_form.setHorizontalSpacing(16)
        output_name_form.setVerticalSpacing(10)
        output_name_form.addRow(HelpLabel("输出文件名", FIELD_HELP["output_name"]), self.output_name)
        self.layout.addWidget(output_name_box)

        self.task = TaskPanel()
        self.task.run_button.setText("开始合并")
        self.task.run_button.clicked.connect(self.run)
        self.layout.addWidget(self.task, 1)

        self.input_path.pathChanged.connect(self._input_path_changed)
        self.input_mode_combo.currentIndexChanged.connect(self._input_mode_changed)
        self.remote_source.prepared.connect(lambda path: self.file_order.set_input_dir(path))
        self.merge_main_bus.toggled.connect(self._on_merge_main_bus_toggled)
        self.add_frame_after_merge.toggled.connect(self.merge_frame_selector.setEnabled)
        self._configure_merge_source_mode()
        self._wrap_file_order_actions_for_remote()

    def _is_remote_input(self) -> bool:
        return str(self.input_mode_combo.currentData()) == "ssh"

    def _configure_merge_source_mode(self) -> None:
        remote = self._is_remote_input()
        self.local_input_page.setVisible(not remote)
        self.remote_source.setVisible(remote)
        self.local_input_page.updateGeometry()
        self.remote_source.updateGeometry()
        self.updateGeometry()
        self.user_settings.set_value("merge/input_source_mode", "ssh" if remote else "local")
        self.file_order.set_input_dir(self.remote_source.cache_dir() if remote else self.input_path.path())

    def _input_mode_changed(self, *_args) -> None:
        self._configure_merge_source_mode()

    def _active_input_dir(self, *, prepare_remote: bool = False) -> Path:
        if not self._is_remote_input():
            return Path(self.input_path.path())
        if prepare_remote:
            path = self.remote_source.prepare_selected()
            self.file_order.set_input_dir(path)
            return Path(path)
        return Path(self.remote_source.cache_dir())

    def _prepare_remote_for_file_order(self) -> bool:
        if not self._is_remote_input():
            self.file_order.set_input_dir(self.input_path.path())
            return True
        try:
            path = self._active_input_dir(prepare_remote=True)
            self.file_order.set_input_dir(path)
            return True
        except Exception as exc:
            QMessageBox.warning(self, "SSH 远程输入准备失败", str(exc))
            return False

    def _wrap_file_order_actions_for_remote(self) -> None:
        # FileOrderEditor 原按钮默认直接读取 input_dir。远程模式先把本次勾选文件
        # 下载为只读本地快照，再复用原来的检查/排序逻辑。
        try:
            self.file_order.refresh_button.clicked.disconnect()
        except Exception:
            pass
        self.file_order.refresh_button.clicked.connect(self._load_merge_candidates)
        try:
            self.file_order.import_button.clicked.disconnect()
        except Exception:
            pass
        self.file_order.import_button.clicked.connect(self._import_merge_candidates)
        try:
            self.file_order.natural_button.clicked.disconnect()
        except Exception:
            pass
        self.file_order.natural_button.clicked.connect(self._import_all_merge_candidates)

    def _load_merge_candidates(self) -> None:
        if self._prepare_remote_for_file_order():
            self.file_order.load_candidates()

    def _import_merge_candidates(self) -> None:
        if self._prepare_remote_for_file_order():
            self.file_order.open_import_dialog()

    def _import_all_merge_candidates(self) -> None:
        if self._prepare_remote_for_file_order():
            self.file_order.import_all_eligible()

    def _input_path_changed(self, text: str) -> None:
        self.file_order.set_input_dir(text)

    def _refresh_main_bus_visual_state(self) -> None:
        """Make the active main-bus choice visually unmistakable.

        Business rules and stored values are untouched; only the two action
        buttons change presentation according to the current UI state.
        """
        enabled = self.merge_main_bus.isChecked()
        mode_selected = enabled and self.main_bus_mode in {"single", "double"}
        if mode_selected:
            self.main_bus_mode_button.setStyleSheet(
                "QPushButton { background:#DFF3EA; color:#075B45; border:2px solid #0B7A5A; border-radius:7px; padding:7px 12px; font-weight:750; }"
                "QPushButton:hover { background:#D2EDE2; }"
                "QPushButton:pressed { background:#C4E5D8; }"
            )
        else:
            self.main_bus_mode_button.setStyleSheet(
                "QPushButton { background:#EEF3F2; color:#667B76; border:1px solid #C5D4D0; border-radius:7px; padding:7px 12px; font-weight:650; }"
                "QPushButton:disabled { background:#EEF3F2; color:#8A9A96; border-color:#D1DDDA; }"
            )

        grouped = enabled and bool(self.main_bus_groups)
        if grouped:
            self.main_bus_group_button.setStyleSheet(
                "QPushButton { background:#E8F2FF; color:#244E78; border:2px solid #5B8FC7; border-radius:7px; padding:7px 12px; font-weight:750; }"
                "QPushButton:hover { background:#DDECFB; }"
            )
        else:
            self.main_bus_group_button.setStyleSheet(
                "QPushButton { background:#F8FBFA; color:#29464D; border:1px solid #BFD4CD; border-radius:7px; padding:7px 12px; font-weight:650; }"
                "QPushButton:hover { border-color:#64AA93; background:#F1F9F6; }"
                "QPushButton:disabled { background:#EEF3F2; color:#8A9A96; border-color:#D1DDDA; }"
            )

    def _choose_main_bus_mode(self) -> bool:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("选择主母线类型")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("请选择当前参与合并的馈线图属于单母线还是双母线。")
        dialog.setInformativeText(
            "单母线：只检查 Y 值最小的最高有效水平 <Bus>。\n"
            "双母线：检查最高母线，以及同方向下方长度大致相同的第二条有效水平 <Bus>。"
        )
        single_button = dialog.addButton("单母线", QMessageBox.ButtonRole.AcceptRole)
        double_button = dialog.addButton("双母线", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is cancel_button:
            return False
        if clicked is double_button:
            self.main_bus_mode = "double"
            self.main_bus_mode_button.setText("母线类型：双母线")
        elif clicked is single_button:
            self.main_bus_mode = "single"
            self.main_bus_mode_button.setText("母线类型：单母线")
        else:
            return False
        self._refresh_main_bus_visual_state()
        return True

    def _on_merge_main_bus_toggled(self, checked: bool) -> None:
        self.main_bus_mode_button.setEnabled(checked)
        self.main_bus_group_button.setEnabled(checked)
        self._refresh_main_bus_visual_state()
        if not checked:
            self.main_bus_mode_button.setText("母线类型：未选择")
            self.main_bus_groups = []
            self.main_bus_group_button.setText("设置母线分组")
            self._refresh_main_bus_visual_state()
            return
        names = self.file_order.ordered_file_names()
        if not names:
            QMessageBox.warning(self, "主母线处理不可用", "请先加载并导入需要合并的馈线文件。")
            self.merge_main_bus.blockSignals(True)
            self.merge_main_bus.setChecked(False)
            self.merge_main_bus.blockSignals(False)
            self.main_bus_mode_button.setEnabled(False)
            self.main_bus_group_button.setEnabled(False)
            self._refresh_main_bus_visual_state()
            return
        if not self._choose_main_bus_mode():
            self.merge_main_bus.blockSignals(True)
            self.merge_main_bus.setChecked(False)
            self.merge_main_bus.blockSignals(False)
            self.main_bus_mode_button.setEnabled(False)
            self.main_bus_group_button.setEnabled(False)
            self.main_bus_mode_button.setText("母线类型：未选择")
            self._refresh_main_bus_visual_state()
            return
        self._edit_main_bus_groups()

    def _validate_manual_groups(self, names: list[str], groups: list[list[str]]) -> tuple[bool, str]:
        index = {name: i for i, name in enumerate(names)}
        seen: set[str] = set()
        for group_no, group in enumerate(groups, 1):
            if len(group) < 2:
                return False, f"母线组 {group_no} 至少需要 2 个馈线文件。"
            if any(name not in index for name in group):
                return False, f"母线组 {group_no} 包含已不在当前合并列表中的文件，请重新设置分组。"
            if any(name in seen for name in group):
                return False, f"母线组 {group_no} 中存在已经属于其他母线组的文件。"
            positions = sorted(index[name] for name in group)
            if positions != list(range(positions[0], positions[-1] + 1)):
                return False, f"母线组 {group_no} 的馈线必须在当前合并顺序中连续。"
            seen.update(group)
        return True, ""

    def _edit_main_bus_groups(self) -> None:
        names = self.file_order.ordered_file_names()
        if not names:
            QMessageBox.warning(self, "设置母线分组", "请先把馈线导入合并顺序列表。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("设置主母线人工分组")
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(InfoBanner("按当前馈线顺序选择连续的两行或多行，然后点击“创建母线组”。同组馈线将共用主母线；未分组馈线保持独立。分组完全由人工指定，不读取 keyid。"))
        # 分组顺序直接沿用馈线合并主列表的当前顺序。
        # 左侧垂直行号已经足够表达位置，不再重复显示“顺序”列，
        # 将空间优先留给完整文件名，避免文件名被压缩成省略号。
        table = QTableWidget(len(names), 2)
        table.setHorizontalHeaderLabels(["文件名", "母线组"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(36)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(120)
        configure_responsive_table(table)
        table.setObjectName("mainBusGroupTable")
        table.setAlternatingRowColors(True)
        table.setStyleSheet(
            "QTableWidget#mainBusGroupTable { selection-background-color:#DDF4EB; selection-color:#123B32; }"
            "QTableWidget#mainBusGroupTable::item:selected { background:#DDF4EB; color:#123B32; border-top:1px solid #79BBA5; border-bottom:1px solid #79BBA5; }"
            "QTableWidget#mainBusGroupTable::item:selected:!active { background:#E8F7F2; color:#123B32; }"
        )
        for row, name in enumerate(names):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem("未分组"))
        layout.addWidget(table, 1)
        working = [list(group) for group in self.main_bus_groups]

        def refresh() -> None:
            membership = {}
            for gi, group in enumerate(working, 1):
                for name in group:
                    membership[name] = gi
            for row, name in enumerate(names):
                grouped = name in membership
                group_item = table.item(row, 1)
                group_item.setText(f"组{membership[name]}" if grouped else "未分组")
                # Keep already-created bus groups visible even after the active
                # row selection moves elsewhere.  The active selection still uses
                # the stronger mint highlight defined on the table stylesheet.
                row_background = QColor("#EDF8F4") if grouped else QColor("#FFFFFF")
                row_foreground = QColor("#123B32") if grouped else QColor("#29464D")
                for column in range(2):
                    item = table.item(row, column)
                    if item is None:
                        continue
                    item.setBackground(row_background)
                    item.setForeground(row_foreground)
                group_font = group_item.font()
                group_font.setBold(grouped)
                group_item.setFont(group_font)

        refresh()
        actions = QHBoxLayout()
        create_btn = QPushButton("创建母线组")
        clear_selected_btn = QPushButton("清除所选分组")
        clear_all_btn = QPushButton("清空全部分组")
        # 分组弹窗中的操作按钮使用更高对比度的独立样式，避免浅色背景下文字看不清。
        create_btn.setStyleSheet(
            "QPushButton { background:#0B7A5A; color:#FFFFFF; border:none; border-radius:7px; padding:8px 16px; font-weight:700; }"
            "QPushButton:hover { background:#08684D; }"
            "QPushButton:pressed { background:#07553F; }"
            "QPushButton:disabled { background:#6F8F87; color:#F7FAF9; }"
        )
        clear_selected_btn.setStyleSheet(
            "QPushButton { background:#5C7771; color:#FFFFFF; border:1px solid #4D6862; border-radius:7px; padding:8px 16px; font-weight:700; }"
            "QPushButton:hover { background:#4C6862; }"
            "QPushButton:pressed { background:#3F5954; }"
            "QPushButton:disabled { background:#829791; color:#F7FAF9; border-color:#748A84; }"
        )
        clear_all_btn.setStyleSheet(
            "QPushButton { background:#A64A4C; color:#FFFFFF; border:none; border-radius:7px; padding:8px 16px; font-weight:700; }"
            "QPushButton:hover { background:#913E40; }"
            "QPushButton:pressed { background:#7C3436; }"
            "QPushButton:disabled { background:#A77A7B; color:#FFF8F8; }"
        )
        actions.addWidget(create_btn); actions.addWidget(clear_selected_btn); actions.addWidget(clear_all_btn); actions.addStretch(1)
        layout.addLayout(actions)

        def selected_names() -> list[str]:
            rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
            return [names[row] for row in rows]

        def create_group() -> None:
            selected = selected_names()
            if len(selected) < 2:
                QMessageBox.warning(dialog, "创建母线组", "请至少选择 2 个连续馈线。")
                return
            positions = [names.index(name) for name in selected]
            if positions != list(range(min(positions), max(positions) + 1)):
                QMessageBox.warning(dialog, "创建母线组", "同一母线组中的馈线必须连续。")
                return
            working[:] = [[n for n in group if n not in selected] for group in working]
            working[:] = [group for group in working if len(group) >= 2]
            working.append(selected)
            working.sort(key=lambda g: names.index(g[0]))
            refresh()

        def clear_selected() -> None:
            selected = set(selected_names())
            if not selected:
                return
            working[:] = [[n for n in group if n not in selected] for group in working]
            working[:] = [group for group in working if len(group) >= 2]
            refresh()

        create_btn.clicked.connect(create_group)
        clear_selected_btn.clicked.connect(clear_selected)
        clear_all_btn.clicked.connect(lambda: (working.clear(), refresh()))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ok, message = self._validate_manual_groups(names, working)
        if not ok:
            QMessageBox.warning(self, "母线分组无效", message)
            return
        self.main_bus_groups = working
        self.main_bus_group_button.setText(f"设置母线分组（{len(working)}组）")
        self._refresh_main_bus_visual_state()
        summary = "\n".join(f"组{i}: {group[0]} ～ {group[-1]}（{len(group)}个）" for i, group in enumerate(working, 1)) or "未设置任何组；所有馈线母线保持独立。"
        QMessageBox.information(self, "主母线人工分组", f"当前母线类型：{'双母线' if self.main_bus_mode == 'double' else '单母线'}\n\n{summary}")

    @staticmethod
    def spin(value: int) -> IntegerInput:
        return IntegerInput(value=value, minimum=0, maximum=100000)

    def _shared_poke_rmu_settings(self) -> tuple[tuple[str, ...], str, str]:
        positions = tuple(
            key for key, default in (("top", True), ("bottom", False), ("left", False), ("right", False))
            if self.user_settings.get_bool(f"basic/rmu/name_{key}", default)
        )
        if not positions:
            positions = ("top",)
        exclusions = self.user_settings.get_value("basic/rmu/name_exclusions", "").strip()
        markers = self.user_settings.get_value("basic/rmu/intelligent_markers", "SMART, SMR").strip() or "SMART, SMR"
        return positions, exclusions, markers

    def _classification_marker_entries(self) -> list[tuple[str, str, str]]:
        """Reuse only the already-synced local server-symbol cache; never query SSH here."""
        try:
            host = self.user_settings.get_value("remote_g_source/host", "").strip()
            root = self.user_settings.get_value(
                "site_profile/remote_symbol_library_root", DEFAULT_REMOTE_SYMBOL_ROOT
            ).strip() or DEFAULT_REMOTE_SYMBOL_ROOT
            if not host or not root:
                return []
            entries = RemoteSymbolLibraryService().load_classification_marker_entries(
                host=host,
                root=root,
            )
            return [
                (
                    str(entry.get("file_name", "") or ""),
                    str(entry.get("devref", "") or ""),
                    str(entry.get("classification_marker", "") or ""),
                )
                for entry in entries
                if str(entry.get("classification_marker", "") or "").strip()
            ]
        except Exception:
            return []

    def settings(self) -> MergeSettings:
        poke_positions, poke_exclusions, poke_markers = self._shared_poke_rmu_settings()
        return MergeSettings(
            input_dir=self._active_input_dir(),
            output_dir=self.output_path.path(),
            output_name=self.output_name.text(),
            ordered_file_names=self.file_order.ordered_file_names(),
            feeder_gap=self.gap.value(),
            feeder_min_width=self.feeder_min_width.value(),
            merge_main_bus=self.merge_main_bus.isChecked(),
            main_bus_mode=self.main_bus_mode,
            main_bus_groups=self.main_bus_groups,
            left_margin=self.left.value(),
            top_margin=self.top.value(),
            right_margin=self.right.value(),
            bottom_margin=self.bottom.value(),
            add_poke_after_merge=self.add_poke_after_merge.isChecked(),
            poke_rmu_name_positions=poke_positions,
            poke_rmu_name_exclusions=poke_exclusions,
            poke_rmu_intelligent_markers=poke_markers,
            poke_classification_marker_entries=(
                self._classification_marker_entries()
                if self.add_poke_after_merge.isChecked()
                else []
            ),
            add_frame_after_merge=self.add_frame_after_merge.isChecked(),
            frame_template_file=(
                self.merge_frame_selector.resolved_template_path()
                if self.add_frame_after_merge.isChecked()
                else None
            ),
            frame_template_mode=self.merge_frame_selector.mode(),
            frame_builtin_template_id=self.merge_frame_selector.builtin_template_id(),
            frame_left=50,
            frame_top=50,
            frame_right=50,
            frame_bottom=50,
        )

    def save_state(self) -> None:
        self.input_path.persist_current_text()
        self.remote_source.persist()
        self.user_settings.set_value("merge/input_source_mode", "ssh" if self._is_remote_input() else "local")
        self.output_path.persist_current_text()
        self.user_settings.set_value("merge/add_poke_after_merge", self.add_poke_after_merge.isChecked())
        self.user_settings.set_value("merge/add_frame_after_merge", self.add_frame_after_merge.isChecked())
        self.merge_frame_selector.persist_current()

    def run(self) -> None:
        if self._is_remote_input():
            if not self._prepare_remote_for_file_order():
                return
        else:
            if not validate_existing_directory(self, self.input_path.path(), "馈线图合并输入目录"):
                return
            self.input_path.persist_valid_path()
        # Managed workspace output is recreated by begin_managed_run().
        self.remote_source.persist()
        if self.add_frame_after_merge.isChecked() and not self.merge_frame_selector.validate_selection():
            return
        self.user_settings.set_value("merge/add_poke_after_merge", self.add_poke_after_merge.isChecked())
        self.user_settings.set_value("merge/add_frame_after_merge", self.add_frame_after_merge.isChecked())
        run_dir = begin_managed_run(self.output_path, "merge", "merge")
        self.file_order.set_input_dir(self._active_input_dir())
        if not self.file_order.ensure_ready():
            return
        settings = self.settings()
        self.task.start(
            lambda log, progress: merge_feeders(
                settings,
                log,
                progress,
                database_service=self.database_service,
            ),
            settings.output_dir,
        )
