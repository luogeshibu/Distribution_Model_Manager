from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QEventLoop, QThread, QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.services.paths import app_cache_root, default_workspace
from g_file_studio.services.remote_g_source import (
    DEFAULT_SSH_PORT,
    ReadOnlySshClient,
    RemoteGFile,
    download_stable_files,
    human_size,
)
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.widgets.help_widgets import set_secondary
from g_file_studio.ui.table_layout import apply_graphics_table_selection_style
from g_file_studio.ui.widgets.wheel_safe_line_edit import WheelSafeLineEdit
from g_file_studio.workers import FunctionWorker


_CACHE_SCHEMA = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_cache_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "remote").strip())
    return safe.strip("._") or "remote"


class RemoteGSourceWidget(QWidget):
    """Unified read-only SSH/SFTP G source with local-first per-module caching.

    Important runtime rules:
    * opening a module never contacts SSH;
    * each module restores its own last successful remote file-list cache, but never
      restores the previous application session's checked-file selection;
    * only an explicit ``刷新 G 文件列表`` contacts SSH and the successful result
      atomically replaces that module's local cache;
    * SSH connection/list/download work is never executed directly on the GUI thread;
    * processing snapshots are reused locally when the selected server metadata has
      not changed since the last successful download.
    """

    selectionChanged = Signal()
    prepared = Signal(str)
    connectionSettingsRequested = Signal()

    def __init__(
        self,
        *,
        settings_prefix: str,
        settings_service: UserSettingsService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings_prefix = settings_prefix
        self.settings_service = settings_service or UserSettingsService()
        self._files: list[RemoteGFile] = []
        self._prepared_dir = default_workspace() / "remote_input" / settings_prefix
        self._cached_selected_paths: set[str] = set()
        self._loaded_cache_signature: dict[str, object] | None = None
        self._table_materialized = False
        self._test_worker: FunctionWorker | None = None
        self._list_worker: FunctionWorker | None = None
        self._download_worker: FunctionWorker | None = None
        self._worker_pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Compatibility editors remain hidden on business pages. They mirror the
        # global Connection & Environment settings and keep the legacy API stable.
        self.host = WheelSafeLineEdit(self._saved("host", ""))
        self.port = WheelSafeLineEdit(self._saved("port", str(DEFAULT_SSH_PORT)))
        self.username = WheelSafeLineEdit(self._saved("username", ""))
        self.password = WheelSafeLineEdit(self._saved("password", ""))
        self.password.setEchoMode(WheelSafeLineEdit.EchoMode.Password)
        self.remote_dir = WheelSafeLineEdit(self._saved("remote_directory", ""))
        for editor in (self.host, self.port, self.username, self.password, self.remote_dir):
            editor.setVisible(False)
            editor.editingFinished.connect(self._persist_silently)

        source_card = QWidget()
        source_card.setObjectName("remoteSourceSummary")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(12, 10, 12, 10)
        source_layout.setSpacing(6)
        top_row = QHBoxLayout()
        self.environment_label = QLabel()
        self.environment_label.setObjectName("sectionCaption")
        top_row.addWidget(self.environment_label, 1)
        self.connection_settings_button = QPushButton("连接设置")
        set_secondary(self.connection_settings_button)
        self.connection_settings_button.clicked.connect(self.connectionSettingsRequested.emit)
        top_row.addWidget(self.connection_settings_button)
        source_layout.addLayout(top_row)
        self.connection_summary = QLabel()
        self.connection_summary.setObjectName("mutedText")
        self.connection_summary.setWordWrap(True)
        source_layout.addWidget(self.connection_summary)
        self.directory_summary = QLabel()
        self.directory_summary.setObjectName("mutedText")
        self.directory_summary.setWordWrap(True)
        source_layout.addWidget(self.directory_summary)
        root.addWidget(source_card)

        actions = QHBoxLayout()
        self.test_button = QPushButton("测试 SSH 连接")
        self.save_button = QPushButton("保存 SSH 设置")
        self.test_button.clicked.connect(self.test_connection)
        self.save_button.clicked.connect(self.save_settings)
        self.test_button.setVisible(False)
        self.save_button.setVisible(False)
        self.refresh_button = QPushButton("刷新 G 文件列表")
        self.download_button = QPushButton("下载所选到本地…")
        set_secondary(self.refresh_button)
        set_secondary(self.download_button)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.download_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self.status = QLabel("尚未加载远程文件。")
        self.status.setWordWrap(True)
        self.status.setObjectName("mutedText")
        root.addWidget(self.status)

        notice = QLabel(
            "SSH 服务器严格只读：仅列目录、读取文件属性和下载 G 文件；"
            "G File Studio 不提供上传、覆盖、重命名、删除、移动、新建或修改服务器内容的接口。"
        )
        notice.setWordWrap(True)
        notice.setObjectName("infoBanner")
        root.addWidget(notice)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索 G 文件"))
        self.search = WheelSafeLineEdit()
        self.search.setPlaceholderText("例如：ABH-06、JED-NTH、B412")
        search_row.addWidget(self.search, 1)
        self.count_label = QLabel("尚未加载远程文件")
        search_row.addWidget(self.count_label)
        root.addLayout(search_row)

        select_row = QHBoxLayout()
        self.select_visible = QPushButton("全选当前结果")
        self.clear_selection = QPushButton("清空全部")
        for btn in (self.select_visible, self.clear_selection):
            set_secondary(btn)
            select_row.addWidget(btn)
        select_row.addStretch(1)
        root.addLayout(select_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["选择", "文件名", "大小", "服务器修改时间"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 420)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 180)
        self.table.setMinimumHeight(230)
        apply_graphics_table_selection_style(self.table)
        root.addWidget(self.table)

        self.refresh_button.clicked.connect(self.refresh_files)
        self.download_button.clicked.connect(self.download_selected_to_local)
        self.search.textChanged.connect(self._apply_filter)
        self.select_visible.clicked.connect(lambda: self._set_visible_checked(True))
        self.clear_selection.clicked.connect(self._clear_all)
        self.table.itemChanged.connect(self._item_changed)

        # LOCAL ONLY: construction never reaches the network. Read one small JSON
        # cache and defer table-row creation until the widget is actually visible.
        self.refresh_shared_settings(reload_cache=False)
        self._load_cached_file_list(render=False)

    def _key(self, suffix: str) -> str:
        return f"remote_g_source/{suffix}"

    def _saved(self, suffix: str, default: str) -> str:
        return str(self.settings_service.get_value(self._key(suffix), default))

    def persist(self) -> None:
        self.settings_service.set_value(self._key("host"), self.host.text().strip())
        self.settings_service.set_value(self._key("port"), self.port.text().strip())
        self.settings_service.set_value(self._key("username"), self.username.text().strip())
        self.settings_service.set_value(self._key("password"), self.password.text())
        self.settings_service.set_value(self._key("remote_directory"), self.remote_dir.text().strip())

    def _persist_silently(self) -> None:
        self.persist()

    def save_settings(self) -> None:
        """Backward-compatible explicit save; global UI should normally own edits."""
        try:
            self.config()
            self.persist()
            self.status.setText("SSH 设置已保存；所有使用 SSH 文件源的模块将复用这组最后输入。")
            self.refresh_shared_settings()
        except Exception as exc:
            QMessageBox.warning(self, "保存 SSH 设置失败", str(exc))

    def _restore_shared_settings(self) -> None:
        values = (
            (self.host, self._saved("host", "")),
            (self.port, self._saved("port", str(DEFAULT_SSH_PORT))),
            (self.username, self._saved("username", "")),
            (self.password, self._saved("password", "")),
            (self.remote_dir, self._saved("remote_directory", "")),
        )
        for editor, value in values:
            if not editor.hasFocus() and editor.text() != value:
                editor.setText(value)

    def refresh_shared_settings(self, *, reload_cache: bool = True) -> None:
        previous = self._loaded_cache_signature
        self._restore_shared_settings()
        cfg = self.config()
        self.environment_label.setText("共享连接配置")
        self.connection_summary.setText(
            f"文件服务器：{cfg['host']}:{cfg['port']} · 用户 {cfg['username']} · 严格只读"
        )
        self.directory_summary.setText(f"业务 G 根目录：{cfg['remote_directory']}")
        if reload_cache and previous is not None and previous != self._endpoint_signature(cfg):
            # A manual/global connection change must never leave rows from the old
            # endpoint visible. Load a matching local snapshot if one exists.
            self._load_cached_file_list(render=self.isVisible())

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API naming
        self.refresh_shared_settings()
        if self._files and not self._table_materialized:
            self._rebuild_table(self._cached_selected_paths)
        super().showEvent(event)

    def config(self) -> dict[str, object]:
        try:
            port = int(self.port.text().strip())
        except ValueError as exc:
            raise ValueError("SSH 端口必须是整数。") from exc
        return {
            "host": self.host.text().strip(),
            "port": port,
            "username": self.username.text().strip(),
            "password": self.password.text(),
            "remote_directory": self.remote_dir.text().strip(),
        }

    @staticmethod
    def _endpoint_signature(cfg: dict[str, object]) -> dict[str, object]:
        return {
            "host": str(cfg.get("host", "")).strip(),
            "port": int(cfg.get("port", DEFAULT_SSH_PORT)),
            "username": str(cfg.get("username", "")).strip(),
            "remote_directory": str(cfg.get("remote_directory", "")).strip(),
        }

    def _cache_file_path(self) -> Path:
        return app_cache_root() / "RemoteGSource" / f"{_safe_cache_name(self.settings_prefix)}.json"

    def _snapshot_manifest_path(self) -> Path:
        return self._prepared_dir / ".gfs_remote_snapshot.json"

    def _selected_path_set(self) -> set[str]:
        if self._table_materialized:
            return {item.remote_path for item in self.selected_files()}
        return set(self._cached_selected_paths)

    def _load_cached_file_list(self, *, render: bool) -> bool:
        path = self._cache_file_path()
        cfg = self.config()
        signature = self._endpoint_signature(cfg)
        self._files = []
        self._cached_selected_paths = set()
        self._loaded_cache_signature = signature
        self._table_materialized = False
        if not path.is_file():
            if render:
                self.table.setRowCount(0)
                self.count_label.setText("本模块尚无本地服务器文件列表缓存")
            self.status.setText("本模块尚无本地缓存；点击“刷新 G 文件列表”才会访问服务器。")
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.status.setText("本模块本地服务器文件列表缓存损坏；请手动刷新覆盖缓存。")
            if render:
                self.table.setRowCount(0)
            return False
        cached_signature = payload.get("endpoint") if isinstance(payload, dict) else None
        if not isinstance(cached_signature, dict) or cached_signature != signature:
            self.status.setText("当前连接配置与本模块缓存不一致；请手动刷新后覆盖本地缓存。")
            if render:
                self.table.setRowCount(0)
                self.count_label.setText("当前连接没有匹配的本地缓存")
            return False
        rows = payload.get("files", []) if isinstance(payload, dict) else []
        files: list[RemoteGFile] = []
        if isinstance(rows, list):
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                remote_path = str(raw.get("remote_path", "") or "").strip()
                name = str(raw.get("name", "") or "").strip()
                if not remote_path or not name.lower().endswith(".g"):
                    continue
                try:
                    files.append(
                        RemoteGFile(
                            name=name,
                            remote_path=remote_path,
                            size=int(raw.get("size", 0) or 0),
                            mtime_epoch=int(raw.get("mtime_epoch", 0) or 0),
                        )
                    )
                except (TypeError, ValueError):
                    continue
        files.sort(key=lambda item: item.name.casefold())
        # File-list cache is persistent; checkbox selection is session-only.
        # Older cache schemas may contain selected_paths, but intentionally ignore
        # them so every new application process starts with zero checked G files.
        self._files = files
        self._cached_selected_paths = set()
        updated_at = str(payload.get("updated_at", "") or "") if isinstance(payload, dict) else ""
        self.status.setText(
            f"已从本机缓存恢复 {len(files)} 个服务器 G 文件；不会自动访问服务器。"
            + (f" 缓存时间：{updated_at}" if updated_at else "")
        )
        if render:
            self._rebuild_table(self._cached_selected_paths)
        else:
            self.count_label.setText(f"本地缓存 {len(files)} 个文件；打开本模块后显示")
        return True

    def _save_file_list_cache(self) -> None:
        if self._loaded_cache_signature is None:
            return
        path = self._cache_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": _CACHE_SCHEMA,
            "kind": "GFileStudio per-module remote G file-list cache",
            "module": self.settings_prefix,
            "updated_at": _utc_now(),
            "endpoint": dict(self._loaded_cache_signature),
            # Keep the field empty for backward compatibility with older cache readers.
            # User checkbox selection must never persist across application restarts.
            "selected_paths": [],
            "files": [
                {
                    "name": item.name,
                    "remote_path": item.remote_path,
                    "size": int(item.size),
                    "mtime_epoch": int(item.mtime_epoch),
                }
                for item in self._files
            ],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _worker_error_message(details: object) -> str:
        text = str(details or "未知错误")
        return text.split("\n\n---TRACEBACK---", 1)[0].strip() or "未知错误"

    def test_connection(self) -> bool:
        if self._test_worker is not None:
            return False
        try:
            self._restore_shared_settings()
            cfg = dict(self.config())
        except Exception as exc:
            QMessageBox.warning(self, "SSH 连接失败", str(exc))
            return False

        def task(*, log, progress):
            progress(5)
            with ReadOnlySshClient(
                str(cfg["host"]), int(cfg["port"]), str(cfg["username"]), str(cfg["password"])
            ) as client:
                client.test_connection()
            progress(100)
            return cfg

        worker = FunctionWorker(task)
        self._test_worker = worker
        self.test_button.setEnabled(False)
        self.status.setText("正在后台测试 SSH/SFTP 连接…界面可继续操作。")

        def done(_result: object) -> None:
            self.status.setText(
                f"SSH/SFTP 连接正常：{cfg['host']}:{cfg['port']}；远程文件源为只读。"
            )

        def failed(details: str) -> None:
            message = self._worker_error_message(details)
            self.status.setText(f"SSH/SFTP 连接失败：{message}")
            QMessageBox.warning(self, "SSH 连接失败", message)

        def finished() -> None:
            self._test_worker = None
            self.test_button.setEnabled(True)

        worker.signals.result.connect(done)
        worker.signals.error.connect(failed)
        worker.signals.finished.connect(finished)
        self._worker_pool.start(worker)
        return True

    def refresh_files(self) -> bool:
        """Manually fetch the server list in a worker and REPLACE local cache."""
        if self._list_worker is not None:
            return False
        try:
            self._restore_shared_settings()
            cfg = dict(self.config())
        except Exception as exc:
            QMessageBox.warning(self, "远程文件列表加载失败", str(exc))
            return False
        signature = self._endpoint_signature(cfg)
        previous_checked = self._selected_path_set()

        def task(*, log, progress):
            progress(5)
            with ReadOnlySshClient(
                str(cfg["host"]), int(cfg["port"]), str(cfg["username"]), str(cfg["password"])
            ) as client:
                files = client.list_g_files(str(cfg["remote_directory"]))
            progress(100)
            return files

        worker = FunctionWorker(task)
        self._list_worker = worker
        self.refresh_button.setEnabled(False)
        self.status.setText("正在后台读取服务器 G 文件列表…不会阻塞界面。")

        def done(result: object) -> None:
            # Do not apply a result to a connection that changed while the request ran.
            if self._endpoint_signature(self.config()) != signature:
                self.status.setText("连接配置在刷新过程中已变化；本次服务器结果未写入本地缓存。")
                return
            files = [item for item in (result if isinstance(result, list) else []) if isinstance(item, RemoteGFile)]
            self._files = files
            self._loaded_cache_signature = signature
            valid_paths = {item.remote_path for item in files}
            self._cached_selected_paths = previous_checked & valid_paths
            self._rebuild_table(self._cached_selected_paths)
            # Successful manual pull is authoritative for this module: atomic replace.
            self._save_file_list_cache()
            self.status.setText(
                f"服务器文件列表已手动刷新：{len(files)} 个 .g 文件；已覆盖本模块本地缓存。"
            )

        def failed(details: str) -> None:
            message = self._worker_error_message(details)
            self.status.setText(f"读取远程 G 文件列表失败：{message}；继续保留现有本地缓存。")
            QMessageBox.warning(self, "远程文件列表加载失败", message)

        def finished() -> None:
            self._list_worker = None
            self.refresh_button.setEnabled(True)

        worker.signals.result.connect(done)
        worker.signals.error.connect(failed)
        worker.signals.finished.connect(finished)
        self._worker_pool.start(worker)
        return True

    def _rebuild_table(self, checked_paths: set[str] | None = None) -> None:
        checked = set(checked_paths if checked_paths is not None else self._selected_path_set())
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setSortingEnabled(False)
            self.table.clearContents()
            self.table.setRowCount(len(self._files))
            for row, info in enumerate(self._files):
                select_item = QTableWidgetItem("")
                select_item.setFlags(
                    select_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                )
                select_item.setCheckState(
                    Qt.CheckState.Checked if info.remote_path in checked else Qt.CheckState.Unchecked
                )
                select_item.setData(Qt.ItemDataRole.UserRole, info.remote_path)
                self.table.setItem(row, 0, select_item)
                self.table.setItem(row, 1, QTableWidgetItem(info.name))
                self.table.setItem(row, 2, QTableWidgetItem(human_size(info.size)))
                self.table.setItem(row, 3, QTableWidgetItem(info.mtime_text))
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        self._table_materialized = True
        self._cached_selected_paths = checked
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._table_materialized:
            self.count_label.setText(
                f"本地缓存 {len(self._files)} 个文件 | 已选择 {len(self._cached_selected_paths)}"
            )
            return
        keyword = self.search.text().strip().casefold()
        visible = 0
        selected = 0
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            select_item = self.table.item(row, 0)
            if name_item is None or select_item is None:
                continue
            name = name_item.text().casefold()
            show = not keyword or keyword in name
            self.table.setRowHidden(row, not show)
            if show:
                visible += 1
            if select_item.checkState() == Qt.CheckState.Checked:
                selected += 1
        self.count_label.setText(f"总数 {len(self._files)} | 当前显示 {visible} | 已选择 {selected}")

    def _schedule_selection_cache_save(self) -> None:
        # Selection is intentionally session-only. Keep the in-memory mirror current,
        # but do not write checkbox state into the persistent remote-file cache.
        self._cached_selected_paths = self._selected_path_set()

    def _set_visible_checked(self, checked: bool) -> None:
        if not self._table_materialized and self._files:
            self._rebuild_table(self._cached_selected_paths)
        self.table.blockSignals(True)
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                item = self.table.item(row, 0)
                if item is not None:
                    item.setCheckState(state)
        self.table.blockSignals(False)
        self._apply_filter()
        self._schedule_selection_cache_save()
        self.selectionChanged.emit()

    def select_all_files(self) -> None:
        """Select all locally cached/loaded remote G files without server I/O."""
        if not self._table_materialized and self._files:
            self._rebuild_table(self._cached_selected_paths)
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)
        self.table.blockSignals(False)
        self._apply_filter()
        self._schedule_selection_cache_save()
        self.selectionChanged.emit()

    def _clear_checks(self) -> None:
        if not self._table_materialized and self._files:
            self._rebuild_table(self._cached_selected_paths)
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._apply_filter()
        self._schedule_selection_cache_save()
        self.selectionChanged.emit()

    def _clear_all(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._clear_checks()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._apply_filter()
            self._schedule_selection_cache_save()
            self.selectionChanged.emit()

    def selected_files(self) -> list[RemoteGFile]:
        by_path = {item.remote_path: item for item in self._files}
        if not self._table_materialized:
            return [by_path[path] for path in self._cached_selected_paths if path in by_path]
        selected: list[RemoteGFile] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                remote_path = str(item.data(Qt.ItemDataRole.UserRole) or "")
                if remote_path in by_path:
                    selected.append(by_path[remote_path])
        return selected

    def has_loaded_files(self) -> bool:
        return bool(self._files)

    def cache_dir(self) -> Path:
        return self._prepared_dir

    def _processing_snapshot_dir(self) -> Path:
        workspace_root = default_workspace().resolve()
        prepared = self._prepared_dir.resolve()
        try:
            prepared.relative_to(workspace_root)
        except ValueError as exc:
            raise RuntimeError(f"SSH 处理快照目录必须位于本地 workspace 中：{prepared}") from exc
        return prepared

    def _snapshot_matches_selection(self, selected: list[RemoteGFile]) -> bool:
        manifest = self._snapshot_manifest_path()
        if not manifest.is_file():
            return False
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            return False
        if not isinstance(payload, dict) or payload.get("endpoint") != self._endpoint_signature(self.config()):
            return False
        raw = payload.get("files", [])
        if not isinstance(raw, list):
            return False
        cached = {
            str(item.get("remote_path", "")): (
                int(item.get("size", -1) or -1), int(item.get("mtime_epoch", -1) or -1)
            )
            for item in raw if isinstance(item, dict)
        }
        if set(cached) != {item.remote_path for item in selected}:
            return False
        for item in selected:
            if cached.get(item.remote_path) != (int(item.size), int(item.mtime_epoch)):
                return False
            local = self._prepared_dir / item.name
            if not local.is_file() or local.stat().st_size != int(item.size):
                return False
        return True

    def _write_snapshot_manifest(self, selected: list[RemoteGFile]) -> None:
        path = self._snapshot_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "kind": "GFileStudio prepared remote G processing snapshot",
            "module": self.settings_prefix,
            "updated_at": _utc_now(),
            "endpoint": self._endpoint_signature(self.config()),
            "files": [
                {
                    "name": item.name,
                    "remote_path": item.remote_path,
                    "size": int(item.size),
                    "mtime_epoch": int(item.mtime_epoch),
                }
                for item in selected
            ],
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _download_processing_snapshot(
        self,
        *,
        selected: list[RemoteGFile],
        cfg: dict[str, object],
        snapshot_dir: Path,
        log=None,
        progress=None,
    ) -> Path:
        if log is not None:
            log(f"[SSH只读] 将 {len(selected)} 个服务器 G 文件下载为本地处理快照：{snapshot_dir}")
            log("[SSH只读] 后续扫描/处理仅使用 workspace 本地快照，不会修改服务器文件。")
        download_stable_files(
            host=str(cfg["host"]),
            port=int(cfg["port"]),
            username=str(cfg["username"]),
            password=str(cfg["password"]),
            selected_files=selected,
            target_dir=snapshot_dir,
            log=log,
            progress=progress,
        )
        return snapshot_dir

    def prepare_selected(self, *, log=None, progress=None) -> Path:
        """Return a local processing snapshot without freezing the GUI.

        If the selected files already match the last downloaded snapshot (path,
        size and server mtime from the manually refreshed list), no SSH call occurs.
        Otherwise the download runs on the global worker pool. On the GUI thread a
        small nested event loop keeps painting/input responsive while preserving the
        historical synchronous ``Path`` return contract used by all processing pages.
        """
        selected = self.selected_files()
        if not selected:
            raise ValueError("请先在 SSH G 文件列表中选择一个或多个文件。")
        self._restore_shared_settings()
        cfg = dict(self.config())
        snapshot_dir = self._processing_snapshot_dir()

        if self._snapshot_matches_selection(selected):
            if log is not None:
                log(f"[本地缓存] 复用 {len(selected)} 个已下载服务器 G 文件，不访问 SSH。")
            self.status.setText(f"已复用本模块本地处理缓存：{len(selected)} 个 G 文件。")
            self.prepared.emit(str(snapshot_dir))
            return snapshot_dir

        # If this method is ever called from a worker already, do the I/O directly
        # there rather than nesting another thread wait.
        app = QApplication.instance()
        on_gui_thread = app is not None and QThread.currentThread() == app.thread()
        if not on_gui_thread:
            result = self._download_processing_snapshot(
                selected=selected,
                cfg=cfg,
                snapshot_dir=snapshot_dir,
                log=log,
                progress=progress,
            )
            self._write_snapshot_manifest(selected)
            return result

        loop = QEventLoop(self)
        outcome: dict[str, object] = {}
        caller_log = log
        caller_progress = progress

        def task(*, log, progress):
            # FunctionWorker passes Qt signal emitters here; all UI-facing callbacks
            # are connected below and therefore execute back on the GUI thread.
            return self._download_processing_snapshot(
                selected=selected,
                cfg=cfg,
                snapshot_dir=snapshot_dir,
                log=log,
                progress=progress,
            )

        worker = FunctionWorker(task)
        self.status.setText(f"正在后台准备 {len(selected)} 个服务器 G 文件，本窗口不会卡死…")

        def on_progress(value: int) -> None:
            self.status.setText(f"正在后台准备服务器 G 文件… {value}%")
            if caller_progress is not None:
                caller_progress(value)

        def on_result(result: object) -> None:
            outcome["result"] = result

        def on_error(details: str) -> None:
            outcome["error"] = self._worker_error_message(details)

        def on_finished() -> None:
            loop.quit()

        if caller_log is not None:
            worker.signals.log.connect(caller_log)
        worker.signals.progress.connect(on_progress)
        worker.signals.result.connect(on_result)
        worker.signals.error.connect(on_error)
        worker.signals.finished.connect(on_finished)
        self._worker_pool.start(worker)
        loop.exec()

        if "error" in outcome:
            message = str(outcome["error"])
            self.status.setText(f"服务器 G 文件准备失败：{message}")
            raise RuntimeError(message)
        self._write_snapshot_manifest(selected)
        if log is not None:
            log(f"[SSH只读] 已后台下载 {len(selected)} 个 G 文件到本地处理缓存：{snapshot_dir}")
        self.status.setText(f"服务器 G 文件已缓存到本地：{len(selected)} 个。后续相同版本直接复用。")
        self.prepared.emit(str(snapshot_dir))
        return snapshot_dir

    def download_selected_to_local(self) -> None:
        if self._download_worker is not None:
            return
        selected = self.selected_files()
        if not selected:
            QMessageBox.information(self, "请选择文件", "请先选择一个或多个要下载到本地的 G 文件。")
            return
        destination = QFileDialog.getExistingDirectory(self, "选择本地下载目录", str(default_workspace()))
        if not destination:
            return
        self._restore_shared_settings()
        cfg = dict(self.config())

        def task(*, log, progress):
            return download_stable_files(
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                username=str(cfg["username"]),
                password=str(cfg["password"]),
                selected_files=selected,
                target_dir=Path(destination),
                clear_target=False,
                log=log,
                progress=progress,
            )

        worker = FunctionWorker(task)
        self._download_worker = worker
        self.download_button.setEnabled(False)
        self.status.setText(f"正在后台下载 {len(selected)} 个 G 文件…")
        worker.signals.progress.connect(
            lambda value: self.status.setText(f"正在后台下载 {len(selected)} 个 G 文件… {value}%")
        )

        def done(result: object) -> None:
            outputs = result if isinstance(result, list) else []
            self.status.setText(f"下载完成：{len(outputs)} 个 G 文件。")
            QMessageBox.information(self, "下载完成", f"已下载 {len(outputs)} 个 G 文件到：\n{destination}")

        def failed(details: str) -> None:
            message = self._worker_error_message(details)
            self.status.setText(f"下载失败：{message}")
            QMessageBox.warning(self, "下载失败", message)

        def finished() -> None:
            self._download_worker = None
            self.download_button.setEnabled(True)

        worker.signals.result.connect(done)
        worker.signals.error.connect(failed)
        worker.signals.finished.connect(finished)
        self._worker_pool.start(worker)
