from __future__ import annotations

import csv
import html
import re
import time
from dataclasses import dataclass
from pathlib import Path

from dmm.domain.graphics_cleanup.jeddah_topology_connectivity import (
    JeddahTopologyConnectivityResult,
    repair_jeddah_topology_connectivity,
)
from g_file_studio.models import InputMode, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs


@dataclass(frozen=True)
class WholeGraphTopologySettings:
    source_path: Path
    input_mode: InputMode
    output_dir: Path


def _safe_folder_name(index: int, source: Path) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", source.name).strip("._") or "g_file"
    return f"{index:03d}_{safe}"


def _relative_href(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        value = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        value = path.resolve().as_uri()
    return html.escape(value, quote=True)


def _write_batch_summary_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "index",
        "file",
        "status",
        "line_count",
        "candidate_count",
        "repair_count",
        "geometry_repair_count",
        "topology_link_repair_count",
        "remaining_candidate_count",
        "unresolved_count",
        "elapsed_seconds",
        "report_html",
        "report_csv",
        "before_svg",
        "after_svg",
        "fixed_g",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_batch_summary_html(path: Path, rows: list[dict], *, elapsed_seconds: float) -> None:
    succeeded = [row for row in rows if row.get("status") != "FAILED"]
    failed = [row for row in rows if row.get("status") == "FAILED"]
    needs_review = [
        row
        for row in succeeded
        if int(row.get("unresolved_count", 0) or 0) > 0
        or int(row.get("remaining_candidate_count", 0) or 0) > 0
    ]
    total_repairs = sum(int(row.get("repair_count", 0) or 0) for row in succeeded)
    total_lines = sum(int(row.get("line_count", 0) or 0) for row in succeeded)

    table_rows: list[str] = []
    for row in rows:
        status = str(row.get("status", ""))
        report_href = str(row.get("report_html_href", "") or "")
        before_href = str(row.get("before_svg_href", "") or "")
        after_href = str(row.get("after_svg_href", "") or "")
        fixed_href = str(row.get("fixed_g_href", "") or "")
        report_cell = f"<a href='{report_href}'>单文件报告</a>" if report_href else "-"
        before_cell = f"<a href='{before_href}'>修复前 / 问题位置</a>" if before_href else "-"
        after_cell = f"<a href='{after_href}'>修复后拓扑</a>" if after_href else "-"
        fixed_cell = f"<a href='{fixed_href}'>修复后 G</a>" if fixed_href else "无需生成"
        error = html.escape(str(row.get("error", "") or ""))
        if error:
            error = f"<div class='error'>{error}</div>"
        table_rows.append(
            "<tr>"
            f"<td>{int(row.get('index', 0) or 0)}</td>"
            f"<td><code>{html.escape(str(row.get('file', '')))}</code>{error}</td>"
            f"<td class='status {status.lower()}'>{html.escape(status)}</td>"
            f"<td>{row.get('line_count', '')}</td>"
            f"<td>{row.get('candidate_count', '')}</td>"
            f"<td>{row.get('repair_count', '')}</td>"
            f"<td>{row.get('unresolved_count', '')}</td>"
            f"<td>{row.get('remaining_candidate_count', '')}</td>"
            f"<td>{row.get('elapsed_seconds', '')}</td>"
            f"<td>{report_cell}</td>"
            f"<td>{before_cell}</td>"
            f"<td>{after_cell}</td>"
            f"<td>{fixed_cell}</td>"
            "</tr>"
        )

    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><title>吉达整图拓扑连接批量汇总</title>"
        "<style>body{font-family:Arial,'Microsoft YaHei',sans-serif;margin:24px;color:#1f2937}"
        "h1{font-size:22px}.summary{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.card{background:#f8fafc;"
        "border:1px solid #dbe4ea;border-radius:8px;padding:10px 14px;min-width:130px}.num{font-size:22px;font-weight:700}"
        ".note{background:#eef8f4;border-left:4px solid #0a8f68;padding:12px;margin:12px 0}"
        "table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #d1d5db;padding:6px;vertical-align:top}"
        "th{background:#f3f4f6;position:sticky;top:0}.failed{color:#b91c1c;font-weight:700}.review{color:#b45309;font-weight:700}"
        ".ok{color:#047857;font-weight:700}.error{color:#b91c1c;margin-top:4px;max-width:520px;white-space:pre-wrap}"
        "code{font-family:Consolas,monospace}a{color:#0369a1}</style></head><body>"
        "<h1>吉达整图拓扑连接检查 / 自动修复 — 批量汇总</h1>"
        "<div class='note'><b>处理规则：</b>逐个 G 文件独立检查、独立修复、独立生成报告；"
        "不判断馈线、不识别 NOP、不读取 Bus 馈线名、不连接数据库。某一个文件失败不会中断后续文件。</div>"
        "<div class='summary'>"
        f"<div class='card'><div>输入文件</div><div class='num'>{len(rows)}</div></div>"
        f"<div class='card'><div>成功处理</div><div class='num'>{len(succeeded)}</div></div>"
        f"<div class='card'><div>处理失败</div><div class='num'>{len(failed)}</div></div>"
        f"<div class='card'><div>需人工确认</div><div class='num'>{len(needs_review)}</div></div>"
        f"<div class='card'><div>线路对象</div><div class='num'>{total_lines}</div></div>"
        f"<div class='card'><div>自动修复</div><div class='num'>{total_repairs}</div></div>"
        f"<div class='card'><div>总耗时</div><div class='num'>{elapsed_seconds:.2f}s</div></div>"
        "</div>"
        "<table><thead><tr><th>#</th><th>G 文件</th><th>状态</th><th>线路对象</th><th>候选断点</th>"
        "<th>自动修复</th><th>待人工确认</th><th>修复后剩余</th><th>耗时(s)</th><th>单文件报告</th>"
        "<th>修复前拓扑 / 问题位置</th><th>修复后拓扑</th><th>修复后 G</th>"
        "</tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table></body></html>",
        encoding="utf-8",
    )


