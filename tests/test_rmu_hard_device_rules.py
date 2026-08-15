from dmm.domain.rmu.validator import RmuValidator


class DummyParser:
    pass


class DummyDB:
    def get_devices_by_combined_id(self, table_id, combined_id):
        return "dummy", list(self.rows_by_owner.get((table_id, combined_id), []))

    rows_by_owner = {}


def validator():
    return RmuValidator(
        db=DummyDB(),
        parser=DummyParser(),
        device_rules={},
    )


def base_row(**kwargs):
    row = {
        "db_code": "Y1",
        "selected_device_name": "Y1",
        "logical_code": "Y1",
        "db_device_id": 100,
        "model_linked": "NO",
        "model_link_correct": "",
        "association_ready": "YES",
        "writeback_needed": "YES",
        "status": "WARN",
        "severity": "UNLINKED",
        "reason": "MODEL_NOT_LINKED",
        "xml_id": "1",
        "object_type": "CBreakerDis",
    }
    row.update(kwargs)
    return row


def test_database_device_must_belong_to_current_unique_rmu():
    v = validator()
    row = base_row()
    dev = {"id": 100, "code": "Y1", "combined_id": 200}

    ok = v._validate_expected_device_ownership(row, dev, 100)

    assert ok is False
    assert row["status"] == "RMU_LINK"
    assert row["association_ready"] == "NO"


def test_same_pname_used_by_two_g_elements_is_hard_error():
    v = validator()
    rmu = {
        "device_rows": [
            base_row(xml_id="1", db_device_id=100),
            base_row(xml_id="2", db_device_id=101),
        ],
        "inventory_issues": [],
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    v._validate_one_to_one_device_mapping(rmu)

    assert rmu["inventory_issues"]
    assert all(row["status"] == "FAIL" for row in rmu["device_rows"])
    assert all(row["association_ready"] == "NO" for row in rmu["device_rows"])


def test_same_database_device_used_by_two_g_elements_is_hard_error():
    v = validator()
    rmu = {
        "device_rows": [
            base_row(xml_id="1", logical_code="Y1", db_device_id=100),
            base_row(xml_id="2", logical_code="Y2", db_device_id=100),
        ],
        "inventory_issues": [],
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    v._validate_one_to_one_device_mapping(rmu)

    assert rmu["db_integrity_issues"]
    assert all(row["status"] == "FAIL" for row in rmu["device_rows"])


def test_unrelated_extra_database_devices_are_not_part_of_one_to_one_rule():
    v = validator()
    rmu = {
        "device_rows": [
            base_row(xml_id="1", logical_code="Y1", db_device_id=100),
        ],
        "inventory_issues": [],
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    v._validate_one_to_one_device_mapping(rmu)

    assert not rmu["inventory_issues"]
    assert not rmu["db_integrity_issues"]
