from pathlib import Path

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {"records": [{"file_name": "sw.g", "root_id": "SWROOT", "classification": "LBS"}]}


def _row(tmp_path: Path, body: str):
    path = tmp_path / "case.g"
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    parsed = GParser().parse(path)
    return PoleSwitchParser().discover(parsed, _catalog(), {})[0]


def test_yellow_device_name_is_allowed_when_explicitly_colored(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="yellow-top" x="100" y="60" w="80" h="20" ts="LBS240" lc="255,255,127"/>
    """)
    assert row["graphical_name"] == "LBS240"
    assert row["name_xml_id"] == "yellow-top"


def test_nonwhite_device_like_label_is_accepted(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="green-top" x="100" y="60" w="80" h="20" ts="LBS123" lc="0,255,0"/>
    """)
    assert row["graphical_name"] == "LBS123"
    assert row["name_priority"] == "TOP"


def test_red_text_still_uses_top_right_global_priority(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="red-top" x="100" y="50" w="80" h="20" ts="LBS-TOP" lc="255,0,0"/>
      <Text id="red-right" x="150" y="100" w="80" h="20" ts="LBS-RIGHT" lc="#ff0000"/>
    """)
    assert row["graphical_name"] == "LBS-TOP"
    assert row["name_priority"] == "TOP"


def test_dark_red_aa0000_is_still_red_pole_switch_name(tmp_path):
    row = _row(tmp_path, """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="dark-red-top" x="100" y="60" w="80" h="20" ts="LBS1325" lc="170,0,0" lcc="#aa0000"/>
    """)
    assert row["graphical_name"] == "LBS1325"
    assert row["name_xml_id"] == "dark-red-top"
    assert row["name_priority"] == "TOP"
