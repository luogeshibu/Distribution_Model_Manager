from __future__ import annotations

import csv
import html
from pathlib import Path

from g_file_studio.services.html_report_selection import (
    selection_bar,
    selection_cell,
    selection_header,
    selection_script,
    selection_style,
)
from g_file_studio.services.report_i18n import report_is_english


_DETAIL_HEADERS = [
    "File",
    "Type",
    "SourceName",
    "NameElementID",
    "FrameElementID",
    "StationKey",
    "AdjacentRMU",
    "LocateLabel",
    "ResolvedBusinessName",
    "CurrentStation",
    "TargetFormat",
    "Action",
    "PokeID",
    "TargetAhref",
    "Confidence",
    "RecognitionSource",
    "Reason",
]


def _target_format(row: dict[str, object], *, english: bool) -> str:
    """Describe the target naming rule that produced the written ahref."""
    jump_type = str(row.get("Type") or "").strip().lower()
    locate_label = str(row.get("LocateLabel") or "").strip()
    if jump_type == "rmu":
        return "RMU detail: {area}-{substation}-{feeder}-{RMU}.com.pic.g" if english else "RMU 明细图：{区域}-{变电站}-{馈线}-{RMU}.com.pic.g"
    if jump_type == "classified_device":
        return "Device detail: {area}-{substation}-{feeder}-{device}.com.pic.g" if english else "设备明细图：{区域}-{变电站}-{馈线}-{设备名}.com.pic.g"
    if jump_type == "station":
        if locate_label:
            return "Station overview: {area}-{substation}.sln.pic.g?locateLabel={number}&&scaleFlag=true" if english else "站点馈线总图：{区域}-{变电站}.sln.pic.g?locateLabel={数字}&&scaleFlag=true"
        return "Station overview: {area}-{substation}.sln.pic.g" if english else "站点馈线总图：{区域}-{变电站}.sln.pic.g"
    return ""


def _yes_no(value: object, *, english: bool) -> str:
    return ("Yes" if bool(value) else "No") if english else ("是" if bool(value) else "否")


def _action_text(value: object, *, english: bool) -> str:
    action = str(value or "").strip().lower()
    if english:
        return {
            "added": "Added",
            "updated": "Updated",
            "unchanged": "Unchanged",
            "skipped": "Skipped",
            "file_skipped": "File Skipped",
        }.get(action, str(value or ""))
    return {
        "added": "新增",
        "updated": "更新/复用",
        "unchanged": "已符合",
        "skipped": "未加跳转",
        "file_skipped": "文件未处理",
    }.get(action, str(value or ""))


def _type_text(value: object, *, english: bool) -> str:
    key = str(value or "").strip().lower()
    if english:
        return {"rmu": "RMU Poke", "classified_device": "AR/LBS/SEC Poke", "station": "Station-jump Poke", "file": "File"}.get(key, str(value or ""))
    return {"rmu": "RMU Poke", "classified_device": "AR/LBS/SEC 设备 Poke", "station": "站点跳转 Poke", "file": "文件"}.get(key, str(value or ""))


def _source_text(value: object, *, english: bool) -> str:
    key = str(value or "").strip().lower()
    if english:
        return {
            "existing_poke": "Existing Poke",
            "rmu_identification": "Shared RMU identification",
            "classification_device_name": "AR/LBS/SEC classification + nearest unique Text",
            "background_color": "Colored background",
            "station_interval": "Station interval suffix",
            "locate_label": "Adjacent parenthesized RMU label",
            "file_precondition": "File precondition",
        }.get(key, str(value or ""))
    return {
        "existing_poke": "已有 Poke 覆盖",
        "rmu_identification": "公共 RMU 识别",
        "classification_device_name": "AR/LBS/SEC 分类图元 + 最近唯一名称 Text",
        "background_color": "彩色背景",
        "station_interval": "站点间隔后缀",
        "locate_label": "相邻括号环网柜名",
        "file_precondition": "文件前置条件",
    }.get(key, str(value or ""))


