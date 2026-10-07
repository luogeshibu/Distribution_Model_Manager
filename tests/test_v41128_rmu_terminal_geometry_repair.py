from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_feeder_topology import analyze_rmu_feeder_topology_file
from dmm.domain.graphics_cleanup.whole_graph_topology import analyze_whole_graph_topology_file


def _write_9002_like_fixture(path: Path) -> None:
    path.write_text(
        """<G><Layer>
<!-- Main feeder MKN-AH341 -->
<Rect id="bay_mkn" x="0" y="0" w="220" h="220"/>
<CBreaker id="cb_mkn" x="80" y="120" w="40" h="40" link="0,0,fl_mkn"/>
<Text id="title_mkn" x="35" y="-45" w="160" h="30" ts="MKN-AH341" lc="255,255,255"/>
<FeedLine id="fl_mkn" x="100" y="154" w="440" h="6" d="100,154 540,154" link="0,0,cb_mkn"/>

<!-- Main feeder TNM-AH324 -->
<Rect id="bay_tnm" x="900" y="0" w="220" h="220"/>
<CBreaker id="cb_tnm" x="980" y="120" w="40" h="40" link="0,0,fl_tnm"/>
<Text id="title_tnm" x="935" y="-45" w="160" h="30" ts="TNM-AH324" lc="255,255,255"/>
<FeedLine id="fl_tnm" x="680" y="154" w="320" h="6" d="1000,154 680,154" link="0,0,cb_tnm"/>

<!-- RMU 9002.  Deliberately omit link/node_area on all RMU objects and
     internal lines.  The drawing is electrically connected by geometry only,
     matching the field export defect fixed in v4.1.128. -->
<rect id="rmu_frame" x="500" y="100" w="220" h="220"/>
<CBreakerDis id="y1" x="520" y="150" w="40" h="40" p_NameString="Y1"/>
<CBreakerDis id="y2" x="660" y="150" w="40" h="40" p_NameString="Y2"/>
<CBreakerDis id="q1" x="603" y="250" w="34" h="38" p_NameString="Q1"/>
<BusDis id="bus" x="535" y="220" w="160" h="6"/>
<ZhaiWaiJieDiDaoZha id="gd" x="610" y="195" w="20" h="20"/>

<ConnectLine id="cl_y1_bus" x="537" y="186" w="6" h="40" d="540,186 540,223"/>
<ConnectLine id="cl_y2_bus" x="677" y="186" w="6" h="40" d="680,186 680,223"/>
<ConnectLine id="cl_q1_bus" x="617" y="223" w="6" h="31" d="620,223 620,254"/>

<Text id="rmu_name" x="730" y="210" w="80" h="35" ts="9002" lc="255,255,255"/>
<Text id="nop" x="430" y="150" w="80" h="35" ts="N.O.P" lc="255,0,0" lcc="#ff0000"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_rmu_analyzer_repairs_geometry_and_resolves_9002_owner(tmp_path: Path):
    source = tmp_path / "9002.g"
    _write_9002_like_fixture(source)
    analysis = analyze_rmu_feeder_topology_file(source)

    rmu = next(row for row in analysis["rmu_rows"] if row["rmu_name"] == "9002")
    assert rmu["primary_feeder"] == "TNM-AH324"
    assert rmu["ownership_status"] == "RESOLVED_BY_NON_NOP_PORTS"
    assert rmu["stopped_feeders"] == "MKN-AH341"
    assert rmu["nop_ports"] == "Y1"

    ports = {row["port_name"]: row for row in analysis["port_rows"] if row["rmu_name"] == "9002"}
    assert ports["Y1"]["ownership_role"] == "NOP_STOP_BOUNDARY"
    assert ports["Y2"]["feeder_labels"] == "TNM-AH324"
    assert ports["Q1"]["feeder_labels"] == "TNM-AH324"
    assert analysis["summary"]["rmu_terminal_geometry_repair_count"] >= 5


def test_whole_graph_uses_same_strict_rmu_terminal_repair(tmp_path: Path):
    source = tmp_path / "9002.g"
    _write_9002_like_fixture(source)
    analysis = analyze_whole_graph_topology_file(source)

    rmu = next(row for row in analysis["rmu_rows"] if row["rmu_name"] == "9002")
    assert rmu["status"] == "CONFIRMED"
    assert rmu["primary_feeder"] == "TNM-AH324"
    assert analysis["summary"]["rmu_terminal_geometry_repair_count"] >= 5


def test_terminal_repair_does_not_connect_line_ending_deep_inside_symbol(tmp_path: Path):
    # Endpoint in the middle of the Y1 box is intentionally not a valid terminal.
    source = tmp_path / "deep.g"
    source.write_text(
        """<G><Layer>
<rect id="rmu_frame" x="500" y="100" w="220" h="220"/>
<CBreakerDis id="y1" x="520" y="150" w="40" h="40" p_NameString="Y1"/>
<BusDis id="bus" x="535" y="220" w="160" h="6"/>
<ZhaiWaiJieDiDaoZha id="gd" x="610" y="195" w="20" h="20"/>
<FeedLine id="fl" x="0" y="167" w="540" h="6" d="0,170 540,170"/>
<Text id="name" x="730" y="210" w="80" h="35" ts="9002" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )
    analysis = analyze_rmu_feeder_topology_file(source)
    repairs = analysis["terminal_repair_rows"]
    assert not any(row["line_xml_id"] == "fl" and row["target_xml_id"] == "y1" for row in repairs)
