from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dmm" / "ui" / "widgets" / "master_station_settings.py"


def test_master_station_description_and_logic_cards_do_not_expand_vertically():
    source = SRC.read_text(encoding="utf-8")
    assert 'info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source
    assert 'box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source
    assert 'label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source
