from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import PoleSwitchParser, _marked_pole_switch_family
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import Box, GObject, ParsedG


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def test_default_makkah_pole_switch_files_are_exact_and_classification_free():
    dev = GObject(
        "CBreakerDis",
        {"id": "sw1", "devref": "#path/SEC_S.zwk.icn.g:SEC_S"},
        Box(100, 100, 20, 20),
        1,
    )
    text = GObject("Text", {"id": "t1", "ts": "SEC100"}, Box(125, 105, 20, 10), 2)
    rows = PoleSwitchParser().discover(_parsed([dev, text]), {"records": []}, {})
    assert len(rows) == 1
    assert rows[0]["device_family"] == "SEC"
    assert rows[0]["graphical_name"] == "SEC100"


def test_custom_pole_switch_file_rule_replaces_element_classification():
    settings = {
        "pole_switch_element_rules": [
            {"file_name": "MySiteSwitch.icn.g", "family": "LBS"},
        ],
        "transformer_element_files": ["MySiteTransformer.icn.g"],
    }
    devref = "#folder/MySiteSwitch.icn.g:ROOT"
    assert _marked_pole_switch_family(devref, settings) == "LBS"

    dev = GObject("AnythingDevice", {"id": "sw1", "devref": devref}, Box(0, 0, 10, 10), 1)
    text = GObject("Text", {"id": "t1", "ts": "LBS100"}, Box(12, 0, 10, 10), 2)
    rows = PoleSwitchParser().discover(_parsed([dev, text]), {"records": []}, settings)
    assert len(rows) == 1
    assert rows[0]["device_family"] == "LBS"


def test_element_classification_alone_no_longer_identifies_pole_switch():
    catalog = {
        "records": [{"file_name": "LegacySwitch.icn.g", "classification": "SEC"}]
    }
    dev = GObject(
        "CBreakerDis",
        {"id": "sw1", "devref": "#LegacySwitch.icn.g:ROOT"},
        Box(0, 0, 10, 10),
        1,
    )
    text = GObject("Text", {"id": "t1", "ts": "SEC100"}, Box(12, 0, 10, 10), 2)
    rows = PoleSwitchParser().discover(
        _parsed([dev, text]),
        catalog,
        {"pole_switch_element_rules": []},
    )
    assert rows == []


def test_user_selected_rmu_prefixed_file_is_accepted_without_prefix_veto():
    settings = {
        "pole_switch_element_rules": [
            {"file_name": "RMU_LBS_S.zwk.icn.g", "family": "LBS"},
        ]
    }
    assert _marked_pole_switch_family("#RMU_LBS_S.zwk.icn.g:RMU_LBS_S", settings) == "LBS"


def test_transformer_is_driven_only_by_operator_file_list():
    settings = {"transformer_element_files": ["CustomTransformer.pb.icn.g"]}
    dev = GObject(
        "TransformerDis",
        {"id": "tr1", "devref": "#CustomTransformer.pb.icn.g:ROOT"},
        Box(100, 100, 20, 20),
        1,
    )
    text = GObject("Text", {"id": "t1", "ts": "97803"}, Box(125, 105, 20, 10), 2)
    rows, _ = TransformerParser().discover_for_transformer_model(
        _parsed([dev, text]),
        {"records": []},
        settings,
    )
    assert len(rows) == 1
    assert rows[0]["recognition_source"] == "CONFIGURED_ELEMENT_FILE"

    legacy = GObject(
        "TransformerDis",
        {"id": "tr2", "devref": "#LegacyTransformer.icn.g:ROOT"},
        Box(200, 100, 20, 20),
        3,
    )
    catalog = {
        "records": [{"file_name": "LegacyTransformer.icn.g", "classification": "TRANSFORMER_OH"}]
    }
    rows, _ = TransformerParser().discover_for_transformer_model(
        _parsed([legacy, text]),
        catalog,
        settings,
    )
    assert rows == []
