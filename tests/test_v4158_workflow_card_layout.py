from pathlib import Path


def read(path):
    return Path(path).read_text(encoding="utf-8")


def test_makkah_model_workflows_use_separate_step_cards():
    rmu = read("src/dmm/ui/widgets/rmu_settings.py")
    master = read("src/dmm/ui/widgets/master_station_settings.py")
    feeder = read("src/dmm/ui/widgets/feeder_settings.py")
    pole = read("src/dmm/ui/widgets/pole_switch_settings.py")
    transformer = read("src/dmm/ui/widgets/transformer_settings.py")
    fuse = read("src/dmm/ui/widgets/fuse_settings.py")
    assert "workflow_card(" in rmu
    assert "步骤 1｜识别环网柜框" in rmu
    assert "def step(" in master
    assert "步骤 1｜识别主网 Bay 框" in master
    assert "def step(" in feeder
    assert "_logic_label(" in pole and "1. 识别哪些设备" in pole
    assert "_logic_label(" in transformer and "1. 识别哪些设备" in transformer
    assert "_logic_label(" in fuse and "1. 识别哪些设备" in fuse


def test_workflow_cards_use_common_readable_padding():
    for path in [
        "src/dmm/ui/widgets/rmu_settings.py",
        "src/dmm/ui/widgets/master_station_settings.py",
        "src/dmm/ui/widgets/feeder_settings.py",
        "src/dmm/ui/widgets/pole_switch_settings.py",
        "src/dmm/ui/widgets/transformer_settings.py",
        "src/dmm/ui/widgets/fuse_settings.py",
    ]:
        src = read(path)
        assert "padding:4px 7px" in src
