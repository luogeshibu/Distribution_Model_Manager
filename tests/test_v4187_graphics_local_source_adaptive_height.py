from pathlib import Path


def test_graphics_source_stack_uses_current_page_size_hint():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")

    assert "class CurrentPageStackedWidget(QStackedWidget):" in source
    assert "return current.sizeHint()" in source
    assert "return current.minimumSizeHint()" in source
    assert "self.poke_input_source_stack = CurrentPageStackedWidget()" in source
    assert "QSizePolicy.Expanding, QSizePolicy.Maximum" in source


def test_graphics_source_switch_forces_geometry_refresh():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")

    local_switch = 'self.poke_input_source_stack.setCurrentIndex(1 if source == "SSH" else 0)'
    assert source.count(local_switch) >= 2
    assert source.count("self.poke_input_source_stack.updateGeometry()") >= 2


def test_release_version_is_4188():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.112"' in constants
    assert 'version = "4.1.112"' in pyproject
