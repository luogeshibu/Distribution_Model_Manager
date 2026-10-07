from __future__ import annotations

from pathlib import Path

import pytest

from dmm.domain.graphics_cleanup.whole_graph_topology import (
    analyze_whole_graph_topology_file,
    process_whole_graph_topology_analysis,
)


def _write_fixture(path: Path):
    path.write_text(
        """<G><Layer>
<FeedLine id="fl_left" x="0" y="100" w="100" h="6" d="0,103 100,103" link="1,0,nop_sw"/>
<Text id="feeder_left" x="-80" y="45" w="80" h="40" ts="TURB-BH-04" lc="255,255,255"/>
<CBreakerDis id="nop_sw" x="100" y="83" w="40" h="40" node_area="0,0,fl_left;1,0,fl_right" devref="#Load_Breaker_Switch_SMART.zwk.icn.g:Load_Breaker_Switch_SMART"/>
<Text id="switch_name" x="75" y="30" w="190" h="40" ts="SLBS-2002" lc="255,255,255"/>
<Text id="nop_text" x="105" y="130" w="90" h="40" ts="NOP" lc="255,0,0" lcc="#ff0000"/>
<FeedLine id="fl_right" x="140" y="100" w="120" h="6" d="140,103 260,103" link="0,0,nop_sw;1,0,pole1"/>
<Pole id="pole1" x="250" y="83" w="40" h="40" node_area="0,0,fl_right;1,0,fl_tail" devref="#pole.gt.icn.g:pole"/>
<FeedLine id="fl_tail" x="290" y="100" w="160" h="6" d="290,103 450,103" link="0,0,pole1"/>
<Text id="feeder_right" x="330" y="45" w="110" h="40" ts="TRUB-AH309" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_whole_graph_line_labels_and_external_pole_nop(tmp_path):
    source = tmp_path / "whole.g"
    _write_fixture(source)
    analysis = analyze_whole_graph_topology_file(source)

    anchors = {(row["feeder_label"], row["node_xml_id"]) for row in analysis["anchor_rows"]}
    assert ("TURB-BH-04", "fl_left") in anchors
    assert ("TRUB-AH309", "fl_tail") in anchors
    assert all(row["feeder_label"] != "SLBS-2002" for row in analysis["anchor_rows"])

    nop = next(row for row in analysis["nop_rows"] if row["nop_text_xml_id"] == "nop_text")
    assert nop["nop_type"] == "POLE_NOP"
    assert nop["switch_xml_id"] == "nop_sw"
    assert "LEFT:TURB-BH-04" in nop["side_feeders"]
    assert "RIGHT:TRUB-AH309" in nop["side_feeders"]

    rows = {row["xml_id"]: row for row in analysis["device_rows"]}
    assert "nop_sw" not in rows  # NOP switch itself is a boundary, not feeder-owned.
    assert rows["fl_left"]["primary_feeder"] == "TURB-BH-04"
    assert rows["fl_right"]["primary_feeder"] == "TRUB-AH309"
    assert rows["pole1"]["primary_feeder"] == "TRUB-AH309"
    assert rows["fl_tail"]["primary_feeder"] == "TRUB-AH309"


def test_whole_graph_process_is_read_only_and_single_file_only(tmp_path):
    source = tmp_path / "whole.g"
    _write_fixture(source)
    before = source.read_bytes()
    result = process_whole_graph_topology_analysis([source], tmp_path / "report")
    assert source.read_bytes() == before
    assert result.html_path.exists()
    assert result.device_csv_path.exists()
    assert result.nop_csv_path.exists()
    assert result.anchor_csv_path.exists()
    assert result.rmu_csv_path.exists()
    html = result.html_path.read_text(encoding="utf-8")
    assert "RMU 所属馈线" in html
    assert "拓扑异常设备" in html
    assert result.pole_nop_count == 1

    second = tmp_path / "second.g"
    _write_fixture(second)
    with pytest.raises(ValueError, match="一次只处理 1 个 G 文件"):
        process_whole_graph_topology_analysis([source, second], tmp_path / "report2")


def test_ui_registers_new_whole_graph_topology_without_replacing_old_modules():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.graphics_operation_combo.addItem("环网柜馈线拓扑分析", "RMU_FEEDER_TOPOLOGY")' in source
    assert 'self.graphics_operation_combo.addItem("馈线段所属馈线分析", "FEEDLINE_FEEDER_TOPOLOGY")' in source
    assert 'self.graphics_operation_combo.addItem("整图馈线拓扑分析", "WHOLE_GRAPH_TOPOLOGY")' in source
    assert "def _build_whole_graph_topology_panel" in source
    assert "def start_whole_graph_topology_analysis" in source


def test_version_is_41127():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