def _result_row(index: int, source: Path, result: JeddahTopologyConnectivityResult, report_root: Path) -> dict:
    status = "OK"
    if result.unresolved_count or result.remaining_candidate_count:
        status = "REVIEW"
    return {
        "index": index,
        "file": source.name,
        "status": status,
        "line_count": result.line_count,
        "candidate_count": result.candidate_count,
        "repair_count": result.repair_count,
        "geometry_repair_count": result.geometry_repair_count,
        "topology_link_repair_count": result.topology_link_repair_count,
        "remaining_candidate_count": result.remaining_candidate_count,
        "unresolved_count": result.unresolved_count,
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "report_html": str(result.html_path),
        "report_csv": str(result.csv_path),
        "before_svg": str(result.before_svg_path),
        "after_svg": str(result.after_svg_path),
        "fixed_g": str(result.fixed_g_path or ""),
        "report_html_href": _relative_href(result.html_path, report_root),
        "before_svg_href": _relative_href(result.before_svg_path, report_root),
        "after_svg_href": _relative_href(result.after_svg_path, report_root),
        "fixed_g_href": _relative_href(result.fixed_g_path, report_root),
        "error": "",
    }


def process_whole_graph_topology(
    settings: WholeGraphTopologySettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    """Check and repair Jeddah G-file connection continuity, one file at a time.

    Single-file input keeps the compact one-file output layout. Directory/SSH
    snapshot input may contain any number of G files. Every file is processed
    independently; batch runs create one report per file plus a summary HTML/CSV.
    """
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    report_root = Path(settings.output_dir) / "whole_graph_topology_report"
    report_root.mkdir(parents=True, exist_ok=True)
    batch_mode = len(files) > 1
    batch_start = time.perf_counter()
    rows: list[dict] = []
    output_files: list[Path] = []
    warnings: list[str] = []

    log(
        f"[整图拓扑] 共发现 {len(files)} 个 G 文件；"
        + ("将逐个检查/修复，并生成单文件报告 + 总汇总报告。" if batch_mode else "开始单文件检查/修复。")
    )

    for index, source in enumerate(files, start=1):
        log(f"\n===== [{index}/{len(files)}] {source.name} =====")
        per_file_dir = report_root if not batch_mode else report_root / "files" / _safe_folder_name(index, source)
        per_file_dir.mkdir(parents=True, exist_ok=True)

        def topology_progress(percent: int, message: str = "") -> None:
            # Reserve the final 2% for writing a batch summary. The mapping makes
            # a 50-file run advance smoothly instead of restarting at 0 for each G.
            overall = int((((index - 1) + max(0, min(100, int(percent))) / 100.0) / len(files)) * 98)
            if message:
                log(f"[{index}/{len(files)}][{int(percent):3d}%] {message}")
            if progress is not None:
                progress(overall)

        try:
            result = repair_jeddah_topology_connectivity(
                source,
                per_file_dir,
                log=log,
                progress=topology_progress,
            )
            row = _result_row(index, source, result, report_root)
            rows.append(row)
            output_files.extend([result.html_path, result.csv_path, result.before_svg_path, result.after_svg_path])
            if result.fixed_g_path is not None:
                output_files.append(result.fixed_g_path)
            if result.unresolved_count:
                warnings.append(
                    f"{source.name}: 有 {result.unresolved_count} 处断点附近存在同等级候选，"
                    "无法唯一判断，未自动修改。"
                )
            if result.remaining_candidate_count:
                warnings.append(
                    f"{source.name}: 自动修复后仍检测到 {result.remaining_candidate_count} 处安全阈值内唯一近邻断点。"
                )
        except Exception as exc:  # one bad G must not stop a directory/SSH batch
            if not batch_mode:
                raise
            message = f"{type(exc).__name__}: {exc}"
            log(f"[文件处理失败] {source.name}: {message}")
            rows.append({
                "index": index,
                "file": source.name,
                "status": "FAILED",
                "line_count": "",
                "candidate_count": "",
                "repair_count": "",
                "geometry_repair_count": "",
                "topology_link_repair_count": "",
                "remaining_candidate_count": "",
                "unresolved_count": "",
                "elapsed_seconds": "",
                "report_html": "",
                "report_csv": "",
                "before_svg": "",
                "after_svg": "",
                "fixed_g": "",
                "report_html_href": "",
                "before_svg_href": "",
                "after_svg_href": "",
                "fixed_g_href": "",
                "error": message,
            })
            warnings.append(f"{source.name}: 处理失败，已跳过并继续后续文件。{message}")

    if progress is not None:
        progress(98)

    elapsed = time.perf_counter() - batch_start
    failed_count = sum(1 for row in rows if row.get("status") == "FAILED")
    succeeded_rows = [row for row in rows if row.get("status") != "FAILED"]

    if batch_mode:
        summary_csv = report_root / "jeddah_topology_batch_summary.csv"
        summary_html = report_root / "jeddah_topology_batch_summary.html"
        _write_batch_summary_csv(summary_csv, rows)
        _write_batch_summary_html(summary_html, rows, elapsed_seconds=elapsed)
        # Put the two batch entry points first in the run output/log.
        output_files = [summary_html, summary_csv] + output_files
        html_report = summary_html
        log(f"\n[批量汇总] {summary_html}")
        log(f"[批量完成] 成功 {len(succeeded_rows)}/{len(files)}，失败 {failed_count}，总耗时 {elapsed:.2f}s。")
    else:
        html_report = Path(str(rows[0].get("report_html", ""))) if rows else report_root / "jeddah_topology_connection_report.html"

    if progress is not None:
        progress(100)

    total_repairs = sum(int(row.get("repair_count", 0) or 0) for row in succeeded_rows)
    total_candidates = sum(int(row.get("candidate_count", 0) or 0) for row in succeeded_rows)
    total_unresolved = sum(int(row.get("unresolved_count", 0) or 0) for row in succeeded_rows)
    total_remaining = sum(int(row.get("remaining_candidate_count", 0) or 0) for row in succeeded_rows)
    total_lines = sum(int(row.get("line_count", 0) or 0) for row in succeeded_rows)

    return ProcessingResult(
        success=failed_count == 0,
        output_files=output_files,
        warnings=warnings,
        statistics={
            "输入 G 文件数": len(files),
            "成功处理": len(succeeded_rows),
            "处理失败": failed_count,
            "线路对象合计": total_lines,
            "断点候选合计": total_candidates,
            "自动修复合计": total_repairs,
            "待人工确认合计": total_unresolved,
            "修复后剩余唯一断点合计": total_remaining,
            "总耗时（秒）": round(elapsed, 2),
            "汇总/主报告": str(html_report),
            "_html_report": str(html_report),
        },
    )
