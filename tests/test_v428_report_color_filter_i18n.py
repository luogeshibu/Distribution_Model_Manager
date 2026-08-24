from dmm.infrastructure.reporting.writer import export_html_bundle


def test_rmu_report_color_filter_is_independent_and_english_localized(tmp_path):
    reports = [{
        "report_type": "RMU",
        "file_name": "x.g",
        "rmu_results": [
            {
                "frame_index": 1,
                "frame_xml_id": "r1",
                "rmu_name": "1001",
                "rmu_status": "WARN",
                "rmu_reason": "RMU_ASSOCIATION_ACTION_REQUIRED",
                "rmu_records": [{"id": 1}],
                "association_block_reasons": [],
                "device_block_reasons": [],
                "inventory_issues": [],
                "db_integrity_issues": [],
                "device_rows": [{"xml_id": "d1", "status": "RELINK", "rmu_name": "1001"}],
            },
            {
                "frame_index": 2,
                "frame_xml_id": "r2",
                "rmu_name": "1002",
                "rmu_status": "FAIL",
                "rmu_reason": "ERROR",
                "rmu_records": [],
                "association_block_reasons": [],
                "device_block_reasons": [],
                "inventory_issues": [],
                "db_integrity_issues": [],
                "device_rows": [],
            },
        ],
    }]
    out = tmp_path / "rmu-en.html"
    export_html_bundle(
        reports,
        out,
        {
            "CBreakerDis": {"table_id": 13502, "domain": 40},
            "ZhaiWaiJieDiDaoZha": {"table_id": 13514, "domain": 40},
            "BusDis": {"table_id": 13506, "domain": 1},
        },
        language="en_US",
    )
    text = out.read_text(encoding="utf-8")
    assert "All Colors" in text
    assert ">Yellow</option>" in text
    assert ">Red</option>" in text
    assert "<tr class='warn'>" in text
    assert "<tr class='fail'>" in text
    assert "<tr class='relink'>" in text
    assert "textMatched && colorMatched" in text
    assert "id='rmu-summary-table-text-filter'" in text
    assert "id='rmu-summary-table-color-filter'" in text
