from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_workspace_is_first_level_and_operation_is_right_side_selector():
    source = _source()
    assert '("图形工作区", 3)' in source
    assert 'self.graphics_operation_combo = NoWheelComboBox()' in source
    assert 'self.graphics_operation_combo.addItem("Poke 跳转处理", "POKE")' in source
    assert 'self.graphics_operation_stack = QStackedWidget()' in source
    assert '("Poke 跳转", 3, "child")' not in source
