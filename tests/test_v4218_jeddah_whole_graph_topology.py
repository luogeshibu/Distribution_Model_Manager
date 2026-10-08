from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.whole_graph_topology import analyze_whole_graph_topology_file


def _write_jeddah_bus_and_red_background_nop_fixture(path: Path) -> None:
    path.write_text(
        """<G><Layer>
<Text id="bus_title" x="20" y="40" w="80" h="30" ts="AH303" lc="255,255,255"/>
<Bus id="main_bus" x="0" y="100" w="120" h="6" d="0,103 120,103" node_area="1,0,fl_left"/>
<FeedLine id="fl_left" x="120" y="100" w="100" h="6" d="120,103 220,103" link="0,0,main_bus;1,0,nop_sw"/>
<CBreakerDis id="nop_sw" x="220" y="83" w="40" h="40" node_area="0,0,fl_left;1,0,fl_right" devref="#Load_Breaker_Switch_SMART.zwk.icn.g:Load_Breaker_Switch_SMART"/>
<ellipse id="nop_bg" x="220" y="125" w="100" h="60" cx="269" cy="154" rx="49" ry="29" fc="255,0,0" fcc="#ff0000" lc="255,0,0" lcc="#ff0000"/>
<Text id="nop_text" x="230" y="135" w="73" h="32" ts="N.O.P" lc="255,255,255" lcc="#ffffff"/>
<FeedLine id="fl_right" x="260" y="100" w="180" h="6" d="260,103 440,103" link="0,0,nop_sw"/>
<Text id="right_title" x="330" y="45" w="100" h="30" ts="DHN-40" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_jeddah_no_frame_bus_title_is_authoritative_source(tmp_path):
    source = tmp_path / "jeddah.g"
    _write_jeddah_bus_and_red_background_nop_fixture(source)

    analysis = analyze_whole_graph_topology_file(source)
    source_row = next(row for row in analysis["source_rows"] if row["source_type"] == "MAIN_BUS_TEXT")
    assert source_row["status"] == "SOURCE_CONFIRMED"
    assert source_row["breaker_xml_id"] == "main_bus"
    assert source_row["feeder_label"] == "AH303"
    assert source_row["text_xml_id"] == "bus_title"

    anchor = next(row for row in analysis["anchor_rows"] if row["anchor_type"] == "MAIN_BUS_TEXT")
    assert anchor["node_xml_id"] == "main_bus"
    assert anchor["feeder_label"] == "AH303"


def test_jeddah_white_nop_text_on_red_ellipse_uses_makkah_boundary_logic(tmp_path):
    source = tmp_path / "jeddah.g"
    _write_jeddah_bus_and_red_background_nop_fixture(source)

    analysis = analyze_whole_graph_topology_file(source)
    nop = next(row for row in analysis["nop_rows"] if row["nop_text_xml_id"] == "nop_text")
    assert nop["switch_xml_id"] == "nop_sw"
    assert nop["status"] == "NOP_BOUNDARY"
    assert analysis["summary"]["nop_boundary_count"] == 1

    rows = {row["xml_id"]: row for row in analysis["device_rows"]}
    assert "nop_sw" not in rows
    assert rows["main_bus"]["primary_feeder"] == "AH303"
    assert rows["fl_left"]["primary_feeder"] == "AH303"
    assert rows["fl_right"]["primary_feeder"] == "DHN-40"


def test_graphics_workspace_registers_whole_graph_topology_page():
    source = Path("src/dmm/ui/graphics_workspace.py").read_text(encoding="utf-8")
    assert '("整图拓扑连接检查/修复", "whole_graph_topology", "g_file_studio.ui.pages.whole_graph_topology_page:WholeGraphTopologyPage")' in source


def test_jeddah_page_processor_uses_connectivity_only_engine():
    source = Path("src/g_file_studio/processors/whole_graph_topology_processor.py").read_text(encoding="utf-8")
    assert "repair_jeddah_topology_connectivity" in source
    assert "process_whole_graph_topology_analysis" not in source


def test_version_is_4219():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.2.23"' in constants
