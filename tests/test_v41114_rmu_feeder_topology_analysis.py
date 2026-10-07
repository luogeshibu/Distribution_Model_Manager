from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser
from dmm.domain.graphics_cleanup.rmu_feeder_topology import (
    _exact_nop_boundaries,
    _rmu_name_map,
    process_rmu_feeder_topology_analysis,
)


def _write_nop_fixture(path: Path):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    ET.SubElement(layer, "Rect", id="2001", x="100", y="100", w="240", h="260")
    # Two right-side Y switches close enough that old +20G nearest-distance
    # logic could cut both; the NOP center-Y is exactly aligned to Y2 only.
    ET.SubElement(layer, "CBreakerDis", id="3101", x="260", y="150", w="30", h="30", p_NameString="Y1")
    ET.SubElement(layer, "CBreakerDis", id="3102", x="260", y="230", w="30", h="30", p_NameString="Y2")
    ET.SubElement(layer, "ZhaiWaiJieDiDaoZha", id="3201", x="180", y="180", w="20", h="20")
    ET.SubElement(layer, "BusDis", id="3301", x="150", y="300", w="120", h="10")
    ET.SubElement(layer, "Text", id="8001", x="370", y="170", w="100", h="50", ts="30038", lc="255,255,255", lcc="#ffffff")
    # center Y = 245, exactly matching Y2 (230+15)
    ET.SubElement(layer, "Text", id="8002", x="370", y="220", w="100", h="50", ts="N.O.P", lc="255,0,0", lcc="#ff0000")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def test_nop_boundary_chooses_one_yq_switch_by_center_y(tmp_path):
    source = tmp_path / "nop.g"
    _write_nop_fixture(source)
    parser = _new_makkah_parser()
    parsed = parser.parse(source)
    frames = list(parser.find_rmu_frames(parsed))
    names = _rmu_name_map(parser, parsed, frames)
    boundary_nodes, rows = _exact_nop_boundaries(parser, parsed, frames, names)

    assert boundary_nodes == {"3102"}
    assert len(rows) == 1
    assert rows[0]["switch_name"] == "Y2"
    assert rows[0]["y_delta"] == 0.0


def test_analysis_is_read_only_and_writes_reports(tmp_path):
    source = tmp_path / "nop.g"
    _write_nop_fixture(source)
    before = source.read_bytes()

    result = process_rmu_feeder_topology_analysis(
        [source], tmp_path / "report"
    )

    assert source.read_bytes() == before
    assert result.html_path.exists()
    assert result.rmu_csv_path.exists()
    assert result.port_csv_path.exists()
    html = result.html_path.read_text(encoding="utf-8")
    assert "环网柜馈线拓扑分析报告" in html
    assert "NOP所属RMU / 开关汇总" in html
    assert "RMU端口拓扑证据" in html


def test_ui_registers_rmu_feeder_topology_module():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.graphics_operation_combo.addItem("环网柜馈线拓扑分析", "RMU_FEEDER_TOPOLOGY")' in source
    assert "def _build_rmu_feeder_topology_panel" in source
    assert "def start_rmu_feeder_topology_analysis" in source
    assert "只判断环网柜 RMU 的所属馈线" in source
    assert "不输出 FeedLine 业务归属" in source


def test_version_is_41120():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
