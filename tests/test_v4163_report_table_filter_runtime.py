from dmm.infrastructure.reporting.writer import (
    _export_fuse_html_bundle,
    _export_master_station_html_bundle,
    _export_pole_html_bundle,
    _export_transformer_html_bundle,
)


def _assert_filter_runtime(html: str, table_id: str) -> None:
    assert f"id='{table_id}-color-filter'" in html
    assert f"filterReportTable('{table_id}')" in html
    assert "function filterReportTable" in html
    assert "function getReportRowColor" in html
    assert "function toggleSelectedRow" in html
    assert "row.style.display = matched ? '' : 'none';" in html


def test_transformer_report_embeds_filter_runtime(tmp_path):
    out = tmp_path / "transformer.html"
    _export_transformer_html_bundle(
        [{"report_type": "TRANSFORMER", "file_name": "x.g", "transformer_rows": [{"status": "FAIL"}]}],
        out,
        {},
        language="zh_CN",
    )
    html = out.read_text(encoding="utf-8")
    _assert_filter_runtime(html, "transformer-table")
    assert "<option value='red'>红色</option>" in html


def test_other_filtered_reports_embed_same_runtime(tmp_path):
    cases = [
        (
            _export_pole_html_bundle,
            [{"report_type": "POLE_SWITCH", "file_name": "x.g", "pole_switch_rows": [{"status": "FAIL"}]}],
            "pole-switch-table",
        ),
        (
            _export_fuse_html_bundle,
            [{"report_type": "FUSE", "file_name": "x.g", "fuse_rows": [{"status": "FAIL"}]}],
            "fuse-table",
        ),
        (
            _export_master_station_html_bundle,
            [{"report_type": "MASTER_STATION", "file_name": "x.g", "master_station_rows": [{"status": "FAIL"}]}],
            "master-station-table",
        ),
    ]
    for idx, (exporter, reports, table_id) in enumerate(cases):
        out = tmp_path / f"report-{idx}.html"
        exporter(reports, out, {}, language="zh_CN")
        html = out.read_text(encoding="utf-8")
        _assert_filter_runtime(html, table_id)
