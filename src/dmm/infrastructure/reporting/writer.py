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


DEVICE_FIELDS = [
    "rmu_name", "rmu_id",
    "object_type", "xml_id", "p_name_string", "graphical_name",
    "selected_name_source", "selected_device_name", "paired_breaker_name",
    "table_id", "table_name", "configured_domain", "match_mode",
    "db_match_count", "db_device_id", "db_code", "db_name",
    "g_file_feeder", "db_feeder_id", "db_feeder_name",
    "device_feeder_match", "device_feeder_reason",
    "db_combined_id", "db_bv_id",
    "expected_keyid", "expected_keyid_verified",
    "current_keyid", "current_device_id", "current_table_id", "current_domain",
    "current_table_name", "current_db_code", "current_db_name",
    "current_combined_id", "current_rmu_match",
    "model_linked", "model_link_correct", "model_link_status",
    "association_action", "writeback_needed",
    "association_ready", "status", "severity", "reason",
]

RMU_FIELDS = [
    "file_name", "frame_index", "frame_xml_id", "rmu_name",
    "rmu_status", "rmu_severity", "rmu_reason", "rmu_db_count", "db_record_index",
    "rmu_id", "code", "feeder_id",
    "file_feeder_hint", "feeder_table_id", "feeder_table_name",
    "feeder_db_name", "database_feeder_name", "feeder_match",
    "feeder_match_reason",
    "graph_name", "combined_type", "run_state", "device_count",
    "linked_correct_count", "unlinked_count", "linked_wrong_count",
    "association_eligible", "association_block_reasons", "inventory_issues",
    "db_integrity_issues",
]

DEVICE_LABELS = {
    "file_name": "G文件",
    "rmu_name": "环网柜名称",
    "rmu_id": "环网柜ID",
    "object_type": "G图元类型",
    "xml_id": "图元XML ID",
    "p_name_string": "用于校验的p_NameString",
    "graphical_name": "图上名称",
    "selected_name_source": "名称来源",
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
    "g_file_feeder": "G文件所属馈线",
    "db_feeder_id": "数据库设备馈线ID",
    "db_feeder_name": "数据库设备所属馈线",
    "device_feeder_match": "设备馈线是否正确",
    "device_feeder_reason": "设备馈线说明",
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
    "current_rmu_match": "当前模型环网柜ID是否正确",
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
    "rmu_status": "状态",
    "rmu_severity": "状态类型",
    "rmu_reason": "说明",
    "rmu_db_count": "数据库记录数",
    "db_record_index": "数据库记录序号",
    "rmu_id": "环网柜ID",
    "code": "CODE",
    "feeder_id": "馈线ID",
    "file_feeder_hint": "G文件馈线",
    "feeder_table_id": "馈线表号",
    "feeder_table_name": "馈线数据库表",
    "feeder_db_name": "馈线NAME",
    "database_feeder_name": "数据库馈线名称",
    "feeder_match": "馈线匹配",
    "feeder_match_reason": "馈线校验说明",
    "graph_name": "GRAPH_NAME",
    "combined_type": "COMBINED_TYPE",
    "run_state": "RUN_STATE",
    "device_count": "已处理图元数",
    "linked_correct_count": "已正确关联设备数",
    "unlinked_count": "未关联设备数",
    "linked_wrong_count": "关联错误设备数",
    "association_eligible": "RMU可关联",
    "association_block_reasons": "关联阻断原因",
    "inventory_issues": "G图元匹配问题",
    "db_integrity_issues": "数据库匹配问题",
}


def esc(value):
    return html.escape("" if value is None else str(value))


