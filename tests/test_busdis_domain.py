from dmm.config.defaults import DEFAULT_DEVICE_RULES
from dmm.domain.rmu.validator import RmuValidator


def test_busdis_default_domain_is_one():
    rule = DEFAULT_DEVICE_RULES["BusDis"]
    assert rule["table_id"] == 13506
    assert rule["domain"] == 1


def test_busdis_expected_keyid_domain_one():
    device_id = 3801601035454119950
    expected = 3801601039749087246

    assert (
        RmuValidator._make_expected_keyid(device_id, 1)
        == expected
    )
