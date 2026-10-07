from pathlib import Path


def test_makkah_feeder_help_matches_multi_feeder_pool_logic():
    src = Path("src/dmm/ui/widgets/feeder_settings.py").read_text(encoding="utf-8")
    for text in (
        "1. 扫描当前环网图全部主网馈线",
        "2. 唯一确认变电站和馈线",
        "3. 校验已有 FeedLine 关联",
        "4. 汇总全部空闲 13503",
        "5. 未关联 FeedLine 优先复用",
        "6. 资源不足时才创建 13503",
        "7. HTML 报告列出全部识别结果",
        "本图已确认馈线集合",
        "不更换 13503.ID",
        "可用馈线段资源池",
        "只创建实际缺少数量",
        "HTML 必须列出主网 Bay 扫描到的全部馈线",
        "优先复用本图有效馈线下的空闲馈线段，不足时仅创建缺少数量",
    ):
        assert text in src


def test_old_first_feeder_ui_description_is_removed():
    src = Path("src/dmm/ui/widgets/feeder_settings.py").read_text(encoding="utf-8")
    assert "馈线模型任选其中一条作为整图目标" not in src
    assert "当前 G 图全部 FeedLine 都统一归到这条目标馈线" not in src
