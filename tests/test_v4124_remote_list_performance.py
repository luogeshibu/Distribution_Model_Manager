from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = ROOT / "src" / "dmm" / "ui" / "main_window.py"


def _method_body(text: str, name: str, next_name: str) -> str:
    start = text.index(f"    def {name}")
    end = text.index(f"    def {next_name}", start)
    return text[start:end]


def test_remote_search_uses_debounce_and_row_visibility_not_table_rebuild():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    assert "self._remote_filter_timer.setInterval(120)" in text
    assert "self._schedule_remote_file_filter" in text

    body = _method_body(text, "_apply_remote_file_filter", "_update_remote_count_label")
    assert "setRowHidden" in body
    assert "setRowCount" not in body
    assert "QTableWidgetItem" not in body


def test_remote_table_is_built_only_when_remote_directory_is_refreshed():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    refresh_start = text.index("    def refresh_remote_g_files")
    refresh_end = text.index("    def download_selected_remote_g_files", refresh_start)
    refresh_body = text[refresh_start:refresh_end]
    assert "self._rebuild_remote_file_table()" in refresh_body


def test_clear_selection_and_search_reuses_existing_rows():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    body = _method_body(text, "_clear_remote_selection", "_selected_remote_files")
    assert "self.remote_selected_names.clear()" in body
    assert "self.remote_search_edit.clear()" in body
    assert "setRowHidden(row, False)" in body
    assert "setRowCount" not in body
    assert "QTableWidgetItem" not in body
    assert "self._rebuild_remote_file_table()" not in body
    assert "table.blockSignals(True)" in body
    assert "table.setUpdatesEnabled(False)" in body


def test_select_visible_results_ignores_filtered_out_rows():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    body = _method_body(text, "_set_visible_remote_selection", "_clear_remote_selection")
    assert "table.isRowHidden(row)" in body
