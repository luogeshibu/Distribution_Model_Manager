from pathlib import Path

from dmm.application.modules.feeder_context import resolve_drawing_feeder
from dmm.domain.gfile.parser import GParser


class FilenameDB:
    def __init__(self, *, stations=None, feeders=None):
        self.stations = list(stations or [])
        self.feeders = list(feeders or [])
        self.calls = []

    def find_substations_by_name(self, name, table_id=405):
        self.calls.append(("station", name, table_id))
        return [dict(row) for row in self.stations]

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        self.calls.append(("feeder", int(station_id), feeder_name, table_id))
        return [dict(row) for row in self.feeders]

    def get_feeder_info(self, feeder_id, table_id=13500):
        for row in self.feeders:
            if int(row.get("id")) == int(feeder_id):
                result = dict(row)
                result.setdefault("station_name", "MDN")
                result.setdefault("display_name", f"MDN {result.get('name', '')}".strip())
                return result
        return None


def _parse(tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_text("<G><Layer/></G>", encoding="utf-8")
    return GParser().parse(path)


def test_ag06_filename_resolves_mdn_station_and_ag406_feeder(tmp_path):
    parsed = _parse(tmp_path, "JED-XXX-MDN-AG06.sln.pic.g")
    db = FilenameDB(
        stations=[{"id": 40506, "name": "MDN"}],
        feeders=[{"id": 13500406, "name": "AG406", "st_id": 40506}],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is True
    assert result["feeder_id"] == 13500406
    assert result["feeder_source"] == "FILENAME_405_13500"
    assert db.calls == [
        ("station", "MDN", 405),
        ("feeder", 40506, "AG406", 13500),
    ]
    assert "filename_token=AG06" in result["feeder_evidence"]
    assert "program_prefix=AG4" in result["feeder_evidence"]
    assert "13500.NAME=AG406" in result["feeder_evidence"]


def test_legacy_two_digit_filename_still_builds_ah3xx(tmp_path):
    parsed = _parse(tmp_path, "JED-NTH-ABH-06.sln.pic.g")
    db = FilenameDB(
        stations=[{"id": 40501, "name": "ABH"}],
        feeders=[{"id": 306, "name": "AH306", "st_id": 40501}],
    )

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is True
    assert ("feeder", 40501, "AH306", 13500) in db.calls
    assert "filename_token=06" in result["feeder_evidence"]
    assert "program_prefix=AH3" in result["feeder_evidence"]


def test_ag_token_requires_exactly_two_digits(tmp_path):
    db = FilenameDB()
    for name in (
        "JED-XXX-MDN-AG6.sln.pic.g",
        "JED-XXX-MDN-AG006.sln.pic.g",
        "JED-XXX-MDN-AGXX.sln.pic.g",
    ):
        result = resolve_drawing_feeder(db, _parse(tmp_path, name))
        assert result["ready"] is False
        assert result["feeder_source"] == "FILENAME_INVALID"
    assert db.calls == []


def test_ag_lookup_not_found_keeps_existing_feeder_not_created_message(tmp_path):
    parsed = _parse(tmp_path, "JED-XXX-MDN-AG06.sln.pic.g")
    db = FilenameDB(stations=[{"id": 40506, "name": "MDN"}], feeders=[])

    result = resolve_drawing_feeder(db, parsed)

    assert result["ready"] is False
    assert result["feeder_source"] == "FILENAME_13500_NOT_FOUND"
    assert "NAME=AG406" in result["reason"]
    assert "馈线不存在，请检查该图的馈线是否已创建" in result["reason"]
