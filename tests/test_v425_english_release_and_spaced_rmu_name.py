import re
from pathlib import Path

from dmm.config.constants import RMU_LABEL_PATTERN
from dmm.domain.gfile.parser import GParser
from dmm.i18n import tr


def _write_rmu_fixture(path: Path, label: str):
    # One structural RMU at x=100,y=100,w=220,h=220 with a top label.
    path.write_text(
        f'''<?xml version="1.0" encoding="utf-8"?>
<G><Layer>
  <rect id="2000597" x="100" y="100" w="220" h="220" />
  <CBreakerDis id="1" x="150" y="160" w="20" h="20" />
  <ZhaiWaiJieDiDaoZha id="2" x="190" y="160" w="20" h="20" />
  <BusDis id="3" x="230" y="160" w="20" h="20" />
  <Text id="8000611" x="150" y="50" w="100" h="50" ts="{label}" lc="255,255,255" />
</Layer></G>''',
        encoding="utf-8",
    )


def test_rmu_name_pattern_accepts_numeric_space_suffix():
    assert re.fullmatch(RMU_LABEL_PATTERN, "66 B")
    assert re.fullmatch(RMU_LABEL_PATTERN, "123 C2")


def test_rmu_name_pattern_does_not_open_arbitrary_space_names():
    assert not re.fullmatch(RMU_LABEL_PATTERN, "RMU 42646")
    assert not re.fullmatch(RMU_LABEL_PATTERN, "BHR 01")


def test_spaced_rmu_name_is_assigned_to_nearest_top_frame(tmp_path):
    g = tmp_path / "spaced-name.g"
    _write_rmu_fixture(g, "66 B")
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        overlap_tolerance=20,
    )
    parsed = parser.parse(g)
    frames = parser.find_rmu_frames(parsed)
    assert len(frames) == 1
    assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, ["top"])
    key = (frames[0].frame.xml_index, frames[0].frame.xml_id)
    assert [c.text for c in assigned[key]] == ["66 B"]


def test_english_release_strings_from_reported_screens_have_no_chinese():
    strings = [
        "团队内部版",
        "查看模型校验和模型关联的历史记录、报告、修改记录与运行目录。",
        "时间", "模型", "操作", "G 文件/输入", "选中", "成功",
        "跳过/失败", "结果", "运行目录",
        "团队内部版的公共安全策略和报告保留策略。",
        "模型帮助",
    ]
    han = re.compile(r"[\u4e00-\u9fff]")
    for source in strings:
        translated = tr(source, "en_US")
        assert translated != source
        assert not han.search(translated), (source, translated)
