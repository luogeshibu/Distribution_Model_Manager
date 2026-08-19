from pathlib import Path

from dmm.domain.gfile.parser import Box, GObject, RmuFrame
from dmm.domain.rmu.validator import RmuValidator
from dmm.infrastructure.reporting.writer import export_html_bundle, flatten_rmu_rows


class _Db:
    def get_rmu_records(self, name):
        return []


class _NoNameParser:
    def find_label_candidates(self, parsed, frame, positions):
        return []


def _frame():
    return RmuFrame(
        GObject(
            tag="rect",
            attrs={"id": "2000999"},
            box=Box(0, 0, 100, 100),
            xml_index=1,
        )
    )


def test_no_rmu_name_is_explicit_hard_fail_and_has_precise_block_reason():
    validator = RmuValidator(_Db(), _NoNameParser(), {})
    resolved = validator._resolve_rmu_name(None, _frame(), ["TOP"])

    assert resolved["status"] == "FAIL"
    assert resolved["reason"].startswith("RMU_NAME_NOT_PARSED:")

    block = validator._rmu_identity_block_reason(
        resolved["reason"],
        "2000999",
        "",
    )
    assert block.startswith("RMU_NAME_NOT_PARSED:")
    assert "矩形框XML ID=2000999" in block
    assert "未解析出环网柜名称" in block
    assert "禁止该RMU及柜内设备自动关联" in block


def _report(reason, block_reasons=None):
    return [{
        "report_type": "RMU",
        "file_name": "missing-name.g",
        "rmu_results": [{
            "frame_index": 1,
            "frame_xml_id": "2000999",
            "rmu_name": "",
            "rmu_type": "2L1T",
            "rmu_type_source": "DEVREF",
            "rmu_type_text": "2L1T",
            "rmu_type_devref": "2L1T",
            "rmu_type_consistent": "YES",
            "rmu_type_check_status": "PASS",
            "rmu_type_check_reason": "",
            "rmu_is_smart": "NO",
            "rmu_smart_marker_types": "",
            "rmu_status": "FAIL",
            "rmu_severity": "ERROR",
            "rmu_reason": reason,
            "rmu_records": [],
            "association_block_reasons": list(block_reasons or []),
            "device_block_reasons": [],
            "inventory_issues": [],
            "db_integrity_issues": [],
            "association_eligible": False,
            "linked_correct_count": 0,
            "unlinked_count": 0,
            "linked_wrong_count": 0,
            "device_rows": [],
        }],
    }]


def test_report_keeps_name_not_parsed_as_red_fail_and_does_not_relabel_as_db_not_found(tmp_path):
    reports = _report(
        "RMU_NAME_NOT_PARSED: 在当前配置的环网柜名称方向内未解析到有效名称文字"
    )
    rows = flatten_rmu_rows(reports)
    row = rows[0]

    assert row["rmu_status"] == "FAIL"
    assert row["rmu_severity"] == "ERROR"
    assert row["rmu_reason"].startswith("RMU_NAME_NOT_PARSED:")
    assert "RMU_NAME_NOT_PARSED:" in row["association_block_reasons"]
    assert "RMU_NOT_FOUND_IN_DATABASE" not in row["rmu_reason"]

    html = tmp_path / "rmu.html"
    export_html_bundle(
        reports,
        html,
        {
            "CBreakerDis": {"table_id": 13502, "domain": 40},
            "ZhaiWaiJieDiDaoZha": {"table_id": 13514, "domain": 40},
            "BusDis": {"table_id": 13506, "domain": 1},
        },
    )
    text = html.read_text(encoding="utf-8")
    assert "<tr class='fail'>" in text
    assert "RMU_NAME_NOT_PARSED" in text
    assert "RMU级关联阻断原因" in text
    assert "未解析出环网柜名称" in text


def test_report_resolution_exception_is_red_and_block_reason_is_explicit():
    reports = _report(
        "RMU_NAME_RESOLUTION_ERROR: ValueError: bad label geometry"
    )
    row = flatten_rmu_rows(reports)[0]

    assert row["rmu_status"] == "FAIL"
    assert row["rmu_severity"] == "ERROR"
    assert "RMU_NAME_RESOLUTION_ERROR" in row["rmu_reason"]
    assert "名称解析/核验异常" in row["association_block_reasons"]
    assert row["association_eligible"] == "NO"
