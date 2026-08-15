#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import html
import json
import re
from datetime import datetime
from pathlib import Path

from dmm.config.constants import APP_NAME, APP_VERSION



FEEDER_FIELDS = [
    "file_name", "drawing_type", "region_index",
    "region_assignment_method",
    "trusted_rmu_count", "ignored_rmu_count",
    "trusted_rmu_names", "trusted_feeder_ids", "ignored_rmu_details",
    "feeder_hint", "feeder_hint_source",
    "feeder_normalized_hint",
    "feeder_db_count", "feeder_id", "feeder_name",
    "feedline_count", "linked_correct_count",
    "unlinked_count", "error_count",
    "association_ready_count", "association_eligible",
    "status", "severity", "reason",
]

FEEDLINE_FIELDS = [
    "file_name", "feeder_name",
    "drawing_type", "region_index", "region_assignment_method",
    "topology_component", "topology_cross_region",
    "order_index", "object_type", "xml_id",
    "model_linked", "model_link_correct",
    "current_keyid", "current_device_id",
    "current_table_id", "current_domain",
    "current_db_name", "current_db_code",
    "current_bv_id", "current_feeder_id",
    "assigned_device_id", "assigned_section_name", "assigned_bv_id",
    "expected_keyid", "expected_keyid_verified",
    "association_ready", "writeback_needed",
    "status", "severity", "reason",
]

FEEDER_LABELS = {
    "file_name": "G文件",
    "drawing_type": "图纸类型",
    "region_index": "馈线区域序号",
    "region_assignment_method": "FeedLine归属方式",
    "trusted_rmu_count": "可信环网柜数",
    "ignored_rmu_count": "忽略环网柜数",
    "trusted_rmu_names": "可信环网柜",
    "trusted_feeder_ids": "可信RMU的FEEDER_ID",
    "ignored_rmu_details": "未作为依据的环网柜说明",
    "feeder_hint": "图上/文件馈线标识",
    "feeder_hint_source": "馈线名称来源",
    "feeder_normalized_hint": "标准化馈线标识",
    "feeder_db_count": "馈线数据库匹配数",
    "feeder_id": "馈线ID",
    "feeder_name": "数据库馈线名称",
    "feedline_count": "FeedLine图元数",
    "linked_correct_count": "已正确关联数",
    "unlinked_count": "未关联数",
    "error_count": "错误数",
    "association_ready_count": "可自动关联数",
    "association_eligible": "馈线可执行关联",
    "status": "状态",
    "severity": "状态类型",
    "reason": "说明",
}

FEEDLINE_LABELS = {
    "file_name": "G文件",
    "feeder_name": "馈线名称",
    "drawing_type": "图纸类型",
    "region_index": "馈线区域序号",
    "region_assignment_method": "FeedLine归属方式",
    "topology_component": "连接分量",
    "topology_cross_region": "连接关系跨区域",
    "order_index": "FeedLine序号",
    "object_type": "G图元类型",
    "xml_id": "图元XML ID",
    "model_linked": "是否已关联",
    "model_link_correct": "当前模型是否正确",
    "current_keyid": "当前KeyID",
    "current_device_id": "当前数据库馈线段ID",
    "current_table_id": "当前表号",
    "current_domain": "当前域号",
    "current_db_name": "当前数据库馈线段NAME",
    "current_db_code": "当前数据库馈线段CODE",
    "current_bv_id": "当前模型BV_ID",
    "current_feeder_id": "当前模型所属馈线ID",
    "assigned_device_id": "目标馈线段ID",
    "assigned_section_name": "目标馈线段NAME",
    "assigned_bv_id": "目标BV_ID / voltype",
    "expected_keyid": "期望KeyID",
    "expected_keyid_verified": "期望KeyID校验",
    "association_ready": "可进入关联流程",
    "writeback_needed": "是否需要回写",
    "status": "状态",
    "severity": "状态类型",
    "reason": "说明",
}


DEVICE_FIELDS = [
    "rmu_name", "rmu_id",
    "object_type", "xml_id", "logical_code", "graphical_name",
    "selected_name_source", "selected_device_name", "paired_breaker_name",
    "table_id", "table_name", "configured_domain", "match_mode",
    "db_match_count", "db_device_id", "db_code", "db_name",
    "db_combined_id", "db_bv_id",
    "expected_keyid", "expected_keyid_verified",
    "current_keyid", "current_device_id", "current_table_id", "current_domain",
    "current_table_name", "current_db_code", "current_db_name",
    "current_combined_id", "current_rmu_name",
    "current_rmu_match", "current_rmu_name_match",
    "model_linked", "model_link_correct", "model_link_status",
    "association_action", "writeback_needed",
    "association_ready", "status", "severity", "reason",
]

