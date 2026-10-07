from pathlib import Path


def _source():
    return (Path(__file__).parents[1] / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_graphics_workspace_aligns_with_other_primary_navigation_items():
    source = _source()
    specs = source.index('nav_specs = (')
    assert source.index('("模型工作区", 0)', specs) < source.index('("图形工作区", 3)', specs) < source.index('("数据库", 1)', specs)


def test_poke_is_not_a_sidebar_second_level_item_anymore():
    source = _source()
    assert '("Poke 跳转", 3, "child")' not in source
    assert 'QLabel("图形处理类型")' in source
