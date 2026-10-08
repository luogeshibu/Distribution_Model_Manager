from pathlib import Path

from dmm.application.modules.pole_switch import (
    POLE_SWITCH_TEXT_MAX_DISTANCE,
    PoleSwitchParser,
)
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


def test_pole_switch_top_beats_closer_right(tmp_path):
    g = _write(tmp_path / "top_first.g", '''
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="top" x="100" y="10" w="70" h="20" ts="LBS-TOP" lc="255,0,0"/>
      <Text id="right" x="125" y="100" w="70" h="20" ts="LBS-RIGHT" lc="255,0,0"/>
    ''')
    row = PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]
    assert row["graphical_name"] == "LBS-TOP"
    assert row["name_direction"] == "top"
    assert row["name_priority"] == "TOP"


def test_pole_switch_right_beats_global_fallback(tmp_path):
    g = _write(tmp_path / "right_second.g", '''
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="right" x="140" y="100" w="70" h="20" ts="SEC-RIGHT" lc="255,0,0"/>
      <Text id="bottom" x="100" y="125" w="70" h="20" ts="SEC-BOTTOM" lc="255,0,0"/>
    ''')
    row = PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]
    assert row["graphical_name"] == "SEC-RIGHT"
    assert row["name_direction"] == "right"
    assert row["name_priority"] == "RIGHT"


def test_pole_switch_uses_global_when_top_and_right_absent(tmp_path):
    g = _write(tmp_path / "global_fallback.g", '''
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="left" x="10" y="100" w="60" h="20" ts="AR-LEFT" lc="255,0,0"/>
      <Text id="bottom" x="100" y="145" w="70" h="20" ts="AR-BOTTOM" lc="255,0,0"/>
    ''')
    row = PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]
    assert row["graphical_name"] == "AR-BOTTOM"
    assert row["name_direction"] == "bottom"
    assert row["name_priority"] == "GLOBAL"


def test_pole_switch_distance_limit_is_200():
    assert POLE_SWITCH_TEXT_MAX_DISTANCE == 200.0


def test_pole_switch_text_beyond_200_is_rejected(tmp_path):
    g = _write(tmp_path / "over_200.g", '''
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="far-red" x="100" y="321" w="70" h="20" ts="LBS-FAR" lc="255,0,0"/>
    ''')
    row = PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]
    assert row["graphical_name"] == ""
    assert row["name_distance"] == ""


def test_pole_switch_global_fallback_keeps_existing_text_eligibility(tmp_path):
    # Numeric/background Text remains eligible for pole switches when it is red;
    # the transformer-only pure-numeric-white-no-background rule must not leak here.
    g = _write(tmp_path / "eligibility_unchanged.g", '''
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="bottom" x="100" y="140" w="70" h="20" ts="12345" lc="255,0,0" background="1"/>
    ''')
    row = PoleSwitchParser().discover(GParser().parse(g), _catalog(), {})[0]
    assert row["graphical_name"] == "12345"
    assert row["name_priority"] == "GLOBAL"
