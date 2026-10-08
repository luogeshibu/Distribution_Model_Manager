import csv
from pathlib import Path

from dmm.application.modules.feeder_context import add_feeder_fields
from dmm.infrastructure.reporting.writer import export_csv_bundle, flatten_rmu_rows


def _read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def _report():
    return {
        "file_name": "JED-CTL-ADF-34.sln.pic.g",
        "feeder_context_ready": "YES",
        "feeder_resolution_source": "FILENAME_405_13500",
        "feeder_id": "3799912185593859999",
        "subcontrolarea_path": "JED CTL",
        "station_name": "ADF",
        "feeder_db_name": "AH334",
        "feeder_name": "JED CTL ADF AH334",
        "feeder_path": "JED CTL ADF AH334",
        "rmu_results": [
            {
                "frame_index": 1,
                "frame_xml_id": "200001",
                "rmu_name": "43223",
                "rmu_records": [{"id": "1001"}],
                "rmu_status": "PASS",
                "rmu_severity": "PASS",
                "rmu_reason": "",
                "device_rows": [
                    {
                        "xml_id": "300001",
                        "db_match_count": 1,
                        "db_combined_id": "1001",
                        "status": "PASS",
                    }
                ],
            }
        ],
    }


def test_add_feeder_fields_prefers_full_database_hierarchy():
    row = {}
    add_feeder_fields(row, {
        "ready": True,
        "feeder_source": "FILENAME_405_13500",
        "feeder_id": 123,
        "feeder": {
            "id": 123,
            "subcontrolarea_path": "JED CTL",
            "station_name": "ADF",
            "name": "AH334",
            "display_name": "JED CTL ADF AH334",
        },
    })
    assert row["subcontrolarea_path"] == "JED CTL"
    assert row["station_name"] == "ADF"
    assert row["feeder_db_name"] == "AH334"
    assert row["feeder_name"] == "JED CTL ADF AH334"
    assert row["feeder_path"] == "JED CTL ADF AH334"


def test_rmu_summary_row_contains_full_database_verified_feeder():
    row = flatten_rmu_rows([_report()])[0]
    assert row["subcontrolarea_path"] == "JED CTL"
    assert row["station_name"] == "ADF"
    assert row["feeder_db_name"] == "AH334"
    assert row["feeder_name"] == "JED CTL ADF AH334"


def test_rmu_cn_en_csv_both_export_full_feeder_name(tmp_path):
    paths = export_csv_bundle([_report()], tmp_path / "report.csv", language="zh_CN")
    cn = next(path for path in paths if path.name.endswith("_环网柜汇总_CN.csv"))
    en = tmp_path / "report_rmu_summary_EN.csv"
    assert cn.exists() and en.exists()

    cn_rows = _read_csv(cn)
    en_rows = _read_csv(en)
    cn_header, cn_data = cn_rows[0], cn_rows[1]
    en_header, en_data = en_rows[0], en_rows[1]

    cn_full_idx = cn_header.index("数据库验证馈线全名")
    cn_raw_idx = cn_header.index("13500馈线NAME（来源：数据库）")
    en_full_idx = en_header.index("Database-verified Full Feeder Name")
    en_raw_idx = en_header.index("13500 Feeder NAME (Database)")

    assert cn_data[cn_full_idx] == en_data[en_full_idx] == "JED CTL ADF AH334"
    assert cn_data[cn_raw_idx] == en_data[en_raw_idx] == "AH334"
