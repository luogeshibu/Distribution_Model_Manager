
from pathlib import Path

ROOT = Path(__file__).parents[1]

def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")

def test_feeder_ui_has_filename_as_only_authoritative_source():
    text = _read("src/dmm/ui/widgets/feeder_settings.py")
    assert "馈线唯一以 G 文件名为标准" in text
    assert "405/substation.NAME" in text
    assert "13500/dms_feeder_device.ST_ID" in text
    assert "环网柜、柱上开关、柱上变压器或其它设备反推馈线" in text

def test_feeder_help_explicitly_rejects_rmu_topology_fallback():
    text = _read("src/dmm/ui/main_window.py")
    assert "唯一来源：G 文件名" in text
    assert "facID" in text and "文件名" in text and "人工选择" in text
