from pathlib import Path


WIDGETS = [
    "pole_switch_settings.py",
    "transformer_settings.py",
    "fuse_settings.py",
    "master_station_settings.py",
    "feeder_settings.py",
    "rmu_settings.py",
]


def test_readonly_workflows_follow_jeddah_native_qlabel_layout():
    for name in WIDGETS:
        src = (Path("src/dmm/ui/widgets") / name).read_text(encoding="utf-8")
        assert "CompactLogicLabel" not in src
        assert "setWordWrap(True)" in src
        assert "QSizePolicy.Maximum" in src


def test_custom_compact_logic_label_is_not_used_by_workflow_panels():
    for name in WIDGETS:
        src = (Path("src/dmm/ui/widgets") / name).read_text(encoding="utf-8")
        assert "dmm.ui.widgets.logic_card" not in src
