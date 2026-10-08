from pathlib import Path

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "sw.g", "root_id": "SWROOT", "classification": "LBS"},
        ]
    }


def _write(path: Path, body: str):
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    return path


def _row(tmp_path, body: str):
    g = _write(tmp_path / "case.g", body)
    return PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]


def test_white_text_is_never_a_pole_switch_name(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="white-top" x="100" y="60" w="70" h="20" ts="LBS-WHITE" lc="255,255,255"/>
    """)
    assert row["graphical_name"] == ""
    assert row["name_direction"] == ""


def test_missing_color_is_default_white_and_is_rejected(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="default-white" x="100" y="60" w="70" h="20" ts="LBS-DEFAULT"/>
    """)
    assert row["graphical_name"] == ""


def test_any_nonwhite_color_is_eligible_and_top_still_beats_right(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="orange-top" x="100" y="55" w="80" h="20" ts="LBS-ORANGE" lc="255,170,0"/>
      <Text id="red-right" x="150" y="100" w="80" h="20" ts="LBS-RED" lc="255,0,0"/>
    """)
    assert row["graphical_name"] == "LBS-ORANGE"
    assert row["name_direction"] == "top"
    assert row["name_priority"] == "TOP"


def test_red_keeps_top_then_right_then_global_direction_priority(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="red-top" x="100" y="30" w="80" h="20" ts="LBS-TOP" lc="#ff0000"/>
      <Text id="red-right" x="125" y="100" w="80" h="20" ts="LBS-RIGHT" lc="255,0,0"/>
    """)
    assert row["graphical_name"] == "LBS-TOP"
    assert row["name_direction"] == "top"
    assert row["name_priority"] == "TOP"


def test_other_nonwhite_colors_are_valid_candidates(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="blue-top" x="100" y="40" w="80" h="20" ts="LBS-BLUE" lc="0,0,255"/>
      <Text id="green-right" x="125" y="100" w="80" h="20" ts="LBS-GREEN" lc="0,255,0"/>
    """)
    assert row["graphical_name"] == "LBS-BLUE"
    assert row["name_direction"] == "top"
    assert row["name_priority"] == "TOP"
