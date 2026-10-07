
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


def test_feeder_report_hides_identification_logic_from_user_output():
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

    assert "馈线识别规则：FACID、文件名、人工输入" not in source
    assert "本报告展示馈线段模型处理结果" in source
    assert "图形馈线" in source
    assert "feeder_resolution_source" not in writer.FEEDER_REPORT_FIELDS
    assert "feeder_resolution_evidence" not in writer.FEEDER_REPORT_FIELDS
    assert "ownership_method" not in writer.FEEDLINE_REPORT_FIELDS
    assert "ownership_evidence" not in writer.FEEDLINE_REPORT_FIELDS


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
