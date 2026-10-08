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
            ET.SubElement(layer, "pwbh", id="182000002", x="105", y="292", w="36", h="36", devref=NORMAL_DEVREF, tfr="rotate(0) scale(2,2)")
    else:
        ET.SubElement(layer, "BusDis", id="38000001", x="130", y="310", w="160", h="6")
        ET.SubElement(layer, "CBreakerDis", id="117000001", x="150", y="260", w="28", h="30")
        ET.SubElement(layer, "CBreakerDis", id="117000002", x="240", y="260", w="28", h="30")
        ET.SubElement(layer, "pwbh", id="182000001", x="195", y="226", w="30", h="30", devref=EARTH_DEVREF)
        if with_normal:
            ET.SubElement(layer, "pwbh", id="182000002", x="192", y="205", w="36", h="36", devref=NORMAL_DEVREF, tfr="rotate(0) scale(2,2)")
    return ET.ElementTree(root)


def _rule() -> IdRule:
    return IdRule("pwbh", "182", 9)


def test_left_layout_matches_confirmed_rendered_reference_offsets():
    tree = _tree(side="left")
    result = add_rmu_efi_normal_icons(tree, file_name="left.g", pwbh_id_rule=_rule())
    assert result.detected_rmus == 1
    assert result.added == 1
    layer = tree.getroot().find("Layer")
    frame = next(e for e in layer if e.tag == "rect")
    normal = next(e for e in layer if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in layer if e.get("devref") == EARTH_DEVREF)

    # Current default parameters are Normal-Earth=5 px and frame=10 px.
    # The left-side synthetic fixture has enough room, so the frame target wins.
    assert float(normal.get("x")) == 110.0
    assert float(normal.get("y")) - float(earth.get("y")) == 7.0


def test_top_layout_matches_confirmed_43223_rendered_reference_offsets():
    tree = _tree(side="top")
    result = add_rmu_efi_normal_icons(tree, file_name="top.g", pwbh_id_rule=_rule())
    assert result.added == 1
    layer = tree.getroot().find("Layer")
    frame = next(e for e in layer if e.tag == "rect")
    normal = next(e for e in layer if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in layer if e.get("devref") == EARTH_DEVREF)

    # Current default parameters keep the confirmed horizontal visual-centering
    # correction and use the 10 px frame target when there is enough room.
    assert float(normal.get("x")) - float(earth.get("x")) == 5.0
    assert float(normal.get("y")) == 210.0


def test_existing_normal_is_not_duplicated():
    tree = _tree(side="left", with_normal=True)
    result = add_rmu_efi_normal_icons(tree, file_name="existing.g", pwbh_id_rule=_rule())
    assert result.added == 0
    assert result.already_present == 1
    layer = tree.getroot().find("Layer")
    assert sum(1 for e in layer if e.get("devref") == NORMAL_DEVREF) == 1
