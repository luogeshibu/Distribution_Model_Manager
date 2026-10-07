from pathlib import Path

from dmm.application.modules.master_station import MasterStationModelModule, KEYID_STEP
from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES


def _write_g(path: Path, inner: str):
    path.write_text(f'<G><Layer>{inner}</Layer></G>', encoding='utf-8')
    return path


def _frame_with_two_bus_pieces():
    return (
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<Bus id="bus1" x="145" y="135" w="130" h="6" keyid="" '
        'key_name="busbarsection ARF2 AHBB1 AHBB1 id"/>'
        '<Bus id="bus2" x="270" y="135" w="6" h="6" keyid=""/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40" keyid=""/>'
        '<Disconnector id="d1" x="180" y="230" w="40" h="40" keyid=""/>'
        '<GroundDisconnector id="g1" x="230" y="230" w="40" h="40" keyid=""/>'
        '<Text id="title1" x="150" y="55" w="120" h="30" ts="ARF2-07" '
        'lc="255,255,255" lcc="#ffffff"/>'
    )


def _frame_with_one_bus():
    return _frame_with_two_bus_pieces().replace('<Bus id="bus2" x="270" y="135" w="6" h="6" keyid=""/>', '')


class _BusBayDB:
    def __init__(self, duplicate_bus=False):
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
            410: [
                {'id': 10001, 'code': 'AHBB1', 'name': 'AHBB1', 'st_id': 10, 'bay_id': 900, 'bv_id': 100},
            ],
        }
        if duplicate_bus:
            self.device_tables[410].append(
                {'id': 10002, 'code': 'AHBB2', 'name': 'AHBB2', 'st_id': 10, 'bay_id': 900, 'bv_id': 100}
            )

    def find_stations_by_name_hint(self, hint, table_id=405):
        assert hint == 'ARF2'
        return [{'id': 10, 'code': '10', 'name': 'ARF2', 'bv_id': 100}]

    def get_feeders_by_station(self, station_id, table_id=13500):
        return [{'id': 77, 'code': '07', 'name': '07', 'graph_name': 'ARF2-07', 'st_id': 10}]

    def get_bays_by_station(self, station_id, table_id=406):
        return [{'id': 900, 'code': 'ARF2-07', 'name': '07', 'st_id': 10, 'bv_id': 100, 'vl_id': 200}]

    def get_devices_by_bay(self, table_id, bay_id):
        assert int(bay_id) == 900
        names = {407: 'breaker', 408: 'disconnector', 409: 'grounddisconnector', 410: 'busbarsection'}
        return names.get(int(table_id), 'unknown'), [dict(x) for x in self.device_tables.get(int(table_id), [])]

    def verify_keyid(self, keyid):
        keyid = int(keyid)
        device_id = keyid - 40 * KEYID_STEP
        table_id = {
            7001: 407,
            8001: 408,
            9001: 409,
            10001: 410,
            10002: 410,
        }[device_id]
        return {'device_id': device_id, 'tab_no': table_id, 'col_no': 40}


def test_master_station_bus_rule_is_410_domain40():
    rule = DEFAULT_MASTER_STATION_RULES['Bus']
    assert rule['table_id'] == 410
    assert rule['domain'] == 40
    assert rule['table_name'] == 'busbarsection'


def test_single_bus_uses_unique_410_record_in_same_bay(tmp_path):
    g = _write_g(tmp_path / 'bus.g', _frame_with_one_bus())
    report = MasterStationModelModule()._analyze_file(_BusBayDB(), g, {}, None)
    bus_rows = [row for row in report['master_station_rows'] if row['object_type'] == 'Bus']

    assert len(bus_rows) == 1
    assert bus_rows[0]['table_id'] == 410
    assert bus_rows[0]['configured_domain'] == 40
    assert bus_rows[0]['context_bay_id'] == 900
    assert bus_rows[0]['db_device_id'] == 10001
    assert bus_rows[0]['expected_keyid'] == 10001 + 40 * KEYID_STEP
    assert bus_rows[0]['association_ready'] == 'YES'
    assert bus_rows[0]['writeback_needed'] == 'YES'


def test_two_bus_graphics_pair_arbitrarily_with_two_410_records(tmp_path):
    g = _write_g(tmp_path / 'bus_ambiguous.g', _frame_with_two_bus_pieces())
    report = MasterStationModelModule()._analyze_file(_BusBayDB(duplicate_bus=True), g, {}, None)
    bus_rows = [row for row in report['master_station_rows'] if row['object_type'] == 'Bus']

    assert len(bus_rows) == 2
    assert [row['db_device_id'] for row in bus_rows] == [10001, 10002]
    assert len({row['expected_keyid'] for row in bus_rows}) == 2
    assert all(row['association_ready'] == 'YES' for row in bus_rows)
    assert all(row['writeback_needed'] == 'YES' for row in bus_rows)


def test_bus_count_mismatch_is_blocked(tmp_path):
    g = _write_g(tmp_path / 'bus_mismatch.g', _frame_with_two_bus_pieces())
    db = _BusBayDB(duplicate_bus=False)
    report = MasterStationModelModule()._analyze_file(db, g, {}, None)
    bus_rows = [row for row in report['master_station_rows'] if row['object_type'] == 'Bus']

    assert len(bus_rows) == 2
    assert all(row['association_ready'] == 'NO' for row in bus_rows)
    assert all('MASTER_STATION_BUS_COUNT_MISMATCH' in row['reason'] for row in bus_rows)


def test_bus_writeback_matches_existing_main_network_bus_attributes():
    attrs = MasterStationModelModule._attributes_for_row({
        'object_type': 'Bus',
        'xml_id': 'bus1',
        'db_bv_id': '112871465660973067',
        'expected_keyid': 123456789,
    })
    assert attrs == {
        'app': '100000',
        'voltype': '112871465660973067',
        'p_ReportType': '1',
        'state': '10',
        'keyid': '123456789',
    }


def test_graphics_poke_is_selected_from_graphics_workspace_type_combo():
    source = (Path(__file__).parents[1] / 'src' / 'dmm' / 'ui' / 'main_window.py').read_text(encoding='utf-8')
    assert '("图形工作区", 3)' in source
    assert 'self.graphics_operation_combo.addItem("Poke 跳转处理", "POKE")' in source
    assert 'self.nav.currentRowChanged.connect(self._on_nav_row_changed)' in source
