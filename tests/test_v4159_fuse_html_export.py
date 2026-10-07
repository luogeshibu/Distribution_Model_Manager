from pathlib import Path

from dmm.infrastructure.reporting.writer import _export_fuse_html_bundle


def test_fuse_html_export_has_table_interaction_script(tmp_path: Path):
    out = tmp_path / "fuse.html"
    _export_fuse_html_bundle([], out, {}, language="zh_CN")
    text = out.read_text(encoding="utf-8")
    assert "function toggleSelectedRow" in text
    assert "function filterReportTable" in text
    assert "fuse-table" in text
