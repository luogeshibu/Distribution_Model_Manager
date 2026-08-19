from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier


FEEDER_ID = 3799912185593856228


class NoDbCalls:
    pass


def _write_g(path: Path, *, with_feedline=False):
    body = '<Bus id="b1" key_name="busbarsection JED CTL AJWD 13.8kV AHBB1A AHBB1A id"/>'
    if with_feedline:
        body += '<FeedLine id="f1" />'
    path.write_text(f'<G id="root" facID=""><Layer>{body}</Layer></G>', encoding='utf-8')


def test_drawing_mode_single_overrides_automatic_multi(monkeypatch, tmp_path):
    g = tmp_path / 'x.g'
    _write_g(g)

    def fake_classify(self, _g):
        return {
            'drawing_type': 'MULTI_FEEDER_COMPOSITE',
            'classification_reason': 'MULTIPLE_INDEPENDENT_SOURCE_BRANCHES',
            'parsed': object(),
            'bus_count': 3,
            'effective_busbar_count': 3,
            'feeder_source_branch_count': 7,
            'feeder_title_count': 7,
            'feedline_count': 12,
        }

    monkeypatch.setattr(FeederDrawingTopologyClassifier, 'classify', fake_classify)
    profile = FeederModelModule._drawing_profile(g, {'feeder_drawing_mode': 'SINGLE'})
    assert profile['automatic_drawing_type'] == 'MULTI_FEEDER_COMPOSITE'
    assert profile['drawing_type'] == 'SINGLE_FEEDER'
    assert profile['drawing_type_overridden'] == 'YES'
    assert profile['classification_reason'] == 'USER_CONFIRMED_SINGLE_FEEDER'


def test_drawing_mode_multi_overrides_automatic_single(monkeypatch, tmp_path):
    g = tmp_path / 'x.g'
    _write_g(g)

    def fake_classify(self, _g):
        return {
            'drawing_type': 'SINGLE_FEEDER',
            'classification_reason': 'SINGLE_FEEDER_TITLE_FALLBACK',
            'parsed': object(),
            'bus_count': 1,
            'effective_busbar_count': 1,
            'feeder_source_branch_count': 0,
            'feeder_title_count': 1,
            'feedline_count': 0,
        }

    monkeypatch.setattr(FeederDrawingTopologyClassifier, 'classify', fake_classify)
    profile = FeederModelModule._drawing_profile(g, {'feeder_drawing_mode': 'MULTI'})
    assert profile['automatic_drawing_type'] == 'SINGLE_FEEDER'
    assert profile['drawing_type'] == 'MULTI_FEEDER_COMPOSITE'
    assert profile['classification_reason'] == 'USER_CONFIRMED_MULTI_FEEDER_COMPOSITE'


def test_preview_keeps_root_candidate_even_when_section_region_is_blocked(monkeypatch, tmp_path):
    g = tmp_path / 'TEST88.sln.pic.g'
    _write_g(g, with_feedline=True)
    report = {
        'g_file': str(g),
        'file_name': g.name,
        'drawing_type': 'SINGLE_FEEDER',
        'region_index': 1,
        'feeder_id': FEEDER_ID,
        'feeder_name': 'AJWD 43',
        'feeder_resolution_source': 'MANUAL',
        'feeder_root_writeback_needed': 'YES',
        'association_eligible': False,
        'feedline_rows': [
            {
                'object_type': 'FeedLine',
                'xml_id': 'f1',
                'association_ready': 'NO',
                'writeback_needed': 'NO',
                'reason': 'SECTION_MODEL_ERROR',
            }
        ],
        'status': 'FAIL',
        'reason': 'SECTION_MODEL_ERROR',
        'summary': {},
    }
    module = FeederModelModule()
    monkeypatch.setattr(
        module,
        'validate',
        lambda *a, **k: ([report], {'feeder_files': 1}, module._rules({})),
    )
    settings = {
        'feeder_resolution_mode': 'MANUAL',
        'manual_feeder_name': 'AJWD 43',
        'feeder_drawing_mode': 'SINGLE',
    }
    preview = module.preview_association(NoDbCalls(), [g], settings, lambda _m: None)
    changes = preview['changes_by_file'][str(g)]
    assert len(changes) == 1
    assert changes[0]['change_kind'] == 'FEEDER_ROOT_FACID'
    assert changes[0]['attributes'] == {'facID': str(FEEDER_ID)}


def test_apply_root_candidate_ignores_blocked_feedline_region(tmp_path):
    g = tmp_path / 'TEST88.sln.pic.g'
    _write_g(g, with_feedline=True)
    stat = g.stat()
    report = {
        'g_file': str(g),
        'file_name': g.name,
        'drawing_type': 'SINGLE_FEEDER',
        'region_index': 1,
        'feeder_id': FEEDER_ID,
        'feeder_name': 'AJWD 43',
        'feeder_resolution_source': 'MANUAL',
        'feeder_root_writeback_needed': 'YES',
        'association_eligible': False,
        'feedline_rows': [],
        'reason': 'SECTION_MODEL_ERROR',
    }
    root_row = {
        'object_type': 'G',
        'xml_id': 'root',
        'status': 'WARN',
        'severity': 'UNLINKED',
        'association_ready': 'YES',
        'writeback_needed': 'YES',
    }
    change = {
        'change_kind': 'FEEDER_ROOT_FACID',
        'xml_id': 'root',
        'tag': 'G',
        'attributes': {'facID': str(FEEDER_ID)},
        'feeder_name': 'AJWD 43',
        'feeder_id': FEEDER_ID,
        'region_index': 1,
        'validated_row': root_row,
    }
    settings = {
        'feeder_table_id': 13500,
        'section_table_id': 13503,
        'section_domain': 1,
        'feeder_resolution_mode': 'MANUAL',
        'manual_feeder_name': 'AJWD 43',
        'feeder_drawing_mode': 'SINGLE',
        'auto_create_missing_sections': True,
    }
    preview = {
        'reports': [report],
        'changes_by_file': {str(g): [change]},
        'ls_normalization_by_file': {},
        'file_fingerprints': {str(g): {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}},
        'settings_snapshot': dict(settings),
        'rules': FeederModelModule._rules(settings),
    }
    out = tmp_path / 'out'
    result = FeederModelModule().apply_association(
        NoDbCalls(), [g], settings, preview, lambda _m: None, output_g_dir=out
    )
    output = Path(result['copied_files'][0])
    assert f'facID="{FEEDER_ID}"' in output.read_text(encoding='utf-8')
    assert result['applied_count'] == 1
    assert result['database_created_count'] == 0


def test_feeder_settings_ui_exposes_explicit_drawing_type_choice():
    src = Path('src/dmm/ui/widgets/feeder_settings.py').read_text(encoding='utf-8')
    assert '图纸类型确认' in src
    assert '强制单馈线图（本次文件/目录）' in src
    assert '强制组合图（本次文件/目录）' in src
    assert 'feeder_drawing_mode' in src
