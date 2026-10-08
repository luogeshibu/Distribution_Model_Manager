from pathlib import Path

from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser


def _parse(tmp_path: Path, text_xml: str):
    path = tmp_path / "strict-top.g"
    path.write_text(f'''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="rmu1" x="100" y="100" w="100" h="100" />
  <CBreakerDis id="cb1" x="120" y="125" w="20" h="20" />
  <ZhaiWaiJieDiDaoZha id="gd1" x="150" y="125" w="20" h="20" />
  <BusDis id="bus1" x="120" y="165" w="50" h="10" />
  {text_xml}
</Layer></G>''', encoding="utf-8")
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        overlap_tolerance=20,
    )
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["top"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    return [c.text for c in assigned[key]]


def test_whole_text_box_above_frame_is_accepted(tmp_path):
    assert _parse(tmp_path, '<Text id="t" x="120" y="60" w="60" h="20" ts="33417" />') == ["33417"]


def test_text_box_overlapping_top_edge_is_rejected_even_if_center_is_outside(tmp_path):
    assert _parse(tmp_path, '<Text id="t" x="120" y="60" w="60" h="70" ts="33417" />') == []


def test_inside_text_is_rejected(tmp_path):
    assert _parse(tmp_path, '<Text id="t" x="120" y="120" w="60" h="20" ts="33417" />') == []


def test_right_text_is_rejected(tmp_path):
    assert _parse(tmp_path, '<Text id="t" x="210" y="120" w="60" h="20" ts="33417" />') == []
