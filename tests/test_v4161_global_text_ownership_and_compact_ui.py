from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.application.modules.pole_switch import PoleSwitchParser
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import Box, GObject, GParser, ParsedG, RmuFrame


def _parsed(objects):
    root = ET.Element("G")
    layer = ET.SubElement(root, "Layer")
    return ParsedG(Path("test.g"), root, layer, objects)


def _pole_catalog():
    return {"records": [{"file_name": "pole.g", "root_id": "ROOT", "classification": "LBS"}]}


def _tr_catalog():
    return {"records": [{"file_name": "tr.g", "root_id": "ROOT", "classification": "TRANSFORMER_OH"}]}


def test_pole_text_id_is_consumed_only_once():
    a = GObject("CBreakerDis", {"id": "a", "devref": "#SEC_S.zwk.icn.g:SEC_S"}, Box(0, 0, 10, 10), 1)
    b = GObject("CBreakerDis", {"id": "b", "devref": "#SEC_S.zwk.icn.g:SEC_S"}, Box(30, 0, 10, 10), 2)
    text = GObject("Text", {"id": "t", "ts": "LBS100"}, Box(12, 0, 10, 10), 3)
    rows = PoleSwitchParser().discover(_parsed([a, b, text]), _pole_catalog(), {})
    names = [row["graphical_name"] for row in rows]
    assert names.count("LBS100") == 1
    assert rows[0]["graphical_name"] == "LBS100"
    assert rows[1]["graphical_name"] == ""


def test_transformer_text_id_is_consumed_only_once():
    a = GObject("TransformerDis", {"id": "a", "devref": "#Transformer_OH.pb.icn.g:ROOT"}, Box(0, 0, 10, 10), 1)
    b = GObject("TransformerDis", {"id": "b", "devref": "#Transformer_OH.pb.icn.g:ROOT"}, Box(30, 0, 10, 10), 2)
    text = GObject("Text", {"id": "t", "ts": "TR100"}, Box(12, 0, 10, 10), 3)
    rows, _ = TransformerParser().discover_for_transformer_model(_parsed([a, b, text]), _tr_catalog(), {})
    names = [row["graphical_name"] for row in rows]
    assert names.count("TR100") == 1
    assert rows[0]["graphical_name"] == "TR100"
    assert rows[1]["graphical_name"] == ""


def test_rmu_text_id_is_consumed_only_once():
    r1 = GObject("rect", {"id": "r1"}, Box(0, 0, 20, 20), 1)
    r2 = GObject("rect", {"id": "r2"}, Box(40, 0, 20, 20), 2)
    text = GObject("Text", {"id": "t", "ts": "902"}, Box(22, 0, 10, 10), 3)
    parser = GParser(
        label_regex=r"^[A-Za-z0-9][A-Za-z0-9_.\-/ ]{0,127}$",
        max_distance=200.0,
        exclude_numeric_decimal_rmu_names=True,
        exclude_phone_like_rmu_names=True,
        exclude_hyphenated_rmu_names=True,
    )
    result = parser.assign_rmu_label_candidates_globally(
        _parsed([r1, r2, text]), [RmuFrame(r1), RmuFrame(r2)], ["global"]
    )
    assert [x.text for x in result[(1, "r1")]] == ["902"]
    assert result[(2, "r2")] == []


def test_logic_panels_follow_jeddah_full_width_style():
    for name, cls in [
        ("pole_switch_settings.py", "PoleSwitchSettingsWidget"),
        ("transformer_settings.py", "TransformerSettingsWidget"),
        ("fuse_settings.py", "FuseSettingsWidget"),
    ]:
        source = Path("src/dmm/ui/widgets") / name
        text = source.read_text(encoding="utf-8")
        assert f"class {cls}(QGroupBox):" in text
        assert "setMaximumWidth(1180)" not in text
        assert "Qt.AlignHCenter" not in text
        assert "QSizePolicy.Expanding" in text
        assert "padding:4px 7px" in text
