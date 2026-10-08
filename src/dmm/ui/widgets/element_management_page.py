from __future__ import annotations

import json
import hashlib
import unicodedata
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QEvent, QTimer, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from dmm.config.settings import publish_central_settings, save_settings
from dmm.domain.gfile.element_catalog import (
    parse_element_definition,
    resolve_element_record,
)
from dmm.infrastructure.remote import ReadOnlySshClient
from dmm.i18n.translator import translate_runtime_text, retranslate_qt_tree


def _record_with_defaults(record: dict) -> dict:
    result = dict(record or {})
    # These preferences belong to the concrete model settings, not to an
    # element mark.  Drop legacy per-element values when old local settings
    # are loaded so they are not silently carried forward or shared.
    result.pop("name_format", None)
    result.pop("color_preference", None)
    if str(result.get("status") or "").startswith("解析失败："):
        result["status"] = "历史状态：已改为按图元文件维护"
    result.setdefault("element_key", "")
    result.setdefault("file_key", result.get("file_name", ""))
    result.setdefault("file_name", PurePosixPath(str(result.get("file_key", ""))).name)
    result.setdefault("target_xml", "")
    result.setdefault("root_id", "")
    result.setdefault("width", "")
    result.setdefault("height", "")
    result.setdefault("align_center", "")
    result.setdefault("pins", "")
    result.setdefault("classification", "")
    result.setdefault("device_alias", "")
    result.setdefault("device_code", "")
    result.setdefault("remark", "")
    result.setdefault("status", "已保存标记")
    result.setdefault("definition_hash", "")
    result.setdefault("missing_on_server", False)
    return result


def _record_identity(record: dict) -> str:
    """Use the relative file path as the stable maintenance identity."""
    value = str(record.get("file_key") or record.get("file_name") or "")
    return _normalize_element_path(value).casefold()


def _normalize_element_path(value: str) -> str:
    """Normalize path spelling differences that are invisible in the table."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("\\", "/")
    value = value.replace("\u200b", "").replace("\ufeff", "")
    parts = []
    for part in value.split("/"):
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _merge_duplicate_records(records) -> list[dict]:
    """Collapse repeated rows for the same relative element path.

    A server listing or an older local cache can contain the same path more
    than once.  The path is the maintenance identity, so duplicate rows must
    not become duplicate devices in the UI.  Preserve any non-empty user mark
    or remark found on one of the duplicate records.
    """
    merged_by_identity = {}
    order = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        row = _record_with_defaults(record)
        identity = _record_identity(row)
        if not identity:
            continue
        existing = merged_by_identity.get(identity)
        if existing is None:
            merged_by_identity[identity] = row
            order.append(identity)
            continue
        existing_marked = any(
            str(existing.get(key) or "").strip()
            for key in ("classification", "remark", "device_alias", "device_code")
        )
        row_marked = any(
            str(row.get(key) or "").strip()
            for key in ("classification", "remark", "device_alias", "device_code")
        )
        existing_mtime = str(existing.get("mtime_text") or "")
        row_mtime = str(row.get("mtime_text") or "")
        prefer_row = (
            (row_marked and not existing_marked)
            or (row.get("source") == "SSH" and existing.get("source") != "SSH")
            or (row_mtime and row_mtime > existing_mtime)
        )
        if prefer_row:
            merged_by_identity[identity] = row
            existing = row
        for key in ("classification", "remark", "device_alias", "device_code"):
            if not str(existing.get(key) or "").strip() and str(row.get(key) or "").strip():
                existing[key] = row[key]
        if row.get("missing_on_server"):
            existing["missing_on_server"] = True
        if row.get("definition_hash") and not existing.get("definition_hash"):
            existing["definition_hash"] = row["definition_hash"]
    return [merged_by_identity[identity] for identity in order]


def _portable_record(record: dict) -> dict:
    """Return a portable mark record without local/server-only metadata.

    The exported file is intentionally independent of this application's
    cache layout, SSH settings and runtime status.  Other tools can identify
    the same element by ``path``/``file_name`` and consume the semantic mark
    fields directly.
    """
    file_key = str(record.get("file_key") or record.get("file_name") or "")
    return {
        "path": file_key.replace("\\", "/"),
        "file_name": record.get("file_name", ""),
        "element_key": record.get("element_key", ""),
        "target_xml": record.get("target_xml", ""),
        "root_id": record.get("root_id", ""),
        "classification": record.get("classification", ""),
        "device_alias": record.get("device_alias", ""),
        "device_code": record.get("device_code", ""),
        "remark": record.get("remark", ""),
    }


def _portable_import_records(payload) -> list[dict]:
    """Read current and legacy mark JSON, plus simple third-party variants."""
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("records", payload.get("items", []))
    else:
        raise ValueError("共享配置必须是 JSON 数组或包含 records/items 的对象。")
    if not isinstance(records, list):
        raise ValueError("共享配置 records/items 必须是数组。")

    normalized = []
    aliases = {
        "path": ("path", "file_key", "relative_path", "file", "file_path"),
        "file_name": ("file_name", "filename", "name"),
        "element_key": ("element_key", "element", "key"),
        "target_xml": ("target_xml", "xml_tag", "tag"),
        "root_id": ("root_id", "root", "root_element"),
        "classification": ("classification", "category", "mark", "label"),
        "device_alias": ("device_alias", "alias"),
        "device_code": ("device_code", "code"),
        "remark": ("remark", "note", "description"),
    }
    for record in records:
        if not isinstance(record, dict):
            continue
        item = dict(record)
        for target, candidates in aliases.items():
            if str(item.get(target) or "").strip():
                continue
            for candidate in candidates:
                value = item.get(candidate)
                if value is not None and str(value).strip():
                    item[target] = value
                    break
        if item.get("path") and not item.get("file_key"):
            item["file_key"] = item["path"]
        if item.get("file_name") and not item.get("file_key"):
            item["file_key"] = item["file_name"]
        normalized.append(item)
    return normalized


def _definition_changed(saved: dict, current: dict) -> bool:
    old_hash = str(saved.get("definition_hash") or "").strip()
    new_hash = str(current.get("definition_hash") or "").strip()
    if old_hash and new_hash:
        return old_hash != new_hash
    fields = ("target_xml", "root_id", "width", "height", "align_center", "pins")
    return any(
        str(saved.get(field) or "").strip()
        and str(saved.get(field) or "").strip()
        != str(current.get(field) or "").strip()
        for field in fields
    )


def _merge_server_metadata(local: dict, remote: dict) -> dict:
    """Refresh server metadata while keeping the user's local mark fields."""
    merged = dict(local or {})
    for key in (
        "element_key",
        "file_key",
        "file_name",
        "remote_path",
        "source",
        "size",
        "mtime_text",
        "definition_hash",
        "target_xml",
        "root_id",
        "width",
        "height",
        "align_center",
        "pins",
    ):
        if key in remote:
            merged[key] = remote[key]
    merged["missing_on_server"] = False
    return _record_with_defaults(merged)


