from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGET_DIR = ROOT / "src" / "dmm" / "ui" / "widgets"
FILES = [
    "rmu_settings.py",
    "pole_switch_settings.py",
    "transformer_settings.py",
    "fuse_settings.py",
    "feeder_settings.py",
    "master_station_settings.py",
]

def test_makkah_workflow_cards_use_jeddah_qlabel_layout():
    for name in FILES:
        text = (WIDGET_DIR / name).read_text(encoding="utf-8")
        assert "CompactLogicLabel" not in text, name
        assert "QSizePolicy.Maximum" in text, name
        assert "setWordWrap(True)" in text, name

def test_compact_logic_label_is_not_imported_anywhere():
    for path in WIDGET_DIR.glob("*.py"):
        if path.name == "logic_card.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "from dmm.ui.widgets.logic_card import" not in text, path.name
