from pathlib import Path

from dmm.i18n.translator import ZH_TO_EN, translate_runtime_text


def test_merged_top_level_pages_and_settings_have_english_labels():
    required = {
        "模型工作区": "Model Workspace",
        "图形工作区": "Graphics Workspace",
        "图元管理": "Element Management",
        "数据库": "Database",
        "运行历史": "Run History",
        "帮助": "Help",
        "设置": "Settings",
        "公共配置同步": "Shared Configuration Sync",
        "中央服务器": "Central Server",
        "中央服务器用户名": "Central Server Username",
        "中央服务器密码": "Central Server Password",
        "中央配置目录": "Central Configuration Directory",
        "保存本机连接配置": "Save Local Connection Settings",
        "连接并同步中央配置": "Connect and Sync Central Configuration",
        "保存并发布全部配置": "Save and Publish All Configuration",
        "抢占 Admin 权限": "Take Over Admin",
        "释放 Admin 权限": "Release Admin",
        "安全策略": "Safety Policy",
    }
    for source, expected in required.items():
        assert ZH_TO_EN.get(source) == expected


def test_graphics_workspace_language_is_bridged_to_embedded_gfilestudio():
    source = (
        Path(__file__).parents[1] / "src/dmm/ui/graphics_workspace.py"
    ).read_text(encoding="utf-8")
    assert "LanguageManager" in source
    assert "def set_language" in source
    assert 'self.gfs_settings.set_value("general/language", target)' in source
    assert "self.language_manager.translate_widget_tree(page)" in source


def test_english_runtime_console_fragments_are_fully_translated():
    samples = [
        "批量模型校验完成",
        "[发现柱上开关] 文件=",
        "[发现柱上变压器] 文件=",
        "[发现熔断器] 文件=",
        "图级馈线识别通过：唯一来源=文件名 -> 405/substation -> 13500/dms_feeder_device；FEEDER_ID=",
        "关联失败 CSV：",
    ]
    for source in samples:
        rendered = translate_runtime_text(source, "en_US")
        assert not any("\u3400" <= ch <= "\u9fff" for ch in rendered), rendered
