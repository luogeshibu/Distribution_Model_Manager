from pathlib import Path

from dmm.application.batch_orchestrator import (
    BatchAssociationOrchestrator,
    detect_preview_conflicts,
    rebase_preview_for_current_files,
)


class FakeModule:
    def __init__(self, module_id, marker):
        self.module_id = module_id
        self.display_name = module_id
        self.marker = marker

    def supports(self, operation):
        return operation in {"PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION"}

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        output = Path(output_g_dir)
        output.mkdir(parents=True, exist_ok=True)
        copied = []
        applied = 0
        for source_file, changes in preview_data.get("changes_by_file", {}).items():
            source = Path(source_file)
            target = output / source.name
            data = source.read_text(encoding="utf-8")
            target.write_text(data + self.marker, encoding="utf-8")
            copied.append(str(target))
            applied += len(changes)
        return {
            "selected_count": applied,
            "applied_count": applied,
            "skipped_count": 0,
            "copied_files": copied,
            "operation_reports": [],
            "rules": {},
        }


def _preview(path, xml_id, value):
    stat = path.stat()
    return {
        "changes_by_file": {
            str(path): [
                {
                    "xml_id": xml_id,
                    "tag": "CBreakerDis",
                    "attributes": {"keyid": value},
                    "_source_file": str(path),
                }
            ]
        },
        "file_fingerprints": {
            str(path): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        },
        "reports": [],
        "rules": {},
    }


def test_batch_conflict_detection_is_attribute_level(tmp_path):
    g = tmp_path / "a.g"
    g.write_text("x", encoding="utf-8")
    previews = {
        "RMU": _preview(g, "100", "A"),
        "POLE_SWITCH": _preview(g, "100", "B"),
    }
    conflicts = detect_preview_conflicts(previews)
    assert len(conflicts) == 1
    assert conflicts[0]["attribute"] == "keyid"
    assert conflicts[0]["first_module"] == "RMU"
    assert conflicts[0]["second_module"] == "POLE_SWITCH"


def test_rebase_preview_points_to_cumulative_file(tmp_path):
    original = tmp_path / "source.g"
    original.write_text("original", encoding="utf-8")
    cumulative = tmp_path / "stage" / "source.g"
    cumulative.parent.mkdir()
    cumulative.write_text("changed", encoding="utf-8")
    preview = _preview(original, "100", "A")
    rebased = rebase_preview_for_current_files(
        preview,
        {str(original.resolve()): cumulative},
    )
    assert list(rebased["changes_by_file"]) == [str(cumulative)]
    change = rebased["changes_by_file"][str(cumulative)][0]
    assert change["_source_file"] == str(cumulative)
    assert change["_batch_original_source_file"] == str(original)


def test_batch_apply_chains_module_output_into_one_final_copy(tmp_path):
    original = tmp_path / "JED-A.g"
    original.write_text("BASE", encoding="utf-8")
    modules = {
        "RMU": FakeModule("RMU", "|RMU"),
        "POLE_SWITCH": FakeModule("POLE_SWITCH", "|POLE"),
    }
    orchestrator = BatchAssociationOrchestrator(modules)
    validation = {
        "selected_modules": ["RMU", "POLE_SWITCH"],
        "previews": {
            "RMU": _preview(original, "1", "A"),
            "POLE_SWITCH": _preview(original, "2", "B"),
        },
        "conflicts": [],
        "source_fingerprints": {
            str(original.resolve()): {
                "path": str(original),
                "size": original.stat().st_size,
                "mtime_ns": original.stat().st_mtime_ns,
            }
        },
    }
    result = orchestrator.apply(
        db=None,
        files=[original],
        settings_by_module={"RMU": {}, "POLE_SWITCH": {}},
        validation_bundle=validation,
        output_root=tmp_path / "final",
        report_root=tmp_path / "reports",
        log_callback=lambda *_: None,
    )
    final = Path(result["output_g_dir"]) / original.name
    assert final.read_text(encoding="utf-8") == "BASE|RMU|POLE"
    assert original.read_text(encoding="utf-8") == "BASE"


def test_rebase_preview_rebases_report_g_file_for_report_driven_modules(tmp_path):
    original = tmp_path / "source.g"
    original.write_text("original", encoding="utf-8")
    cumulative = tmp_path / "stage" / "source.g"
    cumulative.parent.mkdir()
    cumulative.write_text("changed", encoding="utf-8")
    preview = _preview(original, "100", "A")
    preview["reports"] = [
        {
            "g_file": str(original),
            "file_name": original.name,
            "region_index": "1",
            "feeder_id": "123",
            "feedline_rows": [{"xml_id": "100"}],
        }
    ]

    rebased = rebase_preview_for_current_files(
        preview,
        {str(original.resolve()): cumulative},
    )

    assert rebased["reports"][0]["g_file"] == str(cumulative)
    assert rebased["reports"][0]["file_name"] == cumulative.name
    # Validation snapshot remains immutable; only the batch execution copy is rebased.
    assert preview["reports"][0]["g_file"] == str(original)
