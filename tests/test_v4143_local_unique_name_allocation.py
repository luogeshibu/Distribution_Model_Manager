from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import Box, GObject, ParsedG


def _parsed(objects, **root_attrs):
    root = ET.Element("G", {key: str(value) for key, value in root_attrs.items()})
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def _device(index, x, *, tag="CBreakerDis", devref="#SEC_S.zwk.icn.g:SEC_S"):
    return GObject(
        tag,
        {"id": f"d{index}", "devref": devref},
        Box(x, 0, 10, 10),
        index,
    )


def _text(index, x, value, *, xml_id=None, color="255,255,255", background=None):
    attrs = {
        "id": xml_id or f"t{index}",
        "ts": value,
        "lc": color,
    }
    if background is not None:
        attrs["background"] = background
    return GObject("Text", attrs, Box(x, 0, 10, 10), index)


def _pole_catalog():
    return {
        "records": [
            {
                "file_name": "pole.g",
                "root_id": "ROOT",
                "classification": "LBS",
            }
        ]
    }


def _transformer_catalog():
    return {
        "records": [
            {
                "file_name": "transformer.g",
                "root_id": "ROOT",
                "classification": "TRANSFORMER_OH",
            }
        ]
    }


def test_pole_switch_same_visible_name_different_text_ids_can_both_allocate():
    d1 = _device(1, 0)
    d2 = _device(2, 40)
    # Same visible content, but two different Text ids.  Each physical label
    # is an independent allocation unit.
    t1 = _text(10, 20, "LBS101", xml_id="NAME_A", color="255,0,0")
    t2 = _text(11, 60, "LBS101", xml_id="NAME_B", color="200,0,0")
    rows = PoleSwitchParser().discover(
        _parsed([d1, d2, t1, t2]),
        _pole_catalog(),
        {
            "pole_switch_name_format": "ALPHANUMERIC_SPACE",
            "pole_switch_name_colors": ["WHITE"],
            "pole_switch_name_has_background": False,
        },
    )
    assert [row["graphical_name"] for row in rows] == ["LBS101", "LBS101"]
    assert [row["name_xml_id"] for row in rows] == ["NAME_A", "NAME_B"]


def test_pole_switch_assigned_text_id_is_not_reused():
    d1 = _device(1, 0)
    d2 = _device(2, 40)
    only_name = _text(10, 20, "LBS101", xml_id="ONE_NAME", color="255,0,0")
    rows = PoleSwitchParser().discover(
        _parsed([d1, d2, only_name]),
        _pole_catalog(),
        {
            "name_format": "ALPHANUMERIC_SPACE",
            "name_colors": ["WHITE"],
            "name_has_background": False,
        },
    )
    assert rows[0]["name_xml_id"] == "ONE_NAME"
    assert rows[1]["graphical_name"] == ""
    assert rows[1]["name_xml_id"] == ""


def test_pole_switch_makkah_color_is_unrestricted_and_200_limit_is_hard():
    device = _device(1, 0)
    white = _text(10, 15, "LBS-WHITE", xml_id="WHITE")
    red = _text(11, 50, "LBS-RED", xml_id="RED", color="255,0,0")
    far = _text(12, 250, "LBS-FAR", xml_id="FAR", color="255,0,0")
    rows = PoleSwitchParser().discover(_parsed([device, white, red, far]), _pole_catalog(), {})
    assert len(rows) == 1
    assert rows[0]["graphical_name"] == "LBS-WHITE"
    assert rows[0]["name_xml_id"] == "WHITE"
    assert float(rows[0]["name_distance"]) <= 200.0

def test_transformer_same_visible_name_different_ids_allocate_once_each():
    d1 = _device(1, 0, tag="TransformerDis", devref="#Transformer_OH.pb.icn.g:ROOT")
    d2 = _device(2, 40, tag="TransformerDis", devref="#Transformer_OH.pb.icn.g:ROOT")
    t1 = _text(10, 20, "97803", xml_id="TR_NAME_A")
    t2 = _text(11, 60, "97803", xml_id="TR_NAME_B")
    rows, _context = TransformerParser().discover_for_transformer_model(
        _parsed([d1, d2, t1, t2]),
        _transformer_catalog(),
        {
            "transformer_name_format": "NUMERIC",
            "transformer_name_colors": ["WHITE"],
            "transformer_name_has_background": False,
        },
    )
    assert [row["graphical_name"] for row in rows] == ["97803", "97803"]
    assert [row["name_xml_id"] for row in rows] == ["TR_NAME_A", "TR_NAME_B"]


def test_transformer_assigned_text_not_reused_and_over_200_is_rejected():
    d1 = _device(1, 0, tag="TransformerDis", devref="#Transformer_OH.pb.icn.g:ROOT")
    d2 = _device(2, 40, tag="TransformerDis", devref="#Transformer_OH.pb.icn.g:ROOT")
    shared = _text(10, 20, "97803", xml_id="ONLY_TR_NAME")
    far_for_second = _text(11, 251, "97804", xml_id="FAR_TR_NAME")
    rows, _context = TransformerParser().discover_for_transformer_model(
        _parsed([d1, d2, shared, far_for_second]),
        _transformer_catalog(),
        {
            "transformer_name_format": "NUMERIC",
            "transformer_name_colors": ["WHITE"],
            "transformer_name_has_background": False,
        },
    )
    assert rows[0]["name_xml_id"] == "ONLY_TR_NAME"
    # Makkah hard limit is 200, so the second transformer cannot use a 201+ candidate.
    assert rows[1]["graphical_name"] == ""
    assert rows[1]["name_xml_id"] == ""
