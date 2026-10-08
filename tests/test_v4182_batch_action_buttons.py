from pathlib import Path


MAIN_WINDOW = Path(__file__).resolve().parents[1] / "src" / "dmm" / "ui" / "main_window.py"


def _text():
    return MAIN_WINDOW.read_text(encoding="utf-8")


def test_batch_action_buttons_use_dedicated_visual_styles():
    text = _text()
    assert 'QFrame#batchActionPanel' in text
    assert 'QPushButton#batchValidateAction' in text
    assert 'QPushButton#batchApplyAction' in text
    assert 'self.batch_validate_btn.setObjectName("batchValidateAction")' in text
    assert 'self.batch_apply_btn.setObjectName("batchApplyAction")' in text


def test_batch_action_buttons_have_clear_interaction_states():
    text = _text()
    assert 'QPushButton#batchValidateAction:hover' in text
    assert 'QPushButton#batchValidateAction:pressed' in text
    assert 'QPushButton#batchApplyAction:hover' in text
    assert 'QPushButton#batchApplyAction:pressed' in text
    assert 'QPushButton#batchApplyAction:disabled' in text
    assert 'setCursor(Qt.PointingHandCursor)' in text


def test_batch_action_copy_emphasizes_validate_then_apply():
    text = _text()
    block = text[text.index('        batch_action_panel = QFrame()'):text.index('        batch_layout.addLayout(batch_actions)')]
    assert 'QPushButton("批量校验")' in block
    assert 'QPushButton("执行批量关联")' in block
    assert '先检查所选模块' in block
    assert '通过批量校验' in block
