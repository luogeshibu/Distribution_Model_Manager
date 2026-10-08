from pathlib import Path

from dmm.application.batch_orchestrator import (
    build_batch_candidate_rows,
    detect_preview_conflicts,
    filter_validation_bundle_candidates,
)


MAIN_WINDOW = Path(__file__).resolve().parents[1] / "src" / "dmm" / "ui" / "main_window.py"


def _preview(path, changes):
    stat = path.stat()
    return {
        "changes_by_file": {str(path): changes},
        "file_fingerprints": {
            str(path): {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        },
        "reports": [],
        "rows": [],
        "rules": {},
        "summary": {},
    }


def _change(xml_id, value, name):
    return {
        "xml_id": xml_id,
        "tag": "CBreakerDis",
        "attributes": {"keyid": value},
        "device_name": name,
        "device_id": f"DB-{xml_id}",
        "validated_row": {"selected_device_name": name},
    }


def test_batch_page_has_post_validation_candidate_confirmation_table():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    block = text[
        text.index("    def _build_batch_page(self):"):
        text.index("    def _prepare_batch_page(self):")
    ]
    assert 'QGroupBox("待关联设备（批量校验后确认）")' in block
    assert '"选择", "模块", "G文件", "XML ID", "图上名称"' in block
    assert '"数据库目标", "状态", "说明"' in block
    assert 'QPushButton("全选可关联")' in block
    assert 'QPushButton("取消全选")' in block


def test_batch_candidate_filter_only_keeps_user_selected_existing_changes(tmp_path):
    g = tmp_path / "JED-A.g"
    g.write_text("BASE", encoding="utf-8")
    previews = {
        "RMU": _preview(
            g,
            [
                _change("1", "K1", "RMU-A"),
                _change("2", "K2", "RMU-B"),
            ],
        )
    }
    candidates = build_batch_candidate_rows(previews, [])
    assert len(candidates) == 2
    selected_id = candidates[1]["candidate_id"]
    bundle = {
        "selected_modules": ["RMU"],
        "previews": previews,
        "module_rows": [
            {"module_id": "RMU", "module_name": "RMU 环网柜", "candidate_count": 2}
        ],
        "candidate_rows": candidates,
        "conflicts": [],
    }
    filtered = filter_validation_bundle_candidates(bundle, [selected_id])
    changes = filtered["previews"]["RMU"]["changes_by_file"][str(g)]
    assert [change["xml_id"] for change in changes] == ["2"]
    assert filtered["module_rows"][0]["candidate_count"] == 1
    assert filtered["previews"]["RMU"]["summary"]["association_change_count"] == 1
    assert [row["candidate_id"] for row in filtered["candidate_rows"]] == [selected_id]


def test_cross_module_conflict_candidates_are_marked_blocked(tmp_path):
    g = tmp_path / "JED-A.g"
    g.write_text("BASE", encoding="utf-8")
    previews = {
        "RMU": _preview(g, [_change("100", "A", "A")]),
        "POLE_SWITCH": _preview(g, [_change("100", "B", "B")]),
    }
    conflicts = detect_preview_conflicts(previews)
    candidates = build_batch_candidate_rows(previews, conflicts)
    assert len(conflicts) == 1
    assert len(candidates) == 2
    assert all(row["blocked"] for row in candidates)
    assert all(row["status"] == "跨模块冲突" for row in candidates)


def test_batch_apply_filters_confirmation_selection_before_existing_module_apply():
    text = MAIN_WINDOW.read_text(encoding="utf-8")
    block = text[
        text.index("    def apply_batch_association(self):"):
        text.index("    def _on_batch_association_completed", text.index("    def apply_batch_association(self):"))
    ]
    worker = text[
        text.index("class BatchAssociationExecutionWorker(QThread):"):
        text.index("class CentralAdminOwnershipWorker(QThread):")
    ]
    assert "self._selected_batch_candidate_ids()" in block
    assert "selected_candidate_ids" in block
    assert "filter_validation_bundle_candidates(" in worker
    assert "未勾选对象不会写回" in block
