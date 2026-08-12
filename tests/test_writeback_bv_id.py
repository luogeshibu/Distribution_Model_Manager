from dmm.application.modules.rmu import RmuModelModule


def test_rmu_breaker_writeback_uses_bv_id_as_voltype():
    attrs = RmuModelModule._attributes_for_row({
        "object_type": "CBreakerDis",
        "xml_id": "117000001",
        "expected_keyid": 100,
        "db_bv_id": 112871465660973067,
    })
    assert attrs["voltype"] == "112871465660973067"
    assert attrs["state"] == "41"


def test_rmu_ground_writeback_uses_bv_id_as_voltype():
    attrs = RmuModelModule._attributes_for_row({
        "object_type": "ZhaiWaiJieDiDaoZha",
        "xml_id": "188000001",
        "expected_keyid": 101,
        "db_bv_id": 112871465660973067,
    })
    assert attrs["voltype"] == "112871465660973067"
    assert attrs["state"] == "41"


def test_rmu_bus_writeback_uses_bv_id_as_voltype():
    attrs = RmuModelModule._attributes_for_row({
        "object_type": "BusDis",
        "xml_id": "38000001",
        "expected_keyid": 102,
        "db_bv_id": 112871465660973067,
    })
    assert attrs["voltype"] == "112871465660973067"
    assert attrs["state"] == "15"
