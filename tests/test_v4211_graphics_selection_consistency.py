from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_shared_graphics_selection_style_is_light_and_high_contrast():
    src = _read("src/g_file_studio/ui/table_layout.py")
    assert "GRAPHICS_TABLE_SELECTION_QSS" in src
    assert "#DDF4EB" in src
    assert "#123B32" in src
    assert "#79BBA5" in src
    assert "apply_graphics_table_selection_style(table)" in src


def test_candidate_import_and_all_responsive_graphics_tables_use_shared_selection_style():
    table_layout = _read("src/g_file_studio/ui/table_layout.py")
    file_order = _read("src/g_file_studio/ui/widgets/file_order_editor.py")
    icon_editor = _read("src/g_file_studio/ui/widgets/icon_upgrade_editor.py")
    id_page = _read("src/g_file_studio/ui/pages/id_page.py")
    assert "apply_graphics_table_selection_style(table)" in table_layout
    assert "configure_responsive_table(self.table)" in file_order
    assert "configure_responsive_table(self.table)" in icon_editor
    assert "configure_responsive_table(self.table)" in id_page


def test_nonresponsive_graphics_tables_also_use_shared_selection_style():
    remote = _read("src/g_file_studio/ui/widgets/remote_g_source.py")
    symbols = _read("src/g_file_studio/ui/pages/site_profile_page.py")
    assert "apply_graphics_table_selection_style(self.table)" in remote
    assert "apply_graphics_table_selection_style(self.standard_table)" in symbols


def test_feeder_merge_order_and_bus_group_match_shared_light_palette():
    src = _read("src/g_file_studio/ui/pages/merge_page.py")
    assert "#DDF4EB" in src
    assert "#123B32" in src
    assert "border-top:1px solid #79BBA5" in src
    assert "#0078D7" not in src
