from dmm.domain.rmu.validator import RmuValidator


def test_domain_zero_keyid_equals_device_id():
    device_id = 3801610135454131518
    assert (
        RmuValidator._make_expected_keyid(device_id, 0)
        == device_id
    )


def test_domain_40_keyid_encoding():
    device_id = 3800475135547315502
    expected = 3800475307346007342

    assert (
        RmuValidator._make_expected_keyid(device_id, 40)
        == expected
    )


def test_domain_40_offset_is_40_times_2_pow_32():
    device_id = 3800475135547315502
    keyid = RmuValidator._make_expected_keyid(device_id, 40)

    assert keyid - device_id == 40 * (2 ** 32)
