import ast
import re
from pathlib import Path

from dmm.i18n import translate_runtime_text

HAN = re.compile(r"[\u4e00-\u9fff]")


def test_reported_rmu_console_line_is_fully_english():
    source = (
        "[JED-CTL-AMR.sln.pic.g] 环网柜 38/53："
        "矩形框 XML ID=2000269；类型=2L1T；类型来源=TEXT_YQ；"
        "智能=YES；智能标识=SMART,SMR"
    )
    result = translate_runtime_text(source, "en_US")
    assert result == (
        "[JED-CTL-AMR.sln.pic.g] RMU 38/53: "
        "Frame XML ID=2000269; type=2L1T; type source=TEXT_YQ; "
        "smart=YES; smart markers=SMART,SMR"
    )
    assert not HAN.search(result)


def test_runtime_diagnostics_keep_codes_and_values_but_remove_chinese():
    samples = [
        "RMU_NAME_NOT_PARSED: 矩形框XML ID=123 未解析出环网柜名称；"
        "请检查环网柜名称方向配置、图内名称文字及其与矩形框的位置关系。"
        "环网柜身份未确定，禁止该RMU及柜内设备自动关联。",
        "[A.g] 正在处理馈线模型：A.g | 类型=SINGLE_FEEDER | "
        "CBreaker=1 | 置信度=HIGH | Bus=1 (有效母线=1) | "
        "源分支=0 | 标题锚点=1 | FeedLine=0 | 判据=SINGLE_SOURCE_CBREAKER",
        "SSH只读文件源：172.16.21.27:22 | /home/up8000/data/graph/display/sln",
        "服务器最终一致性检查通过：所有已选 G 文件在模型校验开始前均为最新稳定版本。",
        "本次馈线模型关联完成：选中对象=2，成功=2，跳过=0，数据库新增馈线段=1。",
    ]
    for source in samples:
        result = translate_runtime_text(source, "en_US")
        assert not HAN.search(result), (source, result)

    # Engineering/status tokens must remain stable across languages.
    result = translate_runtime_text(samples[0], "en_US")
    assert "RMU_NAME_NOT_PARSED" in result
    assert "XML ID=123" in result


def test_all_console_log_literal_fragments_have_english_translation():
    """Guard presentation-layer coverage without touching business logic."""
    project_root = Path(__file__).resolve().parents[1]
    targets = []
    for rel in (
        "src/dmm/application",
        "src/dmm/domain",
        "src/dmm/infrastructure",
    ):
        targets.extend((project_root / rel).rglob("*.py"))
    targets.append(project_root / "src/dmm/ui/main_window.py")

    callback_names = {"log", "log_callback", "progress_callback", "db_log"}
    untranslated = []
    for path in targets:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            else:
                continue
            if name not in callback_names:
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
                    continue
                if not HAN.search(child.value):
                    continue
                translated = translate_runtime_text(child.value, "en_US")
                if HAN.search(translated):
                    untranslated.append((str(path), child.lineno, child.value, translated))

    assert untranslated == []
