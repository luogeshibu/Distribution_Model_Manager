from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.feeder_avoidance import (
    avoid_feedline_text_overlap,
    process_feeder_avoidance,
)
from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser


def _write_fixture(path: Path) -> None:
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")

    # One valid RMU frame with the three required tags.
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="220", h="220")
    ET.SubElement(layer, "CBreakerDis", id="3001", x="150", y="150", w="30", h="30", p_NameString="Y1")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3002", x="200", y="160", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3003", x="160", y="230", w="100", h="10")

    # RMU name on the right, and NOP below it. Both must remain fixed.
    ET.SubElement(layer, "Text", id="8001", x="350", y="170", w="125", h="50", ts="30038", lc="255,255,255", lcc="#ffffff")
    ET.SubElement(layer, "Text", id="8002", x="350", y="245", w="123", h="50", ts="N.O.P", lc="255,0,0", lcc="#ff0000")

    # Vertical trunk x=360 crosses both protected Text boxes. The endpoints
    # must remain unchanged while the trunk moves to the right.
    ET.SubElement(
        layer,
        "FeedLine",
        id="3501",
        x="297",
        y="117",
        w="66",
        h="236",
        lw="3",
        d="300,120 360,120 360,350 300,350",
        link="A;B",
        node_area="A;B",
        keyid="KEEP-ME",
    )
    # A line with no text collision must remain byte-for-byte geometry-equivalent.
    ET.SubElement(
        layer,
        "FeedLine",
        id="3502",
        x="497",
        y="97",
        w="6",
        h="256",
        lw="3",
        d="500,100 500,350",
        link="C;D",
    )

    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def _element(root: ET.Element, xml_id: str) -> ET.Element:
    return next(elem for elem in root.iter() if elem.get("id") == xml_id)


def test_feeder_avoidance_moves_only_feedline_right_and_preserves_text_and_topology(tmp_path):
    source = tmp_path / "sample.g"
    _write_fixture(source)
    parser = _new_makkah_parser()
    parsed = parser.parse(source)

    before_name = dict(_element(parsed.root, "8001").attrib)
    before_nop = dict(_element(parsed.root, "8002").attrib)
    before_line2 = _element(parsed.root, "3502").get("d")

    counts = avoid_feedline_text_overlap(
        parsed,
        text_clearance=20,
        feeder_spacing=0,
        max_right_shift=500,
    )

    line1 = _element(parsed.root, "3501")
    assert counts["colliding_feedline_count"] == 1
    assert counts["moved_feedline_count"] == 1
    assert counts["unresolved_collision_count"] == 0
    assert line1.get("d") == "300,120 495,120 495,350 300,350"
    assert line1.get("link") == "A;B"
    assert line1.get("node_area") == "A;B"
    assert line1.get("keyid") == "KEEP-ME"
    assert dict(_element(parsed.root, "8001").attrib) == before_name
    assert dict(_element(parsed.root, "8002").attrib) == before_nop
    assert _element(parsed.root, "3502").get("d") == before_line2


def test_process_feeder_avoidance_writes_safe_copy_and_reports(tmp_path):
    source = tmp_path / "source.g"
    _write_fixture(source)
    original = source.read_bytes()

    result = process_feeder_avoidance(
        [source],
        tmp_path / "out",
        tmp_path / "report",
        text_clearance=20,
        max_right_shift=500,
    )

    assert source.read_bytes() == original
    assert len(result.output_files) == 1
    assert result.output_files[0].exists()
    assert result.csv_path.exists()
    assert result.html_path.exists()
    assert result.moved_feedline_count == 1
    assert result.unresolved_collision_count == 0


def test_ui_registers_feeder_avoidance_module():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.graphics_operation_combo.addItem("馈线避让调整", "FEEDER_AVOIDANCE")' in source
    assert "def _build_feeder_avoidance_panel" in source
    assert "def start_feeder_avoidance" in source
    assert "环网柜名称和 NOP / N.O.P 原地不动" in source
