from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.whole_graph_topology import (
    analyze_whole_graph_topology_file,
    process_whole_graph_topology_analysis,
)


def _write_single_feeder_rmu(path: Path):
    path.write_text(
        """<G><Layer>
<FeedLine id="fl" x="0" y="100" w="180" h="6" d="0,103 180,103" link="1,0,y1"/>
<Text id="feeder" x="30" y="60" w="100" h="25" ts="TURB-BH-04" lc="255,255,255"/>
<rect id="frame" x="190" y="30" w="220" h="220"/>
<CBreakerDis id="y1" x="205" y="90" w="25" h="25" p_NameString="Y1" link="0,0,fl;1,0,bus"/>
<CBreakerDis id="y2" x="300" y="90" w="25" h="25" p_NameString="Y2" link="0,0,bus"/>
<BusDis id="bus" x="245" y="120" w="120" h="10" link="0,0,y1;1,0,y2;2,0,gd"/>
<ZhaiWaiJieDiDaoZha id="gd" x="260" y="150" w="25" h="25" link="0,0,bus"/>
<Text id="rmu_name" x="420" y="100" w="70" h="30" ts="12345" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )


def _write_multi_feeder_rmu(path: Path):
    path.write_text(
        """<G><Layer>
<FeedLine id="fl1" x="0" y="100" w="180" h="6" d="0,103 180,103" link="1,0,y1"/>
<Text id="f1" x="20" y="60" w="100" h="25" ts="TURB-BH-04" lc="255,255,255"/>
<rect id="frame" x="190" y="30" w="220" h="220"/>
<CBreakerDis id="y1" x="205" y="90" w="25" h="25" p_NameString="Y1" link="0,0,fl1;1,0,bus"/>
<CBreakerDis id="y2" x="370" y="90" w="25" h="25" p_NameString="Y2" link="0,0,bus;1,0,fl2"/>
<BusDis id="bus" x="245" y="120" w="120" h="10" link="0,0,y1;1,0,y2;2,0,gd"/>
<ZhaiWaiJieDiDaoZha id="gd" x="260" y="150" w="25" h="25" link="0,0,bus"/>
<Text id="rmu_name" x="420" y="160" w="70" h="30" ts="12345" lc="255,255,255"/>
<FeedLine id="fl2" x="400" y="100" w="180" h="6" d="400,103 580,103" link="0,0,y2"/>
<Text id="f2" x="470" y="60" w="90" h="25" ts="TRUB-BH20" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_whole_graph_rmu_has_one_owner_from_non_nop_ports(tmp_path):
    source = tmp_path / "single.g"
    _write_single_feeder_rmu(source)
    analysis = analyze_whole_graph_topology_file(source)
    assert analysis["summary"]["topology_error_count"] == 0
    assert analysis["summary"]["rmu_confirmed_count"] == 1
    rmu = analysis["rmu_rows"][0]
    assert rmu["status"] == "CONFIRMED"
    assert rmu["primary_feeder"] == "TURB-BH-04"
    assert "Y1=TURB-BH-04" in rmu["non_nop_port_feeders"]
    assert "Y2=TURB-BH-04" in rmu["non_nop_port_feeders"]


def test_two_source_names_in_one_source_end_are_blocked_before_propagation(tmp_path):
    source = tmp_path / "multi.g"
    _write_multi_feeder_rmu(source)
    analysis = analyze_whole_graph_topology_file(source)

    # v4.1.134 hardens the earlier device-level MULTI_FEEDER check: two
    # different text-only main-station names in the same non-NOP source region
    # are rejected before either name is allowed to seed propagation.
    assert analysis["summary"]["source_error_count"] == 2
    assert analysis["summary"]["anchor_count"] == 0
    assert analysis["summary"]["multi_feeder_error_count"] == 0
    assert analysis["summary"]["no_feeder_error_count"] > 0
    source_errors = [
        row for row in analysis["source_validation_rows"]
        if row["status"] == "SOURCE_COMPONENT_MULTIPLE_NAMES_ERROR"
    ]
    assert {row["feeder_label"] for row in source_errors} == {"TURB-BH-04", "TRUB-BH20"}

    rmu = analysis["rmu_rows"][0]
    assert rmu["status"] == "ERROR"
    assert rmu["error_type"] == "NO_FEEDER_ERROR"
    assert rmu["primary_feeder"] == ""


def test_non_nop_without_feeder_is_reported_as_nop_topology_error(tmp_path):
    source = tmp_path / "none.g"
    source.write_text(
        """<G><Layer>
<FeedLine id="isolated" x="0" y="100" w="100" h="6" d="0,103 100,103"/>
</Layer></G>""",
        encoding="utf-8",
    )
    analysis = analyze_whole_graph_topology_file(source)
    row = analysis["device_rows"][0]
    assert row["status"] == "ERROR"
    assert row["error_type"] == "NO_FEEDER_ERROR"
    assert "NOP" in row["reason"]


def test_html_has_dedicated_rmu_and_error_tables(tmp_path):
    source = tmp_path / "single.g"
    _write_single_feeder_rmu(source)
    result = process_whole_graph_topology_analysis([source], tmp_path / "report")
    html = result.html_path.read_text(encoding="utf-8")
    assert "RMU 所属馈线（按非NOP Y/Q开关唯一一致性判断）" in html
    assert "拓扑异常设备（非NOP设备必须且只能有一个所属馈线）" in html
    assert "whole_graph_rmu_feeders.csv" not in html  # separate artifact, not a UI dependency
    assert result.rmu_csv_path.exists()
