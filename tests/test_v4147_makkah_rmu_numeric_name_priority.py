from pathlib import Path

from dmm.application.modules.rmu import RmuModelModule
from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser


def _write_case(path: Path):
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<G><Layer>
  <rect id=\"2001\" x=\"100\" y=\"100\" w=\"120\" h=\"160\"/>
  <CBreakerDis id=\"3001\" x=\"120\" y=\"120\" w=\"10\" h=\"10\"/>
  <ZhaiWaiJieDiDaoZha id=\"3002\" x=\"140\" y=\"140\" w=\"10\" h=\"10\"/>
  <BusDis id=\"3003\" x=\"160\" y=\"160\" w=\"10\" h=\"10\"/>
  <Text id=\"8001\" x=\"230\" y=\"120\" w=\"55\" h=\"20\" ts=\"RMU\"/>
  <Text id=\"8002\" x=\"250\" y=\"150\" w=\"50\" h=\"20\" ts=\"A902\"/>
  <Text id=\"8003\" x=\"280\" y=\"180\" w=\"45\" h=\"20\" ts=\"902\"/>
  <Text id=\"8004\" x=\"225\" y=\"205\" w=\"95\" h=\"20\" ts=\"21.449047\"/>
  <Text id=\"8005\" x=\"225\" y=\"230\" w=\"95\" h=\"20\" ts=\"39.555820\"/>
</Layer></G>""",
        encoding="utf-8",
    )


def _assigned_names(parser, path):
    parsed = parser.parse(path)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["right"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    return [item.text for item in assigned[key]]


def test_makkah_global_nearest_beats_old_numeric_priority(tmp_path):
    path = tmp_path / "numeric_priority.g"
    _write_case(path)
    parser = GParser(
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        exclude_numeric_decimal_rmu_names=True,
        exclude_phone_like_rmu_names=True,
        exclude_hyphenated_rmu_names=True,
        prefer_pure_numeric_rmu_names=True,
    )
    assert _assigned_names(parser, path) == ["A902"]


def test_decimal_numbers_are_not_candidates_even_when_numeric_priority_enabled(tmp_path):
    path = tmp_path / "decimal_filter.g"
    _write_case(path)
    parser = GParser(
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        exclude_numeric_decimal_rmu_names=True,
        prefer_pure_numeric_rmu_names=True,
    )
    parsed = parser.parse(path)
    assert parser._valid_rmu_name_text(next(x for x in parsed.objects if x.attrs.get("ts") == "21.449047")) is False
    assert parser._valid_rmu_name_text(next(x for x in parsed.objects if x.attrs.get("ts") == "39.555820")) is False


def test_global_nearest_is_used_even_without_numeric_priority_flag(tmp_path):
    path = tmp_path / "generic.g"
    _write_case(path)
    parser = GParser(
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        exclude_numeric_decimal_rmu_names=True,
    )
    # Descriptive RMU text is filtered; A902 is the nearest remaining valid name.
    assert _assigned_names(parser, path) == ["A902"]


def test_rmu_module_disables_numeric_name_priority_in_global_mode():
    class DummyDB:
        pass

    validator = RmuModelModule()._new_validator(DummyDB(), {}, lambda _m: None)
    assert validator.parser.prefer_pure_numeric_rmu_names is False
