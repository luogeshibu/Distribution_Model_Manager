from __future__ import annotations

import csv
import html
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from dmm.domain.feeder.ownership import FeederOwnershipResolver
from dmm.domain.graphics_cleanup.rmu_feeder_topology import (
    _apply_source_entry_nop_rule,
    _exact_nop_boundaries,
    _neighbor_reachability_labels,
    _propagate_feeder_reachability,
    _rmu_name_map,
    _rmu_port_index,
    _source_anchors,
    _txt,
)
from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser


@dataclass
class FeedlineFeederTopologyResult:
    html_path: Path
    feedline_csv_path: Path
    nop_csv_path: Path
    file_count: int
    feedline_count: int
    confirmed_count: int
    conflict_count: int
    unresolved_count: int
    source_feeder_count: int
    nop_boundary_count: int


def _esc(value) -> str:
    return html.escape(_txt(value), quote=True)


def _write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _html_table(title: str, rows: list[dict], columns: list[tuple[str, str]]) -> str:
    header = "".join(f"<th>{_esc(label)}</th>" for _, label in columns)
    body = []
    for row in rows:
        body.append(
            "<tr>" + "".join(f"<td>{_esc(row.get(key, ''))}</td>" for key, _ in columns) + "</tr>"
        )
    if not body:
        body.append(f"<tr><td colspan='{len(columns)}'>无记录</td></tr>")
    return (
        f"<section><h2>{_esc(title)}</h2><div class='table-wrap'><table>"
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody>"
        f"</table></div></section>"
    )


def analyze_feedline_feeder_topology_file(path: Path):
    """Resolve FeedLine -> feeder using the proven Makkah NOP topology rules.

    This is deliberately a separate read-only analysis from the RMU feeder
    topology module.  It reuses the same source discovery, graph building and
    red-NOP switch boundaries, but its business output is only FeedLine feeder
    ownership.  It never changes the RMU analysis logic and never writes the G
    file or Oracle.
    """
    path = Path(path)
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    frames = list(parser.find_rmu_frames(parsed))
    rmu_names = _rmu_name_map(parser, parsed, frames)

    source_rows, source_by_breaker_all = _source_anchors(parsed)
    boundary_nodes, nop_rows = _exact_nop_boundaries(parser, parsed, frames, rmu_names)
    _by_id, adjacency, repaired_count = FeederOwnershipResolver._build_graph(parsed)

    port_index = _rmu_port_index(parser, parsed, frames, rmu_names)
    source_by_breaker, source_entry_nop_labels, direct_source_by_port = _apply_source_entry_nop_rule(
        source_rows, source_by_breaker_all, adjacency, port_index, boundary_nodes
    )
    labels_by_node = _propagate_feeder_reachability(
        source_by_breaker, adjacency, boundary_nodes
    )

    nop_by_switch = {}
    for row in nop_rows:
        switch_id = _txt(row.get("switch_xml_id"))
        labels, neighbor_nodes = (
            _neighbor_reachability_labels(adjacency, switch_id, labels_by_node)
            if switch_id else (set(), set())
        )
        row["file_name"] = path.name
        row["feeder_labels"] = " | ".join(sorted(labels))
        row["neighbor_node_count"] = len(neighbor_nodes)
        row["source_entry_feeders"] = " | ".join(
            sorted(direct_source_by_port.get(switch_id, set()))
        ) if switch_id else ""
        row["boundary_status"] = (
            "CONFIRMED_BOUNDARY" if len(labels) >= 2 else
            "PARTIAL_BOUNDARY" if len(labels) == 1 else
            "UNRESOLVED_BOUNDARY"
        ) if row.get("status") == "NOP_BOUNDARY" else _txt(row.get("status"))
        if switch_id:
            nop_by_switch[switch_id] = row

    feedline_rows = []
    for obj in parsed.objects:
        if obj.tag != "FeedLine":
            continue
        xml_id = _txt(obj.xml_id)
        labels = set(labels_by_node.get(xml_id, set()))
        adjacent_nop_ids = sorted(
            neighbor for neighbor in adjacency.get(xml_id, set())
            if neighbor in boundary_nodes
        )
        nop_labels = []
        for switch_id in adjacent_nop_ids:
            info = nop_by_switch.get(switch_id, {})
            rmu_name = _txt(info.get("rmu_name")) or "?"
            switch_name = _txt(info.get("switch_name")) or switch_id
            nop_labels.append(f"{rmu_name}.{switch_name}")

        if len(labels) == 1:
            status = "CONFIRMED"
            primary = next(iter(labels))
            reason = (
                f"从主网馈线 {primary} 沿 link/node_area 与严格几何补链可达该 FeedLine，"
                "且传播过程中未穿过红色 NOP 开关。"
            )
        elif len(labels) > 1:
            status = "CONFLICT"
            primary = ""
            reason = (
                "同一 FeedLine 可由多条主网馈线到达，说明当前拓扑在红色 NOP 断点规则下仍存在多源冲突；"
                "不自动猜测所属馈线。"
            )
        else:
            status = "UNRESOLVED"
            primary = ""
            reason = (
                "没有任何有效主网馈线能够在不穿过红色 NOP 开关的前提下到达该 FeedLine；"
                "不按几何最近馈线猜测。"
            )
        if nop_labels:
            reason += " 该 FeedLine 直接邻接红色 NOP 边界：" + "、".join(nop_labels) + "。"

        feedline_rows.append({
            "file_name": path.name,
            "feedline_xml_id": xml_id,
            "status": status,
            "primary_feeder": primary,
            "candidate_feeders": " | ".join(sorted(labels)),
            "adjacent_nop_ports": " | ".join(nop_labels),
            "adjacent_nop_switch_xml_ids": " | ".join(adjacent_nop_ids),
            "topology_degree": len(adjacency.get(xml_id, set())),
            "link": _txt(obj.attrs.get("link")),
            "node_area": _txt(obj.attrs.get("node_area")),
            "reason": reason,
        })

    feedline_rows.sort(key=lambda row: (row["file_name"], row["feedline_xml_id"]))
    summary = {
        "file_name": path.name,
        "source_feeder_labels": sorted(set(source_by_breaker.values())),
        "source_entry_nop_feeder_labels": sorted(source_entry_nop_labels),
        "feedline_count": len(feedline_rows),
        "confirmed_count": sum(1 for row in feedline_rows if row["status"] == "CONFIRMED"),
        "conflict_count": sum(1 for row in feedline_rows if row["status"] == "CONFLICT"),
        "unresolved_count": sum(1 for row in feedline_rows if row["status"] == "UNRESOLVED"),
        "nop_boundary_count": len(boundary_nodes),
        "strict_geometry_repair_count": repaired_count,
    }
    return {
        "summary": summary,
        "source_rows": source_rows,
        "nop_rows": nop_rows,
        "feedline_rows": feedline_rows,
    }


