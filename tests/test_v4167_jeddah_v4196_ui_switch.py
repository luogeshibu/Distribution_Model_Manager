from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "src" / "dmm" / "ui" / "widgets"


def test_logic_cards_match_jeddah_v4196_geometry():
    for name in [
        "pole_switch_settings.py",
        "transformer_settings.py",
        "fuse_settings.py",
    ]:
        text = (W / name).read_text(encoding="utf-8")
        assert "setMinimumHeight(0)" in text
        assert "setMaximumHeight(64)" in text
        assert "layout.setContentsMargins(7, 10, 7, 7)" in text
        assert "layout.setSpacing(3)" in text

    master = (W / "master_station_settings.py").read_text(encoding="utf-8")
    assert "setMaximumHeight(64)" in master
    assert "layout.setContentsMargins(7, 10, 7, 7)" in master
    assert "layout.setSpacing(3)" in master

    feeder = (W / "feeder_settings.py").read_text(encoding="utf-8")
    assert "setMaximumHeight(64)" in feeder
    assert "layout.setContentsMargins(7, 10, 7, 7)" in feeder
    assert "layout.setSpacing(3)" in feeder

    rmu = (W / "rmu_settings.py").read_text(encoding="utf-8")
    assert "setMaximumHeight(64)" in rmu
    assert "rules.setContentsMargins(7, 10, 7, 7)" in rmu
    assert "rules.setSpacing(3)" in rmu


def test_model_switch_matches_jeddah_v4196_without_repaint_freeze():
    text = (ROOT / "src" / "dmm" / "ui" / "main_window.py").read_text(encoding="utf-8")
    start = text.index("def on_module_changed")
    end = text.index("def refresh_operation_state", start)
    block = text[start:end]
    assert "self.module_stack.setUpdatesEnabled(False)" not in block
    assert "self.module_stack.setUpdatesEnabled(True)" not in block
    assert "self.module_stack.setMinimumHeight(0)" in block
    assert "self.module_stack.setMaximumHeight(16777215)" in block
    assert "self.module_stack.setCurrentIndex(index)" in block
    assert "widget.layout().invalidate()" in block
    assert "widget.layout().activate()" in block
    assert "QTimer.singleShot(0, self._update_module_stack_height)" in block
    assert block.index("setMinimumHeight(0)") < block.index("setCurrentIndex(index)")
