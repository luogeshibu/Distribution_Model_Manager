from pathlib import Path

from dmm.application.modules.fuse import FuseModelModule, FuseParser
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.reporting.writer import export_html_bundle


def _catalog():
    return {
        "records": [
            {"file_name": "Fuse_NON_SMART.zwdz.icn.g", "classification": "FUSE"},
            {"file_name": "Transformer_OH.pb.icn.g", "classification": "TRANSFORMER_OH"},
        ]
    }


def _write_conflict_g(path: Path):
    path.write_text(
        '''<?xml version="1.0" encoding="UTF-8"?>
<G><Layer>
  <TransformerDis id="tr1" x="100" y="100" w="20" h="20" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <Text id="txt1" x="130" y="100" w="40" h="10" ts="973360" />
  <TransformerDis id="tr2" x="1000" y="100" w="20" h="20" devref="#Transformer_OH.pb.icn.g:Transformer_OH" />
  <Text id="txt2" x="1030" y="100" w="40" h="10" ts="971576" />
  <ZhaiWaiDaoZha id="f_far" x="150" y="100" w="20" h="20" devref="#Fuse_NON_SMART.zwdz.icn.g:Fuse_NON_SMART" keyid="" />
  <ZhaiWaiDaoZha id="f_near" x="121" y="100" w="20" h="20" devref="#Fuse_NON_SMART.zwdz.icn.g:Fuse_NON_SMART" keyid="" />
</Layer></G>''',
        encoding="utf-8",
    )
    return path


def test_same_transformer_can_only_be_owned_by_closest_fuse_and_loser_does_not_fallback(tmp_path):
    parsed = GParser().parse(_write_conflict_g(tmp_path / "conflict.g"))
    rows, context = FuseParser().discover(parsed, _catalog(), {})
    by_id = {str(row["xml_id"]): row for row in rows}

    assert len(rows) == 2
    assert context["matched_fuse_count"] == 1
    assert context["unmatched_fuse_count"] == 1

    assert by_id["f_near"]["nearest_transformer_xml_id"] == "tr1"
    assert by_id["f_near"]["transformer_assignment_status"] == "MATCHED"

    # The farther FUSE also nominated tr1 as its true nearest transformer, but
    # tr1 is already owned by the closer FUSE.  It must remain unassigned and
    # must NOT fall back to the distant tr2.
    assert by_id["f_far"]["nearest_transformer_xml_id"] == "tr1"
    assert by_id["f_far"]["transformer_assignment_status"] == "NOT_ASSIGNED"
    assert by_id["f_far"]["transformer_owner_fuse_xml_id"] == "f_near"
    assert by_id["f_far"]["nearest_transformer_name"] == ""
    assert by_id["f_far"]["derived_fuse_name"] == ""


class _MustNotQueryDB:
    def __getattr__(self, name):
        raise AssertionError(f"statistics-only FUSE must not query DB: {name}")


def test_unassigned_fuse_is_statistics_only_and_never_enters_association():
    row = {
        "xml_id": "f_far",
        "object_type": "ZhaiWaiDaoZha",
        "nearest_transformer_xml_id": "tr1",
        "nearest_transformer_distance": 30.0,
        "transformer_assignment_status": "NOT_ASSIGNED",
        "transformer_owner_fuse_xml_id": "f_near",
        "current_keyid": "123",
    }
    resolved = FuseModelModule()._resolve_row(
        row,
        _MustNotQueryDB(),
        {"ready": True, "feeder_id": 100},
    )

    assert resolved["status"] == "INFO"
    assert resolved["association_ready"] == "NO"
    assert resolved["writeback_needed"] == "NO"
    assert resolved["association_action"] == "仅统计，不处理"
    assert "FUSE_TRANSFORMER_NOT_ASSIGNED" in resolved["reason"]


def test_fuse_html_report_exposes_assignment_statistics(tmp_path):
    reports = [{
        "file_name": "x.g",
        "report_type": "FUSE",
        "fuse_rows": [
            {
                "xml_id": "f1",
                "transformer_assignment_status": "MATCHED",
                "status": "PASS",
                "association_ready": "YES",
                "writeback_needed": "NO",
            },
            {
                "xml_id": "f2",
                "transformer_assignment_status": "NOT_ASSIGNED",
                "transformer_owner_fuse_xml_id": "f1",
                "status": "INFO",
                "association_ready": "NO",
                "writeback_needed": "NO",
                "reason": "FUSE_TRANSFORMER_NOT_ASSIGNED",
            },
        ],
        "summary": {
            "fuse_count": 2,
            "fuse_transformer_matched": 1,
            "fuse_transformer_unmatched": 1,
            "association_ready_count": 1,
        },
    }]
    path = export_html_bundle(reports, tmp_path / "report.html", FuseModelModule._rules())
    html = path.read_text(encoding="utf-8")
    assert "熔断器与柱上变压器分配统计" in html
    assert "仅统计不处理" in html
    assert "柱上变压器分配状态" in html
