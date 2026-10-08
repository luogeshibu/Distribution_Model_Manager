from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from g_file_studio.engines import merge_engine
from g_file_studio.engines.merge_frame_inspector import (
    FRAME_BUILTIN,
    FRAME_UNSUPPORTED,
)
from g_file_studio.ui.table_layout import configure_responsive_table
from g_file_studio.ui.widgets.help_widgets import set_secondary


class CandidateImportDialog(QDialog):
    """按文件名模糊查询，并把选中的可用文件导入合并顺序列表。"""

    def __init__(
        self,
        candidates: list[merge_engine.MergeCandidateInspection],
        existing_names: set[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("查询并导入 G 文件")
        self.resize(980, 620)
        self._candidates = candidates
        self._existing_names = {name.casefold() for name in existing_names}
        self._selected_names: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        note = QLabel(
            "输入文件名关键字进行模糊查询；多个关键字用空格分隔，文件名需同时包含这些关键字。"
            "只有无图框文件和 G File Studio 内置图框文件可选择；内置图框会在合并前自动移除。"
        )
        note.setWordWrap(True)
        note.setObjectName("mutedText")
        root.addWidget(note)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_label = QLabel("文件名关键字")
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("例如：AJWD 48；留空显示全部文件")
        self.search_edit.setToolTip("不区分大小写；多个空格分隔关键字采用同时包含的匹配方式。")
        search_row.addWidget(search_label)
        search_row.addWidget(self.search_edit, 1)
        root.addLayout(search_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.select_all_button = QPushButton("全选当前结果")
        self.clear_button = QPushButton("取消当前选择")
        set_secondary(self.select_all_button)
        set_secondary(self.clear_button)
        action_row.addWidget(self.select_all_button)
        action_row.addWidget(self.clear_button)
        action_row.addStretch(1)
        self.result_label = QLabel()
        self.result_label.setObjectName("mutedText")
        action_row.addWidget(self.result_label)
        root.addLayout(action_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["选择", "文件名", "图框检查", "状态/原因"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        configure_responsive_table(self.table)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.import_button = QPushButton("确认导入")
        set_secondary(self.cancel_button)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.import_button)
        root.addLayout(bottom)

        self.search_edit.textChanged.connect(self._apply_filter)
        self.select_all_button.clicked.connect(self._select_all_visible)
        self.clear_button.clicked.connect(self._clear_visible)
        self.cancel_button.clicked.connect(self.reject)
        self.import_button.clicked.connect(self._accept_import)
        self.table.itemDoubleClicked.connect(self._toggle_row)

        self._rebuild_table()
        self.search_edit.setFocus()

    def selected_names(self) -> list[str]:
        return list(self._selected_names)

    @staticmethod
    def _frame_label(candidate: merge_engine.MergeCandidateInspection) -> str:
        if candidate.frame_kind == FRAME_BUILTIN:
            return "内置图框"
        if candidate.frame_kind == FRAME_UNSUPPORTED:
            return "非内置图框"
        if candidate.frame_kind == "invalid":
            return "无法检查"
        return "无图框"

    def _rebuild_table(self) -> None:
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            existing = candidate.info.path.name.casefold() in self._existing_names

            check_item = QTableWidgetItem("")
            check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            if candidate.eligible and not existing:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
                check_item.setCheckState(Qt.CheckState.Unchecked)
            elif existing:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
                check_item.setCheckState(Qt.CheckState.Checked)
                check_item.setToolTip("该文件已经在合并顺序列表中。")
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            else:
                check_item.setCheckState(Qt.CheckState.Unchecked)
                check_item.setToolTip(candidate.error or candidate.status)
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            check_item.setFlags(flags)
            self.table.setItem(row, 0, check_item)

            name_item = QTableWidgetItem(candidate.info.path.name)
            frame_item = QTableWidgetItem(self._frame_label(candidate))
            if existing:
                status_text = "已在列表"
            elif candidate.error:
                reason = candidate.error.splitlines()[-1].strip()
                status_text = f"{candidate.status}：{reason}"
            else:
                status_text = candidate.status
            status_item = QTableWidgetItem(status_text)
            if candidate.error:
                status_item.setToolTip(candidate.error)
                name_item.setToolTip(candidate.error)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, frame_item)
            self.table.setItem(row, 3, status_item)

        self._apply_filter(self.search_edit.text())

    def _matches(self, filename: str, text: str) -> bool:
        keywords = [part.casefold() for part in text.split() if part.strip()]
        value = filename.casefold()
        return all(keyword in value for keyword in keywords)

    def _apply_filter(self, text: str) -> None:
        visible = 0
        eligible_visible = 0
        for row, candidate in enumerate(self._candidates):
            matched = self._matches(candidate.info.path.name, text)
            self.table.setRowHidden(row, not matched)
            if matched:
                visible += 1
                if candidate.eligible:
                    eligible_visible += 1
        self.result_label.setText(
            f"当前匹配 {visible} 个，其中 {eligible_visible} 个可导入。"
        )

    def _select_all_visible(self) -> None:
        for row, candidate in enumerate(self._candidates):
            if self.table.isRowHidden(row):
                continue
            if not candidate.eligible:
                continue
            if candidate.info.path.name.casefold() in self._existing_names:
                continue
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

    def _clear_visible(self) -> None:
        for row, candidate in enumerate(self._candidates):
            if self.table.isRowHidden(row):
                continue
            if candidate.info.path.name.casefold() in self._existing_names:
                continue
            item = self.table.item(row, 0)
            if item is not None and candidate.eligible:
                item.setCheckState(Qt.CheckState.Unchecked)

    def _toggle_row(self, item: QTableWidgetItem) -> None:
        row = item.row()
        candidate = self._candidates[row]
        if not candidate.eligible:
            return
        if candidate.info.path.name.casefold() in self._existing_names:
            return
        check_item = self.table.item(row, 0)
        if check_item is None:
            return
        new_state = (
            Qt.CheckState.Unchecked
            if check_item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
        check_item.setCheckState(new_state)

    def _accept_import(self) -> None:
        selected: list[str] = []
        for row, candidate in enumerate(self._candidates):
            if not candidate.eligible:
                continue
            if candidate.info.path.name.casefold() in self._existing_names:
                continue
            item = self.table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                selected.append(candidate.info.path.name)
        if not selected:
            QMessageBox.information(
                self,
                "尚未选择文件",
                "请勾选一个或多个可参与合并的文件，或者点击“全选当前结果”。",
            )
            return
        self._selected_names = selected
        self.accept()


class FileOrderEditor(QWidget):
    """加载候选文件、模糊查询导入，并自由调整实际合并顺序。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._input_dir = Path()
        self._rows: list[dict[str, str]] = []
        self._catalog: list[merge_engine.MergeCandidateInspection] = []
        self._excluded_names: set[str] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(9)

        note = QLabel(
            "先点击“加载 / 检查”扫描目录。加载时会显示进度并检查图框：内置图框可参与合并，"
            "合并前会自动移除；客户或未知图框禁止参与。随后可通过“查询并导入”按文件名模糊查询、"
            "选择或全选并导入列表，再执行删除、置顶、上移、下移和置底。"
        )
        note.setObjectName("mutedText")
        note.setWordWrap(True)
        root.addWidget(note)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.refresh_button = QPushButton("加载 / 检查")
        self.import_button = QPushButton("查询并导入")
        self.natural_button = QPushButton("导入全部可用")
        self.delete_button = QPushButton("删除所选")
        self.top_button = QPushButton("置顶")
        self.up_button = QPushButton("上移")
        self.down_button = QPushButton("下移")
        self.bottom_button = QPushButton("置底")

        for button in (
            self.refresh_button,
            self.import_button,
            self.natural_button,
            self.delete_button,
            self.top_button,
            self.up_button,
            self.down_button,
            self.bottom_button,
        ):
            set_secondary(button)
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.summary_label = QLabel("尚未加载输入目录。")
        self.summary_label.setObjectName("mutedText")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["顺序", "文件名", "垂直对齐基准", "原始基准 Y", "状态"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        configure_responsive_table(self.table)
        self.table.setMinimumHeight(230)
        root.addWidget(self.table)

        self.refresh_button.setToolTip(
            "显示加载进度，重新扫描目录并检查 XML、对齐基准和图框类型。"
        )
        self.import_button.setToolTip(
            "打开模糊查询窗口，输入文件名关键字，选择或全选匹配文件后导入当前列表。"
        )
        self.natural_button.setToolTip(
            "把目录中全部可参与合并的文件按自然文件名顺序导入；非内置图框和检查失败文件不会导入。"
        )
        self.delete_button.setToolTip(
            "从本次合并列表移除所选文件。支持 Ctrl/Shift 多选；不会删除磁盘源文件。"
        )
        self.top_button.setToolTip("把当前选中的一行移动到第一位，并作为合并基准文件。")
        self.up_button.setToolTip("把当前选中的一行向前移动一位。")
        self.down_button.setToolTip("把当前选中的一行向后移动一位。")
        self.bottom_button.setToolTip("把当前选中的一行移动到最后一位。")

        self.refresh_button.clicked.connect(self.load_candidates)
        self.import_button.clicked.connect(self.open_import_dialog)
        self.natural_button.clicked.connect(self.import_all_eligible)
        self.delete_button.clicked.connect(self.remove_selected)
        self.top_button.clicked.connect(self.move_top)
        self.up_button.clicked.connect(lambda: self.move_selected(-1))
        self.down_button.clicked.connect(lambda: self.move_selected(1))
        self.bottom_button.clicked.connect(self.move_bottom)

    def set_input_dir(self, path: Path | str) -> None:
        new_path = Path(path)
        if str(new_path) != str(self._input_dir):
            self._input_dir = new_path
            self.clear(reset_exclusions=True, reset_catalog=True)

    def input_dir(self) -> Path:
        return self._input_dir

    def clear(
        self,
        *,
        reset_exclusions: bool = True,
        reset_catalog: bool = False,
    ) -> None:
        self._rows.clear()
        if reset_exclusions:
            self._excluded_names.clear()
        if reset_catalog:
            self._catalog.clear()
        self.table.setRowCount(0)
        self._update_summary()

    def ordered_file_names(self) -> list[str]:
        """当前主列表就是最终参与合并的文件集合和顺序。"""
        return [row["file_name"] for row in self._rows]

    def excluded_file_names(self) -> list[str]:
        return sorted(self._excluded_names)

    def _show_loading_progress(self) -> QProgressDialog:
        progress = QProgressDialog(
            "正在加载并检查 G 文件……",
            "取消",
            0,
            100,
            self,
        )
        progress.setWindowTitle("加载中")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        QApplication.processEvents()
        return progress

    def load_candidates(
        self,
        preserve_order: bool = True,
        show_errors: bool = True,
        open_import_after_load: bool = True,
    ) -> bool:
        progress = self._show_loading_progress()

        class LoadingCancelled(RuntimeError):
            pass

        def update(done: int, total: int, filename: str) -> None:
            progress.setRange(0, 100)
            progress.setValue(round(done * 100 / max(1, total)))
            progress.setLabelText(
                f"正在加载并检查 G 文件…… {done}/{total}\n{filename}"
            )
            QApplication.processEvents()
            if progress.wasCanceled():
                raise LoadingCancelled("用户取消了文件加载。")

        try:
            catalog = merge_engine.inspect_merge_candidates(
                self._input_dir,
                progress_callback=update,
            )
        except LoadingCancelled:
            progress.close()
            self._update_summary()
            return False
        except Exception as exc:
            progress.close()
            if show_errors:
                QMessageBox.warning(self, "输入目录加载失败", str(exc))
            return False
        finally:
            progress.close()

        self._catalog = catalog
        all_keys = {item.info.path.name.casefold() for item in catalog}
        self._excluded_names.intersection_update(all_keys)
        eligible_map = {
            item.info.path.name.casefold(): item
            for item in catalog
            if item.eligible
        }

        removed_unavailable: list[str] = []
        if preserve_order:
            existing_names = self.ordered_file_names()
            new_rows: list[dict[str, str]] = []
            for name in existing_names:
                candidate = eligible_map.get(name.casefold())
                if candidate is None:
                    removed_unavailable.append(name)
                    continue
                new_rows.append(self._row_from_candidate(candidate))
            self._rows = new_rows
        else:
            self._rows = []

        self._rebuild_table()
        if removed_unavailable and show_errors:
            QMessageBox.warning(
                self,
                "部分文件已移出列表",
                "以下文件已经不存在、检查失败，或检测到非内置图框，已不能参与本次合并：\n\n"
                + "\n".join(f"• {name}" for name in removed_unavailable),
            )

        if open_import_after_load:
            self.open_import_dialog(load_if_needed=False)
        return True

    # 保留旧调用名，方便页面和既有测试兼容。
    def refresh(self, preserve_order: bool = True, show_errors: bool = True) -> bool:
        return self.load_candidates(
            preserve_order=preserve_order,
            show_errors=show_errors,
            open_import_after_load=not bool(self._rows),
        )

    def _row_from_candidate(
        self,
        candidate: merge_engine.MergeCandidateInspection,
    ) -> dict[str, str]:
        alignment_y = (
            merge_engine.format_integer(candidate.alignment_y)
            if candidate.alignment_y is not None
            else ""
        )
        return {
            "file_name": candidate.info.path.name,
            "alignment_mode": candidate.alignment_mode,
            "alignment_y": alignment_y,
            "status": candidate.status,
        }

    def open_import_dialog(self, *, load_if_needed: bool = True) -> None:
        if not self._catalog:
            if not load_if_needed:
                return
            if not self.load_candidates(
                preserve_order=True,
                show_errors=True,
                open_import_after_load=False,
            ):
                return

        dialog = CandidateImportDialog(
            self._catalog,
            set(self.ordered_file_names()),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_keys = {name.casefold() for name in dialog.selected_names()}
        existing_keys = {name.casefold() for name in self.ordered_file_names()}
        for candidate in self._catalog:
            key = candidate.info.path.name.casefold()
            if key not in selected_keys or key in existing_keys or not candidate.eligible:
                continue
            self._rows.append(self._row_from_candidate(candidate))
            self._excluded_names.discard(key)
            existing_keys.add(key)
        self._rebuild_table()
        if self._rows:
            self.table.selectRow(len(self._rows) - 1)

    def import_all_eligible(self) -> None:
        if not self._catalog:
            if not self.load_candidates(
                preserve_order=False,
                show_errors=True,
                open_import_after_load=False,
            ):
                return
        self._excluded_names.clear()
        self._rows = [
            self._row_from_candidate(candidate)
            for candidate in self._catalog
            if candidate.eligible
        ]
        self._rebuild_table()
        if not self._rows:
            QMessageBox.warning(
                self,
                "没有可合并文件",
                "目录中没有通过检查的文件。非内置图框和检查失败文件不会参与合并。",
            )

    def reset_natural_order(self) -> None:
        """兼容旧接口：导入全部可用文件并使用自然排序。"""
        self.import_all_eligible()

    def ensure_ready(self) -> bool:
        """运行前重新加载检查，并只允许主列表中的可用文件参与合并。"""
        if not self.load_candidates(
            preserve_order=True,
            show_errors=True,
            open_import_after_load=False,
        ):
            return False
        if not self._rows:
            QMessageBox.warning(
                self,
                "尚未导入文件",
                "请点击“查询并导入”，按关键字选择文件；也可以点击“导入全部可用”。",
            )
            return False
        return True

    def remove_selected(self) -> None:
        """从本次合并集合删除选中行，不删除磁盘文件。"""
        selection_model = self.table.selectionModel()
        selected_rows = sorted(
            {index.row() for index in selection_model.selectedRows()},
            reverse=True,
        )
        if not selected_rows:
            QMessageBox.information(
                self,
                "请选择文件",
                "请先在表格中选择一个或多个要从本次合并列表移除的文件。",
            )
            return

        names = [self._rows[row]["file_name"] for row in reversed(selected_rows)]
        answer = QMessageBox.question(
            self,
            "从本次合并列表移除",
            f"确定从本次合并列表移除所选的 {len(names)} 个文件吗？\n\n"
            "此操作不会删除磁盘上的源文件。可再次通过“查询并导入”加入。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        first_removed_row = min(selected_rows)
        for row in selected_rows:
            item = self._rows.pop(row)
            self._excluded_names.add(item["file_name"].casefold())

        self._rebuild_table()
        if self._rows:
            self.table.selectRow(min(first_removed_row, len(self._rows) - 1))

    def move_selected(self, offset: int) -> None:
        row = self.table.currentRow()
        if row < 0 or not self._rows:
            return
        target = max(0, min(len(self._rows) - 1, row + offset))
        if target == row:
            return
        item = self._rows.pop(row)
        self._rows.insert(target, item)
        self._rebuild_table()
        self.table.selectRow(target)

    def move_top(self) -> None:
        row = self.table.currentRow()
        if row <= 0:
            return
        item = self._rows.pop(row)
        self._rows.insert(0, item)
        self._rebuild_table()
        self.table.selectRow(0)

    def move_bottom(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows) - 1:
            return
        item = self._rows.pop(row)
        self._rows.append(item)
        self._rebuild_table()
        self.table.selectRow(len(self._rows) - 1)

    def _update_summary(self) -> None:
        if not self._catalog:
            self.summary_label.setText("尚未加载输入目录。")
            return
        total = len(self._catalog)
        eligible = sum(1 for item in self._catalog if item.eligible)
        builtin = sum(1 for item in self._catalog if item.frame_kind == FRAME_BUILTIN)
        blocked = sum(1 for item in self._catalog if item.frame_kind == FRAME_UNSUPPORTED)
        invalid = sum(1 for item in self._catalog if item.frame_kind == "invalid")
        self.summary_label.setText(
            f"已加载 {total} 个文件：可参与 {eligible} 个（其中内置图框 {builtin} 个，合并时自动移除）；"
            f"非内置图框禁止参与 {blocked} 个；检查失败 {invalid} 个。"
            f"当前已导入合并列表 {len(self._rows)} 个。"
        )

    def _rebuild_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            values = [
                str(row_index + 1),
                row["file_name"],
                row["alignment_mode"],
                row["alignment_y"],
                row["status"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (0, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, column, item)
        self._update_summary()
