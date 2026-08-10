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
    QProgressBar, QSplitter
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
        self.log("工作流：模型校验 → 模型关联预览 → 模型关联回写。")
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
            f"{APP_NAME_EN} · 模型校验 · 关联预览 · 安全回写"
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
        grid.addWidget(self.module_combo, 0, 1, 1, 3)

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
            widget = create_settings_widget(module_id, self.module_stack, self.cfg)
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

        self.preview_btn = QPushButton("模型关联预览")
        self.preview_btn.setObjectName("secondary")
        self.preview_btn.clicked.connect(
            lambda: self.start_job("PREVIEW_ASSOCIATION")
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
            self.preview_btn,
            self.apply_btn,
            database_btn,
        ):
            button.setFixedSize(168, 42)

        actions.addWidget(self.validate_btn)
        actions.addWidget(self.preview_btn)
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
        """确保当前模型配置页完整显示，由最外层页面滚动条负责滚动。"""
        if not hasattr(self, "module_stack"):
            return

        widget = self.module_stack.currentWidget()
        if widget is None:
            return

        widget.adjustSize()
        hint = widget.sizeHint()
        minimum = widget.minimumSizeHint()

        height = max(
            hint.height(),
            minimum.height(),
            330,
        )

        # 多留少量余量，避免 GroupBox 标题/边框在不同 DPI 下被裁切。
        self.module_stack.setMinimumHeight(height + 18)
        self.module_stack.setMaximumHeight(height + 18)
        self.module_stack.updateGeometry()

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
            "• 模型回写必须先生成关联预览\n"
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
                "团队内部使用说明：RMU 模型校验、名称来源、报告和模型关联回写。",
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
            "2. 进入【模型工作区】，选择 RMU 环网柜模型和 G 文件/目录。\n"
            "3. 配置环网柜名称方向、开关名称来源以及表号/域号。\n"
            "4. 点击底部【模型校验】执行独立校验，并生成校验 HTML / CSV。\n"
            "5. 需要关联时先点击【模型关联预览】，确认预览结果后【执行模型关联】才会启用。\n"
            "6. 执行模型关联只修改 Workspace 中的安全副本，原始 G 文件不变。\n"
            "7. 关联完成后程序会重新校验安全副本，并生成与模型校验同规格的最终 HTML / CSV 报告。"
        )
        quick_text.setWordWrap(True)
        quick_layout.addWidget(quick_text)
        layout.addWidget(quick)

        rmu_naming = QGroupBox("环网柜名称识别规则")
        rmu_naming_layout = QVBoxLayout(rmu_naming)
        rmu_naming_text = QLabel(
            "• 环网柜仍然通过矩形框 + 三类目标设备图元自动识别。\n"
            "• 环网柜名称按照用户勾选的方向读取：上方 / 下方 / 左侧 / 右侧。\n"
            "• 同一方向只有一个名称时直接取最近名称，不判断颜色；只有存在多个名称时才使用绿色文字消歧。\n"
            "• 绿色依据 G 文件属性判断：lc=0,255,0 或 lcc=#00ff00；实际名称读取 Text 的 ts 属性。\n"
            "• 绿色名称不受旧的 120 坐标单位搜索距离限制，因此名称离环网柜较远也可以识别。\n"
            "• 如果所选方向没有绿色名称，才回退到普通名称识别规则。\n"
            "• 环网柜名称始终按字符串处理，支持 42646、RMU-42646、ABC_123、JED-RMU-01、ABC.01 等常见工程名称，不会强制转换成数字。"
        )
        rmu_naming_text.setWordWrap(True)
        rmu_naming_layout.addWidget(rmu_naming_text)
        layout.addWidget(rmu_naming)

        naming = QGroupBox("设备名称判断规则")
        naming_layout = QVBoxLayout(naming)
        naming_text = QLabel(
            "【使用 p_NameString】\n"
            "• CBreakerDis：直接使用 G 图元 p_NameString。\n"
            "• ZhaiWaiJieDiDaoZha：通过空间关系配对 CBreakerDis，数据库目标 CODE=开关名+D，"
            "同时要求 G 图元 p_NameString=该 CODE。\n"
            "• BusDis：直接使用 G 图元 p_NameString。\n\n"
            "【使用环网柜内图上文字】\n"
            "• CBreakerDis：完全不使用该图元 XML 的 p_NameString；将识别到的图上设备名作为逻辑 p_NameString。\n"
            "• ZhaiWaiJieDiDaoZha：完全不使用自身 XML 的 p_NameString；逻辑 p_NameString=配对开关名称+D。\n"
            "• BusDis：完全不使用 XML 的 p_NameString；逻辑 p_NameString 固定为 BUS。\n"
            "• 图上文字无法唯一识别时直接 FAIL，不猜测设备名称。"
        )
        naming_text.setWordWrap(True)
        naming_layout.addWidget(naming_text)
        layout.addWidget(naming)

        policy = QGroupBox("关联前强制校验策略")
        policy_layout = QVBoxLayout(policy)
        policy_text = QLabel(
            "• CBreakerDis：CODE 不得为空；CODE 必须等于当前用于校验的 p_NameString，NAME 不参与判断。\n"
            "• ZhaiWaiJieDiDaoZha：与 CBreakerDis 空间配对；用于校验的 p_NameString=开关名+D；CODE 必须与其一致，NAME 不参与判断。\n"
            "• BusDis：CODE 不得为空；CODE 必须等于当前用于校验的 p_NameString；图上文字模式固定为 BUS，NAME 不参与判断。\n"
            "• 环网柜数据库记录为 0 条或多条时，环网柜汇总直接 FAIL。若 G 设备未关联，禁止自动关联。\n"
            "• 环网柜数据库记录为 0 条或多条，但 G 设备已经有人为 KeyID 时，不丢弃该模型：继续反解当前设备并校验 CODE/p_NameString 和实际所属环网柜。\n"
            "• 已有关联模型如果实际属于其它环网柜，使用紫色 RMU_LINK 标记，属于硬错误，禁止自动覆盖。\n"
            "• 环网柜馈线或设备馈线不一致只使用橙色 FEEDER 告警，不再作为自动关联的强制阻断条件。\n"
            "• 唯一 RMU 下已有 KeyID 时，仍继续校验当前设备 ID、表号、域号、combined_id 和 Expected KeyID。"
        )
        policy_text.setWordWrap(True)
        policy_layout.addWidget(policy_text)
        layout.addWidget(policy)

        db_rule = QGroupBox("数据库强制校验")
        db_layout = QVBoxLayout(db_rule)
        db_text = QLabel(
            "• 13502 / CBreakerDis：CODE 不得为空，且 CODE 必须等于当前用于校验的 p_NameString；NAME 不参与判断。\n"
            "• 13514 / ZhaiWaiJieDiDaoZha：CODE 不得为空，且 CODE 必须等于当前用于校验的 p_NameString（开关名称+D）；NAME 不参与判断。\n"
            "• 13506 / BusDis：CODE 不得为空，且 CODE 必须等于当前用于校验的 p_NameString；图上文字模式固定为 BUS；NAME 不参与判断。\n"
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
            "黄色 WARN：设备尚未关联，但除馈线告警外满足自动关联条件。\n"
            "橙色 FEEDER：环网柜或设备馈线不一致/馈线信息异常，仅告警，不阻断模型关联。\n"
            "紫色 RMU_LINK：当前 KeyID 反解后的设备属于其他环网柜；这是硬错误，禁止自动覆盖。\n"
            "红色 FAIL：硬错误，例如 RMU 0条/多条且设备未关联、CODE 与 p_NameString 对不上、CODE不存在/重复、KeyID无法反解。\n"
            "注意：RMU 0条或多条时，环网柜汇总仍然是红色 FAIL；但已有人为 KeyID 的设备会继续检查，不因馈线问题直接判定模型错误。"
        )
        colors_text.setWordWrap(True)
        colors_layout.addWidget(colors_text)
        layout.addWidget(colors)

        assoc = QGroupBox("模型关联与 G 文件回写")
        assoc_layout = QVBoxLayout(assoc)
        assoc_text = QLabel(
            "建议先执行【模型关联预览】，确认所有 Expected KeyID 和可关联设备。\n"
            "真正执行模型关联时，程序会重新检查数据库及预览有效性，然后复制所有选中 G 文件到 Workspace/g_output，只修改副本。原始 G 文件绝不修改。\n\n"
            "CBreakerDis / ZhaiWaiJieDiDaoZha 回写：\n"
            "app=6500000, voltype=0, p_ReportType=1, state=41, keyid=Expected KeyID\n\n"
            "BusDis 回写：\n"
            "app=6500000, voltype=0, p_ReportType=1, state=15, keyid=Expected KeyID\n\n"
            "模型关联不会自动修改 p_NameString。自动关联不以馈线一致为前置条件，但目标数据库设备必须通过 CODE/p_NameString 校验并属于当前唯一环网柜。已有人工 KeyID 还会反查实际所属环网柜。"
        )
        assoc_text.setWordWrap(True)
        assoc_layout.addWidget(assoc_text)
        layout.addWidget(assoc)

        reports = QGroupBox("报告说明")
        reports_layout = QVBoxLayout(reports)
        reports_text = QLabel(
            "•【环网柜汇总】严格按 G 文件环网柜序号排列，每个 G 环网柜只显示一行；数据库 0 条或多条直接 FAIL，不展开多个 ID。\n"
            "•【设备明细】只显示 G 文件实际存在的设备图元，并展示逻辑 p_NameString、数据库 CODE、当前 KeyID、实际所属环网柜和馈线告警。\n"
            "• RMU 数据库记录异常时，已有人为 KeyID 的设备仍继续校验；未关联设备则直接阻断自动关联。\n"
            "• 当选择图上文字模式时，报告中的 p_NameString 表示用于校验的逻辑 p_NameString，不是 XML 原属性。\n"
            "• 每次模型校验、关联预览和关联完成都会自动生成对应 HTML / CSV；Workspace 历史按软件保留策略自动清理。"
        )
        reports_text.setWordWrap(True)
        reports_layout.addWidget(reports_text)
        layout.addWidget(reports)

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
        self.module_stack.setCurrentIndex(index)
        self.current_preview = None
        self.apply_btn.setEnabled(False)
        self.refresh_operation_state()
        QTimer.singleShot(0, self._update_module_stack_height)

    def refresh_operation_state(self):
        module_id = self.module_combo.currentData()
        if not module_id:
            return

        module = self.modules[module_id]
        self.validate_btn.setEnabled(module.supports("VALIDATE"))
        self.preview_btn.setEnabled(module.supports("PREVIEW_ASSOCIATION"))

        has_preview = bool(
            self.current_preview
            and self.current_preview.get("changes_by_file")
        )
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
        self.preview_btn.setEnabled(
            bool(enabled and module and module.supports("PREVIEW_ASSOCIATION"))
        )

        if not enabled:
            self.apply_btn.setEnabled(False)
        else:
            self.refresh_operation_state()

    def _update_artifact_buttons(self, task_type=""):
        """Only show result buttons for artifacts that really exist."""
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
        html_text, rmu_text, device_text = labels.get(
            task_type,
            ("打开 HTML", "打开环网柜 CSV", "打开设备 CSV"),
        )
        self.open_html_btn.setText(html_text)
        self.open_rmu_csv_btn.setText(rmu_text)
        self.open_device_csv_btn.setText(device_text)

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
                "PREVIEW_ASSOCIATION": "模型关联预览",
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

            for key in ("rmu_name_positions", "device_rules", "breaker_name_source"):
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
            change_count = sum(len(v) for v in self.current_preview["changes_by_file"].values())
            self.apply_btn.setEnabled(change_count > 0)
            self.log(f"关联预览已生成：可回写设备 {change_count} 个。")
        else:
            self.apply_btn.setEnabled(False)

        self.progress_bar.setValue(100)
        self.progress_message.setText(
            "模型校验完成，报告已生成"
            if self.current_task_type == "validation"
            else "模型关联预览完成，预览报告已生成"
        )
        self.workspace_status.setText("任务执行完成")
        apply_status_style(self.workspace_status, True)
        QTimer.singleShot(3500, self.workspace_status.hide)

        self._update_artifact_buttons(self.current_task_type)

        self.log(f"任务完成。本次运行目录：{report_dir}")
        self.log(f"HTML：{self.current_artifacts.get('html', '')}")
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
            (
                "模型校验完成，校验报告已生成。"
                if self.current_task_type == "validation"
                else "模型关联预览完成，预览报告已生成。"
            ),
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
    def apply_association(self):
        if not self.current_preview or not self.current_preview.get("changes_by_file"):
            QMessageBox.information(
                self,
                "模型关联",
                "当前没有可执行的关联预览，请先点击下方“模型关联预览”。",
            )
            return

        change_count = sum(
            len(v) for v in self.current_preview["changes_by_file"].values()
        )
        skipped_count = len(self.current_preview.get("skipped_rmus", []))
        message = (
            f"本次将关联 {change_count} 个设备图元。\n"
            f"因校验不通过而跳过的 RMU：{skipped_count} 个。\n\n"
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

            self.log("\n开始执行模型关联：重新验证 Oracle 数据库连接。")
            db = OracleClient(self.current_db_config())
            self.log(db.test_connection())

            self.progress_bar.setValue(15)
            self.progress_message.setText("正在写入安全 G 文件副本……")
            result_bundle = module.apply_association(
                db,
                files,
                settings,
                self.current_preview,
                self.log,
                output_g_dir=Path(self.current_run_dir) / "g_output",
            )

            total = int(result_bundle.get("applied_count", 0))
            output_dir = result_bundle.get("output_g_dir", "")
            copied_files = [
                Path(p)
                for p in result_bundle.get("copied_files", [])
                if Path(p).exists()
            ]

            if not copied_files:
                raise RuntimeError(
                    "模型关联已执行，但没有找到可用于最终校验的 G 文件安全副本。"
                )

            self.progress_bar.setValue(65)
            self.progress_message.setText(
                "关联完成，正在重新校验安全副本……"
            )
            self.log(
                "模型关联写入完成，开始对 g_output 中的安全副本执行最终模型校验。"
            )

            def final_progress(percent, message=""):
                # module.validate gives roughly 5~95; map it into 65~92
                mapped = 65 + int(max(0, min(100, int(percent))) * 0.27)
                self.progress_bar.setValue(min(mapped, 92))
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

            self.log(
                f"模型关联完成：修改设备图元={total}；"
                f"原始 G 文件未修改；输出目录={output_dir}"
            )
            self.log(f"关联完成 HTML：{html_path}")
            if len(csv_paths) > 0:
                self.log(f"关联完成环网柜 CSV：{csv_paths[0]}")
            if len(csv_paths) > 1:
                self.log(f"关联完成设备 CSV：{csv_paths[1]}")

            QMessageBox.information(
                self,
                "模型关联完成",
                f"模型关联处理完成，共修改 {total} 个设备图元。\n\n"
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
