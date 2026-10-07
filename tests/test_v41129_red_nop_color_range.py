from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.gfile.parser import Box, GObject
from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser
from dmm.domain.graphics_cleanup.rmu_feeder_topology import (
    _exact_nop_boundaries,
    _is_red_nop_text,
    _rmu_name_map,
)


def _obj(*, lc: str = "", lcc: str = "") -> GObject:
    return GObject("Text", {"id": "x", "ts": "N.O.P", "lc": lc, "lcc": lcc}, Box(0, 0, 10, 10), 0)


def test_red_range_accepts_field_orange_red_but_rejects_green_family():
    assert _is_red_nop_text(_obj(lc="255,43,5", lcc="#ff2b05"))
    assert _is_red_nop_text(_obj(lcc="#e60000"))
    assert _is_red_nop_text(_obj(lcc="#cc1010"))
    assert _is_red_nop_text(_obj(lcc="#ff3333"))
    assert _is_red_nop_text(_obj(lcc="#b00000"))

    assert not _is_red_nop_text(_obj(lcc="#00ff00"))
    assert not _is_red_nop_text(_obj(lcc="#55ff00"))
    assert not _is_red_nop_text(_obj(lcc="#ffff00"))
    assert not _is_red_nop_text(_obj(lcc="#00ffff"))
    assert not _is_red_nop_text(_obj(lcc="#0000ff"))
    assert not _is_red_nop_text(_obj(lcc="#ffffff"))


def test_red_range_preserves_legacy_8_digit_color_encodings():
    assert _is_red_nop_text(_obj(lcc="#ffff0000"))  # AARRGGBB
    assert _is_red_nop_text(_obj(lcc="#ff0000ff"))  # RRGGBBAA
    assert _is_red_nop_text(_obj(lc="255,0,0,255"))


def test_field_orange_red_nop_participates_in_boundary_matching(tmp_path: Path):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Rect", id="2000202", x="400", y="2600", w="300", h="260")
    ET.SubElement(layer, "CBreakerDis", id="117000200", x="405", y="2655", w="30", h="30", p_NameString="Y1")
    ET.SubElement(layer, "CBreakerDis", id="117000201", x="650", y="2655", w="30", h="30", p_NameString="Y2")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="118000200", x="500", y="2700", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="119000200", x="450", y="2760", w="180", h="10")
    ET.SubElement(layer, "Text", id="8000598", x="306", y="2651", w="90", h="38", ts="N.O.P", lc="255,43,5", lcc="#ff2b05")
    ET.SubElement(layer, "Text", id="8000600", x="710", y="2680", w="80", h="30", ts="4113", lc="255,255,255", lcc="#ffffff")
    source = tmp_path / "field_red_nop.g"
    ET.ElementTree(root).write(source, encoding="utf-8", xml_declaration=True)

    parser = _new_makkah_parser()
    parsed = parser.parse(source)
    frames = list(parser.find_rmu_frames(parsed))
    names = _rmu_name_map(parser, parsed, frames)
    boundary_nodes, rows = _exact_nop_boundaries(parser, parsed, frames, names)

    assert boundary_nodes == {"117000200"}
    assert len(rows) == 1
    assert rows[0]["nop_text_xml_id"] == "8000598"
    assert rows[0]["switch_name"] == "Y1"


def test_v41129_version():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
