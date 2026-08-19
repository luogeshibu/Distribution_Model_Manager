from dmm.application.modules.feeder import FeederModelModule


class ADF15DB:
    def __init__(self):
        names = [
            "ADF_15_SEC001",
            "ADF_15_SEC002",
            "ADF_15_SEC003",
            "ADF_15_SEC004",
            "ADF_15_SEC005",
            "ADF_15_SEC006",
        ]
        self.sections = [
            {
                "id": 3800756610523988985 + i,
                "name": name,
                "feeder_id": 3799912185593856227,
                "bv_id": 112871465660973067,
            }
            for i, name in enumerate(names)
        ]

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {
            "id": int(feeder_id),
            "name": "15",
            "display_name": "ADF 15",
            "st_id": 1,
            "station_name": "ADF",
        }

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections]

    def get_preferred_feeder_section_voltage(self, station_id):
        return {
            "voltagelevel_name": "ADF/13.8kV",
            "bv_id": 112871465660973067,
            "nomvol": 13.8,
        }


def _settings():
    return {
        "auto_create_missing_sections": True,
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
    }


def test_adf15_permuted_but_valid_sec_links_remain_pass():
    db = ADF15DB()
    by_name = {r["name"]: r for r in db.sections}
    # Real ADF-15 order after the application's y/x geometry sort:
    # SEC001, SEC004, SEC002, SEC005, SEC003, SEC006.
    geometry_order = [
        "ADF_15_SEC001",
        "ADF_15_SEC004",
        "ADF_15_SEC002",
        "ADF_15_SEC005",
        "ADF_15_SEC003",
        "ADF_15_SEC006",
    ]
    rows = []
    for idx, name in enumerate(geometry_order, 1):
        rec = by_name[name]
        rows.append({
            "order_index": idx,
            "xml_id": f"fl{idx}",
            "ls": "2",
            "model_linked": "YES",
            "model_link_correct": "YES",
            "current_device_id": rec["id"],
            "current_feeder_id": rec["feeder_id"],
            "current_db_name": name,
            "assigned_device_id": rec["id"],
            "assigned_section_name": name,
            "assigned_bv_id": rec["bv_id"],
            "status": "PASS",
            "severity": "PASS",
            "association_ready": "YES",
            "writeback_needed": "NO",
            "reason": "MODEL_ALREADY_LINKED_CORRECT",
        })

    report = {
        "g_file": "/tmp/JED-CTL-ADF-15.sln.pic.g",
        "feeder_id": 3799912185593856227,
        "feeder_name": "ADF 15",
        "feedline_rows": rows,
    }
    result = FeederModelModule()._augment_section_creation_plan(
        db, report, _settings(), lambda _msg: None
    )

    assert result["section_create_plan"] == []
    checked = result["feedline_rows"]
    assert [r["planned_section_name"] for r in checked] == geometry_order
    assert all(r["status"] == "PASS" for r in checked)
    assert all(r["severity"] == "PASS" for r in checked)
    assert all(r["writeback_needed"] == "NO" for r in checked)
    assert all(r["reason"] == "MODEL_ALREADY_LINKED_CORRECT" for r in checked)


def test_shortage_creation_does_not_reuse_name_held_by_valid_link():
    db = ADF15DB()
    sec2 = next(r for r in db.sections if r["name"] == "ADF_15_SEC002")
    # Row #2 is a shortage, but SEC002 is already validly occupied by row #5.
    # The planner must create one new unique SEC name, never steal SEC002.
    rows = [
        {
            "order_index": 2,
            "xml_id": "missing",
            "ls": "2",
            "model_linked": "NO",
            "model_link_correct": "",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "reason": "SECTION_NOT_AVAILABLE: 当前馈线数据库剩余馈线段数量不足",
        },
        {
            "order_index": 5,
            "xml_id": "existing",
            "ls": "2",
            "model_linked": "YES",
            "model_link_correct": "YES",
            "current_device_id": sec2["id"],
            "current_feeder_id": sec2["feeder_id"],
            "current_db_name": sec2["name"],
            "assigned_device_id": sec2["id"],
            "assigned_section_name": sec2["name"],
            "assigned_bv_id": sec2["bv_id"],
            "status": "PASS",
            "severity": "PASS",
            "association_ready": "YES",
            "writeback_needed": "NO",
            "reason": "MODEL_ALREADY_LINKED_CORRECT",
        },
    ]
    report = {
        "g_file": "/tmp/JED-CTL-ADF-15.sln.pic.g",
        "feeder_id": sec2["feeder_id"],
        "feeder_name": "ADF 15",
        "feedline_rows": rows,
    }
    result = FeederModelModule()._augment_section_creation_plan(
        db, report, _settings(), lambda _msg: None
    )
    plans = result["section_create_plan"]
    assert len(plans) == 1
    assert plans[0]["name"] not in {r["name"] for r in db.sections}
    existing = next(r for r in result["feedline_rows"] if r["xml_id"] == "existing")
    assert existing["planned_section_name"] == "ADF_15_SEC002"
    assert existing["status"] == "PASS"
