from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_workspace_reuses_standard_sidebar_palette():
    source = _source()
    assert 'QListWidget#navList::item:selected' in source
    assert 'background: #B58A36;' in source
    assert '("图形工作区", 3)' in source
    assert 'QPushButton#graphicsNavGroupButton' not in source


def test_poke_is_orchestrated_by_right_side_combo_not_sidebar_child():
    source = _source()
    assert 'self.graphics_operation_combo.addItem("Poke 跳转处理", "POKE")' in source
    assert 'self.graphics_poke_nav_item' not in source
