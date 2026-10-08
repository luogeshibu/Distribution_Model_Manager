from __future__ import annotations

import csv
import html
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .g_native_svg_renderer import GRenderStats, render_g_root_to_svg


# Jeddah rule: this module does NOT identify feeders, NOPs, RMUs, Bus labels,
# or query any database.  It only repairs broken graphic/electrical continuity
# already visible in the G file.  It deliberately treats tiny ConnectLine↔ConnectLine
# splits differently from the ~18G open-contact gaps intentionally used inside
# switch symbols.
NETWORK_LINE_TAGS = {"ConnectLine", "FeedLine", "Bus", "ACLine"}
MAX_AUTO_GAP = 25.0
CONNECTLINE_TO_CONNECTLINE_MAX_GAP = 3.0
AMBIGUITY_MARGIN = 2.0
GEOMETRY_EPSILON = 0.01
GRID_CELL_SIZE = 32.0


@dataclass(frozen=True)
class EndpointEntry:
    element_id: str
    tag: str
    endpoint_index: int
    point: tuple[float, float]
    element: ET.Element


@dataclass
class JeddahTopologyConnectivityResult:
    html_path: Path
    csv_path: Path
    before_svg_path: Path
    after_svg_path: Path
    fixed_g_path: Path | None
    source_file: Path
    line_count: int
    dangling_endpoint_count_before: int
    candidate_count: int
    repair_count: int
    geometry_repair_count: int
    topology_link_repair_count: int
    remaining_candidate_count: int
    unresolved_count: int
    elapsed_seconds: float


def _local_name(tag: str) -> str:
    return str(tag).split("}", 1)[-1]


def _txt(value: object) -> str:
    return "" if value is None else str(value).strip()


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _fmt(value: float) -> str:
    if abs(value - round(value)) <= 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _points(element: ET.Element) -> list[tuple[float, float]]:
    raw = _txt(element.get("d"))
    if not raw:
        return []
    values: list[float] = []
    for token in re.split(r"[\s,]+", raw):
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            return []
    if len(values) < 4 or len(values) % 2:
        return []
    return list(zip(values[0::2], values[1::2]))


def _same_point(a: tuple[float, float], b: tuple[float, float], tol: float = GEOMETRY_EPSILON) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _orientation(a: tuple[float, float], b: tuple[float, float], tol: float = 0.01) -> str:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    if dy <= tol and dx > tol:
        return "H"
    if dx <= tol and dy > tol:
        return "V"
    return "D"


