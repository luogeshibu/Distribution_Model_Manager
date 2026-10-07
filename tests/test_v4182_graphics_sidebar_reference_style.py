from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_workspace_matches_model_workspace_task_pattern():
    source = _source()
    assert 'job_box = QGroupBox("图形任务")' in source
    assert 'grid.addWidget(QLabel("图形处理类型"), 0, 0)' in source
    assert 'self.graphics_operation_help_btn = QPushButton("当前图形帮助")' in source
    assert 'self.graphics_operation_stack = QStackedWidget()' in source


def test_graphics_workspace_uses_standard_sidebar_green_gold_styles():
    source = _source()
    assert 'QListWidget#navList::item:selected' in source
    assert 'background: #B58A36;' in source
    assert 'background: #004E3D;' in source
    assert 'graphicsNavGroupButton' not in source
