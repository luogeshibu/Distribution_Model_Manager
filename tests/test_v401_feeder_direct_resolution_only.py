
from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule


class NameDB:
    def __init__(self):
        self.rows = [
            {
                "id": 1001,
                "name": "16",
                "st_id": 40501,
                "station_name": "ADF",
                "station_bv_id": 112871465660973067,
                "display_name": "ADF 16",
            }
        ]

    def get_feeder_info(self, feeder_id, table_id=13500):
        return None

    def find_feeders_by_name_hint(self, hint, table_id=13500):
        # Mimic DB helper broad matching: ADF16 returns the feeder.
        if "ADF16" in str(hint):
            return [dict(self.rows[0])]
        return []


def test_filename_can_match_db_station_feeder_suffix(tmp_path):
    g = tmp_path / "JED-CTL-ADF-16.sln.pic.g"
    g.write_text(
        '<G facID=""><Layer><FeedLine id="f1" ls="2"/></Layer></G>',
        encoding="utf-8",
    )
    row = FeederModelModule()._resolve_file_feeder(
        NameDB(),
        g,
        {
            "feeder_resolution_mode": "AUTO",
            "feeder_table_id": 13500,
            "manual_feeder_name": "",
        },
        lambda _msg: None,
    )
    assert row["id"] == 1001
    assert row["_resolution_source"] == "FILENAME"


def test_feeder_module_has_no_rmu_topology_fallback():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/application/modules/feeder.py"
    ).read_text(encoding="utf-8")

    assert "validator.validate_file(" not in source
    assert "validate_file_with_feeder_record" in source
    assert "_build_topology_regions" not in source
    assert "_validate_rmu_topology_region" not in source


def test_only_13503_database_write_path_exists():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/infrastructure/database/oracle.py"
    ).read_text(encoding="utf-8")

    assert source.upper().count("INSERT INTO") == 1
    assert source.upper().count("UPDATE ") == 0
    assert source.upper().count("DELETE ") == 0
    assert "table_id != 13503" in source
    assert "自动创建馈线段仅允许 DMS_SECTION_DEVICE / table_id=13503" in source


def test_id_is_checked_before_insert():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/infrastructure/database/oracle.py"
    ).read_text(encoding="utf-8")

    check_pos = source.index(
        'SELECT COUNT(*) FROM {table_name} WHERE id = :id'
    )
    insert_pos = source.index("INSERT INTO {table_name}")
    assert check_pos < insert_pos


def test_obsolete_rmu_topology_selector_removed():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/ui/widgets/feeder_settings.py"
    ).read_text(encoding="utf-8")

    assert "图纸类型识别" not in source
    assert "RMU 拓扑自动识别" not in source
    assert "自动：facID → 文件名 → 人工输入" in source
