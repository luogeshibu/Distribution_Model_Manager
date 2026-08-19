from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser

KEY_STEP = 1 << 32


def keyid(device_id, domain=1):
    return int(device_id) + int(domain) * KEY_STEP


class DB:
    def __init__(self, names):
        self.sections = [
            {
                "id": 3000 + i,
                "name": name,
                "code": "",
                "feeder_id": 700,
                "bv_id": 93001,
                "section_type": 0,
            }
            for i, name in enumerate(names, 1)
        ]

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
            "name": "15",
            "display_name": "ADF 15",
            "st_id": 500,
            "station_name": "ADF",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        return {
            "voltagelevel_name": "ADF/13.8kV",
            "bv_id": 93001,
            "nomvol": 13.8,
        }


def feeder_record():
    return {
        "id": 700,
        "name": "15",
        "display_name": "ADF 15",
        "st_id": 500,
        "station_name": "ADF",
    }


def validator(db):
    return FeederValidator(
        db,
        GParser(),
        section_table_id=13503,
        section_domain=1,
    )


def settings():
    return {
        "auto_create_missing_sections": True,
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
    }


def write_g(path: Path, keyids):
    parts = ["<G><Layer>"]
    for i, kid in enumerate(keyids, 1):
        attr = f' keyid="{kid}"' if kid else ""
        parts.append(
            f'<FeedLine id="fl{i}" x="10" y="{i*20}" w="100" h="6" '
            f'd="10,{i*20+3} 110,{i*20+3}" ls="2"{attr}/>'
        )
    parts.append("</Layer></G>")
    path.write_text("".join(parts), encoding="utf-8")


def region(report):
    return report["feeder_regions"][0]


def test_fully_new_drawing_may_allocate_by_order(tmp_path):
    db = DB(["ADF_15_SEC001", "ADF_15_SEC002", "ADF_15_SEC003"])
    g = tmp_path / "new.g"
    write_g(g, [None, None])

    report = region(
        validator(db).validate_file_with_feeder_record(
            g, feeder_record(), source="MANUAL"
        )
    )
    assert report["section_assignment_mode"] == "NEW_DRAWING_ORDER"
    rows = report["feedline_rows"]
    assert [r["assigned_section_name"] for r in rows] == [
        "ADF_15_SEC001",
        "ADF_15_SEC002",
    ]
    assert all(r["association_ready"] == "YES" for r in rows)


def test_partial_drawing_uses_remaining_db_sequence_without_reordering_existing(tmp_path):
    db = DB(["ADF_15_SEC001", "ADF_15_SEC002", "ADF_15_SEC003"])
    sec2 = db.sections[1]
    g = tmp_path / "partial.g"
    write_g(g, [keyid(sec2["id"]), None])

    report = region(
        validator(db).validate_file_with_feeder_record(
            g, feeder_record(), source="MANUAL"
        )
    )
    assert report["section_assignment_mode"] == "PRESERVE_EXISTING_DB_SEQUENCE"
    rows = report["feedline_rows"]
    assert rows[0]["status"] == "PASS"
    assert rows[0]["assigned_section_name"] == "ADF_15_SEC002"
    # Existing SEC002 remains untouched; unresolved fl2 takes the first free
    # same-feeder DB record in deterministic sequence (SEC001).
    assert rows[1]["assigned_section_name"] == "ADF_15_SEC001"
    assert rows[1]["association_ready"] == "YES"
    assert rows[1]["severity"] == "UNLINKED"
    assert "DB_SEQUENCE" in rows[1]["reason"]


def test_partial_drawing_may_use_unique_one_to_one_remainder(tmp_path):
    db = DB(["ADF_15_SEC001", "ADF_15_SEC002"])
    sec2 = db.sections[1]
    g = tmp_path / "unique.g"
    write_g(g, [keyid(sec2["id"]), None])

    report = region(
        validator(db).validate_file_with_feeder_record(
            g, feeder_record(), source="MANUAL"
        )
    )
    rows = report["feedline_rows"]
    assert rows[0]["status"] == "PASS"
    assert rows[1]["assigned_section_name"] == "ADF_15_SEC001"
    assert rows[1]["association_ready"] == "YES"
    assert "DB_SEQUENCE" in rows[1]["reason"]


def test_existing_same_feeder_same_domain_is_pass_even_if_duplicate_section(tmp_path):
    db = DB(["ADF_15_SEC001"])
    sec1 = db.sections[0]
    g = tmp_path / "duplicate.g"
    write_g(g, [keyid(sec1["id"]), keyid(sec1["id"])])

    report = region(
        validator(db).validate_file_with_feeder_record(
            g, feeder_record(), source="MANUAL"
        )
    )
    rows = report["feedline_rows"]
    assert all(r["status"] == "PASS" for r in rows)
    assert all(r["reason"] == "MODEL_ALREADY_LINKED_CORRECT" for r in rows)


def test_partial_singleton_shortage_creates_first_unused_not_geometry_suffix(tmp_path):
    db = DB(["ADF_15_SEC001"])
    sec1 = db.sections[0]
    g = tmp_path / "shortage.g"
    # fl1 is valid; fl2 is a stale link whose DB row no longer exists. This is
    # not a fully new drawing, so no geometric SEC002-vs-order validation is
    # allowed. There is exactly one unresolved row and zero free sections.
    write_g(g, [keyid(sec1["id"]), keyid(9999)])

    report = region(
        validator(db).validate_file_with_feeder_record(
            g, feeder_record(), source="MANUAL"
        )
    )
    assert report["section_assignment_mode"] == "PRESERVE_EXISTING_DB_SEQUENCE"
    pending = report["feedline_rows"][1]
    assert pending["reason"].startswith("SECTION_NOT_AVAILABLE")

    planned = FeederModelModule()._augment_section_creation_plan(
        db, report, settings(), lambda _msg: None
    )
    assert len(planned["section_create_plan"]) == 1
    assert planned["section_create_plan"][0]["name"] == "ADF_15_SEC002"
