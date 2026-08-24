from pathlib import Path

import pytest

from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser
from dmm.domain.gfile.xml_diagnostics import GFileXmlParseError


def _write_rmu_with_nop(path: Path):
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="2001" x="100" y="100" w="120" h="120"/>
  <CBreakerDis id="3001" x="120" y="120" w="10" h="10"/>
  <ZhaiWaiJieDiDaoZha id="3002" x="140" y="140" w="10" h="10"/>
  <BusDis id="3003" x="160" y="160" w="10" h="10"/>
  <Text id="8001" x="230" y="130" w="35" h="12" ts="N.O.P" lc="255,0,0"/>
  <Text id="8002" x="230" y="155" w="35" h="12" ts="33254" lc="255,255,0"/>
</Layer></G>'''
    path.write_text(xml, encoding="utf-8")


def test_nop_is_not_an_rmu_name_candidate(tmp_path):
    path = tmp_path / "nop.g"
    _write_rmu_with_nop(path)
    parser = GParser(label_regex=RMU_LABEL_PATTERN)
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["right"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    names = [c.text for c in assigned[key]]
    assert "N.O.P" not in names
    assert "33254" in names


def test_nop_variants_are_filtered(tmp_path):
    path = tmp_path / "nop_variants.g"
    _write_rmu_with_nop(path)
    parser = GParser(label_regex=RMU_LABEL_PATTERN)
    parsed = parser.parse(path)
    base = next(o for o in parsed.objects if o.tag == "Text" and o.attrs.get("ts") == "N.O.P")
    for value in ("N.O.P", "NOP", "N-O-P", "N_O_P", "n.o.p."):
        clone = type(base)(base.tag, {**base.attrs, "ts": value}, base.box, base.xml_index)
        assert parser._valid_rmu_name_text(clone) is False


def test_misdeclared_utf8_file_is_rejected_not_fallback_parsed(tmp_path):
    path = tmp_path / "misdeclared.g"
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<G><Layer><Text id="8" x="1" y="2" w="3" h="4" ts="33254"/></Layer>
<Theme><Font><Item>微软雅黑,14</Item></Font></Theme></G>'''
    # Deliberate source-file defect: XML declares UTF-8, bytes are GBK.
    path.write_bytes(xml.encode("gbk"))

    parser = GParser(label_regex=RMU_LABEL_PATTERN)
    with pytest.raises(GFileXmlParseError) as caught:
        parser.parse(path)

    message = str(caught.value)
    assert "G_FILE_XML_INVALID" in message
    assert "misdeclared.g" in message
    assert "XML 声明编码：utf-8" in message
    assert "编码一致性检查：失败" in message
    assert "不会自动尝试 GBK/GB18030" in message
    assert "重新导出" in message
    assert "原始字节(HEX)" in message


def test_valid_utf8_file_still_parses_normally(tmp_path):
    path = tmp_path / "valid_utf8.g"
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<G><Layer><Text id="8" x="1" y="2" w="3" h="4" ts="33254"/></Layer>
<Theme><Font><Item>微软雅黑,14</Item></Font></Theme></G>'''
    path.write_text(xml, encoding="utf-8")
    parsed = GParser(label_regex=RMU_LABEL_PATTERN).parse(path)
    assert parsed.root.tag == "G"
    assert parsed.root.find("Theme/Font/Item").text == "微软雅黑,14"
