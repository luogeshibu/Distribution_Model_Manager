from dmm.infrastructure.reporting.writer import (
    POLE_FIELDS,
    _pole_report_for_output,
    flatten_pole_rows,
)


def _sample_report():
    return {
        "report_type": "POLE_SWITCH",
        "file_name": "sample.g",
        "pole_switch_rows": [
            {
                "xml_id": "1001",
                "graphical_name": "LBS001",
                "feeder_resolution_source": "GRAPH_UNIQUE_RMU",
                "feeder_resolution_evidence": "RMU:1=>match=1=>FEEDER_ID=123",
                "feeder_id": "123",
                "feeder_name": "AH306",
            }
        ],
    }


def test_pole_detail_columns_hide_graph_feeder_evidence():
    assert "feeder_resolution_evidence" not in POLE_FIELDS


def test_flattened_pole_rows_hide_graph_feeder_evidence():
    rows = flatten_pole_rows([_sample_report()])
    assert len(rows) == 1
    assert "feeder_resolution_evidence" not in rows[0]
    assert rows[0]["feeder_resolution_source"] == "GRAPH_UNIQUE_RMU"
    assert rows[0]["feeder_id"] == "123"


def test_public_pole_json_hides_graph_feeder_evidence():
    payload = _pole_report_for_output(_sample_report())
    row = payload["pole_switch_rows"][0]
    assert "feeder_resolution_evidence" not in row
    assert row["feeder_resolution_source"] == "GRAPH_UNIQUE_RMU"
