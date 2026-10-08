from pathlib import Path

from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.config.defaults import resolve_rmu_name_positions
from dmm.domain.gfile.parser import GParser
from dmm.domain.rmu.validator import RmuValidator


class _Db:
    def get_rmu_records(self, name):
        return [{"id": 1, "name": name, "feeder_id": 100}]


def _write(path: Path, texts: str):
    body = f'''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="rmu1" x="100" y="100" w="100" h="100" />
  <CBreakerDis id="cb1" x="120" y="125" w="20" h="20" />
  <ZhaiWaiJieDiDaoZha id="gd1" x="150" y="125" w="20" h="20" />
  <BusDis id="bus1" x="120" y="165" w="50" h="10" />
  {texts}
</Layer></G>'''
    path.write_text(body, encoding="utf-8")
    return path


def _validator():
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        max_distance=200,
        overlap_tolerance=20,
    )
    return RmuValidator(_Db(), parser, {})


def test_fixed_resolver_is_top_only():
    assert resolve_rmu_name_positions("FIXED", {"top": True, "right": True}) == ["top"]


def test_validator_ignores_legacy_right_and_uses_top(tmp_path):
    g = _write(tmp_path / "top-wins.g", '''
      <Text id="top" x="120" y="50" w="60" h="20" ts="33417" />
      <Text id="right" x="205" y="130" w="60" h="20" ts="WRONG-RIGHT" />
    ''')
    report = _validator().validate_file(g, ["right", "global"], required_feeder_id=100)
    assert report["rmu_results"][0]["rmu_name"] == "33417"


def test_right_only_is_name_failure(tmp_path):
    g = _write(tmp_path / "right-only.g", '''
      <Text id="right" x="205" y="130" w="60" h="20" ts="RIGHT-RMU" />
    ''')
    report = _validator().validate_file(g, ["right", "global"], required_feeder_id=100)
    row = report["rmu_results"][0]
    assert not row.get("rmu_name")
    assert row.get("rmu_status") == "FAIL"
    assert "上方" in str(row.get("rmu_reason") or "")


def test_inside_text_is_not_borrowed_as_top_name(tmp_path):
    g = _write(tmp_path / "inside.g", '''
      <Text id="inside" x="130" y="130" w="40" h="20" ts="INSIDE" />
    ''')
    report = _validator().validate_file(g, ["top"], required_feeder_id=100)
    assert report["rmu_results"][0]["rmu_status"] == "FAIL"
