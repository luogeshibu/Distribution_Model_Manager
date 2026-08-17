
from pathlib import Path


def test_local_source_stack_uses_current_page_height_only():
    main = (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")

    assert "def _update_input_source_stack_height" in main
    assert 'if self._current_input_source() == "LOCAL"' in main
    assert "height = min(height, 58)" in main
    assert "self.input_source_stack.setMaximumHeight(height)" in main
    assert "QTimer.singleShot(" in main


def test_ssh_logic_remains_present():
    main = (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")

    assert "SSH 文件服务器（只读）" in main
    assert "RemoteSnapshotService" in main
    assert "self.current_snapshot_files" in main
