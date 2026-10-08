from pathlib import Path

from dmm.application.modules.feeder_context import (
    enforce_device_feeder_membership,
    resolve_drawing_feeder,
)
from dmm.domain.gfile.parser import GParser


class FilenameOnlyDB:
    def __init__(self, *, stations=None, feeders=None):
        self.stations = list(stations or [])
        self.feeders = list(feeders or [])
        self.calls = []

    # These must never be used to decide the drawing feeder in v4.1.101.
    def get_rmu_records(self, name):
        raise AssertionError("RMU must not participate in feeder resolution")

    def get_combined_device_records(self, name):
        raise AssertionError("Pole switch must not participate in feeder resolution")

    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        raise AssertionError("Transformer must not participate in feeder resolution")

    def find_substations_by_name(self, name, table_id=405):
        self.calls.append(("station", name, table_id))
        return [dict(x) for x in self.stations]

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        self.calls.append(("feeder", int(station_id), feeder_name, table_id))
        return [dict(x) for x in self.feeders]

    def get_feeder_info(self, feeder_id, table_id=13500):
        for row in self.feeders:
            if int(row.get("id")) == int(feeder_id):
                result = dict(row)
                result.setdefault("station_name", "ABH")
                result.setdefault("display_name", f"ABH {result.get('name', '')}".strip())
                return result
        return None


def _parse(tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_text("<G><Layer/></G>", encoding="utf-8")
    return GParser().parse(path)


def test_filename_is_only_feeder_source_and_resolves_abh03(tmp_path):
    parsed = _parse(tmp_path, "JED-NTH-ABH-03.sln.pic.g")
    db = FilenameOnlyDB(
        stations=[{"id": 113997365567815681, "name": "ABH"}],
        feeders=[{
            "id": 3799912185593857738,
            "name": "AH303",
            "code": None,
            "st_id": 113997365567815681,
        }],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is True
    assert result["feeder_id"] == 3799912185593857738
    assert result["feeder_source"] == "FILENAME_405_13500"
    assert db.calls == [
        ("station", "ABH", 405),
        ("feeder", 113997365567815681, "AH303", 13500),
    ]


def test_filename_area_must_be_three_letters_and_jed_prefix(tmp_path):
    db = FilenameOnlyDB()
    for name in (
        "ABH-03.sln.pic.g",
        "JED-N-ABH-03.sln.pic.g",
        "JED-NORTH-ABH-03.sln.pic.g",
    ):
        result = resolve_drawing_feeder(db, _parse(tmp_path, name))
        assert result["ready"] is False
        assert result["feeder_source"] == "FILENAME_INVALID"
        assert "请先修改文件名" in result["reason"]
    assert db.calls == []


def test_missing_13500_feeder_has_operator_facing_message(tmp_path):
    parsed = _parse(tmp_path, "JED-NTH-ABH-04.sln.pic.g")
    db = FilenameOnlyDB(
        stations=[{"id": 40501, "name": "ABH"}],
        feeders=[],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is False
    assert result["feeder_source"] == "FILENAME_13500_NOT_FOUND"
    assert "馈线不存在，请检查该图的馈线是否已创建" in result["reason"]
    assert ("feeder", 40501, "AH304", 13500) in db.calls


def test_other_device_must_belong_to_filename_resolved_feeder(tmp_path):
    parsed = _parse(tmp_path, "JED-NTH-ABH-16.sln.pic.g")
    db = FilenameOnlyDB(
        stations=[{"id": 40516, "name": "ABH"}],
        feeders=[{"id": 316, "name": "AH316", "st_id": 40516}],
    )
    resolution = resolve_drawing_feeder(db, parsed)

    ok = enforce_device_feeder_membership(
        {"status": "UNLINKED"},
        resolution,
        device_feeder_id=316,
        reason_prefix="TEST",
    )
    bad = enforce_device_feeder_membership(
        {"status": "UNLINKED"},
        resolution,
        device_feeder_id=999,
        reason_prefix="TEST",
    )

    assert ok["feeder_membership_verified"] == "YES"
    assert bad["status"] == "FAIL"
    assert bad["association_ready"] == "NO"
    assert "FEEDER_ID" in bad["reason"]
