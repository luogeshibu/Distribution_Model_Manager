from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.feeder_avoidance import (
    DEFAULT_FEEDER_SPACING,
    avoid_feedline_text_overlap,
)
from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser


def _write_fixture(path: Path) -> None:
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")

    # Valid RMU frame + protected name/NOP text.
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="220", h="220")
    ET.SubElement(layer, "CBreakerDis", id="3001", x="150", y="150", w="30", h="30", p_NameString="Y1")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3002", x="200", y="160", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3003", x="160", y="230", w="100", h="10")
    ET.SubElement(layer, "Text", id="8001", x="350", y="170", w="125", h="50", ts="30038", lc="255,255,255", lcc="#ffffff")
    ET.SubElement(layer, "Text", id="8002", x="350", y="245", w="123", h="50", ts="N.O.P", lc="255,0,0", lcc="#ff0000")

    # Fixed non-colliding trunk at x=500. Two other feeders collide with the
    # same protected text and overlap its Y corridor.
    ET.SubElement(layer, "FeedLine", id="3502", lw="3", d="500,100 500,350", link="C;D")
    ET.SubElement(layer, "FeedLine", id="3501", lw="3", d="300,120 360,120 360,350 300,350", link="A;B", node_area="A;B", keyid="KEEP")
    ET.SubElement(layer, "FeedLine", id="3503", lw="3", d="310,130 362,130 362,340 310,340", link="E;F")

    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _element(root: ET.Element, xml_id: str) -> ET.Element:
    return next(elem for elem in root.iter() if elem.get("id") == xml_id)


def test_v41111_overlapping_feeders_use_separate_outward_lanes(tmp_path):
    source = tmp_path / "sample.g"
    _write_fixture(source)
    parsed = _new_makkah_parser().parse(source)

    before_fixed = _element(parsed.root, "3502").get("d")
    before_name = dict(_element(parsed.root, "8001").attrib)
    before_nop = dict(_element(parsed.root, "8002").attrib)

    counts = avoid_feedline_text_overlap(
        parsed,
        text_clearance=20,
        feeder_spacing=30,
        max_right_shift=500,
    )

    assert DEFAULT_FEEDER_SPACING == 50
    assert counts["colliding_feedline_count"] == 2
    assert counts["moved_feedline_count"] == 2
    assert counts["staggered_segment_count"] == 1
    assert counts["unresolved_collision_count"] == 0

    # x=500 is occupied; new trunks keep at least 30 G spacing and remain
    # individually identifiable instead of both landing at text.right+clearance.
    moved_paths = {
        _element(parsed.root, "3501").get("d"),
        _element(parsed.root, "3503").get("d"),
    }
    assert moved_paths == {
        "300,120 560,120 560,350 300,350",
        "310,130 530,130 530,340 310,340",
    }
    assert _element(parsed.root, "3502").get("d") == before_fixed
    assert dict(_element(parsed.root, "8001").attrib) == before_name
    assert dict(_element(parsed.root, "8002").attrib) == before_nop


def test_v41111_ui_exposes_configurable_lane_spacing_and_both_sides():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "DEFAULT_FEEDER_SPACING" in source
    assert "feeder_avoidance_spacing_spin" in source
    assert 'QLabel("错落轨道间距")' in source
    assert 'QLabel("同列判定范围")' in source
    assert 'QCheckBox("处理右侧馈线")' in source
    assert 'QCheckBox("处理左侧馈线")' in source
