from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.engines.icon_upgrade_engine import (
    analyze_icon_mappings,
    parse_icon_definition,
    suggest_icon_pairs,
)
from g_file_studio.services.remote_g_source import DEFAULT_SSH_HOST
from g_file_studio.services.remote_symbol_library import DEFAULT_REMOTE_SYMBOL_ROOT, RemoteSymbolLibraryService
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.ui.table_layout import configure_responsive_table
from g_file_studio.ui.widgets.wheel_safe_combo_box import WheelSafeComboBox


class ServerSymbolPickerDialog(QDialog):
    """Pick one or more server-library symbols from the LOCAL AppData cache.

    The dialog never opens SSH.  It consumes the same cached inventory shown by
    main DMM Element Management so both OLD and NEW inputs can reuse authoritative
    server symbols without another network round-trip.
    """

    ROLE_CACHE_PATH = int(Qt.ItemDataRole.UserRole) + 20

    def __init__(self, records: list[dict[str, object]], *, side: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("从服务器图元中选择旧图元" if side == "old" else "从服务器图元中选择新图元")
        self.resize(1180, 680)
        layout = QVBoxLayout(self)

        note = QLabel(
            "数据来自主程序“图元管理”已桥接到本机 AppData 的图元缓存，不会再次访问 SSH。"
            "如服务器图元有更新，请先到主程序“图元管理”刷新图元列表并保存到本地缓存。可按 Ctrl/Shift 多选。"
        )
        note.setWordWrap(True)
        note.setObjectName("mutedText")
        layout.addWidget(note)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("筛选"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("输入文件名、服务器相对路径、分类标记、尺寸或状态")
        filter_row.addWidget(self.filter_edit, 1)
        self.selection_label = QLabel("已选择 0 个")
        filter_row.addWidget(self.selection_label)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["图元定义文件", "w×h", "AlignCenter", "Pins", "分类标记", "状态", "本地缓存"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        configure_responsive_table(self.table)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(70)
        layout.addWidget(self.table, 1)

        self._populate(records)
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.table.itemSelectionChanged.connect(self._update_selection_label)
        self.table.itemDoubleClicked.connect(lambda _item, _column: self.accept())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("添加选中图元")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _display_path(record: dict[str, object]) -> str:
        standard = record.get("standard_record")
        standard = standard if isinstance(standard, dict) else {}
        return str(record.get("relative_path") or standard.get("relative_path") or record.get("name", "")).strip()

    @staticmethod
    def _standard(record: dict[str, object]) -> dict[str, object]:
        raw = record.get("standard_record")
        return dict(raw) if isinstance(raw, dict) else {}

    def _populate(self, records: list[dict[str, object]]) -> None:
        rows = sorted(records, key=lambda row: self._display_path(row).casefold())
        self.table.setRowCount(len(rows))
        for row_index, record in enumerate(rows):
            standard = self._standard(record)
            cache_raw = str(record.get("cache_path", standard.get("cache_path", "")) or "").strip()
            cache_path = Path(cache_raw) if cache_raw else None
            cache_ok = bool(cache_path and cache_path.is_file())
            width = standard.get("width", "")
            height = standard.get("height", "")
            size_text = f"{width}×{height}" if str(width) and str(height) else "-"
            align = standard.get("align_center", "-")
            pins = standard.get("pins", "-")
            marker = str(
                record.get("classification_marker", standard.get("classification_marker", "")) or ""
            ).strip()
            status = str(record.get("sync_status", "READY") or "READY")
            if not cache_ok:
                status = f"{status} · 缺少本地文件"
            values = [
                self._display_path(record),
                size_text,
                str(align),
                str(pins),
                marker,
                status,
                "可用" if cache_ok else "不可用",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(self.ROLE_CACHE_PATH, str(cache_path) if cache_ok else "")
                    item.setToolTip(str(record.get("remote_path", "") or value))
                self.table.setItem(row_index, col, item)
        # Do not scan every cell with resizeColumnsToContents(): this dialog can
        # show the entire server inventory and must open instantly even on older
        # Windows workstations.  Stable widths keep every field readable and the
        # table provides pixel-level horizontal scrolling when needed.
        widths = (430, 100, 160, 340, 150, 210, 110)
        for col, width in enumerate(widths):
            self.table.setColumnWidth(col, width)

    def _apply_filter(self, text: str) -> None:
        needle = str(text or "").strip().casefold()
        for row in range(self.table.rowCount()):
            haystack = " ".join(
                self.table.item(row, col).text() if self.table.item(row, col) is not None else ""
                for col in range(self.table.columnCount())
            ).casefold()
            self.table.setRowHidden(row, bool(needle and needle not in haystack))

    def _update_selection_label(self) -> None:
        rows = {index.row() for index in self.table.selectedIndexes() if not self.table.isRowHidden(index.row())}
        usable = 0
        for row in rows:
            item = self.table.item(row, 0)
            if item is not None and str(item.data(self.ROLE_CACHE_PATH) or "").strip():
                usable += 1
        self.selection_label.setText(f"已选择 {len(rows)} 个，可添加 {usable} 个")

    def selected_paths(self) -> list[Path]:
        result: list[Path] = []
        seen: set[str] = set()
        for row in sorted({index.row() for index in self.table.selectedIndexes()}):
            if self.table.isRowHidden(row):
                continue
            item = self.table.item(row, 0)
            raw = str(item.data(self.ROLE_CACHE_PATH) or "").strip() if item is not None else ""
            if not raw:
                continue
            path = Path(raw)
            if not path.is_file():
                continue
            key = str(path.resolve(strict=False)).casefold()
            if key not in seen:
                seen.add(key)
                result.append(path)
        return result


class IconUpgradeEditor(QWidget):
    """通用 OLD -> NEW 图元升级映射编辑器。

    同名图元会自动配对；文件名发生变化时允许用户显式配对。这里只维护
    图元定义文件与升级映射，不触碰主 G 文件业务数据。
    """

    ROLE_ROW_KIND = int(Qt.ItemDataRole.UserRole) + 1
    ROLE_ROW_KEY = int(Qt.ItemDataRole.UserRole) + 2

    def __init__(self, user_settings: UserSettingsService | None = None, parent=None) -> None:
        super().__init__(parent)
        self.user_settings = user_settings
        self._old: dict[str, Path] = {}
        # Keep every uploaded NEW symbol, including ones already used by another
        # OLD mapping. This intentionally permits explicit many-OLD -> one-NEW
        # mappings, which are valid when several legacy aliases converge on one
        # current standard symbol.
        self._all_new: dict[str, Path] = {}
        self._new_for_old: dict[str, Path] = {}
        self._unmatched_new: dict[str, Path] = {}
        self._pair_method: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        source_actions = QHBoxLayout()
        source_actions.addWidget(QLabel("旧图元 OLD"))
        self.add_old_server = QPushButton("从服务器选择旧图元")
        self.add_old = QPushButton("本地添加旧图元")
        source_actions.addWidget(self.add_old_server)
        source_actions.addWidget(self.add_old)
        source_actions.addSpacing(18)
        source_actions.addWidget(QLabel("新图元 NEW"))
        self.add_new_server = QPushButton("从服务器选择新图元")
        self.add_new = QPushButton("本地添加新图元")
        source_actions.addWidget(self.add_new_server)
        source_actions.addWidget(self.add_new)
        source_actions.addStretch(1)
        for button in (self.add_old_server, self.add_old, self.add_new_server, self.add_new):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            button.setMinimumWidth(button.sizeHint().width() + 8)
        layout.addLayout(source_actions)

        actions = QHBoxLayout()
        self.auto_pair = QPushButton("智能自动配对")
        self.manual_pair = QPushButton("手动配对")
        self.manual_pair.setToolTip(
            "文件名不需要一致。选择任意旧图元行后点击这里，或不选行直接打开配对窗口，"
            "再从已上传的新图元列表中明确指定 OLD → NEW。"
        )
        self.unpair = QPushButton("解除配对")
        self.remove = QPushButton("移除选中")
        self.clear = QPushButton("清空")
        self.analyze = QPushButton("检查全部映射")
        for button in (
            self.auto_pair,
            self.manual_pair,
            self.unpair,
            self.remove,
            self.clear,
            self.analyze,
        ):
            # Keep action captions intact and prevent the button from being
            # compressed until Qt elides the label when the window is resized.
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            button.setMinimumWidth(button.sizeHint().width() + 8)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["升级规则", "旧图元文件", "新图元文件", "配对方式", "几何变化", "端口", "devref", "状态"]
        )
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(64)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        configure_responsive_table(self.table)
        self.table.setMinimumHeight(240)
        self.table.cellDoubleClicked.connect(lambda _row, _col: self._pair_selected())
        layout.addWidget(self.table)

        self.summary = QLabel(
            "尚未添加图元。可一次批量添加多份旧图元，再一次批量添加对应新图元；"
            "程序优先按完全同名配对，同名失败时再按图元主体类型 + 主体 ID 智能配对。"
            "文件名可以完全不同：自动无法确认时，点击“手动配对…”明确指定 OLD → NEW。"
        )
        self.summary.setWordWrap(True)
        self.summary.setObjectName("mutedText")
        layout.addWidget(self.summary)

        self.add_old_server.clicked.connect(lambda: self._choose_server("old"))
        self.add_new_server.clicked.connect(lambda: self._choose_server("new"))
        self.add_old.clicked.connect(lambda: self._choose("old"))
        self.add_new.clicked.connect(lambda: self._choose("new"))
        self.auto_pair.clicked.connect(self._auto_pair)
        self.manual_pair.clicked.connect(self._pair_selected)
        self.unpair.clicked.connect(self._unpair_selected)
        self.remove.clicked.connect(self._remove_selected)
        self.clear.clicked.connect(self._clear)
        self.analyze.clicked.connect(self._show_analysis)

    def pairs(self) -> list[tuple[Path, Path]]:
        return [
            (self._old[key], self._new_for_old[key])
            for key in sorted(self._old)
            if key in self._new_for_old
        ]

    # Legacy helpers retained so older callers/settings remain harmless.
    def old_paths(self) -> list[Path]:
        return [old for old, _new in self.pairs()]

    def new_paths(self) -> list[Path]:
        return [new for _old, new in self.pairs()]

    def _add_paths(self, side: str, paths: list[Path]) -> tuple[int, list[str]]:
        added = 0
        duplicates: list[str] = []
        for path in paths:
            path = Path(path)
            if not path.is_file():
                continue
            key = path.name
            target = self._old if side == "old" else self._all_new
            previous = target.get(key)
            if previous is not None and previous.resolve(strict=False) != path.resolve(strict=False):
                duplicates.append(key)
            if side == "old":
                self._old[key] = path
                pending = self._unmatched_new.pop(key, None)
                if pending is not None:
                    self._new_for_old[key] = pending
                    self._pair_method[key] = "完全同名"
            else:
                self._all_new[key] = path
                if key in self._old and key not in self._new_for_old:
                    self._new_for_old[key] = path
                    self._pair_method[key] = "完全同名"
                else:
                    self._unmatched_new[key] = path
            added += 1
        self._auto_pair(show_message=False)
        self._refresh()
        return added, sorted(set(duplicates))

    def _choose(self, side: str) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "本地选择旧图元 G 文件" if side == "old" else "本地选择新图元 G 文件",
            "",
            "G Files (*.g);;All Files (*)",
        )
        if not files:
            return
        _added, duplicates = self._add_paths(side, [Path(name) for name in files])
        if duplicates:
            QMessageBox.warning(
                self,
                "同名图元已替换",
                "以下文件名重复，当前映射逻辑按图元文件名识别，因此后选择的文件已替换前一个：\n"
                + "\n".join(duplicates),
            )

    def _server_records(self) -> list[dict[str, object]]:
        if self.user_settings is None:
            return []
        host = self.user_settings.get_value("remote_g_source/host", DEFAULT_SSH_HOST).strip() or DEFAULT_SSH_HOST
        root = self.user_settings.get_value(
            "site_profile/remote_symbol_library_root", DEFAULT_REMOTE_SYMBOL_ROOT
        ).strip() or DEFAULT_REMOTE_SYMBOL_ROOT
        payload = RemoteSymbolLibraryService().load_cached_sync_snapshot(host=host, root=root)
        rows = payload.get("server_file_records", []) if isinstance(payload, dict) else []
        return [dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _choose_server(self, side: str) -> None:
        records = self._server_records()
        if not records:
            QMessageBox.information(
                self,
                "没有服务器图元缓存",
                "当前本机没有可选择的服务器图元缓存。\n\n"
                "请先到主程序“图元管理”刷新图元列表并保存到本地缓存，之后再从这里选择。",
            )
            return
        dialog = ServerSymbolPickerDialog(records, side=side, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        paths = dialog.selected_paths()
        if not paths:
            QMessageBox.information(
                self,
                "未添加图元",
                "没有选中可用的本地图元缓存文件。若列表显示‘缺少本地文件’，请先在主程序“图元管理”中下载对应图元，或改用本地文件来源。",
            )
            return
        added, duplicates = self._add_paths(side, paths)
        message = f"已从服务器图元缓存添加 {added} 个{'旧' if side == 'old' else '新'}图元。"
        if duplicates:
            message += "\n\n以下同名图元按现有文件名映射规则以后选择者覆盖前者：\n" + "\n".join(duplicates)
        QMessageBox.information(self, "服务器图元选择完成", message)

    def _auto_pair(self, checked: bool = False, *, show_message: bool = True) -> None:
        exact_paired = 0
        identity_paired = 0

        available_old = {
            key: path for key, path in self._old.items() if key not in self._new_for_old
        }
        suggestions = suggest_icon_pairs(available_old, self._unmatched_new)
        for old_key, (new_key, method) in suggestions.items():
            new_path = self._unmatched_new.pop(new_key, None)
            if new_path is None:
                continue
            self._new_for_old[old_key] = new_path
            self._pair_method[old_key] = method
            if method == "完全同名":
                exact_paired += 1
            else:
                identity_paired += 1

        self._refresh()
        if show_message:
            total = exact_paired + identity_paired
            QMessageBox.information(
                self,
                "智能自动配对",
                f"本次自动完成 {total} 组配对：完全同名 {exact_paired} 组，"
                f"图元类型 + 主体 ID {identity_paired} 组。\n"
                "存在歧义的图元不会自动猜测，请在表格中手动配对。",
            )

    def _selected_descriptors(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for row in sorted({index.row() for index in self.table.selectedIndexes()}):
            item = self.table.item(row, 0)
            if item is None:
                continue
            kind = str(item.data(self.ROLE_ROW_KIND) or "")
            key = str(item.data(self.ROLE_ROW_KEY) or "")
            if kind and key:
                result.append((kind, key))
        return result

    @staticmethod
    def _definition_summary(path: Path | None) -> str:
        if path is None:
            return "—"
        try:
            definition = parse_icon_definition(path)
            pin_parts = []
            for idx, ((x, y), pin_id) in enumerate(zip(definition.pins, definition.pin_ids)):
                logical = definition.pin_indices[idx] if idx < len(definition.pin_indices) else ""
                label = []
                if logical:
                    label.append(f"index={logical}")
                if pin_id:
                    label.append(f"id={pin_id}")
                meta = (" " + "/".join(label)) if label else ""
                pin_parts.append(f"({x:g},{y:g}){meta}")
            pin_text = ", ".join(pin_parts) or "无"
            return (
                f"XML={definition.element_tag}  |  Body ID={definition.element_id or '—'}  |  "
                f"Size={definition.width:g}×{definition.height:g}  |  "
                f"AlignCenter=({definition.align_center[0]:g},{definition.align_center[1]:g})  |  "
                f"Pins={len(definition.pins)} [{pin_text}]"
            )
        except Exception as exc:
            return f"无法读取图元属性：{exc}"

    def _pair_old_to_new(self, old_key: str, new_key: str) -> tuple[bool, str]:
        old_path = self._old.get(old_key)
        new_path = self._all_new.get(new_key)
        if old_path is None:
            return False, "所选旧图元已不存在，请重新选择。"
        if new_path is None:
            return False, "所选新图元已不存在，请重新选择。"

        # Manual pairing may use completely different filenames/body IDs, but
        # electrical structure still has to be safe. The engine deliberately
        # permits a body-ID rename; incompatible XML tags / pin topology remain
        # blockers.
        analysis = analyze_icon_mappings([(old_path, new_path)])
        if analysis.incompatible or not analysis.rules:
            detail = "\n".join(analysis.incompatible) or "图元结构无法建立安全升级规则。"
            return False, detail

        previous = self._new_for_old.get(old_key)
        self._new_for_old[old_key] = new_path
        self._pair_method[old_key] = "手动确认"
        self._unmatched_new.pop(new_key, None)

        # If the OLD row used to point elsewhere, put that former NEW back into
        # the unmatched pool only when no other explicit mapping still uses it.
        if previous is not None and previous != new_path:
            still_used = any(
                mapped == previous
                for key, mapped in self._new_for_old.items()
                if key != old_key
            )
            if not still_used:
                self._unmatched_new[previous.name] = previous
        return True, ""

    def _pair_selected(self) -> None:
        if not self._old:
            QMessageBox.information(self, "手动配对", "请先批量添加至少一个旧图元 G 文件。")
            return
        if not self._all_new:
            QMessageBox.information(self, "手动配对", "请先批量添加至少一个新图元 G 文件。")
            return

        descriptors = self._selected_descriptors()
        selected_old = next((key for kind, key in descriptors if kind == "old"), "")
        selected_new = next((key for kind, key in descriptors if kind == "new"), "")
        if selected_old and not selected_new:
            current = self._new_for_old.get(selected_old)
            if current is not None:
                selected_new = current.name

        dialog = QDialog(self)
        dialog.setWindowTitle("手动 OLD → NEW 图元配对")
        dialog.setMinimumWidth(760)
        main = QVBoxLayout(dialog)

        note = QLabel(
            "文件名不要求一致。请选择要升级的旧图元和它对应的新图元；"
            "手动配对优先级最高。程序仍会检查 XML 类型与端口结构，避免错误映射。"
        )
        note.setWordWrap(True)
        note.setObjectName("mutedText")
        main.addWidget(note)

        form = QFormLayout()
        old_combo = WheelSafeComboBox()
        new_combo = WheelSafeComboBox()
        for key in sorted(self._old):
            old_combo.addItem(key, key)
        for key in sorted(self._all_new):
            used_by = [old for old, path in self._new_for_old.items() if path.name == key]
            suffix = f"  [已用于: {', '.join(used_by)}]" if used_by else ""
            new_combo.addItem(key + suffix, key)
        form.addRow("旧图元 OLD", old_combo)
        form.addRow("新图元 NEW", new_combo)
        main.addLayout(form)

        old_info = QLabel()
        new_info = QLabel()
        old_info.setWordWrap(True)
        new_info.setWordWrap(True)
        old_info.setObjectName("mutedText")
        new_info.setObjectName("mutedText")
        main.addWidget(QLabel("旧图元属性"))
        main.addWidget(old_info)
        main.addWidget(QLabel("新图元属性"))
        main.addWidget(new_info)

        def select_key(combo: WheelSafeComboBox, key: str) -> None:
            if not key:
                return
            for index in range(combo.count()):
                if combo.itemData(index) == key:
                    combo.setCurrentIndex(index)
                    break

        def refresh_preview() -> None:
            old_key = str(old_combo.currentData() or "")
            new_key = str(new_combo.currentData() or "")
            old_info.setText(self._definition_summary(self._old.get(old_key)))
            new_info.setText(self._definition_summary(self._all_new.get(new_key)))

        select_key(old_combo, selected_old)
        select_key(new_combo, selected_new)
        old_combo.currentIndexChanged.connect(refresh_preview)
        new_combo.currentIndexChanged.connect(refresh_preview)
        refresh_preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText("确认配对")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        main.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_key = str(old_combo.currentData() or "")
        new_key = str(new_combo.currentData() or "")
        ok, message = self._pair_old_to_new(old_key, new_key)
        if not ok:
            QMessageBox.warning(
                self,
                "手动配对不兼容",
                "文件名可以不同，但这两份图元的结构无法安全升级：\n\n" + message,
            )
            return
        self._refresh()
        QMessageBox.information(
            self,
            "手动配对完成",
            f"已建立手动映射：\n{old_key}\n→\n{new_key}",
        )

    def _unpair_selected(self) -> None:
        descriptors = self._selected_descriptors()
        old_keys = [key for kind, key in descriptors if kind == "old"]
        changed = 0
        for old_key in old_keys:
            new_path = self._new_for_old.pop(old_key, None)
            self._pair_method.pop(old_key, None)
            if new_path is not None:
                still_used = any(mapped == new_path for mapped in self._new_for_old.values())
                if not still_used:
                    self._unmatched_new[new_path.name] = new_path
                changed += 1
        self._refresh()
        if not changed:
            QMessageBox.information(self, "解除配对", "请选择至少一个已经完成配对的旧图元行。")

    def _remove_selected(self) -> None:
        descriptors = self._selected_descriptors()
        for kind, key in descriptors:
            if kind == "old":
                self._old.pop(key, None)
                previous = self._new_for_old.pop(key, None)
                self._pair_method.pop(key, None)
                if previous is not None and not any(
                    mapped == previous for mapped in self._new_for_old.values()
                ):
                    self._unmatched_new[previous.name] = previous
            elif kind == "new":
                self._unmatched_new.pop(key, None)
                self._all_new.pop(key, None)
        self._refresh()

    def _clear(self) -> None:
        self._old.clear()
        self._new_for_old.clear()
        self._all_new.clear()
        self._unmatched_new.clear()
        self._pair_method.clear()
        self._refresh()

    def _rows(self) -> list[tuple[str, str, Path | None, Path | None]]:
        rows: list[tuple[str, str, Path | None, Path | None]] = []
        for key in sorted(self._old):
            rows.append(("old", key, self._old[key], self._new_for_old.get(key)))
        for key in sorted(self._unmatched_new):
            rows.append(("new", key, None, self._unmatched_new[key]))
        return rows

    @staticmethod
    def _short(path: Path | None) -> str:
        return path.name if path else "—"

    def _refresh(self) -> None:
        rows = self._rows()
        self.table.setRowCount(len(rows))
        for row, (kind, key, old, new) in enumerate(rows):
            if old and new:
                rule_text = f"{old.name} → {new.name}"
                status = "待检查"
            elif old:
                rule_text = old.name
                status = "缺少新图元"
            else:
                rule_text = f"未配对新图元：{new.name if new else key}"
                status = "缺少旧图元"
            pair_method = self._pair_method.get(key, "—") if old and new else "—"
            values = [rule_text, self._short(old), self._short(new), pair_method, "—", "—", "—", status]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(self.ROLE_ROW_KIND, kind)
                    item.setData(self.ROLE_ROW_KEY, key)
                if col == 1 and old:
                    item.setToolTip(str(old))
                if col == 2 and new:
                    item.setToolTip(str(new))
                self.table.setItem(row, col, item)
        complete = len(self.pairs())
        missing_old = len(self._unmatched_new)
        missing_new = len(self._old) - complete
        self.summary.setText(
            f"旧图元 {len(self._old)} 种，新图元 {len(self._all_new)} 种；"
            f"完整映射 {complete} 种，缺少新图元 {missing_new} 种，未配对新图元 {missing_old} 种。"
            " 文件名不要求一致；未自动配对的项目可选中旧图元后点击“手动配对…”。"
        )
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        QTimer.singleShot(0, self._fit_table)

    def _fit_table(self) -> None:
        self.table.resizeColumnsToContents()
        minimums = (260, 190, 190, 150, 190, 100, 220, 190)
        maximums = (520, 340, 340, 260, 420, 160, 440, 520)
        for col in range(self.table.columnCount()):
            width = max(self.table.columnWidth(col), minimums[col])
            width = min(width, maximums[col])
            self.table.setColumnWidth(col, width)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, max(38, self.table.rowHeight(row)))

    def analysis(self):
        return analyze_icon_mappings(self.pairs())

    def validate_for_run(self) -> tuple[bool, str]:
        if not self._old and not self._unmatched_new:
            return False, "已启用同类图元版本升级，但尚未添加 OLD 图元和 NEW 图元 G 文件。"
        problems: list[str] = []
        missing_new = [key for key in sorted(self._old) if key not in self._new_for_old]
        if missing_new:
            problems.append("缺少新图元：" + ", ".join(missing_new))
        if self._unmatched_new:
            problems.append("存在未配对新图元：" + ", ".join(sorted(self._unmatched_new)))
        try:
            analysis = self.analysis()
        except Exception as exc:
            return False, str(exc)
        if analysis.incompatible:
            problems.append("不兼容：\n" + "\n".join(analysis.incompatible))
        if not analysis.rules:
            problems.append("没有可用的 OLD → NEW 图元映射。")
        if problems:
            return False, "\n".join(problems)
        return True, f"同类图元版本升级映射检查通过，共 {len(analysis.rules)} 种。"

    def _show_analysis(self) -> None:
        ok, message = self.validate_for_run()
        try:
            analysis = self.analysis()
        except Exception:
            analysis = None
        if analysis is not None:
            by_name = analysis.rules
            for row, (kind, key, old_path, new_path) in enumerate(self._rows()):
                if kind != "old":
                    continue
                rule = by_name.get(key)
                if rule:
                    geometry = (
                        f"{rule.old.width:g}×{rule.old.height:g} → {rule.new.width:g}×{rule.new.height:g}; "
                        f"AC {rule.old.align_center} → {rule.new.align_center}"
                    )
                    pins = f"{len(rule.old.pins)} → {len(rule.new.pins)}"
                    devref = (
                        "保持原 devref" if rule.old.file_name == rule.new.file_name
                        else f"#{rule.old.file_name}:… → #{rule.new.file_name}:{rule.new_reference_name}"
                    )
                    for col, value in ((4, geometry), (5, pins), (6, devref), (7, "✓ Ready")):
                        item = QTableWidgetItem(value)
                        item.setToolTip(value)
                        self.table.setItem(row, col, item)
        self.summary.setText(message)
        self._schedule_fit()
        if ok:
            QMessageBox.information(self, "同类图元版本升级检查", message)
        else:
            QMessageBox.warning(self, "同类图元版本升级检查未通过", message)
