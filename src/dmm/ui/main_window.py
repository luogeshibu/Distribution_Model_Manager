#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QPlainTextEdit, QFrame, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QListWidget, QListWidgetItem, QGroupBox, QTabWidget, QScrollArea, QSizePolicy,
    QProgressBar, QSplitter, QDialog, QTextBrowser, QDialogButtonBox
)

from dmm.application.job_worker import JobWorker
from dmm.application.registry import get_model_modules
from dmm.ui.registry import create_settings_widget
from dmm.config.constants import (
    APP_NAME, APP_NAME_EN, APP_VERSION, APP_EDITION,
    WORKSPACE_RETENTION_DAYS,
)
from dmm.config.settings import load_settings, save_settings
from dmm.infrastructure.database.oracle import OracleClient
from dmm.infrastructure.reporting.writer import (
    flatten_device_rows, flatten_rmu_rows,
    export_csv_bundle, export_html_bundle,
    DEVICE_FIELDS, RMU_FIELDS, DEVICE_LABELS, RMU_LABELS,
)
from dmm.infrastructure.filesystem.workspace import (
    WORKSPACE_ROOT,
    LOGS_ROOT,
    ensure_workspace,
    cleanup_workspace,
    create_run_directory,
    append_database_log,
)


# Windows taskbar/app identity
if sys.platform.startswith("win"):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"StateGrid.DistributionModelManager.{APP_VERSION}"
        )
    except Exception:
        pass


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "dmm" / "resources"
else:
    APP_DIR = Path(__file__).resolve().parents[2]
    RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"

LOGO_PATH = RESOURCE_DIR / "app_logo.png"
ICON_PATH = RESOURCE_DIR / "app_logo.ico"


def apply_status_style(label: QLabel, ok: bool):
    label.setObjectName("statusOK" if ok else "statusBAD")
    label.style().unpolish(label)
    label.style().polish(label)