RMU_FIELDS = [
    "file_name", "frame_index", "frame_xml_id", "rmu_name",
    "rmu_type", "rmu_type_source", "rmu_type_text", "rmu_type_devref",
    "rmu_type_consistent", "rmu_type_check_status", "rmu_type_check_reason",
    "rmu_is_smart", "rmu_smart_marker_types",
    "rmu_status", "rmu_severity", "rmu_reason",
    "rmu_db_count", "rmu_id",
    "device_count", "matched_device_count", "device_complete",
    "linked_correct_count", "unlinked_count",
    "linked_wrong_count", "association_eligible",
    "association_block_reasons", "device_block_reasons",
    "inventory_issues", "db_integrity_issues",
]


RMU_PROFILE_FIELDS = [
    "file_name",
    "frame_index",
    "frame_xml_id",
    "rmu_name",
    "rmu_type",
    "rmu_type_source",
    "rmu_type_text",
    "rmu_type_devref",
    "rmu_type_consistent",
    "rmu_type_check_status",
    "rmu_type_check_reason",
    "rmu_is_smart",
    "rmu_smart_marker_types",
    "rmu_db_count",
    "database_unique",
    "rmu_id",
    "device_count",
    "matched_device_count",
    "device_complete",
    "rmu_status",
    "rmu_reason",
]

RMU_PROFILE_LABELS = {
    "file_name": "G文件",
    "frame_index": "环网柜序号",
    "frame_xml_id": "矩形框XML ID",
    "rmu_name": "环网柜名称",
    "rmu_type": "环网柜类型",
    "rmu_type_source": "类型识别来源",
    "rmu_type_text": "柜内Y/Q文字类型",
    "rmu_type_devref": "devref类型",
    "rmu_type_consistent": "类型交叉校验",
    "rmu_type_check_status": "柜型校验状态",
    "rmu_type_check_reason": "柜型交叉校验说明",
    "rmu_is_smart": "是否智能",
    "rmu_smart_marker_types": "智能标识",
    "rmu_db_count": "数据库记录数",
    "database_unique": "数据库是否唯一",
    "rmu_id": "环网柜ID",
    "device_count": "G图设备数",
    "matched_device_count": "数据库唯一匹配设备数",
    "device_complete": "设备是否完整",
    "matched_device_count": "数据库唯一匹配设备数",
    "device_complete": "环网柜设备是否完整",
    "rmu_status": "校验状态",
    "rmu_reason": "说明",
}

DEVICE_LABELS = {
    "file_name": "G文件",
    "rmu_name": "环网柜名称",
    "rmu_type": "环网柜类型",
    "rmu_type_source": "类型识别来源",
    "rmu_type_text": "图内文字类型",
    "rmu_type_devref": "devref类型",
    "rmu_type_consistent": "类型交叉校验",
    "rmu_type_check_status": "柜型校验状态",
    "rmu_type_check_reason": "柜型交叉校验说明",
    "rmu_is_smart": "是否智能",
    "rmu_smart_marker_types": "智能标识",
    "rmu_id": "环网柜ID",
    "object_type": "G图元类型",
    "xml_id": "图元XML ID",
    "logical_code": "逻辑CODE（图上规则）",
    "graphical_name": "图上名称",
    "selected_name_source": "设备名称来源",
    "selected_device_name": "最终设备名称",
    "paired_breaker_name": "配对开关名称",
    "table_id": "表号",
    "table_name": "数据库表",
    "configured_domain": "域号",
    "match_mode": "匹配规则",
    "db_match_count": "数据库匹配数",
    "db_device_id": "关联数据库设备ID",
    "db_code": "关联设备CODE",
    "db_name": "关联设备NAME",
    "db_combined_id": "所属环网柜ID",
    "db_bv_id": "BV_ID",
    "expected_keyid": "期望KeyID",
    "expected_keyid_verified": "期望KeyID校验",
    "current_keyid": "当前KeyID",
    "current_device_id": "当前设备ID",
    "current_table_id": "当前表号",
    "current_domain": "当前域号",
    "current_table_name": "当前模型数据库表",
    "current_db_code": "当前模型设备CODE",
    "current_db_name": "当前模型设备NAME",
    "current_combined_id": "当前模型所属环网柜ID",
    "current_rmu_name": "当前模型所属环网柜名称",
    "current_rmu_match": "当前模型环网柜ID是否正确",
    "current_rmu_name_match": "当前模型环网柜名称是否正确",
    "model_linked": "设备是否已关联模型",
    "model_link_correct": "当前模型是否正确",
    "model_link_status": "当前模型状态",
    "association_action": "处理建议",
    "writeback_needed": "是否需要回写",
    "association_ready": "可进入关联流程",
    "status": "状态",
    "severity": "状态类型",
    "reason": "说明",
}

