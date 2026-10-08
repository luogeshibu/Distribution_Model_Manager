from pathlib import Path


def test_path_row_does_not_show_stale_path_warning():
    source = Path("src/g_file_studio/ui/widgets/path_row.py").read_text(encoding="utf-8")
    assert "QMessageBox.warning" not in source
    assert "上次路径不存在" not in source
    assert "上次目录不存在" not in source
    assert "restore_path() has already" in source

    template_source = Path("src/g_file_studio/ui/widgets/template_selector.py").read_text(encoding="utf-8")
    assert "上次导出模板使用的目录已经不存在" not in template_source


def test_stale_saved_paths_are_still_cleared_by_settings_service(tmp_path):
    from g_file_studio.services.user_settings_service import UserSettingsService

    ini = tmp_path / "user_settings.ini"
    settings = UserSettingsService(ini)
    missing = tmp_path / "does-not-exist"
    settings.set_path("demo/path", missing)

    result = settings.restore_path("demo/path", expect="directory")

    assert result.path is None
    assert result.missing_path == missing
    assert settings.get_path("demo/path") is None
