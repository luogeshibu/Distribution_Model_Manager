from pathlib import Path

from dmm.application.modules.feeder_context import resolve_drawing_feeder
from dmm.domain.gfile.parser import GParser


class FilenameFallbackDB:
    def __init__(self, *, station_rows=None, feeder_rows=None):
        self.station_rows = list(station_rows or [])
        self.feeder_rows = list(feeder_rows or [])
        self.calls = []

    # Graphical candidate APIs: return nothing so filename fallback is reached.
    def get_rmu_records(self, name):
        return []

    def get_combined_device_records(self, name):
        return []

    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        return []

    def find_substations_by_name(self, name, table_id=405):
        self.calls.append(("station", name, table_id))
        return [dict(row) for row in self.station_rows]

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        self.calls.append(("feeder", int(station_id), feeder_name, table_id))
        return [dict(row) for row in self.feeder_rows]

    def get_feeder_info(self, feeder_id, table_id=13500):
        for row in self.feeder_rows:
            if int(row.get("id")) == int(feeder_id):
                value = dict(row)
                value.setdefault("station_name", "ABH")
                value.setdefault("display_name", f"ABH {value.get('name', '')}".strip())
                return value
        return None


def _empty_g(path: Path):
    path.write_text("<G><Layer/></G>", encoding="utf-8")
    return GParser().parse(path)


def test_strict_jeddah_filename_fallback_resolves_abh_03_to_ah303(tmp_path):
    parsed = _empty_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g")
    db = FilenameFallbackDB(
        station_rows=[{"id": 113997365567815681, "name": "ABH"}],
        feeder_rows=[{
            "id": 3799912185593870244,
            "name": "AH303",
            "code": "AH303",
            "st_id": 113997365567815681,
        }],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is True
    assert result["feeder_id"] == 3799912185593870244
    assert result["feeder_source"] == "FILENAME_405_13500"
    assert ("station", "ABH", 405) in db.calls
    assert ("feeder", 113997365567815681, "AH303", 13500) in db.calls
    assert "program_prefix=AH3" in result["feeder_evidence"]
    assert "filename_suffix=03" in result["feeder_evidence"]


def test_filename_fallback_adds_ah3_prefix_for_other_two_digit_suffix(tmp_path):
    parsed = _empty_g(tmp_path / "JED-CTL-ADF-16.sln.pic.g")
    db = FilenameFallbackDB(
        station_rows=[{"id": 40516, "name": "ADF"}],
        feeder_rows=[{"id": 1350016, "name": "AH316", "st_id": 40516}],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is True
    assert ("station", "ADF", 405) in db.calls
    assert ("feeder", 40516, "AH316", 13500) in db.calls


def test_invalid_filename_is_hard_error_when_filename_fallback_is_needed(tmp_path):
    parsed = _empty_g(tmp_path / "ABH-03.sln.pic.g")
    db = FilenameFallbackDB(
        station_rows=[{"id": 40501, "name": "ABH"}],
        feeder_rows=[{"id": 303, "name": "AH303", "st_id": 40501}],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is False
    assert result["feeder_source"] == "FILENAME_INVALID"
    assert "JED_FILENAME_INVALID" in result["reason"]
    assert "请先修改文件名" in result["reason"]
    assert db.calls == []


def test_405_station_must_be_exactly_one(tmp_path):
    parsed = _empty_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g")
    db = FilenameFallbackDB(
        station_rows=[
            {"id": 40501, "name": "ABH"},
            {"id": 40502, "name": "ABH"},
        ],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is False
    assert result["feeder_source"] == "FILENAME_405_NOT_UNIQUE"
    assert "匹配 2 条" in result["reason"]
    assert not any(call[0] == "feeder" for call in db.calls)


def test_13500_station_and_name_must_be_exactly_one(tmp_path):
    parsed = _empty_g(tmp_path / "JED-NTH-ABH-03.sln.pic.g")
    db = FilenameFallbackDB(
        station_rows=[{"id": 40501, "name": "ABH"}],
        feeder_rows=[
            {"id": 303, "name": "AH303", "st_id": 40501},
            {"id": 304, "name": "AH303", "st_id": 40501},
        ],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is False
    assert result["feeder_source"] == "FILENAME_13500_NOT_UNIQUE"
    assert "ST_ID=40501" in result["reason"]
    assert "NAME=AH303" in result["reason"]
    assert "匹配 2 条" in result["reason"]


def test_timestamped_snapshot_keeps_same_logical_filename_rule(tmp_path):
    parsed = _empty_g(tmp_path / "JED-NTH-ABH-03.sln.pic(20260930-093900).g")
    db = FilenameFallbackDB(
        station_rows=[{"id": 40501, "name": "ABH"}],
        feeder_rows=[{"id": 303, "name": "AH303", "st_id": 40501}],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is True
    assert result["feeder_id"] == 303