def _simplify_polyline(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    dedup: list[tuple[float, float]] = []
    for point in points:
        if dedup and _same_point(dedup[-1], point):
            continue
        dedup.append(point)
    if len(dedup) <= 2:
        return dedup

    result = [dedup[0]]
    for index in range(1, len(dedup) - 1):
        prev = result[-1]
        current = dedup[index]
        nxt = dedup[index + 1]
        if _orientation(prev, current) == _orientation(current, nxt) in {"H", "V"}:
            continue
        result.append(current)
    result.append(dedup[-1])
    return result


def _rewrite_polyline(element: ET.Element, points: list[tuple[float, float]]) -> None:
    points = _simplify_polyline(points)
    element.set("d", " ".join(f"{_fmt(x)},{_fmt(y)}" for x, y in points))
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    # Business G line elements use a 3-G visual margin around the path.
    element.set("x", _fmt(min(xs) - 3.0))
    element.set("y", _fmt(min(ys) - 3.0))
    element.set("w", _fmt(max(xs) - min(xs) + 6.0))
    element.set("h", _fmt(max(ys) - min(ys) + 6.0))


def _extend_endpoint_orthogonally(
    element: ET.Element,
    endpoint_index: int,
    target: tuple[float, float],
) -> bool:
    """Extend one line endpoint to target without turning the existing path diagonal.

    FeedLine is the preferred object to move.  If the old terminal segment is
    horizontal/vertical, a short orthogonal dogleg is inserted when needed and
    the rest of the original path is left unchanged.
    """
    points = _points(element)
    if len(points) < 2:
        return False
    index = 0 if int(endpoint_index) == 0 else len(points) - 1
    old = points[index]
    if _same_point(old, target):
        return False

    if index == 0:
        neighbor = points[1]
        axis = _orientation(old, neighbor)
        if axis == "H":
            if abs(target[1] - old[1]) <= GEOMETRY_EPSILON:
                new_points = [target] + points[1:]
            else:
                corner = (target[0], old[1])
                new_points = [target, corner] + points[1:]
        elif axis == "V":
            if abs(target[0] - old[0]) <= GEOMETRY_EPSILON:
                new_points = [target] + points[1:]
            else:
                corner = (old[0], target[1])
                new_points = [target, corner] + points[1:]
        else:
            # Rare legacy diagonal terminal: preserve the old point as a bend and
            # reach it through a Manhattan bridge instead of inventing a diagonal.
            corner = (target[0], old[1])
            new_points = [target, corner, old] + points[1:]
    else:
        neighbor = points[-2]
        axis = _orientation(neighbor, old)
        if axis == "H":
            if abs(target[1] - old[1]) <= GEOMETRY_EPSILON:
                new_points = points[:-1] + [target]
            else:
                corner = (target[0], old[1])
                new_points = points[:-1] + [corner, target]
        elif axis == "V":
            if abs(target[0] - old[0]) <= GEOMETRY_EPSILON:
                new_points = points[:-1] + [target]
            else:
                corner = (old[0], target[1])
                new_points = points[:-1] + [corner, target]
        else:
            corner = (target[0], old[1])
            new_points = points[:-1] + [old, corner, target]

    _rewrite_polyline(element, new_points)
    return True


def _parse_reference_tokens(element: ET.Element) -> list[tuple[str, int, int, str]]:
    rows: list[tuple[str, int, int, str]] = []
    for attr in ("link", "node_area"):
        raw = _txt(element.get(attr))
        if not raw:
            continue
        for token in raw.split(";"):
            parts = [part.strip() for part in token.split(",")]
            if len(parts) < 3 or not parts[-1]:
                continue
            try:
                own_index = int(float(parts[0]))
            except (TypeError, ValueError):
                own_index = 0
            try:
                other_index = int(float(parts[1]))
            except (TypeError, ValueError):
                other_index = 0
            rows.append((attr, own_index, other_index, parts[-1]))
    return rows


def _endpoint_reference_ids(element: ET.Element) -> dict[int, set[str]]:
    result = {0: set(), 1: set()}
    for _attr, own_index, _other_index, other_id in _parse_reference_tokens(element):
        if own_index in result:
            result[own_index].add(other_id)
    return result


def _append_reference_token(
    element: ET.Element,
    attr: str,
    own_endpoint: int,
    other_endpoint: int,
    other_id: str,
) -> bool:
    raw = _txt(element.get(attr))
    tokens = [token.strip() for token in raw.split(";") if token.strip()]
    for token in tokens:
        parts = [part.strip() for part in token.split(",")]
        if len(parts) >= 3 and parts[-1] == other_id:
            return False
    tokens.append(f"{int(own_endpoint)},{int(other_endpoint)},{other_id}")
    element.set(attr, ";".join(tokens))
    return True


def _ensure_reciprocal_line_references(
    left: EndpointEntry,
    right: EndpointEntry,
) -> int:
    changed = 0
    for attr in ("link", "node_area"):
        if _append_reference_token(
            left.element, attr, left.endpoint_index, right.endpoint_index, right.element_id
        ):
            changed += 1
        if _append_reference_token(
            right.element, attr, right.endpoint_index, left.endpoint_index, left.element_id
        ):
            changed += 1
    return changed


def _line_elements(root: ET.Element) -> list[ET.Element]:
    return [
        element
        for element in root.iter()
        if _local_name(element.tag) in NETWORK_LINE_TAGS
        and _txt(element.get("id"))
        and len(_points(element)) >= 2
    ]


def _candidate_endpoint_entries(lines: list[ET.Element]) -> tuple[list[EndpointEntry], int]:
    entries: list[EndpointEntry] = []
    dangling_count = 0
    for element in lines:
        tag = _local_name(element.tag)
        if tag not in {"ConnectLine", "FeedLine"}:
            continue
        points = _points(element)
        refs = _endpoint_reference_ids(element)
        for endpoint_index, point in ((0, points[0]), (1, points[-1])):
            if refs[endpoint_index]:
                continue
            dangling_count += 1
            # A real topology stub should already lead somewhere at its other end.
            # This excludes decorative/free-floating line fragments from auto repair.
            if not refs[1 - endpoint_index]:
                continue
            entries.append(EndpointEntry(
                element_id=_txt(element.get("id")),
                tag=tag,
                endpoint_index=endpoint_index,
                point=point,
                element=element,
            ))
    return entries, dangling_count


def _distance(a: EndpointEntry, b: EndpointEntry) -> float:
    return math.hypot(a.point[0] - b.point[0], a.point[1] - b.point[1])


def _terminal_axis(entry: EndpointEntry) -> str:
    points = _points(entry.element)
    if len(points) < 2:
        return "D"
    if entry.endpoint_index == 0:
        return _orientation(points[0], points[1])
    return _orientation(points[-2], points[-1])


def _pair_gap_limit(left: EndpointEntry, right: EndpointEntry, distance: float) -> float | None:
    """Return safe Jeddah auto-repair radius for a line-pair, or None.

    ConnectLine↔FeedLine is the actual outside-RMU/feeder handoff seen in the
    Jeddah drawings, so a unique local gap up to 25G is repairable.

    ConnectLine↔ConnectLine needs a much tighter rule because open switch
    contacts and symbol internals intentionally contain ~18G gaps.  Only a tiny
    0.01G..3G collinear discontinuity is treated as an accidental split.
    Exact/overlapping ConnectLine geometry is deliberately left alone.
    """
    pair = tuple(sorted((left.tag, right.tag)))
    if pair == ("ConnectLine", "FeedLine"):
        return MAX_AUTO_GAP
    if pair == ("ConnectLine", "ConnectLine"):
        if not (GEOMETRY_EPSILON < distance <= CONNECTLINE_TO_CONNECTLINE_MAX_GAP):
            return None
        left_axis = _terminal_axis(left)
        right_axis = _terminal_axis(right)
        if left_axis != right_axis or left_axis not in {"H", "V"}:
            return None
        if left_axis == "H" and abs(left.point[1] - right.point[1]) > GEOMETRY_EPSILON:
            return None
        if left_axis == "V" and abs(left.point[0] - right.point[0]) > GEOMETRY_EPSILON:
            return None
        return CONNECTLINE_TO_CONNECTLINE_MAX_GAP
    return None


def _find_unique_gap_pairs(
    lines: list[ET.Element],
    *,
    max_gap: float = MAX_AUTO_GAP,
) -> tuple[list[tuple[float, EndpointEntry, EndpointEntry]], list[dict], int]:
    entries, dangling_count = _candidate_endpoint_entries(lines)
    cell_size = max(float(GRID_CELL_SIZE), float(max_gap) + 1.0)
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)

    def cell(point: tuple[float, float]) -> tuple[int, int]:
        return (
            int(math.floor(point[0] / cell_size)),
            int(math.floor(point[1] / cell_size)),
        )

    for index, entry in enumerate(entries):
        grid[cell(entry.point)].append(index)

    nearest: dict[int, list[tuple[float, int]]] = {}
    for index, entry in enumerate(entries):
        cx, cy = cell(entry.point)
        candidates: list[tuple[float, int]] = []
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for other_index in grid.get((gx, gy), ()):
                    if other_index == index:
                        continue
                    other = entries[other_index]
                    distance = _distance(entry, other)
                    limit = _pair_gap_limit(entry, other, distance)
                    if limit is None:
                        continue
                    if distance <= min(float(max_gap), float(limit)) + 1e-9:
                        candidates.append((distance, other_index))
        candidates.sort(key=lambda item: (item[0], entries[item[1]].element_id, entries[item[1]].endpoint_index))
        if candidates:
            nearest[index] = candidates

    pairs: list[tuple[float, EndpointEntry, EndpointEntry]] = []
    unresolved: list[dict] = []
    used_pair_keys: set[tuple[str, int, str, int]] = set()
    for index, candidates in nearest.items():
        best_distance, other_index = candidates[0]
        other_candidates = nearest.get(other_index)
        if not other_candidates or other_candidates[0][1] != index:
            continue
        left = entries[index]
        right = entries[other_index]
        key = (
            left.element_id,
            left.endpoint_index,
            right.element_id,
            right.endpoint_index,
        )
        reverse_key = (key[2], key[3], key[0], key[1])
        if key in used_pair_keys or reverse_key in used_pair_keys:
            continue
        used_pair_keys.add(key)

        left_second = candidates[1][0] if len(candidates) > 1 else float("inf")
        right_second = other_candidates[1][0] if len(other_candidates) > 1 else float("inf")
        if (
            left_second <= best_distance + AMBIGUITY_MARGIN
            or right_second <= best_distance + AMBIGUITY_MARGIN
        ):
            unresolved.append({
                "status": "REVIEW_AMBIGUOUS_NEIGHBOR",
                "left_xml_id": left.element_id,
                "left_tag": left.tag,
                "left_endpoint": left.endpoint_index,
                "left_x": left.point[0],
                "left_y": left.point[1],
                "right_xml_id": right.element_id,
                "right_tag": right.tag,
                "right_endpoint": right.endpoint_index,
                "right_x": right.point[0],
                "right_y": right.point[1],
                "distance": round(best_distance, 3),
                "reason": "断点附近存在同等级第二近邻，不能唯一判断连接对象，未自动修改。",
            })
            continue
        pairs.append((best_distance, left, right))

    pairs.sort(key=lambda item: (item[0], item[1].element_id, item[2].element_id))
    return pairs, unresolved, dangling_count


