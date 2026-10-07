from pathlib import Path

from dmm.application.modules.fuse import (
    FuseParser,
    _normalized_fuse_element_files,
)
from dmm.domain.gfile.parser import Box, GObject

ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = (ROOT / "src/dmm/config/defaults.py").read_text(encoding="utf-8")
FUSE_UI = (ROOT / "src/dmm/ui/widgets/fuse_settings.py").read_text(encoding="utf-8")
FUSE_MODULE = (ROOT / "src/dmm/application/modules/fuse.py").read_text(encoding="utf-8")
MAIN_WINDOW = (ROOT / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _obj(devref):
    return GObject("CBreakerDis", {"id": "1", "devref": devref}, Box(0, 0, 10, 10), 1)


def test_fuse_identity_uses_exact_operator_file_list_only():
    settings = {"fuse_element_files": ["Fuse_arrow.zwk.icn.g"]}
    assert FuseParser._is_fuse_object(_obj("#Fuse_arrow.zwk.icn.g:Fuse_arrow"), {}, settings)
    assert FuseParser._is_fuse_object(_obj("#dir/FUSE_ARROW.ZWK.ICN.G:ROOT"), {}, settings)
    assert not FuseParser._is_fuse_object(_obj("#Fuse_arrow_extra.zwk.icn.g:ROOT"), {}, settings)
    # Element Management classification is not consulted anymore.
    catalog = {"records": [{"file_name": "other.g", "classification": "FUSE"}]}
    assert not FuseParser._is_fuse_object(_obj("#other.g:ROOT"), catalog, settings)


def test_explicit_empty_fuse_list_disables_fuse_discovery():
    assert _normalized_fuse_element_files({"fuse_element_files": []}) == []
    assert not FuseParser._is_fuse_object(_obj("#Fuse_arrow.zwk.icn.g:ROOT"), {}, {"fuse_element_files": []})


def test_makkah_default_fuse_files_are_declared():
    assert 'DEFAULT_FUSE_ELEMENT_FILES = [' in DEFAULTS
    assert '"Fuse_arrow.zwk.icn.g"' in DEFAULTS
    assert '"Fuse_NON_SMART.zwk.icn.g"' in DEFAULTS
    assert '"fuse_element_files": DEFAULT_FUSE_ELEMENT_FILES' in DEFAULTS


def test_fuse_ui_matches_switch_and_transformer_picker_workflow():
    assert 'super().__init__("熔断器模型配置")' in FUSE_UI
    assert 'QGroupBox("熔断器图元名单")' in FUSE_UI
    assert 'QPushButton("展开服务器搜索")' in FUSE_UI
    assert 'QPushButton("全选可添加")' in FUSE_UI
    assert 'QPushButton("全部取消")' in FUSE_UI
    assert 'QPushButton("添加勾选到熔断器名单")' in FUSE_UI
    assert 'QPushButton("保存到本地用户缓存")' in FUSE_UI
    assert 'self.config["fuse_element_files"] = files' in FUSE_UI
    assert 'save_settings(self.config)' in FUSE_UI
    assert '_MAX_FILE_LIST_ROWS = 12' in FUSE_UI
    assert 'self.server_search_panel.setVisible(False)' in FUSE_UI


def test_fuse_help_and_model_no_longer_use_element_management_classification():
    assert 'classification_is' not in FUSE_MODULE
    assert 'resolve_element_record' not in FUSE_MODULE
    assert '用户配置熔断器 devref 文件名单' in FUSE_MODULE
    assert '只要加入名单就直接认定为熔断器' in MAIN_WINDOW


def test_v41100_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'APP_BUILD_DATE = "2026-10-01"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
