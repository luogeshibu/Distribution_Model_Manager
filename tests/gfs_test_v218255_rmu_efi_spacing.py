from __future__ import annotations

import xml.etree.ElementTree as ET

from g_file_studio.engines.rmu_efi_engine import EARTH_DEVREF, NORMAL_DEVREF, add_rmu_efi_normal_icons
from g_file_studio.services.id_rule_service import IdRule


def _rule() -> IdRule:
    return IdRule("pwbh", "182", 9)


def _top_tree(*, earth_y: float = 2994.0) -> ET.ElementTree:
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Text", id="9000001", x="1760", y="2920", w="100", h="40", ts="30895")
    ET.SubElement(layer, "rect", id="2000001", x="1703", y="2973", w="224", h="219", ls="2")
    ET.SubElement(layer, "BusDis", id="38000001", x="1750", y="3070", w="160", h="6")
    ET.SubElement(layer, "CBreakerDis", id="117000001", x="1750", y="3020", w="28", h="30")
    ET.SubElement(layer, "CBreakerDis", id="117000002", x="1840", y="3020", w="28", h="30")
    ET.SubElement(layer, "pwbh", id="182000579", x="1800", y=str(earth_y), w="30", h="30", devref=EARTH_DEVREF)
    return ET.ElementTree(root)


def _left_tree() -> ET.ElementTree:
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "rect", id="2000001", x="3259", y="2791", w="220", h="220", ls="2")
    ET.SubElement(layer, "BusDis", id="38000001", x="3360", y="2820", w="6", h="160")
    ET.SubElement(layer, "CBreakerDis", id="117000001", x="3310", y="2840", w="28", h="30")
    ET.SubElement(layer, "CBreakerDis", id="117000002", x="3310", y="2930", w="28", h="30")
    ET.SubElement(layer, "pwbh", id="182000579", x="3310", y="2880", w="30", h="30", devref=EARTH_DEVREF)
    return ET.ElementTree(root)


def test_default_top_spacing_matches_30895_calibration():
    tree = _top_tree()
    result = add_rmu_efi_normal_icons(tree, file_name="30895.g", pwbh_id_rule=_rule())
    assert result.added == 1
    normal = next(e for e in tree.getroot().find("Layer") if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in tree.getroot().find("Layer") if e.get("devref") == EARTH_DEVREF)
    assert float(normal.get("x")) == 1805.0
    assert float(normal.get("y")) == 2983.0
    assert float(earth.get("y")) == 3010.0
    assert "Normal-Earth=5 G单位" in result.rows[-1]["detail"]
    assert "EFI-柜框=10 G单位" in result.rows[-1]["detail"]


def test_default_left_spacing_matches_existing_30827_reference():
    tree = _left_tree()
    result = add_rmu_efi_normal_icons(tree, file_name="30827.g", pwbh_id_rule=_rule())
    assert result.added == 1
    normal = next(e for e in tree.getroot().find("Layer") if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in tree.getroot().find("Layer") if e.get("devref") == EARTH_DEVREF)
    assert float(normal.get("x")) == 3269.0
    assert float(normal.get("y")) == 2887.0
    assert float(earth.get("x")) == 3296.0
    assert float(earth.get("y")) == 2880.0


def test_spacing_inputs_change_position():
    tree = _top_tree(earth_y=3005.0)
    add_rmu_efi_normal_icons(
        tree,
        file_name="custom.g",
        pwbh_id_rule=_rule(),
        normal_earth_gap_px=8,
        frame_margin_px=14,
    )
    normal = next(e for e in tree.getroot().find("Layer") if e.get("devref") == NORMAL_DEVREF)
    earth = next(e for e in tree.getroot().find("Layer") if e.get("devref") == EARTH_DEVREF)
    assert float(normal.get("y")) == 2987.0
    assert float(earth.get("y")) == 3017.0


def test_old_earth_position_never_overrides_frame_first_layout():
    tree = _top_tree(earth_y=2990.0)
    earth = next(e for e in tree.getroot().find("Layer") if e.get("devref") == EARTH_DEVREF)
    result = add_rmu_efi_normal_icons(
        tree,
        file_name="tight.g",
        pwbh_id_rule=_rule(),
        normal_earth_gap_px=8,
        frame_margin_px=14,
    )
    normal = next(e for e in tree.getroot().find("Layer") if e.get("devref") == NORMAL_DEVREF)
    # Frame is the first reference: Normal is always 14 G units from frame top.
    assert float(normal.get("y")) == 2987.0
    # Earth is then repositioned from Normal: 22 G visible span + 8 G gap.
    assert float(earth.get("y")) == 3017.0
    assert "先以柜框定位 Normal，再由 Normal 定位 Earth" in result.rows[-1]["detail"]
