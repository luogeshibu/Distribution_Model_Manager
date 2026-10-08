from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from g_file_studio import __version__
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.i18n import LANG_EN, LANG_ZH, LanguageManager
from g_file_studio.ui.theme import build_app_style
from g_file_studio.ui.widgets.wheel_safe_combo_box import WheelSafeComboBox


class MainWindow(QMainWindow):
    PAGE_COUNT = 15
    HELP_PAGE_INDEX = 14

    def __init__(
        self,
        user_settings: UserSettingsService,
    ) -> None:
        super().__init__()
        self.user_settings = user_settings
        self.language_manager = LanguageManager(user_settings, self)
        # v2.18.200 startup contract:
        # - construct and paint the lightweight window shell first;
        # - create ONLY the remembered landing page during startup;
        # - every other business page is true lazy-load and is constructed only when
        #   the operator opens it; this prevents hidden modules from freezing the GUI;
        # - each page restores only its own LOCAL AppData cache when it is opened;
        # - never contact SSH, Oracle or the central configuration repository unless
        #   the operator explicitly invokes the corresponding action.
        self._legacy_paths_cleared = False
        self.pages: list[QWidget | None] = [None] * self.PAGE_COUNT
        self.page_hosts: list[QWidget] = []

        self.setWindowTitle("G File Studio · 吉达现场")
        self.resize(1280, 860)
        self.setMinimumSize(1040, 720)

        central = QWidget()
        central.setObjectName("contentRoot")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentRoot")
        for index in range(self.PAGE_COUNT):
            host = QWidget()
            host.setObjectName(f"lazyPageHost{index}")
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            loading = QLabel("正在载入模块…")
            loading.setObjectName("mutedText")
            loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(loading, 1)
            self.page_hosts.append(host)
            self.stack.addWidget(host)

        self.config_access_button.clicked.connect(self._show_global_admin_access)
        self._update_global_admin_access({"mode": "ordinary", "button_text": "配置权限：普通模式"})
        self.nav.currentRowChanged.connect(self._change_page)

        root.addWidget(sidebar)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(build_app_style())

        from PySide6.QtWidgets import QApplication
        qt_app = QApplication.instance()
        if qt_app is not None:
            qt_app.installEventFilter(self.language_manager)
        self.language_manager.languageChanged.connect(self._apply_language)
        self.statusBar().showMessage(
            "NARI 国际业务部 · 吉达现场 · G 文件处理工具已就绪。"
            "启动阶段只读取本机轻量设置；远程连接与中央配置仅在手动操作时访问。"
        )
        self._apply_language(self.language_manager.language)
        self._install_help_shortcut()

        # MainWindow construction stops at the lightweight shell.  After the native
        # window gets its first paint, only the remembered landing page is created.
        # Hidden pages are never pre-created in the background: constructing a heavy
        # hidden page on the GUI thread can still starve Windows painting and produce
        # an all-white / "Not Responding" window even though no network I/O occurs.
        self._startup_target_page = self._resolved_last_business_page_index()
        self._startup_pages_initialized = False
        self._startup_initialization_scheduled = False
        self._startup_loading = True
        # True lazy loading: startup owns exactly one page construction.  All other
        # modules are created by _select_page() on first use.
        self._startup_page_order = [self._startup_target_page]
        self._startup_page_cursor = 0

        self.nav.setCurrentRow(-1)
        self.connection_button.setChecked(False)
        self.help_button.setChecked(False)
        self.stack.setCurrentIndex(0)

        first_layout = self.page_hosts[0].layout()
        if first_layout is not None and first_layout.count():
            first_widget = first_layout.itemAt(0).widget()
            if isinstance(first_widget, QLabel):
                first_widget.setText("正在加载本地页面…")
        self.statusBar().showMessage(
            "正在打开本地页面；其他模块将在首次进入时按需加载，不访问 SSH、Oracle 或中央配置。"
        )


    def _resolved_last_business_page_index(self) -> int:
        """Resolve the locally remembered landing page without any remote access."""
        page_id = self.user_settings.get_value(self.LAST_BUSINESS_PAGE_KEY, "").strip()
        return next(
            (index for index, stable_id in self.BUSINESS_PAGE_IDS.items() if stable_id == page_id),
            3,
        )

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        """Render the native shell first, then create only the remembered page."""
        super().showEvent(event)
        if self._startup_pages_initialized or self._startup_initialization_scheduled:
            return
        self._startup_initialization_scheduled = True
        # Give Windows one full native paint cycle before the first business page
        # is constructed.  A short 150 ms delay is imperceptible to the operator but
        # prevents a large QWidget tree from starving the very first WM_PAINT.
        QTimer.singleShot(150, self._load_next_startup_page)

    def _load_next_startup_page(self) -> None:
        """Create the remembered landing page after the native shell has painted.

        Qt widgets must be constructed on the GUI thread.  v2.18.200 deliberately
        does not preload hidden modules: they are constructed only when selected.
        """
        if self._startup_page_cursor >= len(self._startup_page_order):
            self._finish_startup_page_loading()
            return

        page_index = self._startup_page_order[self._startup_page_cursor]
        self.statusBar().showMessage(
            "正在载入当前模块的本地状态；不会访问中央服务器"
        )

        # Startup page construction is read-only for persistent local settings.
        self.user_settings.set_writes_enabled(False)
        try:
            try:
                page = self._ensure_page(page_index)
            except Exception as exc:
                host = self.page_hosts[page_index]
                layout = host.layout()
                if layout is not None:
                    while layout.count():
                        item = layout.takeAt(0)
                        widget = item.widget()
                        if widget is not None:
                            widget.deleteLater()
                    label = QLabel(
                        f"模块加载失败（页面 {page_index}）\n\n{type(exc).__name__}: {exc}"
                    )
                    label.setObjectName("mutedText")
                    label.setWordWrap(True)
                    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    layout.addWidget(label, 1)
                page = None
        finally:
            self.user_settings.set_writes_enabled(True)

        # Make the remembered landing page usable as soon as it exists. Remaining
        # pages continue loading automatically in the background of the event loop.
        if page_index == self._startup_target_page and page is not None:
            self._select_page(page_index)

        self._startup_page_cursor += 1
        QTimer.singleShot(0, self._load_next_startup_page)

    def _finish_startup_page_loading(self) -> None:
        self._startup_pages_initialized = True
        self._startup_loading = False

        # If the target failed to load, fall back to the first available business page.
        if self.pages[self._startup_target_page] is None:
            fallback = next(
                (index for index in self.BUSINESS_PAGE_IDS if self.pages[index] is not None),
                0,
            )
            self._select_page(fallback)

        # Server Symbol Sync Management restores its LOCAL AppData cache only after
        # the page has painted; JSON loading runs in a worker and table rows are
        # hydrated in small batches. No network access is part of startup.

        self.statusBar().showMessage(
            "当前模块已就绪；其他模块首次进入时加载本机缓存。中央配置仅在手工同步/发布时访问。"
        )

    def _clear_legacy_managed_output_paths(self) -> None:
        """清除旧版本保存的 workspace 托管输出路径。

        这些输出目录由程序按模块和运行批次统一生成，历史 run 目录可能被
        定期清理，因此不属于需要用户重新选择的路径。必须在各页面 PathRow
        构造前清理，避免它们把已经删除的旧 run 目录当成用户路径失效并弹窗。
        """
        managed_keys = (
            "small_elements/output_directory",
            "recent_paths/small_elements/output_directory",
            "id_rules/output_directory",
            "recent_paths/id_rules/output_directory",
            "site_profile/output_directory",
            "recent_paths/site_profile/output_directory",
            "symbol_inventory/output_directory",
            "recent_paths/symbol_inventory/output_directory",
            "rmu/output_directory",
            "recent_paths/rmu/output_directory",
            "poke/output_directory",
            "recent_paths/poke/output_directory",
            "basic/output_directory",
            "recent_paths/basic/output_directory",
            "merge/output_directory",
            "recent_paths/merge/output_directory",
            "margin/output_directory",
            "recent_paths/margin/output_directory",
            "frame/output_directory",
            "recent_paths/frame/output_directory",
            "jeddah_batch/output_directory",
            "recent_paths/jeddah_batch/output_directory",
            "transformer_fuse/output_directory",
            "recent_paths/transformer_fuse/output_directory",
            "rmu_efi/output_directory",
            "recent_paths/rmu_efi/output_directory",
            "orthogonalize/output_directory",
            "recent_paths/orthogonalize/output_directory",
        )
        # These are disposable workspace output locations, not persistent user
        # configuration. Remove legacy values with a single AppData INI write.
        self.user_settings.clear_many(managed_keys)

    NAV_PAGE_ROLE = int(Qt.ItemDataRole.UserRole) + 20
    NAV_SECTION_ROLE = int(Qt.ItemDataRole.UserRole) + 21
    LAST_BUSINESS_PAGE_KEY = "navigation/last_business_page"
    BUSINESS_PAGE_IDS = {
        1: "small_elements",
        2: "id_rules",
        3: "symbol_standard",
        4: "rmu",
        5: "poke",
        6: "basic",
        7: "merge",
        8: "margin",
        9: "frame",
        10: "jeddah_batch",
        11: "orthogonalize",
        12: "transformer_fuse",
        13: "rmu_efi",
    }

    def _create_page(self, page_index: int) -> QWidget:
        # Compatibility marker: SiteProfilePage(self.user_settings, defer_catalog_restore=False)
        """Import and construct one page.

        During normal startup this is called automatically for every page after the
        shell is visible. Imports stay local so MainWindow construction itself remains
        lightweight. No remote connection is opened here.
        """
        if page_index == 0:
            from g_file_studio.ui.pages.database_page import DatabasePage
            return DatabasePage(self.user_settings)
        if page_index == 1:
            from g_file_studio.ui.pages.small_element_page import SmallElementPage
            return SmallElementPage(self.user_settings)
        if page_index == 2:
            from g_file_studio.ui.pages.id_page import IdPage
            return IdPage(self.user_settings)
        if page_index == 3:
            from g_file_studio.ui.pages.site_profile_page import SiteProfilePage
            # Construct the page first and let the native window paint before the
            # cached 200-row symbol inventory is rendered.  The deferred restore is
            # still AppData-only and never opens SSH/Oracle/central configuration.
            return SiteProfilePage(self.user_settings, defer_catalog_restore=True)
        if page_index == 4:
            from g_file_studio.ui.pages.rmu_page import RmuPage
            return RmuPage(self.user_settings)
        if page_index == 5:
            from g_file_studio.ui.pages.poke_page import PokePage
            return PokePage(self.user_settings)
        if page_index == 6:
            from g_file_studio.ui.pages.basic_page import BasicPage
            return BasicPage(self.user_settings)
        if page_index == 7:
            from g_file_studio.ui.pages.merge_page import MergePage
            return MergePage(self.user_settings)
        if page_index == 8:
            from g_file_studio.ui.pages.margin_page import MarginPage
            return MarginPage(self.user_settings)
        if page_index == 9:
            from g_file_studio.ui.pages.frame_page import FramePage
            return FramePage(self.user_settings)
        if page_index == 10:
            from g_file_studio.ui.pages.jeddah_batch_page import JeddahBatchPage
            return JeddahBatchPage(self.user_settings)
        if page_index == 11:
            from g_file_studio.ui.pages.orthogonalize_page import OrthogonalizePage
            return OrthogonalizePage(self.user_settings)
        if page_index == 12:
            from g_file_studio.ui.pages.transformer_fuse_page import TransformerFusePage
            return TransformerFusePage(self.user_settings)
        if page_index == 13:
            from g_file_studio.ui.pages.rmu_efi_page import RmuEfiPage
            return RmuEfiPage(self.user_settings)
        if page_index == self.HELP_PAGE_INDEX:
            from g_file_studio.ui.pages.help_page import HelpPage
            return HelpPage()
        raise IndexError(f"Unknown page index: {page_index}")

    def _ensure_page(self, page_index: int) -> QWidget:
        page = self.pages[page_index]
        if page is not None:
            return page
        if not self._legacy_paths_cleared and page_index not in {0, self.HELP_PAGE_INDEX}:
            self._clear_legacy_managed_output_paths()
            self._legacy_paths_cleared = True
        host = self.page_hosts[page_index]
        layout = host.layout()

        # v2.18.203: keep the already-painted lazy placeholder alive while the
        # requested page is being constructed.  Older builds removed the placeholder
        # first, leaving an empty native child window for one paint cycle; on Windows
        # this looked like a white/blank rectangle flashing before the real page (and
        # was especially noticeable just before the server-symbol table appeared).
        # Construct first, then swap the widgets atomically on the GUI thread.
        page = self._create_page(page_index)
        self.pages[page_index] = page
        if layout is not None:
            old_widgets: list[QWidget] = []
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    old_widgets.append(widget)
            layout.addWidget(page)
            for widget in old_widgets:
                widget.hide()
                widget.deleteLater()
        self._wire_page(page_index, page)
        if page_index == 6:
            basic_title = page.findChild(QLabel, "pageTitle")
            if basic_title is not None:
                basic_title.setText("通用基础处理")
        # Chinese is the canonical source language.  Walking every child widget and
        # installing table-model translation hooks while a heavy page is being
        # constructed is pure overhead in Chinese mode and used to noticeably delay
        # first paint.  If the operator later switches to English, _apply_language()
        # translates all already-created pages at that moment and captures the same
        # source strings safely.
        if self.language_manager.is_english:
            self.language_manager.translate_widget_tree(page)
        return page

    def _wire_page(self, page_index: int, page: QWidget) -> None:
        """Connect shared-state signals only among pages that already exist."""
        from g_file_studio.ui.widgets.remote_g_source import RemoteGSourceWidget

        if page_index == 0:
            self.database_page = page
        elif page_index == 3:
            self.site_profile_page = page
            self.site_profile_page.adminAccessChanged.connect(self._update_global_admin_access)
            self.site_profile_page.orthogonalizeRequested.connect(lambda: self._select_page(11))
            self.site_profile_page.connectionSettingsRequested.connect(lambda: self._select_page(0))
            self._update_global_admin_access(self.site_profile_page.admin_access_state())
        elif page_index == 10:
            self.jeddah_batch_page = page
        elif page_index == 11:
            self.orthogonalize_page = page

        # Compact SSH widgets only open the local connection-settings page. They
        # never test the server while a page is being created.
        for remote_widget in page.findChildren(RemoteGSourceWidget):
            remote_widget.connectionSettingsRequested.connect(lambda: self._select_page(0))

        database_page = self.pages[0]
        site_profile_page = self.pages[3]
        jeddah_page = self.pages[10]
        admin_state = site_profile_page.admin_access_state() if site_profile_page is not None else {}
        set_admin_mode = getattr(page, "set_admin_mode", None)
        if callable(set_admin_mode):
            set_admin_mode(
                bool(admin_state.get("is_admin", False)),
                int(admin_state.get("admin_epoch", 0) or 0) or None,
            )
        if database_page is not None:
            if page_index == 0:
                # The connection page may be created after business pages. Wire all
                # already-created SSH widgets at that moment.
                existing_remote_widgets = []
                for existing_page in self.pages:
                    if existing_page is None or existing_page is database_page:
                        continue
                    existing_remote_widgets.extend(existing_page.findChildren(RemoteGSourceWidget))
                for remote_widget in existing_remote_widgets:
                    database_page.environmentChanged.connect(
                        lambda _uid, w=remote_widget: w.refresh_shared_settings()
                    )
            else:
                for remote_widget in page.findChildren(RemoteGSourceWidget):
                    database_page.environmentChanged.connect(
                        lambda _uid, w=remote_widget: w.refresh_shared_settings()
                    )
        if database_page is not None and site_profile_page is not None:
            # The signal may be wired more than once as lazy pages appear. Qt safely
            # calls duplicate slots, but avoid duplication with a per-window flag.
            if not getattr(self, "_database_site_profile_wired", False):
                database_page.environmentChanged.connect(
                    lambda _uid: site_profile_page._refresh_global_connection_settings()
                )
                self._database_site_profile_wired = True

        # The connection page owns the one-click central sync.  If ID / symbol
        # pages are already open, refresh their LOCAL views after the bulk sync;
        # if they are created later they simply load the newly written local cache.
        if database_page is not None:
            id_page = self.pages[2]
            if id_page is not None and not getattr(self, "_bulk_sync_id_page_wired", False):
                refresh = getattr(id_page, "refresh_after_external_central_sync", None)
                if callable(refresh):
                    database_page.centralConfigSynced.connect(refresh)
                    self._bulk_sync_id_page_wired = True
            if site_profile_page is not None and not getattr(self, "_bulk_sync_site_page_wired", False):
                refresh = getattr(site_profile_page, "refresh_after_external_central_sync", None)
                if callable(refresh):
                    database_page.centralConfigSynced.connect(refresh)
                    self._bulk_sync_site_page_wired = True
        if site_profile_page is not None and jeddah_page is not None:
            if not getattr(self, "_site_jeddah_wired", False):
                site_profile_page.activeProfileChanged.connect(jeddah_page.refresh_profiles)
                self._site_jeddah_wired = True

    def _remember_business_page(self, page_index: int) -> None:
        stable_id = self.BUSINESS_PAGE_IDS.get(int(page_index))
        if not stable_id:
            return
        if self.user_settings.get_value(self.LAST_BUSINESS_PAGE_KEY).strip() != stable_id:
            self.user_settings.set_value(self.LAST_BUSINESS_PAGE_KEY, stable_id)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        self.sidebar = sidebar
        sidebar.setFixedWidth(270)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 20, 18, 18)
        side_layout.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(11)
        badge = QFrame()
        badge.setObjectName("brandBadge")
        badge.setFixedSize(44, 44)
        badge_layout = QVBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_letter = QLabel("G")
        badge_letter.setObjectName("brandLetter")
        badge_letter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_layout.addWidget(badge_letter)

        brand_text = QWidget()
        brand_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        brand_text_layout = QVBoxLayout(brand_text)
        brand_text_layout.setContentsMargins(0, 1, 0, 0)
        brand_text_layout.setSpacing(1)
        title = QLabel("G File Studio")
        title.setObjectName("brandTitle")
        subtitle = QLabel("NARI 国际业务部 · 吉达现场")
        subtitle.setObjectName("brandSubtitle")
        brand_text_layout.addWidget(title)
        brand_text_layout.addWidget(subtitle)
        brand_row.addWidget(badge)
        brand_row.addWidget(brand_text, 1)

        grid_badge = QLabel("G 文件处理工具 · 吉达现场")
        grid_badge.setObjectName("gridModeBadge")
        grid_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid_badge.setFixedHeight(32)
        grid_badge.setStyleSheet("font-size: 11px; font-weight: 700;")

        # v2.18.171: central configuration administrator is a global application
        # permission, so its entry belongs in the persistent sidebar rather than in
        # the server-symbol page. The page still owns the mature SSH/admin workflow;
        # this button is only the global presentation/control surface.
        self.config_access_button = QPushButton("配置权限：普通客户端")
        self.config_access_button.setObjectName("sidebarConfigAccessButton")
        self.config_access_button.setFixedHeight(36)
        self.config_access_button.setToolTip("查看或切换中央配置管理员权限")
        self.config_access_button.setStyleSheet(
            "QPushButton { background: #0e2a34; color: #d4e2e2; border: 1px solid #1c4a56; "
            "border-radius: 8px; padding: 8px 12px; text-align: left; font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background: #123b45; color: #ffffff; border-color: #2f736f; }"
            "QPushButton:disabled { color: #8aa3a3; background: #102932; border-color: #24434a; }"
        )

        self.nav = QListWidget()
        self.nav.setObjectName("navigation")
        self.nav.setSpacing(2)
        # 分组标题和业务项共用一个可滚动导航列表；业务项始终单行完整显示。
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setWordWrap(False)
        self.nav.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.nav.setUniformItemSizes(False)
        self.nav.setResizeMode(QListView.ResizeMode.Adjust)
        # v2.18.112：继续优化侧栏大标题显示。分组标题行预留足够内容区，避免 QListWidget item 的 padding 在高 DPI 下裁掉按钮下边框/文字；同时统一提升分组标题与顶部工具标题的可读性。仅调整导航展示。
        self.nav.setStyleSheet(
            "QListWidget#navigation { background: transparent; border: none; color: #d4e2e2; "
            "outline: none; padding: 0; font-size: 14px; }"
            "QListWidget#navigation::item { background: transparent; border: none; "
            "border-left: 3px solid transparent; border-radius: 8px; margin: 2px 0; "
            "padding: 11px 14px 11px 18px; font-size: 14px; font-weight: 560; }"
            "QListWidget#navigation::item:hover { background: #123440; color: #ffffff; "
            "border-left-color: #2fa889; }"
            "QListWidget#navigation::item:selected { background: #0b7a5a; color: #ffffff; "
            "border-left-color: #84e2c3; }"
        )
        self._page_to_nav_row: dict[int, int] = {}
        self._nav_section_rows: dict[str, list[int]] = {}
        self._nav_section_buttons: dict[str, QToolButton] = {}

        # 页面索引保持 self.pages 的既有稳定顺序，只调整左侧展示层级；
        # 不修改任何页面/处理器的业务调用关系。
        navigation_sections = [
            (
                "检查与标准",
                "validation_standard",
                [
                    ("异常小尺寸图元检测", "检测 ConnectLine、FeedLine、Bus、BusDis 中 w/h 同时过小的疑似残留短线图元；通过首列勾选单选/多选/全选后统一执行处理", 1),
                    ("ID 检查与修复", "全局 ID 规则中心：维护模板、扫描覆盖并强制修复格式异常或重复 ID", 2),
                    ("服务器图元同步管理", "同步远程服务器图元信息并维护本地分类标记；不执行图元标准检查、纠正或拓扑分析", 3),
                ],
            ),
            (
                "图形处理",
                "graphic_processing",
                [
                    ("环网柜处理", "独立处理环网柜组合/取消组合、增强操作，以及柜名与柜型识别", 4),
                    ("Poke 跳转处理", "独立生成/修复 RMU 与站点跳转 Poke；复用公共 RMU 识别、Oracle 数据库及站点 Poke 参考属性", 5),
                    ("通用基础处理", "执行通用属性、同类图元版本升级、馈线标题、连接点和线路/母线颜色处理；涉及 ID 时强制使用全局模板", 6),
                    ("馈线图合并", "按用户选择顺序合并多个馈线 G 图", 7),
                    ("图形边距调整", "调整主体四边距，并同步适配内置图框", 8),
                    ("图框添加", "添加 SLD 外框、标题和签字栏", 9),
                    ("线路正交化", "按单个 G 文件的线路结构处理连接点对齐、线路横平竖直和安全重画", 11),
                ],
            ),
            (
                "现场批处理",
                "site_batch",
                [
                    ("吉达图形批处理", "Jeddah 专用：第一步彻底取消图形组合（删除全部 <Merge>、RMU 外框置底），再批量删除异常小元素、SMART/SMR 红框、SMART 图元校正 + SMR 智能清理/转换 + 转换后图元复检、RMU 柜名严格按外框内三类组成并只从上方识别 + 白色 + 字号50 + 上边框上方10居中、删除 RMU channel_status 红色状态点、Bus 外框清理、馈线名称上移、删除 H.T、清理同柜重复 SMART、相邻 2000.00 + UPDATED_MEASURMENT 成对删除、ID 检查与修复、图形边距调整并添加图框", 10),
                    ("柱上变压器熔断器替换", "按 TRANSFORMER_OH 分类识别柱上变压器；仅当只有一个 Transformer 端点已连接时，替换为模板中的完整矩形框组合（Merge + rect + Fuse + Transformer），并保持原外部线路端点坐标不变。", 12),
                    ("环网柜 EFI 保护图元添加", "检查环网柜框内是否缺少 NariPd_Normal；缺少时根据 NariPd_Earth 放置，可调 Normal-Earth 间距和柜框间距。", 13),
                ],
            ),
        ]

        for section_title, section_key, entries in navigation_sections:
            header_item = QListWidgetItem()
            header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            header_item.setSizeHint(QSize(0, 74))
            self.nav.addItem(header_item)

            section_button = QToolButton()
            section_button.setObjectName("navSectionButton")
            section_button.setText(section_title)
            section_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            section_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            section_button.setFixedHeight(40)
            section_button.setStyleSheet(
                "QToolButton { background: #0e2a34; color: #9fc4c1; "
                "border: 1px solid #173d48; border-radius: 8px; "
                "padding: 7px 10px; text-align: left; font-size: 14px; font-weight: 750; }"
                "QToolButton:hover { color: #e1f5f0; background: #12343f; border-color: #286071; }"
                "QToolButton:checked { color: #dff8ef; background: #10313b; border-color: #1e5663; }"
            )
            section_button.setCheckable(True)
            expanded = self.user_settings.get_bool(f"navigation/{section_key}_expanded", True)
            section_button.setChecked(expanded)
            section_button.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            )
            # Header rows use a dedicated container with vertical breathing room.
            # This prevents the section card from visually colliding with the first child row
            # under Windows display scaling and keeps the child titles clearly subordinate.
            header_container = QWidget()
            header_container.setObjectName("navSectionContainer")
            header_layout = QVBoxLayout(header_container)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(0)
            header_layout.addWidget(section_button)
            self.nav.setItemWidget(header_item, header_container)
            self._nav_section_buttons[section_key] = section_button
            self._nav_section_rows[section_key] = []

            for name, tip, page_index in entries:
                item = QListWidgetItem(name)
                item.setToolTip(tip)
                item.setStatusTip(tip)
                item.setData(self.NAV_PAGE_ROLE, page_index)
                item.setData(self.NAV_SECTION_ROLE, section_key)
                self.nav.addItem(item)
                row = self.nav.row(item)
                self._page_to_nav_row[page_index] = row
                self._nav_section_rows[section_key].append(row)
                item.setHidden(not expanded)

            section_button.toggled.connect(
                lambda checked, key=section_key: self._set_navigation_section_expanded(key, checked)
            )

        self.connection_button = QPushButton("连接与环境")
        self.connection_button.setObjectName("sidebarConnectionButton")
        self.connection_button.setCheckable(True)
        self.connection_button.setStyleSheet(
            "QPushButton { background: transparent; color: #d4e2e2; border: none; "
            "border-left: 3px solid transparent; border-radius: 8px; padding: 12px 16px; "
            "text-align: left; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: #123440; color: #ffffff; border-left-color: #2fa889; }"
            "QPushButton:checked { background: #0b7a5a; color: #ffffff; border-left-color: #84e2c3; }"
        )
        self.connection_button.setToolTip("统一管理本机共享的只读文件服务器、资源目录和 Oracle 数据库连接")
        self.connection_button.setStatusTip("统一管理本机共享的只读文件服务器、资源目录和 Oracle 数据库连接")
        self.connection_button.clicked.connect(lambda: self._select_page(0))

        self.help_button = QPushButton("帮助中心")
        self.help_button.setObjectName("sidebarHelpButton")
        self.help_button.setCheckable(True)
        self.help_button.setStyleSheet(
            "QPushButton { background: transparent; color: #d4e2e2; border: none; "
            "border-left: 3px solid transparent; border-radius: 8px; padding: 12px 16px; "
            "text-align: left; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: #123440; color: #ffffff; border-left-color: #2fa889; }"
            "QPushButton:checked { background: #0b7a5a; color: #ffffff; border-left-color: #84e2c3; }"
        )
        self.help_button.setToolTip("查看使用说明和目录建议")
        self.help_button.setStatusTip("查看使用说明和目录建议")
        self.help_button.clicked.connect(lambda: self._select_page(self.HELP_PAGE_INDEX))

        language_label = QLabel("语言 / Language")
        language_label.setObjectName("sidebarLanguageLabel")
        language_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.language_combo = WheelSafeComboBox()
        self.language_combo.setObjectName("languageSelector")
        self.language_combo.addItem("中文", LANG_ZH)
        self.language_combo.addItem("English", LANG_EN)
        current_language = self.language_manager.language
        current_index = self.language_combo.findData(current_language)
        self.language_combo.setCurrentIndex(max(0, current_index))
        self.language_combo.setToolTip("切换界面语言；选择会自动保存，下次启动继续使用。")
        self.language_combo.currentIndexChanged.connect(self._language_combo_changed)

        version = QLabel(f"G File Studio {__version__}")
        version.setObjectName("sidebarVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        side_layout.addLayout(brand_row)
        side_layout.addSpacing(14)
        side_layout.addWidget(grid_badge)
        side_layout.addSpacing(8)
        side_layout.addWidget(self.config_access_button)
        side_layout.addSpacing(10)
        side_layout.addWidget(self.nav, 1)
        side_layout.addSpacing(8)
        side_layout.addWidget(self.connection_button)
        side_layout.addSpacing(4)
        side_layout.addWidget(self.help_button)
        side_layout.addSpacing(12)
        side_layout.addWidget(language_label)
        side_layout.addSpacing(5)
        side_layout.addWidget(self.language_combo)
        side_layout.addSpacing(10)
        side_layout.addWidget(version)
        return sidebar

    def _update_global_admin_access(self, state: object) -> None:
        if not hasattr(self, "config_access_button"):
            return
        data = state if isinstance(state, dict) else {}
        mode = str(data.get("mode", "ordinary"))
        text = str(data.get("button_text", "配置权限：普通模式"))
        owner = str(data.get("owner_text", "未占用"))
        version = int(data.get("config_version", 0) or 0)
        busy = bool(data.get("busy", False))
        self.config_access_button.setText(text)
        if mode == "admin":
            tip = f"本机持有中央配置管理员权限。当前管理员：{owner}"
        else:
            tip = (
                f"当前为普通客户端。当前已知 Admin：{owner}。"
                "本机可修改保存本地配置并手动同步中央配置；发布中央仓库需要抢占 Admin。"
            )
        if version > 0:
            tip += f" 中央配置版本：V{version}。"
        self.config_access_button.setToolTip(tip)
        self.config_access_button.setStatusTip(tip)
        self.config_access_button.setEnabled(not busy)
        admin_epoch = int(data.get("admin_epoch", 0) or 0) or None
        for page in getattr(self, "pages", []):
            if page is None:
                continue
            setter = getattr(page, "set_admin_mode", None)
            if callable(setter):
                setter(bool(data.get("is_admin", False)), admin_epoch)
        self._adjust_sidebar_width()

    def _show_global_admin_access(self) -> None:
        # Explicit operator action only. Startup remains strictly local-only.
        site_profile_page = self._ensure_page(3)
        self.site_profile_page = site_profile_page
        self.site_profile_page._refresh_admin_lease_status()
        state = self.site_profile_page.admin_access_state()
        mode = str(state.get("mode", "ordinary"))
        owner = str(state.get("owner_text", "未占用"))
        version = int(state.get("config_version", 0) or 0)
        version_text = f"V{version}" if version > 0 else "尚未发布"

        if mode == "admin":
            box = QMessageBox(self)
            box.setWindowTitle("中央配置权限")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText(
                f"当前模式：Admin\n当前 Admin：{owner}\n中央配置版本：{version_text}\n\n"
                "本机可修改并保存本地配置，也可以发布到中央仓库。后台仅每 10 秒检查一次很小的 instance.json，"
                "不会自动同步数据库、文件服务器、ID 规则或图元分类配置。"
            )
            release_button = box.addButton("释放 Admin 权限", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is release_button:
                if QMessageBox.question(
                    self,
                    "释放 Admin 权限",
                    "释放后本机不再拥有中央发布权限，其他机器可以重新抢占 Admin。是否继续？",
                ) == QMessageBox.StandardButton.Yes:
                    self.site_profile_page._release_admin_mode()
            return

        box = QMessageBox(self)
        box.setWindowTitle("中央配置权限")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            f"当前模式：普通客户端\n当前已知 Admin：{owner}\n中央配置版本：{version_text}\n\n"
            "普通客户端可以修改并保存本机配置，也可以手动从中央仓库同步配置；只有上传/发布到中央仓库需要 Admin。"
            "任何机器都可以手动抢占 Admin。\n\n"
            "抢占只变更 Admin 所有权，不会自动同步或发布任何业务配置。"
        )
        takeover_button = box.addButton("抢占 Admin 权限", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is takeover_button:
            self.site_profile_page._toggle_admin_mode()

    def _set_navigation_section_expanded(self, section_key: str, expanded: bool) -> None:
        button = self._nav_section_buttons.get(section_key)
        if button is not None:
            button.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
            )
        for row in self._nav_section_rows.get(section_key, []):
            item = self.nav.item(row)
            if item is not None:
                item.setHidden(not expanded)
        self.user_settings.set_value(
            f"navigation/{section_key}_expanded", "true" if expanded else "false"
        )

    def _select_page(self, page_index: int) -> None:
        if not (0 <= page_index < self.PAGE_COUNT):
            return
        page = self._ensure_page(page_index)
        if page_index == 0:
            self.nav.setCurrentRow(-1)
            self.stack.setCurrentIndex(0)
            self.connection_button.setChecked(True)
            self.help_button.setChecked(False)
            on_page_activated = getattr(page, "on_page_activated", None)
            if callable(on_page_activated):
                on_page_activated()
            self.statusBar().showMessage(
                self.connection_button.statusTip() or self.connection_button.toolTip()
            )
            return
        if page_index == self.HELP_PAGE_INDEX:
            self.nav.setCurrentRow(-1)
            self.stack.setCurrentIndex(self.HELP_PAGE_INDEX)
            self.connection_button.setChecked(False)
            self.help_button.setChecked(True)
            on_page_activated = getattr(page, "on_page_activated", None)
            if callable(on_page_activated):
                on_page_activated()
            self.statusBar().showMessage(self.help_button.statusTip() or self.help_button.toolTip())
            return

        row = self._page_to_nav_row.get(page_index)
        if row is None:
            return
        item = self.nav.item(row)
        section_key = str(item.data(self.NAV_SECTION_ROLE) or "")
        if section_key:
            section_button = self._nav_section_buttons.get(section_key)
            if section_button is not None and not section_button.isChecked():
                section_button.setChecked(True)
        self.connection_button.setChecked(False)
        self.help_button.setChecked(False)
        if self.nav.currentRow() == row:
            self._change_page(row)
        else:
            self.nav.setCurrentRow(row)


    def _language_combo_changed(self, index: int) -> None:
        language = self.language_combo.itemData(index)
        if language:
            self.language_manager.set_language(str(language))

    def _apply_language(self, language: str) -> None:
        del language
        self.language_manager.translate_widget_tree(self)
        if hasattr(self, "nav"):
            # Keep child-page titles visually subordinate to the group heading.
            # The i18n layer stores the clean source text in Qt.UserRole, so this
            # presentation-only indent can be re-applied safely after every language switch.
            self._apply_navigation_child_indent()
            # English module/group names are longer. Grow the sidebar so every
            # visible label remains complete on one line.
            self._adjust_sidebar_width()
            QTimer.singleShot(0, self._adjust_sidebar_width)
            if hasattr(self, "connection_button") and self.connection_button.isChecked():
                self.statusBar().showMessage(self.connection_button.statusTip() or self.connection_button.toolTip())
            elif hasattr(self, "help_button") and self.help_button.isChecked():
                self.statusBar().showMessage(self.help_button.statusTip() or self.help_button.toolTip())
            else:
                item = self.nav.currentItem()
                if item and item.data(self.NAV_PAGE_ROLE) is not None:
                    self.statusBar().showMessage(item.statusTip() or item.toolTip())

    def _apply_navigation_child_indent(self) -> None:
        """Indent business page labels without changing their stored i18n source text."""
        indent = "\u2003\u2003"
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item is None or item.data(self.NAV_PAGE_ROLE) is None:
                continue
            clean_text = item.text().lstrip(" \t\u2002\u2003")
            item.setText(indent + clean_text)

    def _adjust_sidebar_width(self) -> None:
        """Keep grouped navigation labels fully visible on one line."""
        if not hasattr(self, "nav") or not hasattr(self, "sidebar"):
            return
        metrics = self.nav.fontMetrics()
        widest = 0
        for row in range(self.nav.count()):
            item = self.nav.item(row)
            if item is not None and item.text():
                source_text = item.data(int(Qt.ItemDataRole.UserRole))
                display_text = str(source_text) if source_text else item.text().lstrip(" \t\u2002\u2003")
                widest = max(widest, metrics.horizontalAdvance(display_text))
        for button in getattr(self, "_nav_section_buttons", {}).values():
            widest = max(widest, button.fontMetrics().horizontalAdvance(button.text()) + 22)
        if hasattr(self, "config_access_button"):
            widest = max(widest, self.config_access_button.fontMetrics().horizontalAdvance(self.config_access_button.text()))
        if hasattr(self, "connection_button"):
            widest = max(widest, self.connection_button.fontMetrics().horizontalAdvance(self.connection_button.text()))
        if hasattr(self, "help_button"):
            widest = max(widest, self.help_button.fontMetrics().horizontalAdvance(self.help_button.text()))
        # Business items keep their original width budget; visual child indentation is added after translation and is not allowed to inflate the sidebar.
        width = max(270, min(420, widest + 88))
        self.sidebar.setFixedWidth(width)

    def _change_page(self, nav_row: int) -> None:
        if nav_row < 0 or nav_row >= self.nav.count():
            return
        item = self.nav.item(nav_row)
        if item is None:
            return
        page_index = item.data(self.NAV_PAGE_ROLE)
        if not isinstance(page_index, int) or not (0 <= page_index < self.PAGE_COUNT):
            return
        page = self._ensure_page(page_index)
        self.connection_button.setChecked(False)
        self.help_button.setChecked(False)
        self.stack.setCurrentIndex(page_index)
        self._remember_business_page(page_index)
        on_page_activated = getattr(page, "on_page_activated", None)
        if callable(on_page_activated):
            on_page_activated()
        self.statusBar().showMessage(item.statusTip() or item.toolTip())


    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        for page in self.pages:
            if page is None:
                continue
            save_state = getattr(page, "save_state", None)
            if callable(save_state):
                save_state()
        super().closeEvent(event)

    def _install_help_shortcut(self) -> None:
        action = QAction(self)
        action.setShortcut(QKeySequence.StandardKey.HelpContents)
        action.triggered.connect(lambda: self._select_page(self.HELP_PAGE_INDEX))
        self.addAction(action)