def write_poke_reports(
    output_dir: Path,
    *,
    statistics: dict[str, object],
    file_summaries: list[dict[str, object]],
    detail_rows: list[dict[str, object]],
) -> tuple[Path, Path]:
    """Write one run-scoped Poke CSV detail report and an HTML summary/detail report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "poke-processing-report.csv"
    html_path = output_dir / "poke-processing-report.html"
    english = report_is_english()

    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=_DETAIL_HEADERS)
        writer.writeheader()
        for raw in detail_rows:
            row = dict(raw)
            row["Type"] = _type_text(row.get("Type"), english=english)
            row["Action"] = _action_text(row.get("Action"), english=english)
            row["RecognitionSource"] = _source_text(row.get("RecognitionSource"), english=english)
            row["TargetFormat"] = _target_format(raw, english=english)
            writer.writerow({key: row.get(key, "") for key in _DETAIL_HEADERS})

    title = "Poke Processing Report" if english else "Poke 跳转处理报告"
    summary_title = "Run Summary" if english else "本次处理汇总"
    file_title = "Per-file Summary" if english else "文件级汇总"
    detail_title = "Jump Details and Skip Reasons" if english else "跳转明细与未加跳转原因"

    cards = [
        ("Files processed" if english else "处理文件", f"{statistics.get('processed_count', 0)}/{statistics.get('input_count', 0)}"),
        ("RMUs recognized" if english else "识别 RMU 总数", statistics.get("rmu_identified_total", 0)),
        ("Smart RMUs" if english else "智能 RMU 数", statistics.get("smart_rmu_identified_total", 0)),
        ("RMU DB resolved" if english else "RMU 数据库解析成功", statistics.get("rmu_database_resolved", 0)),
        ("RMU DB unresolved" if english else "RMU 数据库未解析", statistics.get("rmu_database_unresolved", 0)),
        ("RMU Pokes added" if english else "新增 RMU Poke", statistics.get("rmu_added", 0)),
        ("RMU Pokes updated" if english else "更新/复用 RMU Poke", statistics.get("rmu_updated", 0)),
        ("RMU Pokes skipped" if english else "RMU 未加跳转", statistics.get("rmu_skipped", 0)),
        ("AR/LBS/SEC devices" if english else "AR/LBS/SEC 分类设备", statistics.get("classified_device_total", 0)),
        ("Device names assigned" if english else "设备名称已分配", statistics.get("classified_device_named", 0)),
        ("Device Pokes added" if english else "新增设备 Poke", statistics.get("classified_device_added", 0)),
        ("Device Pokes updated" if english else "更新设备 Poke", statistics.get("classified_device_updated", 0)),
        ("Device Pokes skipped" if english else "设备未加跳转", statistics.get("classified_device_skipped", 0)),
        ("Station-jump candidates" if english else "站点跳转候选", statistics.get("station_candidates", 0)),
        ("Stations resolved" if english else "成功解析站点跳转", statistics.get("station_resolved_count", 0)),
        ("Station Pokes added" if english else "新增站点跳转 Poke", statistics.get("station_added", 0)),
        ("Station Pokes updated" if english else "更新/复用站点跳转 Poke", statistics.get("station_updated", 0)),
        ("Station Pokes skipped" if english else "站点 Poke 未加跳转", statistics.get("station_skipped", 0)),
        ("Duplicate station Pokes removed" if english else "删除重复站点跳转 Poke", statistics.get("station_duplicate_removed", 0)),
    ]
    card_html = "".join(
        f"<div class='card'><div class='card-label'>{html.escape(str(label))}</div>"
        f"<div class='card-value'>{html.escape(str(value))}</div></div>"
        for label, value in cards
    )

    file_headers = [
        "File",
        "FacID",
        "FeederBusinessName",
        "RMURecognized",
        "SmartRMU",
        "RMUAdded",
        "RMUUpdated",
        "RMUSkipped",
        "DeviceRecognized",
        "DeviceNamed",
        "DeviceAdded",
        "DeviceUpdated",
        "DeviceSkipped",
        "StationCandidates",
        "StationResolved",
        "StationAdded",
        "StationUpdated",
        "StationSkipped",
        "DuplicatesRemoved",
        "Status",
        "Reason",
    ]
    file_header_labels = {
        "File": "File" if english else "文件",
        "FacID": "facID",
        "FeederBusinessName": "RMU-resolved feeders" if english else "RMU 解析所属馈线（可多条）",
        "RMURecognized": "RMUs recognized" if english else "识别 RMU",
        "SmartRMU": "Smart RMUs" if english else "智能 RMU",
        "RMUAdded": "RMU added" if english else "新增 RMU Poke",
        "RMUUpdated": "RMU updated" if english else "更新 RMU Poke",
        "RMUSkipped": "RMU skipped" if english else "RMU 未跳转",
        "DeviceRecognized": "AR/LBS/SEC devices" if english else "AR/LBS/SEC 设备",
        "DeviceNamed": "Device names assigned" if english else "设备名称分配",
        "DeviceAdded": "Device Pokes added" if english else "新增设备 Poke",
        "DeviceUpdated": "Device Pokes updated" if english else "更新设备 Poke",
        "DeviceSkipped": "Device Pokes skipped" if english else "设备未跳转",
        "StationCandidates": "Station candidates" if english else "站点跳转候选",
        "StationResolved": "Station resolved" if english else "站点跳转成功解析",
        "StationAdded": "Station added" if english else "新增站点跳转 Poke",
        "StationUpdated": "Station updated" if english else "更新站点跳转 Poke",
        "StationSkipped": "Station skipped" if english else "站点 Poke 未加跳转",
        "DuplicatesRemoved": "Duplicates removed" if english else "删除重复 Poke",
        "Status": "Status" if english else "状态",
        "Reason": "Reason" if english else "说明",
    }
    file_rows_html = []
    for row in file_summaries:
        status = str(row.get("Status", "")).lower()
        css = "issue" if status in {"skipped", "warning", "failed"} else "ok"
        cells = "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in file_headers)
        file_rows_html.append(f"<tr class='{css}'>{selection_cell()}{cells}</tr>")

    detail_header_labels = {
        "File": "File" if english else "文件",
        "Type": "Type" if english else "类型",
        "SourceName": "Source name" if english else "识别名称/站点标签原文",
        "NameElementID": "Name element ID" if english else "名称元素 ID",
        "FrameElementID": "Frame element ID" if english else "环网柜框元素 ID",
        "StationKey": "Station key" if english else "站名关键字",
        "AdjacentRMU": "Adjacent RMU name" if english else "相邻环网柜名",
        "LocateLabel": "Locate label" if english else "定位号",
        "ResolvedBusinessName": "Resolved business name" if english else "数据库解析业务名",
        "CurrentStation": "Current station" if english else "当前变电站判定",
        "TargetFormat": "Target format" if english else "跳转目标格式",
        "Action": "Action" if english else "处理结果",
        "PokeID": "Poke ID",
        "TargetAhref": "Target ahref" if english else "写入跳转名称 (ahref)",
        "Confidence": "Confidence" if english else "识别置信度",
        "RecognitionSource": "Recognition source" if english else "识别依据",
        "Reason": "Reason" if english else "处理说明 / 未加跳转原因",
    }
    detail_rows_html = []
    for raw in detail_rows:
        row = dict(raw)
        action_key = str(row.get("Action", "")).strip().lower()
        css = "added" if action_key == "added" else ("updated" if action_key == "updated" else ("issue" if action_key in {"skipped", "file_skipped"} else "ok"))
        row["Type"] = _type_text(row.get("Type"), english=english)
        row["Action"] = _action_text(row.get("Action"), english=english)
        row["RecognitionSource"] = _source_text(row.get("RecognitionSource"), english=english)
        row["TargetFormat"] = _target_format(raw, english=english)
        cells = "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in _DETAIL_HEADERS)
        detail_rows_html.append(f"<tr class='{css}'>{selection_cell()}{cells}</tr>")

    html_path.write_text(
        "<!doctype html>"
        f"<html lang='{'en' if english else 'zh-CN'}'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        "<style>"
        "body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1f2937;background:#fff}"
        "h1{margin:0 0 8px}h2{margin-top:26px}.note{color:#64748b;margin-bottom:16px}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:14px 0 22px}"
        ".card{border:1px solid #cbd5e1;border-left:4px solid #12815f;border-radius:6px;padding:10px;background:#f8fbfa}"
        ".card-label{font-size:12px;color:#64748b}.card-value{font-size:22px;font-weight:700;margin-top:3px}"
        "table{border-collapse:collapse;width:100%;font-size:12px;margin-top:10px}"
        "th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left;vertical-align:top;white-space:normal}"
        "th{background:#e8f3ef;position:sticky;top:0}.ok{background:#f7faf9}.added{background:#e9f8ef}.updated{background:#fff8dc}.issue{background:#ffe7e7}"
        ".legend{font-size:12px;color:#64748b;margin:8px 0 12px}"
        + selection_style()
        + "</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<div class='note'>{html.escape('报告记录每个 RMU/站点跳转 Poke 的识别名称元素 ID、环网柜框元素 ID、Poke ID、相邻环网柜名、定位号、目标格式、写入 ahref、处理动作，以及所有未加跳转的原因。' if not english else 'The report records the source name-element ID, RMU frame-element ID, Poke ID, adjacent RMU name, locate label, target format, written ahref, action, and every reason a jump was not added.')}</div>"
        f"<h2>{html.escape(summary_title)}</h2><div class='cards'>{card_html}</div>"
        f"<h2>{html.escape(file_title)}</h2>"
        + selection_bar()
        + "<table><thead><tr>" + selection_header() + "".join(f"<th>{html.escape(file_header_labels[h])}</th>" for h in file_headers) + "</tr></thead><tbody>"
        + "".join(file_rows_html)
        + "</tbody></table>"
        f"<h2>{html.escape(detail_title)}</h2>"
        + "<div class='legend'>" + html.escape("绿色=新增，黄色=更新/复用，红色=未加跳转/文件跳过。" if not english else "Green=added, yellow=updated/reused, red=jump not added/file skipped.") + "</div>"
        + selection_bar()
        + "<table><thead><tr>" + selection_header() + "".join(f"<th>{html.escape(detail_header_labels[h])}</th>" for h in _DETAIL_HEADERS) + "</tr></thead><tbody>"
        + "".join(detail_rows_html)
        + "</tbody></table>"
        + selection_script()
        + "</body></html>",
        encoding="utf-8",
    )
    return csv_path, html_path
