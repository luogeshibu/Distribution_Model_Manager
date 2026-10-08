from pathlib import Path

from dmm.application.modules.feeder_context import _graphical_pole_switch_candidates
from dmm.application.modules.pole_switch import (
    PoleSwitchModelModule,
    normalize_pole_switch_db_lookup_name,
)
from dmm.domain.gfile.parser import GParser


def _catalog(classification="LBS"):
    return {
        "records": [
            {"file_name": "sw.g", "root_id": "SWROOT", "classification": classification},
        ]
    }


class _CaptureDB:
    def __init__(self):
        self.lookups = []

    def get_combined_device_records(self, name):
        self.lookups.append(name)
        return []


def test_compound_business_name_keeps_hyphen_only_with_matching_classification():
    assert normalize_pole_switch_db_lookup_name("LBS96527-21240", "LBS") == "LBS96527-21240"
    assert normalize_pole_switch_db_lookup_name("LBS33513-97376", "LBS") == "LBS33513-97376"
    assert normalize_pole_switch_db_lookup_name("SEC96527-21240", "SEC") == "SEC96527-21240"
    assert normalize_pole_switch_db_lookup_name("AR96527-21240", "AR") == "AR96527-21240"
    assert normalize_pole_switch_db_lookup_name("ARC96527-21240", "AR") == "ARC96527-21240"

    # Classification mismatch does not activate the exception.
    assert normalize_pole_switch_db_lookup_name("SEC96527-21240", "LBS") == "SEC9652721240"


def test_historical_normalization_remains_unchanged_for_ordinary_names():
    assert normalize_pole_switch_db_lookup_name("SEC-2385", "SEC") == "SEC2385"
    assert normalize_pole_switch_db_lookup_name("SEC 2369", "SEC") == "SEC2369"
    assert normalize_pole_switch_db_lookup_name("SEC.2270", "SEC") == "SEC2270"
    assert normalize_pole_switch_db_lookup_name("LBS-2291", "LBS") == "LBS2291"
    # Existing one-argument API keeps its historical behavior.
    assert normalize_pole_switch_db_lookup_name("LBS96527-21240") == "LBS9652721240"


def test_pole_switch_model_queries_compound_name_verbatim_but_keeps_old_path_for_ordinary_name():
    db = _CaptureDB()
    compound = {
        "graphical_name": "LBS96527-21240",
        "current_keyid": "",
        "object_type": "AnyXmlTag",
        "xml_id": "sw1",
        "device_family": "LBS",
    }
    result = PoleSwitchModelModule()._resolve_row(compound, db)
    assert db.lookups == ["LBS96527-21240"]
    assert result["graphical_name"] == "LBS96527-21240"
    assert result["database_query_name"] == "LBS96527-21240"

    db = _CaptureDB()
    ordinary = dict(compound, graphical_name="SEC-2385", device_family="SEC")
    result = PoleSwitchModelModule()._resolve_row(ordinary, db)
    assert db.lookups == ["SEC2385"]
    assert result["graphical_name"] == "SEC-2385"
    assert result["database_query_name"] == "SEC2385"


def test_feeder_context_uses_same_compound_lookup_rule(tmp_path):
    g = tmp_path / "case.g"
    g.write_text(
        '<G><Layer>'
        '<AnyXmlTag id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>'
        '<Text id="t1" x="100" y="60" w="200" h="20" ts="LBS96527-21240" lc="255,0,0"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    db = _CaptureDB()
    _rows, candidates = _graphical_pole_switch_candidates(
        db,
        GParser().parse(g),
        {"element_catalog": _catalog("LBS")},
    )
    assert db.lookups == ["LBS96527-21240"]
    assert candidates[0]["name"] == "LBS96527-21240"
    assert candidates[0]["query_name"] == "LBS96527-21240"
