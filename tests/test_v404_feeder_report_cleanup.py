
from pathlib import Path

from dmm.infrastructure.reporting import writer


def test_feeder_summary_schema_has_no_rmu_or_topology_columns():
    forbidden = {
        "trusted_rmu_count",
        "ignored_rmu_count",
        "trusted_rmu_names",
        "trusted_feeder_ids",
        "ignored_rmu_details",
        "region_assignment_method",
    }
    assert forbidden.isdisjoint(set(writer.FEEDER_FIELDS))


def test_feedline_schema_has_no_topology_region_columns():
    assert "topology_component" not in writer.FEEDLINE_FIELDS
    assert "topology_cross_region" not in writer.FEEDLINE_FIELDS
    assert "region_index" not in writer.FEEDLINE_FIELDS
    assert "region_assignment_method" not in writer.FEEDLINE_FIELDS


def test_feeder_report_uses_only_direct_identification_wording():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/infrastructure/reporting/writer.py"
    ).read_text(encoding="utf-8")

    obsolete = [
        "程序先构建 G 图连接拓扑",
        "可信环网柜的 FEEDER_ID",
        "未作为依据的环网柜说明",
        "可信RMU的FEEDER_ID",
        "可信环网柜数",
        "忽略环网柜数",
    ]
    for text in obsolete:
        assert text not in source

    assert "facID" in source and "文件名" in source and "人工输入" in source
    assert "馈线报告不再包含任何 RMU / 环网柜拓扑判定字段" in source


def test_feeder_summary_contains_new_database_preparation_fields():
    required = {
        "feeder_resolution_source",
        "feeder_resolution_evidence",
        "feeder_db_count",
        "station_name",
        "station_bv_id",
        "section_prefix",
        "database_section_count",
        "planned_create_count",
    }
    assert required.issubset(set(writer.FEEDER_FIELDS))
