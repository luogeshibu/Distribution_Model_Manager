from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "src/dmm/ui/widgets/transformer_settings.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_transformer_matches_pole_switch_server_picker_layout():
    assert 'QGroupBox("柱上变压器图元名单")' in UI_SOURCE
    assert 'QLabel("从图元服务器搜索并添加")' in UI_SOURCE
    assert 'QPushButton("展开服务器搜索")' in UI_SOURCE
    assert 'self.server_search_panel.setVisible(False)' in UI_SOURCE
    assert 'QPushButton("全选可添加")' in UI_SOURCE
    assert 'QPushButton("全部取消")' in UI_SOURCE
    assert 'QPushButton("添加勾选到柱上变压器名单")' in UI_SOURCE
    assert 'QPushButton("收起搜索")' in UI_SOURCE
    assert 'ElementServerSearchWorker' in UI_SOURCE


def test_transformer_list_is_dynamic_and_manual_input_removed():
    assert '_MAX_FILE_LIST_ROWS = 12' in UI_SOURCE
    assert 'def _resize_file_list(self):' in UI_SOURCE
    assert 'self._resize_file_list()' in UI_SOURCE
    assert 'self.file_edit' not in UI_SOURCE
    assert 'QPushButton("添加")' not in UI_SOURCE


def test_v4198_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
