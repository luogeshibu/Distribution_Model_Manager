from pathlib import Path

from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {
                "file_name": "Transformer_OH.pb.icn.g",
                "classification": "TRANSFORMER_OH",
            }
        ]
    }


def _parse(tmp_path: Path, body: str):
    path = tmp_path / "transformer_global_matching.g"
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    return GParser(required_rmu_tags=set()).parse(path)


def test_transformer_names_are_allocated_by_global_nearest_pairs_not_device_order(tmp_path):
    parsed = _parse(
        tmp_path,
        # tr1 is serialized first.  A sequential algorithm would let tr1 take
        # t1 (18 units away), forcing tr2 to take t2 (50 units away).  Global
        # matching must first give t1 to tr2 (2 units), then t2 to tr1 (20).
        '<CBreaker id="tr1" devref="#Transformer_OH.pb.icn.g:ROOT" '
        'x="100" y="100" w="20" h="20"/>'
        '<CBreaker id="tr2" devref="#Transformer_OH.pb.icn.g:ROOT" '
        'x="130" y="100" w="20" h="20"/>'
        '<Text id="t1" ts="11111" lc="255,255,255" x="128" y="105" w="10" h="10"/>'
        '<Text id="t2" ts="22222" lc="255,255,255" x="80" y="105" w="10" h="10"/>',
    )
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog(), {})
    by_id = {row["xml_id"]: row for row in rows}
    assert by_id["tr2"]["name_xml_id"] == "t1"
    assert by_id["tr2"]["graphical_name"] == "11111"
    assert by_id["tr1"]["name_xml_id"] == "t2"
    assert by_id["tr1"]["graphical_name"] == "22222"


def test_global_transformer_matching_keeps_same_text_value_when_ids_differ(tmp_path):
    parsed = _parse(
        tmp_path,
        '<CBreaker id="tr1" devref="#Transformer_OH.pb.icn.g:ROOT" '
        'x="100" y="100" w="20" h="20"/>'
        '<CBreaker id="tr2" devref="#Transformer_OH.pb.icn.g:ROOT" '
        'x="300" y="100" w="20" h="20"/>'
        '<Text id="t1" ts="97803" lc="255,255,255" x="125" y="105" w="20" h="10"/>'
        '<Text id="t2" ts="97803" lc="255,255,255" x="325" y="105" w="20" h="10"/>',
    )
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog(), {})
    assert {row["graphical_name"] for row in rows} == {"97803"}
    assert {row["name_xml_id"] for row in rows} == {"t1", "t2"}


def test_global_transformer_matching_has_no_color_or_background_limit_and_rejects_pure_decimal(tmp_path):
    parsed = _parse(
        tmp_path,
        '<CBreaker id="tr1" devref="#Transformer_OH.pb.icn.g:ROOT" '
        'x="100" y="100" w="20" h="20"/>'
        '<Text id="decimal" ts="39.555820" lc="255,255,255" x="121" y="105" w="20" h="10"/>'
        '<Text id="red" ts="TX-RED" lc="255,0,0" background="1" x="125" y="105" w="20" h="10"/>'
        '<Text id="far" ts="33333" lc="255,255,255" x="330" y="105" w="20" h="10"/>',
    )
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog(), {})
    assert rows[0]["graphical_name"] == "TX-RED"
    assert rows[0]["name_xml_id"] == "red"
