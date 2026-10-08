from pathlib import Path

from dmm.config.defaults import DEFAULT_DEVICE_RULES

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_rmu_module_uses_filename_feeder_resolution_for_all_drawings():
    text = (
        PROJECT_ROOT / "src" / "dmm" / "application" / "modules" / "rmu.py"
    ).read_text(encoding="utf-8")
    assert "resolve_drawing_feeder" in text
    assert "required_feeder_id" in text
    assert 'if drawing_type == "SINGLE_FEEDER"' not in text
    assert 'report["feeder_context_required"] = "YES"' in text


def test_rmu_validator_filters_same_name_database_records_by_required_feeder():
    text = (
        PROJECT_ROOT / "src" / "dmm" / "domain" / "rmu" / "validator.py"
    ).read_text(encoding="utf-8")
    assert "_filter_rmu_records_by_feeder" in text
    assert "RMU_NOT_FOUND_IN_CURRENT_FEEDER" in text
    assert "RMU_DUPLICATE_IN_FEEDER" in text


def test_busdis_domain_remains_one():
    rule = DEFAULT_DEVICE_RULES["BusDis"]
    assert rule["table_id"] == 13506
    assert rule["domain"] == 1
