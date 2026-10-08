from pathlib import Path
from types import SimpleNamespace

import dmm.application.modules.rmu as rmu_module
from dmm.application.modules.rmu import RmuModelModule
from dmm.domain.rmu.validator import RmuValidator


class DummyParser:
    pass


class DummyDB:
    def __init__(self, records):
        self.records = list(records)

    def get_rmu_records(self, name):
        return [dict(row) for row in self.records if row.get("name") == name]


def _candidate(name="RMU100"):
    return SimpleNamespace(
        text=name,
        direction="top",
        score=1.0,
        gap=12.0,
        color="255,255,255",
        is_green=False,
        obj=SimpleNamespace(xml_id="80001", xml_index=10),
    )


def _frame():
    return SimpleNamespace(frame=SimpleNamespace(xml_index=1, xml_id="FRAME1"))


def _resolve(records, required_feeder_id):
    validator = RmuValidator(DummyDB(records), DummyParser(), {})
    frame = _frame()
    candidate = _candidate()
    return validator._resolve_rmu_name(
        parsed=object(),
        frame=frame,
        positions=("top",),
        preassigned_candidates={(1, "FRAME1"): [candidate]},
        required_feeder_id=required_feeder_id,
    )


def test_same_name_on_other_feeders_does_not_block_when_current_feeder_has_one():
    result = _resolve(
        [
            {"id": 101, "name": "RMU100", "feeder_id": 700},
            {"id": 202, "name": "RMU100", "feeder_id": 800},
        ],
        800,
    )
    assert result["status"] == "PASS"
    selected = result["selected"]
    assert selected["db_total_count"] == 2
    assert selected["feeder_match_count"] == 1
    assert [row["id"] for row in selected["db_records"]] == [202]


def test_same_name_blocks_when_current_feeder_has_no_match():
    result = _resolve(
        [
            {"id": 101, "name": "RMU100", "feeder_id": 700},
            {"id": 202, "name": "RMU100", "feeder_id": 800},
        ],
        900,
    )
    assert result["status"] == "FAIL"
    assert result["reason"] == "RMU_NOT_FOUND_IN_CURRENT_FEEDER"


def test_same_name_still_blocks_when_current_feeder_itself_has_duplicates():
    result = _resolve(
        [
            {"id": 101, "name": "RMU100", "feeder_id": 700},
            {"id": 102, "name": "RMU100", "feeder_id": 700},
            {"id": 202, "name": "RMU100", "feeder_id": 800},
        ],
        700,
    )
    assert result["status"] == "FAIL"
    assert result["reason"] == "RMU_DUPLICATE_IN_FEEDER"


def test_non_single_line_no_feeder_filter_preserves_historical_duplicate_rule():
    result = _resolve(
        [
            {"id": 101, "name": "RMU100", "feeder_id": 700},
            {"id": 202, "name": "RMU100", "feeder_id": 800},
        ],
        None,
    )
    assert result["status"] == "FAIL"
    assert result["reason"] == "RMU_DUPLICATE_IN_DATABASE"


def test_rmu_module_passes_resolved_single_line_feeder_into_validator(monkeypatch, tmp_path):
    captured = {}

    class Parser:
        def parse(self, path):
            return object()

    class Validator:
        parser = Parser()

        def validate_file(self, path, positions, progress_callback=None, required_feeder_id=None):
            captured["required_feeder_id"] = required_feeder_id
            return {
                "g_file": str(path),
                "file_name": Path(path).name,
                "rmu_results": [{
                    "rmu_name": "RMU100",
                    "association_eligible": True,
                    "rmu_status": "PASS",
                    "device_rows": [],
                    "label_candidates": [],
                }],
                "summary": {},
            }

    class Classifier:
        def classify(self, parsed):
            return {"drawing_type": "SINGLE_FEEDER"}

    monkeypatch.setattr(rmu_module, "FeederDrawingTopologyClassifier", Classifier)
    monkeypatch.setattr(
        rmu_module,
        "resolve_drawing_feeder",
        lambda *a, **k: {
            "ready": True,
            "feeder_id": 700,
            "feeder_source": "GRAPH_UNIQUE_POLE_SWITCH",
            "feeder_evidence": "LBS100=>700",
            "feeder": {"id": 700, "name": "F700"},
            "reason": "",
        },
    )
    module = RmuModelModule()
    monkeypatch.setattr(module, "_new_validator", lambda *a, **k: Validator())

    g = tmp_path / "x.g"
    g.write_text("<G/>", encoding="utf-8")
    reports, _summary, _rules = module.validate(
        db=object(), files=[g], settings={}, log_callback=lambda _m: None
    )
    assert captured["required_feeder_id"] == 700
    assert reports[0]["feeder_context_ready"] == "YES"
    assert reports[0]["feeder_id"] == 700


