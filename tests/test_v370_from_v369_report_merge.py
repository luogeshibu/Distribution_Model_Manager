
from pathlib import Path

from dmm.infrastructure.reporting.writer import RMU_FIELDS, RMU_LABELS


def _read(rel):
    return (
        Path(__file__).parents[1] / rel
    ).read_text(encoding="utf-8")


def test_unified_summary_contains_profile_information():
    required = {
        "rmu_type",
        "rmu_type_source",
        "rmu_type_text",
        "rmu_type_devref",
        "rmu_type_consistent",
        "rmu_is_smart",
        "rmu_smart_marker_types",
        "rmu_db_count",
        "database_unique",
        "rmu_id",
        "device_count",
        "matched_device_count",
        "device_complete",
        "rmu_status",
        "rmu_reason",
    }
    assert required.issubset(set(RMU_FIELDS))
    assert RMU_LABELS["database_unique"] == "数据库是否唯一"
    assert RMU_LABELS["device_complete"] == "环网柜设备是否完整"


def test_profile_button_and_artifact_are_removed():
    combined = "\n".join([
        _read("src/dmm/ui/main_window.py"),
        _read("src/dmm/application/job_worker.py"),
    ])
    assert "open_rmu_profile_csv_btn" not in combined
    assert "rmu_profile_csv" not in combined
    assert "打开环网柜档案 CSV" not in combined


def test_v369_simplified_workflow_is_still_present():
    main = _read("src/dmm/ui/main_window.py")
    worker = _read("src/dmm/application/job_worker.py")
    feeder = _read("src/dmm/application/modules/feeder.py")

    assert "self.preview_btn" not in main
    assert 'start_job("PREVIEW_ASSOCIATION")' not in main
    assert "模型校验 → 勾选可关联对象 → 执行模型关联" in main
    assert 'self.module.module_id in {"RMU", "FEEDER"}' in worker
    assert '"operation_reports": list(' in feeder
