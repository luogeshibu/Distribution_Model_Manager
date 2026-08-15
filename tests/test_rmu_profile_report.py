
from pathlib import Path

from dmm.infrastructure.reporting.writer import (
    export_csv_bundle,
    export_html_bundle,
)


def _reports():
    return [{
        "report_type": "RMU",
        "file_name": "demo.g",
        "rmu_results": [{
            "frame_index": 1,
            "frame_xml_id": "2001",
            "rmu_name": "25583",
            "rmu_type": "2L1T",
            "rmu_type_source": "TEXT_YQ",
            "rmu_type_text": "2L1T",
            "rmu_type_devref": "2L1T",
            "rmu_type_consistent": "YES",
            "rmu_is_smart": "YES",
            "rmu_smart_marker_types": "SMART, SMR",
            "rmu_status": "PASS",
            "rmu_severity": "PASS",
            "rmu_reason": "RMU_MODEL_DATA_VALID",
            "rmu_records": [{"id": 9001}],
            "association_block_reasons": [],
            "device_block_reasons": [],
            "inventory_issues": [],
            "db_integrity_issues": [],
            "association_eligible": True,
            "linked_correct_count": 0,
            "unlinked_count": 3,
            "linked_wrong_count": 0,
            "device_rows": [
                {
                    "xml_id": "c1",
                    "object_type": "CBreakerDis",
                    "db_match_count": 1,
                    "db_combined_id": 9001,
                },
                {
                    "xml_id": "z1",
                    "object_type": "ZhaiWaiJieDiDaoZha",
                    "db_match_count": 1,
                    "db_combined_id": 9001,
                },
                {
                    "xml_id": "b1",
                    "object_type": "BusDis",
                    "db_match_count": 1,
                    "db_combined_id": 9001,
                },
            ],
        }],
    }]


def test_rmu_csv_bundle_contains_dedicated_profile_csv(tmp_path):
    paths = export_csv_bundle(_reports(), tmp_path / "report.csv")
    assert len(paths) == 3
    profile = paths[2]
    assert profile.name.endswith("_环网柜档案.csv")
    text = profile.read_text(encoding="utf-8-sig")
    assert "环网柜名称" in text
    assert "环网柜类型" in text
    assert "是否智能" in text
    assert "数据库是否唯一" in text
    assert "环网柜设备是否完整" in text
    assert "25583" in text
    assert "2L1T" in text
    assert "SMART, SMR" in text
    assert "YES" in text


def test_rmu_html_contains_smart_and_profile_section(tmp_path):
    html = tmp_path / "report.html"
    export_html_bundle(
        _reports(),
        html,
        {
            "CBreakerDis": {"table_id": 13502, "domain": 40},
            "ZhaiWaiJieDiDaoZha": {"table_id": 13514, "domain": 40},
            "BusDis": {"table_id": 13506, "domain": 1},
        },
    )
    text = html.read_text(encoding="utf-8")
    assert "环网柜档案" in text
    assert "是否智能" in text
    assert "智能标识" in text
    assert "设备是否完整" in text
