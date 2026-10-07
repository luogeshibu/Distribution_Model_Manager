from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.graphics_cleanup.whole_graph_topology import (
    process_whole_graph_topology_analysis,
)


def _write_gap_fixture(path: Path):
    path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
<FeedLine id="fl_anchor" x="0" y="97" w="100" h="6" d="0,100 100,100"/>
<Text id="feeder" x="10" y="45" w="120" h="30" ts="TURB-BH-04" lc="255,255,255"/>
<FeedLine id="fl_island" x="101" y="100" w="99" h="6" d="101,103 200,103"/>
</Layer></G>""",
        encoding="utf-8",
    )


def test_whole_graph_auto_repairs_unique_small_endpoint_gap_and_outputs_before_after(tmp_path):
    source = tmp_path / "gap.sln.pic.g"
    _write_gap_fixture(source)
    original = source.read_bytes()

    result = process_whole_graph_topology_analysis([source], tmp_path / "report")

    assert source.read_bytes() == original  # original is never overwritten
    assert result.repair_applied_count == 1
    assert result.before_topology_error_count == 1
    assert result.after_topology_error_count == 0
    assert result.fixed_g_path is not None and result.fixed_g_path.exists()
    assert result.before_svg_path.exists()
    assert result.after_svg_path.exists()
    assert result.repair_csv_path.exists()

    html = result.html_path.read_text(encoding="utf-8")
    assert "修复前拓扑图" in html
    assert "修复后拓扑图" in html
    assert "AUTO_FIXED" in html
    assert result.before_svg_path.name in html
    assert result.after_svg_path.name in html
    assert result.fixed_g_path.name in html

    root = ET.parse(result.fixed_g_path).getroot()
    by_id = {elem.get("id"): elem for elem in root.iter() if elem.get("id")}
    assert "fl_island" in (by_id["fl_anchor"].get("link") or "")
    assert "fl_anchor" in (by_id["fl_island"].get("link") or "")
    assert "fl_island" in (by_id["fl_anchor"].get("node_area") or "")
    assert "fl_anchor" in (by_id["fl_island"].get("node_area") or "")


def test_version_is_41132():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.135"' in constants
