from pathlib import Path

from dmm.application.modules.feeder_context import resolve_drawing_feeder
from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.application.modules.transformer import TransformerParser
from dmm.config.defaults import resolve_rmu_name_positions
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


def test_rmu_name_direction_is_fixed_top_right_global():
    assert resolve_rmu_name_positions("FIXED", {
        "top": False,
        "right": True,
        "left": True,
        "bottom": True,
    }) == ["top"]


def test_pole_switch_rejects_bottom_name_and_uses_right_name(tmp_path):
    g = _write(tmp_path / "pole.g", '''
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="bottom" x="100" y="130" w="70" h="20" ts="BAD-BOTTOM" lc="255,0,0"/>
      <Text id="right" x="130" y="100" w="70" h="20" ts="SW-RIGHT" lc="255,0,0"/>
    ''')
    parsed = GParser().parse(g)
    rows = PoleSwitchParser().discover(parsed, _catalog(), {})
    assert len(rows) == 1
    assert rows[0]["graphical_name"] == "SW-RIGHT"
    assert rows[0]["name_direction"] == "right"


def test_transformer_uses_nearest_white_name_from_any_direction(tmp_path):
    g = _write(tmp_path / "tr.g", '''
      <TransformerDis id="tr1" x="100" y="100" w="20" h="20" devref="#tr.g:TRROOT"/>
      <Text id="left" x="0" y="100" w="70" h="20" ts="11111" lc="255,255,255"/>
      <Text id="bottom" x="100" y="125" w="70" h="20" ts="22222" lc="255,255,255"/>
    ''')
    parsed = GParser().parse(g)
    rows, _ = TransformerParser().discover(parsed, _catalog(), {
        "name_format": "NUMERIC",
        "name_colors": ["WHITE"],
        "name_has_background": False,
    })
    assert len(rows) == 1
    assert rows[0]["graphical_name"] == "22222"
    assert rows[0]["name_direction"] == "bottom"


class _DB:
    def find_substations_by_name(self, name, table_id=405):
        return [{"id": 40501, "name": "ABH"}] if name == "ABH" else []

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        if int(station_id) == 40501 and feeder_name == "AH303":
            return [{"id": 700, "name": "AH303", "st_id": 40501}]
        return []

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {"id": int(feeder_id), "code": "AH303", "name": "AH303", "station_name": "ABH"}

    def get_combined_device_records(self, name):
        raise AssertionError("graphical device must not decide feeder")


def test_feeder_resolution_logs_filename_and_resolved_feeder(tmp_path):
    g = _write(tmp_path / "JED-NTH-ABH-03.sln.pic.g", """
      <CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>
      <Text id="right" x="130" y="100" w="70" h="20" ts="SW-RIGHT" lc="255,0,0"/>
    """)
    logs = []
    result = resolve_drawing_feeder(
        _DB(),
        GParser().parse(g),
        {"element_catalog": _catalog()},
        log_callback=logs.append,
    )
    assert result["ready"] is True
    assert result["feeder_id"] == 700
    assert any("唯一来源=文件名" in line and "AH303" in line for line in logs)
    assert any("[发现馈线] 文件名唯一确定" in line and "FEEDER_ID=700" in line for line in logs)

def test_feeder_ui_no_longer_exposes_drawing_type_selector():
    source = Path("src/dmm/ui/widgets/feeder_settings.py").read_text(encoding="utf-8")
    assert "图纸类型确认" not in source
    assert "强制组合图（本次文件/目录）" not in source
    assert "self.feeder_drawing_mode = NoWheelComboBox()" not in source
    assert '"feeder_drawing_mode": "SINGLE"' in source
