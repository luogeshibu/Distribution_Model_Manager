from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "dmm" / "ui" / "main_window.py"


def _body(text: str, name: str, next_name: str) -> str:
    start = text.index(f"    def {name}")
    end = text.index(f"    def {next_name}", start)
    return text[start:end]


def test_remote_refresh_ssh_io_runs_in_qthread_not_gui_method():
    text = MAIN.read_text(encoding="utf-8")
    assert "class RemoteGFileListWorker(QThread)" in text
    worker = text[text.index("class RemoteGFileListWorker(QThread)"):text.index("class MainWindow", text.index("class RemoteGFileListWorker(QThread)"))]
    assert "client.list_g_files" in worker
    assert "self.completed.emit(rows)" in worker

    body = _body(text, "refresh_remote_g_files", "_update_remote_refresh_wait_status")
    assert "RemoteGFileListWorker(cfg)" in body
    assert "worker.start()" in body
    assert "with ReadOnlySshClient" not in body
    assert "client.list_g_files" not in body


def test_remote_refresh_has_live_wait_status_and_duplicate_guard():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "refresh_remote_g_files", "_update_remote_refresh_wait_status")
    assert "self.remote_list_worker.isRunning()" in body
    assert "self.refresh_ssh_btn.setEnabled(False)" in body
    assert "self._remote_refresh_timer.start()" in body

    wait_body = _body(text, "_update_remote_refresh_wait_status", "_on_remote_g_files_loaded")
    assert "界面仍可正常操作" in wait_body
    assert "The application remains responsive" in wait_body


def test_remote_refresh_completion_preserves_changed_list_pipeline():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "_on_remote_g_files_loaded", "_on_remote_g_files_failed")
    assert "self.remote_selected_names.intersection_update(current_names)" in body
    assert "same_files" in body
    assert "self.remote_file_rows = rows" in body
    assert "self._rebuild_remote_file_table()" in body
    assert "self._apply_remote_file_filter" in body
    assert "self._invalidate_validation_snapshot" in body
