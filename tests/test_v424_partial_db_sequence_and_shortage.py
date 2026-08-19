from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser

KEY_STEP = 1 << 32


def keyid(device_id, domain=1):
    return int(device_id) + int(domain) * KEY_STEP


class DB:
    def __init__(self, sections):
        self.sections = [dict(row) for row in sections]

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
            "id": int(feeder_id), "name": "15", "display_name": "ADF 15",
            "st_id": 500, "station_name": "ADF",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        return {
            "voltagelevel_name": "ADF/13.8kV", "bv_id": 93001, "nomvol": 13.8,
        }


def section(id_, name):
    return {
        "id": id_, "name": name, "code": "", "feeder_id": 700,
        "bv_id": 93001, "section_type": 0,
    }


def feeder_record():
    return {
        "id": 700, "name": "15", "display_name": "ADF 15",
        "st_id": 500, "station_name": "ADF",
    }


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


def validate(db, g):
    validator = FeederValidator(db, GParser(), section_table_id=13503, section_domain=1)
    return validator.validate_file_with_feeder_record(
        g, feeder_record(), source="MANUAL"
    )["feeder_regions"][0]


def test_four_linked_two_unlinked_use_two_remaining_sections(tmp_path):
    sections = [section(3000 + i, f"ADF_15_SEC{i:03d}") for i in range(1, 7)]
    db = DB(sections)
    # Existing links deliberately do not follow geometry/SEC order.
    g = tmp_path / "partial.g"
    write_g(g, [
        keyid(sections[3]["id"]),  # SEC004
        keyid(sections[1]["id"]),  # SEC002
        None,
        keyid(sections[5]["id"]),  # SEC006
        None,
        keyid(sections[0]["id"]),  # SEC001
    ])

    report = validate(db, g)
    rows = report["feedline_rows"]
    assert report["section_assignment_mode"] == "PRESERVE_EXISTING_DB_SEQUENCE"
    # Locked existing links stay exactly as-is.
    assert rows[0]["assigned_section_name"] == "ADF_15_SEC004"
    assert rows[1]["assigned_section_name"] == "ADF_15_SEC002"
    assert rows[3]["assigned_section_name"] == "ADF_15_SEC006"
    assert rows[5]["assigned_section_name"] == "ADF_15_SEC001"
    # Remaining free DB sequence is SEC003 then SEC005.
    assert rows[2]["assigned_section_name"] == "ADF_15_SEC003"
    assert rows[4]["assigned_section_name"] == "ADF_15_SEC005"
    assert rows[2]["association_ready"] == "YES"
    assert rows[4]["association_ready"] == "YES"


def test_non_sec_history_names_use_database_id_ascending(tmp_path):
    db = DB([
        section(4100, "Z_HISTORY"),
        section(4000, "A_HISTORY"),
        section(4300, "M_HISTORY"),
    ])
    g = tmp_path / "history.g"
    # Lock ID 4300; two unresolved rows must receive IDs 4000 then 4100.
    write_g(g, [keyid(4300), None, None])

    rows = validate(db, g)["feedline_rows"]
    assert rows[0]["assigned_device_id"] == 4300
    assert rows[1]["assigned_device_id"] == 4000
    assert rows[2]["assigned_device_id"] == 4100


def test_existing_rows_used_first_then_only_true_shortage_is_created(tmp_path):
    sections = [
        section(3001, "ADF_15_SEC001"),
        section(3002, "ADF_15_SEC002"),
        section(3003, "ADF_15_SEC003"),
        section(3004, "ADF_15_SEC004"),
        section(3005, "ADF_15_SEC005"),
    ]
    db = DB(sections)
    g = tmp_path / "short.g"
    # 6 FeedLines total. Four valid links; two unresolved; only one free DB row.
    write_g(g, [keyid(3001), keyid(3002), keyid(3003), keyid(3004), None, None])

    report = validate(db, g)
    rows = report["feedline_rows"]
    assert rows[4]["assigned_device_id"] == 3005
    assert rows[4]["association_ready"] == "YES"
    assert rows[5]["reason"].startswith("SECTION_NOT_AVAILABLE")

    planned = FeederModelModule()._augment_section_creation_plan(
        db, report, settings(), lambda _msg: None
    )
    assert len(planned["section_create_plan"]) == 1
    assert planned["feedline_rows"][5]["severity"] == "CREATE_PENDING"
    assert planned["section_create_plan"][0]["name"] == "ADF_15_SEC006"
