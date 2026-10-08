from pathlib import Path

import dmm.domain.graphics_cleanup.whole_graph_topology as whole
from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    _new_makkah_parser,
    _objects_inside_frame,
)


def test_indexed_display_name_matches_legacy_scan(tmp_path: Path):
    g = tmp_path / "mini.sln.pic.g"
    g.write_text(
        '<D5000><Layer>'
        '<FeedLine id="10" x="100" y="100" w="10" h="30" />'
        '<Text id="20" x="115" y="100" w="30" h="12" ts="AH303" />'
        '<Text id="21" x="500" y="500" w="30" h="12" ts="FAR" />'
        '</Layer></D5000>', encoding="utf-8"
    )
    parser = _new_makkah_parser()
    parsed = parser.parse(g)
    obj = next(o for o in parsed.objects if o.xml_id == "10")
    legacy = whole._display_name_for_network_object(obj, parsed)
    index = whole._build_display_text_spatial_index(parsed)
    indexed = whole._display_name_for_network_object(obj, parsed, index)
    assert indexed == legacy == "AH303"


def test_frame_spatial_index_matches_naive_center_contains(tmp_path: Path):
    g = tmp_path / "frame.sln.pic.g"
    g.write_text(
        '<D5000><Layer>'
        '<rect id="1" x="100" y="100" w="300" h="200" />'
        '<CBreakerDis id="2" x="150" y="150" w="20" h="20" p_NameString="Y1" />'
        '<BusDis id="3" x="220" y="150" w="20" h="20" />'
        '<Text id="4" x="900" y="900" w="20" h="10" ts="OUT" />'
        '</Layer></D5000>', encoding="utf-8"
    )
    parser = _new_makkah_parser()
    parsed = parser.parse(g)
    frame_obj = next(o for o in parsed.objects if o.xml_id == "1")
    from dmm.domain.graphics_cleanup.makkah_parser import RmuFrame
    frame = RmuFrame(frame=frame_obj)
    indexed = _objects_inside_frame(parsed, frame)
    naive = [
        o for o in parsed.objects
        if o is not frame_obj and frame_obj.box.center_contains(o.box, tolerance=1.0)
    ]
    assert [o.xml_index for o in indexed] == [o.xml_index for o in naive]
