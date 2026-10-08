from pathlib import Path

from dmm.application.modules.fuse import FuseModelModule, FuseParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "Fuse_NON_SMART.zwk.icn.g", "classification": "FUSE"},
            {"file_name": "Transformer_OH.pb.icn.g", "classification": "TRANSFORMER_OH"},
        ]
    }


def _write_case(path: Path):
    # Geometry mirrors the field failure from JED-STH-ADEL-04.sln.pic.g:
    # tr2 is the FUSE's nearest transformer. Transformer naming now uses the
    # minimum edge-to-edge distance between the transformer rectangle and Text
    # rectangle, while TOP -> RIGHT -> GLOBAL priority is preserved.
    path.write_text(
        '''<?xml version="1.0" encoding="UTF-8"?>
<G><Layer>
  <TransformerDis id="115000013" x="1893" y="4273" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <TransformerDis id="115000015" x="2099" y="4344" w="40" h="40" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <Text id="8000322" x="2048" y="4287" w="150" h="50" ts="971488" lc="255,255,255" />
  <Text id="8000323" x="2177" y="4361" w="150" h="50" ts="971765" lc="255,255,255" />
  <CBreakerDis id="117000344" x="2079" y="4369" w="24" h="16" devref="#Fuse_NON_SMART.zwk.icn.g:Fuse_NON_SMART" keyid="" />
</Layer></G>''',
        encoding="utf-8",
    )
    return path


class _DB:
    def __init__(self):
        self.transformer_lookups = []
        self.fuse_lookup = None

    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        self.transformer_lookups.append((name, feeder_id, table_id))
        if name in {"971488", "971765"}:
            return [{
                "id": 2001 if name == "971765" else 2002,
                "name": name,
                "code": "",
                "feeder_id": 100,
                "bv_id": 88,
            }]
        return []

    def get_disconnector_devices_by_name(self, name, feeder_id=None, table_id=13513):
        self.fuse_lookup = (name, feeder_id, table_id)
        if name == "FUSE971488" and feeder_id == 100:
            return [{
                "id": 3001,
                "name": "FUSE971488",
                "code": "",
                "feeder_id": 100,
                "bv_id": 88,
            }]
        return []

    def verify_keyid(self, keyid):
        return {
            "device_id": int(keyid) - (40 << 32),
            "tab_no": 13513,
            "col_no": 40,
        }

    def get_device_by_id(self, table_id, device_id):
        return None


def _resolution():
    return {
        "ready": True,
        "feeder_id": 100,
        "feeder_source": "GRAPH_UNIQUE_RMU",
        "feeder_anchor": "RMU:test",
        "feeder": {"id": 100, "name": "AH304", "display_name": "ADEL / AH304"},
    }


def test_fuse_uses_nearest_transformer_then_jeddah_top_right_global_name_rule(tmp_path):
    parsed = GParser().parse(_write_case(tmp_path / "case.g"))
    rows, _ = FuseParser().discover(parsed, _catalog(), {})
    row = next(item for item in rows if str(item["xml_id"]) == "117000344")

    assert row["nearest_transformer_xml_id"] == "115000015"
    assert row["nearest_transformer_distance"] == 0.0
    # v4.1.68 keeps the nearest Transformer_OH fixed, then applies the same
    # name rule as the standalone transformer model.  The TOP candidate wins
    # before the closer bottom/global candidate.
    assert row["nearest_transformer_name"] == "971488"
    assert row["transformer_name_xml_id"] == "8000322"
    assert row["transformer_name_priority"] == "TOP"
    assert row["transformer_name_direction"] == "top"
    assert row["transformer_name_distance_basis"] == "RECTANGLE_MIN_EDGE_DISTANCE"
    assert round(float(row["transformer_name_distance"]), 3) == 7.0
    assert row["nearest_transformer_name_candidates"][0]["text"] == "971488"
    assert row["nearest_transformer_name_candidates"][0]["priority"] == "TOP"

    db = _DB()
    resolved = FuseModelModule()._resolve_row(dict(row), db, _resolution())

    assert db.transformer_lookups == [("971488", None, 13505)]
    assert resolved["nearest_transformer_name"] == "971488"
    assert resolved["derived_fuse_name"] == "FUSE971488"
    assert db.fuse_lookup == ("FUSE971488", 100, 13513)
    assert resolved["association_ready"] == "YES"
