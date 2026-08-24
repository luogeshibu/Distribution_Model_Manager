from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "dmm" / "ui" / "main_window.py"


def _body(text: str, name: str, next_name: str) -> str:
    start = text.index(f"    def {name}")
    end = text.index(f"    def {next_name}", start)
    return text[start:end]


def test_association_backend_runs_in_qthread_and_gui_waits_via_event_loop():
    text = MAIN.read_text(encoding="utf-8")
    assert "class AssociationExecutionWorker(QThread)" in text
    worker_start = text.index("class AssociationExecutionWorker(QThread)")
    worker_end = text.index("class MainWindow", worker_start)
    worker = text[worker_start:worker_end]
    assert "OracleClient(self.db_config)" in worker
    assert "self.module.apply_association(" in worker
    assert "self.completed.emit(result_bundle)" in worker

    body = _body(text, "apply_association", "copy_log")
    assert "AssociationExecutionWorker(" in body
    assert "association_worker.start()" in body
    assert "association_loop.exec()" in body
    assert "module.apply_association(" not in body


def test_association_uses_indeterminate_busy_progress_until_completion():
    text = MAIN.read_text(encoding="utf-8")
    body = _body(text, "apply_association", "copy_log")
    assert "self.progress_bar.setRange(0, 0)" in body
    assert "self.progress_bar.setTextVisible(False)" in body
    assert "self.progress_bar.setRange(0, 100)" in body
    assert "self.progress_bar.setTextVisible(True)" in body
    assert 'self.progress_bar.setFormat("%p%")' in body


def test_new_association_busy_messages_translate_to_english():
    from dmm.i18n import translate_runtime_text

    samples = [
        "模型关联写回完成，正在整理执行结果……",
        "模型关联后台任务异常结束，未返回执行结果。",
    ]
    for sample in samples:
        translated = translate_runtime_text(sample, "en_US")
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in translated), translated
