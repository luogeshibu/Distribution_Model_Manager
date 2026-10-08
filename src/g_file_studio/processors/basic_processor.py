from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

from g_file_studio.engines.color_engine import ColorRule, apply_line_colors
from g_file_studio.engines.connection_engine import repair_tree_connections
from g_file_studio.engines.icon_upgrade_engine import analyze_icon_mappings, analyze_icon_pairs, apply_icon_upgrade
from g_file_studio.engines.rmu_group_engine import enhance_rmu_tree, group_rmu_tree, remove_all_graphic_merges, ungroup_rmu_tree
from g_file_studio.engines.rmu_identification_engine import identify_rmus, parse_intelligent_markers, parse_name_exclusions
from g_file_studio.engines.rmu_name_style_engine import apply_rmu_name_white_to_tree
from g_file_studio.engines.rmu_poke_engine import apply_smart_rmu_pokes
from g_file_studio.models import (
    BasicOutputConflictAction,
    BasicSettings,
    ProcessingResult,
    RmuAction,
    RmuLedgerInputMode,
)
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs, enforce_confirmed_id_rules
from g_file_studio.services.output_naming import (
    make_task_timestamp,
    strip_g_suffix,
)
from g_file_studio.services.html_report_selection import selection_bar, selection_cell, selection_header, selection_script, selection_style
from g_file_studio.services.report_i18n import report_is_english, report_text
from g_file_studio.services.rmu_ledger_service import (
    GraphicRmuRow,
    compare_ledger,
    load_ledger_file,
    parse_name_list,
    parse_pasted_table,
    write_comparison_reports,
)

REFERENCE_LIST_ATTRIBUTES = ("link", "node_area")
REFERENCE_SINGLE_ATTRIBUTES = ("p_FatherObjId",)


