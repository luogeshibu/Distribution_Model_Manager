from __future__ import annotations

import csv
import html
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from g_file_studio.services.output_naming import make_task_timestamp
from g_file_studio.services.html_report_selection import selection_bar, selection_cell, selection_header, selection_script, selection_style
from g_file_studio.services.report_i18n import report_is_english, report_text

TARGET_TAGS = {"ConnectLine", "FeedLine", "Bus", "BusDis"}
REFERENCE_LIST_ATTRIBUTES = ("link", "node_area")
REFERENCE_SINGLE_ATTRIBUTES = ("p_FatherObjId",)


def local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _number(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None


@dataclass(frozen=True)
class SmallElementIssue:
    file_path: Path
    file_name: str
    element_type: str
    xml_id: str
    ordinal: int
    x: str
    y: str
    w: str
    h: str
    keyid: str

    @property
    def location(self) -> str:
        return f"x={self.x or '-'}, y={self.y or '-'}"


def scan_file(path: Path, threshold: int = 10) -> list[SmallElementIssue]:
    tree = ET.parse(path)
    root = tree.getroot()
    limit = Decimal(str(threshold))
    result: list[SmallElementIssue] = []
    ordinal = 0
    for element in root.iter():
        tag = local_name(element.tag)
        if tag not in TARGET_TAGS:
            continue
        ordinal += 1
        w = _number(element.get("w"))
        h = _number(element.get("h"))
        if w is None or h is None:
            continue
        if w < limit and h < limit:
            result.append(
                SmallElementIssue(
                    file_path=path,
                    file_name=path.name,
                    element_type=tag,
                    xml_id=(element.get("id") or "").strip(),
                    ordinal=ordinal,
                    x=(element.get("x") or "").strip(),
                    y=(element.get("y") or "").strip(),
                    w=(element.get("w") or "").strip(),
                    h=(element.get("h") or "").strip(),
                    keyid=(element.get("keyid") or "").strip(),
                )
            )
    return result


def scan_files(paths: Iterable[Path], threshold: int = 10) -> list[SmallElementIssue]:
    result: list[SmallElementIssue] = []
    for path in paths:
        result.extend(scan_file(Path(path), threshold))
    return result


def write_reports(
    output_dir: Path,
    issues: list[SmallElementIssue],
    threshold: int,
    timestamp: str | None = None,
    report_kind: str = "scan",
    processed_keys: set[tuple[str, str, int, str]] | None = None,
) -> tuple[Path, Path]:
    """Write the current report, overwriting the previous report of the same kind.

    report_kind="scan" and report_kind="process" intentionally use different fixed
    filenames so repeated scans/processing do not accumulate report files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or make_task_timestamp()
    base = "small-element-scan-report" if report_kind == "scan" else "small-element-process-report"
    csv_path = output_dir / f"{base}.csv"
    html_path = output_dir / f"{base}.html"
    is_process = report_kind == "process"
    headers = ["File", "ElementType", "XMLID", "X", "Y", "W", "H", "KeyID", "Reason"]
    if is_process:
        headers.extend(["Selected", "ProcessResult"])
    if is_process and processed_keys is None:
        processed_keys = {
            (str(item.file_path), item.element_type, item.ordinal, item.xml_id)
            for item in issues
        }
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for item in issues:
            values = [
                item.file_name, item.element_type, item.xml_id, item.x, item.y,
                item.w, item.h, item.keyid,
                (f"w<{threshold} and h<{threshold}" if report_is_english() else f"w<{threshold} 且 h<{threshold}"),
            ]
            if is_process:
                key = (str(item.file_path), item.element_type, item.ordinal, item.xml_id)
                selected = key in (processed_keys or set())
                values.extend(["YES" if selected else "NO", report_text("已删除" if selected else "未处理")])
            writer.writerow(values)

    rows = []
    for item in issues:
        key_class = " keyid" if item.keyid else ""
        key = (str(item.file_path), item.element_type, item.ordinal, item.xml_id)
        was_processed = is_process and key in (processed_keys or set())
        row_class = "processed" if was_processed else ("unprocessed" if is_process else ("issue keyid" if item.keyid else "issue"))
        values = [
            item.file_name, item.element_type, item.xml_id, item.x, item.y,
            item.w, item.h, item.keyid, (f"w<{threshold} and h<{threshold}" if report_is_english() else f"w<{threshold} 且 h<{threshold}"),
        ]
        if is_process:
            values.extend(["YES" if was_processed else "NO", report_text("已删除" if was_processed else "未处理")])
        rows.append(
            f"<tr class='{row_class}'>"
            + selection_cell()
            + "".join(f"<td>{html.escape(str(v))}</td>" for v in values)
            + "</tr>"
        )
    english = report_is_english()
    report_title = (
        "Abnormal Small Element Processing Report" if (english and is_process) else
        "Abnormal Small Element Detection Report" if english else
        "异常小尺寸图元处理报告" if is_process else "异常小尺寸图元检测报告"
    )
    selected_count = sum(1 for x in issues if (str(x.file_path), x.element_type, x.ordinal, x.xml_id) in (processed_keys or set()))
    keyid_count = sum(1 for x in issues if x.keyid)
    if english:
        summary_html = (
            f"<div class='summary'>Original abnormal elements: {len(issues)}; Selected this run: {selected_count}; Deleted: {selected_count}; Not processed: {len(issues)-selected_count}; With keyid: {keyid_count}. Green = deleted this run; white = not processed.</div>"
            if is_process else
            f"<div class='summary'>Generated: {html.escape(stamp)}; Threshold: w &lt; {threshold} and h &lt; {threshold}; Abnormal elements: {len(issues)}; With keyid: {keyid_count}</div>"
        )
    else:
        summary_html = (
            f"<div class='summary'>原始异常图元：{len(issues)}；本次选择：{selected_count}；已删除：{selected_count}；未处理：{len(issues)-selected_count}；带 keyid：{keyid_count}。绿色=本次已删除；白色=本次未处理。</div>"
            if is_process else
            f"<div class='summary'>生成时间：{html.escape(stamp)}；阈值：w &lt; {threshold} 且 h &lt; {threshold}；异常数量：{len(issues)}；带 keyid：{keyid_count}</div>"
        )
    html_path.write_text(
        f"<!doctype html><html lang='{"en" if english else "zh-CN"}'><head><meta charset='utf-8'><title>{report_title}</title>"
        "<style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1f2937}"
        "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left}"
        "th{background:#e8f3ef}.issue{background:#fff2f2}.issue.keyid{background:#ffd7d7;font-weight:600}"
        ".processed{background:#e8f7ee}.processed td:last-child{color:#087443;font-weight:700;background:#ccefd9}.unprocessed{background:#ffffff}.unprocessed td:last-child{color:#475569;font-weight:600}"
        ".summary{margin:12px 0;padding:10px;background:#f3f7f5;border-left:4px solid #12815f}" + selection_style() + "</style></head><body>"
        f"<h2>{report_title}</h2>" + summary_html
        + selection_bar() + "<table><thead><tr>" + selection_header() + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>" + selection_script() + "</body></html>",
        encoding="utf-8",
    )
    return csv_path, html_path


def _remove_reference_groups(value: str, removed_ids: set[str]) -> str:
    kept: list[str] = []
    for group in value.split(";"):
        parts = group.split(",", 2)
        if len(parts) >= 3 and parts[2].strip() in removed_ids:
            continue
        kept.append(group)
    return ";".join(kept)


def delete_issues_to_output(
    selected: list[SmallElementIssue],
    output_dir: Path,
) -> list[Path]:
    """Delete only explicitly selected issues and write modified copies to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[Path, list[SmallElementIssue]] = {}
    for item in selected:
        grouped.setdefault(item.file_path, []).append(item)

    outputs: list[Path] = []
    for source, items in grouped.items():
        tree = ET.parse(source)
        root = tree.getroot()
        parent_map = {child: parent for parent in root.iter() for child in parent}
        wanted = {(item.element_type, item.ordinal, item.xml_id) for item in items}
        removed_ids: set[str] = set()
        ordinal = 0
        for element in list(root.iter()):
            tag = local_name(element.tag)
            if tag not in TARGET_TAGS:
                continue
            ordinal += 1
            key = (tag, ordinal, (element.get("id") or "").strip())
            if key not in wanted:
                continue
            parent = parent_map.get(element)
            if parent is None:
                continue
            xml_id = (element.get("id") or "").strip()
            if xml_id:
                removed_ids.add(xml_id)
            parent.remove(element)

        if removed_ids:
            for element in root.iter():
                for attr in REFERENCE_LIST_ATTRIBUTES:
                    value = element.get(attr)
                    if value:
                        element.set(attr, _remove_reference_groups(value, removed_ids))
                for attr in REFERENCE_SINGLE_ATTRIBUTES:
                    value = (element.get(attr) or "").strip()
                    if value in removed_ids:
                        element.set(attr, "")

        if hasattr(ET, "indent"):
            ET.indent(tree, space="    ")
        output = output_dir / source.name
        tmp = output.with_name(output.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        ET.parse(tmp)
        os.replace(tmp, output)
        outputs.append(output)
    return outputs
