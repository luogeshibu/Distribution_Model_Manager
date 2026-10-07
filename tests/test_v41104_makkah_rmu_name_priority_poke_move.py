from pathlib import Path

from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    _new_makkah_parser,
    reposition_rmu_annotations,
)


def _base_devices():
    return '''
<rect id="rmu1" x="100" y="100" w="400" h="300" />
<BusDis id="bus1" x="170" y="210" w="250" h="8" d="170,214 420,214" />
<CBreakerDis id="y1" x="170" y="140" w="40" h="40" p_NameString="Y1" />
<ZhaiWaiJieDiDaoZha id="ground1" x="260" y="180" w="30" h="30" />
<Text id="ty1" x="120" y="145" w="40" h="20" ts="Y1" />
'''


def _write(path: Path, tail: str):
    path.write_text(f"<G><Layer>{_base_devices()}{tail}</Layer></G>", encoding="utf-8")


def _assigned_name(path: Path):
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed, frames, ("right", "bottom", "global")
    )
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    return assigned[key][0]


def test_makkah_rmu_name_priority_right_beats_closer_bottom(tmp_path):
    path = tmp_path / "right_first.g"
    _write(
        path,
        '''
<Text id="right_name" x="520" y="210" w="80" h="20" ts="40376" />
<Text id="bottom_name" x="250" y="401" w="80" h="20" ts="40377" />
''',
    )
    candidate = _assigned_name(path)
    assert candidate.text == "40376"
    assert candidate.direction == "right"


def test_makkah_rmu_name_priority_bottom_when_right_missing(tmp_path):
    path = tmp_path / "bottom_second.g"
    _write(
        path,
        '''
<Text id="bottom_name" x="250" y="405" w="80" h="20" ts="40377" />
<Text id="top_name" x="250" y="50" w="80" h="20" ts="40378" />
''',
    )
    candidate = _assigned_name(path)
    assert candidate.text == "40377"
    assert candidate.direction == "bottom"


def test_makkah_rmu_name_global_fallback_when_right_and_bottom_missing(tmp_path):
    path = tmp_path / "global_last.g"
    _write(
        path,
        '''
<Text id="top_name" x="250" y="65" w="80" h="20" ts="40378" />
''',
    )
    candidate = _assigned_name(path)
    assert candidate.text == "40378"
    assert candidate.direction == "global"


def test_moving_rmu_name_moves_its_linked_poke_by_same_delta(tmp_path):
    path = tmp_path / "name_poke.g"
    _write(
        path,
        '''
<poke id="17000001" x="520" y="210" w="80" h="20" ahref="DETAIL.com.pic.g"
      gfs_rmu_poke="1" gfs_rmu_text_id="right_name" />
<Text id="right_name" x="520" y="210" w="80" h="20" ts="40376" />
''',
    )
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    counts = reposition_rmu_annotations(
        parsed,
        nop_position="auto",
        rmu_name_position="top",
        rmu_name_margin=10,
    )
    assert counts["rmu_name_found"] == 1
    assert counts["rmu_name_moved"] == 1
    assert counts["rmu_name_poke_found"] == 1
    assert counts["rmu_name_poke_moved"] == 1

    layer = parsed.root.find("Layer")
    name = next(e for e in layer if e.get("id") == "right_name")
    poke = next(e for e in layer if e.get("id") == "17000001")
    assert (name.get("x"), name.get("y")) == ("260", "70")
    assert (poke.get("x"), poke.get("y")) == ("260", "70")
    assert (poke.get("w"), poke.get("h")) == (name.get("w"), name.get("h"))


def test_plain_legacy_poke_can_follow_name_by_geometry(tmp_path):
    path = tmp_path / "legacy_poke.g"
    _write(
        path,
        '''
<poke id="17000002" x="520" y="210" w="80" h="20" ahref="DETAIL.com.pic.g" />
<Text id="right_name" x="520" y="210" w="80" h="20" ts="40376" />
''',
    )
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    counts = reposition_rmu_annotations(parsed, rmu_name_position="bottom", rmu_name_margin=5)
    assert counts["rmu_name_poke_found"] == 1
    assert counts["rmu_name_poke_moved"] == 1
    layer = parsed.root.find("Layer")
    name = next(e for e in layer if e.get("id") == "right_name")
    poke = next(e for e in layer if e.get("id") == "17000002")
    assert (poke.get("x"), poke.get("y")) == (name.get("x"), name.get("y"))
