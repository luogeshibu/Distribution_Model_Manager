from dmm.infrastructure.reporting.writer import _rmu_feeder_overview


def test_filename_feeder_overview_only_shows_file_and_simple_feeder_result():
    html = _rmu_feeder_overview([
        {
            "file_name": "JED-NTH-ABH-16.sln.pic.g",
            "feeder_resolution_source": "FILENAME_405_13500",
            "feeder_resolution_evidence": "internal resolution details should not be shown",
            "feeder_id": "3799912185593857746",
            "station_name": "ABH",
            "feeder_name": "AH316",
            "feeder_context_ready": "YES",
        }
    ])

    assert "G文件" in html
    assert "所属站" in html
    assert "ABH" in html
    assert "AH316" in html
    assert "数据库已找到，馈线：AH316" not in html
    assert "馈线来源" not in html
    assert "文件名 / 数据库判定路径" not in html
    assert "最终馈线ID" not in html
    assert "3799912185593857746" not in html
    assert "internal resolution details" not in html


def test_filename_feeder_overview_reports_missing_feeder_plainly():
    html = _rmu_feeder_overview([
        {
            "file_name": "JED-NTH-ABH-05.sln.pic.g",
            "feeder_resolution_source": "FILENAME_13500_NOT_FOUND",
            "feeder_id": "",
            "feeder_context_ready": "NO",
            "feeder_context_message": "FILENAME_FEEDER_NOT_FOUND: internal diagnostic",
        }
    ])

    assert "ABH" in html
    assert "数据库未找到，请检查该图的馈线是否已创建。" in html
    assert "FILENAME_FEEDER_NOT_FOUND" not in html
