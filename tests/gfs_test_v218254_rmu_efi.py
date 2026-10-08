from __future__ import annotations

import xml.etree.ElementTree as ET

from g_file_studio.engines.rmu_efi_engine import (
    EARTH_DEVREF,
    NORMAL_DEVREF,
    add_rmu_efi_normal_icons,
)
from g_file_studio.services.id_rule_service import IdRule


def _tree(*, side: str, with_normal: bool = False) -> ET.ElementTree:
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "rect", id="2000001", x="100", y="200", w="220", h="220", ls="2")
    if side == "left":
        ET.SubElement(layer, "BusDis", id="38000001", x="210", y="230", w="6", h="160")
        ET.SubElement(layer, "CBreakerDis", id="117000001", x="150", y="250", w="28", h="30")
        ET.SubElement(layer, "CBreakerDis", id="117000002", x="150", y="330", w="28", h="30")
        ET.SubElement(layer, "pwbh", id="182000001", x="151", y="295", w="30", h="30", devref=EARTH_DEVREF)
        if with_normal:
            ET.SubElement(layer, "pwbh", id="182000002", x="135", y="302", w="36", h="36", devref=NORMAL_DEVREF, tfr="rotate(0) scale(2,2)")
    else:
        ET.SubElement(layer, "BusDis", id="38000001", x="130", y="310", w="160", h="6")
        ET.SubElement(layer, "CBreakerDis", id="117000001", x="150", y="260", w="28", h="30")
        ET.SubElement(layer, "CBreakerDis", id="117000002", x="240", y="260", w="28", h="30")
        ET.SubElement(layer, "pwbh", id="182000001", x="195", y="226", w="30", h="30", devref=EARTH_DEVREF)
        if with_normal:
            ET.SubElement(layer, "pwbh", id="182000002", x="200", y="210", w="36", h="36", devref=NORMAL_DEVREF, tfr="rotate(0) scale(2,2)")
    return ET.ElementTree(root)


def _rule() -> IdRule:
    return IdRule("pwbh", "182", 9)


def test_left_layout_is_frame_first_then_repositions_earth_with_requested_gap():
    tree = _tree(side="left")
    result = add_rmu_efi_normal_icons(tree, file_name="left.g", pwbh_id_rule=_rule())
    assert result.detected_rmus == 1
    assert result.added == 1
    layer = tree.getroot().find("Layer")
    normal = next(e for e in layer if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in layer if e.get("devref") == EARTH_DEVREF)

    # v2.18.256 defaults: frame -> Normal is 10 G units; rendered Normal
    # footprint is 22 G units; requested visible gap is 5 G units.
    assert float(normal.get("x")) == 110.0
    assert float(earth.get("x")) == 137.0
    assert float(earth.get("x")) - float(normal.get("x")) == 27.0
    assert float(normal.get("y")) - float(earth.get("y")) == 7.0


def test_top_layout_is_frame_first_then_repositions_earth_with_requested_gap():
    tree = _tree(side="top")
    result = add_rmu_efi_normal_icons(tree, file_name="top.g", pwbh_id_rule=_rule())
    assert result.added == 1
    layer = tree.getroot().find("Layer")
    normal = next(e for e in layer if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in layer if e.get("devref") == EARTH_DEVREF)

    assert float(normal.get("x")) - float(earth.get("x")) == 5.0
    assert float(normal.get("y")) == 210.0
    assert float(earth.get("y")) == 237.0
    assert float(earth.get("y")) - float(normal.get("y")) == 27.0


def test_existing_normal_is_not_moved_or_duplicated():
    tree = _tree(side="left", with_normal=True)
    before = next(e for e in tree.getroot().find("Layer") if e.get("devref") == NORMAL_DEVREF)
    before_xy = (before.get("x"), before.get("y"))
    result = add_rmu_efi_normal_icons(tree, file_name="existing.g", pwbh_id_rule=_rule())
    assert result.added == 0
    assert result.already_present == 1
    layer = tree.getroot().find("Layer")
    normals = [e for e in layer if e.get("devref") == NORMAL_DEVREF]
    assert len(normals) == 1
    assert (normals[0].get("x"), normals[0].get("y")) == before_xy


def test_custom_twenty_twenty_uses_frame_as_strict_primary_reference():
    tree = _tree(side="top")
    result = add_rmu_efi_normal_icons(
        tree,
        file_name="top-20-20.g",
        pwbh_id_rule=_rule(),
        normal_earth_gap_px=20,
        frame_margin_px=20,
    )
    assert result.added == 1
    layer = tree.getroot().find("Layer")
    normal = next(e for e in layer if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in layer if e.get("devref") == EARTH_DEVREF)

    # Frame top is y=200.  Normal must be y=220 regardless of the old Earth y.
    assert float(normal.get("y")) == 220.0
    # Earth is placed only after Normal: 22-unit visible Normal span + 20-unit gap.
    assert float(earth.get("y")) == 262.0
    assert float(normal.get("x")) - float(earth.get("x")) == 5.0


def test_impossible_spacing_is_reported_instead_of_shrunk():
    tree = _tree(side="top")
    result = add_rmu_efi_normal_icons(
        tree,
        file_name="too-large.g",
        pwbh_id_rule=_rule(),
        normal_earth_gap_px=100,
        frame_margin_px=100,
    )
    assert result.added == 0
    assert result.skipped_insufficient_space == 1
    layer = tree.getroot().find("Layer")
    assert not any(e.get("devref") == NORMAL_DEVREF for e in layer)
