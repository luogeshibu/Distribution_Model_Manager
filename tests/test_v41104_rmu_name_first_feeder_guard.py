from pathlib import Path
from types import SimpleNamespace

from dmm.domain.rmu.validator import RmuValidator


class DummyDB:
    pass


class DummyParser:
    pass


def make_validator():
    v = RmuValidator(DummyDB(), DummyParser(), device_rules={})
    v._verify_expected_keyid = lambda row, device_id, rule: True
    v._evaluate_current_model = (
        lambda row, elem, device_id, rule, rmu_id, **kwargs:
        row.update({"status": "PASS", "picked_device_id": device_id})
    )
    return v


def base_row():
    return {
        "rmu_id": 900,
        "required_feeder_id": 700,
        "association_ready": "NO",
        "status": "",
        "reason": "",
    }


def rule(table_id=13502):
    return {"table_id": table_id, "domain": 40}


def elem():
    return SimpleNamespace(keyid="")


def test_breaker_prefers_name_before_code_inside_same_rmu_and_feeder():
    v = make_validator()
    row = base_row()
    db_set = {
        "rows": [
            {
                "id": 1,
                "name": "Y1",
                "code": "LEGACY-CODE",
                "combined_id": 900,
                "feeder_id": 700,
                "bv_id": 11,
            },
            {
                "id": 2,
                "name": "OTHER",
                "code": "Y1",
                "combined_id": 900,
                "feeder_id": 700,
                "bv_id": 11,
            },
        ]
    }

    v._validate_breaker(row, elem(), db_set, rule(), "Y1", "Y1")

    assert row["picked_device_id"] == 1
    assert row["db_match_field"] == "NAME"
    assert row["db_name"] == "Y1"
    assert row["db_code"] == "LEGACY-CODE"


def test_breaker_uses_code_only_when_name_not_found():
    v = make_validator()
    row = base_row()
    db_set = {
        "rows": [
            {
                "id": 2,
                "name": "OTHER",
                "code": "Y2",
                "combined_id": 900,
                "feeder_id": 700,
                "bv_id": 11,
            }
        ]
    }

    v._validate_breaker(row, elem(), db_set, rule(), "Y2", "Y2")

    assert row["picked_device_id"] == 2
    assert row["db_match_field"] == "CODE"


def test_breaker_rejects_same_rmu_device_on_wrong_feeder():
    v = make_validator()
    row = base_row()
    db_set = {
        "rows": [
            {
                "id": 3,
                "name": "Y1",
                "code": "Y1",
                "combined_id": 900,
                "feeder_id": 701,
                "bv_id": 11,
            }
        ]
    }

    v._validate_breaker(row, elem(), db_set, rule(), "Y1", "Y1")

    assert row["status"] == "FAIL"
    assert "CURRENT_FEEDER" in row["reason"]


def test_ground_prefers_k_name_then_falls_back_to_old_d_code():
    v = make_validator()

    name_row = base_row()
    db_set_name = {
        "rows": [
            {
                "id": 4,
                "name": "KY1",
                "code": "SOMETHING-ELSE",
                "combined_id": 900,
                "feeder_id": 700,
                "bv_id": 11,
            }
        ]
    }
    v._validate_ground(name_row, elem(), db_set_name, rule(13514), "Y1")
    assert name_row["picked_device_id"] == 4
    assert name_row["db_match_field"] == "NAME"
    assert name_row["selected_device_name"] == "KY1"

    code_row = base_row()
    db_set_code = {
        "rows": [
            {
                "id": 5,
                "name": "OTHER",
                "code": "Q2D",
                "combined_id": 900,
                "feeder_id": 700,
                "bv_id": 11,
            }
        ]
    }
    v._validate_ground(code_row, elem(), db_set_code, rule(13514), "Q2")
    assert code_row["picked_device_id"] == 5
    assert code_row["db_match_field"] == "CODE"
    assert code_row["selected_device_name"] == "Q2D"


def test_rmu_module_no_longer_limits_feeder_guard_to_single_feeder_drawings():
    src = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/rmu.py"
    ).read_text(encoding="utf-8")
    assert 'if drawing_type == "SINGLE_FEEDER"' not in src
    assert 'report["feeder_context_required"] = "YES"' in src
    assert "resolve_drawing_feeder(" in src