RMU_LABELS = {
    "file_name": "G文件",
    "frame_index": "环网柜序号",
    "frame_xml_id": "矩形框XML ID",
    "rmu_name": "环网柜名称",
    "rmu_type": "环网柜类型",
    "rmu_type_source": "类型识别来源",
    "rmu_type_text": "图内文字类型",
    "rmu_type_devref": "devref类型",
    "rmu_type_consistent": "类型交叉校验",
    "rmu_type_check_status": "柜型校验状态",
    "rmu_type_check_reason": "柜型交叉校验说明",
    "rmu_is_smart": "是否智能",
    "rmu_smart_marker_types": "智能标识",
    "rmu_status": "状态",
    "rmu_severity": "状态类型",
    "rmu_reason": "说明",
    "rmu_db_count": "数据库记录数",
    "rmu_id": "环网柜ID",
    "device_count": "已处理图元数",
    "linked_correct_count": "已正确关联设备数",
    "unlinked_count": "未关联设备数",
    "linked_wrong_count": "关联错误设备数",
    "association_eligible": "RMU可关联",
    "association_block_reasons": "RMU级关联阻断原因",
    "device_block_reasons": "设备级阻断原因",
    "inventory_issues": "G图元匹配问题",
    "db_integrity_issues": "数据库匹配问题",
}


def esc(value):
    return html.escape("" if value is None else str(value))


def status_cls(status):
    return {
        "PASS": "pass",
        "WARN": "warn",
        "RELINK": "relink",
        "RMU_RELINK": "rmu-relink",
        # RMU_LINK remains a hard error used by ambiguous/non-unique RMU cases.
        "RMU_LINK": "fail",
        "BLOCKED": "blocked",
        "FAIL": "fail",
        "INFO": "info",
    }.get(status, "")



# ---------------------------------------------------------------------------
# Report ordering
# ---------------------------------------------------------------------------
# RMU summary:
#   only order by RMU sequence/frame_index within each G file.
#
# Device details:
#   preserve G-file order and RMU processing order;
#   inside each RMU, only group rows by G object type.
#   Rows of the same type keep their original validation order.
DEVICE_TYPE_ORDER = {
    "CBreakerDis": 10,
    "ZhaiWaiJieDiDaoZha": 20,
    "BusDis": 30,
}


def _numeric_sequence(value):
    if value in (None, ""):
        return 10**18
    try:
        return int(value)
    except (TypeError, ValueError):
        return 10**18


def sort_rmu_results_by_sequence(rmu_results):
    """
    Stable sort by RMU sequence only.

    Duplicate database records remain adjacent because they are expanded
    after the RMU itself has been ordered.
    """
    return sorted(
        list(rmu_results),
        key=lambda rmu: _numeric_sequence(rmu.get("frame_index", "")),
    )


def sort_devices_within_rmu(device_rows):
    """
    The ONLY device-detail ordering rule:

        CBreakerDis
        ZhaiWaiJieDiDaoZha
        BusDis
        other types

    Python's sort is stable, so rows inside the same G object type retain
    their original validator order.
    """
    return sorted(
        list(device_rows),
        key=lambda row: DEVICE_TYPE_ORDER.get(
            str(row.get("object_type", "") or "").strip(),
            999,
        ),
    )


