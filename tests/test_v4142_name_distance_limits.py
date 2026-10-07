from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import PoleSwitchParser, POLE_SWITCH_TEXT_MAX_DISTANCE
from dmm.application.modules.transformer import TransformerParser, TRANSFORMER_MODEL_TEXT_MAX_DISTANCE
from dmm.domain.gfile.parser import Box, GObject, GParser, ParsedG, RmuFrame


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def _text(index, x, y, value="NAME1"):
    return GObject(
        "Text",
        {"id": f"t{index}", "ts": value, "lc": "255,255,255"},
        Box(x, y, 10, 10),
        index,
    )


def test_rmu_name_over_200_is_not_a_candidate():
    frame_obj = GObject("rect", {"id": "r1"}, Box(0, 0, 100, 100), 1)
    frame = RmuFrame(frame_obj)
    near = _text(2, 250, 45, "RMU-NEAR")  # right-side edge gap = 150
    far = _text(3, 301, 45, "RMU-FAR")     # right-side edge gap = 201
    parser = GParser(
        label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
        max_distance=200.0,
        overlap_tolerance=20.0,
    )
    result = parser.assign_rmu_label_candidates_globally(
        _parsed([frame_obj, near, far]), [frame], ["right"]
    )[(1, "r1")]
    assert len(result) == 1
    assert result[0].text == "RMU-NEAR"
    assert result[0].gap == 150.0


def test_rmu_name_exactly_200_is_allowed():
    frame_obj = GObject("rect", {"id": "r1"}, Box(0, 0, 100, 100), 1)
    frame = RmuFrame(frame_obj)
    text = _text(2, 300, 45, "RMU-200")  # right-side edge gap = 200
    parser = GParser(
        label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
        max_distance=200.0,
        overlap_tolerance=20.0,
    )
    result = parser.assign_rmu_label_candidates_globally(
        _parsed([frame_obj, text]), [frame], ["right"]
    )[(1, "r1")]
    assert len(result) == 1
    assert result[0].gap == 200.0


def _owners(parser, distance):
    device = GObject("CBreakerDis", {"id": "d1"}, Box(0, 0, 10, 10), 1)
    # Device center is (5, 5).  With the text box beginning at x=5+distance,
    # point-to-box distance from the center is exactly `distance`.
    text = _text(2, 5 + distance, 0, "SW1")
    parsed = _parsed([device, text])
    return parser.build_global_name_owners(
        parsed,
        nearest_only=True,
        device_filter=lambda obj: obj.xml_index == 1,
    )


def test_pole_switch_jeddah_name_limit_200_is_hard():
    assert POLE_SWITCH_TEXT_MAX_DISTANCE == 200.0


def test_transformer_makkah_name_limit_200_is_hard():
    assert TRANSFORMER_MODEL_TEXT_MAX_DISTANCE == 200.0
