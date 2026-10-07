from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_workspace_is_same_level_as_model_workspace():
    source = _source()
    specs = source.index("nav_specs = (")
    model_pos = source.index('("模型工作区", 0)', specs)
    graphics_pos = source.index('("图形工作区", 3)', specs)
    database_pos = source.index('("数据库", 1)', specs)
    element_pos = source.index('("图元管理", 2)', specs)
    assert model_pos < graphics_pos < database_pos < element_pos
    assert '("图形处理", None, "group")' not in source
    assert '("Poke 跳转", 3, "child")' not in source


def test_graphics_workflows_do_not_call_removed_poke_source_summary():
    source = _source()
    assert "_refresh_poke_source_summary" not in source
    assert source.count("_sync_poke_source_from_workspace(rebuild_remote=False)") >= 3


def test_graphics_operation_selector_is_extensible_and_stacked():
    source = _source()
    assert 'job_box = QGroupBox("图形任务")' in source
    assert 'self.graphics_operation_combo = NoWheelComboBox()' in source
    assert 'self.graphics_operation_combo.addItem("Poke 跳转处理", "POKE")' in source
    assert 'self.graphics_operation_stack = QStackedWidget()' in source
    assert 'self.on_graphics_operation_changed' in source


def test_graphics_page_title_and_help_follow_workspace_pattern():
    source = _source()
    assert '"图形工作区",' in source
    assert 'self.graphics_operation_help_btn = QPushButton("当前图形帮助")' in source