def flatten_rmu_rows(reports):
    """
    RMU summary rules (v3.0.19)
    --------------------------
    1. One G-file RMU frame -> exactly one summary row.
    2. Rows are always sorted by G-file RMU sequence/frame_index.
    3. Oracle dms_combined_device result count is reported in that one row:
       - 0 rows  -> RMU_NOT_FOUND_IN_DATABASE
       - 1 row   -> normal validation; show the unique RMU ID
       - >1 rows -> RMU_DUPLICATE_IN_DATABASE, but DO NOT expand every DB ID.
                    Leave RMU ID blank and tell the user how many RMUs were found.
    4. Device detail remains G-element based and is handled separately.
    """
    rows = []

    for report in reports:
        file_name = report.get("file_name", "")
        rmu_results = sort_rmu_results_by_sequence(
            report.get("rmu_results", [])
        )

        for rmu in rmu_results:
            records = list(rmu.get("rmu_records") or [])
            db_count = len(records)

            # Only one database record is considered safe/usable.
            unique_record = records[0] if db_count == 1 else {}

            status = rmu.get("rmu_status", "")
            severity = rmu.get("rmu_severity", "")
            reason = rmu.get("rmu_reason", "")
            block_reasons = list(rmu.get("association_block_reasons", []))

            if db_count > 1:
                status = "FAIL"
                severity = "ERROR"
                reason = (
                    f"RMU_DUPLICATE_IN_DATABASE: 数据库中找到 {db_count} 个同名环网柜，"
                    "请检查数据库模型和单线图中的该环网柜。"
                )
                duplicate_block = (
                    f"数据库中找到 {db_count} 个同名环网柜；环网柜必须唯一，"
                    "禁止自动关联，请检查数据库模型和单线图中的该环网柜。"
                )
                if duplicate_block not in block_reasons:
                    block_reasons.append(duplicate_block)

            elif db_count == 0:
                status = "FAIL"
                severity = "ERROR"
                if not reason or reason == "RMU_NOT_FOUND_IN_DATABASE":
                    reason = (
                        "RMU_NOT_FOUND_IN_DATABASE: 数据库中未找到该环网柜，"
                        "请检查数据库模型和单线图中的环网柜名称。"
                    )

            device_rows = [
                d for d in rmu.get("device_rows", [])
                if d.get("xml_id")
            ]
            matched_device_count = sum(
                1
                for d in device_rows
                if int(d.get("db_match_count") or 0) == 1
                and (
                    db_count != 1
                    or str(d.get("db_combined_id", ""))
                    == str(unique_record.get("id", ""))
                )
            )
            device_complete = (
                db_count == 1
                and bool(device_rows)
                and matched_device_count == len(device_rows)
            )

            row = {
                "file_name": file_name,
                "frame_index": rmu.get("frame_index", ""),
                "frame_xml_id": rmu.get("frame_xml_id", ""),
                "rmu_name": rmu.get("rmu_name", ""),
                "rmu_type": rmu.get("rmu_type", "UNKNOWN"),
                "rmu_type_source": rmu.get("rmu_type_source", ""),
                "rmu_type_text": rmu.get("rmu_type_text", ""),
                "rmu_type_devref": rmu.get("rmu_type_devref", ""),
                "rmu_type_consistent": rmu.get("rmu_type_consistent", ""),
                "rmu_type_check_status": rmu.get(
                    "rmu_type_check_status",
                    "",
                ),
                "rmu_type_check_reason": rmu.get(
                    "rmu_type_check_reason",
                    "",
                ),
                "rmu_is_smart": rmu.get("rmu_is_smart", "NO"),
                "rmu_smart_marker_types": rmu.get(
                    "rmu_smart_marker_types",
                    "",
                ),
                "rmu_status": status,
                "rmu_severity": severity,
                "rmu_reason": reason,
                "rmu_db_count": db_count,
                # Duplicate RMU: intentionally DO NOT list multiple IDs.
                "rmu_id": unique_record.get("id", "") if db_count == 1 else "",
                "device_count": len(device_rows),
                "matched_device_count": matched_device_count,
                "device_complete": "YES" if device_complete else "NO",
                "linked_correct_count": rmu.get(
                    "linked_correct_count", 0
                ),
                "unlinked_count": rmu.get("unlinked_count", 0),
                "linked_wrong_count": rmu.get(
                    "linked_wrong_count", 0
                ),
                "association_eligible": (
                    "YES"
                    if rmu.get("association_eligible") and db_count == 1
                    else "NO"
                ),
                "association_block_reasons": "; ".join(block_reasons),
                "device_block_reasons": "; ".join(
                    rmu.get("device_block_reasons", [])
                ),
                "inventory_issues": "; ".join(
                    rmu.get("inventory_issues", [])
                ),
                "db_integrity_issues": "; ".join(
                    rmu.get("db_integrity_issues", [])
                ),
            }
            rows.append(row)

    # Final sort across all files: file name then numeric RMU sequence.
    return sorted(
        rows,
        key=lambda r: (
            str(r.get("file_name", "")),
            _numeric_sequence(r.get("frame_index", "")),
        ),
    )



def flatten_rmu_profile_rows(reports):
    """Compact one-row-per-RMU inventory required for field review."""
    rows = flatten_rmu_rows(reports)
    result = []
    for row in rows:
        item = dict(row)
        item["database_unique"] = (
            "YES" if int(item.get("rmu_db_count") or 0) == 1 else "NO"
        )
        result.append(item)
    return result


