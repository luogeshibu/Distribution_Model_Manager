from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import (
    export_csv_bundle,
    export_html_bundle,
)


DOMAIN = 1
TABLE_ID = 13503
FEEDER_ID = 700


def keyid(device_id):
    return int(device_id) + (DOMAIN << 32)


class FakeDB:
    def __init__(self):
        self.sections = [
            {
                "id": 1001,
                "code": "",
                "name": "AJWD_07_SEC001",
                "feeder_id": FEEDER_ID,
                "bv_id": 9001,
            },
            {
                "id": 1002,
                "code": "",
                "name": "AJWD_07_SEC002",
                "feeder_id": FEEDER_ID,
                "bv_id": 9002,
            },
            {
                "id": 1003,
                "code": "",
                "name": "AJWD_07_SEC003",
                "feeder_id": FEEDER_ID,
                "bv_id": 9003,
            },
        ]

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        assert hint == "AJWD07"
        assert table_id == 13500
        return [{
            "id": FEEDER_ID,
            "code": "",
            "name": "JED CTL AJWD 07",
        }]

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        assert feeder_id == FEEDER_ID
        assert table_id == TABLE_ID
        return "dms_section_device", list(self.sections)

    def verify_keyid(self, value):
        return {
            "device_id": int(value) - (DOMAIN << 32),
            "tab_no": TABLE_ID,
            "col_no": DOMAIN,
        }

    def get_device_by_id(self, table_id, device_id):
        for row in self.sections:
            if int(row["id"]) == int(device_id):
                return dict(row)
        return None

    def get_feeder_info(self, feeder_id):
        if int(feeder_id) == FEEDER_ID:
            return {"id": FEEDER_ID, "name": "JED CTL AJWD 07"}
        return {"id": feeder_id, "name": "OTHER FEEDER"}


def write_g(path: Path, feedline2_keyid="", feedline3_keyid=""):
    path.write_text(
        f"""<?xml version="1.0" encoding="utf-8"?>
<G>
  <Layer>
    <Bus id="3001" x="100" y="100" w="120" h="6" />
    <Text id="8001" x="110" y="50" w="80" h="20" ts="AJWD-07" />
    <FeedLine id="3501" x="100" y="200" w="6" h="100"
              keyid="{keyid(1001)}" />
    <FeedLine id="3502" x="100" y="400" w="6" h="100"
              keyid="{feedline2_keyid}" />
    <FeedLine id="3503" x="200" y="600" w="6" h="100"
              keyid="{feedline3_keyid}" />
  </Layer>
</G>
""",
        encoding="utf-8",
    )


def test_bus_nearest_text_resolves_feeder_and_fills_middle_gaps(tmp_path):
    g = tmp_path / "overview.g"
    write_g(g)

    report = FeederValidator(
        FakeDB(),
        GParser(),
    ).validate_file(g)

    assert report["feeder_hint"] == "AJWD-07"
    assert report["feeder_hint_source"] == "BUS_NEAREST_TEXT"
    assert report["feeder_name"] == "JED CTL AJWD 07"

    rows = report["feedline_rows"]
    assert rows[0]["status"] == "PASS"
    assert rows[0]["assigned_section_name"] == "AJWD_07_SEC001"

    assert rows[1]["status"] == "WARN"
    assert rows[1]["assigned_section_name"] == "AJWD_07_SEC002"
    assert rows[1]["expected_keyid"] == keyid(1002)
    assert rows[1]["writeback_needed"] == "YES"

    assert rows[2]["status"] == "WARN"
    assert rows[2]["assigned_section_name"] == "AJWD_07_SEC003"
    assert rows[2]["expected_keyid"] == keyid(1003)


def test_filename_fallback_when_bus_near_text_missing(tmp_path):
    g = tmp_path / "JED-CTL-AJWD-07.sln.pic.g"
    g.write_text(
        """<G><Layer>
        <Bus id="1" x="10" y="10" w="100" h="6"/>
        <FeedLine id="2" x="20" y="100" w="6" h="100" keyid=""/>
        </Layer></G>""",
        encoding="utf-8",
    )

    report = FeederValidator(FakeDB(), GParser()).validate_file(g)
    assert report["feeder_hint"] == "AJWD-07"
    assert report["feeder_hint_source"] == "FILE_NAME"


def test_existing_wrong_feeder_is_error_and_not_overwritten(tmp_path):
    g = tmp_path / "test.g"
    write_g(g)

    class WrongOwnerDB(FakeDB):
        def get_device_by_id(self, table_id, device_id):
            row = super().get_device_by_id(table_id, device_id)
            if row and int(device_id) == 1001:
                row["feeder_id"] = 999
            return row

        def get_feeder_info(self, feeder_id):
            return {"id": feeder_id, "name": "JED CTL AJWD 99"}

    report = FeederValidator(WrongOwnerDB(), GParser()).validate_file(g)
    first = report["feedline_rows"][0]
    assert first["status"] == "FAIL"
    assert "CURRENT_MODEL_FEEDER_MISMATCH" in first["reason"]
    assert first["writeback_needed"] == "NO"


def test_feeder_writeback_attributes_use_bv_id_as_voltype():
    attrs = FeederModelModule._attributes_for_row(
        {
            "xml_id": "3502",
            "expected_keyid": 123456,
            "assigned_bv_id": 112871465660973067,
        }
    )
    assert attrs == {
        "app": "6500000",
        "p_ReportType": "1",
        "state": "20",
        "voltype": "112871465660973067",
        "keyid": "123456",
    }


def test_feeder_reports_are_independent(tmp_path):
    g = tmp_path / "report.g"
    write_g(g)
    report = FeederValidator(FakeDB(), GParser()).validate_file(g)

    html_path = tmp_path / "report.html"
    csv_paths = export_csv_bundle(
        [report],
        tmp_path / "report.csv",
    )
    export_html_bundle(
        [report],
        html_path,
        {"FeedLine": {"table_id": 13503, "domain": 1}},
    )

    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "馈线汇总" in html
    assert "馈线段明细" in html
    assert [p.name for p in csv_paths] == [
        "report_馈线汇总.csv",
        "report_馈线段明细.csv",
    ]
