from __future__ import annotations

import csv
import html
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from g_file_studio.engines.id_engine import inspect_tree_ids
from g_file_studio.engines.id_rule_engine import normalize_tree_ids_strict, scan_tree_against_rules
from g_file_studio.models import BasicOutputConflictAction, IdAction, IdSettings, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs
from g_file_studio.services.id_rule_service import IdRuleService
from g_file_studio.services.html_report_selection import selection_bar, selection_cell, selection_header, selection_script, selection_style
from g_file_studio.services.report_i18n import report_is_english, report_text
from g_file_studio.services.output_naming import make_task_timestamp
from g_file_studio.services.user_settings_service import UserSettingsService


def _write_id_reports(
    output_dir: Path,
    rows: list[dict[str, str]],
    timestamp: str,
    report_kind: str = "repair",
) -> tuple[Path, Path]:
    """Write ID report using stable filenames and overwrite previous same-kind report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base = "id-scan-report" if report_kind == "scan" else "id-repair-report"
    csv_path = output_dir / f"{base}.csv"
    html_path = output_dir / f"{base}.html"
    headers = ["File", "Category", "ElementType", "OriginalID", "NewID", "Detail"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: report_text(row.get(h, "")) if h in {"Category", "Detail"} else row.get(h, "") for h in headers})

    body_rows = []
    for row in rows:
        category = row.get("Category", "")
        css = "ok" if category == "正常" else ("fixed" if category == "已修复" else "issue")
        body_rows.append(
            f"<tr class='{css}'>" + selection_cell() + "".join(
                f"<td>{html.escape(report_text(row.get(h, '')) if h in {'Category', 'Detail'} else str(row.get(h, '')))}</td>"
                for h in headers
            ) + "</tr>"
        )
    english = report_is_english()
    report_title = "ID Scan Report" if (english and report_kind == "scan") else ("ID Check & Repair Report" if english else "ID 检查与修复报告")
    summary_text = (
        f"Generated: {html.escape(timestamp)}; Records: {len(rows)}"
        if english else f"生成时间：{html.escape(timestamp)}；记录数：{len(rows)}"
    )
    html_path.write_text(
        f"<!doctype html><html lang='{"en" if english else "zh-CN"}'><head><meta charset='utf-8'><title>{report_title}</title>"
        "<style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1f2937}"
        "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left;vertical-align:top}"
        "th{background:#e8f3ef;position:sticky;top:0}.ok{background:#edf9f2}.fixed{background:#fff7d6}.issue{background:#ffe1e1}"
        ".summary{margin:12px 0;padding:10px;background:#f3f7f5;border-left:4px solid #12815f}" + selection_style() + "</style></head><body>"
        f"<h2>{report_title}</h2><div class='summary'>{summary_text}</div>"
        + selection_bar() + "<table><thead><tr>" + selection_header() + "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"
        + "".join(body_rows) + "</tbody></table>" + selection_script() + "</body></html>",
        encoding="utf-8",
    )
    return csv_path, html_path


def process_ids(settings: IdSettings, log: LogCallback, progress: ProgressCallback) -> ProcessingResult:
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    if not files:
        raise ValueError("没有找到可处理的 G 文件。")

    rules = IdRuleService().load_rules()
    strict_existing = UserSettingsService().get_bool("id_rules/global_strict", True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    warnings: list[str] = []
    duplicate_kinds = 0
    repaired_count = 0
    new_types: set[str] = set()
    changed_types: set[str] = set()
    report_rows: list[dict[str, str]] = []
    report_timestamp = settings.task_timestamp or make_task_timestamp()

    for index, input_path in enumerate(files, 1):
        file_issue_count = 0
        try:
            tree = ET.parse(input_path)
            scan = scan_tree_against_rules(tree, input_path, rules)
            for item in scan.new_rule_candidates:
                new_types.add(item.tag)
                detail = f"尚未加入模板；候选前缀 {item.prefix}（需人工确认）"
                log(f"[新 ID 类型] {input_path.name}：<{item.tag}> {detail}；样本：{', '.join(item.sample_ids)}")
                for value in item.sample_ids or [""]:
                    report_rows.append({"File": input_path.name, "Category": "未配置模板", "ElementType": item.tag, "OriginalID": value, "NewID": "", "Detail": detail})
                    file_issue_count += 1
            for item in scan.unknown_uninferable:
                new_types.add(item.tag)
                detail = "尚未加入模板，且样本不足以可靠推断格式"
                log(f"[新 ID 类型] {input_path.name}：<{item.tag}> {detail}；样本：{', '.join(item.sample_ids)}")
                for value in item.sample_ids or [""]:
                    report_rows.append({"File": input_path.name, "Category": "未配置模板", "ElementType": item.tag, "OriginalID": value, "NewID": "", "Detail": detail})
                    file_issue_count += 1
            for item in scan.changed_formats:
                changed_types.add(item.tag)
                rule = rules.get(item.tag)
                detail = f"模板要求前缀 {rule.prefix}、总位数 {rule.total_length}" if rule else "不符合当前模板"
                log(
                    f"[ID 格式变化] {input_path.name}：<{item.tag}> {detail}，但发现：{', '.join(item.sample_ids)}。"
                    + ("执行修复时将严格按当前模板强制更新这些 ID。" if strict_existing else "全局强制约束已关闭：这些已有格式不符 ID 将保留不变。")
                )
                for value in item.sample_ids:
                    report_rows.append({"File": input_path.name, "Category": "格式不符", "ElementType": item.tag, "OriginalID": value, "NewID": "", "Detail": detail})
                    file_issue_count += 1

            inspection = inspect_tree_ids(tree, input_path)
            duplicate_kinds += len(inspection.duplicate_groups)
            if inspection.duplicate_groups:
                for group in inspection.duplicate_groups:
                    tags = ", ".join(group.tags)
                    log(f"[重复 ID] {input_path.name}：{group.value} × {group.count}；类型：{tags}")
                    report_rows.append({"File": input_path.name, "Category": "重复 ID", "ElementType": tags, "OriginalID": group.value, "NewID": "", "Detail": f"出现 {group.count} 次"})
                    file_issue_count += 1
            else:
                log(f"[ID 检查] {input_path.name}：未发现重复 ID。")

            if settings.action == IdAction.REPAIR:
                repair = normalize_tree_ids_strict(tree, input_path, rules, repair_invalid_formats=strict_existing)
                if repair.final_duplicate_count:
                    raise ValueError("严格模板修复后仍存在重复 ID。")
                repaired_count += repair.changed_element_ids
                for tag, old_id, new_id, reason in repair.changes:
                    log(f"[ID 强制修复] <{tag}> {old_id} → {new_id}（{reason}；严格按模板）")
                    report_rows.append({"File": input_path.name, "Category": "已修复", "ElementType": tag, "OriginalID": old_id, "NewID": new_id, "Detail": reason})
                if repair.format_fixed_count:
                    log(f"[ID 模板修复] {input_path.name}：强制修复格式不符 ID {repair.format_fixed_count} 个。")

                # 一对一 G 文件处理统一保持源文件名；运行目录负责隔离不同批次。
                output_path = settings.output_dir / input_path.name
                if hasattr(ET, "indent"):
                    ET.indent(tree, space="    ")
                tmp = output_path.with_name(output_path.name + ".tmp")
                tree.write(tmp, encoding="utf-8", xml_declaration=True)
                ET.parse(tmp)
                os.replace(tmp, output_path)
                outputs.append(output_path)

            if file_issue_count == 0:
                report_rows.append({"File": input_path.name, "Category": "正常", "ElementType": "", "OriginalID": "", "NewID": "", "Detail": "未发现模板格式异常或重复 ID"})
        except Exception as exc:
            warnings.append(f"{input_path.name}: {exc}")
            log(f"[ID 处理失败] {input_path.name}：{exc}")
            report_rows.append({"File": input_path.name, "Category": "处理失败", "ElementType": "", "OriginalID": "", "NewID": "", "Detail": str(exc)})
        if progress:
            progress(round(index * 100 / len(files)))

    csv_path, html_path = _write_id_reports(settings.output_dir, report_rows, report_timestamp, report_kind="repair")
    outputs.extend([csv_path, html_path])
    log(f"[ID 报告] CSV：{csv_path}")
    log(f"[ID 报告] HTML：{html_path}")

    return ProcessingResult(
        success=not warnings,
        output_files=outputs,
        warnings=warnings,
        statistics={
            "scanned_file_count": len(files),
            "duplicate_id_kind_count": duplicate_kinds,
            "repaired_id_count": repaired_count,
            "new_id_type_count": len(new_types),
            "changed_id_format_type_count": len(changed_types),
            "html_report_path": str(html_path),
            "csv_report_path": str(csv_path),
        },
    )
