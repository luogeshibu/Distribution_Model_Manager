from pathlib import Path

from dmm.config.constants import (
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
    RMU_LABEL_SEARCH_MAX_DISTANCE,
)
from dmm.config.defaults import DEFAULT_RMU_NAME_EXCLUSIONS
from dmm.domain.gfile.parser import GParser


def _parser():
    return GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
        overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
        excluded_rmu_name_strings=DEFAULT_RMU_NAME_EXCLUSIONS,
        exclude_numeric_decimal_rmu_names=True,
        exclude_phone_like_rmu_names=True,
        exclude_hyphenated_rmu_names=True,
        prefer_pure_numeric_rmu_names=False,
    )


def _rmu_xml(rid: str, x: int, y: int) -> str:
    return f'''\n<rect id="{rid}" x="{x}" y="{y}" w="220" h="220"/>\n<CBreakerDis id="{rid}_cb" x="{x+20}" y="{y+20}" w="20" h="20"/>\n<ZhaiWaiJieDiDaoZha id="{rid}_g" x="{x+50}" y="{y+50}" w="20" h="20"/>\n<BusDis id="{rid}_bus" x="{x+20}" y="{y+100}" w="120" h="8"/>\n'''


def test_right_stage_beats_other_rmu_global_nearest(tmp_path: Path):
    """Regression from MAK ... MNA3/SHI/MASM/MNA4/MNA drawing.

    8248P2 is 145 units to the RIGHT of rmu_left, but only 80 units from the
    next RMU's LEFT side.  RIGHT-stage ownership must win before GLOBAL nearest.
    """
    path = tmp_path / "staged_right.g"
    path.write_text(
        "<G><Layer>"
        + _rmu_xml("rmu_left", 880, 902)
        + _rmu_xml("rmu_next", 1480, 901)
        + '<Text id="t8248" x="1245" y="1022" w="155" h="50" ts="8248P2" lc="255,255,255"/>'
        + '<Text id="t36781" x="1844" y="1030" w="125" h="50" ts="36781" lc="255,255,255"/>'
        + "</Layer></G>",
        encoding="utf-8",
    )
    parser = _parser()
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed, frames, ("right", "bottom", "global")
    )
    by_id = {
        frame.frame.xml_id: assigned[(frame.frame.xml_index, frame.frame.xml_id)][0]
        for frame in frames
    }
    assert by_id["rmu_left"].text == "8248P2"
    assert by_id["rmu_left"].direction == "right"
    assert by_id["rmu_left"].gap == 145.0
    assert by_id["rmu_next"].text == "36781"
    assert by_id["rmu_next"].direction == "right"
    assert by_id["rmu_next"].gap == 144.0


def test_bottom_stage_runs_only_after_right_stage(tmp_path: Path):
    path = tmp_path / "right_then_bottom.g"
    path.write_text(
        "<G><Layer>"
        + _rmu_xml("r1", 100, 100)
        + _rmu_xml("r2", 700, 100)
        + '<Text id="r1_right" x="330" y="180" w="80" h="30" ts="RIGHT1" lc="255,255,255"/>'
        + '<Text id="r2_bottom" x="760" y="340" w="100" h="30" ts="BOTTOM2" lc="255,255,255"/>'
        + "</Layer></G>",
        encoding="utf-8",
    )
    parser = _parser()
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed, frames, ("right", "bottom", "global")
    )
    by_id = {
        frame.frame.xml_id: assigned[(frame.frame.xml_index, frame.frame.xml_id)][0]
        for frame in frames
    }
    assert by_id["r1"].text == "RIGHT1"
    assert by_id["r1"].direction == "right"
    assert by_id["r2"].text == "BOTTOM2"
    assert by_id["r2"].direction == "bottom"
