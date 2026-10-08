import csv
from pathlib import Path

from dmm.application.batch_orchestrator import export_batch_summary
from dmm.infrastructure.reporting.writer import export_csv_bundle


def _read(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def _simple_rmu_report():
    return {
        "file_name": "TEST.sln.pic.g",
        "rmu_results": [
            {
                "frame_index": 1,
                "frame_xml_id": "2001",
                "rmu_name": "30881",
                "rmu_records": [{"id": "1001"}],
                "rmu_status": "PASS",
                "rmu_severity": "PASS",
                "rmu_reason": "无需关联",
                "device_rows": [{"xml_id": "3001", "db_match_count": 1, "db_combined_id": "1001"}],
            }
        ],
    }


def test_chinese_ui_exports_cn_and_en_csv_from_same_rows(tmp_path):
    paths = export_csv_bundle([_simple_rmu_report()], tmp_path / "report.csv", language="zh_CN")
    assert paths[0].name.endswith("_环网柜汇总_CN.csv")
    cn = paths[0]
    en = tmp_path / "report_rmu_summary_EN.csv"
    assert cn.exists()
    assert en.exists()
    cn_rows = _read(cn)
    en_rows = _read(en)
    assert len(cn_rows) == len(en_rows)
    assert len(cn_rows[0]) == len(en_rows[0])
    # Data identity: first stable source/name columns are generated from the same row.
    assert cn_rows[1][0] == en_rows[1][0]


def test_batch_summary_chinese_ui_has_cn_and_en_versions(tmp_path):
    rows = [{
        "module_id": "RMU",
        "module_name": "RMU 环网柜",
        "candidate_count": 3,
        "applied_count": 2,
        "skipped_count": 1,
        "status": "DONE",
        "report_html": "",
    }]
    _, primary = export_batch_summary(rows, tmp_path, "批量模型关联执行汇总", language="zh_CN")
    assert primary.name == "batch_summary_CN.csv"
    cn = tmp_path / "batch_summary_CN.csv"
    en = tmp_path / "batch_summary_EN.csv"
    assert cn.exists() and en.exists()
    cn_rows = _read(cn)
    en_rows = _read(en)
    assert len(cn_rows) == len(en_rows) == 2
    # ID/counts/status are identical; only presentation labels/module name are localized.
    assert cn_rows[1][0] == en_rows[1][0] == "RMU"
    assert cn_rows[1][2:6] == en_rows[1][2:6]
