from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser
from dmm.domain.graphics_cleanup.rmu_feeder_topology import _exact_nop_boundaries, _rmu_name_map


def _write_fixture(path: Path):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="300", h="260")
    ET.SubElement(layer, "CBreakerDis", id="3101", x="130", y="180", w="30", h="30", p_NameString="Y1")
    ET.SubElement(layer, "CBreakerDis", id="3102", x="330", y="180", w="30", h="30", p_NameString="Y2")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3201", x="200", y="220", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3301", x="160", y="280", w="160", h="10")
    ET.SubElement(layer, "Text", id="8001", x="430", y="240", w="100", h="50", ts="42605", lc="255,255,0", lcc="#ffff00")
    # Valid red NOP close to Y1.
    ET.SubElement(layer, "Text", id="8002", x="45", y="176", w="75", h="40", ts="NOP", lc="255,0,0", lcc="#ff0000")
    # Green NOP close to Y2 must be ignored completely.
    ET.SubElement(layer, "Text", id="8003", x="370", y="176", w="75", h="40", ts="NOP", lc="0,255,0", lcc="#00ff00")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_green_nop_is_completely_ignored_in_rmu_feeder_topology(tmp_path):
    source = tmp_path / "green_nop.g"
    _write_fixture(source)
    parser = _new_makkah_parser()
    parsed = parser.parse(source)
    frames = list(parser.find_rmu_frames(parsed))
    names = _rmu_name_map(parser, parsed, frames)

    boundary_nodes, rows = _exact_nop_boundaries(parser, parsed, frames, names)

    assert boundary_nodes == {"3101"}
    assert len(rows) == 1
    assert rows[0]["nop_text_xml_id"] == "8002"
    assert rows[0]["switch_name"] == "Y1"
    assert all(row["nop_text_xml_id"] != "8003" for row in rows)


def test_v41119_ui_explains_green_nop_is_ignored():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "非红色 NOP 全部忽略" in source
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
