from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.feeder_avoidance import (
    avoid_feedline_text_overlap,
    _parse_path_points,
)
from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser


def _add_rmu(layer: ET.Element, *, base: int, x: int, y: int, name: str, name_x: int) -> None:
    ET.SubElement(layer, "Rect", id=str(2000 + base), x=str(x), y=str(y), w="220", h="220")
    ET.SubElement(
        layer,
        "CBreakerDis",
        id=str(3000 + base),
        x=str(x + 50),
        y=str(y + 50),
        w="30",
        h="30",
        p_NameString="Y1",
    )
    ET.SubElement(
        layer,
        "ZhaiWaiJieDiDaoZha",
        id=str(4000 + base),
        x=str(x + 100),
        y=str(y + 60),
        w="20",
        h="20",
    )
    ET.SubElement(layer, "BusDis", id=str(5000 + base), x=str(x + 60), y=str(y + 130), w="100", h="10")
    ET.SubElement(
        layer,
        "Text",
        id=str(8000 + base),
        x=str(name_x),
        y=str(y + 80),
        w="125",
        h="50",
        ts=name,
        lc="255,255,255",
        lcc="#ffffff",
    )


def _vertical_x(root: ET.Element, xml_id: str) -> float:
    element = next(elem for elem in root.iter() if elem.get("id") == xml_id)
    points = _parse_path_points(element.get("d", ""))
    verticals = [
        (a[0] + b[0]) / 2.0
        for a, b in zip(points, points[1:])
        if abs(a[0] - b[0]) <= 3 and abs(a[1] - b[1]) > 3
    ]
    # The rerouted trunk is the vertical segment farthest from the original RMU column.
    assert verticals
    return max(verticals)


def test_right_side_adjacent_spans_align_and_long_span_moves_outward(tmp_path: Path):
    source = tmp_path / "right.g"
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    _add_rmu(layer, base=1, x=100, y=100, name="10001", name_x=350)
    _add_rmu(layer, base=2, x=100, y=500, name="10002", name_x=350)
    _add_rmu(layer, base=3, x=100, y=900, name="10003", name_x=350)

    # Three disjoint/adjacent spans: they should reuse the same inner track.
    ET.SubElement(layer, "FeedLine", id="3501", lw="3", d="360,140 360,340")
    ET.SubElement(layer, "FeedLine", id="3502", lw="3", d="360,540 360,740")
    ET.SubElement(layer, "FeedLine", id="3503", lw="3", d="360,940 360,1140")
    # One long feeder overlaps all three spans and therefore must use the next outer track.
    ET.SubElement(layer, "FeedLine", id="3510", lw="3", d="370,140 370,1140")
    ET.ElementTree(root).write(source, encoding="utf-8", xml_declaration=True)

    parsed = _new_makkah_parser().parse(source)
    counts = avoid_feedline_text_overlap(
        parsed,
        text_clearance=20,
        feeder_spacing=50,
        corridor_tolerance=220,
        max_right_shift=500,
        process_right=True,
        process_left=True,
    )

    inner = [_vertical_x(parsed.root, xml_id) for xml_id in ("3501", "3502", "3503")]
    outer = _vertical_x(parsed.root, "3510")
    assert inner == [495.0, 495.0, 495.0]
    assert outer == 545.0
    assert counts["moved_segment_count"] == 4
    assert counts["staggered_segment_count"] == 1


def test_left_side_mirrors_outward_and_can_be_disabled(tmp_path: Path):
    source = tmp_path / "left.g"
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    _add_rmu(layer, base=11, x=500, y=100, name="20001", name_x=345)
    _add_rmu(layer, base=12, x=500, y=500, name="20002", name_x=345)

    ET.SubElement(layer, "FeedLine", id="3601", lw="3", d="400,140 400,340")
    ET.SubElement(layer, "FeedLine", id="3602", lw="3", d="400,540 400,740")
    ET.SubElement(layer, "FeedLine", id="3610", lw="3", d="390,140 390,740")
    ET.ElementTree(root).write(source, encoding="utf-8", xml_declaration=True)

    parsed = _new_makkah_parser().parse(source)
    counts = avoid_feedline_text_overlap(
        parsed,
        text_clearance=20,
        feeder_spacing=50,
        corridor_tolerance=220,
        max_right_shift=500,
        process_right=True,
        process_left=True,
    )
    # Label box is 345..470, so the inner left lane is 325 and the long span is 275.
    for xml_id in ("3601", "3602"):
        element = next(elem for elem in parsed.root.iter() if elem.get("id") == xml_id)
        xs = [x for x, _y in _parse_path_points(element.get("d", ""))]
        assert min(xs) == 325.0
    long_element = next(elem for elem in parsed.root.iter() if elem.get("id") == "3610")
    assert min(x for x, _y in _parse_path_points(long_element.get("d", ""))) == 275.0
    assert counts["staggered_segment_count"] == 1

    parsed_disabled = _new_makkah_parser().parse(source)
    disabled = avoid_feedline_text_overlap(
        parsed_disabled,
        text_clearance=20,
        feeder_spacing=50,
        corridor_tolerance=220,
        max_right_shift=500,
        process_right=True,
        process_left=False,
    )
    assert disabled["moved_feedline_count"] == 0
    assert disabled["skipped_side_count"] == 3
