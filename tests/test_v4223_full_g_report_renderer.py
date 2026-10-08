from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.graphics_cleanup.g_native_svg_renderer import render_g_root_to_svg
from dmm.domain.graphics_cleanup.jeddah_topology_connectivity import repair_jeddah_topology_connectivity


def _full_demo_g(path: Path) -> None:
    path.write_text(
        """<?xml version='1.0' encoding='utf-8'?>
<G id='root' x='0' y='0' w='500' h='400' width='500' height='400' bgc='0,0,0'>
 <Layer show='1'>
  <ConnectLine id='34000001' d='10,50 100,50' x='7' y='47' w='96' h='6' lc='85,170,255' lw='1'/>
  <rect id='2000001' x='120' y='80' w='150' h='160' lc='255,0,0' lw='1' ls='2' fm='0'/>
  <Text id='8000001' x='140' y='45' w='125' h='50' fs='50' ts='41973' lc='255,255,255' ff='Arial'/>
  <CBreakerDis id='117000001' x='140' y='130' w='28' h='30' rotate='270' lc='85,170,255' p_NameString='Y1' devref='#Load_Breaker_Switch_SMART.zwk.icn.g:Load_Breaker_Switch_SMART'/>
  <Status id='126000001' x='240' y='130' w='26' h='26' devref='#NariPd_Generator.zt.icn.g:NariPd_Generator'/>
  <image id='140000001' x='300' y='90' w='120' h='50' rotate='0' ahref='NOP.png'/>
  <poke id='170000001' x='300' y='170' w='120' h='40' ls='1' fm='1' lc='0,0,0' fc='100,100,100' ahref='OTHER.sln.pic.g'/>
 </Layer>
</G>""",
        encoding="utf-8",
    )


def test_native_renderer_uses_complete_g_geometry_and_visible_content(tmp_path: Path):
    source = tmp_path / "demo.sln.pic.g"
    _full_demo_g(source)
    root = ET.parse(source).getroot()
    output = tmp_path / "demo.svg"

    stats = render_g_root_to_svg(root, output)
    svg = output.read_text(encoding="utf-8")

    assert stats.canvas_width == 500
    assert stats.canvas_height == 400
    assert stats.visible_source_objects == 7
    assert stats.rendered_objects == 7
    # The report is an actual G redraw: source label, RMU frame, switch icon,
    # status icon, NOP image and visible poke rectangle all survive.
    assert "41973" in svg
    assert "N.O.P" in svg
    assert "CBreakerDis" in svg
    assert "Status" in svg
    assert "poke" in svg
    assert "x='120.000' y='80.000' width='150.000' height='160.000'" in svg
    assert "10.000,50.000 100.000,50.000" in svg


def test_repair_report_before_after_are_full_g_redraws_not_line_only(tmp_path: Path):
    source = tmp_path / "full-gap.sln.pic.g"
    source.write_text(
        "<G id='root' width='600' height='400'><Layer>"
        '<Text id="8000001" x="180" y="40" w="125" h="50" fs="50" ts="FULL-G-LABEL" lc="255,255,255" />'
        '<rect id="2000001" x="160" y="100" w="180" h="180" lc="255,0,0" lw="1" ls="2" fm="0" />'
        '<Status id="126000001" x="320" y="120" w="26" h="26" devref="#NariPd_Generator.zt.icn.g:NariPd_Generator" />'
        '<ConnectLine id="34000001" d="0,0 10,0" x="-3" y="-3" w="16" h="6" lc="85,170,255" lw="1" '
        'link="0,0,99000001" node_area="0,0,99000001" />'
        '<FeedLine id="117000001" d="20,0 30,0" x="17" y="-3" w="16" h="6" lc="85,170,255" lw="3" '
        'link="1,0,99000002" node_area="1,0,99000002" />'
        "</Layer></G>",
        encoding="utf-8",
    )

    result = repair_jeddah_topology_connectivity(source, tmp_path / "out")
    before = result.before_svg_path.read_text(encoding="utf-8")
    after = result.after_svg_path.read_text(encoding="utf-8")

    assert result.repair_count == 1
    for svg in (before, after):
        assert "FULL-G-LABEL" in svg
        assert "Status" in svg
        assert "2000001" in svg
    assert "#1 断点" in before
    assert "#1 已修复" in after
