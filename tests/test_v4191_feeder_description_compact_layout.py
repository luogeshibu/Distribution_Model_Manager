from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dmm" / "ui" / "widgets" / "feeder_settings.py"


def test_feeder_top_description_does_not_expand_vertically():
    source = SRC.read_text(encoding="utf-8")
    assert 'info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source
