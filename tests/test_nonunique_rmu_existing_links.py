from dmm.domain.rmu.validator import RmuValidator


class Dummy:
    pass


def make_validator():
    return RmuValidator(
        db=Dummy(),
        parser=Dummy(),
        device_rules={},
    )


def make_row(current_id, current_name="15953"):
    return {
        "model_linked": "YES",
        "model_link_correct": "YES",
        "association_ready": "YES",
        "writeback_needed": "NO",
        "current_combined_id": current_id,
        "current_rmu_name": current_name,
        "status": "PASS",
        "severity": "PASS",
        "reason": "EXISTING_MANUAL_LINK_VALID",
    }


def test_same_actual_rmu_id_is_allowed_for_existing_manual_links():
    validator = make_validator()
    rmu = {
        "rmu_name": "15953",
        "device_rows": [
            make_row(100),
            make_row(100),
            make_row(100),
        ],
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    validator._validate_nonunique_rmu_existing_links(rmu)

    assert not rmu["db_integrity_issues"]
    assert all(
        row["model_link_correct"] == "YES"
        for row in rmu["device_rows"]
    )


def test_same_name_but_multiple_actual_rmu_ids_is_error():
    validator = make_validator()
    rmu = {
        "rmu_name": "15953",
        "device_rows": [
            make_row(100),
            make_row(200),
            make_row(100),
        ],
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    validator._validate_nonunique_rmu_existing_links(rmu)

    assert rmu["db_integrity_issues"]
    assert rmu["association_block_reasons"]
    assert all(
        row["status"] == "RMU_LINK"
        for row in rmu["device_rows"]
    )
    assert all(
        row["model_link_correct"] == "NO"
        for row in rmu["device_rows"]
    )


def test_existing_link_to_other_rmu_name_is_error():
    validator = make_validator()
    rmu = {
        "rmu_name": "15953",
        "device_rows": [
            make_row(100, "26772"),
        ],
        "db_integrity_issues": [],
        "association_block_reasons": [],
    }

    validator._validate_nonunique_rmu_existing_links(rmu)

    row = rmu["device_rows"][0]
    assert row["status"] == "RMU_LINK"
    assert row["model_link_correct"] == "NO"
    assert row["association_ready"] == "NO"
