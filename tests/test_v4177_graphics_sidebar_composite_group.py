from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_sidebar_uses_normal_primary_row_without_nested_group_widget():
    source = _source()
    assert '("图形工作区", 3)' in source
    assert 'graphicsNavGroupButton' not in source
    assert 'self.nav.setItemWidget(item, group_button)' not in source


def test_graphics_workspace_keeps_full_width_right_page():
    source = _source()
    assert 'self.pages.addWidget(self.graphics_processing_page)' in source
    assert 'outer.addWidget(self.graphics_operation_stack)' in source
