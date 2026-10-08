from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WIDGETS = ROOT / "src" / "dmm" / "ui" / "widgets"


def _source(name):
    return (WIDGETS / name).read_text(encoding="utf-8")


def test_database_definition_tables_are_replaced_by_logic_descriptions():
    rmu = _source("rmu_settings.py")
    master = _source("master_station_settings.py")
    feeder = _source("feeder_settings.py")

    assert 'QGroupBox("RMU 自动关联完整逻辑（只读说明）")' in rmu
    assert 'QGroupBox("RMU 设备数据库定义（固定）")' not in rmu

    assert 'QGroupBox("配网主站设备自动关联完整逻辑（只读说明）")' in master
    assert 'QGroupBox("配网主站设备数据库定义（固定）")' not in master

    assert 'QGroupBox("馈线自动关联完整逻辑（只读说明）")' in feeder
    assert 'QGroupBox("馈线段数据库表与域配置")' not in feeder
    assert "NoWheelSpinBox" not in feeder


def test_every_independent_module_explains_recognition_database_and_writeback():
    expected = {
        "rmu_settings.py": ["如何识别", "数据库怎样校验", "回写哪些字段"],
        "pole_switch_settings.py": ["识别哪些设备", "数据库关联链路", "回写哪些字段"],
        "transformer_settings.py": ["识别哪些设备", "数据库和馈线校验", "回写哪些字段"],
        "fuse_settings.py": ["识别哪些设备", "数据库和馈线校验", "回写哪些字段"],
        "master_station_settings.py": ["识别哪些设备", "怎样从数据库选目标设备", "回写哪些字段"],
        "feeder_settings.py": ["怎样判定当前图属于哪条馈线", "数据库补齐边界", "真正执行时写什么"],
    }
    for filename, markers in expected.items():
        source = _source(filename)
        for marker in markers:
            assert marker in source, f"{filename} missing {marker}"


def test_feeder_hidden_engineering_values_preserve_existing_config_contract():
    source = _source("feeder_settings.py")
    assert 'config.get("section_table_id", self.DEFAULT_SECTION_TABLE_ID)' in source
    assert 'config.get("section_domain", self.DEFAULT_SECTION_DOMAIN)' in source
    assert '"section_table_id": int(self._section_table_id)' in source
    assert '"section_domain": int(self._section_domain)' in source
