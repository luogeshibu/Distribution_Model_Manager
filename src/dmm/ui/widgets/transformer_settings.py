from __future__ import annotations

from pathlib import PurePosixPath

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from dmm.application.modules.transformer import TRANSFORMER_DOMAIN, TRANSFORMER_TABLE_ID
from dmm.application.modules.pole_switch import _normalized_transformer_element_files
from dmm.config.defaults import DEFAULT_TRANSFORMER_ELEMENT_FILES
from dmm.config.settings import save_settings
from dmm.ui.widgets.pole_switch_settings import ElementServerSearchWorker


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


class TransformerSettingsWidget(QGroupBox):
    """Makkah pole-transformer rules with operator-maintained devref files."""

    _MAX_FILE_LIST_ROWS = 12
    _MAX_SEARCH_RESULT_ROWS = 7

    def __init__(self, config):
        super().__init__("柱上变压器模型配置")
        self.config = config
        self.search_worker: ElementServerSearchWorker | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 7)
        layout.setSpacing(3)

        layout.addWidget(_logic_label(
            "1. 识别哪些设备",
            "只按下方用户维护的 devref 图元文件名识别柱上变压器。只要加入名单，就直接认定为柱上变压器；"
            "不再读取【图元管理】TRANSFORMER_OH 分类。匹配按文件名精确、忽略大小写和路径；用户加入名单的图元不再按 XML 类型、颜色、形状或内部结构二次排除。",
            True,
        ))

        editor_box = QGroupBox("柱上变压器图元名单")
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

        self.server_search_panel = QWidget()
        self.server_search_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        server_panel_layout = QVBoxLayout(self.server_search_panel)
        server_panel_layout.setContentsMargins(0, 0, 0, 0)
        server_panel_layout.setSpacing(5)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self.server_search_edit = QLineEdit()
        self.server_search_edit.setPlaceholderText(
            "输入图元文件名关键字，例如 Transformer_OH、Transformer、transformer"
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
        self.server_add_button = QPushButton("添加勾选到柱上变压器名单")
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
            "所有柱上变压器与 Text 统一按矩形最小边缘距离计算，只保留距离 ≤ 200 的候选，按全局距离从近到远一对一分配。",
        ))
        layout.addWidget(_logic_label(
            "3. 麦加数据库关联",
            "不识别、不要求、不校验 FEEDER_ID。图上名称直接按 13505/dms_tr_device.NAME 精确查询；唯一命中 1 条就直接关联，0 条或多条都不自动关联。",
        ))
        layout.addWidget(_logic_label(
            "4. KeyID 与安全回写",
            "按 13505.ID、固定 Domain=1 计算并反解验证 Expected KeyID；keyid1/keyid2 两组槽位按现有规则写入，仅修改 Workspace 安全副本。",
        ))

        initial = config.get("transformer_element_files")
        if initial is None:
            initial = DEFAULT_TRANSFORMER_ELEMENT_FILES
        self._load_files(initial)

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
            key = file_name.casefold()
            if file_name and key not in seen:
                seen.add(key)
                values.append(file_name)
        return values

    def _load_files(self, values):
        normalized = _normalized_transformer_element_files({
            "transformer_element_files": values,
        })
        self.file_list.clear()
        for file_name in normalized:
            item = QListWidgetItem(file_name)
            item.setData(Qt.UserRole, file_name)
            self.file_list.addItem(item)
        self._resize_file_list()

    def _persist(self):
        files = self._files_from_list()
        self.config["transformer_element_files"] = files
        save_settings(self.config)
        if hasattr(self, "local_cache_status_label"):
            self.local_cache_status_label.setText(
                f"已保存到本地用户缓存：柱上变压器图元 {len(files)} 个。"
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
                "请输入图元文件名或目录关键字后再搜索，例如 Transformer_OH、Transformer。",
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
        selectable = self.server_result_list.count() > 0
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
            QMessageBox.information(self, "柱上变压器图元", "请先勾选需要加入柱上变压器名单的图元。")
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
        if added:
            self.server_status_label.setText(f"已添加 {added} 个图元到柱上变压器名单。")
        else:
            self.server_status_label.setText("勾选的图元已在柱上变压器名单中，没有重复添加。")

    def _delete_selected(self):
        for item in list(self.file_list.selectedItems()):
            row = self.file_list.row(item)
            if row >= 0:
                self.file_list.takeItem(row)
        self._resize_file_list()
        self._persist()

    def _restore_defaults(self):
        self._load_files(DEFAULT_TRANSFORMER_ELEMENT_FILES)
        self._persist()

    def collect_settings(self):
        files = self._files_from_list()
        self.config["transformer_element_files"] = files
        return {
            "transformer_table_id": TRANSFORMER_TABLE_ID,
            "transformer_domain": TRANSFORMER_DOMAIN,
            "transformer_element_files": files,
        }
