from pathlib import Path

from dmm.i18n import tr, translate_runtime_text


ROOT = Path(__file__).resolve().parents[1]
MAIN_WINDOW = ROOT / "src" / "dmm" / "ui" / "main_window.py"


def test_remote_file_controls_remove_unselect_and_are_bilingual():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    assert 'QPushButton("取消当前结果")' not in text
    assert 'QPushButton("清空选择和搜索")' in text
    assert tr("全选当前结果", "en_US") == "Select Visible Results"
    assert tr("清空选择和搜索", "en_US") == "Clear Selection & Search"


def test_clear_remote_selection_resets_selection_and_search():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    start = text.index("    def _clear_remote_selection(self):")
    end = text.index("    def _selected_remote_files", start)
    body = text[start:end]

    assert "self.remote_selected_names.clear()" in body
    assert "self.remote_search_edit.clear()" in body
    assert 'self._apply_remote_file_filter("")' not in body
    assert 'table.setRowHidden(row, False)' in body
    assert 'self._rebuild_remote_file_table()' not in body
    assert "远程 G 文件选择和搜索条件已清空" in body


def test_remote_reset_runtime_message_translates_to_english():
    source = "输入已变化，请重新执行模型校验：远程 G 文件选择和搜索条件已清空"
    translated = translate_runtime_text(source, "en_US")
    assert "Input changed. Run Model Validation again:" in translated
    assert "remote G-file selection and search filter cleared" in translated
