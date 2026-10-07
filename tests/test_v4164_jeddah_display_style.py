from pathlib import Path


def _read(name: str) -> str:
    return (Path("src/dmm/ui/widgets") / name).read_text(encoding="utf-8")


def test_simple_model_logic_panels_use_jeddah_groupbox_structure():
    for name, cls in [
        ("pole_switch_settings.py", "PoleSwitchSettingsWidget"),
        ("transformer_settings.py", "TransformerSettingsWidget"),
        ("fuse_settings.py", "FuseSettingsWidget"),
    ]:
        src = _read(name)
        assert f"class {cls}(QGroupBox):" in src
        assert "layout.setContentsMargins(7, 10, 7, 7)" in src
        assert "layout.setSpacing(3)" in src
        assert "padding:4px 7px" in src
        assert "setMaximumHeight(64)" in src
        assert "AlignHCenter" not in src
        assert "setMaximumWidth(1180)" not in src


def test_master_and_feeder_logic_panels_are_full_width_like_jeddah():
    for name in ["master_station_settings.py", "feeder_settings.py"]:
        src = _read(name)
        assert "root.addWidget(box)" in src
        assert "AlignHCenter" not in src
        assert "setMaximumWidth(1180)" not in src
        assert "padding:4px 7px" in src


def test_rmu_logic_panel_uses_jeddah_two_column_proportions():
    src = _read("rmu_settings.py")
    assert "rules_box.setMinimumWidth(590)" in src
    assert "rules_box.setMaximumWidth" not in src
    assert "rules_box.setMinimumHeight(355)" in src
    assert "rules.setContentsMargins(7, 10, 7, 7)" in src
    assert "rules.setSpacing(3)" in src
    assert "padding:4px 7px" in src