class NoWheelComboBox(QComboBox):
    """禁止滚轮误切换选项，点击下拉选择仍正常。"""

    def wheelEvent(self, event):
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ensure_workspace()
        cleanup_workspace(WORKSPACE_RETENTION_DAYS)

        self.cfg = load_settings()
        self.modules = get_model_modules()
        self.module_widgets = {}

        self.current_rules = {}
        self.current_preview = None
        self.current_artifacts = {}
        self.current_report_dir = self.cfg.get("last_run_dir", "")
        self.current_task_type = ""
        self.worker = None

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} - {APP_EDITION}")
        self.resize(1600, 960)
        self.setMinimumSize(1280, 800)

        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._build_ui()
        self._apply_style()
        self._restore_ui_state()
        self._check_saved_input_path_on_startup()

        self.log(f"{APP_NAME} v{APP_VERSION} 已启动。")
        self.log("工作流：模型校验 → 勾选可关联对象 → 执行模型关联。")
        self.log("安全模式：原始 G 文件永不修改；执行关联时只处理 Workspace 中的安全副本。")

    # ------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------
    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow {
            background: #F1F6F3;
        }

        QWidget {
            font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
            font-size: 10pt;
            color: #17372E;
        }

        #header {
            background: #006B52;
            border-bottom: 4px solid #00B578;
        }

        #headerTitle {
            color: white;
            font-size: 23pt;
            font-weight: 700;
        }

        #headerSub {
            color: #D8EEE6;
        }

        #brandTag {
            color: #72E6B7;
            font-weight: 700;
            letter-spacing: 1px;
        }

        #sideNav {
            background: #005B46;
            border: none;
        }

        QListWidget#navList {
            background: #005B46;
            color: #D8EEE6;
            border: none;
            outline: 0;
            font-size: 10.5pt;
        }

        QListWidget#navList::item {
            padding: 14px 16px;
            border-radius: 7px;
            margin: 3px 7px;
        }

        QListWidget#navList::item:selected {
            background: #00966E;
            color: white;
        }

        QListWidget#navList::item:hover {
            background: #00785B;
        }

        #pageTitle {
            color: #006B52;
            font-size: 18pt;
            font-weight: 700;
        }

        #pageSub {
            color: #667C74;
        }

        QGroupBox {
            background: white;
            border: 1px solid #CFE0D9;
            border-radius: 10px;
            margin-top: 16px;
            padding-top: 8px;
            font-weight: 700;
            color: #005F49;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 1px;
            padding: 0 7px;
            background: #F1F6F3;
        }

        QScrollArea#workspaceScroll,
        QScrollArea#workspaceOuterScroll {
            background: transparent;
            border: none;
        }

        QScrollArea#workspaceScroll > QWidget > QWidget,
        QScrollArea#workspaceOuterScroll > QWidget > QWidget {
            background: transparent;
        }

        QScrollBar:vertical {
            background: #E6F0EC;
            width: 14px;
            margin: 2px 2px 2px 2px;
            border-radius: 7px;
        }

        QScrollBar::handle:vertical {
            background: #7EB5A1;
            min-height: 42px;
            border-radius: 6px;
        }

        QScrollBar::handle:vertical:hover {
            background: #00966E;
        }

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }

        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: transparent;
        }

        QLineEdit,
        QComboBox,
        QSpinBox {
            background: white;
            border: 1px solid #AFC8BE;
            border-radius: 6px;
            padding: 6px 8px;
            min-height: 25px;
            selection-background-color: #00966E;
        }

        QLineEdit:focus,
        QComboBox:focus,
        QSpinBox:focus {
            border: 1px solid #00966E;
        }

        /* 保留 QSpinBox 原生上下按钮，保证按钮可点击 */
        QSpinBox::up-button,
        QSpinBox::down-button {
            width: 26px;
            border-left: 1px solid #B7CCC4;
            background: #F3F8F6;
        }

        QSpinBox::up-button:hover,
        QSpinBox::down-button:hover {
            background: #DFF2EA;
        }

        QSpinBox::up-button:pressed,
        QSpinBox::down-button:pressed {
            background: #BFE5D6;
        }

        QPushButton {
            background: #F8FBFA;
            border: 1px solid #B5CCC3;
            border-radius: 7px;
            padding: 7px 13px;
            font-weight: 600;
        }

        QPushButton:hover {
            background: #EAF5F0;
            border-color: #7EB5A1;
        }

        QPushButton:pressed {
            background: #00966E;
            color: white;
            border-color: #00785B;
        }

        QPushButton:focus {
            border: 1px solid #00966E;
        }

        QPushButton#primary {
            background: #00966E;
            color: white;
            border: none;
            min-height: 34px;
        }

        QPushButton#primary:hover {
            background: #007F5E;
        }

        QPushButton#secondary {
            background: #006B52;
            color: white;
            border: none;
        }

        QPushButton#danger {
            background: #B42318;
            color: white;
            border: none;
        }

        QPushButton:disabled {
            background: #CDD9D4;
            color: #778880;
        }

        QLabel#statusOK {
            color: #006E50;
            background: #E5F7EF;
            border: 1px solid #AFE2CE;
            padding: 7px 10px;
            border-radius: 7px;
            font-weight: 700;
        }

        QLabel#statusBAD {
            color: #B42318;
            background: #FFF1F0;
            border: 1px solid #F0C5C1;
            padding: 7px 10px;
            border-radius: 7px;
            font-weight: 700;
        }

        QLabel#moduleDescription {
            background: #F1F8F5;
            color: #587269;
            border: 1px solid #D7E8E1;
            border-radius: 7px;
            padding: 9px;
        }

        QPlainTextEdit {
            background: #082820;
            color: #D9F4E9;
            border: 1px solid #13503F;
            border-radius: 8px;
            font-family: Consolas, "Microsoft YaHei UI";
            font-size: 9.5pt;
        }

        #metricCard {
            background: white;
            border: 1px solid #CFE0D9;
            border-radius: 9px;
        }

        #metricTitle {
            color: #688077;
            font-size: 9pt;
        }

        #metricValue {
            color: #006B52;
            font-size: 20pt;
            font-weight: 700;
        }

        QTableWidget {
            background: white;
            alternate-background-color: #F5FAF8;
            border: 1px solid #CFE0D9;
            gridline-color: #DDE9E4;
        }

        QHeaderView::section {
            background: #006B52;
            color: white;
            border: 0;
            border-right: 1px solid #3A806C;
            padding: 7px;
            font-weight: 600;
        }

        QProgressBar {
            border: 1px solid #AFC8BE;
            border-radius: 7px;
            background: white;
            text-align: center;
            min-height: 24px;
            font-weight: 600;
            color: #17372E;
        }

        QProgressBar::chunk {
            background: #00966E;
            border-radius: 6px;
        }

        QTabWidget::pane {
            border: 1px solid #CFE0D9;
            background: white;
        }

        QTabBar::tab {
            background: #E9F2EE;
            padding: 8px 18px;
            margin-right: 2px;
        }

        QTabBar::tab:selected {
            background: #00966E;
            color: white;
        }
        """)

    # ------------------------------------------------------------
    # Common widgets
    # ------------------------------------------------------------
    def _page_header(self, title, sub):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 8)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")

        sub_label = QLabel(sub)
        sub_label.setObjectName("pageSub")
        sub_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(sub_label)
        return widget

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(112)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 15, 28, 15)

        if LOGO_PATH.exists():
            logo = QLabel()
            pixmap = QPixmap(str(LOGO_PATH))
            logo.setPixmap(
                pixmap.scaled(
                    78, 78,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            logo.setFixedSize(82, 82)
            header_layout.addWidget(logo)

        titles = QVBoxLayout()

        brand = QLabel("NARI国际业务部内部工具")
        brand.setObjectName("brandTag")

        title = QLabel(APP_NAME)
        title.setObjectName("headerTitle")

        subtitle = QLabel(
            f"{APP_NAME_EN} · 模型校验 · 校验候选 · 安全回写"
        )
        subtitle.setObjectName("headerSub")

        titles.addStretch()
        titles.addWidget(brand)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        titles.addStretch()

        header_layout.addLayout(titles, 1)

        version = QLabel(f"{APP_EDITION}  |  v{APP_VERSION}")
        version.setObjectName("headerSub")
        header_layout.addWidget(
            version,
            alignment=Qt.AlignRight | Qt.AlignVCenter,
        )

        root.addWidget(header)

        # Main body
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body = QWidget()
        body.setLayout(body_layout)
        root.addWidget(body, 1)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sideNav")
        sidebar.setFixedWidth(238)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 12, 0, 12)

        self.nav = QListWidget()
        self.nav.setObjectName("navList")

        for label in ("数据库", "模型工作区", "设置", "帮助"):
            self.nav.addItem(QListWidgetItem(label))

        self.nav.setCurrentRow(1)
        sidebar_layout.addWidget(self.nav)
        body_layout.addWidget(sidebar)

        # 每个功能模块自带日志/结果，不再设置独立的全局“报告”一级菜单。
        self.pages = QStackedWidget()
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)

        self.pages.addWidget(self._build_database_page())
        self.pages.addWidget(self._build_workspace_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(self._build_help_page())

        self.pages.setCurrentIndex(1)
        body_layout.addWidget(self.pages, 1)

    # ------------------------------------------------------------
    # Database page
    # ------------------------------------------------------------
    def _build_database_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)

        layout.addWidget(
            self._page_header(
                "数据库",
                "Oracle 数据库作为独立公共模块。数据库测试日志只显示在本模块中。",
            )
        )

        box = QGroupBox("Oracle 数据库连接")
        grid = QGridLayout(box)

        self.db_edits = {}
        fields = [
            ("user", "用户名"),
            ("password", "密码"),
            ("host", "服务器地址"),
            ("port", "端口"),
            ("service_name", "Service Name"),
        ]

        for row, (key, label) in enumerate(fields):
            grid.addWidget(QLabel(label), row, 0)
            edit = QLineEdit(str(self.cfg["db"].get(key, "")))
            if key == "password":
                edit.setEchoMode(QLineEdit.Password)
            grid.addWidget(edit, row, 1)
            self.db_edits[key] = edit

        layout.addWidget(box)

        actions = QHBoxLayout()
        test_btn = QPushButton("测试数据库连接")
        test_btn.clicked.connect(self.test_connection)

        save_btn = QPushButton("保存数据库配置")
        save_btn.clicked.connect(self.save_database_settings)

        actions.addWidget(test_btn)
        actions.addWidget(save_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.db_status = QLabel("尚未验证")
        apply_status_style(self.db_status, False)
        layout.addWidget(self.db_status)

        log_box = QGroupBox("数据库运行日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()

        copy_btn = QPushButton("复制日志")
        clear_btn = QPushButton("清空日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.db_log_edit.toPlainText())
        )
        clear_btn.clicked.connect(lambda: self.db_log_edit.clear())

        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch()
        log_layout.addLayout(log_actions)

        self.db_log_edit = QPlainTextEdit()
        self.db_log_edit.setReadOnly(True)
        log_layout.addWidget(self.db_log_edit, 1)
        layout.addWidget(log_box, 1)

        return page

    # ------------------------------------------------------------
    # Workspace
    # ------------------------------------------------------------
    def _build_workspace_page(self):
        """
        模型工作区采用“整页滚动”设计。

        重要原则：
        - RMU/Feeder 配置区域自身不使用 QScrollArea；
        - 不再用垂直 Splitter 压缩模型配置；
        - 只在页面最外层提供一个纵向滚动条；
        - 所有模块按自然高度完整展开；
        - Console 日志保留自身文本滚动，这是日志控件的正常行为，
          但不会影响上方模型配置的完整显示。
        """
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        outer_scroll = QScrollArea()
        outer_scroll.setObjectName("workspaceOuterScroll")
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setFrameShape(QFrame.NoFrame)
        outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content.setObjectName("workspaceContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)

        layout.addWidget(
            self._page_header(
                "模型工作区",
                "模型配置、处理进度和 Console 运行日志集中在当前工作区；任务完成后自动生成 HTML / CSV 报告。",
            )
        )

        # --------------------------------------------------------
        # 模型任务
        # --------------------------------------------------------
        job_box = QGroupBox("模型任务")
        grid = QGridLayout(job_box)
        grid.setContentsMargins(14, 18, 14, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("模型类型"), 0, 0)
        self.module_combo = NoWheelComboBox()
        for module_id, module in self.modules.items():
            self.module_combo.addItem(module.display_name, module_id)
        self.module_combo.currentIndexChanged.connect(self.on_module_changed)
        grid.addWidget(self.module_combo, 0, 1, 1, 2)

        self.module_help_btn = QPushButton("当前模型帮助")
        self.module_help_btn.setMinimumWidth(112)
        self.module_help_btn.clicked.connect(self.show_current_module_help)
        grid.addWidget(self.module_help_btn, 0, 3)

        grid.addWidget(QLabel("G 文件 / 目录"), 1, 0)
        self.input_edit = QLineEdit(self.cfg.get("input_path", ""))
        self.input_edit.setPlaceholderText("请选择一个 G 文件，或包含 G 文件的目录")
        self.input_edit.editingFinished.connect(self._save_input_path_from_edit)
        grid.addWidget(self.input_edit, 1, 1)

        file_btn = QPushButton("选择文件")
        folder_btn = QPushButton("选择目录")
        file_btn.setMinimumWidth(100)
        folder_btn.setMinimumWidth(100)
        file_btn.clicked.connect(self.browse_file)
        folder_btn.clicked.connect(self.browse_folder)
        grid.addWidget(file_btn, 1, 2)
        grid.addWidget(folder_btn, 1, 3)

        self.workspace_status = QLabel("执行前需要进行 Oracle 预检查。")
        apply_status_style(self.workspace_status, False)
        grid.addWidget(self.workspace_status, 2, 0, 1, 4)

        safe_notice = QLabel(
            "安全说明：原始 G 文件始终保持不变。执行模型关联时，会先复制全部选中 G 文件到本软件 Workspace，再只修改安全副本。"
        )
        safe_notice.setWordWrap(True)
        safe_notice.setStyleSheet(
            "background:#E8F7F1; color:#006B52; border:1px solid #A9DCC8; "
            "border-radius:7px; padding:8px 10px; font-weight:600;"
        )
        grid.addWidget(safe_notice, 3, 0, 1, 4)

        ws_row = QHBoxLayout()
        ws_row.addWidget(QLabel("Workspace"))
        ws_path = QLineEdit(str(WORKSPACE_ROOT))
        ws_path.setReadOnly(True)
        ws_row.addWidget(ws_path, 1)
        ws_btn = QPushButton("打开 Workspace")
        ws_btn.clicked.connect(self.open_workspace)
        ws_row.addWidget(ws_btn)
        ws_holder = QWidget()
        ws_holder.setLayout(ws_row)
        grid.addWidget(ws_holder, 4, 0, 1, 4)

        layout.addWidget(job_box)

        # --------------------------------------------------------
        # 模型专属配置：完整展开，不使用局部滚动条
        # --------------------------------------------------------
        self.module_stack = QStackedWidget()
        self.module_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

        for module_id, module in self.modules.items():
            widget = create_settings_widget(
                module_id,
                self.module_stack,
                self.cfg,
            )
            widget.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Preferred,
            )
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16777215)
            self.module_widgets[module_id] = widget
            self.module_stack.addWidget(widget)

        # 根据当前页面的 sizeHint 自动给 stack 足够高度，避免内部控件被裁剪。
        self.module_stack.currentChanged.connect(self._update_module_stack_height)
        layout.addWidget(self.module_stack)

        # --------------------------------------------------------
        # 任务进度
        # --------------------------------------------------------
        progress_box = QGroupBox("任务进度")
        progress_layout = QVBoxLayout(progress_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.progress_message = QLabel("等待执行任务")
        self.progress_message.setStyleSheet("color:#60756d;")

        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_message)
        layout.addWidget(progress_box)

        # --------------------------------------------------------
        # RMU 模型校验后的可选择关联设备明细
        # --------------------------------------------------------
        self.association_selection_box = QGroupBox(
            "可关联设备选择（模型校验结果）"
        )
        selection_layout = QVBoxLayout(self.association_selection_box)
        selection_layout.setContentsMargins(12, 16, 12, 12)
        selection_layout.setSpacing(8)

        self.association_selection_tip = QLabel(
            "模型校验完成后，这里展示 G 文件设备明细。"
            "只有数据库当前事实已经唯一确定、并且需要关联或重新关联的设备"
            "才允许勾选。PASS / FAIL / BLOCKED 行不会被误关联。"
            "执行模型关联时只处理你勾选的设备。"
        )
        self.association_selection_tip.setWordWrap(True)
        self.association_selection_tip.setStyleSheet(
            "color:#315B4F; background:#F3F8F6; "
            "border:1px solid #D0E2DA; border-radius:6px; padding:7px 9px;"
        )
        selection_layout.addWidget(self.association_selection_tip)

        filter_row = QHBoxLayout()
        self.association_filter_label = QLabel("环网柜名称筛选")
        filter_row.addWidget(self.association_filter_label)
        self.rmu_filter_edit = QLineEdit()
        self.rmu_filter_edit.setPlaceholderText(
            "输入环网柜名称快速筛选，例如：17613 / RMU-42646"
        )
        self.rmu_filter_edit.setClearButtonEnabled(True)
        self.rmu_filter_edit.textChanged.connect(
            self._apply_rmu_name_filter
        )
        filter_row.addWidget(self.rmu_filter_edit, 1)

        clear_filter_btn = QPushButton("清除筛选")
        clear_filter_btn.clicked.connect(
            lambda: self.rmu_filter_edit.clear()
        )
        filter_row.addWidget(clear_filter_btn)
        selection_layout.addLayout(filter_row)

        selection_actions = QHBoxLayout()
        self.selection_count_label = QLabel("已选择 0 个设备")
        self.select_all_assoc_btn = QPushButton("全选可关联")
        self.clear_assoc_selection_btn = QPushButton("清空选择")
        self.select_all_assoc_btn.clicked.connect(
            self._select_all_association_candidates
        )
        self.clear_assoc_selection_btn.clicked.connect(
            self._clear_association_selection
        )
        selection_actions.addWidget(self.selection_count_label)
        selection_actions.addStretch(1)
        selection_actions.addWidget(self.select_all_assoc_btn)
        selection_actions.addWidget(self.clear_assoc_selection_btn)
        selection_layout.addLayout(selection_actions)

        self.association_table = QTableWidget()
        self.association_table.setColumnCount(12)
        self.association_table.setHorizontalHeaderLabels([
            "选择",
            "G文件",
            "环网柜序号",
            "环网柜名称",
            "G图元类型",
            "逻辑设备名称（图上规则）",
            "数据库CODE",
            "状态",
            "当前关联",
            "目标设备ID",
            "Expected KeyID",
            "处理说明",
        ])
        self.association_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.association_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.association_table.setAlternatingRowColors(False)
        self.association_table.setWordWrap(False)
        self.association_table.setTextElideMode(Qt.ElideRight)
        self.association_table.setMinimumHeight(260)
        self.association_table.setMaximumHeight(460)

        vertical_header = self.association_table.verticalHeader()
        vertical_header.setVisible(False)
        vertical_header.setMinimumSectionSize(38)
        vertical_header.setDefaultSectionSize(38)
        vertical_header.setSectionResizeMode(QHeaderView.Fixed)

        header = self.association_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(11, QHeaderView.Stretch)
        self.association_table.itemChanged.connect(
            self._on_association_selection_changed
        )
        selection_layout.addWidget(self.association_table)

        self.association_selection_box.setVisible(False)
        self._association_table_populating = False
        self._association_candidate_keys = set()
        layout.addWidget(self.association_selection_box)

        # --------------------------------------------------------
        # Console 日志 + 自动报告入口
        # --------------------------------------------------------
        log_box = QGroupBox("本次运行 Console 日志")
        log_layout = QVBoxLayout(log_box)

        log_actions = QHBoxLayout()
        copy_log_btn = QPushButton("复制日志")
        clear_log_btn = QPushButton("清空日志")

        self.open_html_btn = QPushButton("打开 HTML")
        self.open_rmu_csv_btn = QPushButton("打开环网柜 CSV")
        self.open_device_csv_btn = QPushButton("打开设备 CSV")
        self.open_report_dir_btn = QPushButton("打开本次运行目录")

        copy_log_btn.clicked.connect(self.copy_log)
        clear_log_btn.clicked.connect(lambda: self.log_edit.clear())
        self.open_html_btn.clicked.connect(lambda: self.open_artifact("html"))
        self.open_rmu_csv_btn.clicked.connect(lambda: self.open_artifact("rmu_csv"))
        self.open_device_csv_btn.clicked.connect(lambda: self.open_artifact("device_csv"))
        self.open_report_dir_btn.clicked.connect(self.open_current_run_dir)

        for button in (
            self.open_html_btn,
            self.open_rmu_csv_btn,
            self.open_device_csv_btn,
            self.open_report_dir_btn,
        ):
            button.setEnabled(False)
            button.setVisible(False)

        log_actions.addWidget(copy_log_btn)
        log_actions.addWidget(clear_log_btn)
        log_actions.addStretch()
        log_actions.addWidget(self.open_html_btn)
        log_actions.addWidget(self.open_rmu_csv_btn)
        log_actions.addWidget(self.open_device_csv_btn)
        log_actions.addWidget(self.open_report_dir_btn)
        log_layout.addLayout(log_actions)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(260)
        self.log_edit.setMaximumHeight(420)
        log_layout.addWidget(self.log_edit)

        layout.addWidget(log_box)

        # --------------------------------------------------------
        # 底部操作按钮
        # --------------------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(12)

        self.validate_btn = QPushButton("模型校验")
        self.validate_btn.setObjectName("primary")
        self.validate_btn.clicked.connect(
            lambda: self.start_job("VALIDATE")
        )

        self.apply_btn = QPushButton("执行模型关联")
        self.apply_btn.setObjectName("danger")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_association)

        database_btn = QPushButton("数据库设置")
        database_btn.setObjectName("secondary")
        database_btn.clicked.connect(lambda: self.nav.setCurrentRow(0))

        for button in (
            self.validate_btn,
            self.apply_btn,
            database_btn,
        ):
            button.setFixedSize(168, 42)

        actions.addWidget(self.validate_btn)
        actions.addWidget(self.apply_btn)
        actions.addWidget(database_btn)
        actions.addStretch()

        layout.addLayout(actions)
        layout.addStretch(1)

        outer_scroll.setWidget(content)
        page_layout.addWidget(outer_scroll)

        # 保存引用，模块切换时可调整完整高度。
        self.workspace_outer_scroll = outer_scroll
        self.workspace_content = content

        # 初始高度在事件循环进入后再计算一次。
        QTimer.singleShot(0, self._update_module_stack_height)

        return page

    def _update_module_stack_height(self, *_args):
        """
        当前模块始终横向铺满工作区，纵向使用自然高度。
        模块自身不产生滚动条，只由工作区最外层 QScrollArea 滚动。
        """
        if not hasattr(self, "module_stack"):
            return

        widget = self.module_stack.currentWidget()
        if widget is None:
            return

        # 清除上一模块残留的固定高度。
        self.module_stack.setMinimumHeight(0)
        self.module_stack.setMaximumHeight(16777215)

        widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)

        # 先按当前 stack 的真实宽度布局，WordWrap 标签才能得到正确高度。
        available_width = self.module_stack.width()
        if hasattr(self, "workspace_content"):
            available_width = max(
                available_width,
                self.workspace_content.width() - 56,
            )
        available_width = max(available_width, 800)

        widget.resize(
            available_width,
            max(widget.height(), 1),
        )

        if widget.layout() is not None:
            widget.layout().invalidate()
            widget.layout().activate()

        widget.adjustSize()

        hint = widget.sizeHint()
        minimum = widget.minimumSizeHint()
        height = max(
            hint.height(),
            minimum.height(),
            280,
        )

        # DPI / GroupBox 标题留出少量余量。
        final_height = height + 18
        self.module_stack.setMinimumHeight(final_height)
        self.module_stack.setMaximumHeight(final_height)

        self.module_stack.updateGeometry()
        widget.updateGeometry()
        if hasattr(self, "workspace_content"):
            self.workspace_content.updateGeometry()

    def _current_module_help_html(self):
        module_id = str(self.module_combo.currentData() or "RMU").upper()

        if module_id == "FEEDER":
            return """
            <h2>馈线模型帮助</h2>

            <h3>1. 馈线归属：RMU 拓扑规则</h3>
            <p><b>核心原则：</b>馈线模型不再通过馈线名称判断归属，而是先利用已经能够可靠确认的 RMU 作为锚点，从 RMU 的数据库 FEEDER_ID 反推出当前连接区域所属馈线，再处理该区域内的 FeedLine。</p>
            <ol>
              <li>单馈线图和组合大图使用完全相同的算法，不再依赖 ABH-03 / AJWD-07 等馈线文字。</li>
              <li>程序先解析 G 图中的 RMU、FeedLine、ConnectLine、Bus 及主要开关图元，建立连接拓扑区域。</li>
              <li><b>RMU 结构硬条件：</b>候选矩形框内部必须同时至少存在 1 个 CBreakerDis、1 个 ZhaiWaiJieDiDaoZha、1 个 BusDis，缺少任意一类都不识别为环网柜。</li>
              <li>馈线模块复用 RMU 模块同一套柜型识别：柜内 Y1/Y2/Y3/Y4… 每个计 1 个 L，Q1/Q2/Q3/Q4… 每个计 1 个 T；<b>只要识别到任何 Y/Q 文字，就绝对以文字结果为准</b>。只有完全识别不到 Y/Q 时才使用 devref 中 Load_Breaker / Circuit_Breaker 兜底。</li>
              <li>SMART / SMR 在整张 G 图全局识别，并分别归属最近的 RMU；任意一个标识命中即为智能环网柜，SMART 与 SMR 同时命中仍记为一个“智能环网柜”。馈线可信 RMU 日志同时显示柜型和智能属性。</li>
              <li>RMU 柜名与 RMU 模块使用完全相同的识别结果：严格只看用户勾选方向，在整张 G 图全局寻找 Text / DText；每个文字只归属最近一个 RMU，不再使用旧的 120 坐标单位距离上限。</li>
              <li>只有数据库名称唯一、存在 FEEDER_ID、并且已有模型 KeyID 能正确证明其设备属于当前 RMU 的环网柜，才属于<b>可信环网柜参考</b>。</li>
              <li>未关联 RMU、数据库0/多条、FEEDER_ID 为空或已有错误模型的 RMU 只在报告中告警，不参与馈线归属判断。</li>
              <li>同一连接区域中，所有可信 RMU 的 FEEDER_ID 必须完全一致。</li>
              <li>没有可信 RMU：<b>NO_TRUSTED_RMU_REFERENCE</b>，禁止自动关联。</li>
              <li>出现两个及以上不同 FEEDER_ID：<b>FEEDER_RMU_CONFLICT</b>，整个区域阻断，必须人工确认。</li>
            </ol>

            <h3>2. FeedLine 关联规则</h3>
            <ul>
              <li>连接区域唯一确认 FEEDER_ID 后，直接查询该 FEEDER_ID 下真实存在的 <b>dms_section_device</b>；数据库事实唯一、正确时，允许修复 G 文件中的旧关联错误。</li>
              <li>馈线段数据库表：<b>13503 / dms_section_device</b>，Domain：<b>1</b>。</li>
              <li>已有正确模型先占用数据库馈线段，保持不变。</li>
              <li>未关联、旧关联属于其它 feeder、设备已重建导致 ID/KeyID 变化、表号/域号错误等情况，只要当前数据库目标能够唯一确定，都进入可关联/RELINK 候选，而不是直接 FAIL。</li>
              <li>同一个 dms_section_device 被多个 FeedLine 重复使用时，所有重复行统一标记 <b>DUPLICATE_LINK</b> 并允许勾选修复；只勾选其中一条时，未勾选行保留原数据库段，勾选行改分配到其它剩余段；多条一起勾选时一起重新参与排序分配。</li>
              <li>未关联和需要 RELINK 的 FeedLine 按<b>从上到下、同高度从左到右</b>排序。</li>
              <li>剩余数据库馈线段按 SEC001、SEC002… 的实际自然顺序从小到大分配；不会自行生成数据库不存在的 SEC 编号。</li>
            </ul>

            <h3>3. FeedLine 安全回写</h3>
            <pre>
    app="6500000"
    p_ReportType="1"
    state="20"
    voltype="dms_section_device.BV_ID"
    keyid="Expected KeyID"
            </pre>
            <p>原始 G 文件永不修改，只修改 Workspace 中的安全副本。</p>

            <h3>4. 工作区选择与报告</h3>
            <p>模型校验完成后，工作区会出现“可关联馈线段选择”表格，可逐条勾选 UNLINKED / RELINK / DUPLICATE_LINK FeedLine；执行关联时只处理勾选行。</p>
            <p>馈线汇总会展示可信/忽略 RMU、FEEDER_ID 一致性和阻断原因；馈线段明细展示当前/目标模型。HTML 两张表都带复选框，勾选后整行持续高亮，仅用于人工标记，不参与程序关联逻辑。</p>
            """

        return """
        <h2>RMU 环网柜模型帮助</h2>

        <h3>1. 环网柜识别</h3>
        <ul>
          <li><b>结构硬条件：</b>矩形框内必须同时包含 CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 三类图元（每类至少 1 个），缺少任意一类不识别为 RMU。</li>
          <li><b>RMU 类型识别：</b>首先读取矩形框内部 Text / DText。Y1/Y2/Y3/Y4… 每个计为 1 个 L，Q1/Q2/Q3/Q4… 每个计为 1 个 T，例如 Y1、Y2、Q1 → <b>2L1T</b>。编号按自然递增顺序展示。</li>
          <li><b>文字是绝对第一优先级：</b>只要柜内识别到至少一个 Y* 或 Q*，最终柜型就使用柜内文字统计结果；不会因为文字数量与 CBreakerDis 数量不一致而改用 devref。</li>
          <li>只有柜内<b>完全识别不到任何 Y/Q 文字</b>时，才使用 CBreakerDis.devref 兜底：包含 <b>Load_Breaker</b> 计 L，包含 <b>Circuit_Breaker</b> 计 T。若两套信息都存在，devref 仅用于交叉检查，不覆盖文字结果。</li>
          <li>如果文字类型与 devref 类型不一致，报告中显示“类型交叉校验=NO”，但不改变 RMU 数据库关联资格，供人工检查图元模板。</li>
          <li><b>智能环网柜识别：</b>在整张 G 图全局寻找 Text / DText 中精确的 SMART 和 SMR，并把每个标识唯一归属给距离最近的 RMU。SMART 通常在柜内、SMR 可以在柜外，因此不设置最大距离限制。</li>
          <li>一个 RMU 只要命中 SMART 或 SMR 任意一种就标记“是否智能=YES”；若 SMART 和 SMR 都归属于同一个柜，仍然只表示该柜为智能环网柜，并在“智能标识”中记录 <b>SMART, SMR</b>。</li>
          <li>环网柜名称严格只按照当前页面勾选的方向读取：上方 / 下方 / 左侧 / 右侧；未勾选方向绝不参与。</li>
          <li>在所选方向对整张 G 图执行全局搜索，不再使用旧的 120 坐标单位柜名距离上限；较远的普通文字和绿色文字都可参与。</li>
          <li>每个 Text / DText 全局只归属距离最近的一个环网柜，避免同一名称被相邻环网柜重复使用。</li>
          <li>一个环网柜只有一个候选名称时直接使用，不判断颜色；拥有多个候选名称时才优先使用最近的绿色文字消歧，否则取最近候选。</li>
          <li>名称始终按照字符串处理，支持数字、字母、横线、下划线等常见工程名称。</li>
        </ul>

        <h3>2. 设备名称规则（固定）</h3>
        <ul>
          <li><b>CBreakerDis：</b>只使用环网柜内部、与开关图元空间对应的图上文字作为设备名称。XML <code>p_NameString</code> 完全不参与设备命名。</li>
          <li><b>ZhaiWaiJieDiDaoZha：</b>与 CBreakerDis 做最近唯一空间配对，逻辑设备名称=配对开关图上名称+D。</li>
          <li><b>BusDis：</b>逻辑设备名称固定为 <b>BUS</b>。</li>
          <li>上述逻辑设备名称必须与当前 RMU 下数据库设备 <b>CODE</b> 唯一对应；NAME 不参与判断。</li>
          <li>开关图上文字无法唯一识别、数据库不存在相同 CODE 或同 CODE 存在多条记录时，报告会明确指出对应环网柜并提示检查开关命名方式。</li>
        </ul>

        <h3>2.1 RMU 柜型两套规则与交叉验证</h3>
        <ul>
          <li><b>规则一（主规则）：</b>柜内 Y1/Y2/Y3/Y4… 每个计 1 个 L，Q1/Q2/Q3/Q4… 每个计 1 个 T。只要识别到任何 Y/Q 文字，最终柜型就采用文字结果。</li>
          <li><b>规则二（兜底规则）：</b>只有完全识别不到 Y/Q 文字时，才用 CBreakerDis.devref 判断：Load_Breaker=L，Circuit_Breaker=T。</li>
          <li><b>全面验证：</b>当文字结果和 devref 结果同时存在时，两套结果必须进行交叉验证。</li>
          <li>若两套结果冲突，最终仍采用规则一的文字柜型，但该 RMU 会产生 WARN，并在 HTML / CSV / Console 中输出：环网柜名称、文字柜型、devref 柜型和“请检查该环网柜 Y/Q 命名方式及开关 devref 模板”。</li>
          <li>柜型交叉验证告警本身不阻断已经由数据库唯一事实确定的设备关联。</li>
        </ul>

        <h3>3. 强制校验与可修复原则</h3>
        <p><b>核心原则：</b>数据库当前事实正确且能够唯一确定时，允许程序修复 G 文件中的旧关联、错关联、旧 KeyID、错误 Domain 等问题；只有数据库事实本身无法唯一确定时才阻断。</p>
        <ul>
          <li>环网柜数据库记录必须唯一；0 条或多条时环网柜汇总直接 FAIL。</li>
          <li>设备 CODE 必须与当前图上逻辑设备名称 一致；NAME 不参与判断。</li>
          <li>RMU 唯一后，每个 G 设备独立判断：当前 RMU 内 CODE 必须与逻辑设备名称 唯一对应，并且目标数据库设备必须属于当前 RMU。</li>
          <li>已有 KeyID 只用于判断当前模型是否需要修复：旧设备 ID、表号、域号或 KeyID 错误，不再作为数据库当前正确目标的硬阻断条件。</li>
          <li>如果旧设备被删除后重新创建并产生新 ID，只要当前 CODE/图上逻辑名称 仍能唯一确定本 RMU 内的新设备，就允许重新关联。</li>
          <li>如果当前 KeyID 指向其他环网柜，但本 RMU 内已经唯一确定正确目标设备，则标记为 RMU_RELINK，并允许重新关联到当前环网柜。</li>
          <li>同一 RMU 内某些设备不符合条件时，只阻断这些设备；其它符合条件的设备仍可以正常关联。</li>
          <li>模型校验完成后，工作区会展示设备明细选择表，并可按环网柜名称快速筛选；只有数据库事实已唯一确定且需要写回的设备可勾选。</li>
          <li>执行模型关联时直接使用校验阶段已确定并由用户勾选的设备，只处理本次勾选记录，不再重新全量循环所有环网柜；本次关联报告也只记录本次实际选择和写回结果。</li>
          <li>RMU 模块不进行任何馈线判断。</li>
        </ul>

        <h3>4. RMU 安全回写</h3>
        <p>CBreakerDis / ZhaiWaiJieDiDaoZha：</p>
        <pre>
    app="6500000"
    voltype="数据库设备BV_ID"
    p_ReportType="1"
    state="41"
    keyid="Expected KeyID"
        </pre>

        <p>BusDis：</p>
        <pre>
    app="6500000"
    voltype="数据库设备BV_ID"
    p_ReportType="1"
    state="15"
    keyid="Expected KeyID"
        </pre>

        <p>原始 G 文件永不修改，只修改 Workspace 中的安全副本。</p>
        """

    def show_current_module_help(self):
        """在模型工作区内提供当前模型专属帮助。"""
        module_name = self.module_combo.currentText() or "模型"

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{module_name} - 模型帮助")
        dialog.resize(820, 680)
        dialog.setMinimumSize(680, 520)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(
            """
            <style>
              body {
                font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI';
                color: #17372E;
                font-size: 14px;
                line-height: 1.6;
              }
              h2 { color: #006B52; margin-top: 4px; }
              h3 { color: #007A5E; margin-top: 18px; }
              pre {
                background: #F3F7F5;
                border: 1px solid #D3E3DC;
                border-radius: 6px;
                padding: 10px;
              }
              li { margin-bottom: 5px; }
            </style>
            """
            + self._current_module_help_html()
        )
        layout.addWidget(browser, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.clicked.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    # ------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------
    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)

        layout.addWidget(
            self._page_header(
                "设置",
                "团队内部版的公共安全策略和报告保留策略。",
            )
        )

        safety_box = QGroupBox("安全策略")
        safety_layout = QVBoxLayout(safety_box)

        text = QLabel(
            f"• 当前工作目录下自动生成的报告保留 {WORKSPACE_RETENTION_DAYS} 天\n"
            "• 每次执行任务前必须进行 Oracle 预检查\n"
            "• 模型回写必须先生成校验候选\n"
            "• 修改 G 文件前必须创建原文件备份\n"
            "• 回写目标必须通过 G 图元类型 + XML ID 唯一定位\n"
            "• G 文件采用临时文件写入后原子替换\n"
            "• 文件与目录选择会自动记住上一次位置"
        )
        text.setWordWrap(True)

        safety_layout.addWidget(text)
        layout.addWidget(safety_box)
        layout.addStretch()

        return page

    # ------------------------------------------------------------
    # Help
    # ------------------------------------------------------------
    def _build_help_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(10)

        root.addWidget(
            self._page_header(
                "帮助",
                "团队内部使用说明：RMU 与馈线模型校验、校验候选、报告和安全回写。",
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 12, 12)
        layout.setSpacing(12)

        quick = QGroupBox("快速使用")
        quick_layout = QVBoxLayout(quick)
        quick_text = QLabel(
            "1. 在【数据库】页面确认 Oracle 配置，可先点击‘测试数据库连接’。\n"
            "2. 进入【模型工作区】，选择 RMU 环网柜模型或馈线模型，并选择 G 文件/目录。\n"
            "3. RMU 模块配置名称来源与设备表/域；馈线模块配置 13503 馈线段表及域号。\n"
            "4. 点击底部【模型校验】执行独立校验，并生成校验 HTML / CSV。\n"
            "5. 需要关联时先点击【可关联清单】，确认预览结果后【执行模型关联】才会启用。\n"
            "6. 执行模型关联只修改 Workspace 中的安全副本，原始 G 文件不变。\n"
            "7. 关联完成后程序会重新校验安全副本，并生成与模型校验同规格的最终 HTML / CSV 报告。"
        )
        quick_text.setWordWrap(True)
        quick_layout.addWidget(quick_text)
        layout.addWidget(quick)

        rmu_naming = QGroupBox("环网柜名称识别规则")
        rmu_naming_layout = QVBoxLayout(rmu_naming)
        rmu_naming_text = QLabel(
            "• 环网柜只有在矩形框内同时存在 CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 三类图元时才识别为 RMU。\n"
            "• RMU 柜型规则一：柜内 Y* 每个计 1L、Q* 每个计 1T，文字绝对优先；规则二：完全识别不到 Y/Q 时才用 devref（Load_Breaker=L、Circuit_Breaker=T）兜底。两套结果同时存在时必须交叉验证，冲突则 WARN 并指出具体环网柜。\n"
            "• 环网柜名称严格只按照用户勾选的方向读取：上方 / 下方 / 左侧 / 右侧；未勾选方向绝不参与。\n"
            "• 对所选方向执行整张 G 图全局搜索，柜名不再受旧的 120 坐标单位距离上限限制。\n"
            "• 每个 Text / DText 全局只分配给距离最近的一个环网柜，避免同一个名字被两个柜重复使用。\n"
            "• 一个环网柜只有一个名称候选时直接使用；多个候选时才优先最近绿色名称，否则取最近候选。\n"
            "• 绿色依据 G 文件属性判断：lc=0,255,0 或 lcc=#00ff00；实际名称读取 Text / DText 的 ts 属性。\n"
            "• 环网柜名称始终按字符串处理，支持 42646、RMU-42646、ABC_123、JED-RMU-01、ABC.01 等常见工程名称，不会强制转换成数字。"
        )
        rmu_naming_text.setWordWrap(True)
        rmu_naming_layout.addWidget(rmu_naming_text)
        layout.addWidget(rmu_naming)

        naming = QGroupBox("设备名称判断规则")
        naming_layout = QVBoxLayout(naming)
        naming_text = QLabel(
            "【设备名称规则（固定）】\n"
            "• CBreakerDis：只使用环网柜内图上文字；XML p_NameString 完全不参与设备命名。\n"
            "• ZhaiWaiJieDiDaoZha：逻辑名称=配对开关图上名称+D。\n"
            "• BusDis：逻辑名称固定为 BUS。\n"
            "• 图上开关名称必须与当前 RMU 下数据库 CODE 唯一对应；失败时明确告警对应环网柜并提示检查命名方式。\n\n"
            "【RMU 柜型识别】\n"
            "• 第一套：柜内 Y1/Y2/Y3... 每个计 L；Q1/Q2/Q3... 每个计 T，文字优先。\n"
            "• 第二套：完全识别不到 Y/Q 时才用 devref 兜底：Load_Breaker=L，Circuit_Breaker=T。\n"
            "• 两套结果都存在时必须交叉验证；冲突时最终仍采用文字柜型，同时产生 WARN 并指出具体环网柜。\n\n"
"• 环网柜数据库记录为 0 条或多条时，环网柜汇总直接 FAIL。若 G 设备未关联，禁止自动关联。\n"
            "• 环网柜数据库记录为 0 条或多条，但 G 设备已经有人为 KeyID 时，不丢弃该模型：继续反解当前设备并校验 CODE/图上逻辑名称 和实际所属环网柜。\n"
            "• 唯一 RMU 下，若旧 KeyID 实际属于其它环网柜，使用紫色 RMU_RELINK 标记，可以覆盖旧模型并重新关联到当前 RMU；只有 RMU 本身不唯一时才继续作为硬阻断。\n"
            "• RMU 模块中的馈线判断已完全关闭；馈线模型关联由独立的【馈线模型】模块处理。\n"
            "• 唯一 RMU 下以当前数据库为准：CODE/图上逻辑名称 和目标设备 RMU 归属通过后，即使旧设备 ID、表号、域号、KeyID 已失效，也允许重新关联。"
        )
        naming_text.setWordWrap(True)
        naming_layout.addWidget(naming_text)
        layout.addWidget(naming)

        db_rule = QGroupBox("数据库强制校验")
        db_layout = QVBoxLayout(db_rule)
        db_text = QLabel(
            "• 13502 / CBreakerDis：CODE 不得为空，且 CODE 必须等于当前图上逻辑设备名称；NAME 不参与判断。\n"
            "• 13514 / ZhaiWaiJieDiDaoZha：CODE 不得为空，且 CODE 必须等于当前图上逻辑设备名称（开关名称+D）；NAME 不参与判断。\n"
            "• 13506 / BusDis：CODE 不得为空，且 CODE 必须等于当前图上逻辑设备名称；图上文字模式固定为 BUS；NAME 不参与判断。\n"
            "• 设备校验以 G 文件实际存在的图元为准，只查询这些图元最终需要的 CODE。\n"
            "• 数据库中与 G 图元 CODE 无关的其它设备记录忽略，不参与数量比较。\n"
            "• G 图元需要的 CODE 不存在，或同一 CODE 匹配到多条记录时，才作为设备模型错误并阻止关联。"
        )
        db_text.setWordWrap(True)
        db_layout.addWidget(db_text)
        layout.addWidget(db_rule)

        colors = QGroupBox("状态颜色说明")
        colors_layout = QVBoxLayout(colors)
        colors_text = QLabel(
            "绿色 PASS：设备模型校验正常；已有人工关联且 CODE、环网柜归属均正确时也可显示绿色。\n"
            "黄色 WARN：设备尚未关联，但满足自动关联条件。\n"
            "黄色 WARN：设备当前未关联，但数据库当前目标唯一有效，可以关联。\n"
            "橙色 RELINK：旧设备 ID、KeyID、表号或域号已过期/错误，或旧设备被删除重建；数据库当前目标唯一有效，可以重新关联。\n"
            "紫色 RMU_RELINK：旧 KeyID 指向其他环网柜，但当前 RMU 内已唯一确定正确设备，可以强制重新关联。\n"
            "红色 FAIL：数据库当前事实无法唯一确定安全目标，例如 RMU 0/多条、CODE 0/多条、CODE/图上逻辑名称 不一致、目标设备不属于当前 RMU、Expected KeyID/BV_ID 无效。\n"
            "RMU 报告不输出馈线状态；馈线模块使用独立报告。"
        )
        colors_text.setWordWrap(True)
        colors_layout.addWidget(colors_text)
        layout.addWidget(colors)

        assoc = QGroupBox("模型关联与 G 文件回写")
        assoc_layout = QVBoxLayout(assoc)
        assoc_text = QLabel(
            "建议先执行【可关联清单】，确认所有 Expected KeyID 和可关联设备。\n"
            "真正执行模型关联时，程序会重新检查数据库及预览有效性，然后复制所有选中 G 文件到 Workspace/g_output，只修改副本。原始 G 文件绝不修改。\n\n"
            "CBreakerDis / ZhaiWaiJieDiDaoZha 回写：\n"
            "app=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID\n\n"
            "BusDis 回写：\n"
            "app=6500000, voltype=数据库设备BV_ID, p_ReportType=1, state=15, keyid=Expected KeyID\n\n"
            "模型关联不会修改图上设备名称，也不会读取 XML p_NameString 作为设备名称。馈线信息完全不参与判断；数据库当前唯一 RMU 和 CODE/图上逻辑名称 匹配结果是关联依据。旧 KeyID 仅用于识别 PASS / RELINK / RMU_RELINK，不会阻止修复已经过期的模型关联。"
        )
        assoc_text.setWordWrap(True)
        assoc_layout.addWidget(assoc_text)
        layout.addWidget(assoc)

        reports = QGroupBox("报告说明")
        reports_layout = QVBoxLayout(reports)
        reports_text = QLabel(
            "•【环网柜汇总】严格按 G 文件环网柜序号排列，每个 G 环网柜只显示一行；数据库 0 条或多条直接 FAIL，不展开多个 ID。\n"
            "•【设备明细】只显示 G 文件实际存在的 RMU 设备图元，并展示逻辑设备名称、数据库 CODE、当前 KeyID 和实际所属环网柜。\n"
            "• RMU 数据库记录异常时，已有人为 KeyID 的设备仍继续校验；未关联设备则直接阻断自动关联。\n"
            "• 当选择图上文字模式时，报告中的逻辑设备名称 表示用于校验的逻辑 图上逻辑名称，不是 XML 原属性。\n"
            "• 每次模型校验、校验候选和关联完成都会自动生成对应 HTML / CSV；Workspace 历史按软件保留策略自动清理。"
        )
        reports_text.setWordWrap(True)
        reports_layout.addWidget(reports_text)
        layout.addWidget(reports)


        feeder_help = QGroupBox("馈线模型规则")
        feeder_help_layout = QVBoxLayout(feeder_help)
        feeder_help_text = QLabel(
            "• 当前版本仅处理单馈线 G 图，不处理一个文件内多馈线总图。\n"
            "• 馈线名称优先从 <Bus> 周围最近的有效 Text 获取，例如 AJWD-07；若找不到，再从文件名提取。\n"
            "• 数据库可读馈线名称由站名 + dms_feeder_device.NAME 组合；名称匹配忽略横线、下划线和空格：AJWD-07 → AJWD07；JED CTL AJWD + 07 → JEDCTLAJWD07。\n"
            "• 馈线主表：13500 / dms_feeder_device；馈线段表：13503 / dms_section_device；默认域号：1。\n"
            "• G 馈线段图元为 <FeedLine>。已有关联时，当前 KeyID 必须反解到 13503 / Domain 1 且数据库记录属于当前馈线。\n"
            "• 未关联 FeedLine：已正确关联的数据库馈线段先视为占用；其余数据库馈线段按 SEC001、SEC002… 自然顺序排列，未关联 G FeedLine 按从上到下、从左到右依次分配。\n"
            "• 已经关联错误的 FeedLine 不自动覆盖，只在报告中标红，避免静默改错已有模型。\n"
            "• FeedLine 回写安全副本：app=6500000, p_ReportType=1, state=20, voltype=dms_section_device.BV_ID, keyid=Expected KeyID。\n"
            "• 馈线模块拥有独立的【馈线汇总】和【馈线段明细】HTML / CSV 报告，不改变 RMU 模块已经取消馈线判断的规则。"
        )
        feeder_help_text.setWordWrap(True)
        feeder_help_layout.addWidget(feeder_help_text)
        layout.addWidget(feeder_help)

        safety = QGroupBox("注意事项")
        safety_layout = QVBoxLayout(safety)
        safety_text = QLabel(
            "• 执行模型关联前建议保留 G 文件源目录的额外工程备份。\n"
            "• 如果图上设备文字本身错误，图上文字模式也会得到错误名称，因此必须查看报告后再执行关联。\n"
            "• 表号和域号可以修改，但修改后会直接影响 Expected KeyID，请仅在确认数据库定义后调整。\n"
            "• 本工具为团队内部工程工具，不建议在未验证的数据库或未知版本 G 文件上直接批量回写。"
        )
        safety_text.setWordWrap(True)
        safety_layout.addWidget(safety_text)
        layout.addWidget(safety)

        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        return page

    # ------------------------------------------------------------
    # Restore state
    # ------------------------------------------------------------
    def _restore_ui_state(self):
        # Restore selected module
        module_id = self.cfg.get("model_module", "RMU")
        module_index = self.module_combo.findData(module_id)
        if module_index >= 0:
            self.module_combo.setCurrentIndex(module_index)

        self.on_module_changed(self.module_combo.currentIndex())

    # ------------------------------------------------------------
    # Model operation state
    # ------------------------------------------------------------
    def on_module_changed(self, index):
        """切换模块时解除旧页面几何限制，并重新布局当前模块。"""
        if not hasattr(self, "module_stack"):
            return

        # 先解除上一模块写入的固定高度，避免新模块继承旧页面尺寸。
        self.module_stack.setMinimumHeight(0)
        self.module_stack.setMaximumHeight(16777215)

        self.module_stack.setCurrentIndex(index)

        widget = self.module_stack.currentWidget()
        if widget is not None:
            widget.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Preferred,
            )
            widget.setMinimumWidth(0)
            widget.setMaximumWidth(16777215)
            if widget.layout() is not None:
                widget.layout().invalidate()
                widget.layout().activate()
            widget.updateGeometry()

        self.current_preview = None
        self.apply_btn.setEnabled(False)
        if hasattr(self, "association_table"):
            self._clear_association_table()
        self.refresh_operation_state()

        # 等 Qt 完成本次 stacked page 切换后，再计算新页面高度。
        QTimer.singleShot(0, self._update_module_stack_height)

    def refresh_operation_state(self):
        module_id = self.module_combo.currentData()
        if not module_id:
            return

        module = self.modules[module_id]
        self.validate_btn.setEnabled(module.supports("VALIDATE"))

        has_preview = bool(
            self.current_preview
            and self.current_preview.get("changes_by_file")
        )

        if str(module_id).upper() == "RMU":
            selected_count = len(
                self._selected_association_keys()
                if hasattr(self, "association_table")
                else set()
            )
            self.apply_btn.setEnabled(
                bool(
                    module.supports("APPLY_ASSOCIATION")
                    and has_preview
                    and selected_count > 0
                )
            )
        else:
            self.apply_btn.setEnabled(
                module.supports("APPLY_ASSOCIATION") and has_preview
            )

        self.workspace_status.setText("请选择下方具体任务按钮执行。")
        apply_status_style(self.workspace_status, False)

    def _set_task_buttons_enabled(self, enabled: bool):
        module_id = self.module_combo.currentData()
        module = self.modules.get(module_id) if module_id else None

        self.validate_btn.setEnabled(
            bool(enabled and module and module.supports("VALIDATE"))
        )
        if not enabled:
            self.apply_btn.setEnabled(False)
        else:
            self.refresh_operation_state()

    def _update_artifact_buttons(self, task_type=""):
        """Only show result buttons for artifacts that really exist."""
        report_kind = str(
            self.current_artifacts.get(
                "report_kind",
                self.module_combo.currentData() or "RMU",
            )
        ).upper()

        if report_kind == "FEEDER":
            labels = {
                "validation": (
                    "打开校验 HTML",
                    "打开馈线汇总 CSV",
                    "打开馈线段明细 CSV",
                ),
                "preview": (
                    "打开预览 HTML",
                    "打开馈线汇总 CSV",
                    "打开馈线段明细 CSV",
                ),
                "association": (
                    "打开关联结果 HTML",
                    "打开馈线汇总 CSV",
                    "打开馈线段明细 CSV",
                ),
            }
        else:
            labels = {
                "validation": (
                    "打开校验 HTML",
                    "打开校验环网柜 CSV",
                    "打开校验设备 CSV",
                ),
                "preview": (
                    "打开预览 HTML",
                    "打开预览环网柜 CSV",
                    "打开预览设备 CSV",
                ),
                "association": (
                    "打开关联结果 HTML",
                    "打开关联结果环网柜 CSV",
                    "打开关联结果设备 CSV",
                ),
            }

        html_text, first_csv_text, second_csv_text = labels.get(
            task_type,
            ("打开 HTML", "打开汇总 CSV", "打开明细 CSV"),
        )
        self.open_html_btn.setText(html_text)
        self.open_rmu_csv_btn.setText(first_csv_text)
        self.open_device_csv_btn.setText(second_csv_text)

        for key, button in (
            ("html", self.open_html_btn),
            ("rmu_csv", self.open_rmu_csv_btn),
            ("device_csv", self.open_device_csv_btn),
            ("run_dir", self.open_report_dir_btn),
        ):
            value = self.current_artifacts.get(key, "")
            exists = bool(value and Path(value).exists())
            button.setEnabled(exists)
            button.setVisible(exists)

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------
    def log(self, text):
        if hasattr(self, "log_edit"):
            self.log_edit.appendPlainText(str(text))
            scrollbar = self.log_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())


    def db_log(self, text):
        message = str(text)
        if hasattr(self, "db_log_edit"):
            self.db_log_edit.appendPlainText(message)
            scrollbar = self.db_log_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        try:
            append_database_log(message)
        except Exception:
            pass

    def _check_saved_input_path_on_startup(self):
        value = (self.cfg.get("input_path") or "").strip()
        if not value:
            return

        path = Path(value)
        if path.exists():
            return

        message = f"上次记录的文件或目录不存在：\n{value}"
        self.workspace_status.setText("上次记录的文件或目录不存在，请重新选择。")
        apply_status_style(self.workspace_status, False)
        self.log(message)

        # 窗口显示后再弹出提示，避免启动阶段对话框挡住主窗口初始化。
        QTimer.singleShot(
            250,
            lambda: QMessageBox.warning(
                self,
                "历史路径不存在",
                message + "\n\n请重新选择有效的 G 文件或目录。",
            ),
        )

    # ------------------------------------------------------------
    # Database
    # ------------------------------------------------------------
    def current_db_config(self):
        db = {
            key: edit.text().strip()
            for key, edit in self.db_edits.items()
        }
        db["port"] = int(db["port"])
        return db

    def save_database_settings(self):
        try:
            self.cfg["db"] = self.current_db_config()
            save_settings(self.cfg)
            self.statusBar().showMessage("数据库配置已保存。", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "数据库配置", str(exc))

    def test_connection(self):
        try:
            config = self.current_db_config()
            db = OracleClient(config)
            message = db.test_connection()
            db.close()

            self.cfg["db"] = config
            save_settings(self.cfg)

            self.db_status.setText("数据库连接正常")
            self.db_status.show()
            apply_status_style(self.db_status, True)
            QTimer.singleShot(3500, self.db_status.hide)

            self.db_log(message)
            self.statusBar().showMessage("Oracle 数据库连接验证通过。", 3500)

        except Exception as exc:
            self.db_status.setText("数据库连接失败")
            self.db_status.show()
            apply_status_style(self.db_status, False)

            self.db_log(f"Oracle 数据库连接失败：{exc}")
            QMessageBox.critical(
                self,
                "Oracle 数据库连接失败",
                str(exc),
            )

    # ------------------------------------------------------------
    # Remember file/folder
    # ------------------------------------------------------------
    def _existing_start_path(self, value, fallback=None):
        if value:
            path = Path(value)
            if path.exists():
                return str(path if path.is_dir() else path.parent)

        if fallback:
            path = Path(fallback)
            if path.exists():
                return str(path if path.is_dir() else path.parent)

        return str(Path.home())

    def browse_file(self):
        start_dir = self._existing_start_path(
            self.cfg.get("last_file_path", ""),
            self.cfg.get("last_folder_path", ""),
        )

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 G 文件",
            start_dir,
            "G 文件 (*.g);;所有文件 (*.*)",
        )

        if not path:
            return

        self.input_edit.setText(path)
        self.cfg["input_path"] = path
        self.cfg["last_file_path"] = path
        self.cfg["last_folder_path"] = str(Path(path).parent)
        save_settings(self.cfg)

    def browse_folder(self):
        start_dir = self._existing_start_path(
            self.cfg.get("last_folder_path", ""),
            self.cfg.get("last_file_path", ""),
        )

        path = QFileDialog.getExistingDirectory(
            self,
            "选择包含 G 文件的目录",
            start_dir,
        )

        if not path:
            return

        self.input_edit.setText(path)
        self.cfg["input_path"] = path
        self.cfg["last_folder_path"] = path
        save_settings(self.cfg)

    def _save_input_path_from_edit(self):
        value = self.input_edit.text().strip()
        if not value:
            return

        self.cfg["input_path"] = value

        path = Path(value)
        if path.exists():
            if path.is_file():
                self.cfg["last_file_path"] = str(path)
                self.cfg["last_folder_path"] = str(path.parent)
            elif path.is_dir():
                self.cfg["last_folder_path"] = str(path)

        save_settings(self.cfg)

    def resolve_files(self, value):
        path = Path(value)

        if path.is_file():
            return [path]

        if path.is_dir():
            return sorted(
                child
                for child in path.iterdir()
                if child.is_file()
                and child.suffix.lower() == ".g"
            )

        return []

    def open_workspace(self):
        ensure_workspace()
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(WORKSPACE_ROOT))
            else:
                subprocess.Popen(["xdg-open", str(WORKSPACE_ROOT)])
        except Exception as exc:
            QMessageBox.critical(self, "打开 Workspace 失败", str(exc))

    def open_current_run_dir(self):
        path_value = self.current_artifacts.get("run_dir", "") or self.cfg.get("last_run_dir", "")
        if not path_value:
            QMessageBox.information(self, "本次运行目录", "当前没有可打开的运行目录。")
            return

        path = Path(path_value)
        if not path.exists():
            QMessageBox.warning(self, "本次运行目录", f"目录不存在：\n{path}")
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.critical(self, "打开本次运行目录失败", str(exc))

    # ------------------------------------------------------------
    # Run model job
    # ------------------------------------------------------------
    def start_job(self, operation):
        try:
            module_id = self.module_combo.currentData()
            module = self.modules[module_id]
            operation_labels = {
                "VALIDATE": "模型校验",
            }
            operation_label = operation_labels.get(operation, operation)

            if not module.supports(operation):
                raise ValueError(
                    f"{module.display_name} 当前版本暂未开放“"
                    f"{operation_label}”。"
                )

            settings = self.module_widgets[module_id].collect_settings()

            input_value = self.input_edit.text().strip()
            if not input_value:
                raise ValueError("请先选择 G 文件或目录。")

            input_path = Path(input_value)
            if not input_path.exists():
                raise ValueError(f"文件或目录不存在：\n{input_value}")

            files = self.resolve_files(input_value)
            if not files:
                raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")

            self.cfg["model_module"] = module_id
            self.cfg["operation"] = operation
            self.cfg["input_path"] = input_value
            self.cfg["db"] = self.current_db_config()

            input_path = Path(input_value)
            if input_path.exists():
                if input_path.is_file():
                    self.cfg["last_file_path"] = str(input_path)
                    self.cfg["last_folder_path"] = str(input_path.parent)
                else:
                    self.cfg["last_folder_path"] = str(input_path)

            for key in (
                "rmu_name_positions",
                "device_rules",
                "breaker_name_source",
                "feeder_table_id",
                "section_table_id",
                "section_domain",
                "drawing_mode",
            ):
                if key in settings:
                    self.cfg[key] = settings[key]

            save_settings(self.cfg)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "模型任务配置错误",
                str(exc),
            )
            return

        try:
            self.current_run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self._set_task_buttons_enabled(False)
        self.current_preview = None
        self.apply_btn.setEnabled(False)
        self._clear_association_table()
        self.log_edit.clear()

        self.progress_bar.setValue(0)
        self.progress_message.setText("任务准备中……")
        self.current_artifacts = {}
        self.current_task_type = ""
        for button in (
            self.open_html_btn,
            self.open_rmu_csv_btn,
            self.open_device_csv_btn,
            self.open_report_dir_btn,
        ):
            button.setEnabled(False)
            button.setVisible(False)

        self.workspace_status.show()
        self.workspace_status.setText("正在进行 Oracle 数据库预检查……")
        apply_status_style(self.workspace_status, False)

        self.log(
            f"\n开始执行：{module.display_name} / {operation_label}"
        )

        self.worker = JobWorker(
            self.cfg,
            module,
            operation,
            settings,
            files,
            self.current_run_dir,
        )
        self.worker.log.connect(self.on_worker_log)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.completed.connect(self.on_job_completed)
        self.worker.failed.connect(self.on_job_failed)
        self.worker.start()

    def on_worker_progress(self, percent, message):
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        if message:
            self.progress_message.setText(str(message))

    def on_worker_log(self, text):
        self.log(text)

        if "Oracle 预检查：通过" in text:
            self.workspace_status.show()
            self.workspace_status.setText("Oracle 数据库预检查通过")
            apply_status_style(self.workspace_status, True)

    def on_job_completed(
        self,
        report_dir,
        summary,
        rules,
        preview_data,
        artifacts,
    ):
        self._set_task_buttons_enabled(True)
        self.current_report_dir = str(
            (artifacts or {}).get("report_dir", report_dir)
        )
        self.current_rules = dict(rules)
        self.current_preview = preview_data
        self.current_artifacts = dict(artifacts or {})
        self.current_task_type = self.current_artifacts.get("task_type", "")

        if self.current_preview and self.current_preview.get("changes_by_file"):
            change_count = sum(
                len(v)
                for v in self.current_preview["changes_by_file"].values()
            )

            current_module = str(
                self.module_combo.currentData() or ""
            ).upper()
            if current_module in {"RMU", "FEEDER"}:
                self._populate_association_table(self.current_preview)
                if current_module == "FEEDER":
                    self.log(
                        f"模型校验已生成可关联馈线段清单："
                        f"可关联/重新关联 FeedLine {change_count} 个。"
                        "请在工作区表格中勾选需要处理的馈线段。"
                    )
                else:
                    self.log(
                        f"模型校验已生成可关联设备清单："
                        f"可关联/重新关联设备 {change_count} 个。"
                        "请在工作区表格中勾选需要处理的设备。"
                    )
                # Both modules require explicit row selection.
                self.apply_btn.setEnabled(False)
            else:
                self.apply_btn.setEnabled(change_count > 0)
                self.log(
                    f"模型校验已生成可关联清单：可回写设备 {change_count} 个。"
                )
        else:
            self.apply_btn.setEnabled(False)
            self._clear_association_table()

        self.progress_bar.setValue(100)
        self.progress_message.setText(
            "模型校验完成，报告和可关联清单已生成"
        )
        self.workspace_status.setText("任务执行完成")
        apply_status_style(self.workspace_status, True)
        QTimer.singleShot(3500, self.workspace_status.hide)

        self._update_artifact_buttons(self.current_task_type)

        self.log(f"任务完成。本次运行目录：{report_dir}")
        self.log(f"HTML：{self.current_artifacts.get('html', '')}")
        if str(self.current_artifacts.get("report_kind", "")).upper() == "FEEDER":
            self.log(f"馈线汇总 CSV：{self.current_artifacts.get('rmu_csv', '')}")
            self.log(f"馈线段明细 CSV：{self.current_artifacts.get('device_csv', '')}")
        else:
            self.log(f"环网柜 CSV：{self.current_artifacts.get('rmu_csv', '')}")
            self.log(f"设备 CSV：{self.current_artifacts.get('device_csv', '')}")

        # 保存完整的本次 Console 日志到当前任务的实际报告目录。
        try:
            actual_report_dir = Path(
                self.current_artifacts.get("report_dir", report_dir)
            )
            actual_report_dir.mkdir(parents=True, exist_ok=True)
            log_path = actual_report_dir / "console.log"
            log_path.write_text(
                self.log_edit.toPlainText(),
                encoding="utf-8",
            )
            self.current_artifacts["console_log"] = str(log_path)
        except Exception as exc:
            self.log(f"保存 console.log 失败：{exc}")

        self.statusBar().showMessage(
            "模型校验完成，校验报告和可关联清单已生成。",
            5000,
        )

    def on_job_failed(self, text):
        self._set_task_buttons_enabled(True)
        self.progress_message.setText("任务执行失败")
        self.workspace_status.show()
        self.workspace_status.setText("任务执行失败")
        apply_status_style(self.workspace_status, False)

        self.log(text)

        QMessageBox.critical(
            self,
            "模型任务执行失败",
            text,
        )

    # ------------------------------------------------------------
    # Association write-back placeholder
    # ------------------------------------------------------------
    @staticmethod
    def _association_change_key(source_file, change):
        """Stable UI key for one G object association candidate."""
        return "|".join([
            str(Path(source_file).resolve()),
            str(change.get("tag", "") or ""),
            str(change.get("xml_id", "") or ""),
        ])

    def _clear_association_table(self):
        if not hasattr(self, "association_table"):
            return
        self._association_table_populating = True
        try:
            self.association_table.clearContents()
            self.association_table.setRowCount(0)
            self._association_candidate_keys = set()
            self.selection_count_label.setText("已选择 0 个对象")
            if hasattr(self, "rmu_filter_edit"):
                self.rmu_filter_edit.blockSignals(True)
                self.rmu_filter_edit.clear()
                self.rmu_filter_edit.blockSignals(False)
            self.association_selection_box.setVisible(False)
        finally:
            self._association_table_populating = False

    def _candidate_change_lookup(self, preview_data):
        lookup = {}
        if not preview_data:
            return lookup

        for source_file, changes in (
            preview_data.get("changes_by_file", {}) or {}
        ).items():
            for change in changes or []:
                key = self._association_change_key(
                    source_file,
                    change,
                )
                lookup[key] = change
        return lookup

    @staticmethod
    def _row_status_text(row):
        status = str(row.get("status", "") or "")
        mapping = {
            "PASS": "PASS",
            "WARN": "UNLINKED",
            "RELINK": "RELINK",
            "RMU_RELINK": "RMU_RELINK",
            "FAIL": "FAIL",
            "RMU_LINK": "FAIL",
            "BLOCKED": "BLOCKED",
        }
        return mapping.get(status, status)

    @staticmethod
    def _association_status_brush(status):
        # Keep exactly the same semantic palette as the HTML report.
        from PySide6.QtGui import QColor, QBrush

        colors = {
            "PASS": "#EAF8F2",
            "WARN": "#FFF8DE",
            "RELINK": "#FFE8CC",
            "DUPLICATE_LINK": "#FFF1CC",
            "UNLINKED": "#FFF8DE",
            "RMU_RELINK": "#F0E7FF",
            "FAIL": "#FFF0F0",
            "RMU_LINK": "#FFF0F0",
            "BLOCKED": "#EAF3FF",
        }
        value = colors.get(str(status or ""), "")
        return QBrush(QColor(value)) if value else None

    def _populate_association_table(self, preview_data):
        """Show selectable association candidates for RMU or FeedLine models."""
        self._clear_association_table()
        if not preview_data:
            return

        module_id = str(self.module_combo.currentData() or "").upper()
        if module_id not in {"RMU", "FEEDER"}:
            return

        candidate_lookup = self._candidate_change_lookup(preview_data)
        reports = preview_data.get("reports", []) or []
        display_rows = []

        if module_id == "RMU":
            self.association_selection_box.setTitle(
                "可关联设备选择（模型校验结果）"
            )
            self.association_selection_tip.setText(
                "模型校验完成后，这里展示 G 文件设备明细。只有数据库当前事实已经唯一确定、"
                "并且需要关联或重新关联的设备才允许勾选。执行模型关联时只处理你勾选的设备。"
            )
            self.association_filter_label.setText("环网柜名称筛选")
            self.rmu_filter_edit.setPlaceholderText(
                "输入环网柜名称快速筛选，例如：17613 / RMU-42646"
            )
            headers = [
                "选择", "G文件", "环网柜序号", "环网柜名称", "G图元类型",
                "逻辑设备名称（图上规则）", "数据库CODE", "状态", "当前关联",
                "目标设备ID", "Expected KeyID", "处理说明",
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                for rmu in report.get("rmu_results", []) or []:
                    frame_index = rmu.get("frame_index", "")
                    for row in rmu.get("device_rows", []) or []:
                        if not row.get("xml_id"):
                            continue
                        item = dict(row)
                        item["_source_file"] = source_file
                        item["_file_name"] = file_name
                        item["_frame_index"] = frame_index
                        display_rows.append(item)
        else:
            self.association_selection_box.setTitle(
                "可关联馈线段选择（模型校验结果）"
            )
            self.association_selection_tip.setText(
                "模型校验完成后，这里展示 FeedLine 明细。数据库 FEEDER_ID 与馈线段事实唯一正确时，"
                "未关联、旧关联错误以及 DUPLICATE_LINK 重复关联行允许勾选。"
                "只处理你勾选的 FeedLine；未勾选对象保持原样。"
            )
            self.association_filter_label.setText("馈线段快速筛选")
            self.rmu_filter_edit.setPlaceholderText(
                "输入 FEEDER_ID / 馈线名称 / FeedLine XML ID / 目标馈线段名称"
            )
            headers = [
                "选择", "G文件", "连接区域", "FEEDER_ID", "FeedLine序号",
                "图元XML ID", "当前关联", "状态", "目标馈线段",
                "目标设备ID", "Expected KeyID", "处理说明",
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                for row in report.get("feedline_rows", []) or []:
                    if not row.get("xml_id"):
                        continue
                    item = dict(row)
                    item["_source_file"] = source_file
                    item["_file_name"] = file_name
                    item["_region_index"] = report.get("region_index", "")
                    item["_feeder_id"] = report.get("feeder_id", "")
                    item["_feeder_name"] = report.get("feeder_name", "")
                    display_rows.append(item)

        self.association_table.setHorizontalHeaderLabels(headers)
        self._association_table_populating = True
        try:
            self.association_table.setRowCount(len(display_rows))
            self._association_candidate_keys = set(candidate_lookup)

            for row_index, row in enumerate(display_rows):
                source_file = row["_source_file"]
                key = self._association_change_key(
                    source_file,
                    {"tag": row.get("object_type", ""), "xml_id": row.get("xml_id", "")},
                )
                is_candidate = key in candidate_lookup

                check_item = QTableWidgetItem()
                check_item.setData(Qt.UserRole, key)
                if is_candidate:
                    check_item.setFlags(
                        Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
                    )
                    check_item.setCheckState(Qt.Unchecked)
                    check_item.setToolTip(
                        "数据库当前事实唯一正确，可选择执行关联/重新关联。"
                    )
                else:
                    check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    check_item.setText("—")
                    check_item.setToolTip("当前记录无需回写或已被校验阻断。")
                self.association_table.setItem(row_index, 0, check_item)

                if module_id == "RMU":
                    current_text = str(
                        row.get("model_link_status", "")
                        or ("已关联" if row.get("model_linked") == "YES" else "未关联")
                    )
                    values = [
                        row["_file_name"], row["_frame_index"], row.get("rmu_name", ""),
                        row.get("object_type", ""),
                        row.get("logical_code", "") or row.get("selected_device_name", ""),
                        row.get("db_code", ""), self._row_status_text(row), current_text,
                        row.get("db_device_id", ""), row.get("expected_keyid", ""),
                        row.get("reason", ""),
                    ]
                else:
                    current_text = (
                        f"KeyID={row.get('current_keyid')} / {row.get('current_db_name') or '-'}"
                        if row.get("model_linked") == "YES" else "未关联"
                    )
                    status_text = (
                        str(row.get("severity", ""))
                        if str(row.get("severity", "")) in {"DUPLICATE_LINK", "RELINK", "UNLINKED"}
                        else str(row.get("status", ""))
                    )
                    values = [
                        row["_file_name"], row["_region_index"], row["_feeder_id"],
                        row.get("order_index", ""), row.get("xml_id", ""), current_text,
                        status_text, row.get("assigned_section_name", ""),
                        row.get("assigned_device_id", ""), row.get("expected_keyid", ""),
                        row.get("reason", ""),
                    ]

                brush = self._association_status_brush(
                    row.get("severity", "") if module_id == "FEEDER" else row.get("status", "")
                ) or self._association_status_brush(row.get("status", ""))

                for col_offset, value in enumerate(values, start=1):
                    cell = QTableWidgetItem("" if value is None else str(value))
                    cell.setToolTip("" if value is None else str(value))
                    if brush is not None:
                        cell.setBackground(brush)
                    self.association_table.setItem(row_index, col_offset, cell)
                if brush is not None:
                    check_item.setBackground(brush)

            for table_row in range(self.association_table.rowCount()):
                self.association_table.setRowHeight(table_row, 38)
            self.association_selection_box.setVisible(bool(display_rows))
        finally:
            self._association_table_populating = False

        self._update_association_selection_state()
        self._apply_rmu_name_filter(self.rmu_filter_edit.text())

    def _selected_association_keys(self):
        if not hasattr(self, "association_table"):
            return set()

        selected = set()
        for row in range(self.association_table.rowCount()):
            item = self.association_table.item(row, 0)
            if (
                item is not None
                and item.flags() & Qt.ItemIsUserCheckable
                and item.checkState() == Qt.Checked
            ):
                key = item.data(Qt.UserRole)
                if key:
                    selected.add(str(key))
        return selected

    def _update_association_selection_state(self):
        selected_count = len(self._selected_association_keys())
        total_candidates = len(
            getattr(self, "_association_candidate_keys", set())
        )
        if hasattr(self, "selection_count_label"):
            filter_text = (
                self.rmu_filter_edit.text().strip()
                if hasattr(self, "rmu_filter_edit")
                else ""
            )
            visible_count = sum(
                1
                for row in range(self.association_table.rowCount())
                if not self.association_table.isRowHidden(row)
            ) if hasattr(self, "association_table") else 0
            suffix = (
                f"；当前显示 {visible_count} 行"
                if filter_text
                else ""
            )
            unit = (
                "个馈线段"
                if str(self.module_combo.currentData() or "").upper() == "FEEDER"
                else "个设备"
            )
            self.selection_count_label.setText(
                f"已选择 {selected_count} {unit} / "
                f"可关联 {total_candidates} {unit}{suffix}"
            )

        module_id = str(self.module_combo.currentData() or "")
        module = self.modules.get(module_id)
        self.apply_btn.setEnabled(
            bool(
                module
                and module.supports("APPLY_ASSOCIATION")
                and self.current_preview
                and selected_count > 0
            )
        )

    def _on_association_selection_changed(self, item):
        if getattr(self, "_association_table_populating", False):
            return
        if item.column() != 0:
            return
        self._update_association_selection_state()

    def _apply_rmu_name_filter(self, text=""):
        """Display-only filter for RMU or FeedLine association tables."""
        if not hasattr(self, "association_table"):
            return

        needle = str(text or "").strip().casefold()
        module_id = str(self.module_combo.currentData() or "").upper()
        visible_count = 0

        for row in range(self.association_table.rowCount()):
            if module_id == "FEEDER":
                # FEEDER_ID, XML ID, target section and explanation are all
                # useful quick-filter keys for large topology reports.
                columns = (3, 5, 8, 11)
            else:
                columns = (3,)
            haystack = " ".join(
                self.association_table.item(row, col).text().strip().casefold()
                for col in columns
                if self.association_table.item(row, col) is not None
            )
            visible = (not needle) or (needle in haystack)
            self.association_table.setRowHidden(row, not visible)
            if visible:
                visible_count += 1

        if hasattr(self, "selection_count_label"):
            selected_count = len(self._selected_association_keys())
            total_candidates = len(
                getattr(self, "_association_candidate_keys", set())
            )
            suffix = f"；当前显示 {visible_count} 行" if needle else ""
            unit = "个馈线段" if module_id == "FEEDER" else "个设备"
            self.selection_count_label.setText(
                f"已选择 {selected_count} {unit} / "
                f"可关联 {total_candidates} {unit}{suffix}"
            )


    def _select_all_association_candidates(self):
        self._association_table_populating = True
        try:
            for row in range(self.association_table.rowCount()):
                item = self.association_table.item(row, 0)
                if (
                    item is not None
                    and item.flags() & Qt.ItemIsUserCheckable
                ):
                    item.setCheckState(Qt.Checked)
        finally:
            self._association_table_populating = False
        self._update_association_selection_state()

    def _clear_association_selection(self):
        self._association_table_populating = True
        try:
            for row in range(self.association_table.rowCount()):
                item = self.association_table.item(row, 0)
                if (
                    item is not None
                    and item.flags() & Qt.ItemIsUserCheckable
                ):
                    item.setCheckState(Qt.Unchecked)
        finally:
            self._association_table_populating = False
        self._update_association_selection_state()

    def _selected_association_preview(self):
        """
        Filter validated preview data down to the rows explicitly selected by
        the user.  No new eligibility decision is made here.
        """
        if not self.current_preview:
            return None

        selected_keys = self._selected_association_keys()
        if not selected_keys:
            return None

        filtered = dict(self.current_preview)
        filtered_changes = {}
        selected_source_files = set()

        for source_file, changes in (
            self.current_preview.get("changes_by_file", {}) or {}
        ).items():
            kept = []
            for change in changes or []:
                key = self._association_change_key(
                    source_file,
                    change,
                )
                if key in selected_keys:
                    kept.append(dict(change))
            if kept:
                filtered_changes[source_file] = kept
                selected_source_files.add(
                    str(Path(source_file).resolve())
                )

        filtered["changes_by_file"] = filtered_changes
        filtered["selected_change_count"] = sum(
            len(v) for v in filtered_changes.values()
        )
        filtered["selected_source_files"] = sorted(
            selected_source_files
        )

        fingerprints = {}
        for source_file, fingerprint in (
            self.current_preview.get("file_fingerprints", {}) or {}
        ).items():
            if str(Path(source_file).resolve()) in selected_source_files:
                fingerprints[source_file] = dict(fingerprint)
        filtered["file_fingerprints"] = fingerprints

        # Keep only selected preview rows when the module supplied them.
        selected_rows = []
        for row in self.current_preview.get("rows", []) or []:
            for source_file in filtered_changes:
                key = self._association_change_key(
                    source_file,
                    {
                        "tag": row.get("object_type", ""),
                        "xml_id": row.get("xml_id", ""),
                    },
                )
                if key in selected_keys:
                    selected_rows.append(dict(row))
                    break
        filtered["rows"] = selected_rows

        return filtered

    def apply_association(self):
        if not self.current_preview or not self.current_preview.get("changes_by_file"):
            QMessageBox.information(
                self,
                "模型关联",
                "当前没有可执行的模型校验结果，请先执行模型校验。",
            )
            return

        module_id = str(self.module_combo.currentData() or "")

        if module_id.upper() in {"RMU", "FEEDER"}:
            execution_preview = self._selected_association_preview()
            if not execution_preview or not execution_preview.get(
                "changes_by_file"
            ):
                QMessageBox.information(
                    self,
                    "模型关联",
                    (
                        "请先在“可关联馈线段选择”表格中勾选至少一个需要关联或重新关联的FeedLine。"
                        if module_id.upper() == "FEEDER"
                        else "请先在“可关联设备选择”表格中勾选至少一个需要关联或重新关联的设备。"
                    ),
                )
                return
        else:
            execution_preview = self.current_preview

        change_count = sum(
            len(v)
            for v in execution_preview["changes_by_file"].values()
        )
        skipped_count = len(
            execution_preview.get("skipped_rmus", [])
        )
        skip_label = "馈线文件" if module_id == "FEEDER" else "RMU"
        target_label = "FeedLine 图元" if module_id == "FEEDER" else "设备图元"

        if module_id.upper() == "RMU":
            message = (
                f"本次将只处理已勾选的 {change_count} 个{target_label}。\n\n"
                "执行阶段不会重新扫描整张 G 图，也不会重新循环全部环网柜。"
                "程序只会对这些设备所属环网柜和设备做轻量数据库复核，"
                "然后按 XML ID 精确写回 Workspace 安全副本。\n\n"
                "最终 HTML / CSV 只汇报本次选中的环网柜和设备。\n\n"
                "是否确认执行？"
            )
        elif module_id.upper() == "FEEDER":
            message = (
                f"本次将只处理已勾选的 {change_count} 个FeedLine 图元。\n\n"
                "程序会基于模型校验已确认的可信RMU/FEEDER_ID拓扑区域，"
                "重新计算未勾选FeedLine当前占用的数据库馈线段，再只给勾选行分配剩余段。\n"
                "DUPLICATE_LINK 行可以只选其中一条重新分配，也可以多条一起重新分配。\n\n"
                "原始 G 文件不会被修改，只修改 Workspace 安全副本。\n\n"
                "是否确认执行？"
            )
        else:
            message = (
                f"本次将只处理已勾选的 {change_count} 个{target_label}。\n"
                f"因校验不通过而跳过的{skip_label}：{skipped_count} 个。\n\n"
                "原始 G 文件不会被修改。程序会复制全部选中 G 文件到 "
                "Workspace/g_output，再只修改安全副本。\n"
                "关联完成后，程序会立即重新校验这些安全副本，并生成与模型校验"
                "同规格的 HTML / CSV 最终报告。\n\n"
                "是否确认执行？"
            )
        reply = QMessageBox.question(
            self,
            "确认执行模型关联",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        db = None
        try:
            self._set_task_buttons_enabled(False)
            self.progress_bar.setValue(5)
            self.progress_message.setText("正在准备模型关联……")

            module_id = self.module_combo.currentData()
            module = self.modules[module_id]
            settings = self.module_widgets[module_id].collect_settings()
            files = self.resolve_files(self.input_edit.text().strip())

            if module_id in {"RMU", "FEEDER"}:
                selected_source_files = {
                    str(Path(p).resolve())
                    for p in execution_preview.get(
                        "selected_source_files",
                        [],
                    )
                }
                files = [
                    Path(p)
                    for p in files
                    if str(Path(p).resolve()) in selected_source_files
                ]
                if not files:
                    raise RuntimeError(
                        "没有找到已勾选设备对应的 G 文件，请重新执行模型校验。"
                    )

            self.log("\n开始执行模型关联：重新验证 Oracle 数据库连接。")
            db = OracleClient(self.current_db_config())
            self.log(db.test_connection())

            self.progress_bar.setValue(15)
            self.progress_message.setText("正在写入安全 G 文件副本……")
            result_bundle = module.apply_association(
                db,
                files,
                settings,
                execution_preview,
                self.log,
                output_g_dir=Path(self.current_run_dir) / "g_output",
            )

            total = int(result_bundle.get("applied_count", 0))
            skipped_total = int(result_bundle.get("skipped_count", 0))
            selected_total = int(
                result_bundle.get("selected_count", change_count)
            )
            output_dir = result_bundle.get("output_g_dir", "")
            copied_files = [
                Path(p)
                for p in result_bundle.get("copied_files", [])
                if Path(p).exists()
            ]

            if module_id in {"RMU", "FEEDER"}:
                # Execution reports are intentionally operation-scoped:
                # only the rows explicitly selected by the user are included.
                # The full drawing is NOT scanned/validated again after
                # write-back.  Database/file safety is rechecked inside each
                # module immediately before the selected XML IDs are written.
                reports = result_bundle.get(
                    "operation_reports",
                    [],
                )
                final_rules = result_bundle.get(
                    "rules",
                    settings.get("_runtime_rules", {}),
                )
                final_summary = {
                    "selected": selected_total,
                    "applied": total,
                    "skipped": skipped_total,
                }
                self.progress_bar.setValue(90)
                self.progress_message.setText(
                    "正在生成本次模型关联执行报告……"
                )
                self.log(
                    (
                        "已完成已选馈线段的轻量数据库复核、剩余段重算与精确回写；"
                        "不再对整张 G 图重新循环校验。"
                    )
                    if module_id == "FEEDER"
                    else (
                        "已完成已选设备的轻量数据库复核与精确回写；"
                        "不再对整张 G 图重新循环校验。"
                    )
                )
            else:
                if not copied_files:
                    raise RuntimeError(
                        "模型关联已执行，但没有找到可用于最终校验的 "
                        "G 文件安全副本。"
                    )

                self.progress_bar.setValue(65)
                self.progress_message.setText(
                    "关联完成，正在重新校验安全副本……"
                )
                self.log(
                    "模型关联写入完成，开始对 g_output 中的安全副本"
                    "执行最终模型校验。"
                )

                def final_progress(percent, message=""):
                    mapped = (
                        65
                        + int(
                            max(
                                0,
                                min(100, int(percent)),
                            )
                            * 0.27
                        )
                    )
                    self.progress_bar.setValue(
                        min(mapped, 92)
                    )
                    if message:
                        self.progress_message.setText(
                            f"最终校验：{message}"
                        )
                    QApplication.processEvents()

                reports, final_summary, final_rules = module.validate(
                    db,
                    copied_files,
                    settings,
                    self.log,
                    final_progress,
                )

                self.progress_bar.setValue(94)
                self.progress_message.setText(
                    "正在生成模型关联完成报告……"
                )

            if module_id in {"RMU", "FEEDER"} and not reports:
                raise RuntimeError(
                    "模型关联已执行，但没有生成本次选中对象的执行报告。"
                )

            report_dir = (
                Path(self.current_run_dir) / "association_result_report"
            )
            report_dir.mkdir(parents=True, exist_ok=True)

            html_path = report_dir / "report.html"
            csv_base = report_dir / "report.csv"
            export_html_bundle(reports, html_path, final_rules)
            csv_paths = export_csv_bundle(
                reports,
                csv_base,
            )

            self.current_artifacts = {
                "task_type": "association",
                "report_kind": module.module_id,
                "operation": "APPLY_ASSOCIATION",
                "run_dir": str(self.current_run_dir),
                "report_dir": str(report_dir),
                "html": str(html_path),
                "rmu_csv": (
                    str(csv_paths[0]) if len(csv_paths) > 0 else ""
                ),
                "device_csv": (
                    str(csv_paths[1]) if len(csv_paths) > 1 else ""
                ),
                "g_output_dir": str(output_dir),
            }
            self.current_report_dir = str(report_dir)
            self.current_task_type = "association"
            self.current_rules = dict(final_rules)
            self.current_preview = None
            self._clear_association_table()

            # Save complete console log beside final association report.
            try:
                log_path = report_dir / "console.log"
                log_path.write_text(
                    self.log_edit.toPlainText(),
                    encoding="utf-8",
                )
                self.current_artifacts["console_log"] = str(log_path)
            except Exception as exc:
                self.log(f"保存关联完成 console.log 失败：{exc}")

            self.cfg["last_run_dir"] = str(self.current_run_dir)
            save_settings(self.cfg)

            self.progress_bar.setValue(100)
            self.progress_message.setText(
                "模型关联完成，最终 HTML / CSV 报告已生成"
            )
            self.workspace_status.show()
            self.workspace_status.setText(
                "模型关联完成，最终报告已生成"
            )
            apply_status_style(self.workspace_status, True)
            QTimer.singleShot(3500, self.workspace_status.hide)

            self._set_task_buttons_enabled(True)
            self.apply_btn.setEnabled(False)
            self._update_artifact_buttons("association")

            is_feeder = module.module_id == "FEEDER"
            object_label = "FeedLine 图元" if is_feeder else "设备图元"
            self.log(
                f"模型关联完成：本次选择={selected_total}，"
                f"成功写回={total}，执行时跳过={skipped_total}；"
                f"原始 G 文件未修改；输出目录={output_dir}"
            )
            self.log(f"关联完成 HTML：{html_path}")
            if len(csv_paths) > 0:
                self.log(
                    (
                        f"关联完成馈线汇总 CSV：{csv_paths[0]}"
                        if is_feeder
                        else f"关联完成环网柜 CSV：{csv_paths[0]}"
                    )
                )
            if len(csv_paths) > 1:
                self.log(
                    (
                        f"关联完成馈线段明细 CSV：{csv_paths[1]}"
                        if is_feeder
                        else f"关联完成设备 CSV：{csv_paths[1]}"
                    )
                )

            QMessageBox.information(
                self,
                "模型关联完成",
                f"模型关联处理完成。\n"
                f"本次选择：{selected_total} 个{object_label}\n"
                f"成功写回：{total} 个\n"
                f"执行时跳过：{skipped_total} 个\n\n"
                f"原始 G 文件未修改。\n"
                f"处理后的 G 文件：\n{output_dir}\n\n"
                f"最终校验报告：\n{html_path}",
            )

        except Exception as exc:
            self.progress_message.setText("模型关联失败")
            self.workspace_status.show()
            self.workspace_status.setText("模型关联失败")
            apply_status_style(self.workspace_status, False)
            self.log(f"模型关联失败：{exc}")
            self._set_task_buttons_enabled(True)
            QMessageBox.critical(
                self,
                "模型关联失败",
                str(exc),
            )
        finally:
            if db:
                db.close()

    # ------------------------------------------------------------
    # Console / generated artifacts
    # ------------------------------------------------------------
    def copy_log(self):
        QGuiApplication.clipboard().setText(self.log_edit.toPlainText())
        self.statusBar().showMessage("运行日志已复制。", 2500)

    def open_artifact(self, key):
        path_value = self.current_artifacts.get(key, "")
        if not path_value:
            QMessageBox.information(self, "打开结果", "当前没有可打开的结果文件。")
            return

        path = Path(path_value)
        if not path.exists():
            QMessageBox.warning(self, "打开结果", f"文件或目录不存在：\n{path}")
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.critical(self, "打开结果失败", str(exc))


def run():
    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    window = MainWindow()

    if ICON_PATH.exists():
        window.setWindowIcon(QIcon(str(ICON_PATH)))

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