def _geometry_text(element: ET.Element) -> str:
    return _txt(element.get("d"))


def _fixed_g_name(source: Path) -> str:
    name = source.name
    suffix = ".sln.pic.g"
    if name.lower().endswith(suffix):
        return name[:-len(suffix)] + ".topology-fixed.sln.pic.g"
    return source.stem + ".topology-fixed.g"


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "status",
        "left_tag", "left_xml_id", "left_endpoint", "left_x_before", "left_y_before",
        "right_tag", "right_xml_id", "right_endpoint", "right_x_before", "right_y_before",
        "distance_before", "moved_xml_id", "geometry_changed", "topology_tokens_added",
        "geometry_before", "geometry_after", "reason",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def _write_html(
    path: Path,
    *,
    source: Path,
    rows: list[dict],
    line_count: int,
    dangling_before: int,
    remaining_candidates: int,
    elapsed_seconds: float,
    before_svg_path: Path,
    after_svg_path: Path,
    fixed_g_path: Path | None,
    render_stats: GRenderStats,
) -> None:
    fixed = [row for row in rows if row.get("status") == "AUTO_FIXED"]
    unresolved = [row for row in rows if row.get("status") != "AUTO_FIXED"]
    table_rows = []
    for issue_index, row in enumerate(rows, start=1):
        table_rows.append(
            "<tr>"
            f"<td>#{issue_index}</td>"
            f"<td>{html.escape(_txt(row.get('status')))}</td>"
            f"<td>{html.escape(_txt(row.get('left_tag')))} / {html.escape(_txt(row.get('left_xml_id')))}</td>"
            f"<td>{html.escape(_txt(row.get('right_tag')))} / {html.escape(_txt(row.get('right_xml_id')))}</td>"
            f"<td>{html.escape(_txt(row.get('distance_before')))}</td>"
            f"<td>({_txt(row.get('left_x_before'))}, {_txt(row.get('left_y_before'))}) ↔ ({_txt(row.get('right_x_before'))}, {_txt(row.get('right_y_before'))})</td>"
            f"<td>{html.escape(_txt(row.get('geometry_before')))}</td>"
            f"<td>{html.escape(_txt(row.get('geometry_after')))}</td>"
            f"<td>{html.escape(_txt(row.get('reason')))}</td>"
            "</tr>"
        )
    fixed_link = (
        f"<a href='{html.escape(fixed_g_path.name, quote=True)}'>打开修复后的 G</a>"
        if fixed_g_path is not None else "无需生成修复副本"
    )
    body = (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>吉达整图拓扑连接检查与修复</title>"
        "<style>body{font-family:Segoe UI,Arial,'Microsoft YaHei',sans-serif;margin:24px;color:#1f2937;background:#f7faf9}"
        "article{max-width:1800px;margin:auto;background:#fff;border:1px solid #dbe5e1;border-radius:12px;padding:20px}"
        "h1{font-size:22px;color:#075f4a}.note{background:#eef8f4;border-left:4px solid #0a8f68;padding:12px;margin:12px 0}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}.card{background:#f5faf8;border:1px solid #d8e7e1;border-radius:8px;padding:10px}.card b{display:block;color:#55746a;font-size:12px}.card span{font-size:20px;font-weight:700;color:#174f42}"
        ".diagram-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:24px}.diagram-controls{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.diagram-controls button{border:1px solid #b9d3c8;background:#fff;color:#075f4a;border-radius:6px;padding:6px 10px;cursor:pointer}.zoom-value{min-width:52px;text-align:center;font-weight:700}.diagram{border:1px solid #d9e5df;border-radius:10px;padding:8px;background:#fff;overflow:auto;max-height:72vh}.diagram img{display:block;width:100%;max-width:none;height:auto;transform-origin:top left}.legend{color:#526d65;font-size:13px}.before-legend b{color:#dc2626}.after-legend b{color:#047857}"
        "table{border-collapse:collapse;width:100%;font-size:12px;margin-top:12px}th,td{border:1px solid #d1d5db;padding:6px;vertical-align:top}th{background:#f3f4f6;position:sticky;top:0}.table-wrap{overflow:auto;max-height:58vh}code{font-family:Consolas,monospace;background:#eef4f1;padding:2px 5px;border-radius:4px}a{color:#0369a1}"
        "section:fullscreen{background:#f7faf8;padding:14px;overflow:hidden}section:fullscreen .diagram{max-height:calc(100vh - 120px);height:calc(100vh - 120px)}"
        "</style></head><body><article>"
        "<h1>吉达整图拓扑连接检查与自动修复</h1>"
        "<div class='note'><b>吉达规则：</b>拓扑判定仍然只检查 G 图 ConnectLine / FeedLine 的物理与拓扑连接完整性，不判断馈线、不识别 NOP、不读取 Bus 馈线名、不查数据库。<b>报告图不再画抽象拓扑图</b>，而是直接按原 G 文件坐标、文字、线条、RMU 框、设备图元、状态图标、NOP 图片和图框内容重绘整张 G；修复前图在原图上叠加红/橙问题位置，修复后图在修复后的 G 上叠加绿色修复位置。</div>"
        f"<p>源文件：<code>{html.escape(source.name)}</code>；{fixed_link}</p>"
        "<div class='cards'>"
        f"<div class='card'><b>G 可见图元</b><span>{render_stats.visible_source_objects}</span></div>"
        f"<div class='card'><b>SVG 已绘制图元</b><span>{render_stats.rendered_objects}</span></div>"
        f"<div class='card'><b>线路对象</b><span>{line_count}</span></div>"
        f"<div class='card'><b>候选断点</b><span>{len(fixed)+len(unresolved)}</span></div>"
        f"<div class='card'><b>自动修复</b><span>{len(fixed)}</span></div>"
        f"<div class='card'><b>待人工确认</b><span>{len(unresolved)}</span></div>"
        f"<div class='card'><b>修复后剩余唯一断点</b><span>{remaining_candidates}</span></div>"
        f"<div class='card'><b>耗时</b><span>{elapsed_seconds:.2f}s</span></div>"
        "</div>"
        f"<p>原始无引用端点（包含正常符号开口，仅作扫描基数）：{dangling_before}。整图画布：{render_stats.canvas_width:.0f} × {render_stats.canvas_height:.0f} G；不可见图元跳过 {render_stats.skipped_invisible_objects} 个。</p>"
        "<section><div class='diagram-heading'><h2>修复前拓扑图（问题定位）</h2><div class='diagram-controls'>"
        "<button data-zoom-action='out'>− 缩小</button><span class='zoom-value'>100%</span><button data-zoom-action='in'>+ 放大</button><button data-zoom-action='reset'>重置</button><button data-zoom-action='fullscreen'>全屏</button></div></div>"
        "<p class='legend before-legend'>这里显示的是<b>原始 G 的整图重绘</b>，不是简化拓扑草图。线条、文字、RMU 框、开关/接地/状态图标、NOP 图片、站间跳转框和图框均按 G 中原始坐标绘制；白色原生文字/边框仅在白底报告中转换为深灰以便阅读。<b>红色圆圈/×/编号</b> = 唯一确认的断点；<span style='color:#b45309;font-weight:700'>橙色</span> = 有歧义、只报告不修改。</p>"
        f"<div class='topology-viewer' data-topology-viewer data-zoom='100'><div class='diagram'><img src='{html.escape(before_svg_path.name, quote=True)}' alt='修复前拓扑图'></div></div></section>"
        "<section><div class='diagram-heading'><h2>修复后拓扑图</h2><div class='diagram-controls'>"
        "<button data-zoom-action='out'>− 缩小</button><span class='zoom-value'>100%</span><button data-zoom-action='in'>+ 放大</button><button data-zoom-action='reset'>重置</button><button data-zoom-action='fullscreen'>全屏</button></div></div>"
        "<p class='legend after-legend'>修复后图同样由<b>修复后的完整 G</b>直接重绘；<b>绿色圆圈/编号</b> = 已修复位置，绿色半透明描边同时突出被修改的线路；橙色仍表示未自动修改、需要人工确认的位置。</p>"
        f"<div class='topology-viewer' data-topology-viewer data-zoom='100'><div class='diagram'><img src='{html.escape(after_svg_path.name, quote=True)}' alt='修复后拓扑图'></div></div></section>"
        "<h2>拓扑断点 / 修复明细</h2><div class='table-wrap'><table><thead><tr><th>问题#</th><th>状态</th><th>线路 A</th><th>线路 B</th><th>断点距离(G)</th><th>问题位置坐标</th><th>修复前几何</th><th>修复后几何</th><th>说明</th></tr></thead><tbody>"
        + ("".join(table_rows) if table_rows else "<tr><td colspan='9'>未发现满足安全规则的断点。</td></tr>")
        + "</tbody></table></div>"
        + """<script>
(function(){
 const STEP=20,MIN=20,MAX=500;
 function setZoom(viewer,value,reset){
   const img=viewer.querySelector('.diagram img'); if(!img)return;
   const z=Math.max(MIN,Math.min(MAX,Math.round(value/STEP)*STEP)); viewer.dataset.zoom=String(z); img.style.width=z+'%';
   const controls=viewer.closest('section').querySelector('.diagram-controls'); const label=controls&&controls.querySelector('.zoom-value'); if(label)label.textContent=z+'%';
   if(reset){const pane=viewer.querySelector('.diagram'); if(pane){pane.scrollLeft=0;pane.scrollTop=0;}}
 }
 document.querySelectorAll('[data-topology-viewer]').forEach(function(viewer){setZoom(viewer,100,false);const pane=viewer.querySelector('.diagram');if(pane)pane.addEventListener('wheel',function(ev){if(!ev.ctrlKey)return;ev.preventDefault();setZoom(viewer,Number(viewer.dataset.zoom||100)+(ev.deltaY<0?STEP:-STEP),false);},{passive:false});});
 document.addEventListener('click',function(ev){const btn=ev.target.closest('[data-zoom-action]');if(!btn)return;const section=btn.closest('section');const viewer=section&&section.querySelector('[data-topology-viewer]');if(!viewer)return;const action=btn.dataset.zoomAction;const cur=Number(viewer.dataset.zoom||100);if(action==='in')setZoom(viewer,cur+STEP,false);else if(action==='out')setZoom(viewer,cur-STEP,false);else if(action==='reset')setZoom(viewer,100,true);else if(action==='fullscreen'){if(document.fullscreenElement===section){document.exitFullscreen&&document.exitFullscreen();}else{section.requestFullscreen&&section.requestFullscreen();}}});
})();
</script></article></body></html>"""
    )
    path.write_text(body, encoding="utf-8")


