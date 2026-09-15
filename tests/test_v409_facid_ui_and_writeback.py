
from pathlib import Path
from dmm.infrastructure.gfile.writeback import GWriteBackService

def test_root_facid_writeback_only_changes_root(tmp_path):
    p = tmp_path / "x.g"
    p.write_text(
        '<G facID=""><Layer><FeedLine id="1" facID="KEEP"/></Layer></G>',
        encoding="utf-8",
    )
    result = GWriteBackService().apply_root_g_attributes(
        p, {"facID": "12345"}, create_backup=False
    )
    text = p.read_text(encoding="utf-8")
    assert '<G facID="12345">' in text
    assert 'FeedLine id="1" facID="KEEP"' in text
    assert result["before"]["facID"] == ""

def test_local_facid_regex_fixed():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")
    assert r'<G\b[^>]*\bfacID="([^"]*)"' in source
    assert r'<G\\b[^>]*\\bfacID="([^"]*)"' not in source

def test_ui_keeps_sources_independent_and_exposes_explicit_override():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/ui/widgets/feeder_settings.py"
    ).read_text(encoding="utf-8")
    assert "允许覆盖现有 facID 和馈线段关联" in source
    assert "feeder_station_hint" in source
    assert "QMessageBox.information" not in source
    assert "禁止使用文件名或人工输入重新查询馈线" not in source

def test_execution_writes_root_facid_only_for_name_modes():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/feeder.py"
    ).read_text(encoding="utf-8")
    assert 'resolution_source in {"FILENAME", "MANUAL"}' in source
    assert "facid_writeback_by_file" in source
    assert "apply_root_g_attributes" in source
