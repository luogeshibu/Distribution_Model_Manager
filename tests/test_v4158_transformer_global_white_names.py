from pathlib import Path

from dmm.application.modules.transformer import TransformerParser, resolve_transformer_graphical_name
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "tr.g", "root_id": "TRROOT", "classification": "Transformer_OH"},
        ]
    }


def _write(path: Path, body: str):
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    return path


class _DB:
    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        if name in {"99223", "TR-WHITE"}:
            return [{"id": 1, "name": name, "feeder_id": 100, "bv_id": 1}]
        return []


def test_transformer_accepts_bottom_white_and_rejects_nearer_red(tmp_path):
    g = _write(tmp_path / "tr.g", '''
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#tr.g:TRROOT"/>
      <Text id="red-top" x="100" y="60" w="80" h="20" ts="LBS1162" lc="255,0,0"/>
      <Text id="white-bottom" x="100" y="150" w="80" h="20" ts="99223" lc="255,255,255"/>
    ''')
    rows, _ = TransformerParser().discover(GParser().parse(g), _catalog(), {})
    assert len(rows) == 1
    row = resolve_transformer_graphical_name(rows[0], _DB(), set())
    assert row["graphical_name"] == "99223"
    assert row["name_direction"] == "bottom"
    assert row["name_db_match_count"] == 1
    assert "LBS1162" not in row["name_resolution_trace"]


def test_transformer_accepts_default_white_text_from_left(tmp_path):
    g = _write(tmp_path / "tr.g", '''
      <TransformerDis id="tr1" x="100" y="100" w="40" h="40" devref="#tr.g:TRROOT"/>
      <Text id="left" x="20" y="105" w="50" h="20" ts="TR-WHITE"/>
    ''')
    rows, _ = TransformerParser().discover(GParser().parse(g), _catalog(), {})
    assert len(rows) == 1
    row = resolve_transformer_graphical_name(rows[0], _DB(), set())
    assert row["graphical_name"] == "TR-WHITE"
    assert row["name_direction"] == "left"
