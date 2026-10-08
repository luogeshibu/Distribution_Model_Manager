from pathlib import Path


MAIN_WINDOW = Path(__file__).resolve().parents[1] / "src" / "dmm" / "ui" / "main_window.py"
BATCH_ORCHESTRATOR = Path(__file__).resolve().parents[1] / "src" / "dmm" / "application" / "batch_orchestrator.py"


def test_batch_ssh_snapshot_is_deferred_to_batch_worker():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    worker_block = text[
        text.index("class BatchValidationWorker(QThread):"):
        text.index("class BatchAssociationExecutionWorker(QThread):")
    ]
    start_block = text[
        text.index("    def start_batch_validation(self):"):
        text.index("    def _on_batch_validation_completed", text.index("    def start_batch_validation(self):"))
    ]
    assert "RemoteSnapshotService(" in worker_block
    assert "download_latest(" in worker_block
    assert "snapshot_service.download_latest" not in start_block
    assert "ssh_snapshot_request=ssh_snapshot_request" in start_block


def test_batch_candidate_filter_runs_in_execution_worker_not_gui_handler():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    worker_block = text[
        text.index("class BatchAssociationExecutionWorker(QThread):"):
        text.index("class CentralAdminOwnershipWorker(QThread):")
    ]
    apply_block = text[
        text.index("    def apply_batch_association(self):"):
        text.index("    def _on_batch_association_completed", text.index("    def apply_batch_association(self):"))
    ]
    assert "filter_validation_bundle_candidates(" in worker_block
    assert "filter_validation_bundle_candidates(" not in apply_block
    assert "selected_candidate_ids" in apply_block


def test_batch_final_publish_reports_file_progress():
    text = BATCH_ORCHESTRATOR.read_text(encoding="utf-8")
    assert "正在生成最终安全副本 {publish_index}/{publish_total}" in text
