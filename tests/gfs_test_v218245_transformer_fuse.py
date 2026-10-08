from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from g_file_studio.engines.transformer_fuse_engine import (
    _parse_points,
    _parse_ref_groups,
    _template_variants,
    replace_transformer_oh_with_fuse_pairs,
)
from g_file_studio.services.id_rule_service import IdRule


MARKERS = (
    (
        "NariPd_Transformer_OH.pb.icn.g",
        "#NariPd_Transformer_OH.pb.icn.g:NariPd_Transformer_OH",
        "TRANSFORMER_OH",
        "NariPd_Transformer_OH",
    ),
)
RULES = {
    "Merge": IdRule("Merge", "20", 8, True, True),
    "rect": IdRule("rect", "2", 7, True, True),
    "ZhaiWaiDaoZha": IdRule("ZhaiWaiDaoZha", "117", 9, True, True),
    "ConnectLine": IdRule("ConnectLine", "34", 8, True, True),
}


def _tree(*children: ET.Element) -> ET.ElementTree:
    root = ET.Element("G", {"id": "root", "w": "1000", "h": "1000"})
    layer = ET.SubElement(root, "Layer", {"name": "0", "show": "1"})
    for child in children:
        layer.append(child)
    return ET.ElementTree(root)


def _transformer(node_area: str) -> ET.Element:
    return ET.Element(
        "TransformerDis",
        {
            "id": "115000001",
            "devref": "#NariPd_Transformer_OH.pb.icn.g:NariPd_Transformer_OH",
            "x": "300",
            "y": "100",
            "w": "150",
            "h": "150",
            "rotate": "90",
            "tfr": "rotate(90) scale(1,1)",
            "node_area": node_area,
            "keyid1": "BUSINESS-KEEP",
        },
    )


def _line(line_id: str, d: str, link: str) -> ET.Element:
    return ET.Element(
        "ConnectLine",
        {
            "id": line_id,
            "d": d,
            "x": "0",
            "y": "0",
            "w": "100",
            "h": "6",
            "link": link,
            "node_area": link,
        },
    )


def _groups(value: str) -> list[tuple[str, str, str]]:
    rows = []
    for group in value.split(";"):
        parts = group.split(",")
        if len(parts) >= 3:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def test_single_connected_transformer_is_replaced_and_external_line_geometry_is_unchanged(tmp_path: Path) -> None:
    transformer = _transformer("1,0,34000001")
    external = _line("34000001", "300,175 100,175", "0,1,115000001;1,0,117000999")
    tree = _tree(transformer, external)

    result = replace_transformer_oh_with_fuse_pairs(
        tree,
        tmp_path / "one.g",
        marker_entries=MARKERS,
        id_rules=RULES,
    )

    assert result.replaced == 1
    assert result.skipped_multi_connected == 0
    layer = next(child for child in list(tree.getroot()) if child.tag == "Layer")
    by_id = {item.get("id"): item for item in list(layer) if item.get("id")}

    # The replacement is the complete canonical Merge group, including the
    # user-provided dashed rectangular frame.
    merge = next(item for item in list(layer) if item.tag == "Merge")
    frame = next(item for item in list(layer) if item.tag == "rect")
    assert merge.get("mergesize") == "4"
    assert frame.get("ls") == "2"
    assert frame.get("lc") == "255,255,255"
    merge_index = list(layer).index(merge)
    assert [item.tag for item in list(layer)[merge_index:merge_index + 5]] in ([
        "Merge", "rect", "ZhaiWaiDaoZha", "TransformerDis", "ConnectLine"
    ], [
        "Merge", "rect", "TransformerDis", "ZhaiWaiDaoZha", "ConnectLine"
    ], [
        "Merge", "TransformerDis", "ZhaiWaiDaoZha", "ConnectLine", "rect"
    ])

    transformed = by_id["115000001"]
    assert transformed.get("devref") == "#Transformer_OH.pb.icn.g:Transformer_OH"
    assert transformed.get("keyid1") == "BUSINESS-KEEP"
    assert transformed.get("w") == "40"
    assert transformed.get("h") == "40"

    # The original conductor geometry is authoritative and must not move.
    assert by_id["34000001"].get("d") == "300,175 100,175"
    external_targets = _groups(by_id["34000001"].get("link") or "")
    assert all(target != "115000001" for _, _, target in external_targets)

    fuses = [item for item in list(layer) if item.tag == "ZhaiWaiDaoZha"]
    assert len(fuses) == 1
    fuse = fuses[0]
    assert fuse.get("id") == "117000001"
    assert any(target == "34000001" for _, _, target in _groups(fuse.get("node_area") or ""))

    # The original line endpoint must land exactly on the Fuse's *free* pin.
    # This guards against visually-near but topologically-offset placement.
    external_group = next(
        group for group in _parse_ref_groups(fuse.get("node_area"))
        if group[2] == "34000001"
    )
    free_pin, external_endpoint, _ = external_group
    external_points = _parse_points(by_id["34000001"].get("d"))
    external_anchor = external_points[0] if external_endpoint == 0 else external_points[-1]
    variants = _template_variants()
    pin_offsets = {}
    for variant in variants:
        rotation = int(round(float(variant.fuse.get("rotate") or 0))) % 360
        fx = float(variant.fuse.get("x") or 0)
        fy = float(variant.fuse.get("y") or 0)
        pin_offsets[(rotation, variant.fuse_free_pin)] = (
            variant.free_anchor[0] - fx,
            variant.free_anchor[1] - fy,
        )
    rotation = int(round(float(fuse.get("rotate") or 0))) % 360
    offset = pin_offsets[(rotation, free_pin)]
    free_anchor = (float(fuse.get("x") or 0) + offset[0], float(fuse.get("y") or 0) + offset[1])
    assert free_anchor == external_anchor

    internal_lines = [
        item for item in list(layer)
        if item.tag == "ConnectLine" and item.get("id") != "34000001"
    ]
    assert len(internal_lines) == 1
    internal = internal_lines[0]
    assert internal.get("id") == "34000002"
    assert any(target == internal.get("id") for _, _, target in _groups(transformed.get("node_area") or ""))
    internal_targets = {target for _, _, target in _groups(internal.get("link") or "")}
    assert internal_targets == {"115000001", "117000001"}


