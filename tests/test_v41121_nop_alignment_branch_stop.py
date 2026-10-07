from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser
from dmm.domain.graphics_cleanup.rmu_feeder_topology import (
    _components,
    _exact_nop_boundaries,
    _labels_by_component,
    _rmu_name_map,
)


def _write_q1_alignment_fixture(path: Path):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="220", h="220")
    ET.SubElement(layer, "CBreakerDis", id="3101", x="135", y="135", w="40", h="40", p_NameString="Y1")
    ET.SubElement(layer, "CBreakerDis", id="3102", x="235", y="135", w="40", h="40", p_NameString="Y2")
    ET.SubElement(layer, "CBreakerDis", id="3103", x="185", y="235", w="34", h="38", p_NameString="Q1")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3201", x="190", y="180", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3301", x="150", y="200", w="120", h="8")
    ET.SubElement(layer, "Text", id="8001", x="335", y="230", w="80", h="40", ts="34391", lc="255,255,0")
    # Left-side red NOP. Q1 is horizontally aligned much better than Y1/Y2,
    # although raw edge distance to Y1 can be smaller.
    ET.SubElement(layer, "Text", id="8002", x="35", y="226", w="75", h="50", ts="N.O.P", lc="255,0,0", lcc="#ff0000")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _write_same_row_fixture(path: Path):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="220", h="220")
    ET.SubElement(layer, "CBreakerDis", id="3101", x="135", y="145", w="40", h="40", p_NameString="Y1")
    ET.SubElement(layer, "CBreakerDis", id="3102", x="235", y="145", w="40", h="40", p_NameString="Y2")
    ET.SubElement(layer, "CBreakerDis", id="3103", x="185", y="235", w="34", h="38", p_NameString="Q1")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3201", x="190", y="190", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3301", x="150", y="205", w="120", h="8")
    ET.SubElement(layer, "Text", id="8001", x="335", y="230", w="80", h="40", ts="42121", lc="255,255,0")
    # Right-side red NOP is on the same horizontal row as both Y1/Y2.
    # The nearer switch on that row (Y2) must win.
    ET.SubElement(layer, "Text", id="8002", x="335", y="140", w="75", h="50", ts="NOP", lc="255,0,0", lcc="#ff0000")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _resolve(path: Path):
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    frames = list(parser.find_rmu_frames(parsed))
    names = _rmu_name_map(parser, parsed, frames)
    return _exact_nop_boundaries(parser, parsed, frames, names)


def test_left_right_nop_prefers_horizontal_row_q1(tmp_path):
    source = tmp_path / "q1_alignment.g"
    _write_q1_alignment_fixture(source)
    boundary_nodes, rows = _resolve(source)
    assert boundary_nodes == {"3103"}
    assert len(rows) == 1
    assert rows[0]["switch_name"] == "Q1"
    assert rows[0]["nop_side"] == "LEFT"
    assert rows[0]["alignment_axis"] == "Y"


def test_same_horizontal_row_uses_nearest_switch_inside_same_rmu(tmp_path):
    source = tmp_path / "same_row.g"
    _write_same_row_fixture(source)
    boundary_nodes, rows = _resolve(source)
    assert boundary_nodes == {"3102"}
    assert rows[0]["switch_name"] == "Y2"
    assert rows[0]["nop_side"] == "RIGHT"
    assert rows[0]["alignment_delta"] == 0.0


def test_nop_stops_only_its_branch_other_rmu_paths_continue():
    # HHR source enters through Y1, can continue through Q1 to downstream.
    # Y2 is the NOP branch and blocks the other feeder only at Y2.
    adjacency = {
        "HHR": {"Y1"},
        "Y1": {"HHR", "BUS"},
        "BUS": {"Y1", "Q1", "Y2"},
        "Q1": {"BUS", "DOWNSTREAM"},
        "DOWNSTREAM": {"Q1"},
        "Y2": {"BUS", "OTHER_SIDE"},
        "OTHER_SIDE": {"Y2", "BHA"},
        "BHA": {"OTHER_SIDE"},
    }
    by_id = {node: object() for node in adjacency}
    component_by_id, _ = _components(by_id, adjacency, {"Y2"})
    labels = _labels_by_component(component_by_id, {"HHR": "HHR1-AH314", "BHA": "BHA2-AH349"})

    hhr_component = component_by_id["DOWNSTREAM"]
    bha_component = component_by_id["OTHER_SIDE"]
    assert labels[hhr_component] == {"HHR1-AH314"}
    assert labels[bha_component] == {"BHA2-AH349"}
    assert component_by_id["Y1"] == component_by_id["Q1"] == hhr_component
    assert "Y2" not in component_by_id


def test_rmu_ownership_does_not_use_feedline_bounding_box_center():
    source = Path("src/dmm/domain/graphics_cleanup/rmu_feeder_topology.py").read_text(encoding="utf-8")
    assert "center_contains(obj.box" not in source
    assert "RMU所属馈线仅根据其Y*/Q*端口" in source
