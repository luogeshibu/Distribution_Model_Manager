import csv
from pathlib import Path

import pytest

from dmm.infrastructure.reporting.writer import export_csv_bundle


def _rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize(
    "report, expected_section, expected_name",
    [
        (
            {
                "report_type": "POLE_SWITCH",
                "file_name": "JED-NTH-ABH-01.sln.pic.g",
                "pole_switch_rows": [
                    {"xml_id": "ps-fail", "graphical_name": "101", "status": "FAIL", "reason": "NO_TARGET"},
                    {"xml_id": "ps-ok", "graphical_name": "102", "status": "PASS", "reason": "OK"},
                ],
            },
            "柱上开关明细",
            "JED-NTH-ABH-01.sln.pic.g",
        ),
        (
            {
                "report_type": "TRANSFORMER",
                "file_name": "JED-NTH-ABH-02.sln.pic.g",
                "transformer_rows": [
                    {"xml_id": "tr-fail", "graphical_name": "201", "status": "FAIL", "reason": "NO_TARGET"},
                    {"xml_id": "tr-warn", "graphical_name": "202", "status": "UNLINKED", "reason": "READY"},
                ],
            },
            "柱上变压器明细",
            "JED-NTH-ABH-02.sln.pic.g",
        ),
        (
            {
                "report_type": "FUSE",
                "file_name": "JED-NTH-ABH-03.sln.pic.g",
                "fuse_rows": [
                    {"xml_id": "fu-fail", "fuse_name": "FUSE301", "status": "FAIL", "reason": "NO_TARGET"},
                    {"xml_id": "fu-ok", "fuse_name": "FUSE302", "status": "PASS", "reason": "OK"},
                ],
            },
            "熔断器明细",
            "JED-NTH-ABH-03.sln.pic.g",
        ),
        (
            {
                "report_type": "MASTER_STATION",
                "file_name": "JED-NTH-ABH-04.sln.pic.g",
                "master_station_rows": [
                    {"xml_id": "ms-fail", "object_type": "CBreaker", "status": "FAIL", "reason": "NO_TARGET"},
                    {"xml_id": "ms-ok", "object_type": "CBreaker", "status": "PASS", "reason": "OK"},
                ],
            },
            "配网主站设备明细",
            "JED-NTH-ABH-04.sln.pic.g",
        ),
    ],
)
def test_single_table_models_always_export_one_extra_red_failure_csv(
    tmp_path, report, expected_section, expected_name
):
    paths = export_csv_bundle([report], tmp_path / "report.csv")
    assert len(paths) == 2
    failure = paths[-1]
    assert failure.name == "report_关联失败_CN.csv"
    rows = _rows(failure)
    assert len(rows) == 1
    assert rows[0]["报告分类"] == expected_section
    assert rows[0]["G文件"] == expected_name
    assert rows[0]["状态"] == "FAIL"


def test_rmu_failure_csv_collects_red_rows_from_summary_and_device_details(tmp_path):
    report = {
        "report_type": "RMU",
        "file_name": "JED-NTH-ABH-05.sln.pic.g",
        "rmu_results": [
            {
                "frame_index": 1,
                "frame_xml_id": "frame-1",
                "rmu_name": "RMU-1",
                "rmu_records": [{"ID": 1001}],
                "rmu_status": "FAIL",
                "rmu_reason": "RMU_BLOCKED",
                "device_rows": [
                    {"xml_id": "dev-fail", "object_type": "CBreakerDis", "status": "FAIL", "reason": "NO_TARGET"},
                    {"xml_id": "dev-warn", "object_type": "CBreakerDis", "status": "UNLINKED", "reason": "READY"},
                ],
            }
        ],
    }
    paths = export_csv_bundle([report], tmp_path / "report.csv")
    assert len(paths) == 3
    rows = _rows(paths[-1])
    assert {row["报告分类"] for row in rows} == {"环网柜汇总", "设备明细"}
    assert len(rows) == 2


def test_rmu_link_is_exported_because_html_renders_it_red(tmp_path):
    report = {
        "report_type": "RMU",
        "file_name": "JED-NTH-ABH-06.sln.pic.g",
        "rmu_results": [
            {
                "frame_index": 1,
                "frame_xml_id": "frame-1",
                "rmu_name": "RMU-1",
                "rmu_records": [{"ID": 1001}],
                "rmu_status": "PASS",
                "device_rows": [
                    {"xml_id": "dev-rmu-link", "object_type": "CBreakerDis", "status": "RMU_LINK", "reason": "WRONG_RMU"},
                ],
            }
        ],
    }
    paths = export_csv_bundle([report], tmp_path / "report.csv")
    rows = _rows(paths[-1])
    assert len(rows) == 1
    assert rows[0]["状态"] == "RMU_LINK"


def test_feeder_failure_csv_collects_red_summary_and_section_rows(tmp_path):
    report = {
        "report_type": "FEEDER",
        "file_name": "JED-NTH-ABH-07.sln.pic.g",
        "status": "FAIL",
        "reason": "FEEDER_NOT_FOUND",
        "feedline_rows": [
            {"order_index": 1, "xml_id": "fl-fail", "status": "FAIL", "reason": "NO_SECTION"},
            {"order_index": 2, "xml_id": "fl-create", "status": "WARN", "severity": "CREATE_PENDING", "reason": "CREATE"},
        ],
    }
    paths = export_csv_bundle([report], tmp_path / "report.csv")
    assert len(paths) == 3
    rows = _rows(paths[-1])
    assert {row["报告分类"] for row in rows} == {"馈线汇总", "馈线段明细"}
    assert len(rows) == 2
    assert all(row["状态"] == "FAIL" for row in rows)


def test_failure_csv_is_created_with_headers_even_when_there_are_no_red_rows(tmp_path):
    report = {
        "report_type": "TRANSFORMER",
        "file_name": "JED-NTH-ABH-08.sln.pic.g",
        "transformer_rows": [
            {"xml_id": "tr-ok", "graphical_name": "801", "status": "PASS", "reason": "OK"},
        ],
    }
    paths = export_csv_bundle([report], tmp_path / "report.csv")
    failure = paths[-1]
    assert failure.exists()
    rows = _rows(failure)
    assert rows == []
    header = failure.read_text(encoding="utf-8-sig").splitlines()[0]
    assert "报告分类" in header
    assert "状态" in header


def test_english_failure_csv_name_and_headers(tmp_path):
    report = {
        "report_type": "FUSE",
        "file_name": "JED-NTH-ABH-09.sln.pic.g",
        "fuse_rows": [
            {"xml_id": "fu-fail", "status": "FAIL", "reason": "NO_TARGET"},
        ],
    }
    paths = export_csv_bundle([report], tmp_path / "report.csv", language="en_US")
    failure = paths[-1]
    assert failure.name == "report_association_failures_EN.csv"
    rows = _rows(failure)
    assert rows[0]["Report Section"] == "Fuse Details"
    assert rows[0]["Status"] == "FAIL"
