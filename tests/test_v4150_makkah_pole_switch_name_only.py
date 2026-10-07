from pathlib import Path

from dmm.infrastructure.database.oracle import OracleClient


class RecordingOracle(OracleClient):
    def __init__(self):
        super().__init__({
            "user": "u", "password": "p", "host": "h", "port": 1521,
            "service_name": "s",
        })
        self._table_name_cache[13501] = "dms_combined_device"
        self.calls = []

    def _query(self, sql, binds=None):
        self.calls.append((" ".join(str(sql).split()).lower(), dict(binds or {})))
        return [{"id": 101, "name": binds["device_name"], "code": "OTHER"}]


def test_pole_switch_parent_lookup_matches_name_only_without_code_or_feeder():
    db = RecordingOracle()
    rows = db.get_combined_device_records("SEC123")

    assert len(rows) == 1
    assert rows[0]["_matched_field"] == "NAME"
    assert len(db.calls) == 1
    sql, binds = db.calls[0]
    assert "name = :device_name" in sql
    assert "trim(name)" not in sql
    assert "trim(code)" not in sql
    assert "feeder_id" not in sql
    assert binds == {"device_name": "SEC123"}


def test_pole_switch_module_reports_name_only_matching():
    source = Path("src/dmm/application/modules/pole_switch.py").read_text(encoding="utf-8")
    assert "get_combined_device_records(query_name)" in source
    assert "database_query_name" in source
    assert "NAME_OR_CODE" not in source


def test_oracle_business_path_has_no_code_fallback_for_pole_switch_parent():
    source = Path("src/dmm/infrastructure/database/oracle.py").read_text(encoding="utf-8")
    start = source.index("def get_combined_device_records")
    end = source.index("def get_cb_devices_by_combined_name", start)
    method = source[start:end]
    assert "WHERE name = :device_name" in method
    assert "TRIM(name)" not in method
    assert "WHERE TRIM(code) = :device_name" not in method
    assert "feeder_id" not in method.lower().split('do not add a feeder_id constraint')[-1]
