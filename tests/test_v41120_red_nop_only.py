from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser
from dmm.domain.graphics_cleanup.rmu_feeder_topology import (
    _exact_nop_boundaries,
    _is_red_nop_text,
    _rmu_name_map,
)
from dmm.domain.gfile.parser import Box, GObject


def _obj(lc: str = "", lcc: str = "") -> GObject:
    return GObject("Text", {"id": "x", "ts": "N.O.P", "lc": lc, "lcc": lcc}, Box(0, 0, 10, 10), 0)


def test_red_nop_whitelist_accepts_red_only():
    assert _is_red_nop_text(_obj("255,0,0", "#ff0000"))
    assert _is_red_nop_text(_obj("", "#ffff0000"))
    assert not _is_red_nop_text(_obj("0,255,0", "#00ff00"))
    assert not _is_red_nop_text(_obj("85,255,0", "#55ff00"))
    assert not _is_red_nop_text(_obj("255,255,0", "#ffff00"))
    assert not _is_red_nop_text(_obj("255,255,255", "#ffffff"))


def _write_fixture(path: Path):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="300", h="260")
    ET.SubElement(layer, "CBreakerDis", id="3101", x="130", y="180", w="30", h="30", p_NameString="Y1")
    ET.SubElement(layer, "CBreakerDis", id="3102", x="330", y="180", w="30", h="30", p_NameString="Y2")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3201", x="200", y="220", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3301", x="160", y="280", w="160", h="10")
    ET.SubElement(layer, "Text", id="8001", x="430", y="240", w="100", h="50", ts="42605", lc="255,255,0")
    ET.SubElement(layer, "Text", id="8002", x="45", y="176", w="75", h="40", ts="NOP", lc="255,0,0", lcc="#ff0000")
    # Field green is not pure #00ff00. It must still be ignored because only red is allowed.
    ET.SubElement(layer, "Text", id="8003", x="370", y="176", w="75", h="40", ts="NOP", lc="85,255,0", lcc="#55ff00")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_non_red_nop_is_completely_ignored(tmp_path):
    source = tmp_path / "red_only_nop.g"
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


def test_v41120_ui_explains_red_nop_only():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "只处理红色 NOP" in source
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
