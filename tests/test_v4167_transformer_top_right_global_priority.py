from pathlib import Path

from dmm.application.modules.fuse import FuseParser
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {
                "file_name": "Transformer_OH.pb.icn.g",
                "root_id": "Transformer_OH",
                "classification": "Transformer_OH",
            },
            {
                "file_name": "Fuse_NON_SMART.zwk.icn.g",
                "classification": "FUSE",
            },
        ]
    }


def _parse(tmp_path: Path, body: str):
    g = tmp_path / "case.g"
    g.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    return TransformerParser().discover_for_transformer_model(
        GParser().parse(g), _catalog(), {}
    )[0]


def test_top_priority_beats_closer_right_candidate(tmp_path):
    rows = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="top" x="120" y="40" w="50" h="20" ts="10001" lc="255,255,255"/>
      <Text id="right" x="150" y="120" w="50" h="20" ts="10002" lc="255,255,255"/>
    """)
    row = rows[0]
    assert row["graphical_name"] == "10001"
    assert row["name_direction"] == "top"
    assert row["name_priority"] == "TOP"
    assert row["name_candidates"][0]["text"] == "10001"
    assert row["name_candidates"][1]["text"] == "10002"


def test_right_priority_beats_closer_global_candidate_when_no_top(tmp_path):
    rows = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="right" x="180" y="110" w="30" h="20" ts="20001" lc="255,255,255"/>
      <Text id="left" x="90" y="110" w="5" h="20" ts="20002" lc="255,255,255"/>
    """)
    row = rows[0]
    assert row["graphical_name"] == "20001"
    assert row["name_direction"] == "right"
    assert row["name_priority"] == "RIGHT"


def test_global_fallback_is_used_only_after_top_and_right_are_absent(tmp_path):
    rows = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="bottom" x="120" y="175" w="30" h="20" ts="30001" lc="255,255,255"/>
    """)
    row = rows[0]
    assert row["graphical_name"] == "30001"
    assert row["name_direction"] == "bottom"
    assert row["name_priority"] == "GLOBAL"


def test_only_pure_numeric_white_no_background_text_is_eligible(tmp_path):
    rows = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="top-alpha" x="120" y="45" w="40" h="20" ts="TR100" lc="255,255,255"/>
      <Text id="top-red" x="120" y="55" w="40" h="20" ts="40001" lc="255,0,0"/>
      <Text id="top-bg" x="120" y="65" w="40" h="20" ts="40002" lc="255,255,255" background="1"/>
      <Text id="right-ok" x="160" y="110" w="40" h="20" ts="40003" lc="255,255,255"/>
    """)
    row = rows[0]
    assert row["graphical_name"] == "40003"
    assert row["name_priority"] == "RIGHT"
    assert [item["text"] for item in row["name_candidates"]] == ["40003"]


def test_global_one_to_one_text_ownership_is_preserved(tmp_path):
    rows = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <TransformerDis id="tr2" x="250" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="name1" x="120" y="60" w="50" h="20" ts="50001" lc="255,255,255"/>
      <Text id="name2" x="270" y="60" w="50" h="20" ts="50002" lc="255,255,255"/>
    """)
    assert {row["graphical_name"] for row in rows} == {"50001", "50002"}
    assert len({row["name_xml_id"] for row in rows}) == 2


def test_fuse_reuses_standalone_transformer_priority_after_nearest_transformer_is_fixed(tmp_path):
    g = tmp_path / "fuse-priority.g"
    g.write_text("""<G><Layer>
      <TransformerDis id="tr1" x="1893" y="4273" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <TransformerDis id="tr2" x="2099" y="4344" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="top-name" x="2048" y="4287" w="150" h="50" ts="971488" lc="255,255,255"/>
      <Text id="bottom-name" x="2177" y="4361" w="150" h="50" ts="971765" lc="255,255,255"/>
      <CBreakerDis id="f1" x="2079" y="4369" w="24" h="16" devref="#Fuse_NON_SMART.zwk.icn.g:Fuse_NON_SMART" keyid=""/>
    </Layer></G>""", encoding="utf-8")
    parsed = GParser().parse(g)
    standalone, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog(), {})
    fuse_rows, _ = FuseParser().discover(parsed, _catalog(), {})
    standalone_by_id = {row["xml_id"]: row for row in standalone}
    fuse = fuse_rows[0]

    assert standalone_by_id["tr2"]["graphical_name"] == "971488"
    assert standalone_by_id["tr2"]["name_priority"] == "TOP"
    assert fuse["nearest_transformer_xml_id"] == "tr2"
    assert fuse["nearest_transformer_name"] == "971488"
    assert fuse["transformer_name_priority"] == "TOP"
