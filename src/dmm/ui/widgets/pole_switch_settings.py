from __future__ import annotations

from pathlib import PurePosixPath

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dmm.application.modules.pole_switch import (
    POLE_SWITCH_DOMAIN,
    POLE_SWITCH_TABLE_ID,
    _normalized_pole_switch_element_files,
)
from dmm.config.defaults import (
    DEFAULT_POLE_SWITCH_ELEMENT_FILES,
    DEFAULT_TRANSFORMER_ELEMENT_FILES,
)
from dmm.config.settings import save_settings
from dmm.infrastructure.remote import ReadOnlySshClient


def _logic_label(title: str, text: str, accent: bool = False) -> QLabel:
    label = QLabel(f"<b>{title}：</b> {text}")
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
    label.setMinimumHeight(0)
    label.setMaximumHeight(64)
    label.setStyleSheet(
        ("background:#EAF8F2;color:#17372E;border:1px solid #B9DACD;" if accent else
         "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;")
        + "border-radius:6px;padding:4px 7px;line-height:1.22;"
    )
    return label


class ElementServerSearchWorker(QThread):
    """Read-only server-side element file search for the pole-switch picker."""

    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, ssh_config: dict, remote_directory: str, keyword: str, parent=None):
        super().__init__(parent)
        self.ssh_config = dict(ssh_config or {})
        self.remote_directory = str(remote_directory or "").strip()
        self.keyword = str(keyword or "").strip().casefold()

    def run(self):
        client = None
        try:
            client = ReadOnlySshClient(
                host=self.ssh_config.get("host", ""),
                port=self.ssh_config.get("port", 22),
                username=self.ssh_config.get("username", ""),
                password=self.ssh_config.get("password", ""),
            )
            rows = client.list_element_files(self.remote_directory)
            matches = []
            for remote_file in rows:
                relative = str(remote_file.name or "").replace("\\", "/").strip()
                if not relative:
                    continue
                if self.keyword and self.keyword not in relative.casefold():
                    continue
                matches.append(relative)
            self.loaded.emit({"matches": matches, "total": len(rows)})
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if client is not None:
                client.close()


