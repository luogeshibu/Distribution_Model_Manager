
from pathlib import Path

from dmm.domain.rmu.validator import RmuValidator


def test_default_device_row_never_seeds_logical_code_from_xml_pnamestring():
    class Elem:
        tag = "CBreakerDis"
        xml_id = "117000001"
        keyid = ""
        attrs = {"p_NameString": "SHOULD_NOT_BE_USED"}

    row = RmuValidator._default_device_row(
        "25583",
        9001,
        Elem(),
        {"table_id": 13502, "domain": 40, "match_mode": "CODE_EQUALS_LOGICAL_CODE"},
        {"table_name": "dms_cb_device"},
    )
    assert row["logical_code"] == ""
    assert "p_name_string" not in row


def test_main_window_help_source_has_no_removed_policy_variables():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "dmm"
        / "ui"
        / "main_window.py"
    ).read_text(encoding="utf-8")

    assert "policy_text.setWordWrap" not in source
    assert "policy_layout.addWidget(policy_text)" not in source
    assert "layout.addWidget(policy)" not in source
    assert "naming_text.setWordWrap(True)" in source
    assert "naming_layout.addWidget(naming_text)" in source
    assert "layout.addWidget(naming)" in source


def test_business_code_uses_logical_code_not_p_name_string():
    root = Path(__file__).parents[1] / "src" / "dmm"
    business_files = [
        root / "domain" / "rmu" / "validator.py",
        root / "application" / "modules" / "rmu.py",
        root / "infrastructure" / "reporting" / "writer.py",
        root / "ui" / "main_window.py",
    ]
    combined = "\n".join(p.read_text(encoding="utf-8") for p in business_files)

    assert '"logical_code"' in combined
    assert '"p_name_string"' not in combined
