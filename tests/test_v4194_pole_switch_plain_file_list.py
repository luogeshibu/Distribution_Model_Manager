from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import (
    PoleSwitchModelModule,
    PoleSwitchParser,
    _is_configured_pole_switch_devref,
    _normalized_pole_switch_element_files,
)
from dmm.domain.gfile.parser import Box, GObject, ParsedG


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = (ROOT / "src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def test_v4194_plain_file_list_means_every_entry_is_a_pole_switch():
    settings = {
        "pole_switch_element_files": ["MySwitch.icn.g"],
        "transformer_element_files": ["Transformer_OH.pb.icn.g"],
    }
    assert _normalized_pole_switch_element_files(settings) == ["MySwitch.icn.g"]
    assert _is_configured_pole_switch_devref("#folder/MySwitch.icn.g:ROOT", settings)

    dev = GObject(
        "AnythingDevice",
        {"id": "sw1", "devref": "#folder/MySwitch.icn.g:ROOT"},
        Box(0, 0, 10, 10),
        1,
    )
    text = GObject("Text", {"id": "t1", "ts": "SW100"}, Box(12, 0, 10, 10), 2)
    rows = PoleSwitchParser().discover(_parsed([dev, text]), {"records": []}, settings)
    assert len(rows) == 1
    assert rows[0]["graphical_name"] == "SW100"
    assert rows[0]["device_family"] == ""


def test_v4194_user_selected_rmu_prefix_is_not_blocked():
    settings = {"pole_switch_element_files": ["RMU_LBS_S.zwk.icn.g"]}
    assert _normalized_pole_switch_element_files(settings) == ["RMU_LBS_S.zwk.icn.g"]
    assert _is_configured_pole_switch_devref(
        "#RMU_LBS_S.zwk.icn.g:RMU_LBS_S", settings
    )


def test_v4194_multiple_13502_children_block_without_family_disambiguation():
    class FakeDb:
        def get_combined_device_records(self, name):
            return [{"id": 501, "name": name, "code": "PARENT", "_matched_field": "NAME"}]

        def get_cb_devices_by_combined_device_id(self, combined_id):
            assert combined_id == 501
            return [
                {"id": 1001, "combined_id": 501, "name": "SEC", "code": "SEC", "bv_id": 1},
                {"id": 1002, "combined_id": 501, "name": "AR", "code": "AR", "bv_id": 1},
            ]

    row = {
        "graphical_name": "SEC100",
        "device_family": "SEC",  # legacy metadata must no longer disambiguate
        "current_keyid": "",
        "object_type": "CBreakerDis",
        "xml_id": "sw1",
    }
    resolved = PoleSwitchModelModule()._resolve_row(row, FakeDb())
    assert resolved["status"] == "FAIL"
    assert resolved["cb_parent_match_count"] == 2
    assert resolved["cb_db_match_count"] == 2
    assert "不再按 AR/LBS/SEC 分类消歧" in resolved["reason"]


def test_v4194_ui_has_no_family_selector_and_is_compact():
    assert "QComboBox" not in UI_SOURCE
    assert "family_combo" not in UI_SOURCE
    assert '_resize_file_list' in UI_SOURCE
    assert '搜索服务器' in UI_SOURCE
    assert '添加勾选到柱上开关名单' in UI_SOURCE
    assert "只要加入名单，就直接认定为柱上开关" in UI_SOURCE


def test_v4194_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
