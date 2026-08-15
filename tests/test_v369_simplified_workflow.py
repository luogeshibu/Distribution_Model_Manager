
from pathlib import Path


def _read(rel):
    return (
        Path(__file__).parents[1] / rel
    ).read_text(encoding="utf-8")


def test_workspace_has_no_preview_button_or_preview_user_task():
    main = _read("src/dmm/ui/main_window.py")
    assert 'QPushButton("模型关联预览")' not in main
    assert "self.preview_btn" not in main
    assert 'start_job("PREVIEW_ASSOCIATION")' not in main
    assert "模型校验 → 勾选可关联对象 → 执行模型关联" in main


def test_validation_builds_candidates_for_rmu_and_feeder():
    worker = _read("src/dmm/application/job_worker.py")
    assert 'self.module.module_id in {"RMU", "FEEDER"}' in worker
    assert "preview_association(" in worker
    assert '"PREVIEW_ASSOCIATION": ("preview"' not in worker


def test_feeder_apply_returns_operation_scoped_reports():
    feeder = _read("src/dmm/application/modules/feeder.py")
    assert '"operation_reports": list(' in feeder
    assert "ASSOCIATION_EXECUTED_SUCCESS" in feeder


def test_main_window_does_not_full_revalidate_rmu_or_feeder_after_apply():
    main = _read("src/dmm/ui/main_window.py")
    assert 'if module_id in {"RMU", "FEEDER"}:' in main
    assert "不再对整张 G 图重新循环校验" in main
