from pathlib import Path

from dmm.domain.gfile.parser import GParser


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rmu.g"
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    return path


def _cabinet(rect_id: str, x: int, y: int) -> str:
    return f'''\n    <rect id="{rect_id}" x="{x}" y="{y}" w="220" h="220"/>\n    <CBreakerDis id="117{rect_id}" x="{x+25}" y="{y+35}" w="30" h="30" p_NameString="Y1"/>\n    <ZhaiWaiJieDiDaoZha id="188{rect_id}" x="{x+25}" y="{y+80}" w="30" h="28" p_NameString="Y1D"/>\n    <BusDis id="380{rect_id}" x="{x+100}" y="{y+35}" w="6" h="150" p_NameString="BUS"/>\n    '''


def test_selected_top_direction_searches_globally_without_120_limit(tmp_path):
    path = _write(
        tmp_path,
        _cabinet("2000001", 100, 1000)
        + '<Text id="8000001" x="155" y="400" w="100" h="40" ts="36352" lc="255,255,255"/>',
    )
    parser = GParser(label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", max_distance=120)
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1

    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["top"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    candidates = assigned[key]
    assert [c.text for c in candidates] == ["36352"]
    assert candidates[0].gap > 120
    assert not candidates[0].is_green


def test_unselected_direction_never_participates_even_if_closer(tmp_path):
    path = _write(
        tmp_path,
        _cabinet("2000001", 100, 1000)
        + '<Text id="8000001" x="155" y="400" w="100" h="40" ts="TOP-NAME"/>'
        + '<Text id="8000002" x="155" y="1225" w="100" h="40" ts="BOTTOM-NAME"/>',
    )
    parser = GParser(label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["top"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    assert [c.text for c in assigned[key]] == ["TOP-NAME"]


def test_one_text_has_only_one_nearest_rmu_owner_globally(tmp_path):
    path = _write(
        tmp_path,
        _cabinet("2000001", 100, 500)
        + _cabinet("2000002", 100, 1000)
        + '<Text id="8000001" x="155" y="400" w="100" h="40" ts="UPPER"/>'
        + '<Text id="8000002" x="155" y="850" w="100" h="40" ts="LOWER"/>',
    )
    parser = GParser(label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 2
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["top"])

    by_id = {
        frame.frame.xml_id: [
            c.text
            for c in assigned[(frame.frame.xml_index, frame.frame.xml_id)]
        ]
        for frame in frames
    }
    assert by_id["2000001"] == ["UPPER"]
    assert by_id["2000002"] == ["LOWER"]
