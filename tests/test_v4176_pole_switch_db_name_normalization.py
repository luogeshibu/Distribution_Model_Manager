from pathlib import Path

from dmm.application.modules.feeder_context import _graphical_pole_switch_candidates
from dmm.application.modules.pole_switch import (
    PoleSwitchModelModule,
    normalize_pole_switch_db_lookup_name,
)
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import POLE_FIELDS, POLE_LABELS, _pole_reason_for_report


def _catalog():
    return {
        "records": [
            {"file_name": "sw.g", "root_id": "SWROOT", "classification": "LBS"},
        ]
    }


def test_pole_switch_database_lookup_removes_dot_hyphen_and_spaces():
    assert normalize_pole_switch_db_lookup_name("SEC-2385") == "SEC2385"
    assert normalize_pole_switch_db_lookup_name("SEC 2369") == "SEC2369"
    assert normalize_pole_switch_db_lookup_name("SEC.2270") == "SEC2270"
    assert normalize_pole_switch_db_lookup_name(" LBS- 12.34 ") == "LBS1234"
    assert normalize_pole_switch_db_lookup_name("AR100") == "AR100"


class _CaptureDB:
    def __init__(self):
        self.lookups = []

    def get_combined_device_records(self, name):
        self.lookups.append(name)
        return []


def test_model_uses_compact_name_for_13501_but_keeps_graphical_name():
    db = _CaptureDB()
    row = {
        "graphical_name": "SEC-2385",
        "current_keyid": "",
        "object_type": "CBreakerDis",
        "xml_id": "sw1",
        "device_family": "SEC",
    }
    result = PoleSwitchModelModule()._resolve_row(row, db)
    assert db.lookups == ["SEC2385"]
    assert result["graphical_name"] == "SEC-2385"
    assert result["logical_code"] == "SEC-2385"
    assert result["selected_device_name"] == "SEC-2385"
    assert result["combined_name"] == "SEC2385"
    assert result["database_query_name"] == "SEC2385"
    assert "图上名称=SEC-2385" in result["reason"]
    assert "数据库查询名称=SEC2385" in result["reason"]


def test_feeder_resolution_pole_candidate_uses_same_compact_database_name(tmp_path):
    g = tmp_path / "case.g"
    g.write_text(
        '<G><Layer>'
        '<CBreakerDis id="sw1" x="100" y="100" w="20" h="20" devref="#sw.g:SWROOT"/>'
        '<Text id="t1" x="100" y="60" w="80" h="20" ts="LBS-2291" lc="255,0,0"/>'
        '</Layer></G>',
        encoding="utf-8",
    )
    db = _CaptureDB()
    _rows, candidates = _graphical_pole_switch_candidates(
        db,
        GParser().parse(g),
        {"element_catalog": _catalog()},
    )
    assert db.lookups == ["LBS2291"]
    assert candidates[0]["name"] == "LBS-2291"
    assert candidates[0]["query_name"] == "LBS2291"


def test_report_uses_clear_lookup_column_and_human_readable_feeder_reason():
    assert "数据库查询名称" in POLE_LABELS["combined_name"]
    assert "横杠" in POLE_LABELS["combined_name"]
    text = _pole_reason_for_report(
        "POLE_SWITCH_FEEDER_ID_EMPTY: 目标设备数据库 FEEDER_ID 为空，无法证明其属于图级馈线 3799912185593856099."
    )
    assert "没有完整的馈线归属信息" in text
    assert "3799912185593856099" in text
    assert "不自动关联" in text
    assert "POLE_SWITCH_FEEDER_ID_EMPTY" not in text


def test_report_places_original_and_database_lookup_names_side_by_side():
    gi = POLE_FIELDS.index("graphical_name")
    qi = POLE_FIELDS.index("database_query_name")
    assert qi == gi + 1
    assert "原样" in POLE_LABELS["graphical_name"]
    assert "普通名查询前" in POLE_LABELS["database_query_name"]
    assert "复合名保留横杠" in POLE_LABELS["database_query_name"]


def test_report_reason_is_plain_language_without_internal_code():
    text = _pole_reason_for_report(
        "POLE_SWITCH_COMBINED_NAME_NOT_UNIQUE: 图上名称=SEC-2385；数据库查询名称=SEC2385；在 13501 的 NAME/CODE 中匹配到 2 条，必须唯一，因此本条不处理。"
    )
    assert "图上名称是 SEC-2385" in text
    assert "查询数据库时使用 SEC2385" in text
    assert "查到 2 条" in text
    assert "POLE_SWITCH_" not in text
