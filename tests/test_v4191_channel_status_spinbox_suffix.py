from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src" / "dmm" / "ui" / "main_window.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src" / "dmm" / "config" / "constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

def test_release_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT

def test_channel_status_spinboxes_keep_px_suffix_and_have_room():
    assert 'self.channel_status_margin_spin.setSuffix(" px")' in MAIN
    assert 'self.channel_status_margin_spin.setFixedWidth(140)' in MAIN
    assert 'self.pipeline_channel_margin_spin.setSuffix(" px")' in MAIN
    assert 'self.pipeline_channel_margin_spin.setFixedWidth(140)' in MAIN
