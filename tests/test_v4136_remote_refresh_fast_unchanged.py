from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "dmm" / "ui" / "main_window.py"


def _body(text: str, name: str, next_name: str) -> str:
    start = text.index(f"    def {name}")
    end = text.index(f"    def {next_name}", start)
    return text[start:end]


def test_remote_signature_uses_name_size_and_mtime():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "_remote_rows_signature", "_on_remote_g_files_loaded")
    assert "item.name" in body
    assert "item.size" in body
    assert "item.mtime_epoch" in body


def test_unchanged_refresh_skips_table_rebuild_and_snapshot_invalidation():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "_on_remote_g_files_loaded", "_on_remote_g_files_failed")
    assert "same_files" in body
    assert "if same_files:" in body
    fast_path = body[body.index("if same_files:"):body.index("self._set_ssh_connection_status(\n                f\"远程目录读取完成", body.index("if same_files:"))]
    assert "self._rebuild_remote_file_table()" not in fast_path
    assert "self._invalidate_validation_snapshot" not in fast_path
    assert "table rebuild skipped" in fast_path
    assert "已跳过表格重建" in fast_path


def test_changed_refresh_still_rebuilds_and_invalidates_snapshot():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "_on_remote_g_files_loaded", "_on_remote_g_files_failed")
    assert "self._rebuild_remote_file_table()" in body
    assert 'self._invalidate_validation_snapshot("远程 G 文件列表已变化")' in body


def test_remote_table_disables_continuous_resize_during_population():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "_rebuild_remote_file_table", "_apply_remote_file_filter")
    interactive = "header.setSectionResizeMode(column, QHeaderView.Interactive)"
    assert interactive in body
    assert body.index(interactive) < body.index("table.setRowCount")
    assert "table.resizeColumnsToContents()" in body
    assert body.index("table.resizeColumnsToContents()") > body.index("table.setItem(row_index, column, item)")
    assert "header.setSectionResizeMode(1, QHeaderView.Stretch)" in body
