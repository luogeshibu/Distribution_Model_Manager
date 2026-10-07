#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import ctypes
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QEventLoop, QEvent
from PySide6.QtGui import QIcon, QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox as QtMessageBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QPlainTextEdit, QFrame, QStackedWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QListWidget, QListWidgetItem, QGroupBox, QTabWidget, QScrollArea, QSizePolicy,
    QProgressBar, QSplitter, QDialog, QTextBrowser, QDialogButtonBox, QCheckBox, QSpinBox, QAbstractSpinBox, QAbstractScrollArea
)

from dmm.application.job_worker import JobWorker
from dmm.application.poke_worker import PokeProcessingWorker
from dmm.application.graphics_cleanup_worker import GraphicsCleanupWorker
from dmm.application.channel_status_worker import ChannelStatusRepositionWorker
from dmm.application.rmu_annotation_position_worker import RmuAnnotationPositionWorker
from dmm.application.feeder_avoidance_worker import FeederAvoidanceWorker
from dmm.application.rmu_feeder_topology_worker import RmuFeederTopologyWorker
from dmm.application.feedline_feeder_topology_worker import FeedlineFeederTopologyWorker
from dmm.application.whole_graph_topology_worker import WholeGraphTopologyWorker
from dmm.application.main_station_background_label_worker import MainStationBackgroundLabelWorker
from dmm.application.graphics_pipeline_worker import GraphicsPipelineWorker
from dmm.application.registry import get_model_modules
from dmm.ui.registry import create_settings_widget
from dmm.ui.widgets.element_management_page import ElementManagementWidget
from dmm.config.constants import (
    APP_NAME, APP_NAME_EN, APP_VERSION, APP_EDITION,
    APP_SITE_LABEL, APP_SITE_LABEL_EN, APP_BUILD_DATE,
    WORKSPACE_RETENTION_DAYS,
)
from dmm.config.defaults import (
    DEFAULT_RMU_NAME_EXCLUSIONS,
    DEFAULT_RMU_NAME_POSITIONS,
)
from dmm.config.settings import (
    load_settings,
    publish_central_settings,
    read_central_admin_state,
    release_central_admin,
    save_settings,
    sync_central_settings,
    takeover_central_admin,
)
from dmm.i18n import normalize_language, tr, translate_runtime_text, retranslate_qt_tree
from dmm.infrastructure.database.oracle import OracleClient
from dmm.domain.graphics_cleanup.channel_status import CHANNEL_STATUS_POSITIONS
from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    NOP_HORIZONTAL_POSITIONS,
    RMU_NAME_POSITIONS,
)
from dmm.domain.graphics_cleanup.feeder_avoidance import (
    DEFAULT_CORRIDOR_TOLERANCE,
    DEFAULT_TEXT_CLEARANCE,
    DEFAULT_FEEDER_SPACING,
    DEFAULT_MAX_RIGHT_SHIFT,
)
from dmm.domain.feeder.ring_discovery import (
    attach_makkah_ring_feeder_inventory,
    compare_makkah_ring_feeders_for_files,
)
from dmm.infrastructure.reporting.writer import (
    flatten_device_rows, flatten_rmu_rows,
    export_csv_bundle, export_html_bundle,
    DEVICE_FIELDS, RMU_FIELDS, DEVICE_LABELS, RMU_LABELS,
)
from dmm.infrastructure.remote import (
    ReadOnlySshClient,
    RemoteGFile,
    RemoteSnapshotService,
)
from dmm.infrastructure.filesystem.workspace import (
    WORKSPACE_ROOT,
    RUNS_ROOT,
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


class CurrentPageStackedWidget(QStackedWidget):
    """Size the stack from the visible page instead of the largest hidden page.

    QStackedWidget normally reports a size hint large enough for every page.
    The graphics workspace shares one source selector between a one-row LOCAL
    page and a much taller SSH page, so the default behavior leaves a large
    empty area when LOCAL is selected.  This stack deliberately follows only
    the current page and asks the parent layout to recalculate on page changes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._refresh_current_page_geometry)

    def sizeHint(self):
        current = self.currentWidget()
        if current is not None:
            return current.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        if current is not None:
            return current.minimumSizeHint()
        return super().minimumSizeHint()

    def _refresh_current_page_geometry(self, *_args):
        current = self.currentWidget()
        if current is not None:
            current.updateGeometry()
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()


class QMessageBox(QtMessageBox):
    """QMessageBox adapter that localizes user-facing title/body text.

    Engineering values and status codes remain untouched because the runtime
    translator only replaces known UI phrases.
    """

    @staticmethod
    def _localized(parent, value):
        language = getattr(parent, "language", "zh_CN")
        return translate_runtime_text(value, language)

    @classmethod
    def critical(cls, parent, title, text, *args, **kwargs):
        return QtMessageBox.critical(
            parent, cls._localized(parent, title), cls._localized(parent, text),
            *args, **kwargs
        )

    @classmethod
    def warning(cls, parent, title, text, *args, **kwargs):
        return QtMessageBox.warning(
            parent, cls._localized(parent, title), cls._localized(parent, text),
            *args, **kwargs
        )

    @classmethod
    def information(cls, parent, title, text, *args, **kwargs):
        return QtMessageBox.information(
            parent, cls._localized(parent, title), cls._localized(parent, text),
            *args, **kwargs
        )

    @classmethod
    def question(cls, parent, title, text, *args, **kwargs):
        return QtMessageBox.question(
            parent, cls._localized(parent, title), cls._localized(parent, text),
            *args, **kwargs
        )


class RemoteGFileListWorker(QThread):
    """Read the remote G-file directory without blocking the Qt GUI thread.

    This worker is presentation/I/O scheduling only. It delegates to the same
    read-only SSH client and returns the same RemoteGFile rows used previously.
    """

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, ssh_config: dict):
        super().__init__()
        self.ssh_config = dict(ssh_config)

    def run(self):
        try:
            cfg = self.ssh_config
            with ReadOnlySshClient(
                cfg["host"],
                cfg["port"],
                cfg["username"],
                cfg["password"],
            ) as client:
                rows = client.list_g_files(cfg["remote_directory"])
            self.completed.emit(rows)
        except Exception as exc:
            self.failed.emit(str(exc))


class AssociationExecutionWorker(QThread):
    """Execute model association outside the GUI thread.

    v4.1.33 keeps the exact validated snapshot, Oracle checks, module
    association decisions and G-file write-back implementation unchanged.
    Only execution scheduling moves to QThread so Qt can continuously animate
    the busy progress bar and repaint the console while association is busy.
    """

    log = Signal(str)
    completed = Signal(object)
    failed = Signal(object)

    def __init__(
        self,
        db_config: dict,
        module,
        files,
        settings: dict,
        execution_preview: dict,
        output_g_dir: Path,
    ):
        super().__init__()
        self.db_config = dict(db_config)
        self.module = module
        self.files = list(files)
        self.settings = settings
        self.execution_preview = execution_preview
        self.output_g_dir = Path(output_g_dir)

    def run(self):
        db = None
        try:
            self.log.emit("\n开始执行模型关联：重新验证 Oracle 数据库连接。")
            db = OracleClient(self.db_config)
            self.log.emit(db.test_connection())
            result_bundle = self.module.apply_association(
                db,
                self.files,
                self.settings,
                self.execution_preview,
                lambda text: self.log.emit(str(text)),
                output_g_dir=self.output_g_dir,
            )
            self.completed.emit(result_bundle)
        except Exception as exc:
            # Preserve the original exception object so the existing UI error
            # handling shows exactly the same business error text as before.
            self.failed.emit(exc)
        finally:
            if db:
                db.close()


class CentralAdminOwnershipWorker(QThread):
    """One-shot lightweight Admin ownership probe.

    Reads only central instance.json; shared business configuration is never
    pulled by this background check.
    """

    checked = Signal(object)
    failed = Signal(str)

    def __init__(self, settings_snapshot: dict, parent=None):
        super().__init__(parent)
        self.settings_snapshot = settings_snapshot

    def run(self):
        try:
            self.checked.emit(read_central_admin_state(self.settings_snapshot))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        ensure_workspace()
        cleanup_workspace(WORKSPACE_RETENTION_DAYS)

        self.cfg = load_settings(sync_central=False)
        self.language = normalize_language(self.cfg.get("language", "zh_CN"))
        self.cfg["language"] = self.language
        self.modules = get_model_modules()
        self.module_widgets = {}

        self.current_rules = {}
        self.current_preview = None
        self.current_artifacts = {}
        self.current_report_dir = self.cfg.get("last_run_dir", "")
        self.current_task_type = ""
        self.worker = None
        self.poke_worker = None
        self.poke_artifacts = {}
        self.graphics_cleanup_worker = None
        self.graphics_cleanup_artifacts = {}
        self.channel_status_worker = None
        self.channel_status_artifacts = {}
        self.rmu_annotation_worker = None
        self.rmu_annotation_artifacts = {}
        self.feeder_avoidance_worker = None
        self.feeder_avoidance_artifacts = {}
        self.rmu_feeder_topology_worker = None
        self.rmu_feeder_topology_artifacts = {}
        self.feedline_feeder_topology_worker = None
        self.feedline_feeder_topology_artifacts = {}
        self.whole_graph_topology_worker = None
        self.whole_graph_topology_artifacts = {}
        self.main_station_background_label_worker = None
        self.main_station_background_label_artifacts = {}
        self.graphics_pipeline_worker = None
        self.graphics_pipeline_artifacts = {}
        self.current_source_info = {}
        self.current_snapshot_files = []
        self.remote_file_rows = []
        self.remote_selected_names = set()
        self._remote_table_populating = False
        self._remote_row_by_name = {}
        self._remote_visible_count = 0
        self._poke_remote_visible_count = 0
        self._poke_remote_table_dirty = True
        self._poke_remote_table_populating = False
        self._poke_remote_row_by_name = {}
        self._remote_filter_timer = QTimer(self)
        self._remote_filter_timer.setSingleShot(True)
        self._remote_filter_timer.setInterval(120)
        self._remote_filter_timer.timeout.connect(self._run_remote_file_filter)
        self.remote_list_signature = None
        self.remote_list_worker = None
        self._remote_refresh_started_at = None
        self._remote_refresh_timer = QTimer(self)
        self._remote_refresh_timer.setInterval(1000)
        self._remote_refresh_timer.timeout.connect(
            self._update_remote_refresh_wait_status
        )

        # Admin ownership is session-scoped. Startup is strictly local-first;
        # only a proven Admin session performs the lightweight 10-second
        # instance.json ownership check.
        self._admin_session_epoch = None
        self._central_admin_check_worker = None
        self._central_admin_timer = QTimer(self)
        self._central_admin_timer.setInterval(10000)
        self._central_admin_timer.timeout.connect(
            self._schedule_central_admin_ownership_check
        )

        self.setWindowTitle(
            f"{APP_NAME} v{APP_VERSION} - {APP_EDITION} · {APP_SITE_LABEL}"
        )
        self.resize(1600, 960)
        self.setMinimumSize(1280, 800)

        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._apply_style()
        self._restore_ui_state()
        self._apply_language(save=False)
        self._check_saved_input_path_on_startup()
        self._central_admin_timer.start()

        self.log(f"{APP_NAME} v{APP_VERSION} 已启动。")
        self.log("工作流：模型校验 → 勾选可关联对象 → 执行模型关联。")
        self.log("安全模式：原始 G 文件永不修改；执行关联时只处理 Workspace 中的安全副本。")

    def eventFilter(self, watched, event):
        """Prevent wheel edits while keeping normal page scrolling.

        A wheel gesture over any QComboBox/QAbstractSpinBox must never alter
        the control value.  When the control lives inside a scroll area, the
        same gesture is forwarded to that page's vertical scrollbar instead.
        """
        if event is not None and event.type() == QEvent.Wheel:
            widget = watched if isinstance(watched, QWidget) else None
            control = None
            probe = widget
            for _ in range(6):
                if probe is None:
                    break
                if isinstance(probe, (QComboBox, QAbstractSpinBox)):
                    control = probe
                    break
                probe = probe.parentWidget()
            if control is not None:
                parent = control.parentWidget()
                while parent is not None:
                    if isinstance(parent, QAbstractScrollArea):
                        bar = parent.verticalScrollBar()
                        pixel_delta = event.pixelDelta().y()
                        angle_delta = event.angleDelta().y()
                        if pixel_delta:
                            bar.setValue(bar.value() - int(pixel_delta))
                        elif angle_delta:
                            steps = angle_delta / 120.0
                            distance = max(1, bar.singleStep()) * 3
                            bar.setValue(int(bar.value() - steps * distance))
                        break
                    parent = parent.parentWidget()
                event.ignore()
                return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------
    def _apply_style(self):
        if getattr(sys, "frozen", False):
            resource_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "dmm" / "resources"
        else:
            resource_dir = Path(__file__).resolve().parents[1] / "resources"
        spin_up_icon = (resource_dir / "spin_up.png").as_posix()
        spin_down_icon = (resource_dir / "spin_down.png").as_posix()
        style_sheet = """
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
            border-bottom: 4px solid #D3A84C;
        }

        #headerTitle {
            color: white;
            font-size: 23pt;
            font-weight: 700;
        }

        #headerSub {
            color: #EFE9D7;
        }

        #brandTag {
            color: #F2D28A;
            font-weight: 700;
            letter-spacing: 1px;
        }

        #siteMark {
            color: #F2D28A;
            font-family: "Segoe UI Symbol", "Microsoft YaHei UI";
            font-size: 27pt;
            font-weight: 700;
            padding: 0 8px 0 2px;
        }

        #sideNav {
            background: #004E3D;
            border: none;
        }

        QListWidget#navList {
            background: #004E3D;
            color: #E6E8D8;
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
            background: #B58A36;
            color: white;
        }

        QListWidget#navList::item:hover {
            background: #006650;
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
            border: 1px solid #DCCFAE;
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
            background: #F4F2E9;
        }

        /* Console-adjacent Task Progress should visually merge with its
           white card instead of showing the generic pale-green title chip. */
        QGroupBox#progressBox::title {
            background: white;
            padding: 0 5px;
        }

        QScrollArea#workspaceScroll,
        QScrollArea#workspaceOuterScroll,
        QScrollArea#graphicsOuterScroll {
            background: transparent;
            border: none;
        }

        QScrollArea#workspaceScroll > QWidget > QWidget,
        QScrollArea#workspaceOuterScroll > QWidget > QWidget,
        QScrollArea#graphicsOuterScroll > QWidget > QWidget {
            background: transparent;
        }

        #graphicsFunctionBar {
            background: #E8F7F1;
            border: 1px solid #B8DDCF;
            border-radius: 8px;
        }

        #graphicsFunctionTitle {
            color: #006B52;
            font-weight: 700;
            font-size: 11pt;
            padding-right: 8px;
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
            border: 1px solid #B58A36;
        }

        /* SpinBox 上/下按钮使用与整套界面一致的深绿色高对比样式。
           之前浅灰按钮在现场显示器和高 DPI 下几乎看不清。 */
        QSpinBox {
            padding-right: 34px;
        }

        QSpinBox::up-button,
        QSpinBox::down-button {
            width: 28px;
            border-left: 1px solid #005640;
            background: #006B52;
        }

        QSpinBox::up-button {
            border-top-right-radius: 5px;
        }

        QSpinBox::down-button {
            border-bottom-right-radius: 5px;
        }

        QSpinBox::up-button:hover,
        QSpinBox::down-button:hover {
            background: #00966E;
        }

        QSpinBox::up-button:pressed,
        QSpinBox::down-button:pressed {
            background: #004D3A;
        }

        QSpinBox::up-arrow {
            image: url("__SPIN_UP_ICON__");
            width: 14px;
            height: 10px;
        }

        QSpinBox::down-arrow {
            image: url("__SPIN_DOWN_ICON__");
            width: 14px;
            height: 10px;
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
            border-color: #BDA365;
        }

        QPushButton:pressed {
            background: #B58A36;
            color: white;
            border-color: #8F6A27;
        }

        QPushButton:focus {
            border: 1px solid #B58A36;
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
            background: #F5F3EA;
            color: #5F6C5D;
            border: 1px solid #E2D6B7;
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
            border: 1px solid #DCCFAE;
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
            background: #B58A36;
            border-radius: 6px;
        }

        QTabWidget::pane {
            border: 1px solid #DCCFAE;
            background: white;
        }

        QTabBar::tab {
            background: #E9F2EE;
            padding: 8px 18px;
            margin-right: 2px;
        }

        QTabBar::tab:selected {
            background: #B58A36;
            color: white;
        }
        """
        style_sheet = style_sheet.replace("__SPIN_UP_ICON__", spin_up_icon).replace("__SPIN_DOWN_ICON__", spin_down_icon)
        self.setStyleSheet(style_sheet)

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

        # Small Makkah-site visual mark: restrained star-and-crescent accent
        # beside the existing NARI logo, without changing the page structure.
        site_mark = QLabel("☪")
        site_mark.setObjectName("siteMark")
        site_mark.setAccessibleName("麦加现场标识")
        header_layout.addWidget(site_mark)

        titles = QVBoxLayout()

        brand = QLabel("NARI国际业务部内部工具")
        brand.setObjectName("brandTag")
        self.header_brand_label = brand

        title = QLabel(APP_NAME)
        title.setObjectName("headerTitle")
        self.header_title_label = title

        subtitle = QLabel(
            f"{APP_NAME_EN} · 模型校验 · 校验候选 · 安全回写"
        )
        subtitle.setObjectName("headerSub")
        self.header_subtitle_label = subtitle

        titles.addStretch()
        titles.addWidget(brand)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        titles.addStretch()

        header_layout.addLayout(titles, 1)

        version = QLabel(
            f"{APP_EDITION} · {APP_SITE_LABEL}  |  v{APP_VERSION}"
        )
        version.setObjectName("headerSub")
        self.header_version_label = version
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

        # 图形工作区与模型工作区保持同一级导航样式。
        # 具体图形操作不再放在左侧二级菜单，而是在右侧工作区通过
        # “图形处理类型”统一编排，便于后续继续增加其它图形处理任务。
        nav_specs = (
            ("模型工作区", 0),
            ("图形工作区", 3),
            ("数据库", 1),
            ("图元管理", 2),
            ("运行历史", 4),
            ("设置", 5),
            ("帮助", 6),
        )
        for label, page_index in nav_specs:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, page_index)
            item.setData(Qt.UserRole + 1, "primary")
            item.setData(Qt.UserRole + 2, label)
            self.nav.addItem(item)

        self.nav.setCurrentRow(0)
        sidebar_layout.addWidget(self.nav)
        body_layout.addWidget(sidebar)

        # 每个功能模块自带日志/结果，不再设置独立的全局“报告”一级菜单。
        self.pages = QStackedWidget()
        self.nav.currentRowChanged.connect(self._on_nav_row_changed)

        self.pages.addWidget(self._build_workspace_page())
        self.pages.addWidget(self._build_database_page())
        self.element_management_page = self._build_element_management_page()
        self.pages.addWidget(self.element_management_page)
        self.graphics_processing_page = self._build_graphics_processing_page()
        self.pages.addWidget(self.graphics_processing_page)
        self.pages.addWidget(self._build_history_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(self._build_help_page())

        self.pages.setCurrentIndex(0)
        body_layout.addWidget(self.pages, 1)

    # ------------------------------------------------------------
    # Element management page
    # ------------------------------------------------------------
    def _build_element_management_page(self):
        page = ElementManagementWidget(self.cfg, self)
        page.catalogChanged.connect(
            lambda: self._invalidate_validation_snapshot("图元标记配置已修改")
        )
        page.centralSyncRequested.connect(self.sync_central_configuration)
        return page

    def _on_nav_row_changed(self, row):
        item = self.nav.item(int(row)) if hasattr(self, "nav") and int(row) >= 0 else None
        if item is None:
            return
        page_index = item.data(Qt.UserRole)
        if page_index is None:
            return
        try:
            page_index = int(page_index)
        except (TypeError, ValueError):
            return
        if hasattr(self, "pages"):
            self.pages.setCurrentIndex(page_index)
        self._on_primary_nav_changed(page_index)

    def _on_primary_nav_changed(self, index):
        # 图形工作区当前仅提供 Poke 处理。进入该工作区时同步公共文件源；
        # 以后新增其它图形处理类型时仍复用这一工作区级公共输入状态。
        if int(index) != 3 or not hasattr(self, "poke_input_source_combo"):
            return
        rebuild = (
            getattr(self, "_poke_remote_table_dirty", False)
            or self.poke_remote_file_table.rowCount() != len(self.remote_file_rows)
        )
        self._sync_poke_source_from_workspace(rebuild_remote=rebuild)

    # ------------------------------------------------------------
    # Graphics processing / Poke jump
    # ------------------------------------------------------------
    def _build_graphics_processing_page(self):
        """Build the Graphics Workspace using the same task-orchestration pattern
        as the Model Workspace.

        The left navigation contains only one first-level ``图形工作区`` entry.
        Concrete graphics operations are selected from ``图形处理类型`` on the
        right, so future operations can be added without growing a second menu.
        """
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("graphicsOuterScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content.setObjectName("graphicsContent")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(12)
        outer.addWidget(
            self._page_header(
                "图形工作区",
                "图形配置、处理进度和运行日志集中在当前工作区；后续图形处理功能统一通过图形处理类型进行编排。",
            )
        )

        # Keep the top-level task selector consistent with Model Workspace.
        job_box = QGroupBox("图形任务")
        grid = QGridLayout(job_box)
        grid.setContentsMargins(14, 18, 14, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("图形处理类型"), 0, 0)
        self.graphics_operation_combo = NoWheelComboBox()
        self.graphics_operation_combo.addItem("Poke 跳转处理", "POKE")
        self.graphics_operation_combo.addItem("环网柜网络图元清理", "RMU_NETWORK_CLEANUP")
        self.graphics_operation_combo.addItem("环网柜 channel_status 移动", "RMU_CHANNEL_STATUS_REPOSITION")
        self.graphics_operation_combo.addItem("NOP / 环网柜名称位置调整", "RMU_ANNOTATION_REPOSITION")
        self.graphics_operation_combo.addItem("馈线避让调整", "FEEDER_AVOIDANCE")
        self.graphics_operation_combo.addItem("环网柜馈线拓扑分析", "RMU_FEEDER_TOPOLOGY")
        self.graphics_operation_combo.addItem("馈线段所属馈线分析", "FEEDLINE_FEEDER_TOPOLOGY")
        self.graphics_operation_combo.addItem("主网入口背景标签修正", "MAIN_STATION_BACKGROUND_LABEL")
        self.graphics_operation_combo.addItem("整图馈线拓扑分析", "WHOLE_GRAPH_TOPOLOGY")
        self.graphics_operation_combo.addItem("组合处理（一键）", "GRAPHICS_PIPELINE")
        self.graphics_operation_combo.currentIndexChanged.connect(
            self.on_graphics_operation_changed
        )
        grid.addWidget(self.graphics_operation_combo, 0, 1, 1, 2)

        graphics_actions = QHBoxLayout()
        self.graphics_operation_help_btn = QPushButton("当前图形帮助")
        self.graphics_operation_help_btn.setMinimumWidth(112)
        self.graphics_operation_help_btn.clicked.connect(
            self.show_current_graphics_operation_help
        )
        graphics_actions.addWidget(self.graphics_operation_help_btn)
        graphics_actions.addStretch()
        grid.addLayout(graphics_actions, 0, 3)
        outer.addWidget(job_box)

        # 图形工作区内所有处理任务共用同一套本地/SSH只读文件来源。
        # 保留既有 poke_* 控件命名以避免破坏已验证的远程文件选择状态。
        outer.addWidget(self._build_poke_source_box())

        self.graphics_operation_stack = QStackedWidget()
        poke_page = QWidget()
        poke_layout = QVBoxLayout(poke_page)
        poke_layout.setContentsMargins(0, 0, 0, 0)
        poke_layout.addWidget(self._build_poke_processing_panel())
        self.graphics_operation_stack.addWidget(poke_page)

        cleanup_page = QWidget()
        cleanup_layout = QVBoxLayout(cleanup_page)
        cleanup_layout.setContentsMargins(0, 0, 0, 0)
        cleanup_layout.addWidget(self._build_rmu_network_cleanup_panel())
        self.graphics_operation_stack.addWidget(cleanup_page)

        channel_status_page = QWidget()
        channel_status_layout = QVBoxLayout(channel_status_page)
        channel_status_layout.setContentsMargins(0, 0, 0, 0)
        channel_status_layout.addWidget(self._build_rmu_channel_status_panel())
        self.graphics_operation_stack.addWidget(channel_status_page)

        annotation_page = QWidget()
        annotation_layout = QVBoxLayout(annotation_page)
        annotation_layout.setContentsMargins(0, 0, 0, 0)
        annotation_layout.addWidget(self._build_rmu_annotation_position_panel())
        self.graphics_operation_stack.addWidget(annotation_page)

        feeder_avoidance_page = QWidget()
        feeder_avoidance_layout = QVBoxLayout(feeder_avoidance_page)
        feeder_avoidance_layout.setContentsMargins(0, 0, 0, 0)
        feeder_avoidance_layout.addWidget(self._build_feeder_avoidance_panel())
        self.graphics_operation_stack.addWidget(feeder_avoidance_page)

        rmu_feeder_topology_page = QWidget()
        rmu_feeder_topology_layout = QVBoxLayout(rmu_feeder_topology_page)
        rmu_feeder_topology_layout.setContentsMargins(0, 0, 0, 0)
        rmu_feeder_topology_layout.addWidget(self._build_rmu_feeder_topology_panel())
        self.graphics_operation_stack.addWidget(rmu_feeder_topology_page)

        feedline_feeder_topology_page = QWidget()
        feedline_feeder_topology_layout = QVBoxLayout(feedline_feeder_topology_page)
        feedline_feeder_topology_layout.setContentsMargins(0, 0, 0, 0)
        feedline_feeder_topology_layout.addWidget(self._build_feedline_feeder_topology_panel())
        self.graphics_operation_stack.addWidget(feedline_feeder_topology_page)

        main_station_background_label_page = QWidget()
        main_station_background_label_layout = QVBoxLayout(main_station_background_label_page)
        main_station_background_label_layout.setContentsMargins(0, 0, 0, 0)
        main_station_background_label_layout.addWidget(self._build_main_station_background_label_panel())
        self.graphics_operation_stack.addWidget(main_station_background_label_page)

        whole_graph_topology_page = QWidget()
        whole_graph_topology_layout = QVBoxLayout(whole_graph_topology_page)
        whole_graph_topology_layout.setContentsMargins(0, 0, 0, 0)
        whole_graph_topology_layout.addWidget(self._build_whole_graph_topology_panel())
        self.graphics_operation_stack.addWidget(whole_graph_topology_page)

        pipeline_page = QWidget()
        pipeline_layout = QVBoxLayout(pipeline_page)
        pipeline_layout.setContentsMargins(0, 0, 0, 0)
        pipeline_layout.addWidget(self._build_graphics_pipeline_panel())
        self.graphics_operation_stack.addWidget(pipeline_page)

        outer.addWidget(self.graphics_operation_stack)

        outer.addStretch()
        scroll.setWidget(content)
        page_layout.addWidget(scroll)
        return page

    def on_graphics_operation_changed(self, index):
        if not hasattr(self, "graphics_operation_stack"):
            return
        index = max(0, min(int(index), self.graphics_operation_stack.count() - 1))
        self.graphics_operation_stack.setCurrentIndex(index)

    def show_current_graphics_operation_help(self):
        operation_id = str(
            self.graphics_operation_combo.currentData()
            if hasattr(self, "graphics_operation_combo")
            else "POKE"
        ).upper()
        if operation_id == "POKE":
            title = "Poke Jump Help" if self.language == "en_US" else "Poke 跳转处理帮助"
            text = (
                "Adds or repairs Poke jumps for main-network feeder labels and SMART/SMR RMUs. "
                "Source G files remain read-only; results are written to Workspace safe copies."
                if self.language == "en_US"
                else "为主网馈线标题和 SMART/SMR 智能环网柜新增或修复 Poke 跳转。"
                "原始 G 文件保持只读，处理结果写入 Workspace 安全副本。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "RMU_NETWORK_CLEANUP":
            title = "RMU Network Graphic Cleanup" if self.language == "en_US" else "环网柜网络图元清理帮助"
            text = (
                "Removes the fixed Generator(G), Temporary Cable(L), and General Note(N) Status icons "
                "from selected Makkah G files. Source files remain read-only and only Workspace safe copies are changed."
                if self.language == "en_US"
                else "删除麦加 G 图中固定的 Generator(G)、Temporary Cable(L)、General Note(N) 三类 Status 图元。"
                "规则按 devref 写死，不做位置猜测；原始 G 文件保持只读，只修改 Workspace 安全副本。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "RMU_CHANNEL_STATUS_REPOSITION":
            title = "RMU channel_status Reposition" if self.language == "en_US" else "环网柜 channel_status 移动帮助"
            text = (
                "Moves each RMU channel_status Status icon to the selected anchor inside its RMU frame, using the same field-proven logic as G File Studio v2.18.244. "
                "Only the Status icon is moved; source files stay read-only."
                if self.language == "en_US"
                else "完全复用 G File Studio v2.18.244 的 channel_status 定位与移动规则：识别有效 RMU 外框，"
                "为每个柜体寻找唯一 channel_status Status，并移动到所选框内位置。只移动该 Status 本身，"
                "不移动环网柜、母线、设备、文字或连接线；原始 G 文件保持只读。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "RMU_ANNOTATION_REPOSITION":
            title = "RMU NOP / Name Position" if self.language == "en_US" else "NOP / 环网柜名称位置调整帮助"
            text = (
                "NOP is placed only on the left/right side of the RMU and its vertical center is aligned exactly with the corresponding Y*/Q* switch center. RMU names can be placed at the midpoint of the top/right/bottom/left frame edge. Source G files stay read-only."
                if self.language == "en_US"
                else "NOP 只在环网柜左侧或右侧显示，并且必须与柜内对应的 Y*/Q* 开关设备（如 Y1/Y2/Y3/Q1/Q2/Q3）水平中心对齐：NOP 中心 Y = 开关中心 Y。"
                "环网柜名称只从 RMU 框外 Text 中识别（Text 中心落在任意 RMU 框内即排除），固定按 RIGHT → BOTTOM → GLOBAL fallback；名称位置仍可选择上、右、下、左四个边框的正中位置。若名称已有 Poke 跳转，移动名称时 Poke 会使用相同位移同步移动。原始 G 文件保持只读，只修改 Workspace 安全副本。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "FEEDER_AVOIDANCE":
            title = "Feeder Text Avoidance" if self.language == "en_US" else "馈线避让调整帮助"
            text = (
                "Only FeedLine geometry is changed. In the same RMU column, adjacent non-overlapping RMU-to-RMU feeder spans share the same inner lane, while longer spans that cross them are assigned progressively farther outer lanes. Right-side lanes expand right and left-side lanes mirror left. RMU names/NOP text, endpoints and topology attributes never move."
                if self.language == "en_US"
                else "只移动 FeedLine，不移动环网柜名称、NOP / N.O.P、环网柜本体或其它设备。"
                "同一 RMU 列内，相邻环网柜之间、Y 范围不重叠的馈线共用同一条内侧轨道并保持对齐；"
                "跨越其它环网柜的长馈线按重叠层级依次放到更外侧轨道。右侧向右外扩，左侧向左镜像外扩。"
                "轨道间距、同列判定范围、最大外移和左右侧处理均可配置。原连接端点与 link / node_area / keyid 等拓扑属性保持不变。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "RMU_FEEDER_TOPOLOGY":
            title = "RMU Feeder Topology Analysis" if self.language == "en_US" else "环网柜馈线拓扑分析帮助"
            text = (
                "Read-only topology analysis for Makkah ring drawings. It discovers all main-network feeder sources from Bay CBreakers and nearby feeder labels, builds the electrical graph from link/node_area with only strict endpoint repairs, maps each NOP to the corresponding Y*/Q* switch by RMU side and center-Y alignment, and stops feeder propagation at that switch. Normal RMUs receive one feeder; NOP boundary RMUs keep both side feeders instead of being forced into one. No G file or database is modified."
                if self.language == "en_US"
                else "麦加环网图只读拓扑分析：先从主网 Bay 的 CBreaker 与附近馈线标题识别全部馈线源，再使用 link / node_area 建立电气连接图；只有 XML 缺链时才允许极小误差的严格几何补链。NOP 先归属最近 RMU，并且只在该 RMU 框内寻找 Y*/Q* 开关：NOP 位于左/右侧时优先按水平中心 Y 对齐，同一水平行有多个开关时再取离 NOP 最近者；位于上/下侧时镜像按中心 X 对齐。线路允许多路传播，只有真正走到 NOP 开关的支路在该开关处停止，其它非 NOP 端口继续传播。普通 RMU 给出唯一所属馈线；NOP 边界柜由非 NOP 端口侧唯一一致馈线决定所属。不会修改 G 文件，也不会写数据库。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "FEEDLINE_FEEDER_TOPOLOGY":
            title = "FeedLine Feeder Topology Analysis" if self.language == "en_US" else "馈线段所属馈线分析帮助"
            text = (
                "Read-only Makkah FeedLine ownership analysis. It reuses the already validated feeder-source, link/node_area, strict geometry-repair and red-NOP port-boundary rules from the RMU topology analysis, without changing that module. Each FeedLine is CONFIRMED only when exactly one main feeder can reach it without crossing a red NOP switch; multiple reachable feeders are CONFLICT and no reachable feeder is UNRESOLVED. No G file or Oracle data is modified."
                if self.language == "en_US"
                else "独立判断每一条 FeedLine 属于哪条主网馈线，不修改已经验证通过的环网柜馈线拓扑分析逻辑。"
                "分析复用相同的主网馈线源、link/node_area、严格几何补链和红色 NOP 端口级断点规则：线路可以多路传播，只有真正碰到红色 NOP 对应 Y*/Q* 开关的那一路停止。"
                "一条 FeedLine 只能由一条有效主网馈线到达时判定 CONFIRMED；多馈线同时可达为 CONFLICT；无馈线可达为 UNRESOLVED。只读 G 文件，不修改 G，也不连接、不查询、不写入 Oracle。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "MAIN_STATION_BACKGROUND_LABEL":
            title = "Main-station Background Label Repair" if self.language == "en_US" else "主网入口背景标签修正帮助"
            text = (
                "Repairs colored jump labels near a confirmed main-station CBreaker. A label group must have a visible background and a nearby parenthesized target such as (33359). The parenthesized target is preserved; only the other feeder-like text is replaced with the confirmed main-station feeder name. Candidates farther than 300 G units or with multiple main-station matches are never auto-modified. Source G files stay read-only and safe copies are written to Workspace."
                if self.language == "en_US"
                else "修正主网开关附近的带背景跳转标签：候选必须具有可见背景色，并且同一背景内存在形如 (33359) 的目标环网柜名称。括号目标绝不修改，只把另一段馈线样式文字替换成该主网 CBreaker 已确认的馈线名称。距离超过 300G 或 300G 内存在多个主网候选时不自动修改。原始 G 文件不覆盖，只输出 Workspace 安全副本。此类背景跳转标签在整图馈线拓扑分析中会被强制排除，绝不作为馈线锚点。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "WHOLE_GRAPH_TOPOLOGY":
            title = "Whole-Graph Feeder Topology Analysis" if self.language == "en_US" else "整图馈线拓扑分析帮助"
            text = (
                "Read-only topology analysis for exactly one G file. It does not use Oracle or model tables. Main-station Bay labels and feeder names written directly on FeedLine (for example TURB-BH-04) both become feeder anchors. Red NOPs owned by an RMU keep the existing Y*/Q* boundary rule; all other red NOPs are treated as pole-switch NOPs. Feeder propagation never crosses an NOP switch, and the NOP switch itself is not assigned a feeder; both sides are reported independently."
                if self.language == "en_US"
                else "针对单个 G 文件做整张图的纯图形只读拓扑分析，不访问 Oracle，也不做任何模型表校验。一个主站出线有且只能有一个馈线名字：主网 Bay/CBreaker 标题优先；若没有主站设备而只在线路末端写 TRUB-BH21 这类名字，则仅在无设备源的末端区域选中唯一文字源。同名重复或同一源端多个名字都不会同时传播。带背景跳转标签会在馈线识别前强制排除。红色 NOP 按既有规则作为硬边界，NOP 每一侧也必须最终只得到一个主站/馈线名字，否则直接报告源唯一性/NOP拓扑异常。"
            )
            QMessageBox.information(self, title, text)
            return
        if operation_id == "GRAPHICS_PIPELINE":
            title = "Graphics Pipeline" if self.language == "en_US" else "组合处理（一键）帮助"
            text = (
                "Runs selected graphics operations serially on the same safe copy. A final G file is published only after all selected steps for that file succeed."
                if self.language == "en_US"
                else "将勾选的图形处理步骤按固定顺序串行作用于同一份 Workspace 安全副本："
                "网络图元清理 → channel_status 移动 → Poke 跳转。单个文件任一步骤失败时不发布最终 G，"
                "但会继续处理其它文件。"
            )
            QMessageBox.information(self, title, text)

    def _build_poke_processing_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "主网馈线标题按 405 / SUBSTATION.GRAPH_NAME 生成跳转；"
            "智能 RMU 复用 G File Studio 的 RMU Poke 属性和数据库命名链。"
            "只修改本次运行目录中的安全副本。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        option_box = QGroupBox("Poke 跳转类型")
        option_layout = QVBoxLayout(option_box)
        self.poke_enable_main_feeder = QCheckBox(
            "主网馈线标题跳转：GVCM-AH304 → 405.GRAPH_NAME?locateLabel=AH304&&scaleFlag=true"
        )
        self.poke_enable_main_feeder.setChecked(True)
        self.poke_enable_smart_rmu = QCheckBox(
            "智能 RMU 跳转：仅 SMART / SMR 环网柜，复制 G File Studio 的 RMU Poke 处理"
        )
        self.poke_enable_smart_rmu.setChecked(True)
        option_layout.addWidget(self.poke_enable_main_feeder)
        option_layout.addWidget(self.poke_enable_smart_rmu)
        note = QLabel(
            "主网馈线 Poke 直接包住图中的馈线名称 Text；如果该名称已有相关 Poke 则复用/修复，"
            "没有则新增。智能 RMU 也只对识别为智能的柜体名称加 Poke。"
        )
        note.setWordWrap(True)
        note.setObjectName("moduleDescription")
        option_layout.addWidget(note)
        layout.addWidget(option_box)

        actions = QHBoxLayout()
        self.poke_run_btn = QPushButton("开始 Poke 跳转处理")
        self.poke_run_btn.setObjectName("primary")
        self.poke_run_btn.clicked.connect(self.start_poke_processing)
        self.poke_open_output_btn = QPushButton("打开 G 输出目录")
        self.poke_open_output_btn.setEnabled(False)
        self.poke_open_output_btn.clicked.connect(self._open_poke_output_dir)
        self.poke_open_report_btn = QPushButton("打开 Poke 报告")
        self.poke_open_report_btn.setEnabled(False)
        self.poke_open_report_btn.clicked.connect(self._open_poke_report)
        actions.addWidget(self.poke_run_btn)
        actions.addWidget(self.poke_open_output_btn)
        actions.addWidget(self.poke_open_report_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.poke_progress = QProgressBar()
        self.poke_progress.setRange(0, 100)
        self.poke_progress.setValue(0)
        layout.addWidget(self.poke_progress)
        self.poke_progress_message = QLabel("等待处理")
        self.poke_progress_message.setObjectName("pageSub")
        layout.addWidget(self.poke_progress_message)

        log_box = QGroupBox("Poke 运行日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.poke_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.poke_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch()
        log_layout.addLayout(log_actions)
        self.poke_log_edit = QPlainTextEdit()
        self.poke_log_edit.setReadOnly(True)
        log_layout.addWidget(self.poke_log_edit, 1)
        layout.addWidget(log_box, 1)

        self._sync_poke_source_from_workspace(rebuild_remote=True)
        return panel

    def _build_rmu_network_cleanup_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "删除麦加环网柜下方固定的 G / L / N 网络状态图元。"
            "识别规则直接按 Status.devref 写死，不依赖 RMU 名称、坐标、数据库或拓扑。"
            "只修改本次运行目录中的 Workspace 安全副本。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        target_box = QGroupBox("固定清理目标")
        target_layout = QVBoxLayout(target_box)
        for text in (
            "NariPd_Generator.zt.icn.g  （G）",
            "NariPd_Temporary_Cable.zt.icn.g  （L）",
            "NariPd_General_Note.zt.icn.g  （N）",
        ):
            label = QLabel(text)
            label.setObjectName("moduleDescription")
            target_layout.addWidget(label)
        note = QLabel(
            "现场样本实际使用 NariPd_General_Note.zt.icn.g；同时兼容旧拼写 "
            "NariPd_General_Note.zt.icg.g。只删除 <Status> 元素，不删除其它图元。"
        )
        note.setWordWrap(True)
        note.setObjectName("moduleDescription")
        target_layout.addWidget(note)
        layout.addWidget(target_box)

        actions = QHBoxLayout()
        self.graphics_cleanup_run_btn = QPushButton("开始环网柜网络图元清理")
        self.graphics_cleanup_run_btn.setObjectName("primary")
        self.graphics_cleanup_run_btn.clicked.connect(self.start_rmu_network_cleanup)
        self.graphics_cleanup_open_output_btn = QPushButton("打开 G 输出目录")
        self.graphics_cleanup_open_output_btn.setEnabled(False)
        self.graphics_cleanup_open_output_btn.clicked.connect(
            self._open_graphics_cleanup_output_dir
        )
        self.graphics_cleanup_open_report_btn = QPushButton("打开清理报告")
        self.graphics_cleanup_open_report_btn.setEnabled(False)
        self.graphics_cleanup_open_report_btn.clicked.connect(
            self._open_graphics_cleanup_report
        )
        actions.addWidget(self.graphics_cleanup_run_btn)
        actions.addWidget(self.graphics_cleanup_open_output_btn)
        actions.addWidget(self.graphics_cleanup_open_report_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.graphics_cleanup_progress = QProgressBar()
        self.graphics_cleanup_progress.setRange(0, 100)
        self.graphics_cleanup_progress.setValue(0)
        layout.addWidget(self.graphics_cleanup_progress)
        self.graphics_cleanup_progress_message = QLabel("等待处理")
        self.graphics_cleanup_progress_message.setObjectName("pageSub")
        layout.addWidget(self.graphics_cleanup_progress_message)

        log_box = QGroupBox("环网柜网络图元清理日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.graphics_cleanup_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.graphics_cleanup_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch()
        log_layout.addLayout(log_actions)
        self.graphics_cleanup_log_edit = QPlainTextEdit()
        self.graphics_cleanup_log_edit.setReadOnly(True)
        log_layout.addWidget(self.graphics_cleanup_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_rmu_channel_status_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "移动麦加环网柜中的 channel_status.zt.icn.g 红色状态点。"
            "定位、RMU 归属和移动算法直接复用 G File Studio v2.18.244 的现场逻辑；"
            "只移动 channel_status Status 本身，不移动环网柜、母线、设备、文字或连接线。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        option_box = QGroupBox("channel_status 移动设置")
        option_layout = QHBoxLayout(option_box)
        option_layout.setContentsMargins(14, 18, 14, 12)
        option_layout.setSpacing(10)
        option_layout.addWidget(QLabel("框内位置"))
        self.channel_status_position_combo = NoWheelComboBox()
        self.channel_status_position_combo.setMinimumWidth(150)
        for value, label in CHANNEL_STATUS_POSITIONS.items():
            self.channel_status_position_combo.addItem(label, value)
        default_index = self.channel_status_position_combo.findData("bottom_left")
        if default_index >= 0:
            self.channel_status_position_combo.setCurrentIndex(default_index)
        option_layout.addWidget(self.channel_status_position_combo)
        option_layout.addWidget(QLabel("距边"))
        self.channel_status_margin_spin = QSpinBox()
        self.channel_status_margin_spin.setRange(0, 1000)
        self.channel_status_margin_spin.setValue(5)
        self.channel_status_margin_spin.setSuffix(" px")
        self.channel_status_margin_spin.setFixedWidth(140)
        option_layout.addWidget(self.channel_status_margin_spin)
        option_layout.addStretch(1)
        layout.addWidget(option_box)

        note = QLabel(
            "支持左上角、上边中点、右上角、左边中点、右边中点、左下角、下边中点、右下角 8 个位置。"
            "状态点中心优先在 RMU 框内查找；兼容旧图时允许在外框扩展 40 像素范围内寻找，"
            "多个候选时取距离本柜 BusDis 中心最近的一点，同一个 Status 不会分配给多个柜体。"
        )
        note.setWordWrap(True)
        note.setObjectName("moduleDescription")
        layout.addWidget(note)

        actions = QHBoxLayout()
        self.channel_status_run_btn = QPushButton("开始移动 channel_status")
        self.channel_status_run_btn.setObjectName("primary")
        self.channel_status_run_btn.clicked.connect(self.start_rmu_channel_status_reposition)
        self.channel_status_open_output_btn = QPushButton("打开 G 输出目录")
        self.channel_status_open_output_btn.setEnabled(False)
        self.channel_status_open_output_btn.clicked.connect(
            self._open_channel_status_output_dir
        )
        self.channel_status_open_report_btn = QPushButton("打开移动报告")
        self.channel_status_open_report_btn.setEnabled(False)
        self.channel_status_open_report_btn.clicked.connect(
            self._open_channel_status_report
        )
        actions.addWidget(self.channel_status_run_btn)
        actions.addWidget(self.channel_status_open_output_btn)
        actions.addWidget(self.channel_status_open_report_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.channel_status_progress = QProgressBar()
        self.channel_status_progress.setRange(0, 100)
        self.channel_status_progress.setValue(0)
        layout.addWidget(self.channel_status_progress)
        self.channel_status_progress_message = QLabel("等待处理")
        self.channel_status_progress_message.setObjectName("pageSub")
        layout.addWidget(self.channel_status_progress_message)

        log_box = QGroupBox("channel_status 移动日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.channel_status_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.channel_status_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.channel_status_log_edit = QPlainTextEdit()
        self.channel_status_log_edit.setReadOnly(True)
        log_layout.addWidget(self.channel_status_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_rmu_annotation_position_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "调整麦加环网柜 NOP 和环网柜名称的位置。NOP 不按柜体整体居中，而是只匹配柜内 Y*/Q* 开关设备，"
            "并与对应开关保持完全水平中心对齐；环网柜名称识别按 RIGHT → BOTTOM → GLOBAL fallback，位置按外框四边中点放置；名称已有 Poke 时同步移动 Poke。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        option_box = QGroupBox("NOP / 环网柜名称位置设置")
        option_layout = QGridLayout(option_box)
        option_layout.setContentsMargins(14, 18, 14, 12)
        option_layout.setHorizontalSpacing(10)
        option_layout.setVerticalSpacing(9)
        option_layout.setColumnStretch(1, 1)
        option_layout.setColumnStretch(4, 1)

        option_layout.addWidget(QLabel("NOP 位置"), 0, 0)
        self.rmu_annotation_nop_position_combo = NoWheelComboBox()
        self.rmu_annotation_nop_position_combo.setMinimumWidth(220)
        for value, label in NOP_HORIZONTAL_POSITIONS.items():
            self.rmu_annotation_nop_position_combo.addItem(label, value)
        idx = self.rmu_annotation_nop_position_combo.findData("auto")
        if idx >= 0:
            self.rmu_annotation_nop_position_combo.setCurrentIndex(idx)
        option_layout.addWidget(self.rmu_annotation_nop_position_combo, 0, 1)
        option_layout.addWidget(QLabel("距边"), 0, 2)
        self.rmu_annotation_nop_margin_spin = QSpinBox()
        self.rmu_annotation_nop_margin_spin.setRange(0, 1000)
        self.rmu_annotation_nop_margin_spin.setValue(5)
        self.rmu_annotation_nop_margin_spin.setSuffix(" px")
        self.rmu_annotation_nop_margin_spin.setFixedWidth(120)
        option_layout.addWidget(self.rmu_annotation_nop_margin_spin, 0, 3)

        option_layout.addWidget(QLabel("环网柜名称位置"), 1, 0)
        self.rmu_annotation_name_position_combo = NoWheelComboBox()
        self.rmu_annotation_name_position_combo.setMinimumWidth(220)
        for value, label in RMU_NAME_POSITIONS.items():
            self.rmu_annotation_name_position_combo.addItem(label, value)
        idx = self.rmu_annotation_name_position_combo.findData("right")
        if idx >= 0:
            self.rmu_annotation_name_position_combo.setCurrentIndex(idx)
        option_layout.addWidget(self.rmu_annotation_name_position_combo, 1, 1)
        option_layout.addWidget(QLabel("距边"), 1, 2)
        self.rmu_annotation_name_margin_spin = QSpinBox()
        self.rmu_annotation_name_margin_spin.setRange(0, 1000)
        self.rmu_annotation_name_margin_spin.setValue(5)
        self.rmu_annotation_name_margin_spin.setSuffix(" px")
        self.rmu_annotation_name_margin_spin.setFixedWidth(120)
        option_layout.addWidget(self.rmu_annotation_name_margin_spin, 1, 3)
        layout.addWidget(option_box)

        note = QLabel(
            "NOP 对齐规则：只使用当前 RMU 内的 CBreakerDis，并要求设备名称能确定为 Y* 或 Q*。"
            "优先使用设备 p_NameString，缺失时复用现有可见 Y*/Q* 名称识别。NOP 与对应设备的中心 Y 完全一致，"
            "因此不会再按环网柜外框中心对齐。自动模式只保持 NOP 原来的左/右侧。"
            "环网柜名称只从 RMU 框外 Text 中按 RIGHT → BOTTOM → GLOBAL fallback 识别；柜内 Text 不参与，一柜一名称、一 Text 只分配一次；若名称 Text 已绑定 Poke，名称移动时 Poke 同步移动。"
        )
        note.setWordWrap(True)
        note.setObjectName("moduleDescription")
        layout.addWidget(note)

        actions = QHBoxLayout()
        self.rmu_annotation_run_btn = QPushButton("开始调整 NOP / 环网柜名称")
        self.rmu_annotation_run_btn.setObjectName("primary")
        self.rmu_annotation_run_btn.clicked.connect(self.start_rmu_annotation_reposition)
        self.rmu_annotation_open_output_btn = QPushButton("打开 G 输出目录")
        self.rmu_annotation_open_output_btn.setEnabled(False)
        self.rmu_annotation_open_output_btn.clicked.connect(self._open_rmu_annotation_output_dir)
        self.rmu_annotation_open_report_btn = QPushButton("打开位置报告")
        self.rmu_annotation_open_report_btn.setEnabled(False)
        self.rmu_annotation_open_report_btn.clicked.connect(self._open_rmu_annotation_report)
        actions.addWidget(self.rmu_annotation_run_btn)
        actions.addWidget(self.rmu_annotation_open_output_btn)
        actions.addWidget(self.rmu_annotation_open_report_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.rmu_annotation_progress = QProgressBar()
        self.rmu_annotation_progress.setRange(0, 100)
        self.rmu_annotation_progress.setValue(0)
        layout.addWidget(self.rmu_annotation_progress)
        self.rmu_annotation_progress_message = QLabel("等待处理")
        self.rmu_annotation_progress_message.setObjectName("pageSub")
        layout.addWidget(self.rmu_annotation_progress_message)

        log_box = QGroupBox("NOP / 环网柜名称位置调整日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.rmu_annotation_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.rmu_annotation_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.rmu_annotation_log_edit = QPlainTextEdit()
        self.rmu_annotation_log_edit.setReadOnly(True)
        log_layout.addWidget(self.rmu_annotation_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_feeder_avoidance_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "只移动压住环网柜名称或 NOP / N.O.P 文字的 FeedLine。"
            "同一 RMU 列中，相邻环网柜之间的馈线对齐到同一内侧轨道；"
            "跨越其它环网柜的长馈线依次往外排列。右侧向右、左侧向左镜像处理。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        option_box = QGroupBox("馈线避让参数")
        option_layout = QGridLayout(option_box)
        option_layout.setContentsMargins(14, 18, 14, 12)
        option_layout.setHorizontalSpacing(10)
        option_layout.setVerticalSpacing(9)

        option_layout.addWidget(QLabel("文字安全间距"), 0, 0)
        self.feeder_avoidance_clearance_spin = QSpinBox()
        self.feeder_avoidance_clearance_spin.setRange(0, 300)
        self.feeder_avoidance_clearance_spin.setValue(
            int(self.cfg.get("feeder_avoidance_text_clearance", DEFAULT_TEXT_CLEARANCE))
        )
        self.feeder_avoidance_clearance_spin.setSuffix(" G")
        self.feeder_avoidance_clearance_spin.setFixedWidth(120)
        option_layout.addWidget(self.feeder_avoidance_clearance_spin, 0, 1)

        option_layout.addWidget(QLabel("错落轨道间距"), 0, 2)
        self.feeder_avoidance_spacing_spin = QSpinBox()
        self.feeder_avoidance_spacing_spin.setRange(10, 300)
        self.feeder_avoidance_spacing_spin.setValue(
            int(self.cfg.get("feeder_avoidance_track_spacing", DEFAULT_FEEDER_SPACING))
        )
        self.feeder_avoidance_spacing_spin.setSuffix(" G")
        self.feeder_avoidance_spacing_spin.setFixedWidth(120)
        option_layout.addWidget(self.feeder_avoidance_spacing_spin, 0, 3)

        option_layout.addWidget(QLabel("同列判定范围"), 0, 4)
        self.feeder_avoidance_corridor_spin = QSpinBox()
        self.feeder_avoidance_corridor_spin.setRange(0, 1000)
        self.feeder_avoidance_corridor_spin.setValue(
            int(self.cfg.get("feeder_avoidance_corridor_tolerance", DEFAULT_CORRIDOR_TOLERANCE))
        )
        self.feeder_avoidance_corridor_spin.setSuffix(" G")
        self.feeder_avoidance_corridor_spin.setFixedWidth(130)
        option_layout.addWidget(self.feeder_avoidance_corridor_spin, 0, 5)

        option_layout.addWidget(QLabel("最大外移"), 1, 0)
        self.feeder_avoidance_max_shift_spin = QSpinBox()
        self.feeder_avoidance_max_shift_spin.setRange(50, 3000)
        self.feeder_avoidance_max_shift_spin.setValue(
            int(self.cfg.get("feeder_avoidance_max_shift", DEFAULT_MAX_RIGHT_SHIFT))
        )
        self.feeder_avoidance_max_shift_spin.setSuffix(" G")
        self.feeder_avoidance_max_shift_spin.setFixedWidth(120)
        option_layout.addWidget(self.feeder_avoidance_max_shift_spin, 1, 1)

        self.feeder_avoidance_right_check = QCheckBox("处理右侧馈线")
        self.feeder_avoidance_right_check.setChecked(
            bool(self.cfg.get("feeder_avoidance_process_right", True))
        )
        option_layout.addWidget(self.feeder_avoidance_right_check, 1, 2, 1, 2)

        self.feeder_avoidance_left_check = QCheckBox("处理左侧馈线")
        self.feeder_avoidance_left_check.setChecked(
            bool(self.cfg.get("feeder_avoidance_process_left", True))
        )
        option_layout.addWidget(self.feeder_avoidance_left_check, 1, 4, 1, 2)
        option_layout.setColumnStretch(6, 1)
        layout.addWidget(option_box)

        note = QLabel(
            "硬规则：环网柜名称和 NOP / N.O.P 原地不动；没有文字碰撞的 FeedLine 完全不处理。"
            "同一 RMU 列中，相邻 RMU 之间且 Y 范围不重叠的馈线复用同一条内侧轨道；"
            "跨越这些区间的馈线按重叠层级依次放到更外侧轨道。"
            "右侧轨道只向 +X 外扩，左侧轨道只向 -X 外扩。"
            "只修改 Workspace 安全副本中的 FeedLine.d 及其几何包围框，link / node_area / keyid 不变。"
        )
        note.setWordWrap(True)
        note.setObjectName("moduleDescription")
        layout.addWidget(note)

        actions = QHBoxLayout()
        self.feeder_avoidance_run_btn = QPushButton("开始馈线避让调整")
        self.feeder_avoidance_run_btn.setObjectName("primary")
        self.feeder_avoidance_run_btn.clicked.connect(self.start_feeder_avoidance)
        self.feeder_avoidance_open_output_btn = QPushButton("打开 G 输出目录")
        self.feeder_avoidance_open_output_btn.setEnabled(False)
        self.feeder_avoidance_open_output_btn.clicked.connect(self._open_feeder_avoidance_output_dir)
        self.feeder_avoidance_open_report_btn = QPushButton("打开避让报告")
        self.feeder_avoidance_open_report_btn.setEnabled(False)
        self.feeder_avoidance_open_report_btn.clicked.connect(self._open_feeder_avoidance_report)
        actions.addWidget(self.feeder_avoidance_run_btn)
        actions.addWidget(self.feeder_avoidance_open_output_btn)
        actions.addWidget(self.feeder_avoidance_open_report_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.feeder_avoidance_progress = QProgressBar()
        self.feeder_avoidance_progress.setRange(0, 100)
        self.feeder_avoidance_progress.setValue(0)
        layout.addWidget(self.feeder_avoidance_progress)
        self.feeder_avoidance_progress_message = QLabel("等待处理")
        self.feeder_avoidance_progress_message.setObjectName("pageSub")
        layout.addWidget(self.feeder_avoidance_progress_message)

        log_box = QGroupBox("馈线避让调整日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.feeder_avoidance_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.feeder_avoidance_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.feeder_avoidance_log_edit = QPlainTextEdit()
        self.feeder_avoidance_log_edit.setReadOnly(True)
        log_layout.addWidget(self.feeder_avoidance_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_rmu_feeder_topology_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "本模块只判断环网柜 RMU 的所属馈线。FeedLine、ConnectLine、Bus、BusDis 和其它网络对象只作为电气拓扑寻路介质，不判断 FeedLine 属于哪个 RMU，也不输出 FeedLine 业务归属。"
            "分析从每条主网馈线 CBreaker 出发，沿 link/node_area 和严格几何补链持续传播；只处理红色 NOP，非红色 NOP 全部忽略。"
            "只有某一条传播路径实际碰到红色 NOP 对应的 Y*/Q* 开关时，这一路才在该开关处停止；同一馈线的其它支路、同一 RMU 的其它非 NOP 端口继续传播。"
            "本模块只读分析，不修改 G 文件，也不连接、不查询、不写入 Oracle 数据库。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        rule_box = QGroupBox("NOP 拓扑分析规则")
        rule_layout = QVBoxLayout(rule_box)
        rules = (
            "① 分析目标：只判断 RMU 所属馈线；FeedLine / ConnectLine / Bus / BusDis 仅用于拓扑寻路，不作为 RMU 归属对象。",
            "② 主网馈线源：识别包含 CBreaker 的最内层 Bay 框，并读取附近无背景合法馈线标题（颜色不限）。",
            "③ 电气传播：从每个主网 CBreaker 出发，优先沿 link / node_area 传播；缺失连接时只允许端点≤3G、端点到线段≤2G的严格补链。没有碰到 NOP 就一直继续，线路分叉时每一条支路都继续。",
            "④ NOP 归属：只处理红色 NOP；非红色 NOP 全部忽略。红色 NOP 先归属最近 RMU，而且只能在该 RMU 框内找 Y*/Q* CBreakerDis。左右侧 NOP 优先按中心 Y 水平对齐，上下侧 NOP 按中心 X 对齐；同一对齐行/列有多个候选时再取离 NOP 最近者。",
            "⑤ NOP 断点：NOP 是端口级、支路级断点。只有传播路径真正走到 NOP 对应 Y*/Q* 开关时，该一路在此停止；同一 feeder 的其它支路以及同柜其它非 NOP 端口继续传播，不做整条 feeder 的全局删除。",
            "⑥ RMU归属：普通 RMU 根据其 Y*/Q* 端口从哪些主网 feeder 可达来判断；NOP 柜忽略 NOP 端口作为归属端口，使用同柜其它非 NOP Y*/Q* 的唯一一致 feeder 作为 RMU 所属馈线，NOP 另一侧 feeder 记录为在此截止。",
            "⑦ 报告：只输出主网传播入口、NOP所属RMU/开关、RMU所属馈线和RMU端口拓扑证据，不输出 FeedLine 业务归属。",
            "⑧ 安全原则：多馈线同时可达标记 CONFLICT，无可靠可达证据标记 UNRESOLVED，不按全图最近距离猜测。",
        )
        for line in rules:
            label = QLabel(line)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        layout.addWidget(rule_box)

        actions = QHBoxLayout()
        self.rmu_feeder_topology_run_btn = QPushButton("开始环网柜馈线拓扑分析")
        self.rmu_feeder_topology_run_btn.setObjectName("primary")
        self.rmu_feeder_topology_run_btn.clicked.connect(self.start_rmu_feeder_topology_analysis)
        self.rmu_feeder_topology_open_report_btn = QPushButton("打开拓扑分析报告")
        self.rmu_feeder_topology_open_report_btn.setEnabled(False)
        self.rmu_feeder_topology_open_report_btn.clicked.connect(self._open_rmu_feeder_topology_report)
        self.rmu_feeder_topology_open_dir_btn = QPushButton("打开分析结果目录")
        self.rmu_feeder_topology_open_dir_btn.setEnabled(False)
        self.rmu_feeder_topology_open_dir_btn.clicked.connect(self._open_rmu_feeder_topology_report_dir)
        actions.addWidget(self.rmu_feeder_topology_run_btn)
        actions.addWidget(self.rmu_feeder_topology_open_report_btn)
        actions.addWidget(self.rmu_feeder_topology_open_dir_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.rmu_feeder_topology_progress = QProgressBar()
        self.rmu_feeder_topology_progress.setRange(0, 100)
        self.rmu_feeder_topology_progress.setValue(0)
        layout.addWidget(self.rmu_feeder_topology_progress)
        self.rmu_feeder_topology_progress_message = QLabel("等待分析")
        self.rmu_feeder_topology_progress_message.setObjectName("pageSub")
        layout.addWidget(self.rmu_feeder_topology_progress_message)

        log_box = QGroupBox("环网柜馈线拓扑分析日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.rmu_feeder_topology_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.rmu_feeder_topology_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.rmu_feeder_topology_log_edit = QPlainTextEdit()
        self.rmu_feeder_topology_log_edit.setReadOnly(True)
        log_layout.addWidget(self.rmu_feeder_topology_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_feedline_feeder_topology_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "本模块独立分析 FeedLine 的所属馈线，不修改已经验证通过的‘环网柜馈线拓扑分析’逻辑。"
            "从每条主网馈线 CBreaker 出发，沿 link/node_area、连接线、FeedLine、配网母线及严格几何补链持续传播；只处理红色 NOP，非红色 NOP 全部忽略。"
            "只有当前传播路径真正碰到红色 NOP 对应的 Y*/Q* 开关时，这一路才停止，其它支路继续。"
            "本模块只读分析，不修改 G 文件，也不连接、不查询、不写入 Oracle 数据库。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        rule_box = QGroupBox("馈线段拓扑分析规则")
        rule_layout = QVBoxLayout(rule_box)
        rules = (
            "① 分析目标：输出每条 FeedLine 的所属主网馈线；RMU、ConnectLine、Bus、BusDis 和其它网络对象只作为拓扑节点/路径证据。",
            "② 主网馈线源：与环网柜拓扑分析保持一致，识别包含 CBreaker 的最内层 Bay 框及附近无背景合法馈线标题，标题颜色不限。",
            "③ 电气传播：优先使用 link / node_area；XML 缺链时只允许端点≤3G、端点到线段≤2G的严格补链。线路分叉后每条支路独立继续传播。",
            "④ NOP 断点：只处理红色 NOP。NOP 只能在所属 RMU 框内匹配 Y*/Q* 开关；左右侧优先按中心 Y 水平对齐，上下侧按中心 X 对齐。同一行/列多个候选时再按距离消歧。",
            "⑤ 支路停止：只有传播路径真正走到红色 NOP 对应开关时，该一路停止；同一 feeder 的其它支路继续，不做整条 feeder 全局删除。",
            "⑥ FeedLine归属：只有一个 feeder 可达 → CONFIRMED；多个 feeder 可达 → CONFLICT；没有 feeder 可达 → UNRESOLVED。绝不按全图最近馈线猜测。",
            "⑦ 输出：HTML 汇总主网馈线传播入口、红色 NOP 边界和全部 FeedLine 所属馈线；同时输出 FeedLine CSV 与 NOP 边界 CSV。",
        )
        for line in rules:
            label = QLabel(line)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        layout.addWidget(rule_box)

        actions = QHBoxLayout()
        self.feedline_feeder_topology_run_btn = QPushButton("开始馈线段所属馈线分析")
        self.feedline_feeder_topology_run_btn.setObjectName("primary")
        self.feedline_feeder_topology_run_btn.clicked.connect(self.start_feedline_feeder_topology_analysis)
        self.feedline_feeder_topology_open_report_btn = QPushButton("打开馈线段分析报告")
        self.feedline_feeder_topology_open_report_btn.setEnabled(False)
        self.feedline_feeder_topology_open_report_btn.clicked.connect(self._open_feedline_feeder_topology_report)
        self.feedline_feeder_topology_open_dir_btn = QPushButton("打开分析结果目录")
        self.feedline_feeder_topology_open_dir_btn.setEnabled(False)
        self.feedline_feeder_topology_open_dir_btn.clicked.connect(self._open_feedline_feeder_topology_report_dir)
        actions.addWidget(self.feedline_feeder_topology_run_btn)
        actions.addWidget(self.feedline_feeder_topology_open_report_btn)
        actions.addWidget(self.feedline_feeder_topology_open_dir_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.feedline_feeder_topology_progress = QProgressBar()
        self.feedline_feeder_topology_progress.setRange(0, 100)
        self.feedline_feeder_topology_progress.setValue(0)
        layout.addWidget(self.feedline_feeder_topology_progress)
        self.feedline_feeder_topology_progress_message = QLabel("等待分析")
        self.feedline_feeder_topology_progress_message.setObjectName("pageSub")
        layout.addWidget(self.feedline_feeder_topology_progress_message)

        log_box = QGroupBox("馈线段所属馈线分析日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.feedline_feeder_topology_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.feedline_feeder_topology_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.feedline_feeder_topology_log_edit = QPlainTextEdit()
        self.feedline_feeder_topology_log_edit.setReadOnly(True)
        log_layout.addWidget(self.feedline_feeder_topology_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_main_station_background_label_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "专门修正主网入口附近的带背景跳转标签。程序先识别真实主网 Bay CBreaker 和馈线名，"
            "再在其 300G 范围内寻找具有可见背景、并与“(目标环网柜名称)”成组显示的标签。"
            "括号内容保持不变，只修正括号外主网文字；修正后自动调整背景对象大小，并把两行文字上下居中对齐；原始 G 文件不覆盖。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        rule_box = QGroupBox("背景标签修正规则")
        rule_layout = QVBoxLayout(rule_box)
        rules = (
            "① 候选必须有可见背景色：优先识别填充的 Poke / Rect，也兼容 Text 自带背景属性；不依赖固定 RGB。",
            "② 同一背景内必须存在一段馈线样式文字和一段形如 (33359) / （33359） 的目标名称；两段文字必须紧邻。",
            "③ 只在已确认主网 CBreaker 300G 范围内处理；300G 内有多个主网候选时标记 AMBIGUOUS，不自动修改。",
            "④ 修正时只替换括号外文字，例如 MNA4-12 + (33359) → MNA4-AH312 + (33359)；括号目标绝不修改。",
            "⑤ 此类背景跳转标签不是馈线标题：整图馈线拓扑分析会在主网/沿线馈线候选识别前强制排除这些 Text。",
            "⑥ 背景排版：按修正后的文字宽度自动扩展背景 Poke / Rect / 其它可见填充对象；主网名称在上、(目标RMU)在下，两行水平居中且整体垂直居中。",
            "⑦ 安全原则：原始 G 永不覆盖；只在 Workspace/g_output 生成 *.main-station-label-fixed.sln.pic.g 安全副本，并输出 HTML/CSV 明细。",
        )
        for line in rules:
            label = QLabel(line)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        layout.addWidget(rule_box)

        actions = QHBoxLayout()
        self.main_station_background_label_run_btn = QPushButton("开始主网入口背景标签修正")
        self.main_station_background_label_run_btn.setObjectName("primary")
        self.main_station_background_label_run_btn.clicked.connect(self.start_main_station_background_label_repair)
        self.main_station_background_label_open_report_btn = QPushButton("打开修正报告")
        self.main_station_background_label_open_report_btn.setEnabled(False)
        self.main_station_background_label_open_report_btn.clicked.connect(self._open_main_station_background_label_report)
        self.main_station_background_label_open_dir_btn = QPushButton("打开输出目录")
        self.main_station_background_label_open_dir_btn.setEnabled(False)
        self.main_station_background_label_open_dir_btn.clicked.connect(self._open_main_station_background_label_output_dir)
        actions.addWidget(self.main_station_background_label_run_btn)
        actions.addWidget(self.main_station_background_label_open_report_btn)
        actions.addWidget(self.main_station_background_label_open_dir_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.main_station_background_label_progress = QProgressBar()
        self.main_station_background_label_progress.setRange(0, 100)
        self.main_station_background_label_progress.setValue(0)
        layout.addWidget(self.main_station_background_label_progress)
        self.main_station_background_label_progress_message = QLabel("等待处理")
        self.main_station_background_label_progress_message.setObjectName("pageSub")
        layout.addWidget(self.main_station_background_label_progress_message)

        log_box = QGroupBox("主网入口背景标签修正日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.main_station_background_label_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.main_station_background_label_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.main_station_background_label_log_edit = QPlainTextEdit()
        self.main_station_background_label_log_edit.setReadOnly(True)
        log_layout.addWidget(self.main_station_background_label_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_whole_graph_topology_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "本模块是全新的整张 G 图拓扑分析，只处理一个 G 文件；不修改既有‘环网柜馈线拓扑分析’和‘馈线段所属馈线分析’逻辑。"
            "完全只看图形：不连接 Oracle、不校验 13500/13501/13502/13503、不做模型关联。发现唯一且可验证的微小拓扑断点时，"
            "会保留原始 G 不变，并额外生成 topology-fixed 修复副本，同时在 HTML 显示修复前/修复后两张拓扑图。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        rule_box = QGroupBox("整图拓扑分析规则")
        rule_layout = QVBoxLayout(rule_box)
        rules = (
            "① 分析范围：一次只分析一个 G 文件；输出整张图中 FeedLine、ConnectLine、Bus/BusDis、普通柱上开关、Pole、变压器及其它有 link/node_area 的电气对象所属馈线。",
            "② 馈线源唯一性：一个主站出线有且只能有一个馈线名字。主网 Bay CBreaker + 馈线标题是权威源；若现场没有主站设备、只在线路末端写 TRUB-BH21 这类主站/馈线名称，则只允许在无主网设备源的末端拓扑区域选中唯一一个文字源。同名文字重复、同一源端出现多个不同名字都只报错/排除，绝不同时参与传播。带背景跳转标签仍强制排除。",
            "③ 电气连接：优先使用 link / node_area；基础分析仍按端点≤3G、端点到线段≤2G严格补链。若出现无馈线孤立区，会额外检查3G~4.5G之间的线端点微小间隙；只有双方唯一近邻且模拟后错误减少、不新增多馈线时才允许自动修复。",
            "④ RMU NOP：能按现有逻辑归属到 RMU 的红色 NOP，继续按该 RMU 内唯一 Y*/Q* 开关作为端口级断点；既有环网柜拓扑模块代码不改。",
            "⑤ 柱上 NOP：所有未归属 RMU 的红色 NOP 都按柱上开关 NOP 处理，匹配最近的外部 CBreakerDis/Disconnector；该开关是硬边界。",
            "⑥ 传播规则：只从通过唯一性校验的馈线源沿真实拓扑传播；遇到 NOP 开关停止当前路径，其它分支继续。被排除的重复主站名字、中段文字、背景跳转文字都不能成为传播源。NOP 开关本身暂不判断所属馈线。",
            "⑦ NOP 两侧：分别读取 NOP 开关各邻接侧在断点外的馈线结果。每一侧必须最终有且只有一个主站/馈线名字；0 个=NO_SOURCE_ERROR，多个=MULTI_SOURCE_ERROR，只有唯一一个才算确认。",
            "⑧ 非NOP设备硬规则：每个设备必须且只能属于一条馈线。唯一馈线可达 → CONFIRMED；没有馈线 → NO_FEEDER_ERROR；多个馈线 → MULTI_FEEDER_ERROR。后两种都作为拓扑错误，优先检查NOP设置或连接。",
            "⑨ RMU所属馈线：单独汇总同柜 Y*/Q* 开关；NOP端口只作为边界，不参与RMU归属。所有非NOP端口必须各自唯一且最终一致到同一馈线，否则RMU报错；不使用多数投票。HTML报告新增RMU所属馈线独立表格。",
            "⑩ 安全原则：原始 G 永不覆盖；自动修复只写新的 *.topology-fixed.sln.pic.g 安全副本，并再次完整复核。HTML同时输出修复前/修复后拓扑图和断点修复明细；不连接、不查询、不写入 Oracle。",
        )
        for line in rules:
            label = QLabel(line)
            label.setWordWrap(True)
            rule_layout.addWidget(label)
        layout.addWidget(rule_box)

        actions = QHBoxLayout()
        self.whole_graph_topology_run_btn = QPushButton("开始整图馈线拓扑分析 / 自动修复")
        self.whole_graph_topology_run_btn.setObjectName("primary")
        self.whole_graph_topology_run_btn.clicked.connect(self.start_whole_graph_topology_analysis)
        self.whole_graph_topology_open_report_btn = QPushButton("打开整图拓扑报告")
        self.whole_graph_topology_open_report_btn.setEnabled(False)
        self.whole_graph_topology_open_report_btn.clicked.connect(self._open_whole_graph_topology_report)
        self.whole_graph_topology_open_dir_btn = QPushButton("打开分析结果目录")
        self.whole_graph_topology_open_dir_btn.setEnabled(False)
        self.whole_graph_topology_open_dir_btn.clicked.connect(self._open_whole_graph_topology_report_dir)
        actions.addWidget(self.whole_graph_topology_run_btn)
        actions.addWidget(self.whole_graph_topology_open_report_btn)
        actions.addWidget(self.whole_graph_topology_open_dir_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.whole_graph_topology_progress = QProgressBar()
        self.whole_graph_topology_progress.setRange(0, 100)
        self.whole_graph_topology_progress.setValue(0)
        layout.addWidget(self.whole_graph_topology_progress)
        self.whole_graph_topology_progress_message = QLabel("等待分析")
        self.whole_graph_topology_progress_message.setObjectName("pageSub")
        layout.addWidget(self.whole_graph_topology_progress_message)

        log_box = QGroupBox("整图馈线拓扑分析日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(
                self.whole_graph_topology_log_edit.toPlainText()
            )
        )
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.whole_graph_topology_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.whole_graph_topology_log_edit = QPlainTextEdit()
        self.whole_graph_topology_log_edit.setReadOnly(True)
        log_layout.addWidget(self.whole_graph_topology_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_graphics_pipeline_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        description = QLabel(
            "一次对同一批 G 文件连续执行多个图形处理步骤。每个文件只有全部已选步骤成功后才写入最终 g_output；"
            "任何一步失败都不会发布该文件的半成品，并继续处理下一文件。"
        )
        description.setWordWrap(True)
        description.setObjectName("pageSub")
        layout.addWidget(description)

        steps_box = QGroupBox("组合处理步骤")
        steps_layout = QVBoxLayout(steps_box)
        self.pipeline_enable_cleanup = QCheckBox("① 环网柜网络图元清理（删除 G / L / N）")
        self.pipeline_enable_channel = QCheckBox("② 环网柜 channel_status 移动")
        self.pipeline_enable_poke = QCheckBox("③ Poke 跳转处理")
        for cb in (self.pipeline_enable_cleanup, self.pipeline_enable_channel, self.pipeline_enable_poke):
            cb.setChecked(True)
            steps_layout.addWidget(cb)

        choice_actions = QHBoxLayout()
        select_all = QPushButton("全选")
        clear_all = QPushButton("全部取消")
        select_all.clicked.connect(lambda: [cb.setChecked(True) for cb in (self.pipeline_enable_cleanup, self.pipeline_enable_channel, self.pipeline_enable_poke)])
        clear_all.clicked.connect(lambda: [cb.setChecked(False) for cb in (self.pipeline_enable_cleanup, self.pipeline_enable_channel, self.pipeline_enable_poke)])
        choice_actions.addWidget(select_all)
        choice_actions.addWidget(clear_all)
        choice_actions.addStretch(1)
        steps_layout.addLayout(choice_actions)
        layout.addWidget(steps_box)

        channel_box = QGroupBox("channel_status 移动参数")
        channel_layout = QHBoxLayout(channel_box)
        channel_layout.setContentsMargins(14, 18, 14, 12)
        channel_layout.addWidget(QLabel("框内位置"))
        self.pipeline_channel_position_combo = NoWheelComboBox()
        self.pipeline_channel_position_combo.setMinimumWidth(150)
        for value, label in CHANNEL_STATUS_POSITIONS.items():
            self.pipeline_channel_position_combo.addItem(label, value)
        idx = self.pipeline_channel_position_combo.findData("bottom_left")
        if idx >= 0:
            self.pipeline_channel_position_combo.setCurrentIndex(idx)
        channel_layout.addWidget(self.pipeline_channel_position_combo)
        channel_layout.addWidget(QLabel("距边"))
        self.pipeline_channel_margin_spin = QSpinBox()
        self.pipeline_channel_margin_spin.setRange(0, 1000)
        self.pipeline_channel_margin_spin.setValue(5)
        self.pipeline_channel_margin_spin.setSuffix(" px")
        self.pipeline_channel_margin_spin.setFixedWidth(140)
        channel_layout.addWidget(self.pipeline_channel_margin_spin)
        channel_layout.addStretch(1)
        layout.addWidget(channel_box)

        poke_box = QGroupBox("Poke 参数")
        poke_layout = QVBoxLayout(poke_box)
        self.pipeline_poke_main_feeder = QCheckBox("主网馈线标题 Poke")
        self.pipeline_poke_smart_rmu = QCheckBox("SMART / SMR 智能 RMU Poke")
        self.pipeline_poke_main_feeder.setChecked(True)
        self.pipeline_poke_smart_rmu.setChecked(True)
        poke_layout.addWidget(self.pipeline_poke_main_feeder)
        poke_layout.addWidget(self.pipeline_poke_smart_rmu)

        poke_choice_actions = QHBoxLayout()
        self.pipeline_poke_select_all_btn = QPushButton("全选")
        self.pipeline_poke_clear_all_btn = QPushButton("全部取消")
        self.pipeline_poke_select_all_btn.clicked.connect(
            lambda: [cb.setChecked(True) for cb in (self.pipeline_poke_main_feeder, self.pipeline_poke_smart_rmu)]
        )
        self.pipeline_poke_clear_all_btn.clicked.connect(
            lambda: [cb.setChecked(False) for cb in (self.pipeline_poke_main_feeder, self.pipeline_poke_smart_rmu)]
        )
        poke_choice_actions.addWidget(self.pipeline_poke_select_all_btn)
        poke_choice_actions.addWidget(self.pipeline_poke_clear_all_btn)
        poke_choice_actions.addStretch(1)
        poke_layout.addLayout(poke_choice_actions)
        layout.addWidget(poke_box)

        actions = QHBoxLayout()
        self.graphics_pipeline_run_btn = QPushButton("开始组合处理")
        self.graphics_pipeline_run_btn.setObjectName("primary")
        self.graphics_pipeline_run_btn.clicked.connect(self.start_graphics_pipeline)
        self.graphics_pipeline_open_output_btn = QPushButton("打开 G 输出目录")
        self.graphics_pipeline_open_output_btn.setEnabled(False)
        self.graphics_pipeline_open_output_btn.clicked.connect(self._open_graphics_pipeline_output_dir)
        self.graphics_pipeline_open_report_btn = QPushButton("打开组合处理报告")
        self.graphics_pipeline_open_report_btn.setEnabled(False)
        self.graphics_pipeline_open_report_btn.clicked.connect(self._open_graphics_pipeline_report)
        actions.addWidget(self.graphics_pipeline_run_btn)
        actions.addWidget(self.graphics_pipeline_open_output_btn)
        actions.addWidget(self.graphics_pipeline_open_report_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.graphics_pipeline_progress = QProgressBar()
        self.graphics_pipeline_progress.setRange(0, 100)
        self.graphics_pipeline_progress.setValue(0)
        layout.addWidget(self.graphics_pipeline_progress)
        self.graphics_pipeline_progress_message = QLabel("等待处理")
        self.graphics_pipeline_progress_message.setObjectName("pageSub")
        layout.addWidget(self.graphics_pipeline_progress_message)

        log_box = QGroupBox("组合处理运行日志")
        log_layout = QVBoxLayout(log_box)
        log_actions = QHBoxLayout()
        copy_btn = QPushButton("复制日志")
        clear_btn = QPushButton("清空日志")
        copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.graphics_pipeline_log_edit.toPlainText()))
        clear_btn.clicked.connect(lambda: self.graphics_pipeline_log_edit.clear())
        log_actions.addWidget(copy_btn)
        log_actions.addWidget(clear_btn)
        log_actions.addStretch(1)
        log_layout.addLayout(log_actions)
        self.graphics_pipeline_log_edit = QPlainTextEdit()
        self.graphics_pipeline_log_edit.setReadOnly(True)
        log_layout.addWidget(self.graphics_pipeline_log_edit, 1)
        layout.addWidget(log_box, 1)
        return panel

    def _build_poke_source_box(self):
        """Build a full-width source selector for the Poke page.

        The controls mirror the Model Workspace source state instead of
        creating a separate source model. This keeps SSH read-only semantics,
        selection state and snapshots consistent across both pages.
        """
        box = QGroupBox("文件来源（图形工作区）")
        root = QVBoxLayout(box)
        root.setContentsMargins(14, 18, 14, 12)
        root.setSpacing(8)

        source_row = QGridLayout()
        source_row.setColumnStretch(1, 1)
        source_row.addWidget(QLabel("文件来源"), 0, 0)
        self.poke_input_source_combo = NoWheelComboBox()
        self.poke_input_source_combo.addItem("本地文件 / 目录", "LOCAL")
        self.poke_input_source_combo.addItem("SSH 文件服务器（只读）", "SSH")
        self.poke_input_source_combo.currentIndexChanged.connect(
            self._on_poke_input_source_changed
        )
        source_row.addWidget(self.poke_input_source_combo, 0, 1, 1, 3)
        root.addLayout(source_row)

        self.poke_input_source_stack = CurrentPageStackedWidget()
        # LOCAL is only one input row while SSH contains a 240px+ file table.
        # Follow the visible page height so LOCAL does not reserve SSH space.
        self.poke_input_source_stack.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Maximum
        )

        local_page = QWidget()
        local_layout = QGridLayout(local_page)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setColumnStretch(1, 1)
        local_layout.addWidget(QLabel("G 文件 / 目录"), 0, 0)
        self.poke_input_edit = QLineEdit()
        self.poke_input_edit.setPlaceholderText("请选择一个 G 文件，或包含 G 文件的目录")
        self.poke_input_edit.editingFinished.connect(
            self._sync_workspace_source_from_poke
        )
        local_layout.addWidget(self.poke_input_edit, 0, 1)
        poke_file_btn = QPushButton("选择文件")
        poke_folder_btn = QPushButton("选择目录")
        poke_file_btn.clicked.connect(self._poke_browse_file)
        poke_folder_btn.clicked.connect(self._poke_browse_folder)
        local_layout.addWidget(poke_file_btn, 0, 2)
        local_layout.addWidget(poke_folder_btn, 0, 3)
        self.poke_input_source_stack.addWidget(local_page)

        remote_page = QWidget()
        remote_layout = QVBoxLayout(remote_page)
        remote_layout.setContentsMargins(0, 0, 0, 0)
        remote_layout.setSpacing(8)
        ssh_grid = QGridLayout()
        ssh_grid.setColumnStretch(1, 1)
        self.poke_ssh_edits = {}
        ssh_cfg = dict(self.cfg.get("ssh", {}) or {})
        ssh_fields = [
            ("host", "IP / 主机", ssh_cfg.get("host", "172.16.21.27")),
            ("port", "端口", ssh_cfg.get("port", 22)),
            ("username", "用户名", ssh_cfg.get("username", "up8000")),
            ("password", "密码", ssh_cfg.get("password", "up8000")),
            ("remote_directory", "远程目录", ssh_cfg.get("remote_directory", "/home/up8000/data/graph/display/sln")),
        ]
        for row_index, (key, label, value) in enumerate(ssh_fields):
            ssh_grid.addWidget(QLabel(label), row_index, 0)
            edit = QLineEdit(str(value))
            if key == "password":
                edit.setEchoMode(QLineEdit.Password)
            self.poke_ssh_edits[key] = edit
            ssh_grid.addWidget(edit, row_index, 1, 1, 3)

        ssh_buttons = QHBoxLayout()
        poke_test_btn = QPushButton("测试 SSH 连接")
        poke_save_btn = QPushButton("保存 SSH 配置")
        self.poke_refresh_ssh_btn = QPushButton("刷新 G 文件列表")
        poke_download_btn = QPushButton("下载所选 G 文件")
        poke_test_btn.clicked.connect(self._poke_test_ssh_connection)
        poke_save_btn.clicked.connect(self._poke_save_ssh_settings)
        self.poke_refresh_ssh_btn.clicked.connect(self._poke_refresh_remote_g_files)
        poke_download_btn.clicked.connect(self._poke_download_selected_remote_g_files)
        ssh_buttons.addWidget(poke_test_btn)
        ssh_buttons.addWidget(poke_save_btn)
        ssh_buttons.addWidget(self.poke_refresh_ssh_btn)
        ssh_buttons.addWidget(poke_download_btn)
        ssh_buttons.addStretch()
        ssh_grid.addLayout(ssh_buttons, len(ssh_fields), 1, 1, 3)

        self.poke_ssh_connection_status = QLabel("尚未测试 SSH/SFTP 连接。")
        self.poke_ssh_connection_status.setWordWrap(True)
        self.poke_ssh_connection_status.setStyleSheet(
            "background:#F5F7F8; color:#53636C; "
            "border:1px solid #D7E0E4; border-radius:6px; padding:7px 10px;"
        )
        ssh_grid.addWidget(
            self.poke_ssh_connection_status, len(ssh_fields) + 1, 1, 1, 3
        )
        remote_layout.addLayout(ssh_grid)

        readonly_notice = QLabel(
            "SSH 服务器只读：本工具仅允许列目录、读取属性和下载 G 文件；"
            "禁止上传、覆盖、重命名、删除或修改服务器上的任何文件。"
        )
        readonly_notice.setWordWrap(True)
        readonly_notice.setStyleSheet(
            "background:#E8F7F1; color:#006B52; "
            "border:1px solid #A9DCC8; border-radius:7px; "
            "padding:8px 10px; font-weight:600;"
        )
        remote_layout.addWidget(readonly_notice)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索 G 文件"))
        self.poke_remote_search_edit = QLineEdit()
        self.poke_remote_search_edit.setPlaceholderText("例如：ABH-06、SAMR、JED-NTH")
        self.poke_remote_search_edit.textChanged.connect(
            self._apply_poke_remote_file_filter
        )
        search_row.addWidget(self.poke_remote_search_edit, 1)
        self.poke_remote_count_label = QLabel("尚未加载远程文件")
        search_row.addWidget(self.poke_remote_count_label)
        remote_layout.addLayout(search_row)

        remote_actions = QHBoxLayout()
        select_visible_btn = QPushButton("全选当前结果")
        clear_btn = QPushButton("清空选择和搜索")
        select_visible_btn.clicked.connect(
            lambda: self._poke_set_visible_remote_selection(True)
        )
        clear_btn.clicked.connect(self._poke_clear_remote_selection)
        remote_actions.addWidget(select_visible_btn)
        remote_actions.addWidget(clear_btn)
        remote_actions.addStretch()
        remote_layout.addLayout(remote_actions)

        self.poke_remote_file_table = QTableWidget()
        self.poke_remote_file_table.setColumnCount(4)
        self.poke_remote_file_table.setHorizontalHeaderLabels(
            ["选择", "文件名", "大小", "服务器修改时间"]
        )
        self.poke_remote_file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.poke_remote_file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.poke_remote_file_table.verticalHeader().setDefaultSectionSize(30)
        header = self.poke_remote_file_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.poke_remote_file_table.itemChanged.connect(
            self._on_poke_remote_file_item_changed
        )
        self.poke_remote_file_table.setMinimumHeight(240)
        remote_layout.addWidget(self.poke_remote_file_table)
        self.poke_input_source_stack.addWidget(remote_page)
        root.addWidget(self.poke_input_source_stack)
        return box

    def _on_poke_input_source_changed(self, *_args):
        if not hasattr(self, "poke_input_source_combo"):
            return
        source = str(self.poke_input_source_combo.currentData() or "LOCAL").upper()
        self.poke_input_source_stack.setCurrentIndex(1 if source == "SSH" else 0)
        self.poke_input_source_stack.updateGeometry()
        self._sync_workspace_source_from_poke()

    def _sync_workspace_source_from_poke(self):
        """Push Poke-page source controls into the shared workspace source state."""
        if not hasattr(self, "poke_input_source_combo"):
            return

        # Copy values first so the workspace source-change handler persists the
        # same SSH configuration the user is currently looking at.
        if hasattr(self, "poke_input_edit") and hasattr(self, "input_edit"):
            self.input_edit.setText(self.poke_input_edit.text().strip())
        if hasattr(self, "poke_ssh_edits") and hasattr(self, "ssh_edits"):
            for key, edit in self.poke_ssh_edits.items():
                if key in self.ssh_edits:
                    self.ssh_edits[key].setText(edit.text())

        source = str(self.poke_input_source_combo.currentData() or "LOCAL").upper()
        if hasattr(self, "input_source_combo"):
            index = self.input_source_combo.findData(source)
            if index >= 0 and self.input_source_combo.currentIndex() != index:
                self.input_source_combo.setCurrentIndex(index)

        if source == "LOCAL" and hasattr(self, "_save_input_path_from_edit"):
            self._save_input_path_from_edit()

    def _sync_poke_source_from_workspace(self, rebuild_remote=False):
        if not hasattr(self, "poke_input_source_combo"):
            return
        source = self._current_input_source()
        index = self.poke_input_source_combo.findData(source)
        self.poke_input_source_combo.blockSignals(True)
        try:
            if index >= 0:
                self.poke_input_source_combo.setCurrentIndex(index)
        finally:
            self.poke_input_source_combo.blockSignals(False)
        self.poke_input_source_stack.setCurrentIndex(1 if source == "SSH" else 0)
        self.poke_input_source_stack.updateGeometry()

        if hasattr(self, "poke_input_edit"):
            self.poke_input_edit.setText(self.input_edit.text())
        if hasattr(self, "poke_ssh_edits"):
            for key, edit in self.poke_ssh_edits.items():
                if key in self.ssh_edits:
                    edit.setText(self.ssh_edits[key].text())

        if hasattr(self, "poke_ssh_connection_status") and hasattr(self, "ssh_connection_status"):
            self.poke_ssh_connection_status.setText(self.ssh_connection_status.text())
            self.poke_ssh_connection_status.setStyleSheet(self.ssh_connection_status.styleSheet())

        if rebuild_remote and hasattr(self, "poke_remote_file_table"):
            self._rebuild_poke_remote_file_table()
            self._apply_poke_remote_file_filter(
                self.poke_remote_search_edit.text()
                if hasattr(self, "poke_remote_search_edit") else ""
            )
        else:
            self._update_poke_remote_count_label()

    def _poke_browse_file(self):
        self.browse_file()
        self._sync_poke_source_from_workspace()

    def _poke_browse_folder(self):
        self.browse_folder()
        self._sync_poke_source_from_workspace()

    def _poke_test_ssh_connection(self):
        self._sync_workspace_source_from_poke()
        self.test_ssh_connection()
        self._sync_poke_source_from_workspace()

    def _poke_save_ssh_settings(self):
        self._sync_workspace_source_from_poke()
        self.save_ssh_settings()
        self._sync_poke_source_from_workspace()

    def _poke_refresh_remote_g_files(self):
        self._sync_workspace_source_from_poke()
        self.refresh_remote_g_files()

    def _poke_download_selected_remote_g_files(self):
        self._sync_workspace_source_from_poke()
        self.download_selected_remote_g_files()

    def _rebuild_poke_remote_file_table(self):
        if not hasattr(self, "poke_remote_file_table"):
            return
        table = self.poke_remote_file_table
        header = table.horizontalHeader()
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        self._poke_remote_table_populating = True
        try:
            for column in range(table.columnCount()):
                header.setSectionResizeMode(column, QHeaderView.Interactive)
            table.clearContents()
            table.setRowCount(len(self.remote_file_rows))
            self._poke_remote_row_by_name = {}
            for row_index, remote_file in enumerate(self.remote_file_rows):
                self._poke_remote_row_by_name[remote_file.name] = row_index
                check = QTableWidgetItem()
                check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                check.setCheckState(
                    Qt.Checked if remote_file.name in self.remote_selected_names else Qt.Unchecked
                )
                check.setData(Qt.UserRole, remote_file.name)
                table.setItem(row_index, 0, check)
                for column, value in enumerate(
                    [remote_file.name, self._format_file_size(remote_file.size), remote_file.mtime_text],
                    start=1,
                ):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    table.setItem(row_index, column, item)
            table.resizeColumnsToContents()
            header.setSectionResizeMode(1, QHeaderView.Stretch)
        finally:
            self._poke_remote_table_populating = False
            table.setUpdatesEnabled(True)
            table.blockSignals(False)
        self._poke_remote_visible_count = len(self.remote_file_rows)
        self._poke_remote_table_dirty = False
        self._update_poke_remote_count_label()

    def _mark_poke_remote_table_dirty(self):
        self._poke_remote_table_dirty = True
        if (
            hasattr(self, "pages")
            and self.pages.currentIndex() == 3
            and hasattr(self, "poke_remote_file_table")
        ):
            self._rebuild_poke_remote_file_table()
            self._apply_poke_remote_file_filter(
                self.poke_remote_search_edit.text()
                if hasattr(self, "poke_remote_search_edit") else ""
            )

    def _apply_poke_remote_file_filter(self, text=""):
        if not hasattr(self, "poke_remote_file_table"):
            return
        query = str(text or "").strip().lower()
        table = self.poke_remote_file_table
        visible = 0
        table.setUpdatesEnabled(False)
        try:
            for row_index, remote_file in enumerate(self.remote_file_rows):
                matched = not query or query in remote_file.name.lower()
                table.setRowHidden(row_index, not matched)
                if matched:
                    visible += 1
        finally:
            table.setUpdatesEnabled(True)
        self._poke_remote_visible_count = visible
        self._update_poke_remote_count_label()

    def _update_poke_remote_count_label(self):
        if not hasattr(self, "poke_remote_count_label"):
            return
        visible = getattr(self, "_poke_remote_visible_count", len(self.remote_file_rows))
        self.poke_remote_count_label.setText(
            (f"Total {len(self.remote_file_rows)} | Visible {visible} | Selected {len(self.remote_selected_names)}")
            if self.language == "en_US" else
            (f"总数 {len(self.remote_file_rows)} | 当前显示 {visible} | 已选择 {len(self.remote_selected_names)}")
        )

    def _sync_workspace_remote_checks_from_state(self):
        if not hasattr(self, "remote_file_table"):
            return
        table = self.remote_file_table
        table.blockSignals(True)
        try:
            for name, row in self._remote_row_by_name.items():
                item = table.item(row, 0)
                if item is None:
                    continue
                wanted = Qt.Checked if name in self.remote_selected_names else Qt.Unchecked
                if item.checkState() != wanted:
                    item.setCheckState(wanted)
        finally:
            table.blockSignals(False)
        self._update_remote_count_label()

    def _sync_poke_remote_checks_from_state(self):
        if not hasattr(self, "poke_remote_file_table"):
            return
        table = self.poke_remote_file_table
        table.blockSignals(True)
        try:
            for name, row in getattr(self, "_poke_remote_row_by_name", {}).items():
                item = table.item(row, 0)
                if item is None:
                    continue
                wanted = Qt.Checked if name in self.remote_selected_names else Qt.Unchecked
                if item.checkState() != wanted:
                    item.setCheckState(wanted)
        finally:
            table.blockSignals(False)
        self._update_poke_remote_count_label()

    def _on_poke_remote_file_item_changed(self, item):
        if getattr(self, "_poke_remote_table_populating", False) or item.column() != 0:
            return
        name = str(item.data(Qt.UserRole) or "")
        if not name:
            return
        if item.checkState() == Qt.Checked:
            self.remote_selected_names.add(name)
        else:
            self.remote_selected_names.discard(name)
        self._sync_workspace_remote_checks_from_state()
        self._update_poke_remote_count_label()
        self._invalidate_validation_snapshot("远程 G 文件选择发生变化")

    def _poke_set_visible_remote_selection(self, selected: bool):
        if not hasattr(self, "poke_remote_file_table"):
            return
        table = self.poke_remote_file_table
        table.blockSignals(True)
        try:
            for row in range(table.rowCount()):
                if table.isRowHidden(row):
                    continue
                item = table.item(row, 0)
                if item is None:
                    continue
                name = str(item.data(Qt.UserRole) or "")
                if selected:
                    self.remote_selected_names.add(name)
                    item.setCheckState(Qt.Checked)
                else:
                    self.remote_selected_names.discard(name)
                    item.setCheckState(Qt.Unchecked)
        finally:
            table.blockSignals(False)
        self._sync_workspace_remote_checks_from_state()
        self._update_poke_remote_count_label()
        self._invalidate_validation_snapshot("远程 G 文件选择发生变化")

    def _poke_clear_remote_selection(self):
        self.remote_selected_names.clear()
        if hasattr(self, "poke_remote_search_edit"):
            self.poke_remote_search_edit.blockSignals(True)
            try:
                self.poke_remote_search_edit.clear()
            finally:
                self.poke_remote_search_edit.blockSignals(False)
        self._sync_workspace_remote_checks_from_state()
        self._sync_poke_remote_checks_from_state()
        self._apply_poke_remote_file_filter("")
        self._invalidate_validation_snapshot("远程 G 文件选择和搜索条件已清空")

    def _poke_log(self, message):
        if hasattr(self, "poke_log_edit"):
            self.poke_log_edit.appendPlainText(str(message))

    def _set_poke_busy(self, busy: bool):
        for widget in (
            getattr(self, "poke_run_btn", None),
            getattr(self, "poke_enable_main_feeder", None),
            getattr(self, "poke_enable_smart_rmu", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_poke_processing(self):
        if self.poke_worker is not None and self.poke_worker.isRunning():
            return
        # Poke page owns a full source selector in v4.1.73; synchronize its
        # values into the shared source state before resolving the snapshot.
        self._sync_workspace_source_from_poke()
        enable_main = self.poke_enable_main_feeder.isChecked()
        enable_rmu = self.poke_enable_smart_rmu.isChecked()
        if not (enable_main or enable_rmu):
            QMessageBox.warning(self, "Poke 跳转", "请至少选择一种 Poke 跳转类型。")
            return

        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError(
                        "SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。"
                    )
                selected_remote = self._selected_remote_files()
                if not selected_remote:
                    raise ValueError(
                        "请先勾选至少一个远程 G 文件。"
                    )
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "Poke 跳转配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.poke_artifacts = {}
        self.poke_log_edit.clear()
        self.poke_progress.setValue(0)
        self.poke_progress_message.setText(self._t("任务准备中……"))
        self.poke_open_output_btn.setEnabled(False)
        self.poke_open_report_btn.setEnabled(False)
        self._set_poke_busy(True)

        try:
            if source_type == "SSH":
                self._poke_log("正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……")
                self.poke_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._poke_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_poke_busy(False)
            self.poke_progress_message.setText("文件准备失败")
            self._poke_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "Poke 文件准备失败", str(exc))
            return

        settings = {
            "rmu_name_positions": dict(
                self.cfg.get("rmu_name_positions", DEFAULT_RMU_NAME_POSITIONS)
            ),
            "rmu_name_exclusions": list(
                self.cfg.get("rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS)
            ),
        }
        self.poke_worker = PokeProcessingWorker(
            db_config=self.current_db_config(),
            files=files,
            settings=settings,
            run_dir=run_dir,
            enable_main_feeder=enable_main,
            enable_smart_rmu=enable_rmu,
        )
        self.poke_worker.log.connect(self._poke_log)
        self.poke_worker.progress.connect(self._on_poke_progress)
        self.poke_worker.completed.connect(self._on_poke_completed)
        self.poke_worker.failed.connect(self._on_poke_failed)
        self.poke_worker.start()

    def _on_poke_progress(self, percent, message):
        self.poke_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.poke_progress_message.setText(self._rt(message))

    def _on_poke_completed(self, artifacts):
        self.poke_artifacts = dict(artifacts or {})
        self._set_poke_busy(False)
        self.poke_progress.setValue(100)
        self.poke_progress_message.setText("Poke 跳转处理完成")
        self.poke_open_output_btn.setEnabled(
            bool(self.poke_artifacts.get("g_output_dir"))
        )
        self.poke_open_report_btn.setEnabled(
            bool(self.poke_artifacts.get("html_report"))
        )
        self.cfg["last_run_dir"] = self.poke_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._poke_log(
            "[完成] "
            f"新增={self.poke_artifacts.get('added', 0)}；"
            f"更新={self.poke_artifacts.get('updated', 0)}；"
            f"已符合={self.poke_artifacts.get('unchanged', 0)}；"
            f"跳过={self.poke_artifacts.get('skipped', 0)}。"
        )

    def _on_poke_failed(self, trace_text):
        self._set_poke_busy(False)
        self.poke_progress_message.setText("Poke 跳转处理失败")
        self._poke_log(str(trace_text))
        # Keep the dialog compact while the complete traceback remains in log.
        last_line = str(trace_text).strip().splitlines()[-1] if str(trace_text).strip() else "未知错误"
        QMessageBox.critical(self, "Poke 跳转处理失败", last_line)

    def _open_poke_output_dir(self):
        value = self.poke_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "G 输出目录")

    def _open_poke_report(self):
        value = self.poke_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "Poke 报告")

    def _open_external_path(self, path: Path, label: str):
        path = Path(path)
        if not path.exists():
            QMessageBox.warning(self, label, f"路径不存在：\n{path}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.critical(self, f"打开{label}失败", str(exc))

    def _graphics_cleanup_log(self, message):
        if hasattr(self, "graphics_cleanup_log_edit"):
            self.graphics_cleanup_log_edit.appendPlainText(str(message))

    def _set_graphics_cleanup_busy(self, busy: bool):
        for widget in (
            getattr(self, "graphics_cleanup_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_rmu_network_cleanup(self):
        if (
            self.graphics_cleanup_worker is not None
            and self.graphics_cleanup_worker.isRunning()
        ):
            return

        # 图形工作区所有任务共用上方同一套本地/SSH只读文件来源。
        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError(
                        "SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。"
                    )
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "环网柜网络图元清理配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.graphics_cleanup_artifacts = {}
        self.graphics_cleanup_log_edit.clear()
        self.graphics_cleanup_progress.setValue(0)
        self.graphics_cleanup_progress_message.setText(self._t("任务准备中……"))
        self.graphics_cleanup_open_output_btn.setEnabled(False)
        self.graphics_cleanup_open_report_btn.setEnabled(False)
        self._set_graphics_cleanup_busy(True)

        try:
            if source_type == "SSH":
                self._graphics_cleanup_log(
                    "正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……"
                )
                self.graphics_cleanup_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._graphics_cleanup_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_graphics_cleanup_busy(False)
            self.graphics_cleanup_progress_message.setText("文件准备失败")
            self._graphics_cleanup_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "清理文件准备失败", str(exc))
            return

        self.graphics_cleanup_worker = GraphicsCleanupWorker(
            files=files,
            run_dir=run_dir,
        )
        self.graphics_cleanup_worker.log.connect(self._graphics_cleanup_log)
        self.graphics_cleanup_worker.progress.connect(
            self._on_graphics_cleanup_progress
        )
        self.graphics_cleanup_worker.completed.connect(
            self._on_graphics_cleanup_completed
        )
        self.graphics_cleanup_worker.failed.connect(
            self._on_graphics_cleanup_failed
        )
        self.graphics_cleanup_worker.start()

    def _on_graphics_cleanup_progress(self, percent, message):
        self.graphics_cleanup_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.graphics_cleanup_progress_message.setText(self._rt(message))

    def _on_graphics_cleanup_completed(self, artifacts):
        self.graphics_cleanup_artifacts = dict(artifacts or {})
        self._set_graphics_cleanup_busy(False)
        self.graphics_cleanup_progress.setValue(100)
        self.graphics_cleanup_progress_message.setText("环网柜网络图元清理完成")
        self.graphics_cleanup_open_output_btn.setEnabled(
            bool(self.graphics_cleanup_artifacts.get("g_output_dir"))
        )
        self.graphics_cleanup_open_report_btn.setEnabled(
            bool(self.graphics_cleanup_artifacts.get("html_report"))
        )
        self.cfg["last_run_dir"] = self.graphics_cleanup_artifacts.get(
            "run_dir", ""
        )
        save_settings(self.cfg)
        self._graphics_cleanup_log(
            "[完成] "
            f"已删除固定网络图元={self.graphics_cleanup_artifacts.get('removed', 0)}。"
        )

    def _on_graphics_cleanup_failed(self, trace_text):
        self._set_graphics_cleanup_busy(False)
        self.graphics_cleanup_progress_message.setText("环网柜网络图元清理失败")
        self._graphics_cleanup_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "环网柜网络图元清理失败", last_line)

    def _open_graphics_cleanup_output_dir(self):
        value = self.graphics_cleanup_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "G 输出目录")

    def _open_graphics_cleanup_report(self):
        value = self.graphics_cleanup_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "环网柜网络图元清理报告")

    def _graphics_pipeline_log(self, message):
        if hasattr(self, "graphics_pipeline_log_edit"):
            self.graphics_pipeline_log_edit.appendPlainText(str(message))

    def _set_graphics_pipeline_busy(self, busy: bool):
        for widget in (
            getattr(self, "graphics_pipeline_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
            getattr(self, "pipeline_enable_cleanup", None),
            getattr(self, "pipeline_enable_channel", None),
            getattr(self, "pipeline_enable_poke", None),
            getattr(self, "pipeline_channel_position_combo", None),
            getattr(self, "pipeline_channel_margin_spin", None),
            getattr(self, "pipeline_poke_main_feeder", None),
            getattr(self, "pipeline_poke_smart_rmu", None),
            getattr(self, "pipeline_poke_select_all_btn", None),
            getattr(self, "pipeline_poke_clear_all_btn", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_graphics_pipeline(self):
        if self.graphics_pipeline_worker is not None and self.graphics_pipeline_worker.isRunning():
            return
        self._sync_workspace_source_from_poke()
        steps = {
            "cleanup": self.pipeline_enable_cleanup.isChecked(),
            "channel_status": self.pipeline_enable_channel.isChecked(),
            "poke": self.pipeline_enable_poke.isChecked(),
        }
        if not any(steps.values()):
            QMessageBox.warning(self, "组合处理", "请至少选择一个图形处理步骤。")
            return
        if steps["poke"] and not (self.pipeline_poke_main_feeder.isChecked() or self.pipeline_poke_smart_rmu.isChecked()):
            QMessageBox.warning(self, "组合处理", "启用 Poke 时，请至少选择一种 Poke 跳转类型。")
            return

        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "组合处理配置错误", str(exc))
            return

        db_config = None
        if steps["poke"]:
            try:
                db_config = self.current_db_config()
            except Exception as exc:
                QMessageBox.critical(self, "组合处理数据库配置错误", str(exc))
                return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.graphics_pipeline_artifacts = {}
        self.graphics_pipeline_log_edit.clear()
        self.graphics_pipeline_progress.setValue(0)
        self.graphics_pipeline_progress_message.setText(self._t("任务准备中……"))
        self.graphics_pipeline_open_output_btn.setEnabled(False)
        self.graphics_pipeline_open_report_btn.setEnabled(False)
        self._set_graphics_pipeline_busy(True)

        try:
            if source_type == "SSH":
                self._graphics_pipeline_log("正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……")
                self.graphics_pipeline_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._graphics_pipeline_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_graphics_pipeline_busy(False)
            self.graphics_pipeline_progress_message.setText("文件准备失败")
            self._graphics_pipeline_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "组合处理文件准备失败", str(exc))
            return

        settings = {
            "rmu_name_positions": dict(self.cfg.get("rmu_name_positions", DEFAULT_RMU_NAME_POSITIONS)),
            "rmu_name_exclusions": list(self.cfg.get("rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS)),
        }
        self.graphics_pipeline_worker = GraphicsPipelineWorker(
            files=files,
            run_dir=run_dir,
            steps=steps,
            channel_position=str(self.pipeline_channel_position_combo.currentData() or "bottom_left"),
            channel_margin=int(self.pipeline_channel_margin_spin.value()),
            db_config=db_config,
            poke_settings=settings,
            poke_enable_main_feeder=self.pipeline_poke_main_feeder.isChecked(),
            poke_enable_smart_rmu=self.pipeline_poke_smart_rmu.isChecked(),
        )
        self.graphics_pipeline_worker.log.connect(self._graphics_pipeline_log)
        self.graphics_pipeline_worker.progress.connect(self._on_graphics_pipeline_progress)
        self.graphics_pipeline_worker.completed.connect(self._on_graphics_pipeline_completed)
        self.graphics_pipeline_worker.failed.connect(self._on_graphics_pipeline_failed)
        self.graphics_pipeline_worker.start()

    def _on_graphics_pipeline_progress(self, percent, message):
        self.graphics_pipeline_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.graphics_pipeline_progress_message.setText(self._rt(message))

    def _on_graphics_pipeline_completed(self, artifacts):
        self.graphics_pipeline_artifacts = dict(artifacts or {})
        self._set_graphics_pipeline_busy(False)
        self.graphics_pipeline_progress.setValue(100)
        passed = int(self.graphics_pipeline_artifacts.get("passed", 0))
        failed = int(self.graphics_pipeline_artifacts.get("failed", 0))
        self.graphics_pipeline_progress_message.setText(f"组合处理完成：成功 {passed}，失败 {failed}")
        self.graphics_pipeline_open_output_btn.setEnabled(bool(self.graphics_pipeline_artifacts.get("g_output_dir")))
        self.graphics_pipeline_open_report_btn.setEnabled(bool(self.graphics_pipeline_artifacts.get("html_report")))
        self.cfg["last_run_dir"] = self.graphics_pipeline_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._graphics_pipeline_log(
            "[完成] "
            f"成功文件={passed}, 失败文件={failed}, "
            f"删除图元={self.graphics_pipeline_artifacts.get('cleanup_removed', 0)}, "
            f"channel_status移动={self.graphics_pipeline_artifacts.get('channel_moved', 0)}, "
            f"Poke新增={self.graphics_pipeline_artifacts.get('poke_added', 0)}, "
            f"Poke更新={self.graphics_pipeline_artifacts.get('poke_updated', 0)}。"
        )

    def _on_graphics_pipeline_failed(self, trace_text):
        self._set_graphics_pipeline_busy(False)
        self.graphics_pipeline_progress_message.setText("组合处理失败")
        self._graphics_pipeline_log(str(trace_text))
        last_line = str(trace_text).strip().splitlines()[-1] if str(trace_text).strip() else "未知错误"
        QMessageBox.critical(self, "组合处理失败", last_line)

    def _open_graphics_pipeline_output_dir(self):
        value = self.graphics_pipeline_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "G 输出目录")

    def _open_graphics_pipeline_report(self):
        value = self.graphics_pipeline_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "图形组合处理报告")

    def _channel_status_log(self, message):
        if hasattr(self, "channel_status_log_edit"):
            self.channel_status_log_edit.appendPlainText(str(message))

    def _set_channel_status_busy(self, busy: bool):
        for widget in (
            getattr(self, "channel_status_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
            getattr(self, "channel_status_position_combo", None),
            getattr(self, "channel_status_margin_spin", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_rmu_channel_status_reposition(self):
        if self.channel_status_worker is not None and self.channel_status_worker.isRunning():
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "channel_status 移动配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        position = str(self.channel_status_position_combo.currentData() or "bottom_left")
        inner_margin = int(self.channel_status_margin_spin.value())
        self.channel_status_artifacts = {}
        self.channel_status_log_edit.clear()
        self.channel_status_progress.setValue(0)
        self.channel_status_progress_message.setText(self._t("任务准备中……"))
        self.channel_status_open_output_btn.setEnabled(False)
        self.channel_status_open_report_btn.setEnabled(False)
        self._set_channel_status_busy(True)

        try:
            if source_type == "SSH":
                self._channel_status_log(
                    "正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……"
                )
                self.channel_status_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._channel_status_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_channel_status_busy(False)
            self.channel_status_progress_message.setText("文件准备失败")
            self._channel_status_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "channel_status 文件准备失败", str(exc))
            return

        self.channel_status_worker = ChannelStatusRepositionWorker(
            files=files,
            run_dir=run_dir,
            position=position,
            inner_margin=inner_margin,
        )
        self.channel_status_worker.log.connect(self._channel_status_log)
        self.channel_status_worker.progress.connect(self._on_channel_status_progress)
        self.channel_status_worker.completed.connect(self._on_channel_status_completed)
        self.channel_status_worker.failed.connect(self._on_channel_status_failed)
        self.channel_status_worker.start()

    def _on_channel_status_progress(self, percent, message):
        self.channel_status_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.channel_status_progress_message.setText(self._rt(message))

    def _on_channel_status_completed(self, artifacts):
        self.channel_status_artifacts = dict(artifacts or {})
        self._set_channel_status_busy(False)
        self.channel_status_progress.setValue(100)
        self.channel_status_progress_message.setText("环网柜 channel_status 移动完成")
        self.channel_status_open_output_btn.setEnabled(
            bool(self.channel_status_artifacts.get("g_output_dir"))
        )
        self.channel_status_open_report_btn.setEnabled(
            bool(self.channel_status_artifacts.get("html_report"))
        )
        self.cfg["last_run_dir"] = self.channel_status_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._channel_status_log(
            "[完成] "
            f"找到 channel_status={self.channel_status_artifacts.get('found', 0)}，"
            f"移动={self.channel_status_artifacts.get('moved', 0)}，"
            f"未找到={self.channel_status_artifacts.get('missing', 0)}。"
        )

    def _on_channel_status_failed(self, trace_text):
        self._set_channel_status_busy(False)
        self.channel_status_progress_message.setText("环网柜 channel_status 移动失败")
        self._channel_status_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "环网柜 channel_status 移动失败", last_line)

    def _open_channel_status_output_dir(self):
        value = self.channel_status_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "G 输出目录")

    def _open_channel_status_report(self):
        value = self.channel_status_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "环网柜 channel_status 移动报告")

    def _rmu_annotation_log(self, message):
        if hasattr(self, "rmu_annotation_log_edit"):
            self.rmu_annotation_log_edit.appendPlainText(str(message))

    def _set_rmu_annotation_busy(self, busy: bool):
        for widget in (
            getattr(self, "rmu_annotation_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
            getattr(self, "rmu_annotation_nop_position_combo", None),
            getattr(self, "rmu_annotation_nop_margin_spin", None),
            getattr(self, "rmu_annotation_name_position_combo", None),
            getattr(self, "rmu_annotation_name_margin_spin", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_rmu_annotation_reposition(self):
        if self.rmu_annotation_worker is not None and self.rmu_annotation_worker.isRunning():
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "NOP / 名称位置配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        nop_position = str(self.rmu_annotation_nop_position_combo.currentData() or "auto")
        rmu_name_position = str(self.rmu_annotation_name_position_combo.currentData() or "right")
        nop_margin = int(self.rmu_annotation_nop_margin_spin.value())
        rmu_name_margin = int(self.rmu_annotation_name_margin_spin.value())

        self.rmu_annotation_artifacts = {}
        self.rmu_annotation_log_edit.clear()
        self.rmu_annotation_progress.setValue(0)
        self.rmu_annotation_progress_message.setText(self._t("任务准备中……"))
        self.rmu_annotation_open_output_btn.setEnabled(False)
        self.rmu_annotation_open_report_btn.setEnabled(False)
        self._set_rmu_annotation_busy(True)

        try:
            if source_type == "SSH":
                self._rmu_annotation_log("正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……")
                self.rmu_annotation_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._rmu_annotation_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_rmu_annotation_busy(False)
            self.rmu_annotation_progress_message.setText("文件准备失败")
            self._rmu_annotation_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "NOP / 名称位置文件准备失败", str(exc))
            return

        self.rmu_annotation_worker = RmuAnnotationPositionWorker(
            files=files,
            run_dir=run_dir,
            nop_position=nop_position,
            rmu_name_position=rmu_name_position,
            nop_margin=nop_margin,
            rmu_name_margin=rmu_name_margin,
        )
        self.rmu_annotation_worker.log.connect(self._rmu_annotation_log)
        self.rmu_annotation_worker.progress.connect(self._on_rmu_annotation_progress)
        self.rmu_annotation_worker.completed.connect(self._on_rmu_annotation_completed)
        self.rmu_annotation_worker.failed.connect(self._on_rmu_annotation_failed)
        self.rmu_annotation_worker.start()

    def _on_rmu_annotation_progress(self, percent, message):
        self.rmu_annotation_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.rmu_annotation_progress_message.setText(self._rt(message))

    def _on_rmu_annotation_completed(self, artifacts):
        self.rmu_annotation_artifacts = dict(artifacts or {})
        self._set_rmu_annotation_busy(False)
        self.rmu_annotation_progress.setValue(100)
        self.rmu_annotation_progress_message.setText("NOP / 环网柜名称位置调整完成")
        self.rmu_annotation_open_output_btn.setEnabled(
            bool(self.rmu_annotation_artifacts.get("g_output_dir"))
        )
        self.rmu_annotation_open_report_btn.setEnabled(
            bool(self.rmu_annotation_artifacts.get("html_report"))
        )
        self.cfg["last_run_dir"] = self.rmu_annotation_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._rmu_annotation_log(
            "[完成] "
            f"环网柜名称找到={self.rmu_annotation_artifacts.get('rmu_name_found', 0)}，"
            f"名称移动={self.rmu_annotation_artifacts.get('rmu_name_moved', 0)}，"
            f"NOP找到={self.rmu_annotation_artifacts.get('nop_found', 0)}，"
            f"NOP移动={self.rmu_annotation_artifacts.get('nop_moved', 0)}，"
            f"NOP无对应Y/Q开关={self.rmu_annotation_artifacts.get('nop_unmatched_device', 0)}。"
        )

    def _on_rmu_annotation_failed(self, trace_text):
        self._set_rmu_annotation_busy(False)
        self.rmu_annotation_progress_message.setText("NOP / 环网柜名称位置调整失败")
        self._rmu_annotation_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "NOP / 环网柜名称位置调整失败", last_line)

    def _open_rmu_annotation_output_dir(self):
        value = self.rmu_annotation_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "G 输出目录")

    def _open_rmu_annotation_report(self):
        value = self.rmu_annotation_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "NOP / 环网柜名称位置报告")

    def _feeder_avoidance_log(self, message):
        if hasattr(self, "feeder_avoidance_log_edit"):
            self.feeder_avoidance_log_edit.appendPlainText(str(message))

    def _set_feeder_avoidance_busy(self, busy: bool):
        for widget in (
            getattr(self, "feeder_avoidance_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
            getattr(self, "feeder_avoidance_clearance_spin", None),
            getattr(self, "feeder_avoidance_spacing_spin", None),
            getattr(self, "feeder_avoidance_corridor_spin", None),
            getattr(self, "feeder_avoidance_max_shift_spin", None),
            getattr(self, "feeder_avoidance_right_check", None),
            getattr(self, "feeder_avoidance_left_check", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_feeder_avoidance(self):
        if self.feeder_avoidance_worker is not None and self.feeder_avoidance_worker.isRunning():
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "馈线避让配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        text_clearance = int(self.feeder_avoidance_clearance_spin.value())
        feeder_spacing = int(self.feeder_avoidance_spacing_spin.value())
        corridor_tolerance = int(self.feeder_avoidance_corridor_spin.value())
        max_right_shift = int(self.feeder_avoidance_max_shift_spin.value())
        process_right = bool(self.feeder_avoidance_right_check.isChecked())
        process_left = bool(self.feeder_avoidance_left_check.isChecked())
        if not process_right and not process_left:
            QMessageBox.critical(self, "馈线避让配置错误", "右侧馈线和左侧馈线至少选择一个处理方向。")
            return

        # Keep field-tuned graphics parameters in the per-user settings cache
        # so replacement builds preserve the operator's preferred lane layout.
        self.cfg["feeder_avoidance_text_clearance"] = text_clearance
        self.cfg["feeder_avoidance_track_spacing"] = feeder_spacing
        self.cfg["feeder_avoidance_corridor_tolerance"] = corridor_tolerance
        self.cfg["feeder_avoidance_max_shift"] = max_right_shift
        self.cfg["feeder_avoidance_process_right"] = process_right
        self.cfg["feeder_avoidance_process_left"] = process_left
        save_settings(self.cfg)

        self.feeder_avoidance_artifacts = {}
        self.feeder_avoidance_log_edit.clear()
        self.feeder_avoidance_progress.setValue(0)
        self.feeder_avoidance_progress_message.setText(self._t("任务准备中……"))
        self.feeder_avoidance_open_output_btn.setEnabled(False)
        self.feeder_avoidance_open_report_btn.setEnabled(False)
        self._set_feeder_avoidance_busy(True)

        try:
            if source_type == "SSH":
                self._feeder_avoidance_log("正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……")
                self.feeder_avoidance_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._feeder_avoidance_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_feeder_avoidance_busy(False)
            self.feeder_avoidance_progress_message.setText("文件准备失败")
            self._feeder_avoidance_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "馈线避让文件准备失败", str(exc))
            return

        self.feeder_avoidance_worker = FeederAvoidanceWorker(
            files=files,
            run_dir=run_dir,
            text_clearance=text_clearance,
            feeder_spacing=feeder_spacing,
            corridor_tolerance=corridor_tolerance,
            max_right_shift=max_right_shift,
            process_right=process_right,
            process_left=process_left,
        )
        self.feeder_avoidance_worker.log.connect(self._feeder_avoidance_log)
        self.feeder_avoidance_worker.progress.connect(self._on_feeder_avoidance_progress)
        self.feeder_avoidance_worker.completed.connect(self._on_feeder_avoidance_completed)
        self.feeder_avoidance_worker.failed.connect(self._on_feeder_avoidance_failed)
        self.feeder_avoidance_worker.start()

    def _on_feeder_avoidance_progress(self, percent, message):
        self.feeder_avoidance_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.feeder_avoidance_progress_message.setText(self._rt(message))

    def _on_feeder_avoidance_completed(self, artifacts):
        self.feeder_avoidance_artifacts = dict(artifacts or {})
        self._set_feeder_avoidance_busy(False)
        self.feeder_avoidance_progress.setValue(100)
        self.feeder_avoidance_progress_message.setText("馈线避让调整完成")
        self.feeder_avoidance_open_output_btn.setEnabled(
            bool(self.feeder_avoidance_artifacts.get("g_output_dir"))
        )
        self.feeder_avoidance_open_report_btn.setEnabled(
            bool(self.feeder_avoidance_artifacts.get("html_report"))
        )
        self.cfg["last_run_dir"] = self.feeder_avoidance_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._feeder_avoidance_log(
            "[完成] "
            f"碰撞馈线={self.feeder_avoidance_artifacts.get('colliding_feedline_count', 0)}，"
            f"已移动馈线={self.feeder_avoidance_artifacts.get('moved_feedline_count', 0)}，"
            f"已移动线段={self.feeder_avoidance_artifacts.get('moved_segment_count', 0)}，"
            f"错落线段={self.feeder_avoidance_artifacts.get('staggered_segment_count', 0)}，"
            f"未解决碰撞={self.feeder_avoidance_artifacts.get('unresolved_collision_count', 0)}。"
        )

    def _on_feeder_avoidance_failed(self, trace_text):
        self._set_feeder_avoidance_busy(False)
        self.feeder_avoidance_progress_message.setText("馈线避让调整失败")
        self._feeder_avoidance_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "馈线避让调整失败", last_line)

    def _open_feeder_avoidance_output_dir(self):
        value = self.feeder_avoidance_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "G 输出目录")

    def _open_feeder_avoidance_report(self):
        value = self.feeder_avoidance_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "馈线避让调整报告")

    def _rmu_feeder_topology_log(self, message):
        if hasattr(self, "rmu_feeder_topology_log_edit"):
            self.rmu_feeder_topology_log_edit.appendPlainText(str(message))

    def _set_rmu_feeder_topology_busy(self, busy: bool):
        for widget in (
            getattr(self, "rmu_feeder_topology_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_rmu_feeder_topology_analysis(self):
        if (
            self.rmu_feeder_topology_worker is not None
            and self.rmu_feeder_topology_worker.isRunning()
        ):
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可分析的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "环网柜馈线拓扑分析配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.rmu_feeder_topology_artifacts = {}
        self.rmu_feeder_topology_log_edit.clear()
        self.rmu_feeder_topology_progress.setValue(0)
        self.rmu_feeder_topology_progress_message.setText(self._t("任务准备中……"))
        self.rmu_feeder_topology_open_report_btn.setEnabled(False)
        self.rmu_feeder_topology_open_dir_btn.setEnabled(False)
        self._set_rmu_feeder_topology_busy(True)

        try:
            if source_type == "SSH":
                self._rmu_feeder_topology_log("正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……")
                self.rmu_feeder_topology_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._rmu_feeder_topology_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_rmu_feeder_topology_busy(False)
            self.rmu_feeder_topology_progress_message.setText("文件准备失败")
            self._rmu_feeder_topology_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "环网柜馈线拓扑分析文件准备失败", str(exc))
            return

        self.rmu_feeder_topology_worker = RmuFeederTopologyWorker(
            files=files,
            run_dir=run_dir,
        )
        self.rmu_feeder_topology_worker.log.connect(self._rmu_feeder_topology_log)
        self.rmu_feeder_topology_worker.progress.connect(self._on_rmu_feeder_topology_progress)
        self.rmu_feeder_topology_worker.completed.connect(self._on_rmu_feeder_topology_completed)
        self.rmu_feeder_topology_worker.failed.connect(self._on_rmu_feeder_topology_failed)
        self.rmu_feeder_topology_worker.start()

    def _on_rmu_feeder_topology_progress(self, percent, message):
        self.rmu_feeder_topology_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.rmu_feeder_topology_progress_message.setText(self._rt(message))

    def _on_rmu_feeder_topology_completed(self, artifacts):
        self.rmu_feeder_topology_artifacts = dict(artifacts or {})
        self._set_rmu_feeder_topology_busy(False)
        self.rmu_feeder_topology_progress.setValue(100)
        self.rmu_feeder_topology_progress_message.setText("环网柜馈线拓扑分析完成")
        self.rmu_feeder_topology_open_report_btn.setEnabled(
            bool(self.rmu_feeder_topology_artifacts.get("html_report"))
        )
        self.rmu_feeder_topology_open_dir_btn.setEnabled(
            bool(self.rmu_feeder_topology_artifacts.get("report_dir"))
        )
        self.cfg["last_run_dir"] = self.rmu_feeder_topology_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._rmu_feeder_topology_log(
            "[完成] "
            f"主网馈线={self.rmu_feeder_topology_artifacts.get('source_feeder_count', 0)}，"
            f"入口支路遇NOP={self.rmu_feeder_topology_artifacts.get('source_entry_nop_feeder_count', 0)}，"
            f"RMU={self.rmu_feeder_topology_artifacts.get('rmu_count', 0)}，"
            f"唯一归属={self.rmu_feeder_topology_artifacts.get('unique_count', 0)}，"
            f"NOP边界柜={self.rmu_feeder_topology_artifacts.get('nop_boundary_count', 0)}，"
            f"冲突={self.rmu_feeder_topology_artifacts.get('conflict_count', 0)}，"
            f"未确定={self.rmu_feeder_topology_artifacts.get('unresolved_count', 0)}。"
        )

    def _on_rmu_feeder_topology_failed(self, trace_text):
        self._set_rmu_feeder_topology_busy(False)
        self.rmu_feeder_topology_progress_message.setText("环网柜馈线拓扑分析失败")
        self._rmu_feeder_topology_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "环网柜馈线拓扑分析失败", last_line)

    def _open_rmu_feeder_topology_report(self):
        value = self.rmu_feeder_topology_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "环网柜馈线拓扑分析报告")

    def _open_rmu_feeder_topology_report_dir(self):
        value = self.rmu_feeder_topology_artifacts.get("report_dir", "")
        if value:
            self._open_external_path(Path(value), "拓扑分析结果目录")

    def _feedline_feeder_topology_log(self, message):
        if hasattr(self, "feedline_feeder_topology_log_edit"):
            self.feedline_feeder_topology_log_edit.appendPlainText(str(message))

    def _set_feedline_feeder_topology_busy(self, busy: bool):
        for widget in (
            getattr(self, "feedline_feeder_topology_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_feedline_feeder_topology_analysis(self):
        if (
            self.feedline_feeder_topology_worker is not None
            and self.feedline_feeder_topology_worker.isRunning()
        ):
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可分析的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "馈线段所属馈线分析配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.feedline_feeder_topology_artifacts = {}
        self.feedline_feeder_topology_log_edit.clear()
        self.feedline_feeder_topology_progress.setValue(0)
        self.feedline_feeder_topology_progress_message.setText(self._t("任务准备中……"))
        self.feedline_feeder_topology_open_report_btn.setEnabled(False)
        self.feedline_feeder_topology_open_dir_btn.setEnabled(False)
        self._set_feedline_feeder_topology_busy(True)

        try:
            if source_type == "SSH":
                self._feedline_feeder_topology_log("正在从 SSH 只读服务器获取本次选择文件的最新稳定快照……")
                self.feedline_feeder_topology_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._feedline_feeder_topology_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_feedline_feeder_topology_busy(False)
            self.feedline_feeder_topology_progress_message.setText("文件准备失败")
            self._feedline_feeder_topology_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "馈线段所属馈线分析文件准备失败", str(exc))
            return

        self.feedline_feeder_topology_worker = FeedlineFeederTopologyWorker(
            files=files,
            run_dir=run_dir,
        )
        self.feedline_feeder_topology_worker.log.connect(self._feedline_feeder_topology_log)
        self.feedline_feeder_topology_worker.progress.connect(self._on_feedline_feeder_topology_progress)
        self.feedline_feeder_topology_worker.completed.connect(self._on_feedline_feeder_topology_completed)
        self.feedline_feeder_topology_worker.failed.connect(self._on_feedline_feeder_topology_failed)
        self.feedline_feeder_topology_worker.start()

    def _on_feedline_feeder_topology_progress(self, percent, message):
        self.feedline_feeder_topology_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.feedline_feeder_topology_progress_message.setText(self._rt(message))

    def _on_feedline_feeder_topology_completed(self, artifacts):
        self.feedline_feeder_topology_artifacts = dict(artifacts or {})
        self._set_feedline_feeder_topology_busy(False)
        self.feedline_feeder_topology_progress.setValue(100)
        self.feedline_feeder_topology_progress_message.setText("馈线段所属馈线分析完成")
        self.feedline_feeder_topology_open_report_btn.setEnabled(
            bool(self.feedline_feeder_topology_artifacts.get("html_report"))
        )
        self.feedline_feeder_topology_open_dir_btn.setEnabled(
            bool(self.feedline_feeder_topology_artifacts.get("report_dir"))
        )
        self.cfg["last_run_dir"] = self.feedline_feeder_topology_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._feedline_feeder_topology_log(
            "[完成] "
            f"主网馈线={self.feedline_feeder_topology_artifacts.get('source_feeder_count', 0)}，"
            f"FeedLine={self.feedline_feeder_topology_artifacts.get('feedline_count', 0)}，"
            f"确认={self.feedline_feeder_topology_artifacts.get('confirmed_count', 0)}，"
            f"冲突={self.feedline_feeder_topology_artifacts.get('conflict_count', 0)}，"
            f"未确定={self.feedline_feeder_topology_artifacts.get('unresolved_count', 0)}，"
            f"红色NOP边界={self.feedline_feeder_topology_artifacts.get('nop_boundary_count', 0)}。"
        )

    def _on_feedline_feeder_topology_failed(self, trace_text):
        self._set_feedline_feeder_topology_busy(False)
        self.feedline_feeder_topology_progress_message.setText("馈线段所属馈线分析失败")
        self._feedline_feeder_topology_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "馈线段所属馈线分析失败", last_line)

    def _open_feedline_feeder_topology_report(self):
        value = self.feedline_feeder_topology_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "馈线段所属馈线分析报告")

    def _open_feedline_feeder_topology_report_dir(self):
        value = self.feedline_feeder_topology_artifacts.get("report_dir", "")
        if value:
            self._open_external_path(Path(value), "馈线段拓扑分析结果目录")

    def _main_station_background_label_log(self, message):
        if hasattr(self, "main_station_background_label_log_edit"):
            self.main_station_background_label_log_edit.appendPlainText(str(message))

    def _set_main_station_background_label_busy(self, busy: bool):
        for widget in (
            getattr(self, "main_station_background_label_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_main_station_background_label_repair(self):
        if (
            self.main_station_background_label_worker is not None
            and self.main_station_background_label_worker.isRunning()
        ):
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可处理的 .g 文件。")
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                if not self._selected_remote_files():
                    raise ValueError("请先勾选至少一个远程 G 文件。")
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "主网入口背景标签修正配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.main_station_background_label_artifacts = {}
        self.main_station_background_label_log_edit.clear()
        self.main_station_background_label_progress.setValue(0)
        self.main_station_background_label_progress_message.setText(self._t("任务准备中……"))
        self.main_station_background_label_open_report_btn.setEnabled(False)
        self.main_station_background_label_open_dir_btn.setEnabled(False)
        self._set_main_station_background_label_busy(True)

        try:
            if source_type == "SSH":
                self._main_station_background_label_log("正在从 SSH 只读服务器获取所选 G 文件的最新稳定快照……")
                self.main_station_background_label_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._main_station_background_label_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_main_station_background_label_busy(False)
            self.main_station_background_label_progress_message.setText("文件准备失败")
            self._main_station_background_label_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "主网入口背景标签修正文件准备失败", str(exc))
            return

        self.main_station_background_label_worker = MainStationBackgroundLabelWorker(
            files=files, run_dir=run_dir
        )
        self.main_station_background_label_worker.log.connect(self._main_station_background_label_log)
        self.main_station_background_label_worker.progress.connect(self._on_main_station_background_label_progress)
        self.main_station_background_label_worker.completed.connect(self._on_main_station_background_label_completed)
        self.main_station_background_label_worker.failed.connect(self._on_main_station_background_label_failed)
        self.main_station_background_label_worker.start()

    def _on_main_station_background_label_progress(self, percent, message):
        self.main_station_background_label_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.main_station_background_label_progress_message.setText(self._rt(message))

    def _on_main_station_background_label_completed(self, artifacts):
        self.main_station_background_label_artifacts = dict(artifacts or {})
        self._set_main_station_background_label_busy(False)
        self.main_station_background_label_progress.setValue(100)
        self.main_station_background_label_progress_message.setText("主网入口背景标签修正完成")
        self.main_station_background_label_open_report_btn.setEnabled(
            bool(self.main_station_background_label_artifacts.get("html_report"))
        )
        self.main_station_background_label_open_dir_btn.setEnabled(
            bool(self.main_station_background_label_artifacts.get("g_output_dir"))
        )
        self.cfg["last_run_dir"] = self.main_station_background_label_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._main_station_background_label_log(
            "[完成] "
            f"候选={self.main_station_background_label_artifacts.get('candidate_count', 0)}，"
            f"文字已修正={self.main_station_background_label_artifacts.get('updated_count', 0)}，"
            f"背景排版={self.main_station_background_label_artifacts.get('layout_count', 0)}，"
            f"歧义={self.main_station_background_label_artifacts.get('ambiguous_count', 0)}，"
            f"跳过={self.main_station_background_label_artifacts.get('skipped_count', 0)}。"
        )

    def _on_main_station_background_label_failed(self, trace_text):
        self._set_main_station_background_label_busy(False)
        self.main_station_background_label_progress_message.setText("主网入口背景标签修正失败")
        self._main_station_background_label_log(str(trace_text))
        last_line = str(trace_text).strip().splitlines()[-1] if str(trace_text).strip() else "未知错误"
        QMessageBox.critical(self, "主网入口背景标签修正失败", last_line)

    def _open_main_station_background_label_report(self):
        value = self.main_station_background_label_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "主网入口背景标签修正报告")

    def _open_main_station_background_label_output_dir(self):
        value = self.main_station_background_label_artifacts.get("g_output_dir", "")
        if value:
            self._open_external_path(Path(value), "主网入口背景标签输出目录")

    def _whole_graph_topology_log(self, message):
        if hasattr(self, "whole_graph_topology_log_edit"):
            self.whole_graph_topology_log_edit.appendPlainText(str(message))

    def _set_whole_graph_topology_busy(self, busy: bool):
        for widget in (
            getattr(self, "whole_graph_topology_run_btn", None),
            getattr(self, "graphics_operation_combo", None),
        ):
            if widget is not None:
                widget.setEnabled(not busy)

    def start_whole_graph_topology_analysis(self):
        if (
            self.whole_graph_topology_worker is not None
            and self.whole_graph_topology_worker.isRunning()
        ):
            return

        self._sync_workspace_source_from_poke()
        files = []
        try:
            source_type = self._current_input_source()
            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择一个 G 文件。")
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError("当前文件/目录中没有找到可分析的 .g 文件。")
                if len(files) != 1:
                    raise ValueError(
                        f"整图馈线拓扑分析一次只处理 1 个 G 文件；当前解析到 {len(files)} 个，请直接选择单个 .g 文件。"
                    )
            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"], int(ssh_cfg["port"]),
                    ssh_cfg["username"], ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError("SSH 配置与当前文件列表不一致，请先刷新 G 文件列表。")
                selected = self._selected_remote_files()
                if len(selected) != 1:
                    raise ValueError(
                        f"整图馈线拓扑分析一次只处理 1 个 G 文件；当前已勾选 {len(selected)} 个。"
                    )
            else:
                raise ValueError(f"不支持的文件来源：{source_type}")
        except Exception as exc:
            QMessageBox.critical(self, "整图馈线拓扑分析配置错误", str(exc))
            return

        try:
            run_dir = create_run_directory()
        except Exception as exc:
            QMessageBox.critical(self, "创建 Workspace 运行目录失败", str(exc))
            return

        self.whole_graph_topology_artifacts = {}
        self.whole_graph_topology_log_edit.clear()
        self.whole_graph_topology_progress.setValue(0)
        self.whole_graph_topology_progress_message.setText(self._t("任务准备中……"))
        self.whole_graph_topology_open_report_btn.setEnabled(False)
        self.whole_graph_topology_open_dir_btn.setEnabled(False)
        self._set_whole_graph_topology_busy(True)

        try:
            if source_type == "SSH":
                self._whole_graph_topology_log("正在从 SSH 只读服务器获取所选 G 文件的最新稳定快照……")
                self.whole_graph_topology_progress.setValue(2)
                QApplication.processEvents()
                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg["remote_directory"],
                    max_attempts=3,
                )
                files, _source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    run_dir,
                    log=self._whole_graph_topology_log,
                )
            self._sync_poke_source_from_workspace(rebuild_remote=False)
        except Exception as exc:
            self._set_whole_graph_topology_busy(False)
            self.whole_graph_topology_progress_message.setText("文件准备失败")
            self._whole_graph_topology_log(f"文件准备失败：{exc}")
            QMessageBox.critical(self, "整图馈线拓扑分析文件准备失败", str(exc))
            return

        self.whole_graph_topology_worker = WholeGraphTopologyWorker(
            files=files,
            run_dir=run_dir,
        )
        self.whole_graph_topology_worker.log.connect(self._whole_graph_topology_log)
        self.whole_graph_topology_worker.progress.connect(self._on_whole_graph_topology_progress)
        self.whole_graph_topology_worker.completed.connect(self._on_whole_graph_topology_completed)
        self.whole_graph_topology_worker.failed.connect(self._on_whole_graph_topology_failed)
        self.whole_graph_topology_worker.start()

    def _on_whole_graph_topology_progress(self, percent, message):
        self.whole_graph_topology_progress.setValue(max(0, min(100, int(percent))))
        if message:
            self.whole_graph_topology_progress_message.setText(self._rt(message))

    def _on_whole_graph_topology_completed(self, artifacts):
        self.whole_graph_topology_artifacts = dict(artifacts or {})
        self._set_whole_graph_topology_busy(False)
        self.whole_graph_topology_progress.setValue(100)
        self.whole_graph_topology_progress_message.setText("整图馈线拓扑分析 / 自动修复完成")
        self.whole_graph_topology_open_report_btn.setEnabled(
            bool(self.whole_graph_topology_artifacts.get("html_report"))
        )
        self.whole_graph_topology_open_dir_btn.setEnabled(
            bool(self.whole_graph_topology_artifacts.get("report_dir"))
        )
        self.cfg["last_run_dir"] = self.whole_graph_topology_artifacts.get("run_dir", "")
        save_settings(self.cfg)
        self._whole_graph_topology_log(
            "[完成] "
            f"馈线={self.whole_graph_topology_artifacts.get('feeder_count', 0)}，"
            f"设备={self.whole_graph_topology_artifacts.get('device_count', 0)}，"
            f"确认={self.whole_graph_topology_artifacts.get('confirmed_count', 0)}，"
            f"拓扑异常={self.whole_graph_topology_artifacts.get('topology_error_count', 0)}，"
            f"无馈线={self.whole_graph_topology_artifacts.get('no_feeder_error_count', 0)}，"
            f"多馈线={self.whole_graph_topology_artifacts.get('multi_feeder_error_count', 0)}，"
            f"RMU={self.whole_graph_topology_artifacts.get('rmu_count', 0)}（确认={self.whole_graph_topology_artifacts.get('rmu_confirmed_count', 0)}，异常={self.whole_graph_topology_artifacts.get('rmu_error_count', 0)}），"
            f"RMU NOP={self.whole_graph_topology_artifacts.get('rmu_nop_count', 0)}，"
            f"柱上NOP={self.whole_graph_topology_artifacts.get('pole_nop_count', 0)}，"
            f"自动修复={self.whole_graph_topology_artifacts.get('repair_applied_count', 0)}，"
            f"拓扑异常={self.whole_graph_topology_artifacts.get('before_topology_error_count', 0)}→{self.whole_graph_topology_artifacts.get('after_topology_error_count', 0)}。"
        )
        fixed_g = self.whole_graph_topology_artifacts.get("fixed_g", "")
        if fixed_g:
            self._whole_graph_topology_log(f"[修复后 G] {fixed_g}")

    def _on_whole_graph_topology_failed(self, trace_text):
        self._set_whole_graph_topology_busy(False)
        self.whole_graph_topology_progress_message.setText("整图馈线拓扑分析失败")
        self._whole_graph_topology_log(str(trace_text))
        last_line = (
            str(trace_text).strip().splitlines()[-1]
            if str(trace_text).strip()
            else "未知错误"
        )
        QMessageBox.critical(self, "整图馈线拓扑分析失败", last_line)

    def _open_whole_graph_topology_report(self):
        value = self.whole_graph_topology_artifacts.get("html_report", "")
        if value:
            self._open_external_path(Path(value), "整图馈线拓扑分析报告")

    def _open_whole_graph_topology_report_dir(self):
        value = self.whole_graph_topology_artifacts.get("report_dir", "")
        if value:
            self._open_external_path(Path(value), "整图拓扑分析结果目录")

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

        db_mode = QLabel(
            "数据库访问模式：只读查询为默认。仅馈线模型在启用“自动创建缺失馈线段”并执行"
            "【模型关联】时，允许 INSERT DMS_SECTION_DEVICE；不会 UPDATE / DELETE "
            "已有数据库设备。除该明确启用的馈线段 INSERT 外，其他流程"
            "不会向 Oracle 数据库执行 INSERT / UPDATE / DELETE。"
            "G 文件仍只修改 Workspace 安全副本。"
        )
        db_mode.setWordWrap(True)
        db_mode.setStyleSheet(
            "color:#006B52;background:#EAF8F2;"
            "border:1px solid #B9DACD;border-radius:6px;padding:8px;"
        )
        layout.addWidget(db_mode)

        actions = QHBoxLayout()
        test_btn = QPushButton("测试数据库连接")
        test_btn.clicked.connect(self.test_connection)

        save_btn = QPushButton("保存数据库配置")
        save_btn.clicked.connect(self.save_database_settings)
        self.db_save_button = save_btn

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

        top_actions = QHBoxLayout()
        self.module_help_btn = QPushButton("当前模型帮助")
        self.module_help_btn.setMinimumWidth(112)
        self.module_help_btn.clicked.connect(self.show_current_module_help)
        top_actions.addWidget(self.module_help_btn)
        top_actions.addStretch()
        grid.addLayout(top_actions, 0, 3)

        grid.addWidget(QLabel("文件来源（RMU / 馈线通用）"), 1, 0)
        self.input_source_combo = NoWheelComboBox()
        self.input_source_combo.addItem("本地文件 / 目录", "LOCAL")
        self.input_source_combo.addItem("SSH 文件服务器（只读）", "SSH")
        saved_source = str(self.cfg.get("input_source", "LOCAL")).upper()
        source_index = self.input_source_combo.findData(saved_source)
        self.input_source_combo.setCurrentIndex(
            source_index if source_index >= 0 else 0
        )
        self.input_source_combo.currentIndexChanged.connect(
            self._on_input_source_changed
        )
        grid.addWidget(self.input_source_combo, 1, 1, 1, 3)

        self.input_source_stack = QStackedWidget()
        self.input_source_stack.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        # Local source page.
        local_page = QWidget()
        local_layout = QGridLayout(local_page)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.addWidget(QLabel("G 文件 / 目录"), 0, 0)
        self.input_edit = QLineEdit(self.cfg.get("input_path", ""))
        self.input_edit.setPlaceholderText(
            "请选择一个 G 文件，或包含 G 文件的目录"
        )
        self.input_edit.editingFinished.connect(
            self._save_input_path_from_edit
        )
        local_layout.addWidget(self.input_edit, 0, 1)
        file_btn = QPushButton("选择文件")
        folder_btn = QPushButton("选择目录")
        file_btn.setMinimumWidth(100)
        folder_btn.setMinimumWidth(100)
        file_btn.clicked.connect(self.browse_file)
        folder_btn.clicked.connect(self.browse_folder)
        local_layout.addWidget(file_btn, 0, 2)
        local_layout.addWidget(folder_btn, 0, 3)
        local_page.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        self.input_source_stack.addWidget(local_page)

        # SSH read-only source page.
        remote_page = QWidget()
        remote_layout = QVBoxLayout(remote_page)
        remote_layout.setContentsMargins(0, 0, 0, 0)
        remote_layout.setSpacing(8)

        ssh_cfg = dict(self.cfg.get("ssh", {}) or {})
        ssh_grid = QGridLayout()
        self.ssh_edits = {}

        ssh_fields = [
            ("host", "IP / 主机", ssh_cfg.get("host", "172.16.21.27")),
            ("port", "端口", ssh_cfg.get("port", 22)),
            ("username", "用户名", ssh_cfg.get("username", "up8000")),
            ("password", "密码", ssh_cfg.get("password", "up8000")),
            (
                "remote_directory",
                "远程目录",
                ssh_cfg.get(
                    "remote_directory",
                    "/home/up8000/data/graph/display/sln",
                ),
            ),
        ]
        for row_index, (key, label, value) in enumerate(ssh_fields):
            ssh_grid.addWidget(QLabel(label), row_index, 0)
            edit = QLineEdit(str(value))
            if key == "password":
                edit.setEchoMode(QLineEdit.Password)
            self.ssh_edits[key] = edit
            ssh_grid.addWidget(edit, row_index, 1, 1, 3)

        ssh_buttons = QHBoxLayout()
        test_ssh_btn = QPushButton("测试 SSH 连接")
        save_ssh_btn = QPushButton("保存 SSH 配置")
        self.ssh_save_button = save_ssh_btn
        self.refresh_ssh_btn = QPushButton("刷新 G 文件列表")
        download_ssh_btn = QPushButton("下载所选 G 文件")
        test_ssh_btn.clicked.connect(self.test_ssh_connection)
        save_ssh_btn.clicked.connect(self.save_ssh_settings)
        self.refresh_ssh_btn.clicked.connect(self.refresh_remote_g_files)
        download_ssh_btn.clicked.connect(self.download_selected_remote_g_files)
        ssh_buttons.addWidget(test_ssh_btn)
        ssh_buttons.addWidget(save_ssh_btn)
        ssh_buttons.addWidget(self.refresh_ssh_btn)
        ssh_buttons.addWidget(download_ssh_btn)
        ssh_buttons.addStretch()
        ssh_grid.addLayout(ssh_buttons, len(ssh_fields), 1, 1, 3)

        self.ssh_connection_status = QLabel(
            "尚未测试 SSH/SFTP 连接。"
        )
        self.ssh_connection_status.setWordWrap(True)
        self.ssh_connection_status.setStyleSheet(
            "background:#F5F7F8; color:#53636C; "
            "border:1px solid #D7E0E4; border-radius:6px; "
            "padding:7px 10px;"
        )
        ssh_grid.addWidget(
            self.ssh_connection_status,
            len(ssh_fields) + 1,
            1,
            1,
            3,
        )

        remote_layout.addLayout(ssh_grid)

        self.ssh_readonly_notice = QLabel(
            "SSH 服务器只读：本工具仅允许列目录、读取属性和下载 G 文件；"
            "禁止上传、覆盖、重命名、删除或修改服务器上的任何文件。"
        )
        self.ssh_readonly_notice.setWordWrap(True)
        self.ssh_readonly_notice.setStyleSheet(
            "background:#E8F7F1; color:#006B52; "
            "border:1px solid #A9DCC8; border-radius:7px; "
            "padding:8px 10px; font-weight:600;"
        )
        remote_layout.addWidget(self.ssh_readonly_notice)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索 G 文件"))
        self.remote_search_edit = QLineEdit()
        self.remote_search_edit.setPlaceholderText(
            "例如：ABH-06、SAMR、JED-NTH"
        )
        self.remote_search_edit.textChanged.connect(
            self._schedule_remote_file_filter
        )
        search_row.addWidget(self.remote_search_edit, 1)
        self.remote_count_label = QLabel("尚未加载远程文件")
        search_row.addWidget(self.remote_count_label)
        remote_layout.addLayout(search_row)

        remote_actions = QHBoxLayout()
        select_visible_btn = QPushButton("全选当前结果")
        clear_remote_btn = QPushButton("清空选择和搜索")
        select_visible_btn.clicked.connect(
            lambda: self._set_visible_remote_selection(True)
        )
        clear_remote_btn.clicked.connect(self._clear_remote_selection)
        remote_actions.addWidget(select_visible_btn)
        remote_actions.addWidget(clear_remote_btn)
        remote_actions.addStretch()
        remote_layout.addLayout(remote_actions)

        self.remote_file_table = QTableWidget()
        self.remote_file_table.setColumnCount(4)
        self.remote_file_table.setHorizontalHeaderLabels(
            ["选择", "文件名", "大小", "服务器修改时间"]
        )
        self.remote_file_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.remote_file_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.remote_file_table.verticalHeader().setDefaultSectionSize(30)
        self.remote_file_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.remote_file_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self.remote_file_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,
        )
        self.remote_file_table.horizontalHeader().setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents,
        )
        self.remote_file_table.itemChanged.connect(
            self._on_remote_file_item_changed
        )
        self.remote_file_table.setMinimumHeight(210)
        remote_layout.addWidget(self.remote_file_table)
        remote_page.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        self.input_source_stack.addWidget(remote_page)

        grid.addWidget(self.input_source_stack, 2, 0, 1, 4)
        self.input_source_stack.setCurrentIndex(
            1 if saved_source == "SSH" else 0
        )
        QTimer.singleShot(
            0,
            self._update_input_source_stack_height,
        )

        self.workspace_status = QLabel("执行前需要进行 Oracle 预检查。")
        apply_status_style(self.workspace_status, False)
        grid.addWidget(self.workspace_status, 3, 0, 1, 4)

        safe_notice = QLabel(
            "安全说明：RMU 环网柜模型和馈线模型共用本地/SSH文件来源；"
            "本地原始 G 文件和 SSH 服务器文件均不修改。"
            "SSH 模式每次【模型校验】都会重新下载服务器当前最新稳定版本到 "
            "remote_input；同一次校验后的【执行模型关联】只使用该次快照，"
            "并仅修改 g_output 安全副本。"
        )
        safe_notice.setWordWrap(True)
        safe_notice.setStyleSheet(
            "background:#E8F7F1; color:#006B52; border:1px solid #A9DCC8; "
            "border-radius:7px; padding:8px 10px; font-weight:600;"
        )
        grid.addWidget(safe_notice, 4, 0, 1, 4)

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
        grid.addWidget(ws_holder, 5, 0, 1, 4)

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
        # 任务进度控件
        #
        # v4.1.33: keep the task progress visually attached to the Console
        # area instead of placing it above the (potentially tall) association
        # candidate table.  This is presentation/layout only; all validation,
        # association and write-back execution paths are unchanged.
        # --------------------------------------------------------
        self.progress_box = QGroupBox("任务进度")
        self.progress_box.setObjectName("progressBox")
        progress_layout = QVBoxLayout(self.progress_box)
        progress_layout.setContentsMargins(10, 10, 10, 8)
        progress_layout.setSpacing(5)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.progress_message = QLabel("等待执行任务")
        self.progress_message.setStyleSheet("color:#60756d;")
        self.progress_message.setWordWrap(True)

        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_message)

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
        self.open_change_log_btn = QPushButton("打开修改记录 CSV")
        self.open_report_dir_btn = QPushButton("打开本次运行目录")

        copy_log_btn.clicked.connect(self.copy_log)
        clear_log_btn.clicked.connect(lambda: self.log_edit.clear())
        self.open_html_btn.clicked.connect(lambda: self.open_artifact("html"))
        self.open_rmu_csv_btn.clicked.connect(lambda: self.open_artifact("rmu_csv"))
        self.open_device_csv_btn.clicked.connect(lambda: self.open_artifact("device_csv"))
        self.open_change_log_btn.clicked.connect(
            lambda: self.open_artifact("change_log_csv")
        )
        self.open_report_dir_btn.clicked.connect(self.open_current_run_dir)

        for button in (
            self.open_html_btn,
            self.open_rmu_csv_btn,
            self.open_device_csv_btn,
            self.open_change_log_btn,
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
        log_actions.addWidget(self.open_change_log_btn)
        log_actions.addWidget(self.open_report_dir_btn)
        log_layout.addLayout(log_actions)

        # Keep the animated task state immediately next to the Console so it
        # remains visible while the user watches live execution logs.
        log_layout.addWidget(self.progress_box)

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
        database_btn.clicked.connect(lambda: self.nav.setCurrentRow(2))

        for button in (
            self.validate_btn,
            self.apply_btn,
            database_btn,
        ):
            # Keep the compact Chinese baseline width, but allow longer
            # translated captions (for example "Apply Model Association")
            # to use their natural size instead of clipping characters.
            button.setMinimumWidth(168)
            button.setFixedHeight(42)

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

        if self.language == "en_US":
            if module_id == "FEEDER":
                return """
                <h2>Feeder Model Help</h2>
                <h3>1. Feeder Resolution</h3>
                <ol>
                  <li>Scan every main-network Bay feeder first and resolve each graph feeder to one 13500 / dms_feeder_device record.</li>
                  <li>For each FeedLine, reuse the Graphics Workspace topology rule: propagate from the main-network CBreaker through link/node_area and strict geometry repair, stopping only the branch that reaches a red NOP Y*/Q* switch.</li>
                  <li>Only a FeedLine with exactly one reachable feeder is eligible. CONFLICT / UNRESOLVED rows are blocked rather than guessed.</li>
                  <li>The resolved graph feeder must map uniquely to the database feeder; no cross-feeder fallback allocation is allowed.</li>
                </ol>
                <h3>2. Database Query / Create Boundary</h3>
                <ul>
                  <li>13500 / dms_feeder_device: read-only, used to identify the unique feeder.</li>
                  <li>405 / substation and 402 / voltagelevel + 401 / basevoltage: read-only, used to resolve the feeder substation and supported voltage level/BV_ID.</li>
                  <li>13503 / dms_section_device: the only writable table, and only missing feeder sections may be INSERTed.</li>
                  <li>No UPDATE / DELETE is performed on 13503, 13500, 405, or any other database table.</li>
                  <li>Existing feeder sections are reused and never duplicated.</li>
                  <li>New IDs are checked again before INSERT; batch creation uses one transaction and any error causes a full ROLLBACK.</li>
                </ul>
                <h3>3. FeedLine Allocation and Association</h3>
                <ul>
                  <li>An existing FeedLine association is preserved only when its 13503.FEEDER_ID equals that FeedLine's topology-resolved feeder. A Domain-only mismatch keeps the same 13503.ID and repairs only the KeyID Domain.</li>
                  <li>Unlinked/stale/wrong-feeder FeedLines reuse only unused 13503 rows under their own topology feeder. If that feeder is short, only that feeder receives the missing SECnnn rows. One drawing may therefore create sections under several feeders independently.</li>
                  <li>ls=2 → SECTION_TYPE=0; ls=1 → SECTION_TYPE=1; missing/empty ls → SECTION_TYPE=3.</li>
                  <li>After creation, 13503 is queried again and the final database ID / BV_ID is used to calculate Expected KeyID.</li>
                  <li>The existing LINK / RELINK and duplicate-association rules then continue normally.</li>
                </ul>
                <h3>4. Safe G-file Write-back</h3>
                <pre>
    app="6500000"
    p_ReportType="1"
    state="20"
    voltype="dms_section_device.BV_ID"
    keyid="Expected KeyID"
                </pre>
                <p><b>Only these five FeedLine attributes are changed.</b> key_name, ls, coordinates, colors, line style, and all other attributes remain unchanged.</p>
                """
            if module_id == "TRANSFORMER":
                return """
                <h2>Pole Transformer Model Help</h2>
                <ol>
                  <li>Only objects whose devref file name is listed in the operator-maintained pole-transformer element list are processed; Element Management classification is not used.</li>
                  <li>Name rules fully follow Jeddah: pure-numeric, white/default-white, no-background Text; 全局最近 priority; minimum rectangle-edge distance between transformer and Text ≤ 300; Text ownership is globally one-to-one.</li>
                  <li>Makkah does <b>not</b> resolve, require, or validate FEEDER_ID. The graphical name is queried only against 13505/dms_tr_device.NAME and must return exactly one row.</li>
                  <li>Expected KeyID uses 13505.ID with Domain 1. Only Workspace safe copies are written; original G files are unchanged.</li>
                </ol>
                """
            if module_id == "POLE_SWITCH":
                return """
                <h2>Pole Switch Model Help</h2>
                <ol>
                  <li>Only objects whose devref file name is listed in the operator-maintained pole-switch element list are processed. Every listed file is directly treated as a pole switch; users do not classify AR/LBS/SEC and Element Management classification is not used.</li>
                  <li>Makkah name rules are geometry-driven: valid Text is globally matched one-to-one by minimum rectangle-edge distance, maximum distance 200; obvious unit/decimal noise is excluded.</li>
                  <li>Before database lookup, ordinary names are normalized as before, while valid prefix+digits-digits business names keep their hyphen without requiring a configured device family.</li>
                  <li>Makkah does <b>not</b> resolve or validate FEEDER_ID. 13501 is matched by exact NAME only (no CODE fallback), then its 13502 child must also be unique. Multiple 13502 children block association instead of being disambiguated by AR/LBS/SEC.</li>
                  <li>Expected KeyID uses 13502.ID with Domain 40; write-back changes Workspace safe copies only.</li>
                </ol>
                """
            if module_id == "FUSE":
                return """
                <h2>Fuse Model Help</h2>
                <ol>
                  <li>Only graphic objects classified <b>FUSE</b> in Element Management are processed.</li>
                  <li>Each FUSE nominates only its nearest TRANSFORMER_OH. One transformer can be owned by only one FUSE; conflicts are won by the closer FUSE and losers do not fall back to a second transformer.</li>
                  <li>The assigned transformer name fully reuses the Jeddah transformer rule: pure numeric, white/no-background, 全局最近, max distance 300, globally one-to-one.</li>
                  <li>The fuse business NAME is FUSE + transformer name. Makkah does not validate FEEDER_ID: 13505.NAME and 13513.NAME must each be unique; uniqueness is enough to associate.</li>
                  <li>Expected KeyID uses 13513.ID with Domain 40; only Workspace safe copies are changed.</li>
                </ol>
                """
            return """
                <h2>Pole Switch Model Help</h2>
                <h3>1. Recognition Rules</h3>
                <ul>
                  <li>Only <b>CBreakerDis</b> objects whose element file is marked <b>LBS</b>, <b>SEC</b>, or <b>AR</b> in Element Management are included.</li>
                  <li>The element mark is mandatory; devref text, key_name, and p_NameString are not type-recognition sources.</li>
                  <li>Each eligible CBreakerDis independently takes its nearest valid Text. RMU, ConnectLine, node_area, and other topology are not analyzed by this module.</li>
                </ul>
                <h3>2. Database Chain</h3>
                <p>Graphical name → 13501 / dms_combined_device.NAME (if not found, CODE) → 13501.ID → 13502 / dms_cb_device.combined_id. The target device is 13502.ID and Domain is fixed at 40 for KeyID calculation.</p>
                <h3>3. Safe Write-back</h3>
                <pre>
    app="6500000"
    voltype="dms_cb_device.BV_ID"
    p_ReportType="1"
    state="41"
    keyid="Device ID + 40 * 2^32"
                </pre>
                <p>Only selected objects are written to Workspace safe copies; original G files are not modified.</p>
                """
            return """
            <h2>RMU Model Help</h2>
            <h3>1. RMU Recognition</h3>
            <ul>
              <li><b>Structural hard condition:</b> the rectangle must contain CBreakerDis, ZhaiWaiJieDiDaoZha, and BusDis (at least one of each).</li>
              <li><b>Text type:</b> Y1/Y2/Y3... each count as one L way; Q1/Q2/Q3... each count as one T way. Example: Y1, Y2, Q1 → <b>2L1T</b>.</li>
              <li><b>Dual-source type recognition:</b> Y*/Q* graphical text and CBreakerDis.devref template structure are calculated independently and cross-checked.</li>
              <li><b>devref names are not interpreted:</b> only CBreakerDis participates. Y devices must share one template, Q devices must share one template, and the Y/Q templates must differ. ZhaiWaiJieDiDaoZha (for example RMU_ES), BusDis, and all other objects are excluded.</li>
              <li>If text type and valid devref type disagree, the final RMU type uses the devref result and the report raises WARN.</li>
              <li><b>SMART/NORMAL:</b> SMART and SMR graphical markers are globally assigned to the nearest RMU. Any SMART/SMR marker makes the cabinet SMART; otherwise it is NORMAL.</li>
               <li>RMU name priority is fixed as <b>RIGHT → BOTTOM → GLOBAL fallback</b>, within the 300-unit hard limit.</li>
               <li>RMU names are external labels only: any Text whose centre lies inside a recognised RMU frame is excluded before all three stages. Names are then assigned one-to-one: RIGHT, BOTTOM, then GLOBAL fallback.</li>
              <li>Names are strings. Standard compact names are supported, plus the field form <b>number + space + suffix</b> such as <b>66 B</b>. Arbitrary descriptive text containing spaces is still rejected.</li>
            </ul>
            <h3>2. Device Naming Rules</h3>
            <ul>
              <li><b>CBreakerDis:</b> use only the graphical text spatially associated with the breaker inside the RMU. XML p_NameString is not a naming source.</li>
              <li><b>ZhaiWaiJieDiDaoZha:</b> pair uniquely with the nearest CBreakerDis; logical name = paired breaker graphical name + D.</li>
              <li><b>BusDis:</b> logical name is always <b>BUS</b>.</li>
              <li>The logical name must uniquely match database <b>CODE</b> inside the current RMU; NAME is not used.</li>
            </ul>
            <h3>3. Validation and Repair Principles</h3>
            <p><b>Core principle:</b> when current database facts are correct and uniquely identify a target, stale/incorrect G-file associations may be repaired. Processing is blocked only when database truth itself is ambiguous.</p>
            <ul>
              <li>The RMU database record must be unique.</li>
              <li>Device CODE must equal the current graphical logical name.</li>
              <li>For a unique RMU, each G device is validated independently and the target database device must belong to that RMU.</li>
              <li>Old device ID, table ID, Domain, or KeyID may be repaired when the current target is unique.</li>
              <li>If an old KeyID points to another RMU but the correct current-RMU device is uniquely determined, the row is marked RMU_RELINK and may be repaired.</li>
              <li>RMU validation does not perform feeder validation.</li>
            </ul>
            <h3>4. Safe RMU Write-back</h3>
            <p>CBreakerDis / ZhaiWaiJieDiDaoZha:</p>
            <pre>
    app="6500000"
    voltype="Database device BV_ID"
    p_ReportType="1"
    state="41"
    keyid="Expected KeyID"
            </pre>
            <p>BusDis:</p>
            <pre>
    app="6500000"
    voltype="Database device BV_ID"
    p_ReportType="1"
    state="15"
    keyid="Expected KeyID"
            </pre>
            <p>Original G files are never modified. Only safe Workspace copies are changed.</p>
            """

        if module_id == "TRANSFORMER":
            return """
            <h2>柱上变压器模型帮助</h2>
            <ol>
              <li>只识别【柱上变压器模型配置】中用户维护的 devref 图元文件名单；默认包含 <b>Transformer_OH.pb.icn.g</b>，不再读取【图元管理】TRANSFORMER_OH 分类。</li>
              <li>麦加名称规则：全图 Text 不限制颜色、背景、纯数字/字母/字母数字组合；纯小数直接排除。优先级为<b>上方 TOP → 右方 RIGHT → 全局 GLOBAL</b>；按设备矩形框与 Text 矩形框的最小边缘距离计算，最大距离 200；所有变压器与 Text 全局一对一分配。</li>
              <li>麦加<b>不识别、不要求、不校验 FEEDER_ID</b>。图上名称只按 13505/dms_tr_device.NAME 精确查询，唯一命中 1 条就直接作为目标，0 条或多条不自动关联。</li>
              <li>使用 13505.ID、Domain=1 计算并反解校验 Expected KeyID；只写 Workspace 安全副本。</li>
            </ol>
            """
        if module_id == "POLE_SWITCH":
            return """
            <h2>柱上开关模型帮助</h2>
            <ol>
              <li>只识别【柱上开关模型配置】中用户维护的 devref 图元文件名单；<b>只要加入名单就直接认定为柱上开关</b>，用户不再区分 AR / LBS / SEC，也不再读取【图元管理】分类。</li>
              <li>麦加名称规则：Text 不限制颜色、背景、纯数字/字母/字母数字组合；纯小数直接排除。按设备与 Text 的矩形最小边缘距离做全局一对一匹配，最大距离 200。</li>
              <li>数据库查询直接使用 G 文件中的柱上开关原始 Text 名称；不删除空格、横杠、点号，不做拼接、大小写转换或其他名称标准化。</li>
              <li>麦加<b>不识别、不要求、不校验 FEEDER_ID</b>。13501 只按 NAME 精确匹配，不使用 CODE 兜底；13501 必须唯一，其 13502 子设备也必须唯一。若 13502 有多条，直接阻断关联，不再按 AR/LBS/SEC 消歧。</li>
              <li>使用 13502.ID、Domain=40 计算 Expected KeyID，只写 Workspace 安全副本。</li>
            </ol>
            """
        if module_id == "FUSE":
            return """
            <h2>熔断器模型帮助</h2>
            <ol>
              <li>只识别【熔断器模型配置】中用户维护的 devref 图元文件名单；<b>只要加入名单就直接认定为熔断器</b>，不再读取【图元管理】FUSE 分类。</li>
              <li>每个 FUSE 只提名几何位置最近的 TRANSFORMER_OH；同一柱上变压器只能分配给一个 FUSE，冲突时距离更近者获得，失败者不再找第二近。</li>
              <li>获得柱上变压器后，名称复用麦加柱上变压器规则：不限制颜色、背景、纯数字/字母/字母数字组合，纯小数排除；全局最近，最大距离 200，全局一对一。</li>
              <li>熔断器业务名称固定为 FUSE+变压器名称。麦加<b>不识别、不要求、不校验 FEEDER_ID</b>：13505.NAME 必须唯一，派生后的 13513.NAME 也必须唯一；唯一即关联。</li>
              <li>使用 13513.ID、Domain=40 计算 Expected KeyID，只写 Workspace 安全副本。</li>
            </ol>
            """

        if module_id == "MASTER_STATION":
            return """
            <h2>配网主站设备关联帮助</h2>
            <h3>1. 强制识别</h3>
            <p>只扫描 Bus、CBreaker、Disconnector、GroundDisconnector 图元，不分析拓扑，也不从无关文字猜测设备。</p>
            <h3>2. 数据库匹配</h3>
            <p>先识别含 CBreaker 的最内层矩形框，只有这种框才作为主网 Bay 框。每个框只取附近最近的无背景合法馈线标题（例如 MNA4-12、ARF2-07），文字颜色不参与判断；标题超出安全距离或存在背景时不借用。标题拆分出变电站与馈线，在 405/13500 中确定唯一厂站和馈线，再在 406 中确定唯一 BAY_ID，并用 407 breaker 的 ST_ID/BAY_ID 进行交叉确认。确认 Bay 后，框内 CBreaker → 407、Disconnector → 408、GroundDisconnector → 409 继续按 BAY_ID 查询；Bus → 410/busbarsection 只检查已确认的变电站 ST_ID，不检查 BAY_ID。同站 410 记录作为候选池，已有正确 Bus 关联优先保留，其余 Bus 任意一对一取未使用记录。Disconnector/GroundDisconnector 多记录仍按 key_name CODE 消歧。不依赖 RMU 已有关联，也不分析全图拓扑。</p>
            <h3>3. 安全回写</h3>
            <p>只修改 Workspace 安全副本，不修改原始 G 文件。执行前会重新检查数据库和目标有效性，并且只有执行前目标仍与用户校验时确认的目标一致才允许写回。</p>
            <pre>
