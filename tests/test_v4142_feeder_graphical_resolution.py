"""v4.1.101 supersedes graphical feeder resolution with filename authority."""
from pathlib import Path

from dmm.application.modules.feeder import FeederModelModule


class _DB:
    def find_substations_by_name(self, name, table_id=405):
        return [{"id": 40501, "name": "ABH"}] if name == "ABH" else []

    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        if int(station_id) == 40501 and feeder_name == "AH303":
            return [{"id": 700, "name": "AH303", "st_id": 40501}]
        return []

    def get_feeder_info(self, feeder_id, table_id=13500):
        return {"id": 700, "name": "AH303", "display_name": "ABH AH303", "station_name": "ABH"} if int(feeder_id) == 700 else None

    def get_rmu_records(self, name):
        raise AssertionError("RMU must not decide feeder")


def _g(tmp_path: Path):
    path = tmp_path / "JED-NTH-ABH-03.sln.pic.g"
    path.write_text('<G facID="999"><Layer><Text id="t" x="0" y="0" ts="RMU-A"/></Layer></G>', encoding="utf-8")
    return path


def test_feeder_uses_filename_only_and_ignores_graphical_devices(tmp_path):
    logs = []
    row, error = FeederModelModule()._resolve_file_feeder_result(_DB(), _g(tmp_path), {}, logs.append)
    assert error == ""
    assert row["id"] == 700
    assert row["_resolution_source"] == "FILENAME_405_13500"
    assert "filename_suffix=03" in row["_resolution_evidence"]


def test_feeder_ui_documents_filename_only_authority():
    source = Path("src/dmm/ui/widgets/feeder_settings.py").read_text(encoding="utf-8")
    assert "馈线唯一以 G 文件名为标准" in source
    assert "405/substation.NAME" in source
    assert "13500/dms_feeder_device.ST_ID" in source
    assert "self.feeder_resolution_mode = NoWheelComboBox()" not in source
    assert "self.manual_feeder_name = QLineEdit" not in source
