from pathlib import Path

from dmm.application.modules.rmu import RmuModelModule
from dmm.config.constants import (
    RMU_CHANNEL_STATUS_DEVREF_TOKEN,
    RMU_CHANNEL_STATUS_DOMAIN,
    RMU_CHANNEL_STATUS_KEYID_OFFSET,
    RMU_CHANNEL_STATUS_TABLE_ID,
)
from dmm.domain.gfile.parser import Box, GObject, GParser
from dmm.domain.rmu.validator import RmuValidator
from dmm.infrastructure.database.oracle import OracleClient
from dmm.infrastructure.gfile.writeback import GWriteBackService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeDb:
    def __init__(self, rows=None, decoded=None):
        self.rows = list(rows or [])
        self.calls = []
        self.decoded = decoded

    def get_channel_status_keyids_by_combined_id(self, combined_id):
        self.calls.append(int(combined_id))
        return list(self.rows)

    def verify_keyid(self, keyid):
        if self.decoded is not None:
            return dict(self.decoded)
        for row in self.rows:
            if int(row.get("new_id")) == int(keyid):
                return {
                    "device_id": int(row.get("channel_id")),
                    "tab_no": 13566,
                    "col_no": 40,
                }
        return {}


def _validator(db):
    return RmuValidator(db, GParser(), {}, element_catalog={})


def _status(devref="#channel_status.zt.icn.g:channel_status", keyid=""):
    return GObject(
        tag="Status",
        attrs={"id": "126000001", "devref": devref, "keyid": keyid},
        box=Box(10, 10, 66, 26),
        xml_index=1,
    )


def _rmu_result(rmu_id=200):
    return {"rmu_name": "RMU-1", "rmu_id": rmu_id}


def test_makkah_channel_status_constants_match_jazan_field_rule():
    assert RMU_CHANNEL_STATUS_DEVREF_TOKEN == "channel_status.zt.icn.g"
    assert RMU_CHANNEL_STATUS_TABLE_ID == 13566
    assert RMU_CHANNEL_STATUS_DOMAIN == 40
    assert RMU_CHANNEL_STATUS_KEYID_OFFSET == 171798691840


def test_channel_status_recognition_is_status_plus_devref_token():
    validator = _validator(FakeDb())
    assert validator._is_channel_status_element(_status()) is True
    assert validator._is_channel_status_element(_status("#other.zt.icn.g:other")) is False
    non_status = GObject(
        tag="Text",
        attrs={"id": "t1", "devref": "#channel_status.zt.icn.g:channel_status"},
        box=Box(0, 0, 10, 10),
        xml_index=1,
    )
    assert validator._is_channel_status_element(non_status) is False


def test_unique_channel_row_is_direct_association_candidate_without_feeder_gate():
    db = FakeDb([{
        "new_id": 987654321,
        "channel_id": 123,
        "chan_name": "CHANNEL STATUS",
        "combined_id": 200,
    }])
    validator = _validator(db)
    elem = _status()
    row = validator._make_channel_status_row(_rmu_result(), elem)
    validator._validate_channel_status(row, elem, _rmu_result())

    assert db.calls == [200]
    assert row["association_kind"] == "RMU_CHANNEL_STATUS"
    assert row["expected_keyid"] == 987654321
    assert row["expected_keyid_verified"] == "YES"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert row["severity"] == "UNLINKED"
    assert row["table_id"] == 13566
    assert row["configured_domain"] == 40


def test_existing_matching_channel_keyid_is_pass():
    db = FakeDb([{
        "new_id": 987654321,
        "channel_id": 123,
        "chan_name": None,
    }])
    validator = _validator(db)
    elem = _status(keyid="987654321")
    row = validator._make_channel_status_row(_rmu_result(), elem)
    validator._validate_channel_status(row, elem, _rmu_result())
    assert row["status"] == "PASS"
    assert row["model_link_correct"] == "YES"
    assert row["writeback_needed"] == "NO"


