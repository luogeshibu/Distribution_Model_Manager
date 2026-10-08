from __future__ import annotations

from pathlib import Path
import re
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from dmm.infrastructure.filesystem.workspace import user_data_root
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.i18n import LanguageManager, LANG_EN, LANG_ZH
from dmm.i18n.translator import normalize_language, retranslate_qt_tree
from g_file_studio.ui.table_layout import apply_graphics_table_selection_style


class GraphicsWorkspaceWidget(QWidget):
    """Embed the Jeddah GFileStudio business modules inside DMM.

    Integration contract for v4.2.3:
    - DMM v4.1.111 remains authoritative for model-association rules.
    - GFileStudio v2.18.257 remains authoritative for graphics-processing rules.
    - Jazan v4.1.131 is used only as the UI/integration pattern reference.
    - Graphics pages are lazy-created so the DMM startup stays local/offline and fast.
    - The main DMM Oracle / SSH / central-repository values can be projected into the
      GFileStudio local settings with one local-only action.  No network operation is
      performed by that projection.
    - Main DMM Element Management is the only visible symbol catalog. Its saved
      metadata/classifications are mirrored locally for graphics processors.
    """

    requestMainPage = Signal(int)

    OPERATIONS: tuple[tuple[str, str, str], ...] = (
        ("异常小尺寸图元处理", "small", "g_file_studio.ui.pages.small_element_page:SmallElementPage"),
        ("ID 检查与修复", "id", "g_file_studio.ui.pages.id_page:IdPage"),
        ("环网柜处理", "rmu", "g_file_studio.ui.pages.rmu_page:RmuPage"),
        ("Poke 跳转处理", "poke", "g_file_studio.ui.pages.poke_page:PokePage"),
        ("通用基础处理", "basic", "g_file_studio.ui.pages.basic_page:BasicPage"),
        ("馈线图合并", "merge", "g_file_studio.ui.pages.merge_page:MergePage"),
        ("图形边距调整", "margin", "g_file_studio.ui.pages.margin_page:MarginPage"),
        ("图框添加", "frame", "g_file_studio.ui.pages.frame_page:FramePage"),
        ("线路正交化", "orthogonalize", "g_file_studio.ui.pages.orthogonalize_page:OrthogonalizePage"),
        ("整图拓扑连接检查/修复", "whole_graph_topology", "g_file_studio.ui.pages.whole_graph_topology_page:WholeGraphTopologyPage"),
        ("吉达图形批处理", "jeddah_batch", "g_file_studio.ui.pages.jeddah_batch_page:JeddahBatchPage"),
        ("柱上变压器熔断器替换", "transformer_fuse", "g_file_studio.ui.pages.transformer_fuse_page:TransformerFusePage"),
        ("环网柜 EFI 保护图元添加", "rmu_efi", "g_file_studio.ui.pages.rmu_efi_page:RmuEfiPage"),
    )

    def __init__(self, dmm_settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dmm_settings = dmm_settings
        self._is_admin_mode = False
        self._admin_epoch: int | None = None
        # Keep the mature GFileStudio AppData cache location for seamless migration
        # from the standalone tool.  This prevents an upgrade from losing ID rules,
        # symbol cache, classification marks or page preferences.
        self.gfs_settings = UserSettingsService()
        self.language = normalize_language((dmm_settings or {}).get("language", "zh_CN"))
        self.language_manager = LanguageManager(self.gfs_settings, self)
        self.language_manager.set_language(LANG_EN if self.language == "en_US" else LANG_ZH)
        self._pages: dict[int, QWidget] = {}
        self._build_ui()
        # v4.2.12: protect every current and future graphics-workspace table from
        # the Windows native dark-blue selection palette, including QDialogs that
        # are created only after the user clicks a feature button.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            # v4.2.13: embedded GFileStudio pages update many labels dynamically
            # after the initial translation pass.  Install the mature GFS
            # LanguageManager event filter as well so runtime labels/dialogs
            # cannot fall back to Chinese while DMM is in English mode.
            app.installEventFilter(self.language_manager)
        # Project only local values; this performs no Oracle/SSH/central connection.
        self.sync_main_configuration(show_message=False)
        self._ensure_page(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 24)
        root.setSpacing(12)

        title = QLabel("图形工作区")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "吉达图形处理已合并到自动模型关联软件。模型业务继续使用 Jeddah DMM 规则；"
            "图形处理继续使用 GFileStudio v2.18.257 的成熟处理引擎。"
        )
        subtitle.setObjectName("pageSub")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        banner = QFrame()
        banner.setObjectName("card")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(14, 10, 14, 10)
        note = QLabel(
            "统一入口：这里直接处理 G 图形；原始 G 永不覆盖。"
            "现场批处理继续遵守“只有实际修改过的 G 才输出”的规则。"
        )
        note.setWordWrap(True)
        banner_layout.addWidget(note, 1)
        self.sync_button = QPushButton("同步主程序配置到图形工作区")
        self.sync_button.setToolTip(
            "仅把当前 DMM 本机缓存中的 Oracle、业务 G 文件 SSH、图元目录和中央仓库参数投影到图形工作区；不会连接网络。"
        )
        self.sync_button.clicked.connect(lambda: self.sync_main_configuration(show_message=True))
        banner_layout.addWidget(self.sync_button)
        root.addWidget(banner)

        chooser = QFrame()
        chooser.setObjectName("card")
        chooser_layout = QHBoxLayout(chooser)
        chooser_layout.setContentsMargins(14, 10, 14, 10)
        chooser_layout.addWidget(QLabel("图形处理类型"))
        self.operation_combo = QComboBox()
        self.operation_combo.setMinimumWidth(320)
        for label, stable_id, _factory in self.OPERATIONS:
            self.operation_combo.addItem(label, stable_id)
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)
        chooser_layout.addWidget(self.operation_combo, 1)

        element_button = QPushButton("主程序图元管理")
        element_button.clicked.connect(lambda: self.requestMainPage.emit(2))
        chooser_layout.addWidget(element_button)
        database_button = QPushButton("主程序数据库/连接")
        database_button.clicked.connect(lambda: self.requestMainPage.emit(3))
        chooser_layout.addWidget(database_button)
        root.addWidget(chooser)

        self.stack = QStackedWidget()
        self.stack.setObjectName("graphicsWorkspaceStack")
        for _label, _stable_id, _factory in self.OPERATIONS:
            host = QWidget()
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            loading = QLabel("首次进入时加载图形处理模块……")
            loading.setAlignment(Qt.AlignCenter)
            loading.setObjectName("pageSub")
            layout.addWidget(loading, 1)
            self.stack.addWidget(host)
        root.addWidget(self.stack, 1)

    def _belongs_to_graphics_workspace(self, widget: QWidget) -> bool:
        current = widget
        while current is not None:
            if current is self:
                return True
            current = current.parentWidget()
        return False

    def _style_graphics_tables(self, root: QWidget) -> None:
        if isinstance(root, QTableWidget):
            apply_graphics_table_selection_style(root)
        for table in root.findChildren(QTableWidget):
            apply_graphics_table_selection_style(table)

    def eventFilter(self, watched, event):
        # Dialogs such as "Query and Import G Files" and main-bus grouping are
        # top-level windows but retain their graphics-page QObject parent.  Patch
        # tables again when polished/shown so host/native styles cannot restore
        # the unreadable blue selection.
        if isinstance(watched, QTableWidget) and event.type() in (QEvent.Type.Polish, QEvent.Type.Show):
            if self._belongs_to_graphics_workspace(watched):
                apply_graphics_table_selection_style(watched)
        return super().eventFilter(watched, event)

    def _on_operation_changed(self, index: int) -> None:
        self._ensure_page(index)
        self.stack.setCurrentIndex(index)

    @staticmethod
    def _load_factory(spec: str) -> type[QWidget]:
        module_name, class_name = spec.split(":", 1)
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)

    def _ensure_page(self, index: int) -> QWidget:
        index = max(0, min(int(index), len(self.OPERATIONS) - 1))
        existing = self._pages.get(index)
        if existing is not None:
            return existing
        _label, stable_id, factory_spec = self.OPERATIONS[index]
        factory = self._load_factory(factory_spec)
        page = factory(self.gfs_settings)
        if hasattr(page, "set_admin_mode"):
            try:
                page.set_admin_mode(self._is_admin_mode, self._admin_epoch)
            except TypeError:
                page.set_admin_mode(self._is_admin_mode)
        host = self.stack.widget(index)
        layout = host.layout()
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            layout.addWidget(page)
        self._pages[index] = page
        # Embedded GFileStudio pages use their mature presentation-layer i18n.
        self.language_manager.translate_widget_tree(page)
        # Apply the canonical pale selection immediately to every table created
        # by the page.  Lazy child dialogs are covered by eventFilter above.
        self._style_graphics_tables(page)
        return page

    def set_language(self, language: str) -> None:
        """Keep the embedded Graphics Workspace in the same language as DMM."""
        self.language = normalize_language(language)
        target = LANG_EN if self.language == "en_US" else LANG_ZH
        self.gfs_settings.set_value("general/language", target)
        self.language_manager.set_language(target)
        # Translate the DMM-owned wrapper and every already-created GFileStudio page.
        retranslate_qt_tree(self, self.language)
        for page in list(self._pages.values()):
            self.language_manager.translate_widget_tree(page)

    def sync_main_configuration(self, *, show_message: bool = True) -> dict[str, int]:
        """Project DMM local settings into the embedded GFileStudio cache.

        This is intentionally local-only.  It does not test or open Oracle/SSH.
        GFileStudio retains its own robust runtime services and safety guards, but
        both workspaces start from the same operator-approved DMM connection values.
        """
        cfg = self.dmm_settings or {}
        ssh = dict(cfg.get("ssh", {}) or {})
        db = dict(cfg.get("db", {}) or {})
        central = dict(cfg.get("central_config", {}) or {})
        settings = self.gfs_settings

        mapped = {
            "remote_g_source/host": ssh.get("host", ""),
            "remote_g_source/port": ssh.get("port", 22),
            "remote_g_source/username": ssh.get("username", ""),
            "remote_g_source/password": ssh.get("password", ""),
            "remote_g_source/remote_directory": ssh.get("remote_directory", ""),
            "site_profile/remote_symbol_library_root": ssh.get("element_directory", ""),
            "central_repository/host": central.get("host", ssh.get("host", "")),
            "central_repository/port": central.get("port", ssh.get("port", 22)),
            "central_repository/username": central.get("username", ssh.get("username", "")),
            "central_repository/password": central.get("password", ssh.get("password", "")),
            # v4.2.3: the merged application has exactly one central repository.
            # ID rules and all embedded graphics central actions use the same DMM
            # path as database/file-server/element_marks/instance configuration.
            "central_repository/config_dir": (
                central.get("remote_directory")
                or "/home/up8000/nari-international/distribution-model-manager/config"
            ),
            # Reuse the DMM machine identity so embedded graphics pages validate
            # the same Admin owner recorded in instance.json.
            "access_control/machine_id": cfg.get("machine_id", ""),
            "database/oracle_username": db.get("user", ""),
            "database/oracle_host": db.get("host", ""),
            "database/oracle_port": db.get("port", 1521),
            "database/oracle_service": db.get("service_name", ""),
            "database/oracle_config_saved": "true",
        }
        count = 0
        for key, value in mapped.items():
            if value is None:
                continue
            settings.set_value(key, value)
            count += 1

        # Persist Oracle password with the exact GFileStudio DPAPI implementation on
        # Windows.  On non-Windows development hosts the service intentionally does
        # not persist secrets; the public connection values above are still bridged.
        try:
            from g_file_studio.services.database_service import (
                OracleConnectionConfig,
                OracleDatabaseService,
            )
            password = str(db.get("password", "") or "")
            if password and str(db.get("user", "") or "").strip():
                OracleDatabaseService(settings).save_config(
                    OracleConnectionConfig(
                        username=str(db.get("user", "") or ""),
                        password=password,
                        host=str(db.get("host", "") or ""),
                        port=int(db.get("port", 1521) or 1521),
                        service_name=str(db.get("service_name", "") or ""),
                    )
                )
        except Exception:
            # The bridge must never make the merged application unusable merely
            # because a development/non-Windows host cannot persist a secret.
            pass

        catalog_count = self._bridge_element_catalog(ssh)
        marker_count = self._bridge_element_marks(ssh)
        if show_message:
            QMessageBox.information(
                self,
                "图形工作区配置已同步",
                "已从主程序本机配置同步连接参数与图元目录到图形工作区。\n\n"
                f"连接参数：{count} 项\n"
                f"可用图元定义：{catalog_count} 项\n"
                f"图元分类标记：{marker_count} 项\n\n"
                "图形工作区不再维护独立的服务器图元同步页面；图元定义与分类统一以主程序“图元管理”为准。\n"
                "ID 规则、Admin 身份和中央仓库路径也统一使用主程序设置。\n"
                "此操作只更新本机缓存，没有连接 Oracle、SSH 或中央服务器。",
            )
        return {"settings": count, "catalog": catalog_count, "markers": marker_count}

    @staticmethod
    def _parse_numeric_pair(value: object) -> list[float]:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                return [float(value[0]), float(value[1])]
            except (TypeError, ValueError):
                return []
        numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", str(value or ""))
        if len(numbers) < 2:
            return []
        try:
            return [float(numbers[0]), float(numbers[1])]
        except ValueError:
            return []

    @staticmethod
    def _parse_pin_pairs(value: object) -> list[list[float]]:
        if isinstance(value, (list, tuple)):
            result: list[list[float]] = []
            for item in value:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        result.append([float(item[0]), float(item[1])])
                    except (TypeError, ValueError):
                        continue
            return result
        text = str(value or "")
        number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
        result = []
        for x_text, y_text in re.findall(rf"\(\s*({number})\s*,\s*({number})\s*\)", text):
            try:
                result.append([float(x_text), float(y_text)])
            except ValueError:
                continue
        return result

    def _bridge_element_catalog(self, ssh: dict) -> int:
        """Mirror DMM Element Management metadata into the graphics local cache.

        v4.2.3 keeps the duplicate GFileStudio server-symbol page removed.  The main
        DMM Element Management page is now the single authoritative symbol catalog
        for both model and graphics workflows.  This bridge is strictly local: it
        serializes already-saved DMM metadata into the mature GFileStudio cache
        format and never opens SSH.
        """
        catalog = dict((self.dmm_settings or {}).get("element_catalog", {}) or {})
        records = catalog.get("records", [])
        if not isinstance(records, list) or not records:
            return 0
        host = str(ssh.get("host", "") or "").strip()
        root = str(ssh.get("element_directory", "") or "").strip()
        if not host or not root:
            return 0

        try:
            from g_file_studio.services.remote_symbol_library import RemoteSymbolLibraryService

            service = RemoteSymbolLibraryService()
            previous = service.load_cached_sync_snapshot(host=host, root=root)
            previous_rows = previous.get("server_file_records", []) if isinstance(previous, dict) else []
            cache_by_identity: dict[str, str] = {}
            if isinstance(previous_rows, list):
                for previous_row in previous_rows:
                    if not isinstance(previous_row, dict):
                        continue
                    standard = previous_row.get("standard_record", {})
                    standard = standard if isinstance(standard, dict) else {}
                    cache_path = str(previous_row.get("cache_path", standard.get("cache_path", "")) or "").strip()
                    if not cache_path or not Path(cache_path).is_file():
                        continue
                    identities = {
                        str(previous_row.get("relative_path", standard.get("relative_path", "")) or "").replace("\\", "/").strip("/").casefold(),
                        str(previous_row.get("name", standard.get("original_name", "")) or "").casefold(),
                        str(standard.get("devref", "") or "").casefold(),
                    }
                    for identity in identities:
                        if identity:
                            cache_by_identity.setdefault(identity, cache_path)

            inventory: list[dict[str, object]] = []
            matched: dict[str, dict[str, object]] = {}
            for raw in records:
                if not isinstance(raw, dict):
                    continue
                file_key = str(
                    raw.get("file_key")
                    or raw.get("path")
                    or raw.get("relative_path")
                    or raw.get("file_name")
                    or ""
                ).replace("\\", "/").strip("/")
                file_name = str(raw.get("file_name", "") or Path(file_key).name).strip()
                if not file_name.lower().endswith(".g"):
                    continue
                sha256 = str(raw.get("definition_hash", raw.get("sha256", "")) or "").strip().lower()
                if not re.fullmatch(r"[0-9a-f]{64}", sha256):
                    continue
                root_id = str(raw.get("root_id", raw.get("element_id", "")) or "").strip()
                devref = str(raw.get("devref", raw.get("element_key", "")) or "").strip()
                if devref and not devref.startswith("#"):
                    devref = f"#{devref}"
                if not devref and root_id:
                    devref = f"#{file_name}:{root_id}"
                if not devref:
                    continue
                try:
                    width = float(raw.get("width", 0) or 0)
                    height = float(raw.get("height", 0) or 0)
                except (TypeError, ValueError):
                    width = height = 0.0
                align_center = self._parse_numeric_pair(raw.get("align_center", raw.get("AlignCenter", "")))
                pins = self._parse_pin_pairs(raw.get("pins", []))
                marker = str(raw.get("classification", raw.get("classification_marker", "")) or "").strip()
                remote_path = str(raw.get("remote_path", "") or "").strip()
                if not remote_path and file_key:
                    remote_path = f"{root.rstrip('/')}/{file_key}"

                cache_path = ""
                for identity in (file_key.casefold(), file_name.casefold(), devref.casefold()):
                    if identity and cache_by_identity.get(identity):
                        cache_path = cache_by_identity[identity]
                        break

                standard: dict[str, object] = {
                    "devref": devref,
                    "sha256": sha256,
                    "original_name": file_name,
                    "original_source": cache_path,
                    "managed_path": "",
                    "relative_path": file_key,
                    "element_tag": str(raw.get("target_xml", raw.get("element_tag", "")) or "").strip(),
                    "element_id": root_id,
                    "width": width,
                    "height": height,
                    "align_center": align_center,
                    "pins": pins,
                    "pin_ids": [],
                    "pin_indices": [],
                    "standard_source": "server",
                    "remote_host": host,
                    "remote_root": root,
                    "remote_path": remote_path,
                    "remote_size": int(raw.get("size", 0) or 0),
                    "remote_mtime": 0,
                    "cache_path": cache_path,
                    "synced_at": "",
                    "classification_marker": marker,
                    "category_marker": marker,
                }
                row: dict[str, object] = {
                    "name": file_name,
                    "remote_path": remote_path,
                    "relative_path": file_key,
                    "remote_host": host,
                    "remote_root": root,
                    "size": int(raw.get("size", 0) or 0),
                    "mtime_epoch": 0,
                    "sha256": sha256,
                    "cache_path": cache_path,
                    "standard_record": standard,
                    "classification_marker": marker,
                    "category_marker": marker,
                    "sync_status": "READY",
                }
                inventory.append(row)
                # matched_records is only a compatibility fallback.  The graphics
                # processors prefer the complete physical inventory above.
                matched.setdefault(file_name, standard)

            # An unconfigured or legacy DMM catalog must not erase a valid
            # standalone GFileStudio cache during migration.  Replace the graphics
            # snapshot only after at least one authoritative DMM definition could
            # be normalized successfully.
            if not inventory:
                return 0

            payload: dict[str, object] = {
                "server_file_records": inventory,
                "matched_records": matched,
                "checked_at": "",
                "downloaded": 0,
                "reused": len(inventory),
                "added_names": [],
                "changed_names": [],
                "unchanged_names": [row.get("name", "") for row in inventory],
                "unmatched_names": [],
                "conflicts": {},
                "errors": {},
                "inventory_complete": True,
                "source": "DMM Element Management local cache",
            }
            service.save_cached_sync_snapshot_payload(host=host, root=root, payload=payload)
            return len(inventory)
        except Exception:
            return 0

    def _bridge_element_marks(self, ssh: dict) -> int:
        catalog = dict((self.dmm_settings or {}).get("element_catalog", {}) or {})
        records = catalog.get("records", [])
        if not isinstance(records, list) or not records:
            return 0
        markers: list[dict[str, str]] = []
        for raw in records:
            if not isinstance(raw, dict):
                continue
            marker = str(raw.get("classification", "") or "").strip()
            if not marker:
                continue
            file_key = str(
                raw.get("file_key")
                or raw.get("path")
                or raw.get("relative_path")
                or raw.get("file_name")
                or ""
            ).replace("\\", "/").strip("/")
            file_name = str(raw.get("file_name", "") or Path(file_key).name).strip()
            devref = str(raw.get("devref", raw.get("element_key", "")) or "").strip()
            if devref and not devref.startswith("#"):
                devref = f"#{devref}"
            if not devref:
                root_id = str(raw.get("root_id", raw.get("element_id", "")) or "").strip()
                devref = f"#{file_name}:{root_id}" if root_id else file_name
            markers.append(
                {
                    "relative_path": file_key,
                    "file_name": file_name,
                    "devref": devref,
                    "element_id": str(raw.get("root_id", "") or raw.get("element_id", "") or "").strip(),
                    "classification_marker": marker,
                }
            )
        host = str(ssh.get("host", "") or "").strip()
        root = str(ssh.get("element_directory", "") or "").strip()
        if not host or not root:
            return 0
        try:
            from g_file_studio.services.remote_symbol_library import RemoteSymbolLibraryService
            result = RemoteSymbolLibraryService().replace_classification_marker_payload(
                host=host,
                root=root,
                payload={"schema": 2, "markers": markers},
            )
            return int(result.get("imported", 0) or 0)
        except Exception:
            return 0

    def set_admin_mode(self, is_admin: bool, admin_epoch: int | None = None) -> None:
        """Propagate the single DMM Admin session to embedded graphics pages.

        There is no second GFileStudio Admin identity in the merged application.
        ``instance.json`` under the DMM central repository is the only ownership
        source, so ID-rule publishing and any compatible embedded page use the
        same machine id / epoch as the main program.
        """
        self._is_admin_mode = bool(is_admin)
        self._admin_epoch = int(admin_epoch) if is_admin and admin_epoch is not None else None
        for page in tuple(self._pages.values()):
            if not hasattr(page, "set_admin_mode"):
                continue
            try:
                page.set_admin_mode(self._is_admin_mode, self._admin_epoch)
            except TypeError:
                page.set_admin_mode(self._is_admin_mode)

    def refresh_from_main_configuration(self) -> None:
        """Refresh local projection after the DMM settings dictionary changed."""
        self.sync_main_configuration(show_message=False)
        self.set_admin_mode(self._is_admin_mode, self._admin_epoch)