def test_two_connected_endpoints_are_skipped_without_any_mutation(tmp_path: Path) -> None:
    transformer = _transformer("0,1,34000001;1,0,34000002")
    line_a = _line("34000001", "100,100 300,100", "1,0,115000001")
    line_b = _line("34000002", "300,250 500,250", "0,1,115000001")
    original_attrs = dict(transformer.attrib)
    original_a = dict(line_a.attrib)
    original_b = dict(line_b.attrib)
    tree = _tree(transformer, line_a, line_b)

    result = replace_transformer_oh_with_fuse_pairs(
        tree,
        tmp_path / "two.g",
        marker_entries=MARKERS,
        id_rules=RULES,
    )

    assert result.replaced == 0
    assert result.skipped_multi_connected == 1
    assert transformer.attrib == original_attrs
    assert line_a.attrib == original_a
    assert line_b.attrib == original_b
    layer = next(child for child in list(tree.getroot()) if child.tag == "Layer")
    assert not any(item.tag == "ZhaiWaiDaoZha" for item in list(layer))


def test_nonclassified_transformer_is_never_replaced(tmp_path: Path) -> None:
    transformer = _transformer("1,0,34000001")
    transformer.set("devref", "#Other.pb.icn.g:Other")
    external = _line("34000001", "300,175 100,175", "0,1,115000001")
    tree = _tree(transformer, external)

    result = replace_transformer_oh_with_fuse_pairs(
        tree,
        tmp_path / "other.g",
        marker_entries=MARKERS,
        id_rules=RULES,
    )
    assert result.matched_transformers == 0
    assert result.replaced == 0


def test_multiple_conductors_on_same_transformer_pin_are_replaced_together(tmp_path: Path) -> None:
    transformer = _transformer("1,0,34000001;1,0,34000002")
    line_a = _line("34000001", "300,175 100,175", "0,1,115000001;1,0,117000901")
    line_b = _line("34000002", "300,175 50,175", "0,1,115000001;1,0,117000902")
    tree = _tree(transformer, line_a, line_b)

    result = replace_transformer_oh_with_fuse_pairs(
        tree,
        tmp_path / "same-pin.g",
        marker_entries=MARKERS,
        id_rules=RULES,
    )

    assert result.replaced == 1
    assert result.skipped_multi_connected == 0
    layer = next(child for child in list(tree.getroot()) if child.tag == "Layer")
    by_id = {item.get("id"): item for item in list(layer) if item.get("id")}

    # Neither external conductor is moved.
    assert by_id["34000001"].get("d") == "300,175 100,175"
    assert by_id["34000002"].get("d") == "300,175 50,175"

    fuse = next(item for item in list(layer) if item.tag == "ZhaiWaiDaoZha")
    fuse_id = fuse.get("id")
    assert fuse_id
    fuse_targets = {target for _, _, target in _groups(fuse.get("node_area") or "")}
    assert {"34000001", "34000002"}.issubset(fuse_targets)

    for line_id in ("34000001", "34000002"):
        line_targets = _groups(by_id[line_id].get("link") or "")
        assert all(target != "115000001" for _, _, target in line_targets)
        assert any(target == fuse_id for _, _, target in line_targets)