def _write_rmu_processing_report(output_dir: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    """Write one fixed RMU graphic-processing report for the latest run."""
    from html import escape

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "rmu-graphic-processing-report.csv"
    html_path = output_dir / "rmu-graphic-processing-report.html"
    headers = [
        "File", "Action", "RMURectCount", "GroupedCount", "UngroupedCount",
        "SmartMatched", "SmartChanged", "SmrTextCount", "SmrMatched", "SmrChanged",
        "RMUNameWhiteMatched", "RMUNameWhiteChanged",
        "ChannelStatusFound", "ChannelStatusMoved", "BusFrameRemoved", "TitleMoved", "Warnings",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([report_text(row.get(h, "")) for h in headers])

    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(report_text(row.get(h, '')))}</td>" for h in headers)
        body.append("<tr>" + selection_cell() + cells + "</tr>")
    english = report_is_english()
    report_title = "RMU Graphic Processing Report" if english else "环网柜图元处理报告"
    report_note = (
        "This report records the RMU graphic operations enabled for this run; running again replaces the previous report of the same type."
        if english else "本报告记录本次启用的环网柜图元操作；再次执行会覆盖上一份同类报告。"
    )
    html_path.write_text(
        f"<!doctype html><html lang='{"en" if english else "zh-CN"}'><head><meta charset='utf-8'><title>{report_title}</title>"
        "<style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1f2937}"
        "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left}"
        "th{background:#e8f3ef;position:sticky;top:0}" + selection_style() + "</style></head><body>"
        + f"<h2>{report_title}</h2><p>{report_note}</p>"
        + selection_bar() + "<table><thead><tr>" + selection_header()
        + "".join(f"<th>{escape(h)}</th>" for h in headers)
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        + selection_script() + "</body></html>",
        encoding="utf-8",
    )
    return csv_path, html_path


def _write_rmu_summary_reports(
    output_dir: Path, rows: list[GraphicRmuRow], *, intelligent_classification_enabled: bool = True
) -> tuple[Path, Path]:
    """Write one aggregate fixed RMU information summary report for the latest run."""
    from html import escape

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "rmu-summary-report.csv"
    html_path = output_dir / "rmu-summary-report.html"
    headers = [
        "File", "RMUName", "RMUType", "IntelligentRMU", "IntelligentSource",
        "Confidence", "Duplicate", "RectID", "RectX", "RectY", "RectW", "RectH", "Warnings",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([
                row.file_name, row.name, row.rmu_type, row.intelligent, row.intelligent_source,
                report_text(row.confidence), row.duplicate, row.rect_id, row.rect_x, row.rect_y, row.rect_w, row.rect_h, report_text(row.warnings),
            ])

    def row_class(row: GraphicRmuRow) -> str:
        if row.duplicate == "YES" or not row.name or not row.rmu_type:
            return "bad"
        if row.confidence not in {"高", "HIGH", "High"}:
            return "warn"
        return "good"

    body = []
    for row in rows:
        vals = [
            row.file_name, row.name, row.rmu_type, row.intelligent, row.intelligent_source,
            report_text(row.confidence), row.duplicate, row.rect_id, row.rect_x, row.rect_y, row.rect_w, row.rect_h, report_text(row.warnings),
        ]
        body.append(
            f"<tr class='{row_class(row)}'>" + selection_cell()
            + "".join(f"<td>{escape(str(v))}</td>" for v in vals) + "</tr>"
        )
    total = len(rows)
    duplicates = sum(1 for row in rows if row.duplicate == "YES")
    intelligent = sum(1 for row in rows if row.intelligent == "YES")
    ordinary = sum(1 for row in rows if row.intelligent == "NO") if intelligent_classification_enabled else 0
    unnamed = sum(1 for row in rows if not row.name)
    untyped = sum(1 for row in rows if not row.rmu_type or row.rmu_type == "0L0T")
    warning_rows = sum(1 for row in rows if row.confidence not in {"高", "HIGH", "High"} and row.name and row.rmu_type and row.duplicate != "YES")
    english = report_is_english()
    report_title = "RMU Summary Report" if english else "RMU 信息汇总报告"
    if english:
        summary_html = (
            f"<div class='summary'><div class='badge'>Total RMUs: <b>{total}</b></div>"
            + (f"<div class='badge'>Smart RMUs: <b>{intelligent}</b></div><div class='badge'>Normal RMUs: <b>{ordinary}</b></div>" if intelligent_classification_enabled else "<div class='badge'>Smart Classification: <b>Disabled</b></div>")
            + f"<div class='badge'>Duplicate Name/ID Rows: <b>{duplicates}</b></div>"
            + f"<div class='badge'>Unrecognized Names: <b>{unnamed}</b></div>"
            + f"<div class='badge'>Unrecognized Cabinet Types: <b>{untyped}</b></div>"
            + f"<div class='badge'>Medium/Low Confidence Pending Review: <b>{warning_rows}</b></div></div>"
        )
        legend = "Green = complete with high confidence; yellow = review required; red = duplicate or unrecognized name/cabinet type."
    else:
        summary_html = (
            f"<div class='summary'><div class='badge'>RMU 总数：<b>{total}</b></div>"
            + (f"<div class='badge'>智能环网柜：<b>{intelligent}</b></div><div class='badge'>普通环网柜：<b>{ordinary}</b></div>" if intelligent_classification_enabled else "<div class='badge'>智能分类：<b>未启用</b></div>")
            + f"<div class='badge'>重复名称/ID 行：<b>{duplicates}</b></div>"
            + f"<div class='badge'>名称未识别：<b>{unnamed}</b></div>"
            + f"<div class='badge'>柜型未识别：<b>{untyped}</b></div>"
            + f"<div class='badge'>中/低置信度待确认：<b>{warning_rows}</b></div></div>"
        )
        legend = "绿色=高置信度且完整；黄色=需要确认；红色=重复、名称/柜型未识别。"
    html_path.write_text(
        f"<!doctype html><html lang='{"en" if english else "zh-CN"}'><head><meta charset='utf-8'><title>{report_title}</title>"
        "<style>body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1f2937}"
        ".summary{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.badge{padding:7px 10px;border:1px solid #cbd5e1;border-radius:6px}"
        "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d1d5db;padding:6px 8px;text-align:left}"
        "th{background:#e8f3ef;position:sticky;top:0}tr.good td{background:#dcfce7}tr.warn td{background:#fef9c3}tr.bad td{background:#fee2e2}"
        + selection_style() + f"</style></head><body><h2>{report_title}</h2>"
        + summary_html + f"<p>{legend}</p>"
        + selection_bar() + "<table><thead><tr>" + selection_header()
        + "".join(f"<th>{escape(h)}</th>" for h in headers)
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        + selection_script() + "</body></html>",
        encoding="utf-8",
    )
    return csv_path, html_path



def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _iter_graph_elements(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if element is not root:
            yield element


def _collect_subtree_ids(element: ET.Element) -> set[str]:
    result: set[str] = set()
    for current in element.iter():
        value = (current.get("id") or "").strip()
        if value:
            result.add(value)
    return result


def _remove_reference_groups(value: str, removed_ids: set[str]) -> tuple[str, int]:
    if not value or not removed_ids:
        return value, 0

    kept: list[str] = []
    removed_count = 0
    for group in value.split(";"):
        parts = group.split(",", 2)
        if len(parts) >= 3 and parts[2].strip() in removed_ids:
            removed_count += 1
            continue
        kept.append(group)
    return ";".join(kept), removed_count


def _clean_removed_references(layer: ET.Element, removed_ids: set[str]) -> tuple[int, int]:
    if not removed_ids:
        return 0, 0

    remaining_ids = {
        value
        for element in layer.iter()
        if (value := (element.get("id") or "").strip())
    }
    truly_removed_ids = removed_ids - remaining_ids
    if not truly_removed_ids:
        return 0, 0

    removed_groups = 0
    cleared_single = 0
    for element in _iter_graph_elements(layer):
        for attribute in REFERENCE_LIST_ATTRIBUTES:
            value = element.get(attribute)
            if value is None:
                continue
            new_value, count = _remove_reference_groups(value, truly_removed_ids)
            if count:
                element.set(attribute, new_value)
                removed_groups += count

        for attribute in REFERENCE_SINGLE_ATTRIBUTES:
            value = (element.get(attribute) or "").strip()
            if value and value in truly_removed_ids:
                element.set(attribute, "")
                cleared_single += 1

    return removed_groups, cleared_single


def _validate_rules(settings: BasicSettings) -> None:
    if settings.replace_attribute:
        if not settings.replace_target_tag.strip():
            raise ValueError("启用‘替换元素属性值’后，元素标签不能为空。")
        if not settings.replace_target_attribute.strip():
            raise ValueError("启用‘替换元素属性值’后，属性名不能为空。")

    if settings.delete_attribute:
        if not settings.delete_attribute_target_tag.strip():
            raise ValueError("启用‘删除元素属性’后，元素标签不能为空。")
        if not settings.delete_attribute_name.strip():
            raise ValueError("启用‘删除元素属性’后，要删除的属性名不能为空。")

    if settings.delete_matching_element:
        if not settings.delete_target_tag.strip():
            raise ValueError("启用‘删除匹配元素’后，元素标签不能为空。")
        if not settings.delete_target_attribute.strip():
            raise ValueError("启用‘删除匹配元素’后，属性名不能为空。")

    rmu_name_mode = (settings.rmu_name_resolution_mode or "selected_direction").strip().lower()
    if rmu_name_mode not in {"selected_direction", "auto_cluster"}:
        raise ValueError(f"未知 RMU 柜名识别模式：{settings.rmu_name_resolution_mode}")
    # The shared RMU recognizer enforces the validated-frame + top-name rule.
    # Keep accepting the legacy mode value for settings compatibility, but do not
    # reject a run because obsolete direction checkboxes are empty.

    if settings.compare_rmu_ledger and not settings.identify_rmu_name_and_type:
        raise ValueError("启用 RMU 台账对比前，必须先启用 RMU 信息汇总。")
    if settings.compare_rmu_ledger:
        if settings.rmu_ledger_input_mode == RmuLedgerInputMode.FILE:
            if settings.rmu_ledger_file is None:
                raise ValueError("请选择 RMU 台账 Excel/CSV 文件。")
        elif not settings.rmu_ledger_text.strip():
            raise ValueError("RMU 台账输入内容不能为空。")

    if settings.upgrade_icon_geometry:
        analysis = (
            analyze_icon_mappings(settings.icon_upgrade_pairs)
            if settings.icon_upgrade_pairs
            else analyze_icon_pairs(settings.old_icon_files, settings.new_icon_files)
        )
        problems: list[str] = []
        if analysis.missing_old:
            problems.append("缺少旧图元：" + ", ".join(analysis.missing_old))
        if analysis.missing_new:
            problems.append("缺少新图元：" + ", ".join(analysis.missing_new))
        if analysis.incompatible:
            problems.append("不兼容图元：" + " | ".join(analysis.incompatible))
        if not analysis.rules:
            problems.append("没有可用的旧/新图元配对。")
        if problems:
            raise ValueError("同类图元版本升级检查未通过：" + "；".join(problems))


def _write_smr_frame_reports(output_dir: Path, rows: list[dict[str, object]]) -> tuple[Path, Path]:
    from html import escape
    csv_path = output_dir / "rmu-smr-frame-report.csv"
    html_path = output_dir / "rmu-smr-frame-report.html"
    headers = ["File","SMRTextID","SMRX","SMRY","RectID","RectX","RectY","RectW","RectH","Distance","OldColor","NewColor","Result"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(headers)
        for row in rows:
            writer.writerow([report_text(row.get(h, "")) for h in headers])
    trs=[]
    for row in rows:
        cells="".join("<td>%s</td>" % escape(report_text(row.get(h,""))) for h in headers)
        trs.append("<tr>%s%s</tr>" % (selection_cell(), cells))
    english = report_is_english()
    report_title = "RMU SMR Frame Processing Report" if english else "RMU SMR 外框处理报告"
    report_note = "This report replaces the previous report of the same type on each run." if english else "本报告每次执行覆盖上一份同类报告。"
    html = (f"<!doctype html><html lang='{"en" if english else "zh-CN"}'><head><meta charset='utf-8'><title>{report_title}</title><style>" + selection_style() + "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #cbd5e1;padding:6px 8px;text-align:left}</style></head><body>" + f"<h2>{report_title}</h2><p>{report_note}</p>" + selection_bar() + "<table><thead><tr>" + selection_header() + "".join("<th>%s</th>" % escape(h) for h in headers) + "</tr></thead><tbody>" + "".join(trs) + "</tbody></table>" + selection_script() + "</body></html>")
    html_path.write_text(html, encoding="utf-8")
    return csv_path, html_path


def _process_layer(
    layer: ET.Element,
    settings: BasicSettings,
) -> tuple[int, int, int, set[str]]:
    """只处理 Layer 的直接子元素。"""
    replaced = 0
    deleted_attributes = 0
    removed_matching = 0
    removed_ids: set[str] = set()

    replace_tag = settings.replace_target_tag.strip()
    replace_attribute = settings.replace_target_attribute.strip()
    delete_attr_tag = settings.delete_attribute_target_tag.strip()
    delete_attr_name = settings.delete_attribute_name.strip()
    delete_tag = settings.delete_target_tag.strip()
    delete_attribute = settings.delete_target_attribute.strip()

    for element in list(layer):
        tag = _local_name(element.tag)

        if (
            settings.delete_attribute
            and tag == delete_attr_tag
            and delete_attr_name in element.attrib
        ):
            del element.attrib[delete_attr_name]
            deleted_attributes += 1

        if (
            settings.delete_matching_element
            and tag == delete_tag
            and element.get(delete_attribute) == settings.delete_target_value
        ):
            removed_ids.update(_collect_subtree_ids(element))
            layer.remove(element)
            removed_matching += 1
            continue

        if (
            settings.replace_attribute
            and tag == replace_tag
            and element.get(replace_attribute) == settings.replace_old_value
        ):
            element.set(replace_attribute, settings.replace_new_value)
            replaced += 1

    return replaced, deleted_attributes, removed_matching, removed_ids


def _effective_rmu_action(settings: BasicSettings) -> RmuAction:
    if settings.rmu_action != RmuAction.NONE:
        return settings.rmu_action
    if settings.group_rmu_elements:
        return RmuAction.GROUP
    return RmuAction.NONE


def _color_rules(settings: BasicSettings) -> list[ColorRule]:
    """构造线路/母线样式规则。颜色和线型可独立启用。"""
    rules: list[ColorRule] = []
    candidates = [
        ("FeedLine", "馈线", settings.feedline_color, settings.feedline_line_style, settings.change_feedline_color),
        ("ConnectLine", "连接线", settings.connectline_color, settings.connectline_line_style, settings.change_connectline_color),
        ("BusDis", "配网母线", settings.busdis_color, settings.busdis_line_style, settings.change_busdis_color),
        ("Bus", "主网母线", settings.bus_color, settings.bus_line_style, settings.change_bus_color),
    ]
    for tag, label, color, line_style, change_color in candidates:
        if change_color or line_style != "keep":
            rules.append(ColorRule(tag, label, color, line_style=line_style, change_color=change_color))
    return rules


def _output_path_for(
    input_path: Path,
    settings: BasicSettings,
    timestamp: str,
) -> Path:
    # 一对一处理统一保留源 G 文件名。每次运行使用独立 workspace 目录，
    # 因此不再通过时间戳修改 G 文件名。
    return settings.output_dir / input_path.name


def _rmu_duplicate_names(identification) -> tuple[dict[str, int], set[str]]:
    counts: dict[str, int] = {}
    for item in identification.items:
        name = (item.name or "").strip()
        if not name:
            continue
        key = name.casefold()
        counts[key] = counts.get(key, 0) + 1
    duplicates = {key for key, count in counts.items() if count > 1}
    return counts, duplicates


def _write_rmu_csv(output_path: Path, identification) -> Path:
    stem, _suffix = strip_g_suffix(output_path.name)
    csv_path = output_path.with_name(f"{stem}.rmu.csv")
    _counts, duplicates = _rmu_duplicate_names(identification)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "CabinetName", "CabinetType", "TypeSource", "TextYQType", "DevrefType",
            "TypeCrossCheck", "TypeValidationStatus", "TypeCrossNote",
            "LCount", "TCount", "IntelligentRMU", "IntelligentSource",
            "NamePosition", "Confidence", "Duplicate", "RectID",
            "RectX", "RectY", "RectW", "RectH", "Warnings",
        ])
        for item in identification.items:
            name_key = (item.name or "").strip().casefold()
            duplicate = "YES" if name_key and name_key in duplicates else "NO"
            writer.writerow([
                item.name, item.rmu_type, getattr(item, "type_source", ""), getattr(item, "text_yq_type", ""),
                getattr(item, "devref_type", ""), getattr(item, "type_cross_check", "N/A"),
                getattr(item, "type_validation_status", "WARN"), report_text(getattr(item, "type_cross_note", "")),
                item.l_count, item.t_count, item.smart_count, getattr(item, "smart_source", ""),
                item.name_position, report_text(item.confidence), duplicate, item.rect_id,
                f"{item.rect_x:g}", f"{item.rect_y:g}", f"{item.rect_w:g}", f"{item.rect_h:g}",
                report_text(" | ".join(item.warnings)),
            ])
    return csv_path


def _write_rmu_html(output_path: Path, identification) -> Path:
    from html import escape

    stem, _suffix = strip_g_suffix(output_path.name)
    html_path = output_path.with_name(f"{stem}.rmu.html")
    counts, duplicates = _rmu_duplicate_names(identification)

    high_count = sum(
        1 for item in identification.items
        if item.confidence == "高" and (item.name or "").strip().casefold() not in duplicates
    )
    medium_count = sum(
        1 for item in identification.items
        if item.confidence in {"中", "待确认"} and (item.name or "").strip().casefold() not in duplicates
    )
    unidentified_count = sum(
        1 for item in identification.items if not item.name or item.confidence == "未识别"
    )
    duplicate_row_count = sum(
        1 for item in identification.items
        if (item.name or "").strip() and (item.name or "").strip().casefold() in duplicates
    )
    type_pass_count = sum(1 for item in identification.items if getattr(item, "type_validation_status", "") == "PASS")
    type_warn_count = sum(1 for item in identification.items if getattr(item, "type_validation_status", "") == "WARN")
    type_fail_count = sum(1 for item in identification.items if getattr(item, "type_validation_status", "") == "FAIL")

    def row_class(item) -> str:
        key = (item.name or "").strip().casefold()
        type_status = getattr(item, "type_validation_status", "WARN")
        if (key and key in duplicates) or not item.name or item.confidence == "未识别" or type_status == "FAIL":
            return "bad"
        if type_status == "WARN" or item.confidence in {"中", "待确认"}:
            return "medium"
        if item.confidence == "高":
            return "high"
        return "medium"

    english = report_is_english()
    headers = ([
        "RMU Name", "RMU Type", "Type Source", "Y/Q Text Type", "devref Type",
        "Type Cross-Check", "Type Validation Status", "Type Cross-Check Note",
        "L Count", "T Count", "Smart RMU", "Smart Source",
        "Name Position", "Confidence", "Duplicate", "RectID",
        "RectX", "RectY", "RectW", "RectH", "Warnings",
    ] if english else [
        "环网柜名称", "环网柜类型", "类型识别来源", "柜内Y/Q文字类型", "devref类型",
        "类型交叉校验", "柜型校验状态", "柜型交叉校验说明",
        "L数量", "T数量", "智能环网柜", "智能标识来源",
        "柜名位置", "识别置信度", "是否重复", "RectID",
        "RectX", "RectY", "RectW", "RectH", "Warnings",
    ])
    rows: list[str] = []
    for item in identification.items:
        key = (item.name or "").strip().casefold()
        duplicate = "YES" if key and key in duplicates else "NO"
        values = [
            item.name, item.rmu_type, getattr(item, "type_source", ""), getattr(item, "text_yq_type", ""),
            getattr(item, "devref_type", ""), getattr(item, "type_cross_check", "N/A"),
            getattr(item, "type_validation_status", "WARN"), report_text(getattr(item, "type_cross_note", "")),
            str(item.l_count), str(item.t_count), str(item.smart_count), getattr(item, "smart_source", ""),
            item.name_position, report_text(item.confidence), duplicate, item.rect_id,
            f"{item.rect_x:g}", f"{item.rect_y:g}", f"{item.rect_w:g}", f"{item.rect_h:g}",
            report_text(" | ".join(item.warnings)),
        ]
        cells = "".join(f"<td>{escape(value)}</td>" for value in values)
        rows.append(f'<tr class="{row_class(item)}">{selection_cell()}{cells}</tr>')

    duplicate_list: list[str] = []
    for key in sorted(duplicates):
        display_name = next(
            (item.name for item in identification.items if (item.name or "").strip().casefold() == key),
            key,
        )
        duplicate_list.append(f"{escape(display_name)} × {counts[key]}")
    duplicate_text = ((", ".join(duplicate_list) if duplicate_list else "None") if english else ("、".join(duplicate_list) if duplicate_list else "无"))

    header_cells = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_rows = "".join(rows)
    if english:
        report_title = f"{stem} RMU Identification Report"
        report_heading = "RMU Identification Report"
        report_summary = (
            f'<div class="summary"><div class="badge">Total RMUs: <b>{len(identification.items)}</b></div>'
            f'<div class="badge">Names Identified: <b>{identification.named_count}</b></div>'
            f'<div class="badge">Types Identified: <b>{identification.typed_count}</b></div>'
            f'<div class="badge">High Confidence: <b>{high_count}</b></div>'
            f'<div class="badge">Medium/Pending: <b>{medium_count}</b></div>'
            f'<div class="badge">Unrecognized: <b>{unidentified_count}</b></div>'
            f'<div class="badge">Duplicate RMU Names/IDs: <b>{len(duplicates)}</b> ({duplicate_row_count} rows)</div></div>'
        )
        report_note = f"Colors: green = high confidence; yellow = medium/pending review; red = unrecognized or duplicate RMU name/ID. Duplicates: {duplicate_text}"
    else:
        report_title = f"{stem} RMU 信息汇总报告"
        report_heading = "RMU 信息汇总报告"
        report_summary = (
            f'<div class="summary"><div class="badge">总环网柜：<b>{len(identification.items)}</b></div>'
            f'<div class="badge">柜名成功：<b>{identification.named_count}</b></div>'
            f'<div class="badge">柜型成功：<b>{identification.typed_count}</b></div>'
            f'<div class="badge">高置信度：<b>{high_count}</b></div>'
            f'<div class="badge">中/待确认：<b>{medium_count}</b></div>'
            f'<div class="badge">未识别：<b>{unidentified_count}</b></div>'
            f'<div class="badge">重复柜名/ID：<b>{len(duplicates)}</b> 个（涉及 {duplicate_row_count} 行）</div></div>'
        )
        report_note = f"颜色：绿色=高置信度；黄色=中等/待确认；红色=未识别或柜名/环网柜 ID 重复。重复项：{duplicate_text}"
    html = f"""<!DOCTYPE html>
<html lang="{'en' if english else 'zh-CN'}">
<head>
<meta charset="utf-8">
<title>{escape(report_title)}</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ margin: 0 0 16px; font-size: 24px; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }}
.badge {{ border: 1px solid #d1d5db; border-radius: 6px; padding: 7px 10px; background: #f8fafc; }}
.note {{ margin: 10px 0 18px; color: #475569; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; vertical-align: top; }}
th {{ background: #e2e8f0; position: sticky; top: 0; }}
tr.high td {{ background: #dcfce7; }}
tr.medium td {{ background: #fef9c3; }}
tr.bad td {{ background: #fee2e2; }}
{selection_style()}
</style>
</head>
<body>
<h1>{report_heading}</h1>
{report_summary}
<div class="note">{report_note}</div>
{selection_bar()}
<table>
<thead><tr>{selection_header()}{header_cells}</tr></thead>
<tbody>{body_rows}</tbody>
</table>
{selection_script()}
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")
    return html_path

def process_basic(
    settings: BasicSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
    *,
    database_service: Any | None = None,
) -> ProcessingResult:
    """统一执行基础处理页面选择的全部操作。"""
    _validate_rules(settings)

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    timestamp = settings.task_timestamp.strip() or make_task_timestamp()
    rmu_action = _effective_rmu_action(settings)
    color_rules = _color_rules(settings)
    icon_analysis = (
        (
            analyze_icon_mappings(settings.icon_upgrade_pairs)
            if settings.icon_upgrade_pairs
            else analyze_icon_pairs(settings.old_icon_files, settings.new_icon_files)
        )
        if settings.upgrade_icon_geometry
        else None
    )
    icon_rules = icon_analysis.rules if icon_analysis is not None else {}
    if settings.upgrade_icon_geometry:
        log(f"[同类图元版本升级] 已加载并验证 {len(icon_rules)} 种旧/新图元配对。")
        for name, rule in sorted(icon_rules.items()):
            log(
                f"  - {rule.old.file_name} → {rule.new.file_name}："
                f"{rule.old.width:g}×{rule.old.height:g} → {rule.new.width:g}×{rule.new.height:g}；AlignCenter "
                f"{rule.old.align_center} → {rule.new.align_center}；Pins "
                f"{len(rule.old.pins)} → {len(rule.new.pins)}。"
            )

    outputs: list[Path] = []
    failed: list[str] = []
    total_replaced = 0
    total_deleted_attributes = 0
    total_removed_matching = 0
    total_removed_reference_groups = 0
    total_cleared_single_references = 0
    total_rects = 0
    total_rmu_groups = 0
    total_rmu_members = 0
    total_rmu_ungrouped = 0
    total_rmu_released_members = 0
    total_rmu_lowered_rects = 0
    total_graphic_merges_removed = 0
    total_graphic_merge_cleanup_rmu_rects = 0
    total_graphic_merge_cleanup_lowered_rects = 0
    total_color_changed = 0
    total_dynamic_colors = 0
    total_smart_rmu_rects = 0
    total_smart_rmu_frames_changed = 0
    total_smr_texts = 0
    total_smr_matched_rects = 0
    total_smr_frames_changed = 0
    total_rmu_name_white_matched = 0
    total_rmu_name_white_changed = 0
    total_smart_rmu_poke_candidates = 0
    total_smart_rmu_poke_added = 0
    total_smart_rmu_poke_updated = 0
    total_smart_rmu_poke_unchanged = 0
    total_smart_rmu_poke_skipped = 0
    smr_report_rows: list[dict[str, object]] = []
    total_channel_status_rects = 0
    total_channel_status_found = 0
    total_channel_status_moved = 0
    total_channel_status_missing = 0
    total_bus_rect_removed = 0
    total_bus_title_moved = 0
    total_connection_aligned_devices = 0
    total_connection_adjusted_lines = 0
    total_connection_relations = 0
    total_connection_added = 0
    total_connection_updated = 0
    total_connection_removed = 0
    total_connection_changed_elements = 0
    total_connection_changed_attributes = 0
    total_icon_upgraded_instances = 0
    total_icon_adjusted_lines = 0
    total_icon_already_new = 0
    total_icon_skipped_unknown_size = 0
    total_rmu_identified = 0
    total_rmu_named = 0
    total_rmu_typed = 0
    total_rmu_ambiguous = 0
    total_rmu_csv = 0
    rmu_graphic_rows: list[GraphicRmuRow] = []
    rmu_processing_rows: list[dict[str, object]] = []
    ledger_rows = []
    if settings.compare_rmu_ledger:
        if settings.rmu_ledger_input_mode == RmuLedgerInputMode.FILE:
            ledger_rows = load_ledger_file(settings.rmu_ledger_file)
        elif settings.rmu_ledger_input_mode == RmuLedgerInputMode.PASTE_TABLE:
            ledger_rows = parse_pasted_table(settings.rmu_ledger_text)
        else:
            ledger_rows = parse_name_list(settings.rmu_ledger_text)
        if not ledger_rows:
            raise ValueError("RMU 台账没有解析到任何有效名称。")
        log(f"[RMU台账] 已读取 {len(ledger_rows)} 条台账记录，输入方式：{settings.rmu_ledger_input_mode.value}。")

    if settings.output_conflict_action == BasicOutputConflictAction.TIMESTAMP:
        log(f"[输出策略] 检测到输出冲突，本批文件统一自动添加时间戳 {timestamp}。")
    else:
        log("[输出策略] 使用原文件名；如目标已存在，将通过临时文件验证后安全覆盖。")

    for index, input_path in enumerate(files, 1):
        try:
            output_path = _output_path_for(input_path, settings, timestamp)
            tree = ET.parse(input_path)
            root = tree.getroot()

            replaced = 0
            deleted_attributes = 0
            removed_matching = 0
            removed_reference_groups = 0
            cleared_single_references = 0

            layers = [child for child in list(root) if _local_name(child.tag) == "Layer"]
            if not layers:
                raise ValueError(f"文件 {input_path.name} 的 G 根节点下没有直属 Layer。")

            rmu_identification = None
            if settings.identify_rmu_name_and_type:
                positions = tuple(
                    key for key, enabled in (
                        ("top", settings.rmu_name_top),
                        ("bottom", settings.rmu_name_bottom),
                        ("left", settings.rmu_name_left),
                        ("right", settings.rmu_name_right),
                    ) if enabled
                )
                rmu_identification = identify_rmus(
                    tree,
                    input_path,
                    name_positions=positions,
                    smart_in_type=settings.rmu_smart_in_type,
                    excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                    intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                    name_resolution_mode=settings.rmu_name_resolution_mode,
                )
                total_rmu_identified += rmu_identification.cabinet_count
                total_rmu_named += rmu_identification.named_count
                total_rmu_typed += rmu_identification.typed_count
                total_rmu_ambiguous += rmu_identification.ambiguous_name_count
                log(
                    f"[环网柜识别] {input_path.name}：识别环网柜 {rmu_identification.cabinet_count} 个，"
                    f"柜名 {rmu_identification.named_count} 个，柜型 {rmu_identification.typed_count} 个，"
                    f"待确认柜名 {rmu_identification.ambiguous_name_count} 个。"
                )
                for item in rmu_identification.items:
                    name = item.name or "<未识别>"
                    position_label = {
                        "top": "上方", "bottom": "下方", "left": "左侧", "right": "右侧",
                        "BusDis.key_name+Text": "BusDis.key_name + Text 确认回退",
                    }.get(item.name_position, item.name_position or "-")
                    log(
                        f"  - rect {item.rect_id or '<无ID>'}：柜名 {name}（{position_label}），"
                        f"类型 {item.rmu_type}，L={item.l_count}，T={item.t_count}，智能={item.smart_count}（{item.smart_source or "-"}），"
                        f"置信度 {item.confidence}。"
                    )
                if settings.identify_rmu_name_and_type:
                    _, duplicate_names = _rmu_duplicate_names(rmu_identification)
                    for item in rmu_identification.items:
                        name_key = (item.name or "").strip().casefold()
                        rmu_graphic_rows.append(GraphicRmuRow(
                            file_name=input_path.name,
                            name=(item.name or "").strip(),
                            rmu_type=(item.rmu_type or "").strip(),
                            intelligent=("YES" if bool(item.smart_count) else "NO") if settings.rmu_smart_in_type else "",
                            intelligent_source=(getattr(item, "smart_source", "") or "") if settings.rmu_smart_in_type else "",
                            confidence=item.confidence or "",
                            duplicate="YES" if name_key and name_key in duplicate_names else "NO",
                            rect_id=item.rect_id or "",
                            rect_x=f"{item.rect_x:g}", rect_y=f"{item.rect_y:g}",
                            rect_w=f"{item.rect_w:g}", rect_h=f"{item.rect_h:g}",
                            warnings=" | ".join(item.warnings),
                        ))
                for warning in rmu_identification.warnings:
                    log(f"[环网柜识别告警] {input_path.name}：{warning}")

            # SMART RMU Poke uses exactly the same RMU identification engine as the
            # summary module.  It is intentionally identified BEFORE grouping,
            # because grouping moves cabinet devices under <Merge>.
            poke_identification = None
            if settings.add_smart_rmu_poke:
                positions = tuple(
                    key for key, enabled in (
                        ("top", settings.rmu_name_top),
                        ("bottom", settings.rmu_name_bottom),
                        ("left", settings.rmu_name_left),
                        ("right", settings.rmu_name_right),
                    ) if enabled
                )
                if rmu_identification is not None and settings.rmu_smart_in_type:
                    poke_identification = rmu_identification
                else:
                    poke_identification = identify_rmus(
                        tree,
                        input_path,
                        name_positions=positions,
                        smart_in_type=True,
                        excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                        intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                        name_resolution_mode=settings.rmu_name_resolution_mode,
                    )
                poke_smart_count = sum(1 for item in poke_identification.items if item.smart_count)
                log(
                    f"[智能RMU Poke识别] {input_path.name}：完全复用 RMU 信息汇总识别器，"
                    f"识别 RMU {poke_identification.cabinet_count} 个，其中智能 RMU {poke_smart_count} 个。"
                )

            for layer in layers:
                one_replaced, one_deleted_attributes, one_removed, one_removed_ids = _process_layer(layer, settings)
                replaced += one_replaced
                deleted_attributes += one_deleted_attributes
                removed_matching += one_removed

                groups, singles = _clean_removed_references(layer, one_removed_ids)
                removed_reference_groups += groups
                cleared_single_references += singles

            if settings.upgrade_icon_geometry:
                icon_result = apply_icon_upgrade(tree, icon_rules)
                total_icon_upgraded_instances += icon_result.upgraded_instances
                total_icon_adjusted_lines += icon_result.adjusted_lines
                total_icon_already_new += icon_result.already_new_instances
                total_icon_skipped_unknown_size += icon_result.skipped_unknown_size
                log(
                    f"[同类图元版本升级] {input_path.name}：升级实例 "
                    f"{icon_result.upgraded_instances} 个，调整连接线 "
                    f"{icon_result.adjusted_lines} 条；已是新尺寸 "
                    f"{icon_result.already_new_instances} 个，未知尺寸跳过 "
                    f"{icon_result.skipped_unknown_size} 个。"
                )
                if icon_result.changed_instance_ids:
                    log("  - 升级图元 ID：" + ", ".join(icon_result.changed_instance_ids))
                for warning in icon_result.warnings:
                    log(f"[同类图元版本升级告警] {input_path.name}：{warning}")

            if settings.remove_all_graphic_merges:
                cleanup_identification = identify_rmus(
                    tree,
                    input_path,
                    name_positions=("top",),
                    smart_in_type=True,
                    excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                    intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                    name_resolution_mode=settings.rmu_name_resolution_mode,
                )
                cleanup_rmu_rect_ids = {
                    item.rect_id for item in cleanup_identification.items if item.rect_id
                }
                cleanup = remove_all_graphic_merges(
                    tree,
                    input_path,
                    lower_rmu_rects=settings.lower_rmu_rects_after_merge_cleanup,
                    rmu_rect_ids=cleanup_rmu_rect_ids,
                )
                total_graphic_merges_removed += cleanup.removed_merge_count
                total_graphic_merge_cleanup_rmu_rects += cleanup.rmu_rect_count
                total_graphic_merge_cleanup_lowered_rects += cleanup.lowered_rect_count
                log(
                    f"[图形组合清理] {input_path.name}：原 Merge {cleanup.previous_merge_count} 个，"
                    f"删除 {cleanup.removed_merge_count} 个，处理后剩余 {cleanup.remaining_merge_count} 个；"
                    f"识别 RMU 外框 {cleanup.rmu_rect_count} 个，置底 {cleanup.lowered_rect_count} 个。"
                )
                if cleanup.lowered_rect_count:
                    log("  - RMU 外框仅调整 XML 元素顺序；坐标、ID、keyid、devref、tfr 和其他业务属性均未修改。")

            rmu_processing_row = {
                "File": input_path.name,
                "Action": rmu_action.value,
                "RMURectCount": 0,
                "GroupedCount": 0,
                "UngroupedCount": 0,
                "SmartMatched": 0,
                "SmartChanged": 0,
                "SmrTextCount": 0,
                "SmrMatched": 0,
                "SmrChanged": 0,
                "RMUNameWhiteMatched": 0,
                "RMUNameWhiteChanged": 0,
                "ChannelStatusFound": 0,
                "ChannelStatusMoved": 0,
                "BusFrameRemoved": 0,
                "TitleMoved": 0,
                "Warnings": "",
            }
            rmu_processing_warnings: list[str] = []

            # v2.18.59: 独立“环网柜处理 -> 组合所有环网柜”不再自行判断哪些 rect 是 RMU。
            # 直接复用“RMU 信息汇总”的 identify_rmus() 结果作为唯一柜体集合。
            # 即使用户没有勾选“启用 RMU 信息汇总”，组合动作也会在内存中执行一次只读识别；
            # 不额外生成汇总报告，也不改变信息汇总本身的开关语义。
            grouping_rmu_rect_ids: set[str] | None = None
            if rmu_action == RmuAction.GROUP:
                grouping_identification = rmu_identification or poke_identification
                if grouping_identification is None:
                    grouping_positions = tuple(
                        key for key, enabled in (
                            ("top", settings.rmu_name_top),
                            ("bottom", settings.rmu_name_bottom),
                            ("left", settings.rmu_name_left),
                            ("right", settings.rmu_name_right),
                        ) if enabled
                    ) or ("top",)
                    grouping_identification = identify_rmus(
                        tree,
                        input_path,
                        name_positions=grouping_positions,
                        smart_in_type=settings.rmu_smart_in_type,
                        excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                        intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                        name_resolution_mode=settings.rmu_name_resolution_mode,
                    )
                grouping_rmu_rect_ids = {
                    item.rect_id
                    for item in grouping_identification.items
                    if item.rect_id
                }
                log(
                    f"[环网柜组合识别] {input_path.name}：直接复用 RMU 信息汇总识别器，"
                    f"确认 RMU {grouping_identification.cabinet_count} 个，可用于组合的 rect ID "
                    f"{len(grouping_rmu_rect_ids)} 个。"
                )
                if grouping_identification.cabinet_count and len(grouping_rmu_rect_ids) != grouping_identification.cabinet_count:
                    raise ValueError(
                        f"文件 {input_path.name} 的 RMU 信息汇总识别到 "
                        f"{grouping_identification.cabinet_count} 个柜体，但仅有 "
                        f"{len(grouping_rmu_rect_ids)} 个有效 rect ID；为避免误组合，已停止处理。"
                    )

            if rmu_action == RmuAction.GROUP:
                # 独立“环网柜处理”页面的安全重建模式：仅当当前文件确实已有
                # Layer 直属 Merge 时，先复用“彻底取消图形组合”能力删除全部旧 Merge，
                # 再根据当前图元几何重新组合。默认关闭，因此基础处理等其他调用不变。
                if settings.reset_existing_merges_before_rmu_group:
                    existing_merge_count = sum(
                        1
                        for layer in layers
                        for element in list(layer)
                        if _local_name(element.tag) == "Merge"
                    )
                    if existing_merge_count:
                        cleanup = remove_all_graphic_merges(
                            tree,
                            input_path,
                            lower_rmu_rects=True,
                            rmu_rect_ids=grouping_rmu_rect_ids,
                        )
                        total_graphic_merges_removed += cleanup.removed_merge_count
                        total_graphic_merge_cleanup_rmu_rects += cleanup.rmu_rect_count
                        total_graphic_merge_cleanup_lowered_rects += cleanup.lowered_rect_count
                        log(
                            f"[环网柜组合预清理] {input_path.name}：检测到旧 Merge "
                            f"{existing_merge_count} 个，已先彻底取消图形组合；删除 "
                            f"{cleanup.removed_merge_count} 个，剩余 {cleanup.remaining_merge_count} 个，"
                            f"RMU 外框置底 {cleanup.lowered_rect_count} 个。随后按当前图元重新组合。"
                        )

                grouping = group_rmu_tree(
                    tree,
                    input_path,
                    validated_rmu_only=False,
                    validated_rmu_rect_ids=grouping_rmu_rect_ids,
                )
                total_rects += grouping.rect_count
                total_rmu_groups += grouping.rebuilt_group_count
                total_rmu_members += grouping.grouped_member_count
                rmu_processing_row["RMURectCount"] = grouping.rect_count
                rmu_processing_row["GroupedCount"] = grouping.rebuilt_group_count
                rmu_processing_warnings.extend(grouping.warnings)
                log(
                    f"[环网柜组合] {input_path.name}：发现 <rect> {grouping.rect_count} 个，"
                    f"原环网柜 Merge {grouping.previous_rmu_merge_count} 个，保留其他业务 Merge "
                    f"{grouping.preserved_non_rmu_merge_count} 个，重建环网柜组合 "
                    f"{grouping.rebuilt_group_count} 个。"
                )
                for warning in grouping.warnings:
                    log(f"[环网柜组合告警] {warning}")
                for change in grouping.changes:
                    action_text = "复用原 Merge" if change.reused_existing_merge else "新建 Merge"
                    log(
                        f"  - rect ID {change.rect_id or '<无ID>'}：{action_text} "
                        f"ID {change.merge_id}，组合框内直属图元 {change.member_count} 个；"
                        "框外图元不组合。"
                    )
                if grouping.rect_count == 0:
                    log(f"[环网柜组合] {input_path.name}：未发现直属 <rect>，无需组合。")
            elif rmu_action == RmuAction.UNGROUP:
                ungroup_identification = rmu_identification or poke_identification
                if ungroup_identification is None:
                    ungroup_identification = identify_rmus(
                        tree,
                        input_path,
                        name_positions=("top",),
                        smart_in_type=True,
                        excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                        intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                        name_resolution_mode=settings.rmu_name_resolution_mode,
                    )
                ungroup_rmu_rect_ids = {
                    item.rect_id for item in ungroup_identification.items if item.rect_id
                }
                ungrouping = ungroup_rmu_tree(
                    tree,
                    input_path,
                    validated_rmu_rect_ids=ungroup_rmu_rect_ids,
                )
                total_rmu_ungrouped += ungrouping.removed_rmu_merge_count
                total_rmu_released_members += ungrouping.released_member_count
                total_rmu_lowered_rects += ungrouping.lowered_rect_count
                rmu_processing_row["UngroupedCount"] = ungrouping.removed_rmu_merge_count
                rmu_processing_warnings.extend(ungrouping.warnings)
                log(
                    f"[取消环网柜组合] {input_path.name}：删除环网柜 Merge "
                    f"{ungrouping.removed_rmu_merge_count} 个，释放成员 "
                    f"{ungrouping.released_member_count} 个，将环网柜外框下移到设备下层 "
                    f"{ungrouping.lowered_rect_count} 个，保留其他业务 Merge "
                    f"{ungrouping.preserved_non_rmu_merge_count} 个。"
                )
                for merge_id in ungrouping.removed_merge_ids:
                    log(f"  - 已删除环网柜 Merge ID {merge_id or '<无ID>'}。")
                for rect_id in ungrouping.lowered_rect_ids:
                    log(
                        f"  - rect ID {rect_id or '<无ID>'} 已移动到柜内设备之前；"
                        "仅调整图层顺序，坐标和业务属性不变。"
                    )
                for warning in ungrouping.warnings:
                    log(f"[取消环网柜组合告警] {warning}")

            if (
                settings.change_smart_rmu_frame_color
                or settings.change_smr_rmu_frame_color
                or settings.reposition_channel_status
                or settings.remove_bus_rmu_frame_and_reposition_title
            ):
                smart_frame_rmu_rect_ids: set[str] | None = None
                if settings.change_smart_rmu_frame_color:
                    # SMART frame coloring must use the same authoritative RMU
                    # recognition as RMU Summary instead of re-testing whether
                    # the whole SMART Text box is geometrically inside the rect.
                    smart_frame_identification = None
                    if poke_identification is not None:
                        smart_frame_identification = poke_identification
                    elif rmu_identification is not None and settings.rmu_smart_in_type:
                        smart_frame_identification = rmu_identification
                    else:
                        smart_positions = tuple(
                            key for key, enabled in (
                                ("top", settings.rmu_name_top),
                                ("bottom", settings.rmu_name_bottom),
                                ("left", settings.rmu_name_left),
                                ("right", settings.rmu_name_right),
                            ) if enabled
                        ) or ("top",)
                        smart_frame_identification = identify_rmus(
                            tree,
                            input_path,
                            name_positions=smart_positions,
                            smart_in_type=True,
                            excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                            intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                            name_resolution_mode=settings.rmu_name_resolution_mode,
                        )
                    smart_frame_rmu_rect_ids = {
                        item.rect_id
                        for item in smart_frame_identification.items
                        if item.rect_id and bool(item.smart_count)
                    }
                    log(
                        f"[智能环网柜外框识别] {input_path.name}：复用 RMU 信息汇总识别结果，"
                        f"确认智能 RMU {len(smart_frame_rmu_rect_ids)} 个。"
                    )

                validated_rmu_rect_ids: set[str] | None = None
                validated_identification = rmu_identification or poke_identification
                if validated_identification is None:
                    validated_identification = identify_rmus(
                        tree,
                        input_path,
                        name_positions=("top",),
                        smart_in_type=True,
                        excluded_name_values=parse_name_exclusions(settings.rmu_name_exclusions),
                        intelligent_marker_values=parse_intelligent_markers(settings.rmu_intelligent_markers),
                        name_resolution_mode=settings.rmu_name_resolution_mode,
                    )
                validated_rmu_rect_ids = {
                    item.rect_id
                    for item in validated_identification.items
                    if item.rect_id
                }

                enhancement = enhance_rmu_tree(
                    tree,
                    input_path,
                    change_smart_frame_color=settings.change_smart_rmu_frame_color,
                    smart_frame_color=settings.smart_rmu_frame_color,
                    change_smr_frame_color=settings.change_smr_rmu_frame_color,
                    smr_frame_color=settings.smr_rmu_frame_color,
                    reposition_channel_status=settings.reposition_channel_status,
                    channel_status_position=settings.channel_status_position.value,
                    channel_status_inner_margin=settings.channel_status_inner_margin,
                    remove_bus_frame_and_reposition_title=(
                        settings.remove_bus_rmu_frame_and_reposition_title
                    ),
                    smart_rmu_rect_ids=smart_frame_rmu_rect_ids,
                    validated_rmu_rect_ids=validated_rmu_rect_ids,
                )
                total_smart_rmu_rects += enhancement.smart_rmu_rect_count
                total_smart_rmu_frames_changed += enhancement.smart_frame_color_changed
                total_smr_texts += enhancement.smr_text_count
                total_smr_matched_rects += enhancement.smr_matched_rect_count
                total_smr_frames_changed += enhancement.smr_frame_color_changed
                for change in enhancement.smr_changes:
                    smr_report_rows.append({"File": input_path.name, "SMRTextID": change.text_id, "SMRX": f"{change.text_x:g}", "SMRY": f"{change.text_y:g}", "RectID": change.rect_id, "RectX": f"{change.rect_x:g}", "RectY": f"{change.rect_y:g}", "RectW": f"{change.rect_w:g}", "RectH": f"{change.rect_h:g}", "Distance": f"{change.distance:.2f}", "OldColor": change.old_color, "NewColor": change.new_color, "Result": "已修改" if change.changed else "已是目标颜色"})
                total_channel_status_rects += enhancement.channel_status_rect_count
                total_channel_status_found += enhancement.channel_status_found_count
                total_channel_status_moved += enhancement.channel_status_moved_count
                total_channel_status_missing += enhancement.channel_status_missing_count
                total_bus_rect_removed += enhancement.bus_rect_removed
                total_bus_title_moved += enhancement.bus_title_moved
                rmu_processing_row["SmartMatched"] = enhancement.smart_rmu_rect_count
                rmu_processing_row["SmartChanged"] = enhancement.smart_frame_color_changed
                rmu_processing_row["SmrTextCount"] = enhancement.smr_text_count
                rmu_processing_row["SmrMatched"] = enhancement.smr_matched_rect_count
                rmu_processing_row["SmrChanged"] = enhancement.smr_frame_color_changed
                rmu_processing_row["ChannelStatusFound"] = enhancement.channel_status_found_count
                rmu_processing_row["ChannelStatusMoved"] = enhancement.channel_status_moved_count
                rmu_processing_row["BusFrameRemoved"] = enhancement.bus_rect_removed
                rmu_processing_row["TitleMoved"] = enhancement.bus_title_moved
                rmu_processing_warnings.extend(enhancement.warnings)
                if settings.change_smart_rmu_frame_color:
                    log(
                        f"[智能环网柜外框颜色] {input_path.name}：识别为智能的环网柜 "
                        f"{enhancement.smart_rmu_rect_count} 个，仅修改外框 "
                        f"{enhancement.smart_frame_color_changed} 个，颜色 "
                        f"{settings.smart_rmu_frame_color.upper()}；智能标记文字未修改。"
                    )
                if settings.change_smr_rmu_frame_color:
                    log(f"[SMR环网柜外框颜色] {input_path.name}：SMR Text {enhancement.smr_text_count} 个，匹配外框 {enhancement.smr_matched_rect_count} 个，改色 {enhancement.smr_frame_color_changed} 个；SMR Text 未修改。")
                if settings.reposition_channel_status:
                    log(
                        f"[环网柜红色状态点] {input_path.name}：识别带 BusDis 的环网柜 "
                        f"{enhancement.channel_status_rect_count} 个，找到 channel_status 状态点 "
                        f"{enhancement.channel_status_found_count} 个，移动 "
                        f"{enhancement.channel_status_moved_count} 个到框内“"
                        f"{settings.channel_status_position.label}”，距边 "
                        f"{settings.channel_status_inner_margin} 像素；环网柜、母线、设备和连接线位置未修改。"
                    )
                if settings.remove_bus_rmu_frame_and_reposition_title:
                    log(
                        f"[Bus环网柜处理] {input_path.name}：识别带 Bus 的环网柜 "
                        f"{enhancement.bus_rect_count} 个，删除外框 {enhancement.bus_rect_removed} 个，"
                        f"删除对应 Merge {enhancement.bus_merge_removed} 个，"
                        f"将最近标题移到母线上方并居中 {enhancement.bus_title_moved} 个。"
                    )
                for warning in enhancement.warnings:
                    log(f"[环网柜增强告警] {warning}")

            if settings.set_rmu_name_text_white:
                name_positions = tuple(
                    key for key, enabled in (
                        ("top", settings.rmu_name_top),
                        ("bottom", settings.rmu_name_bottom),
                        ("left", settings.rmu_name_left),
                        ("right", settings.rmu_name_right),
                    ) if enabled
                )
                name_color = apply_rmu_name_white_to_tree(
                    tree,
                    input_path,
                    name_positions=name_positions,
                    name_exclusions=", ".join(
                        value for value in (settings.rmu_name_exclusions, settings.rmu_intelligent_markers) if value.strip()
                    ),
                    name_resolution_mode=settings.rmu_name_resolution_mode,
                )
                total_rmu_name_white_matched += name_color.matched_name_text_count
                total_rmu_name_white_changed += name_color.changed_name_text_count
                rmu_processing_row["RMUNameWhiteMatched"] = name_color.matched_name_text_count
                rmu_processing_row["RMUNameWhiteChanged"] = name_color.changed_name_text_count
                rmu_processing_warnings.extend(name_color.warnings)
                log(
                    f"[RMU柜名白色] {input_path.name}：识别柜名 {name_color.named_rmu_count} 个，"
                    f"匹配名称 Text {name_color.matched_name_text_count} 个，改为白色 "
                    f"{name_color.changed_name_text_count} 个。"
                )
                for warning in name_color.warnings:
                    log(f"[RMU柜名白色告警] {warning}")

            if settings.add_smart_rmu_poke and poke_identification is not None:
                smart_count = sum(1 for item in poke_identification.items if item.smart_count)
                total_smart_rmu_poke_candidates += smart_count
                if smart_count == 0:
                    fac_id = ""
                else:
                    root = tree.getroot()
                    fac_id = (root.get("facID") or "").strip()
                if smart_count == 0:
                    pass
                elif not fac_id:
                    total_smart_rmu_poke_skipped += smart_count
                    log(
                        f"[智能RMU Poke跳转告警] {input_path.name}：当前 G 文件 facID 为空，"
                        "无法自动查询馈线/变电站信息。请先关联馈线，再执行智能环网柜 Poke 跳转。"
                    )
                else:
                    try:
                        if database_service is None:
                            from g_file_studio.services.database_service import OracleDatabaseService
                            from g_file_studio.services.user_settings_service import UserSettingsService
                            database_service = OracleDatabaseService(UserSettingsService())
                        context = database_service.resolve_g_file_context(fac_id)
                        g_fac_name = (root.get("facName") or "").strip()
                        log(
                            f"[智能RMU Poke数据库] {input_path.name}：facID={fac_id} → "
                            f"区域={context.subcontrolarea_name}，变电站={context.station_name}，"
                            f"馈线={context.feeder_name}，完整馈线名={context.feeder_full_name}。"
                        )
                        if g_fac_name and g_fac_name.casefold() != context.feeder_name.casefold():
                            log(
                                f"[智能RMU Poke跳转告警] {input_path.name}：G.facName={g_fac_name!r} 与 "
                                f"DMS_FEEDER_DEVICE.NAME={context.feeder_name!r} 不一致；"
                                "Poke 以数据库 NAME 为准。"
                            )
                        poke_result = apply_smart_rmu_pokes(
                            tree, input_path, poke_identification,
                            naming_mode="database_prefix",
                            naming_rule=context.feeder_full_name,
                        )
                        # candidates were counted before the database lookup.
                        total_smart_rmu_poke_added += poke_result.added_count
                        total_smart_rmu_poke_updated += poke_result.updated_count
                        total_smart_rmu_poke_unchanged += poke_result.unchanged_count
                        total_smart_rmu_poke_skipped += poke_result.skipped_count
                        log(
                            f"[智能RMU Poke跳转] {input_path.name}：数据库自动前缀 {context.feeder_full_name}；"
                            f"智能 RMU {poke_result.intelligent_rmu_count} 个，可安全生成 {poke_result.eligible_rmu_count} 个；"
                            f"新增 Poke {poke_result.added_count} 个，更新 {poke_result.updated_count} 个，"
                            f"已符合 {poke_result.unchanged_count} 个，跳过 {poke_result.skipped_count} 个。"
                        )
                        for change in poke_result.changes:
                            action_label = {"added": "新增", "updated": "更新", "unchanged": "已符合"}.get(change.action, change.action)
                            log(
                                f"  - RMU {change.rmu_name} / rect {change.rect_id}：{action_label} Poke {change.poke_id}，"
                                f"范围 ({change.x:g}, {change.y:g}, {change.w:g}, {change.h:g})，"
                                f"跳转 {change.target_file}。"
                            )
                        for warning in poke_result.warnings:
                            log(f"[智能RMU Poke跳转告警] {input_path.name}：{warning}")
                    except Exception as exc:
                        total_smart_rmu_poke_skipped += smart_count
                        log(
                            f"[智能RMU Poke跳转告警] {input_path.name}：数据库无法解析 facID={fac_id}：{exc}。"
                            "本文件仅跳过 Poke，其他环网柜处理继续执行。"
                        )

            if (
                rmu_action != RmuAction.NONE
                or settings.change_smart_rmu_frame_color
                or settings.change_smr_rmu_frame_color
                or settings.set_rmu_name_text_white
                or settings.reposition_channel_status
                or settings.remove_bus_rmu_frame_and_reposition_title
            ):
                rmu_processing_row["Warnings"] = " | ".join(rmu_processing_warnings)
                rmu_processing_rows.append(rmu_processing_row)

            if color_rules:
                color_result = apply_line_colors(tree, input_path, color_rules)
                total_color_changed += color_result.total_changed
                total_dynamic_colors += color_result.total_dynamic_color
                labels = {rule.element_tag: rule.display_name for rule in color_rules}
                style_names = {"keep": "保持原样", "solid": "实线(ls=1)", "dashed": "虚线(ls=2)"}
                log(f"[线路与母线样式/颜色处理] {input_path.name}：")
                for rule in color_rules:
                    count = color_result.changed_by_tag.get(rule.element_tag, 0)
                    color_count = color_result.color_changed_by_tag.get(rule.element_tag, 0)
                    style_count = color_result.style_changed_by_tag.get(rule.element_tag, 0)
                    dynamic = color_result.dynamic_color_by_tag.get(rule.element_tag, 0)
                    parts = [f"修改 {count} 个"]
                    if rule.change_color:
                        parts.append(f"颜色 {rule.color.upper()}（{color_count} 个）")
                    if rule.line_style != "keep":
                        parts.append(f"线型 {style_names.get(rule.line_style, rule.line_style)}（{style_count} 个）")
                    line = f"  - {labels[rule.element_tag]} <{rule.element_tag}>：" + "；".join(parts)
                    if dynamic and rule.change_color:
                        line += f"；其中 {dynamic} 个启用了动态颜色，运行时颜色可能被动态规则覆盖"
                    log(line)
                log(f"[线路与母线样式/颜色处理] {input_path.name}：合计修改 {color_result.total_changed} 个图元。")

            if settings.repair_connection_points:
                connection = repair_tree_connections(tree, input_path)
                total_connection_aligned_devices += connection.aligned_device_count
                total_connection_adjusted_lines += connection.adjusted_line_endpoint_count
                total_connection_relations += connection.inferred_relation_count
                total_connection_added += connection.added_reference_count
                total_connection_updated += connection.updated_reference_count
                total_connection_removed += connection.removed_reference_count
                total_connection_changed_elements += connection.changed_element_count
                total_connection_changed_attributes += connection.changed_attribute_count
                log(
                    f"[连接点修复] {input_path.name}：连接线 {connection.line_count} 个、"
                    f"母线 {connection.conductor_count} 个、可连接设备 {connection.device_count} 个；"
                    f"半像素水平对齐设备 {connection.aligned_device_count} 个、连接线坐标修改 "
                    f"{connection.adjusted_line_endpoint_count} 个；保守识别连接关系 "
                    f"{connection.inferred_relation_count} 条，新增引用 "
                    f"{connection.added_reference_count} 处；原引用改号 "
                    f"{connection.updated_reference_count} 处、原引用删除 "
                    f"{connection.removed_reference_count} 处，实际变更图元 "
                    f"{connection.changed_element_count} 个、属性 "
                    f"{connection.changed_attribute_count} 个。"
                )
                if connection.changed_element_ids:
                    log("  - 变更图元 ID：" + ", ".join(connection.changed_element_ids))
                else:
                    log("  - 当前文件连接关系完整，无需修改。")
                for warning in connection.warnings:
                    log(f"[连接点修复告警] {input_path.name}：{warning}")

            if hasattr(ET, "indent"):
                ET.indent(tree, space="    ")

            tmp_path = output_path.with_name(output_path.name + ".tmp")
            tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
            ET.parse(tmp_path)
            os.replace(tmp_path, output_path)

            enforce_confirmed_id_rules(output_path, log)
            outputs.append(output_path)
            if rmu_identification is not None and settings.export_rmu_identification_csv:
                rmu_csv = _write_rmu_csv(output_path, rmu_identification)
                rmu_html = _write_rmu_html(output_path, rmu_identification)
                total_rmu_csv += 1
                log(f"[环网柜识别] 已导出：{rmu_csv.name}；HTML：{rmu_html.name}")
            total_replaced += replaced
            total_deleted_attributes += deleted_attributes
            total_removed_matching += removed_matching
            total_removed_reference_groups += removed_reference_groups
            total_cleared_single_references += cleared_single_references

            log(
                f"✓ {input_path.name}：属性替换 {replaced} 处，删除元素属性 {deleted_attributes} 处，"
                f"匹配元素删除 {removed_matching} 个，"
                f"清理引用分组 {removed_reference_groups} 个，清空父引用 "
                f"{cleared_single_references} 个；输出 {output_path.name}"
            )
        except Exception as exc:
            failed.append(f"{input_path.name}: {exc}")
            log(f"[基础处理失败] {input_path.name}：{exc}")

        if progress:
            progress(round(index * 100 / len(files)))

    rmu_graphic_report_csv = None
    rmu_graphic_report_html = None
    if rmu_processing_rows:
        rmu_graphic_report_csv, rmu_graphic_report_html = _write_rmu_processing_report(settings.output_dir, rmu_processing_rows)
        log(f"[环网柜图元处理报告] CSV：{rmu_graphic_report_csv}；HTML：{rmu_graphic_report_html}（覆盖上一份同类报告）。")

    rmu_summary_report_csv = None
    rmu_summary_report_html = None
    if settings.identify_rmu_name_and_type:
        rmu_summary_report_csv, rmu_summary_report_html = _write_rmu_summary_reports(
            settings.output_dir, rmu_graphic_rows,
            intelligent_classification_enabled=settings.rmu_smart_in_type,
        )
        log(f"[RMU信息汇总报告] CSV：{rmu_summary_report_csv}；HTML：{rmu_summary_report_html}（覆盖上一份同类报告）。")

    if settings.change_smr_rmu_frame_color:
        csv_report, html_report = _write_smr_frame_reports(settings.output_dir, smr_report_rows)
        outputs.extend([csv_report, html_report])
        log(f"[SMR环网柜报告] CSV：{csv_report}；HTML：{html_report}（覆盖上一份同类报告）。")

    ledger_stats = {}
    ledger_csv = None
    ledger_html = None
    if settings.compare_rmu_ledger:
        comparison_rows, ledger_stats = compare_ledger(ledger_rows, rmu_graphic_rows)
        ledger_csv, ledger_html = write_comparison_reports(settings.output_dir, comparison_rows, ledger_stats)
        outputs.extend([ledger_csv, ledger_html])
        log(
            f"[RMU台账对比] 台账 {ledger_stats['ledger_count']} 条，图形 {ledger_stats['graphic_count']} 个；"
            f"完全一致 {ledger_stats['matched_count']}，柜型不一致 {ledger_stats['type_mismatch_count']}，"
            f"智能属性不一致 {ledger_stats['intelligent_mismatch_count']}，图形缺失 {ledger_stats['graphic_missing_count']}，"
            f"台账缺失 {ledger_stats['ledger_missing_count']}。"
        )
        log(f"[RMU台账对比] 报告：{ledger_csv.name}；{ledger_html.name}（覆盖上一份同类报告）。")

    summary = (
        f"[基础处理汇总] 输入 {len(files)} 个文件，成功 {len(outputs)} 个，失败 {len(failed)} 个；"
        f"环网柜 rect {total_rects} 个，重建组合 "
        f"{total_rmu_groups} 个，取消组合 {total_rmu_ungrouped} 个，外框下移 "
        f"{total_rmu_lowered_rects} 个；识别含 SMART 环网柜 {total_smart_rmu_rects} 个，"
        f"SMART 环网柜外框改色 {total_smart_rmu_frames_changed} 个；SMR Text {total_smr_texts} 个，匹配环网柜 {total_smr_matched_rects} 个，SMR 外框改色 {total_smr_frames_changed} 个；"
        f"RMU 柜名匹配 {total_rmu_name_white_matched} 个、改白 {total_rmu_name_white_changed} 个；"
        f"智能 RMU Poke 候选 {total_smart_rmu_poke_candidates} 个、新增 {total_smart_rmu_poke_added} 个、"
        f"更新 {total_smart_rmu_poke_updated} 个、已符合 {total_smart_rmu_poke_unchanged} 个、跳过 {total_smart_rmu_poke_skipped} 个；channel_status 状态点"
        f"找到 {total_channel_status_found} 个、移动 {total_channel_status_moved} 个、"
        f"未找到 {total_channel_status_missing} 个，带 Bus 外框删除 "
        f"{total_bus_rect_removed} 个，标题上移 {total_bus_title_moved} 个；"
        f"线路/母线颜色修改 {total_color_changed} 个图元"
    )
    if settings.remove_all_graphic_merges:
        summary += (
            f"；彻底取消图形组合删除 Merge {total_graphic_merges_removed} 个，"
            f"识别 RMU 外框 {total_graphic_merge_cleanup_rmu_rects} 个、置底 {total_graphic_merge_cleanup_lowered_rects} 个"
        )
    elif settings.reset_existing_merges_before_rmu_group:
        summary += (
            f"；环网柜重组前清理旧 Merge {total_graphic_merges_removed} 个，"
            f"RMU 外框置底 {total_graphic_merge_cleanup_lowered_rects} 个"
        )
    if settings.identify_rmu_name_and_type:
        summary += (
            f"；环网柜识别 {total_rmu_identified} 个、柜名成功 {total_rmu_named} 个、"
            f"柜型成功 {total_rmu_typed} 个、待确认 {total_rmu_ambiguous} 个、导出 CSV/HTML 报告 {total_rmu_csv} 份"
        )
    if settings.compare_rmu_ledger and ledger_stats:
        summary += (
            f"；RMU台账 {ledger_stats['ledger_count']} 条，对比完全一致 {ledger_stats['matched_count']} 条，"
            f"柜型不一致 {ledger_stats['type_mismatch_count']} 条，智能属性不一致 {ledger_stats['intelligent_mismatch_count']} 条，"
            f"图形缺失 {ledger_stats['graphic_missing_count']} 条，台账缺失 {ledger_stats['ledger_missing_count']} 条"
        )
    if settings.upgrade_icon_geometry:
        summary += (
            f"；同类图元版本升级实例 {total_icon_upgraded_instances} 个、连接线端点适配 "
            f"{total_icon_adjusted_lines} 条、已是新尺寸 {total_icon_already_new} 个、"
            f"未知尺寸跳过 {total_icon_skipped_unknown_size} 个"
        )
    if settings.repair_connection_points:
        summary += (
            f"；连接点半像素水平对齐设备 {total_connection_aligned_devices} 个、连接线坐标修改 "
            f"{total_connection_adjusted_lines} 个，保守识别关系 {total_connection_relations} 条，新增引用 "
            f"{total_connection_added} 处、原引用改号 {total_connection_updated} 处、"
            f"原引用删除 {total_connection_removed} 处，"
            f"变更图元 {total_connection_changed_elements} 个、属性 "
            f"{total_connection_changed_attributes} 个"
        )
    log(summary + "。")

    return ProcessingResult(
        success=not failed,
        output_files=outputs,
        warnings=failed,
        statistics={
            "input_mode": settings.input_mode.value,
            "source_path": str(settings.source_path),
            "file_count": len(outputs),
            "failed_file_count": len(failed),
            "replaced_attribute_count": total_replaced,
            "deleted_attribute_count": total_deleted_attributes,
            "removed_matching_element_count": total_removed_matching,
            "removed_reference_group_count": total_removed_reference_groups,
            "cleared_single_reference_count": total_cleared_single_references,
            "rmu_rect_count": total_rects,
            "rmu_group_count": total_rmu_groups,
            "rmu_grouped_member_count": total_rmu_members,
            "rmu_ungrouped_count": total_rmu_ungrouped,
            "rmu_released_member_count": total_rmu_released_members,
            "rmu_lowered_rect_count": total_rmu_lowered_rects,
            "graphic_merge_cleanup_enabled": settings.remove_all_graphic_merges,
            "graphic_merge_removed_count": total_graphic_merges_removed,
            "graphic_merge_cleanup_rmu_rect_count": total_graphic_merge_cleanup_rmu_rects,
            "graphic_merge_cleanup_lowered_rect_count": total_graphic_merge_cleanup_lowered_rects,
            "color_changed_count": total_color_changed,
            "dynamic_color_warning_count": total_dynamic_colors,
            "smart_rmu_rect_count": total_smart_rmu_rects,
            "smart_rmu_frame_color_changed_count": total_smart_rmu_frames_changed,
            "smr_text_count": total_smr_texts,
            "smr_matched_rmu_rect_count": total_smr_matched_rects,
            "smr_rmu_frame_color_changed_count": total_smr_frames_changed,
            "rmu_name_text_white_enabled": settings.set_rmu_name_text_white,
            "rmu_name_text_white_matched_count": total_rmu_name_white_matched,
            "rmu_name_text_white_changed_count": total_rmu_name_white_changed,
            "smart_rmu_poke_enabled": settings.add_smart_rmu_poke,
            "smart_rmu_poke_candidate_count": total_smart_rmu_poke_candidates,
            "smart_rmu_poke_added_count": total_smart_rmu_poke_added,
            "smart_rmu_poke_updated_count": total_smart_rmu_poke_updated,
            "smart_rmu_poke_unchanged_count": total_smart_rmu_poke_unchanged,
            "smart_rmu_poke_skipped_count": total_smart_rmu_poke_skipped,
            "channel_status_rmu_rect_count": total_channel_status_rects,
            "channel_status_found_count": total_channel_status_found,
            "channel_status_moved_count": total_channel_status_moved,
            "channel_status_missing_count": total_channel_status_missing,
            "bus_rmu_frame_removed_count": total_bus_rect_removed,
            "bus_rmu_title_moved_count": total_bus_title_moved,
            "rmu_identification_enabled": settings.identify_rmu_name_and_type,
            "rmu_identified_count": total_rmu_identified,
            "rmu_named_count": total_rmu_named,
            "rmu_typed_count": total_rmu_typed,
            "rmu_ambiguous_name_count": total_rmu_ambiguous,
            "rmu_csv_count": total_rmu_csv,
            "rmu_ledger_compare_enabled": settings.compare_rmu_ledger,
            "rmu_ledger_count": ledger_stats.get("ledger_count", 0),
            "rmu_ledger_matched_count": ledger_stats.get("matched_count", 0),
            "rmu_ledger_type_mismatch_count": ledger_stats.get("type_mismatch_count", 0),
            "rmu_ledger_intelligent_mismatch_count": ledger_stats.get("intelligent_mismatch_count", 0),
            "rmu_ledger_graphic_missing_count": ledger_stats.get("graphic_missing_count", 0),
            "rmu_ledger_missing_count": ledger_stats.get("ledger_missing_count", 0),
            "rmu_graphic_processing_report_html": str(rmu_graphic_report_html or ""),
            "rmu_summary_report_html": str(rmu_summary_report_html or ""),
            "rmu_ledger_report_html": str(ledger_html or ""),
            "icon_upgrade_enabled": settings.upgrade_icon_geometry,
            "icon_upgrade_rule_count": len(icon_rules),
            "icon_upgraded_instance_count": total_icon_upgraded_instances,
            "icon_adjusted_line_count": total_icon_adjusted_lines,
            "icon_already_new_count": total_icon_already_new,
            "icon_unknown_size_skipped_count": total_icon_skipped_unknown_size,
            "connection_repair_enabled": settings.repair_connection_points,
            "aligned_connection_device_count": total_connection_aligned_devices,
            "adjusted_connection_line_count": total_connection_adjusted_lines,
            "inferred_connection_count": total_connection_relations,
            "added_connection_reference_count": total_connection_added,
            "updated_connection_reference_count": total_connection_updated,
            "removed_connection_reference_count": total_connection_removed,
            "changed_connection_element_count": total_connection_changed_elements,
            "changed_connection_attribute_count": total_connection_changed_attributes,
        },
    )
