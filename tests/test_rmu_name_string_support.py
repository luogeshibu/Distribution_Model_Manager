from dmm.config.constants import RMU_LABEL_PATTERN
import re


def test_rmu_name_pattern_supports_engineering_names():
    pattern = re.compile(RMU_LABEL_PATTERN)

    valid = [
        "42646",
        "RMU-42646",
        "ABC_123",
        "JED-RMU-01",
        "RMU.42646",
        "A1",
    ]

    for name in valid:
        assert pattern.fullmatch(name), name


def test_rmu_name_pattern_rejects_obvious_non_names():
    pattern = re.compile(RMU_LABEL_PATTERN)

    invalid = [
        "",
        " RMU-42646",
        "RMU 42646",
        "RMU/42646",
        "RMU@42646",
    ]

    for name in invalid:
        assert not pattern.fullmatch(name), name
