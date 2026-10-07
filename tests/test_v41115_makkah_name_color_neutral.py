from pathlib import Path

from dmm.domain.gfile.master_station_frames import find_master_station_frames
from dmm.domain.gfile.parser import GParser
from dmm.config.constants import RMU_LABEL_PATTERN


def _write(path: Path, body: str) -> Path:
    path.write_text(f'<G><Layer>{body}</Layer></G>', encoding='utf-8')
    return path


def _rmu_xml(rid: str, x: int, y: int) -> str:
    return (
        f'<rect id="{rid}" x="{x}" y="{y}" w="220" h="220"/>'
        f'<CBreakerDis id="{rid}_cb" x="{x+20}" y="{y+20}" w="20" h="20"/>'
        f'<ZhaiWaiJieDiDaoZha id="{rid}_g" x="{x+50}" y="{y+50}" w="20" h="20"/>'
        f'<BusDis id="{rid}_bus" x="{x+20}" y="{y+100}" w="120" h="8"/>'
    )


def test_master_station_accepts_red_feeder_caption(tmp_path: Path):
    g = _write(
        tmp_path / 'red_master.g',
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40"/>'
        '<Text id="title1" x="150" y="55" w="120" h="30" '
        'ts="MNA4-12" lc="255,0,0" lcc="#ff0000"/>',
    )
    frame = find_master_station_frames(GParser().parse(g))[0]
    assert frame.feeder_label == 'MNA4-12'
    assert frame.station_hint == 'MNA4'
    assert frame.feeder_hint == '12'


def test_master_station_color_is_not_a_priority(tmp_path: Path):
    g = _write(
        tmp_path / 'master_color_neutral.g',
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40"/>'
        # Red is closer and must win even though a white candidate exists.
        '<Text id="red" x="150" y="70" w="120" h="20" ts="MNA4-12" lc="255,0,0"/>'
        '<Text id="white" x="150" y="30" w="120" h="20" ts="ARF2-07" lc="255,255,255" lcc="#ffffff"/>',
    )
    frame = find_master_station_frames(GParser().parse(g))[0]
    assert frame.feeder_label == 'MNA4-12'
    assert frame.label_obj.xml_id == 'red'


def test_master_station_still_rejects_background_caption(tmp_path: Path):
    g = _write(
        tmp_path / 'master_bg.g',
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40"/>'
        '<Text id="red_bg" x="150" y="70" w="120" h="20" ts="MNA4-12" '
        'lc="255,0,0" background="1"/>'
        '<Text id="blue_plain" x="150" y="30" w="120" h="20" ts="ARF2-07" lc="0,0,255"/>',
    )
    frame = find_master_station_frames(GParser().parse(g))[0]
    assert frame.feeder_label == 'ARF2-07'
    assert frame.label_obj.xml_id == 'blue_plain'


def test_rmu_staged_name_selection_ignores_text_color(tmp_path: Path):
    g = _write(
        tmp_path / 'rmu_color_neutral.g',
        _rmu_xml('r1', 100, 100)
        # Both are valid RIGHT candidates; red is geometrically closer.
        + '<Text id="red_near" x="330" y="175" w="80" h="30" ts="30038" lc="255,0,0"/>'
        + '<Text id="green_far" x="390" y="175" w="80" h="30" ts="30039" lc="0,255,0" lcc="#00ff00"/>',
    )
    parser = GParser(label_regex=RMU_LABEL_PATTERN, max_distance=300)
    parsed = parser.parse(g)
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ('right','bottom','global'))
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    assert assigned[key][0].text == '30038'
    assert assigned[key][0].obj.xml_id == 'red_near'
