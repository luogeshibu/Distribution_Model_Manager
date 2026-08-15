from types import SimpleNamespace

from dmm.domain.rmu.validator import RmuValidator


class FakeDb:
    def verify_keyid(self, keyid):
        # expected keyid verification helper:
        # validator's table/domain checks are not exercised here.
        return {}


class DummyParser:
    pass


def _validator():
    rules = {
        "CBreakerDis": {
            "table_id": 13502,
            "domain": 40,
            "match_mode": "CODE_EQUALS_LOGICAL_CODE",
        }
    }
    return RmuValidator(
        db=FakeDb(),
        parser=DummyParser(),
        device_rules=rules,
        breaker_name_source="P_NAME_STRING",
    )


def test_find_by_code_ignores_unrelated_database_rows():
    validator = _validator()

    rows = [
        {"id": 1, "name": "Q1", "code": ""},
        {"id": 2, "name": "Y1", "code": ""},
        {"id": 3, "name": "Y2", "code": ""},
        {"id": 4, "name": "TR1", "code": "Q1"},
        {"id": 5, "name": "Y1-8723", "code": "Y1"},
        {"id": 6, "name": "Y2-22333", "code": "Y2"},
    ]

    assert [r["id"] for r in validator._find_by_code(rows, "Q1")] == [4]
    assert [r["id"] for r in validator._find_by_code(rows, "Y1")] == [5]
    assert [r["id"] for r in validator._find_by_code(rows, "Y2")] == [6]


def test_duplicate_relevant_code_is_an_error_condition():
    validator = _validator()

    rows = [
        {"id": 1, "code": "Y1"},
        {"id": 2, "code": "Y1"},
        {"id": 3, "code": "OTHER"},
    ]

    assert len(validator._find_by_code(rows, "Y1")) == 2
    assert len(validator._find_by_code(rows, "OTHER")) == 1
