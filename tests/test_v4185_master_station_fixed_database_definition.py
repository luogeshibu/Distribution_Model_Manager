from pathlib import Path

from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES
from dmm.config.settings import _enforce_fixed_master_station_rules


def test_master_station_fixed_database_definition_values():
    assert DEFAULT_MASTER_STATION_RULES["CBreaker"]["table_id"] == 407
    assert DEFAULT_MASTER_STATION_RULES["CBreaker"]["domain"] == 40
    assert DEFAULT_MASTER_STATION_RULES["Disconnector"]["table_id"] == 408
    assert DEFAULT_MASTER_STATION_RULES["Disconnector"]["domain"] == 30
    assert DEFAULT_MASTER_STATION_RULES["GroundDisconnector"]["table_id"] == 409
    assert DEFAULT_MASTER_STATION_RULES["GroundDisconnector"]["domain"] == 30


def test_stale_master_station_overrides_are_sanitized_in_config_layer():
    settings = {
        "master_station_rules": {
            "CBreaker": {"table_id": 999, "domain": 9},
            "Disconnector": {"table_id": 998, "domain": 8},
            "GroundDisconnector": {"table_id": 997, "domain": 7},
        }
    }
    _enforce_fixed_master_station_rules(settings)
    assert settings["master_station_rules"] == DEFAULT_MASTER_STATION_RULES


def test_master_station_settings_ui_is_read_only_description():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "dmm" / "ui" / "widgets" / "master_station_settings.py"
    ).read_text(encoding="utf-8")
    assert 'QGroupBox("配网主站设备自动关联完整逻辑（只读说明）")' in source
    assert "回写哪些字段" in source
    assert "NoWheelSpinBox" not in source
    assert "恢复主站设备默认配置" not in source
    assert 'int(default["table_id"])' in source
    assert 'int(default["domain"])' in source


def test_master_station_application_module_implementation_is_unchanged_from_v4184():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "dmm" / "application" / "modules" / "master_station.py"
    ).read_text(encoding="utf-8")
    assert 'saved = (settings or {}).get("master_station_rules", {}) or {}' in source
    assert 'item.update(saved.get(tag, {}) or {})' in source
