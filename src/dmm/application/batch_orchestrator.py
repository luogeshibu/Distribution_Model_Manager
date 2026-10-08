from __future__ import annotations

import copy
import csv
import html
import shutil
from collections import defaultdict
from pathlib import Path

from dmm.infrastructure.reporting.writer import export_csv_bundle, export_html_bundle


# Keep the operational order explicit.  It is intentionally separate from the
# single-module registry order so batch execution can respect dependencies
# without changing any independent module implementation.
BATCH_MODULE_ORDER = (
    "RMU",
    "POLE_SWITCH",
    "TRANSFORMER",
    "FUSE",
    "MASTER_STATION",
    "FEEDER",
)

BATCH_MODULE_LABELS = {
    "RMU": "RMU 环网柜",
    "POLE_SWITCH": "柱上开关",
    "TRANSFORMER": "柱上变压器",
    "FUSE": "熔断器",
    "FEEDER": "馈线",
    "MASTER_STATION": "配网主站设备",
}

BATCH_MODULE_LABELS_EN = {
    "RMU": "RMU",
    "POLE_SWITCH": "Pole Switch",
    "TRANSFORMER": "Pole Transformer",
    "FUSE": "Fuse",
    "FEEDER": "Feeder",
    "MASTER_STATION": "Master Station Device",
}


def _path_key(value) -> str:
    return str(Path(value).resolve())


def ensure_unique_basenames(files):
    """Batch chaining needs one stable final name per source G file."""
    seen = {}
    duplicates = []
    for value in files:
        path = Path(value)
        name = path.name.lower()
        if name in seen and _path_key(seen[name]) != _path_key(path):
            duplicates.append(path.name)
        else:
            seen[name] = path
    if duplicates:
        names = ", ".join(sorted(set(duplicates)))
        raise RuntimeError(
            "批量关联要求本次输入 G 文件名唯一；检测到重名文件："
            f"{names}。请分批处理这些同名文件。"
        )


