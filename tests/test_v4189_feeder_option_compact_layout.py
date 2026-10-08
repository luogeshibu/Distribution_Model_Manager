from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "dmm" / "ui" / "widgets" / "feeder_settings.py"


def test_feeder_option_card_and_notice_do_not_expand_vertically():
    source = SRC.read_text(encoding="utf-8")
    assert 'options.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source
    assert 'db_notice.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source


def test_feeder_logic_labels_use_natural_height():
    source = SRC.read_text(encoding="utf-8")
    assert 'label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)' in source
