from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGETS = ROOT / "src" / "dmm" / "ui" / "widgets"


def _src(name):
    return (WIDGETS / name).read_text(encoding="utf-8")


def test_logic_cards_are_compact_and_keep_natural_height():
    for name in [
        "pole_switch_settings.py",
        "transformer_settings.py",
        "fuse_settings.py",
        "master_station_settings.py",
        "feeder_settings.py",
    ]:
        source = _src(name)
        assert 'QLabel(f"<b>{title}：</b> {text}")' in source
        assert "padding:4px 7px" in source
        assert "line-height:1.22" in source
        assert "QSizePolicy.Expanding, QSizePolicy.Maximum" in source


def test_pole_switch_logic_text_is_not_removed_when_layout_is_compacted():
    source = _src("pole_switch_settings.py")
    for marker in [
        "识别哪些设备",
        "怎样找图上名称",
        "查询数据库前怎样处理名称",
        "数据库关联链路",
        "真正执行时回写哪些字段",
        "模块边界",
    ]:
        assert marker in source
