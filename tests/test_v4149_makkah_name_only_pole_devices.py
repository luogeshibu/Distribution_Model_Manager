from pathlib import Path

from dmm.application.modules.transformer import TransformerModelModule


class TransformerNameOnlyDB:
    def __init__(self):
        self.queries = []

    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        self.queries.append((name, feeder_id, table_id))
        return [{"id": 77, "name": name, "code": "TR77", "feeder_id": 999}]

    def verify_keyid(self, keyid):
        return {"device_id": int(keyid) - (1 << 32), "tab_no": 13505, "col_no": 1}


def test_makkah_transformer_resolves_by_name_without_feeder_filter():
    db = TransformerNameOnlyDB()
    row = {
        "graphical_name": "97803",
        "current_keyid1": "",
        "current_keyid2": "",
        "object_type": "TransformerDis",
        "xml_id": "tr1",
    }
    resolved = TransformerModelModule()._resolve_row(row, db)

    assert db.queries == [("97803", None, 13505)]
    assert resolved["db_device_id"] == 77
    assert resolved["association_ready"] == "YES"
    assert "feeder_id" not in resolved
    assert "db_feeder_id" not in resolved


def test_makkah_transformer_business_path_has_no_feeder_resolution_or_membership_guard():
    source = Path("src/dmm/application/modules/transformer.py").read_text(encoding="utf-8")
    assert "def _resolve_feeder" not in source
    assert "TRANSFORMER_FEEDER_NOT_RESOLVED" not in source
    assert "get_feeder_info(" not in source
    assert "find_feeders_by_name_hint(" not in source
    assert "feeder_id=feeder_id" not in source
    assert "enforce_device_feeder_membership" not in source
    assert "feeder_id=None" in source


def test_makkah_pole_switch_business_path_is_already_name_only():
    source = Path("src/dmm/application/modules/pole_switch.py").read_text(encoding="utf-8")
    assert "resolve_drawing_feeder" not in source
    assert "enforce_device_feeder_membership" not in source
    assert "get_feeder_info(" not in source
    assert "find_feeders_by_name_hint(" not in source