def test_multiple_channel_rows_are_never_guessed():
    db = FakeDb([
        {"new_id": 1, "channel_id": 11},
        {"new_id": 2, "channel_id": 12},
    ])
    validator = _validator(db)
    elem = _status()
    row = validator._make_channel_status_row(_rmu_result(), elem)
    validator._validate_channel_status(row, elem, _rmu_result())
    assert row["status"] == "FAIL"
    assert row["association_ready"] == "NO"
    assert "CHANNEL_STATUS_DUPLICATE" in row["reason"]


def test_wrong_verified_table_or_domain_is_blocked():
    db = FakeDb(
        [{"new_id": 987654321, "channel_id": 123}],
        decoded={"device_id": 123, "tab_no": 13566, "col_no": 39},
    )
    validator = _validator(db)
    elem = _status()
    row = validator._make_channel_status_row(_rmu_result(), elem)
    validator._validate_channel_status(row, elem, _rmu_result())
    assert row["status"] == "FAIL"
    assert row["association_ready"] == "NO"
    assert "CHANNEL_STATUS_KEYID_VERIFY_FAILED" in row["reason"]


def test_oracle_channel_query_matches_jazan_sql_and_offset():
    client = OracleClient({
        "user": "u", "password": "p", "host": "h", "port": 1521, "service_name": "s"
    })
    captured = {}

    def fake_query(sql, binds=None):
        captured["sql"] = sql
        captured["binds"] = binds
        return [{"new_id": 99}]

    client._query = fake_query
    rows = client.get_channel_status_keyids_by_combined_id(3800193660570625890)
    assert rows == [{"new_id": 99}]
    assert captured["binds"] == {
        "combined_id": 3800193660570625890,
        "channel_keyid_offset": 171798691840,
    }
    assert "ci.id + :channel_keyid_offset AS new_id" in captured["sql"]
    assert "UPPER(TRIM(ci.chan_name)) NOT LIKE '%DR'" in captured["sql"]


def test_channel_status_writeback_fields_and_slot1_cleanup(tmp_path):
    row = {
        "association_kind": "RMU_CHANNEL_STATUS",
        "expected_keyid": 3818489705855469990,
    }
    attrs = RmuModelModule._attributes_for_row(row)
    assert attrs == {
        "app": "6600000",
        "voltype": "-1",
        "p_ReportType": "1",
        "state": "39",
        "keyid": "3818489705855469990",
    }
    assert RmuModelModule._remove_attributes_for_row(row) == [
        "app1", "voltype1", "p_ReportType1", "state1", "keyid1"
    ]

    g_file = tmp_path / "sample.g"
    g_file.write_text(
        '<G><Status id="126000019" '
        'devref="#channel_status.zt.icn.g:channel_status" '
        'app="6500000" app1="6500000" voltype1="0" '
        'p_ReportType1="1" state1="41" keyid="123" keyid1="999"/></G>',
        encoding="utf-8",
    )
    GWriteBackService().apply_attribute_changes(
        g_file,
        [{
            "tag": "Status",
            "xml_id": "126000019",
            "attributes": attrs,
            "remove_attributes": RmuModelModule._remove_attributes_for_row(row),
        }],
        create_backup=False,
    )
    text = g_file.read_text(encoding="utf-8")
    assert 'app="6600000"' in text
    assert 'voltype="-1"' in text
    assert 'p_ReportType="1"' in text
    assert 'state="39"' in text
    assert 'keyid="3818489705855469990"' in text
    assert "app1=" not in text
    assert "voltype1=" not in text
    assert "p_ReportType1=" not in text
    assert "state1=" not in text
    assert "keyid1=" not in text


def test_makkah_port_keeps_rmu_resolution_and_has_no_channel_feeder_gate():
    validator_source = (
        PROJECT_ROOT / "src/dmm/domain/rmu/validator.py"
    ).read_text(encoding="utf-8")
    module_source = (
        PROJECT_ROOT / "src/dmm/application/modules/rmu.py"
    ).read_text(encoding="utf-8")

    assert "assign_rmu_label_candidates_globally" in validator_source
    assert "get_channel_status_keyids_by_combined_id" in validator_source
    assert "CHANNEL_STATUS_DRAWING_FEEDER_NOT_RESOLVED" not in validator_source
    assert "CHANNEL_STATUS_RMU_FEEDER_MISMATCH" not in validator_source
    assert 'association_kind == "RMU_CHANNEL_STATUS"' in module_source
    assert "EXEC_CHANNEL_STATUS_NOT_UNIQUE" in module_source


