from pathlib import Path


def test_unlinked_model_uses_warn_status():
    validator_file = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "dmm"
        / "domain"
        / "rmu"
        / "validator.py"
    )
    text = validator_file.read_text(encoding="utf-8")

    assert 'row["model_link_status"] = "未关联"' in text
    assert 'row["status"] = "WARN"' in text
    assert 'row["reason"] = "MODEL_NOT_LINKED"' in text
