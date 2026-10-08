from pathlib import Path

from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser


def _write(path: Path, texts: str):
    body = f'''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="rmu1" x="100" y="100" w="100" h="100" />
  <CBreakerDis id="cb1" x="120" y="125" w="20" h="20" />
  <ZhaiWaiJieDiDaoZha id="gd1" x="150" y="125" w="20" h="20" />
  <BusDis id="bus1" x="120" y="165" w="50" h="10" />
  {texts}
</Layer></G>'''
    path.write_text(body, encoding="utf-8")
    return path


def _pick(path: Path):
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        overlap_tolerance=20,
    )
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed, frames, ["top", "right", "global"]
    )
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    rows = assigned[key]
    return rows[0] if rows else None


def test_rmu_name_prefers_top_even_when_right_is_closer(tmp_path):
    g = _write(tmp_path / "top-first.g", '''
      <Text id="inside" x="130" y="130" w="30" h="20" ts="INSIDE" />
      <Text id="top" x="120" y="40" w="60" h="20" ts="TOP-RMU" />
      <Text id="right" x="205" y="130" w="60" h="20" ts="RIGHT-RMU" />
    ''')
    picked = _pick(g)
    assert picked is not None
    assert picked.text == "TOP-RMU"
    assert picked.direction == "top"


def test_rmu_name_uses_right_when_no_top(tmp_path):
    g = _write(tmp_path / "right-second.g", '''
      <Text id="right" x="225" y="130" w="60" h="20" ts="RIGHT-RMU" />
      <Text id="bottom" x="120" y="205" w="60" h="20" ts="BOTTOM-RMU" />
    ''')
    picked = _pick(g)
    assert picked is not None
    assert picked.text == "RIGHT-RMU"
    assert picked.direction == "right"


def test_rmu_name_global_fallback_uses_other_outside_direction(tmp_path):
    g = _write(tmp_path / "global-last.g", '''
      <Text id="left" x="20" y="130" w="50" h="20" ts="LEFT-RMU" />
      <Text id="bottom" x="120" y="230" w="60" h="20" ts="BOTTOM-RMU" />
    ''')
    picked = _pick(g)
    assert picked is not None
    assert picked.text == "LEFT-RMU"
    assert picked.direction in {"left", "bottom", "global"}


def test_rmu_name_never_uses_text_inside_frame(tmp_path):
    g = _write(tmp_path / "outside-only.g", '''
      <Text id="inside" x="130" y="130" w="40" h="20" ts="INSIDE-RMU" />
      <Text id="right" x="220" y="130" w="60" h="20" ts="OUTSIDE-RMU" />
    ''')
    picked = _pick(g)
    assert picked is not None
    assert picked.text == "OUTSIDE-RMU"


def test_rmu_name_inside_only_returns_no_candidate(tmp_path):
    g = _write(tmp_path / "inside-only.g", '''
      <Text id="inside" x="130" y="130" w="40" h="20" ts="INSIDE-RMU" />
    ''')
    assert _pick(g) is None
