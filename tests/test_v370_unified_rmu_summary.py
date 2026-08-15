
from pathlib import Path

from dmm.infrastructure.reporting.writer import (
    RMU_FIELDS,
    RMU_LABELS,
)


def test_unified_rmu_summary_contains_old_profile_information():
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


def test_workspace_has_no_rmu_profile_csv_artifact_or_button():
    root = Path(__file__).parents[1] / "src/dmm"
    combined = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [
            root / "ui/main_window.py",
            root / "application/job_worker.py",
        ]
    )

    assert "open_rmu_profile_csv_btn" not in combined
    assert "rmu_profile_csv" not in combined
    assert "打开环网柜档案 CSV" not in combined
