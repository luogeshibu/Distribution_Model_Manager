from dmm.application.modules.fuse import FuseModelModule


class _DB:
    def get_transformer_devices_by_name(self, name, feeder_id=None, table_id=13505):
        assert name == "97156"
        assert feeder_id is None
        assert table_id == 13505
        return [
            {"id": 1, "name": "97156", "feeder_id": None},
            {"id": 2, "name": "97156", "feeder_id": 100},
        ]

    def verify_keyid(self, keyid):
        raise AssertionError("must not verify FUSE keyid after non-unique transformer")

    def get_device_by_id(self, table_id, device_id):
        return None


def test_fuse_keeps_graphical_transformer_name_when_13505_is_not_unique():
    row = {
        "transformer_assignment_status": "MATCHED",
        "nearest_transformer_xml_id": "115000644",
        "nearest_transformer_name": "97156",
        "transformer_name_xml_id": "8000100",
        "transformer_name_direction": "top",
        "transformer_name_priority": "TOP",
        "transformer_name_distance": 43.863,
        "current_keyid": "",
    }
    feeder = {
        "ready": True,
        "feeder_id": 3799912185593856098,
        "feeder_source": "GRAPH_UNIQUE_RMU",
        "feeder_anchor": "RMU:43204",
        "feeder": {"id": 3799912185593856098, "name": "AH320", "display_name": "ADEL / AH320"},
    }

    resolved = FuseModelModule()._resolve_row(dict(row), _DB(), feeder)

    assert resolved["nearest_transformer_name"] == "97156"
    assert resolved["transformer_name_xml_id"] == "8000100"
    assert resolved["derived_fuse_name"] == "FUSE97156"
    assert resolved["transformer_name_resolution_status"] == "NO_UNIQUE_13505_CANDIDATE"
    assert resolved["transformer_13505_match_count"] == 2
    assert resolved["association_ready"] == "NO"
    assert resolved["writeback_needed"] == "NO"
    assert resolved["status"] == "FAIL"
    assert "FUSE_TRANSFORMER_DATABASE_NOT_UNIQUE" in resolved["reason"]
    assert "13505匹配数=2" in resolved["reason"]