def test_execution_recheck_filters_duplicate_rmu_name_by_validated_graph_feeder(tmp_path):
    from dmm.domain.rmu.validator import KEYID_STEP

    class DB:
        def get_rmu_records(self, name):
            assert name == "RMU100"
            return [
                {"id": 101, "name": "RMU100", "feeder_id": 700},
                {"id": 202, "name": "RMU100", "feeder_id": 800},
            ]

        def get_devices_by_combined_id(self, table_id, rmu_id):
            assert table_id == 13502
            assert rmu_id == 202
            return "dms_cb_device", [{
                "id": 7001,
                "code": "LEGACY-Y1",
                "name": "Y1",
                "combined_id": 202,
                "feeder_id": 800,
                "bv_id": 112871465660973067,
            }]

        def verify_keyid(self, keyid):
            return {"device_id": 7001, "tab_no": 13502, "col_no": 40}

    source = tmp_path / "rmu.g"
    source.write_text(
        '<G><CBreakerDis id="117000001" keyid="" voltype="" app="" state="" p_ReportType="0" /></G>',
        encoding="utf-8",
    )
    stat = source.stat()
    settings = {
        "rmu_protection_scope": "ALL",
        "device_rules": {"CBreakerDis": {"table_id": 13502, "domain": 40}},
        "_runtime_rules": {"CBreakerDis": {"table_id": 13502, "domain": 40}},
    }
    expected = 7001 + 40 * KEYID_STEP
    preview = {
        "settings_snapshot": {
            "rmu_name_detection_mode": "FIXED",
            "rmu_name_positions": {"top": True, "right": True, "left": False, "bottom": False, "global": True},
            "rmu_protection_scope": "ALL",
            "breaker_name_source": "GRAPHICAL_TEXT",
            "device_rules": dict(settings["device_rules"]),
        },
        "file_fingerprints": {
            str(source): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
        },
        "changes_by_file": {
            str(source): [{
                "xml_id": "117000001",
                "tag": "CBreakerDis",
                "rmu_name": "RMU100",
                "rmu_id": 202,
                "device_name": "Y1",
                "frame_index": 1,
                "validated_row": {
                    "rmu_name": "RMU100",
                    "rmu_id": 202,
                    "feeder_id": 800,
                    "required_feeder_id": 800,
                    "feeder_name": "F800",
                    "feeder_resolution_source": "FILENAME_405_13500",
                    "object_type": "CBreakerDis",
                    "xml_id": "117000001",
                    "logical_code": "Y1",
                    "graphical_name": "Y1",
                    "selected_device_name": "Y1",
                    "db_device_id": 7001,
                    "db_bv_id": 112871465660973067,
                    "expected_keyid": expected,
                    "model_linked": "NO",
                    "status": "WARN",
                },
                "attributes": {},
            }],
        },
    }
    result = RmuModelModule().apply_association(
        DB(), [source], settings, preview, lambda _m: None,
        output_g_dir=tmp_path / "out",
    )
    assert result["applied_count"] == 1
    assert result["skipped_count"] == 0
    rmu = result["operation_reports"][0]["rmu_results"][0]
    assert rmu["rmu_id"] == 202
    assert rmu["rmu_db_total_count"] == 2
    assert rmu["rmu_db_count"] == 1
    assert rmu["feeder_id"] == 800
