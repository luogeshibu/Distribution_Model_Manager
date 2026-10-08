from pathlib import Path

from dmm.application.modules.feeder_context import enforce_device_feeder_membership, resolve_drawing_feeder
from dmm.domain.gfile.parser import GParser


class DB:
    def __init__(self, feeder_id=700):
        self.feeder_id = feeder_id
        self.calls = []
    def find_substations_by_name(self, name, table_id=405):
        self.calls.append(("station", name))
        return [{"id": 40501, "name": "ABH"}] if name == "ABH" else []
    def find_feeders_by_station_and_name(self, station_id, feeder_name, table_id=13500):
        self.calls.append(("feeder", feeder_name))
        return [{"id": self.feeder_id, "name": feeder_name, "st_id": station_id}] if feeder_name == "AH303" else []
    def get_feeder_info(self, feeder_id, table_id=13500):
        return {"id": int(feeder_id), "name": "AH303", "display_name": "ABH AH303", "station_name": "ABH"}
    def get_rmu_records(self, name):
        raise AssertionError("RMU must not decide feeder")
    def get_combined_device_records(self, name):
        raise AssertionError("Pole switch must not decide feeder")
    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        raise AssertionError("Transformer must not decide feeder")


def _parse(tmp_path, name="JED-NTH-ABH-03.sln.pic.g"):
    p=Path(tmp_path)/name
    p.write_text('<G><Layer><Rect id="r" x="0" y="0" w="10" h="10"/></Layer></G>',encoding="utf-8")
    return GParser().parse(p)


def test_filename_has_absolute_priority_and_devices_are_not_queried(tmp_path):
    db=DB(700)
    result=resolve_drawing_feeder(db,_parse(tmp_path),{})
    assert result["ready"] is True
    assert result["feeder_id"] == 700
    assert result["feeder_source"] == "FILENAME_405_13500"
    assert db.calls == [("station","ABH"),("feeder","AH303")]


def test_invalid_filename_is_hard_block_before_database(tmp_path):
    db=DB()
    result=resolve_drawing_feeder(db,_parse(tmp_path,"ABH-03.sln.pic.g"),{})
    assert result["ready"] is False
    assert result["feeder_source"] == "FILENAME_INVALID"
    assert db.calls == []


def test_non_rmu_device_must_belong_to_filename_resolved_feeder(tmp_path):
    resolution=resolve_drawing_feeder(DB(700),_parse(tmp_path),{})
    row={"status":"UNLINKED","association_ready":"YES","writeback_needed":"YES"}
    enforce_device_feeder_membership(row,resolution,device_feeder_id=800,reason_prefix="POLE_SWITCH")
    assert row["association_ready"] == "NO"
    assert row["writeback_needed"] == "NO"
    assert row["reason"].startswith("POLE_SWITCH_FEEDER_MISMATCH:")


def test_rmu_module_uses_filename_feeder_resolver_for_every_drawing():
    source=Path("src/dmm/application/modules/rmu.py").read_text(encoding="utf-8")
    assert "resolve_drawing_feeder" in source
    assert 'if drawing_type == "SINGLE_FEEDER"' not in source
    assert 'report["feeder_context_required"] = "YES"' in source
    assert "required_feeder_id" in source