def _write_html(path: Path, analyses: list[dict]):
    blocks = []
    for item in analyses:
        s = item["summary"]
        feeders = "、".join(s["source_feeder_labels"]) or "-"
        entry_stops = "、".join(s.get("source_entry_nop_feeder_labels", [])) or "-"
        blocks.append(
            "<article>"
            f"<h1>{_esc(s['file_name'])}</h1>"
            "<div class='cards'>"
            f"<div><b>识别主网馈线</b><span>{_esc(feeders)}</span></div>"
            f"<div><b>入口支路遇NOP</b><span>{_esc(entry_stops)}</span></div>"
            f"<div><b>FeedLine</b><span>{s['feedline_count']}</span></div>"
            f"<div><b>确认所属</b><span>{s['confirmed_count']}</span></div>"
            f"<div><b>冲突</b><span>{s['conflict_count']}</span></div>"
            f"<div><b>未确定</b><span>{s['unresolved_count']}</span></div>"
            f"<div><b>红色NOP边界</b><span>{s['nop_boundary_count']}</span></div>"
            f"<div><b>严格补链</b><span>{s['strict_geometry_repair_count']}</span></div>"
            "</div>"
        )
        blocks.append(_html_table("主网馈线传播入口", item["source_rows"], [
            ("feeder_label", "馈线标题"), ("frame_xml_id", "Bay框XML"),
            ("breaker_xml_id", "CBreaker XML"), ("text_xml_id", "标题Text XML"),
            ("distance", "标题距离"), ("first_rmu_name", "首个直连RMU"),
            ("entry_port_name", "主网入线Y/Q"), ("entry_port_xml_id", "入线开关XML"),
            ("entry_port_is_nop", "入线开关是否NOP"), ("candidate_status", "传播状态"),
            ("candidate_reason", "判定说明"),
        ]))
        blocks.append(_html_table("红色NOP边界", item["nop_rows"], [
            ("nop_text", "NOP"), ("nop_text_xml_id", "NOP Text XML"),
            ("rmu_name", "所属RMU"), ("frame_xml_id", "RMU框XML"),
            ("switch_name", "NOP对应Y/Q开关"), ("switch_xml_id", "开关XML"),
            ("nop_side", "NOP相对RMU方位"), ("alignment_axis", "对齐轴"),
            ("alignment_delta", "对齐差"), ("switch_distance", "NOP到开关距离"),
            ("feeder_labels", "边界两侧可达馈线"), ("boundary_status", "边界状态"),
        ]))
        blocks.append(_html_table("FeedLine所属馈线", item["feedline_rows"], [
            ("feedline_xml_id", "FeedLine XML"), ("status", "状态"),
            ("primary_feeder", "所属馈线"), ("candidate_feeders", "候选馈线"),
            ("adjacent_nop_ports", "直接邻接NOP端口"),
            ("topology_degree", "拓扑邻接数"), ("reason", "判定说明"),
        ]))
        blocks.append("</article>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>馈线段所属馈线分析报告</title><style>
body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#16332c;background:#f7faf8}
article{background:#fff;border:1px solid #dbe8e2;border-radius:12px;padding:20px;margin-bottom:24px}
h1{margin:0 0 14px;color:#075f4a}h2{font-size:17px;margin:24px 0 10px;color:#075f4a}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px}
.cards div{border:1px solid #dbe8e2;background:#f3f9f6;border-radius:8px;padding:10px}.cards b{display:block;font-size:12px;color:#567168}.cards span{display:block;margin-top:4px;font-weight:600}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d9e5df;padding:7px 8px;text-align:left;white-space:nowrap}th{background:#eaf5f0;color:#174f42;position:sticky;top:0}
.note{padding:12px 14px;border-left:4px solid #0b7b60;background:#edf8f4;margin-bottom:18px}
</style></head><body><div class='note'>本模块独立分析 FeedLine 属于哪条主网馈线，不修改已经验证通过的“环网柜馈线拓扑分析”逻辑。分析复用同一套主网馈线源、link/node_area、严格几何补链和红色NOP端口级断点规则：线路可多路传播，只有实际走到红色NOP对应Y*/Q*开关的那一路停止，其它支路继续。每条FeedLine若仅被一个有效主网馈线到达则判定CONFIRMED；多馈线同时可达为CONFLICT；无可达馈线为UNRESOLVED。模块只读G文件，不修改G，也不连接、查询或写入Oracle数据库。</div>"""
        + "".join(blocks)
        + "</body></html>",
        encoding="utf-8",
    )


def process_feedline_feeder_topology_analysis(
    files: Iterable[Path],
    report_dir: Path,
    *,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> FeedlineFeederTopologyResult:
    log = log or (lambda _msg: None)
    progress = progress or (lambda _p, _m="": None)
    paths = [Path(p) for p in files]
    if not paths:
        raise ValueError("请至少选择一个 G 文件。")
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    analyses = []
    all_feedlines: list[dict] = []
    all_nops: list[dict] = []
    for idx, path in enumerate(paths, start=1):
        progress(max(1, int((idx - 1) * 90 / len(paths))), f"正在分析 {path.name}")
        analysis = analyze_feedline_feeder_topology_file(path)
        analyses.append(analysis)
        all_feedlines.extend(analysis["feedline_rows"])
        all_nops.extend(analysis["nop_rows"])
        s = analysis["summary"]
        log(
            f"[{path.name}] 主网馈线={','.join(s['source_feeder_labels']) or '-'}；"
            f"FeedLine={s['feedline_count']}；确认={s['confirmed_count']}；"
            f"冲突={s['conflict_count']}；未确定={s['unresolved_count']}；"
            f"红色NOP边界={s['nop_boundary_count']}"
        )

    feedline_csv = report_dir / "feedline_feeder_topology.csv"
    nop_csv = report_dir / "feedline_nop_boundary_summary.csv"
    html_path = report_dir / "feedline_feeder_topology_report.html"
    _write_csv(feedline_csv, all_feedlines, [
        "file_name", "feedline_xml_id", "status", "primary_feeder",
        "candidate_feeders", "adjacent_nop_ports", "adjacent_nop_switch_xml_ids",
        "topology_degree", "link", "node_area", "reason",
    ])
    _write_csv(nop_csv, all_nops, [
        "file_name", "nop_text", "nop_text_xml_id", "rmu_name", "frame_xml_id",
        "switch_name", "switch_xml_id", "nop_side", "alignment_axis",
        "alignment_delta", "switch_distance", "feeder_labels", "boundary_status",
    ])
    _write_html(html_path, analyses)
    progress(100, "馈线段所属馈线分析完成")

    return FeedlineFeederTopologyResult(
        html_path=html_path,
        feedline_csv_path=feedline_csv,
        nop_csv_path=nop_csv,
        file_count=len(paths),
        feedline_count=len(all_feedlines),
        confirmed_count=sum(1 for row in all_feedlines if row["status"] == "CONFIRMED"),
        conflict_count=sum(1 for row in all_feedlines if row["status"] == "CONFLICT"),
        unresolved_count=sum(1 for row in all_feedlines if row["status"] == "UNRESOLVED"),
        source_feeder_count=len({
            feeder
            for analysis in analyses
            for feeder in analysis["summary"]["source_feeder_labels"]
        }),
        nop_boundary_count=sum(
            int(analysis["summary"]["nop_boundary_count"])
            for analysis in analyses
        ),
    )