def test_v41101_version():
    constants = (PROJECT_ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.112"' in constants
    assert 'version = "4.1.112"' in pyproject


def test_apply_channel_status_rechecks_db_and_writes_safe_copy(tmp_path):
    from dmm.config.defaults import (
        DEFAULT_RMU_NAME_DETECTION_MODE,
        DEFAULT_RMU_NAME_POSITIONS,
    )

    class ApplyDb:
        def get_rmu_records(self, name):
            assert name == "RMU-1"
            return [{"id": 200, "name": "RMU-1"}]

        def get_channel_status_keyids_by_combined_id(self, combined_id):
            assert int(combined_id) == 200
            return [{
                "new_id": 987654321,
                "channel_id": 123,
                "chan_name": "RMU-1-Channel-PR",
                "combined_id": 200,
            }]

        def verify_keyid(self, keyid):
            assert int(keyid) == 987654321
            return {"device_id": 123, "tab_no": 13566, "col_no": 40}

    source = tmp_path / "makkah.g"
    source.write_text(
        '<G><Status id="s1" devref="#channel_status.zt.icn.g:channel_status" '
        'app="6500000" app1="6500000" voltype1="0" '
        'p_ReportType1="1" state1="41" keyid="" keyid1="999"/></G>',
        encoding="utf-8",
    )
    stat = source.stat()

    settings = {
        "rmu_name_detection_mode": DEFAULT_RMU_NAME_DETECTION_MODE,
        "rmu_name_positions": dict(DEFAULT_RMU_NAME_POSITIONS),
        "device_rules": {},
        "_runtime_rules": {},
    }
    snapshot = {
        "rmu_name_detection_mode": str(DEFAULT_RMU_NAME_DETECTION_MODE).upper(),
        "rmu_name_positions": dict(DEFAULT_RMU_NAME_POSITIONS),
        "breaker_name_source": "GRAPHICAL_TEXT",
        "device_rules": {},
    }
    base_row = {
        "association_kind": "RMU_CHANNEL_STATUS",
        "rmu_name": "RMU-1",
        "rmu_id": 200,
        "object_type": "Status",
        "xml_id": "s1",
        "logical_code": "CHANNEL_STATUS",
        "selected_device_name": "CHANNEL_STATUS",
        "table_id": 13566,
        "table_name": "dms_channel_info",
        "configured_domain": 40,
        "expected_keyid": 987654321,
        "association_ready": "YES",
        "writeback_needed": "YES",
        "status": "WARN",
        "severity": "UNLINKED",
        "model_linked": "NO",
    }
    preview = {
        "settings_snapshot": snapshot,
        "file_fingerprints": {
            str(source): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        },
        "changes_by_file": {
            str(source): [{
                "xml_id": "s1",
                "tag": "Status",
                "attributes": RmuModelModule._attributes_for_row(base_row),
                "remove_attributes": RmuModelModule._remove_attributes_for_row(base_row),
                "rmu_name": "RMU-1",
                "rmu_id": 200,
                "device_name": "CHANNEL_STATUS",
                "device_id": 123,
                "expected_keyid": 987654321,
                "frame_index": 1,
                "validated_row": dict(base_row),
                "association_kind": "RMU_CHANNEL_STATUS",
            }]
        },
    }

    out = tmp_path / "g_output"
    result = RmuModelModule().apply_association(
        ApplyDb(),
        [source],
        settings,
        preview,
        lambda _msg: None,
        output_g_dir=out,
    )

    written = out / source.name
    assert written.exists()
    text = written.read_text(encoding="utf-8")
    assert 'app="6600000"' in text
    assert 'voltype="-1"' in text
    assert 'p_ReportType="1"' in text
    assert 'state="39"' in text
    assert 'keyid="987654321"' in text
    assert "app1=" not in text
    assert "voltype1=" not in text
    assert "p_ReportType1=" not in text
    assert "state1=" not in text
    assert "keyid1=" not in text
    assert result["applied_count"] == 1
