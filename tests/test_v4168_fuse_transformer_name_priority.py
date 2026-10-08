from pathlib import Path

from dmm.application.modules.fuse import FuseParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "Transformer_OH.pb.icn.g", "classification": "TRANSFORMER_OH"},
            {"file_name": "Fuse_NON_SMART.zwk.icn.g", "classification": "FUSE"},
        ]
    }


def _parse(tmp_path: Path, body: str):
    path = tmp_path / "case.g"
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    rows, _ = FuseParser().discover(GParser().parse(path), _catalog(), {})
    assert len(rows) == 1
    return rows[0]


def test_fuse_first_locks_nearest_transformer_then_prefers_top_name(tmp_path):
    row = _parse(tmp_path, """
      <TransformerDis id="tr-near" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <TransformerDis id="tr-far" x="600" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="top" x="120" y="20" w="50" h="20" ts="81001" lc="255,255,255"/>
      <Text id="right" x="150" y="120" w="50" h="20" ts="81002" lc="255,255,255"/>
      <CBreakerDis id="f1" x="110" y="145" w="20" h="20" devref="#Fuse_NON_SMART.zwk.icn.g:Fuse_NON_SMART"/>
    """)
    assert row["nearest_transformer_xml_id"] == "tr-near"
    assert row["nearest_transformer_name"] == "81001"
    assert row["transformer_name_priority"] == "TOP"
    assert row["transformer_name_direction"] == "top"


def test_fuse_uses_right_when_no_top_and_global_only_as_last_fallback(tmp_path):
    row = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="right" x="180" y="110" w="30" h="20" ts="82001" lc="255,255,255"/>
      <Text id="left" x="90" y="110" w="5" h="20" ts="82002" lc="255,255,255"/>
      <CBreakerDis id="f1" x="120" y="145" w="20" h="20" devref="#Fuse_NON_SMART.zwk.icn.g:Fuse_NON_SMART"/>
    """)
    assert row["nearest_transformer_name"] == "82001"
    assert row["transformer_name_priority"] == "RIGHT"


def test_fuse_name_candidates_are_numeric_white_no_background(tmp_path):
    row = _parse(tmp_path, """
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH"/>
      <Text id="bad-alpha" x="120" y="40" w="40" h="20" ts="TR900" lc="255,255,255"/>
      <Text id="bad-color" x="120" y="50" w="40" h="20" ts="83001" lc="255,0,0"/>
      <Text id="bad-bg" x="120" y="60" w="40" h="20" ts="83002" lc="255,255,255" background="1"/>
      <Text id="ok-global" x="120" y="170" w="40" h="20" ts="83003" lc="255,255,255"/>
      <CBreakerDis id="f1" x="120" y="145" w="20" h="20" devref="#Fuse_NON_SMART.zwk.icn.g:Fuse_NON_SMART"/>
    """)
    assert row["nearest_transformer_name"] == "83003"
    assert row["transformer_name_priority"] == "GLOBAL"
    assert [item["text"] for item in row["nearest_transformer_name_candidates"]] == ["83003"]
