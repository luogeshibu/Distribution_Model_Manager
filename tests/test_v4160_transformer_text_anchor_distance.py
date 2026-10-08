from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {
                "file_name": "Transformer_OH.pb.icn.g",
                "root_id": "Transformer_OH",
                "classification": "Transformer_OH",
            }
        ]
    }


def test_standalone_transformer_model_uses_rectangle_min_edge_distance(tmp_path):
    g = tmp_path / "anchor.g"
    g.write_text(
        """<G><Layer>
        <TransformerDis id="tr1" x="2326" y="1041" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
        <TransformerDis id="tr2" x="2567" y="1041" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
        <Text id="name1" x="2399" y="1059" w="138" h="55" ts="991890" lc="255,255,255"/>
        <Text id="name2" x="2642" y="1061" w="115" h="55" ts="99969" lc="255,255,255"/>
        </Layer></G>""",
        encoding="utf-8",
    )

    parsed = GParser().parse(g)
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog())
    by_id = {row["xml_id"]: row for row in rows}

    assert by_id["tr1"]["graphical_name"] == "991890"
    assert by_id["tr1"]["name_xml_id"] == "name1"
    assert round(float(by_id["tr1"]["name_distance"]), 3) == 33.0

    assert by_id["tr2"]["graphical_name"] == "99969"
    assert by_id["tr2"]["name_xml_id"] == "name2"
    assert round(float(by_id["tr2"]["name_distance"]), 3) == 35.0


def test_standalone_transformer_model_keeps_white_any_direction_and_300_limit(tmp_path):
    g = tmp_path / "rules.g"
    g.write_text(
        """<G><Layer>
        <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
        <Text id="red-near" x="120" y="90" w="40" h="20" ts="11111" lc="255,0,0"/>
        <Text id="white-bottom" x="120" y="170" w="40" h="20" ts="99223" lc="255,255,255"/>
        <Text id="white-far" x="450" y="120" w="40" h="20" ts="99999" lc="255,255,255"/>
        </Layer></G>""",
        encoding="utf-8",
    )

    parsed = GParser().parse(g)
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog())
    assert len(rows) == 1
    row = rows[0]
    assert row["graphical_name"] == "99223"
    assert row["name_direction"] == "bottom"
    assert row["name_xml_id"] == "white-bottom"
    assert row["name_distance_basis"] == "RECTANGLE_MIN_EDGE_DISTANCE"
