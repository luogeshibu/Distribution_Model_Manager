from pathlib import Path

from dmm.application.modules.rmu import RmuModelModule
from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser


def _write_texts(path: Path):
    xml = '''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="2001" x="100" y="100" w="120" h="120"/>
  <CBreakerDis id="3001" x="120" y="120" w="10" h="10"/>
  <ZhaiWaiJieDiDaoZha id="3002" x="140" y="140" w="10" h="10"/>
  <BusDis id="3003" x="160" y="160" w="10" h="10"/>
  <Text id="8001" x="230" y="120" w="125" h="20" ts="42213"/>
  <Text id="8002" x="230" y="145" w="250" h="20" ts="0551491216"/>
  <Text id="8003" x="230" y="170" w="275" h="20" ts="V2-W-H-0008"/>
  <Text id="8004" x="230" y="195" w="327" h="20" ts="V2-W-M-H-0009"/>
</Layer></G>'''
    path.write_text(xml, encoding="utf-8")


def test_makkah_rmu_name_filters_phone_like_and_hyphenated_labels(tmp_path):
    path = tmp_path / "makkah_rmu.g"
    _write_texts(path)
    parser = GParser(
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        exclude_phone_like_rmu_names=True,
        exclude_hyphenated_rmu_names=True,
    )
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["right"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    names = [c.text for c in assigned[key]]
    assert names == ["42213"]


def test_filters_are_opt_in_and_do_not_change_other_parser_users(tmp_path):
    path = tmp_path / "generic.g"
    _write_texts(path)
    parser = GParser(label_regex=RMU_LABEL_PATTERN, max_distance=200)
    parsed = parser.parse(path)
    texts = {obj.attrs.get("ts"): obj for obj in parsed.objects if obj.tag.lower() == "text"}
    assert parser._valid_rmu_name_text(texts["0551491216"]) is True
    assert parser._valid_rmu_name_text(texts["V2-W-H-0008"]) is True
    assert parser._valid_rmu_name_text(texts["V2-W-M-H-0009"]) is True


def test_rmu_module_enables_both_noise_filters():
    class DummyDB:
        pass

    validator = RmuModelModule()._new_validator(DummyDB(), {}, lambda _m: None)
    assert validator.parser.exclude_phone_like_rmu_names is True
    assert validator.parser.exclude_hyphenated_rmu_names is True
