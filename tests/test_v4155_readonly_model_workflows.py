from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8")


def test_rmu_database_knobs_replaced_by_readonly_workflow():
    src = read("src/dmm/ui/widgets/rmu_settings.py")
    assert "RMU 自动关联逻辑（只读说明）" in src
    assert "RMU 设备数据库表与域配置（可编辑）" not in src
    assert "步骤 1｜识别环网柜框" in src
    assert "步骤 7｜校验并回写" in src


def test_master_station_database_knobs_replaced_by_readonly_workflow():
    src = read("src/dmm/ui/widgets/master_station_settings.py")
    assert "配网主站设备自动关联逻辑（只读说明）" in src
    assert "数据库表与域配置（可编辑）" not in src
    assert "步骤 3｜解析变电站和 Bay" in src
    assert "BAY_ID" in src


def test_feeder_db_mapping_replaced_by_readonly_makkah_ring_workflow():
    src = read("src/dmm/ui/widgets/feeder_settings.py")
    assert "麦加馈线自动关联逻辑（只读说明）" in src
    assert "馈线段数据库表与域配置" not in src
    assert "self.feeder_drawing_mode" not in src
    assert "校验已有 FeedLine 关联" in src
    assert "汇总全部空闲 13503" in src
    assert "HTML 报告列出全部识别结果" in src
    assert "self.auto_create_missing_sections" in src


def test_other_model_pages_keep_readonly_business_rules_but_allow_pole_element_lists():
    pole = read("src/dmm/ui/widgets/pole_switch_settings.py")
    transformer = read("src/dmm/ui/widgets/transformer_settings.py")
    fuse = read("src/dmm/ui/widgets/fuse_settings.py")
    assert "柱上开关模型配置" in pole
    assert "柱上开关图元名单" in pole
    assert "直接按 13501/dms_combined_device.NAME 精确匹配" in pole
    assert "不删除空格、横线、点号等字符" in pole
    assert "不识别、不要求、不校验 FEEDER_ID" in pole
    assert "柱上变压器模型配置" in transformer
    assert "柱上变压器图元名单" in transformer
    assert "全局距离从近到远一对一分配" in transformer
    assert "不识别、不要求、不校验 FEEDER_ID" in transformer
    assert "熔断器自动关联完整逻辑（只读说明）" in fuse
    assert "13513" in fuse and "不识别、不要求、不校验 FEEDER_ID" in fuse
