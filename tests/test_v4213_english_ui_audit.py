import ast
import re
from pathlib import Path

from dmm.i18n.translator import translate_runtime_text

ROOT = Path(__file__).parents[1]
HAN = re.compile(r"[\u3400-\u9fff]")


def _assert_english(source: str):
    rendered = translate_runtime_text(source, "en_US")
    assert not HAN.search(rendered), (source, rendered)


def test_reported_english_screens_have_no_chinese_presentation_text():
    samples = [
        "当前仅使用本机缓存；启动未访问中央仓库。本机配置可修改保存，可手动同步中央配置；发布中央仓库需要 Admin。",
        "当前仅使用本机缓存；软件启动不会访问中央配置。只有手动点击【连接并同步中央配置】才会读取并覆盖本机共享配置缓存。",
        "普通客户端可修改、测试、刷新并保存本机配置，也可手动同步中央配置；只有【保存并同步到中央仓库】需要先抢占 Admin。",
        "SSH只读模式：模型校验会重新下载服务器当前最新 G 文件。",
        "按指定方向",
        "保护 / EFI 关联范围",
        "所有环网柜都关联保护 / EFI",
        "仅 SMART 智能环网柜关联保护 / EFI",
        "环网柜名称来源",
        "服务器图元库",
        "READY · 服务器已同步",
    ]
    for source in samples:
        _assert_english(source)


def test_settings_safety_policy_is_fully_english():
    source = """• 当前工作目录下自动生成的报告保留 30 天
• 软件启动不检查 Oracle/SSH/中央服务器；只有显式操作才连接。成为 Admin 后仅每 10 秒轻量检查一次 Admin 所有权
• 每次执行模型任务时才进行 Oracle 预检查
• 模型回写必须先生成校验候选
• 原始 G 文件不修改；关联前先复制到 Workspace 安全副本
• 回写目标必须通过 G 图元类型 + XML ID 唯一定位
• G 文件采用临时文件写入后原子替换
• 文件与目录选择会自动记住上一次位置
• SSH 文件服务器严格只读；每次模型校验重新下载当前最新版本，关联锁定该次快照"""
    _assert_english(source)


def test_all_direct_dmm_ui_literals_translate_without_cjk():
    widget_ctor_names = {
        "QLabel", "QGroupBox", "QPushButton", "QCheckBox", "QRadioButton",
        "QAction", "QListWidgetItem",
    }
    setter_names = {
        "setText", "setTitle", "setPlaceholderText", "addItem", "setToolTip",
        "setStatusTip", "setWindowTitle", "setHorizontalHeaderLabels",
        "setVerticalHeaderLabels",
    }
    failures = []
    for path in (ROOT / "src/dmm/ui").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            values = []
            if name in widget_ctor_names or (isinstance(func, ast.Attribute) and name in setter_names):
                try:
                    value = ast.literal_eval(node.args[0])
                except Exception:
                    continue
                values = list(value) if isinstance(value, (list, tuple)) else [value]
            for value in values:
                if isinstance(value, str) and HAN.search(value):
                    rendered = translate_runtime_text(value, "en_US")
                    if HAN.search(rendered):
                        failures.append((path.name, node.lineno, value, rendered))
    assert not failures, failures[:20]


def test_embedded_gfilestudio_runtime_i18n_is_installed_and_has_remote_source_terms():
    graphics = (ROOT / "src/dmm/ui/graphics_workspace.py").read_text(encoding="utf-8")
    gfs_i18n = (ROOT / "src/g_file_studio/i18n.py").read_text(encoding="utf-8")
    assert "app.installEventFilter(self.language_manager)" in graphics
    for source, english in {
        "共享连接配置": "Shared Connection Settings",
        "文件服务器：": "File Server: ",
        "业务 G 根目录：": "Business G Root: ",
        "已从本机缓存恢复 ": "Restored ",
        " 缓存时间：": " Cache time: ",
    }.items():
        assert source in gfs_i18n
        assert english in gfs_i18n


def test_language_pass_runs_again_after_dynamic_page_refreshes():
    source = (ROOT / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    anchor = "# v4.2.13: several pages rebuild status/help text after the first"
    assert anchor in source
    tail = source[source.index(anchor):]
    assert "retranslate_qt_tree(self, self.language)" in tail
