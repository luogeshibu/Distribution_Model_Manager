
from pathlib import Path

from dmm.application.modules.feeder_context import resolve_drawing_feeder
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import _rmu_feeder_overview


class HierarchyDB:
    def __init__(self, station_name="ADF", feeder_name="AH334", control_path="JED CTL"):
        self.station_name = station_name
        self.feeder_name = feeder_name
        self.control_path = control_path
        self.calls = []

    def find_substations_by_name(self, name, table_id=405):
        self.calls.append(("station", name, table_id))
        if name != self.station_name:
            return []
        return [{
            "id": 405334,
            "name": self.station_name,
            "subarea_id": 40421,
            "bv_id": 123,
        }]

    def get_subcontrolarea_info(self, subarea_id, table_id=404):
        self.calls.append(("subarea", int(subarea_id), table_id))
        if int(subarea_id) != 40421:
            return None
        return {
            "id": 40421,
            "code": "JED-CTL",
            "father_id": 40401,
            "parent_code": "JED",
            "path": self.control_path,
        }

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        self.calls.append(("feeder", int(station_id), feeder_name, table_id))
        if int(station_id) == 405334 and feeder_name == self.feeder_name:
            return [{
                "id": 13500334,
                "name": self.feeder_name,
                "st_id": 405334,
                "graph_name": "",
            }]
        return []

    def get_feeder_info(self, feeder_id, table_id=13500):
        # Deliberately return an incomplete generic record.  v4.2.6 must
        # enrich it from the already-verified 405 -> 404 -> 13500 chain.
        if int(feeder_id) != 13500334:
            return None
        return {
            "id": 13500334,
            "name": self.feeder_name,
            "st_id": 405334,
        }


def _parse(tmp_path: Path, name: str):
    path = tmp_path / name
    path.write_text("<G><Layer/></G>", encoding="utf-8")
    return GParser().parse(path)


def test_adf_34_resolves_full_database_hierarchy(tmp_path):
    db = HierarchyDB()
    result = resolve_drawing_feeder(
        db, _parse(tmp_path, "JED-CTL-ADF-34.sln.pic.g")
    )

    assert result["ready"] is True
    assert result["feeder_id"] == 13500334
    assert result["feeder"]["subcontrolarea_path"] == "JED CTL"
    assert result["feeder"]["station_name"] == "ADF"
    assert result["feeder"]["name"] == "AH334"
    assert result["feeder"]["display_name"] == "JED CTL ADF AH334"
    assert ("subarea", 40421, 404) in db.calls
    assert ("feeder", 405334, "AH334", 13500) in db.calls
    assert "405.SUBAREA_ID=40421" in result["feeder_evidence"]
    assert "subcontrolarea_path=JED CTL" in result["feeder_evidence"]


def test_ag04_resolves_ag404_inside_mdn_station(tmp_path):
    db = HierarchyDB(
        station_name="MDN",
        feeder_name="AG404",
        control_path="JED NTH",
    )
    result = resolve_drawing_feeder(
        db, _parse(tmp_path, "JED-XXX-MDN-AG04.sln.pic.g")
    )

    assert result["ready"] is True
    assert result["feeder"]["name"] == "AG404"
    assert result["feeder"]["display_name"] == "JED NTH MDN AG404"
    assert ("feeder", 405334, "AG404", 13500) in db.calls
    assert "filename_token=AG04" in result["feeder_evidence"]
    assert "program_prefix=AG4" in result["feeder_evidence"]


def test_html_feeder_overview_shows_database_hierarchy_columns():
    html = _rmu_feeder_overview([{
        "file_name": "JED-CTL-ADF-34.sln.pic.g",
        "feeder_context_ready": "YES",
        "feeder_resolution_source": "FILENAME_405_13500",
        "feeder_id": "13500334",
        "subcontrolarea_path": "JED CTL",
        "station_name": "ADF",
        "feeder_db_name": "AH334",
        "feeder_name": "JED CTL ADF AH334",
    }], english=False)

    assert "调控区域" in html
    assert "厂站" in html
    assert "13500馈线NAME" in html
    assert "数据库验证馈线全名" in html
    assert "JED CTL" in html
    assert "ADF" in html
    assert "AH334" in html
    assert "JED CTL ADF AH334" in html


def test_subcontrolarea_path_falls_back_to_name_when_code_is_empty():
    from dmm.infrastructure.database.oracle import OracleClient

    client = OracleClient.__new__(OracleClient)
    client.get_table_name = lambda table_id: "subcontrolarea"
    client._query = lambda sql, binds=None: [{
        "id": 40421,
        "code": None,
        "name": "JED-CTL",
        "father_id": 40401,
        "parent_id": 40401,
        "parent_code": None,
        "parent_name": "JED",
    }]

    row = OracleClient.get_subcontrolarea_info(client, 40421)
    assert row["path"] == "JED CTL"


def test_get_feeder_info_builds_full_path_from_station_subarea():
    from dmm.infrastructure.database.oracle import OracleClient

    client = OracleClient.__new__(OracleClient)
    client.get_table_name = lambda table_id: {13500: "dms_feeder_device", 405: "substation", 404: "subcontrolarea"}[int(table_id)]
    client._query = lambda sql, binds=None: [{
        "id": 13500334,
        "code": None,
        "name": "AH334",
        "st_id": 405334,
        "graph_name": None,
        "station_name": "ADF",
        "station_bv_id": 123,
        "station_subarea_id": 40421,
    }]
    client.get_subcontrolarea_info = lambda subarea_id, table_id=404: {
        "id": 40421,
        "path": "JED CTL",
    }

    row = OracleClient.get_feeder_info(client, 13500334)
    assert row["subcontrolarea_path"] == "JED CTL"
    assert row["station_name"] == "ADF"
    assert row["name"] == "AH334"
    assert row["display_name"] == "JED CTL ADF AH334"
