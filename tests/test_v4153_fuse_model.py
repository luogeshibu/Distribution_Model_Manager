from pathlib import Path

from dmm.application.modules.fuse import (
    FUSE_DOMAIN,
    FUSE_TABLE_ID,
    FuseModelModule,
    FuseParser,
)
from dmm.application.registry import get_model_modules
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import export_csv_bundle, export_html_bundle


def _catalog():
    return {
        "records": [
            {"file_name": "Fuse_NON_SMART.zwdz.icn.g", "classification": "FUSE"},
            {"file_name": "Transformer_OH.pb.icn.g", "classification": "TRANSFORMER_OH"},
        ]
    }


def _write_g(tmp_path: Path):
    path = tmp_path / "test.g"
    path.write_text(
        '''<?xml version="1.0" encoding="UTF-8"?>
<G><Layer>
  <TransformerDis id="tr1" x="100" y="100" w="20" h="20" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <Text id="txt1" x="100" y="60" w="40" h="10" ts="973360" />
  <TransformerDis id="tr2" x="500" y="100" w="20" h="20" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <Text id="txt2" x="500" y="60" w="40" h="10" ts="971576" />
  <ZhaiWaiDaoZha id="f1" x="120" y="130" w="20" h="20" devref="#Fuse_NON_SMART.zwdz.icn.g:Fuse_NON_SMART" keyid="" />
</Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_fuse_classification_uses_nearest_transformer_name(tmp_path):
    parsed = GParser().parse(_write_g(tmp_path))
    rows, context = FuseParser().discover(parsed, _catalog(), {})

    assert len(rows) == 1
    assert len(context["transformer_rows"]) == 2
    assert rows[0]["nearest_transformer_xml_id"] == "tr1"
    assert rows[0]["nearest_transformer_name"] == "973360"
    assert rows[0]["derived_fuse_name"] == "FUSE973360"


def test_fuse_domain_40_matches_supplied_g_keyid_example():
    # Supplied database ID for FUSE973360 + Domain 40.
    assert FUSE_TABLE_ID == 13513
    assert FUSE_DOMAIN == 40
    assert FuseModelModule._make_expected_keyid(3803571360291094530) == 3803571532089786370


class _DB:
    def __init__(self, row_feeder=100):
        self.row_feeder = row_feeder
        self.last_lookup = None

    def get_disconnector_devices_by_name(self, name, feeder_id=None, table_id=13513):
        self.last_lookup = (name, feeder_id, table_id)
        return [{
            "id": 1234,
            "code": "",
            "name": name,
            "feeder_id": self.row_feeder,
            "bv_id": 88,
        }]

    def verify_keyid(self, keyid):
        return {
            "device_id": int(keyid) - (40 << 32),
            "tab_no": 13513,
            "col_no": 40,
        }

    def get_device_by_id(self, table_id, device_id):
        return None


def _resolution(feeder_id=100):
    return {
        "ready": True,
        "feeder_id": feeder_id,
        "feeder_source": "GRAPH_UNIQUE_TRANSFORMER",
        "feeder_anchor": "TRANSFORMER:973360",
        "feeder_evidence": "",
        "feeder": {
            "id": feeder_id,
            "name": "AH306",
            "display_name": "JED-STH ADEL AH306",
            "station_name": "ADEL",
            "code": "AH306",
        },
    }


def _row():
    return {
        "xml_id": "f1",
        "object_type": "ZhaiWaiDaoZha",
        "nearest_transformer_xml_id": "tr1",
        "nearest_transformer_name": "973360",
        "nearest_transformer_distance": 5.0,
        "derived_fuse_name": "FUSE973360",
        "current_keyid": "",
    }


def test_fuse_queries_13513_by_derived_name_and_graph_feeder():
    module = FuseModelModule()
    db = _DB(row_feeder=100)
    row = module._resolve_row(_row(), db, _resolution(100))

    assert db.last_lookup == ("FUSE973360", 100, 13513)
    assert row["association_ready"] == "YES"
    assert row["writeback_needed"] == "YES"
    assert row["db_device_id"] == 1234
    assert row["expected_keyid"] == 1234 + (40 << 32)
    assert row["feeder_membership_verified"] == "YES"


def test_fuse_blocks_wrong_feeder_even_if_database_row_is_returned():
    module = FuseModelModule()
    db = _DB(row_feeder=200)
    row = module._resolve_row(_row(), db, _resolution(100))

    assert row["association_ready"] == "NO"
    assert row["writeback_needed"] == "NO"
    assert row["status"] == "FAIL"
    assert "FUSE_FEEDER_MISMATCH" in row["reason"]


def test_fuse_module_registered():
    modules = get_model_modules()
    assert "FUSE" in modules
    assert modules["FUSE"].display_name == "熔断器模型"


def test_fuse_report_csv_and_html(tmp_path):
    reports = [{
        "file_name": "x.g",
        "report_type": "FUSE",
        "fuse_rows": [{
            **_row(),
            "feeder_id": 100,
            "feeder_resolution_source": "GRAPH_UNIQUE_TRANSFORMER",
            "feeder_anchor": "TRANSFORMER:973360",
            "db_match_count": 1,
            "db_device_id": 1234,
            "db_name": "FUSE973360",
            "db_bv_id": 88,
            "db_feeder_id": 100,
            "table_id": 13513,
            "table_name": "dms_disconnector_device",
            "configured_domain": 40,
            "expected_keyid": 1234 + (40 << 32),
            "association_ready": "YES",
            "writeback_needed": "YES",
            "status": "UNLINKED",
            "severity": "WARN",
            "reason": "FUSE_ASSOCIATION_READY",
        }],
        "feeder_resolution_source": "GRAPH_UNIQUE_TRANSFORMER",
        "feeder_anchor": "TRANSFORMER:973360",
        "feeder_id": 100,
        "feeder_name": "AH306",
        "summary": {"fuse_count": 1},
    }]
    csvs = export_csv_bundle(reports, tmp_path / "report.csv")
    html = export_html_bundle(reports, tmp_path / "report.html", FuseModelModule._rules())

    assert len(csvs) == 2
    assert csvs[0].exists()
    assert csvs[1].name.endswith("_关联失败_CN.csv")
    assert csvs[1].exists()
    assert "FUSE973360" in csvs[0].read_text(encoding="utf-8-sig")
    assert html.exists()
    assert "熔断器模型报告" in html.read_text(encoding="utf-8")