def repair_jeddah_topology_connectivity(
    source: Path,
    report_dir: Path,
    *,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> JeddahTopologyConnectivityResult:
    """Repair Jeddah G-file topology continuity without feeder/NOP/database logic.

    The connectivity decision remains deliberately small and fast.  Reporting is
    different: before/after diagrams are full G-file redraws, not abstract
    topology sketches.
    """
    start_time = time.perf_counter()
    log = log or (lambda _message: None)
    progress = progress or (lambda _percent, _message="": None)
    source = Path(source)
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    progress(5, f"正在解析 G 图连接：{source.name}")
    tree = ET.parse(source)
    root = tree.getroot()
    lines = _line_elements(root)

    progress(20, "正在扫描线路未连接端点与局部几何断口")
    pairs, unresolved_raw, dangling_before = _find_unique_gap_pairs(lines)
    log(
        f"[拓扑检查] 线路对象 {len(lines)}；原始无引用端点 {dangling_before}（含正常符号开口）；"
        f"安全阈值内唯一近邻断点 {len(pairs)}；歧义 {len(unresolved_raw)}。"
    )

    # Build the complete issue list while the original geometry is still
    # untouched.  The before SVG is rendered from this exact original root.
    repair_rows: list[dict] = []
    for distance, first, second in pairs:
        if {first.tag, second.tag} == {"ConnectLine", "FeedLine"}:
            moved = first if first.tag == "FeedLine" else second
        else:
            moved = second
        repair_rows.append({
            "status": "AUTO_FIXED",
            "left_tag": first.tag,
            "left_xml_id": first.element_id,
            "left_endpoint": first.endpoint_index,
            "left_x_before": _fmt(first.point[0]),
            "left_y_before": _fmt(first.point[1]),
            "right_tag": second.tag,
            "right_xml_id": second.element_id,
            "right_endpoint": second.endpoint_index,
            "right_x_before": _fmt(second.point[0]),
            "right_y_before": _fmt(second.point[1]),
            "distance_before": round(float(distance), 3),
            "moved_xml_id": moved.element_id,
            "geometry_changed": "PENDING",
            "topology_tokens_added": 0,
            "geometry_before": _geometry_text(moved.element),
            "geometry_after": "",
            "reason": "双方未连接端点互为唯一最近邻；待自动闭合并补齐双方 link/node_area。",
        })

    for row in unresolved_raw:
        repair_rows.append({
            "status": row.get("status", "REVIEW"),
            "left_tag": row.get("left_tag", ""),
            "left_xml_id": row.get("left_xml_id", ""),
            "left_endpoint": row.get("left_endpoint", ""),
            "left_x_before": row.get("left_x", ""),
            "left_y_before": row.get("left_y", ""),
            "right_tag": row.get("right_tag", ""),
            "right_xml_id": row.get("right_xml_id", ""),
            "right_endpoint": row.get("right_endpoint", ""),
            "right_x_before": row.get("right_x", ""),
            "right_y_before": row.get("right_y", ""),
            "distance_before": row.get("distance", ""),
            "moved_xml_id": "",
            "geometry_changed": "NO",
            "topology_tokens_added": 0,
            "geometry_before": "",
            "geometry_after": "",
            "reason": row.get("reason", ""),
        })

    progress(34, "正在按原 G 图元完整生成修复前整图，并标出问题位置")
    before_svg_path = report_dir / "jeddah_topology_before.svg"
    before_stats = render_g_root_to_svg(
        root,
        before_svg_path,
        issue_rows=repair_rows,
        after=False,
    )
    log(
        f"[修复前整图] G 可见图元 {before_stats.visible_source_objects}；"
        f"SVG 实际绘制 {before_stats.rendered_objects}；画布 "
        f"{before_stats.canvas_width:.0f}×{before_stats.canvas_height:.0f} G。"
    )

    geometry_repair_count = 0
    topology_link_repair_count = 0
    progress(55, f"正在自动修复 {len(pairs)} 处唯一断点")
    for row_index, (distance, first, second) in enumerate(pairs):
        # Common Jeddah RMU handoff: keep the small internal ConnectLine fixed
        # and extend FeedLine to it.  For <=3G ConnectLine splits, move the
        # second terminal to the first terminal.
        if {first.tag, second.tag} == {"ConnectLine", "FeedLine"}:
            moved = first if first.tag == "FeedLine" else second
            target = second if moved is first else first
        else:
            moved, target = second, first

        geometry_changed = _extend_endpoint_orthogonally(
            moved.element, moved.endpoint_index, target.point
        )
        if geometry_changed:
            geometry_repair_count += 1
        tokens_added = _ensure_reciprocal_line_references(first, second)
        topology_link_repair_count += tokens_added

        row = repair_rows[row_index]
        row["geometry_changed"] = "YES" if geometry_changed else "NO"
        row["topology_tokens_added"] = tokens_added
        row["geometry_after"] = _geometry_text(moved.element)
        row["reason"] = (
            "双方未连接端点互为唯一最近邻；已按正交方向闭合可见断口，并补齐双方 link/node_area。"
            if geometry_changed
            else "双方端点坐标已经重合但拓扑引用缺失；已补齐双方 link/node_area。"
        )

    fixed_g_path: Path | None = None
    if pairs:
        progress(70, "正在写入拓扑修复安全副本")
        fixed_g_path = report_dir / _fixed_g_name(source)
        tmp = fixed_g_path.with_name(fixed_g_path.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        ET.parse(tmp)
        os.replace(tmp, fixed_g_path)
        log(f"[修复后 G] {fixed_g_path}")
    else:
        log("[拓扑检查] 未发现可自动修复的唯一局部断点；原始 G 未修改。")

    # Re-check the repaired in-memory topology.
    lines_after = _line_elements(root)
    remaining_pairs, _remaining_unresolved, _dangling_after = _find_unique_gap_pairs(lines_after)

    progress(84, "正在按修复后的完整 G 图元生成修复后整图")
    after_svg_path = report_dir / "jeddah_topology_after.svg"
    after_stats = render_g_root_to_svg(
        root,
        after_svg_path,
        issue_rows=repair_rows,
        after=True,
    )
    log(
        f"[修复后整图] G 可见图元 {after_stats.visible_source_objects}；"
        f"SVG 实际绘制 {after_stats.rendered_objects}。"
    )

    progress(95, "正在生成单文件 HTML / CSV 报告")
    csv_path = report_dir / "jeddah_topology_connection_repairs.csv"
    html_path = report_dir / "jeddah_topology_connection_report.html"
    _write_csv(csv_path, repair_rows)
    elapsed = time.perf_counter() - start_time
    _write_html(
        html_path,
        source=source,
        rows=repair_rows,
        line_count=len(lines),
        dangling_before=dangling_before,
        remaining_candidates=len(remaining_pairs),
        elapsed_seconds=elapsed,
        before_svg_path=before_svg_path,
        after_svg_path=after_svg_path,
        fixed_g_path=fixed_g_path,
        render_stats=before_stats,
    )

    log(
        f"[完成] 自动修复 {len(pairs)} 处（几何 {geometry_repair_count}，"
        f"新增拓扑引用 token {topology_link_repair_count}）；"
        f"修复后安全阈值内唯一近邻断点 {len(remaining_pairs)}；耗时 {elapsed:.2f}s。"
    )
    progress(100, "吉达整图拓扑连接检查与自动修复完成")

    return JeddahTopologyConnectivityResult(
        html_path=html_path,
        csv_path=csv_path,
        before_svg_path=before_svg_path,
        after_svg_path=after_svg_path,
        fixed_g_path=fixed_g_path,
        source_file=source,
        line_count=len(lines),
        dangling_endpoint_count_before=dangling_before,
        candidate_count=len(pairs) + len(unresolved_raw),
        repair_count=len(pairs),
        geometry_repair_count=geometry_repair_count,
        topology_link_repair_count=topology_link_repair_count,
        remaining_candidate_count=len(remaining_pairs),
        unresolved_count=len(unresolved_raw),
        elapsed_seconds=elapsed,
    )

