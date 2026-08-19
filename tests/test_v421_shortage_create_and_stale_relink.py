from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser

KEY_STEP = 1 << 32


def keyid(device_id, domain):
    return int(device_id) + int(domain) * KEY_STEP


class ShortageDB:
    def __init__(self, include_spare=False):
        self.sections = [
            {"id": 3001, "name": "31475-Y1_30814-Y2", "code": "", "feeder_id": 700, "bv_id": 93001, "section_type": 0},
            {"id": 3002, "name": "30814-Y1_30882-Y2", "code": "", "feeder_id": 700, "bv_id": 93001, "section_type": 0},
        ]
        if include_spare:
            self.sections.append(
                {"id": 3003, "name": "30882-Y1_30902-Y2", "code": "", "feeder_id": 700, "bv_id": 93001, "section_type": 0}
            )

    def verify_keyid(self, value):
        value = int(value)
        domain = value // KEY_STEP
        device_id = value - domain * KEY_STEP
        return {"device_id": device_id, "tab_no": 13503, "col_no": domain}

    def get_device_by_id(self, table_id, device_id):
        if int(table_id) != 13503:
            return None
        for row in self.sections:
            if int(row["id"]) == int(device_id):
                return dict(row)
        return None

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [
            dict(row) for row in self.sections
            if int(row["feeder_id"]) == int(feeder_id)
        ]

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {
            "id": int(feeder_id),
            "name": "43",
            "display_name": "AJWD 43",
            "st_id": 500,
            "station_name": "AJWD",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        assert int(station_id) == 500
        return {
            "voltagelevel_name": "AJWD/13.8kV",
            "bv_id": 93001,
            "nomvol": 13.8,
        }


def write_three_feedlines(path: Path):
    # fl1 points to a deleted/non-existent old 13503 row. fl2/fl3 still point
    # to two existing rows, but with the historical wrong domain=5.
    path.write_text(
        f'''<G><Layer>
        <FeedLine id="fl1" x="10" y="10" w="100" h="6" d="10,13 110,13" ls="2" keyid="{keyid(3999,5)}"/>
        <FeedLine id="fl2" x="10" y="30" w="100" h="6" d="10,33 110,33" ls="2" keyid="{keyid(3001,5)}"/>
        <FeedLine id="fl3" x="10" y="50" w="100" h="6" d="10,53 110,53" ls="2" keyid="{keyid(3002,5)}"/>
        </Layer></G>''',
        encoding="utf-8",
    )


def feeder_record():
    return {
        "id": 700,
        "name": "43",
        "display_name": "AJWD 43",
        "st_id": 500,
        "station_name": "AJWD",
    }


def settings():
    return {
        "auto_create_missing_sections": True,
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
    }


def test_stale_old_keyid_plus_db_shortage_creates_only_actual_shortage(tmp_path):
    g = tmp_path / "AJWD-43.g"
    write_three_feedlines(g)
    db = ShortageDB(include_spare=False)
    validator = FeederValidator(db, GParser(), section_table_id=13503, section_domain=1)
    file_report = validator.validate_file_with_feeder_record(g, feeder_record(), source="MANUAL")
    report = file_report["feeder_regions"][0]

    rows = {row["xml_id"]: row for row in report["feedline_rows"]}
    # Existing rows are retained and only need domain repair.
    assert rows["fl2"]["assigned_device_id"] == 3001
    assert rows["fl3"]["assigned_device_id"] == 3002
    assert rows["fl2"]["relink_same_section"] == "YES"
    assert rows["fl3"]["relink_same_section"] == "YES"

    # Only the stale/deleted old link is still short after the current feeder's
    # remaining DB pool is exhausted.
    assert rows["fl1"]["relink_missing_section"] == "YES"
    assert rows["fl1"]["reason"].startswith("SECTION_NOT_AVAILABLE")

    planned = FeederModelModule()._augment_section_creation_plan(
        db, report, settings(), lambda _msg: None
    )
    plans = planned["section_create_plan"]
    assert len(plans) == 1
    assert plans[0]["xml_id"] == "fl1"
    assert plans[0]["name"] == "AJWD_43_SEC001"
    shortage = next(row for row in planned["feedline_rows"] if row["xml_id"] == "fl1")
    assert shortage["db_create_needed"] == "YES"
    assert shortage["association_ready"] == "YES"
    assert shortage["severity"] == "CREATE_PENDING"


def test_stale_old_keyid_reuses_spare_same_feeder_section_before_create(tmp_path):
    g = tmp_path / "AJWD-43-spare.g"
    write_three_feedlines(g)
    db = ShortageDB(include_spare=True)
    validator = FeederValidator(db, GParser(), section_table_id=13503, section_domain=1)
    file_report = validator.validate_file_with_feeder_record(g, feeder_record(), source="MANUAL")
    report = file_report["feeder_regions"][0]
    row = next(row for row in report["feedline_rows"] if row["xml_id"] == "fl1")

    assert row["relink_missing_section"] == "YES"
    assert row["assigned_device_id"] == 3003
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert row["severity"] == "RELINK"
    assert "STALE_SECTION_RELINK_READY" in row["reason"]

    planned = FeederModelModule()._augment_section_creation_plan(
        db, report, settings(), lambda _msg: None
    )
    assert planned["section_create_plan"] == []
    row2 = next(row for row in planned["feedline_rows"] if row["xml_id"] == "fl1")
    assert row2["assigned_device_id"] == 3003


def test_execution_prefers_validated_assigned_device_id_for_legacy_names():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/feeder.py"
    ).read_text(encoding="utf-8")
    assert "EXEC_ASSIGNED_SECTION_NOT_AVAILABLE" in source
    assert "if not create_needed and assigned_id is not None" in source
