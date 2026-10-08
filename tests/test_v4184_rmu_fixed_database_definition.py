from pathlib import Path

from dmm.config.constants import (
    RMU_RELAY_SIGNAL_DOMAIN,
    RMU_RELAY_SIGNAL_TABLE_ID,
)
from dmm.config.defaults import DEFAULT_DEVICE_RULES


def test_rmu_fixed_database_definition_values():
    assert DEFAULT_DEVICE_RULES["CBreakerDis"]["table_id"] == 13502
    assert DEFAULT_DEVICE_RULES["CBreakerDis"]["domain"] == 40
    assert DEFAULT_DEVICE_RULES["ZhaiWaiJieDiDaoZha"]["table_id"] == 13514
    assert DEFAULT_DEVICE_RULES["ZhaiWaiJieDiDaoZha"]["domain"] == 40
    assert DEFAULT_DEVICE_RULES["BusDis"]["table_id"] == 13506
    assert DEFAULT_DEVICE_RULES["BusDis"]["domain"] == 1
    assert RMU_RELAY_SIGNAL_TABLE_ID == 13533
    assert RMU_RELAY_SIGNAL_DOMAIN == 40


def test_rmu_settings_ui_is_read_only_description():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "dmm" / "ui" / "widgets" / "rmu_settings.py"
    ).read_text(encoding="utf-8")
    assert 'QGroupBox("RMU 自动关联完整逻辑（只读说明）")' in source
    assert "回写哪些字段" in source
    assert "table = NoWheelSpinBox()" not in source
    assert "self.relay_table_spin = NoWheelSpinBox()" not in source
    assert 'table_id = int(default["table_id"])' in source
    assert 'domain = int(default["domain"])' in source
    assert "relay_table_id = int(RMU_RELAY_SIGNAL_TABLE_ID)" in source
    assert "relay_domain = int(RMU_RELAY_SIGNAL_DOMAIN)" in source
