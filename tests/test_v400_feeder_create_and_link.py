
from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule


class FakeFeederDB:
    def __init__(self):
        self.feeder = {
            "id": 3799912185593856228,
            "name": "16",
            "st_id": 113997365567815684,
            "station_name": "ADF",
            "station_bv_id": 112871465660973067,
            "display_name": "ADF 16",
        }

    def get_feeder_info(self, feeder_id, table_id=13500):
        if int(feeder_id) == int(self.feeder["id"]):
            return dict(self.feeder)
        return None

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        return [dict(self.feeder)] if "ADF16" in str(hint) else []

    def get_preferred_feeder_section_voltage(self, station_id):
        assert int(station_id) == int(self.feeder["st_id"])
        return {
            "voltagelevel_name": "ADF/13.8kV",
            "bv_id": 112871465660973067,
            "basevoltage_name": "13.8kV",
            "nomvol": 13.8,
        }

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [
            {
                "id": 101,
                "name": "ADF_16_SEC001",
                "feeder_id": feeder_id,
                "bv_id": 112871465660973067,
                "section_type": 0,
            }
        ]


def test_facid_is_first_class_feeder_source(tmp_path):
    g = tmp_path / "JED-CTL-ADF-16.sln.pic.g"
    g.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<G facID="3799912185593856228"><Layer>
<FeedLine id="f1" ls="2" x="1" y="1" w="10" h="1"/>
</Layer></G>""",
        encoding="utf-8",
    )
    logs = []
    row = FeederModelModule()._resolve_file_feeder(
        FakeFeederDB(),
        g,
        {
            "feeder_resolution_mode": "FACID",
            "feeder_table_id": 13500,
        },
        logs.append,
    )
    assert row["id"] == 3799912185593856228
    assert row["_resolution_source"] == "FACID_FORCED"


def test_section_type_mapping_is_exact():
    module = FeederModelModule()
    assert module._section_type_from_ls("2") == 0
    assert module._section_type_from_ls("1") == 1
    assert module._section_type_from_ls("") == 3
    assert module._section_type_from_ls(None) == 3
    assert module._section_type_from_ls("4") == 0


def test_writeback_attributes_are_exactly_five_fields():
    attrs = FeederModelModule()._attributes_for_row(
        {
            "xml_id": "f1",
            "assigned_bv_id": 112871465660973067,
            "expected_keyid": 3800760905491280000,
        }
    )
    assert set(attrs) == {
        "app",
        "p_ReportType",
        "state",
        "voltype",
        "keyid",
    }
    assert attrs["app"] == "6500000"
    assert attrs["p_ReportType"] == "1"
    assert attrs["state"] == "20"
    assert attrs["voltype"] == "112871465660973067"


def test_oracle_allocator_uses_d5000_area_zero_scheme():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/infrastructure/database/oracle.py"
    ).read_text(encoding="utf-8")
    assert "LOCK TABLE" in source
    assert "keyid_to_long3(:table_id, 0, :area_id, 0)" in source
    assert "TO_NUMBER('FFFFFF','XXXXXX')" in source
    assert "FROM deleted_record" in source
    assert "region_id = :area_id" in source
    assert "record_app4" in source


def test_feeder_ui_exposes_resolution_and_create_controls():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/ui/widgets/feeder_settings.py"
    ).read_text(encoding="utf-8")
    assert "馈线识别方式" in source
    assert "仅使用 G 根节点 facID" in source
    assert "仅使用文件名" in source
    assert "人工输入" in source
    assert "自动创建数据库中缺失的馈线段" in source
