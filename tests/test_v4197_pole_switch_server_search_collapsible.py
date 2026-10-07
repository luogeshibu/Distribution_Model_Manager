from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_v4197_server_search_is_collapsed_by_default_and_toggleable():
    assert 'QPushButton("展开服务器搜索")' in UI_SOURCE
    assert 'self.server_search_panel.setVisible(False)' in UI_SOURCE
    assert 'def _toggle_server_search_panel(self):' in UI_SOURCE
    assert 'def _set_server_search_panel_visible(self, visible: bool):' in UI_SOURCE
    assert '"收起服务器搜索" if visible else "展开服务器搜索"' in UI_SOURCE


def test_v4197_expanded_picker_has_explicit_close_button():
    assert 'QPushButton("收起搜索")' in UI_SOURCE
    assert 'self._set_server_search_panel_visible(False)' in UI_SOURCE


def test_v4197_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