def flatten_device_rows(reports):
    rows = []

    # Preserve report / G-file order.
    for report in reports:
        file_name = report.get("file_name", "")

        # Preserve RMU processing order exactly as validator produced it.
        for rmu in report.get("rmu_results", []):
            # The only device-detail sort is object-type grouping
            # inside this single RMU.
            devices = sort_devices_within_rmu(
                rmu.get("device_rows", [])
            )

            for device in devices:
                row = dict(device)
                row.pop("x", None)
                row.pop("y", None)
                row["file_name"] = file_name
                row.setdefault("rmu_name", rmu.get("rmu_name", ""))
                row.setdefault("rmu_id", rmu.get("rmu_id", ""))
                rows.append(row)

    return rows



def _is_feeder_reports(reports):
    return bool(
        reports
        and str(reports[0].get("report_type", "")).upper() == "FEEDER"
    )


def flatten_feeder_rows(reports):
    rows = []
    for report in reports:
        feedline_rows = list(report.get("feedline_rows", []))
        rows.append({
            "file_name": report.get("file_name", ""),
            "drawing_type": report.get("drawing_type", "SINGLE_FEEDER"),
            "region_index": report.get("region_index", 1),
            "region_assignment_method": report.get(
                "region_assignment_method", "WHOLE_FILE"
            ),
            "trusted_rmu_count": report.get("trusted_rmu_count", 0),
            "ignored_rmu_count": report.get("ignored_rmu_count", 0),
            "trusted_rmu_names": report.get("trusted_rmu_names", ""),
            "trusted_feeder_ids": report.get("trusted_feeder_ids", ""),
            "ignored_rmu_details": report.get("ignored_rmu_details", ""),
            "feeder_hint": report.get("feeder_hint", ""),
            "feeder_hint_source": report.get("feeder_hint_source", ""),
            "feeder_normalized_hint": report.get(
                "feeder_normalized_hint", ""
            ),
            "feeder_db_count": len(report.get("feeder_records", []) or []),
            "feeder_id": report.get("feeder_id", ""),
            "feeder_name": report.get("feeder_name", ""),
            "feedline_count": len(feedline_rows),
            "linked_correct_count": sum(
                1 for row in feedline_rows
                if row.get("model_link_correct") == "YES"
            ),
            "unlinked_count": sum(
                1 for row in feedline_rows
                if row.get("model_linked") == "NO"
            ),
            "error_count": sum(
                1 for row in feedline_rows
                if row.get("status") == "FAIL"
            ),
            "association_ready_count": sum(
                1 for row in feedline_rows
                if (
                    row.get("association_ready") == "YES"
                    and row.get("writeback_needed") == "YES"
                )
            ),
            "association_eligible": (
                "YES" if report.get("association_eligible") else "NO"
            ),
            "status": report.get("status", ""),
            "severity": report.get("severity", ""),
            "reason": report.get("reason", ""),
        })

    return rows


def flatten_feedline_rows(reports):
    rows = []
    for report in reports:
        file_name = report.get("file_name", "")
        feeder_name = report.get("feeder_name", "")
        for row in report.get("feedline_rows", []):
            item = dict(row)
            item.pop("x", None)
            item.pop("y", None)
            item["file_name"] = file_name
            item["feeder_name"] = feeder_name
            rows.append(item)

    return sorted(
        rows,
        key=lambda row: (
            str(row.get("file_name", "")),
            _numeric_sequence(row.get("order_index", "")),
        ),
    )


def _write_csv(path, rows, fields, labels):
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([labels.get(field, field) for field in fields])
        for row in rows:
            writer.writerow([row.get(field, "") for field in fields])


