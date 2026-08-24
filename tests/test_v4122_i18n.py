from pathlib import Path

from dmm.config.defaults import DEFAULT_SETTINGS
from dmm.i18n import normalize_language, tr, translate_runtime_text
from dmm.infrastructure.reporting.writer import export_csv_bundle, export_html_bundle


def test_language_default_and_translation_contract():
    assert DEFAULT_SETTINGS["language"] == "zh_CN"
    assert normalize_language("English") == "en_US"
    assert normalize_language("zh-CN") == "zh_CN"
    assert tr("数据库", "en_US") == "Database"
    assert tr("模型校验", "en_US") == "Model Validation"
    # Engineering/status codes are never translated.
    assert tr("RMU_NAME_NOT_PARSED", "en_US") == "RMU_NAME_NOT_PARSED"
    assert translate_runtime_text("Oracle 预检查：通过", "en_US") == "Oracle pre-check: passed"


def test_rmu_report_can_export_english(tmp_path):
    report = {"file_name": "A.g", "rmu_results": []}
    html = tmp_path / "report.html"
    export_html_bundle(
        [report],
        html,
        {"CBreakerDis": {"table_id": 13502, "domain": 40}},
        language="en_US",
    )
    text = html.read_text(encoding="utf-8")
    assert '<html lang="en">' in text
    assert "Distribution Model Management Report" in text
    assert "RMU Summary" in text
    assert "Device Details" in text
    assert "Filter:" in text
    assert "RMU Name" in text

    paths = export_csv_bundle([report], tmp_path / "report.csv", language="en_US")
    assert paths[0].name.endswith("_rmu_summary.csv")
    assert paths[1].name.endswith("_device_details.csv")
    assert "RMU Name" in paths[0].read_text(encoding="utf-8-sig")


def test_feeder_report_can_export_english(tmp_path):
    report = {
        "report_type": "FEEDER",
        "file_name": "F.g",
        "feedline_rows": [],
        "feeder_records": [],
    }
    html = tmp_path / "feeder.html"
    export_html_bundle(
        [report],
        html,
        {"FeedLine": {"table_id": 13503, "domain": 1}},
        language="en_US",
    )
    text = html.read_text(encoding="utf-8")
    assert "Feeder Model Management Report" in text
    assert "Feeder Summary" in text
    assert "Feeder Section Details" in text
    assert "Feeder Name" in text
    assert "Orange CREATE" in text

    paths = export_csv_bundle([report], tmp_path / "feeder.csv", language="en_US")
    assert paths[0].name.endswith("_feeder_summary.csv")
    assert paths[1].name.endswith("_feeder_section_details.csv")
    assert "Database Feeder Name" in paths[0].read_text(encoding="utf-8-sig")
