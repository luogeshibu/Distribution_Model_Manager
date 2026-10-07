from __future__ import annotations

from pathlib import Path

from dmm.domain.graphics_cleanup.whole_graph_topology import analyze_whole_graph_topology_file


def test_label_only_source_is_unique_per_nop_side_and_duplicate_is_suppressed(tmp_path):
    source = tmp_path / "unique-source.g"
    source.write_text(
        """<G><Layer>
<FeedLine id="left" x="0" y="100" w="100" h="6" d="0,103 100,103" link="1,0,nop"/>
<Text id="left_name" x="-90" y="45" w="120" h="35" ts="TRUB-BH09" lc="255,255,255"/>
<CBreakerDis id="nop" x="100" y="83" w="40" h="40" node_area="0,0,left;1,0,right"/>
<Text id="nop_text" x="105" y="125" w="70" h="35" ts="NOP" lc="255,20,10" lcc="#ff140a"/>
<FeedLine id="right" x="140" y="100" w="160" h="6" d="140,103 300,103" link="0,0,nop"/>
<Text id="right_name" x="185" y="45" w="130" h="35" ts="TRUB-BH21" lc="255,255,255"/>
<!-- duplicate display name elsewhere: it must not become a second source -->
<FeedLine id="island" x="500" y="500" w="120" h="6" d="500,503 620,503"/>
<Text id="dup_name" x="500" y="445" w="130" h="35" ts="TRUB-BH21" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )
    analysis = analyze_whole_graph_topology_file(source)
    anchors = [(x["feeder_label"], x["node_xml_id"]) for x in analysis["anchor_rows"]]
    assert ("TRUB-BH09", "left") in anchors
    assert ("TRUB-BH21", "right") in anchors
    assert ("TRUB-BH21", "island") not in anchors
    rows = analysis["source_validation_rows"]
    dup = next(x for x in rows if x.get("text_xml_id") == "dup_name")
    assert dup["status"] == "SOURCE_REJECTED_DUPLICATE_NAME"


def test_midline_feeder_like_text_is_not_a_source(tmp_path):
    source = tmp_path / "midline.g"
    source.write_text(
        """<G><Layer>
<FeedLine id="a" x="0" y="100" w="100" h="6" d="0,103 100,103" link="1,0,b"/>
<FeedLine id="b" x="100" y="100" w="100" h="6" d="100,103 200,103" link="0,0,a;1,0,c"/>
<FeedLine id="c" x="200" y="100" w="100" h="6" d="200,103 300,103" link="0,0,b"/>
<Text id="mid_name" x="115" y="45" w="150" h="35" ts="TRUB-BH21" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )
    analysis = analyze_whole_graph_topology_file(source)
    assert not analysis["anchor_rows"]
    row = next(x for x in analysis["source_validation_rows"] if x.get("text_xml_id") == "mid_name")
    assert row["status"] == "SOURCE_REJECTED_NOT_TERMINAL"


def test_one_source_free_component_cannot_have_two_different_terminal_names(tmp_path):
    source = tmp_path / "two-names.g"
    source.write_text(
        """<G><Layer>
<FeedLine id="a" x="0" y="100" w="100" h="6" d="0,103 100,103" link="1,0,b"/>
<FeedLine id="b" x="100" y="100" w="100" h="6" d="100,103 200,103" link="0,0,a;1,0,c"/>
<FeedLine id="c" x="200" y="100" w="100" h="6" d="200,103 300,103" link="0,0,b"/>
<Text id="name_a" x="-60" y="45" w="120" h="35" ts="TRUB-BH21" lc="255,255,255"/>
<Text id="name_c" x="270" y="45" w="120" h="35" ts="TRUB-BH22" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )
    analysis = analyze_whole_graph_topology_file(source)
    assert not analysis["anchor_rows"]
    errors = [x for x in analysis["source_validation_rows"] if x["status"] == "SOURCE_COMPONENT_MULTIPLE_NAMES_ERROR"]
    assert len(errors) == 2


def test_nop_side_with_multiple_source_names_is_reported_as_error(tmp_path):
    source = tmp_path / "nop-multi.g"
    source.write_text(
        """<G><Layer>
<FeedLine id="left" x="0" y="100" w="100" h="6" d="0,103 100,103" link="1,0,nop"/>
<Text id="left_name" x="-90" y="45" w="120" h="35" ts="TRUB-BH09" lc="255,255,255"/>
<CBreakerDis id="nop" x="100" y="83" w="40" h="40" node_area="0,0,left;1,0,right"/>
<Text id="nop_text" x="105" y="125" w="70" h="35" ts="NOP" lc="255,20,10" lcc="#ff140a"/>
<FeedLine id="right" x="140" y="100" w="160" h="6" d="140,103 300,103" link="0,0,nop"/>
<Text id="right_name" x="185" y="45" w="130" h="35" ts="TRUB-BH21" lc="255,255,255"/>
</Layer></G>""",
        encoding="utf-8",
    )
    analysis = analyze_whole_graph_topology_file(source)
    nop = analysis["nop_rows"][0]
    assert nop["boundary_status"] == "CONFIRMED_TWO_SIDES"
    assert "LEFT=TRUB-BH09(CONFIRMED)" in nop["source_side_summary"]
    assert "RIGHT=TRUB-BH21(CONFIRMED)" in nop["source_side_summary"]
