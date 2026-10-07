from types import SimpleNamespace

from dmm.domain.rmu.validator import RmuValidator


class Candidate:
    def __init__(self, text='1001'):
        self.text = text
        self.direction = 'right'
        self.score = 10
        self.gap = 10
        self.color = ''
        self.is_green = False
        self.obj = SimpleNamespace(xml_id='TXT1', xml_index=1)


class Parser:
    def __init__(self, linked=False):
        self.linked = linked

    def find_label_candidates(self, parsed, frame, positions):
        return [Candidate()]

    def find_target_objects_in_frame(self, parsed, frame, tags):
        if not self.linked:
            return []
        return [SimpleNamespace(tag='CBreakerDis', keyid='900', attrs={}, xml_id='SW1')]


class DB:
    def __init__(self):
        self.rows = [
            {'id': 10, 'name': '1001', 'feeder_id': 111},
            {'id': 20, 'name': '1001', 'feeder_id': 222},
        ]

    def get_rmu_records(self, name, feeder_id=None):
        rows = [r for r in self.rows if r['name'] == name]
        if feeder_id is not None:
            rows = [r for r in rows if r['feeder_id'] == feeder_id]
        return rows

    def verify_keyid(self, keyid):
        return {'tab_no': 13502, 'device_id': 500}

    def get_device_by_id(self, table_id, device_id):
        return {'id': device_id, 'combined_id': 20}


def frame():
    return SimpleNamespace(
        frame=SimpleNamespace(xml_index=1, xml_id='FRAME1'),
        label_candidates=[],
    )


def validator(db, parser, force=False, feeder_id=111):
    return RmuValidator(
        db,
        parser,
        {'CBreakerDis': {'table_id': 13502, 'domain': 40}},
        feeder_context_by_frame={
            'FRAME1': {
                'topology_status': 'UNIQUE',
                'primary_feeder': 'GVCM-AH304',
                'feeder_id': feeder_id,
            }
        },
        force_rmu_feeder_correction=force,
    )


def test_unlinked_rmu_is_resolved_only_inside_topology_feeder():
    result = validator(DB(), Parser(linked=False), feeder_id=111)._resolve_rmu_name(
        object(), frame(), ('right',)
    )
    assert result['status'] == 'PASS'
    assert result['selected']['db_records'][0]['id'] == 10
    assert result['selected']['db_records'][0]['feeder_id'] == 111


def test_existing_wrong_feeder_requires_force_switch():
    result = validator(DB(), Parser(linked=True), force=False, feeder_id=333)._resolve_rmu_name(
        object(), frame(), ('right',)
    )
    assert result['status'] == 'FAIL'
    assert result['feeder_correction_needed'] is True
    assert 'FORCE_DISABLED' in result['reason']


def test_existing_wrong_feeder_can_be_preserved_for_safe_correction_when_forced():
    result = validator(DB(), Parser(linked=True), force=True, feeder_id=333)._resolve_rmu_name(
        object(), frame(), ('right',)
    )
    assert result['status'] == 'PASS'
    assert result['feeder_correction_needed'] is True
    assert result['selected']['db_records'][0]['id'] == 20
    assert result['current_feeder_id'] == 222