def capture_source_fingerprints(files):
    result = {}
    for value in files:
        path = Path(value)
        stat = path.stat()
        result[_path_key(path)] = {
            "path": str(path),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    return result


def verify_source_fingerprints(fingerprints):
    for item in (fingerprints or {}).values():
        path = Path(item["path"])
        if not path.exists():
            raise RuntimeError(
                f"批量校验后的 G 文件已经不存在，请重新校验：{path}"
            )
        stat = path.stat()
        if (
            stat.st_size != item.get("size")
            or stat.st_mtime_ns != item.get("mtime_ns")
        ):
            raise RuntimeError(
                "G 文件在批量校验后发生变化，禁止使用旧结果，请重新校验："
                f"{path}"
            )


def _association_count(preview) -> int:
    return sum(
        len(items)
        for items in ((preview or {}).get("changes_by_file", {}) or {}).values()
    )


def _batch_candidate_id(module_id, source_file, change, ordinal):
    return "|".join([
        str(module_id),
        _path_key(source_file),
        str(change.get("tag") or ""),
        str(change.get("xml_id") or ""),
        str(ordinal),
    ])


def _first_value(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _candidate_display_name(change):
    row = dict(change.get("validated_row", {}) or {})
    return (
        str(change.get("device_name") or "")
        or _first_value(
            row,
            (
                "selected_device_name",
                "derived_fuse_name",
                "feeder_name",
                "assigned_section_name",
                "rmu_name",
                "name",
                "graph_name",
                "logical_code",
            ),
        )
    )


def _candidate_database_target(change):
    row = dict(change.get("validated_row", {}) or {})
    target_name = _first_value(
        row,
        (
            "db_device_name",
            "target_device_name",
            "target_name",
            "db_name",
            "assigned_section_name",
        ),
    )
    target_id = (
        str(change.get("device_id") or "")
        or _first_value(
            row,
            (
                "db_device_id",
                "target_device_id",
                "assigned_device_id",
                "current_device_id",
            ),
        )
    )
    if target_name and target_id:
        return f"{target_name} / ID={target_id}"
    if target_name:
        return target_name
    if target_id:
        return f"ID={target_id}"
    expected = str(change.get("expected_keyid") or "")
    return f"KeyID={expected}" if expected else "-"


def build_batch_candidate_rows(previews, conflicts=None):
    """Expose batch-safe write candidates without changing module logic.

    Candidates are taken directly from each module's existing
    ``changes_by_file`` preview.  The helper only adds an opaque batch id and
    display metadata; independent module validation/apply code remains
    untouched.
    """
    conflict_map = defaultdict(list)
    for conflict in conflicts or []:
        source_key = _path_key(conflict.get("source_file", ""))
        tag = str(conflict.get("tag") or "")
        xml_id = str(conflict.get("xml_id") or "")
        first = str(conflict.get("first_module") or "")
        second = str(conflict.get("second_module") or "")
        attr = str(conflict.get("attribute") or "")
        desc = (
            f"跨模块冲突：{BATCH_MODULE_LABELS.get(first, first)} 与 "
            f"{BATCH_MODULE_LABELS.get(second, second)} 对属性 {attr} 写入不同值。"
        )
        conflict_map[(first, source_key, tag, xml_id)].append(desc)
        conflict_map[(second, source_key, tag, xml_id)].append(desc)

    rows = []
    for module_id in BATCH_MODULE_ORDER:
        preview = (previews or {}).get(module_id)
        if not preview:
            continue
        ordinal = 0
        for source_file, changes in (preview.get("changes_by_file", {}) or {}).items():
            for change in changes or []:
                ordinal += 1
                candidate_id = _batch_candidate_id(
                    module_id, source_file, change, ordinal
                )
                change["_batch_candidate_id"] = candidate_id
                conflict_notes = conflict_map.get(
                    (
                        module_id,
                        _path_key(source_file),
                        str(change.get("tag") or ""),
                        str(change.get("xml_id") or ""),
                    ),
                    [],
                )
                rows.append({
                    "candidate_id": candidate_id,
                    "module_id": module_id,
                    "module_name": BATCH_MODULE_LABELS.get(module_id, module_id),
                    "source_file": str(source_file),
                    "g_file": Path(source_file).name,
                    "tag": str(change.get("tag") or ""),
                    "xml_id": str(change.get("xml_id") or ""),
                    "device_name": _candidate_display_name(change),
                    "database_target": _candidate_database_target(change),
                    "blocked": bool(conflict_notes),
                    "status": "跨模块冲突" if conflict_notes else "可关联",
                    "reason": "；".join(dict.fromkeys(conflict_notes))
                    if conflict_notes
                    else "已通过该独立模块现有校验，可进入批量关联。",
                })
    return rows


def filter_validation_bundle_candidates(validation_bundle, selected_candidate_ids):
    """Return a batch-only filtered copy for the user's final confirmation.

    This function never re-implements or alters any independent module rule.
    It merely removes unselected preview changes before calling the same module
    ``apply_association`` methods that single-module execution uses.
    """
    selected_ids = {str(value) for value in (selected_candidate_ids or [])}
    filtered = copy.deepcopy(validation_bundle or {})
    previews = filtered.get("previews", {}) or {}

    for module_id, preview in previews.items():
        original_changes = (preview.get("changes_by_file", {}) or {})
        kept_changes = {}
        selected_files = set()
        for source_file, changes in original_changes.items():
            kept = [
                change
                for change in (changes or [])
                if str(change.get("_batch_candidate_id") or "") in selected_ids
            ]
            if kept:
                kept_changes[source_file] = kept
                selected_files.add(_path_key(source_file))
        preview["changes_by_file"] = kept_changes

        if "file_fingerprints" in preview:
            preview["file_fingerprints"] = {
                key: value
                for key, value in (preview.get("file_fingerprints", {}) or {}).items()
                if _path_key(key) in selected_files
            }
        if "ls_normalization_by_file" in preview:
            preview["ls_normalization_by_file"] = {
                key: value
                for key, value in (
                    preview.get("ls_normalization_by_file", {}) or {}
                ).items()
                if _path_key(key) in selected_files
            }
        summary = dict(preview.get("summary", {}) or {})
        summary["association_change_count"] = sum(
            len(items) for items in kept_changes.values()
        )
        preview["summary"] = summary

    for row in filtered.get("module_rows", []) or []:
        module_id = str(row.get("module_id") or "")
        preview = previews.get(module_id, {}) or {}
        count = _association_count(preview)
        row["candidate_count"] = count
        row["status"] = "READY" if count else "NO_CHANGE"

    filtered["conflicts"] = detect_preview_conflicts(previews)
    filtered["candidate_rows"] = [
        row
        for row in (filtered.get("candidate_rows", []) or [])
        if str(row.get("candidate_id") or "") in selected_ids
    ]
    filtered["selected_candidate_ids"] = sorted(selected_ids)
    return filtered


def detect_preview_conflicts(previews):
    """Detect attribute-level write conflicts across selected modules.

    Two modules may legitimately touch the same XML object when they write the
    exact same value.  A different value for the same attribute is unsafe and
    blocks batch apply before any G file is copied or modified.
    """
    owners = {}
    conflicts = []
    for module_id in BATCH_MODULE_ORDER:
        preview = (previews or {}).get(module_id)
        if not preview:
            continue
        for source_file, changes in (preview.get("changes_by_file", {}) or {}).items():
            source_key = _path_key(source_file)
            for change in changes or []:
                xml_id = str(change.get("xml_id") or "")
                tag = str(change.get("tag") or "")
                for attr, value in (change.get("attributes", {}) or {}).items():
                    key = (source_key, tag, xml_id, str(attr))
                    current = (module_id, str(value))
                    previous = owners.get(key)
                    if previous and previous[1] != current[1]:
                        conflicts.append({
                            "source_file": source_file,
                            "tag": tag,
                            "xml_id": xml_id,
                            "attribute": str(attr),
                            "first_module": previous[0],
                            "first_value": previous[1],
                            "second_module": module_id,
                            "second_value": current[1],
                        })
                    else:
                        owners[key] = current
    return conflicts


def rebase_preview_for_current_files(preview, current_by_original):
    """Rebase a validation preview onto cumulative batch-stage files.

    Business decisions and selected XML IDs remain those produced by the
    module itself.  Only filesystem paths/fingerprints are updated so the
    module's existing execution-time recheck can run against the cumulative
    copy containing changes from earlier modules.
    """
    rebased = copy.deepcopy(preview or {})
    original_changes = (preview or {}).get("changes_by_file", {}) or {}
    changes_by_file = defaultdict(list)
    old_to_new = {}

    for original_source, changes in original_changes.items():
        original_key = _path_key(original_source)
        current_path = Path(current_by_original.get(original_key, original_source))
        old_to_new[_path_key(original_source)] = str(current_path)
        for item in changes or []:
            change = copy.deepcopy(item)
            change["_batch_original_source_file"] = str(original_source)
            change["_source_file"] = str(current_path)
            changes_by_file[str(current_path)].append(change)

    rebased["changes_by_file"] = dict(changes_by_file)

    # Feeder previews contain an additional per-file normalization plan.
    if "ls_normalization_by_file" in rebased:
        normalized = defaultdict(list)
        for original_source, changes in (
            (preview or {}).get("ls_normalization_by_file", {}) or {}
        ).items():
            original_key = _path_key(original_source)
            current_path = Path(current_by_original.get(original_key, original_source))
            normalized[str(current_path)].extend(copy.deepcopy(changes or []))
        rebased["ls_normalization_by_file"] = dict(normalized)

    fingerprints = {}
    for current_source in changes_by_file:
        path = Path(current_source)
        stat = path.stat()
        fingerprints[str(path)] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    rebased["file_fingerprints"] = fingerprints

    # Batch-only path rebasing for report-driven execution.  Some modules
    # (most importantly FEEDER) use the validation report rows again during
    # apply_association to reconstruct the full topology region around the
    # selected XML IDs.  Earlier batch stages change the cumulative source
    # path, therefore keeping report["g_file"] on the original validation
    # path makes the final FEEDER stage fail to find its report_lookup key.
    # Single-module previews are never touched by this helper.
    rebased_reports = []
    for original_report in (preview or {}).get("reports", []) or []:
        report = copy.deepcopy(original_report)
        report_g_file = str(report.get("g_file") or "")
        if report_g_file:
            mapped = current_by_original.get(_path_key(report_g_file))
            if mapped is not None:
                report["g_file"] = str(Path(mapped))
                # file_name is a display-only field, but keeping it aligned
                # avoids misleading operation reports after rebasing.
                if "file_name" in report:
                    report["file_name"] = Path(mapped).name
        rebased_reports.append(report)
    if "reports" in rebased:
        rebased["reports"] = rebased_reports

    rebased["_batch_rebased_paths"] = old_to_new
    return rebased


def _module_report_dir(base_dir: Path, index: int, module_id: str) -> Path:
    return base_dir / f"{index:02d}_{module_id.lower()}"


def export_batch_summary(rows, output_dir, title, subtitle="", language="zh_CN"):
    """Write the batch summary HTML plus bilingual CSVs in Chinese UI mode."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / "batch_summary.html"
    language = str(language or "zh_CN")
    chinese_ui = language != "en_US"

    fields = [
        "module_id",
        "module_name",
        "candidate_count",
        "applied_count",
        "skipped_count",
        "status",
        "report_html",
    ]
    cn_headers = {
        "module_id": "模型ID",
        "module_name": "模型名称",
        "candidate_count": "可关联对象",
        "applied_count": "成功写回",
        "skipped_count": "执行时跳过",
        "status": "状态",
        "report_html": "模块报告",
    }
    en_headers = {
        "module_id": "Module ID",
        "module_name": "Module Name",
        "candidate_count": "Candidate Count",
        "applied_count": "Applied Count",
        "skipped_count": "Skipped Count",
        "status": "Status",
        "report_html": "Module Report",
    }

    def write_summary_csv(path, headers, english=False):
        with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([headers[field] for field in fields])
            for row in rows:
                module_id = str(row.get("module_id") or "")
                module_name = (
                    BATCH_MODULE_LABELS_EN.get(module_id, row.get("module_name", ""))
                    if english
                    else BATCH_MODULE_LABELS.get(module_id, row.get("module_name", ""))
                )
                values = {
                    **row,
                    "module_id": module_id,
                    "module_name": module_name,
                }
                writer.writerow([values.get(field, "") for field in fields])

    if chinese_ui:
        csv_path = output_dir / "batch_summary_CN.csv"
        csv_en_path = output_dir / "batch_summary_EN.csv"
        write_summary_csv(csv_path, cn_headers, english=False)
        write_summary_csv(csv_en_path, en_headers, english=True)
    else:
        csv_path = output_dir / "batch_summary_EN.csv"
        write_summary_csv(csv_path, en_headers, english=True)

    table_rows = []
    for row in rows:
        report_value = str(row.get("report_html") or "")
        report_cell = "-"
        if report_value:
            try:
                rel = Path(report_value).resolve().relative_to(output_dir.resolve())
                href = rel.as_posix()
            except Exception:
                href = Path(report_value).as_uri() if Path(report_value).is_absolute() else report_value
            report_cell = f'<a href="{html.escape(href)}">打开模块报告</a>'
        table_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('module_name') or row.get('module_id') or ''))}</td>"
            f"<td>{int(row.get('candidate_count') or 0)}</td>"
            f"<td>{int(row.get('applied_count') or 0)}</td>"
            f"<td>{int(row.get('skipped_count') or 0)}</td>"
            f"<td>{html.escape(str(row.get('status') or ''))}</td>"
            f"<td>{report_cell}</td>"
            "</tr>"
        )

    html_text = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body{{font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;margin:0;background:#F3F7F5;color:#17372E}}
header{{background:#006B52;color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}} .card{{background:white;border:1px solid #D3E3DC;border-radius:10px;padding:16px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th{{background:#006B52;color:white}}
th,td{{border:1px solid #D3E3DC;padding:8px 10px;text-align:left}} a{{color:#006B52;font-weight:600}}
.note{{margin:8px 0 16px;color:#53636C}}
</style></head><body><header><h1>{html.escape(title)}</h1></header><main><div class="card">
<p class="note">{html.escape(subtitle)}</p>
<table><thead><tr><th>模块</th><th>可关联对象</th><th>成功写回</th><th>执行时跳过</th><th>状态</th><th>详细报告</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table></div></main></body></html>"""
    html_path.write_text(html_text, encoding="utf-8")
    return html_path, csv_path


class BatchAssociationOrchestrator:
    """Compose existing independent modules without duplicating business rules."""

    def __init__(self, modules):
        self.modules = modules

    def validate(
        self,
        db,
        files,
        settings_by_module,
        selected_module_ids,
        report_root,
        log_callback,
        progress_callback=None,
        language="zh_CN",
    ):
        files = [Path(p) for p in files]
        ensure_unique_basenames(files)
        selected = [mid for mid in BATCH_MODULE_ORDER if mid in set(selected_module_ids)]
        if not selected:
            raise RuntimeError("请至少选择一个批量关联模块。")

        previews = {}
        rows = []
        report_root = Path(report_root)
        report_root.mkdir(parents=True, exist_ok=True)

        total = len(selected)
        for index, module_id in enumerate(selected, start=1):
            module = self.modules[module_id]
            if not module.supports("PREVIEW_ASSOCIATION") or not module.supports("APPLY_ASSOCIATION"):
                raise RuntimeError(f"{module.display_name} 当前不支持批量关联。")
            if progress_callback:
                progress_callback(
                    5 + int((index - 1) * 80 / max(total, 1)),
                    f"批量校验：{module.display_name}",
                )
            log_callback(f"\n[批量校验 {index}/{total}] {module.display_name}")
            settings = dict(settings_by_module[module_id])
            preview = module.preview_association(
                db,
                files,
                settings,
                log_callback,
                None,
            )
            previews[module_id] = preview
            candidate_count = _association_count(preview)

            module_dir = _module_report_dir(report_root, index, module_id)
            module_dir.mkdir(parents=True, exist_ok=True)
            report_html = module_dir / "report.html"
            export_html_bundle(
                preview.get("reports", []),
                report_html,
                preview.get("rules", {}),
                language=language,
            )
            csv_paths = export_csv_bundle(
                preview.get("reports", []),
                module_dir / "report.csv",
                language=language,
            )
            rows.append({
                "module_id": module_id,
                "module_name": BATCH_MODULE_LABELS.get(module_id, module.display_name),
                "candidate_count": candidate_count,
                "applied_count": 0,
                "skipped_count": 0,
                "status": "READY" if candidate_count else "NO_CHANGE",
                "report_html": str(report_html),
                "report_csv": str(csv_paths[0]) if csv_paths else "",
                "failure_csv": str(csv_paths[-1]) if csv_paths else "",
            })
            log_callback(
                f"批量校验完成：{module.display_name}，可关联对象 {candidate_count} 个。"
            )

        conflicts = detect_preview_conflicts(previews)
        candidate_rows = build_batch_candidate_rows(previews, conflicts)
        if conflicts:
            log_callback(f"批量写回冲突检查：发现 {len(conflicts)} 个属性冲突；冲突对象将在批量确认列表中禁用。")
        else:
            log_callback("批量写回冲突检查：通过。")

        summary_html, summary_csv = export_batch_summary(
            rows,
            report_root,
            "批量模型校验汇总",
            "独立模块仍保留；批量模式只统一调度现有模块。执行批量关联时，每个模块会再次做自己的执行前安全复核。",
            language=language,
        )
        if progress_callback:
            progress_callback(100, "批量模型校验完成")
        return {
            "selected_modules": selected,
            "previews": previews,
            "module_rows": rows,
            "conflicts": conflicts,
            "candidate_rows": candidate_rows,
            "source_fingerprints": capture_source_fingerprints(files),
            "summary_html": str(summary_html),
            "summary_csv": str(summary_csv),
        }

    def apply(
        self,
        db,
        files,
        settings_by_module,
        validation_bundle,
        output_root,
        report_root,
        log_callback,
        progress_callback=None,
        language="zh_CN",
    ):
        files = [Path(p) for p in files]
        ensure_unique_basenames(files)
        verify_source_fingerprints(validation_bundle.get("source_fingerprints", {}))
        conflicts = validation_bundle.get("conflicts", []) or []
        if conflicts:
            raise RuntimeError(
                f"批量校验存在 {len(conflicts)} 个跨模块写回冲突，禁止执行批量关联。"
            )

        selected = [
            mid for mid in BATCH_MODULE_ORDER
            if mid in set(validation_bundle.get("selected_modules", []))
        ]
        previews = validation_bundle.get("previews", {}) or {}
        if not selected:
            raise RuntimeError("没有可执行的批量关联模块。")

        output_root = Path(output_root)
        report_root = Path(report_root)
        stage_root = output_root.parent / "_batch_stages"
        if stage_root.exists():
            shutil.rmtree(stage_root)
        stage_root.mkdir(parents=True, exist_ok=True)
        if output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)
        report_root.mkdir(parents=True, exist_ok=True)

        original_files = [Path(p) for p in files]
        current_by_original = {_path_key(p): Path(p) for p in original_files}
        module_rows = []
        module_results = {}
        total = len(selected)

        for index, module_id in enumerate(selected, start=1):
            module = self.modules[module_id]
            preview = previews.get(module_id) or {}
            candidate_count = _association_count(preview)
            if progress_callback:
                progress_callback(
                    3 + int((index - 1) * 85 / max(total, 1)),
                    f"批量关联：{module.display_name}",
                )
            log_callback(f"\n[批量关联 {index}/{total}] {module.display_name}")

            if candidate_count <= 0:
                module_rows.append({
                    "module_id": module_id,
                    "module_name": BATCH_MODULE_LABELS.get(module_id, module.display_name),
                    "candidate_count": 0,
                    "applied_count": 0,
                    "skipped_count": 0,
                    "status": "NO_CHANGE",
                    "report_html": "",
                })
                log_callback(f"{module.display_name}：本次没有需要写回的对象，跳过。")
                continue

            rebased_preview = rebase_preview_for_current_files(
                preview,
                current_by_original,
            )
            current_files = [current_by_original[_path_key(p)] for p in original_files]
            stage_dir = stage_root / f"{index:02d}_{module_id.lower()}"
            result = module.apply_association(
                db,
                current_files,
                dict(settings_by_module[module_id]),
                rebased_preview,
                log_callback,
                output_g_dir=stage_dir,
            )
            module_results[module_id] = result

            # Each stage directory starts empty and source basenames are unique,
            # so a changed source has exactly one cumulative output with the same
            # basename.  Files not touched by this module keep their previous
            # cumulative path.
            original_change_files = list((preview.get("changes_by_file", {}) or {}).keys())
            for original_source in original_change_files:
                original_key = _path_key(original_source)
                previous_current = Path(current_by_original[original_key])
                candidate = stage_dir / previous_current.name
                if candidate.exists():
                    current_by_original[original_key] = candidate

            module_dir = _module_report_dir(report_root, index, module_id)
            module_dir.mkdir(parents=True, exist_ok=True)
            report_html = module_dir / "report.html"
            export_html_bundle(
                result.get("operation_reports", []),
                report_html,
                result.get("rules", preview.get("rules", {})),
                language=language,
            )
            export_csv_bundle(
                result.get("operation_reports", []),
                module_dir / "report.csv",
                language=language,
            )
            applied = int(result.get("applied_count", 0) or 0)
            skipped = int(result.get("skipped_count", 0) or 0)
            module_rows.append({
                "module_id": module_id,
                "module_name": BATCH_MODULE_LABELS.get(module_id, module.display_name),
                "candidate_count": candidate_count,
                "applied_count": applied,
                "skipped_count": skipped,
                "status": "DONE" if applied or not skipped else "SKIPPED",
                "report_html": str(report_html),
            })
            log_callback(
                f"{module.display_name}：候选 {candidate_count}，成功写回 {applied}，执行时跳过 {skipped}。"
            )
            if progress_callback:
                progress_callback(
                    min(88, 3 + int(index * 85 / max(total, 1))),
                    f"批量关联：{module.display_name} 已完成",
                )

        # Publish exactly one cumulative safety copy per original G file.
        # Large batches used to look frozen here because hundreds of copy2
        # operations happened after the last module without visible progress.
        publish_total = max(1, len(original_files))
        for publish_index, original in enumerate(original_files, start=1):
            current = current_by_original[_path_key(original)]
            target = output_root / original.name
            shutil.copy2(current, target)
            if progress_callback:
                progress_callback(
                    min(99, 89 + int(publish_index * 10 / publish_total)),
                    f"正在生成最终安全副本 {publish_index}/{publish_total}",
                )

        summary_html, summary_csv = export_batch_summary(
            module_rows,
            report_root,
            "批量模型关联执行汇总",
            "所有模块复用各自原有识别、数据库校验和执行前复核逻辑；最终每个 G 文件只发布一个累计安全副本，原始文件不修改。",
            language=language,
        )
        if progress_callback:
            progress_callback(100, "批量模型关联完成")

        return {
            "module_rows": module_rows,
            "module_results": module_results,
            "selected_count": sum(int(r.get("candidate_count", 0) or 0) for r in module_rows),
            "applied_count": sum(int(r.get("applied_count", 0) or 0) for r in module_rows),
            "skipped_count": sum(int(r.get("skipped_count", 0) or 0) for r in module_rows),
            "output_g_dir": str(output_root),
            "copied_files": [str(output_root / p.name) for p in original_files],
            "summary_html": str(summary_html),
            "summary_csv": str(summary_csv),
        }
