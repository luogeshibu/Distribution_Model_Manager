from pathlib import Path

from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser


def _write_fixture(path: Path, labels):
    text_xml = "\n".join(
        f'<Text id="{8000000+i}" x="{x}" y="{y}" w="{w}" h="{h}" ts="{text}" lc="255,255,255" />'
        for i, (text, x, y, w, h) in enumerate(labels, start=1)
    )
    path.write_text(
        f'''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="2001193" x="100" y="200" w="220" h="220" />
  <CBreakerDis id="1" x="150" y="260" w="20" h="20" />
  <ZhaiWaiJieDiDaoZha id="2" x="190" y="260" w="20" h="20" />
  <BusDis id="3" x="230" y="260" w="20" h="20" />
  {text_xml}
</Layer></G>''',
        encoding="utf-8",
    )


def _assigned_texts(parser: GParser, path: Path):
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["top"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    return [candidate.text for candidate in assigned[key]]


def test_exact_user_exclusion_strings_are_removed_before_name_assignment(tmp_path):
    g = tmp_path / "exclusions.g"
    _write_fixture(
        g,
        [
            ("SFI", 160, 140, 80, 30),
            ("DAS/OK", 160, 100, 90, 30),
            ("9001", 160, 60, 80, 30),
        ],
    )
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        excluded_rmu_name_strings=["SFI", "DAS/OK"],
    )
    assert _assigned_texts(parser, g) == ["9001"]


def test_exclusion_is_complete_string_not_substring(tmp_path):
    g = tmp_path / "exact.g"
    _write_fixture(g, [("SFI-9001", 150, 140, 120, 30)])
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        excluded_rmu_name_strings=["SFI"],
    )
    assert _assigned_texts(parser, g) == ["SFI-9001"]


def test_large_font_top_label_can_overlap_frame_box_but_still_be_owned(tmp_path):
    g = tmp_path / "large-label.g"
    # This reproduces BABJ 38995: the XML Text bounding box overlaps the frame
    # top edge, while the text center is still above the RMU.
    _write_fixture(g, [("38995", 139, 127, 155, 128)])
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        excluded_rmu_name_strings=["SFI", "DAS/OK"],
        overlap_tolerance=20,
    )
    assert _assigned_texts(parser, g) == ["38995"]


def test_rmu_exclusion_ui_strings_have_english_translations():
    from dmm.i18n import tr
    assert tr("环网柜名称排除字符串", "en_US") == "RMU Name Exclusion Strings"
    assert tr("例如：N.O.P, NOP, SFI, DAS/OK", "en_US") == "Example: N.O.P, NOP, SFI, DAS/OK"
