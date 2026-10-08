from pathlib import Path

ROOT = Path(__file__).parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_selection_helper_sets_qss_and_active_inactive_palette():
    src = _read("src/g_file_studio/ui/table_layout.py")
    assert 'QPalette.ColorGroup.Active' in src
    assert 'QPalette.ColorGroup.Inactive' in src
    assert 'QPalette.ColorRole.Highlight' in src
    assert 'QColor("#DDF4EB")' in src
    assert 'QColor("#123B32")' in src
    assert 'QTableView::item:selected' in src


def test_graphics_workspace_reapplies_style_to_lazy_dialog_tables():
    src = _read("src/dmm/ui/graphics_workspace.py")
    assert 'app.installEventFilter(self)' in src
    assert 'QEvent.Type.Polish' in src
    assert 'QEvent.Type.Show' in src
    assert 'self._belongs_to_graphics_workspace(watched)' in src
    assert 'apply_graphics_table_selection_style(watched)' in src
    assert 'self._style_graphics_tables(page)' in src


def test_all_direct_graphics_qtablewidget_constructors_use_shared_style_path():
    # Direct constructors must either pass through configure_responsive_table or
    # explicitly apply the shared graphics selection style.  The workspace event
    # filter is a second line of defense, not an excuse for unstyled page tables.
    expected = {
        "src/g_file_studio/ui/pages/id_page.py": [
            "configure_responsive_table(self.table)",
        ],
        "src/g_file_studio/ui/pages/merge_page.py": [
            "configure_responsive_table(table)",
        ],
        "src/g_file_studio/ui/pages/site_profile_page.py": [
            "apply_graphics_table_selection_style(self.standard_table)",
        ],
        "src/g_file_studio/ui/widgets/file_order_editor.py": [
            "configure_responsive_table(self.table)",
        ],
        "src/g_file_studio/ui/widgets/icon_upgrade_editor.py": [
            "configure_responsive_table(self.table)",
        ],
        "src/g_file_studio/ui/widgets/remote_g_source.py": [
            "apply_graphics_table_selection_style(self.table)",
        ],
        "src/g_file_studio/ui/pages/small_element_page.py": [
            "configure_responsive_table(self.table)",
        ],
    }
    for rel, markers in expected.items():
        src = _read(rel)
        for marker in markers:
            assert marker in src, (rel, marker)
