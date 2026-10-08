from pathlib import Path

from dmm.application.modules.fuse import FuseParser
from dmm.application.modules.transformer import (
    TRANSFORMER_MODEL_TEXT_MAX_DISTANCE,
    TransformerParser,
)
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "Transformer_OH.pb.icn.g", "root_id": "Transformer_OH", "classification": "Transformer_OH"},
            {"file_name": "Fuse_NON_SMART.zwk.icn.g", "classification": "FUSE"},
        ]
    }


def test_supplied_115001120_name_96757_is_right_by_rectangle_position(tmp_path):
    g = tmp_path / "adel19_case.g"
    g.write_text("""<G><Layer>
      <TransformerDis id="115001120" x="2562" y="4223" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="8000636" x="2636" y="4239" w="125" h="50" ts="96757" lc="255,255,255"/>
      <Text id="8000637" x="2705" y="4310" w="150" h="50" ts="971050" lc="255,255,255"/>
    </Layer></G>""", encoding="utf-8")
    rows, _ = TransformerParser().discover_for_transformer_model(GParser().parse(g), _catalog(), {})
    row = rows[0]
    assert row["graphical_name"] == "96757"
    assert row["name_direction"] == "right"
    assert row["name_priority"] == "RIGHT"
    assert row["name_distance"] == 34.0
    assert row["name_distance_basis"] == "RECTANGLE_MIN_EDGE_DISTANCE"


def test_transformer_anchor_distance_limit_is_300(tmp_path):
    assert TRANSFORMER_MODEL_TEXT_MAX_DISTANCE == 300.0
    g = tmp_path / "distance300.g"
    g.write_text("""<G><Layer>
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="within" x="440" y="120" w="50" h="20" ts="91001" lc="255,255,255"/>
      <Text id="outside" x="441" y="120" w="50" h="20" ts="91002" lc="255,255,255"/>
    </Layer></G>""", encoding="utf-8")
    rows, _ = TransformerParser().discover_for_transformer_model(GParser().parse(g), _catalog(), {})
    row = rows[0]
    assert row["graphical_name"] == "91001"
    assert row["name_distance"] == 300.0
    assert [item["text"] for item in row["name_candidates"]] == ["91001"]


def test_fuse_reuses_anchor_direction_and_300_distance_after_nearest_transformer(tmp_path):
    g = tmp_path / "fuse300.g"
    g.write_text("""<G><Layer>
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="name" x="440" y="120" w="50" h="20" ts="92001" lc="255,255,255"/>
      <CBreakerDis id="f1" x="120" y="145" w="20" h="20" devref="#Fuse_NON_SMART.zwk.icn.g:Fuse_NON_SMART"/>
    </Layer></G>""", encoding="utf-8")
    rows, _ = FuseParser().discover(GParser().parse(g), _catalog(), {})
    row = rows[0]
    assert row["nearest_transformer_xml_id"] == "tr1"
    assert row["nearest_transformer_name"] == "92001"
    assert row["transformer_name_direction"] == "right"
    assert row["transformer_name_priority"] == "RIGHT"
