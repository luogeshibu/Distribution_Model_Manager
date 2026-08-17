
from pathlib import Path
from dmm.application.modules.feeder import FeederModelModule

class DB:
    def get_feeder_info(self, feeder_id, table_id=13500):
        return {
            "id": feeder_id, "name": "07",
            "st_id": 113997365567815688,
            "station_name": "AJWD",
            "station_bv_id": 999999,
            "display_name": "AJWD 07",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        assert station_id == 113997365567815688
        return {
            "voltagelevel_id": 113152940637683730,
            "voltagelevel_name": "AJWD/13.8kV",
            "st_id": station_id,
            "bv_id": 112871465660973067,
            "basevoltage_name": "13.8kV",
            "nomvol": 13.8,
        }

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", []

def test_creation_plan_uses_voltagelevel_bv_not_substation_bv():
    report = {
        "g_file": "/tmp/AJWD-07.g",
        "feeder_id": 700,
        "feeder_name": "AJWD 07",
        "feedline_rows": [{
            "order_index": 1, "xml_id": "f1", "ls": "2",
            "reason": "SECTION_NOT_AVAILABLE", "model_linked": "NO",
        }],
    }
    result = FeederModelModule()._augment_section_creation_plan(
        DB(), report,
        {"auto_create_missing_sections": True,
         "feeder_table_id": 13500, "section_table_id": 13503},
        lambda _msg: None,
    )
    plan = result["section_create_plan"][0]
    assert plan["bv_id"] == 112871465660973067
    assert plan["bv_id"] != 999999
    assert result["section_nominal_voltage_kv"] == 13.8

def test_oracle_query_selects_lowest_of_13_8_33_110():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/infrastructure/database/oracle.py"
    ).read_text(encoding="utf-8")
    assert "self.get_table_name(402)" in source
    assert "self.get_table_name(401)" in source
    assert "ON bv.id = vl.bv_id" in source
    assert "vl.st_id = :station_id" in source
    assert "bv.nomvol - 13.8" in source
    assert "bv.nomvol - 33.0" in source
    assert "bv.nomvol - 110.0" in source
    assert "ORDER BY bv.nomvol ASC" in source
