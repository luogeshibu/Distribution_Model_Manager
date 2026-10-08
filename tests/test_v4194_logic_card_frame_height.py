from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGETS = ROOT / "src" / "dmm" / "ui" / "widgets"


def _src(name):
    return (WIDGETS / name).read_text(encoding="utf-8")


def test_logic_cards_cap_outer_frame_height():
    for name in [
        "pole_switch_settings.py",
        "transformer_settings.py",
        "fuse_settings.py",
        "master_station_settings.py",
        "feeder_settings.py",
        "rmu_settings.py",
    ]:
        source = _src(name)
        assert "setMaximumHeight(64)" in source
        assert "setMinimumHeight(0)" in source


def test_pole_switch_text_and_business_markers_are_unchanged():
    source = _src("pole_switch_settings.py")
    for marker in [
        "LBS、SEC、AR",
        "最大距离 200",
        "上方 TOP → 右侧 RIGHT → 全局 GLOBAL",
        "LBS96527-21240",
        "13501 / dms_combined_device",
        "p_ReportType=1",
    ]:
        assert marker in source
