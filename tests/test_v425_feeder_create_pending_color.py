from dmm.infrastructure.reporting.writer import export_html_bundle, status_cls


def test_create_pending_has_dedicated_orange_report_color(tmp_path):
    reports = [{
        "report_type": "FEEDER",
        "g_file": str(tmp_path / "x.g"),
        "file_name": "x.g",
        "drawing_type": "SINGLE_FEEDER",
        "feeder_name": "ADF 15",
        "status": "PASS",
        "severity": "PASS",
        "feedline_rows": [{
            "file_name": "x.g",
            "feeder_name": "ADF 15",
            "xml_id": "fl1",
            "assigned_section_name": "ADF_15_SEC006",
            "db_create_needed": "YES",
            "association_ready": "YES",
            "writeback_needed": "YES",
            "status": "WARN",
            "severity": "CREATE_PENDING",
            "reason": "DB_SECTION_CREATE_PENDING: ADF_15_SEC006",
        }],
    }]

    out = tmp_path / "feeder.html"
    export_html_bundle(
        reports,
        out,
        {"FeedLine": {"table_id": 13503, "domain": 1}},
    )
    text = out.read_text(encoding="utf-8")

    assert status_cls("CREATE_PENDING") == "create"
    assert ".create{background:#FFE8CC}" in text
    assert "橙色 CREATE" in text
    assert "需要先单独创建新的 dms_section_device 记录" in text
    assert "<tr class='create'>" in text
    assert "DB_SECTION_CREATE_PENDING: ADF_15_SEC006" in text
