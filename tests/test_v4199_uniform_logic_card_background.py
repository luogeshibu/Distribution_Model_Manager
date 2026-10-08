from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIDGETS = [
    "master_station_settings.py",
    "pole_switch_settings.py",
    "transformer_settings.py",
    "fuse_settings.py",
    "feeder_settings.py",
    "rmu_settings.py",
]


def test_all_logic_cards_use_one_uniform_background_style():
    for name in WIDGETS:
        source = (ROOT / "src" / "dmm" / "ui" / "widgets" / name).read_text(encoding="utf-8")
        assert "background:#F7FAF9;color:#355148;border:1px solid #D6E4DF;" in source, name
        assert "background:#EAF8F2;color:#17372E;border:1px solid #B9DACD;" not in source, name


def test_uniform_logic_card_release_not_older_than_v4199():
    source = (ROOT / "src" / "dmm" / "config" / "constants.py").read_text(encoding="utf-8")
    import re
    match = re.search(r'APP_VERSION = "(\d+)\.(\d+)\.(\d+)"', source)
    assert match
    assert tuple(map(int, match.groups())) >= (4, 1, 99)
