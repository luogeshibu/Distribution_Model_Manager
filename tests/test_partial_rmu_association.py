from pathlib import Path

from dmm.application.modules.rmu import RmuModelModule


def make_row(xml_id, ready, writeback, expected_keyid, status="WARN"):
    return {
        "xml_id": xml_id,
        "object_type": "CBreakerDis",
        "association_ready": ready,
        "writeback_needed": writeback,
        "model_link_correct": "",
        "rmu_name": "17613",
        "rmu_id": 100,
        "selected_device_name": f"Y{xml_id}",
        "db_device_id": 1000 + int(xml_id),
        "expected_keyid": expected_keyid,
        "status": status,
    }


def test_unique_rmu_partial_association_writes_only_valid_devices(tmp_path):
    module = RmuModelModule()

    good1 = make_row("1", "YES", "YES", 111)
    bad = make_row("2", "NO", "NO", "", status="FAIL")
    good2 = make_row("3", "YES", "YES", 333)

    report = {
        "g_file": str(tmp_path / "test.g"),
        "rmu_results": [{
            "rmu_name": "17613",
            "rmu_id": 100,
            "association_eligible": True,
            "association_block_reasons": [],
            "device_block_reasons": ["Y2:DEVICE_NOT_FOUND"],
            "device_rows": [good1, bad, good2],
        }],
    }

    module.validate = lambda *args, **kwargs: (
        [report],
        {},
        {},
    )

    gfile = tmp_path / "test.g"
    gfile.write_text("<G/>", encoding="utf-8")

    result = module.preview_association(
        db=None,
        files=[gfile],
        settings={
            "_runtime_rules": {},
            "rmu_name_positions": {"top": True},
            "breaker_name_source": "P_NAME_STRING",
            "device_rules": {},
        },
        log_callback=lambda message: None,
    )

    changes = result["changes_by_file"][str(gfile)]
    assert [change["xml_id"] for change in changes] == ["1", "3"]
    assert len(result["skipped_rmus"]) == 0


def test_nonunique_rmu_still_blocks_whole_rmu(tmp_path):
    module = RmuModelModule()

    good1 = make_row("1", "YES", "YES", 111)
    good2 = make_row("2", "YES", "YES", 222)

    report = {
        "g_file": str(tmp_path / "test.g"),
        "rmu_results": [{
            "rmu_name": "17613",
            "rmu_id": "",
            "association_eligible": False,
            "association_block_reasons": ["RMU_DUPLICATE_IN_DATABASE"],
            "device_rows": [good1, good2],
        }],
    }

    module.validate = lambda *args, **kwargs: (
        [report],
        {},
        {},
    )

    gfile = tmp_path / "test.g"
    gfile.write_text("<G/>", encoding="utf-8")

    result = module.preview_association(
        db=None,
        files=[gfile],
        settings={
            "_runtime_rules": {},
            "rmu_name_positions": {"top": True},
            "breaker_name_source": "P_NAME_STRING",
            "device_rules": {},
        },
        log_callback=lambda message: None,
    )

    assert result["changes_by_file"] == {}
    assert len(result["skipped_rmus"]) == 1
