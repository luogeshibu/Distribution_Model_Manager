from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from g_file_studio.engines import smart_profile_engine
from g_file_studio.engines.smart_profile_engine import apply_smart_profile_to_tree
from g_file_studio.jeddah import style_engine
from g_file_studio.jeddah.style_engine import (
    apply_jeddah_rmu_name_standard,
    apply_jeddah_rmu_name_standard_to_tree,
    ensure_jeddah_normal_rmu_frames_white,
    ensure_jeddah_smart_rmu_devices,
    ensure_jeddah_smart_rmu_frames_red,
    remove_duplicate_smart_labels_in_rmus,
    remove_jeddah_channel_status_points,
    replace_jeddah_smr_with_smart,
)


def _minimal_rmu_xml() -> str:
    return '''<G><Layer>
<rect id="r1" x="100" y="100" w="200" h="200" lc="0,0,0"/>
<CBreakerDis id="c1" x="130" y="150" w="30" h="30" devref="#Load_Breaker_Switch.zwk.icn.g:X"/>
<ZhaiWaiJieDiDaoZha id="z1" x="180" y="150" w="30" h="30"/>
<BusDis id="b1" x="200" y="220" w="20" h="50"/>
<Text id="name" x="150" y="50" w="80" h="20" fs="20" ts="12345"/>
<Text id="y1" x="130" y="160" w="20" h="10" ts="Y1"/>
</Layer></G>'''


def test_tree_name_standard_matches_standalone_path_wrapper(tmp_path: Path):
    source = tmp_path / "sample.g"
    output = tmp_path / "standalone.g"
    source.write_text(_minimal_rmu_xml(), encoding="utf-8")

    standalone = apply_jeddah_rmu_name_standard(source, output)
    tree = ET.parse(source)
    in_memory = apply_jeddah_rmu_name_standard_to_tree(tree, source)

    assert standalone.identified_rmu_count == in_memory.identified_rmu_count == 1
    assert standalone.named_rmu_count == in_memory.named_rmu_count == 1
    assert standalone.changed_name_text_count == in_memory.changed_name_text_count == 1
    assert standalone.font_size_changed_count == in_memory.font_size_changed_count == 1
    assert standalone.position_changed_count == in_memory.position_changed_count == 1
    assert ET.parse(output).find('.//Text[@id="name"]').attrib == tree.find('.//Text[@id="name"]').attrib


def test_cached_identification_skips_repeat_rmu_recognition(monkeypatch):
    ident = SimpleNamespace(items=[], cabinet_count=0, named_count=0)
    tree = ET.ElementTree(ET.fromstring("<G><Layer/></G>"))
    path = Path("cached.g")

    def fail_identify(*_args, **_kwargs):
        raise AssertionError("cached identification should be reused")

    monkeypatch.setattr(style_engine, "identify_rmus", fail_identify)
    for fn in (
        ensure_jeddah_normal_rmu_frames_white,
        ensure_jeddah_smart_rmu_frames_red,
        ensure_jeddah_smart_rmu_devices,
        remove_jeddah_channel_status_points,
        remove_duplicate_smart_labels_in_rmus,
        replace_jeddah_smr_with_smart,
    ):
        fn(tree, path, identification=ident)

    monkeypatch.setattr(smart_profile_engine, "identify_rmus", fail_identify)
    apply_smart_profile_to_tree(
        tree,
        path,
        identification=ident,
        smart_lbs_devref="SMART_LBS",
        smart_breaker_devref="SMART_CB",
    )


def test_jeddah_batch_uses_isolated_high_volume_ui_and_no_redundant_margin_id_pass():
    root = Path(__file__).resolve().parents[1]
    page = (root / "src/g_file_studio/ui/pages/jeddah_batch_page.py").read_text(encoding="utf-8")
    batch = (root / "src/g_file_studio/jeddah/batch_processor.py").read_text(encoding="utf-8")

    assert "class _JeddahBatchTaskPanel(TaskPanel)" in page
    assert "self.task = _JeddahBatchTaskPanel()" in page
    assert "apply_jeddah_rmu_name_standard_to_tree" in batch
    assert "discover_g_inputs(stage_white" not in batch
    assert "enforce_id_rules=False" in batch
    assert 'stage_timings["total_seconds"]' in batch
