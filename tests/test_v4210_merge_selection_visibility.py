from pathlib import Path


def _merge_source() -> str:
    return (Path(__file__).parents[1] / "src/g_file_studio/ui/pages/merge_page.py").read_text(encoding="utf-8")


def test_merge_order_and_group_dialog_use_light_high_contrast_selection():
    src = _merge_source()
    assert 'setObjectName("mergeFileOrderTable")' in src
    assert 'setObjectName("mainBusGroupTable")' in src
    assert '#DDF4EB' in src
    assert '#123B32' in src
    assert 'border-top:1px solid #79BBA5' in src


def test_main_bus_controls_have_persistent_selected_visual_states():
    src = _merge_source()
    assert 'setObjectName("mergeMainBusToggle")' in src
    assert 'QCheckBox#mergeMainBusToggle:checked' in src
    assert 'background:#DFF3EA' in src
    assert 'border:2px solid #0B7A5A' in src
    assert 'background:#E8F2FF' in src
    assert '_refresh_main_bus_visual_state()' in src


def test_existing_group_membership_remains_visually_identifiable():
    src = _merge_source()
    assert 'row_background = QColor("#EDF8F4") if grouped else QColor("#FFFFFF")' in src
    assert 'group_font.setBold(grouped)' in src
