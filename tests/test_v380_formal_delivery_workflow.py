
from pathlib import Path


def _read(rel):
    return (
        Path(__file__).parents[1] / rel
    ).read_text(encoding="utf-8")


def test_run_history_and_manifest_are_present():
    main = _read("src/dmm/ui/main_window.py")
    assert '"运行历史"' in main
    assert "def _build_history_page" in main
    assert "run_manifest.json" in main
    assert "def _write_run_manifest" in main


def test_association_change_log_is_present():
    main = _read("src/dmm/ui/main_window.py")
    assert "model_change_log.csv" in main
    assert "def _export_model_change_log" in main
    assert '"修改前"' in main
    assert '"修改后"' in main
    assert "打开修改记录 CSV" in main


def test_execution_confirmation_and_summary_are_actionable():
    main = _read("src/dmm/ui/main_window.py")
    assert "涉及 G 文件" in main
    assert "候选状态" in main
    assert "确认执行模型关联" in main
    assert "打开结果目录" in main
    assert "打开修改记录" in main


def test_about_and_read_only_notice_are_present():
    main = _read("src/dmm/ui/main_window.py")
    assert "关于 / 版本信息" in main
    assert "APP_BUILD_DATE" in main
    assert "数据库访问模式：只读查询" in main
    assert "不会向 Oracle 数据库执行 INSERT / UPDATE / DELETE" in main


def test_release_check_assets_exist():
    root = Path(__file__).parents[1]
    assert (root / "release_check.ps1").exists()
    assert (root / "RELEASE_CHECKLIST.md").exists()
