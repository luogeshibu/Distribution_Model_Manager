import re
from pathlib import Path

from dmm.i18n import tr


def _main_source():
    return Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_apply_model_association_caption_is_complete_and_not_fixed_width_clipped():
    assert tr("执行模型关联", "en_US") == "Apply Model Association"
    src = _main_source()
    # English caption is longer than the Chinese baseline; the action buttons
    # may grow horizontally but retain the same height.
    action_block = src.split("# 底部操作按钮", 1)[1].split("layout.addLayout(actions)", 1)[0]
    assert "button.setMinimumWidth(168)" in action_block
    assert "button.setFixedHeight(42)" in action_block
    assert "button.setFixedSize(168, 42)" not in action_block


def test_completion_dialog_is_explicitly_localized_after_dynamic_creation():
    src = _main_source()
    block = src.split("summary_box = QMessageBox(self)", 1)[1].split("summary_box.exec()", 1)[0]
    assert 'summary_box.setWindowTitle(self._t("模型关联完成"))' in block
    assert 'if self.language == "en_US":' in block
    assert "Model association processing completed." in block
    assert "Written successfully:" in block
    assert "Skipped during execution:" in block
    assert 'self._t("打开结果目录")' in block
    assert 'self._t("打开 HTML")' in block
    assert 'self._t("打开修改记录")' in block
    assert 'self._t("关闭")' in block


def test_completion_status_texts_have_exact_english_translations():
    strings = [
        "模型关联完成",
        "模型关联完成，最终 HTML / CSV 报告已生成",
        "模型关联完成，最终报告已生成",
        "打开结果目录",
        "打开修改记录",
        "关闭",
    ]
    han = re.compile(r"[\u4e00-\u9fff]")
    for source in strings:
        translated = tr(source, "en_US")
        assert translated != source
        assert not han.search(translated), (source, translated)


def test_association_confirmation_has_dedicated_english_copy():
    src = _main_source()
    block = src.split('if module_id.upper() == "RMU":', 1)[1].split(
        "reply = QMessageBox.question", 1
    )[0]
    assert "Proceed with model association?" in block
    assert "This run will process only" in block
    assert "Original G files" in block
    assert 'self.language == "en_US"' in block


def test_association_table_dynamic_status_and_counts_are_localized_for_english():
    src = _main_source()
    table_block = src.split("def _populate_association_table", 1)[1].split(
        "def _selected_association_keys", 1
    )[0]
    assert 'current_text = self._rt(str(' in table_block

    count_block = src.split("def _update_association_selection_state", 1)[1].split(
        "def _on_association_selection_changed", 1
    )[0]
    assert 'if self.language == "en_US":' in count_block
    assert 'f"Selected {selected_count} {unit} / "' in count_block
    assert 'f"Eligible {total_candidates} {unit}{suffix}"' in count_block
