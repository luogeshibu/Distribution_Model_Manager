from pathlib import Path


def test_association_execution_uses_live_log_callback_and_busy_progress():
    text = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "def live_association_log(text):" in text
    assert "self.progress_bar.setRange(0, 0)" in text
    assert "association_worker.log.connect(live_association_log)" in text
    assert "self.progress_bar.setRange(0, 100)" in text


def test_rmu_execution_logs_current_rmu_copy_and_writeback():
    text = Path("src/dmm/application/modules/rmu.py").read_text(encoding="utf-8")
    assert "正在执行环网柜模型关联：RMU=" in text
    assert "正在复制 G 文件到安全输出目录：" in text
    assert "正在回写 G 文件安全副本：" in text
    assert "待写设备数=" in text


def test_feeder_execution_logs_current_feeder_copy_and_writeback():
    text = Path("src/dmm/application/modules/feeder.py").read_text(encoding="utf-8")
    assert "正在执行馈线模型关联：文件=" in text
    assert "正在复制 G 文件到安全输出目录：" in text
    assert "正在回写 G 文件安全副本：" in text
    assert "待写FeedLine数=" in text


def test_new_live_association_messages_have_english_runtime_translation():
    from dmm.i18n import translate_runtime_text

    samples = [
        "正在执行模型关联，请查看实时日志……",
        "正在执行环网柜模型关联：RMU=38995；已选设备=7",
        "正在执行馈线模型关联：文件=A.g；区域=1；FEEDER_ID=123；已选对象=2",
        "正在复制 G 文件到安全输出目录：A.sln.pic.g",
        "正在回写 G 文件安全副本：A.sln.pic.g；待写设备数=7",
    ]
    for sample in samples:
        translated = translate_runtime_text(sample, "en_US")
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in translated), translated
