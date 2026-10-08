from pathlib import Path


MAIN_WINDOW = Path(__file__).resolve().parents[1] / "src" / "dmm" / "ui" / "main_window.py"


def _text():
    return MAIN_WINDOW.read_text(encoding="utf-8")


def test_integrated_bulk_reuses_model_workspace_source_controls():
    text = _text()
    workspace = text[
        text.index("    def _build_workspace_page(self):"):
        text.index("    def _update_module_stack_height", text.index("    def _build_workspace_page(self):"))
    ]
    assert "self.input_source_combo" in workspace
    assert "self.input_source_stack" in workspace
    assert "self.input_edit" in workspace
    assert "self.ssh_edits" in workspace
    assert "self.remote_search_edit" in workspace
    assert "self.remote_file_table" in workspace
    assert 'self.module_combo.addItem("一键多模型关联", "BULK")' in workspace


def test_bulk_validation_reads_shared_source_directly_without_mirror_sync():
    text = _text()
    start = text[
        text.index("    def start_batch_validation(self):"):
        text.index("    def _on_batch_validation_completed", text.index("    def start_batch_validation(self):"))
    ]
    assert "self._current_input_source()" in start
    assert "self.input_edit.text().strip()" in start
    assert "self._selected_remote_files()" in start
    assert "self._sync_workspace_source_controls_from_batch()" not in start


def test_model_workspace_remains_scrollable_with_integrated_bulk_configuration():
    text = _text()
    block = text[
        text.index("    def _build_workspace_page(self):"):
        text.index("    def _update_module_stack_height", text.index("    def _build_workspace_page(self):"))
    ]
    assert 'outer_scroll = QScrollArea()' in block
    assert 'outer_scroll.setWidgetResizable(True)' in block
    assert 'outer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)' in block
