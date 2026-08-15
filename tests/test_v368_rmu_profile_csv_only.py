
from pathlib import Path

def test_rmu_profile_is_csv_only():
    source = (Path(__file__).parents[1] / "src/dmm/infrastructure/reporting/writer.py").read_text(encoding="utf-8")
    assert 'base.name + "_环网柜档案.csv"' in source
    assert "flatten_rmu_profile_rows(reports)" in source
    assert "<h2>环网柜档案</h2>" not in source
    assert "{rmu_profile_table}" not in source