class ElementDefinitionWorker(QThread):
    loaded = Signal(list)
    failed = Signal(str)

    def __init__(self, ssh_config: dict, remote_directory: str, parent=None):
        super().__init__(parent)
        self.ssh_config = dict(ssh_config or {})
        self.remote_directory = str(remote_directory or "").strip()

    def run(self):
        client = None
        try:
            client = ReadOnlySshClient(
                host=self.ssh_config.get("host", ""),
                port=self.ssh_config.get("port", 22),
                username=self.ssh_config.get("username", ""),
                password=self.ssh_config.get("password", ""),
            )
            rows = []
            for remote_file in client.list_element_files(self.remote_directory):
                content = b""
                try:
                    content = client.read_file(remote_file.remote_path)
                    metadata = {
                        "element_key": remote_file.name,
                        "file_key": remote_file.name,
                        "file_name": PurePosixPath(remote_file.name).name,
                        "remote_path": remote_file.remote_path,
                        "status": "已读取",
                        "source": "SSH",
                        "size": remote_file.size,
                        "mtime_text": remote_file.mtime_text,
                        "definition_hash": hashlib.sha256(content).hexdigest(),
                    }
                    try:
                        definition = parse_element_definition(content, remote_file.name)
                    except Exception as exc:
                        # The file itself is readable even when its XML
                        # metadata cannot be parsed. Keep it visible.
                        definition = {
                            "status": f"已读取（属性解析失败：{exc}）",
                        }
                    row = _record_with_defaults({**metadata, **definition})
                except Exception as exc:
                    # Keep an unreadable file visible.  The page is a file
                    # mark registry and does not require XML parsing.
                    row = _record_with_defaults(
                        {
                            "element_key": remote_file.name,
                            "file_key": remote_file.name,
                            "file_name": PurePosixPath(remote_file.name).name,
                            "remote_path": remote_file.remote_path,
                            "status": f"读取失败：{exc}",
                            "source": "SSH",
                            "size": remote_file.size,
                            "mtime_text": remote_file.mtime_text,
                            "definition_hash": hashlib.sha256(content).hexdigest(),
                        }
                    )
                rows.append(row)
            self.loaded.emit(rows)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if client is not None:
                client.close()


class ElementDownloadWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        ssh_config: dict,
        remote_directory: str,
        rows: list[dict],
        destination: str,
        parent=None,
    ):
        super().__init__(parent)
        self.ssh_config = dict(ssh_config or {})
        self.remote_directory = str(remote_directory or "").strip()
        self.rows = list(rows or [])
        self.destination = Path(destination)

    @staticmethod
    def _relative_parts(row: dict) -> tuple[str, ...]:
        value = str(row.get("file_key") or row.get("file_name") or "").strip()
        parts = tuple(
            part
            for part in PurePosixPath(value.replace("\\", "/")).parts
            if part not in ("", ".", "..")
        )
        return parts or (PurePosixPath(value).name or "element.g",)

    def run(self):
        success = 0
        failed = []
        try:
            self.destination.mkdir(parents=True, exist_ok=True)
            with ReadOnlySshClient(
                self.ssh_config.get("host", ""),
                self.ssh_config.get("port", 22),
                self.ssh_config.get("username", ""),
                self.ssh_config.get("password", ""),
            ) as client:
                for row in self.rows:
                    parts = self._relative_parts(row)
                    relative = PurePosixPath(*parts)
                    remote_path = str(
                        PurePosixPath(self.remote_directory) / relative
                    )
                    local_path = self.destination.joinpath(*parts)
                    try:
                        client.stat_file(remote_path)
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        client.download_file(remote_path, str(local_path))
                        success += 1
                    except Exception as exc:
                        failed.append((str(relative), str(exc)))
            self.completed.emit(
                {
                    "success": success,
                    "failed": failed,
                    "destination": str(self.destination),
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class ElementManagementWidget(QWidget):
    """Read-only server inspection plus local maintenance of element marks."""

    catalogChanged = Signal()
    centralSyncRequested = Signal()

    HEADERS = (
        "图元定义文件",
        "w×h",
        "AlignCenter",
        "Pins",
        "标准来源",
        "分类标记",
        "备注",
        "状态",
    )

    # The table remains readable at normal window sizes, while long paths,
    # notes and status text can still grow and be inspected with the
    # horizontal scrollbar.
    TABLE_MINIMUM_WIDTHS = {
        0: 260,
        1: 78,
        2: 110,
        3: 150,
        4: 120,
        5: 110,
        6: 120,
        7: 180,
    }
    TABLE_FLEX_COLUMNS = (0, 4, 5, 6, 7)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.rows: list[dict] = []
        self.worker: ElementDefinitionWorker | None = None
        self.download_worker: ElementDownloadWorker | None = None
        self._rendering = False
        self.dirty = False
        self._admin_mode = False
        self._build_ui()
        self._load_saved_records()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(12)

        title = QLabel("图元管理")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "维护服务器图元文件与设备分类标记。进入页面只读取本地缓存，不会自动访问服务器；"
            "只有点击“刷新图元列表”才会重新读取。普通客户端可以修改并保存本机缓存；配置操作分为三个独立动作："
            "保存到本地缓存、Admin 保存并同步到中央仓库、手动同步中央配置仓库并覆盖本地共享配置。"
            "原始服务器文件只读，不会被修改。"
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        source_box = QGroupBox("图元定义来源")
        source_grid = QGridLayout(source_box)
        ssh_config = dict(self.config.get("ssh", {}) or {})
        self.server_edits = {}
        server_fields = [
            ("host", "IP / 主机", ssh_config.get("host", "172.16.21.27")),
            ("port", "端口", ssh_config.get("port", 22)),
            ("username", "用户名", ssh_config.get("username", "up8000")),
            ("password", "密码", ssh_config.get("password", "up8000")),
            (
                "element_directory",
                "远程目录",
                ssh_config.get(
                    "element_directory",
                    "/home/up8000/data/graph/element",
                ),
            ),
        ]
        for row_index, (key, label, value) in enumerate(server_fields):
            source_grid.addWidget(QLabel(label), row_index, 0)
            edit = QLineEdit(str(value))
            if key == "password":
                edit.setEchoMode(QLineEdit.Password)
            if key == "element_directory":
                edit.setPlaceholderText("/home/up8000/data/graph/element")
                self.directory_edit = edit
            self.server_edits[key] = edit
            source_grid.addWidget(edit, row_index, 1, 1, 6)

        self.test_server_button = QPushButton("测试 SSH 连接")
        self.test_server_button.clicked.connect(self.test_server_connection)
        self.save_server_button = QPushButton("保存 SSH 配置")
        self.save_server_button.clicked.connect(self.save_server_settings)
        self.load_button = QPushButton("刷新图元列表")
        self.load_button.clicked.connect(self.load_remote_definitions)
        self.download_button = QPushButton("下载所选图元")
        self.download_button.clicked.connect(self.download_selected_elements)

        self.load_saved_button = QPushButton("载入本地标记")
        self.load_saved_button.clicked.connect(self._load_saved_records)
        self.save_button = QPushButton("保存到本地缓存")
        self.save_button.setToolTip("仅保存当前图元服务器设置和图元分类标记到本机缓存，不访问中央仓库。")
        self.save_button.clicked.connect(lambda: self.save_local_cache())
        self.publish_button = QPushButton("保存并同步到中央仓库")
        self.publish_button.setToolTip("仅 Admin 可用：先保存到本地缓存，再把当前本机共享配置发布到中央仓库。")
        self.publish_button.clicked.connect(self.publish_catalog_to_central)
        # Backward-compatible attribute name used by older code/tests.
        self.sync_button = self.publish_button
        self.central_pull_button = QPushButton("同步中央配置仓库配置")
        self.central_pull_button.setToolTip("手动读取中央共享配置并覆盖本机缓存；普通客户端也可使用。")
        self.central_pull_button.clicked.connect(self.request_central_sync)
        self.import_button = QPushButton("导入共享配置")
        self.import_button.clicked.connect(self.import_shared_catalog)
        self.export_button = QPushButton("导出共享配置")
        self.export_button.clicked.connect(self.export_shared_catalog)

        self.more_actions_button = QToolButton()
        self.more_actions_button.setText("更多操作")
        self.more_actions_button.setPopupMode(QToolButton.InstantPopup)
        more_menu = QMenu(self.more_actions_button)
        self.test_server_action = more_menu.addAction(
            self.test_server_button.text(), self.test_server_connection
        )
        self.save_server_action = more_menu.addAction(
            self.save_server_button.text(), self.save_server_settings
        )
        more_menu.addSeparator()
        self.download_action = more_menu.addAction(
            self.download_button.text(), self.download_selected_elements
        )
        self.load_saved_action = more_menu.addAction(
            self.load_saved_button.text(), self._load_saved_records
        )
        more_menu.addSeparator()
        self.import_action = more_menu.addAction(
            self.import_button.text(), self.import_shared_catalog
        )
        self.export_action = more_menu.addAction(
            self.export_button.text(), self.export_shared_catalog
        )
        self.more_actions_button.setMenu(more_menu)

        actions = QHBoxLayout()
        actions.addWidget(self.load_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.publish_button)
        actions.addWidget(self.central_pull_button)
        actions.addWidget(self.more_actions_button)
        actions.addStretch()
        source_grid.addLayout(actions, 5, 1, 1, 6)

        self.status_label = QLabel("尚未手动同步服务器图元；当前仅使用本地缓存。")
        self.status_label.setWordWrap(True)
        source_grid.addWidget(self.status_label, 6, 1, 1, 6)
        layout.addWidget(source_box)

        maintain_box = QGroupBox("标记搜索")
        maintain_layout = QGridLayout(maintain_box)
        maintain_layout.addWidget(QLabel("筛选"), 0, 0)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            "输入图元文件名、完整路径、分类标记或备注"
        )
        self.filter_edit.textChanged.connect(self._apply_filter)
        maintain_layout.addWidget(self.filter_edit, 0, 1)
        layout.addWidget(maintain_box)

        self.table = QTableWidget(0, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setWordWrap(False)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(len(self.HEADERS)):
            # Start with content-sized sections, then switch to Interactive so
            # the page can fill available width and the user can resize any
            # column without losing the horizontal scrollbar.
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setStyleSheet(
            "QTableWidget {"
            "selection-background-color: #CFEBDD;"
            "selection-color: #164E3F;"
            "}"
            "QTableWidget::item:selected {"
            "background-color: #CFEBDD; color: #164E3F;"
            "}"
            "QTableWidget::item:selected:!active {"
            "background-color: #E7F5EE; color: #315B4F;"
            "}"
            "QTableWidget::item:hover {"
            "background-color: transparent; color: inherit;"
            "}"
            "QTableWidget::item:selected:hover {"
            "background-color: #CFEBDD; color: #164E3F;"
            "}"
            "QScrollBar:horizontal {"
            "background: #E6F0EC; height: 14px; margin: 2px 2px 2px 2px;"
            "border-radius: 7px;"
            "}"
            "QScrollBar::handle:horizontal {"
            "background: #7EB5A1; min-width: 42px; border-radius: 6px;"
            "}"
            "QScrollBar::handle:horizontal:hover {"
            "background: #00966E;"
            "}"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {"
            "width: 0px;"
            "}"
            "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {"
            "background: transparent;"
            "}"
        )
        self._configure_table_readability()
        self.table.itemChanged.connect(self._on_table_changed)
        layout.addWidget(self.table, 1)
        # The first layout pass happens after this method returns.  Refit
        # once the table has its real viewport width instead of the initial
        # zero-width value.
        QTimer.singleShot(0, self._fit_table_columns)
        self.set_admin_mode(False)

    def set_admin_mode(self, is_admin: bool):
        """Apply Admin ownership only to central publishing.

        All clients may edit, test, refresh, import and save configuration to
        their own local cache.  Admin ownership is required only when a
        client uploads shared configuration to the central repository.
        """
        self._admin_mode = bool(is_admin)

        # Local configuration remains fully editable for every client.
        for edit in getattr(self, "server_edits", {}).values():
            edit.setReadOnly(False)

        if hasattr(self, "table"):
            self.table.setEditTriggers(
                QAbstractItemView.DoubleClicked
                | QAbstractItemView.EditKeyPressed
                | QAbstractItemView.SelectedClicked
            )

        for name in ("save_server_button", "load_button", "save_button", "import_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setEnabled(True)
        for name in ("save_server_action", "import_action"):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(True)

        # The only Admin-only operation on this page is uploading the current
        # shared configuration to the central repository.
        if hasattr(self, "publish_button"):
            self.publish_button.setEnabled(self._admin_mode)

        if hasattr(self, "status_label") and not self._admin_mode:
            self._set_status(
                "普通客户端可修改、测试、刷新并保存本机配置，也可手动同步中央配置；"
                "只有【保存并同步到中央仓库】需要先抢占 Admin。"
            )

        self._retranslate_dynamic_ui()

    def _active_language(self) -> str:
        window = self.window()
        return str(getattr(window, "language", "zh_CN") or "zh_CN")

    def _set_status(self, text) -> None:
        """Set the dynamic status label in the active DMM language."""
        if not hasattr(self, "status_label"):
            return
        self.status_label.setText(
            translate_runtime_text(str(text or ""), self._active_language())
        )

    def _retranslate_dynamic_ui(self) -> None:
        retranslate_qt_tree(self, self._active_language())

    def _require_admin_mode(self, action_text: str) -> bool:
        if self._admin_mode:
            return True
        QMessageBox.information(
            self,
            action_text,
            "当前操作会把共享配置上传到中央仓库，只有 Admin 可以执行；请先到【设置】抢占 Admin。",
        )
        return False

    def _configure_table_readability(self):
        """Keep table content readable and responsive to app/DPI scaling."""
        if not hasattr(self, "table"):
            return
        screen = self.screen()
        dpi_scale = 1.0
        if screen is not None:
            try:
                dpi_scale = float(screen.logicalDotsPerInch()) / 96.0
            except Exception:
                dpi_scale = 1.0
        dpi_scale = max(1.0, min(dpi_scale, 2.0))

        application_font = QApplication.font()
        base_point_size = application_font.pointSizeF()
        if base_point_size <= 0:
            base_point_size = 10.0
        point_size = max(12.0, base_point_size * 1.25, 11.0 * dpi_scale)

        table_font = QFont(self.table.font())
        table_font.setPointSizeF(point_size)
        self.table.setFont(table_font)

        header_font = QFont(table_font)
        header_font.setBold(True)
        header_font.setPointSizeF(point_size + 0.5)
        header = self.table.horizontalHeader()
        header.setFont(header_font)
        header.setMinimumHeight(max(40, round(38 * dpi_scale)))
        self.table.verticalHeader().setDefaultSectionSize(
            max(38, round(36 * dpi_scale))
        )
        self.table.verticalHeader().setMinimumSectionSize(
            max(34, round(34 * dpi_scale))
        )
        self._table_dpi_scale = dpi_scale
        self._fit_table_columns()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.ScreenChangeInternal):
            self._configure_table_readability()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Recalculate only the presentation widths.  Row data and editing
        # state are deliberately left untouched when the window is resized.
        QTimer.singleShot(0, self._fit_table_columns)

    def _fit_table_columns(self):
        """Fill the visible table width without hiding long cell values."""
        if not hasattr(self, "table") or self.table.columnCount() == 0:
            return

        scale = float(getattr(self, "_table_dpi_scale", 1.0) or 1.0)
        minimums = {
            column: round(width * scale)
            for column, width in self.TABLE_MINIMUM_WIDTHS.items()
        }

        header = self.table.horizontalHeader()
        header.setUpdatesEnabled(False)
        try:
            # Content sizing is done only when rows are rendered.  During a
            # resize we preserve those widths and only add spare space.
            for column, minimum in minimums.items():
                if self.table.columnWidth(column) < minimum:
                    self.table.setColumnWidth(column, minimum)

            available = max(0, self.table.viewport().width())
            current_total = sum(
                self.table.columnWidth(column)
                for column in range(self.table.columnCount())
            )
            extra = available - current_total
            if extra <= 0:
                return

            flex_columns = [
                column
                for column in self.TABLE_FLEX_COLUMNS
                if column < self.table.columnCount()
            ]
            if not flex_columns:
                flex_columns = list(range(self.table.columnCount()))

            # Give long textual fields most of the spare width, while keeping
            # numeric metadata compact.
            weights = {0: 4, 4: 3, 5: 2, 6: 2, 7: 3}
            total_weight = sum(weights.get(column, 1) for column in flex_columns)
            for index, column in enumerate(flex_columns):
                if index == len(flex_columns) - 1:
                    addition = extra
                else:
                    addition = round(extra * weights.get(column, 1) / total_weight)
                    addition = min(addition, extra)
                self.table.setColumnWidth(
                    column,
                    self.table.columnWidth(column) + addition,
                )
                extra -= addition
                total_weight -= weights.get(column, 1)
                if total_weight <= 0:
                    total_weight = 1
        finally:
            header.setUpdatesEnabled(True)

    def _current_element_ssh_config(self) -> dict:
        """Read and validate the SSH settings shown on this page."""
        values = {
            key: edit.text().strip()
            for key, edit in self.server_edits.items()
        }
        try:
            values["port"] = int(values.get("port") or 22)
        except Exception as exc:
            raise ValueError("SSH 端口必须是整数。") from exc
        if not 1 <= values["port"] <= 65535:
            raise ValueError("SSH 端口必须在 1~65535 之间。")
        if not values.get("host"):
            raise ValueError("SSH IP / 主机不能为空。")
        if not values.get("username"):
            raise ValueError("SSH 用户名不能为空。")
        if not values.get("element_directory"):
            raise ValueError("远程图元目录不能为空。")

        config = dict(self.config.get("ssh", {}) or {})
        config.update(
            {
                "host": values["host"],
                "port": values["port"],
                "username": values["username"],
                "password": values.get("password", ""),
                "element_directory": values["element_directory"],
            }
        )
        return config

    def _save_element_ssh_config(self, config: dict):
        saved = dict(self.config.get("ssh", {}) or {})
        saved.update(config)
        self.config["ssh"] = saved
        save_settings(self.config)

    def test_server_connection(self):
        try:
            config = self._current_element_ssh_config()
            self._set_status("正在测试图元服务器 SSH/SFTP 只读连接……")
            with ReadOnlySshClient(
                config["host"],
                config["port"],
                config["username"],
                config["password"],
            ) as client:
                client.test_connection()
            self._save_element_ssh_config(config)
            self._set_status(
                "图元服务器 SSH/SFTP 连接正常；远程图元文件为只读。"
            )
        except Exception as exc:
            self._set_status(f"图元服务器连接失败：{exc}")
            QMessageBox.warning(self, "图元服务器连接失败", str(exc))

    def save_server_settings(self):
        try:
            config = self._current_element_ssh_config()
            self._save_element_ssh_config(config)
            self._set_status(
                "图元服务器 SSH 配置已保存；下次启动将自动恢复。"
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存图元服务器配置失败", str(exc))

    def _refresh_server_info(self):
        """Refresh the SSH fields after the shared SSH settings change."""
        config = dict(self.config.get("ssh", {}) or {})
        defaults = {
            "host": "172.16.21.27",
            "port": 22,
            "username": "up8000",
            "password": "up8000",
            "element_directory": "/home/up8000/data/graph/element",
        }
        for key, default in defaults.items():
            edit = self.server_edits.get(key)
            if edit is not None:
                edit.setText(str(config.get(key, default)))

    def refresh_server_info(self):
        """Refresh the endpoint fields after SSH settings are changed."""
        if hasattr(self, "server_edits"):
            self._refresh_server_info()

    def reload_local_cache(self):
        """Reload server fields and element marks from the in-memory local cache."""
        self._refresh_server_info()
        self._load_saved_records()

    def _catalog(self) -> dict:
        catalog = self.config.get("element_catalog", {})
        return catalog if isinstance(catalog, dict) else {}

    def _canonicalize_record_path(self, record: dict) -> dict:
        """Normalize legacy absolute paths to the configured relative path.

        Older caches may contain both
        ``/home/.../element/breaker_dis/Fuse...g`` and
        ``breaker_dis/Fuse...g``.  They identify the same server file and
        must therefore be merged before the table is rendered.
        """
        row = _record_with_defaults(record)
        value = str(row.get("file_key") or row.get("file_name") or "").strip()
        value = value.replace("\\", "/")
        directory = str(getattr(self, "directory_edit", None).text() if hasattr(self, "directory_edit") else "")
        directory = directory.strip().replace("\\", "/").rstrip("/")
        prefix = f"{directory}/" if directory else ""
        if prefix and value.casefold().startswith(prefix.casefold()):
            value = value[len(prefix):]
        value = _normalize_element_path(value)
        if value:
            row["file_key"] = value
            row["file_name"] = PurePosixPath(value).name
        return row

    def _load_saved_records(self):
        records = self._catalog().get("records", [])
        records = [self._canonicalize_record_path(record) for record in records]
        self.rows = _merge_duplicate_records(records)
        self.dirty = False
        self._render_rows()
        self._set_status(
            f"已载入本地缓存：{len(self.rows)} 条（相同图元路径已合并）；不会自动访问服务器。"
        )

    def load_remote_definitions(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self.dirty:
            answer = QMessageBox.question(
                self,
                "重新读取图元定义",
                "当前有未保存的图元标记修改，重新读取会刷新表格。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        try:
            ssh_config = self._current_element_ssh_config()
        except Exception as exc:
            QMessageBox.warning(self, "读取图元定义", str(exc))
            return
        directory = ssh_config["element_directory"]
        self.load_button.setEnabled(False)
        self._set_status("正在读取服务器图元文件列表，请稍候……")
        worker = ElementDefinitionWorker(ssh_config, directory, self)
        self.worker = worker
        worker.loaded.connect(self._on_remote_loaded)
        worker.failed.connect(self._on_remote_failed)
        worker.finished.connect(lambda: self.load_button.setEnabled(self._admin_mode))
        worker.finished.connect(self._clear_worker)
        worker.start()

    def _clear_worker(self):
        self.worker = None

    def _selected_element_rows(self) -> list[dict]:
        selected = []
        for index in self.table.selectionModel().selectedRows():
            row_index = index.row()
            if 0 <= row_index < len(self.rows):
                selected.append(self.rows[row_index])
        return selected

    def download_selected_elements(self):
        if self.download_worker is not None and self.download_worker.isRunning():
            return
        rows = self._selected_element_rows()
        if not rows:
            QMessageBox.information(
                self,
                "下载所选图元",
                "请先在下方表格中选择至少一个图元文件。",
            )
            return
        try:
            config = self._current_element_ssh_config()
        except Exception as exc:
            QMessageBox.warning(self, "下载图元", str(exc))
            return

        start_path = str(self.config.get("last_folder_path") or Path.home())
        destination = QFileDialog.getExistingDirectory(
            self,
            "选择图元下载目录",
            start_path,
        )
        if not destination:
            return

        self.download_button.setEnabled(False)
        self._set_status(f"正在下载 {len(rows)} 个图元文件，请稍候……")
        worker = ElementDownloadWorker(
            config,
            config["element_directory"],
            rows,
            destination,
            self,
        )
        self.download_worker = worker
        worker.completed.connect(self._on_element_download_completed)
        worker.failed.connect(self._on_element_download_failed)
        worker.finished.connect(lambda: self.download_button.setEnabled(True))
        worker.finished.connect(self._clear_download_worker)
        worker.start()

    def _clear_download_worker(self):
        self.download_worker = None

    def _on_element_download_completed(self, result: dict):
        success = int(result.get("success", 0))
        failed = list(result.get("failed", []) or [])
        destination = result.get("destination", "")
        message = f"成功下载 {success} 个，失败 {len(failed)} 个。\n保存目录：{destination}"
        if failed:
            details = "\n".join(f"- {name}: {error}" for name, error in failed[:8])
            message += f"\n\n失败详情：\n{details}"
        self.config["last_folder_path"] = str(destination)
        save_settings(self.config)
        self._set_status(message.replace("\n", "<br>"))
        QMessageBox.information(self, "图元下载完成", message)

    def _on_element_download_failed(self, message: str):
        self._set_status(f"图元下载失败：{message}")
        QMessageBox.warning(self, "图元下载失败", message)

    def _on_remote_failed(self, message: str):
        self._set_status(f"读取失败：{message}")
        QMessageBox.warning(self, "读取图元定义失败", message)

    def _on_remote_loaded(self, rows: list):
        remote_count = len(rows or [])
        rows = _merge_duplicate_records(
            self._canonicalize_record_path(row) for row in rows
        )
        saved_records = _merge_duplicate_records(
            self._canonicalize_record_path(record)
            for record in self._catalog().get("records", [])
        )
        saved_by_identity = {
            _record_identity(record): record
            for record in saved_records
            if _record_identity(record)
        }
        current_identities = set()
        matched_saved_identities = set()
        merged = []
        changed_files = []
        for row in rows:
            row = _record_with_defaults(row)
            identity = _record_identity(row)
            current_identities.add(identity)
            saved = saved_by_identity.get(identity)
            if saved:
                if _record_identity(saved):
                    matched_saved_identities.add(_record_identity(saved))
                changed = _definition_changed(saved, row)
                row = _merge_server_metadata(saved, row)
                if changed:
                    row["status"] = "服务器图元已更新（本地标记已保留，请确认）"
                    changed_files.append(row.get("file_key") or row.get("file_name"))
                else:
                    row["status"] = "本地缓存与服务器一致"
            else:
                row["status"] = "服务器新增图元（待标记）"
            merged.append(row)

        missing = [
            record
            for record in saved_records
            if _record_identity(record)
            and _record_identity(record) not in current_identities
            and _record_identity(record) not in matched_saved_identities
        ]
        deleted_missing = False
        if missing:
            missing_text = "\n".join(
                f"- {record.get('file_key') or record.get('file_name')}"
                for record in missing[:12]
            )
            suffix = "\n……" if len(missing) > 12 else ""
            answer = QMessageBox.question(
                self,
                "服务器图元已不存在",
                f"发现 {len(missing)} 个本地标记对应的图元已从服务器消失：\n"
                f"{missing_text}{suffix}\n\n是否删除这些本地标记？选择“否”将保留并标记为服务器不存在。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            deleted_missing = answer == QMessageBox.Yes
            if not deleted_missing:
                for record in missing:
                    record["status"] = "服务器不存在（本地标记已保留）"
                    record["missing_on_server"] = True
                    merged.append(record)

        self.rows = merged
        self.dirty = True
        self._render_rows()
        try:
            self.save_catalog()
            auto_saved = True
        except Exception as exc:
            auto_saved = False
            self._set_status(f"服务器读取完成，但本地自动保存失败：{exc}")
        if remote_count != len(rows):
            messages = [
                f"已读取服务器图元文件：{remote_count} 条，按相对路径去重后 {len(rows)} 条。"
            ]
        else:
            messages = [f"已读取服务器图元文件：{len(rows)} 条。"]
        if changed_files:
            messages.append(
                f"检测到 {len(changed_files)} 个图元属性或内容更新，原有备注和标记已保留。"
            )
        if missing:
            messages.append(
                f"服务器消失 {len(missing)} 个；"
                + ("已删除本地标记。" if deleted_missing else "已保留并标记。")
            )
        if auto_saved:
            messages.append("本次服务器结果和标记已自动保存到本地缓存；下次打开不会自动访问服务器。")
        else:
            messages.append("请点击“保存图元标记”重试本地保存。")
        self._set_status("\n".join(messages))

    def _item(self, value, editable=False):
        item = QTableWidgetItem(str(value or ""))
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _display_file_path(self, row: dict) -> str:
        relative = str(row.get("file_key") or row.get("file_name") or "").strip()
        directory = self.directory_edit.text().strip().rstrip("/")
        relative = relative.replace("\\", "/")
        if directory:
            normalized_directory = directory.replace("\\", "/")
            prefix = normalized_directory + "/"
            if relative.startswith(prefix):
                relative = relative[len(prefix):]
        if relative.startswith("/"):
            remote_path = str(row.get("remote_path") or "").strip()
            remote_path = remote_path.replace("\\", "/")
            prefix = directory.replace("\\", "/").rstrip("/") + "/"
            if prefix and remote_path.startswith(prefix):
                relative = remote_path[len(prefix):]
        return relative

    def _render_rows(self):
        # Apply the same normalization at render time as a final guard for
        # older in-memory caches.  This prevents two visually identical rows
        # from appearing when one path contains hidden whitespace or Unicode
        # path differences.
        self.rows = _merge_duplicate_records(
            self._canonicalize_record_path(row) for row in self.rows
        )
        self._rendering = True
        self.table.setRowCount(0)
        for row_index, row in enumerate(self.rows):
            row = _record_with_defaults(row)
            self.rows[row_index] = row
            self.table.insertRow(row_index)

            full_path = self._display_file_path(row)
            file_item = self._item(full_path)
            file_item.setToolTip(full_path)
            file_item.setData(Qt.UserRole, row.get("element_key", ""))
            self.table.setItem(row_index, 0, file_item)
            self.table.setItem(
                row_index,
                1,
                self._item(
                    f"{row.get('width')}×{row.get('height')}"
                    if row.get("width") or row.get("height")
                    else "-"
                ),
            )
            self.table.setItem(
                row_index,
                2,
                self._item(row.get("align_center") or "-"),
            )
            self.table.setItem(
                row_index,
                3,
                self._item(row.get("pins") or "-"),
            )
            self.table.setItem(
                row_index,
                4,
                self._item(self._source_text(row)),
            )
            self.table.setItem(
                row_index,
                5,
                self._item(row.get("classification"), editable=True),
            )
            self.table.setItem(
                row_index,
                6,
                self._item(row.get("remark"), editable=True),
            )
            status_item = self._item(self._status_text(row))
            status_item.setToolTip(str(row.get("status") or ""))
            self.table.setItem(row_index, 7, status_item)
        self._rendering = False
        self._apply_filter(self.filter_edit.text())
        self.table.resizeColumnsToContents()
        scale = float(getattr(self, "_table_dpi_scale", 1.0) or 1.0)
        for column, minimum in self.TABLE_MINIMUM_WIDTHS.items():
            scaled_minimum = round(minimum * scale)
            if self.table.columnWidth(column) < scaled_minimum:
                self.table.setColumnWidth(column, scaled_minimum)
        self.table.resizeRowsToContents()
        self._fit_table_columns()
        self._retranslate_dynamic_ui()

    def _apply_filter(self, text: str):
        needle = str(text or "").strip().casefold()
        for row_index in range(self.table.rowCount()):
            values = [
                self.table.item(row_index, column).text()
                for column in range(self.table.columnCount())
                if self.table.item(row_index, column) is not None
            ]
            self.table.setRowHidden(
                row_index,
                bool(needle) and needle not in " ".join(values).casefold(),
            )

    @staticmethod
    def _source_text(row: dict) -> str:
        source = str(row.get("source") or "").strip().upper()
        if source == "SSH":
            return "服务器图元库"
        if source:
            return source
        if row.get("missing_on_server"):
            return "本地缓存"
        return "-"

    @staticmethod
    def _status_text(row: dict) -> str:
        raw = str(row.get("status") or "").strip()
        if row.get("missing_on_server"):
            return "MISSING · 服务器不存在"
        if raw == "本地缓存与服务器一致":
            return "READY · 服务器已同步"
        if raw == "服务器新增图元（待标记）":
            return "NEW · 待标记"
        if raw.startswith("服务器图元已更新"):
            return "UPDATED · 请确认"
        if raw.startswith("读取失败"):
            return "ERROR · 读取失败"
        if raw.startswith("已读取（属性解析失败"):
            return "WARN · 属性解析失败"
        if raw == "已读取":
            return "READY · 服务器已读取"
        if raw == "已保存标记":
            return "LOCAL · 已保存标记"
        return raw or "-"

    def _sync_rows_from_table(self):
        for row_index, row in enumerate(self.rows):
            if row_index >= self.table.rowCount():
                break
            row["classification"] = self.table.item(row_index, 5).text().strip()
            row["remark"] = self.table.item(row_index, 6).text().strip()

    def _on_table_changed(self, _item):
        if self._rendering or not self._admin_mode:
            return
        self.dirty = True
        answer = QMessageBox.question(
            self,
            "保存图元标记修改",
            "检测到图元分类标记或备注发生变化，是否立即保存到本机？\n\n"
            "保存后，后续模型校验会使用新的标记。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            try:
                self.save_catalog()
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "保存图元标记失败",
                    f"修改已保留在当前页面，但保存到本机失败：\n{exc}",
                )
        else:
            self._set_status(
                "有未保存的图元标记修改；模型校验仍会使用上一次已保存的配置。"
            )

    def request_central_sync(self):
        """Request an explicit central pull; this never runs automatically."""
        if self.dirty:
            answer = QMessageBox.question(
                self,
                "同步中央配置仓库配置",
                "当前有未保存的图元标记修改。同步中央仓库会用中央共享配置覆盖本机缓存，"
                "当前未保存修改也会丢失。是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self._set_status("正在手动同步中央配置仓库，请稍候……")
        self.centralSyncRequested.emit()

    def save_local_cache(self, *, show_status=True):
        """Save the visible element-server settings and marks locally only."""
        try:
            ssh_config = self._current_element_ssh_config()
            self._sync_rows_from_table()
            self.config["ssh"] = ssh_config
            self.config["element_catalog"] = {
                "remote_directory": self.directory_edit.text().strip(),
                "records": [dict(row) for row in self.rows],
            }
            save_settings(self.config)
            self.dirty = False
            if show_status:
                self._set_status(
                    f"已保存图元服务器配置和 {len(self.rows)} 条图元标记到本机缓存；未访问中央仓库。"
                )
            self.catalogChanged.emit()
            return True
        except Exception as exc:
            QMessageBox.warning(self, "保存到本地缓存失败", str(exc))
            return False

    def save_catalog(self, sync_central=False):
        """Save element classifications to this client's local cache."""
        self._sync_rows_from_table()
        self.config.setdefault("ssh", {})["element_directory"] = (
            self.directory_edit.text().strip()
        )
        self.config["element_catalog"] = {
            "remote_directory": self.directory_edit.text().strip(),
            "records": [dict(row) for row in self.rows],
        }
        save_settings(self.config)
        self.dirty = False
        self._set_status(
            f"已保存 {len(self.rows)} 条图元标记到本机缓存。后续模型识别会按图元文件标识匹配。"
        )
        self.catalogChanged.emit()

    def publish_catalog_to_central(self):
        """Admin-only: save locally, then explicitly publish to central."""
        if not self._require_admin_mode("保存并同步到中央仓库"):
            return
        if not self.save_local_cache(show_status=False):
            return
        try:
            # No prior central read is required. This explicit action contacts
            # the server, which verifies Admin ownership/epoch before accepting data.
            version = publish_central_settings(self.config)
            save_settings(self.config)
            self._set_status(
                f"已保存到本机缓存，并已同步到中央仓库（版本 {version}，图元标记 {len(self.rows)} 条）。"
            )
        except Exception as exc:
            QMessageBox.warning(self, "中央配置发布失败", str(exc))

    def export_shared_catalog(self):
        self._sync_rows_from_table()
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "导出图元共享配置",
            "element_marks.json",
            "JSON 配置 (*.json)",
        )
        if not path:
            return
        payload = {
            "schema": "element-marks",
            "version": 1,
            "description": "Portable element classification marks",
            "records": [_portable_record(row) for row in self.rows],
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "导出共享配置失败", str(exc))
            return
        self._set_status(
            f"已导出 {len(self.rows)} 条图元标记共享配置；文件不包含 SSH 主机、用户名和密码。"
        )

    def import_shared_catalog(self):
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "导入图元共享配置",
            "",
            "JSON 配置 (*.json)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            records = _portable_import_records(payload)
        except Exception as exc:
            QMessageBox.warning(self, "导入共享配置失败", str(exc))
            return

        current_by_identity = {
            _record_identity(row): row
            for row in self.rows
            if _record_identity(row)
        }
        imported = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            incoming = self._canonicalize_record_path(record)
            identity = _record_identity(incoming)
            target = current_by_identity.get(identity)
            if target is None:
                resolved = resolve_element_record(
                    incoming.get("element_key") or incoming.get("file_key", ""),
                    {"records": self.rows},
                )
                if resolved:
                    target = next(
                        (
                            row
                            for row in self.rows
                            if row.get("element_key") == resolved.get("element_key")
                            or row.get("file_key") == resolved.get("file_key")
                            or row.get("file_name") == resolved.get("file_name")
                        ),
                        None,
                    )
            if target is None:
                target = incoming
                target["status"] = "共享配置标记，待读取服务器定义"
                self.rows.append(target)
                current_by_identity[identity] = target
            for key in (
                "classification",
                "remark",
            ):
                target[key] = incoming.get(key, target.get(key, ""))
            if incoming.get("definition_hash"):
                target["definition_hash"] = incoming["definition_hash"]
            imported += 1

        self.dirty = True
        self._render_rows()
        self._set_status(
            f"已导入 {imported} 条共享标记，等待确认保存到本机。"
        )
        answer = QMessageBox.question(
            self,
            "保存共享图元标记",
            f"已导入 {imported} 条图元标记，是否立即保存到本机？\n\n"
            "保存后，模型校验才能使用这些标记。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer == QMessageBox.Yes:
            try:
                self.save_catalog()
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    "保存图元标记失败",
                    f"共享配置已导入，但保存到本机失败：\n{exc}",
                )
