from __future__ import annotations

import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from PySide6.QtCore import QEvent, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.models import InputMode
from g_file_studio.processors.smart_profile_processor import (
    SmartProfileProcessingSettings,
    process_smart_profile_consistency,
    process_smart_profile_correction,
)
from g_file_studio.services.admin_access_service import AdminAccessService
from g_file_studio.services.classification_registry_service import (
    AdminLeaseSnapshot,
    ClassificationRegistryService,
    DEFAULT_ADMIN_LEASE_SECONDS,
)
from g_file_studio.services.central_repository_settings import CentralRepositorySettings
from g_file_studio.services.paths import default_workspace
from g_file_studio.services.remote_g_source import download_stable_files
from g_file_studio.services.remote_symbol_library import (
    DEFAULT_REMOTE_SYMBOL_ROOT,
    RemoteSymbolLibraryService,
)
from g_file_studio.services.run_history import begin_managed_run, configure_managed_output
from g_file_studio.services.site_profile_service import SiteProfileService, SiteSmartProfile
from g_file_studio.services.symbol_inventory_service import (
    DEVICE_LEVEL_VALUES,
    SYMBOL_USAGE_VALUES,
    default_device_level,
    infer_device_type,
    infer_symbol_usage,
)
from g_file_studio.services.symbol_discovery_service import discover_graphic_symbols
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.help_content import APP_HELP
from g_file_studio.ui.pages.base_page import BasePage
from g_file_studio.ui.path_validation import validate_input_source
from g_file_studio.ui.widgets import InfoBanner, InputSourceSelector, PathRow, SmoothProgressBar, TaskPanel, WheelSafeComboBox
from g_file_studio.ui.widgets.help_widgets import set_primary, set_secondary
from g_file_studio.ui.table_layout import apply_graphics_table_selection_style
from g_file_studio.workers import FunctionWorker


