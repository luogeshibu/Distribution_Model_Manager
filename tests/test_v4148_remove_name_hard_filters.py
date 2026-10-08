from pathlib import Path

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {"file_name": "sw.g", "root_id": "SWROOT", "classification": "LBS"},
            {"file_name": "tr.g", "root_id": "TRROOT", "classification": "Transformer_OH"},
        ]
    }


def _write(path: Path, body: str):
    path.write_text(f"<G><Layer>{body}</Layer></G>", encoding="utf-8")
    return path


def test_pole_switch_ignores_legacy_format_color_background_filters(tmp_path):
    g = _write(tmp_path / "pole.g", """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="right" x="130" y="100" w="70" h="20" ts="LBS12345" lc="255,0,0" background="1"/>
    """)
    parsed = GParser().parse(g)
    rows = PoleSwitchParser().discover(parsed, _catalog(), {
        "name_format": "ALPHANUMERIC_SPACE",
        "name_colors": ["WHITE"],
        "name_has_background": False,
    })
    assert len(rows) == 1
    assert rows[0]["graphical_name"] == "LBS12345"
    assert rows[0]["name_direction"] == "right"


def test_transformer_ignores_legacy_format_background_but_requires_white_text(tmp_path):
    g = _write(tmp_path / "tr.g", """
      <TransformerDis id="tr1" x="100" y="100" w="20" h="20" devref="#tr.g:TRROOT"/>
      <Text id="top" x="100" y="60" w="70" h="20" ts="TR-A1" lc="255,255,255" background="1"/>
    """)
    parsed = GParser().parse(g)
    rows, _ = TransformerParser().discover(parsed, _catalog(), {
        "name_format": "NUMERIC",
        "name_colors": ["WHITE"],
        "name_has_background": False,
    })
    assert len(rows) == 1
    assert rows[0]["graphical_name"] == "TR-A1"
    assert rows[0]["name_direction"] == "top"


def test_pole_switch_and_transformer_ui_no_longer_expose_hard_filter_controls():
    pole = Path("src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
    transformer = Path("src/dmm/ui/widgets/transformer_settings.py").read_text(encoding="utf-8")
    for source in (pole, transformer):
        assert "设备名称筛选条件（强制过滤）" not in source
        assert "format_combo" not in source
        assert "color_combo" not in source
        assert "background_combo" not in source


def test_direction_and_distance_rules_still_exist():
    pole = Path("src/dmm/application/modules/pole_switch.py").read_text(encoding="utf-8")
    assert 'JEDDAH_NAME_PRIORITY = ("top", "right", "global")' in pole
    assert "POLE_SWITCH_TEXT_MAX_DISTANCE = 200.0" in pole
    assert "DEFAULT_DEVICE_TEXT_MAX_DISTANCE = 200.0" in pole
