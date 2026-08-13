
from pathlib import Path

from dmm.application.modules.rmu import RmuModelModule, KEYID_STEP


class DummyDB:
    def get_rmu_records(self, name):
        assert name == "29802"
        return [{"id": 9001, "name": "29802"}]

    def get_devices_by_combined_id(self, table_id, rmu_id):
        assert table_id == 13502
        assert rmu_id == 9001
        return "dms_cb_device", [
            {
                "id": 7001,
                "code": "Y1",
                "name": "Y1",
                "combined_id": 9001,
                "bv_id": 112871465660973067,
            }
        ]

    def verify_keyid(self, keyid):
        return {
            "device_id": 7001,
            "tab_no": 13502,
            "col_no": 40,
        }


def test_apply_association_writes_only_selected_xml_and_reports_only_selected(
    tmp_path,
):
    source = tmp_path / "test.g"
    source.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<G>
  <CBreakerDis id="117000001" p_NameString="Y1" keyid="" voltype="" app="" state="" p_ReportType="0" />
  <CBreakerDis id="117000002" p_NameString="Y2" keyid="" voltype="" app="" state="" p_ReportType="0" />
</G>
""",
        encoding="utf-8",
    )

    stat = source.stat()
    expected_keyid = 7001 + 40 * KEYID_STEP

    settings = {
        "rmu_name_positions": {
            "top": True,
            "right": False,
            "left": False,
            "bottom": False,
        },
        "breaker_name_source": "P_NAME_STRING",
        "device_rules": {
            "CBreakerDis": {
                "table_id": 13502,
                "domain": 40,
            },
        },
        "_runtime_rules": {
            "CBreakerDis": {
                "table_id": 13502,
                "domain": 40,
            },
        },
    }

    preview = {
        "settings_snapshot": {
            "rmu_name_positions": dict(settings["rmu_name_positions"]),
            "breaker_name_source": "P_NAME_STRING",
            "device_rules": dict(settings["device_rules"]),
        },
        "file_fingerprints": {
            str(source): {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            },
        },
        "changes_by_file": {
            str(source): [
                {
                    "xml_id": "117000001",
                    "tag": "CBreakerDis",
                    "rmu_name": "29802",
                    "rmu_id": 9001,
                    "device_name": "Y1",
                    "device_id": 6000,  # old validated ID can change
                    "expected_keyid": 1,
                    "frame_index": 17,
                    "validated_row": {
                        "rmu_name": "29802",
                        "rmu_id": 9001,
                        "object_type": "CBreakerDis",
                        "xml_id": "117000001",
                        "p_name_string": "Y1",
                        "selected_device_name": "Y1",
                        "db_code": "Y1",
                        "db_device_id": 6000,
                        "db_bv_id": 1,
                        "expected_keyid": 1,
                        "model_linked": "NO",
                        "status": "WARN",
                    },
                    "attributes": {
                        "app": "6500000",
                        "voltype": "1",
                        "p_ReportType": "1",
                        "state": "41",
                        "keyid": "1",
                    },
                }
            ],
        },
    }

    logs = []
    output = tmp_path / "g_output"

    result = RmuModelModule().apply_association(
        DummyDB(),
        [source],
        settings,
        preview,
        logs.append,
        output_g_dir=output,
    )

    assert result["selected_count"] == 1
    assert result["applied_count"] == 1
    assert result["skipped_count"] == 0

    copied = Path(result["copied_files"][0])
    text = copied.read_text(encoding="utf-8")

    # Selected Y1 was refreshed to the CURRENT database ID/BV_ID/keyid.
    first_line = next(
        line for line in text.splitlines()
        if 'id="117000001"' in line
    )
    assert 'keyid="' + str(expected_keyid) + '"' in first_line
    assert 'voltype="112871465660973067"' in first_line
    assert 'app="6500000"' in first_line
    assert 'state="41"' in first_line

    # Unselected Y2 is byte/logically untouched.
    second_line = next(
        line for line in text.splitlines()
        if 'id="117000002"' in line
    )
    assert 'keyid=""' in second_line
    assert 'voltype=""' in second_line
    assert 'app=""' in second_line

    reports = result["operation_reports"]
    assert len(reports) == 1
    assert len(reports[0]["rmu_results"]) == 1
    rows = reports[0]["rmu_results"][0]["device_rows"]
    assert len(rows) == 1
    assert rows[0]["xml_id"] == "117000001"
    assert rows[0]["reason"] == "ASSOCIATION_WRITE_SUCCESS"

    # Execution log must describe targeted operation, not a full-RMU scan.
    joined = "\n".join(logs)
    assert "仅复核已选择的 1 个环网柜、1 个设备" in joined
    assert "无需关联：" not in joined


def test_execution_skips_selected_device_if_database_becomes_ambiguous(
    tmp_path,
):
    class AmbiguousDB(DummyDB):
        def get_devices_by_combined_id(self, table_id, rmu_id):
            row = {
                "id": 7001,
                "code": "Y1",
                "name": "Y1",
                "combined_id": 9001,
                "bv_id": 112871465660973067,
            }
            other = dict(row)
            other["id"] = 7002
            return "dms_cb_device", [row, other]

    source = tmp_path / "test.g"
    source.write_text(
        '<G><CBreakerDis id="117000001" p_NameString="Y1" keyid="" /></G>',
        encoding="utf-8",
    )
    stat = source.stat()

    settings = {
        "rmu_name_positions": {"top": True},
        "breaker_name_source": "P_NAME_STRING",
        "device_rules": {
            "CBreakerDis": {"table_id": 13502, "domain": 40},
        },
        "_runtime_rules": {
            "CBreakerDis": {"table_id": 13502, "domain": 40},
        },
    }
    preview = {
        "settings_snapshot": {
            "rmu_name_positions": {"top": True},
            "breaker_name_source": "P_NAME_STRING",
            "device_rules": dict(settings["device_rules"]),
        },
        "file_fingerprints": {
            str(source): {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        },
        "changes_by_file": {
            str(source): [{
                "xml_id": "117000001",
                "tag": "CBreakerDis",
                "rmu_name": "29802",
                "device_name": "Y1",
                "frame_index": 1,
                "validated_row": {
                    "rmu_name": "29802",
                    "object_type": "CBreakerDis",
                    "xml_id": "117000001",
                    "p_name_string": "Y1",
                },
            }]
        },
    }

    result = RmuModelModule().apply_association(
        AmbiguousDB(),
        [source],
        settings,
        preview,
        lambda _msg: None,
        output_g_dir=tmp_path / "g_output",
    )

    assert result["selected_count"] == 1
    assert result["applied_count"] == 0
    assert result["skipped_count"] == 1
    assert result["copied_files"] == []

    row = result["operation_reports"][0]["rmu_results"][0]["device_rows"][0]
    assert row["status"] == "FAIL"
    assert "EXEC_DEVICE_CODE_DUPLICATE" in row["reason"]
