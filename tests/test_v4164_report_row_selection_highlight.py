from dmm.infrastructure.reporting.writer import (
    _export_feeder_html_bundle,
    _export_fuse_html_bundle,
    _export_master_station_html_bundle,
    _export_pole_html_bundle,
    _export_rmu_html_bundle,
    _export_transformer_html_bundle,
)


def test_all_checkbox_html_reports_share_blue_selected_row_highlight(tmp_path):
    cases = [
        (
            _export_rmu_html_bundle,
            [{"report_type": "RMU", "file_name": "x.g", "rmu_results": []}],
            "rmu.html",
        ),
        (
            _export_feeder_html_bundle,
            [{"report_type": "FEEDER", "file_name": "x.g", "feeder_id": 1, "feedline_rows": [{"status": "PASS"}]}],
            "feeder.html",
        ),
        (
            _export_pole_html_bundle,
            [{"report_type": "POLE_SWITCH", "file_name": "x.g", "pole_switch_rows": [{"status": "PASS"}]}],
            "pole.html",
        ),
        (
            _export_transformer_html_bundle,
            [{"report_type": "TRANSFORMER", "file_name": "x.g", "transformer_rows": [{"status": "PASS"}]}],
            "transformer.html",
        ),
        (
            _export_fuse_html_bundle,
            [{"report_type": "FUSE", "file_name": "x.g", "fuse_rows": [{"status": "PASS"}]}],
            "fuse.html",
        ),
        (
            _export_master_station_html_bundle,
            [{"report_type": "MASTER_STATION", "file_name": "x.g", "master_station_rows": [{"status": "PASS"}]}],
            "master.html",
        ),
    ]

    for exporter, reports, name in cases:
        out = tmp_path / name
        exporter(reports, out, {}, language="zh_CN")
        html = out.read_text(encoding="utf-8")
        assert "tr.row-selected > td" in html
        assert "background:#DCEEFF !important" in html
        assert "border-top:2px solid #1976D2 !important" in html
        assert "border-bottom:2px solid #1976D2 !important" in html
        assert "td:first-child { border-left:2px solid #1976D2 !important; }" in html
        assert "td:last-child { border-right:2px solid #1976D2 !important; }" in html
        assert "row.classList.toggle('row-selected', cb.checked);" in html or "row.classList.add('row-selected');" in html
        assert "row.style.display = matched ? '' : 'none';" in html
