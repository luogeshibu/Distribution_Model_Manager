from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import Box, GObject, GParser, ParsedG, RmuFrame


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def _pole_catalog():
    return {"records": [{"file_name": "pole.g", "root_id": "ROOT", "classification": "LBS"}]}


def _transformer_catalog():
    return {"records": [{"file_name": "tr.g", "root_id": "ROOT", "classification": "TRANSFORMER_OH"}]}


def test_pole_switch_global_nearest_beats_direction_and_decimal_is_excluded():
    dev = GObject("CBreakerDis", {"id": "d1", "devref": "#SEC_S.zwk.icn.g:SEC_S"}, Box(100, 100, 20, 20), 1)
    top = GObject("Text", {"id": "top", "ts": "TOPNAME"}, Box(100, 60, 20, 10), 2)   # gap 30
    right = GObject("Text", {"id": "right", "ts": "RIGHTNAME"}, Box(121, 105, 20, 10), 3) # gap 1
    decimal = GObject("Text", {"id": "decimal", "ts": "21.449047"}, Box(100, 80, 20, 10), 4)
    rows = PoleSwitchParser().discover(_parsed([dev, top, right, decimal]), _pole_catalog(), {})
    assert rows[0]["graphical_name"] == "RIGHTNAME"
    assert rows[0]["name_priority"] == "GLOBAL"


def test_transformer_global_nearest_and_200_limit():
    dev = GObject("CBreaker", {"id": "tr1", "devref": "#Transformer_OH.pb.icn.g:ROOT"}, Box(100, 100, 20, 20), 1)
    top = GObject("Text", {"id": "top", "ts": "TR TOP", "lc": "255,0,0", "background": "1"}, Box(100, 50, 20, 10), 2)
    right = GObject("Text", {"id": "right", "ts": "TR RIGHT"}, Box(121, 105, 30, 10), 3)
    far = GObject("Text", {"id": "far", "ts": "TR FAR"}, Box(321, 105, 20, 10), 4)
    decimal = GObject("Text", {"id": "decimal", "ts": "39.555820"}, Box(100, 70, 20, 10), 5)
    rows, _ = TransformerParser().discover_for_transformer_model(_parsed([dev, top, right, far, decimal]), _transformer_catalog(), {})
    assert rows[0]["graphical_name"] == "TR RIGHT"
    assert rows[0]["name_priority"] == "GLOBAL"
    assert all(c["text"] != "39.555820" for c in rows[0]["name_candidates"])
    assert all(c["text"] != "TR FAR" for c in rows[0]["name_candidates"])


def test_rmu_right_bottom_global_fallback_with_rmu_specific_exclusions():
    frame_obj = GObject("rect", {"id": "r1"}, Box(100, 100, 100, 100), 1)
    frame = RmuFrame(frame_obj)
    top = GObject("Text", {"id": "top", "ts": "902"}, Box(120, 70, 20, 10), 2)
    right = GObject("Text", {"id": "right", "ts": "RMU"}, Box(205, 120, 30, 10), 3)
    decimal = GObject("Text", {"id": "dec", "ts": "21.449047"}, Box(120, 85, 30, 10), 4)
    hyphen = GObject("Text", {"id": "hy", "ts": "V2-W-H-0008"}, Box(120, 60, 50, 10), 5)
    parser = GParser(
        label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.\-/ ]{0,127}$",
        max_distance=200.0,
        overlap_tolerance=20.0,
        exclude_numeric_decimal_rmu_names=True,
        exclude_phone_like_rmu_names=True,
        exclude_hyphenated_rmu_names=True,
        prefer_pure_numeric_rmu_names=True,
    )
    result = parser.assign_rmu_label_candidates_globally(_parsed([frame_obj, top, right, decimal, hyphen]), [frame], ["top", "right", "global"])[(1, "r1")]
    assert len(result) == 1
    assert result[0].text == "902"
    assert result[0].direction == "global"
