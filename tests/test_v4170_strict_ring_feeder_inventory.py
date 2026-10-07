from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.ring_discovery import discover_makkah_ring_feeders
from dmm.domain.gfile.master_station_frames import parse_master_feeder_label


class StrictRingDB:
    def __init__(self):
        self.stations = {
            "GVCM": {"id": 101, "name": "GVCM", "code": "GVCM"},
            "ARF4": {"id": 102, "name": "ARF4", "code": "ARF4"},
        }
        self.feeders = {
            101: [
                {"id": 1001, "name": "AH304", "code": "AH304", "st_id": 101},
                {"id": 1002, "name": "AH999", "code": "AH999", "st_id": 101},
            ],
            102: [
                {"id": 2001, "name": "AH348", "code": "AH348", "st_id": 102},
                {"id": 2002, "name": "AH3101", "code": "AH3101", "st_id": 102},
            ],
        }

    def find_stations_by_name_hint(self, hint, table_id=405):
        # Deliberately include a suffix false-positive to prove the strict
        # ring resolver only accepts station.NAME exact normalization.
        rows = []
        if str(hint).upper() == "GVCM":
            rows.append({"id": 999, "name": "MAK GVCM", "code": "X"})
        row = self.stations.get(str(hint).strip().upper())
        if row:
            rows.append(dict(row))
        return rows

    def get_feeders_by_station(self, station_id, table_id=13500):
        return [dict(row) for row in self.feeders.get(int(station_id), [])]

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", []

    def get_preferred_feeder_section_voltage(self, station_id):
        return {"bv_id": 91, "nomvol": 13.8}


def _write_ring(path: Path):
    path.write_text(
        '''<G facID=""><Layer>
        <Rect id="r1" x="0" y="0" w="300" h="140"/>
        <CBreaker id="b1" x="20" y="20" w="20" h="20"/>
        <Text id="t1" x="305" y="20" w="240" h="30" ts="GVCM-AH304" lc="255,255,255"/>
        <Rect id="r2" x="800" y="0" w="300" h="140"/>
        <CBreaker id="b2" x="820" y="20" w="20" h="20"/>
        <Text id="t2" x="1105" y="20" w="240" h="30" ts="ARF4-AH348" lc="255,255,255"/>
        <Rect id="r3" x="1600" y="0" w="300" h="140"/>
        <CBreaker id="b3" x="1620" y="20" w="20" h="20"/>
        <Text id="t3" x="1905" y="20" w="240" h="30" ts="ARF4-AH3101" lc="255,255,255"/>
        <FeedLine id="f1" x="0" y="300" w="100" h="5" ls="2"/>
        <FeedLine id="f2" x="0" y="400" w="100" h="5" ls="2"/>
        </Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_master_title_parser_supports_full_feeder_code():
    assert parse_master_feeder_label("GVCM-AH304") == (
        "GVCM-AH304", "GVCM", "AH304"
    )
    assert parse_master_feeder_label("ARF4-AH3101") == (
        "ARF4-AH3101", "ARF4", "AH3101"
    )
    assert parse_master_feeder_label("SHM1-AH341_X") == (
        "SHM1-AH341_X", "SHM1", "AH341_X"
    )
    assert parse_master_feeder_label("SHM1-AH341_Y") == (
        "SHM1-AH341_Y", "SHM1", "AH341_Y"
    )


def test_strict_ring_inventory_uses_station_then_st_id(tmp_path):
    g = _write_ring(tmp_path / "ring.g")
    logs = []
    rows = discover_makkah_ring_feeders(
        StrictRingDB(), g, log_callback=logs.append
    )
    assert [row["id"] for row in rows] == [1001, 2001, 2002]
    assert [row["st_id"] for row in rows] == [101, 102, 102]
    assert [row["_ring_feeder_hint"] for row in rows] == [
        "AH304", "AH348", "AH3101"
    ]
    assert any("GVCM-AH304" in line and "ST_ID=101" in line for line in logs)
    assert any("ARF4-AH3101" in line and "FEEDER_ID=2002" in line for line in logs)


def test_feeder_model_selects_first_from_complete_inventory(tmp_path):
    g = _write_ring(tmp_path / "ring.g")
    logs = []
    selected, candidates = FeederModelModule()._resolve_any_ring_feeder(
        StrictRingDB(), g, {"feeder_table_id": 13500}, logs.append
    )
    assert selected["id"] == 1001
    assert [row["id"] for row in candidates] == [1001, 2001, 2002]
    assert any("全部 FeedLine" in line for line in logs)


def test_job_worker_has_global_ring_inventory_hook():
    source = Path("src/dmm/application/job_worker.py").read_text(encoding="utf-8")
    assert "compare_makkah_ring_feeders_for_files" in source
    assert "attach_makkah_ring_feeder_inventory" in source
    assert "正在整理当前图形馈线及数据库对比结果" in source
