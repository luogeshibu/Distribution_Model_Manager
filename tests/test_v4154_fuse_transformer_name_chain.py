from pathlib import Path

from dmm.application.modules.fuse import FuseModelModule, FuseParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "Fuse_NON_SMART.zwdz.icn.g", "classification": "FUSE"},
            {"file_name": "Transformer_OH.pb.icn.g", "classification": "TRANSFORMER_OH"},
        ]
    }


def _write_g(path: Path):
    path.write_text(
        '''<?xml version="1.0" encoding="UTF-8"?>
<G><Layer>
  <TransformerDis id="115000129" x="1468" y="3100" w="80" h="80" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <Text id="8000295" x="1404" y="3049" w="182" h="50" ts="LBS1197" />
  <Text id="8000239" x="1567" y="3114" w="125" h="50" ts="96210" />
  <ZhaiWaiDaoZha id="117000458" x="1427" y="3124" w="24" h="16" devref="#Fuse_NON_SMART.zwdz.icn.g:Fuse_NON_SMART" keyid="" />
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
        if name == "96210":
            return [{
                "id": 9001,
                "name": "96210",
                "code": "",
                "feeder_id": 100,
                "bv_id": 88,
            }]
        return []

    def get_disconnector_devices_by_name(self, name, feeder_id=None, table_id=13513):
        self.fuse_lookup = (name, feeder_id, table_id)
        if name == "FUSE96210" and feeder_id == 100:
            return [{
                "id": 1234,
                "name": "FUSE96210",
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
        "feeder_anchor": "RMU:42297",
        "feeder": {"id": 100, "name": "AH306", "display_name": "ADEL AH306"},
    }


def test_fuse_first_binds_nearest_transformer_then_resolves_that_transformer_name(tmp_path):
    parsed = GParser().parse(_write_g(tmp_path / "case.g"))
    discovered, _ = FuseParser().discover(parsed, _catalog(), {})
    assert len(discovered) == 1
    row = discovered[0]

    # Step 1 is fixed: select the nearest Transformer_OH device from the FUSE.
    assert row["nearest_transformer_xml_id"] == "115000129"

    # Transformer-name distance now uses the minimum rectangle edge distance.
    # Only the pure-numeric white/no-background transformer-name candidates
    # participate, so the right-side 96210 Text is selected.
    db = _DB()
    resolved = FuseModelModule()._resolve_row(dict(row), db, _resolution())

    assert db.transformer_lookups[0][0] == "96210"
    assert any(name == "96210" for name, _feeder, _table in db.transformer_lookups)
    assert resolved["nearest_transformer_xml_id"] == "115000129"
    assert resolved["nearest_transformer_name"] == "96210"
    assert resolved["transformer_name_direction"] == "right"
    assert resolved["transformer_name_xml_id"] == "8000239"
    assert resolved["derived_fuse_name"] == "FUSE96210"
    assert db.fuse_lookup == ("FUSE96210", 100, 13513)
    assert resolved["association_ready"] == "YES"
