from pathlib import Path

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {"records": [{"file_name": "sw.g", "root_id": "SWROOT", "classification": "LBS"}]}


def _row(tmp_path: Path, text_attrs: str):
    path = tmp_path / "case.g"
    path.write_text(
        '<G><Layer>'
        '<CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>'
        f'<Text id="name1" x="100" y="60" w="80" h="20" ts="LBS-123" {text_attrs}/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    return PoleSwitchParser().discover(GParser().parse(path), _catalog(), {})[0]


def test_explicit_nonwhite_colors_are_all_allowed(tmp_path):
    for index, attrs in enumerate((
        'lc="255,0,0"',
        'lc="170,0,0" lcc="#aa0000"',
        'lc="255,255,0"',
        'lc="0,0,255"',
        'lc="0,255,0"',
        'lc="0,0,0"',
    )):
        case = tmp_path / str(index)
        case.mkdir()
        row = _row(case, attrs)
        assert row["graphical_name"] == "LBS-123"
        assert row["name_priority"] == "TOP"


def test_white_and_missing_color_are_rejected(tmp_path):
    white = tmp_path / "white"
    white.mkdir()
    assert _row(white, 'lc="255,255,255"')["graphical_name"] == ""

    missing = tmp_path / "missing"
    missing.mkdir()
    assert _row(missing, '')["graphical_name"] == ""


def test_color_rule_does_not_change_database_lookup_normalization(tmp_path):
    row = _row(tmp_path, 'lc="0,0,255"')
    assert row["graphical_name"] == "LBS-123"
