from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_setup_ps1_exists_and_has_environment_bootstrap_contract():
    text = (ROOT / "setup.ps1").read_text(encoding="utf-8-sig")
    assert "Python 3.11 or newer" in text
    assert 'Join-Path $PSScriptRoot ".venv"' in text
    assert "-m venv" in text
    assert "requirements.txt" in text
    assert "pip install -r $Requirements" in text
    assert "[switch]$NoRun" in text
    assert 'Join-Path $PSScriptRoot "app.py"' in text


def test_setup_ps1_uses_python3_launcher_without_pin_to_311():
    text = (ROOT / "setup.ps1").read_text(encoding="utf-8-sig")
    assert 'PrefixArgs @("-3")' in text
    assert 'PrefixArgs @("-3.11")' not in text
