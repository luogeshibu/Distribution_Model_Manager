
from pathlib import Path


def _main():
    return (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")


def test_source_selector_is_explicitly_shared_by_rmu_and_feeder():
    main = _main()
    assert "文件来源（RMU / 馈线通用）" in main
    assert "RMU 与 FEEDER 共用完全相同的" in main


def test_feeder_validation_uses_same_remote_snapshot_service():
    main = _main()

    # start_job is model-generic: no RMU-only branch protects SSH snapshot.
    assert "source_type = self._current_input_source()" in main
    assert "snapshot_service = RemoteSnapshotService(" in main
    assert "files, source_info = snapshot_service.download_latest(" in main

    # Both FEEDER and RMU ultimately receive the resolved snapshot Paths.
    assert "JobWorker(" in main
    assert "self.current_snapshot_files = list(files)" in main


def test_association_for_feeder_also_uses_validation_snapshot_only():
    main = _main()
    assert "files = [" in main
    assert "for p in (self.current_snapshot_files or [])" in main
    assert "关联必须使用本次 remote_input 快照" in main
