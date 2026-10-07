from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_v4195_pole_switch_picker_searches_readonly_element_server():
    assert "class ElementServerSearchWorker(QThread)" in UI_SOURCE
    assert "ReadOnlySshClient" in UI_SOURCE
    assert "client.list_element_files(self.remote_directory)" in UI_SOURCE
    assert 'QPushButton("搜索服务器")' in UI_SOURCE
    assert 'QPushButton("添加勾选到柱上开关名单")' in UI_SOURCE
    assert "使用【图元管理】中的 SSH 配置" in UI_SOURCE


def test_v4195_pole_switch_list_height_grows_with_item_count():
    assert "_MAX_FILE_LIST_ROWS = 12" in UI_SOURCE
    assert "def _resize_file_list(self):" in UI_SOURCE
    assert "self.file_list.count()" in UI_SOURCE
    assert "self._resize_file_list()" in UI_SOURCE
    assert "setFixedHeight(88)" not in UI_SOURCE


def test_v4195_server_result_adds_filename_only_without_prefix_block():
    assert "PurePosixPath" in UI_SOURCE
    assert 'file_name.casefold().startswith("rmu_")' not in UI_SOURCE
    assert "item.setData(Qt.UserRole, base_name)" in UI_SOURCE
    assert "self._append_file_name(file_name)" in UI_SOURCE


def test_v4195_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
