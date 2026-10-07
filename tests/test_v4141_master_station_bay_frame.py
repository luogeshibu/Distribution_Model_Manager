from pathlib import Path

from dmm.application.modules.master_station import MasterStationModelModule, KEYID_STEP
from dmm.domain.feeder.ownership import FeederOwnershipResolver
from dmm.domain.gfile.master_station_frames import find_master_station_frames
from dmm.domain.gfile.parser import GParser


def write_g(path: Path, inner: str):
    path.write_text(f'<G><Layer>{inner}</Layer></G>', encoding='utf-8')
    return path


def main_frame_xml(label='ARF2-07', *, label_lc='255,255,255', label_bg=''):
    label_lcc = '#ffffff' if label_lc.replace(' ', '') == '255,255,255' else '#ff0000'
    bg = f' background="{label_bg}"' if label_bg != '' else ''
    return (
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40" keyid=""/>'
        '<Disconnector id="d1" x="180" y="230" w="40" h="40" keyid=""/>'
        '<GroundDisconnector id="g1" x="230" y="230" w="40" h="40" keyid=""/>'
        f'<Text id="title1" x="150" y="55" w="120" h="30" ts="{label}" '
        f'lc="{label_lc}" lcc="{label_lcc}"{bg}/>'
    )


def test_master_station_frame_requires_cbreaker_and_uses_nearest_no_background_label_regardless_of_color(tmp_path):
    g = write_g(
        tmp_path / 'frame.g',
        '<rect id="outer" x="0" y="0" w="500" h="500"/>'
        + main_frame_xml()
        # Closer-looking annotations that must not become the Bay title.
        + '<Text id="red" x="170" y="86" w="100" h="20" ts="ARF2-99" lc="255,0,0"/>'
        + '<Text id="bg" x="180" y="87" w="100" h="20" ts="MNA4-12" lc="255,255,255" background="1"/>'
        # A rectangle without CBreaker is not a master-station Bay frame.
        + '<rect id="not_bay" x="600" y="100" w="220" h="220"/>'
        + '<Disconnector id="d2" x="650" y="160" w="40" h="40"/>'
        + '<Text id="title2" x="650" y="55" w="120" h="30" ts="MNA4-12" lc="255,255,255"/>'
    )
    frames = find_master_station_frames(GParser().parse(g))
    assert len(frames) == 1
    assert frames[0].frame.xml_id == 'frame1'
    assert frames[0].breaker.xml_id == 'cb1'
    assert frames[0].feeder_label == 'ARF2-99'
    assert frames[0].station_hint == 'ARF2'
    assert frames[0].feeder_hint == '99'
    assert frames[0].label_obj.xml_id == 'red'


def test_red_only_caption_is_used_as_source_anchor(tmp_path):
    g = write_g(
        tmp_path / 'red.g',
        main_frame_xml('BHA-58', label_lc='255,0,0'),
    )

    class DB:
        def find_feeders_by_name_hint(self, hint, table_id=13500):
            assert hint == 'BHA-58'
            assert int(table_id) == 13500
            return [{'id': 58, 'name': 'BHA-58'}]

    anchors = FeederOwnershipResolver(DB())._source_anchor_candidates(GParser().parse(g))
    assert len(anchors) == 1
    assert anchors[0]['status'] == 'SOURCE_CONFIRMED'
    assert anchors[0]['label'] == 'BHA-58'
    assert anchors[0]['feeder_id'] == 58


class BayDB:
    def __init__(self, duplicate_disconnector=False):
        self.duplicate_disconnector = duplicate_disconnector
        self.device_tables = {
            407: [
                {'id': 7001, 'code': 'B1', 'name': 'Breaker', 'st_id': 10, 'bay_id': 900, 'bv_id': 100},
            ],
            408: [
                {'id': 8001, 'code': 'D1', 'name': 'Disconnector', 'st_id': 10, 'bay_id': 900, 'bv_id': 100},
            ],
            409: [
                {'id': 9001, 'code': 'K1', 'name': 'Ground', 'st_id': 10, 'bay_id': 900, 'bv_id': 100},
            ],
        }
        if duplicate_disconnector:
            self.device_tables[408].append(
                {'id': 8002, 'code': 'D2', 'name': 'Disconnector 2', 'st_id': 10, 'bay_id': 900, 'bv_id': 100},
            )

    def find_stations_by_name_hint(self, hint, table_id=405):
        assert hint == 'ARF2'
        return [{'id': 10, 'code': '10', 'name': 'ARF2', 'bv_id': 100}]

    def get_feeders_by_station(self, station_id, table_id=13500):
        assert int(station_id) == 10
        return [
            {'id': 77, 'code': '07', 'name': '07', 'graph_name': 'ARF2-07', 'st_id': 10},
        ]

    def get_bays_by_station(self, station_id, table_id=406):
        assert int(station_id) == 10
        return [
            {'id': 900, 'code': 'ARF2-07', 'name': '07', 'st_id': 10, 'bv_id': 100, 'vl_id': 200},
        ]

    def get_devices_by_bay(self, table_id, bay_id):
        assert int(bay_id) == 900
        return {407: 'breaker', 408: 'disconnector', 409: 'grounddisconnector'}.get(int(table_id), 'unknown'), [
            dict(x) for x in self.device_tables.get(int(table_id), [])
        ]

    def verify_keyid(self, keyid):
        keyid = int(keyid)
        device_id = keyid - 40 * KEYID_STEP
        table_id = {7001: 407, 8001: 408, 8002: 408, 9001: 409}[device_id]
        return {'device_id': device_id, 'tab_no': table_id, 'col_no': 40}


def test_master_station_associates_frame_devices_directly_by_unique_bay_without_key_name(tmp_path):
    g = write_g(tmp_path / 'bay.g', main_frame_xml())
    report = MasterStationModelModule()._analyze_file(BayDB(), g, {}, None)

    rows = {row['object_type']: row for row in report['master_station_rows']}
    assert set(rows) == {'CBreaker', 'Disconnector', 'GroundDisconnector'}
    assert all(row['association_ready'] == 'YES' for row in rows.values())
    assert all(row['logical_code'] == '' for row in rows.values())
    assert all(int(row['context_bay_id']) == 900 for row in rows.values())
    assert rows['CBreaker']['db_device_id'] == 7001
    assert rows['Disconnector']['db_device_id'] == 8001
    assert rows['GroundDisconnector']['db_device_id'] == 9001
    assert report['association_context']['mode'] == 'cbreaker_frame_white_label_bay'


def test_same_bay_same_type_multiple_rows_is_blocked_instead_of_guessed(tmp_path):
    g = write_g(tmp_path / 'ambiguous.g', main_frame_xml())
    report = MasterStationModelModule()._analyze_file(
        BayDB(duplicate_disconnector=True), g, {}, None
    )
    row = next(
        item for item in report['master_station_rows']
        if item['object_type'] == 'Disconnector'
    )
    assert row['association_ready'] == 'NO'
    assert 'MASTER_STATION_BAY_DEVICE_NOT_UNIQUE' in row['reason']


def test_far_white_caption_is_not_borrowed_from_another_frame(tmp_path):
    g = write_g(
        tmp_path / 'far.g',
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40" keyid=""/>'
        '<Text id="far" x="600" y="600" w="120" h="30" ts="ARF2-07" lc="255,255,255"/>'
    )
    frame = find_master_station_frames(GParser().parse(g))[0]
    assert frame.feeder_label == ''