def write_report(report, output_dir, domain_rules):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports = [report]

    _write_csv(
        output_dir/"rmu_summary.csv",
        flatten_rmu_rows(reports),
        RMU_FIELDS,
        RMU_LABELS,
    )
    device_fields = ["file_name"] + DEVICE_FIELDS
    _write_csv(
        output_dir/"device_validation.csv",
        flatten_device_rows(reports),
        device_fields,
        DEVICE_LABELS,
    )

    (output_dir/"report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    html_path = output_dir/"index.html"
    export_html_bundle(reports, html_path, domain_rules)
    return html_path



def export_csv_bundle(reports, export_path):
    export_path = Path(export_path)
    base = (
        export_path.with_suffix("")
        if export_path.suffix.lower() == ".csv"
        else export_path
    )

    if _is_feeder_reports(reports):
        feeder_path = base.with_name(
            base.name + "_馈线汇总.csv"
        )
        section_path = base.with_name(
            base.name + "_馈线段明细.csv"
        )
        _write_csv(
            feeder_path,
            flatten_feeder_rows(reports),
            FEEDER_FIELDS,
            FEEDER_LABELS,
        )
        _write_csv(
            section_path,
            flatten_feedline_rows(reports),
            FEEDLINE_FIELDS,
            FEEDLINE_LABELS,
        )
        return [feeder_path, section_path]

    rmu_path = base.with_name(base.name + "_环网柜汇总.csv")
    dev_path = base.with_name(base.name + "_设备明细.csv")

    _write_csv(
        rmu_path,
        flatten_rmu_rows(reports),
        RMU_FIELDS,
        RMU_LABELS,
    )
    _write_csv(
        dev_path,
        flatten_device_rows(reports),
        ["file_name"] + DEVICE_FIELDS,
        DEVICE_LABELS,
    )

    profile_path = base.with_name(
        base.name + "_环网柜档案.csv"
    )
    _write_csv(
        profile_path,
        flatten_rmu_profile_rows(reports),
        RMU_PROFILE_FIELDS,
        RMU_PROFILE_LABELS,
    )
    return [rmu_path, dev_path, profile_path]

def _table_html(
    rows,
    fields,
    labels,
    status_field=None,
    selectable=False,
):
    body = []
    for row in rows:
        cls = status_cls(str(row.get(status_field, ""))) if status_field else ""
        select_cell = (
            "<td class='select-col'>"
            "<input type='checkbox' class='row-check' "
            "title='选中后整行保持高亮，便于横向查看' "
            "onchange='toggleSelectedRow(this)'>"
            "</td>"
            if selectable else ""
        )
        body.append(
            f"<tr class='{cls}'>"
            + select_cell
            + "".join(
                f"<td>{esc(row.get(field,''))}</td>"
                for field in fields
            )
            + "</tr>"
        )

    select_header = (
        "<th class='select-col'>选择</th>"
        if selectable else ""
    )

    return (
        "<div class='scroll'><table><thead><tr>"
        + select_header
        + "".join(
            f"<th>{esc(labels.get(field,field))}</th>"
            for field in fields
        )
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def _export_rmu_html_bundle(reports, export_path, domain_rules):
    export_path = Path(export_path)
    rmu_rows = flatten_rmu_rows(reports)
    device_rows = flatten_device_rows(reports)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    is_operation_report = any(
        str(rmu.get("rmu_reason", "")).startswith(
            "ASSOCIATION_EXECUT"
        )
        for report in reports
        for rmu in report.get("rmu_results", [])
    )
    report_title = (
        "RMU 模型关联执行报告"
        if is_operation_report
        else "配网模型管理报告"
    )
    rmu_intro = (
        "本报告只展示本次用户勾选并执行的环网柜。"
        "未选中的环网柜不会进入本次执行报告。"
        if is_operation_report
        else (
            "环网柜汇总严格按照 G 文件环网柜序号排列，"
            "每个环网柜只展示一行。"
        )
    )
    device_intro = (
        "本表只展示本次用户勾选执行的设备。"
        "PASS 表示本次成功写回；FAIL 表示执行时数据库事实发生变化，"
        "该设备已跳过且未写回。"
        if is_operation_report
        else (
            "设备明细仅展示 G 文件实际存在的设备图元。"
        )
    )

    domain_rows = "".join(
        f"<tr><td>{esc(tag)}</td><td>{esc(rule['table_id'])}</td><td>{esc(rule['domain'])}</td></tr>"
        for tag, rule in domain_rules.items()
    )

    rmu_table = _table_html(
        rmu_rows,
        RMU_FIELDS,
        RMU_LABELS,
        "rmu_status",
        selectable=True,
    )
    device_fields = ["file_name"] + DEVICE_FIELDS
    device_table = _table_html(device_rows, device_fields, DEVICE_LABELS, "status", selectable=True)

    text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{esc(report_title)}</title>
<style>
:root {{
  --green:#008C6A;
  --green-dark:#006B52;
  --green-light:#E9F7F1;
  --border:#D3E3DC;
  --text:#17372E;
}}
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:var(--text)}}
header{{background:var(--green-dark);color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}}
.card{{background:white;border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th{{background:var(--green-dark);color:white;position:sticky;top:0}}
th,td{{border:1px solid var(--border);padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:650px}}
.pass{{background:#EAF8F2}}
.warn{{background:#FFF8DE}}
.relink{{background:#FFE8CC}}
.rmu-relink{{background:#F0E7FF}}
.blocked{{background:#EAF3FF}}
.fail{{background:#FFF0F0}}
tr.row-selected{{outline:3px solid #1976D2;outline-offset:-3px;font-weight:600}}
.select-col{{position:sticky;left:0;z-index:4;text-align:center!important;min-width:52px;max-width:52px;background:#F8FBFA!important}}
thead .select-col{{z-index:7;background:var(--green-dark)!important;color:white}}
.row-check{{width:17px;height:17px;cursor:pointer;accent-color:#1976D2}}
.status-list{{display:flex;flex-direction:column;gap:8px;max-width:1100px}}
.status-item{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;padding:9px 12px;border-radius:6px;border:1px solid var(--border)}}
.status-item strong{{white-space:nowrap}}
.status-item span{{line-height:1.55}}
.meta{{color:#D7EEE5}}
</style>
</head>
<body>
<header>
  <h1>{esc(report_title)}</h1>
  <div class="meta">软件：{esc(APP_NAME)}　版本：{esc(APP_VERSION)}　导出时间：{esc(now)}</div>
</header>
<main>
  <div class="card">
    <h2>设备模型关联规则</h2>
    <table>
      <thead><tr><th>G 图元类型</th><th>表号</th><th>域号</th></tr></thead>
      <tbody>{domain_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>状态颜色说明</h2>
    <div class="status-list">
      <div class="status-item pass">
        <strong>绿色 PASS</strong>
        <span>当前模型已关联到数据库当前正确设备，无需处理。</span>
      </div>
      <div class="status-item warn">
        <strong>黄色 UNLINKED</strong>
        <span>当前 G 图元尚未关联；数据库 RMU 和目标设备均唯一且符合 CODE/图上逻辑名称与环网柜归属规则，可以关联。</span>
      </div>
      <div class="status-item relink" style="background:#FFE8CC">
        <strong>橙色 RELINK</strong>
        <span>旧 KeyID、设备 ID、表号或 Domain 已过期/错误，或者旧设备被删除后重新创建；数据库当前目标设备仍唯一且符合规则，可以重新关联并覆盖旧模型。</span>
      </div>
      <div class="status-item rmu-relink" style="background:#F0E7FF">
        <strong>紫色 RMU_RELINK</strong>
        <span>当前 KeyID 指向了其他环网柜，但当前 RMU 唯一，并且本 RMU 内 CODE/图上逻辑名称已唯一确定正确设备；允许重新关联到当前环网柜。</span>
      </div>
      <div class="status-item blocked">
        <strong>蓝色 BLOCKED</strong>
        <span>需要人工确认的整体阻断场景。</span>
      </div>
      <div class="status-item fail">
        <strong>红色 FAIL</strong>
        <span>数据库当前事实无法安全确定目标，例如 RMU 0/多条、当前 RMU 内 CODE 0/多条、CODE 与图上逻辑名称不一致、目标设备不属于当前 RMU、Expected KeyID 或 BV_ID 无效。</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>环网柜汇总</h2>
    <p>{esc(rmu_intro)}</p>
    {rmu_table}
  </div>

  <div class="card">
    <h2>设备明细</h2><p>{esc(device_intro)}</p>
    {device_table}
  </div>
</main>
<script>
function toggleSelectedRow(cb) {{
  const row = cb.closest('tr');
  if (!row) return;
  if (cb.checked) {{
    row.classList.add('row-selected');
  }} else {{
    row.classList.remove('row-selected');
  }}
}}
</script>
</body>
</html>"""

    export_path.write_text(text, encoding="utf-8")
    return export_path

def _export_feeder_html_bundle(reports, export_path, domain_rules):
    export_path = Path(export_path)
    feeder_rows = flatten_feeder_rows(reports)
    feedline_rows = flatten_feedline_rows(reports)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    domain_rows = "".join(
        f"<tr><td>{esc(tag)}</td>"
        f"<td>{esc(rule['table_id'])}</td>"
        f"<td>{esc(rule['domain'])}</td></tr>"
        for tag, rule in domain_rules.items()
    )

    feeder_table = _table_html(
        feeder_rows,
        FEEDER_FIELDS,
        FEEDER_LABELS,
        "status",
        selectable=True,
    )
    feedline_table = _table_html(
        feedline_rows,
        FEEDLINE_FIELDS,
        FEEDLINE_LABELS,
        "status",
        selectable=True,
    )

    text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>馈线模型管理报告</title>
<style>
:root {{
  --green:#008C6A;
  --green-dark:#006B52;
  --border:#D3E3DC;
  --text:#17372E;
}}
body{{font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif;margin:0;background:#F3F7F5;color:var(--text)}}
header{{background:var(--green-dark);color:white;padding:24px 32px;border-bottom:5px solid #00B578}}
main{{padding:24px 30px}}
.card{{background:white;border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th{{background:var(--green-dark);color:white;position:sticky;top:0}}
th,td{{border:1px solid var(--border);padding:6px 8px;text-align:left;white-space:nowrap}}
.scroll{{overflow:auto;max-height:650px}}
.pass{{background:#EAF8F2}}
.warn{{background:#FFF8DE}}
.fail{{background:#FFF0F0}}
.info{{background:#EAF3FF}}
.row-selected td{{background:#DCEEFF !important;box-shadow:inset 0 1px #8AB8F5,inset 0 -1px #8AB8F5}}
.select-col{{width:42px;min-width:42px;text-align:center;position:sticky;left:0;z-index:3}}
th.select-col{{z-index:5;background:var(--green-dark)}}
td.select-col{{background:inherit}}
.row-check{{width:16px;height:16px;cursor:pointer}}
.status-list{{display:flex;flex-direction:column;gap:8px;max-width:1100px}}
.status-item{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;padding:9px 12px;border-radius:6px;border:1px solid var(--border)}}
.meta{{color:#D7EEE5}}
</style>
</head>
<body>
<header>
  <h1>馈线模型管理报告</h1>
  <div class="meta">软件：{esc(APP_NAME)}　版本：{esc(APP_VERSION)}　导出时间：{esc(now)}</div>
</header>
<main>
  <div class="card">
    <h2>馈线段模型规则</h2>
    <table>
      <thead><tr><th>G 图元类型</th><th>表号</th><th>域号</th></tr></thead>
      <tbody>{domain_rows}</tbody>
    </table>
    <p>馈线主表：13500 / dms_feeder_device。馈线段表：13503 / dms_section_device，默认域号 1；回写 voltype 使用目标馈线段 BV_ID。</p>
  </div>

  <div class="card">
    <h2>状态颜色说明</h2>
    <div class="status-list">
      <div class="status-item pass" style="background:#EAF8F2">
        <strong>绿色 PASS</strong>
        <span>当前 FeedLine 已经关联到本馈线下的数据库馈线段，表号/域号均正确。</span>
      </div>
      <div class="status-item warn" style="background:#FFF8DE">
        <strong>黄色 WARN</strong>
        <span>当前 FeedLine 尚未关联，但已经分配到可用数据库馈线段，可以在工作区勾选后执行模型关联。</span>
      </div>
      <div class="status-item fail" style="background:#FFF0F0">
        <strong>红色 FAIL</strong>
        <span>馈线名称无法唯一解析、当前 KeyID 不属于本馈线、表号/域号错误、数据库馈线段不足或其它硬错误。</span>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>馈线汇总</h2>
    <p>馈线归属不再依赖图上馈线名称。程序先构建 G 图连接拓扑，再使用“数据库唯一且已有正确模型证据”的环网柜作为可信参考。一个连接区域内可信环网柜的 FEEDER_ID 必须完全一致；若出现多个不同 FEEDER_ID，整个区域禁止自动关联并要求人工确认。未关联、数据库0/多条或已有错误模型的环网柜只报告，不参与馈线判定。</p>
    {feeder_table}
  </div>

  <div class="card">
    <h2>馈线段明细</h2>
    <p>每个拓扑连接区域确认唯一 FEEDER_ID 后，程序查询该 FEEDER_ID 下真实存在的 dms_section_device。已正确关联的 FeedLine 先占用对应数据库记录；旧关联错误或未关联的 FeedLine 再按从上到下、同高度从左到右排序，并从剩余数据库馈线段按自然序号从小到大依次分配。表格左侧复选框仅用于人工标记，勾选后整行持续高亮，不参与任何模型关联逻辑。</p>
    {feedline_table}
  </div>
</main>
<script>
function toggleSelectedRow(cb) {{
  const row = cb.closest('tr');
  if (!row) return;
  row.classList.toggle('row-selected', cb.checked);
}}
</script>
</body>
</html>"""

    export_path.write_text(text, encoding="utf-8")
    return export_path


def export_html_bundle(reports, export_path, domain_rules):
    if _is_feeder_reports(reports):
        return _export_feeder_html_bundle(
            reports,
            export_path,
            domain_rules,
        )
    return _export_rmu_html_bundle(
        reports,
        export_path,
        domain_rules,
    )

