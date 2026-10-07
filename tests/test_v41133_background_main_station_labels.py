from pathlib import Path
import xml.etree.ElementTree as ET

from dmm.domain.graphics_cleanup.main_station_background_label import (
    process_main_station_background_label_repair,
)
from dmm.domain.graphics_cleanup.whole_graph_topology import (
    analyze_whole_graph_topology_file,
)


REAL_SAMPLE = Path('/mnt/data/OSLA-08-MNA2-35-MNA4444444-32-MNA3-29-MNA4-12-ARF2-0.sln.pic.g')


def _sample_or_skip():
    import pytest
    if not REAL_SAMPLE.exists():
        pytest.skip('field sample not mounted')
    return REAL_SAMPLE


def test_whole_graph_excludes_colored_background_jump_label_from_feeder_anchors():
    source = _sample_or_skip()
    analysis = analyze_whole_graph_topology_file(source)
    assert analysis['summary']['excluded_background_jump_label_count'] >= 1
    assert not any(row.get('feeder_label') == 'MNA4-12' for row in analysis['anchor_rows'])
    row = next(row for row in analysis['background_jump_rows'] if row.get('target_rmu_name') == '33359')
    assert row['label_text'] == 'MNA4-12'
    assert row['target_text'] == '(33359)'


def test_background_label_repair_preserves_parenthesized_target_and_replaces_only_main_name(tmp_path):
    source = _sample_or_skip()
    result = process_main_station_background_label_repair(
        [source], tmp_path / 'g_output', tmp_path / 'report'
    )
    assert result.updated_count >= 1
    output = result.output_files[0]
    root = ET.parse(output).getroot()
    values = {el.get('id'): el.get('ts') for el in root.iter() if el.get('id') in {'8003909', '8003910'}}
    assert values['8003909'] == 'MNA4-AH312'
    assert values['8003910'] == '(33359)'
    html = result.html_path.read_text(encoding='utf-8')
    assert 'MNA4-AH312' in html
    assert '(33359)' in html


def test_ui_registers_separate_background_label_module():
    source = Path('src/dmm/ui/main_window.py').read_text(encoding='utf-8')
    assert '"主网入口背景标签修正", "MAIN_STATION_BACKGROUND_LABEL"' in source
    assert 'def _build_main_station_background_label_panel' in source
    assert 'def start_main_station_background_label_repair' in source
