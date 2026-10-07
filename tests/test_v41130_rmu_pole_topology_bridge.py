from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_feeder_topology import analyze_rmu_feeder_topology_file


def _write_fixture(path: Path) -> None:
    path.write_text(
        """<G><Layer>
<!-- MKN feeder enters 9002 at Y1, which is the red NOP boundary. -->
<Rect id="bay_mkn" x="0" y="0" w="220" h="220"/>
<CBreaker id="cb_mkn" x="80" y="120" w="40" h="40" node_area="0,0,fl_mkn"/>
<Text id="title_mkn" x="35" y="-45" w="160" h="30" ts="MKN-AH341" lc="255,255,255"/>
<FeedLine id="fl_mkn" x="100" y="154" w="440" h="6" d="100,154 540,154" node_area="0,0,cb_mkn;1,0,y1"/>

<!-- TNM feeder reaches 9002.Y2 through two Pole junctions.  Without Pole in
     the RMU topology graph this explicit chain is broken. -->
<Rect id="bay_tnm" x="1200" y="0" w="220" h="220"/>
<CBreaker id="cb_tnm" x="1280" y="120" w="40" h="40" node_area="0,0,fl_tnm_a"/>
<Text id="title_tnm" x="1235" y="-45" w="160" h="30" ts="TNM-AH324" lc="255,255,255"/>
<FeedLine id="fl_tnm_a" x="1300" y="154" w="6" h="246" d="1300,154 1300,400" node_area="0,0,cb_tnm;1,0,pole1"/>
<Pole id="pole1" x="1280" y="380" w="40" h="40" node_area="0,0,fl_tnm_a;1,0,fl_tnm_b" devref="#pole.gt.icn.g:pole"/>
<FeedLine id="fl_tnm_b" x="1300" y="420" w="6" h="260" d="1300,420 1300,680" node_area="0,0,pole1;1,0,pole2"/>
<Pole id="pole2" x="1280" y="660" w="40" h="40" node_area="0,0,fl_tnm_b;1,0,fl_tnm_c" devref="#pole.gt.icn.g:pole"/>
<FeedLine id="fl_tnm_c" x="680" y="680" w="620" h="6" d="1300,680 680,680" node_area="0,0,pole2;1,0,y2"/>

<rect id="rmu_frame" x="500" y="100" w="220" h="220"/>
<CBreakerDis id="y1" x="520" y="150" w="40" h="40" p_NameString="Y1" node_area="0,0,fl_mkn;1,0,bus"/>
<CBreakerDis id="y2" x="660" y="150" w="40" h="40" p_NameString="Y2" node_area="0,0,fl_tnm_c;1,0,bus"/>
<CBreakerDis id="q1" x="603" y="250" w="34" h="38" p_NameString="Q1" node_area="0,0,bus"/>
<BusDis id="bus" x="535" y="220" w="160" h="6" node_area="0,0,y1;1,0,y2;2,0,q1"/>
<ZhaiWaiJieDiDaoZha id="gd" x="610" y="195" w="20" h="20"/>
<Text id="rmu_name" x="730" y="210" w="80" h="35" ts="9002" lc="255,255,255"/>
<Text id="nop" x="430" y="150" w="80" h="35" ts="N.O.P" lc="255,43,5" lcc="#ff2b05"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_rmu_topology_propagates_through_explicit_pole_chain(tmp_path: Path):
    source = tmp_path / "pole_chain_9002.g"
    _write_fixture(source)

    analysis = analyze_rmu_feeder_topology_file(source)

    sources = {row["feeder_label"]: row for row in analysis["source_rows"]}
    assert sources["MKN-AH341"]["candidate_status"] == "ENTRY_BRANCH_STOPPED_AT_NOP"
    assert sources["TNM-AH324"]["candidate_status"] == "PROPAGATE"
    assert sources["TNM-AH324"]["first_rmu_name"] == "9002"
    assert sources["TNM-AH324"]["entry_port_name"] == "Y2"

    rmu = next(row for row in analysis["rmu_rows"] if row["rmu_name"] == "9002")
    assert rmu["status"] == "NOP_BOUNDARY"
    assert rmu["ownership_status"] == "RESOLVED_BY_NON_NOP_PORTS"
    assert rmu["primary_feeder"] == "TNM-AH324"
    assert rmu["stopped_feeders"] == "MKN-AH341"
    assert rmu["unresolved_port_count"] == 0

    ports = {row["port_name"]: row for row in analysis["port_rows"] if row["rmu_name"] == "9002"}
    assert ports["Y2"]["feeder_labels"] == "TNM-AH324"
    assert ports["Q1"]["feeder_labels"] == "TNM-AH324"


def test_version_is_41130():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
