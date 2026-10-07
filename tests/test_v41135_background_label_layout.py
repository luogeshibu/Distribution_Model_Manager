from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from dmm.domain.graphics_cleanup.main_station_background_label import (
    process_main_station_background_label_repair,
)


REAL_SAMPLE = Path('/mnt/data/OSLA-08-MNA2-35-MNA4444444-32-MNA3-29-MNA4-12-ARF2-0.sln.pic.g')
ALREADY_FIXED_SAMPLE = Path('/mnt/data/OSLA-08-MNA2-35-MNA55555555-32-MNA3-29-MNA4-12-ARF2-0main-station-label-fixed.sln.pic.g')


def _num(el, key):
    return float(el.get(key))


def _by_id(root, xml_id):
    return next(el for el in root.iter() if el.get('id') == xml_id)


def _assert_centered_two_line_layout(root, bg_id, label_id, target_id):
    bg = _by_id(root, bg_id)
    label = _by_id(root, label_id)
    target = _by_id(root, target_id)

    bg_cx = _num(bg, 'x') + _num(bg, 'w') / 2.0
    label_cx = _num(label, 'x') + _num(label, 'w') / 2.0
    target_cx = _num(target, 'x') + _num(target, 'w') / 2.0
    assert label_cx == pytest.approx(bg_cx, abs=0.6)
    assert target_cx == pytest.approx(bg_cx, abs=0.6)

    content_top = _num(label, 'y')
    content_bottom = _num(target, 'y') + _num(target, 'h')
    top_margin = content_top - _num(bg, 'y')
    bottom_margin = (_num(bg, 'y') + _num(bg, 'h')) - content_bottom
    assert top_margin == pytest.approx(bottom_margin, abs=0.6)
    assert _num(bg, 'w') >= max(_num(label, 'w'), _num(target, 'w')) + 23.0
    assert _num(bg, 'h') >= _num(label, 'h') + _num(target, 'h') + 7.0


def test_background_label_repair_resizes_carrier_and_centers_two_lines(tmp_path):
    if not REAL_SAMPLE.exists():
        pytest.skip('field sample not mounted')
    result = process_main_station_background_label_repair(
        [REAL_SAMPLE], tmp_path / 'g_output', tmp_path / 'report'
    )
    assert result.updated_count >= 1
    assert result.layout_count >= 1
    root = ET.parse(result.output_files[0]).getroot()

    # MNA4 jump label: main-station label + (33359) share Poke 17003908.
    _assert_centered_two_line_layout(root, '17003908', '8003909', '8003910')
    assert _by_id(root, '8003909').get('ts') == 'MNA4-AH312'
    assert _by_id(root, '8003910').get('ts') == '(33359)'

    html = result.html_path.read_text(encoding='utf-8')
    assert 'BACKGROUND_RESIZED_AND_CENTERED' in html
    assert '新背景几何' in html


def test_already_correct_label_still_repairs_stale_background_layout(tmp_path):
    if not ALREADY_FIXED_SAMPLE.exists():
        pytest.skip('already-fixed field sample not mounted')
    result = process_main_station_background_label_repair(
        [ALREADY_FIXED_SAMPLE], tmp_path / 'g_output', tmp_path / 'report'
    )
    assert result.updated_count == 0
    assert result.layout_count >= 1
    root = ET.parse(result.output_files[0]).getroot()
    _assert_centered_two_line_layout(root, '17003157', '8003158', '8003159')
    assert _by_id(root, '8003158').get('ts') == 'MNA4-AH332'
    assert _by_id(root, '8003159').get('ts') == '(33394)'


def test_release_version_is_v41135():
    constants = Path('src/dmm/config/constants.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "4.1.135"' in constants
