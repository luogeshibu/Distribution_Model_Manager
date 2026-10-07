from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    NOP_HORIZONTAL_POSITIONS,
    RMU_NAME_POSITIONS,
    _new_makkah_parser,
    process_rmu_annotation_reposition,
    reposition_rmu_annotations,
)

ROOT = Path(__file__).resolve().parents[1]


def _sample_xml():
    return '''<G><Layer>
<rect id="rmu1" x="100" y="100" w="400" h="300" />
<BusDis id="bus1" x="170" y="210" w="250" h="8" d="170,214 420,214" />
<CBreakerDis id="y1" x="170" y="140" w="40" h="40" p_NameString="Y1" />
<CBreakerDis id="y2" x="170" y="220" w="40" h="40" p_NameString="Y2" />
<CBreakerDis id="y3" x="330" y="140" w="40" h="40" p_NameString="Y3" />
<CBreakerDis id="q1" x="330" y="260" w="40" h="40" p_NameString="Q1" />
<ZhaiWaiJieDiDaoZha id="ground1" x="260" y="180" w="30" h="30" />
<Text id="ty1" x="120" y="145" w="40" h="20" ts="Y1" />
<Text id="ty2" x="120" y="225" w="40" h="20" ts="Y2" />
<Text id="ty3" x="390" y="145" w="40" h="20" ts="Y3" />
<Text id="tq1" x="390" y="265" w="40" h="20" ts="Q1" />
<Text id="smart" x="250" y="110" w="80" h="20" ts="SMART" />
<Text id="nop1" x="540" y="270" w="60" h="20" ts="N.O.P" lc="255,0,0" />
<Text id="name1" x="540" y="310" w="80" h="20" ts="40376" lc="255,0,0" />
</Layer></G>'''


def _write_sample(path: Path):
    path.write_text(_sample_xml(), encoding="utf-8")


def test_nop_positions_are_horizontal_only_and_name_has_four_edge_centers():
    assert list(NOP_HORIZONTAL_POSITIONS) == ["auto", "left", "right"]
    assert list(RMU_NAME_POSITIONS) == ["top", "right", "bottom", "left"]


def test_nop_center_y_aligns_with_corresponding_q_switch(tmp_path):
    source = tmp_path / "sample.g"
    _write_sample(source)
    parser = _new_makkah_parser()
    parsed = parser.parse(source)

    counts = reposition_rmu_annotations(
        parsed,
        nop_position="right",
        rmu_name_position="top",
        nop_margin=10,
        rmu_name_margin=10,
    )
    assert counts["rmu_count"] == 1
    assert counts["nop_found"] == 1
    assert counts["nop_moved"] == 1
    assert counts["nop_unmatched_device"] == 0
    assert counts["rmu_name_found"] == 1
    assert counts["rmu_name_moved"] == 1

    layer = parsed.root.find("Layer")
    nop = next(e for e in layer if e.get("id") == "nop1")
    q1 = next(e for e in layer if e.get("id") == "q1")
    name = next(e for e in layer if e.get("id") == "name1")

    nop_center_y = float(nop.get("y")) + float(nop.get("h")) / 2.0
    q1_center_y = float(q1.get("y")) + float(q1.get("h")) / 2.0
    assert nop_center_y == q1_center_y
    assert float(nop.get("x")) == 510.0  # frame right 500 + 10 px

    # RMU name is centered on the top edge, outside the frame by the margin.
    assert float(name.get("x")) == 260.0
    assert float(name.get("y")) == 70.0


def test_auto_nop_keeps_existing_right_side_but_still_aligns_to_switch(tmp_path):
    source = tmp_path / "sample.g"
    _write_sample(source)
    parser = _new_makkah_parser()
    parsed = parser.parse(source)
    reposition_rmu_annotations(parsed, nop_position="auto", rmu_name_position="right")
    layer = parsed.root.find("Layer")
    nop = next(e for e in layer if e.get("id") == "nop1")
    q1 = next(e for e in layer if e.get("id") == "q1")
    assert float(nop.get("x")) >= 500.0
    assert float(nop.get("y")) + 10.0 == float(q1.get("y")) + 20.0


def test_process_keeps_source_read_only_and_writes_safe_copy(tmp_path):
    source = tmp_path / "sample.g"
    _write_sample(source)
    before = source.read_bytes()
    result = process_rmu_annotation_reposition(
        [source],
        tmp_path / "out",
        tmp_path / "report",
        nop_position="left",
        rmu_name_position="bottom",
        nop_margin=7,
        rmu_name_margin=9,
    )
    assert source.read_bytes() == before
    assert result.nop_found == 1
    assert result.nop_moved == 1
    assert result.rmu_name_found == 1
    assert result.output_files[0].exists()
    assert result.csv_path.exists()
    assert result.html_path.exists()


def test_graphics_workspace_exposes_nop_and_rmu_name_position_operation():
    source = (ROOT / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert '"NOP / 环网柜名称位置调整", "RMU_ANNOTATION_REPOSITION"' in source
    assert "NOP 中心 Y = 开关中心 Y" in source
    assert "Y1/Y2/Y3/Q1/Q2/Q3" in source