CBreaker: app=100000, voltype=数据库 BV_ID, p_ReportType=1, state=41, keyid=Expected KeyID
Disconnector: app=100000, voltype=数据库 BV_ID, p_ReportType=1, state=31, keyid=Expected KeyID
GroundDisconnector: app=100000, voltype=数据库 BV_ID, p_ReportType=1, state=31, keyid=Expected KeyID
Bus: app=100000, voltype=数据库 BV_ID, p_ReportType=1, state=10, keyid=Expected KeyID
            </pre>
            """

        if module_id == "FEEDER":
            return """
            <h2>馈线模型帮助</h2>

            <h3>1. 馈线确定方式</h3>
            <ol>
              <li>先扫描当前环网图全部主网 Bay 馈线，并通过 405/substation → 13500/dms_feeder_device 唯一确认每条图形馈线。</li>
              <li>每条 FeedLine 直接复用【图形工作区 → 馈线段所属馈线分析】规则：从主网 CBreaker 沿 link/node_area 与严格几何补链传播；遇红色 NOP 对应 Y*/Q* 开关时只停止该支路。</li>
              <li>只有唯一主网馈线可达时才继续。CONFLICT / UNRESOLVED 直接阻断，不按最近设备或其它馈线猜测。</li>
              <li>图形所属馈线还必须唯一映射到数据库 13500，之后该 FeedLine 的 13503 复用/创建都限定在自己的 FEEDER_ID 下。</li>
            </ol>

            <h3>2. 数据库查询与创建边界</h3>
            <ul>
              <li>13500 / dms_feeder_device：只查询，用于确认唯一馈线。</li>
              <li>405 / substation：只查询，通过 feeder.ST_ID 获取所属变电站。402 / voltagelevel + 401 / basevoltage：只查询该站 110/33/13.8kV 电压等级，存在多个时取最小值，并使用对应 voltagelevel.BV_ID 创建馈线段。</li>
              <li>13503 / dms_section_device：唯一允许写入的表，并且只允许 INSERT 缺失馈线段。</li>
              <li>不会 UPDATE / DELETE 13503，也不会写入 13500、405 或其它任何数据库表。</li>
              <li>已有同名馈线段直接使用，绝不重复创建。</li>
              <li>新 ID 在 INSERT 前必须再次检查是否已被占用；同批创建使用一个事务，任何异常全部 ROLLBACK。</li>
            </ul>

            <h3>3. FeedLine 创建与关联</h3>
            <ul>
              <li>已有 13503 只有在 FEEDER_ID 与该 FeedLine 的拓扑所属馈线一致时才保持；仅 Domain 错误时保留原 13503.ID 并修正 KeyID。</li>
              <li>未关联/失效/跨馈线关联只复用自己所属馈线下未占用的 13503；该馈线数量不足时，才在该馈线下按 SECnnn 规则新建。一个 G 图可以同时在多条馈线下分别创建。</li>
              <li>ls=2 → SECTION_TYPE=0；ls=1 → SECTION_TYPE=1；ls为空/不存在 → SECTION_TYPE=3。</li>
              <li>创建成功后重新查询 13503，再使用数据库最终 ID / BV_ID 计算 Expected KeyID。</li>
              <li>然后继续沿用原有 FeedLine 自动关联 / RELINK / 重复关联处理逻辑。</li>
            </ul>

            <h3>4. G 文件安全回写</h3>
            <pre>
    app="6500000"
    p_ReportType="1"
    state="20"
    voltype="dms_section_device.BV_ID"
    keyid="Expected KeyID"
            </pre>
                <p><b>FeedLine 只修改以上 5 个属性。</b>key_name、ls、坐标、颜色、线型等其它属性不修改。</p>
                """
            return """
        <h2>RMU 环网柜模型帮助</h2>

        <h3>1. 环网柜识别</h3>
        <ul>
          <li><b>结构硬条件：</b>矩形框内必须同时包含 CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 三类图元（每类至少 1 个），缺少任意一类不识别为 RMU。</li>
          <li><b>RMU 类型识别：</b>首先读取矩形框内部 Text。Y1/Y2/Y3/Y4… 每个计为 1 个 L，Q1/Q2/Q3/Q4… 每个计为 1 个 T，例如 Y1、Y2、Q1 → <b>2L1T</b>。编号按自然递增顺序展示。</li>
          <li><b>柜型双源识别：</b>柜内 Y*/Q* 文字与 CBreakerDis.devref 分别独立计算柜型；两者一致时正常通过交叉校验。</li>
          <li><b>devref 不解析现场图元名称含义：</b>柜型判断只统计 RMU 框内 CBreakerDis；Y1/Y2/Y3... 同类开关的 devref 必须使用同一个模板，Q1/Q2... 同类开关也必须使用同一个模板，同时存在 Y/Q 时两组模板必须不同。ZhaiWaiJieDiDaoZha（例如 RMU_ES）、BusDis 等其它图元完全不参与柜型统计。</li>
          <li>如果文字类型与 devref 类型不一致，报告中显示“类型交叉校验=NO”，最终“环网柜类型”采用 devref 类型；该差异本身不改变 RMU 数据库关联资格。</li>
          <li><b>智能环网柜识别：</b>在整张 G 图全局寻找 Text 中精确的 SMART 和 SMR，并把每个标识唯一归属给距离最近的 RMU。SMART 通常在柜内、SMR 可以在柜外，因此不设置最大距离限制。</li>
          <li>一个 RMU 只要命中 SMART 或 SMR 任意一种，报告“是否智能”列显示 <b>SMART</b>；未命中则显示 <b>NORMAL</b>。若两种标识都归属于同一个柜，“智能标识”仍记录 <b>SMART, SMR</b>。</li>
           <li>麦加现场环网柜名称只从 RMU 框外 Text 中寻找；Text 中心落在任意 RMU 框内时直接排除。其余固定按 <b>右侧 RIGHT → 下方 BOTTOM → 全局 GLOBAL 兜底</b> 的顺序识别；名称距离不得超过 300 G 单位。</li>
           <li>每个 RMU 只保留一个名称；数据库中必须唯一匹配一条同名环网柜记录；同一 Text 全局只归属距离最近的一个环网柜，避免名称重复使用。</li>
          <li>名称始终按照字符串处理，支持数字、字母、横线、下划线等常见工程名称。</li>
        </ul>

        <h3>2. 设备名称规则（固定）</h3>
        <ul>
          <li><b>CBreakerDis：</b>只使用环网柜内部、与开关图元空间对应的图上文字作为设备名称。XML <code>p_NameString</code> 完全不参与设备命名。</li>
          <li><b>ZhaiWaiJieDiDaoZha：</b>与 CBreakerDis 做最近唯一空间配对，逻辑设备名称=配对开关图上名称+D。</li>
          <li><b>BusDis：</b>逻辑设备名称固定为 <b>BUS</b>。</li>
          <li><b>Channel Status：</b>只识别已确定 RMU 框内 devref 含 <code>channel_status.zt.icn.g</code> 的 Status 图元；按当前 RMU ID 查询唯一 channel，目标表固定 13566、Domain 固定 40。</li>
          <li>上述普通设备逻辑名称必须与当前 RMU 下数据库设备 <b>CODE</b> 唯一对应；NAME 不参与判断；Channel Status 使用独立 channel 查询规则。</li>
          <li>开关图上文字无法唯一识别、数据库不存在相同 CODE 或同 CODE 存在多条记录时，报告会明确指出对应环网柜并提示检查开关命名方式。</li>
        </ul>

        <h3>2.1 RMU 柜型两套规则与交叉验证</h3>
        <ul>
          <li><b>规则一：</b>柜内 Y1/Y2/Y3/Y4… 每个计 1 个 L，Q1/Q2/Q3/Q4… 每个计 1 个 T，形成图内文字柜型。</li>
          <li><b>规则二：</b>只使用 CBreakerDis.devref 的模板结构判断：Y 类必须同模板、Q 类必须同模板、Y/Q 两组模板必须可区分；不识别 Load_Breaker、Circuit_Breaker、RMU_LBS、RMU_BRK 等任何现场关键字。</li>
          <li><b>全面验证：</b>当文字结果和 devref 结果同时存在时，两套结果必须进行交叉验证。</li>
          <li>若两套结果冲突，最终采用 <b>devref 柜型</b>，同时该 RMU 产生 WARN，并在 HTML / CSV / Console 中输出环网柜名称、文字柜型和 devref 柜型供检查。</li>
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
        dialog.setWindowTitle(f"{module_name} - {self._t("模型帮助")}")
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

    # ------------------------------------------------------------
    # Run history / audit
    # ------------------------------------------------------------
    def _build_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)

        layout.addWidget(
            self._page_header(
                "运行历史",
                "查看模型校验和模型关联的历史记录、报告、修改记录与运行目录。",
            )
        )

        actions = QHBoxLayout()
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_history_table)

        open_run_btn = QPushButton("打开运行目录")
        open_run_btn.clicked.connect(
            lambda: self._open_history_artifact("run_dir")
        )

        open_html_btn = QPushButton("打开 HTML")
        open_html_btn.clicked.connect(
            lambda: self._open_history_artifact("html")
        )

        open_change_btn = QPushButton("打开修改记录 CSV")
        open_change_btn.clicked.connect(
            lambda: self._open_history_artifact("change_log_csv")
        )

        actions.addWidget(refresh_btn)
        actions.addWidget(open_run_btn)
        actions.addWidget(open_html_btn)
        actions.addWidget(open_change_btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(9)
        self.history_table.setHorizontalHeaderLabels([
            "时间",
            "模型",
            "操作",
            "G 文件/输入",
            "选中",
            "成功",
            "跳过/失败",
            "结果",
            "运行目录",
        ])
        self.history_table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.history_table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.history_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.history_table.setAlternatingRowColors(True)
        self.history_table.verticalHeader().setDefaultSectionSize(30)
        self.history_table.verticalHeader().setMinimumSectionSize(30)
        self.history_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.doubleClicked.connect(
            lambda *_: self._open_history_artifact("run_dir")
        )
        layout.addWidget(self.history_table, 1)

        note = QLabel(
            "每次模型校验/模型关联都会在对应 run 目录写入 run_manifest.json。"
            "模型关联还会生成 model_change_log.csv，记录 XML 图元各属性修改前后的值。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        QTimer.singleShot(0, self.refresh_history_table)
        return page

    def _run_manifest_path(self, run_dir):
        return Path(run_dir) / "run_manifest.json"

    @staticmethod
    def _safe_int(value):
        try:
            return int(value or 0)
        except Exception:
            return 0

    def _write_run_manifest(
        self,
        *,
        operation,
        module_id,
        result="SUCCESS",
        summary=None,
        artifacts=None,
        input_path="",
        selected=0,
        applied=0,
        skipped=0,
        error="",
    ):
        run_dir = Path(
            (artifacts or {}).get("run_dir")
            or self.current_run_dir
            or ""
        )
        if not str(run_dir):
            return
        run_dir.mkdir(parents=True, exist_ok=True)

        previous = {}
        manifest_path = self._run_manifest_path(run_dir)
        if manifest_path.exists():
            try:
                previous = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except Exception:
                previous = {}

        events = list(previous.get("events", []) or [])
        event = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "module": str(module_id or ""),
            "operation": str(operation or ""),
            "result": str(result or ""),
            "input_path": str(input_path or ""),
            "source_info": dict(self.current_source_info or {}),
            "selected": self._safe_int(selected),
            "applied": self._safe_int(applied),
            "skipped": self._safe_int(skipped),
            "summary": dict(summary or {}),
            "artifacts": dict(artifacts or {}),
            "error": str(error or ""),
        }
        events.append(event)

        manifest = {
            "schema_version": 1,
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "run_dir": str(run_dir),
            "updated_at": event["time"],
            "events": events,
            "latest": event,
        }
        manifest_path.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    def _load_run_manifests(self):
        ensure_workspace()
        rows = []
        if not RUNS_ROOT.exists():
            return rows

        for run_dir in sorted(
            [p for p in RUNS_ROOT.iterdir() if p.is_dir()],
            key=lambda p: p.name,
            reverse=True,
        ):
            manifest_path = self._run_manifest_path(run_dir)
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            latest = dict(data.get("latest", {}) or {})
            latest["_manifest_path"] = str(manifest_path)
            latest["run_dir"] = str(run_dir)
            rows.append(latest)
        return rows

    def refresh_history_table(self):
        if not hasattr(self, "history_table"):
            return

        rows = self._load_run_manifests()
        self.history_table.setRowCount(len(rows))
        for row_idx, item in enumerate(rows):
            operation = str(item.get("operation", ""))
            operation_text = {
                "VALIDATE": self._t("模型校验"),
                "APPLY_ASSOCIATION": self._t("模型关联"),
            }.get(operation, operation)

            artifacts = dict(item.get("artifacts", {}) or {})
            values = [
                item.get("time", ""),
                item.get("module", ""),
                operation_text,
                item.get("input_path", ""),
                item.get("selected", 0),
                item.get("applied", 0),
                item.get("skipped", 0),
                item.get("result", ""),
                item.get("run_dir", ""),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setData(
                    Qt.UserRole,
                    {
                        "run_dir": item.get("run_dir", ""),
                        "html": artifacts.get("html", ""),
                        "change_log_csv": artifacts.get(
                            "change_log_csv",
                            "",
                        ),
                        "manifest": item.get("_manifest_path", ""),
                    },
                )
                self.history_table.setItem(row_idx, col, cell)

    def _selected_history_data(self):
        if not hasattr(self, "history_table"):
            return {}
        row = self.history_table.currentRow()
        if row < 0:
            return {}
        item = self.history_table.item(row, 0)
        return dict(item.data(Qt.UserRole) or {}) if item else {}

    def _open_history_artifact(self, key):
        data = self._selected_history_data()
        path_value = data.get(key, "")
        if not path_value:
            QMessageBox.information(
                self,
                "运行历史",
                "当前记录没有对应的文件或目录。",
            )
            return

        path = Path(path_value)
        if not path.exists():
            QMessageBox.warning(
                self,
                "运行历史",
                f"文件或目录不存在：\n{path}",
            )
            return

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.critical(
                self,
                "运行历史",
                str(exc),
            )

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

        central_box = QGroupBox("公共配置同步")
        central_layout = QVBoxLayout(central_box)
        central_layout.setContentsMargins(14, 18, 14, 14)
        central_cfg = dict(self.cfg.get("central_config", {}) or {})
        central_tip = QLabel(
            "软件启动只读取本机缓存，不会自动访问中央仓库。普通客户端可以修改并保存本机配置，也可以手动同步中央共享配置；"
            "只有上传/发布配置到中央仓库需要 Admin 权限。任何机器都可以手动抢占 Admin。"
            "当 Admin 被其他机器抢占后，本机仅后台检查很小的 instance.json 并自动降权；"
            "该检查不会同步数据库、服务器或图元配置。"
        )
        central_tip.setWordWrap(True)
        central_layout.addWidget(central_tip)
        central_grid = QGridLayout()
        self.central_edits = {}
        central_fields = [
            ("host", "中央服务器", central_cfg.get("host", "172.16.21.27")),
            ("port", "端口", central_cfg.get("port", 22)),
            ("username", "中央服务器用户名", central_cfg.get("username", "up8000")),
            ("password", "中央服务器密码", central_cfg.get("password", "up8000")),
            (
                "remote_directory",
                "中央配置目录",
                central_cfg.get(
                    "remote_directory",
                    "/home/up8000/nari-international/distribution-model-manager/config",
                ),
            ),
        ]
        for row, (key, label, value) in enumerate(central_fields):
            central_grid.addWidget(QLabel(label), row, 0)
            edit = QLineEdit(str(value))
            if key == "password":
                edit.setEchoMode(QLineEdit.Password)
            central_grid.addWidget(edit, row, 1)
            self.central_edits[key] = edit
        central_layout.addLayout(central_grid)
        central_actions = QHBoxLayout()
        self.central_save_local_button = QPushButton("保存本机连接配置")
        self.central_save_local_button.clicked.connect(self.save_central_connection_locally)
        self.central_sync_button = QPushButton("连接并同步中央配置")
        self.central_sync_button.clicked.connect(self.sync_central_configuration)
        self.central_publish_button = QPushButton("保存并发布全部配置")
        self.central_publish_button.clicked.connect(self.publish_current_configuration)
        self.central_init_button = QPushButton("抢占 Admin 权限")
        self.central_init_button.clicked.connect(self.takeover_central_configuration)
        self.central_release_button = QPushButton("释放 Admin 权限")
        self.central_release_button.clicked.connect(self.release_central_configuration)
        central_actions.addWidget(self.central_save_local_button)
        central_actions.addWidget(self.central_sync_button)
        central_actions.addWidget(self.central_publish_button)
        central_actions.addWidget(self.central_init_button)
        central_actions.addWidget(self.central_release_button)
        central_actions.addStretch()
        central_layout.addLayout(central_actions)
        self.central_status = QLabel()
        self.central_status.setWordWrap(True)
        central_layout.addWidget(self.central_status)
        self._refresh_central_status()
        layout.addWidget(central_box)

        language_box = QGroupBox("语言设置")
        language_layout = QGridLayout(language_box)
        language_layout.setContentsMargins(14, 18, 14, 14)
        language_layout.addWidget(QLabel("应用语言"), 0, 0)
        self.language_combo = NoWheelComboBox()
        self.language_combo.addItem("简体中文", "zh_CN")
        self.language_combo.addItem("英文", "en_US")
        lang_index = self.language_combo.findData(self.language)
        self.language_combo.setCurrentIndex(lang_index if lang_index >= 0 else 0)
        self.language_combo.setMinimumHeight(36)
        language_layout.addWidget(self.language_combo, 0, 1)
        language_tip = QLabel("语言切换立即生效，并自动保存最后一次选择。")
        language_tip.setWordWrap(True)
        language_layout.addWidget(language_tip, 1, 0, 1, 2)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(language_box)

        safety_box = QGroupBox("安全策略")
        safety_layout = QVBoxLayout(safety_box)

        text = QLabel(
            f"• 当前工作目录下自动生成的报告保留 {WORKSPACE_RETENTION_DAYS} 天\n"
            "• 每次执行任务前必须进行 Oracle 预检查\n"
            "• 模型回写必须先生成校验候选\n"
            "• 原始 G 文件不修改；关联前先复制到 Workspace 安全副本\n"
            "• 回写目标必须通过 G 图元类型 + XML ID 唯一定位\n"
            "• G 文件采用临时文件写入后原子替换\n"
            "• 文件与目录选择会自动记住上一次位置\n"
            "• SSH 文件服务器严格只读；每次模型校验重新下载当前最新版本，关联锁定该次快照"
        )
        text.setWordWrap(True)

        safety_layout.addWidget(text)
        layout.addWidget(safety_box)
        layout.addStretch()

        return page

    def _is_current_central_admin(self) -> bool:
        state = dict(self.cfg.get("_central_sync", {}) or {})
        if str(state.get("status") or "").upper() != "ACTIVE":
            return False
        if str(state.get("admin_machine_id") or "") != str(self.cfg.get("machine_id") or ""):
            return False
        remote_epoch = int(state.get("admin_epoch", 0) or 0)
        return self._admin_session_epoch is not None and remote_epoch == int(self._admin_session_epoch)

    def _adopt_admin_session_if_owner(self):
        state = dict(self.cfg.get("_central_sync", {}) or {})
        is_owner = (
            str(state.get("status") or "").upper() == "ACTIVE"
            and str(state.get("admin_machine_id") or "")
            == str(self.cfg.get("machine_id") or "")
        )
        self._admin_session_epoch = (
            int(state.get("admin_epoch", 0) or 0) if is_owner else None
        )

    def _apply_shared_configuration_permissions(self, is_admin: bool):
        """Keep all local configuration editable; gate only central publish."""
        for edit in getattr(self, "db_edits", {}).values():
            edit.setReadOnly(False)
        if hasattr(self, "db_save_button"):
            self.db_save_button.setEnabled(True)
        for edit in getattr(self, "ssh_edits", {}).values():
            edit.setReadOnly(False)
        if hasattr(self, "ssh_save_button"):
            self.ssh_save_button.setEnabled(True)
        element_page = getattr(self, "element_management_page", None)
        if element_page is not None and hasattr(element_page, "set_admin_mode"):
            element_page.set_admin_mode(is_admin)

    def _refresh_central_status(self):
        if not hasattr(self, "central_status"):
            return
        state = dict(self.cfg.get("_central_sync", {}) or {})
        status = str(state.get("status") or "UNKNOWN").upper()
        message = str(state.get("message") or "")
        is_current_admin = self._is_current_central_admin()

        if hasattr(self, "central_init_button"):
            self.central_init_button.setEnabled(status != "DISABLED" and not is_current_admin)
            self.central_init_button.setText(
                "当前机器已是 Admin" if is_current_admin else "抢占 Admin 权限"
            )
        if hasattr(self, "central_publish_button"):
            self.central_publish_button.setEnabled(is_current_admin)
        if hasattr(self, "central_release_button"):
            self.central_release_button.setEnabled(is_current_admin)
        self._apply_shared_configuration_permissions(is_current_admin)

        admin_name = str(state.get("admin_machine_name") or "").strip()
        admin_ip = str(state.get("admin_ip") or "").strip()
        admin_desc = " / ".join(value for value in (admin_name, admin_ip) if value)
        if not admin_desc:
            admin_desc = "未记录机器信息"
        labels = {
            "ACTIVE": (
                f"已连接中央配置；当前机器为 Admin（{admin_desc}）。"
                if is_current_admin
                else f"当前 Admin：{admin_desc}；本机为普通客户端，可修改并保存本机配置、同步中央配置，但不能发布中央仓库；可随时抢占 Admin。"
            ),
            "UNASSIGNED": "中央配置当前没有 Admin；任意客户端都可以抢占 Admin。",
            "UNINITIALIZED": "中央共享配置尚未初始化；请先抢占 Admin，再用本机配置发布。",
            "OFFLINE": "中央配置暂时不可用，将继续使用本机缓存。",
            "DISABLED": "中央配置同步已关闭。",
            "LOCAL_ONLY": "当前仅使用本机缓存；启动未访问中央仓库。本机配置可修改保存，可手动同步中央配置；发布中央仓库需要 Admin。",
            "UNKNOWN": "尚未读取中央配置；本机配置可修改保存，发布中央仓库需要 Admin。",
        }
        self.central_status.setText(
            f"状态：{labels.get(status, status)}"
            + (f"\n{message}" if message else "")
        )
        self.central_status.setStyleSheet(
            "color:#006B52;background:#EAF8F2;"
            "border:1px solid #B9DACD;border-radius:6px;padding:8px;"
            if status in {"ACTIVE", "UNASSIGNED"}
            else "color:#7A4B00;background:#FFF6DF;"
            "border:1px solid #E7C66A;border-radius:6px;padding:8px;"
        )

    def _schedule_central_admin_ownership_check(self):
        """Poll only instance.json while this app session is the current Admin."""
        if not self._is_current_central_admin():
            return
        worker = self._central_admin_check_worker
        if worker is not None and worker.isRunning():
            return
        worker = CentralAdminOwnershipWorker(dict(self.cfg), self)
        self._central_admin_check_worker = worker
        worker.checked.connect(self._on_central_admin_ownership_checked)
        worker.failed.connect(self._on_central_admin_ownership_check_failed)
        worker.finished.connect(self._clear_central_admin_check_worker)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _clear_central_admin_check_worker(self):
        self._central_admin_check_worker = None

    def _on_central_admin_ownership_check_failed(self, _message: str):
        # Temporary connectivity loss must not alter local configuration/role.
        return

    def _on_central_admin_ownership_checked(self, remote_state: dict):
        if not self._is_current_central_admin():
            return
        previous = dict(self.cfg.get("_central_sync", {}) or {})
        local_id = str(self.cfg.get("machine_id") or "")
        local_epoch = int(self._admin_session_epoch or 0)
        remote_id = str(remote_state.get("admin_machine_id") or "")
        remote_epoch = int(remote_state.get("admin_epoch", 0) or 0)
        still_owner = (
            str(remote_state.get("status") or "").upper() == "ACTIVE"
            and remote_id == local_id
            and remote_epoch == local_epoch
        )
        if still_owner:
            previous.update(remote_state)
            previous["message"] = "Admin 权限有效；后台仅检查所有权，未自动同步中央配置。"
            self.cfg["_central_sync"] = previous
            self._refresh_central_status()
            return

        self.cfg["_central_sync"] = dict(remote_state or {})
        self._admin_session_epoch = None
        self._refresh_central_status()
        admin_name = str(remote_state.get("admin_machine_name") or "").strip()
        admin_ip = str(remote_state.get("admin_ip") or "").strip()
        owner = " / ".join(x for x in (admin_name, admin_ip) if x) or "其他客户端"
        QMessageBox.information(
            self,
            "Admin 权限已释放",
            f"Admin 权限已被 {owner} 接管。当前程序已自动切换为普通客户端；本机配置仍可修改保存和同步，但不能发布到中央仓库。",
        )

    def _current_central_config(self) -> dict:
        cfg = {key: edit.text().strip() for key, edit in self.central_edits.items()}
        try:
            cfg["port"] = int(cfg.get("port") or 22)
        except Exception as exc:
            raise ValueError("中央服务器端口必须是整数。") from exc
        if not cfg.get("host"):
            raise ValueError("中央服务器地址不能为空。")
        if not cfg.get("username"):
            raise ValueError("中央服务器用户名不能为空。")
        if not cfg.get("remote_directory"):
            raise ValueError("中央配置目录不能为空。")
        cfg["enabled"] = True
        return cfg

    def _save_central_connection(self):
        self.cfg["central_config"] = self._current_central_config()

    def save_central_connection_locally(self):
        """Save only the central endpoint locally; do not connect to it."""
        try:
            self._save_central_connection()
            save_settings(self.cfg)
            self.statusBar().showMessage(
                self._rt("中央仓库连接配置已保存到本机；未访问服务器。"), 3500
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存中央仓库连接配置失败", str(exc))

    def sync_central_configuration(self):
        """Manually pull central shared settings and overwrite local cache."""
        try:
            self._save_central_connection()
            save_settings(self.cfg)
            sync_central_settings(self.cfg, raise_on_error=True)
            save_settings(self.cfg)
            self._adopt_admin_session_if_owner()
            self._refresh_shared_configuration_views()
            self._refresh_central_status()
            QMessageBox.information(
                self,
                "读取中央配置",
                "中央配置已手动同步，并已覆盖本机的图元标记、数据库和文件服务器缓存。",
            )
        except Exception as exc:
            self._refresh_central_status()
            QMessageBox.warning(self, "读取中央配置失败", str(exc))

    def _refresh_shared_configuration_views(self):
        db_cfg = dict(self.cfg.get("db", {}) or {})
        for key, edit in getattr(self, "db_edits", {}).items():
            edit.setText(str(db_cfg.get(key, "")))
        ssh_cfg = dict(self.cfg.get("ssh", {}) or {})
        for key, edit in getattr(self, "ssh_edits", {}).items():
            edit.setText(str(ssh_cfg.get(key, "")))
        element_page = getattr(self, "element_management_page", None)
        if element_page is not None and hasattr(element_page, "reload_local_cache"):
            element_page.reload_local_cache()

    def _collect_shared_configuration(self, *, save_local=True):
        if hasattr(self, "central_edits"):
            self._save_central_connection()
        if hasattr(self, "db_edits"):
            self.cfg["db"] = self.current_db_config()
        if hasattr(self, "ssh_edits"):
            self.cfg["ssh"] = self._current_ssh_config()
        element_page = getattr(self, "element_management_page", None)
        if element_page is not None:
            element_page._sync_rows_from_table()
            self.cfg["element_catalog"] = {
                "remote_directory": element_page.directory_edit.text().strip(),
                "records": [dict(row) for row in element_page.rows],
            }
        if save_local:
            save_settings(self.cfg)

    def publish_current_configuration(self):
        """Explicitly publish all current local shared settings."""
        try:
            self._collect_shared_configuration(save_local=False)
            version = publish_central_settings(self.cfg)
            save_settings(self.cfg)
            self._refresh_central_status()
            QMessageBox.information(
                self,
                "中央配置发布完成",
                f"图元标记、数据库和文件服务器配置已全部发布。\n中央配置版本：{version}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "中央配置发布失败", str(exc))

    def takeover_central_configuration(self):
        """Explicitly take over Admin ownership without syncing shared config."""
        state = dict(self.cfg.get("_central_sync", {}) or {})
        admin_name = str(state.get("admin_machine_name") or "").strip()
        admin_ip = str(state.get("admin_ip") or "").strip()
        current_owner = " / ".join(x for x in (admin_name, admin_ip) if x)
        detail = f"当前已知 Admin：{current_owner}。\n\n" if current_owner else ""
        answer = QMessageBox.question(
            self,
            "抢占 Admin 权限",
            detail
            + "抢占后，本机将立即获得共享配置的修改、保存和发布权限；"
            "原 Admin 程序检测到所有权变化后会自动降级。\n\n"
            "本操作只变更 Admin 所有权，不会自动同步或发布数据库、服务器、图元配置。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self._save_central_connection()
            save_settings(self.cfg)
            epoch = takeover_central_admin(self.cfg)
            self._admin_session_epoch = int(epoch)
            save_settings(self.cfg)
            self._refresh_central_status()
            QMessageBox.information(
                self,
                "Admin 抢占完成",
                "当前机器已成为 Admin。现在可以修改并保存本机共享配置，再按需点击【保存并发布全部配置】。"
                "\n本次抢占没有自动同步或发布任何中央业务配置。",
            )
        except Exception as exc:
            QMessageBox.warning(self, "抢占 Admin 失败", str(exc))

    def release_central_configuration(self):
        answer = QMessageBox.question(
            self,
            "释放 Admin 权限",
            "释放后当前机器不再拥有发布权限，其他机器可以重新申请成为 Admin。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            version = release_central_admin(self.cfg)
            self._admin_session_epoch = None
            save_settings(self.cfg)
            self._refresh_central_status()
            QMessageBox.information(
                self,
                "Admin 权限已释放",
                f"Admin 权限已释放，中央配置版本：{version}。",
            )
        except Exception as exc:
            QMessageBox.warning(self, "释放 Admin 失败", str(exc))

    def _on_language_changed(self, _index):
        if not hasattr(self, "language_combo"):
            return
        self.language = normalize_language(self.language_combo.currentData())
        self.cfg["language"] = self.language
        self._apply_language(save=True)

    def _apply_language(self, save=False):
        self.language = normalize_language(getattr(self, "language", "zh_CN"))
        self.cfg["language"] = self.language
        retranslate_qt_tree(self, self.language)

        if self.language == "en_US":
            self.setWindowTitle(
                f"{APP_NAME_EN} v{APP_VERSION} - Internal Team Edition · {APP_SITE_LABEL_EN}"
            )
            QApplication.setApplicationName(f"{APP_NAME_EN} - {APP_SITE_LABEL_EN}")
            QApplication.setApplicationDisplayName(
                f"{APP_NAME_EN} - {APP_SITE_LABEL_EN}"
            )
        else:
            self.setWindowTitle(
                f"{APP_NAME} v{APP_VERSION} - {APP_EDITION} · {APP_SITE_LABEL}"
            )
            QApplication.setApplicationName(f"{APP_NAME} - {APP_SITE_LABEL}")
            QApplication.setApplicationDisplayName(
                f"{APP_NAME} - {APP_SITE_LABEL}"
            )

        # Module names are presentation text only; module IDs remain stable.
        if hasattr(self, "module_combo"):
            labels = {
                "RMU": "RMU Model" if self.language == "en_US" else "RMU 环网柜模型",
                "FEEDER": "Feeder Model" if self.language == "en_US" else "馈线模型",
                "POLE_SWITCH": "Pole Switch Model" if self.language == "en_US" else "柱上开关模型",
                "TRANSFORMER": "Pole Transformer Model" if self.language == "en_US" else "柱上变压器模型",
                "FUSE": "Fuse Model" if self.language == "en_US" else "熔断器模型",
                "MASTER_STATION": "Master Station Device Association" if self.language == "en_US" else "配网主站设备关联",
            }
            for i in range(self.module_combo.count()):
                module_id = str(self.module_combo.itemData(i) or "").upper()
                if module_id in labels:
                    self.module_combo.setItemText(i, labels[module_id])

        # Header product/edition text is rebuilt explicitly because the version
        # label contains dynamic values and therefore cannot be translated by
        # an exact static dictionary key.
        if hasattr(self, "header_brand_label"):
            self.header_brand_label.setText(
                "NARI International Business Internal Tool"
                if self.language == "en_US"
                else "NARI国际业务部内部工具"
            )
        if hasattr(self, "header_title_label"):
            self.header_title_label.setText(
                APP_NAME_EN if self.language == "en_US" else APP_NAME
            )
        if hasattr(self, "header_subtitle_label"):
            self.header_subtitle_label.setText(
                "Distribution Model Manager · Model Validation · Validated Candidates · Safe Write-back"
                if self.language == "en_US"
                else f"{APP_NAME_EN} · 模型校验 · 校验候选 · 安全回写"
            )
        if hasattr(self, "header_version_label"):
            self.header_version_label.setText(
                f"Internal Team Edition · {APP_SITE_LABEL_EN}  |  v{APP_VERSION}"
                if self.language == "en_US"
                else f"{APP_EDITION} · {APP_SITE_LABEL}  |  v{APP_VERSION}"
            )
        if hasattr(self, "graphics_operation_combo"):
            for i in range(self.graphics_operation_combo.count()):
                operation_id = str(self.graphics_operation_combo.itemData(i) or "").upper()
                if operation_id == "POKE":
                    self.graphics_operation_combo.setItemText(
                        i,
                        "Poke Jump Processing"
                        if self.language == "en_US"
                        else "Poke 跳转处理",
                    )
        if hasattr(self, "about_text_label"):
            if self.language == "en_US":
                self.about_text_label.setText(
                    f"<b>{APP_NAME_EN}</b><br><br>"
                    f"Version: v{APP_VERSION}<br>"
                    f"Build date: {APP_BUILD_DATE}<br>"
                    "Edition: Internal Team Edition<br><br>"
                    "Purpose: distribution G-file model validation, RMU/feeder model association, and safe write-back.<br>"
                    "Data safety: original G files are never modified; association writes only Workspace safe copies; "
                    "feeder completion may only INSERT missing DMS_SECTION_DEVICE records and never UPDATE/DELETE existing devices; "
                    "run results, Console logs, and change records are retained in independent run directories."
                )
            else:
                self.about_text_label.setText(
                    f"<b>{APP_NAME}</b><br>"
                    f"{APP_NAME_EN}<br><br>"
                    f"版本：v{APP_VERSION}<br>"
                    f"构建日期：{APP_BUILD_DATE}<br>"
                    f"版本类型：{APP_EDITION}<br><br>"
                    "用途：配网 G 文件模型校验、RMU/馈线模型关联及安全回写。<br>"
                    "数据安全：原始 G 文件不修改；每次关联只写 Workspace 安全副本；"
                    "馈线自动补齐仅允许 INSERT 缺失 DMS_SECTION_DEVICE，禁止 UPDATE/DELETE；"
                    "运行结果、Console 日志和修改记录均保留在独立 run 目录。"
                )

        # Refresh dynamic presentation that is populated after widget creation.
        if hasattr(self, "history_table"):
            self.refresh_history_table()
        if hasattr(self, "module_widgets"):
            feeder_widget = self.module_widgets.get("FEEDER")
            if feeder_widget is not None and hasattr(feeder_widget, "set_facid_lock"):
                try:
                    feeder_widget.language = self.language
                    feeder_widget.set_facid_lock(
                        getattr(feeder_widget, "_facid_locked_value", "")
                    )
                except Exception:
                    pass
        if hasattr(self, "current_artifacts"):
            try:
                self._update_artifact_buttons()
            except Exception:
                pass

        if save:
            save_settings(self.cfg)
            self.log(
                "Language switched to English."
                if self.language == "en_US"
                else "语言已切换为简体中文。"
            )

    def _t(self, text):
        return tr(text, self.language)

    def _rt(self, text):
        return translate_runtime_text(text, self.language)

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
            "4. 点击底部【模型校验】执行校验，并生成 HTML / CSV 以及可关联清单。\n"
            "5. 在可关联清单中勾选需要处理的设备或 FeedLine，然后点击【执行模型关联】。\n"
            "6. 执行前会显示最终确认摘要；模型关联只修改 Workspace 中的安全副本，原始 G 文件不变。\n"
            "7. 关联完成后生成本次执行 HTML / CSV、model_change_log.csv，并写入【运行历史】。"
        )
        quick_text.setWordWrap(True)
        quick_layout.addWidget(quick_text)
        layout.addWidget(quick)

        rmu_naming = QGroupBox("环网柜名称识别规则")
        rmu_naming_layout = QVBoxLayout(rmu_naming)
        rmu_naming_text = QLabel(
            "• 环网柜只有在矩形框内同时存在 CBreakerDis、ZhaiWaiJieDiDaoZha、BusDis 三类图元时才识别为 RMU。\n"
            "• RMU 柜型：柜内 Y*/Q* 文字与 CBreakerDis.devref 模板结构独立计算并交叉验证；devref 不解析任何现场图元关键字，只检查 Y 类同模板、Q 类同模板且 Y/Q 模板可区分。有效 devref 与文字冲突时仍以 devref 为准，同时 WARN。\n"
             "• 麦加现场环网柜名称固定按 <b>右侧 RIGHT → 下方 BOTTOM → 全局 GLOBAL 兜底</b> 的顺序识别；名称距离不得超过 300 G 单位，超过 300 不参与计算。\n"
             "• 每个 RMU 只保留一个名称；数据库中必须唯一匹配一条同名环网柜记录；每个 Text 全局只分配给距离最近的一个环网柜。\n"
            "• RMU 名称颜色不参与判断：红色、绿色、白色或其它颜色均按相同几何与名称规则处理；实际名称读取 Text 的 ts 属性。\n"
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
            "• Channel Status：只识别当前 RMU 框内 channel_status.zt.icn.g 的 Status；按 RMU ID 查询唯一 channel，固定 table=13566 / domain=40。\n"
            "• 图上开关名称必须与当前 RMU 下数据库 CODE 唯一对应；失败时明确告警对应环网柜并提示检查命名方式。\n\n"
            "【RMU 柜型识别】\n"
            "• 第一套：柜内 Y1/Y2/Y3... 每个计 L；Q1/Q2/Q3... 每个计 T，形成文字柜型。\n"
            "• 第二套：只分析 CBreakerDis.devref 模板结构；Y 类同模板、Q 类同模板，且 Y/Q 模板必须不同。ZhaiWaiJieDiDaoZha/RMU_ES 等不参与，且不解析任何现场 devref 名称含义。\n"
            "• 两套结果都存在时必须交叉验证；冲突时最终采用 devref 柜型，同时产生 WARN 并指出具体环网柜。\n\n"
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
            "• 13566 / Channel Status：按 RMU ID 查询 dms_terminal_info → dms_channel_info，排除 DR channel，必须唯一；KeyID 使用 Domain=40 并二次校验。\n"
            "• 设备校验以 G 文件实际存在的图元为准，只查询这些图元最终需要的 CODE；Channel Status 使用独立 channel 查询。\n"
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
            "建议先执行【模型校验】，在可关联清单中确认 Expected KeyID 和待处理对象后再执行关联。\n"
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
            "• 每次模型校验和模型关联都会自动生成 HTML / CSV，并写入【运行历史】。\n"
            "• 模型关联额外生成 model_change_log.csv，逐项记录 XML ID、属性、修改前值和修改后值；Workspace 历史按软件保留策略自动清理。"
        )
        reports_text.setWordWrap(True)
        reports_layout.addWidget(reports_text)
        layout.addWidget(reports)


        feeder_help = QGroupBox("馈线模型规则")
        feeder_help_layout = QVBoxLayout(feeder_help)
        feeder_help_text = QLabel(
            "• 支持一个 G 文件内多条主网馈线；先扫描主网 Bay，再复用【馈线段所属馈线分析】为每条 FeedLine 计算唯一拓扑所属馈线。\n"
            "• 拓扑依据：主网 CBreaker、link/node_area、严格几何补链、红色 NOP 对应 Y*/Q* 支路级断点；CONFLICT / UNRESOLVED 不猜测。\n"
            "• 图形所属馈线必须通过 405/substation → 13500/dms_feeder_device 唯一映射到 FEEDER_ID。\n"
            "• 馈线主表：13500 / dms_feeder_device；馈线段表：13503 / dms_section_device；默认域号：1。\n"
            "• 已有关联只有在 13503.FEEDER_ID 与该 FeedLine 拓扑目标一致时才保持；仅 Domain 错误时保持原 13503.ID 并修正 KeyID。\n"
            "• 未关联/失效/跨馈线 FeedLine 只复用自己所属馈线下的空闲 13503；不足时也只在该馈线下创建实际缺少数量，不跨馈线分配。\n"
            "• 一个 G 图可以同时在多条所属馈线下分别创建 13503；执行阶段按 FEEDER_ID 分组处理。\n"
            "• FeedLine 回写安全副本：app=6500000, p_ReportType=1, state=20, voltype=dms_section_device.BV_ID, keyid=Expected KeyID。\n"
            "• 馈线模块拥有独立的【馈线汇总】和【馈线段明细】HTML / CSV 报告，不改变 RMU 模块已经取消馈线判断的规则。"
        )
        feeder_help_text.setWordWrap(True)
        feeder_help_layout.addWidget(feeder_help_text)
        layout.addWidget(feeder_help)

        ssh_help = QGroupBox("SSH 文件服务器（只读）")
        ssh_help_layout = QVBoxLayout(ssh_help)
        ssh_help_text = QLabel(
            "• SSH 模式只允许读取目录、读取文件属性和下载 G 文件；"
            "程序没有上传、覆盖、删除、重命名服务器文件的功能。\n"
            "• IP/主机、端口、用户名、密码和远程目录都可以自定义；点击【保存 SSH 配置】后写入本地 Workspace 配置，下次启动自动恢复最后一次保存值。\n"
            "• 点击【刷新 G 文件列表】只刷新浏览列表；搜索只在当前已加载列表中本地过滤。\n"
            "• RMU 环网柜模型与馈线模型使用完全相同的 SSH 文件源。"
            "无论当前模型类型是哪一个，每次点击【模型校验】都会重新从服务器下载"
            "当前勾选文件的最新版本，历史 remote_input 或本地缓存绝不会作为"
            "新一次校验输入。\n"
            "• 下载采用 stat-before → download → stat-after 稳定性检查；"
            "如果 size/mtime 在下载期间变化，会自动重新下载，最多 3 次。\n"
            "• 下载成功后写入本次 run/remote_input，并计算 SHA256；"
            "该快照即为本次模型校验的固定输入。\n"
            "• 同一次校验后的【执行模型关联】禁止再次从服务器下载。"
            "关联必须使用本次 remote_input 快照复制到 g_output 后修改，"
            "从而保证“校验哪个版本，就修改哪个版本”。\n"
            "• 若服务器文件后来发生变化，需要重新点击【模型校验】取得新的最新快照。"
        )
        ssh_help_text.setWordWrap(True)
        ssh_help_layout.addWidget(ssh_help_text)
        layout.addWidget(ssh_help)

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

        about = QGroupBox("关于 / 版本信息")
        about_layout = QVBoxLayout(about)
        about_text = QLabel(
            f"<b>{APP_NAME}</b><br>"
            f"{APP_NAME_EN}<br><br>"
            f"版本：v{APP_VERSION}<br>"
            f"构建日期：{APP_BUILD_DATE}<br>"
            f"版本类型：{APP_EDITION}<br><br>"
            "用途：配网 G 文件模型校验、RMU/馈线模型关联及安全回写。<br>"
            "数据安全：原始 G 文件不修改；每次关联只写 Workspace 安全副本；"
            "馈线自动补齐仅允许 INSERT 缺失 DMS_SECTION_DEVICE，禁止 UPDATE/DELETE；"
            "运行结果、Console 日志和修改记录均保留在独立 run 目录。"
        )
        about_text.setWordWrap(True)
        about_text.setTextFormat(Qt.RichText)
        self.about_text_label = about_text
        about_layout.addWidget(about_text)
        layout.addWidget(about)

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

        # 与吉达 v4.1.96 保持一致：不冻结 QStackedWidget 重绘。
        # 先解除上一模块写入的固定高度，再直接切换当前页；
        # currentChanged 会立即针对新页做一次高度计算，事件循环结束后
        # 再校准一次 WordWrap/DPI 的最终 sizeHint。
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

        # 文件来源属于模型工作区公共能力。RMU 与 FEEDER 共用完全相同的
        # LOCAL / SSH 只读输入源，不因模型类型切换而隐藏或重建。
        if hasattr(self, "input_source_stack"):
            QTimer.singleShot(
                0,
                self._update_input_source_stack_height,
            )
        if (
            hasattr(self, "input_source_combo")
            and self._current_input_source() == "SSH"
        ):
            self.workspace_status.setText(self._rt(
                "SSH只读模式：RMU/馈线模型校验都会重新下载服务器当前最新 G 文件。"
            ))
            apply_status_style(self.workspace_status, False)

        # 等 Qt 完成本次 stacked page 切换后，再计算新页面最终高度。
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

        self.workspace_status.setText(self._t("请选择下方具体任务按钮执行。"))
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
        elif report_kind == "POLE_SWITCH":
            labels = {
                "validation": (
                    "打开校验 HTML",
                    "打开校验柱上开关 CSV",
                    "",
                ),
                "preview": (
                    "打开预览 HTML",
                    "打开预览柱上开关 CSV",
                    "",
                ),
                "association": (
                    "打开关联结果 HTML",
                    "打开关联结果柱上开关 CSV",
                    "",
                ),
            }
        elif report_kind == "TRANSFORMER":
            labels = {
                "validation": (
                    "打开校验 HTML",
                    "打开校验柱上变压器 CSV",
                    "",
                ),
                "preview": (
                    "打开预览 HTML",
                    "打开预览柱上变压器 CSV",
                    "",
                ),
                "association": (
                    "打开关联结果 HTML",
                    "打开关联结果柱上变压器 CSV",
                    "",
                ),
            }
        elif report_kind == "FUSE":
            labels = {
                "validation": ("打开校验 HTML", "打开校验熔断器 CSV", ""),
                "preview": ("打开预览 HTML", "打开预览熔断器 CSV", ""),
                "association": ("打开关联结果 HTML", "打开关联结果熔断器 CSV", ""),
            }
        elif report_kind == "MASTER_STATION":
            labels = {
                "validation": ("打开校验 HTML", "打开校验配网主站设备 CSV", ""),
                "preview": ("打开预览 HTML", "打开预览配网主站设备 CSV", ""),
                "association": ("打开关联结果 HTML", "打开关联结果配网主站设备 CSV", ""),
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
        self.open_html_btn.setText(self._t(html_text))
        self.open_rmu_csv_btn.setText(self._t(first_csv_text))
        self.open_device_csv_btn.setText(self._t(second_csv_text))

        self.open_change_log_btn.setText(self._t("打开修改记录 CSV"))

        for key, button in (
            ("html", self.open_html_btn),
            ("rmu_csv", self.open_rmu_csv_btn),
            ("device_csv", self.open_device_csv_btn),
            ("change_log_csv", self.open_change_log_btn),
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
            self.log_edit.appendPlainText(translate_runtime_text(text, self.language))
            scrollbar = self.log_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())


    def db_log(self, text):
        message = translate_runtime_text(text, self.language)
        if hasattr(self, "db_log_edit"):
            self.db_log_edit.appendPlainText(message)
            scrollbar = self.db_log_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        try:
            append_database_log(message)
        except Exception:
            pass

    def _check_saved_input_path_on_startup(self):
        if str(self.cfg.get("input_source", "LOCAL")).upper() == "SSH":
            return
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
            self.statusBar().showMessage(self._rt("数据库配置已保存。"), 3000)
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

            self.db_status.setText(self._t("数据库连接正常"))
            self.db_status.show()
            apply_status_style(self.db_status, True)
            QTimer.singleShot(3500, self.db_status.hide)

            self.db_log(message)
            self.statusBar().showMessage(self._rt("Oracle 数据库连接验证通过。"), 3500)

        except Exception as exc:
            self.db_status.setText(self._t("数据库连接失败"))
            self.db_status.show()
            apply_status_style(self.db_status, False)

            self.db_log(f"Oracle 数据库连接失败：{exc}")
            QMessageBox.critical(
                self,
                "Oracle 数据库连接失败",
                str(exc),
            )


    # ------------------------------------------------------------
    # Input source: local / SSH read-only
    # ------------------------------------------------------------
    def _current_input_source(self) -> str:
        if not hasattr(self, "input_source_combo"):
            return "LOCAL"
        return str(
            self.input_source_combo.currentData() or "LOCAL"
        ).upper()

    def _current_ssh_config(self) -> dict:
        cfg = {
            key: edit.text().strip()
            for key, edit in self.ssh_edits.items()
        }
        try:
            cfg["port"] = int(cfg.get("port") or 22)
        except Exception as exc:
            raise ValueError("SSH 端口必须是整数。") from exc

        if not 1 <= cfg["port"] <= 65535:
            raise ValueError("SSH 端口必须在 1~65535 之间。")
        if not cfg.get("host"):
            raise ValueError("SSH IP / 主机不能为空。")
        if not cfg.get("username"):
            raise ValueError("SSH 用户名不能为空。")
        if not cfg.get("remote_directory"):
            raise ValueError("SSH 远程目录不能为空。")
        return cfg

    def save_ssh_settings(self):
        """Persist the current SSH/SFTP read-only source configuration.

        This mirrors the database module's explicit save action.  The password
        is stored in the same workspace config JSON used by the existing
        database settings so the last user-entered values are restored on the
        next application launch.
        """
        try:
            cfg = self._current_ssh_config()
            self.cfg["ssh"] = cfg
            if hasattr(self, "element_management_page"):
                self.element_management_page.refresh_server_info()
            self.cfg["input_source"] = "SSH"
            save_settings(self.cfg)
            self._set_ssh_connection_status(
                "SSH 配置已保存；下次启动将自动恢复最后一次保存的输入。",
                "success",
            )
            self.statusBar().showMessage(self._rt("SSH 配置已保存。"), 3000)
        except Exception as exc:
            QMessageBox.critical(self, "SSH 配置", str(exc))

    def _save_input_source_settings(self):
        self.cfg["input_source"] = self._current_input_source()
        if hasattr(self, "ssh_edits"):
            self.cfg["ssh"] = self._current_ssh_config()
        save_settings(self.cfg)

    def _current_input_description(self) -> str:
        if self._current_input_source() == "SSH":
            source = dict(self.current_source_info or {})
            if (
                source.get("source_type") == "SSH"
                and self.current_snapshot_files
            ):
                host = source.get("host", "")
                port = source.get("port", 22)
                username = source.get("username", "")
                directory = source.get("remote_directory", "")
                count = len(source.get("files", []) or [])
                return (
                    f"ssh://{username}@{host}:{port}{directory}"
                    f" [{count} files]"
                )

            cfg = self._current_ssh_config()
            selected = sorted(self.remote_selected_names)
            suffix = (
                f" [{len(selected)} files]"
                if selected
                else ""
            )
            return (
                f"ssh://{cfg['username']}@{cfg['host']}:{cfg['port']}"
                f"{cfg['remote_directory']}{suffix}"
            )
        return self.input_edit.text().strip()

    def _invalidate_validation_snapshot(self, reason=""):
        if self.current_preview is None:
            return
        self.current_preview = None
        self.current_snapshot_files = []
        self.current_source_info = {}
        self.apply_btn.setEnabled(False)
        self._clear_association_table()
        if reason:
            self.workspace_status.show()
            self.workspace_status.setText(self._rt(
                f"输入已变化，请重新执行模型校验：{reason}"
            ))
            apply_status_style(self.workspace_status, False)

    def _on_input_source_changed(self, *_args):
        source = self._current_input_source()
        target_index = 1 if source == "SSH" else 0
        self.input_source_stack.setCurrentIndex(target_index)
        self._update_input_source_stack_height()

        self._save_input_source_settings()
        self._invalidate_validation_snapshot("文件来源已切换")
        if source == "SSH":
            self._set_ssh_connection_status(
                "SSH只读模式：请先测试连接或刷新 G 文件列表。",
                "neutral",
            )
            self.workspace_status.setText(self._t(
                "SSH模式：请选择远程 G 文件后执行模型校验。"
            ))
        else:
            self.workspace_status.setText(self._t(
                "本地模式：请选择 G 文件或目录。"
            ))
        apply_status_style(self.workspace_status, False)

    def _update_input_source_stack_height(self):
        """Only reserve the height needed by the currently visible source page."""
        if not hasattr(self, "input_source_stack"):
            return

        widget = self.input_source_stack.currentWidget()
        if widget is None:
            return

        if widget.layout() is not None:
            widget.layout().invalidate()
            widget.layout().activate()

        widget.updateGeometry()
        height = max(
            46,
            int(widget.sizeHint().height()),
        )

        # Local mode should remain as compact as the old single-row design.
        if self._current_input_source() == "LOCAL":
            height = min(height, 58)

        self.input_source_stack.setMinimumHeight(height)
        self.input_source_stack.setMaximumHeight(height)
        self.input_source_stack.updateGeometry()

    @staticmethod
    def _format_file_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024.0 or unit == "GB":
                return (
                    f"{value:.0f} {unit}"
                    if unit == "B"
                    else f"{value:.1f} {unit}"
                )
            value /= 1024.0
        return f"{size} B"

    def _set_ssh_connection_status(
        self,
        text: str,
        state: str = "neutral",
    ):
        if not hasattr(self, "ssh_connection_status"):
            return

        styles = {
            "success": (
                "background:#E8F7F1; color:#006B52; "
                "border:1px solid #A9DCC8;"
            ),
            "error": (
                "background:#FDECEC; color:#B42318; "
                "border:1px solid #F3B7B2;"
            ),
            "working": (
                "background:#FFF7E6; color:#8A5A00; "
                "border:1px solid #F1D59B;"
            ),
            "neutral": (
                "background:#F5F7F8; color:#53636C; "
                "border:1px solid #D7E0E4;"
            ),
        }
        style = (
            styles.get(state, styles["neutral"])
            + "border-radius:6px; padding:7px 10px;"
        )
        self.ssh_connection_status.setText(self._rt(text))
        self.ssh_connection_status.setStyleSheet(style)
        if hasattr(self, "poke_ssh_connection_status"):
            self.poke_ssh_connection_status.setText(self._rt(text))
            self.poke_ssh_connection_status.setStyleSheet(style)

    def test_ssh_connection(self):
        try:
            cfg = self._current_ssh_config()
            self._set_ssh_connection_status(
                "正在测试 SSH/SFTP 只读连接……",
                "working",
            )
            QApplication.processEvents()

            with ReadOnlySshClient(
                cfg["host"],
                cfg["port"],
                cfg["username"],
                cfg["password"],
            ) as client:
                client.test_connection()

            self.cfg["ssh"] = cfg
            if hasattr(self, "element_management_page"):
                self.element_management_page.refresh_server_info()
            self.cfg["input_source"] = "SSH"
            save_settings(self.cfg)
            self._set_ssh_connection_status(
                "SSH/SFTP 连接正常；远程文件源为只读。",
                "success",
            )
            self.log(
                f"SSH连接通过：{cfg['host']}:{cfg['port']} | "
                f"user={cfg['username']} | 只读模式"
            )
        except Exception as exc:
            self._set_ssh_connection_status(
                f"SSH/SFTP 连接失败：{exc}",
                "error",
            )
            QMessageBox.critical(
                self,
                "SSH 连接失败",
                str(exc),
            )

    def refresh_remote_g_files(self):
        """Refresh the remote directory in a worker thread.

        v4.1.31: SSH connect/open_sftp/listdir_attr used to run synchronously on
        the GUI thread. A slow server therefore made Windows mark the whole
        application as "Not Responding". The read-only SSH logic and returned
        file rows are unchanged; only the I/O scheduling moved to QThread.
        """
        if self.remote_list_worker is not None and self.remote_list_worker.isRunning():
            self._set_ssh_connection_status(
                "SSH/SFTP 正在后台读取远程 G 文件列表，请稍候……",
                "working",
            )
            return

        try:
            cfg = self._current_ssh_config()
        except Exception as exc:
            self._set_ssh_connection_status(
                f"读取远程 G 文件列表失败：{exc}",
                "error",
            )
            QMessageBox.critical(
                self,
                "读取远程 G 文件失败",
                str(exc),
            )
            return

        self._set_ssh_connection_status(
            "SSH/SFTP 正在后台连接并读取远程 G 文件列表……",
            "working",
        )
        self.refresh_ssh_btn.setEnabled(False)
        if hasattr(self, "poke_refresh_ssh_btn"):
            self.poke_refresh_ssh_btn.setEnabled(False)
        self._remote_refresh_started_at = datetime.now()
        self._remote_refresh_timer.start()

        worker = RemoteGFileListWorker(cfg)
        self.remote_list_worker = worker
        worker.completed.connect(
            lambda rows, cfg=dict(cfg): self._on_remote_g_files_loaded(rows, cfg)
        )
        worker.failed.connect(self._on_remote_g_files_failed)
        worker.finished.connect(self._on_remote_g_file_worker_finished)
        worker.start()

    def _update_remote_refresh_wait_status(self):
        worker = self.remote_list_worker
        started = self._remote_refresh_started_at
        if worker is None or not worker.isRunning() or started is None:
            return
        seconds = max(0, int((datetime.now() - started).total_seconds()))
        if self.language == "en_US":
            message = (
                "SSH/SFTP is reading the remote G-file list in the background; "
                f"elapsed {seconds}s. The application remains responsive."
            )
        else:
            message = (
                "SSH/SFTP 正在后台读取远程 G 文件列表；"
                f"已等待 {seconds} 秒。界面仍可正常操作。"
            )
        self._set_ssh_connection_status(message, "working")

    @staticmethod
    def _remote_rows_signature(rows):
        """Return the visible remote-file metadata signature.

        Refresh still asks the server for one read-only directory listing so a
        changed file can be detected safely.  When name/size/mtime are exactly
        unchanged, the GUI table is reused instead of creating thousands of
        QTableWidgetItem objects again.
        """
        return tuple(
            (item.name, int(item.size), int(item.mtime_epoch))
            for item in rows
        )

    def _on_remote_g_files_loaded(self, rows, cfg):
        try:
            endpoint_signature = (
                cfg["host"],
                int(cfg["port"]),
                cfg["username"],
                cfg["remote_directory"],
            )
            same_endpoint = self.remote_list_signature == endpoint_signature
            same_files = (
                same_endpoint
                and bool(self.remote_file_rows)
                and self._remote_rows_signature(self.remote_file_rows)
                == self._remote_rows_signature(rows)
            )

            current_names = {item.name for item in rows}
            self.remote_selected_names.intersection_update(current_names)
            self.remote_list_signature = endpoint_signature
            self.cfg["ssh"] = cfg
            self.cfg["input_source"] = "SSH"
            save_settings(self.cfg)

            if same_files:
                # Important fast path: the server was checked, but nothing in
                # the loaded G-file metadata changed. Reuse the existing rows,
                # selection, search visibility, validation snapshot and large
                # association table exactly as-is.
                if self.language == "en_US":
                    status = (
                        "SSH/SFTP refresh completed; no remote G-file changes "
                        f"detected. Reused the existing {len(rows)}-file list."
                    )
                    log_text = (
                        f"SSH remote directory unchanged: {cfg['remote_directory']} | "
                        f"*.g={len(rows)}; table rebuild skipped"
                    )
                else:
                    status = (
                        "SSH/SFTP 刷新完成；远程 G 文件没有变化。"
                        f" 已复用当前 {len(rows)} 个文件列表。"
                    )
                    log_text = (
                        f"SSH远程目录无变化：{cfg['remote_directory']} | "
                        f"*.g={len(rows)}；已跳过表格重建"
                    )
                self._set_ssh_connection_status(status, "success")
                self.log(log_text)
                self._update_remote_count_label()
                self._update_poke_remote_count_label()
                self._sync_poke_remote_checks_from_state()
                return

            self._set_ssh_connection_status(
                f"远程目录读取完成；检测到变化，正在更新 {len(rows)} 个 G 文件到列表……",
                "working",
            )
            QApplication.processEvents()

            self.remote_file_rows = rows

            # Only a genuinely changed remote list reaches this expensive UI
            # path. _rebuild_remote_file_table() also suppresses continuous
            # header ResizeToContents work while the 2k+ rows are populated.
            self._rebuild_remote_file_table()
            self._apply_remote_file_filter(self.remote_search_edit.text())
            self._mark_poke_remote_table_dirty()
            self._invalidate_validation_snapshot("远程 G 文件列表已变化")
            self._set_ssh_connection_status(
                f"SSH/SFTP 连接正常；远程文件源为只读。"
                f" 已加载 {len(rows)} 个 .g 文件。",
                "success",
            )
            self.log(
                f"SSH远程目录：{cfg['remote_directory']} | "
                f"*.g={len(rows)}；已排除 .g.h/.g.data/.g.png"
            )
        except Exception as exc:
            self._on_remote_g_files_failed(str(exc))

    def _on_remote_g_files_failed(self, message):
        self._set_ssh_connection_status(
            f"读取远程 G 文件列表失败：{message}",
            "error",
        )
        QMessageBox.critical(
            self,
            "读取远程 G 文件失败",
            str(message),
        )

    def _on_remote_g_file_worker_finished(self):
        self._remote_refresh_timer.stop()
        self._remote_refresh_started_at = None
        self.refresh_ssh_btn.setEnabled(True)
        if hasattr(self, "poke_refresh_ssh_btn"):
            self.poke_refresh_ssh_btn.setEnabled(True)
        worker = self.remote_list_worker
        self.remote_list_worker = None
        if worker is not None:
            worker.deleteLater()

    def download_selected_remote_g_files(self):
        selected=self._selected_remote_files()
        if not selected:
            QMessageBox.information(self,"下载所选 G 文件","请先勾选至少一个远程 G 文件。"); return
        destination=QFileDialog.getExistingDirectory(self,"选择 G 文件下载目录",self._existing_start_path(self.cfg.get("last_folder_path",""),str(Path.home())))
        if not destination:return
        cfg=self._current_ssh_config(); destination=Path(destination); success=0; failed=[]
        try:
            with ReadOnlySshClient(cfg["host"],cfg["port"],cfg["username"],cfg["password"]) as client:
                for item in selected:
                    try:
                        latest=client.stat_file(item.remote_path)
                        client.download_file(latest.remote_path,str(destination/latest.name))
                        success+=1
                    except Exception as exc: failed.append((item.name,str(exc)))
            self.cfg["last_folder_path"]=str(destination); save_settings(self.cfg)
            QMessageBox.information(self,"G 文件下载完成",f"成功 {success} 个，失败 {len(failed)} 个。\n保存目录：{destination}")
        except Exception as exc:
            QMessageBox.critical(self,"下载远程 G 文件失败",str(exc))

    def _schedule_remote_file_filter(self, _text=""):
        """Debounce remote-file filtering so fast typing never rebuilds UI work."""
        self._remote_filter_timer.start()

    def _run_remote_file_filter(self):
        self._apply_remote_file_filter(self.remote_search_edit.text())

    def _rebuild_remote_file_table(self):
        """Build remote rows once after an SSH directory refresh.

        Search/reset operations only hide/show these existing rows. This avoids
        recreating thousands of QTableWidgetItem objects on the GUI thread.
        """
        table = self.remote_file_table
        header = table.horizontalHeader()
        self._remote_table_populating = True
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            # QHeaderView.ResizeToContents is expensive while thousands of
            # items are inserted because Qt may repeatedly recalculate size
            # hints. Temporarily make every column non-auto-resizing, populate
            # once, then calculate content widths once at the end (the same
            # pattern used by GFileStudio's fast remote-file table refresh).
            for column in range(table.columnCount()):
                header.setSectionResizeMode(column, QHeaderView.Interactive)

            table.clearContents()
            table.setRowCount(len(self.remote_file_rows))
            self._remote_row_by_name = {}
            for row_index, remote_file in enumerate(self.remote_file_rows):
                self._remote_row_by_name[remote_file.name] = row_index

                check = QTableWidgetItem()
                check.setFlags(
                    Qt.ItemIsEnabled
                    | Qt.ItemIsSelectable
                    | Qt.ItemIsUserCheckable
                )
                check.setCheckState(
                    Qt.Checked
                    if remote_file.name in self.remote_selected_names
                    else Qt.Unchecked
                )
                check.setData(Qt.UserRole, remote_file.name)
                table.setItem(row_index, 0, check)

                values = [
                    remote_file.name,
                    self._format_file_size(remote_file.size),
                    remote_file.mtime_text,
                ]
                for column, value in enumerate(values, start=1):
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    table.setItem(row_index, column, item)

            # One content-width calculation after all rows exist. The file-name
            # column then stretches to use the remaining space; the other
            # columns retain their calculated widths without continuous
            # ResizeToContents recalculation during later refreshes.
            table.resizeColumnsToContents()
            header.setSectionResizeMode(1, QHeaderView.Stretch)
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)
            self._remote_table_populating = False

        self._remote_visible_count = len(self.remote_file_rows)

    def _apply_remote_file_filter(self, text=""):
        """Filter by row visibility; never recreate table items."""
        query = str(text or "").strip().lower()
        table = self.remote_file_table
        visible_count = 0

        table.setUpdatesEnabled(False)
        try:
            for row_index, remote_file in enumerate(self.remote_file_rows):
                matched = not query or query in remote_file.name.lower()
                table.setRowHidden(row_index, not matched)
                if matched:
                    visible_count += 1
        finally:
            table.setUpdatesEnabled(True)

        self._remote_visible_count = visible_count
        table.viewport().update()
        self._update_remote_count_label()

    def _update_remote_count_label(self):
        visible_count = self._remote_visible_count
        self.remote_count_label.setText(
            (f"Total {len(self.remote_file_rows)} | Visible {visible_count} | Selected {len(self.remote_selected_names)}")
            if self.language == "en_US" else
            (f"总数 {len(self.remote_file_rows)} | 当前显示 {visible_count} | 已选择 {len(self.remote_selected_names)}")
        )

    def _on_remote_file_item_changed(self, item):
        if self._remote_table_populating or item.column() != 0:
            return
        name = str(item.data(Qt.UserRole) or "")
        if not name:
            return
        if item.checkState() == Qt.Checked:
            self.remote_selected_names.add(name)
        else:
            self.remote_selected_names.discard(name)
        self._update_remote_count_label()
        self._sync_poke_remote_checks_from_state()
        self._invalidate_validation_snapshot(
            "远程 G 文件选择发生变化"
        )

    def _set_visible_remote_selection(self, selected: bool):
        table = self.remote_file_table
        self._remote_table_populating = True
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            for row in range(table.rowCount()):
                if table.isRowHidden(row):
                    continue
                item = table.item(row, 0)
                if item is None:
                    continue
                name = str(item.data(Qt.UserRole) or "")
                if selected:
                    self.remote_selected_names.add(name)
                    if item.checkState() != Qt.Checked:
                        item.setCheckState(Qt.Checked)
                else:
                    self.remote_selected_names.discard(name)
                    if item.checkState() != Qt.Unchecked:
                        item.setCheckState(Qt.Unchecked)
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)
            self._remote_table_populating = False
        table.viewport().update()
        self._update_remote_count_label()
        self._sync_poke_remote_checks_from_state()
        self._invalidate_validation_snapshot(
            "远程 G 文件选择发生变化"
        )

    def _clear_remote_selection(self):
        """Clear selection/search without rebuilding thousands of table cells."""
        self.remote_selected_names.clear()
        self._remote_filter_timer.stop()

        table = self.remote_file_table
        self._remote_table_populating = True
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        try:
            # Reuse the existing table items. Only checked rows are changed.
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None and item.checkState() != Qt.Unchecked:
                    item.setCheckState(Qt.Unchecked)

            self.remote_search_edit.blockSignals(True)
            try:
                self.remote_search_edit.clear()
            finally:
                self.remote_search_edit.blockSignals(False)

            # Clearing the search means every already-created row is visible.
            for row in range(table.rowCount()):
                if table.isRowHidden(row):
                    table.setRowHidden(row, False)
        finally:
            table.setUpdatesEnabled(True)
            table.blockSignals(False)
            self._remote_table_populating = False

        self._remote_visible_count = len(self.remote_file_rows)
        table.viewport().update()
        self._update_remote_count_label()
        self._sync_poke_remote_checks_from_state()
        if hasattr(self, "poke_remote_search_edit"):
            self.poke_remote_search_edit.blockSignals(True)
            try:
                self.poke_remote_search_edit.clear()
            finally:
                self.poke_remote_search_edit.blockSignals(False)
            self._apply_poke_remote_file_filter("")
        self._invalidate_validation_snapshot(
            "远程 G 文件选择和搜索条件已清空"
        )

    def _selected_remote_files(self) -> list[RemoteGFile]:
        selected = self.remote_selected_names
        return [
            item
            for item in self.remote_file_rows
            if item.name in selected
        ]

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

    def _refresh_feeder_facid_ui_from_local_path(self, value):
        widget = self.module_widgets.get("FEEDER")
        if widget is None or not hasattr(widget, "set_facid_lock"):
            return

        path = Path(str(value or "").strip())
        if not path.is_file() or path.suffix.lower() != ".g":
            widget.set_facid_lock(None)
            return

        try:
            with path.open(
                "r",
                encoding="utf-8",
                errors="ignore",
            ) as handle:
                prefix = handle.read(16384)
            match = re.search(
                r'<G\b[^>]*\bfacID="([^"]*)"',
                prefix,
                flags=re.IGNORECASE,
            )
            widget.set_facid_lock(
                match.group(1).strip()
                if match and match.group(1).strip()
                else None
            )
        except Exception:
            widget.set_facid_lock(None)

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
        self._refresh_feeder_facid_ui_from_local_path(path)

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
        feeder_widget = self.module_widgets.get("FEEDER")
        if feeder_widget is not None and hasattr(
            feeder_widget, "set_facid_lock"
        ):
            feeder_widget.set_facid_lock(None)

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
        module_id = None
        module = None
        operation_label = str(operation)
        settings = {}
        files = []
        source_type = "LOCAL"
        input_description = ""

        try:
            module_id = self.module_combo.currentData()
            module = self.modules[module_id]
            operation_labels = {
                "VALIDATE": "模型校验",
            }
            operation_label = operation_labels.get(
                operation,
                operation,
            )

            if not module.supports(operation):
                raise ValueError(
                    f"{module.display_name} 当前版本暂未开放“"
                    f"{operation_label}”。"
                )

            settings = self.module_widgets[
                module_id
            ].collect_settings()
            settings["element_catalog"] = dict(
                self.cfg.get("element_catalog", {}) or {}
            )
            source_type = self._current_input_source()
            settings["input_is_directory"] = False

            self.cfg["model_module"] = module_id
            self.cfg["operation"] = operation
            self.cfg["db"] = self.current_db_config()
            self.cfg["input_source"] = source_type

            if source_type == "LOCAL":
                input_value = self.input_edit.text().strip()
                if not input_value:
                    raise ValueError("请先选择 G 文件或目录。")

                input_path = Path(input_value)
                if not input_path.exists():
                    raise ValueError(
                        f"文件或目录不存在：\n{input_value}"
                    )

                settings["input_is_directory"] = input_path.is_dir()
                files = self.resolve_files(input_value)
                if not files:
                    raise ValueError(
                        "当前文件/目录中没有找到可处理的 .g 文件。"
                    )

                self.cfg["input_path"] = input_value
                if input_path.is_file():
                    self.cfg["last_file_path"] = str(input_path)
                    self.cfg["last_folder_path"] = str(
                        input_path.parent
                    )
                else:
                    self.cfg["last_folder_path"] = str(input_path)

                self.current_source_info = {
                    "source_type": "LOCAL",
                    "read_only_source": True,
                    "input_path": input_value,
                    "files": [str(Path(p).resolve()) for p in files],
                }
                self.current_snapshot_files = list(files)
                input_description = input_value

            elif source_type == "SSH":
                ssh_cfg = self._current_ssh_config()
                current_signature = (
                    ssh_cfg["host"],
                    int(ssh_cfg["port"]),
                    ssh_cfg["username"],
                    ssh_cfg["remote_directory"],
                )
                if self.remote_list_signature != current_signature:
                    raise ValueError(
                        "SSH服务器地址、用户名或远程目录与当前文件列表不一致。"
                        "请点击【刷新 G 文件列表】后重新选择文件。"
                    )
                selected_remote = self._selected_remote_files()
                if not selected_remote:
                    raise ValueError(
                        "请先加载 SSH 服务器 G 文件列表，"
                        "并勾选至少一个远程 .g 文件。"
                    )

                # Save connection settings before the task.  The SSH layer is
                # deliberately read-only and never exposes an upload API.
                self.cfg["ssh"] = ssh_cfg
                input_description = self._current_input_description()
            else:
                raise ValueError(
                    f"不支持的文件来源：{source_type}"
                )

            for key in (
                "rmu_name_positions",
                "rmu_name_positions_custom",
                "feeder_rmu_name_positions",
                "rmu_name_detection_mode",
                "rmu_name_exclusions",
                "device_rules",
                "breaker_name_source",
                "feeder_table_id",
                "section_table_id",
                "section_domain",
                "feeder_resolution_mode",
                "manual_feeder_name",
                "feeder_station_hint",
                "allow_feeder_override",
                "feeder_drawing_mode",
                "auto_create_missing_sections",
                "pole_switch_name_numeric",
                "pole_switch_name_format",
                "pole_switch_name_colors",
                "pole_switch_name_has_background",
                "transformer_name_numeric",
                "transformer_name_format",
                "transformer_name_colors",
                "transformer_name_has_background",
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
            QMessageBox.critical(
                self,
                "创建 Workspace 运行目录失败",
                str(exc),
            )
            return

        self._set_task_buttons_enabled(False)
        self.current_preview = None
        self.apply_btn.setEnabled(False)
        self._clear_association_table()
        self.log_edit.clear()

        self.progress_bar.setValue(0)
        self.progress_message.setText(self._t("任务准备中……"))
        self.current_artifacts = {}
        self.current_task_type = ""
        for button in (
            self.open_html_btn,
            self.open_rmu_csv_btn,
            self.open_device_csv_btn,
            self.open_change_log_btn,
            self.open_report_dir_btn,
        ):
            button.setEnabled(False)
            button.setVisible(False)

        try:
            if source_type == "SSH":
                self.workspace_status.show()
                self.workspace_status.setText(self._rt(
                    "正在从 SSH 服务器重新获取本次选择文件的最新稳定版本……"
                ))
                apply_status_style(self.workspace_status, False)
                self.progress_bar.setValue(3)
                self.progress_message.setText(self._rt(
                    "正在下载服务器最新 G 文件快照……"
                ))
                QApplication.processEvents()

                ssh_cfg = self._current_ssh_config()
                snapshot_service = RemoteSnapshotService(
                    host=ssh_cfg["host"],
                    port=ssh_cfg["port"],
                    username=ssh_cfg["username"],
                    password=ssh_cfg["password"],
                    remote_directory=ssh_cfg[
                        "remote_directory"
                    ],
                    max_attempts=3,
                )
                files, source_info = snapshot_service.download_latest(
                    self._selected_remote_files(),
                    self.current_run_dir,
                    log=self.log,
                )
                self.current_snapshot_files = list(files)
                self.current_source_info = dict(source_info)

                self.log(
                    "本次模型校验已锁定 remote_input 快照；"
                    "后续模型关联必须使用同一快照，"
                    "不会再次从服务器下载。"
                )
                self.workspace_status.setText(
                    f"SSH最新快照准备完成：{len(files)} 个 G 文件。"
                )
                apply_status_style(self.workspace_status, True)
            else:
                # Local validation also remembers the exact path set used by
                # this validation so association does not silently switch input.
                self.current_snapshot_files = list(files)

            if not files:
                raise RuntimeError(
                    "没有可用于本次模型校验的 G 文件。"
                )

        except Exception as exc:
            self._set_task_buttons_enabled(True)
            self.progress_message.setText(self._t("文件准备失败"))
            self.workspace_status.setText(self._t("文件准备失败"))
            apply_status_style(self.workspace_status, False)
            self.log(f"文件准备失败：{exc}")
            QMessageBox.critical(
                self,
                "文件准备失败",
                str(exc),
            )
            return

        self.workspace_status.show()
        self.workspace_status.setText(
            "正在进行 Oracle 数据库预检查……"
        )
        apply_status_style(self.workspace_status, False)

        self.log(
            f"\n开始执行：{module.display_name} / {operation_label}"
        )
        self.log(
            f"文件来源：{source_type} | 本次输入："
            f"{input_description or self._current_input_description()}"
        )

        settings["language"] = self.language
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
            self.progress_message.setText(translate_runtime_text(message, self.language))

    def on_worker_log(self, text):
        self.log(text)

        if "Oracle 预检查：通过" in text:
            self.workspace_status.show()
            self.workspace_status.setText(self._t("Oracle 数据库预检查通过"))
            apply_status_style(self.workspace_status, True)

    def _sync_feeder_facid_lock_from_preview(self, preview_data):
        widget = self.module_widgets.get("FEEDER")
        if widget is None or not hasattr(widget, "set_facid_lock"):
            return
        reports = list((preview_data or {}).get("reports", []) or [])
        if not reports:
            return
        current_facids = {
            str(report.get("feeder_root_current_facid") or "").strip()
            for report in reports
            if str(report.get("feeder_root_current_facid") or "").strip()
        }
        if len(current_facids) == 1:
            widget.set_facid_lock(next(iter(current_facids)))
        elif len(current_facids) > 1:
            widget.set_facid_lock("多个 G 文件存在不同当前 facID")
        else:
            widget.set_facid_lock(None)

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
        if str(self.module_combo.currentData() or "").upper() == "FEEDER":
            self._sync_feeder_facid_lock_from_preview(preview_data)
        self.current_artifacts = dict(artifacts or {})
        self.current_artifacts["source_info"] = dict(
            self.current_source_info or {}
        )
        self.current_task_type = self.current_artifacts.get("task_type", "")

        if self.current_preview and self.current_preview.get("changes_by_file"):
            change_count = sum(
                len(v)
                for v in self.current_preview["changes_by_file"].values()
            )

            current_module = str(
                self.module_combo.currentData() or ""
            ).upper()
            if current_module in {"RMU", "FEEDER", "POLE_SWITCH", "TRANSFORMER", "FUSE", "MASTER_STATION"}:
                self._populate_association_table(self.current_preview)
                if current_module == "FEEDER":
                    self.log(
                        f"模型校验已生成可关联馈线对象清单："
                        f"可关联对象 {change_count} 个。"
                        "请在工作区表格中勾选需要处理的馈线或馈线段。"
                    )
                elif current_module == "RMU":
                    self.log(
                        f"模型校验已生成可关联设备清单："
                        f"可关联/重新关联设备 {change_count} 个。"
                        "请在工作区表格中勾选需要处理的设备。"
                    )
                elif current_module == "POLE_SWITCH":
                    self.log(
                        f"模型校验已生成可关联柱上开关清单："
                        f"可关联/重新关联设备 {change_count} 个。"
                        "请在工作区表格中勾选需要处理的设备。"
                    )
                elif current_module == "FUSE":
                    self.log(
                        f"模型校验已生成可关联熔断器清单："
                        f"可关联/重新关联设备 {change_count} 个。"
                        "请在工作区表格中勾选需要处理的熔断器。"
                    )
                elif current_module == "MASTER_STATION":
                    self.log(
                        f"模型校验已生成可关联配网主站设备清单："
                        f"可关联/重新关联设备 {change_count} 个。"
                        "请在工作区表格中勾选需要处理的设备。"
                    )
                else:
                    self.log(
                        f"模型校验已生成可关联柱上变压器清单："
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
        self.progress_message.setText(self._rt(
            "模型校验完成，报告和可关联清单已生成"
        ))
        self.workspace_status.setText(self._t("任务执行完成"))
        apply_status_style(self.workspace_status, True)
        QTimer.singleShot(3500, self.workspace_status.hide)

        self._update_artifact_buttons(self.current_task_type)

        self.log(f"任务完成。本次运行目录：{report_dir}")
        self.log(f"HTML：{self.current_artifacts.get('html', '')}")
        report_kind = str(
            self.current_artifacts.get("report_kind", "")
        ).upper()
        if report_kind == "FEEDER":
            self.log(f"馈线汇总 CSV：{self.current_artifacts.get('rmu_csv', '')}")
            self.log(f"馈线段明细 CSV：{self.current_artifacts.get('device_csv', '')}")
        elif report_kind == "POLE_SWITCH":
            self.log(f"柱上开关 CSV：{self.current_artifacts.get('rmu_csv', '')}")
        elif report_kind == "TRANSFORMER":
            self.log(f"柱上变压器 CSV：{self.current_artifacts.get('rmu_csv', '')}")
        elif report_kind == "FUSE":
            self.log(f"熔断器 CSV：{self.current_artifacts.get('rmu_csv', '')}")
        elif report_kind == "MASTER_STATION":
            self.log(f"配网主站设备 CSV：{self.current_artifacts.get('rmu_csv', '')}")
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

        validation_candidates = 0
        if self.current_preview:
            validation_candidates = sum(
                len(v)
                for v in (
                    self.current_preview.get("changes_by_file", {}) or {}
                ).values()
            )
        self._write_run_manifest(
            operation="VALIDATE",
            module_id=self.current_artifacts.get(
                "report_kind",
                self.module_combo.currentData(),
            ),
            result="SUCCESS",
            summary=summary,
            artifacts=self.current_artifacts,
            input_path=self._current_input_description(),
            selected=0,
            applied=0,
            skipped=0,
        )
        self.refresh_history_table()

        self.statusBar().showMessage(
            self._rt("模型校验完成，校验报告和可关联清单已生成。"),
            5000,
        )

    def on_job_failed(self, text):
        self._set_task_buttons_enabled(True)
        self.progress_message.setText(self._t("任务执行失败"))
        self.workspace_status.show()
        self.workspace_status.setText(self._t("任务执行失败"))
        apply_status_style(self.workspace_status, False)

        self.log(text)
        try:
            self._write_run_manifest(
                operation="VALIDATE",
                module_id=self.module_combo.currentData(),
                result="FAILED",
                artifacts=self.current_artifacts,
                input_path=self._current_input_description(),
                error=text,
            )
            self.refresh_history_table()
        except Exception:
            pass

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
            self.selection_count_label.setText(self._t("已选择 0 个对象"))
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
        if module_id not in {"RMU", "FEEDER", "POLE_SWITCH", "TRANSFORMER", "FUSE", "MASTER_STATION"}:
            return

        candidate_lookup = self._candidate_change_lookup(preview_data)
        reports = preview_data.get("reports", []) or []
        display_rows = []

        if module_id == "RMU":
            self.association_selection_box.setTitle(
                self._t("可关联设备选择（模型校验结果）")
            )
            self.association_selection_tip.setText(self._rt(
                "模型校验完成后，这里展示 G 文件设备明细。只有数据库当前事实已经唯一确定、"
                "并且需要关联或重新关联的设备才允许勾选。执行模型关联时只处理你勾选的设备。"
            ))
            self.association_filter_label.setText(self._t("环网柜名称筛选"))
            self.rmu_filter_edit.setPlaceholderText(
                self._t("输入环网柜名称快速筛选，例如：17613 / RMU-42646")
            )
            headers = [
                self._t(x) for x in [
                    "选择", "G文件", "环网柜序号", "环网柜名称", "G图元类型",
                    "逻辑设备名称（图上规则）", "数据库CODE", "状态", "当前关联",
                    "目标设备ID", "Expected KeyID", "处理说明",
                ]
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
        elif module_id == "FEEDER":
            self.association_selection_box.setTitle(
                self._t("可关联馈线 / 馈线段选择（模型校验结果）")
            )
            self.association_selection_tip.setText(self._rt(
                "模型校验完成后，这里展示可执行的馈线根关联和 FeedLine 明细。"
                "当 G 文件没有 FeedLine、但人工输入/文件名已唯一确定 13500 馈线时，"
                "可单独勾选 G 根节点 facID 关联；不会创建 13503 馈线段。"
                "其余 FeedLine 仍按原规则逐条选择。"
            ))
            self.association_filter_label.setText(self._t("馈线段快速筛选"))
            self.rmu_filter_edit.setPlaceholderText(
                self._t("输入 FEEDER_ID / 馈线名称 / FeedLine XML ID / 目标馈线段名称")
            )
            headers = [
                self._t(x) for x in [
                    "选择", "G文件", "连接区域", "FEEDER_ID", "FeedLine序号",
                    "图元XML ID", "当前关联", "状态", "目标馈线段",
                    "目标设备ID", "Expected KeyID", "处理说明",
                ]
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                root_row = dict(report.get("feeder_root_candidate_row", {}) or {})
                if root_row.get("xml_id"):
                    root_row["_source_file"] = source_file
                    root_row["_file_name"] = file_name
                    root_row["_region_index"] = report.get("region_index", "")
                    root_row["_feeder_id"] = report.get("feeder_id", "")
                    root_row["_feeder_name"] = report.get("feeder_name", "")
                    display_rows.append(root_row)
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
        elif module_id == "POLE_SWITCH":
            self.association_selection_box.setTitle(
                self._t("可关联柱上开关选择（模型校验结果）")
            )
            self.association_selection_tip.setText(self._rt(
                "模型校验完成后，这里展示按用户维护 devref 图元名单识别的柱上开关明细。"
                "只有 13501 记录、13501.ID 与 13502 combined_id 正确对应，且 Domain 40 KeyID 校验通过，"
                "且需要关联或重新关联的对象才允许勾选。"
            ))
            self.association_filter_label.setText(self._t("柱上开关快速筛选"))
            self.rmu_filter_edit.setPlaceholderText(
                self._t("输入设备名称、型号、devref 或 XML ID")
            )
            headers = [
                self._t(x) for x in [
                    "选择", "G文件", "图元XML ID", "型号", "devref",
                    "图上名称", "名称距离", "名称方向",
                    "当前KeyID", "目标设备ID", "Expected KeyID", "状态", "处理说明",
                ]
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                for pole_row in report.get("pole_switch_rows", []) or []:
                    item = dict(pole_row)
                    item["_source_file"] = source_file
                    item["_file_name"] = file_name
                    display_rows.append(item)
        elif module_id == "FUSE":
            self.association_selection_box.setTitle(
                self._t("可关联熔断器选择（模型校验结果）")
            )
            self.association_selection_tip.setText(self._rt(
                "这里只展示【熔断器模型配置】中用户维护 devref 图元名单命中的对象。每个 FUSE 只提名最近的柱上变压器；柱上变压器身份复用用户维护的 devref 图元名单；"
                "同一柱上变压器只能被一个 FUSE 占用。成功获得变压器后复用麦加柱上变压器名称规则，"
                "派生 NAME=FUSE+变压器名称。麦加不判断 FEEDER_ID，13505 和 13513 都只按 NAME 唯一匹配。"
            ))
            self.association_filter_label.setText(self._t("熔断器快速筛选"))
            self.rmu_filter_edit.setPlaceholderText(
                self._t("输入熔断器名称、柱上变压器名称或 XML ID")
            )
            headers = [
                self._t(x) for x in [
                    "选择", "G文件", "图元XML ID", "最近柱上变压器", "熔断器名称",
                    "变压器距离", "当前KeyID", "目标设备ID", "Expected KeyID", "状态", "处理说明",
                ]
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                for fuse_row in report.get("fuse_rows", []) or []:
                    item = dict(fuse_row)
                    item["_source_file"] = source_file
                    item["_file_name"] = file_name
                    display_rows.append(item)
        elif module_id == "MASTER_STATION":
            self.association_selection_box.setTitle(
                self._t("可关联配网主站设备选择（模型校验结果）")
            )
            self.association_selection_tip.setText(self._rt(
                "只处理含 CBreaker 的最内层主网矩形框；取框附近最近的无背景合法馈线标题（颜色不限） "
                "（如 MNA4-12 / ARF2-07）解析变电站、馈线和唯一 BAY_ID。"
                "确认 Bay 后，框内 CBreaker / Disconnector / GroundDisconnector 继续按 BAY_ID 关联；"
                "Bus 使用 410/busbarsection，只按变电站 ST_ID 取候选，不检查 BAY_ID，并从同站未使用 410 记录中任意一对一分配。"
                "其它设备仍要求目标可唯一确定且 Expected KeyID 校验通过。"
            ))
            self.association_filter_label.setText(self._t("主站设备快速筛选"))
            self.rmu_filter_edit.setPlaceholderText(
                self._t("输入 CODE、图元类型、key_name 或 XML ID")
            )
            headers = [
                self._t(x) for x in [
                    "选择", "G文件", "G图元类型", "图元XML ID", "key_name",
                    "CODE", "当前KeyID", "目标表号", "目标域号", "目标设备ID",
                    "Expected KeyID", "状态", "处理说明",
                ]
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                for master_row in report.get("master_station_rows", []) or []:
                    item = dict(master_row)
                    item["_source_file"] = source_file
                    item["_file_name"] = file_name
                    display_rows.append(item)
        elif module_id == "TRANSFORMER":
            self.association_selection_box.setTitle(
                self._t("可关联柱上变压器选择（模型校验结果）")
            )
            self.association_selection_tip.setText(self._rt(
                "模型校验完成后，这里展示按用户维护 devref 图元名单识别的柱上变压器明细。"
                "麦加不判断 FEEDER_ID；只要图上名称在 13505.NAME 唯一且 Expected KeyID 校验通过即可关联。"
            ))
            self.association_filter_label.setText(self._t("柱上变压器快速筛选"))
            self.rmu_filter_edit.setPlaceholderText(
                self._t("输入变压器名称、devref 或 XML ID")
            )
            headers = [
                self._t(x) for x in [
                    "选择", "G文件", "图元XML ID", "图上名称", "名称距离", "名称方向",
                    "当前keyid1", "当前keyid2", "目标设备ID", "Expected KeyID", "状态", "处理说明",
                ]
            ]
            for report in reports:
                source_file = str(report.get("g_file", "") or "")
                file_name = str(report.get("file_name", "") or Path(source_file).name)
                for transformer_row in report.get("transformer_rows", []) or []:
                    item = dict(transformer_row)
                    item["_source_file"] = source_file
                    item["_file_name"] = file_name
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
                    check_item.setToolTip(self._rt(
                        "数据库当前事实唯一正确，可选择执行关联/重新关联。"
                    ))
                else:
                    check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    check_item.setText("—")
                    check_item.setToolTip(self._t("当前记录无需回写或已被校验阻断。"))
                self.association_table.setItem(row_index, 0, check_item)

                if module_id == "RMU":
                    current_text = self._rt(str(
                        row.get("model_link_status", "")
                        or (self._t("已关联") if row.get("model_linked") == "YES" else self._t("未关联"))
                    ))
                    values = [
                        row["_file_name"], row["_frame_index"], row.get("rmu_name", ""),
                        row.get("object_type", ""),
                        row.get("logical_code", "") or row.get("selected_device_name", ""),
                        row.get("db_code", ""), self._row_status_text(row), current_text,
                        row.get("db_device_id", ""), row.get("expected_keyid", ""),
                        self._rt(row.get("reason", "")),
                    ]
                elif module_id == "FEEDER":
                    is_root_row = (
                        str(row.get("object_type", "")).upper() == "G"
                        and str(row.get("xml_id", "")) == "root"
                    )
                    current_text = (
                        self._t("根facID未关联")
                        if is_root_row
                        else (
                            f"KeyID={row.get('current_keyid')} / {row.get('current_db_name') or '-'}"
                            if row.get("model_linked") == "YES" else self._t("未关联")
                        )
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
                        self._rt(row.get("reason", "")),
                    ]
                elif module_id == "POLE_SWITCH":
                    values = [
                        row["_file_name"], row.get("xml_id", ""),
                        row.get("device_model", ""), row.get("devref", ""),
                        row.get("graphical_name", ""), row.get("name_distance", ""),
                        row.get("name_direction", ""),
                        row.get("current_keyid", ""), row.get("db_device_id", ""),
                        row.get("expected_keyid", ""), self._row_status_text(row),
                        self._rt(row.get("reason", "")),
                    ]
                elif module_id == "FUSE":
                    values = [
                        row["_file_name"], row.get("xml_id", ""),
                        row.get("nearest_transformer_name", ""), row.get("derived_fuse_name", ""),
                        row.get("nearest_transformer_distance", ""), row.get("current_keyid", ""),
                        row.get("db_device_id", ""), row.get("expected_keyid", ""),
                        self._row_status_text(row), self._rt(row.get("reason", "")),
                    ]
                elif module_id == "MASTER_STATION":
                    values = [
                        row["_file_name"], row.get("object_type", ""),
                        row.get("xml_id", ""), row.get("key_name", ""),
                        row.get("logical_code", ""), row.get("current_keyid", ""),
                        row.get("table_id", ""), row.get("configured_domain", ""),
                        row.get("db_device_id", ""), row.get("expected_keyid", ""),
                        self._row_status_text(row), self._rt(row.get("reason", "")),
                    ]
                elif module_id == "TRANSFORMER":
                    values = [
                        row["_file_name"], row.get("xml_id", ""),
                        row.get("graphical_name", ""), row.get("name_distance", ""),
                        row.get("name_direction", ""), row.get("current_keyid1", ""),
                        row.get("current_keyid2", ""), row.get("db_device_id", ""),
                        row.get("expected_keyid", ""), self._row_status_text(row),
                        self._rt(row.get("reason", "")),
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
            is_feeder = (
                str(self.module_combo.currentData() or "").upper() == "FEEDER"
            )
            if self.language == "en_US":
                unit = "feeder objects" if is_feeder else "devices"
                suffix = (
                    f"; visible {visible_count} rows"
                    if filter_text
                    else ""
                )
                self.selection_count_label.setText(
                    f"Selected {selected_count} {unit} / "
                    f"Eligible {total_candidates} {unit}{suffix}"
                )
            else:
                suffix = (
                    f"；当前显示 {visible_count} 行"
                    if filter_text
                    else ""
                )
                unit = "个馈线对象" if is_feeder else "个设备"
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
            elif module_id == "POLE_SWITCH":
                # Model, devref, name, topology component and XML ID are the
                # useful quick-filter keys for standalone pole switches.
                columns = (2, 3, 4, 5, 6, 12)
            elif module_id == "TRANSFORMER":
                columns = (2, 3, 4, 5, 6, 7, 9, 11)
            elif module_id == "FUSE":
                columns = (2, 3, 4, 5, 7, 10)
            elif module_id == "MASTER_STATION":
                columns = (1, 2, 3, 4, 5, 6, 9, 11)
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
            unit = "个馈线对象" if module_id == "FEEDER" else "个设备"
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


    def _export_model_change_log(
        self,
        result_bundle,
        report_dir,
        module_id,
    ):
        """Export exact XML attribute before/after values for this write-back."""
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / "model_change_log.csv"

        fields = [
            "时间",
            "模型",
            "源G文件",
            "输出G文件",
            "G图元类型",
            "图元XML ID",
            "属性",
            "修改前",
            "修改后",
        ]
        rows = []
        stamp = datetime.now().isoformat(timespec="seconds")

        for result in result_bundle.get("results", []) or []:
            source_file = str(
                result.get("source_g_file", "")
                or result.get("g_file", "")
            )
            output_file = str(
                result.get("output_g_file", "")
                or result.get("g_file", "")
            )
            for change in result.get("changes", []) or []:
                before = dict(change.get("before", {}) or {})
                after = dict(change.get("after", {}) or {})
                keys = list(after.keys())
                for key in keys:
                    rows.append({
                        "时间": stamp,
                        "模型": str(module_id or ""),
                        "源G文件": source_file,
                        "输出G文件": output_file,
                        "G图元类型": str(change.get("tag", "")),
                        "图元XML ID": str(change.get("xml_id", "")),
                        "属性": str(key),
                        "修改前": (
                            ""
                            if before.get(key) is None
                            else str(before.get(key))
                        ),
                        "修改后": str(after.get(key, "")),
                    })

        with path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        return str(path)

    @staticmethod
    def _association_status_breakdown(execution_preview):
        counts = {}
        for changes in (
            execution_preview.get("changes_by_file", {}) or {}
        ).values():
            for change in changes or []:
                row = dict(change.get("validated_row", {}) or {})
                status = str(
                    row.get("status")
                    or row.get("model_link_status")
                    or "READY"
                )
                counts[status] = counts.get(status, 0) + 1
        return counts

    def apply_association(self):
        if not self.current_preview or not self.current_preview.get("changes_by_file"):
            QMessageBox.information(
                self,
                "模型关联",
                "当前没有可执行的模型校验结果，请先执行模型校验。",
            )
            return

        module_id = str(self.module_combo.currentData() or "")

        if module_id.upper() in {"RMU", "FEEDER", "POLE_SWITCH", "TRANSFORMER", "FUSE", "MASTER_STATION"}:
            execution_preview = self._selected_association_preview()
            if not execution_preview or not execution_preview.get(
                "changes_by_file"
            ):
                QMessageBox.information(
                    self,
                    "模型关联",
                    (
                        "请先在“可关联馈线 / 馈线段选择”表格中勾选至少一个需要处理的馈线对象。"
                        if module_id.upper() == "FEEDER"
                        else (
                            "请先在“可关联柱上开关选择”表格中勾选至少一个需要关联或重新关联的设备。"
                            if module_id.upper() == "POLE_SWITCH"
                            else (
                                "请先在“可关联柱上变压器选择”表格中勾选至少一个需要关联或重新关联的设备。"
                                if module_id.upper() == "TRANSFORMER"
                                else (
                                    "请先在“可关联熔断器选择”表格中勾选至少一个需要关联或重新关联的设备。"
                                    if module_id.upper() == "FUSE"
                                    else "请先在“可关联设备选择”表格中勾选至少一个需要关联或重新关联的设备。"
                                )
                            )
                        )
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
        selected_file_count = len(
            execution_preview.get("changes_by_file", {}) or {}
        )
        status_counts = self._association_status_breakdown(
            execution_preview
        )
        status_summary = "，".join(
            f"{key}={value}"
            for key, value in sorted(status_counts.items())
        ) or "无"
        skip_label = (
            "馈线文件"
            if module_id == "FEEDER"
            else "柱上开关"
            if module_id == "POLE_SWITCH"
            else "柱上变压器"
            if module_id == "TRANSFORMER"
            else "熔断器"
            if module_id == "FUSE"
            else "RMU"
        )
        target_label = "馈线对象" if module_id == "FEEDER" else "设备图元"

        if module_id.upper() == "RMU":
            if self.language == "en_US":
                message = (
                    f"This run will process only the {change_count} selected device objects.\n"
                    f"G files involved: {selected_file_count}\n"
                    f"Candidate status: {status_summary}\n\n"
                    "The execution stage will not rescan the entire G drawing or iterate through all RMUs again. "
                    "Only the RMUs and devices containing the selected objects will receive lightweight database revalidation, "
                    "followed by precise XML-ID write-back to the Workspace safe copy.\n\n"
                    "The final HTML / CSV reports will include only the RMUs and devices selected in this run.\n\n"
                    "Proceed with model association?"
                )
            else:
                message = (
                    f"本次将只处理已勾选的 {change_count} 个{target_label}。\n"
                    f"涉及 G 文件：{selected_file_count} 个\n"
                    f"候选状态：{status_summary}\n\n"
                    "执行阶段不会重新扫描整张 G 图，也不会重新循环全部环网柜。"
                    "程序只会对这些设备所属环网柜和设备做轻量数据库复核，"
                    "然后按 XML ID 精确写回 Workspace 安全副本。\n\n"
                    "最终 HTML / CSV 只汇报本次选中的环网柜和设备。\n\n"
                    "是否确认执行？"
                )
        elif module_id.upper() == "POLE_SWITCH":
            if self.language == "en_US":
                message = (
                    f"This run will process only the {change_count} selected pole-switch objects.\n"
                    f"G files involved: {selected_file_count}\n"
                    f"Candidate status: {status_summary}\n\n"
                    "The program will recheck dms_combined_device / dms_cb_device and KeyID Domain 40 at execution time, "
                    "then write only the selected XML objects to Workspace safe copies.\n\n"
                    "Original G files will not be modified.\n\n"
                    "Proceed with model association?"
                )
            else:
                message = (
                    f"本次将只处理已勾选的 {change_count} 个柱上开关图元。\n"
                    f"涉及 G 文件：{selected_file_count} 个\n"
                    f"候选状态：{status_summary}\n\n"
                    "执行时会重新查询 13501、13502，并重新校验 Domain=40 的 KeyID，"
                    "然后只按 XML ID 写入 Workspace 安全副本。\n\n"
                    "原始 G 文件不会被修改。\n\n"
                    "是否确认执行？"
                )
        elif module_id.upper() == "TRANSFORMER":
            if self.language == "en_US":
                message = (
                    f"This run will process only the {change_count} selected pole-transformer objects.\n"
                    f"G files involved: {selected_file_count}\n"
                    f"Candidate status: {status_summary}\n\n"
                    "The program will recheck 13505 / dms_tr_device by NAME only (no FEEDER_ID check), "
                    "verify Expected KeyID Domain 1, and write both transformer keyid1/keyid2 fields "
                    "to Workspace safe copies.\n\n"
                    "Original G files will not be modified.\n\n"
                    "Proceed with model association?"
                )
            else:
                message = (
                    f"本次将只处理已勾选的 {change_count} 个柱上变压器图元。\n"
                    f"涉及 G 文件：{selected_file_count} 个\n"
                    f"候选状态：{status_summary}\n\n"
                    "执行时只按 NAME 重新查询 13505 变压器设备，不判断 FEEDER_ID，"
                    "重新校验 Domain=1 的 Expected KeyID，并将 keyid1/keyid2 两组字段写入 Workspace 安全副本。\n\n"
                    "原始 G 文件不会被修改。\n\n"
                    "是否确认执行？"
                )
        elif module_id.upper() == "FUSE":
            if self.language == "en_US":
                message = (
                    f"This run will process only the {change_count} selected fuse objects.\n"
                    f"G files involved: {selected_file_count}\n"
                    f"Candidate status: {status_summary}\n\n"
                    "Execution rechecks the nearest Transformer_OH assignment, 13505 NAME uniqueness, derived FUSE NAME, "
                    "and unique 13513 NAME without any FEEDER_ID validation, then verifies Domain 40 Expected KeyID.\n\n"
                    "Original G files will not be modified.\n\nProceed with model association?"
                )
            else:
                message = (
                    f"本次将只处理已勾选的 {change_count} 个熔断器图元。\n"
                    f"涉及 G 文件：{selected_file_count} 个\n"
                    f"候选状态：{status_summary}\n\n"
                    "执行时会重新计算 FUSE 与最近 Transformer_OH 的独占关系，重新校验 13505.NAME 唯一，"
                    "再生成 FUSE+变压器名称，并只按 13513.NAME 唯一查询；麦加不判断 FEEDER_ID。"
                    "随后重新校验 Domain=40 的 Expected KeyID，只写 Workspace 安全副本。\n\n"
                    "原始 G 文件不会被修改。\n\n是否确认执行？"
                )
        elif module_id.upper() == "FEEDER":
            feeder_settings = self.module_widgets[
                module_id
            ].collect_settings()
            create_enabled = bool(
                feeder_settings.get(
                    "auto_create_missing_sections",
                    True,
                )
            )
            planned_create_count = sum(
                1
                for changes in (
                    execution_preview.get(
                        "changes_by_file",
                        {},
                    ) or {}
                ).values()
                for change in (changes or [])
                if (
                    change.get("db_create_needed") == "YES"
                    or (
                        change.get("validated_row", {}) or {}
                    ).get("db_create_needed") == "YES"
                )
            )
            if self.language == "en_US":
                db_write_notice = (
                    f"\nDatabase completion: enabled; the current selection may require up to "
                    f"{planned_create_count} missing feeder sections. "
                    "The database will be queried again at execution time; only genuinely missing "
                    "DMS_SECTION_DEVICE rows will be INSERTed. Existing devices will never be UPDATEd or DELETEd.\n"
                    if create_enabled
                    else
                    "\nDatabase completion: disabled; missing feeder sections will not be created.\n"
                )
                message = (
                    f"This run will process only the {change_count} selected FeedLine objects.\n"
                    f"G files involved: {selected_file_count}\n"
                    f"Candidate status: {status_summary}\n"
                    f"{db_write_notice}\n"
                    "The program will recheck current feeder-section occupancy in the database. If the database has insufficient sections and completion is enabled, "
                    "the missing sections will be created first, the database will be queried again, and Expected KeyID will then be recalculated.\n"
                    "FeedLine write-back is limited to app, p_ReportType, state, voltype, and keyid. Feeder identity comes from the nearest associated device model; FACID, file name, and manual feeder-name inputs are not used.\n\n"
                    "Original G files and SSH server files will not be modified; only the Workspace/g_output safe copy is changed.\n\n"
                    "Proceed with model association?"
                )
            else:
                db_write_notice = (
                    f"\n数据库补齐：已启用；当前勾选中最多涉及 "
                    f"{planned_create_count} 条缺失馈线段。"
                    "\n执行时会再次查询数据库，只 INSERT 确实缺失的 "
                    "DMS_SECTION_DEVICE；不会 UPDATE / DELETE 已有设备。\n"
                    if create_enabled
                    else
                    "\n数据库补齐：未启用，不会创建缺失馈线段。\n"
                )
                message = (
                    f"本次将只处理已勾选的 {change_count} 个FeedLine 图元。\n"
                    f"涉及 G 文件：{selected_file_count} 个\n"
                    f"候选状态：{status_summary}\n"
                    f"{db_write_notice}\n"
                    "程序会重新确认当前数据库馈线段占用情况；如数据库数量不足且启用了补齐，"
                    "会先创建缺失馈线段并重新查询数据库，再计算 Expected KeyID。\n"
                    "FeedLine 只回写 app、p_ReportType、state、voltype、keyid 这 5 个属性；馈线归属以最近已关联设备模型为准，不使用文件名、人工输入或 G 根 facID 猜测。\n\n"
                    "原始 G 文件和 SSH 服务器文件都不会被修改，"
                    "只修改 Workspace/g_output 安全副本。\n\n"
                    "是否确认执行？"
                )
        else:
            if self.language == "en_US":
                target_text = "feeder objects" if module_id == "FEEDER" else "device objects"
                skip_text = "feeder files" if module_id == "FEEDER" else "RMUs"
                message = (
                    f"This run will process only the {change_count} selected {target_text}.\n"
                    f"{skip_text} skipped by validation: {skipped_count}.\n\n"
                    "Original G files will not be modified. All selected G files will be copied to Workspace/g_output, and only the safe copies will be changed.\n"
                    "After association, the safe copies will be revalidated immediately and final HTML / CSV reports with the same specification as Model Validation will be generated.\n\n"
                    "Proceed with model association?"
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
            self._t("确认执行模型关联"),
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
            self.progress_message.setText(self._t("正在准备模型关联……"))

            module_id = self.module_combo.currentData()
            module = self.modules[module_id]
            settings = self.module_widgets[module_id].collect_settings()
            settings["element_catalog"] = dict(
                self.cfg.get("element_catalog", {}) or {}
            )

            # Association MUST use the exact file set from the corresponding
            # validation.  In SSH mode these are the immutable remote_input
            # snapshots downloaded when validation started.  Never fetch the
            # server again here: that would risk validating version A but
            # writing version B.
            files = [
                Path(p)
                for p in (self.current_snapshot_files or [])
            ]
            if not files and self._current_input_source() == "LOCAL":
                files = self.resolve_files(
                    self.input_edit.text().strip()
                )
            if not files:
                raise RuntimeError(
                    "模型校验输入快照不存在，请重新执行模型校验。"
                )

            if module_id in {"RMU", "FEEDER", "POLE_SWITCH", "TRANSFORMER", "FUSE", "MASTER_STATION"}:
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

            # Run the association backend in QThread so the GUI event loop keeps
            # repainting continuously.  The validated file snapshot, settings,
            # Oracle checks, module association decisions and write-back logic are
            # exactly the same; only execution scheduling changes.  A nested Qt
            # event loop preserves the existing sequential control flow while the
            # busy/indeterminate progress bar remains animated.
            def live_association_log(text):
                self.log(text)
                message_text = translate_runtime_text(text, self.language)
                if message_text:
                    last_line = str(message_text).splitlines()[-1].strip()
                    if last_line:
                        self.progress_message.setText(last_line[:220])

            self.progress_bar.setRange(0, 0)
            self.progress_bar.setTextVisible(False)
            self.progress_message.setText(
                self._t("正在执行模型关联，请查看实时日志……")
            )

            association_loop = QEventLoop(self)
            association_result = {}
            association_worker = AssociationExecutionWorker(
                self.current_db_config(),
                module,
                files,
                settings,
                execution_preview,
                Path(self.current_run_dir) / "g_output",
            )

            def _association_completed(bundle):
                association_result["bundle"] = bundle
                association_loop.quit()

            def _association_failed(exc):
                association_result["error"] = exc
                association_loop.quit()

            association_worker.log.connect(live_association_log)
            association_worker.completed.connect(_association_completed)
            association_worker.failed.connect(_association_failed)
            association_worker.start()
            association_loop.exec()
            association_worker.wait()
            association_worker.deleteLater()

            if "error" in association_result:
                raise association_result["error"]
            if "bundle" not in association_result:
                raise RuntimeError(
                    "模型关联后台任务异常结束，未返回执行结果。"
                )
            result_bundle = association_result["bundle"]

            # Keep the same left-right busy indicator through report generation.
            # Exact counts remain visible in the status text and Console logs.
            self.progress_message.setText(
                self._rt("模型关联写回完成，正在整理执行结果……")
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

            if module_id in {"RMU", "FEEDER", "POLE_SWITCH", "TRANSFORMER", "FUSE", "MASTER_STATION"}:
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
                    self._rt("正在生成本次模型关联执行报告……")
                )
                QApplication.processEvents()
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
                self.progress_message.setText(self._rt(
                    "关联完成，正在重新校验安全副本……"
                ))
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
                self.progress_message.setText(self._rt(
                    "正在生成模型关联完成报告……"
                ))

            inventory_files = copied_files or [Path(p) for p in files]
            graph_feeder_inventory = compare_makkah_ring_feeders_for_files(
                db,
                inventory_files,
                settings,
                self.log,
            )
            attach_makkah_ring_feeder_inventory(
                reports,
                graph_feeder_inventory,
            )

            if module_id in {"RMU", "FEEDER", "POLE_SWITCH", "TRANSFORMER", "FUSE", "MASTER_STATION"} and not reports:
                raise RuntimeError(
                    "模型关联已执行，但没有生成本次选中对象的执行报告。"
                )

            report_dir = (
                Path(self.current_run_dir) / "association_result_report"
            )
            report_dir.mkdir(parents=True, exist_ok=True)

            html_path = report_dir / "report.html"
            csv_base = report_dir / "report.csv"
            export_html_bundle(reports, html_path, final_rules, language=self.language)
            csv_paths = export_csv_bundle(
                reports,
                csv_base,
                language=self.language,
            )
            change_log_csv = self._export_model_change_log(
                result_bundle,
                report_dir,
                module.module_id,
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
                "change_log_csv": str(change_log_csv),
                "source_info": dict(self.current_source_info or {}),
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

            self.progress_bar.setRange(0, 100)
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.setValue(100)
            self.progress_message.setText(
                self._t("模型关联完成，最终 HTML / CSV 报告已生成")
            )
            self.workspace_status.show()
            self.workspace_status.setText(
                self._t("模型关联完成，最终报告已生成")
            )
            apply_status_style(self.workspace_status, True)
            QTimer.singleShot(3500, self.workspace_status.hide)

            self._set_task_buttons_enabled(True)
            self.apply_btn.setEnabled(False)
            self._update_artifact_buttons("association")

            is_feeder = module.module_id == "FEEDER"
            is_pole_switch = module.module_id == "POLE_SWITCH"
            is_transformer = module.module_id == "TRANSFORMER"
            is_fuse = module.module_id == "FUSE"
            is_master_station = module.module_id == "MASTER_STATION"
            object_label = (
                "FeedLine 图元" if is_feeder
                else "柱上变压器图元" if is_transformer
                else "熔断器图元" if is_fuse
                else "配网主站设备图元" if is_master_station
                else "设备图元"
            )
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
                        else (
                            f"关联完成柱上开关 CSV：{csv_paths[0]}"
                            if is_pole_switch
                            else (
                                f"关联完成柱上变压器 CSV：{csv_paths[0]}"
                                if is_transformer
                                else (
                                    f"关联完成熔断器 CSV：{csv_paths[0]}"
                                    if is_fuse
                                    else (
                                        f"关联完成配网主站设备 CSV：{csv_paths[0]}"
                                        if is_master_station
                                        else f"关联完成环网柜 CSV：{csv_paths[0]}"
                                    )
                                )
                            )
                        )
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
            self.log(f"模型修改记录 CSV：{change_log_csv}")

            self._write_run_manifest(
                operation="APPLY_ASSOCIATION",
                module_id=module.module_id,
                result=(
                    "SUCCESS"
                    if skipped_total == 0
                    else "PARTIAL"
                ),
                summary=final_summary,
                artifacts=self.current_artifacts,
                input_path=self._current_input_description(),
                selected=selected_total,
                applied=total,
                skipped=skipped_total,
            )
            self.refresh_history_table()

            summary_box = QMessageBox(self)
            summary_box.setWindowTitle(self._t("模型关联完成"))
            summary_box.setIcon(QMessageBox.Information)
            if self.language == "en_US":
                selected_object_label = (
                    "FeedLine objects" if is_feeder else "device objects"
                )
                summary_text = (
                    "Model association processing completed.\n\n"
                    f"Selected: {selected_total} {selected_object_label}\n"
                    f"Written successfully: {total}\n"
                    f"Skipped during execution: {skipped_total}\n\n"
                    "Original G files were not modified.\n"
                    f"Change log: {change_log_csv}"
                )
            else:
                summary_text = (
                    f"模型关联处理完成。\n\n"
                    f"本次选择：{selected_total} 个{object_label}\n"
                    f"成功写回：{total} 个\n"
                    f"执行时跳过：{skipped_total} 个\n\n"
                    f"原始 G 文件未修改。\n"
                    f"修改记录：{change_log_csv}"
                )
            summary_box.setText(summary_text)
            open_dir_button = summary_box.addButton(
                self._t("打开结果目录"),
                QMessageBox.ActionRole,
            )
            open_html_button = summary_box.addButton(
                self._t("打开 HTML"),
                QMessageBox.ActionRole,
            )
            open_change_button = summary_box.addButton(
                self._t("打开修改记录"),
                QMessageBox.ActionRole,
            )
            summary_box.addButton(
                self._t("关闭"),
                QMessageBox.AcceptRole,
            )
            summary_box.exec()
            if summary_box.clickedButton() is open_dir_button:
                self.open_current_run_dir()
            elif summary_box.clickedButton() is open_html_button:
                self.open_artifact("html")
            elif summary_box.clickedButton() is open_change_button:
                self.open_artifact("change_log_csv")

        except Exception as exc:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.setValue(0)
            self.progress_message.setText(self._t("模型关联失败"))
            QApplication.processEvents()
            self.workspace_status.show()
            self.workspace_status.setText(self._t("模型关联失败"))
            apply_status_style(self.workspace_status, False)
            self.log(f"模型关联失败：{exc}")
            try:
                self._write_run_manifest(
                    operation="APPLY_ASSOCIATION",
                    module_id=self.module_combo.currentData(),
                    result="FAILED",
                    artifacts=self.current_artifacts,
                    input_path=self._current_input_description(),
                    error=str(exc),
                )
                self.refresh_history_table()
            except Exception:
                pass
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
        self.statusBar().showMessage(self._rt("运行日志已复制。"), 2500)

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