def status_cls(status):
    return {
        "PASS": "pass",
        "WARN": "warn",
        "FEEDER": "feeder",
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
    rows = []

    # Preserve report / G-file order.
    for report in reports:
        file_name = report.get("file_name", "")

        # Within a G file, RMUs are ordered ONLY by frame_index.
        rmu_results = sort_rmu_results_by_sequence(
            report.get("rmu_results", [])
        )

        for rmu in rmu_results:
            records = list(rmu.get("rmu_records") or [])
            base = {
                "file_name": file_name,
                "frame_index": rmu.get("frame_index", ""),
                "frame_xml_id": rmu.get("frame_xml_id", ""),
                "rmu_name": rmu.get("rmu_name", ""),
                "rmu_status": rmu.get("rmu_status", ""),
                "rmu_severity": rmu.get("rmu_severity", ""),
                "rmu_reason": rmu.get("rmu_reason", ""),
                "rmu_db_count": rmu.get("rmu_db_count", 0),
                "file_feeder_hint": rmu.get("file_feeder_hint", ""),
                "database_feeder_name": rmu.get("database_feeder_name", ""),
                "feeder_match": rmu.get("feeder_match", ""),
                "feeder_match_reason": rmu.get("feeder_match_reason", ""),
                "feeder_table_id": (
                    (rmu.get("feeder") or {}).get("_table_id", 13500)
                    if rmu.get("feeder") else 13500
                ),
                "feeder_table_name": (
                    (rmu.get("feeder") or {}).get(
                        "_table_name",
                        "dms_feeder_device",
                    )
                ),
                "feeder_db_name": (
                    (rmu.get("feeder") or {}).get("name", "")
                ),
                "device_count": len([
                    d for d in rmu.get("device_rows", [])
                    if d.get("xml_id")
                ]),
                "linked_correct_count": rmu.get("linked_correct_count", 0),
                "unlinked_count": rmu.get("unlinked_count", 0),
                "linked_wrong_count": rmu.get("linked_wrong_count", 0),
                "association_eligible": "YES" if rmu.get("association_eligible") else "NO",
                "association_block_reasons": "; ".join(
                    rmu.get("association_block_reasons", [])
                ),
                "inventory_issues": "; ".join(
                    rmu.get("inventory_issues", [])
                ),
                "db_integrity_issues": "; ".join(
                    rmu.get("db_integrity_issues", [])
                ),
            }

            # Preserve database record order within the same RMU.
            if records:
                for idx, rec in enumerate(records, start=1):
                    row = dict(base)
                    row.update({
                        "db_record_index": idx,
                        "rmu_id": rec.get("id", ""),
                        "code": rec.get("code", ""),
                        "feeder_id": rec.get("feeder_id", ""),
                        "graph_name": rec.get("graph_name", ""),
                        "combined_type": rec.get("combined_type", ""),
                        "run_state": rec.get("run_state", ""),
                    })
                    rows.append(row)
            else:
                row = dict(base)
                row.update({
                    "db_record_index": "",
                    "rmu_id": rmu.get("rmu_id", ""),
                    "code": "",
                    "feeder_id": rmu.get("feeder_id", ""),
                    "graph_name": rmu.get("graph_name_db", ""),
                    "combined_type": "",
                    "run_state": "",
                })
                rows.append(row)

    return rows


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
                rows.append(row)

    return rows


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
    base = export_path.with_suffix("") if export_path.suffix.lower() == ".csv" else export_path

    rmu_path = base.with_name(base.name + "_环网柜汇总.csv")
    dev_path = base.with_name(base.name + "_设备明细.csv")

    _write_csv(rmu_path, flatten_rmu_rows(reports), RMU_FIELDS, RMU_LABELS)
    _write_csv(dev_path, flatten_device_rows(reports), ["file_name"]+DEVICE_FIELDS, DEVICE_LABELS)
    return [rmu_path, dev_path]


def _table_html(rows, fields, labels, status_field=None):
    body = []
    for row in rows:
        cls = status_cls(str(row.get(status_field, ""))) if status_field else ""
        body.append(
            f"<tr class='{cls}'>"
            + "".join(f"<td>{esc(row.get(field,''))}</td>" for field in fields)
            + "</tr>"
        )

    return (
        "<div class='scroll'><table><thead><tr>"
        + "".join(f"<th>{esc(labels.get(field,field))}</th>" for field in fields)
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div>"
    )


def export_html_bundle(reports, export_path, domain_rules):
    export_path = Path(export_path)
    rmu_rows = flatten_rmu_rows(reports)
    device_rows = flatten_device_rows(reports)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    domain_rows = "".join(
        f"<tr><td>{esc(tag)}</td><td>{esc(rule['table_id'])}</td><td>{esc(rule['domain'])}</td></tr>"
        for tag, rule in domain_rules.items()
    )

    rmu_table = _table_html(rmu_rows, RMU_FIELDS, RMU_LABELS, "rmu_status")
    device_fields = ["file_name"] + DEVICE_FIELDS
    device_table = _table_html(device_rows, device_fields, DEVICE_LABELS, "status")

    text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>配网模型管理工具报告</title>
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
.pass{{background:#EAF8F2}} .warn{{background:#FFF8DE}} .feeder{{background:#FFE8CC}} .blocked{{background:#EAF3FF}} .fail{{background:#FFF0F0}}
.meta{{color:#D7EEE5}}
</style>
</head>
<body>
<header>
  <h1>配网模型管理报告</h1>
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
    <p>
      <span style="background:#EAF8F2;padding:4px 10px">绿色 PASS：校验正常</span>
      <span style="background:#FFF8DE;padding:4px 10px;margin-left:8px">黄色 WARN：未关联，但满足自动关联条件</span>
      <span style="background:#FFE8CC;padding:4px 10px;margin-left:8px">橙色 FEEDER：馈线不一致，禁止自动关联</span>
      <span style="background:#EAF3FF;padding:4px 10px;margin-left:8px">蓝色 BLOCKED：已有人工关联，但环网柜不唯一，禁止自动关联</span>
      <span style="background:#FFF0F0;padding:4px 10px;margin-left:8px">红色 FAIL：硬错误</span>
    </p>
  </div>

  <div class="card">
    <h2>环网柜汇总</h2>
    <p>数据库存在重复记录时，每一条环网柜 ID 均单独展示；环网柜本身不唯一时，该柜内已有模型关联一律不能判定为正确。</p>
    {rmu_table}
  </div>

  <div class="card">
    <h2>设备明细</h2><p>设备明细仅展示 G 文件中的设备图元；每个图元显示其唯一匹配到的数据库设备、G文件所属馈线、数据库设备所属馈线、当前 KeyID 及是否需要回写。数据库中与 G 图元 CODE 无关的其它设备不参与校验，也不进入设备明细。</p>
    {device_table}
  </div>
</main>
</body>
</html>"""

    export_path.write_text(text, encoding="utf-8")
    return export_path
