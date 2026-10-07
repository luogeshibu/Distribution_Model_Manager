from pathlib import Path

from dmm.application.modules.master_station import MasterStationModelModule, KEYID_STEP


def _write_g(path: Path):
    path.write_text(
        '<G><Layer>'
        '<rect id="frame1" x="100" y="100" w="220" h="220"/>'
        '<Bus id="bus1" x="145" y="135" w="130" h="6" keyid=""/>'
        '<Bus id="bus2" x="270" y="135" w="6" h="6" keyid=""/>'
        '<CBreaker id="cb1" x="180" y="180" w="40" h="40" keyid=""/>'
        '<Text id="title1" x="150" y="55" w="120" h="30" ts="ARF2-07" '
        'lc="255,255,255" lcc="#ffffff"/>'
        '</Layer></G>',
        encoding='utf-8',
    )
    return path


class _StationOnlyBusDB:
    def find_stations_by_name_hint(self, hint, table_id=405):
        return [{'id': 10, 'code': 'ARF2', 'name': 'ARF2', 'bv_id': 100}]

    def get_bays_by_station(self, station_id, table_id=406):
        return [{'id': 900, 'code': 'ARF2-07', 'name': '07', 'st_id': 10, 'bv_id': 100, 'vl_id': 200}]

    def get_feeders_by_station(self, station_id, table_id=13500):
        return [{'id': 77, 'code': '07', 'name': '07', 'graph_name': 'ARF2-07', 'st_id': 10}]

    def get_devices_by_bay(self, table_id, bay_id):
        # Only breaker needs BAY_ID.  Table 410 must not use this path.
        assert int(table_id) == 407
        return 'breaker', [
            {'id': 7001, 'code': 'B1', 'name': 'Breaker', 'st_id': 10, 'bay_id': 900, 'bv_id': 100},
        ]

    def get_devices_by_station(self, table_id, station_id):
        assert int(table_id) == 410
        assert int(station_id) == 10
        # Deliberately use unrelated BAY_ID values.  Bus association must ignore them.
        return 'busbarsection', [
            {'id': 10001, 'code': 'AHBB1', 'name': 'AHBB1', 'st_id': 10, 'bay_id': 111, 'bv_id': 100},
            {'id': 10002, 'code': 'AHBB2', 'name': 'AHBB2', 'st_id': 10, 'bay_id': 222, 'bv_id': 100},
            # Extra same-station row is allowed; only as many rows as graphical Bus elements are consumed.
            {'id': 10003, 'code': 'AHBB3', 'name': 'AHBB3', 'st_id': 10, 'bay_id': 333, 'bv_id': 100},
        ]

    def verify_keyid(self, keyid):
        keyid = int(keyid)
        device_id = keyid - 40 * KEYID_STEP
        table_id = 407 if device_id == 7001 else 410
        return {'device_id': device_id, 'tab_no': table_id, 'col_no': 40}


def test_bus_uses_station_only_and_ignores_bay_id(tmp_path):
    report = MasterStationModelModule()._analyze_file(
        _StationOnlyBusDB(), _write_g(tmp_path / 'bus.g'), {}, None
    )
    bus_rows = [row for row in report['master_station_rows'] if row['object_type'] == 'Bus']

    assert len(bus_rows) == 2
    assert [row['db_device_id'] for row in bus_rows] == [10001, 10002]
    assert all(row['context_station_id'] == 10 for row in bus_rows)
    assert all(row['context_bay_id'] == 900 for row in bus_rows)  # context may exist, but is not checked for Bus
    assert all(row['association_ready'] == 'YES' for row in bus_rows)
    assert all(row['writeback_needed'] == 'YES' for row in bus_rows)
    assert all(row['reason'] == 'MASTER_STATION_BUS_ASSOCIATION_READY_BY_STATION' for row in bus_rows)


def test_bus_station_pool_only_requires_enough_records(tmp_path):
    db = _StationOnlyBusDB()
    table_name, rows = db.get_devices_by_station(410, 10)
    assert table_name == 'busbarsection'
    assert len(rows) == 3

    report = MasterStationModelModule()._analyze_file(
        db, _write_g(tmp_path / 'bus_extra_db_rows.g'), {}, None
    )
    bus_rows = [row for row in report['master_station_rows'] if row['object_type'] == 'Bus']
    assert len(bus_rows) == 2
    assert {row['db_device_id'] for row in bus_rows} == {10001, 10002}
