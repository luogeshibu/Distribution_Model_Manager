from pathlib import Path


def test_global_spinbox_buttons_are_high_contrast():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'background: #006B52;' in source
    assert 'QSpinBox::up-arrow' in source
    assert 'QSpinBox::down-arrow' in source
    assert 'spin_up.png' in source
    assert 'spin_down.png' in source
    assert 'padding-right: 34px;' in source


def test_release_version_is_4190():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.112"' in constants
    assert 'version = "4.1.112"' in pyproject
