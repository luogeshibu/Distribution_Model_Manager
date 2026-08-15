
from pathlib import Path

from dmm.infrastructure.reporting.writer import RMU_FIELDS, RMU_LABELS


def test_rmu_summary_hides_status_type_but_keeps_status_and_reason():
    assert "rmu_status" in RMU_FIELDS
    assert "rmu_reason" in RMU_FIELDS
    assert "rmu_severity" not in RMU_FIELDS

    assert RMU_LABELS["rmu_status"] == "状态"
    assert RMU_LABELS["rmu_reason"] == "说明"
    assert "rmu_severity" not in RMU_LABELS


def test_internal_rmu_severity_logic_is_still_present():
    validator = (
        Path(__file__).parents[1]
        / "src/dmm/domain/rmu/validator.py"
    ).read_text(encoding="utf-8")

    assert '"rmu_severity"' in validator
