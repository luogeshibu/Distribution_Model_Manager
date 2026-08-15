
from pathlib import Path


def test_rmu_profile_is_merged_into_summary():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/infrastructure/reporting/writer.py"
    ).read_text(encoding="utf-8")

    assert 'base.name + "_环网柜档案.csv"' not in source
    assert "flatten_rmu_profile_rows" not in source
    assert '"database_unique"' in source
    assert "<h2>环网柜汇总</h2>" in source
