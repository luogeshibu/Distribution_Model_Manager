from pathlib import Path

from dmm.application.registry import get_model_modules
from dmm.application.modules.pole_switch import (
    PoleSwitchModelModule,
    POLE_SWITCH_TEXT_MAX_DISTANCE,
    normalize_pole_switch_db_lookup_name,
)
from dmm.application.modules.transformer import (
    TransformerModelModule,
    TRANSFORMER_MODEL_TEXT_MAX_DISTANCE,
)
from dmm.application.modules.fuse import FuseModelModule


class KeyDB:
    def verify_keyid(self, keyid):
        value = int(keyid)
        # Tests below pass the expected table/domain through the encoded value
        if value >= (40 << 32):
            # fuse and pole-switch both use domain 40; table selected from fixture
            device_id = value - (40 << 32)
            return {"device_id": device_id, "tab_no": self.expected_table, "col_no": 40}
        device_id = value - (1 << 32)
        return {"device_id": device_id, "tab_no": 13505, "col_no": 1}

    def get_device_by_id(self, table_id, device_id):
        return None


class PoleDB(KeyDB):
    expected_table = 13502
    def __init__(self):
        self.queries = []
    def get_combined_device_records(self, name):
        self.queries.append(("parent", name))
        return [{"id": 101, "name": name, "code": "OTHER", "_matched_field": "NAME"}]
    def get_cb_devices_by_combined_device_id(self, combined_id):
        self.queries.append(("child", combined_id))
        return [{"id": 202, "name": "SEC", "code": "SEC", "combined_id": combined_id, "bv_id": 91}]


class TransformerDB(KeyDB):
    def __init__(self): self.calls = []
    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        self.calls.append((name, feeder_id, table_id))
        return [{"id": 303, "name": name, "code": "TR", "feeder_id": 999}]


class FuseDB(KeyDB):
    expected_table = 13513
    def __init__(self): self.calls = []
    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        self.calls.append(("tr", name, feeder_id, table_id))
        return [{"id": 303, "name": name, "feeder_id": 999}]
    def get_disconnector_devices_by_name(self, name, feeder_id=None, table_id=13513):
        self.calls.append(("fuse", name, feeder_id, table_id))
        return [{"id": 404, "name": name, "code": name, "feeder_id": 888, "bv_id": 91}]


def test_registry_contains_fuse():
    assert "FUSE" in get_model_modules()


def test_jeddah_distances_are_used_for_makkah_models():
    assert POLE_SWITCH_TEXT_MAX_DISTANCE == 200.0
    assert TRANSFORMER_MODEL_TEXT_MAX_DISTANCE == 200.0


def test_pole_switch_uses_name_only_and_no_feeder():
    db = PoleDB()
    row = {
        "graphical_name": "SEC-2385", "device_family": "SEC", "xml_id": "p1",
        "current_keyid": "", "object_type": "Whatever", "devref": "x",
    }
    out = PoleSwitchModelModule()._resolve_row(row, db)
    assert db.queries[0] == ("parent", normalize_pole_switch_db_lookup_name("SEC-2385", "SEC"))
    assert out["association_ready"] == "YES"
    assert "feeder" not in out["reason"].lower()


def test_transformer_unique_name_is_enough_without_feeder():
    db = TransformerDB()
    row = {
        "graphical_name": "97803", "xml_id": "t1", "object_type": "AnyTag",
        "current_keyid1": "", "current_keyid2": "", "devref": "x",
    }
    out = TransformerModelModule()._resolve_row(row, db)
    assert db.calls == [("97803", None, 13505)]
    assert out["association_ready"] == "YES"


def test_fuse_unique_names_are_enough_without_feeder():
    db = FuseDB()
    row = {
        "transformer_assignment_status": "MATCHED",
        "nearest_transformer_xml_id": "tr1", "nearest_transformer_name": "97803",
        "transformer_name_xml_id": "txt1", "current_keyid": "", "xml_id": "f1",
    }
    out = FuseModelModule()._resolve_row(row, db, set())
    assert ("tr", "97803", None, 13505) in db.calls
    assert ("fuse", "FUSE97803", None, 13513) in db.calls
    assert out["association_ready"] == "YES"


def test_source_contains_no_feeder_context_dependency_for_three_models():
    root = Path(__file__).resolve().parents[1]
    for rel in [
        "src/dmm/application/modules/pole_switch.py",
        "src/dmm/application/modules/transformer.py",
        "src/dmm/application/modules/fuse.py",
    ]:
        source = (root / rel).read_text(encoding="utf-8")
        assert "resolve_drawing_feeder(" not in source
        assert "enforce_device_feeder_membership(" not in source
