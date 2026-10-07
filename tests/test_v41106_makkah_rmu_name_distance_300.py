from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.config.constants import RMU_LABEL_SEARCH_MAX_DISTANCE
from dmm.domain.gfile.parser import Box, GObject, GParser, ParsedG, RmuFrame


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def _text(index, x, value):
    return GObject(
        "Text",
        {"id": f"t{index}", "ts": value, "lc": "255,255,255"},
        Box(x, 45, 10, 10),
        index,
    )


def _parser():
    return GParser(
        label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
        max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
        overlap_tolerance=20.0,
    )


def test_makkah_rmu_name_between_200_and_300_is_allowed():
    frame_obj = GObject("rect", {"id": "r1"}, Box(0, 0, 100, 100), 1)
    frame = RmuFrame(frame_obj)
    text = _text(2, 350, "RMU250")  # right edge gap = 250
    result = _parser().assign_rmu_label_candidates_globally(
        _parsed([frame_obj, text]), [frame], ["right", "bottom", "global"]
    )[(1, "r1")]
    assert len(result) == 1
    assert result[0].text == "RMU250"
    assert result[0].gap == 250.0


def test_makkah_rmu_name_over_300_is_rejected():
    frame_obj = GObject("rect", {"id": "r1"}, Box(0, 0, 100, 100), 1)
    frame = RmuFrame(frame_obj)
    text = _text(2, 401, "RMU301")  # right edge gap = 301
    result = _parser().assign_rmu_label_candidates_globally(
        _parsed([frame_obj, text]), [frame], ["right", "bottom", "global"]
    )[(1, "r1")]
    assert result == []
