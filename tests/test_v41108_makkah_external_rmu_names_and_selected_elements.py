from pathlib import Path

from dmm.application.modules.pole_switch import (
    PoleSwitchParser,
    _is_configured_pole_switch_devref,
    _normalized_pole_switch_element_files,
)
from dmm.application.modules.transformer import TransformerParser
from dmm.config.constants import (
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
    RMU_LABEL_SEARCH_MAX_DISTANCE,
)
from dmm.config.defaults import DEFAULT_RMU_NAME_EXCLUSIONS
from dmm.domain.gfile.parser import GParser


def _rmu_parser():
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
    return f'''
<rect id="{rid}" x="{x}" y="{y}" w="220" h="220"/>
<CBreakerDis id="{rid}_cb" x="{x+20}" y="{y+20}" w="20" h="20"/>
<ZhaiWaiJieDiDaoZha id="{rid}_g" x="{x+50}" y="{y+50}" w="20" h="20"/>
<BusDis id="{rid}_bus" x="{x+20}" y="{y+100}" w="120" h="8"/>
'''


def test_rmu_name_text_inside_any_rmu_frame_is_never_a_candidate(tmp_path: Path):
    path = tmp_path / "external_name_only.g"
    path.write_text(
        "<G><Layer>"
        + _rmu_xml("r1", 100, 100)
        + '<Text id="inside" x="150" y="160" w="100" h="30" ts="INSIDE1" lc="255,255,255"/>'
        + '<Text id="outside" x="0" y="170" w="80" h="30" ts="OUTSIDE1" lc="255,255,255"/>'
        + "</Layer></G>",
        encoding="utf-8",
    )
    parser = _rmu_parser()
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed, frames, ("right", "bottom", "global")
    )
    frame = frames[0]
    chosen = assigned[(frame.frame.xml_index, frame.frame.xml_id)][0]
    assert chosen.text == "OUTSIDE1"
    assert chosen.direction == "global"


def test_rmu_text_center_inside_neighbor_frame_cannot_be_global_fallback(tmp_path: Path):
    path = tmp_path / "neighbor_internal_text.g"
    path.write_text(
        "<G><Layer>"
        + _rmu_xml("r1", 100, 100)
        + _rmu_xml("r2", 500, 100)
        + '<Text id="inside_r2" x="520" y="160" w="120" h="30" ts="CABINET2" lc="255,255,255"/>'
        + "</Layer></G>",
        encoding="utf-8",
    )
    parser = _rmu_parser()
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed, frames, ("right", "bottom", "global")
    )
    assert all(not candidates for candidates in assigned.values())


def test_user_selected_pole_switch_filename_has_no_rmu_prefix_or_transformer_overlap_veto(tmp_path: Path):
    settings = {
        "pole_switch_element_files": ["RMU_CUSTOM.icn.g"],
        "transformer_element_files": ["RMU_CUSTOM.icn.g"],
    }
    assert _normalized_pole_switch_element_files(settings) == ["RMU_CUSTOM.icn.g"]
    assert _is_configured_pole_switch_devref(
        "#folder/RMU_CUSTOM.icn.g:ROOT", settings
    )

    path = tmp_path / "selected_switch.g"
    path.write_text(
        '<G><Layer><OddSymbol id="sw1" x="10" y="10" w="20" h="20" '
        'devref="#folder/RMU_CUSTOM.icn.g:ROOT"/>'
        '<Text id="name1" x="40" y="10" w="80" h="20" ts="SW-1"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    parsed = GParser(required_rmu_tags=set()).parse(path)
    rows = PoleSwitchParser().discover(parsed, None, settings)
    assert len(rows) == 1
    assert rows[0]["devref"] == "#folder/RMU_CUSTOM.icn.g:ROOT"


def test_user_selected_transformer_filename_accepts_arbitrary_xml_tag(tmp_path: Path):
    settings = {"transformer_element_files": ["MY_TRANSFORMER.icn.g"]}
    path = tmp_path / "selected_transformer.g"
    path.write_text(
        '<G><Layer><OddTransformerSymbol id="tr1" x="10" y="10" w="20" h="20" '
        'devref="#MY_TRANSFORMER.icn.g:ROOT"/>'
        '<Text id="name1" x="40" y="10" w="80" h="20" ts="TR-1"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    parsed = GParser(required_rmu_tags=set()).parse(path)
    rows, _ = TransformerParser().discover(parsed, None, settings)
    assert len(rows) == 1
    assert rows[0]["devref"] == "#MY_TRANSFORMER.icn.g:ROOT"
