from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import PoleSwitchParser, _marked_pole_switch_family
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import Box, GObject, ParsedG


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def test_default_transformer_element_is_recognized_without_catalog_mark():
    dev = GObject(
        "PowerTransformer",
        {"id": "tr1", "devref": "#Transformer_OH.pb.icn.g:ROOT"},
        Box(100, 100, 20, 20),
        1,
    )
    text = GObject("Text", {"id": "t1", "ts": "97803"}, Box(125, 105, 20, 10), 2)
    rows, _ = TransformerParser().discover_for_transformer_model(_parsed([dev, text]), {"records": []}, {})
    assert len(rows) == 1
    assert rows[0]["recognition_source"] == "CONFIGURED_ELEMENT_FILE"
    assert rows[0]["graphical_name"] == "97803"


def test_transformer_config_wins_over_wrong_old_pole_switch_classification():
    catalog = {
        "records": [{
            "file_name": "Transformer_OH.pb.icn.g",
            "root_id": "ROOT",
            "classification": "LBS",
        }]
    }
    devref = "#some/path/Transformer_OH.pb.icn.g:ROOT"
    dev = GObject("CBreakerDis", {"id": "tr1", "devref": devref}, Box(100, 100, 20, 20), 1)
    text = GObject("Text", {"id": "t1", "ts": "97803"}, Box(125, 105, 20, 10), 2)

    transformer_rows, _ = TransformerParser().discover_for_transformer_model(_parsed([dev, text]), catalog, {})
    pole_rows = PoleSwitchParser().discover(_parsed([dev, text]), catalog, {})

    assert len(transformer_rows) == 1
    assert transformer_rows[0]["recognition_source"] == "CONFIGURED_ELEMENT_FILE"
    assert pole_rows == []
    assert _marked_pole_switch_family(devref, {}) == ""


def test_old_transformer_classification_is_not_a_fallback_anymore():
    catalog = {
        "records": [{
            "file_name": "LegacyPoleTransformer.icn.g",
            "root_id": "ROOT",
            "classification": "TRANSFORMER_OH",
        }]
    }
    dev = GObject(
        "TransformerDis",
        {"id": "tr1", "devref": "#LegacyPoleTransformer.icn.g:ROOT"},
        Box(100, 100, 20, 20),
        1,
    )
    text = GObject("Text", {"id": "t1", "ts": "97803"}, Box(125, 105, 20, 10), 2)
    rows, _ = TransformerParser().discover_for_transformer_model(
        _parsed([dev, text]),
        catalog,
        {"transformer_element_files": []},
    )
    assert rows == []


def test_configured_file_match_is_exact_not_substring():
    dev = GObject(
        "TransformerDis",
        {"id": "tr1", "devref": "#MyTransformer_OH.pb.icn.g:ROOT"},
        Box(100, 100, 20, 20),
        1,
    )
    assert not TransformerParser._is_transformer_object(dev, {"records": []}, {})