class PoleSwitchSettingsWidget(QGroupBox):
    """Makkah pole-switch rules with operator-maintained devref file names."""

    _MAX_FILE_LIST_ROWS = 12
    _MAX_SEARCH_RESULT_ROWS = 7

    def __init__(self, config):
        super().__init__("柱上开关模型配置")
        self.config = config
        self.search_worker: ElementServerSearchWorker | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        layout.addWidget(_logic_label(
            "1. 识别哪些设备",
            "只按下方用户维护的 devref 图元文件名识别柱上开关。只要加入名单，就直接认定为柱上开关；"
            "不再区分 AR / LBS / SEC，也不再读取【图元管理】分类。匹配按文件名精确、忽略大小写和路径；"
            "用户加入名单的图元不再按 RMU_* 前缀、XML 类型、颜色或内部结构二次排除。",
            True,
        ))

        editor_box = QGroupBox("柱上开关图元名单")
        editor_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        editor_layout = QVBoxLayout(editor_box)
        editor_layout.setContentsMargins(8, 7, 8, 7)
        editor_layout.setSpacing(5)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        editor_layout.addWidget(self.file_list)

        server_header_row = QHBoxLayout()
        server_header_row.setSpacing(6)
        server_title = QLabel("从图元服务器搜索并添加")
        server_title.setStyleSheet("font-weight:600;color:#0B604C;margin-top:2px;")
        self.server_search_toggle_button = QPushButton("展开服务器搜索")
        self.server_search_toggle_button.setToolTip("展开或收起图元服务器搜索区域")
        self.server_search_toggle_button.clicked.connect(self._toggle_server_search_panel)
        server_header_row.addWidget(server_title)
        server_header_row.addStretch()
        server_header_row.addWidget(self.server_search_toggle_button)
        editor_layout.addLayout(server_header_row)

        # The server picker is a secondary operation. Keep it collapsed by default
        # so the pole-switch configuration stays compact; users can expand it only
        # when they need to search the shared element server.
        self.server_search_panel = QWidget()
        self.server_search_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        server_panel_layout = QVBoxLayout(self.server_search_panel)
        server_panel_layout.setContentsMargins(0, 0, 0, 0)
        server_panel_layout.setSpacing(5)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.server_search_edit = QLineEdit()
        self.server_search_edit.setPlaceholderText(
            "输入图元文件名关键字，例如 SEC_NON、AR_NON、breaker_dis"
        )
        self.server_search_button = QPushButton("搜索服务器")
        self.server_search_button.clicked.connect(self._search_server)
        self.server_search_edit.returnPressed.connect(self._search_server)
        search_row.addWidget(self.server_search_edit, 1)
        search_row.addWidget(self.server_search_button)
        server_panel_layout.addLayout(search_row)

        self.server_result_list = QListWidget()
        self.server_result_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.server_result_list.itemDoubleClicked.connect(self._add_server_item_direct)
        self.server_result_list.itemChanged.connect(self._update_server_add_button_state)
        self.server_result_list.setVisible(False)
        server_panel_layout.addWidget(self.server_result_list)

        server_action_row = QHBoxLayout()
        server_action_row.setSpacing(6)
        self.server_select_all_button = QPushButton("全选可添加")
        self.server_select_all_button.setEnabled(False)
        self.server_select_all_button.clicked.connect(self._check_all_server_results)
        self.server_clear_all_button = QPushButton("全部取消")
        self.server_clear_all_button.setEnabled(False)
        self.server_clear_all_button.clicked.connect(self._uncheck_all_server_results)
        self.server_add_button = QPushButton("添加勾选到柱上开关名单")
        self.server_add_button.setEnabled(False)
        self.server_add_button.clicked.connect(self._add_selected_server_files)
        self.server_close_button = QPushButton("收起搜索")
        self.server_close_button.clicked.connect(lambda: self._set_server_search_panel_visible(False))
        self.server_status_label = QLabel("使用【图元管理】中的 SSH 配置，只读搜索服务器，不修改服务器文件。")
        self.server_status_label.setWordWrap(True)
        self.server_status_label.setStyleSheet("color:#5B716A;")
        server_action_row.addWidget(self.server_select_all_button)
        server_action_row.addWidget(self.server_clear_all_button)
        server_action_row.addWidget(self.server_add_button)
        server_action_row.addWidget(self.server_close_button)
        server_action_row.addWidget(self.server_status_label, 1)
        server_panel_layout.addLayout(server_action_row)

        self.server_search_panel.setVisible(False)
        editor_layout.addWidget(self.server_search_panel)

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.save_local_cache_button = QPushButton("保存到本地用户缓存")
        self.save_local_cache_button.setToolTip(
            "保存到当前用户的本地配置缓存；替换程序目录后仍可恢复。"
        )
        delete_btn = QPushButton("删除选中")
        reset_btn = QPushButton("恢复麦加默认")
        self.save_local_cache_button.clicked.connect(self._save_local_cache)
        delete_btn.clicked.connect(self._delete_selected)
        reset_btn.clicked.connect(self._restore_defaults)
        action_row.addWidget(self.save_local_cache_button)
        action_row.addWidget(delete_btn)
        action_row.addWidget(reset_btn)
        action_row.addStretch()
        editor_layout.addLayout(action_row)

        self.local_cache_status_label = QLabel(
            "名单变更后会自动保存到本地用户缓存；也可以点击“保存到本地用户缓存”手动保存。"
        )
        self.local_cache_status_label.setWordWrap(True)
        self.local_cache_status_label.setStyleSheet("color:#5B716A;")
        editor_layout.addWidget(self.local_cache_status_label)
        layout.addWidget(editor_box)

        layout.addWidget(_logic_label(
            "2. 全局匹配图上名称",
            "扫描整张 G 图所有合法 Text；不限制颜色、背景、纯数字、字母或字母数字组合，纯小数直接排除。"
            "所有柱上开关与 Text 统一计算矩形最小边缘距离，只保留距离 ≤ 200 的候选，然后按全局距离从近到远一对一分配。",
        ))
        layout.addWidget(_logic_label(
            "3. 麦加数据库关联",
            "不识别、不要求、不校验 FEEDER_ID。G 文件中的柱上开关名称保持原样，不删除空格、横线、点号等字符，直接按 13501/dms_combined_device.NAME 精确匹配；"
            "13501 必须唯一，再按其 ID 查询 13502/dms_cb_device.combined_id。13502 子设备也必须唯一；"
            "如果存在多个子设备，不再按 AR/LBS/SEC 消歧，直接阻断关联并写入报告。",
        ))
        layout.addWidget(_logic_label(
            "4. KeyID 与安全回写",
            "目标使用 13502.ID、固定 Domain=40 计算并反解验证 Expected KeyID；只修改 Workspace 安全副本，无法唯一确定则只报告不关联。",
        ))

        self._load_files(_normalized_pole_switch_element_files(config))


    def _set_server_search_panel_visible(self, visible: bool):
        visible = bool(visible)
        self.server_search_panel.setVisible(visible)
        self.server_search_toggle_button.setText(
            "收起服务器搜索" if visible else "展开服务器搜索"
        )
        if visible:
            self.server_search_edit.setFocus(Qt.OtherFocusReason)
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None:
            parent.updateGeometry()

    def _toggle_server_search_panel(self):
        self._set_server_search_panel_visible(not self.server_search_panel.isVisible())

    @staticmethod
    def _normalize_file_name(value: str) -> str:
        text = str(value or "").strip().replace("\\", "/")
        text = text.rsplit("/", 1)[-1].lstrip("#")
        if ":" in text:
            text = text.split(":", 1)[0]
        return text.strip()

    @staticmethod
    def _list_height(widget: QListWidget, row_count: int, max_rows: int) -> int:
        visible_rows = max(1, min(int(row_count or 0), int(max_rows)))
        row_height = widget.sizeHintForRow(0) if widget.count() else -1
        if row_height <= 0:
            row_height = max(24, widget.fontMetrics().height() + 10)
        return visible_rows * row_height + widget.frameWidth() * 2 + 6

    def _resize_file_list(self):
        # The maintained list grows with the configured file count instead of
        # reserving a large empty rectangle. Beyond 12 rows the list scrolls.
        self.file_list.setFixedHeight(
            self._list_height(
                self.file_list,
                self.file_list.count(),
                self._MAX_FILE_LIST_ROWS,
            )
        )

    def _resize_server_result_list(self):
        count = self.server_result_list.count()
        self.server_result_list.setVisible(count > 0)
        if count > 0:
            self.server_result_list.setFixedHeight(
                self._list_height(
                    self.server_result_list,
                    count,
                    self._MAX_SEARCH_RESULT_ROWS,
                )
            )

    def _files_from_list(self):
        values = []
        seen = set()
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            file_name = self._normalize_file_name(item.data(Qt.UserRole) or item.text())
            if not file_name:
                continue
            folded = file_name.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            values.append(file_name)
        return values

    def _load_files(self, files):
        normalized = _normalized_pole_switch_element_files({
            "pole_switch_element_files": list(files or []),
        })
        self.file_list.clear()
        for file_name in normalized:
            item = QListWidgetItem(file_name)
            item.setData(Qt.UserRole, file_name)
            self.file_list.addItem(item)
        self._resize_file_list()

    def _persist(self):
        files = self._files_from_list()
        self.config["pole_switch_element_files"] = files
        # Remove the old v4.1.93 family-based key once this UI is saved.
        self.config.pop("pole_switch_element_rules", None)
        save_settings(self.config)
        if hasattr(self, "local_cache_status_label"):
            self.local_cache_status_label.setText(
                f"已保存到本地用户缓存：柱上开关图元 {len(files)} 个。"
            )

    def _save_local_cache(self):
        self._persist()

    def _current_element_server(self):
        ssh_config = dict(self.config.get("ssh", {}) or {})
        remote_directory = str(
            ssh_config.get("element_directory")
            or (self.config.get("element_catalog") or {}).get("remote_directory")
            or "/home/up8000/data/graph/element"
        ).strip()
        return ssh_config, remote_directory

    def _search_server(self):
        if self.search_worker is not None and self.search_worker.isRunning():
            return
        keyword = self.server_search_edit.text().strip()
        if not keyword:
            QMessageBox.information(
                self,
                "搜索图元服务器",
                "请输入图元文件名或目录关键字后再搜索，例如 SEC_NON、AR_NON、breaker_dis。",
            )
            return
        ssh_config, remote_directory = self._current_element_server()
        if not str(ssh_config.get("host") or "").strip():
            QMessageBox.warning(
                self,
                "搜索图元服务器",
                "图元服务器 IP / 主机为空，请先到【图元管理】配置并保存 SSH 参数。",
            )
            return
        self.server_search_button.setEnabled(False)
        self.server_select_all_button.setEnabled(False)
        self.server_clear_all_button.setEnabled(False)
        self.server_add_button.setEnabled(False)
        self.server_result_list.clear()
        self._resize_server_result_list()
        self.server_status_label.setText(
            f"正在只读搜索图元服务器：{remote_directory} …"
        )
        worker = ElementServerSearchWorker(
            ssh_config,
            remote_directory,
            keyword,
            self,
        )
        worker.loaded.connect(self._on_server_search_loaded)
        worker.failed.connect(self._on_server_search_failed)
        worker.finished.connect(self._on_server_search_finished)
        self.search_worker = worker
        worker.start()

    def _on_server_search_loaded(self, payload):
        matches = list((payload or {}).get("matches") or [])
        total = int((payload or {}).get("total") or 0)
        self.server_result_list.clear()
        for relative in matches:
            base_name = self._normalize_file_name(PurePosixPath(relative).name)
            if not base_name:
                continue
            item = QListWidgetItem(str(relative))
            item.setData(Qt.UserRole, base_name)
            item.setToolTip(str(relative))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.server_result_list.addItem(item)
        self._resize_server_result_list()
        selectable = any(
            bool(self.server_result_list.item(i).flags() & Qt.ItemIsUserCheckable)
            for i in range(self.server_result_list.count())
        )
        self.server_select_all_button.setEnabled(selectable)
        self.server_clear_all_button.setEnabled(False)
        self.server_add_button.setEnabled(False)
        if matches:
            self.server_status_label.setText(
                f"服务器共 {total} 个 .g 图元，本次匹配 {len(matches)} 个；请勾选需要加入的图元，也可双击单个图元直接添加。"
            )
        else:
            self.server_status_label.setText(
                f"服务器共 {total} 个 .g 图元，没有找到匹配“{self.server_search_edit.text().strip()}”的图元。"
            )

    def _on_server_search_failed(self, message: str):
        self.server_result_list.clear()
        self._resize_server_result_list()
        self.server_select_all_button.setEnabled(False)
        self.server_clear_all_button.setEnabled(False)
        self.server_add_button.setEnabled(False)
        self.server_status_label.setText(f"服务器搜索失败：{message}")
        QMessageBox.warning(self, "搜索图元服务器失败", str(message))

    def _on_server_search_finished(self):
        self.server_search_button.setEnabled(True)
        self.search_worker = None

    def _checked_server_items(self):
        checked = []
        for index in range(self.server_result_list.count()):
            item = self.server_result_list.item(index)
            if not (item.flags() & Qt.ItemIsUserCheckable):
                continue
            if item.checkState() == Qt.Checked:
                checked.append(item)
        return checked

    def _update_server_add_button_state(self, *_args):
        checked = self._checked_server_items()
        self.server_add_button.setEnabled(bool(checked))
        self.server_clear_all_button.setEnabled(bool(checked))

    def _check_all_server_results(self):
        self.server_result_list.blockSignals(True)
        try:
            for index in range(self.server_result_list.count()):
                item = self.server_result_list.item(index)
                if item.flags() & Qt.ItemIsUserCheckable:
                    item.setCheckState(Qt.Checked)
        finally:
            self.server_result_list.blockSignals(False)
        self._update_server_add_button_state()

    def _uncheck_all_server_results(self):
        self.server_result_list.blockSignals(True)
        try:
            for index in range(self.server_result_list.count()):
                item = self.server_result_list.item(index)
                if item.flags() & Qt.ItemIsUserCheckable:
                    item.setCheckState(Qt.Unchecked)
        finally:
            self.server_result_list.blockSignals(False)
        self._update_server_add_button_state()

    def _add_server_item_direct(self, item: QListWidgetItem):
        if item is None or not (item.flags() & Qt.ItemIsUserCheckable):
            return
        item.setCheckState(Qt.Checked)
        self._add_selected_server_files()

    def _append_file_name(self, file_name: str) -> bool:
        file_name = self._normalize_file_name(file_name)
        if not file_name:
            return False
        for index in range(self.file_list.count()):
            existing = self._normalize_file_name(self.file_list.item(index).text())
            if existing.casefold() == file_name.casefold():
                self.file_list.setCurrentRow(index)
                return False
        item = QListWidgetItem(file_name)
        item.setData(Qt.UserRole, file_name)
        self.file_list.addItem(item)
        return True

    def _add_selected_server_files(self):
        selected = self._checked_server_items()
        if not selected:
            QMessageBox.information(self, "柱上开关图元", "请先勾选需要加入柱上开关名单的图元。")
            return
        added = 0
        self.server_result_list.blockSignals(True)
        try:
            for item in selected:
                file_name = self._normalize_file_name(item.data(Qt.UserRole) or item.text())
                if self._append_file_name(file_name):
                    added += 1
                item.setCheckState(Qt.Unchecked)
        finally:
            self.server_result_list.blockSignals(False)
        self._resize_file_list()
        if added:
            self._persist()
        self._update_server_add_button_state()
        message = f"已添加 {added} 个图元到柱上开关名单。"
        if added == 0:
            message = "勾选的图元已在柱上开关名单中，没有重复添加。"
        self.server_status_label.setText(message)

    def _delete_selected(self):
        for item in list(self.file_list.selectedItems()):
            row = self.file_list.row(item)
            if row >= 0:
                self.file_list.takeItem(row)
        self._resize_file_list()
        self._persist()

    def _restore_defaults(self):
        self._load_files(DEFAULT_POLE_SWITCH_ELEMENT_FILES)
        self._persist()

    def collect_settings(self):
        files = self._files_from_list()
        self.config["pole_switch_element_files"] = files
        self.config.pop("pole_switch_element_rules", None)
        return {
            "pole_switch_table_id": POLE_SWITCH_TABLE_ID,
            "pole_switch_domain": POLE_SWITCH_DOMAIN,
            "pole_switch_element_files": files,
            # Cross-module Text ownership must use the same transformer list.
            "transformer_element_files": list(
                self.config.get("transformer_element_files") or DEFAULT_TRANSFORMER_ELEMENT_FILES
            ),
        }
