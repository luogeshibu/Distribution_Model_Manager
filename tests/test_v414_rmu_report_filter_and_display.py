from dmm.infrastructure.reporting.writer import (
    export_csv_bundle,
    export_html_bundle,
    flatten_rmu_rows,
)


def _reports():
    return [{
        "report_type": "RMU",
        "file_name": "JED-NTH-ABH-06.sln.pic.g",
        "rmu_results": [
            {
                "frame_index": 1,
                "frame_xml_id": "2001",
                "rmu_name": "16934",
                "rmu_type": "2L1T",
                "rmu_type_source": "DEVREF",
                "rmu_type_text": "3L",
                "rmu_type_devref": "2L1T",
                "rmu_type_consistent": "NO",
                "rmu_type_check_status": "WARN",
                "rmu_type_check_reason": "mismatch",
                "rmu_is_smart": "YES",
                "rmu_smart_marker_types": "SMART",
                "rmu_status": "PASS",
                "rmu_severity": "PASS",
                "rmu_reason": "RMU_MODEL_DATA_VALID",
                "rmu_records": [{"id": 9001}],
                "association_block_reasons": [],
                "device_block_reasons": [],
                "inventory_issues": [],
                "db_integrity_issues": [],
                "association_eligible": True,
                "linked_correct_count": 1,
                "unlinked_count": 0,
                "linked_wrong_count": 0,
                "device_rows": [{
                    "xml_id": "c1",
                    "object_type": "CBreakerDis",
                    "rmu_name": "16934",
                    "logical_code": "Y1",
                    "db_match_count": 1,
                    "db_combined_id": 9001,
                    "status": "PASS",
                }],
            },
            {
                "frame_index": 2,
                "frame_xml_id": "2002",
                "rmu_name": "20574",
                "rmu_type": "2L1T",
                "rmu_type_source": "TEXT_YQ",
                "rmu_type_text": "2L1T",
                "rmu_type_devref": "2L1T",
                "rmu_type_consistent": "YES",
                "rmu_type_check_status": "PASS",
                "rmu_type_check_reason": "",
                "rmu_is_smart": "NO",
                "rmu_smart_marker_types": "",
                "rmu_status": "PASS",
                "rmu_severity": "PASS",
                "rmu_reason": "RMU_MODEL_DATA_VALID",
                "rmu_records": [{"id": 9002}],
                "association_block_reasons": [],
                "device_block_reasons": [],
                "inventory_issues": [],
                "db_integrity_issues": [],
                "association_eligible": True,
                "linked_correct_count": 1,
                "unlinked_count": 0,
                "linked_wrong_count": 0,
                "device_rows": [{
                    "xml_id": "c2",
                    "object_type": "CBreakerDis",
                    "rmu_name": "20574",
                    "logical_code": "Q1",
                    "db_match_count": 1,
                    "db_combined_id": 9002,
                    "status": "PASS",
                }],
            },
        ],
    }]


def test_report_facing_smart_column_uses_smart_normal():
    rows = flatten_rmu_rows(_reports())
    assert rows[0]["rmu_is_smart"] == "SMART"
    assert rows[1]["rmu_is_smart"] == "NORMAL"
    # Existing marker column remains unchanged.
    assert rows[0]["rmu_smart_marker_types"] == "SMART"
    assert rows[1]["rmu_smart_marker_types"] == ""


def test_rmu_html_has_independent_fuzzy_filters_for_both_tables(tmp_path):
    html = tmp_path / "report.html"
    export_html_bundle(
        _reports(),
        html,
        {
            "CBreakerDis": {"table_id": 13502, "domain": 40},
            "ZhaiWaiJieDiDaoZha": {"table_id": 13514, "domain": 40},
            "BusDis": {"table_id": 13506, "domain": 1},
        },
    )
    text = html.read_text(encoding="utf-8")
    assert "id='rmu-summary-table'" in text
    assert "id='rmu-device-table'" in text
    assert "filterReportTable('rmu-summary-table'" in text
    assert "filterReportTable('rmu-device-table'" in text
    assert "输入环网柜名称或任意字符，模糊匹配" in text
    assert "haystack.includes(query)" in text
    assert "id='rmu-summary-table-color-filter'" in text
    assert "id='rmu-device-table-color-filter'" in text
    assert "全部颜色" in text
    assert "getReportRowColor" in text
    assert "colorMatched" in text
    assert ">SMART</td>" in text
    assert ">NORMAL</td>" in text


def test_rmu_csv_uses_smart_normal_without_changing_marker_column(tmp_path):
    paths = export_csv_bundle(_reports(), tmp_path / "report.csv")
    summary = paths[0].read_text(encoding="utf-8-sig")
    assert "SMART" in summary
    assert "NORMAL" in summary
    assert "智能标识" in summary
