from dmm.application.modules.feeder import FeederModelModule


class OracleLikeDB:
    """Minimal DB surface matching the real OracleClient for this path.

    Intentionally has NO make_expected_keyid() method.
    """

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {
            "id": int(feeder_id),
            "name": "43",
            "st_id": 100,
            "station_name": "AJWD",
            "display_name": "AJWD 43",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        return {
            "voltagelevel_name": "AJWD/13.8kV",
            "bv_id": 112871465660973067,
            "nomvol": 13.8,
        }

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [
            {
                "id": 3001,
                "name": "AJWD_43_SEC001",
                "feeder_id": int(feeder_id),
                "bv_id": 112871465660973067,
            }
        ]


def test_existing_section_keyid_does_not_require_nonexistent_oracle_method():
    report = {
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
            }
        ],
    }
    settings = {
        "auto_create_missing_sections": True,
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
    }

    result = FeederModelModule()._augment_section_creation_plan(
        OracleLikeDB(), report, settings, lambda _msg: None
    )

    row = result["feedline_rows"][0]
    assert row["assigned_device_id"] == 3001
    assert row["expected_keyid"] == 3001 + (1 << 32)
    assert row["association_ready"] == "YES"
    assert row["severity"] == "UNLINKED"
