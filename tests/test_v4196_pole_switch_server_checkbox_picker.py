from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_v4196_server_results_are_checkbox_driven():
    assert "Qt.ItemIsUserCheckable" in UI_SOURCE
    assert "item.setCheckState(Qt.Unchecked)" in UI_SOURCE
    assert "def _checked_server_items(self):" in UI_SOURCE
    assert "item.checkState() == Qt.Checked" in UI_SOURCE
    assert 'QPushButton("添加勾选到柱上开关名单")' in UI_SOURCE
    assert "请先勾选需要加入柱上开关名单的图元" in UI_SOURCE


def test_v4196_server_picker_has_select_all_and_clear_all():
    assert 'QPushButton("全选可添加")' in UI_SOURCE
    assert 'QPushButton("全部取消")' in UI_SOURCE
    assert "def _check_all_server_results(self):" in UI_SOURCE
    assert "def _uncheck_all_server_results(self):" in UI_SOURCE


def test_v4196_rmu_prefixed_results_are_addable_when_user_selects_them():
    assert "RMU_* 图元被安全规则禁止加入柱上开关名单" not in UI_SOURCE
    assert "item.setFlags(item.flags() | Qt.ItemIsUserCheckable)" in UI_SOURCE


def test_v4196_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
