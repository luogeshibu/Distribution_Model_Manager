
from pathlib import Path

ROOT = Path(__file__).parents[1]

def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")

def test_feeder_ui_has_only_three_identification_sources():
    text = _read("src/dmm/ui/widgets/feeder_settings.py")
    assert "G 根节点 facID" in text
    assert "文件名" in text
    assert "人工输入" in text
    assert "RMU + 连接拓扑 + FEEDER_ID" not in text
    assert "可信 RMU" not in text

def test_feeder_help_explicitly_rejects_rmu_topology_fallback():
    text = _read("src/dmm/ui/main_window.py")
    assert "不再使用 RMU、环网柜、连接拓扑或 FEEDER_ID 反向推断馈线" in text
    assert "facID" in text and "文件名" in text and "人工输入" in text
