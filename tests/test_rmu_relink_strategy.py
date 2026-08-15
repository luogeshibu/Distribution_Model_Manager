from pathlib import Path

from dmm.domain.rmu.validator import RmuValidator
from dmm.infrastructure.reporting.writer import export_html_bundle


class DummyParser:
    pass


class Elem:
    def __init__(self, keyid):
        self.keyid = keyid


class DummyDB:
    def __init__(
        self,
        verify_result=None,
        current_record=None,
        current_rmu=None,
        verify_error=None,
    ):
        self.verify_result = verify_result or {}
        self.current_record = current_record
        self.current_rmu = current_rmu
        self.verify_error = verify_error

    def verify_keyid(self, keyid):
        if self.verify_error:
            raise RuntimeError(self.verify_error)
        return dict(self.verify_result)

    def get_device_by_id(self, table_id, device_id):
        if self.current_record is None:
            return None
        return dict(self.current_record)

    def get_rmu_by_id(self, rmu_id):
        if self.current_rmu is None:
            return None
        return dict(self.current_rmu)


def make_validator(db):
    return RmuValidator(
        db=db,
        parser=DummyParser(),
        device_rules={},
    )


def base_row(**kwargs):
    row = {
        "rmu_name": "17613",
        "rmu_id": 500,
        "db_device_id": 2000,
        "db_code": "Y1",
        "db_bv_id": 112871465660973067,
        "expected_keyid": 3000,
        "model_linked": "YES",
        "model_link_correct": "",
        "model_link_status": "",
        "association_action": "",
        "writeback_needed": "NO",
        "association_ready": "NO",
        "status": "",
        "severity": "",
        "reason": "",
    }
    row.update(kwargs)
    return row


RULE = {"table_id": 13502, "domain": 40}


def test_old_device_deleted_and_recreated_with_new_id_is_relinkable():
    db = DummyDB(
        verify_result={
            "device_id": 1000,  # old deleted database ID
            "tab_no": 13502,
            "col_no": 40,
        },
        current_record=None,  # old row no longer exists
    )
    v = make_validator(db)
    row = base_row()

    v._evaluate_current_model(
        row,
        Elem("1999"),
        device_id=2000,  # newly-created current device
        rule=RULE,
        rmu_id=500,
    )

    assert row["status"] == "RELINK"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert "DEVICE_ID已变化" in row["reason"]


def test_wrong_old_domain_is_relinkable_when_current_target_is_valid():
    db = DummyDB(
        verify_result={
            "device_id": 2000,
            "tab_no": 13502,
            "col_no": 0,  # old G model domain is wrong
        },
        current_record={
            "id": 2000,
            "code": "Y1",
            "name": "Y1",
            "combined_id": 500,
            "_table_name": "dms_cb_device",
        },
        current_rmu={
            "id": 500,
            "name": "17613",
        },
    )
    v = make_validator(db)
    row = base_row()

    v._evaluate_current_model(
        row,
        Elem("2000"),
        device_id=2000,
        rule=RULE,
        rmu_id=500,
    )

    assert row["status"] == "RELINK"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert "DOMAIN不匹配" in row["reason"]


def test_old_link_to_other_rmu_is_correctable_rmu_relink():
    db = DummyDB(
        verify_result={
            "device_id": 1000,
            "tab_no": 13502,
            "col_no": 40,
        },
        current_record={
            "id": 1000,
            "code": "Y1",
            "name": "Y1",
            "combined_id": 999,  # old link belongs to another RMU
            "_table_name": "dms_cb_device",
        },
        current_rmu={
            "id": 999,
            "name": "26772",
        },
    )
    v = make_validator(db)
    row = base_row()

    v._evaluate_current_model(
        row,
        Elem("1000"),
        device_id=2000,
        rule=RULE,
        rmu_id=500,
    )

    assert row["status"] == "RMU_RELINK"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert "26772" in row["reason"]


def test_unresolvable_old_keyid_is_relinkable():
    db = DummyDB(verify_error="old device no longer exists")
    v = make_validator(db)
    row = base_row()

    v._evaluate_current_model(
        row,
        Elem("123456"),
        device_id=2000,
        rule=RULE,
        rmu_id=500,
    )

    assert row["status"] == "RELINK"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert "STALE_OR_UNRESOLVABLE" in row["reason"]


def test_correct_current_model_remains_pass():
    db = DummyDB(
        verify_result={
            "device_id": 2000,
            "tab_no": 13502,
            "col_no": 40,
        },
        current_record={
            "id": 2000,
            "code": "Y1",
            "name": "Y1",
            "combined_id": 500,
            "_table_name": "dms_cb_device",
        },
        current_rmu={
            "id": 500,
            "name": "17613",
        },
    )
    v = make_validator(db)
    row = base_row(expected_keyid=3000)

    # Current keyid must equal the expected keyid for PASS.
    db.verify_result = {
        "device_id": 2000,
        "tab_no": 13502,
        "col_no": 40,
    }

    v._evaluate_current_model(
        row,
        Elem("3000"),
        device_id=2000,
        rule=RULE,
        rmu_id=500,
    )

    assert row["status"] == "PASS"
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "NO"


def test_rmu_html_has_row_selection_and_new_status_legend(tmp_path):
    reports = [{
        "g_file": str(tmp_path / "a.g"),
        "file_name": "a.g",
        "rmu_results": [{
            "frame_index": 1,
            "frame_xml_id": "2000001",
            "rmu_name": "17613",
            "rmu_status": "WARN",
            "rmu_severity": "ASSOCIATION_ACTION_REQUIRED",
            "rmu_reason": "RMU_ASSOCIATION_ACTION_REQUIRED",
            "rmu_db_count": 1,
            "rmu_id": 500,
            "device_rows": [{
                "rmu_name": "17613",
                "rmu_id": 500,
                "object_type": "CBreakerDis",
                "xml_id": "117000001",
                "logical_code": "Y1",
                "db_match_count": 1,
                "db_device_id": 2000,
                "db_code": "Y1",
                "db_combined_id": 500,
                "db_bv_id": 112871465660973067,
                "expected_keyid": 3000,
                "current_keyid": 1000,
                "model_linked": "YES",
                "model_link_correct": "NO",
                "association_action": "重新关联",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "status": "RELINK",
                "severity": "MODEL_RELINK",
                "reason": "MODEL_RELINK_REQUIRED",
            }],
            "association_eligible": True,
            "association_block_reasons": [],
            "device_block_reasons": [],
            "inventory_issues": [],
            "db_integrity_issues": [],
        }],
    }]

    path = tmp_path / "report.html"
    export_html_bundle(
        reports,
        path,
        {
            "CBreakerDis": {
                "table_id": 13502,
                "domain": 40,
            }
        },
    )

    html = path.read_text(encoding="utf-8")
    assert "row-check" in html
    assert "toggleSelectedRow" in html
    assert "橙色 RELINK" in html
    assert "紫色 RMU_RELINK" in html
    assert "row-selected" in html
