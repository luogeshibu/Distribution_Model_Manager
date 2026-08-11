from pathlib import Path

from dmm.config.defaults import DEFAULT_DEVICE_RULES


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_rmu_validator_has_no_feeder_validation():
    text = (
        PROJECT_ROOT
        / "src"
        / "dmm"
        / "domain"
        / "rmu"
        / "validator.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "get_feeder_info(",
        "get_station_info(",
        "feeder_hint_from_g_filename",
        "normalize_feeder_text",
        "FEEDER_MISMATCH",
        "device_feeder_match",
        "file_feeder_hint",
        "g_file_feeder",
    ]

    for token in forbidden:
        assert token not in text, token


def test_rmu_report_has_no_feeder_columns_or_status():
    text = (
        PROJECT_ROOT
        / "src"
        / "dmm"
        / "infrastructure"
        / "reporting"
        / "writer.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        '"FEEDER":',
        '"g_file_feeder"',
        '"device_feeder_match"',
        '"file_feeder_hint"',
        '"feeder_match"',
    ]

    for token in forbidden:
        assert token not in text, token


def test_busdis_domain_remains_one():
    rule = DEFAULT_DEVICE_RULES["BusDis"]
    assert rule["table_id"] == 13506
    assert rule["domain"] == 1
