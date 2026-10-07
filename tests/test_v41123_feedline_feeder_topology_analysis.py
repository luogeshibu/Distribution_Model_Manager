from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.feedline_feeder_topology import (
    analyze_feedline_feeder_topology_file,
    process_feedline_feeder_topology_analysis,
)


def _write_simple_feedline_fixture(path: Path):
    path.write_text(
        """<G><Layer>
<Rect id="bay1" x="100" y="100" w="220" h="220"/>
<CBreaker id="cb1" x="180" y="180" w="40" h="40" link="0,1,fl1"/>
<Text id="title1" x="150" y="55" w="130" h="30" ts="TEST-AH301" lc="255,0,0" lcc="#ff0000"/>
<FeedLine id="fl1" x="200" y="220" w="0" h="100" d="200,220 200,320" link="0,1,cb1;1,0,fl2"/>
<FeedLine id="fl2" x="200" y="320" w="120" h="0" d="200,320 320,320" link="0,1,fl1"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_feedline_analysis_resolves_single_source_without_touching_rmu_logic(tmp_path):
    source = tmp_path / "simple.g"
    _write_simple_feedline_fixture(source)
    analysis = analyze_feedline_feeder_topology_file(source)
    rows = {row["feedline_xml_id"]: row for row in analysis["feedline_rows"]}
    assert rows["fl1"]["status"] == "CONFIRMED"
    assert rows["fl1"]["primary_feeder"] == "TEST-AH301"
    assert rows["fl2"]["status"] == "CONFIRMED"
    assert rows["fl2"]["primary_feeder"] == "TEST-AH301"


def test_feedline_analysis_is_read_only_and_writes_own_reports(tmp_path):
    source = tmp_path / "simple.g"
    _write_simple_feedline_fixture(source)
    before = source.read_bytes()
    result = process_feedline_feeder_topology_analysis([source], tmp_path / "report")
    assert source.read_bytes() == before
    assert result.feedline_count == 2
    assert result.confirmed_count == 2
    assert result.html_path.exists()
    assert result.feedline_csv_path.exists()
    assert result.nop_csv_path.exists()
    html = result.html_path.read_text(encoding="utf-8")
    assert "馈线段所属馈线分析报告" in html
    assert "FeedLine所属馈线" in html
    assert "环网柜馈线拓扑分析" in html  # explicit statement that old module is not changed


def test_ui_registers_independent_feedline_topology_module():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.graphics_operation_combo.addItem("馈线段所属馈线分析", "FEEDLINE_FEEDER_TOPOLOGY")' in source
    assert "def _build_feedline_feeder_topology_panel" in source
    assert "def start_feedline_feeder_topology_analysis" in source
    assert "不修改已经验证通过的‘环网柜馈线拓扑分析’逻辑" in source


def test_rmu_topology_core_file_is_not_rewritten_by_new_module():
    source = Path("src/dmm/domain/graphics_cleanup/rmu_feeder_topology.py").read_text(encoding="utf-8")
    assert "本模块只判断RMU所属馈线" in source
    assert "FeedLine拓扑归属（审计）" not in source


def test_current_version_is_41124():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
