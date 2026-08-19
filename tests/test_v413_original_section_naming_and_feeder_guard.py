from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule


class CreationDB:
    def __init__(self, sections=None):
        self.sections = list(sections or [])

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {
            "id": int(feeder_id),
            "name": "07",
            "st_id": 113997365567815688,
            "station_name": "AJWD",
            "display_name": "AJWD 07",
        }

    def get_preferred_feeder_section_voltage(self, station_id):
        return {
            "voltagelevel_name": "AJWD/13.8kV",
            "bv_id": 112871465660973067,
            "nomvol": 13.8,
        }

    def get_sections_by_feeder_id(self, feeder_id, table_id=13503):
        return "dms_section_device", [dict(x) for x in self.sections]

def base_report(row):
    return {
        "g_file": "/tmp/AJWD-07.g",
        "feeder_id": 700,
        "feeder_name": "AJWD 07",
        "feedline_rows": [row],
    }


def settings():
    return {
        "auto_create_missing_sections": True,
        "feeder_table_id": 13500,
        "section_table_id": 13503,
        "section_domain": 1,
    }


def test_section_creation_name_restored_to_original_secnnn_rule():
    row = {
        "order_index": 1,
        "xml_id": "f1",
        "ls": "2",
        "reason": "SECTION_NOT_AVAILABLE: no free section",
        "model_linked": "NO",
        # v4.1.1 would have used this topology-derived value. v4.1.3 must ignore it.
        "topology_section_name": "B303_22545-Y1",
    }
    result = FeederModelModule()._augment_section_creation_plan(
        CreationDB(), base_report(row), settings(), lambda _msg: None
    )
    assert result["section_create_plan"][0]["name"] == "AJWD_07_SEC001"
    assert result["feedline_rows"][0]["planned_section_name"] == "AJWD_07_SEC001"
    assert result["feedline_rows"][0]["assigned_section_name"] == "AJWD_07_SEC001"
    assert "B303_22545-Y1" not in str(result["section_create_plan"])


def test_wrong_feeder_existing_link_is_hard_error_and_never_auto_relinked():
    # Even if the exact expected SEC001 exists under feeder 700, an existing
    # model link that currently belongs to feeder 701 must not be silently fixed.
    db = CreationDB([
        {
            "id": 3001,
            "name": "AJWD_07_SEC001",
            "feeder_id": 700,
            "bv_id": 112871465660973067,
        }
    ])
    row = {
        "order_index": 1,
        "xml_id": "f1",
        "ls": "2",
        "model_linked": "YES",
        "current_device_id": 4001,
        "current_feeder_id": 701,
        "current_feeder_name": "AJWD 08",
        "status": "FAIL",
        "severity": "ERROR",
        "association_ready": "NO",
        "writeback_needed": "NO",
        "reason": "CURRENT_MODEL_FEEDER_MISMATCH",
    }
    result = FeederModelModule()._augment_section_creation_plan(
        db, base_report(row), settings(), lambda _msg: None
    )
    checked = result["feedline_rows"][0]
    assert checked["status"] == "FAIL"
    assert checked["severity"] == "FEEDER_MISMATCH"
    assert checked["association_ready"] == "NO"
    assert checked["writeback_needed"] == "NO"
    assert checked["db_create_needed"] == "NO"
    assert "禁止自动跨馈线重关联" in checked["reason"]


def test_same_feeder_valid_existing_link_is_not_reordered_by_positional_sec_rule():
    db = CreationDB([
        {
            "id": 3001,
            "name": "AJWD_07_SEC001",
            "feeder_id": 700,
            "bv_id": 112871465660973067,
        },
        {
            "id": 3003,
            "name": "AJWD_07_SEC003",
            "feeder_id": 700,
            "bv_id": 112871465660973067,
        },
    ])
    # Geometry/order says this is row #1, but the G model is already validly
    # linked to SEC003 under the same feeder. v4.1.12 must preserve it.
    row = {
        "order_index": 1,
        "xml_id": "f1",
        "ls": "2",
        "model_linked": "YES",
        "model_link_correct": "YES",
        "current_device_id": 3003,
        "current_feeder_id": 700,
        "current_db_name": "AJWD_07_SEC003",
        "assigned_device_id": 3003,
        "assigned_section_name": "AJWD_07_SEC003",
        "status": "PASS",
        "severity": "PASS",
        "association_ready": "YES",
        "writeback_needed": "NO",
        "reason": "MODEL_ALREADY_LINKED_CORRECT",
    }
    result = FeederModelModule()._augment_section_creation_plan(
        db, base_report(row), settings(), lambda _msg: None
    )
    checked = result["feedline_rows"][0]
    assert checked["planned_section_name"] == "AJWD_07_SEC003"
    assert checked["assigned_device_id"] == 3003
    assert checked["status"] == "PASS"
    assert checked["severity"] == "PASS"
    assert checked["association_ready"] == "YES"
    assert checked["writeback_needed"] == "NO"
    assert checked["reason"] == "MODEL_ALREADY_LINKED_CORRECT"


def test_active_application_path_no_longer_uses_topology_resolver_for_section_names():
    src = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/feeder.py"
    ).read_text(encoding="utf-8")
    assert "FeederTopologyResolver().resolve" not in src
    assert 'target_name = f"{prefix}_SEC{order_index:03d}"' in src
    assert "FeederDrawingTopologyClassifier" in src