class SiteProfilePage(BasePage):
    """Read-only remote symbol catalog and local classification manager.

    The older standard-inspection/profile workflow remains in the implementation
    for data compatibility, but it is intentionally not part of this page's user
    workflow. This page synchronizes remote symbol metadata and stores operator
    classification markers locally for downstream programs.
    """

    activeProfileChanged = Signal(str)
    connectionSettingsRequested = Signal()
    orthogonalizeRequested = Signal()
    adminAccessChanged = Signal(object)

    def __init__(
        self,
        user_settings: UserSettingsService,
        parent=None,
        *,
        defer_catalog_restore: bool = False,
    ) -> None:
        self.user_settings = user_settings
        self._defer_catalog_restore = bool(defer_catalog_restore)
        self._catalog_restore_pending = bool(defer_catalog_restore)
        self._catalog_restore_started = False
        self.admin_access = AdminAccessService(user_settings)
        # Access level is deliberately session-only. Every process starts in the
        # ordinary/read-only role even on a workstation that was previously used
        # by an administrator.
        self._is_admin_mode = False
        self._machine_id = self.user_settings.get_value("access_control/machine_id", "").strip()
        self._machine_name = socket.gethostname().strip() or "Unknown-PC"
        self._admin_lease: AdminLeaseSnapshot | None = None
        self._admin_lease_worker: FunctionWorker | None = None
        self._admin_lease_action = ""
        # When the global access dialog starts an asynchronous Admin-status refresh,
        # a fast operator click on “抢占 Admin” must not be silently discarded.
        # Queue exactly one takeover and execute it as soon as the status worker ends.
        self._pending_admin_takeover = False
        self.service = SiteProfileService()
        self._last_scan = None
        self._last_report_path: Path | None = None
        self._scan_worker: FunctionWorker | None = None
        self._server_sync_worker: FunctionWorker | None = None
        self._profile_operation_worker: FunctionWorker | None = None
        self._classification_registry_worker: FunctionWorker | None = None
        self._central_progress_dialog: QProgressDialog | None = None
        self._profile_operation_callback = None
        self._profile_operation_title = ""
        self._last_server_sync_payload: dict[str, object] = {}
        # Table restoration writes classification cells programmatically.  Those
        # changes must never be mistaken for user edits and trigger one JSON
        # rewrite per row during startup.
        self._suppress_classification_marker_persistence = False
        # v2.18.200: the server-catalog page is a local-first inventory manager.
        # Local snapshot I/O and visible-table hydration are staged independently so
        # neither JSON parsing nor 200-row QTableWidget creation can starve the GUI.
        self._local_catalog_restore_worker: FunctionWorker | None = None
        self._inventory_render_generation = 0
        self._inventory_render_rows: list[dict[str, object]] = []
        self._inventory_render_cursor = 0
        self._inventory_render_batch_size = 500
        # Visible operator columns keep a cheap one-time content width cache.
        # It is recomputed only after the inventory has been populated; subsequent
        # resizes reuse these widths instead of rescanning 200 rows.
        self._inventory_visible_columns = (3, 5, 6, 7, 8, 9, 18)
        self._inventory_natural_widths: dict[int, int] = {}
        self._legacy_profile_state_loaded = False
        self._scan_pool = QThreadPool.globalInstance()
        self._selected_version: int | None = None
        self._selected_is_active = False
        self._selected_profile_locked = False
        self._task_busy = False
        self._candidate_counts: dict[int, dict[str, int]] = {}
        self._symbol_catalog: dict[str, dict[str, object]] = {}
        self._graphic_discovery_catalog: dict[str, dict[str, object]] = {}
        # v2.18.115: remember explicit user removals from the discovery queue so a
        # save/reload cannot resurrect rows merely because old discovery metadata is
        # still attached to the Profile.  "ignored" is persisted by the existing
        # discovery_decisions schema and is only a local/Profile decision; it never
        # changes any remote business G or server symbol-library file.
        self._discovery_decisions: dict[str, str] = {}
        self._pending_standard_file_records: list[dict[str, object]] = []
        # The server element tree is a read-only catalog, independent of the
        # currently edited Profile.  It is refreshed from every remote .g file and
        # then used to enrich the editor without treating a business-G scan as a
        # prerequisite.
        self._server_catalog_records: dict[str, dict[str, object]] = {}
        # Physical server-file inventory kept separate from the parsed standard
        # catalog.  It includes duplicate relative paths and files that could not
        # be parsed, so the table can account for every remote .g file.
        self._server_file_inventory: list[dict[str, object]] = []
        # v2.18.196: keep the server inventory table visible.  The operator asked
        # to remove only the XML element-tag field, not the whole inventory.
        # The mature 20-column internal row schema is kept for compatibility with
        # downstream logic; the operator surface exposes only the useful inventory
        # columns and never shows the XML element-tag column.
        self._server_inventory_table_enabled = True
        self._server_catalog_ignored: set[str] = set()
        # v2.18.119: a fresh-rescan draft is isolated from the saved ACTIVE/GLOBAL
        # version until the operator explicitly saves it as V(N+1).  The saved
        # profile is never mutated merely by scanning business G files.
        self._rescan_prepare_mode = False
        self._rescan_draft_mode = False
        self._rescan_draft_base_name = ""
        self._rescan_draft_base_version: int | None = None
        self._rescan_draft_target_version: int | None = None
        help_title, help_html = APP_HELP["site_profile"]
        super().__init__(
            "服务器图元同步管理",
            "同步服务器图元并维护图元分类。",
            help_title,
            help_html,
            parent,
        )
        # Classification edits are local-first.  Editing a cell updates the in-memory
        # catalog immediately, then one short debounce persists all pending markers in
        # a worker.  The old path rewrote manifest.json + classification_markers.json
        # + sync_snapshot.json synchronously on the GUI thread for every keystroke,
        # which could freeze the entire window even though no network was involved.
        self._classification_marker_save_worker: FunctionWorker | None = None
        self._pending_classification_marker_updates: dict[tuple[str, str, str], str] = {}
        self._classification_marker_save_timer = QTimer(self)
        self._classification_marker_save_timer.setSingleShot(True)
        self._classification_marker_save_timer.setInterval(180)
        self._classification_marker_save_timer.timeout.connect(self._flush_classification_marker_updates)
        # Only while this process owns Admin, poll the tiny instance.json every
        # 10 seconds. This never syncs database/file-server/ID/symbol config.
        self._admin_ownership_timer = QTimer(self)
        self._admin_ownership_timer.setInterval(10_000)
        self._admin_ownership_timer.timeout.connect(self._renew_admin_lease)
        # Detailed rules intentionally live in Page Help/tooltips instead of the main
        # operator surface. Keep these established semantics explicit for maintenance:
        # - 服务器 element 目录是唯一标准源，解析成功的 .g 直接进入标准表。
        # - w×h、AlignCenter、Pins 会自动从服务器标准图元读取。
        # - 待检查业务 G 不参与 devref、尺寸、AlignCenter 或 pin 标准的生成。
        # - “检查图元标准”不修改 G；纠正仅生成 workspace 副本。
        # - 历史版本导出/恢复只读取本地冻结对象，绝不以服务器当前同名文件替代。

        standard_box = QGroupBox("服务器图元与分类")
        standard_layout = QVBoxLayout(standard_box)
        standard_layout.setContentsMargins(14, 18, 14, 12)
        standard_layout.setSpacing(10)

        self.active_profile_summary = QLabel("当前服务器图元目录：尚未同步")
        self.active_profile_summary.setObjectName("sectionCaption")
        self.active_profile_summary.setWordWrap(True)
        standard_layout.addWidget(self.active_profile_summary)


        # v2.18.171: configuration-administrator access is a global application
        # concern, not a symbol-sync-page action.  The visible entry lives in the
        # main-window sidebar.  Keep these legacy widgets in a permanently hidden
        # container because the mature async admin workflow still updates their text
        # internally while the sidebar consumes the new adminAccessChanged signal.
        self._legacy_access_container = QWidget(standard_box)
        self._legacy_access_container.setVisible(False)
        self.access_mode_label = QLabel(self._legacy_access_container)
        self.admin_owner_label = QLabel("当前管理员：检查中…", self._legacy_access_container)
        self.access_mode_button = QPushButton(self._legacy_access_container)
        self.access_mode_button.clicked.connect(self._toggle_admin_mode)
        self.change_admin_password_button = QPushButton("修改管理员密码", self._legacy_access_container)
        self.change_admin_password_button.clicked.connect(self._change_admin_password)


        manage_row = QHBoxLayout()
        self.profile_version_label = QLabel("当前标准")
        manage_row.addWidget(self.profile_version_label)
        self.profile_selector = WheelSafeComboBox()
        self.profile_selector.setMinimumContentsLength(42)
        self.profile_selector.currentIndexChanged.connect(self._profile_selection_changed)
        manage_row.addWidget(self.profile_selector, 1)
        self.set_global_button = QPushButton("设为当前标准")
        set_secondary(self.set_global_button)
        self.set_global_button.setToolTip("兼容旧配置的内部操作；当前服务器标准更新后会自动作为本地当前标准。")
        self.set_global_button.clicked.connect(self._set_selected_global_version)
        manage_row.addWidget(self.set_global_button)
        self.profile_manage_button = QPushButton("标准管理")
        set_secondary(self.profile_manage_button)
        self.profile_menu = QMenu(self.profile_manage_button)
        self.new_action = self.profile_menu.addAction("新建标准")
        self.scan_action = self.profile_menu.addAction("服务器标准图元（只读）")
        self.profile_menu.addSeparator()
        self.version_details_action = self.profile_menu.addAction("查看版本库详情")
        self.verify_version_action = self.profile_menu.addAction("验证版本完整性")
        self.export_version_action = self.profile_menu.addAction("导出该版本完整 element 目录")
        self.export_version_zip_action = self.profile_menu.addAction("导出该版本完整 element ZIP")
        self.profile_menu.addSeparator()
        self.restore_action = self.profile_menu.addAction("恢复为新的编辑版本")
        self.delete_history_action = self.profile_menu.addAction("删除选中历史版本")
        self.delete_action = self.profile_menu.addAction("删除整个标准（全部版本）")
        self.new_action.triggered.connect(self._new_profile)
        self.scan_action.triggered.connect(self._scan_samples)
        # The authoritative source is the read-only server element tree.  Keep the
        # legacy action object for compatibility with older signal paths, but do not
        # expose a local-upload workflow in the current page.
        self.scan_action.setVisible(False)
        self.version_details_action.triggered.connect(self._show_version_repository_details)
        self.verify_version_action.triggered.connect(self._verify_selected_version_repository)
        self.export_version_action.triggered.connect(lambda: self._export_selected_version_repository(zip_output=False))
        self.export_version_zip_action.triggered.connect(lambda: self._export_selected_version_repository(zip_output=True))
        self.restore_action.triggered.connect(self._restore_selected_version)
        self.delete_history_action.triggered.connect(self._delete_selected_history_version)
        self.delete_action.triggered.connect(self._delete_profile)
        self.profile_manage_button.setMenu(self.profile_menu)
        manage_row.addWidget(self.profile_manage_button)
        # The public workflow has one current server standard.  Keep the selector
        # and legacy management actions in memory for old profiles, but do not ask
        # operators to manage versions, GLOBAL pointers, locks or local snapshots.
        self.profile_version_label.setVisible(False)
        self.profile_selector.setVisible(False)
        self.set_global_button.setVisible(False)
        self.profile_manage_button.setVisible(False)
        standard_layout.addLayout(manage_row)

        self.version_switch_status = QLabel("")
        self.version_switch_status.setObjectName("infoBanner")
        self.version_switch_status.setWordWrap(True)
        self.version_switch_status.setVisible(False)
        standard_layout.addWidget(self.version_switch_status)
        self.version_switch_progress = SmoothProgressBar()
        self.version_switch_progress.setRange(0, 100)
        self.version_switch_progress.setTextVisible(False)
        self.version_switch_progress.setFixedHeight(8)
        self.version_switch_progress.setVisible(False)
        standard_layout.addWidget(self.version_switch_progress)


        form = QFormLayout()
        self.site_name = QLineEdit()
        self.site_name.setPlaceholderText("例如：Jeddah / Madinah / General")
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("例如：Jeddah Site Standard")
        form.addRow("适用范围", self.site_name)
        form.addRow("标准名称", self.profile_name)
        # These fields belong to the retired standard-version editor, not to the
        # remote catalog manager. Keep the values in memory for old profiles but
        # remove the empty editor rows from the operator surface.
        # Do not use QFormLayout.setRowVisible() here.  The Qt 6.11 build used by
        # this application can crash during the first show event after that method
        # hides a row.  Hiding the two row widgets keeps the same operator surface
        # and is safe across the supported PySide6 versions.
        for form_row in range(form.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                form_item = form.itemAt(form_row, role)
                form_widget = form_item.widget() if form_item is not None else None
                if form_widget is not None:
                    form_widget.setVisible(False)
        standard_layout.addLayout(form)

        self.lbs_combo = WheelSafeComboBox()
        self.breaker_combo = WheelSafeComboBox()
        self.normal_lbs_combo = WheelSafeComboBox()
        self.normal_breaker_combo = WheelSafeComboBox()
        self.ground_combo = WheelSafeComboBox()
        self.normal_ground_combo = WheelSafeComboBox()


        # v2.18.113: the shared read-only server library is the sole authoritative
        # source for standard symbols. The remote library is never written to.
        server_box = QGroupBox("服务器图元")
        server_layout = QVBoxLayout(server_box)
        server_layout.setContentsMargins(12, 16, 12, 10)
        server_layout.setSpacing(8)
        self.server_standard_enabled = QCheckBox("读取服务器 element 全部图元")
        self.server_standard_enabled.setChecked(
            self.user_settings.get_bool("site_profile/remote_symbol_library_enabled", True)
        )
        self.server_standard_enabled.toggled.connect(self._server_library_enabled_changed)
        server_layout.addWidget(self.server_standard_enabled)
        # The standard source is intentionally not an operator choice. Keep the
        # setting for backward-compatible persisted preferences, but force the
        # current workflow to use the server element tree.
        self.server_standard_enabled.blockSignals(True)
        self.server_standard_enabled.setChecked(True)
        self.server_standard_enabled.blockSignals(False)
        self.server_standard_enabled.setVisible(False)

        server_root_row = QHBoxLayout()
        server_root_row.addWidget(QLabel("图元库根目录"))
        self.server_symbol_root = QLineEdit(
            self.user_settings.get_value("site_profile/remote_symbol_library_root", "").strip()
        )
        self.server_symbol_root.setPlaceholderText(DEFAULT_REMOTE_SYMBOL_ROOT)
        self.server_symbol_root.setToolTip("服务器图元目录由“连接与环境”统一管理；本页只读显示并使用该目录。")
        self.server_symbol_root.setReadOnly(True)
        server_root_row.addWidget(self.server_symbol_root, 1)
        self.server_connection_button = QPushButton("连接设置")
        set_secondary(self.server_connection_button)
        self.server_connection_button.clicked.connect(self.connectionSettingsRequested.emit)
        server_root_row.addWidget(self.server_connection_button)
        self.server_sync_button = QPushButton("同步服务器图元信息")
        set_primary(self.server_sync_button)
        self.server_sync_button.setToolTip(
            "读取服务器 element 目录并同步本地图元信息；文件名不变时沿用本地图元和分类标记，同时提示服务器最新修改时间。"
        )
        # Reads are deliberately explicit: this page only synchronizes the
        # read-only remote catalog and never applies a standard version.
        self.server_sync_button.clicked.connect(
            lambda: self._start_server_symbol_sync(
                background=False, auto_bind=False, compare_profile=False
            )
        )
        server_root_row.addWidget(self.server_sync_button)
        self.server_apply_button = QPushButton("更新当前标准（已停用）")
        set_secondary(self.server_apply_button)
        self.server_apply_button.setToolTip("本页面不再维护或更新图元标准版本。")
        self.server_apply_button.clicked.connect(self._save_profile)
        self.server_apply_button.setEnabled(False)
        self.server_apply_button.setVisible(False)
        server_root_row.addWidget(self.server_apply_button)
        self.server_new_version_button = QPushButton("基于当前版本创建新版本")
        set_secondary(self.server_new_version_button)
        self.server_new_version_button.setVisible(False)
        self.server_new_version_button.setEnabled(False)
        self.server_new_version_button.clicked.connect(self._create_next_version_from_server)
        server_root_row.addWidget(self.server_new_version_button)
        self.server_cache_button = QPushButton("打开本地缓存")
        set_secondary(self.server_cache_button)
        self.server_cache_button.clicked.connect(self._open_server_symbol_cache)
        server_root_row.addWidget(self.server_cache_button)
        self.export_classification_button = QPushButton("导出 JSON")
        set_secondary(self.export_classification_button)
        self.export_classification_button.setToolTip(
            "导出当前本机已保存的分类标记 JSON；不会上传服务器，也不包含服务器账号、密码或图元文件内容。"
        )
        self.export_classification_button.clicked.connect(self._export_classification_markers)
        self.import_classification_button = QPushButton("导入 JSON")
        set_secondary(self.import_classification_button)
        self.import_classification_button.setToolTip(
            "导入 JSON 并覆盖本机分类；不会修改中央配置。"
        )
        self.import_classification_button.clicked.connect(self._import_classification_markers)
        server_layout.addLayout(server_root_row)
        classification_row = QHBoxLayout()
        self.local_classification_label = QLabel("本地分类")
        self.local_classification_label.setObjectName("sectionCaption")
        classification_row.addWidget(self.local_classification_label)
        self.save_classification_button = QPushButton("保存到本地")
        set_primary(self.save_classification_button)
        self.save_classification_button.setToolTip(
            "把当前分类保存到本机；不会修改中央配置。"
        )
        self.save_classification_button.clicked.connect(self._save_classification_markers)
        classification_row.addWidget(self.save_classification_button)
        classification_row.addWidget(self.export_classification_button)
        classification_row.addWidget(self.import_classification_button)
        classification_row.addStretch(1)
        server_layout.addLayout(classification_row)

        central_row = QHBoxLayout()
        server_classification_label = QLabel("分类配置")
        server_classification_label.setObjectName("sectionCaption")
        central_row.addWidget(server_classification_label)
        initial_repo_dir = CentralRepositorySettings(self.user_settings).load().config_dir
        self.central_classification_path = QLineEdit(f"{initial_repo_dir}/symbol_classification.json")
        self.central_classification_path.setReadOnly(True)
        self.central_classification_path.setToolTip(
            "所有软件统一读取这一份 symbol_classification.json；服务器 element 图元目录仍保持严格只读。"
        )
        central_row.addWidget(self.central_classification_path, 1)
        # Keep the legacy constructor strings for backward-compatible source
        # checks, but expose the same local/central action wording used by the
        # other centrally managed configuration modules.
        self.central_sync_button = QPushButton("从服务器同步")
        self.central_sync_button.setText("从中央同步")
        set_primary(self.central_sync_button)
        self.central_sync_button.setToolTip(
            "下载中央 symbol_classification.json，并覆盖本机分类缓存；启动时不会自动同步。"
        )
        self.central_sync_button.clicked.connect(self._sync_central_classification)
        central_row.addWidget(self.central_sync_button)
        self.central_publish_button = QPushButton("上传到服务器")
        self.central_publish_button.setText("发布到中央")
        set_primary(self.central_publish_button)
        self.central_publish_button.setToolTip(
            "仅中央管理员可用：保存本地后发布为中央正式分类。"
        )
        self.central_publish_button.clicked.connect(self._publish_central_classification)
        central_row.addWidget(self.central_publish_button)
        server_layout.addLayout(central_row)

        self.central_classification_status = QLabel("分类状态：默认自动打开本机缓存 · 中央配置不会自动读取")
        self.central_classification_status.setWordWrap(True)
        self.central_classification_status.setObjectName("mutedText")
        server_layout.addWidget(self.central_classification_status)
        self._refresh_classification_cache_status()

        self.server_library_progress = SmoothProgressBar()
        self.server_library_progress.setRange(0, 100)
        self.server_library_progress.setValue(0)
        self.server_library_progress.setFormat("同步服务器图元信息 %p%")
        self.server_library_progress.setVisible(False)
        server_layout.addWidget(self.server_library_progress)
        self.server_library_status = QLabel("图元状态：尚未同步")
        self.server_library_status.setWordWrap(True)
        self.server_library_status.setObjectName("mutedText")
        server_layout.addWidget(self.server_library_status)
        standard_layout.addWidget(server_box)

        # v2.18.176: no automatic remote timers exist. Administrator status,
        # central configuration and server-symbol refresh are all explicit actions.

        # The normal catalog-manager page does not construct the retired business-G
        # discovery panel at all.  Hidden QWidget trees still cost substantial GUI-
        # thread time to create, connect and polish; deferring them is essential for
        # a fast first paint.  Legacy/test callers that opt out of deferred catalog
        # restore retain the original panel unchanged.
        discovery_box = None
        if not self._defer_catalog_restore:
            discovery_box = QGroupBox("业务 G 使用情况分析（兼容隐藏）")
            discovery_layout = QVBoxLayout(discovery_box)
            discovery_layout.setContentsMargins(12, 16, 12, 10)
            discovery_layout.setSpacing(8)
            discovery_note = QLabel(
                "本页面不使用业务 G 建立服务器标准。该旧分析区仅保留兼容代码，不作为图元标准来源。"
            )
            discovery_note.setWordWrap(True)
            discovery_note.setObjectName("mutedText")
            discovery_layout.addWidget(discovery_note)

            # v2.18.119: two distinct workflows are intentionally exposed.  Ordinary
            # scan updates the current editable discovery draft; fresh rescan creates an
            # isolated V(N+1) DRAFT from the selected business G set, using the scan as
            # the source of truth while inheriting only matching prior classifications /
            # authoritative bindings.  GLOBAL never moves automatically.
            rescan_version_row = QHBoxLayout()
            self.rescan_new_version_button = QPushButton("全量重新扫描 → 新版本草稿")
            set_secondary(self.rescan_new_version_button)
            self.rescan_new_version_button.setToolTip(
                "从当前 ACTIVE 标准创建下一版本草稿：重新读取所选业务 G；本次扫描不存在的旧候选不会带入。"
                "匹配到的旧图元可继承人工分类/标准绑定，保存后才生成新的 ACTIVE；GLOBAL 不自动切换。"
            )
            self.rescan_new_version_button.clicked.connect(self._prepare_fresh_rescan_version)
            self.cancel_rescan_draft_button = QPushButton("取消新版本草稿")
            set_secondary(self.cancel_rescan_draft_button)
            self.cancel_rescan_draft_button.setVisible(False)
            self.cancel_rescan_draft_button.clicked.connect(self._cancel_fresh_rescan_draft)
            rescan_version_row.addWidget(self.cancel_rescan_draft_button)
            self.rescan_version_hint = QLabel(
                "普通扫描更新当前候选；全量重扫创建下一版本草稿。"
            )
            self.rescan_version_hint.setObjectName("mutedText")
            self.rescan_version_hint.setWordWrap(True)
            rescan_version_row.addWidget(self.rescan_version_hint, 1)
            discovery_layout.addLayout(rescan_version_row)

            # v2.18.107: the whole graphic-G discovery input area is one visibility unit.
            # When the ACTIVE standard is locked, hide the source mode/SSH/file list as
            # well as its scan/filter actions. Unlocking restores this panel immediately.
            self.discovery_input_panel = QWidget()
            discovery_input_layout = QVBoxLayout(self.discovery_input_panel)
            discovery_input_layout.setContentsMargins(0, 0, 0, 0)
            discovery_input_layout.setSpacing(8)
            self.discovery_source = InputSourceSelector(
                default_directory=default_workspace() / "input",
                file_filter="G Files (*.sln.pic.g *.g)",
                file_tooltip="选择一张用于发现图元候选的图形 G 文件。",
                directory_tooltip="选择包含大量图形 G 的目录，批量统计其中使用到的图元。",
                settings_prefix="site_profile_discovery_source",
                settings_service=self.user_settings,
            )
            discovery_input_layout.addWidget(self.discovery_source)
            discovery_actions = QHBoxLayout()
            self.discovery_scan_button = QPushButton("分析业务 G 使用情况")
            self.discovery_scan_button.setToolTip(
                "普通模式：更新当前可编辑候选；新版本草稿模式：重新读取所选业务 G 并生成 V(N+1) DRAFT。"
                "两种模式都只读业务 G，不会把业务 G 当作标准图元。"
            )
            self.discovery_scan_button.clicked.connect(self._scan_graphic_symbol_candidates)
            discovery_actions.addWidget(self.discovery_scan_button)
            # v2.18.119: keep the full-rescan/new-version action beside the ordinary scan.
            # The previous placement above the source list was easy to miss once the page
            # was scrolled to the selected G files/table, which made users accidentally
            # run an ordinary scan and wonder why the saved candidate set stayed unchanged.
            discovery_actions.addWidget(self.rescan_new_version_button)
            self.discovery_filter = QLineEdit()
            self.discovery_filter.setPlaceholderText("筛选表格：设备类型 / XML / devref / 文件名")
            self.discovery_filter.textChanged.connect(self._apply_standard_table_filter)
            discovery_actions.addWidget(self.discovery_filter, 1)
            self.pending_only_checkbox = QCheckBox("只看待确认服务器匹配")
            self.pending_only_checkbox.toggled.connect(self._apply_standard_table_filter)
            discovery_actions.addWidget(self.pending_only_checkbox)
            discovery_input_layout.addLayout(discovery_actions)
            # v2.18.112: discovery progress lives directly under the scan action so it
            # is visible immediately when scanning starts, rather than below the wide
            # standard table where the user may not see it until much later.
            self.scan_progress = SmoothProgressBar()
            self.scan_progress.setRange(0, 100)
            self.scan_progress.setValue(0)
            self.scan_progress.setFormat("扫描图形 G 图元 %p%")
            self.scan_progress.setToolTip("扫描业务/图形 G 并统计图元候选；SSH 下载与本地解析都在后台线程执行。")
            self.scan_progress.setVisible(False)
            discovery_input_layout.addWidget(self.scan_progress)
            discovery_layout.addWidget(self.discovery_input_panel)
            self.discovery_locked_note = QLabel("服务器图元库已作为唯一标准源；本页面不提供图元上传或图元扫描。")
            self.discovery_locked_note.setWordWrap(True)
            self.discovery_locked_note.setObjectName("mutedText")
            self.discovery_locked_note.setVisible(False)
            discovery_layout.addWidget(self.discovery_locked_note)
            standard_layout.addWidget(discovery_box)
            discovery_box.setVisible(False)

        custom_actions = QHBoxLayout()
        self.upload_standard_button = QPushButton("为选中图元上传 / 更新标准 G")
        self.upload_standard_button.clicked.connect(self._scan_samples)
        custom_actions.addWidget(self.upload_standard_button)
        self.confirm_server_button = QPushButton("确认选中服务器图元")
        set_secondary(self.confirm_server_button)
        self.confirm_server_button.setToolTip("将当前服务器目录中已解析的图元确认加入编辑中的标准版本；保存后才会进入版本库。")
        self.confirm_server_button.clicked.connect(self._confirm_selected_server_symbol)
        custom_actions.addWidget(self.confirm_server_button)
        # v2.18.105: no fixed SMART/NORMAL role pairs are pre-created. Scope is
        # learned/suggested from the graphic G candidate itself, then confirmed on
        # that generic row. Keep a hidden compatibility object so archived profile
        # code paths remain harmless without exposing the obsolete pairing control.
        self.share_pair_checkbox = QCheckBox("SMART / NORMAL 共用此标准")
        self.share_pair_checkbox.setVisible(False)
        self.share_pair_checkbox.toggled.connect(self._share_pair_toggled)
        self.add_custom_button = QPushButton("手动添加图元（可选）")
        set_secondary(self.add_custom_button)
        self.add_custom_button.clicked.connect(self._add_custom_standard)
        custom_actions.addWidget(self.add_custom_button)
        self.delete_custom_button = QPushButton("删除选中图元")
        set_secondary(self.delete_custom_button)
        self.delete_custom_button.clicked.connect(self._delete_selected_custom_standard)
        custom_actions.addWidget(self.delete_custom_button)
        # Standard rows are sourced exclusively from the server catalog. Keep the
        # legacy widgets for compatibility with saved layouts and signal paths, but
        # do not expose local upload/manual mutation actions.
        for button in (
            self.upload_standard_button,
            self.confirm_server_button,
            self.add_custom_button,
            self.delete_custom_button,
        ):
            button.setVisible(False)
            button.setEnabled(False)
        custom_actions.addStretch(1)
        self.lock_standard_button = QPushButton("锁定当前版本")
        set_secondary(self.lock_standard_button)
        self.lock_standard_button.setToolTip("锁定后当前 ACTIVE 标准版本不可修改；服务器有变化时只提示，不会自动应用。")
        self.lock_standard_button.clicked.connect(self._toggle_profile_lock)
        self.lock_standard_button.setVisible(False)
        custom_actions.addWidget(self.lock_standard_button)
        standard_layout.addLayout(custom_actions)

        # Operator inventory.  Keep the proven internal row schema, but show a
        # compact table modeled on Distribution Model Manager: definition file,
        # geometry, source, classification and status.
        self.standard_table_overview = QLabel("服务器图元目录：尚未同步")
        self.standard_table_overview.setObjectName("sectionCaption")
        self.standard_table_overview.setWordWrap(True)
        self.standard_table_overview.setVisible(True)
        standard_layout.addWidget(self.standard_table_overview)

        standard_search_row = QHBoxLayout()
        self.standard_table_search_label = QLabel("筛选")
        self.standard_table_search_label.setVisible(True)
        standard_search_row.addWidget(self.standard_table_search_label)
        self.standard_table_search = QLineEdit()
        self.standard_table_search.setPlaceholderText("输入图元文件名、分类标记、状态或服务器相对路径")
        self.standard_table_search.setClearButtonEnabled(True)
        self.standard_table_search.setToolTip("只筛选本地同步目录，不会重新读取或修改服务器文件。")
        self.standard_table_search.textChanged.connect(self._apply_standard_table_filter)
        self.standard_table_search.setVisible(True)
        standard_search_row.addWidget(self.standard_table_search, 1)

        # v2.18.208: expose the existing cached-symbol export as a single toolbar
        # action instead of one QPushButton per table row.  The table normally has
        # around 200 rows; cell widgets are noticeably more expensive on Windows
        # and would reintroduce the startup/layout cost we removed in v2.18.198+.
        self.standard_download_selected_button = QPushButton("下载选中图元")
        self.standard_download_selected_button.setEnabled(False)
        self.standard_download_selected_button.setToolTip(
            "先在下方表格中选择一个图元。下载只复制本机图元缓存，不会修改服务器。"
        )
        self.standard_download_selected_button.clicked.connect(self._download_selected_standard)
        standard_search_row.addWidget(self.standard_download_selected_button)
        standard_layout.addLayout(standard_search_row)

        # v2.18.203: the local cache is restored asynchronously.  Do not expose an
        # empty native QTableWidget while the worker is parsing the AppData JSON;
        # on Windows that empty framed viewport appears as a short-lived "popup/box"
        # before the 200 cached rows arrive.  Keep a borderless status line in its
        # place and reveal the fully populated table atomically.
        self.standard_table_loading = QLabel("正在加载本地图元缓存…")
        self.standard_table_loading.setObjectName("mutedText")
        self.standard_table_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.standard_table_loading.setMinimumHeight(380)
        self.standard_table_loading.setVisible(self._defer_catalog_restore)
        standard_layout.addWidget(self.standard_table_loading)

        self.standard_table = QTableWidget(0, 20)
        self.standard_table.setVisible(not self._defer_catalog_restore)
        self.standard_table.setHorizontalHeaderLabels(
            [
                "来源", "业务类型 / 设备类型", "内部元素类型", "图元定义文件",
                "主体 ID", "w×h", "AlignCenter", "Pins", "标准来源", "状态",
                "图元用途", "设备子类型", "设备层级", "扫描图元 G 文件全名",
                "图形 G 发现 devref", "发现次数", "样本位置",
                "下载图元", "分类标记", "服务器相对路径",
            ]
        )
        # The server-update page is an operator view, not a topology/discovery
        # analysis screen. Keep these fields in the internal row model for
        # compatibility, but do not expose them in the table.
        # Keep the internal row schema stable for cache/import compatibility.
        # XML element type (column 2) is intentionally removed from the operator
        # surface.  The relative path is displayed in column 3, so the duplicate
        # path column 19 is hidden as well.
        self._hidden_standard_columns = {0, 1, 2, 4, 10, 11, 12, 13, 14, 15, 16, 17, 19}
        for column in self._hidden_standard_columns:
            self.standard_table.setColumnHidden(column, True)
        self.standard_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.standard_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.standard_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        # v2.18.112: use the vertical header as the explicit row serial-number
        # gutter.  This avoids shifting the mature 17-column business schema while
        # still giving every displayed symbol a stable, easy-to-read sequence.
        vertical_header = self.standard_table.verticalHeader()
        vertical_header.setVisible(True)
        vertical_header.setMinimumWidth(50)
        vertical_header.setDefaultSectionSize(34)
        vertical_header.setMinimumSectionSize(34)
        vertical_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.standard_table.setObjectName("symbolStandardTable")
        self.standard_table.setShowGrid(True)
        self.standard_table.setAlternatingRowColors(True)
        # v2.18.105: locating is no longer user-configured.  The candidate discovered
        # from the business G and the authoritative uploaded symbol G provide enough
        # information for the program to derive the internal locator automatically.
        # Keep every visible column content-sized so long symbol-G filenames/devrefs
        # are shown in full; users can inspect the wide table with horizontal scroll.
        self.standard_table.setStyleSheet(
            "QTableWidget#symbolStandardTable { padding: 0px; }"
            # The application-wide QLineEdit theme uses 7px vertical padding. Qt's
            # built-in item editor inherits that style, while inventory rows are
            # intentionally compact; the result is a clipped one-line editor when
            # the operator edits column 18 (classification marker). Keep only the
            # in-table editor compact so the whole value and caret remain visible.
            "QTableWidget#symbolStandardTable QLineEdit { "
            "margin: 1px; border: 1px solid #0c8f69; border-radius: 3px; "
            "padding: 1px 6px; background: #ffffff; }"
            "QTableWidget#symbolStandardTable QComboBox { margin: 0px; border: none; border-radius: 0px; padding: 3px 24px 3px 6px; }"
            "QTableWidget#symbolStandardTable QComboBox::drop-down { border: none; width: 22px; }"
        )
        apply_graphics_table_selection_style(self.standard_table)
        self.standard_table.itemSelectionChanged.connect(self._standard_row_selection_changed)
        self.standard_table.itemChanged.connect(self._classification_marker_changed)
        header = self.standard_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsMovable(False)
        header.setTextElideMode(Qt.TextElideMode.ElideNone)
        header.setMinimumSectionSize(72)
        # v2.18.198: follow the stable Distribution Model Manager table pattern.
        # Do not keep QHeaderView in ResizeToContents while rows are inserted and do
        # not move sections during first-show.  Both operations cause repeated native
        # size-hint/layout work on Windows and were responsible for the white/frozen
        # startup window when the cached inventory was restored.  Fixed/interactive
        # widths are applied once after population; the horizontal scrollbar exposes
        # long values without any continuous content scan.
        for column in range(self.standard_table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        self.standard_table.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.standard_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.standard_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # Match the ID-rule table behavior: every field keeps its readable natural
        # width, and a table-local horizontal scrollbar is always available when
        # the viewport cannot show all content at once.
        self.standard_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.standard_table.setMinimumHeight(380)
        # Listen to the real table viewport, not only the outer page. Qt layouts can
        # change the viewport width without delivering a resizeEvent to this page;
        # that was the reason the columns could occupy only half of the available
        # table width after first show. The event filter only reapplies cached widths
        # and never scans table rows.
        self.standard_table.viewport().installEventFilter(self)
        # This inventory intentionally does not use the generic responsive-table
        # event filter: that helper samples all 20 internal columns on every show/
        # resize.  Only seven columns are visible here, so stable explicit widths are
        # substantially cheaper and match the reference application's approach.
        # v2.18.105 continues the discovery-driven standard library.  There are no
        # built-in/system rows and no user-entered locator rule/condition columns.
        self._standard_specs = []
        self._apply_fast_inventory_column_widths()
        standard_layout.addWidget(self.standard_table)

        save_row = QHBoxLayout()
        self.save_button = QPushButton("手动更新当前标准")
        self.save_button.setToolTip(
            "只有点击此按钮才会把已经读取的服务器标准快照写入本地标准；不会上传或修改服务器图元。"
        )
        self.save_button.clicked.connect(self._save_profile)
        self.save_button.setVisible(False)
        save_row.addWidget(self.save_button)
        self.profile_status = QLabel("")
        self.profile_status.setObjectName("mutedText")
        self.profile_status.setWordWrap(True)
        self.profile_status.setVisible(False)
        save_row.addWidget(self.profile_status, 1)
        standard_layout.addLayout(save_row)

        self.scan_summary = QLabel("尚未同步服务器图元目录。")
        self.scan_summary.setObjectName("mutedText")
        self.scan_summary.setWordWrap(True)
        standard_layout.addWidget(self.scan_summary)

        # v2.18.239: first activation of this lazy page is now page-level atomic.
        # The old implementation hid only the QTableWidget during AppData restore,
        # while the surrounding QGroupBox/form frames could still receive one paint
        # before the cached inventory finished hydrating. On Windows that appears as
        # several empty boxes flashing for a fraction of a second when navigating
        # from ID Check & Repair to Server Symbol Sync Management. Keep the complete
        # server-catalog panel hidden until the local cache is fully ready, and show
        # only one borderless status line in the meantime.
        self.server_catalog_box = standard_box
        self.catalog_page_loading = QLabel("正在加载本地图元缓存…")
        self.catalog_page_loading.setObjectName("mutedText")
        self.catalog_page_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.catalog_page_loading.setMinimumHeight(420)
        self.catalog_page_loading.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.catalog_page_loading.setVisible(self._defer_catalog_restore)
        if self._defer_catalog_restore:
            self.server_catalog_box.setVisible(False)
        self.layout.addWidget(self.server_catalog_box)
        self.layout.addWidget(self.catalog_page_loading)

        # Likewise, the retired consistency-check input/task panels are not part of
        # Server Symbol Sync Management.  Construct them only for an explicit legacy
        # page instance; the public page keeps the same backend methods but avoids
        # building two InputSourceSelectors, remote-file tables and a TaskPanel.
        if not self._defer_catalog_restore:
            source_box = QGroupBox("待检查 G 文件")
            source_layout = QVBoxLayout(source_box)
            source_layout.setContentsMargins(14, 18, 14, 12)
            source_layout.setSpacing(10)
            source_note = QLabel(
                "选择待检查 G；服务器源文件只读，程序只下载本地快照，检查/纠正结果写入 workspace。"
            )
            source_note.setWordWrap(True)
            source_note.setObjectName("mutedText")
            source_layout.addWidget(source_note)
            self.source = InputSourceSelector(
                default_directory=default_workspace() / "input",
                file_filter="G Files (*.sln.pic.g *.g)",
                file_tooltip="选择一张需要按 ACTIVE 标准检查的业务 G 文件。",
                directory_tooltip="选择包含需要按 ACTIVE 标准检查的业务 G 文件目录。",
                settings_prefix="site_profile_source",
                settings_service=self.user_settings,
            )
            source_layout.addWidget(self.source)

            output_row = QHBoxLayout()
            output_row.addWidget(QLabel("输出目录（workspace）"))
            self.output_path = PathRow(
                directory=True,
                dialog_title="服务器图元更新检查输出目录",
                recent_directory_key="recent_paths/site_profile/output_directory",
                persistent_path_key="site_profile/output_directory",
                default_path=default_workspace() / "runs" / "smart-profile",
                location_name="服务器图元更新检查输出目录",
                settings_service=self.user_settings,
            )
            configure_managed_output(self.output_path, "smart-profile")
            output_row.addWidget(self.output_path, 1)
            source_layout.addLayout(output_row)

            self.layout.addWidget(source_box)

            apply_box = QGroupBox("标准一致性检查与纠正")
            apply_layout = QVBoxLayout(apply_box)
            apply_layout.setContentsMargins(14, 18, 14, 12)
            apply_layout.setSpacing(10)

            self.current_profile_label = QLabel("当前全局执行标准：未选择")
            self.current_profile_label.setObjectName("sectionCaption")
            self.current_profile_label.setWordWrap(True)
            self.current_profile_label.setVisible(False)
            apply_layout.addWidget(self.current_profile_label)

            execute_note = QLabel(
                "检查只读；纠正仅生成 workspace 副本，不覆盖源 G。这里仅处理标准图元自身的类型、devref、尺寸、Pin 几何和设备锚点；"
                "不负责全图拓扑判定，不删除或重画 ConnectLine/FeedLine/Bus，也不执行全图拓扑分析。"
            )
            execute_note.setWordWrap(True)
            execute_note.setObjectName("mutedText")
            apply_layout.addWidget(execute_note)

            workflow_row = QHBoxLayout()
            workflow_note = QLabel("后续处理：")
            workflow_note.setObjectName("mutedText")
            workflow_row.addWidget(workflow_note)
            self.orthogonalize_button = QPushButton("进入线路正交化")
            set_secondary(self.orthogonalize_button)
            self.orthogonalize_button.setToolTip(
                "进入线路正交化，执行线路横平竖直、连接点对齐和安全重画。"
            )
            self.orthogonalize_button.clicked.connect(self.orthogonalizeRequested.emit)
            workflow_row.addWidget(self.orthogonalize_button)
            workflow_row.addStretch(1)
            apply_layout.addLayout(workflow_row)

            self.result_summary = QLabel("尚未执行服务器图元更新检查。")
            self.result_summary.setObjectName("mutedText")
            self.result_summary.setWordWrap(True)
            apply_layout.addWidget(self.result_summary)

            self.task = TaskPanel()
            # v2.18.85: symbol-standard inspection/correction always stays in determinate
            # v2.18.85 is rebased directly from v2.18.82.  Keep the exact 0~100
            # determinate style, but smooth only the display-side repaint cadence so
            # queued worker progress does not make the bar flash/jump visually.
            self.task.set_live_progress_enabled(False)
            self.task.set_smooth_progress_enabled(True)
            self.task.progress.setToolTip("服务器图元更新检查/纠正始终以 0~100% 百分比样式显示，并平滑递增；后台真实进度只更新目标值，不会造成进度条闪烁或倒退。")
            self.task.set_result_dialogs_enabled(False)
            self.task.run_button.hide()
            self.check_button = QPushButton("检查图元标准")
            self.check_button.clicked.connect(self._check_profile)
            self.task.buttons_layout.insertWidget(0, self.check_button)
            self.correct_button = QPushButton("生成标准纠正副本")
            set_secondary(self.correct_button)
            self.correct_button.clicked.connect(self._correct_profile)
            self.task.buttons_layout.insertWidget(1, self.correct_button)
            self.open_report_button = QPushButton("查看检查报告")
            set_secondary(self.open_report_button)
            self.open_report_button.setEnabled(False)
            self.open_report_button.clicked.connect(self._open_report)
            self.task.buttons_layout.insertWidget(2, self.open_report_button)
            self.task.open_button.setText("打开结果目录")
            self.toggle_log_button = QPushButton("显示日志")
            set_secondary(self.toggle_log_button)
            self.toggle_log_button.setCheckable(True)
            self.toggle_log_button.toggled.connect(self._toggle_log)
            self.task.buttons_layout.insertWidget(4, self.toggle_log_button)
            self.task.log_view.setVisible(False)
            self.task.clear_button.setVisible(False)
            self.task.resultReceived.connect(self._on_processing_result)
            self.task.busyChanged.connect(self._task_busy_changed)
            apply_layout.addWidget(self.task)
            self.layout.addWidget(apply_box, 1)

            # Workflow order: read/maintain the server standard catalog -> choose a
            # local or server-snapshotted G for check/correction.
            for widget in (source_box, standard_box, apply_box):
                self.layout.removeWidget(widget)
            self.layout.insertWidget(1, standard_box)
            self.layout.insertWidget(2, source_box)
            self.layout.insertWidget(3, apply_box)

            # This page is now a catalog manager. The legacy business-G input and
            # standard inspection/correction panels remain constructed only so old
            # persisted profiles and signal paths can still be read safely.
            source_box.setVisible(False)
            apply_box.setVisible(False)
            discovery_box.setVisible(False)

        # v2.18.195: once the retired inventory table and compatibility panels are
        # hidden, the page's preferred height becomes smaller than the QScrollArea
        # viewport.  Without an explicit top anchor Qt distributes the spare height
        # into the remaining PageHeader / standard_box widgets, which creates the
        # huge blank gaps seen after v2.18.194.  Keep this page compact like the
        # Distribution Model Manager: header and server controls stay at their size
        # hints and all unused viewport space is consumed below them.  This is a
        # Keep the page top-aligned while allowing the restored inventory table to
        # use its requested height.  Server sync, classification, Admin and catalog
        # logic are untouched.
        header_widget = self.layout.itemAt(0).widget()
        if header_widget is not None:
            header_widget.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
            )
        standard_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.addStretch(1)

        # v2.18.200: this visible page is a server-catalog/classification manager.
        # Do NOT enumerate/hydrate the retired Profile version repository during
        # normal startup.  load_profile_versions() can hydrate many historical
        # standard files and was the largest LOCAL-only startup stall.  The legacy
        # profile state is loaded only if an old compatibility action explicitly
        # needs it.  MainWindow passes defer_catalog_restore=True and the catalog
        # itself is restored asynchronously after the page has painted.
        if not self._defer_catalog_restore:
            self._reload_profiles(
                defer_selection=True,
                load_catalog=False,
            )
            self._legacy_profile_state_loaded = True
            if hasattr(self, "server_library_status"):
                self.server_library_status.setText("正在自动打开本地图元缓存…")
            restored = self._restore_cached_server_sync()
            if not restored and hasattr(self, "server_library_status"):
                self.server_library_status.setText(
                    "本机尚无可恢复的图元缓存；不会自动访问服务器。"
                )
        self._refresh_access_controls()
        QTimer.singleShot(0, self._finish_initial_load)

    def on_page_activated(self) -> None:
        """Restore the LOCAL server-symbol cache without exposing half-built UI.

        Snapshot JSON parsing still runs in a worker and never performs SSH/Oracle/
        central access here.  During the very first activation the entire catalog
        panel stays hidden behind one borderless local-loading label.  The panel is
        revealed only after the cached rows and final column widths are ready.
        """
        if not self._catalog_restore_pending or self._catalog_restore_started:
            return
        self._catalog_restore_started = True
        self._set_catalog_page_loading_state(True)
        if hasattr(self, "server_library_status"):
            self.server_library_status.setText("正在读取本地图元缓存…")
        # Yield exactly one event loop so the borderless placeholder paints before
        # local JSON work starts. There is no reason to expose the real panel first.
        QTimer.singleShot(0, self._restore_catalog_after_activation)

    def _restore_catalog_after_activation(self) -> None:
        if self._local_catalog_restore_worker is not None:
            return
        try:
            cfg = self._server_library_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
        except Exception:
            host, root = "", ""
        if not host or not root:
            self._catalog_restore_pending = False
            self._catalog_restore_started = False
            self._set_local_catalog_loading_state(False)
            self._set_catalog_page_loading_state(False)
            if hasattr(self, "server_library_status"):
                self.server_library_status.setText("本机尚未配置图元缓存位置；不会自动访问服务器。")
            return

        def load_local_snapshot(log, progress):
            progress(5)
            payload = RemoteSymbolLibraryService().load_cached_sync_snapshot(host=host, root=root)
            progress(100)
            return payload

        worker = FunctionWorker(load_local_snapshot)
        self._local_catalog_restore_worker = worker
        worker.signals.result.connect(self._on_local_catalog_restore_result)
        worker.signals.error.connect(self._on_local_catalog_restore_error)
        worker.signals.finished.connect(self._on_local_catalog_restore_finished)
        self._scan_pool.start(worker)

    def _set_catalog_page_loading_state(self, loading: bool) -> None:
        """Atomically swap the whole catalog panel and its borderless placeholder.

        This is intentionally broader than ``_set_local_catalog_loading_state``:
        Windows can paint QGroupBox/QLineEdit/table frames independently, so hiding
        only the table is not enough to prevent the first-navigation flash.
        """
        if hasattr(self, "catalog_page_loading"):
            self.catalog_page_loading.setVisible(bool(loading))
        if hasattr(self, "server_catalog_box"):
            self.server_catalog_box.setVisible(not loading)

    def _set_local_catalog_loading_state(self, loading: bool, *, reveal_table: bool = True) -> None:
        """Switch the inner table placeholder/table during local-cache restore.

        Automatic AppData restore must never create a QMessageBox/QProgressDialog.
        The outer catalog panel remains hidden on first activation until the table
        has been completely hydrated and measured.
        """
        if hasattr(self, "standard_table_loading"):
            self.standard_table_loading.setVisible(bool(loading))
        if hasattr(self, "standard_table") and reveal_table:
            self.standard_table.setVisible(not loading)

    def _on_local_catalog_restore_result(self, payload: object) -> None:
        data = dict(payload) if isinstance(payload, dict) else {}
        inventory = data.get("server_file_records", [])
        if not isinstance(inventory, list) or not inventory:
            self._set_local_catalog_loading_state(False)
            self._set_catalog_page_loading_state(False)
            if hasattr(self, "server_library_status"):
                self.server_library_status.setText("本机尚无可恢复的图元缓存；不会自动访问服务器。")
            return
        data["cached_restore"] = True
        self._apply_server_library_payload(data, auto_bind=False, compare_profile=False)
        marked = sum(
            1 for row in self._server_file_inventory
            if str(row.get("classification_marker", row.get("category_marker", "")) or "").strip()
        )
        if hasattr(self, "server_library_status"):
            self.server_library_status.setText(
                f"已读取本机 AppData 缓存：{len(self._server_file_inventory)} 个图元文件，"
                f"分类标记 {marked} 个；正在分批显示，本次未访问服务器。"
            )

    def _on_local_catalog_restore_error(self, details: object) -> None:
        self._set_local_catalog_loading_state(False)
        self._set_catalog_page_loading_state(False)
        if hasattr(self, "server_library_status"):
            self.server_library_status.setText("本地图元缓存读取失败；不会自动访问服务器。")

    def _on_local_catalog_restore_finished(self) -> None:
        self._local_catalog_restore_worker = None
        self._catalog_restore_pending = False
        self._catalog_restore_started = False
        # Normal cached inventory rendering keeps _inventory_atomic_reveal=True
        # until _finish_inventory_table_render().  Any other terminal path must
        # never leave the operator stuck behind the local-loading placeholder.
        if not getattr(self, "_inventory_atomic_reveal", False):
            self._set_catalog_page_loading_state(False)

    def _finish_initial_load(self) -> None:
        """Complete lightweight page state after the main window is visible."""
        self._refresh_local_storage_summary()
        self._refresh_access_controls()
        self._update_action_state()
        # v2.18.174: startup is strictly local-only. Do not read instance.json or
        # any other central configuration here. Remote central configuration is
        # contacted only by an explicit operator action such as “从服务器同步”,
        # “发布到中央”, or opening the global configuration-access dialog.

    def _schedule_inventory_width_update(self) -> None:
        if not hasattr(self, "standard_table"):
            return
        if getattr(self, "_inventory_width_update_pending", False):
            return
        self._inventory_width_update_pending = True

        def apply_widths() -> None:
            self._inventory_width_update_pending = False
            self._apply_fast_inventory_column_widths()

        QTimer.singleShot(0, apply_widths)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._schedule_inventory_width_update()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        # The table viewport can be resized by the layout after the page itself has
        # already reached its final geometry. Refit from cached natural widths so the
        # seven operator fields always consume the whole usable table width.
        if (
            hasattr(self, "standard_table")
            and watched is self.standard_table.viewport()
            and event.type() in (QEvent.Type.Resize, QEvent.Type.Show)
        ):
            self._schedule_inventory_width_update()
        return super().eventFilter(watched, event)

    def _ensure_machine_id(self) -> str:
        """Create the machine id only for an explicit administrator action."""
        machine_id = self.user_settings.get_value("access_control/machine_id", "").strip()
        if not machine_id:
            machine_id = uuid4().hex
            self.user_settings.set_value("access_control/machine_id", machine_id)
        self._machine_id = machine_id
        return machine_id

    def _shared_ssh_config_from_local_settings(self) -> dict[str, object]:
        """Read the shared SSH endpoint directly from the tiny local settings cache.

        The public catalog manager must not instantiate or query a hidden
        InputSourceSelector merely to obtain credentials.  Reading these scalar
        values is local-only, deterministic and does not touch SSH.
        """
        host = self.user_settings.get_value("remote_g_source/host", "").strip()
        username = self.user_settings.get_value("remote_g_source/username", "").strip()
        password = self.user_settings.get_value("remote_g_source/password", "")
        try:
            port = int(self.user_settings.get_value("remote_g_source/port", "22") or 22)
        except (TypeError, ValueError):
            port = 22
        remote_directory = self.user_settings.get_value("remote_g_source/remote_directory", "").strip()
        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "remote_directory": remote_directory,
        }

    def _admin_lease_config(self) -> dict[str, object]:
        """Return explicitly confirmed central-repository settings for Admin operations."""
        settings = CentralRepositorySettings(self.user_settings)
        repository = settings.require_explicitly_saved(action="Admin 权限操作")
        cfg = repository.connection_args()
        cfg["config_dir"] = repository.config_dir
        return cfg

    def _toggle_admin_mode(self) -> None:
        if self._is_admin_mode:
            self._release_admin_mode()
            return

        try:
            CentralRepositorySettings(self.user_settings).require_explicitly_saved(action="抢占 Admin 权限")
        except Exception as exc:
            QMessageBox.warning(self, "无法抢占 Admin 权限", str(exc))
            return

        self._ensure_machine_id()
        lease = self._admin_lease
        detail = f"当前已知 Admin：{lease.owner_text}。\n\n" if lease is not None else ""
        if QMessageBox.question(
            self,
            "抢占 Admin 权限",
            detail
            + "抢占后，本机将获得中央配置发布权限；原 Admin 检测到所有权变化后会自动降级。\n\n"
            "本操作只变更 Admin 所有权，不会自动同步或发布数据库、文件服务器、ID 规则或图元分类配置。是否继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        self._request_admin_mode()

    def _prompt_new_admin_password(self, *, title: str) -> str | None:
        password, ok = QInputDialog.getText(
            self,
            title,
            "新管理员密码（至少 6 个字符）：",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return None
        confirm, ok = QInputDialog.getText(
            self,
            title,
            "再次输入管理员密码：",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return None
        if password != confirm:
            QMessageBox.warning(self, title, "两次输入的管理员密码不一致。")
            return None
        if len(str(password)) < 6 or not str(password).strip():
            QMessageBox.warning(self, title, "管理员密码至少需要 6 个字符。")
            return None
        return str(password)

    def _force_reset_admin_password(self) -> None:
        """Recover a forgotten central admin password through configured SSH write access."""
        self._ensure_machine_id()
        password = self._prompt_new_admin_password(title="强制设置管理员密码")
        if password is None:
            return
        if QMessageBox.question(
            self,
            "强制设置管理员密码",
            "此操作会直接重置中央管理员密码，并由本机接管管理员权限。\n"
            "无需旧管理员密码，但必须能够使用当前 SSH 配置写入中央 config/instance.json。\n\n"
            "是否继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            cfg = self._admin_lease_config()
        except Exception as exc:
            QMessageBox.warning(self, "无法设置管理员密码", str(exc))
            return
        if self._admin_lease_worker is not None:
            return

        self._admin_lease_action = "reset_password"

        def run_reset(log, progress):
            progress(10)
            lease = ClassificationRegistryService(config_dir=str(cfg["config_dir"])).force_set_admin_password(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                new_admin_password=password,
                machine_id=self._machine_id,
                machine_name=self._machine_name,
                take_over=True,
            )
            progress(100)
            return lease

        worker = FunctionWorker(run_reset)
        self._admin_lease_worker = worker
        worker.signals.result.connect(self._on_admin_acquire_result)
        worker.signals.error.connect(
            lambda details: self._on_admin_lease_error(details, action="强制设置密码")
        )
        worker.signals.finished.connect(self._on_admin_lease_worker_finished)
        self._refresh_access_controls()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _initialize_admin_password(self) -> None:
        self._force_reset_admin_password()

    def _change_admin_password(self) -> None:
        if not self._is_admin_mode:
            QMessageBox.warning(self, "需要管理员权限", "请先进入管理员模式。")
            return
        password = self._prompt_new_admin_password(title="修改管理员密码")
        if password is None:
            return
        try:
            cfg = self._admin_lease_config()
        except Exception as exc:
            QMessageBox.warning(self, "无法修改管理员密码", str(exc))
            return
        try:
            lease = ClassificationRegistryService(config_dir=str(cfg["config_dir"])).force_set_admin_password(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                new_admin_password=password,
                machine_id=self._machine_id,
                machine_name=self._machine_name,
                take_over=True,
            )
        except Exception as exc:
            QMessageBox.warning(self, "修改管理员密码失败", str(exc))
            return
        if isinstance(lease, AdminLeaseSnapshot):
            self._admin_lease = lease
        QMessageBox.information(self, "管理员密码已更新", "中央管理员密码已更新。")

    def _request_admin_mode(self) -> None:
        self._ensure_machine_id()
        if self._admin_lease_worker is not None:
            # Opening the global permission dialog triggers a small asynchronous
            # instance.json status refresh.  On higher-latency site links the user
            # can confirm takeover before that refresh finishes.  Older versions
            # simply returned here, so the click appeared to do nothing.  Queue the
            # takeover and run it after the status worker completes instead.
            if self._admin_lease_action == "status":
                self._pending_admin_takeover = True
                if hasattr(self, "admin_owner_label"):
                    self.admin_owner_label.setText("当前管理员：正在读取状态，随后自动抢占…")
                if hasattr(self, "server_library_status"):
                    self.server_library_status.setText(
                        "正在读取中央 Admin 状态；读取完成后将自动执行本次抢占。"
                    )
                return
            QMessageBox.information(self, "管理员操作进行中", "当前已有管理员操作正在进行，请稍后再试。")
            return
        self._pending_admin_takeover = False
        try:
            cfg = self._admin_lease_config()
        except Exception as exc:
            QMessageBox.warning(self, "无法抢占 Admin 权限", str(exc))
            return

        self._admin_lease_action = "acquire"
        if hasattr(self, "admin_owner_label"):
            self.admin_owner_label.setText("当前管理员：正在抢占…")

        def run_acquire(log, progress):
            progress(10)
            lease = ClassificationRegistryService(config_dir=str(cfg["config_dir"])).takeover_admin(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                machine_id=self._machine_id,
                machine_name=self._machine_name,
            )
            progress(100)
            return lease

        worker = FunctionWorker(run_acquire)
        self._admin_lease_worker = worker
        worker.signals.result.connect(self._on_admin_acquire_result)
        worker.signals.error.connect(lambda details: self._on_admin_lease_error(details, action="抢占"))
        worker.signals.finished.connect(self._on_admin_lease_worker_finished)
        self._refresh_access_controls()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_admin_acquire_result(self, result: object) -> None:
        if not isinstance(result, AdminLeaseSnapshot):
            return
        self._admin_lease = result
        self._is_admin_mode = True
        self._admin_ownership_timer.start()
        self.server_library_status.setText(
            f"Admin 抢占完成：{result.owner_text}。本次仅变更所有权，未同步或发布中央业务配置。"
        )
        self._refresh_access_controls()
        self._update_action_state()

    def _release_admin_mode(self) -> None:
        lease = self._admin_lease
        self._is_admin_mode = False
        self._admin_ownership_timer.stop()
        self._refresh_access_controls()
        self._update_action_state()
        if lease is None or not lease.lease_id:
            self.server_library_status.setText("已退出管理员模式。")
            self._refresh_admin_lease_status()
            return
        if self._admin_lease_worker is not None:
            self.server_library_status.setText("管理员操作正在进行，请稍后再释放。")
            return
        try:
            cfg = self._admin_lease_config()
        except Exception:
            self.server_library_status.setText("当前无法连接服务器；中央 instance.json 仍保留本机为管理员，请恢复连接后手动释放。")
            return

        self._admin_lease_action = "release"
        self.server_library_status.setText("正在释放服务器管理员权限…")

        def run_release(log, progress):
            progress(20)
            released = ClassificationRegistryService(config_dir=str(cfg["config_dir"])).release_admin_lease(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                machine_id=self._machine_id,
                lease_id=lease.lease_id,
                expected_admin_epoch=lease.admin_epoch,
            )
            progress(100)
            return released

        worker = FunctionWorker(run_release)
        self._admin_lease_worker = worker
        worker.signals.result.connect(self._on_admin_release_result)
        worker.signals.error.connect(lambda details: self._on_admin_lease_error(details, action="释放", quiet=True))
        worker.signals.finished.connect(self._on_admin_lease_worker_finished)
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_admin_release_result(self, result: object) -> None:
        self._admin_lease = None
        self.server_library_status.setText("管理员权限已释放；本机已恢复普通模式。")
        self._refresh_access_controls()
        QTimer.singleShot(100, self._refresh_admin_lease_status)

    def _renew_admin_lease(self) -> None:
        if not self._is_admin_mode or self._admin_lease is None or self._admin_lease_worker is not None:
            return
        lease = self._admin_lease
        try:
            cfg = self._admin_lease_config()
        except Exception as exc:
            self._on_admin_heartbeat_lost(str(exc))
            return

        self._admin_lease_action = "renew"

        def run_renew(log, progress):
            return ClassificationRegistryService(config_dir=str(cfg["config_dir"])).renew_admin_lease(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                machine_id=self._machine_id,
                lease_id=lease.lease_id,
                lease_seconds=DEFAULT_ADMIN_LEASE_SECONDS,
                expected_admin_epoch=lease.admin_epoch,
            )

        worker = FunctionWorker(run_renew)
        self._admin_lease_worker = worker
        worker.signals.result.connect(self._on_admin_renew_result)
        worker.signals.error.connect(lambda details: self._on_admin_heartbeat_lost(str(details)))
        worker.signals.finished.connect(self._on_admin_lease_worker_finished)
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_admin_renew_result(self, result: object) -> None:
        if isinstance(result, AdminLeaseSnapshot):
            self._admin_lease = result
            self._refresh_access_controls()

    def _on_admin_heartbeat_lost(self, details: str) -> None:
        if not self._is_admin_mode:
            return
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self._is_admin_mode = False
        self._admin_ownership_timer.stop()
        self._refresh_access_controls()
        self._update_action_state()
        self.server_library_status.setText("Admin 所有权已变化；本机已自动恢复普通客户端模式。")
        QMessageBox.warning(
            self,
            "管理员权限已失效",
            (message or "Admin 权限已被其他机器重新抢占。") + "\n\n本机已恢复普通客户端模式；本地配置仍可修改保存和手动同步，但不能发布中央仓库。",
        )

    def _refresh_admin_lease_status(self) -> None:
        if self._is_admin_mode or self._admin_lease_worker is not None:
            return
        try:
            cfg = self._admin_lease_config()
        except Exception:
            if hasattr(self, "admin_owner_label"):
                self.admin_owner_label.setText("当前管理员：请先确认并保存中央仓库配置")
            return

        self._admin_lease_action = "status"

        def run_status(log, progress):
            return ClassificationRegistryService(config_dir=str(cfg["config_dir"])).fetch_admin_lease(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
            )

        worker = FunctionWorker(run_status)
        self._admin_lease_worker = worker
        worker.signals.result.connect(self._on_admin_status_result)
        worker.signals.error.connect(lambda details: self._on_admin_lease_error(details, action="状态", quiet=True))
        worker.signals.finished.connect(self._on_admin_lease_worker_finished)
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_admin_status_result(self, result: object) -> None:
        self._admin_lease = result if isinstance(result, AdminLeaseSnapshot) else None
        self._refresh_access_controls()

    def _on_admin_lease_error(self, details: str, *, action: str, quiet: bool = False) -> None:
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        if action in {"申请", "抢占"}:
            self._is_admin_mode = False
            self._admin_ownership_timer.stop()
            self.server_library_status.setText(message or "Admin 权限抢占失败。")
        elif action == "释放":
            self.server_library_status.setText("释放失败；中央 instance.json 仍保持原管理员，请恢复连接后重试。")
        elif action == "状态" and hasattr(self, "admin_owner_label"):
            self.admin_owner_label.setText("当前管理员：状态暂不可用")
        self._refresh_access_controls()
        self._update_action_state()
        if not quiet:
            QMessageBox.warning(self, f"管理员权限{action}失败", message or str(details))

    def _on_admin_lease_worker_finished(self) -> None:
        finished_action = self._admin_lease_action
        self._admin_lease_worker = None
        self._admin_lease_action = ""
        self._refresh_access_controls()
        self._update_action_state()
        if finished_action == "status" and self._pending_admin_takeover:
            self._pending_admin_takeover = False
            # Defer until all result/error handlers from the finished worker have
            # returned, then perform the already-confirmed takeover with the same
            # locally saved central-repository settings.
            QTimer.singleShot(0, self._request_admin_mode)

    def _release_admin_lease_on_shutdown(self) -> None:
        """End only this process session; central Admin ownership is persistent.

        Matching Distribution Model Manager, closing the application does not
        release or mutate central ``instance.json``. Admin is changed only by an
        explicit release or by another workstation taking over.
        """
        self._admin_ownership_timer.stop()
        self._is_admin_mode = False
        self._admin_lease = None

    def _require_admin_mode(self, action: str) -> bool:
        if self._is_admin_mode and self._admin_lease is not None and not self._admin_lease.expired:
            return True
        QMessageBox.warning(self, "需要管理员权限", f"{action}仅允许当前服务器管理员执行。")
        return False

    def _apply_classification_item_permissions(self) -> None:
        if not hasattr(self, "standard_table"):
            return
        # Every workstation may maintain its own local classification.  Admin only
        # controls who may publish the central server copy.
        for row in range(self.standard_table.rowCount()):
            item = self.standard_table.item(row, 18)
            if item is None:
                continue
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

    def _refresh_access_controls(self) -> None:
        initialized = True
        lease = self._admin_lease
        occupied = bool(lease is not None and not lease.expired)
        occupied_by_other = bool(
            occupied
            and lease is not None
            and lease.machine_id != self._machine_id
        )
        busy_admin = self._admin_lease_worker is not None

        if hasattr(self, "admin_owner_label"):
            if occupied and lease is not None:
                owner = lease.owner_text
                if lease.machine_id == self._machine_id:
                    owner += " · 本机"
                self.admin_owner_label.setText(f"当前管理员：{owner} · 中央 V{lease.config_version}")
            else:
                self.admin_owner_label.setText("当前管理员：未占用")

        if hasattr(self, "access_mode_label"):
            if self._is_admin_mode:
                self.access_mode_label.setText("模式：管理员")
                self.access_mode_button.setText("释放管理员权限")
                self.access_mode_button.setToolTip("释放中央管理员状态，其他机器随后可以申请管理员。")
                self.access_mode_button.setEnabled(not busy_admin)
                self.change_admin_password_button.setVisible(True)
            else:
                self.access_mode_label.setText("模式：普通客户端")
                self.access_mode_button.setText("抢占 Admin 权限")
                self.access_mode_button.setToolTip(
                    "任何客户端都可以显式抢占 Admin；抢占只变更所有权，不自动同步或发布业务配置。"
                )
                self.access_mode_button.setEnabled(not busy_admin)
                self.change_admin_password_button.setVisible(False)

        self._apply_classification_item_permissions()
        if hasattr(self, "standard_table"):
            self.standard_table.setEditTriggers(
                QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked
            )

        # Local configuration belongs to each workstation and is always editable.
        for name in ("save_classification_button", "import_classification_button", "export_classification_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(True)
        if hasattr(self, "local_classification_label"):
            self.local_classification_label.setVisible(True)
        if hasattr(self, "central_publish_button"):
            self.central_publish_button.setVisible(True)
            self.central_publish_button.setEnabled(self._is_admin_mode and self._classification_registry_worker is None)

        # The page no longer exposes administrator controls; keep the compatibility
        # container hidden even when the internal state updater toggles child widgets.
        if hasattr(self, "_legacy_access_container"):
            self._legacy_access_container.setVisible(False)
        self.adminAccessChanged.emit(self.admin_access_state())

    def admin_access_state(self) -> dict[str, object]:
        """Return the current global central-configuration access state for the sidebar."""
        lease = self._admin_lease
        occupied = bool(lease is not None and not lease.expired)
        occupied_by_other = bool(occupied and lease is not None and lease.machine_id != self._machine_id)
        initialized = True
        if self._is_admin_mode:
            mode = "admin"
            button_text = "配置权限：管理员模式"
        else:
            mode = "ordinary"
            button_text = "配置权限：普通客户端"
        return {
            "mode": mode,
            "button_text": button_text,
            "is_admin": bool(self._is_admin_mode),
            "initialized": bool(initialized),
            "busy": bool(self._admin_lease_worker is not None),
            "occupied_by_other": occupied_by_other,
            "owner_text": lease.owner_text if occupied and lease is not None else "未占用",
            "config_version": int(lease.config_version if occupied and lease is not None else 0),
            "admin_epoch": int(lease.admin_epoch if self._is_admin_mode and lease is not None else 0),
        }

    @staticmethod
    def _paired_builtin_row(row: int) -> int:
        return {0: 3, 3: 0, 1: 4, 4: 1, 2: 5, 5: 2}.get(int(row), -1)

    def _standard_row_selection_changed(self) -> None:
        row = self.standard_table.currentRow()
        self._refresh_selected_standard_download_action(row)
        is_builtin = 0 <= row < len(self._standard_specs)
        self.share_pair_checkbox.setEnabled(is_builtin and not self._task_busy)
        if not is_builtin:
            self.share_pair_checkbox.setChecked(False)
            self._update_action_state()
            return
        pair = self._paired_builtin_row(row)
        selected = str(self._standard_specs[row][3].currentData() or "").strip()
        paired = str(self._standard_specs[pair][3].currentData() or "").strip() if pair >= 0 else ""
        role = self._standard_specs[row][1]
        # Existing shared bindings are reflected automatically. For grounding
        # switches with no binding yet, default to shared because many projects do
        # not distinguish SMART/NORMAL grounding symbols. The user can untick it.
        self.share_pair_checkbox.blockSignals(True)
        self.share_pair_checkbox.setChecked(bool(selected and paired and selected.casefold() == paired.casefold()) or (not selected and not paired and role == "接地刀闸"))
        self.share_pair_checkbox.blockSignals(False)
        self._update_action_state()

    def _share_pair_toggled(self, checked: bool) -> None:
        if not checked or self._task_busy:
            return
        row = self.standard_table.currentRow()
        if not (0 <= row < len(self._standard_specs)):
            return
        pair_row = self._paired_builtin_row(row)
        if pair_row < 0:
            return
        combo = self._standard_specs[row][3]
        devref = str(combo.currentData() or "").strip()
        if not devref:
            return
        pair_combo = self._standard_specs[pair_row][3]
        pair_index = pair_combo.findData(devref)
        if pair_index < 0:
            return
        pair_combo.setCurrentIndex(pair_index)
        self._refresh_standard_row(pair_combo)
        self._refresh_standard_row(combo)

    def _toggle_log(self, checked: bool) -> None:
        visible = bool(checked)
        self.task.log_view.setVisible(visible)
        self.task.clear_button.setVisible(visible)
        self.toggle_log_button.setText("隐藏日志" if visible else "显示日志")

    def _selected_profile_key(self) -> tuple[str, int | None, bool]:
        data = self.profile_selector.currentData() if hasattr(self, "profile_selector") else None
        if not isinstance(data, (tuple, list)) or len(data) != 3:
            return "", None, False
        name = str(data[0] or "").strip()
        try:
            version = int(data[1]) if data[1] is not None else None
        except (TypeError, ValueError):
            version = None
        return name, version, bool(data[2])

    def _selected_profile_name(self) -> str:
        return self._selected_profile_key()[0]

    def _reload_profiles(
        self,
        select_name: str = "",
        select_version: int | None = None,
        *,
        defer_selection: bool = False,
        load_catalog: bool = True,
    ) -> None:
        self._legacy_profile_state_loaded = True
        profiles = self.service.load_profiles()
        if not select_name:
            remembered = self.user_settings.get_value("site_profile/last_profile_name", "").strip()
            if remembered in profiles:
                select_name = remembered
                select_version = profiles[remembered].profile_version

        global_name, global_version = self.service.get_global_profile_selection(auto_initialize=False)
        self.profile_selector.blockSignals(True)
        self.profile_selector.clear()
        selected_index = -1
        for profile_name, current in sorted(profiles.items(), key=lambda row: row[0].casefold()):
            versions = self.service.load_profile_versions(profile_name) or [current]
            for profile in reversed(versions):
                is_active = profile.profile_version == current.profile_version
                # Listing versions must stay lightweight. Full SHA256/file integrity
                # validation is performed only when a version is executed or made
                # GLOBAL, never once for every row during a UI refresh.
                ready = profile.authoritative_ready
                standard_rows = self._profile_standard_rows(profile)
                configured = sum(
                    1 for row in standard_rows
                    if bool(row.get("enabled", True)) and str(row.get("standard_devref", "")).strip()
                )
                unique_files = len({
                    str(row.get("standard_devref", "")).strip().casefold()
                    for row in standard_rows if str(row.get("standard_devref", "")).strip()
                })
                state = "ACTIVE" if is_active else "ARCHIVED"
                readiness = "READY" if ready else "NOT READY"
                lock_label = " · LOCKED" if profile.locked else ""
                global_label = " · GLOBAL" if profile_name == global_name and profile.profile_version == global_version else ""
                label = (
                    f"{profile.site_name} / {profile_name} / 服务器 {profile.server_standard_label} · "
                    f"{state}{global_label} · {readiness}{lock_label}"
                    f" · 标准图元 {configured} · 标准文件 {unique_files}"
                )
                self.profile_selector.addItem(label, (profile_name, profile.profile_version, is_active))
                index = self.profile_selector.count() - 1
                target_version = select_version if select_version is not None else current.profile_version
                if profile_name == select_name and profile.profile_version == target_version:
                    selected_index = index

        self.profile_selector.blockSignals(False)
        def select_profile() -> None:
            previous_blocked = self.profile_selector.blockSignals(True)
            if selected_index >= 0:
                self.profile_selector.setCurrentIndex(selected_index)
            elif self.profile_selector.count() > 0:
                self.profile_selector.setCurrentIndex(0)
            else:
                self.profile_selector.blockSignals(previous_blocked)
                self._new_profile(clear_selection=False)
                return
            self.profile_selector.blockSignals(previous_blocked)
            self._profile_selection_changed(load_catalog=load_catalog)

        if defer_selection:
            QTimer.singleShot(0, select_profile)
        elif selected_index >= 0:
            self.profile_selector.setCurrentIndex(selected_index)
            self._profile_selection_changed()
        elif self.profile_selector.count() > 0:
            self.profile_selector.setCurrentIndex(0)
            self._profile_selection_changed()
        else:
            self._new_profile(clear_selection=False)

    @staticmethod
    def _devref_short(devref: str) -> str:
        value = (devref or "").strip()
        if not value:
            return "-"
        tail = value.split(":")[-1].strip()
        if tail:
            return tail.lstrip("#")
        return value

    def _set_readonly_cell(self, row: int, column: int, text: str, *, kind: str = "") -> QTableWidgetItem:
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if kind:
            item.setData(Qt.ItemDataRole.UserRole, kind)
        self.standard_table.setItem(row, column, item)
        return item

    def _classification_marker_changed(self, item: QTableWidgetItem) -> None:
        """Apply one marker immediately in memory and persist it asynchronously."""
        if (
            item.column() != 18
            or getattr(self, "_classification_marker_write_busy", False)
            or getattr(self, "_suppress_classification_marker_persistence", False)
        ):
            return
        remote_path = str(item.data(Qt.ItemDataRole.UserRole + 1) or "").strip()
        if not remote_path:
            return
        host = str(item.data(Qt.ItemDataRole.UserRole + 2) or "").strip()
        root = str(item.data(Qt.ItemDataRole.UserRole + 3) or "").strip()
        if not host or not root:
            return

        marker = item.text().strip()
        if hasattr(self, "_inventory_natural_widths"):
            marker_width = self.standard_table.fontMetrics().horizontalAdvance(marker) + 28
            previous_width = int(self._inventory_natural_widths.get(18, 0) or 0)
            if marker_width > previous_width:
                self._inventory_natural_widths[18] = marker_width
                self._schedule_inventory_width_update()
        # Keep every in-memory view aligned immediately.  No disk or network I/O is
        # allowed on this GUI callback.
        for record in self._server_catalog_records.values():
            if str(record.get("remote_path", "")).strip() != remote_path:
                continue
            if marker:
                record["classification_marker"] = marker
                record["category_marker"] = marker
            else:
                record.pop("classification_marker", None)
                record.pop("category_marker", None)
            break
        devref = self._standard_file_devref(item.row())
        if devref and devref in self._symbol_catalog:
            if marker:
                self._symbol_catalog[devref]["classification_marker"] = marker
                self._symbol_catalog[devref]["category_marker"] = marker
            else:
                self._symbol_catalog[devref].pop("classification_marker", None)
                self._symbol_catalog[devref].pop("category_marker", None)
        for record in self._server_file_inventory:
            if str(record.get("remote_path", "")).strip() != remote_path:
                continue
            if marker:
                record["classification_marker"] = marker
                record["category_marker"] = marker
            else:
                record.pop("classification_marker", None)
                record.pop("category_marker", None)
            break
        self._refresh_standard_table_overview()

        # Last edit wins for the same physical server file.  The timer coalesces a
        # burst of edits and the worker performs the JSON rewrites off the GUI thread.
        self._pending_classification_marker_updates[(host, root, remote_path)] = marker
        self._classification_marker_save_timer.start()

    def _flush_classification_marker_updates(self) -> None:
        if self._classification_marker_save_worker is not None:
            # A worker is already persisting an earlier batch.  Keep the new edits
            # queued; finished() will schedule the next flush.
            return
        if not self._pending_classification_marker_updates:
            return

        pending = dict(self._pending_classification_marker_updates)
        self._pending_classification_marker_updates.clear()

        def persist_local_markers(log, progress):
            del log
            groups: dict[tuple[str, str], dict[str, str]] = {}
            for (host, root, remote_path), marker in pending.items():
                groups.setdefault((host, root), {})[remote_path] = marker
            total = max(1, len(groups))
            saved = 0
            for index, ((host, root), updates) in enumerate(groups.items(), start=1):
                saved += RemoteSymbolLibraryService().update_classification_markers_batch(
                    host=host, root=root, updates=updates
                )
                progress(int(index * 100 / total))
            return saved

        worker = FunctionWorker(persist_local_markers)
        self._classification_marker_save_worker = worker
        worker.signals.result.connect(self._on_classification_marker_save_result)
        worker.signals.error.connect(self._on_classification_marker_save_error)
        worker.signals.finished.connect(self._on_classification_marker_save_finished)
        self._refresh_catalog_action_state()
        self._scan_pool.start(worker)

    def _on_classification_marker_save_result(self, _result: object) -> None:
        self._mark_local_classification_source("custom")
        self.user_settings.set_value("local_cache/classification_saved_at", self._local_config_timestamp())
        self._refresh_classification_cache_status(extra="本地分类已更新")

    def _on_classification_marker_save_error(self, details: object) -> None:
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        if hasattr(self, "central_classification_status"):
            self.central_classification_status.setText(
                f"本地分类缓存保存失败：{message or '未知错误'}"
            )

    def _on_classification_marker_save_finished(self) -> None:
        self._classification_marker_save_worker = None
        self._refresh_catalog_action_state()
        if self._pending_classification_marker_updates:
            self._classification_marker_save_timer.start(60)

    @staticmethod
    def _format_dimension(value: object) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        if number <= 0:
            return "-"
        return str(int(round(number))) if abs(number - round(number)) < 1e-9 else f"{number:g}"

    def _fit_standard_table_columns(self) -> None:
        """Size the symbol-standard table from its actual visible content.

        Unlike the generic dense-table helper, this table intentionally does not
        clamp long filenames/devrefs.  The user asked to see the complete scanned
        symbol-G filename, so horizontal scrolling is preferred over ellipsis.
        """
        if not hasattr(self, "standard_table"):
            return
        # The public catalog-manager workflow never performs content scanning for
        # column widths.  Keep the expensive legacy fitter only for an explicitly
        # loaded historical Profile editor.
        if self._server_inventory_table_enabled and not self._legacy_profile_state_loaded:
            self._apply_fast_inventory_column_widths()
            self._refresh_standard_table_overview()
            return
        table = self.standard_table
        header = table.horizontalHeader()
        table.resizeColumnsToContents()
        for column in range(table.columnCount()):
            # sectionSizeHint covers the full header text while columnWidth after
            # resizeColumnsToContents covers the longest current cell/widget.
            width = max(table.columnWidth(column), header.sectionSizeHint(column), 72)
            table.setColumnWidth(column, width + 16)

        # Preserve the readable cell-widget height that the generic dense-table
        # helper provides to its fixed schemas.  This table is discovery-driven,
        # so its schema is intentionally not registered in that clamping helper.
        for row in range(table.rowCount()):
            row_height = 40
            for column in range(table.columnCount()):
                cell_widget = table.cellWidget(row, column)
                if cell_widget is None:
                    continue
                row_height = max(
                    row_height,
                    cell_widget.sizeHint().height() + 8,
                    cell_widget.minimumSizeHint().height() + 8,
                )
            table.setRowHeight(row, row_height)
        self._refresh_standard_table_overview()

    def _is_server_inventory_row(self, row: int) -> bool:
        """Return whether a row is a read-only physical server-file row."""
        if row < 0 or row >= self.standard_table.rowCount():
            return False
        marker = self.standard_table.item(row, 0)
        return bool(
            marker is not None
            and marker.data(Qt.ItemDataRole.UserRole) == "server_inventory"
        )

    def _remove_server_inventory_rows(self) -> None:
        for row in range(self.standard_table.rowCount() - 1, -1, -1):
            if self._is_server_inventory_row(row):
                self.standard_table.removeRow(row)

    @staticmethod
    def _server_inventory_status(record: dict[str, object]) -> str:
        status = str(record.get("sync_status", "READY")).strip().upper()
        if status == "CONFLICT":
            return "同名冲突 · 待确认"
        if status == "ERROR":
            return "读取/解析失败 · 已保留"
        return "READY · 已同步"

    @staticmethod
    def _format_server_mtime(value: object) -> str:
        try:
            epoch = int(value or 0)
        except (TypeError, ValueError):
            epoch = 0
        if epoch <= 0:
            return "-"
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def _set_server_inventory_cell(self, row: int, column: int, text: object) -> QTableWidgetItem:
        return self._set_readonly_cell(row, column, str(text or "-"), kind="server_inventory")

    def _populate_server_inventory_row_fast(
        self, row: int, inventory: dict[str, object]
    ) -> None:
        """Populate only the operator-visible inventory fields.

        The former startup path created 20 QTableWidgetItem objects per row and
        calculated legacy role/usage fields even though 13 columns are hidden on
        this page.  For a 200-file local cache that meant thousands of needless Qt
        objects on the GUI thread.  This fast row keeps the mature 20-column schema
        allocated, but materializes only the seven visible columns plus a tiny hidden
        identity marker needed by existing compatibility code.
        """
        standard = inventory.get("standard_record", {})
        standard = dict(standard) if isinstance(standard, dict) else {}
        file_name = Path(str(inventory.get("name", "") or standard.get("original_name", ""))).name
        devref = str(standard.get("devref", "")).strip()
        remote_path = str(inventory.get("remote_path", "")).strip() or "-"
        relative_path = str(inventory.get("relative_path", "")).strip() or file_name or "-"
        width = self._format_dimension(standard.get("width", 0))
        height = self._format_dimension(standard.get("height", 0))
        dimension = f"{width}×{height}" if width != "-" and height != "-" else "-"
        align = standard.get("align_center", [])
        pins = standard.get("pins", [])
        status = self._server_inventory_status(inventory)
        server_mtime = self._format_server_mtime(inventory.get("mtime_epoch"))
        updated_note = "本次同步检测到服务器元数据更新" if inventory.get("server_updated") else ""

        marker = self._set_server_inventory_cell(row, 0, "服务器文件")
        marker.setData(Qt.ItemDataRole.UserRole, "server_inventory")
        marker.setData(Qt.ItemDataRole.UserRole + 9, True)
        marker.setData(Qt.ItemDataRole.UserRole + 10, remote_path)
        marker.setData(Qt.ItemDataRole.UserRole + 11, str(inventory.get("remote_host", "")).strip())
        marker.setData(Qt.ItemDataRole.UserRole + 12, str(inventory.get("remote_root", "")).strip())

        file_item = self._set_server_inventory_cell(row, 3, relative_path)
        file_item.setData(Qt.ItemDataRole.UserRole, devref)
        tooltip = "\n".join([
            f"服务器相对路径：{relative_path}",
            f"服务器完整路径：{remote_path}",
            f"文件名：{file_name or '-'}",
            f"devref：{devref or '-'}",
            f"服务器修改时间：{server_mtime}",
            f"状态：{status}",
            updated_note,
        ]).rstrip()
        file_item.setToolTip(tooltip)
        self._set_server_inventory_cell(row, 5, dimension)
        self._set_server_inventory_cell(row, 6, align)
        self._set_server_inventory_cell(row, 7, pins)
        self._set_server_inventory_cell(row, 8, "服务器图元库")
        status_item = self._set_server_inventory_cell(row, 9, status)
        status_item.setToolTip(tooltip)

        classification = str(
            inventory.get("classification_marker", inventory.get("category_marker", "")) or ""
        ).strip()
        classification_item = QTableWidgetItem(classification)
        classification_item.setToolTip("用户维护的分类标记；保存在本地图元缓存，不会写回服务器。")
        classification_item.setData(Qt.ItemDataRole.UserRole + 1, remote_path if remote_path != "-" else "")
        classification_item.setData(Qt.ItemDataRole.UserRole + 2, str(inventory.get("remote_host", "")).strip())
        classification_item.setData(Qt.ItemDataRole.UserRole + 3, str(inventory.get("remote_root", "")).strip())
        self.standard_table.setItem(row, 18, classification_item)

        # Keep the hidden legacy path cell available to old helper methods without
        # materializing any of the other retired columns.
        self._set_server_inventory_cell(row, 19, relative_path)

    def _append_server_inventory_row(
        self, inventory: dict[str, object], *, row: int | None = None
    ) -> int:
        """Populate one physical remote-file row without making it editable.

        ``row`` is supplied by the startup fast path after one bulk ``setRowCount``.
        Legacy merge callers may omit it and retain the mature append behavior.
        """
        standard = inventory.get("standard_record", {})
        standard = dict(standard) if isinstance(standard, dict) else {}
        file_name = Path(str(inventory.get("name", "") or standard.get("original_name", ""))).name
        devref = str(standard.get("devref", "")).strip()
        element_tag = str(standard.get("element_tag", "")).strip()
        element_id = str(standard.get("element_id", "")).strip()
        role = infer_device_type(
            role=element_id,
            source_file=file_name,
            element_tag=element_tag,
            element_id=element_id,
        )
        usage = infer_symbol_usage(role=role, source_file=file_name, element_tag=element_tag)
        width = self._format_dimension(standard.get("width", 0))
        height = self._format_dimension(standard.get("height", 0))
        dimension = f"{width}×{height}" if width != "-" and height != "-" else "-"
        align = standard.get("align_center", [])
        pins = standard.get("pins", [])
        relative_path = str(inventory.get("relative_path", "")).strip() or "-"
        remote_path = str(inventory.get("remote_path", "")).strip() or "-"
        status = self._server_inventory_status(inventory)
        server_mtime = self._format_server_mtime(inventory.get("mtime_epoch"))
        updated_note = "本次同步检测到服务器元数据更新" if inventory.get("server_updated") else ""

        if row is None:
            row = self.standard_table.rowCount()
            self.standard_table.insertRow(row)
        elif row < 0:
            raise ValueError("row must be >= 0")
        elif row >= self.standard_table.rowCount():
            self.standard_table.setRowCount(row + 1)
        marker = self._set_server_inventory_cell(row, 0, "服务器文件")
        marker.setData(Qt.ItemDataRole.UserRole, "server_inventory")
        marker.setData(Qt.ItemDataRole.UserRole + 9, True)
        marker.setData(Qt.ItemDataRole.UserRole + 10, remote_path)
        marker.setData(Qt.ItemDataRole.UserRole + 11, str(inventory.get("remote_host", "")).strip())
        marker.setData(Qt.ItemDataRole.UserRole + 12, str(inventory.get("remote_root", "")).strip())
        marker.setToolTip(
            f"服务器文件清单\n远程路径：{remote_path}\n服务器修改时间：{server_mtime}"
            + (f"\n{updated_note}" if updated_note else "")
        )
        self._set_server_inventory_cell(row, 1, role or "服务器图元")
        self._set_server_inventory_cell(row, 2, element_tag)  # internal compatibility only; hidden
        display_path = relative_path or file_name
        file_item = self._set_server_inventory_cell(row, 3, display_path)
        file_item.setData(Qt.ItemDataRole.UserRole, devref)
        self._set_server_inventory_cell(row, 4, element_id)
        self._set_server_inventory_cell(row, 5, dimension)
        self._set_server_inventory_cell(row, 6, align)
        self._set_server_inventory_cell(row, 7, pins)
        self._set_server_inventory_cell(row, 8, "服务器图元库")
        status_item = self._set_server_inventory_cell(row, 9, status)
        self._set_server_inventory_cell(row, 10, usage)
        self._set_server_inventory_cell(row, 11, "")
        self._set_server_inventory_cell(row, 12, default_device_level(usage))
        self._set_server_inventory_cell(row, 13, file_name)
        self._set_server_inventory_cell(row, 14, devref)
        self._set_server_inventory_cell(row, 15, "-")
        self._set_server_inventory_cell(row, 16, "-")
        classification = str(
            inventory.get("classification_marker", inventory.get("category_marker", "")) or ""
        ).strip()
        classification_item = QTableWidgetItem(classification)
        classification_item.setToolTip("用户维护的分类标记；保存在本地服务器图元清单，不会写回服务器。")
        classification_item.setData(Qt.ItemDataRole.UserRole + 1, remote_path)
        classification_item.setData(Qt.ItemDataRole.UserRole + 2, str(inventory.get("remote_host", "")).strip())
        classification_item.setData(Qt.ItemDataRole.UserRole + 3, str(inventory.get("remote_root", "")).strip())
        self.standard_table.setItem(row, 18, classification_item)
        self._set_server_inventory_cell(row, 19, relative_path)
        for column in (3, 9, 19):
            item = self.standard_table.item(row, column)
            if item is not None:
                item.setToolTip(
                    "\n".join([
                        f"服务器相对路径：{relative_path}",
                        f"服务器完整路径：{remote_path}",
                        f"文件名：{file_name or '-'}",
                        f"devref：{devref or '-'}",
                        f"服务器修改时间：{server_mtime}",
                        f"状态：{status}",
                        updated_note,
                    ])
                )
        # Column 17 remains intentionally empty: invalid/conflicting files have no
        # standard download action and must not be mistaken for editable rows.
        status_item.setToolTip(
            f"{status}\n服务器相对路径：{relative_path}\n服务器修改时间：{server_mtime}"
            + (f"\n{updated_note}" if updated_note else "")
        )
        return row

    def _merge_server_file_inventory_rows(self) -> None:
        # Called only by legacy auto-bind/business-scan paths in tableless mode.
        # The widget remains hidden, preserving mature internal row logic.
        previous_suppression = self._suppress_classification_marker_persistence
        self._suppress_classification_marker_persistence = True
        try:
            self._merge_server_file_inventory_rows_impl()
        finally:
            self._suppress_classification_marker_persistence = previous_suppression

    def _merge_server_file_inventory_rows_impl(self) -> None:
        """Show every physical remote .g while keeping one editable row per devref."""
        if not hasattr(self, "standard_table"):
            return
        self._remove_server_inventory_rows()
        if not self._server_file_inventory:
            return

        # The parsed standard catalog already supplies the editable row for the
        # first occurrence of a devref.  Attach its relative path there, then add
        # duplicate paths and conflict/error files as read-only inventory rows.
        first_row_by_devref: dict[str, int] = {}
        for row in range(self.standard_table.rowCount()):
            if self._is_server_inventory_row(row):
                continue
            devref = self._standard_file_devref(row).casefold()
            if devref:
                first_row_by_devref.setdefault(devref, row)

        used_standard_rows: set[int] = set()
        for inventory in self._server_file_inventory:
            standard = inventory.get("standard_record", {})
            standard = dict(standard) if isinstance(standard, dict) else {}
            devref = str(standard.get("devref", "")).strip().casefold()
            status = str(inventory.get("sync_status", "READY")).strip().upper()
            row = first_row_by_devref.get(devref) if status == "READY" and devref else None
            if row is not None and row not in used_standard_rows:
                used_standard_rows.add(row)
                relative = str(inventory.get("relative_path", "")).strip() or "-"
                path_item = self._set_readonly_cell(row, 19, relative, kind="server_inventory_path")
                path_item.setData(Qt.ItemDataRole.UserRole + 1, str(inventory.get("remote_path", "")).strip())
                path_item.setData(Qt.ItemDataRole.UserRole + 2, str(inventory.get("remote_host", "")).strip())
                path_item.setData(Qt.ItemDataRole.UserRole + 3, str(inventory.get("remote_root", "")).strip())
                path_item.setToolTip(
                    f"服务器相对路径：{relative}\n"
                    f"服务器完整路径：{inventory.get('remote_path', '-') or '-'}\n"
                    f"服务器修改时间：{self._format_server_mtime(inventory.get('mtime_epoch'))}"
                    + ("\n本次同步检测到服务器元数据更新" if inventory.get("server_updated") else "")
                )
                classification = str(
                    inventory.get("classification_marker", inventory.get("category_marker", "")) or ""
                ).strip()
                classification_item = self.standard_table.item(row, 18)
                if classification_item is None:
                    classification_item = QTableWidgetItem()
                    self.standard_table.setItem(row, 18, classification_item)
                classification_item.setText(classification)
                classification_item.setToolTip("用户维护的分类标记；保存在本地服务器图元清单，不会写回服务器。")
                classification_item.setData(Qt.ItemDataRole.UserRole + 1, str(inventory.get("remote_path", "")).strip())
                classification_item.setData(Qt.ItemDataRole.UserRole + 2, str(inventory.get("remote_host", "")).strip())
                classification_item.setData(Qt.ItemDataRole.UserRole + 3, str(inventory.get("remote_root", "")).strip())
                continue
            self._append_server_inventory_row(inventory)

    def _measure_inventory_natural_widths(self) -> dict[int, int]:
        """Measure only the seven visible operator columns once after population.

        This deliberately avoids Qt content-based auto-sizing.  Measuring
        seven plain item strings across ~200 rows is cheap, deterministic, and lets
        us preserve complete filenames, pins, status text and classification labels
        without re-running a full widget size-hint pass on every resize.
        """
        if not hasattr(self, "standard_table"):
            return {}
        table = self.standard_table
        metrics = table.fontMetrics()
        floors = {3: 220, 5: 72, 6: 118, 7: 180, 8: 110, 9: 130, 18: 180}
        widths: dict[int, int] = {}
        for column in self._inventory_visible_columns:
            header_item = table.horizontalHeaderItem(column)
            title = header_item.text() if header_item is not None else ""
            width = max(floors[column], metrics.horizontalAdvance(title) + 28)
            for row in range(table.rowCount()):
                item = table.item(row, column)
                if item is None:
                    continue
                text = item.text()
                if text:
                    width = max(width, metrics.horizontalAdvance(text) + 28)
            widths[column] = width
        return widths

    def _apply_fast_inventory_column_widths(self, *, recompute_content: bool = False) -> None:
        """Keep every visible field readable and use the complete table viewport.

        The ID-rule table is the presentation reference: columns keep readable
        natural widths, the table stretches across the available page, and a local
        horizontal scrollbar exposes the complete schema when the viewport is too
        narrow.  Content is measured only once after population; resize events reuse
        cached widths and therefore remain O(visible columns), not O(rows × columns).
        """
        if not hasattr(self, "standard_table"):
            return
        table = self.standard_table
        header = table.horizontalHeader()
        visible = self._inventory_visible_columns
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)

        if recompute_content or not self._inventory_natural_widths:
            measured = self._measure_inventory_natural_widths()
            if measured:
                self._inventory_natural_widths = measured

        metrics = table.fontMetrics()
        floors = {3: 220, 5: 72, 6: 118, 7: 180, 8: 110, 9: 130, 18: 180}
        widths: dict[int, int] = {}
        for column in visible:
            header_item = table.horizontalHeaderItem(column)
            title = header_item.text() if header_item is not None else ""
            header_width = metrics.horizontalAdvance(title) + 28
            widths[column] = max(
                floors[column],
                header_width,
                int(self._inventory_natural_widths.get(column, 0) or 0),
            )

        # If all natural widths fit, distribute the spare area instead of leaving a
        # large blank block on the right.  Long-text columns receive most of the
        # extra space. If they do not fit, never shrink below natural width: the
        # table-local horizontal scrollbar exposes every field completely.
        available = max(0, int(table.viewport().width() or table.width() or 0) - 4)
        total = sum(widths.values())
        if available > total:
            extra = available - total
            weights = ((3, 36), (7, 24), (18, 22), (9, 8), (6, 5), (8, 5))
            distributed = 0
            for column, percent in weights[:-1]:
                addition = int(extra * percent / 100)
                widths[column] += addition
                distributed += addition
            widths[weights[-1][0]] += extra - distributed

        for column in visible:
            table.setColumnWidth(column, max(48, int(widths[column])))
        table.verticalHeader().setDefaultSectionSize(32)

    def _restore_cached_inventory_table_fast(self, *, atomic_reveal: bool = False) -> None:
        """Hydrate the operator inventory with no empty-table flash.

        AppData restores use ``atomic_reveal=True``: the table stays hidden while
        its cached rows are materialized with painting/signals blocked, then appears
        once with final widths.  Manual refreshes keep the already-visible table and
        still use event-loop batching for responsiveness.
        """
        if not self._server_inventory_table_enabled or not hasattr(self, "standard_table"):
            return
        self._inventory_atomic_reveal = bool(atomic_reveal)
        if self._inventory_atomic_reveal:
            self._set_local_catalog_loading_state(True, reveal_table=True)
        self._inventory_render_generation += 1
        generation = self._inventory_render_generation
        self._inventory_render_rows = [dict(row) for row in self._server_file_inventory]
        self._inventory_render_cursor = 0

        table = self.standard_table
        previous = table.blockSignals(True)
        try:
            table.setSortingEnabled(False)
            table.clearContents()
            table.setRowCount(len(self._inventory_render_rows))
        finally:
            table.blockSignals(previous)
        if not self._inventory_atomic_reveal:
            self._apply_fast_inventory_column_widths()
            self._refresh_standard_table_overview()
        QTimer.singleShot(0, lambda g=generation: self._render_next_inventory_batch(g))

    def _render_next_inventory_batch(self, generation: int) -> None:
        if generation != self._inventory_render_generation:
            return
        if not hasattr(self, "standard_table"):
            return
        rows = self._inventory_render_rows
        start = self._inventory_render_cursor
        if start >= len(rows):
            self._finish_inventory_table_render(generation)
            return
        # A normal local cache is ~200 rows; render it in one hidden batch so the
        # first visible frame is already complete.  Larger/manual inventories retain
        # bounded batches to keep the GUI responsive.
        batch_size = max(self._inventory_render_batch_size, len(rows)) if getattr(self, "_inventory_atomic_reveal", False) and len(rows) <= 500 else self._inventory_render_batch_size
        stop = min(len(rows), start + batch_size)
        table = self.standard_table
        previous_signals = table.blockSignals(True)
        model = table.model()
        previous_model_signals = model.blockSignals(True) if model is not None else False
        previous_suppression = self._suppress_classification_marker_persistence
        self._suppress_classification_marker_persistence = True
        table.setUpdatesEnabled(False)
        try:
            for row in range(start, stop):
                self._populate_server_inventory_row_fast(row, rows[row])
            self._inventory_render_cursor = stop
        finally:
            table.setUpdatesEnabled(True)
            if model is not None:
                model.blockSignals(previous_model_signals)
            table.blockSignals(previous_signals)
            self._suppress_classification_marker_persistence = previous_suppression
        table.viewport().update()
        if stop < len(rows):
            QTimer.singleShot(0, lambda g=generation: self._render_next_inventory_batch(g))
        else:
            self._finish_inventory_table_render(generation)

    def _finish_inventory_table_render(self, generation: int) -> None:
        if generation != self._inventory_render_generation:
            return
        table = self.standard_table
        # QTableWidget's default vertical header already renders 1-based row
        # section numbers.  Do not create 200 QTableWidgetItems just for labels.
        if self.standard_table_search.text().strip():
            self._apply_standard_table_filter()
        else:
            self._refresh_standard_table_overview()
        # Calculate the final geometry while the cache-restore table is still hidden,
        # then swap it in once.  This removes the empty framed-table flash without
        # introducing any modal/progress dialog.
        self._apply_fast_inventory_column_widths(recompute_content=True)
        self._refresh_standard_source_summary()
        table.setSortingEnabled(False)
        if getattr(self, "_inventory_atomic_reveal", False):
            self._set_local_catalog_loading_state(False)
            # v2.18.239: the complete table and all surrounding controls become
            # visible in the same final frame; no transient native frames are shown.
            self._set_catalog_page_loading_state(False)
            self._inventory_atomic_reveal = False
        table.viewport().update()
        if hasattr(self, "server_library_status") and self._server_file_inventory:
            marked = sum(
                1 for row in self._server_file_inventory
                if str(row.get("classification_marker", row.get("category_marker", "")) or "").strip()
            )
            self.server_library_status.setText(
                f"已从本机 AppData 缓存恢复：{len(self._server_file_inventory)} 个图元文件，"
                f"分类标记 {marked} 个；未访问服务器。"
            )

    def _refresh_standard_table_overview(self) -> None:
        """Refresh compact counters for the visible server-symbol inventory."""
        if not self._server_inventory_table_enabled:
            marked = sum(
                1
                for record in self._server_file_inventory
                if str(record.get("classification_marker", record.get("category_marker", "")) or "").strip()
            )
            if hasattr(self, "standard_table_overview"):
                self.standard_table_overview.setText(
                    f"服务器图元目录：本地缓存 {len(self._server_file_inventory)} 个，"
                    f"信息解析成功 {len(self._server_catalog_records)} 项，已分类 {marked} 个"
                )
            return
        if not hasattr(self, "standard_table"):
            return
        table = self.standard_table
        total = table.rowCount()
        visible = 0
        marked = 0
        for row in range(total):
            if not table.isRowHidden(row):
                visible += 1
            marker_item = table.item(row, 18)
            if marker_item is not None and marker_item.text().strip():
                marked += 1
        text = f"服务器图元目录（左侧为序号）：共 {total} 个文件 | 当前显示 {visible} 个"
        if self._server_file_inventory:
            text += f" | 服务器文件 {len(self._server_file_inventory)} 个"
        if self._server_catalog_records:
            text += f" | 信息解析成功 {len(self._server_catalog_records)} 项"
        text += f" | 已分类 {marked} 个"
        if hasattr(self, "standard_table_overview"):
            self.standard_table_overview.setText(text)
        # Catalog rows create column 18 as editable from the start.  Re-applying
        # flags to every row on each counter refresh only creates model churn.
        if self._legacy_profile_state_loaded:
            self._apply_classification_item_permissions()

    @staticmethod
    def _unique_standard_file_count(records: object) -> int:
        """Count unique standard G basenames without treating table rows as files."""
        names = {
            Path(str(row.get("original_name", "")).strip()).name.casefold()
            for row in records
            if isinstance(row, dict) and Path(str(row.get("original_name", "")).strip()).name
        } if isinstance(records, list) else set()
        return len(names)

    def _refresh_standard_source_summary(self) -> None:
        """Show remote-catalog sync metrics without standard-version concepts."""
        if not hasattr(self, "scan_summary"):
            return
        if self._server_inventory_table_enabled and hasattr(self, "standard_table"):
            table_rows = self.standard_table.rowCount()
            marked = sum(
                1 for row in range(table_rows)
                if self.standard_table.item(row, 18) is not None
                and self.standard_table.item(row, 18).text().strip()
            )
        else:
            table_rows = len(self._server_file_inventory)
            marked = sum(
                1
                for record in self._server_file_inventory
                if str(record.get("classification_marker", record.get("category_marker", "")) or "").strip()
            )

        payload = self._last_server_sync_payload if isinstance(self._last_server_sync_payload, dict) else {}
        matched = payload.get("matched_records", {})
        remote_total = int(payload.get("scanned_remote_files", 0) or 0)
        conflicts = payload.get("conflicts", {})
        errors = payload.get("errors", {})
        issue_count = (
            (len(conflicts) if isinstance(conflicts, dict) else 0)
            + (len(errors) if isinstance(errors, dict) else 0)
        )
        parsed = len(matched) if isinstance(matched, dict) else 0
        if remote_total:
            source_text = f"服务器目录：同步 {remote_total} 个 .g，信息解析成功 {parsed} 项"
            if issue_count:
                source_text += f"，异常 {issue_count} 项"
        elif self._server_catalog_records:
            source_text = f"服务器目录：当前已同步 {len(self._server_file_inventory)} 个文件"
        else:
            source_text = "服务器目录：尚未同步"
        added = payload.get("added_names", [])
        changed = payload.get("changed_names", [])
        unchanged = payload.get("unchanged_names", [])
        updated = payload.get("updated_files", [])
        self.scan_summary.setText(
            f"{source_text}；新增 {len(added) if isinstance(added, list) else 0} 个，"
            f"修改 {len(changed) if isinstance(changed, list) else 0} 个，"
            f"未变化 {len(unchanged) if isinstance(unchanged, list) else 0} 个，"
            f"服务器更新时间变化 {len(updated) if isinstance(updated, list) else 0} 个；"
            f"本地缓存 {table_rows} 个，已分类 {marked} 个。"
        )
        if hasattr(self, "active_profile_summary"):
            self.active_profile_summary.setText(
                f"本地同步目录：{source_text}；已分类 {marked} 个；服务器只读。"
            )

    @staticmethod
    def _observed_symbol_g_filename(devref: str) -> str:
        """Return the complete symbol-G filename encoded in a business-G devref."""
        value = str(devref or "").strip().lstrip("#")
        return value.split(":", 1)[0].strip() if value else ""

    @staticmethod
    def _same_symbol_g_filename(expected: str, actual: str) -> bool:
        """Return True only when two symbol-G basenames are the same."""
        expected_name = Path(str(expected or "").strip()).name
        actual_name = Path(str(actual or "").strip()).name
        return bool(expected_name and actual_name and expected_name.casefold() == actual_name.casefold())

    def _symbol_meta(self, devref: str) -> dict[str, object]:
        return dict(self._symbol_catalog.get(str(devref).strip(), {}))

    @staticmethod
    def _catalog_from_standard_records(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        catalog: dict[str, dict[str, object]] = {}
        for raw in records:
            row = dict(raw)
            devref = str(row.get("devref", "")).strip()
            if not devref:
                continue
            catalog[devref] = {
                "devref": devref,
                "element_tag": str(row.get("element_tag", "")).strip(),
                "element_id": str(row.get("element_id", "")).strip(),
                "source_file": str(row.get("original_name", "")).strip(),
                "width": float(row.get("width", 0.0) or 0.0),
                "height": float(row.get("height", 0.0) or 0.0),
                "align_center": list(row.get("align_center", [])),
                "pins": list(row.get("pins", [])),
                "pin_ids": list(row.get("pin_ids", [])),
                "pin_indices": list(row.get("pin_indices", [])),
                "rotations": [0, 90, 180, 270],
                "count": 1,
                "sha256": str(row.get("sha256", "")).strip(),
                "managed_path": str(row.get("managed_path", "")).strip(),
                "standard_source": str(row.get("standard_source", "server") or "server").strip().lower(),
                "remote_host": str(row.get("remote_host", "")).strip(),
                "remote_root": str(row.get("remote_root", "")).strip(),
                "remote_path": str(row.get("remote_path", "")).strip(),
                "relative_path": str(row.get("relative_path", "")).strip(),
                "remote_size": int(row.get("remote_size", 0) or 0),
                "remote_mtime": int(row.get("remote_mtime", 0) or 0),
                "cache_path": str(row.get("cache_path", "")).strip(),
                "synced_at": str(row.get("synced_at", "")).strip(),
                "classification_marker": str(row.get("classification_marker", row.get("category_marker", "")) or "").strip(),
                "category_marker": str(row.get("classification_marker", row.get("category_marker", "")) or "").strip(),
                "p_NameString": "",
                "key_name": "",
            }
        return catalog

    def _rebuild_symbol_catalog(self, records: list[dict[str, object]] | None = None) -> None:
        """Keep server metadata available while profile records remain authoritative."""
        server = self._catalog_from_standard_records(list(self._server_catalog_records.values()))
        if records is None:
            records = self._editor_standard_records()
        # A deliberately uploaded/confirmed Profile record wins over a same-devref
        # server catalog row.  The server copy is still retained in the separate
        # catalog for provenance and change detection.
        server.update(self._catalog_from_standard_records(records))
        self._symbol_catalog = server

    @staticmethod
    def _server_catalog_entry(record: dict[str, object]) -> dict[str, object]:
        """Render one parsed server symbol as an authoritative editor row."""
        devref = str(record.get("devref", "")).strip()
        file_name = Path(str(record.get("original_name", "")).strip()).name
        element_tag = str(record.get("element_tag", "")).strip()
        element_id = str(record.get("element_id", "")).strip()
        role = infer_device_type(
            role=element_id,
            source_file=file_name,
            element_tag=element_tag,
            element_id=element_id,
        )
        usage = infer_symbol_usage(role=role, source_file=file_name, element_tag=element_tag)
        return {
            "uid": "server-" + uuid4().hex,
            "candidate_only": False,
            "server_catalog_only": False,
            "server_devref": "",
            "scope": "ANY",
            "role": role or "服务器图元",
            "device_type": role or "服务器图元",
            "device_subtype": "",
            "device_level": default_device_level(usage),
            "symbol_usage": usage,
            "element_tag": element_tag,
            "standard_devref": devref,
            "match_attr": "devref",
            "match_value": devref,
            "observed_devref": devref,
            "observed_symbol_file": file_name,
            "observed_count": 0,
            "observed_files": [],
            "observed_examples": [],
            "classification_marker": str(record.get("classification_marker", record.get("category_marker", "")) or "").strip(),
            "category_marker": str(record.get("classification_marker", record.get("category_marker", "")) or "").strip(),
        }

    def _merge_server_catalog_rows(self) -> None:
        """Compatibility renderer for legacy editor rows."""
        if not self._server_catalog_records or not hasattr(self, "standard_table"):
            return
        name, version, active = self._selected_profile_key()
        profile = self.service.get_profile_version(name, version) if name and version is not None else None
        if profile is not None and (not active or profile.locked):
            return

        # Preserve only operator classification fields from an already displayed
        # row.  Identity and all geometry/provenance fields always come from the
        # current server record.  Rows that are not present in the server catalog
        # (including legacy business-G candidates) are deliberately removed from
        # the editable snapshot.
        previous_by_ref: dict[str, dict[str, object]] = {}
        previous_by_name: dict[str, dict[str, object]] = {}
        for previous in self._collect_custom_symbols():
            devref = str(previous.get("standard_devref", "")).strip()
            if devref:
                previous_by_ref[devref.casefold()] = dict(previous)
            for value in (
                previous.get("source_file", ""),
                previous.get("observed_symbol_file", ""),
            ):
                file_name = Path(str(value).strip()).name
                if file_name:
                    previous_by_name[file_name.casefold()] = dict(previous)

        server_entries: list[dict[str, object]] = []
        for devref, record in sorted(self._server_catalog_records.items(), key=lambda item: item[0].casefold()):
            entry = self._server_catalog_entry(record)
            file_name = Path(str(record.get("original_name", "")).strip()).name
            previous = previous_by_ref.get(devref.casefold()) or previous_by_name.get(file_name.casefold())
            if previous is not None:
                for key in ("scope", "role", "device_type", "device_subtype", "device_level", "symbol_usage", "classification_marker"):
                    if str(previous.get(key, "")).strip():
                        entry[key] = previous[key]
            server_entries.append(entry)

        self._server_catalog_ignored.clear()
        self._pending_standard_file_records = [
            dict(record)
            for record in self._server_catalog_records.values()
            if str(record.get("devref", "")).strip()
        ]
        self._load_custom_symbols(server_entries)
        self._apply_standard_table_filter()
        self._fit_standard_table_columns()

    def _editor_standard_records(self) -> list[dict[str, object]]:
        """Return current ACTIVE files plus pending uploads, with pending files winning.

        This makes partial updates safe: replacing one learned symbol standard does not
        force the user to re-upload any other standard files.
        """
        name, _version, active = self._selected_profile_key()
        current = self.service.load_profiles().get(name) if name and active else None
        merged: dict[str, dict[str, object]] = {}
        for raw in (current.managed_standard_files if current else []):
            row = dict(raw)
            devref = str(row.get("devref", "")).strip()
            if devref:
                merged[devref.casefold()] = row
        for raw in self._pending_standard_file_records:
            row = dict(raw)
            devref = str(row.get("devref", "")).strip()
            if devref:
                merged[devref.casefold()] = row
        return sorted(merged.values(), key=lambda row: str(row.get("devref", "")).casefold())

    def _fill_authoritative_combo(
        self, combo: WheelSafeComboBox, expected_tag: str, selected: str, records: list[dict[str, object]]
    ) -> None:
        """Populate with every uploaded authoritative G.

        ``expected_tag`` remains a business-drawing locator hint for the built-in
        role, not an upload restriction. The user-selected row is authoritative;
        filename/XML inference never blocks or silently reassigns a standard file.
        """
        combo.blockSignals(True)
        combo.clear()
        combo.setEditable(False)
        for raw in records:
            row = dict(raw)
            devref = str(row.get("devref", "")).strip()
            if not devref:
                continue
            filename = Path(str(row.get("original_name", "")).strip() or "standard.g").name
            combo.addItem(filename, devref)
            parsed_tag = str(row.get("element_tag", "")).strip() or "-"
            combo.setItemData(
                combo.count() - 1,
                "\n".join([
                    f"文件：{filename}",
                    f"devref：{devref}",
                    f"上传 G 解析 XML：{parsed_tag}",
                    f"当前行检查对象 XML：{expected_tag or '-'}",
                    f"主体 ID：{str(row.get('element_id', '')).strip() or '-'}",
                    "绑定依据：用户明确选择当前设备角色；解析类型仅作参考，不限制绑定。",
                ]),
                Qt.ItemDataRole.ToolTipRole,
            )
        index = combo.findData(selected) if selected else -1
        combo.setCurrentIndex(index if index >= 0 else -1)
        combo.blockSignals(False)
        self._refresh_standard_row(combo)

    def _populate_builtin_standard_combos(self, records: list[dict[str, object]], *, preserve_current: bool = True) -> None:
        selections = {
            "lbs": str(self.lbs_combo.currentData() or "").strip() if preserve_current else "",
            "breaker": str(self.breaker_combo.currentData() or "").strip() if preserve_current else "",
            "ground": str(self.ground_combo.currentData() or "").strip() if preserve_current else "",
            "normal_lbs": str(self.normal_lbs_combo.currentData() or "").strip() if preserve_current else "",
            "normal_breaker": str(self.normal_breaker_combo.currentData() or "").strip() if preserve_current else "",
            "normal_ground": str(self.normal_ground_combo.currentData() or "").strip() if preserve_current else "",
        }
        self._fill_authoritative_combo(self.lbs_combo, "CBreakerDis", selections["lbs"], records)
        self._fill_authoritative_combo(self.breaker_combo, "CBreakerDis", selections["breaker"], records)
        self._fill_authoritative_combo(self.ground_combo, "ZhaiWaiJieDiDaoZha", selections["ground"], records)
        self._fill_authoritative_combo(self.normal_lbs_combo, "CBreakerDis", selections["normal_lbs"], records)
        self._fill_authoritative_combo(self.normal_breaker_combo, "CBreakerDis", selections["normal_breaker"], records)
        self._fill_authoritative_combo(self.normal_ground_combo, "ZhaiWaiJieDiDaoZha", selections["normal_ground"], records)

    def _refresh_symbol_properties(self, row: int, devref: str) -> None:
        meta = self._symbol_meta(devref)
        element_id = str(meta.get("element_id", "")).strip() or (devref.split(":", 1)[1] if ":" in devref else "-")
        width = self._format_dimension(meta.get("width"))
        height = self._format_dimension(meta.get("height"))
        size_text = f"{width}×{height}" if width != "-" and height != "-" else "-"
        align = meta.get("align_center", [])
        if isinstance(align, (list, tuple)) and len(align) >= 2:
            align_text = f"({self._format_dimension(align[0])},{self._format_dimension(align[1])})"
        else:
            align_text = "-"
        pins = meta.get("pins", [])
        if isinstance(pins, list) and pins:
            pin_texts = [
                f"({self._format_dimension(pair[0])},{self._format_dimension(pair[1])})"
                for pair in pins
                if isinstance(pair, (list, tuple)) and len(pair) >= 2
            ]
            pins_text = f"{len(pin_texts)}: " + "; ".join(pin_texts)
        else:
            pins_text = "-"
        for column, value in ((4, element_id or "-"), (5, size_text), (6, align_text), (7, pins_text)):
            item = self.standard_table.item(row, column)
            if item is None:
                item = self._set_readonly_cell(row, column, value)
            else:
                item.setText(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setToolTip(
                "\n".join([
                    f"devref: {devref or '-'}",
                    f"XML: {meta.get('element_tag', '-') or '-'}",
                    f"主体 ID: {element_id or '-'}",
                    f"w/h: {size_text}",
                    f"AlignCenter: {align_text}",
                    f"Pins: {pins_text}",
                    f"旋转样本: {meta.get('rotations', []) or '-'}",
                    f"来源: {meta.get('source_file', '-') or '-'}",
                    f"p_NameString: {meta.get('p_NameString', '-') or '-'}",
                    f"key_name: {meta.get('key_name', '-') or '-'}",
                ])
            )

    def _clear_custom_standard_rows(self) -> None:
        while self.standard_table.rowCount() > len(self._standard_specs):
            self.standard_table.removeRow(self.standard_table.rowCount() - 1)

    def _custom_standard_rows(self) -> list[int]:
        result: list[int] = []
        for row in range(len(self._standard_specs), self.standard_table.rowCount()):
            marker_item = self.standard_table.item(row, 0)
            if marker_item is not None and marker_item.data(Qt.ItemDataRole.UserRole) == "custom":
                result.append(row)
        return result

    @staticmethod
    def _profile_standard_rows(profile: SiteSmartProfile) -> list[dict[str, object]]:
        """Return generic standard rows, migrating legacy fixed RMU roles for display/save.

        v2.18.105 keeps the six pre-created SMART/NORMAL system rows. Old profiles
        remain readable: any legacy role that already has an authoritative uploaded
        devref is represented as a normal generic row. Once the user saves again,
        the profile is persisted using ``custom_symbols`` only.
        """
        rows = [dict(item) for item in profile.custom_symbols if isinstance(item, dict)]
        legacy = [
            ("legacy-smart-lbs", "SMART", "LBS", "CBreakerDis", profile.smart_lbs_devref),
            ("legacy-smart-breaker", "SMART", "Circuit Breaker", "CBreakerDis", profile.smart_breaker_devref),
            ("legacy-smart-ground", "SMART", "接地刀闸", "ZhaiWaiJieDiDaoZha", profile.smart_ground_devref),
            ("legacy-normal-lbs", "NORMAL", "LBS", "CBreakerDis", profile.normal_lbs_devref),
            ("legacy-normal-breaker", "NORMAL", "Circuit Breaker", "CBreakerDis", profile.normal_breaker_devref),
            ("legacy-normal-ground", "NORMAL", "接地刀闸", "ZhaiWaiJieDiDaoZha", profile.normal_ground_devref),
        ]

        # Index existing generic definitions. If the same uploaded symbol was used
        # by SMART and NORMAL legacy rows, collapse it to one ANY row rather than
        # recreating the old paired-row UI.
        indexed: dict[tuple[str, str, str], int] = {}
        for idx, row in enumerate(rows):
            devref = str(row.get("standard_devref", "")).strip().casefold()
            role = str(row.get("role", row.get("device_type", ""))).strip().casefold()
            tag = str(row.get("element_tag", "")).strip().casefold()
            if devref:
                indexed[(devref, role, tag)] = idx

        catalog = profile.symbol_catalog if isinstance(profile.symbol_catalog, dict) else {}
        for uid, scope, role, default_tag, devref_raw in legacy:
            devref = str(devref_raw or "").strip()
            if not devref:
                continue
            meta = dict(catalog.get(devref, {})) if isinstance(catalog.get(devref, {}), dict) else {}
            element_tag = str(meta.get("element_tag", "")).strip() or default_tag
            key = (devref.casefold(), role.casefold(), element_tag.casefold())
            if key in indexed:
                existing = rows[indexed[key]]
                prior_scope = str(existing.get("scope", "ANY")).strip().upper() or "ANY"
                if prior_scope != scope:
                    existing["scope"] = "ANY"
                continue
            indexed[key] = len(rows)
            rows.append({
                "uid": uid,
                "scope": scope,
                "role": role,
                "device_type": role,
                "device_subtype": "",
                "device_level": "设备内部部件",
                "symbol_usage": "设备组成图元",
                "element_tag": element_tag,
                "standard_devref": devref,
                "match_attr": "devref",
                "match_value": devref,
                "enabled": True,
                "source_file": str(meta.get("source_file", "")).strip(),
                "observed_devref": devref,
                "observed_count": 0,
                "observed_files": [],
                "observed_examples": [],
            })
        return rows

    def _set_standard_file_cell(self, row: int, devref: str) -> QTableWidgetItem:
        """Render the authoritative G as a normal table cell and keep devref as data."""
        devref = str(devref or "").strip()
        meta = self._symbol_meta(devref)
        filename = Path(str(meta.get("source_file", "")).strip()).name
        display = filename or (self._devref_short(devref) if devref else "-")
        item = self.standard_table.item(row, 3)
        if item is None:
            item = self._set_readonly_cell(row, 3, display)
        else:
            item.setText(display)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setData(Qt.ItemDataRole.UserRole, devref)
        item.setToolTip(
            "\n".join([
                f"文件：{filename or '-'}",
                f"devref：{devref or '-'}",
                f"XML：{str(meta.get('element_tag', '')).strip() or '-'}",
                f"主体 ID：{str(meta.get('element_id', '')).strip() or '-'}",
            "绑定方式：直接使用只读服务器 element 目录中已解析的图元。",
            ])
        )
        return item

    def _standard_file_devref(self, row: int) -> str:
        item = self.standard_table.item(row, 3)
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or "").strip()

    @staticmethod
    def _server_relative_path(meta: dict[str, object]) -> str:
        root = str(meta.get("remote_root", "")).strip()
        remote = str(meta.get("remote_path", "")).strip()
        if not remote:
            return "-"
        try:
            return str(PurePosixPath(remote).relative_to(PurePosixPath(root))) if root else PurePosixPath(remote).name
        except Exception:
            return PurePosixPath(remote).name

    def _standard_download_source(self, row: int) -> Path | None:
        """Return the local read-only source that can be exported for a row.

        Server G files are downloaded into the local symbol cache during the
        server-only sync.  Exporting a row therefore copies that cache file (or
        a local managed snapshot for a historical row); it never opens a write
        channel to the server.
        """
        devref = self._standard_file_devref(row)
        marker = self.standard_table.item(row, 0)
        if not devref and marker is not None:
            devref = str(marker.data(Qt.ItemDataRole.UserRole + 8) or "").strip()
        if not devref:
            return None
        meta = self._symbol_meta(devref)
        # A historical or locked version must export its frozen local object;
        # an editable ACTIVE draft should export the latest server cache instead.
        _name, _version, active = self._selected_profile_key()
        frozen_version = bool(_name and (not active or self._selected_profile_locked))
        source_keys = ("managed_path", "cache_path") if frozen_version else ("cache_path", "managed_path")
        for key in source_keys:
            raw = str(meta.get(key, "") or "").strip()
            if not raw:
                continue
            source = Path(raw)
            if source.is_file():
                return source
        return None

    def _refresh_selected_standard_download_action(self, row: int | None = None) -> None:
        """Enable the one lightweight download action for the selected row."""
        button = getattr(self, "standard_download_selected_button", None)
        if not isinstance(button, QPushButton):
            return
        if row is None:
            row = self.standard_table.currentRow() if hasattr(self, "standard_table") else -1
        source = self._standard_download_source(int(row)) if row is not None and int(row) >= 0 else None
        button.setEnabled(source is not None)
        if source is not None:
            button.setToolTip(
                f"下载选中的图元 {source.name}。文件来自本机缓存；不会修改或写入服务器。"
            )
        elif row is not None and int(row) >= 0:
            button.setToolTip(
                "当前图元还没有可用的本地文件缓存。请先点击‘同步服务器图元信息’，再下载。"
            )
        else:
            button.setToolTip(
                "先在下方表格中选择一个图元。下载只复制本机图元缓存，不会修改服务器。"
            )

    def _download_selected_standard(self) -> None:
        """Export the selected cached symbol without creating per-row widgets."""
        row = self.standard_table.currentRow() if hasattr(self, "standard_table") else -1
        if row < 0:
            QMessageBox.information(self, "请选择图元", "请先在图元表格中选择一行，再点击下载。")
            return
        self._download_standard_row_index(row)

    def _refresh_standard_download_button(self, row: int) -> None:
        """Legacy per-row export helper; avoid hidden cell widgets in operator mode."""
        if row < 0 or row >= self.standard_table.rowCount():
            return
        # The operator table hides legacy column 17.  Do not create 200 hidden
        # QPushButtons just to support download: the toolbar action above handles
        # the selected row and keeps table construction lightweight.
        if self.standard_table.isColumnHidden(17):
            if row == self.standard_table.currentRow():
                self._refresh_selected_standard_download_action(row)
            return
        button = self.standard_table.cellWidget(row, 17)
        if not isinstance(button, QPushButton):
            button = QPushButton("下载")
            button.setAutoDefault(False)
            button.clicked.connect(self._download_standard_row)
            self.standard_table.setCellWidget(row, 17, button)
        source = self._standard_download_source(row)
        button.setEnabled(source is not None)
        if source is not None:
            button.setToolTip(f"下载服务器/本地标准图元：{source.name}")
        else:
            button.setToolTip("当前行尚无本地图元缓存，请先读取/同步服务器全部图元。")

    def _download_standard_row(self) -> None:
        """Compatibility slot for the old hidden per-row download button."""
        button = self.sender()
        if not isinstance(button, QPushButton):
            return
        row = next(
            (
                index
                for index in range(self.standard_table.rowCount())
                if self.standard_table.cellWidget(index, 17) is button
            ),
            -1,
        )
        if row >= 0:
            self._download_standard_row_index(row)

    def _download_standard_row_index(self, row: int) -> None:
        """Copy one selected cached standard G to a user-selected local path."""
        source = self._standard_download_source(row) if row >= 0 else None
        if source is None:
            QMessageBox.information(
                self,
                "图元尚未缓存",
                "当前行没有可用的本地图元文件，请先点击‘同步服务器图元信息’。\n"
                "下载操作只读取本机缓存，服务器始终只读。",
            )
            self._refresh_selected_standard_download_action(row)
            return

        default_path = default_workspace() / "symbol-downloads" / source.name
        target_name, _ = QFileDialog.getSaveFileName(
            self,
            "下载标准图元",
            str(default_path),
            "G 图元文件 (*.g);;所有文件 (*)",
        )
        if not target_name:
            return
        target = Path(target_name)
        try:
            if target.resolve(strict=False) == source.resolve(strict=False):
                QMessageBox.information(self, "无需复制", "目标位置就是当前本地图元缓存，无需重复复制。")
                return
        except OSError:
            pass
        if target.exists() and QMessageBox.question(
            self,
            "确认覆盖本地文件",
            f"本地文件已存在：\n{target}\n\n是否覆盖？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        temp = target.with_name(f".{target.name}.{uuid4().hex}.download")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, temp)
            temp.replace(target)
        except Exception as exc:
            temp.unlink(missing_ok=True)
            QMessageBox.warning(self, "下载图元失败", str(exc))
            return
        QMessageBox.information(
            self,
            "图元下载完成",
            f"已将图元文件复制到本地：\n{target}\n\n服务器文件未被修改。",
        )

    def _insert_custom_standard_row(
        self, entry: dict[str, object] | None = None, *, refresh_layout: bool = True
    ) -> int:
        entry = dict(entry or {})
        row = self.standard_table.rowCount()
        self.standard_table.insertRow(row)

        server_catalog_only = bool(entry.get("server_catalog_only", False)) and not str(entry.get("standard_devref", "")).strip()
        server_devref = str(entry.get("server_devref", "")).strip() if server_catalog_only else ""
        candidate_only = (bool(entry.get("candidate_only", False)) and not str(entry.get("standard_devref", "")).strip()) or server_catalog_only
        observed_devref = str(entry.get("observed_devref", "")).strip()
        if server_catalog_only and not observed_devref:
            observed_devref = server_devref
        # Compatibility: only a legacy devref locator can safely stand in for
        # discovery evidence. Old p_NameString/key_name values must never be
        # rendered as if they were scanned symbol-G filenames.
        legacy_match_attr = str(entry.get("match_attr", "devref")).strip() or "devref"
        if not observed_devref and legacy_match_attr == "devref":
            observed_devref = str(entry.get("match_value", "")).strip()
        observed_symbol_file = str(entry.get("observed_symbol_file", "")).strip() or self._observed_symbol_g_filename(observed_devref)
        observed_count = max(0, int(entry.get("observed_count", entry.get("count", 0)) or 0))
        observed_files = [str(item) for item in entry.get("observed_files", entry.get("files", [])) if str(item).strip()] if isinstance(entry.get("observed_files", entry.get("files", [])), list) else []
        observed_examples = [dict(item) for item in entry.get("observed_examples", entry.get("sample_positions", [])) if isinstance(item, dict)] if isinstance(entry.get("observed_examples", entry.get("sample_positions", [])), list) else []

        scope_combo = WheelSafeComboBox()
        scope_combo.addItems(["ANY", "SMART", "NORMAL"])
        scope = str(entry.get("scope", entry.get("suggested_scope", "ANY"))).strip().upper() or "ANY"
        scope_combo.setCurrentText(scope if scope in {"ANY", "SMART", "NORMAL"} else "ANY")
        self.standard_table.setCellWidget(row, 0, scope_combo)
        marker = QTableWidgetItem("")
        marker.setData(Qt.ItemDataRole.UserRole, "custom")
        marker.setData(Qt.ItemDataRole.UserRole + 1, str(entry.get("uid", "")).strip() or uuid4().hex)
        marker.setData(Qt.ItemDataRole.UserRole + 3, candidate_only)
        marker.setData(Qt.ItemDataRole.UserRole + 4, observed_devref)
        marker.setData(Qt.ItemDataRole.UserRole + 5, observed_count)
        marker.setData(Qt.ItemDataRole.UserRole + 6, observed_files)
        marker.setData(Qt.ItemDataRole.UserRole + 7, observed_examples)
        marker.setData(Qt.ItemDataRole.UserRole + 8, server_devref)
        self.standard_table.setItem(row, 0, marker)

        role_default = str(entry.get("role", entry.get("device_type", entry.get("suggested_device_type", "")))).strip()
        if not role_default and observed_devref:
            observed_file = str(entry.get("observed_symbol_file", "")).strip()
            observed_subject = str(entry.get("observed_subject", "")).strip()
            role_default = infer_device_type(
                role=observed_subject, source_file=observed_file,
                element_tag=str(entry.get("element_tag", "")).strip(), element_id=observed_subject,
            )
        role_item = QTableWidgetItem(role_default or "自定义图元")
        self.standard_table.setItem(row, 1, role_item)
        tag_item = QTableWidgetItem(str(entry.get("element_tag", "")).strip())
        self.standard_table.setItem(row, 2, tag_item)

        selected_devref = str(entry.get("standard_devref", "")).strip()
        self._set_standard_file_cell(row, selected_devref)

        # Columns 4~7 are authoritative standard properties and deliberately stay
        # blank until the user uploads the real symbol-definition G. Business G
        # observations must never become the standard geometry.
        for column in (4, 5, 6, 7):
            self._set_readonly_cell(row, column, "-")

        # Locator rule/condition are intentionally not user-editable anymore.
        # Internally the row is matched by the devref observed during discovery;
        # after upload, the authoritative devref is also accepted by the engine so
        # repeated checks validate the corrected/new symbol as well.
        self._set_readonly_cell(row, 8, "图形 G 发现" if candidate_only else "-")
        self._set_readonly_cell(row, 9, "待服务器匹配" if candidate_only else "待确认")

        meta = self._symbol_meta(selected_devref)
        auto_usage = not str(entry.get("symbol_usage", entry.get("suggested_usage", ""))).strip()
        usage = str(entry.get("symbol_usage", entry.get("suggested_usage", ""))).strip()
        if usage not in SYMBOL_USAGE_VALUES:
            usage = infer_symbol_usage(
                role=role_item.text(),
                source_file=str(meta.get("source_file", entry.get("observed_symbol_file", "")) or ""),
                element_tag=tag_item.text(),
            )
        usage_combo = WheelSafeComboBox()
        usage_combo.addItems(list(SYMBOL_USAGE_VALUES))
        usage_combo.setCurrentText(usage)
        self.standard_table.setCellWidget(row, 10, usage_combo)
        self.standard_table.setItem(row, 11, QTableWidgetItem(str(entry.get("device_subtype", "")).strip()))

        level = str(entry.get("device_level", "")).strip()
        if level not in DEVICE_LEVEL_VALUES:
            level = default_device_level(usage)
        level_combo = WheelSafeComboBox()
        level_combo.addItems(list(DEVICE_LEVEL_VALUES))
        level_combo.setCurrentText(level)
        self.standard_table.setCellWidget(row, 12, level_combo)
        marker.setData(Qt.ItemDataRole.UserRole + 2, auto_usage)

        self._set_readonly_cell(row, 13, observed_symbol_file or "-")
        self._set_readonly_cell(row, 14, observed_devref or "-")
        self._set_readonly_cell(row, 15, str(observed_count))
        example_text = self._discovery_example_text(observed_examples, observed_files)
        self._set_readonly_cell(row, 16, example_text or "-")
        if observed_devref:
            tooltip = self._discovery_tooltip(entry, observed_devref, observed_count, observed_files, observed_examples)
            for column in (13, 14, 15, 16):
                item = self.standard_table.item(row, column)
                if item is not None:
                    item.setToolTip(tooltip)

        def usage_changed(_index: int, m=marker, u=usage_combo, lv=level_combo) -> None:
            m.setData(Qt.ItemDataRole.UserRole + 2, False)
            lv.setCurrentText(default_device_level(u.currentText()))

        usage_combo.activated.connect(usage_changed)

        self._refresh_custom_standard_row(row)
        self._refresh_standard_download_button(row)
        if refresh_layout:
            self._fit_standard_table_columns()
        return row

    @staticmethod
    def _discovery_example_text(examples: list[dict[str, object]], files: list[str]) -> str:
        if examples:
            first = examples[0]
            file_name = str(first.get("file", "")).strip()
            element_id = str(first.get("element_id", "")).strip()
            try:
                x = float(first.get("x", 0.0) or 0.0)
                y = float(first.get("y", 0.0) or 0.0)
                pos = f"({x:g}, {y:g})"
            except (TypeError, ValueError):
                pos = ""
            bits = [value for value in (file_name, f"id={element_id}" if element_id else "", pos) if value]
            return " · ".join(bits)
        if files:
            return files[0]
        return ""

    @staticmethod
    def _discovery_tooltip(
        entry: dict[str, object],
        observed_devref: str,
        observed_count: int,
        observed_files: list[str],
        observed_examples: list[dict[str, object]],
    ) -> str:
        names = [str(item) for item in entry.get("sample_names", []) if str(item).strip()] if isinstance(entry.get("sample_names", []), list) else []
        symbol_file = str(entry.get("observed_symbol_file", "")).strip()
        if not symbol_file:
            value = str(observed_devref or "").strip().lstrip("#")
            symbol_file = value.split(":", 1)[0].strip() if value else ""
        lines = [
            "业务图形 G 发现信息（仅作候选，不是标准）：",
            f"扫描图元 G 文件全名：{symbol_file or '-'}",
            f"devref：{observed_devref or '-'}",
            f"出现次数：{observed_count}",
            f"图形 G 文件：{', '.join(observed_files[:12]) or '-'}",
        ]
        if names:
            lines.append(f"实例名称样本：{', '.join(names[:8])}")
        if observed_examples:
            formatted = []
            for item in observed_examples[:5]:
                formatted.append(
                    f"{item.get('file', '-')} / id={item.get('element_id', '-') or '-'} / "
                    f"x={item.get('x', '-')}, y={item.get('y', '-')}"
                )
            lines.append("位置样本：" + "；".join(formatted))
        lines.append("w×h / AlignCenter / Pins 以服务器标准图元 G 为准。")
        return "\n".join(lines)

    def _refresh_custom_standard_row(self, row: int) -> None:
        if row < len(self._standard_specs) or row >= self.standard_table.rowCount():
            return
        devref = self._standard_file_devref(row)
        marker_item = self.standard_table.item(row, 0)
        server_devref = (
            str(marker_item.data(Qt.ItemDataRole.UserRole + 8) or "").strip()
            if marker_item is not None else ""
        )
        display_devref = devref or server_devref
        self._set_standard_file_cell(row, devref)
        meta = self._symbol_meta(display_devref)
        if not devref and server_devref:
            source_file = Path(str(meta.get("source_file", "")).strip()).name
            standard_item = self.standard_table.item(row, 3)
            if standard_item is not None:
                standard_item.setText(source_file or self._devref_short(server_devref))
                standard_item.setToolTip(
                    "\n".join([
                        f"文件：{source_file or '-'}",
                        f"devref：{server_devref}",
                        f"服务器：{meta.get('remote_host', '-') or '-'}",
                        f"远程路径：{meta.get('remote_path', '-') or '-'}",
                        "状态：服务器已读取，尚未手动更新当前标准。",
                    ])
                )
        tag_item = self.standard_table.item(row, 2)
        if tag_item is not None and not tag_item.text().strip() and meta.get("element_tag"):
            tag_item.setText(str(meta.get("element_tag", "")))
        self._refresh_symbol_properties(row, display_devref)
        usage_combo = self.standard_table.cellWidget(row, 10)
        level_combo = self.standard_table.cellWidget(row, 12)
        if (
            marker_item is not None
            and bool(marker_item.data(Qt.ItemDataRole.UserRole + 2))
            and isinstance(usage_combo, WheelSafeComboBox)
        ):
            inferred = infer_symbol_usage(
                role=(self.standard_table.item(row, 1).text() if self.standard_table.item(row, 1) else ""),
                source_file=str(meta.get("source_file", "") or ""),
                element_tag=(self.standard_table.item(row, 2).text() if self.standard_table.item(row, 2) else ""),
            )
            # A discovery row may carry a stronger usage suggestion (for example a
            # .zt.icn.g status symbol) even before an authoritative standard exists.
            if not devref and marker_item is not None:
                observed = str(marker_item.data(Qt.ItemDataRole.UserRole + 4) or "").strip()
                discovery = self._graphic_discovery_catalog.get(observed, {})
                suggested = str(discovery.get("suggested_usage", "")).strip()
                if suggested in SYMBOL_USAGE_VALUES:
                    inferred = suggested
            usage_combo.blockSignals(True)
            usage_combo.setCurrentText(inferred)
            usage_combo.blockSignals(False)
            if isinstance(level_combo, WheelSafeComboBox):
                level_combo.setCurrentText(default_device_level(inferred))
        source_item = self.standard_table.item(row, 8) or self._set_readonly_cell(row, 8, "-")
        source_file = Path(str(meta.get("source_file", "")).strip()).name
        standard_source = str(meta.get("standard_source", "server") or "server").strip().lower()
        candidate_only = bool(marker_item.data(Qt.ItemDataRole.UserRole + 3)) if marker_item is not None else False
        observed_count = int(marker_item.data(Qt.ItemDataRole.UserRole + 5) or 0) if marker_item is not None else 0
        observed_devref = str(marker_item.data(Qt.ItemDataRole.UserRole + 4) or "").strip() if marker_item is not None else ""
        observed_file_item = self.standard_table.item(row, 13) or self._set_readonly_cell(row, 13, "-")
        observed_file_item.setText(self._observed_symbol_g_filename(observed_devref) or "-")
        if not devref and server_devref:
            source_item.setText("服务器图元库 · 待确认")
            source_item.setToolTip("服务器图元目录已读取；点击“确认选中服务器图元”后才会纳入当前编辑版本。")
        elif devref and source_file and standard_source == "server":
            remote_path = str(meta.get("remote_path", "")).strip()
            remote_mtime = int(meta.get("remote_mtime", 0) or 0)
            synced_at = str(meta.get("synced_at", "")).strip()
            source_item.setText("服务器图元库")
            source_item.setToolTip(
                "\n".join([
                    f"文件：{source_file}",
                    f"服务器：{meta.get('remote_host', '-') or '-'}",
                    f"远程路径：{remote_path or '-'}",
                    f"服务器 mtime：{remote_mtime or '-'}",
                    f"最后同步：{synced_at or '-'}",
                ])
            )
        elif devref and source_file:
            source_item.setText("服务器图元库")
            source_item.setToolTip(source_file or "服务器标准图元")
        elif candidate_only:
            source_item.setText("图形 G 发现")
            source_item.setToolTip("历史候选记录仅作兼容展示；当前标准只接受只读服务器 element 目录中的图元。")
        else:
            source_item.setText("未匹配服务器图元" if not devref else "-")
            source_item.setToolTip(source_file or "未匹配服务器标准图元")
        if standard_source == "server" and meta:
            relative_path = self._server_relative_path(meta)
            path_item = self.standard_table.item(row, 19) or self._set_readonly_cell(row, 19, "-")
            path_item.setText(relative_path)
            path_item.setToolTip(
                f"服务器相对路径：{relative_path}\n服务器完整路径：{meta.get('remote_path', '-') or '-'}"
            )
            path_item.setData(Qt.ItemDataRole.UserRole + 1, str(meta.get("remote_path", "")).strip())
            path_item.setData(Qt.ItemDataRole.UserRole + 2, str(meta.get("remote_host", "")).strip())
            path_item.setData(Qt.ItemDataRole.UserRole + 3, str(meta.get("remote_root", "")).strip())
        elif self.standard_table.item(row, 19) is None:
            self._set_readonly_cell(row, 19, "-")
        marker_item = self.standard_table.item(row, 18)
        if marker_item is None:
            marker_item = QTableWidgetItem()
            self.standard_table.setItem(row, 18, marker_item)
        marker_value = str(meta.get("classification_marker", meta.get("category_marker", "")) or "").strip()
        # Always assign the text, including an empty value. This prevents a
        # cleared marker from being resurrected by a later row refresh.
        marker_item.setText(marker_value)
        marker_item.setToolTip("用户维护的分类标记；用于后续程序分类，保存在本地服务器图元清单，不会写回服务器。")
        marker_item.setData(Qt.ItemDataRole.UserRole + 1, str(meta.get("remote_path", "")).strip())
        marker_item.setData(Qt.ItemDataRole.UserRole + 2, str(meta.get("remote_host", "")).strip())
        marker_item.setData(Qt.ItemDataRole.UserRole + 3, str(meta.get("remote_root", "")).strip())
        status_item = self.standard_table.item(row, 9) or self._set_readonly_cell(row, 9, "待确认")
        if not devref and server_devref:
            status_item.setText("服务器已读取 · 待确认")
        elif not devref:
            status_item.setText(f"发现 {observed_count} 次 · 待服务器匹配" if candidate_only else "缺少服务器标准图元")
        elif not (self.standard_table.item(row, 2) and self.standard_table.item(row, 2).text().strip()):
            status_item.setText("缺少 XML 元素")
        elif standard_source == "server" and observed_count:
            status_item.setText(f"READY · 服务器已同步 · 业务G发现 {observed_count} 次")
        elif standard_source == "server":
            status_item.setText("READY · 服务器已同步")
        elif observed_count:
            status_item.setText(f"READY · 业务G发现 {observed_count} 次")
        else:
            status_item.setText("就绪")
        self._refresh_standard_download_button(row)

    def _add_custom_standard(self) -> None:
        row = self._insert_custom_standard_row()
        self.standard_table.selectRow(row)
        self.standard_table.scrollToItem(self.standard_table.item(row, 1))
        self._update_action_state()

    def _confirm_selected_server_symbol(self) -> None:
        row = self.standard_table.currentRow()
        if row < len(self._standard_specs) or row < 0:
            QMessageBox.information(self, "请选择服务器图元", "请先选择一个服务器图元目录中的待确认行。")
            return
        marker = self.standard_table.item(row, 0)
        server_devref = (
            str(marker.data(Qt.ItemDataRole.UserRole + 8) or "").strip()
            if marker is not None else ""
        )
        if not server_devref:
            QMessageBox.information(self, "无需确认", "当前行不是尚未确认的服务器图元。")
            return
        if self._selected_profile_key()[0] and not self._selected_profile_key()[2]:
            QMessageBox.information(self, "历史版本只读", "历史版本不能确认服务器图元，请先恢复为新的编辑版本。")
            return
        if marker is not None:
            marker.setData(Qt.ItemDataRole.UserRole + 8, "")
            marker.setData(Qt.ItemDataRole.UserRole + 3, False)
        server_record = self._server_catalog_records.get(server_devref)
        if server_record is not None:
            pending_by_devref = {
                str(item.get("devref", "")).casefold(): dict(item)
                for item in self._pending_standard_file_records
                if str(item.get("devref", "")).strip()
            }
            pending_by_devref[server_devref.casefold()] = dict(server_record)
            self._pending_standard_file_records = list(pending_by_devref.values())
        self._set_standard_file_cell(row, server_devref)
        self._refresh_custom_standard_row(row)
        self._rebuild_symbol_catalog()
        self.profile_status.setText(
            f"待保存：已确认服务器图元 {server_devref}。保存后才会进入当前标准版本。"
        )
        self._update_action_state()

    def _delete_selected_custom_standard(self) -> None:
        row = self.standard_table.currentRow()
        if row >= 0:
            marker = self.standard_table.item(row, 0)
            server_devref = (
                str(marker.data(Qt.ItemDataRole.UserRole + 8) or "").strip()
                if marker is not None else ""
            )
            observed_devref = (
                str(marker.data(Qt.ItemDataRole.UserRole + 4) or "").strip()
                if marker is not None else ""
            )
            # A row discovered from business G is a separate piece of metadata from
            # the authoritative standard itself.  Before v2.18.115, deleting the row
            # removed it only from the visible table; Save -> reload then replayed the
            # still-persisted discovery_catalog and the row appeared again even though
            # the user had not rescanned.  Treat Delete as an explicit Profile-level
            # ignore decision and remove the current in-memory discovery entry too.
            if observed_devref and not server_devref:
                self._discovery_decisions[observed_devref] = "ignored"
                self._graphic_discovery_catalog.pop(observed_devref, None)
            if server_devref:
                self._server_catalog_ignored.add(server_devref.casefold())
            self.standard_table.removeRow(row)
        self._apply_standard_table_filter()
        self._update_action_state()

    def _add_unmapped_scanned_symbols(self) -> None:
        """Legacy entry retained for compatibility; business G can no longer become a standard."""
        QMessageBox.information(
            self,
            "缺少服务器标准图元",
            "业务单线图中发现的 devref 只能作为检查线索，不能直接加入图元标准。\n"
            "请先读取服务器 element 目录，确认对应图元定义文件可解析，再将其绑定到业务类型/图元角色。",
        )

    def _collect_custom_symbols(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for row in self._custom_standard_rows():
            marker_item = self.standard_table.item(row, 0)
            scope_combo = self.standard_table.cellWidget(row, 0)
            usage_combo = self.standard_table.cellWidget(row, 10)
            level_combo = self.standard_table.cellWidget(row, 12)
            if (
                not isinstance(scope_combo, WheelSafeComboBox)
                or not isinstance(usage_combo, WheelSafeComboBox)
                or not isinstance(level_combo, WheelSafeComboBox)
            ):
                continue
            devref = self._standard_file_devref(row)
            role = (self.standard_table.item(row, 1).text() if self.standard_table.item(row, 1) else "").strip()
            element_tag = (self.standard_table.item(row, 2).text() if self.standard_table.item(row, 2) else "").strip()
            candidate_only = bool(marker_item.data(Qt.ItemDataRole.UserRole + 3)) if marker_item else False
            server_catalog_only = bool(
                marker_item is not None
                and str(marker_item.data(Qt.ItemDataRole.UserRole + 8) or "").strip()
                and not devref
            )
            # A discovered business-G row is intentionally allowed to stay pending.
            # It is not part of the authoritative standard until the user uploads
            # a real icon-definition G into the row.
            if (candidate_only or server_catalog_only) and not devref:
                continue
            if not devref and not role and not element_tag:
                continue
            meta = self._symbol_meta(devref)
            observed_devref = str(marker_item.data(Qt.ItemDataRole.UserRole + 4) or "").strip() if marker_item else ""
            observed_count = max(0, int(marker_item.data(Qt.ItemDataRole.UserRole + 5) or 0)) if marker_item else 0
            observed_files = marker_item.data(Qt.ItemDataRole.UserRole + 6) if marker_item else []
            observed_examples = marker_item.data(Qt.ItemDataRole.UserRole + 7) if marker_item else []
            classification_marker = (
                self.standard_table.item(row, 18).text().strip()
                if self.standard_table.item(row, 18) is not None else ""
            )
            result.append({
                "uid": str(marker_item.data(Qt.ItemDataRole.UserRole + 1) or uuid4().hex) if marker_item else uuid4().hex,
                "scope": scope_combo.currentText().strip().upper() or "ANY",
                "role": role or self._devref_short(devref) or "自定义图元",
                "device_type": role or self._devref_short(devref) or "自定义图元",
                "device_subtype": (self.standard_table.item(row, 11).text() if self.standard_table.item(row, 11) else "").strip(),
                "device_level": level_combo.currentText().strip() or default_device_level(usage_combo.currentText()),
                "symbol_usage": usage_combo.currentText().strip() or "其他",
                "element_tag": element_tag,
                "standard_devref": devref,
                # Internal locator is learned from discovery + uploaded standard;
                # the user no longer specifies a locator rule or condition.
                "match_attr": "devref",
                "match_value": observed_devref or devref,
                "enabled": True,
                "source_file": str(meta.get("source_file", "")).strip(),
                "observed_devref": observed_devref,
                "observed_symbol_file": self._observed_symbol_g_filename(observed_devref),
                "observed_count": observed_count,
                "observed_files": list(observed_files) if isinstance(observed_files, list) else [],
                "observed_examples": list(observed_examples) if isinstance(observed_examples, list) else [],
                "classification_marker": classification_marker,
                "category_marker": classification_marker,
            })
        return result

    def _load_custom_symbols(self, entries: list[dict[str, object]]) -> None:
        previous_suppression = self._suppress_classification_marker_persistence
        self._suppress_classification_marker_persistence = True
        signals_blocked = self.standard_table.blockSignals(True)
        try:
            self._clear_custom_standard_rows()
            for entry in entries:
                self._insert_custom_standard_row(entry, refresh_layout=False)
            self._fit_standard_table_columns()
            self._apply_standard_table_filter()
        finally:
            self.standard_table.blockSignals(signals_blocked)
            self._suppress_classification_marker_persistence = previous_suppression

    @staticmethod
    def _discovery_entry(meta: dict[str, object]) -> dict[str, object]:
        observed_devref = str(meta.get("observed_devref", meta.get("devref", ""))).strip()
        role = str(meta.get("suggested_device_type", "")).strip()
        if not role:
            role = infer_device_type(
                role=str(meta.get("observed_subject", meta.get("element_id", ""))).strip(),
                source_file=str(meta.get("observed_symbol_file", meta.get("source_file", ""))).strip(),
                element_tag=str(meta.get("element_tag", "")).strip(),
                element_id=str(meta.get("observed_subject", meta.get("element_id", ""))).strip(),
            )
        usage = str(meta.get("suggested_usage", "")).strip()
        if usage not in SYMBOL_USAGE_VALUES:
            usage = infer_symbol_usage(
                role=role,
                source_file=str(meta.get("observed_symbol_file", meta.get("source_file", ""))).strip(),
                element_tag=str(meta.get("element_tag", "")).strip(),
            )
        scope = str(meta.get("suggested_scope", "ANY")).strip().upper() or "ANY"
        if scope not in {"ANY", "SMART", "NORMAL"}:
            scope = "ANY"
        return {
            "uid": "discovery-" + uuid4().hex,
            "candidate_only": True,
            "scope": scope,
            "role": role or "待分类图元",
            "device_type": role or "待分类图元",
            "device_subtype": "",
            "device_level": default_device_level(usage),
            "symbol_usage": usage,
            "element_tag": str(meta.get("element_tag", "")).strip(),
            "standard_devref": "",
            "match_attr": "devref",
            "match_value": observed_devref,
            "observed_devref": observed_devref,
            "observed_count": max(0, int(meta.get("count", 0) or 0)),
            "observed_files": [str(item) for item in meta.get("files", []) if str(item).strip()] if isinstance(meta.get("files", []), list) else [],
            "observed_examples": [dict(item) for item in meta.get("sample_positions", []) if isinstance(item, dict)] if isinstance(meta.get("sample_positions", []), list) else [],
            "sample_names": [str(item) for item in meta.get("sample_names", []) if str(item).strip()] if isinstance(meta.get("sample_names", []), list) else [],
            "observed_symbol_file": str(meta.get("observed_symbol_file", "")).strip(),
            "observed_subject": str(meta.get("observed_subject", "")).strip(),
            "suggested_usage": usage,
            "suggested_scope": scope,
            "suggested_device_type": role,
        }

    def _apply_discovery_to_rows(self) -> None:
        """Retained compatibility hook; server-only mode never imports discovery rows."""
        # The current standard workflow is server-only.  Keep the legacy method
        # for old callers, but never resurrect historical business-G candidates
        # into the authoritative server standard table.
        return
        represented: set[str] = set()
        row_by_ref: dict[str, int] = {}
        for row in self._custom_standard_rows():
            marker = self.standard_table.item(row, 0)
            if marker is None:
                continue
            observed = str(marker.data(Qt.ItemDataRole.UserRole + 4) or "").strip()
            standard = self._standard_file_devref(row)
            for value in (observed, standard):
                if value:
                    represented.add(value)
                    row_by_ref.setdefault(value, row)

        for observed_devref, meta in sorted(
            self._graphic_discovery_catalog.items(),
            key=lambda item: (-int(item[1].get("count", 0) or 0), item[0].casefold()),
        ):
            if self._discovery_decisions.get(observed_devref, "").strip().lower() == "ignored":
                continue
            meta = dict(meta)
            meta.setdefault("observed_devref", observed_devref)
            existing_row = row_by_ref.get(observed_devref)
            if existing_row is not None:
                count = max(0, int(meta.get("count", 0) or 0))
                files = [str(item) for item in meta.get("files", []) if str(item).strip()] if isinstance(meta.get("files", []), list) else []
                examples = [dict(item) for item in meta.get("sample_positions", []) if isinstance(item, dict)] if isinstance(meta.get("sample_positions", []), list) else []
                marker = self.standard_table.item(existing_row, 0)
                if marker is not None:
                    marker.setData(Qt.ItemDataRole.UserRole + 4, observed_devref)
                    marker.setData(Qt.ItemDataRole.UserRole + 5, count)
                    marker.setData(Qt.ItemDataRole.UserRole + 6, files)
                    marker.setData(Qt.ItemDataRole.UserRole + 7, examples)
                symbol_file = str(meta.get("observed_symbol_file", "")).strip() or self._observed_symbol_g_filename(observed_devref)
                self.standard_table.item(existing_row, 13).setText(symbol_file or "-")
                self.standard_table.item(existing_row, 14).setText(observed_devref)
                self.standard_table.item(existing_row, 15).setText(str(count))
                self.standard_table.item(existing_row, 16).setText(self._discovery_example_text(examples, files) or "-")
                tip = self._discovery_tooltip(meta, observed_devref, count, files, examples)
                for column in (13, 14, 15, 16):
                    self.standard_table.item(existing_row, column).setToolTip(tip)
                self._refresh_custom_standard_row(existing_row)
                continue

            if observed_devref in represented:
                continue
            new_row = self._insert_custom_standard_row(self._discovery_entry(meta))
            row_by_ref[observed_devref] = new_row
            represented.add(observed_devref)

        self._apply_standard_table_filter()
        self._fit_standard_table_columns()

    def _apply_standard_table_filter(self, *_args) -> None:
        standard_query = self.standard_table_search.text().strip().casefold() if hasattr(self, "standard_table_search") else ""
        discovery_query = self.discovery_filter.text().strip().casefold() if hasattr(self, "discovery_filter") else ""
        pending_only = bool(self.pending_only_checkbox.isChecked()) if hasattr(self, "pending_only_checkbox") else False
        for row in range(self.standard_table.rowCount()):
            marker = self.standard_table.item(row, 0)
            is_candidate = bool(
                row >= len(self._standard_specs)
                and marker is not None
                and marker.data(Qt.ItemDataRole.UserRole) == "custom"
                and bool(marker.data(Qt.ItemDataRole.UserRole + 3))
                and not self._standard_file_devref(row)
            )
            if pending_only and not is_candidate:
                self.standard_table.setRowHidden(row, True)
                continue
            matches = True
            if standard_query:
                filename_values: list[str] = []
                for column in (2, 3, 13, 14, 18, 19):
                    item = self.standard_table.item(row, column)
                    if item is not None:
                        filename_values.append(item.text())
                        if column == 3:
                            filename_values.append(str(item.data(Qt.ItemDataRole.UserRole) or ""))
                matches = standard_query in " ".join(filename_values).casefold()
            if matches and discovery_query:
                values: list[str] = []
                for column in range(self.standard_table.columnCount()):
                    item = self.standard_table.item(row, column)
                    if item is not None:
                        values.append(item.text())
                    widget = self.standard_table.cellWidget(row, column)
                    if isinstance(widget, WheelSafeComboBox):
                        values.append(widget.currentText())
                haystack = " ".join(values).casefold()
                matches = discovery_query in haystack
            self.standard_table.setRowHidden(row, not matches)
        self._refresh_standard_table_overview()

    def _refresh_global_connection_settings(self) -> None:
        """Refresh shared environment paths without allowing this business page to edit them."""
        root = self.user_settings.get_value(
            "site_profile/remote_symbol_library_root", ""
        ).strip()
        self.server_symbol_root.setText(root)
        if hasattr(self, "central_classification_path"):
            repository = CentralRepositorySettings(self.user_settings).load()
            self.central_classification_path.setText(f"{repository.config_dir}/symbol_classification.json")
        # The public catalog manager reads the shared endpoint directly from the
        # tiny settings cache.  Do not make the hidden legacy remote-file selector
        # reload its own (potentially large) file-list cache on every page show.
        if self._legacy_profile_state_loaded and hasattr(self, "discovery_source"):
            self.discovery_source.remote.refresh_shared_settings()
        self._refresh_local_storage_summary()

    def _refresh_local_storage_summary(self) -> None:
        """Show the local-only locations used by the remote catalog manager."""
        if not hasattr(self, "local_storage_summary"):
            return
        cache_text = "连接配置后确定"
        try:
            cfg = self._server_library_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
            if host and root:
                cache_text = str(RemoteSymbolLibraryService().library_dir(host, root))
        except Exception:
            pass
        self.local_storage_summary.setText(
            "本地只读边界：服务器只执行列目录、读属性和下载；图元解析、同步记录与分类标记只写本机。\n"
            f"图元缓存与分类标记：{cache_text}\n"
            "服务器不会被上传、覆盖、删除或修改。"
        )

    def _restore_cached_server_sync(self) -> bool:
        """Restore the last complete server inventory without opening SSH.

        The parseable catalog and the physical server-file inventory are separate:
        an unreadable or conflicting G still has to remain visible after restart.
        """
        try:
            cfg = self._server_library_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
            if not host or not root:
                return False
            snapshot = RemoteSymbolLibraryService().load_cached_sync_snapshot(
                host=host,
                root=root,
            )
            inventory = snapshot.get("server_file_records", [])
            if not isinstance(inventory, list) or not inventory:
                return False
            snapshot["cached_restore"] = True
            self._apply_server_library_payload(
                snapshot,
                auto_bind=False,
                compare_profile=False,
            )
            # load_cached_sync_snapshot() has already merged the authoritative
            # classification_markers.json layer into each physical inventory row.
            # Avoid reading/matching the same cache again during startup.
            marked = sum(
                1
                for row in self._server_file_inventory
                if str(row.get("classification_marker", row.get("category_marker", "")) or "").strip()
            )
            if hasattr(self, "server_library_status"):
                self.server_library_status.setText(
                    f"已从本机 AppData 缓存恢复：{len(inventory)} 个图元文件，"
                    f"分类标记 {marked} 个；未访问服务器。"
                )
            return True
        except Exception:
            # Opening the page must remain usable even if an old or damaged cache
            # cannot be restored; the next explicit server sync can rebuild it.
            return False

    def _persist_server_library_settings(self) -> None:
        self.user_settings.set_value(
            "site_profile/remote_symbol_library_enabled",
            "true" if self.server_standard_enabled.isChecked() else "false",
        )
        # The root path is a global environment setting and is intentionally not
        # editable/persisted from this business page.
        self._refresh_global_connection_settings()

    def _server_library_enabled_changed(self, enabled: bool) -> None:
        self._persist_server_library_settings()
        self.server_symbol_root.setEnabled(bool(enabled))
        self.server_sync_button.setEnabled(bool(enabled) and self._server_sync_worker is None and self._scan_worker is None)
        if not enabled:
                self.server_library_status.setText("服务器图元同步开关不可关闭。")
        elif self.isVisible():
            self.server_library_status.setText("图元状态：等待同步")

    def _server_library_config(self) -> dict[str, object]:
        # Reuse the application's shared SSH credentials directly from the local
        # settings cache.  This is intentionally independent of the retired hidden
        # discovery widget, so opening/restoring the catalog never needs to build or
        # traverse a remote-file input panel.
        cfg = self._shared_ssh_config_from_local_settings()
        cfg["root"] = self.server_symbol_root.text().strip()
        return cfg

    def _expected_server_symbol_names(self) -> list[str]:
        names: set[str] = set()
        if hasattr(self, "standard_table"):
            for row in range(self.standard_table.rowCount()):
                item = self.standard_table.item(row, 13)
                name = Path(item.text().strip()).name if item is not None else ""
                if name and name != "-":
                    names.add(name)
        profile = self._current_active_profile() if hasattr(self, "profile_selector") else None
        if profile is not None:
            for raw in profile.managed_standard_files:
                row = dict(raw)
                name = Path(str(row.get("original_name", "")).strip()).name
                if name and str(row.get("standard_source", "server")).strip().lower() == "server":
                    names.add(name)
        return sorted(names, key=str.casefold)

    def _open_server_symbol_cache(self) -> None:
        try:
            cfg = self._server_library_config()
            directory = RemoteSymbolLibraryService().library_dir(str(cfg["host"]), str(cfg["root"]))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        except Exception as exc:
            QMessageBox.warning(self, "打开缓存失败", str(exc))

    def _export_classification_markers(self) -> None:
        """Export the local symbol classification markers as portable JSON."""
        try:
            cfg = self._server_library_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
            if not host or not root:
                raise ValueError("请先在连接设置中配置服务器图元库。")
            default_path = Path.home() / "gfile-symbol-classification-markers.json"
            target, _ = QFileDialog.getSaveFileName(
                self,
                "导出本地分类 JSON",
                str(default_path),
                "JSON 文件 (*.json)",
            )
            if not target:
                return
            result = RemoteSymbolLibraryService().export_classification_markers(
                host=host,
                root=root,
                target_path=target,
            )
            QMessageBox.information(
                self,
                "本地分类 JSON 已导出",
                f"已导出 {int(result.get('count', 0) or 0)} 条分类标记。\n\n{result.get('path', target)}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "导出本地 JSON 失败", str(exc))

    def _persist_visible_classification_markers(self) -> dict[str, object]:
        """Persist the local classification layer and current local snapshot.

        Since v2.18.194 the server inventory list is not editable/displayed here.
        Existing classification_markers.json remains authoritative and is never
        cleared merely because the compatibility table has zero rows.
        """
        cfg = self._server_library_config()
        host = str(cfg.get("host", "")).strip()
        root = str(cfg.get("root", self.server_symbol_root.text())).strip()
        if not host or not root:
            raise ValueError("请先在连接设置中配置服务器图元库。")

        service = RemoteSymbolLibraryService()
        saved = 0
        failed = 0
        if self._server_inventory_table_enabled:
            updates: dict[str, str] = {}
            for row in range(self.standard_table.rowCount()):
                item = self.standard_table.item(row, 18)
                if item is None:
                    continue
                remote_path = str(item.data(Qt.ItemDataRole.UserRole + 1) or "").strip()
                if not remote_path:
                    continue
                updates[remote_path] = item.text().strip()
            # One local batch = one manifest write + one marker-file write + one
            # snapshot write.  The previous implementation performed those writes
            # once per table row (about 600 JSON writes for a 200-row catalog).
            saved = service.update_classification_markers_batch(
                host=host, root=root, updates=updates
            )
            failed = max(0, len(updates) - saved)
        else:
            saved = len(service.load_classification_markers(host=host, root=root))

        self._refresh_local_classification_markers()
        snapshot_payload = dict(self._last_server_sync_payload)
        snapshot_payload["server_file_records"] = [dict(row) for row in self._server_file_inventory]
        if not isinstance(snapshot_payload.get("matched_records"), dict):
            snapshot_payload["matched_records"] = {
                Path(str(record.get("original_name", ""))).name: dict(record)
                for record in self._server_catalog_records.values()
                if str(record.get("original_name", "")).strip()
            }
        snapshot_path = service.save_cached_sync_snapshot_payload(
            host=host, root=root, payload=snapshot_payload
        )
        return {
            "host": host,
            "root": root,
            "saved": saved,
            "failed": failed,
            "cache_dir": str(service.library_dir(host, root)),
            "marker_file": str(service.library_dir(host, root) / "classification_markers.json"),
            "snapshot_file": str(snapshot_path),
        }

    def _mark_local_classification_source(self, source: str, *, central_updated_at: str = "") -> None:
        self.user_settings.set_value("local_cache/classification_source", source)
        if central_updated_at:
            self.user_settings.set_value("local_cache/classification_central_updated_at", central_updated_at)

    @staticmethod
    def _local_config_timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _refresh_classification_cache_status(self, *, extra: str = "") -> None:
        """Render local/central provenance without reading the central server."""
        if not hasattr(self, "central_classification_status"):
            return
        source = self.user_settings.get_value("local_cache/classification_source", "local").strip() or "local"
        source_label = {
            "central": "中央同步副本",
            "custom": "本地配置",
            "local": "本地配置",
        }.get(source, "本地配置")
        saved_at = self.user_settings.get_value("local_cache/classification_saved_at", "").strip()
        synced_at = self.user_settings.get_value("local_cache/classification_synced_at", "").strip()
        remote_updated_at = self.user_settings.get_value(
            "local_cache/classification_central_updated_at", ""
        ).strip()
        central_detail = synced_at or "尚未同步"
        if source == "central" and remote_updated_at:
            central_detail += f"（中央更新时间 {remote_updated_at}）"
        extra_text = f" · {extra}" if extra else ""
        self.central_classification_status.setText(
            f"当前来源：{source_label} · 本地更新时间：{saved_at or '尚未保存'} · "
            f"中央同步：{central_detail} · 启动不自动读取中央配置{extra_text}"
        )

    def _save_classification_markers(self) -> None:
        """Explicitly persist every visible server-file marker to the local cache."""
        try:
            result = self._persist_visible_classification_markers()
            saved = int(result.get("saved", 0) or 0)
            failed = int(result.get("failed", 0) or 0)
            self._mark_local_classification_source("custom")
            self.user_settings.set_value("local_cache/classification_saved_at", self._local_config_timestamp())
            self._refresh_classification_cache_status(extra=f"已保存 {saved} 条")
            self.server_library_status.setText(
                f"分类标记已保存到本地：{saved} 条。"
                + (f"另有 {failed} 条未保存，请检查服务器图元是否已完成同步。" if failed else "")
            )
            if failed:
                QMessageBox.warning(
                    self,
                    "保存到本地结果",
                    f"已保存 {saved} 条；{failed} 条未保存。\n"
                    "请先同步服务器图元信息，再重新保存。",
                )
            else:
                QMessageBox.information(
                    self,
                    "已保存到本地",
                    f"已将 {saved} 条分类标记和当前图元目录快照保存到本机缓存。\n\n"
                    f"本地分类文件：{result.get('marker_file', '')}\n"
                    f"本地图元快照：{result.get('snapshot_file', '')}",
                )
        except Exception as exc:
            QMessageBox.warning(self, "保存到本地失败", str(exc))

    def _central_registry_config(self) -> dict[str, object]:
        # Classification content is stored in the central repository, while the
        # downloaded symbol-library cache still belongs to the business file server.
        repository = CentralRepositorySettings(self.user_settings).load()
        cfg = repository.connection_args()
        cfg["config_dir"] = repository.config_dir
        cfg["root"] = self.server_symbol_root.text().strip()
        return cfg

    def _open_central_progress(self, title: str, label: str) -> QProgressDialog:
        dialog = QProgressDialog(label, "", 0, 100, self)
        dialog.setWindowTitle(title)
        dialog.setCancelButton(None)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        # Do not flash a transient progress window for fast local/central operations.
        # Qt will show it only when the operation actually lasts long enough.
        dialog.setMinimumDuration(800)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self._central_progress_dialog = dialog
        return dialog

    def _close_central_progress(self) -> None:
        dialog = self._central_progress_dialog
        self._central_progress_dialog = None
        if dialog is not None:
            dialog.setValue(100)
            dialog.close()
            dialog.deleteLater()

    def _publish_central_classification(self) -> None:
        try:
            CentralRepositorySettings(self.user_settings).require_explicitly_saved(action="发布图元分类到中央")
        except Exception as exc:
            QMessageBox.warning(self, "中央仓库尚未确认", str(exc))
            return
        if not self._require_admin_mode("上传到服务器"):
            return
        if self._classification_registry_worker is not None:
            return
        try:
            local = self._persist_visible_classification_markers()
            if int(local.get("failed", 0) or 0):
                raise ValueError("存在未能保存到本机缓存的分类标记；请先完成服务器图元同步后再发布。")
            cfg = self._central_registry_config()
            payload = RemoteSymbolLibraryService().build_classification_marker_payload(
                host=str(local["host"]), root=str(local["root"])
            )
        except Exception as exc:
            QMessageBox.warning(self, "发布到中央失败", str(exc))
            return

        marker_count = len(payload.get("markers", [])) if isinstance(payload, dict) else 0
        lease = self._admin_lease
        if lease is None:
            QMessageBox.warning(self, "发布到中央失败", "当前没有有效的中央管理员权限。")
            return
        if QMessageBox.question(
            self,
            "发布到中央",
            f"发布 {marker_count} 条分类标记并覆盖中央正式配置？",
        ) != QMessageBox.StandardButton.Yes:
            return

        self.central_classification_status.setText("中央配置：正在发布图元分类…")
        progress_dialog = self._open_central_progress(
            "发布中央图元分类",
            "正在发布图元分类配置…",
        )

        def run_publish(log, progress):
            progress(10)
            result = ClassificationRegistryService(config_dir=str(cfg["config_dir"])).publish(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                payload=payload,
                publisher_machine=lease.machine_name or self._machine_name,
                publisher_ip=lease.ip,
                machine_id=self._machine_id,
                lease_id=lease.lease_id,
                expected_admin_epoch=lease.admin_epoch,
                log=log,
            )
            progress(100)
            return {
                "remote_path": result.remote_path,
                "updated_at": result.updated_at,
                "marker_count": result.marker_count,
            }

        worker = FunctionWorker(run_publish)
        self._classification_registry_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(self._on_central_publish_result)
        worker.signals.error.connect(lambda details: self._on_central_registry_error(details, action="上传"))
        worker.signals.finished.connect(self._on_central_registry_finished)
        self._update_action_state()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _sync_central_classification(self) -> None:
        self._start_central_classification_sync()

    def _start_central_classification_sync(self) -> None:
        """Manual-only central classification download.

        There is deliberately no silent/automatic mode: every central read must be
        initiated by the operator through the visible sync button.
        """
        if self._classification_registry_worker is not None:
            return
        try:
            cfg = self._central_registry_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
            if not host or not root:
                raise ValueError("请先在连接设置中配置 SSH 服务器。")
        except Exception as exc:
            QMessageBox.warning(self, "从中央同步失败", str(exc))
            return

        if QMessageBox.question(
            self,
            "从中央同步",
            # Legacy wording retained as a source-level compatibility marker:
            # 用服务器分类覆盖本机分类标记
            "中央 symbol_classification.json 将覆盖当前本机分类缓存。继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return

        self.central_classification_status.setText("中央配置：正在同步图元分类…")
        progress_dialog = self._open_central_progress(
            "同步中央图元分类",
            "正在读取中央图元分类配置…",
        )

        def run_sync(log, progress):
            progress(10)
            # Compatibility marker for older source checks: ClassificationRegistryService().fetch
            snapshot = ClassificationRegistryService(config_dir=str(cfg["config_dir"])).fetch(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                log=log,
            )
            progress(70)
            imported = RemoteSymbolLibraryService().replace_classification_marker_payload(
                host=host,
                root=root,
                payload=snapshot.payload,
            )
            progress(80)
            return {
                "remote_path": snapshot.remote_path,
                "updated_at": snapshot.updated_at,
                "marker_count": snapshot.marker_count,
                "imported": int(imported.get("imported", 0) or 0),
                "matched": int(imported.get("matched", 0) or 0),
                "pending": int(imported.get("pending", 0) or 0),
            }

        worker = FunctionWorker(run_sync)
        self._classification_registry_worker = worker
        worker.signals.progress.connect(progress_dialog.setValue)
        worker.signals.result.connect(self._on_central_sync_result)
        worker.signals.error.connect(lambda details: self._on_central_registry_error(details, action="同步"))
        worker.signals.finished.connect(self._on_central_registry_finished)
        self._update_action_state()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_central_publish_result(self, result: object) -> None:
        self._close_central_progress()
        payload = dict(result) if isinstance(result, dict) else {}
        count = int(payload.get("marker_count", 0) or 0)
        updated_at = str(payload.get("updated_at", "") or "-")
        fallback_path = self.central_classification_path.text().strip() if hasattr(self, "central_classification_path") else ""
        path = str(payload.get("remote_path", fallback_path))
        self._refresh_classification_cache_status(extra=f"已发布中央 {count} 条 · {updated_at}")
        QMessageBox.information(
            self,
            "已发布到中央",
            f"已发布 {count} 条分类标记。\n\n中央唯一正式文件：\n{path}",
        )

    def _on_central_sync_result(self, result: object) -> None:
        if self._central_progress_dialog is not None:
            self._central_progress_dialog.setLabelText("正在更新本地图元分类缓存…")
            self._central_progress_dialog.setValue(90)
        payload = dict(result) if isinstance(result, dict) else {}
        self._refresh_local_classification_markers()
        count = int(payload.get("marker_count", 0) or 0)
        matched = int(payload.get("matched", 0) or 0)
        pending = int(payload.get("pending", 0) or 0)
        updated_at = str(payload.get("updated_at", "") or "-")
        self._mark_local_classification_source("central", central_updated_at=updated_at)
        stamp = self._local_config_timestamp()
        self.user_settings.set_value("local_cache/classification_saved_at", stamp)
        self.user_settings.set_value("local_cache/classification_synced_at", stamp)
        self._refresh_classification_cache_status(
            extra=f"刚刚同步 {count} 条 · 匹配 {matched} · 待匹配 {pending}"
        )
        self._close_central_progress()
        QMessageBox.information(
            self,
            "已从中央同步",
            f"已同步 {count} 条分类标记；当前匹配 {matched} 条，待匹配 {pending} 条。\n\n中央配置已覆盖本机分类缓存。",
        )

    def refresh_after_external_central_sync(self, summary: object = None) -> None:
        """Refresh local-only views after Connection & Environment bulk sync."""
        payload = dict(summary) if isinstance(summary, dict) else {}
        version = int(payload.get("version", 0) or 0)
        count = int(payload.get("classification_count", 0) or 0)
        matched = int(payload.get("classification_matched", 0) or 0)
        pending = int(payload.get("classification_pending", 0) or 0)
        self._refresh_global_connection_settings()
        self._refresh_local_classification_markers()
        detail = f"一键同步已更新 V{version}" if version else "一键同步已更新"
        if count or matched or pending:
            detail += f" · {count} 条 · 匹配 {matched} · 待匹配 {pending}"
        self._refresh_classification_cache_status(extra=detail)

    def _on_central_registry_error(self, details: str, *, action: str, quiet: bool = False) -> None:
        self._close_central_progress()
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self.central_classification_status.setText(f"中央配置：{action}失败 · {message or details}")
        if not quiet:
            QMessageBox.warning(self, f"中央图元分类{action}失败", message or str(details))

    def _on_central_registry_finished(self) -> None:
        self._classification_registry_worker = None
        self._close_central_progress()
        self._update_action_state()

    def _refresh_local_classification_markers(self) -> None:
        """Reload local markers into the in-memory server catalog/inventory."""
        try:
            cfg = self._server_library_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
            markers = RemoteSymbolLibraryService().load_classification_markers(host=host, root=root)
        except Exception:
            return
        marker_by_path = {str(path).strip(): str(value).strip() for path, value in markers.items()}
        catalog_by_path = {
            str(record.get("remote_path", "")).strip(): record
            for record in self._server_catalog_records.values()
            if str(record.get("remote_path", "")).strip()
        }
        inventory_by_path = {
            str(record.get("remote_path", "")).strip(): record
            for record in self._server_file_inventory
            if str(record.get("remote_path", "")).strip()
        }
        for remote_path, record in {**catalog_by_path, **inventory_by_path}.items():
            value = marker_by_path.get(remote_path, "")
            targets = [catalog_by_path.get(remote_path), inventory_by_path.get(remote_path)]
            for target in targets:
                if target is None:
                    continue
                if value:
                    target["classification_marker"] = value
                    target["category_marker"] = value
                else:
                    target.pop("classification_marker", None)
                    target.pop("category_marker", None)

        if self._server_inventory_table_enabled:
            for row in range(self.standard_table.rowCount()):
                item = self.standard_table.item(row, 18)
                if item is None:
                    continue
                remote_path = str(item.data(Qt.ItemDataRole.UserRole + 1) or "").strip()
                if not remote_path:
                    path_item = self.standard_table.item(row, 19)
                    remote_path = str(path_item.data(Qt.ItemDataRole.UserRole + 1) or "").strip() if path_item else ""
                self._classification_marker_write_busy = True
                try:
                    item.setText(marker_by_path.get(remote_path, ""))
                finally:
                    self._classification_marker_write_busy = False
        self._refresh_standard_table_overview()

    def _import_classification_markers(self) -> None:
        """Import portable markers and refresh the current local server-symbol cache."""
        source, _ = QFileDialog.getOpenFileName(
            self,
            "导入本地分类 JSON",
            str(Path.home()),
            "JSON 文件 (*.json)",
        )
        if not source:
            return
        try:
            cfg = self._server_library_config()
            host = str(cfg.get("host", "")).strip()
            root = str(cfg.get("root", self.server_symbol_root.text())).strip()
            if not host or not root:
                raise ValueError("请先在连接设置中配置服务器图元库。")
            result = RemoteSymbolLibraryService().import_classification_markers(
                host=host,
                root=root,
                source_path=source,
            )
            self._refresh_local_classification_markers()
            self.server_library_status.setText(
                f"已导入本地分类标记 {int(result.get('imported', 0) or 0)} 条；"
                f"当前匹配 {int(result.get('matched', 0) or 0)} 条；"
                f"待后续服务器同步匹配 {int(result.get('pending', 0) or 0)} 条。"
            )
            QMessageBox.information(
                self,
                "分类标记已载入",
                f"载入 {int(result.get('imported', 0) or 0)} 条，"
                f"当前现场已匹配 {int(result.get('matched', 0) or 0)} 条。\n"
                f"未匹配的 {int(result.get('pending', 0) or 0)} 条会在后续读取服务器图元时自动尝试匹配。",
            )
        except Exception as exc:
            QMessageBox.warning(self, "导入本地 JSON 失败", str(exc))

    def _server_profile_changed_names(self, payload: dict[str, object]) -> set[str]:
        changed = {str(item) for item in payload.get("changed_names", []) if str(item).strip()} if isinstance(payload.get("changed_names", []), list) else set()
        matched = payload.get("matched_records", {})
        if not isinstance(matched, dict):
            return changed
        profile = None if catalog_only else self._current_active_profile()
        if profile is None:
            return changed
        current_by_name = {
            Path(str(row.get("original_name", "")).strip()).name.casefold(): dict(row)
            for row in profile.managed_standard_files
            if Path(str(row.get("original_name", "")).strip()).name
        }
        for name, raw in matched.items():
            if not isinstance(raw, dict):
                continue
            current = current_by_name.get(Path(str(name)).name.casefold())
            if current is None:
                continue
            old_hash = str(current.get("sha256", "")).strip().lower()
            new_hash = str(raw.get("sha256", "")).strip().lower()
            if old_hash and new_hash and old_hash != new_hash:
                changed.add(Path(str(name)).name)
        return changed

    def _apply_server_library_payload(
        self,
        payload: dict[str, object],
        *,
        auto_bind: bool,
        compare_profile: bool = True,
    ) -> None:
        previous_inventory = list(self._server_file_inventory)
        previous_table_rows = (
            self.standard_table.rowCount()
            if self._server_inventory_table_enabled and hasattr(self, "standard_table")
            else 0
        )

        def inventory_signature(rows: object) -> tuple[tuple[str, ...], ...]:
            if not isinstance(rows, list):
                return ()
            values: list[tuple[str, ...]] = []
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                values.append((
                    str(raw.get("remote_path", "")),
                    str(raw.get("name", "")),
                    str(raw.get("size", "")),
                    str(raw.get("mtime_epoch", "")),
                    str(raw.get("sha256", "")),
                    str(raw.get("sync_status", "")),
                    str(raw.get("error", "")),
                ))
            return tuple(sorted(values, key=lambda row: (row[0].casefold(), row[1].casefold())))

        previous_inventory_signature = inventory_signature(previous_inventory)
        self._last_server_sync_payload = dict(payload)
        inventory_raw = payload.get("server_file_records", [])
        self._server_file_inventory = [
            dict(item) for item in inventory_raw
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ] if isinstance(inventory_raw, list) else []
        inventory_changed = previous_inventory_signature != inventory_signature(self._server_file_inventory)
        matched_raw = payload.get("matched_records", {})
        matched = {
            Path(str(name)).name.casefold(): dict(record)
            for name, record in matched_raw.items()
            if isinstance(record, dict)
        } if isinstance(matched_raw, dict) else {}
        # Keep the complete parseable server catalog separate from the persisted
        # Profile.  Reading the server is a preview/cache operation only.  The
        # editor snapshot below is still unsaved in-memory state and is persisted
        # only by the explicit "手动更新当前标准" action.
        self._server_catalog_records = {
            str(record.get("devref", "")).strip(): dict(record)
            for record in matched.values()
            if str(record.get("devref", "")).strip()
        }
        catalog_only = bool(not auto_bind and not compare_profile)
        if catalog_only:
            # The visible sync/classification page needs only the server catalog.
            # Do not touch the retired Profile repository during cache restore or
            # a normal manual server refresh.
            self._symbol_catalog = self._catalog_from_standard_records(
                list(self._server_catalog_records.values())
            )
        else:
            self._rebuild_symbol_catalog()
        conflicts = payload.get("conflicts", {}) if isinstance(payload.get("conflicts", {}), dict) else {}
        errors = payload.get("errors", {}) if isinstance(payload.get("errors", {}), dict) else {}
        conflict_keys = {Path(str(name)).name.casefold() for name in conflicts}
        error_keys = {Path(str(name)).name.casefold() for name in errors}
        unmatched = [str(item) for item in payload.get("unmatched_names", []) if str(item).strip()] if isinstance(payload.get("unmatched_names", []), list) else []
        changed = {
            str(item).strip()
            for item in payload.get("changed_names", [])
            if str(item).strip()
        } if isinstance(payload.get("changed_names", []), list) else set()
        added_names = [str(item) for item in payload.get("added_names", []) if str(item).strip()] if isinstance(payload.get("added_names", []), list) else []
        unchanged_names = [str(item) for item in payload.get("unchanged_names", []) if str(item).strip()] if isinstance(payload.get("unchanged_names", []), list) else []
        # Keep the sync result available to legacy code paths, but do not compare
        # it with or write into any local standard/profile version.
        self._last_server_sync_payload["profile_changed_names"] = sorted(changed, key=str.casefold)
        if not compare_profile:
            self._last_server_sync_payload["profile_compare_skipped"] = True
        profile = None if catalog_only else self._current_active_profile()
        # A fresh-rescan DRAFT is a new local working copy, not an edit of the
        # locked base version.  Therefore server GET/cache results may bind into
        # the draft while the saved locked ACTIVE remains byte-for-byte untouched.
        # Locking was part of the old user-managed version workflow.  The public
        # workflow now has one current server standard, so a legacy lock must not
        # prevent the user from explicitly applying a reviewed server snapshot.
        locked = False

        if hasattr(self, "server_new_version_button"):
            has_server_replacements = bool(
                locked
                and changed
                and any(
                    Path(str(name)).name.casefold() in {item.casefold() for item in changed}
                    and isinstance(record, dict)
                    for name, record in (matched_raw.items() if isinstance(matched_raw, dict) else [])
                )
            )
            self.server_new_version_button.setVisible(has_server_replacements)
            self.server_new_version_button.setEnabled(has_server_replacements and self._server_sync_worker is None and self._scan_worker is None and not self._task_busy)

        bound = 0
        if auto_bind and not locked and matched:
            # The server catalog is authoritative. Replace pending records by
            # filename so a server-side update (including a changed devref) is
            # reflected in the next local standard snapshot.
            effective_matched = matched
            # Replace pending server records by filename first. This handles a remote
            # update whose body ID/devref changed while the authoritative filename
            # remained stable.
            incoming_names = {Path(str(row.get("original_name", "")).strip()).name.casefold() for row in effective_matched.values()}
            retained = [
                dict(row) for row in self._pending_standard_file_records
                if Path(str(row.get("original_name", "")).strip()).name.casefold() not in incoming_names
            ]
            retained.extend(dict(row) for row in effective_matched.values())
            self._pending_standard_file_records = retained
            self._symbol_catalog = self._catalog_from_standard_records(self._editor_standard_records())

            for row in self._custom_standard_rows():
                observed_item = self.standard_table.item(row, 13)
                expected_name = Path(observed_item.text().strip()).name if observed_item is not None else ""
                key = expected_name.casefold()
                if not key or key in conflict_keys or key in error_keys or key not in effective_matched:
                    continue
                record = effective_matched[key]
                devref = str(record.get("devref", "")).strip()
                if not devref:
                    continue
                self._set_standard_file_cell(row, devref)
                tag_item = self.standard_table.item(row, 2)
                if tag_item is not None and not tag_item.text().strip():
                    tag_item.setText(str(record.get("element_tag", "")).strip())
                self._refresh_custom_standard_row(row)
                bound += 1

        if catalog_only:
            self._symbol_catalog = self._catalog_from_standard_records(
                list(self._server_catalog_records.values())
            )
        else:
            self._rebuild_symbol_catalog()
        # An explicit sync with an identical physical inventory only needs to
        # refresh counters/status. Rebuilding a large QTableWidget here was the
        # main source of the visible pause even though no file was downloaded.
        # A first restore, any inventory change, or a business-G auto-bind still
        # takes the full rebuild path.
        cached_restore = bool(payload.get("cached_restore"))
        should_rebuild_table = bool(
            auto_bind
            or (
                self._server_inventory_table_enabled
                and (
                    cached_restore
                    or inventory_changed
                    or previous_table_rows < len(self._server_file_inventory)
                )
            )
        )
        if catalog_only and should_rebuild_table:
            # Local AppData restore is revealed atomically; a manual server refresh
            # keeps the current table visible while replacing its rows.
            self._restore_cached_inventory_table_fast(atomic_reveal=cached_restore)
        elif cached_restore:
            self._restore_cached_inventory_table_fast(atomic_reveal=True)
        elif should_rebuild_table:
            self._merge_server_catalog_rows()
            self._merge_server_file_inventory_rows()

        remote_total = int(payload.get("scanned_remote_files", 0) or 0)
        downloaded = int(payload.get("downloaded", 0) or 0)
        reused = int(payload.get("reused", 0) or 0)
        checked_at = str(payload.get("checked_at", "")).strip()
        updated_files = payload.get("updated_files", [])
        parts = [
            f"服务器 element 图元目录同步完成：远程 {remote_total} 个 .g",
            f"信息解析成功 {len(matched)}",
            f"缓存复用 {reused}",
            f"本次下载 {downloaded}",
        ]
        if self._server_file_inventory:
            parts.append(f"本地缓存服务器文件 {len(self._server_file_inventory)} 个")
        if added_names:
            parts.append(f"新增文件 {len(added_names)}")
        if changed:
            parts.append(f"修改文件 {len(changed)}")
        if unchanged_names:
            parts.append(f"未变化文件 {len(unchanged_names)}")
        if isinstance(updated_files, list) and updated_files:
            parts.append(f"服务器更新时间变化 {len(updated_files)} 个（未重新解析）")
        if bound:
            parts.append(f"兼容记录绑定 {bound}")
        if unmatched:
            parts.append(f"未找到 {len(unmatched)}")
        if conflicts:
            conflict_names = sorted(
                {Path(str(name)).name for name in conflicts if str(name).strip()},
                key=str.casefold,
            )
            suffix = f"（{', '.join(conflict_names[:3])}）" if conflict_names else ""
            parts.append(f"同名冲突 {len(conflicts)}{suffix}")
        if errors:
            error_names = sorted(
                {Path(str(name)).name for name in errors if str(name).strip()},
                key=str.casefold,
            )
            suffix = f"（{', '.join(error_names[:3])}）" if error_names else ""
            parts.append(f"读取/解析失败 {len(errors)}{suffix}")
        if changed:
            parts.append(f"修改文件 {len(changed)}")
        if checked_at:
            parts.append(f"同步时间 {checked_at}")
        text = " | ".join(parts)
        if isinstance(updated_files, list) and updated_files:
            notices: list[str] = []
            for raw in updated_files[:12]:
                if not isinstance(raw, dict):
                    continue
                location = str(raw.get("relative_path", "")).strip() or str(raw.get("name", "")).strip()
                when = self._format_server_mtime(raw.get("mtime_epoch"))
                if location:
                    notices.append(f"{location}（服务器修改：{when}）")
            if notices:
                text += "；检测到文件更新：" + "；".join(notices)
                if len(updated_files) > len(notices):
                    text += f"；另有 {len(updated_files) - len(notices)} 个文件"
        if bool(payload.get("cached_restore")):
            text = text.replace(
                "服务器 element 图元目录同步完成",
                "已从本地缓存恢复服务器 element 图元目录",
                1,
            )
            if payload.get("inventory_complete") is False:
                text += "；当前是旧版缓存，点击一次“同步服务器图元信息”后即可保存完整文件清单"
        if matched:
            text += "。本次只同步服务器图元信息和本地缓存，不执行图元标准检查或纠正。"
        elif conflicts:
            text += "。同名但内容不同的服务器 G 已记录到本地同步状态。"
        elif errors:
            text += "。部分服务器 G 无法读取或解析，已记录到本地同步状态。"
        elif unmatched:
            text += "。服务器目录中未找到的文件未进入本地同步缓存。"
        self.server_library_status.setText(text)
        if hasattr(self, "server_apply_button"):
            self.server_apply_button.setEnabled(False)
        self._refresh_standard_source_summary()
        if should_rebuild_table and not cached_restore and not catalog_only:
            self._apply_standard_table_filter()
            self._apply_fast_inventory_column_widths()
            self._refresh_standard_table_overview()
        elif not cached_restore and not catalog_only:
            self._refresh_standard_table_overview()
        elif catalog_only and not should_rebuild_table:
            self._refresh_standard_table_overview()
        self._update_action_state()

    def _create_next_version_from_server(self) -> None:
        """Create an unlocked ACTIVE version from changed server-cached symbols.

        This is intentionally explicit for a locked standard. The locked ACTIVE
        snapshot is kept intact in history; only the new V(N+1) receives the
        changed authoritative server files already cached by the last sync.
        """
        profile = self._current_active_profile()
        if profile is None or not profile.locked:
            QMessageBox.information(
                self,
                "无需创建新版本",
                "只有当前 ACTIVE 标准已锁定，并且服务器图元库检测到标准文件变化时，才需要使用此操作。",
            )
            return

        payload = dict(self._last_server_sync_payload)
        matched_raw = payload.get("matched_records", {})
        if not isinstance(matched_raw, dict):
            matched_raw = {}
        changed_raw = payload.get("profile_changed_names", [])
        if isinstance(changed_raw, list):
            changed = {Path(str(item)).name.casefold() for item in changed_raw if Path(str(item)).name}
        else:
            changed = {item.casefold() for item in self._server_profile_changed_names(payload)}

        replacements: list[dict[str, object]] = []
        display_names: list[str] = []
        for name, record in matched_raw.items():
            basename = Path(str(name)).name
            if basename and basename.casefold() in changed and isinstance(record, dict):
                replacements.append(dict(record))
                display_names.append(basename)
        if not replacements:
            QMessageBox.information(
                self,
                "没有可应用的服务器更新",
                "当前缓存快照中没有检测到与已锁定标准内容不同、且可安全精确匹配的服务器图元。请先点击“读取服务器标准（仅检查）”。",
            )
            return

        next_version = int(profile.profile_version) + 1
        preview = "\n".join(f"• {name}" for name in sorted(set(display_names), key=str.casefold)[:12])
        extra = max(0, len(set(display_names)) - 12)
        if extra:
            preview += f"\n• ……另外 {extra} 项"
        if QMessageBox.question(
            self,
            "基于服务器更新创建新版本",
            f"当前 {profile.profile_name} V{profile.profile_version} 已锁定。\n\n"
            f"将保留 V{profile.profile_version} 的锁定内容不变，并创建新的 ACTIVE V{next_version}（未锁定），"
            "把下面这些服务器图元更新应用到新版本。全局执行版本不会自动切换：\n\n"
            f"{preview}\n\n继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        try:
            saved = self.service.create_next_version_from_server_records(profile.profile_name, replacements)
        except ValueError as exc:
            QMessageBox.warning(self, "创建新版本失败", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "创建新版本失败", str(exc))
            return

        self._pending_standard_file_records = []
        self._reload_profiles(saved.profile_name, saved.profile_version)
        self.activeProfileChanged.emit(saved.profile_name)
        self.server_new_version_button.setVisible(False)
        self.server_new_version_button.setEnabled(False)
        QMessageBox.information(
            self,
            "新标准版本已创建",
            f"已保留原锁定 V{profile.profile_version}，并创建 ACTIVE V{saved.profile_version}（未锁定）。\n"
            "服务器更新已写入新版本；全局执行版本保持原选择。确认后如需启用新版本，请点击“设为全局版本”。",
        )

    def _start_server_symbol_sync(
        self,
        *,
        background: bool,
        auto_bind: bool,
        compare_profile: bool = True,
    ) -> None:
        if not hasattr(self, "server_standard_enabled") or not self.server_standard_enabled.isChecked():
            return
        if self._server_sync_worker is not None or self._scan_worker is not None or self._task_busy:
            return
        try:
            self._persist_server_library_settings()
            cfg = self._server_library_config()
        except Exception as exc:
            if not background:
                QMessageBox.warning(self, "服务器图元库配置无效", str(exc))
            return

        self.server_library_progress.setRange(0, 100)
        self.server_library_progress.setValue(1)
        self.server_library_progress.setVisible(not background)
        if not background:
            self.server_library_status.setText("正在同步服务器 element 目录下全部 .g 图元信息……当前页面不会执行图元标准检查。")

        def run_sync(log, progress):
            service = RemoteSymbolLibraryService()
            result = service.sync_all(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                root=str(cfg["root"]),
                log=log,
                progress=progress,
            )
            return result.to_payload()

        worker = FunctionWorker(run_sync)
        self._server_sync_worker = worker
        worker.signals.progress.connect(self._on_server_sync_progress)
        worker.signals.result.connect(
            lambda result, a=auto_bind, c=compare_profile: self._on_server_sync_result(
                result, auto_bind=a, compare_profile=c
            )
        )
        worker.signals.error.connect(lambda details, b=background: self._on_server_sync_error(details, background=b))
        worker.signals.finished.connect(self._on_server_sync_finished)
        self._update_action_state()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_server_sync_progress(self, value: int) -> None:
        self.server_library_progress.setValue(max(0, min(100, int(value))))

    def _on_server_sync_result(
        self,
        result: object,
        *,
        auto_bind: bool,
        compare_profile: bool = True,
    ) -> None:
        payload = dict(result) if isinstance(result, dict) else {}
        self.server_library_progress.setRange(0, 100)
        self.server_library_progress.setValue(100)
        self._apply_server_library_payload(
            payload, auto_bind=auto_bind, compare_profile=compare_profile
        )

    def _on_server_sync_error(self, details: str, *, background: bool) -> None:
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self.server_library_status.setText(f"服务器图元信息同步失败：{message or details}")
        if not background:
            QMessageBox.warning(self, "读取服务器图元库失败", message or str(details))

    def _on_server_sync_finished(self) -> None:
        self._server_sync_worker = None
        self._update_action_state()
        # v2.18.176: server access is always operator-driven. A completed manual
        # sync must not arm a later automatic SSH refresh.
        QTimer.singleShot(500, lambda: self.server_library_progress.setVisible(False) if self._server_sync_worker is None else None)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API naming
        self._refresh_global_connection_settings()
        super().showEvent(event)
        # Opening this page is strictly local-only. There are deliberately no
        # automatic remote timers in this module.

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API naming
        super().hideEvent(event)

    @staticmethod
    def _profile_observed_refs(profile: SiteSmartProfile | None) -> set[str]:
        if profile is None:
            return set()
        decisions = {str(key): str(value).strip().lower() for key, value in profile.discovery_decisions.items()}
        return {
            str(key).strip()
            for key in profile.discovery_catalog
            if str(key).strip() and decisions.get(str(key), "") != "ignored"
        }

    def _reset_fresh_rescan_state(self) -> None:
        self._rescan_prepare_mode = False
        self._rescan_draft_mode = False
        self._rescan_draft_base_name = ""
        self._rescan_draft_base_version = None
        self._rescan_draft_target_version = None
        if hasattr(self, "cancel_rescan_draft_button"):
            self.cancel_rescan_draft_button.setVisible(False)
        if hasattr(self, "rescan_version_hint"):
            self.rescan_version_hint.setText(
                "普通扫描更新当前候选；全量重扫创建下一版本草稿。"
            )

    def _prepare_fresh_rescan_version(self) -> None:
        """Arm or start a full business-G rescan for the next local standard version."""
        if self._scan_worker is not None or self._server_sync_worker is not None or self._task_busy:
            return
        name, version, active = self._selected_profile_key()
        if not name or version is None or not active:
            QMessageBox.information(
                self, "请选择当前 ACTIVE 标准",
                "重新扫描创建新版本需要以当前 ACTIVE 标准为基准。历史版本仍可查看/恢复，但不会直接作为重新扫描分支。",
            )
            return
        current = self.service.load_profiles().get(name)
        if current is None:
            return

        if self._rescan_prepare_mode:
            # Second click is a convenience start action after the operator has
            # selected the fresh business-G set in the now-visible input panel.
            self._scan_graphic_symbol_candidates()
            return

        if QMessageBox.question(
            self,
            "全量重新扫描 → 新版本草稿",
            f"将以 {name} V{current.profile_version} 为比较基准，重新读取你接下来选择的业务 G。\n\n"
            f"扫描结果会进入 V{current.profile_version + 1} DRAFT：\n"
            "- 本次扫描结果是新草稿的候选来源；本次已不出现的旧候选不会自动带入；\n"
            "- 仍存在的旧图元会尽量继承人工分类和已验证的标准 G 绑定；\n"
            "- 新出现的图元会自动加入并优先从只读服务器图元库匹配；\n"
            "- 当前 ACTIVE / LOCKED / GLOBAL 都不会因扫描而改变；只有点击“保存为新版本”才生成新的 ACTIVE；\n"
            "- GLOBAL 仍需你之后手动选择。\n\n继续进入重新扫描模式吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ) != QMessageBox.StandardButton.Yes:
            return

        self._rescan_prepare_mode = True
        self._rescan_draft_mode = False
        self._rescan_draft_base_name = name
        self._rescan_draft_base_version = int(current.profile_version)
        self._rescan_draft_target_version = int(current.profile_version) + 1
        self._set_discovery_input_visible(True)
        self.rescan_version_hint.setText(
            f"已进入 V{self._rescan_draft_target_version} 全量重新扫描模式。本次所选业务 G 将作为新草稿候选集合的唯一来源；"
            "旧版中本次未扫描到的候选不会自动带入。"
        )
        self.profile_status.setText(
            f"准备创建 V{self._rescan_draft_target_version} DRAFT：正在使用当前勾选的业务 G 全量重新扫描；"
            f"基准为 V{self._rescan_draft_base_version}，全局执行版本保持不变。"
        )
        self._update_action_state()
        # v2.18.119: one click now both arms the isolated next-version workflow
        # and starts the scan using the G files already selected by the operator.
        # If nothing is selected, the existing scan validation shows the warning and
        # leaves prepare mode armed so the operator can select files and retry.
        QTimer.singleShot(0, self._scan_graphic_symbol_candidates)

    def _cancel_fresh_rescan_draft(self) -> None:
        if not (self._rescan_prepare_mode or self._rescan_draft_mode):
            return
        base_name = self._rescan_draft_base_name
        base_version = self._rescan_draft_base_version
        if self._rescan_draft_mode and QMessageBox.question(
            self,
            "取消新版本草稿",
            "当前重新扫描草稿中的分类、绑定和修改尚未保存。确认放弃并返回已保存版本吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._reset_fresh_rescan_state()
        if base_name and base_version is not None:
            self._reload_profiles(base_name, base_version)
        else:
            self._update_action_state()

    def _collect_draft_rows_for_inheritance(self) -> list[dict[str, object]]:
        """Collect every visible draft row, including still-pending discovery rows."""
        configured = self._collect_custom_symbols()
        by_observed = {
            str(row.get("observed_devref", row.get("match_value", ""))).strip().casefold(): dict(row)
            for row in configured
            if str(row.get("observed_devref", row.get("match_value", ""))).strip()
        }
        rows = list(configured)
        for row_index in self._custom_standard_rows():
            marker = self.standard_table.item(row_index, 0)
            if marker is None:
                continue
            observed = str(marker.data(Qt.ItemDataRole.UserRole + 4) or "").strip()
            if not observed or observed.casefold() in by_observed:
                continue
            scope_combo = self.standard_table.cellWidget(row_index, 0)
            usage_combo = self.standard_table.cellWidget(row_index, 10)
            level_combo = self.standard_table.cellWidget(row_index, 12)
            meta = dict(self._graphic_discovery_catalog.get(observed, {}))
            meta.setdefault("observed_devref", observed)
            entry = self._discovery_entry(meta)
            if isinstance(scope_combo, WheelSafeComboBox):
                entry["scope"] = scope_combo.currentText().strip().upper() or "ANY"
            role_item = self.standard_table.item(row_index, 1)
            tag_item = self.standard_table.item(row_index, 2)
            subtype_item = self.standard_table.item(row_index, 11)
            if role_item is not None:
                entry["role"] = entry["device_type"] = role_item.text().strip()
            if tag_item is not None:
                entry["element_tag"] = tag_item.text().strip()
            if subtype_item is not None:
                entry["device_subtype"] = subtype_item.text().strip()
            if isinstance(usage_combo, WheelSafeComboBox):
                entry["symbol_usage"] = usage_combo.currentText().strip()
            if isinstance(level_combo, WheelSafeComboBox):
                entry["device_level"] = level_combo.currentText().strip()
            rows.append(entry)
        return rows

    def _enter_fresh_rescan_draft(self, catalog: dict[str, dict[str, object]]) -> None:
        """Replace the editor with a scan-source-of-truth V(N+1) draft."""
        base = self.service.get_profile_version(
            self._rescan_draft_base_name, self._rescan_draft_base_version
        )
        if base is None:
            # The selected base disappeared unexpectedly; keep the scan visible as a
            # normal discovery result rather than risking a write to the wrong profile.
            self._rescan_prepare_mode = False
            self._rescan_draft_mode = False
            self._discovery_decisions = {}
            self._load_custom_symbols([])
            self._apply_discovery_to_rows()
            self._merge_server_catalog_rows()
            return

        was_draft = bool(self._rescan_draft_mode)
        base_rows = self._collect_draft_rows_for_inheritance() if was_draft else self._profile_standard_rows(base)
        by_observed: dict[str, dict[str, object]] = {}
        by_filename: dict[str, dict[str, object]] = {}
        for raw in base_rows:
            row = dict(raw)
            observed = str(row.get("observed_devref", row.get("match_value", ""))).strip()
            if observed:
                by_observed.setdefault(observed.casefold(), row)
            filename = Path(str(row.get("observed_symbol_file", row.get("source_file", ""))).strip()).name
            if filename:
                by_filename.setdefault(filename.casefold(), row)

        draft_rows: list[dict[str, object]] = []
        inherited = 0
        for observed_devref, meta_raw in sorted(
            catalog.items(), key=lambda item: (-int(item[1].get("count", 0) or 0), item[0].casefold())
        ):
            meta = dict(meta_raw)
            symbol_file = Path(str(meta.get("observed_symbol_file", "")).strip()).name
            prior = by_observed.get(observed_devref.casefold())
            if prior is None and symbol_file:
                prior = by_filename.get(symbol_file.casefold())
            if prior is None:
                draft_rows.append(self._discovery_entry(meta))
                continue
            row = dict(prior)
            row["candidate_only"] = not bool(str(row.get("standard_devref", "")).strip())
            row["observed_devref"] = observed_devref
            row["match_attr"] = "devref"
            row["match_value"] = observed_devref
            row["observed_symbol_file"] = str(meta.get("observed_symbol_file", "")).strip()
            row["observed_count"] = max(0, int(meta.get("count", 0) or 0))
            row["observed_files"] = [str(item) for item in meta.get("files", []) if str(item).strip()] if isinstance(meta.get("files", []), list) else []
            row["observed_examples"] = [dict(item) for item in meta.get("sample_positions", []) if isinstance(item, dict)] if isinstance(meta.get("sample_positions", []), list) else []
            row["sample_names"] = [str(item) for item in meta.get("sample_names", []) if str(item).strip()] if isinstance(meta.get("sample_names", []), list) else []
            draft_rows.append(row)
            inherited += 1

        self._rescan_prepare_mode = False
        self._rescan_draft_mode = True
        self._discovery_decisions = {}  # a fresh scan re-evaluates formerly ignored candidates
        self._graphic_discovery_catalog = {str(key): dict(value) for key, value in catalog.items()}
        if not was_draft:
            self._pending_standard_file_records = []
            self._rebuild_symbol_catalog([dict(row) for row in base.managed_standard_files])
        self._load_custom_symbols(draft_rows)
        self._apply_discovery_to_rows()
        self.site_name.setText(base.site_name)
        self.profile_name.setText(base.profile_name)
        self._set_editor_enabled(True)
        self._set_discovery_input_visible(True)
        global_text = self._global_profile_summary()
        self.current_profile_label.setText(global_text)
        self.active_profile_summary.setText(
            f"{global_text}（正在编辑 V{self._rescan_draft_target_version} DRAFT；基准 V{self._rescan_draft_base_version}）"
        )
        self.profile_status.setText(
            f"DRAFT · V{self._rescan_draft_target_version} · 来源：重新扫描业务 G · "
            f"已继承 {inherited} 个仍存在图元的分类/标准绑定；保存前不会修改任何已保存版本。"
        )
        self.rescan_version_hint.setText(
            f"当前为 V{self._rescan_draft_target_version} DRAFT。可继续重新扫描更新草稿、修改分类、删除候选或补标准；"
            "确认后点击“保存为新版本”。GLOBAL 不会自动切换。"
        )
        self._update_action_state()

    def _scan_graphic_symbol_candidates(self) -> None:
        """Discover business-G symbols and auto-resolve matching server standards in one worker."""
        if self._scan_worker is not None or self._server_sync_worker is not None:
            return

        input_mode = self.discovery_source.mode()
        remote_job: tuple[dict[str, object], list[object], Path] | None = None
        prepared_source: Path | None = None

        # Snapshot only lightweight UI values. All SFTP work happens in FunctionWorker.
        if input_mode == InputMode.REMOTE_SSH:
            remote = self.discovery_source.remote
            selected_files = list(remote.selected_files())
            if not selected_files:
                QMessageBox.warning(self, "图形 G 图元发现输入", "请先在 SSH G 文件列表中选择一个或多个文件。")
                return
            try:
                remote.persist()
                remote_job = (dict(remote.config()), selected_files, remote._processing_snapshot_dir())
            except Exception as exc:
                QMessageBox.warning(self, "SSH 远程输入准备失败", str(exc))
                return
        else:
            if not validate_input_source(self, self.discovery_source, display_name="图形 G 图元发现输入"):
                return
            self.discovery_source.persist_current()
            prepared_source = self.discovery_source.path()

        if input_mode == InputMode.REMOTE_SSH:
            self.scan_progress.setRange(0, 100)
            self.scan_progress.setValue(1)
            self.scan_summary.setText("正在后台下载 SSH 只读业务 G 快照……随后解析业务图元。")
        else:
            self.scan_progress.setRange(0, 100)
            self.scan_progress.setFormat("准备扫描图形 G %p%")
            self.scan_progress.setValue(1)
            self.scan_summary.setText("正在准备扫描业务 G……")
        self.scan_progress.setVisible(True)
        self._update_action_state()

        def run_discovery(log, progress):
            parse_end = 100
            if remote_job is not None:
                cfg, selected, snapshot_dir = remote_job
                log(f"[SSH只读] 后台准备 {len(selected)} 个服务器 G 文件，本地快照：{snapshot_dir}")
                progress(2)
                download_stable_files(
                    host=str(cfg["host"]),
                    port=int(cfg["port"]),
                    username=str(cfg["username"]),
                    password=str(cfg["password"]),
                    selected_files=selected,
                    target_dir=snapshot_dir,
                    log=log,
                )
                progress(25)
                payload = discover_graphic_symbols(
                    snapshot_dir,
                    InputMode.DIRECTORY,
                    log=log,
                    progress=lambda value: progress(25 + round(int(value) * (parse_end - 25) / 100)),
                )
            else:
                assert prepared_source is not None
                progress(2)
                payload = discover_graphic_symbols(
                    prepared_source,
                    input_mode,
                    log=log,
                    progress=lambda value: progress(2 + round(int(value) * (parse_end - 2) / 100)),
                )

            return payload

        # Create/connect the worker now so the scan button is disabled immediately,
        # but defer pool.start() one event-loop turn so Qt can paint the progress bar.
        worker = FunctionWorker(run_discovery)
        self._scan_worker = worker
        worker.signals.progress.connect(self._on_discovery_progress)
        worker.signals.result.connect(self._on_graphic_discovery_result)
        worker.signals.error.connect(self._on_scan_error)
        worker.signals.finished.connect(self._on_scan_finished)
        self._update_action_state()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_discovery_progress(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.scan_progress.setFormat("扫描图形 G 图元 %p%")
        self.scan_progress.setValue(value)

    def _on_graphic_discovery_result(self, result: object) -> None:
        payload = dict(result) if isinstance(result, dict) else {}
        candidates = payload.get("candidates", [])
        catalog: dict[str, dict[str, object]] = {}
        if isinstance(candidates, list):
            for raw in candidates:
                if not isinstance(raw, dict):
                    continue
                observed = str(raw.get("observed_devref", "")).strip()
                if not observed:
                    continue
                row = dict(raw)
                row["devref"] = observed
                row["element_id"] = str(raw.get("observed_subject", "")).strip()
                row["source_file"] = str(raw.get("observed_symbol_file", "")).strip()
                # Geometry fields in discovery metadata are deliberately zero/empty.
                # Business-G observed sizes remain under observed_sizes only.
                row["width"] = 0.0
                row["height"] = 0.0
                row["align_center"] = []
                row["pins"] = []
                catalog[observed] = row
        self._graphic_discovery_catalog = catalog

        fresh_rescan = bool(self._rescan_prepare_mode or self._rescan_draft_mode)
        if fresh_rescan:
            self._enter_fresh_rescan_draft(catalog)
        else:
            # Preserve current authoritative custom rows while rebuilding candidate rows.
            saved_rows = self._collect_custom_symbols()
            self._load_custom_symbols(saved_rows)
            self._apply_discovery_to_rows()

            name, _version, active = self._selected_profile_key()
            if name and active:
                updated = self.service.update_discovery_metadata(name, catalog=catalog)
                if updated is not None:
                    self._graphic_discovery_catalog = {str(key): dict(value) for key, value in updated.discovery_catalog.items()}
                    saved_rows = self._collect_custom_symbols()
                    self._load_custom_symbols(saved_rows)
                    self._apply_discovery_to_rows()

        server_payload = payload.get("server_library", {})
        if isinstance(server_payload, dict) and server_payload:
            self._apply_server_library_payload(server_payload, auto_bind=True)
        else:
            server_error = str(payload.get("server_library_error", "")).strip()
            if server_error:
                self.server_library_status.setText(
                    f"业务 G 扫描成功，但服务器图元库读取失败：{server_error}。可稍后点击“读取服务器标准（仅检查）”重试。"
                )

        file_count = int(payload.get("file_count", 0) or 0)
        candidate_count = int(payload.get("candidate_count", 0) or 0)
        instance_count = int(payload.get("instance_count", 0) or 0)
        pending = sum(
            1 for row in self._custom_standard_rows()
            if (self.standard_table.item(row, 0) is not None
                and bool(self.standard_table.item(row, 0).data(Qt.ItemDataRole.UserRole + 3))
                and not self._standard_file_devref(row))
        )
        self.scan_progress.setValue(100)
        matched_count = 0
        if isinstance(server_payload, dict):
            matched_records = server_payload.get("matched_records", {})
            matched_count = len(matched_records) if isinstance(matched_records, dict) else 0
        if self._rescan_draft_mode:
            base_profile = self.service.get_profile_version(self._rescan_draft_base_name, self._rescan_draft_base_version)
            old_refs = self._profile_observed_refs(base_profile) if base_profile is not None else set()
            new_refs = set(self._graphic_discovery_catalog)
            added = len(new_refs - old_refs)
            removed = len(old_refs - new_refs)
            retained = len(new_refs & old_refs)
            self.scan_summary.setText(
                f"V{self._rescan_draft_target_version or '?'} DRAFT 业务 G 检查线索读取完成：{file_count} 个文件，"
                f"发现 {candidate_count} 种 devref / {instance_count} 个图元实例（不计入标准）；相对基准 V{self._rescan_draft_base_version or '?'}："
                f"新增 {added}、仍存在 {retained}、本次已不出现 {removed}；服务器自动匹配 {matched_count} 项，"
                f"仍待服务器匹配 {pending} 项。"
            )
        else:
            ignored_count = sum(
                1 for key in self._graphic_discovery_catalog
                if str(self._discovery_decisions.get(str(key), "")).strip().lower() == "ignored"
            )
            ignored_note = (
                f" 当前版本还保留 {ignored_count} 个“已忽略”候选决定，因此普通扫描不会把它们重新加入表格；"
                "如需让本次业务 G 重新决定新版本的候选集合，请点击“全量重新扫描 → 新版本草稿”。"
                if ignored_count else
                " 普通扫描只更新当前版本候选，不会自动创建下一版本；如需建立下一版本，请点击“全量重新扫描 → 新版本草稿”。"
            )
            self.scan_summary.setText(
                f"业务 G 检查线索读取完成：{file_count} 个文件，发现 {candidate_count} 种 devref / {instance_count} 个图元实例（不计入标准）；"
                f"服务器自动匹配 {matched_count} 项，当前仍待服务器匹配 {pending} 项。" + ignored_note
            )
        warnings = payload.get("warnings", [])
        if self._rescan_draft_mode:
            warning_text = "；".join(str(item) for item in warnings[:3]) if isinstance(warnings, list) and warnings else ""
            self.profile_status.setText(
                f"DRAFT · V{self._rescan_draft_target_version or '?'} · 基准 V{self._rescan_draft_base_version or '?'} · "
                f"重新扫描结果尚未保存；可继续调整/补标准后点击“保存为新版本”。"
                + (f" 警告：{warning_text}" if warning_text else "")
            )
        elif isinstance(warnings, list) and warnings:
            self.profile_status.setText("；".join(str(item) for item in warnings[:3]))
        elif pending:
            self.profile_status.setText("服务器图元目录已读取；仍未匹配的历史候选不会进入当前标准，需等待服务器目录提供对应定义。")
        elif matched_count:
            self.profile_status.setText("业务 G 候选已自动分类并与服务器图元目录完成匹配；请确认分类/标准后保存当前版本。")
        self._update_action_state()

    def _set_discovery_input_visible(self, visible: bool) -> None:
        """Show discovery source controls only while the selected ACTIVE version is unlocked."""
        visible = bool(visible)
        if hasattr(self, "discovery_input_panel"):
            self.discovery_input_panel.setVisible(visible)
        if hasattr(self, "discovery_locked_note"):
            self.discovery_locked_note.setVisible(not visible)

    def _set_editor_enabled(self, enabled: bool) -> None:
        self.site_name.setReadOnly(not enabled)
        self.profile_name.setReadOnly(not enabled)
        for combo in (self.lbs_combo, self.breaker_combo, self.ground_combo, self.normal_lbs_combo, self.normal_breaker_combo, self.normal_ground_combo):
            combo.setEnabled(enabled)
        for row in self._custom_standard_rows():
            for column in (0, 10, 12):
                widget = self.standard_table.cellWidget(row, column)
                if widget is not None:
                    widget.setEnabled(enabled)
        editor_enabled = bool(enabled and self._is_admin_mode)
        self.standard_table.setEditTriggers(
            (QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
            if editor_enabled else QAbstractItemView.EditTrigger.NoEditTriggers
        )
        if hasattr(self, "upload_standard_button"):
            self.upload_standard_button.setEnabled(False)
        if hasattr(self, "share_pair_checkbox"):
            self.share_pair_checkbox.setEnabled(enabled and 0 <= self.standard_table.currentRow() < len(self._standard_specs))
        self.add_custom_button.setEnabled(False)
        self.delete_custom_button.setEnabled(False)
        self.save_button.setEnabled(enabled and self._is_admin_mode)

    def _current_active_profile(self) -> SiteSmartProfile | None:
        name = self._selected_profile_name()
        return self.service.load_profiles().get(name) if name else None

    def _toggle_profile_lock(self) -> None:
        name, version, active = self._selected_profile_key()
        if not name or version is None or not active:
            QMessageBox.information(self, "请先保存标准", "锁定功能只针对已保存的当前 ACTIVE 标准版本。")
            return
        profile = self.service.load_profiles().get(name)
        if profile is None:
            return
        if profile.locked:
            if QMessageBox.question(
                self,
                "解锁当前标准",
                f"确认解锁 {name} V{profile.profile_version}？\n\n解锁后可以重新上传/绑定标准 G、修改表格并保存新版本。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            locked = False
        else:
            if QMessageBox.question(
                self,
                "锁定当前标准",
                f"确认锁定 {name} V{profile.profile_version}？\n\n锁定后该 ACTIVE 版本不能修改、上传标准 G、删除或恢复历史版本；仍可正常执行服务器图元更新检查。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            locked = True
        def finish(saved: SiteSmartProfile) -> None:
            self._reload_profiles(saved.profile_name, saved.profile_version)
            self.activeProfileChanged.emit(saved.profile_name)

        action = "锁定" if locked else "解锁"
        self._start_profile_operation(
            f"正在{action} {name} V{version}，请稍候……",
            lambda: self.service.set_locked(name, locked),
            finish,
        )

    def _new_profile(self, *_args, clear_selection: bool = True) -> None:
        self._reset_fresh_rescan_state()
        if clear_selection and hasattr(self, "profile_selector"):
            self.profile_selector.blockSignals(True)
            self.profile_selector.setCurrentIndex(-1)
            self.profile_selector.blockSignals(False)
        self._selected_version = None
        self._selected_is_active = False
        self._selected_profile_locked = False
        self._candidate_counts.clear()
        self._rebuild_symbol_catalog([])
        self._graphic_discovery_catalog.clear()
        self._discovery_decisions.clear()
        self._server_catalog_ignored.clear()
        self._pending_standard_file_records = []
        # The visible server inventory is an independent AppData cache, not a
        # Profile editor.  Creating/initializing the legacy hidden Profile state must
        # never wipe the operator's 200-row server-symbol table.  This also closes the
        # no-profile startup race where the 0-ms profile initializer could erase a
        # cache that had just been restored.
        if self._server_inventory_table_enabled and self._server_file_inventory:
            self._restore_cached_inventory_table_fast()
        else:
            self._clear_custom_standard_rows()
            self._merge_server_catalog_rows()
        self.site_name.clear()
        self.profile_name.clear()
        self.lbs_combo.clear()
        self.breaker_combo.clear()
        self.normal_lbs_combo.clear()
        self.normal_breaker_combo.clear()
        self.ground_combo.clear()
        self.normal_ground_combo.clear()
        self.scan_summary.setText("尚未同步服务器图元目录。")
        self.profile_status.setText("当前页面只维护服务器图元同步信息和本地分类标记。")
        self.current_profile_label.setText("服务器图元同步管理")
        self.active_profile_summary.setText("本地同步目录：尚未同步服务器图元目录。")
        self._last_scan = None
        self._set_editor_enabled(True)
        self._set_discovery_input_visible(True)
        if hasattr(self, "lock_standard_button"):
            self.lock_standard_button.setText("锁定当前标准")
            self.lock_standard_button.setEnabled(False)
        if hasattr(self, "server_new_version_button"):
            self.server_new_version_button.setVisible(False)
            self.server_new_version_button.setEnabled(False)
        self._last_server_sync_payload = {}
        if self._server_catalog_records:
            self._refresh_standard_source_summary()
        self.restore_action.setEnabled(False)
        self.delete_action.setEnabled(False)
        self._update_action_state()

    def _global_profile_summary(self) -> str:
        profile = self.service.get_current_server_standard(auto_initialize=False)
        if profile is None:
            return "当前服务器标准：尚未设置"
        return (
            f"当前服务器标准：{profile.site_name} / {profile.profile_name} · "
            f"服务器版本 {profile.server_standard_label} UTC"
        )

    def _set_selected_global_version(self) -> None:
        name, version, _active = self._selected_profile_key()
        if not name or version is None:
            QMessageBox.information(self, "请选择版本", "请先在“标准版本”下拉框中选择一个已保存版本。")
            return
        profile = self.service.get_profile_version(name, version)
        if profile is None:
            QMessageBox.warning(self, "版本不存在", f"未找到 {name} V{version}。")
            return
        if not profile.authoritative_ready:
            QMessageBox.warning(
                self, "版本不可执行",
                "该版本没有已绑定的标准图元，不能设为全局执行标准。",
            )
            return

        def finish(saved: SiteSmartProfile) -> None:
            self._reload_profiles(name, version)
            self.activeProfileChanged.emit(name)
            QMessageBox.information(
                self, "全局版本已更新",
                f"已将 {saved.site_name} / {saved.profile_name} / V{saved.profile_version} 设为全局执行标准。\n"
                "后续模块会固定使用这个版本，直到你再次手动选择其他版本。",
            )

        self._start_profile_operation(
            f"正在设置 {name} V{version} 为全局执行版本，请稍候……",
            lambda: self.service.set_global_profile_version(name, version),
            finish,
        )

    def _set_version_switch_busy(self, busy: bool, *, name: str = "", version: int | None = None) -> None:
        """Show immediate checkout feedback for slower historical-version switches."""
        if not hasattr(self, "version_switch_status"):
            return
        self.version_switch_status.setVisible(bool(busy))
        self.version_switch_progress.setVisible(bool(busy))
        if busy:
            self.version_switch_progress.setValue(1)
            suffix = f" V{version}" if version is not None else ""
            self.version_switch_status.setText(
                f"正在切换标准版本：{name}{suffix}，正在从本地图元版本库加载冻结配置，请稍候……"
            )
        else:
            self.version_switch_progress.setValue(100)
            self.version_switch_status.clear()

    def _start_profile_operation(self, message: str, operation, callback) -> None:
        """Run local version-library work outside the UI thread with visible feedback."""
        if self._profile_operation_worker is not None:
            return
        self._profile_operation_title = str(message)
        self._profile_operation_callback = callback
        self._set_version_switch_busy(True)
        self.version_switch_status.setText(self._profile_operation_title)
        self.version_switch_progress.setValue(1)

        def run(log, progress):
            progress(8)
            result = operation()
            progress(92)
            return result

        worker = FunctionWorker(run)
        self._profile_operation_worker = worker
        worker.signals.progress.connect(
            lambda value: self.version_switch_progress.setValue(max(0, min(100, int(value))))
        )
        worker.signals.result.connect(self._on_profile_operation_result)
        worker.signals.error.connect(self._on_profile_operation_error)
        worker.signals.finished.connect(self._on_profile_operation_finished)
        self._update_action_state()
        QTimer.singleShot(0, lambda w=worker: self._scan_pool.start(w))

    def _on_profile_operation_result(self, result: object) -> None:
        callback = self._profile_operation_callback
        if callable(callback):
            callback(result)

    def _on_profile_operation_error(self, details: str) -> None:
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        self.version_switch_status.setText(f"操作失败：{message or details}")
        QMessageBox.warning(self, "标准版本操作失败", message or str(details))

    def _on_profile_operation_finished(self) -> None:
        self._profile_operation_worker = None
        self._profile_operation_callback = None
        self.version_switch_progress.setValue(100)
        self._set_version_switch_busy(False)
        self._profile_operation_title = ""
        self._update_action_state()
        QTimer.singleShot(
            700,
            lambda: self.version_switch_progress.setVisible(False)
            if self._profile_operation_worker is None else None,
        )

    def _profile_selection_changed(self, *_args, load_catalog: bool = True) -> None:
        # Selecting a saved version abandons any unsaved fresh-rescan DRAFT.
        if self._rescan_prepare_mode or self._rescan_draft_mode:
            self._reset_fresh_rescan_state()
        name, version, active = self._selected_profile_key()
        if not name or version is None:
            return
        self._set_version_switch_busy(True, name=name, version=version)
        try:
            profile = self.service.get_profile_version(name, version)
            current = self.service.load_profiles().get(name)
            if profile is None or current is None:
                return
            self._selected_version = version
            self._selected_is_active = active
            self._selected_profile_locked = bool(profile.locked)
            self._pending_standard_file_records = []
            self._server_catalog_ignored.clear()
            self._last_server_sync_payload = {}
            if hasattr(self, "server_new_version_button"):
                self.server_new_version_button.setVisible(False)
                self.server_new_version_button.setEnabled(False)
            records = [dict(row) for row in profile.managed_standard_files]
            self._rebuild_symbol_catalog(records)
            self._graphic_discovery_catalog = {str(key): dict(value) for key, value in profile.discovery_catalog.items()}
            self._discovery_decisions = {str(key): str(value) for key, value in profile.discovery_decisions.items()}
            if load_catalog:
                # Manual sync, explicit profile changes, and normal application
                # startup may restore the local snapshot.  This is local-only;
                # opening the program must not contact SSH or refresh the server.
                restored = self._restore_cached_server_sync()
                if not restored:
                    display_rows = self._profile_standard_rows(profile)
                    self._load_custom_symbols(display_rows)
                    self._apply_discovery_to_rows()
                    self._merge_server_catalog_rows()
            else:
                # Startup profile selection intentionally skips legacy Profile catalog
                # loading.  The server-symbol inventory is an independent local AppData
                # cache and may already have been restored a few lines earlier in the
                # constructor.  Do NOT clear it here: _reload_profiles(...,
                # defer_selection=True, load_catalog=False) completes on a 0-ms timer,
                # so clearing these objects after the cache restore made the UI report
                # "200 cached files restored" while the visible table was reset to 0.
                # Keep the cached server catalog/table exactly as restored; only the
                # legacy Profile catalog load is skipped by load_catalog=False.
                pass
            self.site_name.setText(profile.site_name)
            self.profile_name.setText(profile.profile_name)
            # Legacy fixed-role fields are intentionally not rendered as special rows.
            # _profile_standard_rows() converts them to ordinary generic definitions for
            # backward compatibility; saving the profile again completes the migration.
            for combo in (self.lbs_combo, self.breaker_combo, self.ground_combo, self.normal_lbs_combo, self.normal_breaker_combo, self.normal_ground_combo):
                combo.clear()
            self._refresh_standard_source_summary()
            global_name, global_version = self.service.get_global_profile_selection()
            is_global = profile.profile_name == global_name and profile.profile_version == global_version
            if active:
                self.user_settings.set_value("site_profile/last_profile_name", profile.profile_name)
                # Do not hash every frozen symbol while changing the combobox.
                # The detailed integrity check remains in execution/GLOBAL actions.
                ready_ok, ready_issues = profile.authoritative_ready, []
                fingerprint = (profile.standard_fingerprint or "-")[:16]
                self.profile_status.setText(
                    f"当前标准：{'READY' if ready_ok else 'NOT READY'} · "
                    f"服务器版本：{profile.server_standard_label} UTC · 标准指纹 {fingerprint} · "
                    f"最后更新：{profile.updated_at or '-'}"
                )
                if not ready_ok:
                    self.scan_summary.setText("当前标准不可执行：" + "；".join(ready_issues[:3]))
            else:
                self.profile_status.setText(
                    "当前配置不是服务器标准的可编辑对象，请返回当前服务器标准。"
                )
            global_text = self._global_profile_summary()
            self.current_profile_label.setText(global_text)
            self.active_profile_summary.setText(global_text)
            self._last_scan = None
            editable = bool(active)
            self._set_editor_enabled(editable)
            # Only a locked ACTIVE version hides the Graphic-G discovery input.
            # Archived versions keep the input area visible for context, but their scan
            # action stays disabled because they are view-only.
            self._set_discovery_input_visible(not bool(active and profile.locked))
            if hasattr(self, "lock_standard_button"):
                self.lock_standard_button.setText("解锁当前版本" if active and profile.locked else "锁定当前版本")
                self.lock_standard_button.setEnabled(bool(active and not self._task_busy))
            self.restore_action.setEnabled(bool(not active and not current.locked))
            global_name, global_version = self.service.get_global_profile_selection(auto_initialize=False)
            selected_is_global = profile.profile_name == global_name and profile.profile_version == global_version
            self.delete_history_action.setEnabled(bool(not active and not selected_is_global))
            self.delete_action.setEnabled(bool(active and not profile.locked))
            self._update_action_state()
            self._standard_row_selection_changed()
            if load_catalog:
                self._refresh_local_classification_markers()
            self._refresh_standard_source_summary()
        finally:
            self._set_version_switch_busy(False)

    def _restore_selected_version(self) -> None:
        name, version, active = self._selected_profile_key()
        if not name or version is None:
            QMessageBox.information(self, "请选择标准", "请先选择需要恢复的历史标准版本。")
            return
        if active:
            QMessageBox.information(self, "已经是当前版本", f"{name} V{version} 已经是 ACTIVE 版本。")
            return
        current = self.service.load_profiles().get(name)
        if current is None:
            return
        if current.locked:
            QMessageBox.information(self, "当前标准已锁定", f"{name} V{current.profile_version} 已锁定。请先解锁后再删除。")
            return
        if QMessageBox.question(
            self,
            "恢复历史版本",
            f"将 {name} V{version} 的图元 devref 与几何标准恢复为新的当前版本。\n"
            f"现有 ACTIVE V{current.profile_version} 会保留在历史中，不会删除。\n\n继续吗？",
        ) != QMessageBox.StandardButton.Yes:
            return
        def finish(restored: SiteSmartProfile) -> None:
            self._reload_profiles(restored.profile_name, restored.profile_version)
            self.activeProfileChanged.emit(restored.profile_name)
            QMessageBox.information(
                self,
                "已恢复",
                f"已将历史 V{version} 恢复为新的 ACTIVE V{restored.profile_version}。后续一致性处理使用 V{restored.profile_version}。",
            )

        self._start_profile_operation(
            f"正在从历史 V{version} 恢复新的标准版本，请稍候……",
            lambda: self.service.restore_version(name, version),
            finish,
        )

    def _fill_candidate_combo(self, combo: WheelSafeComboBox, counts: dict[str, int], selected: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        normalized_counts = {str(key): int(value) for key, value in counts.items()}
        self._candidate_counts[id(combo)] = normalized_counts
        total = sum(max(0, int(value)) for value in normalized_counts.values())
        rows = sorted(normalized_counts.items(), key=lambda row: (-int(row[1]), row[0].casefold()))
        for devref, count in rows:
            confidence = (count / total) if total else 0.0
            combo.addItem(f"{devref}   [{count}, {confidence:.0%}]", devref)
        if selected and combo.findData(selected) < 0:
            combo.addItem(selected, selected)
        index = combo.findData(selected)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self._refresh_standard_row(combo)

    def _refresh_standard_row(self, combo: WheelSafeComboBox) -> None:
        specs = getattr(self, "_standard_specs", [])
        row = next((idx for idx, (_kind, _role, _tag, widget, _match_attr, _match_value) in enumerate(specs) if widget is combo), -1)
        if row < 0 or not hasattr(self, "standard_table"):
            return
        selected = str(combo.currentData() or combo.currentText() or "").strip()
        self._set_standard_file_cell(row, selected)
        self._refresh_symbol_properties(row, selected)
        meta = self._symbol_meta(selected)
        source_item = self.standard_table.item(row, 8) or self._set_readonly_cell(row, 8, "-")
        status_item = self.standard_table.item(row, 9) or self._set_readonly_cell(row, 9, "未上传")
        source_file = Path(str(meta.get("source_file", "")).strip()).name
        source_item.setText("用户上传" if selected and source_file else "未上传")
        source_item.setToolTip(source_file or "未上传")
        status_text = "READY" if selected and meta else "缺少标准图元"
        if row < len(self._standard_specs) and selected and meta:
            expected_tag = str(self._standard_specs[row][2] or "").strip()
            actual_tag = str(meta.get("element_tag", "") or "").strip()
            if expected_tag and actual_tag and expected_tag != actual_tag:
                status_text = "READY · XML参考不同"
                status_item.setToolTip(
                    f"当前设备角色由用户明确绑定。上传 G 解析 XML={actual_tag}；检查对象 XML={expected_tag}。"
                    "这不会阻止保存/检查，但请确认当前行确实是你希望绑定的设备角色。"
                )
            pair_row = self._paired_builtin_row(row)
            if pair_row >= 0:
                paired = str(self._standard_specs[pair_row][3].currentData() or "").strip()
                if paired and paired.casefold() == selected.casefold():
                    pair_scope = self._standard_specs[pair_row][0]
                    suffix = " · XML参考不同" if "XML参考不同" in status_text else ""
                    status_text = f"READY · 与 {pair_scope} 共用{suffix}"
        status_item.setText(status_text)
        if self.standard_table.currentRow() == row and hasattr(self, "share_pair_checkbox"):
            self._standard_row_selection_changed()
        self._fit_standard_table_columns()


    def _scan_samples(self) -> None:
        """Upload one authoritative symbol G into the currently selected generic row."""
        if not self.site_name.text().strip():
            QMessageBox.warning(self, "Site Name", "请先输入适用范围，再上传标准图元 G。")
            return
        if not self.profile_name.text().strip():
            QMessageBox.warning(self, "Profile Name", "请先输入标准名称。")
            return
        selected_name, selected_version, selected_active = self._selected_profile_key()
        selected_profile = self.service.load_profiles().get(selected_name) if selected_name and selected_active else None
        if selected_profile is not None and selected_profile.locked:
            QMessageBox.information(
                self,
                "当前标准已锁定",
                f"{selected_name} V{selected_version} 已锁定，不能上传或替换标准 G。请先点击“解锁当前版本”。",
            )
            return

        row = self.standard_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "先选择图元候选",
                "请先扫描图形 G，并在表格中选中需要纳入标准管理的图元候选，然后上传对应的权威图元 G。"
                "一个图元 G 只绑定当前选中行。",
            )
            return

        typed_name = self.profile_name.text().strip()
        selected_name, _version, _active = self._selected_profile_key()
        existing = self.service.load_profiles().get(typed_name)
        if existing is not None and selected_name != typed_name:
            QMessageBox.warning(
                self,
                "标准名称已存在",
                f"图元标准“{typed_name}”已存在。请在“标准版本”下拉框中选择后更新，或者使用新的标准名称。",
            )
            return

        scope_widget = self.standard_table.cellWidget(row, 0)
        scope = scope_widget.currentText().strip().upper() if isinstance(scope_widget, WheelSafeComboBox) else "ANY"
        role_label = (self.standard_table.item(row, 1).text() if self.standard_table.item(row, 1) else "").strip() or "待分类图元"
        expected_tag = (self.standard_table.item(row, 2).text() if self.standard_table.item(row, 2) else "").strip()
        role_display = f"{scope} / {role_label}"

        recent = self.user_settings.resolve_directory(
            "recent_paths/site_profile/standard_icon_directory", fallback=Path.home()
        ).directory
        selected_file, _filter = QFileDialog.getOpenFileName(
            self,
            f"为 {role_display} 选择标准图元 G",
            str(recent),
            "G Icon Files (*.g);;All Files (*.*)",
        )
        if not selected_file:
            return
        path = Path(selected_file)
        self.user_settings.set_path("recent_paths/site_profile/standard_icon_directory", path.parent)

        # v2.18.106: a discovered candidate can only be bound to the exact
        # symbol-G filename seen in the business/graphic G.  Check the selected
        # basename before parsing or adding anything to the pending standard set,
        # so a wrong-but-valid G can never be accidentally attached to this row.
        # Comparison is case-insensitive to match Windows filesystem semantics.
        # Manually-added rows without discovery evidence keep the existing flow.
        expected_symbol_file = ""
        observed_file_item = self.standard_table.item(row, 13)
        if observed_file_item is not None:
            expected_symbol_file = observed_file_item.text().strip()
        if not expected_symbol_file or expected_symbol_file == "-":
            marker = self.standard_table.item(row, 0)
            if marker is not None:
                observed_devref = str(marker.data(Qt.ItemDataRole.UserRole + 4) or "").strip()
                expected_symbol_file = self._observed_symbol_g_filename(observed_devref)
        actual_symbol_file = path.name
        if expected_symbol_file and not self._same_symbol_g_filename(expected_symbol_file, actual_symbol_file):
            QMessageBox.warning(
                self,
                "禁止上传：图元文件名不匹配",
                "当前候选是从业务/图形 G 自动扫描出来的，上传的标准图元 G 必须与扫描图元文件名一致。\n\n"
                f"扫描检测到：{expected_symbol_file}\n"
                f"当前选择：{actual_symbol_file}\n\n"
                "请重新选择与“扫描图元 G 文件全名”完全对应的标准图元 G。",
            )
            return

        try:
            record = dict(self.service.prepare_standard_file_records([path])[0])
        except Exception as exc:
            QMessageBox.critical(self, "标准图元无效", str(exc))
            return

        actual_tag = str(record.get("element_tag", "")).strip()

        devref = str(record.get("devref", "")).strip()
        pending_by_devref = {
            str(item.get("devref", "")).casefold(): dict(item)
            for item in self._pending_standard_file_records
            if str(item.get("devref", "")).strip()
        }
        pending_by_devref[devref.casefold()] = record
        self._pending_standard_file_records = list(pending_by_devref.values())

        records = self._editor_standard_records()
        self._rebuild_symbol_catalog(records)
        for custom_row in self._custom_standard_rows():
            self._refresh_custom_standard_row(custom_row)

        # Bind the uploaded authoritative symbol only to the selected learned row.
        # XML/devref discovery identifies the candidate; w×h, AlignCenter and Pins
        # come exclusively from this uploaded symbol G.
        if not expected_tag:
            tag_item = self.standard_table.item(row, 2)
            if tag_item is not None:
                tag_item.setText(actual_tag)
        self._set_standard_file_cell(row, devref)
        self._refresh_custom_standard_row(row)

        self._last_scan = None
        shared_text = "绑定当前图元定义"
        reference_note = (
            f" 上传 G 解析 XML={actual_tag or '-'}；当前行扫描 XML={expected_tag or '-'}。定位关系由扫描 XML/devref 与上传标准自动计算，无需人工指定。"
            if expected_tag and actual_tag and actual_tag != expected_tag else ""
        )
        self.scan_summary.setText(
            f"已将 {path.name} 作为 {role_display} 的权威标准图元，{shared_text}。"
            "保存后，只要该图元仍在标准表中，就会参与业务 G 的实例发现、统计与标准校验；设备类还会进入设备导出。" + reference_note
        )
        self.profile_status.setText(
            f"待保存：{role_display} → {devref}。devref、w/h、AlignCenter、pin/连接锚点均以这个上传 G 为准。"
        )
        self._update_action_state()

    def _on_scan_error(self, details: str) -> None:
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        message = str(details).split("\n\n---TRACEBACK---", 1)[0].strip()
        QMessageBox.critical(self, "扫描失败", message or str(details))

    def _on_scan_finished(self) -> None:
        self._scan_worker = None
        self._update_action_state()
        # Keep 100% visible very briefly so completion is perceptible; the bar is
        # already next to the scan button and appears immediately at scan start.
        QTimer.singleShot(450, lambda: self.scan_progress.setVisible(False) if self._scan_worker is None else None)

    def _save_profile(self) -> None:
        selected_name, selected_version, selected_active = self._selected_profile_key()
        selected_profile = self.service.load_profiles().get(selected_name) if selected_name and selected_active else None
        site_name = self.site_name.text().strip()
        profile_name = self.profile_name.text().strip()
        # v2.18.105 no longer persists six special RMU role fields from the UI.
        # Every authoritative definition is a generic discovery-driven standard row.
        lbs = breaker = normal_lbs = normal_breaker = ground = normal_ground = ""
        custom_symbols = self._collect_custom_symbols()
        invalid_custom = [
            entry for entry in custom_symbols
            if not str(entry.get("element_tag", "")).strip() or not str(entry.get("standard_devref", "")).strip()
        ]
        if invalid_custom:
            QMessageBox.warning(self, "图元标准未完成", "服务器图元目录中的标准行必须至少具备“XML 元素”和有效的标准图元 G。请先完成服务器读取后再保存。")
            return
        if not site_name or not profile_name:
            QMessageBox.warning(self, "标准未完成", "适用范围和标准名称不能为空。")
            return
        if not custom_symbols:
            QMessageBox.warning(
                self, "标准未完成",
                "请先读取服务器 element 图元目录，并确保至少解析出 1 个有效服务器标准图元。",
            )
            return

        # The saved standard is built only from the explicitly reviewed server
        # snapshot. Historical business-scan observations/confidence never
        # participate in an authoritative Profile update.
        all_records = self._editor_standard_records()
        selected_devrefs = {
            str(entry.get("standard_devref", "")).strip()
            for entry in custom_symbols
            if str(entry.get("standard_devref", "")).strip()
        }
        managed_standard_files = [
            dict(row) for row in all_records
            if str(row.get("devref", "")).strip() in selected_devrefs
        ]
        sample_files = [
            str(row.get("original_name", "")).strip()
            for row in managed_standard_files
            if str(row.get("original_name", "")).strip()
        ]
        self._symbol_catalog = self._catalog_from_standard_records(managed_standard_files)
        geometry_templates: dict[str, list[dict[str, object]]] = {}

        # These legacy statistical fields remain in the JSON schema only for old
        # profile compatibility. For uploaded authoritative standards they are not
        # evidence and are deliberately reset.
        smart_rmu_count = normal_rmu_count = ignored_rmu_count = 0
        lbs_observations = breaker_observations = 0
        normal_lbs_observations = normal_breaker_observations = 0
        ground_observations = normal_ground_observations = 0
        lbs_confidence = breaker_confidence = 0.0
        normal_lbs_confidence = normal_breaker_confidence = 0.0
        ground_confidence = normal_ground_confidence = 0.0
        lbs_candidates = {}
        breaker_candidates = {}
        normal_lbs_candidates = {}
        normal_breaker_candidates = {}
        ground_candidates = {}
        normal_ground_candidates = {}

        old = self.service.load_profiles().get(profile_name)
        candidate_profile = SiteSmartProfile(
            profile_name=profile_name,
            site_name=site_name,
            smart_lbs_devref=lbs,
            smart_breaker_devref=breaker,
            normal_lbs_devref=normal_lbs,
            normal_breaker_devref=normal_breaker,
            smart_ground_devref=ground,
            normal_ground_devref=normal_ground,
            sample_files=sample_files,
            smart_rmu_count=smart_rmu_count,
            normal_rmu_count=normal_rmu_count,
            ignored_rmu_count=ignored_rmu_count,
            lbs_observations=lbs_observations,
            breaker_observations=breaker_observations,
            normal_lbs_observations=normal_lbs_observations,
            normal_breaker_observations=normal_breaker_observations,
            ground_observations=ground_observations,
            normal_ground_observations=normal_ground_observations,
            lbs_confidence=lbs_confidence,
            breaker_confidence=breaker_confidence,
            normal_lbs_confidence=normal_lbs_confidence,
            normal_breaker_confidence=normal_breaker_confidence,
            ground_confidence=ground_confidence,
            normal_ground_confidence=normal_ground_confidence,
            lbs_candidates=lbs_candidates,
            breaker_candidates=breaker_candidates,
            normal_lbs_candidates=normal_lbs_candidates,
            normal_breaker_candidates=normal_breaker_candidates,
            ground_candidates=ground_candidates,
            normal_ground_candidates=normal_ground_candidates,
            geometry_templates=geometry_templates,
            custom_symbols=custom_symbols,
            symbol_catalog=self._symbol_catalog,
            managed_standard_files=managed_standard_files,
            locked=False,
            discovery_catalog=self._graphic_discovery_catalog,
            discovery_decisions=self._discovery_decisions,
        ).normalized()
        # Every enabled standard row must resolve to exactly one server icon file.
        records_by_devref: dict[str, list[dict[str, object]]] = {}
        for row in candidate_profile.managed_standard_files:
            records_by_devref.setdefault(str(row.get("devref", "")).casefold(), []).append(row)
        role_errors: list[str] = []
        for entry in custom_symbols:
            if not bool(entry.get("enabled", True)):
                continue
            devref = str(entry.get("standard_devref", "")).strip()
            label = str(entry.get("role", "自定义图元")).strip() or "自定义图元"
            rows = records_by_devref.get(devref.casefold(), []) if devref else []
            if len(rows) != 1:
                role_errors.append(f"图元 {label}: 必须且只能绑定 1 个服务器标准图元 G。")
        if role_errors:
            QMessageBox.warning(self, "标准图元绑定无效", "\n".join(role_errors))
            return

        if old is not None and self.service._device_signature(old) != self.service._device_signature(candidate_profile):
            changes = []
            if old.smart_lbs_devref != candidate_profile.smart_lbs_devref:
                changes.append("SMART LBS")
            if old.smart_breaker_devref != candidate_profile.smart_breaker_devref:
                changes.append("SMART Q")
            if old.normal_lbs_devref != candidate_profile.normal_lbs_devref:
                changes.append("NORMAL LBS")
            if old.normal_breaker_devref != candidate_profile.normal_breaker_devref:
                changes.append("NORMAL Q")
            if old.smart_ground_devref != candidate_profile.smart_ground_devref:
                changes.append("SMART 接地刀闸")
            if old.normal_ground_devref != candidate_profile.normal_ground_devref:
                changes.append("NORMAL 接地刀闸")
            if old.geometry_templates != candidate_profile.geometry_templates:
                changes.append("图元几何（大小/端口）")
            if old.custom_symbols != candidate_profile.custom_symbols:
                changes.append("自定义图元")
            if old.symbol_catalog != candidate_profile.symbol_catalog:
                changes.append("图元属性目录")
            if QMessageBox.question(
                self,
                "更新图元标准",
                f"当前标准是 {profile_name}。\n"
                f"检测到标准变化：{', '.join(changes) or '图元标准'}。\n\n"
                "确认后会把已读取的服务器快照写入当前标准；旧本地快照仅用于安全回退。\n"
                "服务器是唯一标准来源；本次更新不会修改服务器，也不会自动切换全局执行选择。\n\n继续吗？",
            ) != QMessageBox.StandardButton.Yes:
                return

        try:
            # Legacy profiles may still carry the old lock flag.  It is no longer
            # a public control, so clear it before applying the explicitly
            # confirmed server standard.
            if old is not None and old.locked:
                self.service.set_locked(profile_name, False)
            if self._rescan_draft_mode:
                profile = self.service.save_as_next_version(candidate_profile)
            else:
                profile = self.service.upsert(candidate_profile)
        except ValueError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        # There is only one public current standard now.  Keep the legacy
        # profile/version storage internally, but always point downstream
        # processing at the standard the user just confirmed.
        try:
            self.service.set_global_profile_version(
                profile.profile_name, profile.profile_version, validate=False
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "当前标准已保存，但未切换执行标准",
                f"服务器标准已写入本地，但无法更新当前执行指针：{exc}",
            )
        self.user_settings.set_value("site_profile/last_profile_name", profile.profile_name)
        saved_from_fresh_rescan = bool(self._rescan_draft_mode)
        self._pending_standard_file_records = []
        self._reset_fresh_rescan_state()
        self._reload_profiles(profile.profile_name, profile.profile_version)
        self.activeProfileChanged.emit(profile.profile_name)
        QMessageBox.information(
            self, "标准已保存",
            f"已按服务器标准更新当前标准：{profile.profile_name}（适用范围：{profile.site_name}）。\n"
            f"服务器版本标记：{profile.server_standard_label} UTC。"
            + ("\n本次更新已作为后续处理使用的当前标准。" if not saved_from_fresh_rescan else ""),
        )

    def _show_version_repository_details(self) -> None:
        name, version, active = self._selected_profile_key()
        if not name or version is None:
            QMessageBox.information(self, "请选择版本", "请先在“标准版本”下拉框中选择一个已保存版本。")
            return
        try:
            details = self.service.version_repository_details(name, version)
            integrity = self.service.verify_version_repository(name, version)
        except ValueError as exc:
            QMessageBox.warning(self, "版本库读取失败", str(exc))
            return
        status = "完整" if integrity.ok else "完整性异常"
        fingerprint = str(details.get("repository_fingerprint", ""))
        QMessageBox.information(
            self,
            f"{name} V{version} · 图元版本库",
            f"状态：{'ACTIVE' if active else 'ARCHIVED'} / {status}\n"
            f"冻结图元：{details.get('entry_count', 0)} 个（服务器来源 {details.get('server_backed', 0)}，其他历史来源 {details.get('manual', 0)}）\n"
            f"已验证：{integrity.verified}/{integrity.total}\n"
            f"历史中发生过内容修订的相对路径：{details.get('paths_with_history', 0)}\n"
            f"版本库指纹：{fingerprint or '-'}\n\n"
            f"Manifest：{details.get('manifest_path', '-')}\n"
            f"本地对象库：{details.get('repository_root', '-')}\n\n"
            "历史版本完全依赖本地冻结对象；服务器当前同名文件不会覆盖或替代该版本。",
        )

    def _verify_selected_version_repository(self) -> None:
        name, version, _active = self._selected_profile_key()
        if not name or version is None:
            QMessageBox.information(self, "请选择版本", "请先选择需要验证的已保存版本。")
            return
        try:
            result = self.service.verify_version_repository(name, version)
        except ValueError as exc:
            QMessageBox.warning(self, "验证失败", str(exc))
            return
        if result.ok:
            QMessageBox.information(
                self,
                "版本完整性验证通过",
                f"{name} V{version}：{result.verified}/{result.total} 个冻结图元均存在，SHA256 与 w×h / AlignCenter / Pins 等解析属性一致。\n\n"
                "即使服务器上的旧图元已被覆盖或删除，该版本仍可离线恢复和导出。",
            )
            return
        issues = []
        issues.extend(f"缺失：{item}" for item in result.missing[:8])
        issues.extend(f"SHA256 不一致：{item}" for item in result.hash_mismatch[:8])
        issues.extend(f"解析属性不一致：{item}" for item in result.metadata_mismatch[:8])
        QMessageBox.warning(
            self,
            "版本完整性异常",
            f"{name} V{version} 仅验证通过 {result.verified}/{result.total}。\n" + "\n".join(issues[:16]) +
            "\n\n不会使用服务器当前同名文件自动补位；请从可信备份恢复对应 SHA256 的历史对象。",
        )

    def _export_selected_version_repository(self, *, zip_output: bool) -> None:
        name, version, _active = self._selected_profile_key()
        if not name or version is None:
            QMessageBox.information(self, "请选择版本", "请先选择需要导出的已保存版本。")
            return
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name).strip("._") or "standard"
        if zip_output:
            default_path = str(default_workspace() / f"{safe_name}_V{version}_element.zip")
            selected, _filter = QFileDialog.getSaveFileName(self, "导出完整 element ZIP", default_path, "ZIP (*.zip)")
            if not selected:
                return
            destination = Path(selected)
        else:
            selected = QFileDialog.getExistingDirectory(self, "选择空目录用于导出该版本 element", str(default_workspace()))
            if not selected:
                return
            destination = Path(selected)
        try:
            output = self.service.export_version_element(name, version, destination, zip_output=zip_output)
        except ValueError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(
            self,
            "版本图元库导出完成",
            f"已从本地冻结对象恢复 {name} V{version} 的完整图元树：\n{output}\n\n"
            "目录结构按保存时相对 /home/up8000/data/graph/element 的路径重建；导出过程不访问也不修改服务器。",
        )
        target = output.parent if output.is_file() else output
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _delete_selected_history_version(self) -> None:
        name, version, active = self._selected_profile_key()
        if not name or version is None:
            QMessageBox.information(self, "请选择历史版本", "请先选择需要删除的 ARCHIVED 历史版本。")
            return
        if active:
            QMessageBox.information(
                self,
                "不能删除 ACTIVE",
                "当前 ACTIVE 版本不能直接删除。若确实不再需要整个标准，请使用“删除整个标准（全部版本）”。",
            )
            return
        global_name, global_version = self.service.get_global_profile_selection(auto_initialize=False)
        if name == global_name and version == global_version:
            QMessageBox.information(
                self,
                "不能删除 GLOBAL",
                "当前版本正在作为全局执行标准。请先将另一个版本设为全局版本，再删除该历史版本。",
            )
            return
        if QMessageBox.question(
            self,
            "删除历史版本",
            f"确认删除 {name} / V{version} 这个 ARCHIVED 历史版本？\n\n"
            "只删除这个版本的配置快照和可达 Manifest；ACTIVE、GLOBAL 及其他历史版本全部保留。\n"
            "SHA256 对象不会自动垃圾回收，避免误删其他版本共享的图元文件。此操作不会访问或修改服务器。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        def finish(current: SiteSmartProfile) -> None:
            self._reload_profiles(name, current.profile_version)
            QMessageBox.information(
                self,
                "历史版本已删除",
                f"{name} / V{version} 已从可用版本历史中删除。其他版本及其图元配置没有变化。\n"
                "本地图元对象库不会自动清理未引用 SHA256 对象；后续如需释放空间，可单独提供安全的未引用对象清理功能。",
            )

        self._start_profile_operation(
            f"正在删除 {name} / V{version} 历史版本，请稍候……",
            lambda: self.service.delete_archived_version(name, version),
            finish,
        )

    def _delete_profile(self) -> None:
        name, version, active = self._selected_profile_key()
        if not name:
            QMessageBox.information(self, "请选择标准", "请先选择需要删除的已保存图元标准。")
            return
        if not active:
            QMessageBox.information(
                self,
                "请选择删除方式",
                "当前选中的是 ARCHIVED 历史版本。若只删除这一版，请使用“删除选中历史版本”；"
                "若要删除整个 Profile，请选择其 ACTIVE 版本后使用“删除整个标准（全部版本）”。",
            )
            return
        current = self.service.load_profiles().get(name)
        if current is None:
            return
        if QMessageBox.question(
            self,
            "删除整个标准",
            f"确认删除图元标准“{name}”及其全部历史版本（当前 ACTIVE V{current.profile_version}）？",
        ) != QMessageBox.StandardButton.Yes:
            return
        def finish(_result: object) -> None:
            self._reload_profiles()
            self.activeProfileChanged.emit("")
            QMessageBox.information(self, "标准已删除", f"图元标准“{name}”及其全部历史版本已删除。")

        self._start_profile_operation(
            f"正在删除标准 {name} 及其全部历史版本，请稍候……",
            lambda: self.service.remove(name),
            finish,
        )

    def _check_profile(self) -> None:
        self._start_profile_run(correct=False)

    def _correct_profile(self) -> None:
        if QMessageBox.question(
            self,
            "确认纠正图元标准问题",
            "将按当前全局图元标准纠正已定义设备图元的变体/devref、尺寸和可可靠计算的设备几何。\n"
            "本操作不会删除、重画或正交化 ConnectLine/FeedLine/Bus，也不会改变拓扑引用。\n\n"
            "源 G 文件不会覆盖；纠正后的 G 会写入本次 workspace 运行目录的 corrected 文件夹，并自动执行一次复查。\n"
            "未纳入当前标准、连接关系不明确、偏移过大或无法可靠拟合的对象不会猜测修改。\n\n继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._start_profile_run(correct=True)

    def _start_profile_run(self, *, correct: bool = False) -> None:
        name, version = self.service.get_global_profile_selection()
        profile = self.service.get_profile_version(name, version) if name and version is not None else None
        if profile is None:
            QMessageBox.warning(self, "尚未设置全局标准", "请先在“标准版本”下拉框中选择已保存版本，并点击“设为全局版本”。")
            return
        ready, issues = self.service.validate_authoritative_standard(profile)
        if not ready:
            QMessageBox.warning(
                self,
                "标准图元库未就绪",
                "执行服务器图元更新检查前，至少要保存 1 个有效的权威标准图元角色。只会检查已配置的角色。\n\n" + "\n".join(issues[:8]),
            )
            return
        if not validate_input_source(self, self.source, display_name="服务器图元更新检查输入", log=self.task.append_log):
            return
        self.source.persist_current()
        self._last_report_path = None
        self.open_report_button.setEnabled(False)
        self._last_run_mode = "CORRECT" if correct else "CHECK"
        if correct:
            self.result_summary.setText(f"正在按全局 V{profile.profile_version} 标准生成纠正副本……源 G 文件不会覆盖。")
        else:
            self.result_summary.setText("正在检查图元标准……源 G 文件不会修改。")
        run_dir = begin_managed_run(self.output_path, "symbol-standard", "correct" if correct else "check")
        settings = SmartProfileProcessingSettings(
            source_path=self.source.path(),
            input_mode=self.source.mode(),
            output_dir=run_dir,
            profile=profile,
            require_authoritative_standard=True,
        )
        processor = process_smart_profile_correction if correct else process_smart_profile_consistency
        self.task.start(lambda log, progress: processor(settings, log, progress), run_dir)

    def _refresh_catalog_action_state(self) -> None:
        """Update only controls used by the public catalog manager.

        This deliberately performs zero Profile repository I/O.  The old generic
        action-state updater reads global/version repository state
        and may hydrate historical local snapshots; invoking it before/after every
        server sync made a background SSH operation *look* as if it froze the GUI.
        """
        busy_scan = self._scan_worker is not None
        busy_server = self._server_sync_worker is not None
        busy_registry = self._classification_registry_worker is not None
        busy_admin = self._admin_lease_worker is not None
        busy_marker = self._classification_marker_save_worker is not None
        busy = bool(busy_scan or busy_server or busy_registry or busy_admin or busy_marker or self._task_busy)
        if hasattr(self, "server_sync_button"):
            enabled = bool(self.server_standard_enabled.isChecked())
            self.server_sync_button.setEnabled(enabled and not busy)
            self.server_symbol_root.setEnabled(enabled and not busy_server)
        if hasattr(self, "server_connection_button"):
            self.server_connection_button.setEnabled(not busy_server)
        for name in ("save_classification_button", "import_classification_button", "export_classification_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(not busy_registry and not busy_marker)
        if hasattr(self, "central_sync_button"):
            self.central_sync_button.setEnabled(not busy_registry and not busy_marker)
        if hasattr(self, "central_publish_button"):
            self.central_publish_button.setEnabled(
                bool(self._is_admin_mode and not busy_registry and not busy_admin and not busy_marker)
            )

    def _update_action_state(self) -> None:
        # Normal Server Symbol Sync Management never needs the retired standard-
        # version repository.  Keep all public actions responsive and local-only.
        if not self._legacy_profile_state_loaded:
            self._refresh_catalog_action_state()
            return
        name, version, active = self._selected_profile_key()
        profile = self.service.load_profiles().get(name) if name else None
        busy_scan = self._scan_worker is not None
        busy_server = self._server_sync_worker is not None
        busy_profile = self._profile_operation_worker is not None
        busy_registry = self._classification_registry_worker is not None
        busy_admin = self._admin_lease_worker is not None
        busy = busy_scan or busy_server or busy_profile or busy_registry or busy_admin or self._task_busy
        global_name, global_version = self.service.get_global_profile_selection()
        global_profile = self.service.get_profile_version(global_name, global_version) if global_name and global_version is not None else None
        ready = bool(global_profile and global_profile.authoritative_ready)
        self.check_button.setEnabled(ready and not busy)
        self.correct_button.setEnabled(ready and not busy)
        if hasattr(self, "set_global_button"):
            selected_profile = self.service.get_profile_version(name, version) if name and version is not None else None
            selected_ready = bool(selected_profile and selected_profile.authoritative_ready)
            already_global = bool(name == global_name and version == global_version)
            self.set_global_button.setEnabled(bool(self._is_admin_mode and selected_profile and selected_ready and not already_global and not busy))
            self.set_global_button.setText("当前全局版本" if already_global else "设为全局版本")
        # The server element tree is the only standard source. Local upload and
        # discovery actions remain as hidden compatibility objects only.
        self.scan_action.setEnabled(False)
        self.scan_action.setText("标准图元仅从服务器读取")
        if hasattr(self, "upload_standard_button"):
            self.upload_standard_button.setEnabled(False)
            self.upload_standard_button.setText("标准图元仅从服务器读取")
        # Legacy lock flags are ignored by the single-current-standard workflow.
        locked = False
        rescan_working = bool(self._rescan_prepare_mode or self._rescan_draft_mode)
        if hasattr(self, "discovery_scan_button"):
            # Locked saved standards stay immutable.  The only exception is an
            # explicitly armed fresh-rescan workflow, whose input/output live in an
            # isolated local DRAFT and therefore cannot modify the locked snapshot.
            allow_discovery = (not name) or bool(active and profile is not None and not locked)
            allow_discovery = bool(rescan_working or allow_discovery)
            self.discovery_scan_button.setEnabled(False)
            self._set_discovery_input_visible(rescan_working or not locked)
        self.discovery_scan_button.setText(
                f"重新扫描生成 V{self._rescan_draft_target_version or '?'} 草稿"
                if self._rescan_prepare_mode else
                ("重新扫描 / 更新当前新版本草稿" if self._rescan_draft_mode else "分析业务 G 使用情况")
            )
        can_edit = self._rescan_draft_mode or (
            not self._rescan_prepare_mode
            and ((not name) or bool(active and profile is not None and not locked))
        )
        self.save_button.setEnabled(self._is_admin_mode and can_edit and not busy)
        self.save_button.setText("手动更新当前标准")
        self.add_custom_button.setEnabled(False)
        if hasattr(self, "confirm_server_button"):
            self.confirm_server_button.setEnabled(False)
        selected_standard_row = self.standard_table.currentRow()
        self.delete_custom_button.setEnabled(False)
        if hasattr(self, "share_pair_checkbox"):
            self.share_pair_checkbox.setEnabled(
                self._is_admin_mode and can_edit and not busy and 0 <= selected_standard_row < len(self._standard_specs)
            )
        if hasattr(self, "server_sync_button"):
            server_enabled = bool(self.server_standard_enabled.isChecked())
            self.server_sync_button.setEnabled(server_enabled and not busy)
            if hasattr(self, "server_apply_button"):
                matched_records = self._last_server_sync_payload.get("matched_records", {})
                has_server_snapshot = isinstance(matched_records, dict) and bool(matched_records)
                self.server_apply_button.setEnabled(
                    bool(self._is_admin_mode and server_enabled and has_server_snapshot and not locked and not busy)
                )
            self.server_symbol_root.setEnabled(server_enabled and not busy_server)
            if hasattr(self, "server_connection_button"):
                self.server_connection_button.setEnabled(not busy_server)
            self.server_cache_button.setEnabled(not busy_server)
            if hasattr(self, "server_new_version_button"):
                changed_names = self._last_server_sync_payload.get("profile_changed_names", [])
                matched_records = self._last_server_sync_payload.get("matched_records", {})
                changed_keys = {Path(str(item)).name.casefold() for item in changed_names if Path(str(item)).name} if isinstance(changed_names, list) else set()
                has_replacements = bool(
                    locked
                    and changed_keys
                    and isinstance(matched_records, dict)
                    and any(Path(str(name)).name.casefold() in changed_keys and isinstance(record, dict) for name, record in matched_records.items())
                )
                self.server_new_version_button.setVisible(has_replacements)
                self.server_new_version_button.setEnabled(self._is_admin_mode and has_replacements and not busy)
        if hasattr(self, "rescan_new_version_button"):
            can_start_fresh = bool(self._is_admin_mode and name and profile and active and not busy and not self._rescan_draft_mode)
            self.rescan_new_version_button.setEnabled(can_start_fresh)
            self.rescan_new_version_button.setText(
                f"开始重新扫描 V{self._rescan_draft_target_version or '?'} 草稿"
                if self._rescan_prepare_mode else "全量重新扫描 → 新版本草稿"
            )
            self.cancel_rescan_draft_button.setVisible(bool(self._rescan_prepare_mode or self._rescan_draft_mode))
            self.cancel_rescan_draft_button.setEnabled(not busy)
        if hasattr(self, "lock_standard_button"):
            self.lock_standard_button.setEnabled(bool(self._is_admin_mode and name and profile and active and not busy and not rescan_working))
            self.lock_standard_button.setText("解锁当前版本" if locked else "锁定当前版本")
        current_profile = self.service.load_profiles().get(name) if name else None
        current_locked = bool(current_profile.locked) if current_profile is not None else False
        has_saved_version = bool(name and version is not None and self.service.get_profile_version(name, version) is not None)
        if hasattr(self, "version_details_action"):
            self.version_details_action.setEnabled(has_saved_version and not busy)
            self.verify_version_action.setEnabled(has_saved_version and not busy)
            self.export_version_action.setEnabled(has_saved_version and not busy)
            self.export_version_zip_action.setEnabled(has_saved_version and not busy)
        self.restore_action.setEnabled(bool(self._is_admin_mode and name and profile and not active and not busy and not current_locked))
        self.delete_history_action.setEnabled(bool(self._is_admin_mode and has_saved_version and not busy))
        self.delete_action.setEnabled(bool(self._is_admin_mode and name and profile and active and not busy and not locked))
        self.new_action.setEnabled(self._is_admin_mode and not busy)
        if hasattr(self, "save_classification_button"):
            self.save_classification_button.setEnabled(not busy)
        if hasattr(self, "import_classification_button"):
            self.import_classification_button.setEnabled(not busy)
        if hasattr(self, "central_sync_button"):
            self.central_sync_button.setEnabled(not busy)
        if hasattr(self, "central_publish_button"):
            self.central_publish_button.setEnabled(self._is_admin_mode and not busy)
        self._refresh_standard_table_overview()
        self._refresh_access_controls()

    def _task_busy_changed(self, busy: bool) -> None:
        self._task_busy = bool(busy)
        self._update_action_state()

    def _on_processing_result(self, result) -> None:
        self._last_report_path = None
        for path in getattr(result, "output_files", []):
            candidate = Path(path)
            if candidate.suffix.lower() == ".html" and "symbol-standard-check" in candidate.name.lower():
                self._last_report_path = candidate
                break
        self.open_report_button.setEnabled(bool(self._last_report_path and self._last_report_path.exists()))
        stats = getattr(result, "statistics", {}) or {}
        mode = str(stats.get("Mode", getattr(self, "_last_run_mode", "CHECK")) or "CHECK").upper()
        bad = int(stats.get("Nonstandard Symbols", 0) or 0)
        if stats:
            unmanaged = int(stats.get("Unmanaged Symbols", 0) or 0)
            if mode == "CORRECT":
                corrected = int(stats.get("Corrected Elements", 0) or 0)
                changed_files = int(stats.get("Corrected Files", 0) or 0)
                geometry = int(stats.get("Geometry Corrections", 0) or 0)
                text = (
                    f"纠正完成：{changed_files} 个文件发生修改，共处理 {corrected} 个标准差异，"
                    f"其中设备图元几何纠正 {geometry} 个；线路与拓扑保持不变，自动复查后剩余 {bad} 个不符合项。"
                )
                if unmanaged:
                    text += f" 另有 {unmanaged} 种未纳入当前标准的图元未自动处理；业务 G 不会被用于学习或补全标准。"
                text += " 源 G 未覆盖；纠正副本位于本次结果目录的 corrected 文件夹。"
            else:
                if bad:
                    text = f"检查完成：发现 {bad} 个不符合当前标准的问题。"
                else:
                    text = "检查完成：已配置的图元标准全部通过。"
                if unmanaged:
                    text += f" 另发现 {unmanaged} 种尚未纳入当前标准的图元（不计为错误）；如需纳入，请在上方设备角色中手动上传权威图元 G。"
                text += " 源 G 未修改；详细原因请查看检查报告。"
            self.result_summary.setText(text)
        if mode == "CORRECT":
            if bad > 0:
                QMessageBox.warning(
                    self,
                    "图元标准纠正完成（仍有待处理项）",
                    f"已生成纠正副本，但自动复查后仍有 {bad} 个不符合项。\n\n"
                    "这些通常属于未纳入标准、连接关系不明确或无法安全拟合的情况，程序不会猜测修改。"
                    "请点击“查看检查报告”确认。源 G 文件未覆盖。",
                )
            else:
                QMessageBox.information(
                    self,
                    "图元标准纠正完成",
                    "已按当前 ACTIVE 标准生成纠正副本并完成自动复查，未发现剩余标准差异。\n"
                    "源 G 文件未覆盖；请在本次结果目录的 corrected 文件夹中查看输出。",
                )
        elif bad > 0:
            QMessageBox.warning(
                self,
                "图元标准不一致",
                f"检测到 {bad} 个图元/几何与当前 ACTIVE 标准不一致。\n\n"
                "检查模式不会修改 G。可先查看报告；如属于标准中已定义图元的变体/devref或设备图元几何问题，"
                "可使用“生成标准纠正副本”生成安全副本。连接线和其他拓扑对象不在本模块的处理范围内。\n"
                "如果是同一设备图元的旧版本 → 新版本升级，请到“基础处理 → 同类图元版本升级”处理。",
            )
        else:
            QMessageBox.information(
                self,
                "服务器图元更新检查完成",
                "未发现图元类型/变体、devref 或设备图元几何与当前 ACTIVE 标准不一致；源 G 文件未修改。",
            )

    def _open_report(self) -> None:
        path = self._last_report_path
        if path is None or not path.exists():
            QMessageBox.information(self, "报告不存在", "当前还没有检查报告，请先点击“检查图元标准”。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def save_state(self) -> None:
        # Public catalog-manager instances deliberately do not construct the retired
        # business-G source/task widgets.  Local classification edits are persisted
        # independently by their debounce worker.
        if hasattr(self, "source"):
            self.source.persist_all_text()
        if hasattr(self, "discovery_source"):
            self.discovery_source.persist_all_text()
        if hasattr(self, "output_path"):
            self.output_path.persist_current_text()