def test_missing_reciprocal_link_is_recovered_from_exact_learned_pin_geometry(tmp_path: Path) -> None:
    # A correctly linked peer teaches the two pin offsets for this exact NariPd
    # symbol/size/rotation.  The target itself intentionally has no node_area/link.
    teacher = ET.Element(
        "TransformerDis",
        {
            "id": "115000010",
            "devref": "#NariPd_Transformer_OH.pb.icn.g:NariPd_Transformer_OH",
            "x": "100", "y": "100", "w": "150", "h": "150",
            "rotate": "90", "tfr": "rotate(90) scale(1,1)",
            "node_area": "0,1,34000010;1,0,34000011",
        },
    )
    # Learn pin 0 at (179,113) and pin 1 at (113,113).
    teacher_a = _line("34000010", "50,113 179,113", "1,0,115000010")
    teacher_b = _line("34000011", "113,113 20,113", "0,1,115000010")

    target = ET.Element(
        "TransformerDis",
        {
            "id": "115000020",
            "devref": "#NariPd_Transformer_OH.pb.icn.g:NariPd_Transformer_OH",
            "x": "300", "y": "100", "w": "150", "h": "150",
            "rotate": "90", "tfr": "rotate(90) scale(1,1)",
        },
    )
    # This endpoint lands exactly on target pin 1: (300+13, 100+13).
    external = _line("34000020", "313,113 250,113", "")
    tree = _tree(teacher, teacher_a, teacher_b, target, external)

    result = replace_transformer_oh_with_fuse_pairs(
        tree,
        tmp_path / "legacy-missing-link.g",
        marker_entries=MARKERS,
        id_rules=RULES,
    )

    assert result.matched_transformers == 2
    assert result.replaced == 1
    assert result.skipped_multi_connected == 1
    layer = next(child for child in list(tree.getroot()) if child.tag == "Layer")
    by_id = {item.get("id"): item for item in list(layer) if item.get("id")}
    # Geometry is untouched and the formerly unlinked endpoint now points to Fuse.
    assert by_id["34000020"].get("d") == "313,113 250,113"
    groups = _groups(by_id["34000020"].get("link") or "")
    assert any(target_id.startswith("117") for _, _, target_id in groups)
    replaced_row = next(row for row in result.rows if row["transformer_id"] == "115000020")
    assert "几何回退识别 1 条" in replaced_row["detail"]


def test_two_exact_geometric_pin_connections_are_skipped_even_when_metadata_is_missing(tmp_path: Path) -> None:
    teacher = ET.Element(
        "TransformerDis",
        {
            "id": "115000010",
            "devref": "#NariPd_Transformer_OH.pb.icn.g:NariPd_Transformer_OH",
            "x": "100", "y": "100", "w": "150", "h": "150",
            "rotate": "90", "tfr": "rotate(90) scale(1,1)",
            "node_area": "0,1,34000010;1,0,34000011",
        },
    )
    teacher_a = _line("34000010", "50,113 179,113", "1,0,115000010")
    teacher_b = _line("34000011", "113,113 20,113", "0,1,115000010")
    target = ET.Element(
        "TransformerDis",
        {
            "id": "115000020",
            "devref": "#NariPd_Transformer_OH.pb.icn.g:NariPd_Transformer_OH",
            "x": "300", "y": "100", "w": "150", "h": "150",
            "rotate": "90", "tfr": "rotate(90) scale(1,1)",
        },
    )
    pin0 = _line("34000020", "200,113 379,113", "")
    pin1 = _line("34000021", "313,113 250,113", "")
    tree = _tree(teacher, teacher_a, teacher_b, target, pin0, pin1)

    result = replace_transformer_oh_with_fuse_pairs(
        tree,
        tmp_path / "legacy-two-ends.g",
        marker_entries=MARKERS,
        id_rules=RULES,
    )

    assert result.replaced == 0
    assert result.skipped_multi_connected == 2
