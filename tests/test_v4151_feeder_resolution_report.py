from dmm.infrastructure.reporting.writer import _feeder_resolution_card, export_html_bundle


def _base_report(report_type="POLE_SWITCH"):
    return {
        "report_type": report_type,
        "file_name": "JED-STH-ADEL-06.sln.pic.g",
        "feeder_resolution_source": "FILENAME_405_13500",
        "feeder_anchor": "FILE:JED-STH-ADEL-06.sln.pic.g->405:ADEL(40501)->13500:AH306",
        "feeder_id": "3799912185593858641",
        "feeder_name": "ADEL AH306",
        "feeder_path": "ADEL / AH306",
        "feeder_context_ready": "YES",
    }


def test_compact_feeder_resolution_card_shows_filename_method():
    html = _feeder_resolution_card([_base_report()], english=False)
    assert "G文件名" in html
    assert "405/substation.NAME 精确找站" in html
    assert "13500 按 ST_ID + NAME 精确查询" in html
    assert "FEEDER_ID=3799912185593858641" in html
    assert "ADEL / AH306" in html


def test_compact_feeder_resolution_card_same_path_for_transformer_report():
    html = _feeder_resolution_card([_base_report("TRANSFORMER")], english=False)
    assert "G文件名" in html
    assert "AH3+两位编号" in html


def test_feeder_html_contains_filename_resolution_card(tmp_path):
    report = _base_report("FEEDER")
    report.update({
        "drawing_type": "SINGLE_FEEDER",
        "drawing_mode": "SINGLE_FEEDER",
        "automatic_drawing_type": "SINGLE_FEEDER",
        "feeder_records": [{"id": report["feeder_id"]}],
        "feedline_rows": [],
        "association_eligible": True,
        "status": "PASS",
        "severity": "OK",
        "reason": "",
    })
    out = tmp_path / "feeder.html"
    export_html_bundle([report], out, {"FeedLine": {"table_id": 13503, "domain": 1}})
    text = out.read_text(encoding="utf-8")
    assert "馈线判定" in text
    assert "G文件名" in text
    assert "405/substation.NAME 精确找站" in text


def test_master_station_context_uses_filename_resolution_method(tmp_path):
    report = {
        "report_type": "MASTER_STATION",
        "file_name": "JED-STH-ADEL-06.sln.pic.g",
        "master_station_rows": [],
        "association_context": {
            "feeder_resolution_source": "FILENAME_405_13500",
            "feeder_anchor": "FILE:JED-STH-ADEL-06.sln.pic.g->405:ADEL(40501)->13500:AH306",
            "feeder_id": "123",
            "feeder_path": "ADEL / AH306",
            "message": "",
        },
        "drawing_scope": {},
    }
    out = tmp_path / "master.html"
    export_html_bundle([report], out, {})
    text = out.read_text(encoding="utf-8")
    assert "判定过程" in text
    assert "G文件名" in text
    assert "13500 按 ST_ID + NAME 精确查询" in text
