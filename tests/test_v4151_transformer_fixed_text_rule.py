from pathlib import Path

from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.parser import GParser


def _catalog():
    return {
        "records": [
            {
                "file_name": "Transformer_OH.pb.icn.g",
                "classification": "TRANSFORMER_OH",
            }
        ]
    }


def _parse(tmp_path: Path, texts: str):
    path = tmp_path / "transformer_fixed_rule.g"
    path.write_text(
        '<G><Layer>'
        '<CBreaker id="tr1" devref="#Transformer_OH.pb.icn.g:ROOT" '
        'x="100" y="100" w="20" h="20"/>'
        + texts +
        '</Layer></G>',
        encoding="utf-8",
    )
    return GParser(required_rmu_tags=set()).parse(path)


def test_transformer_makkah_rule_allows_mixed_text_and_ignores_color_format_cache(tmp_path):
    parsed = _parse(
        tmp_path,
        '<Text id="t1" ts="TX ABC 01" lc="255,255,255" x="125" y="105" w="30" h="10"/>'
        '<Text id="t2" ts="97803" lc="255,255,255" x="180" y="105" w="30" h="10"/>',
    )
    rows, _ = TransformerParser().discover_for_transformer_model(
        parsed,
        _catalog(),
        {
            # Legacy cached NUMERIC must not reject the nearer mixed label.
            "transformer_name_format": "NUMERIC",
            "transformer_name_colors": ["OTHER"],
            "transformer_name_has_background": True,
        },
    )
    assert rows[0]["graphical_name"] == "TX ABC 01"
    assert rows[0]["name_xml_id"] == "t1"


def test_transformer_makkah_accepts_nonwhite_and_background_text_when_nearest(tmp_path):
    parsed = _parse(
        tmp_path,
        '<Text id="t1" ts="11111" lc="255,0,0" x="121" y="105" w="20" h="10"/>'
        '<Text id="t2" ts="22222" lc="255,255,255" background="1" x="123" y="105" w="20" h="10"/>'
        '<Text id="t3" ts="33333" lc="255,255,255" x="140" y="105" w="25" h="10"/>',
    )
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog(), {})
    assert rows[0]["graphical_name"] == "11111"
    assert rows[0]["name_xml_id"] == "t1"


def test_transformer_settings_ui_no_longer_exposes_format_color_background_selectors():
    source = Path("src/dmm/ui/widgets/transformer_settings.py").read_text(encoding="utf-8")
    assert "self.format_combo" not in source
    assert "self.color_combo" not in source
    assert "self.background_combo" not in source
    assert "不限制颜色" in source
    assert "不限制" in source
    assert "纯小数" in source
    assert "距离 ≤ 200" in source


def test_transformer_makkah_rejects_pure_decimal_but_keeps_integer(tmp_path):
    parsed = _parse(
        tmp_path,
        '<Text id="decimal" ts="21.449047" lc="255,0,0" x="121" y="105" w="30" h="10"/>'
        '<Text id="integer" ts="902" lc="0,255,0" x="140" y="105" w="20" h="10"/>',
    )
    rows, _ = TransformerParser().discover_for_transformer_model(parsed, _catalog(), {})
    assert rows[0]["graphical_name"] == "902"
    assert rows[0]["name_xml_id"] == "integer"
