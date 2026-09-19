from __future__ import annotations

import json
import hashlib
from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from dmm.config.settings import save_settings
from dmm.domain.gfile.element_catalog import resolve_element_record
from dmm.infrastructure.remote import ReadOnlySshClient


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
    return value.replace("\\", "/").strip().casefold()


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
        for key in ("classification", "remark", "device_alias", "device_code"):
            if not str(existing.get(key) or "").strip() and str(row.get(key) or "").strip():
                existing[key] = row[key]
        if row.get("missing_on_server"):
            existing["missing_on_server"] = True
        if row.get("definition_hash") and not existing.get("definition_hash"):
            existing["definition_hash"] = row["definition_hash"]
    return [merged_by_identity[identity] for identity in order]


def _shared_record(record: dict) -> dict:
    """Return only portable marks; never export SSH credentials."""
    return {
        "element_key": record.get("element_key", ""),
        "file_key": record.get("file_key", ""),
        "file_name": record.get("file_name", ""),
        "root_id": record.get("root_id", ""),
        "classification": record.get("classification", ""),
        "remark": record.get("remark", ""),
        "definition_hash": record.get("definition_hash", ""),
    }


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
                    row = _record_with_defaults(
                        {
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
                    )
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

    HEADERS = (
        "图元定义文件",
        "分类标记",
        "备注",
        "状态",
    )

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.rows: list[dict] = []
        self.worker: ElementDefinitionWorker | None = None
        self.download_worker: ElementDownloadWorker | None = None
        self._rendering = False
        self.dirty = False
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
            "只有点击“刷新图元列表”才会重新读取。可勾选图元下载到本地，模型识别按完整图元路径匹配，"
            "原始服务器文件只读，不会被修改。图元分类标记保存在当前用户缓存中，替换或删除程序目录后仍会保留。"
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

        actions = QHBoxLayout()
        for button in (
            self.test_server_button,
            self.save_server_button,
            self.load_button,
            self.download_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        source_grid.addLayout(actions, 5, 1, 1, 6)

        self.load_saved_button = QPushButton("载入本地标记")
        self.load_saved_button.clicked.connect(self._load_saved_records)
        self.save_button = QPushButton("保存当前标记")
        self.save_button.clicked.connect(self.save_catalog)
        self.import_button = QPushButton("导入共享配置")
        self.import_button.clicked.connect(self.import_shared_catalog)
        self.export_button = QPushButton("导出共享配置")
        self.export_button.clicked.connect(self.export_shared_catalog)
        mark_actions = QHBoxLayout()
        for button in (
            self.load_saved_button,
            self.save_button,
            self.import_button,
            self.export_button,
        ):
            mark_actions.addWidget(button)
        mark_actions.addStretch()
        source_grid.addLayout(mark_actions, 6, 1, 1, 6)

        self.status_label = QLabel("尚未手动同步服务器图元；当前仅使用本地缓存。")
        self.status_label.setWordWrap(True)
        source_grid.addWidget(self.status_label, 7, 1, 1, 6)
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
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(self.HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
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
        )
        self.table.itemChanged.connect(self._on_table_changed)
        layout.addWidget(self.table, 1)

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
            self.status_label.setText("正在测试图元服务器 SSH/SFTP 只读连接……")
            with ReadOnlySshClient(
                config["host"],
                config["port"],
                config["username"],
                config["password"],
            ) as client:
                client.test_connection()
            self._save_element_ssh_config(config)
            self.status_label.setText(
                "图元服务器 SSH/SFTP 连接正常；远程图元文件为只读。"
            )
        except Exception as exc:
            self.status_label.setText(f"图元服务器连接失败：{exc}")
            QMessageBox.warning(self, "图元服务器连接失败", str(exc))

    def save_server_settings(self):
        try:
            config = self._current_element_ssh_config()
            self._save_element_ssh_config(config)
            self.status_label.setText(
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

    def _catalog(self) -> dict:
        catalog = self.config.get("element_catalog", {})
        return catalog if isinstance(catalog, dict) else {}

    def _load_saved_records(self):
        records = self._catalog().get("records", [])
        self.rows = _merge_duplicate_records(records)
        self.dirty = False
        self._render_rows()
        self.status_label.setText(
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
        self.status_label.setText("正在读取服务器图元文件列表，请稍候……")
        worker = ElementDefinitionWorker(ssh_config, directory, self)
        self.worker = worker
        worker.loaded.connect(self._on_remote_loaded)
        worker.failed.connect(self._on_remote_failed)
        worker.finished.connect(lambda: self.load_button.setEnabled(True))
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
        self.status_label.setText(
            f"正在下载 {len(rows)} 个图元文件，请稍候……"
        )
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
        self.status_label.setText(message.replace("\n", "<br>"))
        QMessageBox.information(self, "图元下载完成", message)

    def _on_element_download_failed(self, message: str):
        self.status_label.setText(f"图元下载失败：{message}")
        QMessageBox.warning(self, "图元下载失败", message)

    def _on_remote_failed(self, message: str):
        self.status_label.setText(f"读取失败：{message}")
        QMessageBox.warning(self, "读取图元定义失败", message)

    def _on_remote_loaded(self, rows: list):
        remote_count = len(rows or [])
        rows = _merge_duplicate_records(rows)
        saved_records = _merge_duplicate_records(self._catalog().get("records", []))
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
            self.status_label.setText(f"服务器读取完成，但本地自动保存失败：{exc}")
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
        self.status_label.setText("\n".join(messages))

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
                self._item(row.get("classification"), editable=True),
            )
            self.table.setItem(
                row_index,
                2,
                self._item(row.get("remark"), editable=True),
            )
            self.table.setItem(row_index, 3, self._item(row.get("status")))
        self._rendering = False
        self._apply_filter(self.filter_edit.text())
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.resizeRowsToContents()

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

    def _sync_rows_from_table(self):
        for row_index, row in enumerate(self.rows):
            if row_index >= self.table.rowCount():
                break
            row["classification"] = self.table.item(row_index, 1).text().strip()
            row["remark"] = self.table.item(row_index, 2).text().strip()

    def _on_table_changed(self, _item):
        if self._rendering:
            return
        self.dirty = True
        self.status_label.setText("有未保存的图元标记修改，请点击“保存图元标记”。")

    def save_catalog(self):
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
        self.status_label.setText(
            f"已保存 {len(self.rows)} 条图元标记。后续模型识别会按图元文件标识匹配。"
        )
        self.catalogChanged.emit()

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
            "schema": "distribution-model-manager.element-marks",
            "schema_version": 1,
            "records": [_shared_record(row) for row in self.rows],
        }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "导出共享配置失败", str(exc))
            return
        self.status_label.setText(
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
            if payload.get("schema") != "distribution-model-manager.element-marks":
                raise ValueError("不是本工具导出的图元共享配置。")
            records = payload.get("records", [])
            if not isinstance(records, list):
                raise ValueError("共享配置 records 必须是数组。")
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
            incoming = _record_with_defaults(record)
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
        self.status_label.setText(
            f"已导入 {imported} 条共享标记，尚未写入本地设置；请确认后点击“保存图元标记”。"
        )
