from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/dmm/ui/widgets/rmu_settings.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_rmu_help_exposes_channel_status_database_rule_and_step():
    assert "Channel Status → 表 {RMU_CHANNEL_STATUS_TABLE_ID} / Domain {RMU_CHANNEL_STATUS_DOMAIN}" in SRC
    assert "步骤 6｜关联 Channel Status 状态图元" in SRC
    assert "channel_status.zt.icn.g" in SRC
    assert "dms_terminal_info.COMBINED_ID" in SRC
    assert "dms_channel_info" in SRC
    assert "CHAN_NAME 以 DR 结尾" in SRC
    assert "dms_channel_info.ID + (40 << 32)" in SRC


def test_rmu_help_exposes_channel_status_writeback_fields_and_safety():
    assert "app=6600000" in SRC
    assert "voltype=-1" in SRC
    assert "p_ReportType=1" in SRC
    assert "state=39" in SRC
    assert "keyid=Expected KeyID" in SRC
    assert "app1/voltype1/p_ReportType1/state1/keyid1" in SRC
    assert "步骤 7｜校验并回写" in SRC
    assert "再次实时查询并校验" in SRC


def test_v41102_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
