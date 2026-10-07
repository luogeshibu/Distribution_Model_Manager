from pathlib import Path

from dmm.domain.gfile.master_station_frames import find_master_station_frames, parse_master_feeder_label
from dmm.domain.gfile.parser import GParser


def test_parse_main_feeder_keeps_xy_suffix():
    assert parse_master_feeder_label("SHM1-AH341_X") == ("SHM1-AH341_X", "SHM1", "AH341_X")
    assert parse_master_feeder_label("HRM2-AH308_X") == ("HRM2-AH308_X", "HRM2", "AH308_X")
    assert parse_master_feeder_label("SHM1-AH341_Y") == ("SHM1-AH341_Y", "SHM1", "AH341_Y")


def test_find_main_frame_keeps_xy_suffix_and_color_neutral(tmp_path: Path):
    g = tmp_path / "xy.g"
    g.write_text(
        '<G><Layer>'
        '<Rect id="r1" x="100" y="100" w="220" h="220"/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40"/>'
        '<Text id="t1" x="130" y="45" w="260" h="40" ts="SHM1-AH341_X" lc="255,0,0" lcc="#ff0000"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    frame = find_master_station_frames(GParser().parse(g))[0]
    assert frame.feeder_label == "SHM1-AH341_X"
    assert frame.station_hint == "SHM1"
    assert frame.feeder_hint == "AH341_X"
