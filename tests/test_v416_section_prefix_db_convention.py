from dmm.application.modules.feeder import FeederModelModule


class OracleLikeAjwdDB:
    def __init__(self, sections):
        self.sections = list(sections)

    def get_feeder_info(self, feeder_id, table_id=13500):
        # Mirrors the real DBI relationship shown by the AJWD-43 data:
        # feeder name=43, station reference renders as JED CTL AJWD.
        return {
            "id": int(feeder_id),
            "name": "43",
            "st_id": 100,
            "station_name": "JED CTL AJWD",
            "display_name": "JED CTL AJWD 43",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        return {
            "voltagelevel_name": "AJWD/13.8kV",
            "bv_id": 112871465660973067,
            "nomvol": 13.8,
        }

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections]


def settings():
    return {
        "auto_create_missing_sections": True,
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
    }


def report():
    return {
        "g_file": "/tmp/TEST88.sln.pic.g",
        "feeder_id": 700,
        "feeder_name": "AJWD 43",
        "feedline_rows": [
            {
                "order_index": 1,
                "xml_id": "f1",
                "ls": "2",
                "model_linked": "NO",
                "reason": "SECTION_NOT_AVAILABLE: no current link",
            },
            {
                "order_index": 2,
                "xml_id": "f2",
                "ls": "2",
                "model_linked": "NO",
                "reason": "SECTION_NOT_AVAILABLE: no current link",
            },
        ],
    }


def test_existing_ajwd_sections_are_matched_not_recreated_with_full_station_prefix():
    db = OracleLikeAjwdDB([
        {
            "id": 3001,
            "name": "AJWD_43_SEC001",
            "feeder_id": 700,
            "bv_id": 112871465660973067,
            "section_type": 0,
        },
        {
            "id": 3002,
            "name": "AJWD_43_SEC002",
            "feeder_id": 700,
            "bv_id": 112871465660973067,
            "section_type": 0,
        },
    ])

    result = FeederModelModule()._augment_section_creation_plan(
        db, report(), settings(), lambda _msg: None
    )

    assert result["section_prefix"] == "AJWD_43"
    assert result["section_create_plan"] == []
    rows = result["feedline_rows"]
    assert [row["planned_section_name"] for row in rows] == [
        "AJWD_43_SEC001",
        "AJWD_43_SEC002",
    ]
    assert [row["assigned_device_id"] for row in rows] == [3001, 3002]
    assert all(row["severity"] == "UNLINKED" for row in rows)
    assert "JED_CTL_AJWD_43" not in str(result)


def test_missing_ajwd_sections_use_station_business_code_not_full_station_name():
    result = FeederModelModule()._augment_section_creation_plan(
        OracleLikeAjwdDB([]), report(), settings(), lambda _msg: None
    )

    assert result["section_prefix"] == "AJWD_43"
    assert [item["name"] for item in result["section_create_plan"]] == [
        "AJWD_43_SEC001",
        "AJWD_43_SEC002",
    ]
    assert "JED_CTL_AJWD_43" not in str(result)
