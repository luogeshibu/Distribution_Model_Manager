from __future__ import annotations

import csv
import html
import math
import re
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from dmm.domain.feeder.ownership import (
    ENDPOINT_TOLERANCE,
    ENDPOINT_TO_SEGMENT_TOLERANCE,
    LINE_TAGS,
    NETWORK_TAGS,
    NOP_SWITCH_SEARCH_DISTANCE,
    FeederOwnershipResolver,
    _endpoints,
    _point_to_segment_distance,
    _reference_ids,
    _segments,
)
from dmm.domain.gfile.master_station_frames import find_master_station_frames, text_has_background
from dmm.domain.gfile.parser import GObject, ParsedG, RmuFrame
from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    _assign_nops_to_frames,
    _frame_key,
    _is_nop_text,
    _named_yq_switches,
    _new_makkah_parser,
)
from dmm.domain.graphics_cleanup.rmu_feeder_topology import (
    _is_red_nop_text,
    _nearest_nop_device,
    _rmu_name_map,
    _txt,
    _repair_rmu_terminal_geometry,
)
from dmm.domain.graphics_cleanup.main_station_background_label import (
    background_jump_label_text_ids,
    find_background_jump_label_groups,
)


# This module is deliberately independent from the proven RMU-only and
# FeedLine-only topology analyzers.  It reuses parsing and strict electrical
# connection primitives, but does not modify those two business modules.
WHOLE_GRAPH_EXTRA_NETWORK_TAGS = {"Pole"}
WHOLE_GRAPH_LINE_LABEL_MAX_DISTANCE = 80.0
WHOLE_GRAPH_DEVICE_LABEL_MARGIN = 20.0
WHOLE_GRAPH_DEVICE_LABEL_ABSOLUTE_GUARD = 35.0

# v4.1.132 whole-graph topology report zoom controls; v4.1.131 auto-repair.  The proven analyzers keep their
# original strict 3G geometry rules.  Only this new whole-graph module may
# propose a slightly wider endpoint-to-endpoint bridge, and only after
# reciprocal-uniqueness plus topology simulation proves that the repair reduces
# NO_FEEDER errors without creating a multi-feeder conflict.
WHOLE_GRAPH_AUTO_REPAIR_MAX_DISTANCE = 4.5
WHOLE_GRAPH_AUTO_REPAIR_MIN_DISTANCE = ENDPOINT_TOLERANCE + 1e-6
WHOLE_GRAPH_AUTO_REPAIR_MAX_PASSES = 32

# Whole-drawing feeder labels may be written on a line rather than beside a
# main-station Bay.  Keep both common forms:
#   TRUB-AH309 / TRUB-BH20 / GVCM-AH304 / SHM1-AH341_X
#   TURB-BH-04 / TRUB-BH-04
# The second form is intentionally broader than the legacy Bay-title parser.
WHOLE_GRAPH_FEEDER_LABEL_RE = re.compile(
    r"^(?P<station>[A-Z]{2,}[A-Z0-9]*)[-_\s]+"
    r"(?P<feeder>(?:[A-Z]{1,8}(?:[-_\s]?\d{1,6})(?:_[XY])?)|(?:\d{1,6}(?:_[XY])?))$",
    re.IGNORECASE,
)


@dataclass
class WholeGraphTopologyResult:
    html_path: Path
    device_csv_path: Path
    nop_csv_path: Path
    anchor_csv_path: Path
    rmu_csv_path: Path
    repair_csv_path: Path
    before_svg_path: Path
    after_svg_path: Path
    fixed_g_path: Path | None
    file_count: int
    device_count: int
    confirmed_count: int
    conflict_count: int
    unresolved_count: int
    feeder_count: int
    nop_boundary_count: int
    pole_nop_count: int
    rmu_nop_count: int
    topology_error_count: int
    no_feeder_error_count: int
    multi_feeder_error_count: int
    rmu_count: int
    rmu_confirmed_count: int
    rmu_error_count: int
    repair_candidate_count: int
    repair_applied_count: int
    before_topology_error_count: int
    after_topology_error_count: int


def _esc(value) -> str:
    return html.escape(_txt(value), quote=True)


def _canonical_feeder_label(value: str) -> str:
    raw = re.sub(r"\s+", " ", _txt(value).upper())
    match = WHOLE_GRAPH_FEEDER_LABEL_RE.fullmatch(raw)
    if not match:
        return ""
    station = match.group("station").upper()
    feeder = re.sub(r"\s+", "-", match.group("feeder").upper())
    return f"{station}-{feeder}"


def _whole_graph_network_objects(parsed: ParsedG) -> list[GObject]:
    """Return electrical objects used by the whole-drawing graph.

    The legacy graph intentionally excludes Pole because its older business
    output only needed RMU/FeedLine ownership.  Whole-drawing analysis must
    preserve pole junctions because field G files can route FeedLine links via
    ``Pole.node_area``.  In addition to the known electrical tags, accept an
    object carrying link/node_area unless it is a known non-electrical visual
    annotation container.
    """
    excluded = {"Text", "text", "rect", "Rect", "Status", "pwbh", "poke", "Merge"}
    result = []
    for obj in parsed.objects:
        if not _txt(obj.xml_id) or obj.tag in excluded:
            continue
        if (
            obj.tag in NETWORK_TAGS
            or obj.tag in WHOLE_GRAPH_EXTRA_NETWORK_TAGS
            or _txt(obj.attrs.get("link"))
            or _txt(obj.attrs.get("node_area"))
        ):
            result.append(obj)
    return result


def _build_whole_graph(parsed: ParsedG):
    """Build a strict read-only electrical graph without changing old analyzers."""
    network = _whole_graph_network_objects(parsed)
    by_id = {obj.xml_id: obj for obj in network}
    adjacency: dict[str, set[str]] = defaultdict(set)

    for obj in network:
        for ref in _reference_ids(obj):
            if ref in by_id:
                FeederOwnershipResolver._add_edge(adjacency, obj.xml_id, ref)

    # Keep the exact strict geometry repair thresholds used by the existing
    # Makkah topology analyzers.  Geometry repair is limited to line-like
    # objects; Pole/device connectivity must come from explicit G references.
    line_objects = [obj for obj in network if obj.tag in LINE_TAGS]
    endpoint_grid: dict[tuple[int, int], list[tuple[str, tuple[float, float]]]] = defaultdict(list)
    repaired_pairs: set[tuple[str, str]] = set()
    grid = ENDPOINT_TOLERANCE

    def cell(point):
        return (
            int(math.floor(point[0] / grid)),
            int(math.floor(point[1] / grid)),
        )

    for obj in line_objects:
        for point in _endpoints(obj):
            endpoint_grid[cell(point)].append((obj.xml_id, point))

    for obj in line_objects:
        for point in _endpoints(obj):
            cx, cy = cell(point)
            for gx in range(cx - 1, cx + 2):
                for gy in range(cy - 1, cy + 2):
                    for other_id, other_point in endpoint_grid.get((gx, gy), []):
                        if other_id == obj.xml_id:
                            continue
                        if math.hypot(
                            point[0] - other_point[0], point[1] - other_point[1]
                        ) <= ENDPOINT_TOLERANCE:
                            pair = tuple(sorted((obj.xml_id, other_id)))
                            if (
                                other_id not in adjacency.get(obj.xml_id, set())
                                and pair not in repaired_pairs
                            ):
                                repaired_pairs.add(pair)
                                FeederOwnershipResolver._add_edge(adjacency, *pair)

    segment_cell_size = 80.0
    segment_grid: dict[
        tuple[int, int],
        list[tuple[str, tuple[tuple[float, float], tuple[float, float]]]],
    ] = defaultdict(list)
    for obj in line_objects:
        for seg in _segments(obj):
            a, b = seg
            left, right = sorted((a[0], b[0]))
            top, bottom = sorted((a[1], b[1]))
            gx0 = int(math.floor((left - ENDPOINT_TO_SEGMENT_TOLERANCE) / segment_cell_size))
            gx1 = int(math.floor((right + ENDPOINT_TO_SEGMENT_TOLERANCE) / segment_cell_size))
            gy0 = int(math.floor((top - ENDPOINT_TO_SEGMENT_TOLERANCE) / segment_cell_size))
            gy1 = int(math.floor((bottom + ENDPOINT_TO_SEGMENT_TOLERANCE) / segment_cell_size))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    segment_grid[(gx, gy)].append((obj.xml_id, seg))

    for obj in line_objects:
        for point in _endpoints(obj):
            gx = int(math.floor(point[0] / segment_cell_size))
            gy = int(math.floor(point[1] / segment_cell_size))
            for other_id, seg in segment_grid.get((gx, gy), []):
                if other_id == obj.xml_id:
                    continue
                a, b = seg
                if _point_to_segment_distance(
                    point[0], point[1], a[0], a[1], b[0], b[1]
                ) <= ENDPOINT_TO_SEGMENT_TOLERANCE:
                    pair = tuple(sorted((obj.xml_id, other_id)))
                    if (
                        other_id not in adjacency.get(obj.xml_id, set())
                        and pair not in repaired_pairs
                    ):
                        repaired_pairs.add(pair)
                        FeederOwnershipResolver._add_edge(adjacency, *pair)

    for xml_id in by_id:
        adjacency.setdefault(xml_id, set())
    return by_id, adjacency, len(repaired_pairs)


def _object_inside_any_rmu(obj: GObject, frames: list[RmuFrame]) -> bool:
    return any(frame.frame.box.center_contains(obj.box, tolerance=1.0) for frame in frames)


def _nearest_switch_name(parsed: ParsedG, switch: GObject) -> tuple[str, str, float | str]:
    candidates = []
    for text_obj in parsed.objects:
        if text_obj.tag.lower() != "text" or _is_nop_text(text_obj):
            continue
        text = _txt(text_obj.attrs.get("ts"))
        if not text:
            continue
        distance = float(text_obj.box.edge_distance(switch.box))
        if distance <= 180.0:
            candidates.append((distance, int(text_obj.xml_index), text_obj, text))
    if not candidates:
        return "", "", ""
    candidates.sort(key=lambda item: (item[0], item[1]))
    distance, _order, text_obj, text = candidates[0]
    return text, _txt(text_obj.xml_id), round(distance, 3)


def _whole_nop_boundaries(
    parser,
    parsed: ParsedG,
    frames: list[RmuFrame],
    rmu_names,
):
    """Resolve red NOPs as RMU-port boundaries or external pole-switch boundaries.

    Existing RMU NOP ownership remains exactly the proven logic: assigned NOPs
    are mapped to one Y*/Q* switch inside that RMU.  Any red NOP that the RMU
    assignment logic does not own is treated by this new module as a pole-switch
    NOP, per the field rule supplied for whole-drawing analysis.
    """
    assignments_all, unmatched_all = _assign_nops_to_frames(parsed, frames)
    assignments = [
        (nop, frame)
        for nop, frame in assignments_all
        if _is_nop_text(nop) and _is_red_nop_text(nop)
    ]
    unmatched = [
        nop for nop in unmatched_all
        if _is_nop_text(nop) and _is_red_nop_text(nop)
    ]

    boundary_nodes: set[str] = set()
    rows: list[dict] = []

    for nop, frame in assignments:
        name_info = rmu_names.get(_frame_key(frame), {})
        match = _nearest_nop_device(parser, parsed, frame, nop)
        if match is None:
            rows.append({
                "nop_text_xml_id": _txt(nop.xml_id),
                "nop_text": _txt(nop.attrs.get("ts")),
                "nop_type": "RMU_NOP",
                "rmu_name": _txt(name_info.get("name")),
                "frame_xml_id": _txt(frame.frame.xml_id),
                "switch_xml_id": "",
                "switch_name": "",
                "switch_tag": "",
                "switch_distance": "",
                "status": "RMU_NOP_SWITCH_NOT_FOUND",
            })
            continue
        device, logical_name, switch_distance, nop_side, alignment_axis, alignment_delta = match
        switch_id = _txt(device.xml_id)
        if switch_id:
            boundary_nodes.add(switch_id)
        rows.append({
            "nop_text_xml_id": _txt(nop.xml_id),
            "nop_text": _txt(nop.attrs.get("ts")),
            "nop_type": "RMU_NOP",
            "rmu_name": _txt(name_info.get("name")),
            "frame_xml_id": _txt(frame.frame.xml_id),
            "switch_xml_id": switch_id,
            "switch_name": logical_name,
            "switch_tag": device.tag,
            "switch_distance": round(float(switch_distance), 3),
            "nop_side": nop_side,
            "alignment_axis": alignment_axis,
            "alignment_delta": round(float(alignment_delta), 3),
            "status": "NOP_BOUNDARY" if switch_id else "RMU_NOP_SWITCH_NOT_FOUND",
        })

    switch_candidates = [
        obj for obj in parsed.objects
        if obj.xml_id and obj.tag in {"CBreakerDis", "Disconnector", "CBreaker"}
        and not _object_inside_any_rmu(obj, frames)
    ]
    priority = {"CBreakerDis": 0, "Disconnector": 1, "CBreaker": 2}

    for nop in unmatched:
        candidates = []
        for obj in switch_candidates:
            distance = float(nop.box.edge_distance(obj.box))
            if distance <= NOP_SWITCH_SEARCH_DISTANCE:
                candidates.append((priority.get(obj.tag, 9), distance, int(obj.xml_index), obj))
        if not candidates:
            rows.append({
                "nop_text_xml_id": _txt(nop.xml_id),
                "nop_text": _txt(nop.attrs.get("ts")),
                "nop_type": "POLE_NOP",
                "rmu_name": "",
                "frame_xml_id": "",
                "switch_xml_id": "",
                "switch_name": "",
                "switch_tag": "",
                "switch_distance": "",
                "status": "POLE_NOP_SWITCH_NOT_FOUND",
            })
            continue

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        best_priority, best_distance, _order, best = candidates[0]
        # A practically identical same-priority second candidate is unsafe to
        # guess.  Block both as topology boundaries and report ambiguity.
        selected = [
            item[3]
            for item in candidates
            if item[0] == best_priority and item[1] <= best_distance + 8.0
        ]
        selected_ids = [_txt(obj.xml_id) for obj in selected if _txt(obj.xml_id)]
        boundary_nodes.update(selected_ids)
        switch_name, switch_name_text_id, name_distance = _nearest_switch_name(parsed, best)
        rows.append({
            "nop_text_xml_id": _txt(nop.xml_id),
            "nop_text": _txt(nop.attrs.get("ts")),
            "nop_type": "POLE_NOP",
            "rmu_name": "",
            "frame_xml_id": "",
            "switch_xml_id": " | ".join(selected_ids),
            "switch_name": switch_name,
            "switch_name_text_xml_id": switch_name_text_id,
            "switch_name_distance": name_distance,
            "switch_tag": best.tag,
            "switch_distance": round(float(best_distance), 3),
            "status": "NOP_BOUNDARY" if len(selected_ids) == 1 else "POLE_NOP_MULTIPLE_CANDIDATES",
        })

    return boundary_nodes, rows


def _whole_graph_source_anchors(parsed: ParsedG, excluded_text_ids: set[str] | None = None):
    """Whole-graph feeder sources with jump-label Texts excluded up front.

    The established RMU-only analyzer is intentionally untouched.  The new
    whole-drawing analyzer alone excludes colored Poke/background labels such
    as ``MNA4-12`` + ``(33359)`` before Bay-title allocation, because those are
    jump captions rather than feeder evidence.
    """
    rows = []
    source_by_breaker: dict[str, str] = {}
    for frame_info in find_master_station_frames(
        parsed, excluded_text_ids=excluded_text_ids or set()
    ):
        breakers = list(frame_info.breakers)
        label = _txt(frame_info.feeder_label)
        breaker_id = (
            _txt(frame_info.breaker.xml_id)
            if len(breakers) == 1 and frame_info.breaker
            else ""
        )
        if len(breakers) != 1:
            status = "SOURCE_CBREAKER_NOT_UNIQUE"
        elif not label:
            status = "SOURCE_LABEL_NOT_FOUND"
        else:
            status = "SOURCE_CONFIRMED"
            if breaker_id:
                source_by_breaker[breaker_id] = label
        rows.append({
            "frame_xml_id": _txt(frame_info.frame.xml_id),
            "breaker_xml_id": breaker_id,
            "feeder_label": label,
            "text_xml_id": _txt(frame_info.label_obj.xml_id) if frame_info.label_obj else "",
            "distance": round(float(frame_info.label_distance), 3) if frame_info.label_distance is not None else "",
            "status": status,
        })
    return rows, source_by_breaker


def _line_feeder_anchors(
    parsed: ParsedG,
    frames: list[RmuFrame],
    rmu_names,
    source_rows: list[dict],
    excluded_text_ids: set[str] | None = None,
):
    """Find feeder-name Text written directly on a feeder line.

    Device labels such as SLBS-2002/SAR-2216 can resemble feeder names.  A line
    title is accepted only when it is close to a FeedLine and is not at least as
    strongly attached to a switch/device.  RMU labels, Bay labels and all NOP
    labels are excluded before ranking.
    """
    caller_excluded_text_ids = set(excluded_text_ids or set())
    excluded_text_ids = {
        _txt(info.get("text_xml_id"))
        for info in rmu_names.values()
        if _txt(info.get("text_xml_id"))
    }
    excluded_text_ids.update(
        _txt(row.get("text_xml_id"))
        for row in source_rows
        if _txt(row.get("text_xml_id"))
    )
    excluded_text_ids.update(
        _txt(value) for value in caller_excluded_text_ids if _txt(value)
    )

    lines = [obj for obj in parsed.objects if obj.tag == "FeedLine" and obj.xml_id]
    device_tags = {
        "CBreakerDis", "CBreaker", "Disconnector", "GroundDisconnector",
        "ZhaiWaiJieDiDaoZha", "TransformerDis", "BusDis", "Pole",
    }
    devices = [obj for obj in parsed.objects if obj.xml_id and obj.tag in device_tags]
    rows = []
    if not lines:
        return rows

    for text_obj in parsed.objects:
        if text_obj.tag.lower() != "text":
            continue
        text_id = _txt(text_obj.xml_id)
        if text_id in excluded_text_ids or _is_nop_text(text_obj):
            continue
        if text_has_background(text_obj):
            continue
        raw = _txt(text_obj.attrs.get("ts"))
        label = _canonical_feeder_label(raw)
        if not label:
            continue

        line_distance, line_obj = min(
            ((float(text_obj.box.edge_distance(line.box)), line) for line in lines),
            key=lambda item: (item[0], int(item[1].xml_index)),
        )
        if line_distance > WHOLE_GRAPH_LINE_LABEL_MAX_DISTANCE:
            continue

        device_distance = float("inf")
        device_obj = None
        if devices:
            device_distance, device_obj = min(
                ((float(text_obj.box.edge_distance(device.box)), device) for device in devices),
                key=lambda item: (item[0], int(item[1].xml_index)),
            )

        if device_obj is not None and device_distance <= max(
            WHOLE_GRAPH_DEVICE_LABEL_ABSOLUTE_GUARD,
            line_distance + WHOLE_GRAPH_DEVICE_LABEL_MARGIN,
        ):
            # The text is visually more consistent with a pole/RMU/device name
            # than with a feeder title; do not seed topology from it.
            continue

        rows.append({
            "anchor_type": "LINE_FEEDER_TEXT",
            "node_xml_id": _txt(line_obj.xml_id),
            "feeder_label": label,
            "text_xml_id": text_id,
            "raw_text": raw,
            "distance": round(line_distance, 3),
            "nearest_device_xml_id": _txt(device_obj.xml_id) if device_obj else "",
            "nearest_device_tag": device_obj.tag if device_obj else "",
            "nearest_device_distance": (
                round(device_distance, 3) if math.isfinite(device_distance) else ""
            ),
            "status": "ANCHOR_CONFIRMED",
        })

    rows.sort(key=lambda row: (
        row["feeder_label"], row["node_xml_id"], row["text_xml_id"]
    ))
    return rows


def _select_unique_line_source_anchors(
    raw_line_rows: list[dict],
    source_rows: list[dict],
    adjacency: dict[str, set[str]],
    boundary_nodes: set[str],
):
    """Select label-only feeder sources conservatively and uniquely.

    Field rule for the whole-graph analyzer:
      * a real main-station Bay/CBreaker source is authoritative;
      * text written on a line is only a *fallback source* when that topology
        region has no main-station source equipment;
      * a fallback source must sit at a topology terminal (degree <= 1 after
        removing NOP switches);
      * one feeder/main-station name may seed the drawing only once.  If the
        same name appears several times, a single occurrence directly on an
        NOP-side region wins; otherwise the duplicated name is reported and is
        not allowed to create multiple feeder sources;
      * one source-free topology region may have only one final source name.

    This prevents repeated display captions and mid-line names from becoming
    independent feeder anchors and creating artificial MULTI_FEEDER results.
    """
    component_of, components = _graph_components(adjacency, boundary_nodes)

    main_rows = [
        row for row in source_rows
        if row.get("status") == "SOURCE_CONFIRMED"
        and _txt(row.get("breaker_xml_id"))
        and _txt(row.get("feeder_label"))
    ]
    main_labels = {_txt(row.get("feeder_label")) for row in main_rows}
    main_by_component: dict[int, set[str]] = defaultdict(set)
    for row in main_rows:
        comp = component_of.get(_txt(row.get("breaker_xml_id")))
        if comp is not None:
            main_by_component[comp].add(_txt(row.get("feeder_label")))

    nop_adjacent_components: set[int] = set()
    for boundary_id in boundary_nodes:
        for neighbor_id in adjacency.get(boundary_id, set()):
            comp = component_of.get(neighbor_id)
            if comp is not None:
                nop_adjacent_components.add(comp)

    validation_rows: list[dict] = []
    eligible_by_label: dict[str, list[dict]] = defaultdict(list)

    for source in main_rows:
        comp = component_of.get(_txt(source.get("breaker_xml_id")))
        validation_rows.append({
            "source_type": "MAIN_STATION_CBREAKER",
            "feeder_label": _txt(source.get("feeder_label")),
            "node_xml_id": _txt(source.get("breaker_xml_id")),
            "text_xml_id": _txt(source.get("text_xml_id")),
            "component_id": "" if comp is None else comp,
            "topology_degree": len(adjacency.get(_txt(source.get("breaker_xml_id")), set())),
            "nop_adjacent": "YES" if comp in nop_adjacent_components else "NO",
            "main_station_labels": " | ".join(sorted(main_by_component.get(comp, set()))),
            "status": "SOURCE_SELECTED",
            "reason": "主网 Bay/CBreaker 已唯一确认馈线名称，作为权威馈线源。",
        })

    for raw in raw_line_rows:
        row = dict(raw)
        node_id = _txt(row.get("node_xml_id"))
        label = _txt(row.get("feeder_label"))
        comp = component_of.get(node_id)
        degree = sum(
            1 for neighbor_id in adjacency.get(node_id, set())
            if neighbor_id not in boundary_nodes
        )
        source_labels = set(main_by_component.get(comp, set()))
        nop_adjacent = comp in nop_adjacent_components

        row.update({
            "source_type": "LINE_TEXT_ONLY",
            "component_id": "" if comp is None else comp,
            "topology_degree": degree,
            "nop_adjacent": "YES" if nop_adjacent else "NO",
            "main_station_labels": " | ".join(sorted(source_labels)),
            "status": "SOURCE_CANDIDATE",
            "reason": "",
        })

        if comp is None:
            row["status"] = "SOURCE_REJECTED_NO_COMPONENT"
            row["reason"] = "候选文字所在 FeedLine 不属于可分析电气拓扑，不能作为馈线源。"
            validation_rows.append(row)
            continue
        if source_labels:
            row["status"] = "SOURCE_REJECTED_MAIN_STATION_PRESENT"
            row["reason"] = (
                "该拓扑区域已经存在主网 Bay/CBreaker 权威馈线源；沿线文字仅作为显示文字，"
                "不能再次成为馈线锚点。"
            )
            validation_rows.append(row)
            continue
        if label in main_labels:
            row["status"] = "SOURCE_REJECTED_DUPLICATE_MAIN_NAME"
            row["reason"] = (
                "同名馈线已经由主网 Bay/CBreaker 确认。一个主站出线只能有一个馈线源，"
                "该沿线同名文字不再参与拓扑传播。"
            )
            validation_rows.append(row)
            continue
        if degree > 1:
            row["status"] = "SOURCE_REJECTED_NOT_TERMINAL"
            row["reason"] = (
                "只在线路上写主站/馈线名称时，名称必须位于拓扑末端；该 FeedLine 仍有多个"
                "非NOP拓扑邻居，属于线路中段，不能作为主站源。"
            )
            validation_rows.append(row)
            continue

        eligible_by_label[label].append(row)

    tentative: list[dict] = []
    for label, rows in sorted(eligible_by_label.items()):
        if len(rows) == 1:
            tentative.append(rows[0])
            continue

        nop_side_rows = [row for row in rows if row.get("nop_adjacent") == "YES"]
        if len(nop_side_rows) == 1:
            winner = nop_side_rows[0]
            tentative.append(winner)
            for row in rows:
                if row is winner:
                    continue
                row["status"] = "SOURCE_REJECTED_DUPLICATE_NAME"
                row["reason"] = (
                    f"馈线名称 {label} 在图上重复出现；唯一直接位于 NOP 另一侧拓扑区域的候选"
                    "作为主站文字源，其余重复文字不参与馈线计算。"
                )
                validation_rows.append(row)
        else:
            for row in rows:
                row["status"] = "SOURCE_NAME_DUPLICATE_ERROR"
                row["reason"] = (
                    f"馈线/主站名称 {label} 出现多个同等级源候选，无法唯一确定。业务规则要求"
                    "一个主站出线有且只能有一个馈线名字，因此不允许这些候选同时传播。"
                )
                validation_rows.append(row)

    tentative_by_component: dict[int, list[dict]] = defaultdict(list)
    for row in tentative:
        comp = row.get("component_id")
        if isinstance(comp, int):
            tentative_by_component[comp].append(row)
        else:
            row["status"] = "SOURCE_REJECTED_NO_COMPONENT"
            row["reason"] = "候选源缺少有效拓扑区域。"
            validation_rows.append(row)

    selected: list[dict] = []
    for comp, rows in tentative_by_component.items():
        labels = {_txt(row.get("feeder_label")) for row in rows if _txt(row.get("feeder_label"))}
        if len(labels) != 1:
            for row in rows:
                row["status"] = "SOURCE_COMPONENT_MULTIPLE_NAMES_ERROR"
                row["reason"] = (
                    "同一个不跨越 NOP 的源端拓扑区域发现多个不同主站/馈线名称："
                    f"{' | '.join(sorted(labels))}。一个源端只能有一个名字，因此本区域不建立文字馈线源。"
                )
                validation_rows.append(row)
            continue

        # There should be one row after global-name de-duplication.  Keep the
        # deterministic closest text if an exact duplicate somehow remains.
        rows.sort(key=lambda item: (
            float(item.get("distance") or 0.0),
            int(_txt(item.get("text_xml_id")) or "0") if _txt(item.get("text_xml_id")).isdigit() else 0,
        ))
        winner = rows[0]
        winner["status"] = "SOURCE_SELECTED"
        winner["reason"] = (
            "该拓扑区域没有主网设备源，候选位于线路末端且主站/馈线名称唯一，"
            "作为‘仅文字主站’馈线源参与拓扑传播。"
        )
        validation_rows.append(winner)
        selected.append({
            "anchor_type": "LINE_FEEDER_TEXT",
            "node_xml_id": _txt(winner.get("node_xml_id")),
            "feeder_label": _txt(winner.get("feeder_label")),
            "text_xml_id": _txt(winner.get("text_xml_id")),
            "raw_text": _txt(winner.get("raw_text")),
            "distance": winner.get("distance", ""),
            "nearest_device_xml_id": _txt(winner.get("nearest_device_xml_id")),
            "nearest_device_tag": _txt(winner.get("nearest_device_tag")),
            "nearest_device_distance": winner.get("nearest_device_distance", ""),
            "status": "ANCHOR_CONFIRMED",
        })
        for loser in rows[1:]:
            loser["status"] = "SOURCE_REJECTED_DUPLICATE_NAME"
            loser["reason"] = "同一拓扑区域的同名重复文字已去重，不重复建立馈线源。"
            validation_rows.append(loser)

    validation_rows.sort(key=lambda row: (
        0 if row.get("source_type") == "MAIN_STATION_CBREAKER" else 1,
        _txt(row.get("feeder_label")),
        _txt(row.get("node_xml_id")),
        _txt(row.get("text_xml_id")),
    ))
    return selected, validation_rows


def _all_feeder_anchors(
    parsed: ParsedG,
    frames: list[RmuFrame],
    rmu_names,
    adjacency: dict[str, set[str]],
    boundary_nodes: set[str],
):
    background_jump_rows = find_background_jump_label_groups(parsed)
    background_jump_ids = background_jump_label_text_ids(parsed)
    source_rows, source_by_breaker = _whole_graph_source_anchors(
        parsed, background_jump_ids
    )

    # Main-station CBreaker anchors remain authoritative.  Validate global
    # source-name uniqueness before they seed the whole graph.
    main_candidates = []
    confirmed_by_label: dict[str, list[dict]] = defaultdict(list)
    for row in source_rows:
        if (
            row.get("status") == "SOURCE_CONFIRMED"
            and _txt(row.get("breaker_xml_id"))
            and _txt(row.get("feeder_label"))
        ):
            confirmed_by_label[_txt(row.get("feeder_label"))].append(row)

    duplicate_main_labels = {
        label for label, rows in confirmed_by_label.items()
        if len({_txt(row.get("breaker_xml_id")) for row in rows}) > 1
    }
    for row in source_rows:
        label = _txt(row.get("feeder_label"))
        breaker_id = _txt(row.get("breaker_xml_id"))
        if row.get("status") != "SOURCE_CONFIRMED" or not label or not breaker_id:
            continue
        if label in duplicate_main_labels:
            row["source_uniqueness_status"] = "SOURCE_NAME_DUPLICATE_ERROR"
            row["source_uniqueness_reason"] = (
                f"主网馈线名称 {label} 被多个 CBreaker 同时识别。业务规则要求一个主站出线"
                "有且只能有一个馈线名字，因此这些重复源不参与整图传播。"
            )
            continue
        row["source_uniqueness_status"] = "SOURCE_SELECTED"
        row["source_uniqueness_reason"] = "主网 Bay/CBreaker 与馈线标题唯一对应。"
        main_candidates.append({
            "anchor_type": "MAIN_STATION_CBREAKER",
            "node_xml_id": breaker_id,
            "feeder_label": label,
            "text_xml_id": _txt(row.get("text_xml_id")),
            "raw_text": label,
            "distance": row.get("distance", ""),
            "status": "ANCHOR_CONFIRMED",
        })

    raw_line_rows = _line_feeder_anchors(
        parsed, frames, rmu_names, source_rows, background_jump_ids
    )
    selected_line_rows, source_validation_rows = _select_unique_line_source_anchors(
        raw_line_rows, source_rows, adjacency, boundary_nodes
    )

    # Replace the optimistic validation row emitted for a duplicated main name.
    duplicate_lookup = {
        (_txt(row.get("breaker_xml_id")), _txt(row.get("feeder_label"))): row
        for row in source_rows
        if row.get("source_uniqueness_status") == "SOURCE_NAME_DUPLICATE_ERROR"
    }
    if duplicate_lookup:
        for row in source_validation_rows:
            key = (_txt(row.get("node_xml_id")), _txt(row.get("feeder_label")))
            src = duplicate_lookup.get(key)
            if src:
                row["status"] = "SOURCE_NAME_DUPLICATE_ERROR"
                row["reason"] = _txt(src.get("source_uniqueness_reason"))

    anchors = main_candidates + selected_line_rows

    # Stable de-duplication.  At this stage each feeder source name is already
    # unique by business rule; this final guard only protects exact repeats.
    unique = []
    seen = set()
    for row in anchors:
        key = (_txt(row.get("node_xml_id")), _txt(row.get("feeder_label")))
        if not all(key) or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return source_rows, source_by_breaker, unique, background_jump_rows, source_validation_rows

def _propagate_anchor_labels(
    anchors: list[dict],
    adjacency: dict[str, set[str]],
    boundary_nodes: set[str],
    source_breaker_ids: set[str],
):
    labels_by_node: dict[str, set[str]] = defaultdict(set)
    evidence_by_node: dict[str, set[str]] = defaultdict(set)

    for anchor in anchors:
        seed = _txt(anchor.get("node_xml_id"))
        label = _txt(anchor.get("feeder_label"))
        if not seed or not label or seed in boundary_nodes:
            continue
        queue = deque([seed])
        visited = {seed}
        while queue:
            current = queue.popleft()
            labels_by_node[current].add(label)
            evidence_by_node[current].add(
                f"{anchor.get('anchor_type','')}:{anchor.get('text_xml_id','') or seed}"
            )

            # A line-title seed may reach its main-station CBreaker, but it may
            # not pass through that breaker into a station bus and leak into a
            # neighbouring outgoing feeder.  A CBreaker-origin seed retains the
            # existing behaviour and starts propagation from that breaker.
            if current in source_breaker_ids and current != seed:
                continue

            for nxt in adjacency.get(current, ()):
                if nxt in visited or nxt in boundary_nodes:
                    continue
                if nxt in source_breaker_ids and nxt != seed:
                    continue
                visited.add(nxt)
                queue.append(nxt)

    return labels_by_node, evidence_by_node


def _direction_to_neighbor(boundary: GObject, neighbor: GObject) -> str:
    if neighbor.tag in LINE_TAGS:
        endpoints = _endpoints(neighbor)
        if endpoints:
            px, py = min(
                endpoints,
                key=lambda p: math.hypot(p[0] - boundary.box.cx, p[1] - boundary.box.cy),
            )
        else:
            px, py = neighbor.box.cx, neighbor.box.cy
    else:
        px, py = neighbor.box.cx, neighbor.box.cy
    dx = float(px) - float(boundary.box.cx)
    dy = float(py) - float(boundary.box.cy)
    if abs(dx) >= abs(dy):
        return "RIGHT" if dx >= 0 else "LEFT"
    return "BOTTOM" if dy >= 0 else "TOP"


def _enrich_nop_sides(
    nop_rows: list[dict],
    by_id: dict[str, GObject],
    adjacency: dict[str, set[str]],
    labels_by_node: dict[str, set[str]],
):
    enriched = []
    direction_order = {"LEFT": 0, "RIGHT": 1, "TOP": 2, "BOTTOM": 3, "UNKNOWN": 4}
    for row in nop_rows:
        # Ambiguous external NOP may contain more than one switch id.
        switch_ids = [
            part.strip() for part in _txt(row.get("switch_xml_id")).split("|") if part.strip()
        ]
        side_records = []
        all_labels = set()
        for switch_id in switch_ids:
            boundary = by_id.get(switch_id)
            if boundary is None:
                continue
            for neighbor_id in sorted(adjacency.get(switch_id, set())):
                neighbor = by_id.get(neighbor_id)
                if neighbor is None:
                    continue
                labels = set(labels_by_node.get(neighbor_id, set()))
                all_labels.update(labels)
                direction = _direction_to_neighbor(boundary, neighbor)
                side_records.append({
                    "switch_xml_id": switch_id,
                    "direction": direction,
                    "neighbor_xml_id": neighbor_id,
                    "neighbor_tag": neighbor.tag,
                    "feeder_labels": " | ".join(sorted(labels)),
                    "status": (
                        "CONFIRMED" if len(labels) == 1 else
                        "CONFLICT" if len(labels) > 1 else
                        "UNRESOLVED"
                    ),
                })
        side_records.sort(key=lambda x: (
            direction_order.get(x["direction"], 9), x["neighbor_xml_id"]
        ))
        row = dict(row)
        row["side_count"] = len(side_records)
        row["side_feeders"] = " ; ".join(
            f"{x['direction']}:{x['feeder_labels'] or '-'}[{x['neighbor_xml_id']}]"
            for x in side_records
        )
        row["feeder_labels"] = " | ".join(sorted(all_labels))

        # Business rule: every physical side of a NOP must resolve to exactly
        # one feeder/main-station source.  Counting the union of labels is not
        # enough: a side carrying two source names is an error even if the
        # opposite side is also populated.  Group neighbour records by visual
        # direction so multiple XML segments on the same physical side are
        # evaluated together.
        side_groups: dict[str, set[str]] = defaultdict(set)
        for item in side_records:
            direction = _txt(item.get("direction")) or "UNKNOWN"
            labels = {
                part.strip() for part in _txt(item.get("feeder_labels")).split("|")
                if part.strip()
            }
            side_groups[direction].update(labels)
        side_group_rows = []
        for direction in sorted(side_groups, key=lambda x: direction_order.get(x, 9)):
            labels = side_groups[direction]
            status = (
                "CONFIRMED" if len(labels) == 1 else
                "MULTI_SOURCE_ERROR" if len(labels) > 1 else
                "NO_SOURCE_ERROR"
            )
            side_group_rows.append({
                "direction": direction,
                "feeder_labels": " | ".join(sorted(labels)),
                "status": status,
            })

        if not switch_ids:
            boundary_status = _txt(row.get("status"))
        elif any(x["status"] == "MULTI_SOURCE_ERROR" for x in side_group_rows):
            boundary_status = "ERROR_MULTI_SOURCE_ON_SIDE"
        elif any(x["status"] == "NO_SOURCE_ERROR" for x in side_group_rows):
            boundary_status = "ERROR_SOURCE_NOT_FOUND_ON_SIDE"
        elif len(side_group_rows) >= 2:
            boundary_status = "CONFIRMED_TWO_SIDES"
        elif len(side_group_rows) == 1:
            boundary_status = "PARTIAL_ONE_SIDE"
        else:
            boundary_status = "UNRESOLVED"

        row["boundary_status"] = boundary_status
        row["source_side_summary"] = " ; ".join(
            f"{x['direction']}={x['feeder_labels'] or '-'}({x['status']})"
            for x in side_group_rows
        )
        row["side_group_rows"] = side_group_rows
        row["side_records"] = side_records
        enriched.append(row)
    return enriched


def _display_name_for_network_object(obj: GObject, parsed: ParsedG) -> str:
    p_name = _txt(obj.attrs.get("p_NameString"))
    if p_name:
        return p_name
    candidates = []
    for text_obj in parsed.objects:
        if text_obj.tag.lower() != "text" or _is_nop_text(text_obj):
            continue
        text = _txt(text_obj.attrs.get("ts"))
        if not text:
            continue
        distance = float(text_obj.box.edge_distance(obj.box))
        if distance <= 90.0:
            candidates.append((distance, int(text_obj.xml_index), text))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][2]


def _analyze_rmu_ownership(
    parser,
    parsed: ParsedG,
    frames: list[RmuFrame],
    rmu_names,
    boundary_nodes: set[str],
    labels_by_node: dict[str, set[str]],
    adjacency: dict[str, set[str]],
):
    """Resolve one feeder for each RMU from its non-NOP Y*/Q* switches.

    Whole-graph business rule:
      * a red-NOP Y*/Q* switch is a topology boundary and does not vote for
        cabinet ownership;
      * every other Y*/Q* switch must resolve to exactly one feeder;
      * all non-NOP Y*/Q* switches in the same RMU must agree on the same
        feeder.  There is deliberately no majority-vote fallback;
      * zero or multiple feeder ownership is a topology error and is reported
        as a likely NOP configuration/topology problem.
    """
    rows: list[dict] = []
    port_rows: list[dict] = []

    for frame in frames:
        frame_key = _frame_key(frame)
        name_info = rmu_names.get(frame_key, {})
        rmu_name = _txt(name_info.get("name"))
        frame_id = _txt(frame.frame.xml_id)
        frame_ports = list(_named_yq_switches(parser, parsed, frame))

        non_nop_feeders: set[str] = set()
        all_non_nop_labels: set[str] = set()
        non_nop_details: list[str] = []
        nop_details: list[str] = []
        port_error_types: set[str] = set()
        non_nop_port_count = 0
        nop_port_count = 0

        for device, logical_name in frame_ports:
            device_id = _txt(device.xml_id)
            if not device_id:
                continue

            if device_id in boundary_nodes:
                nop_port_count += 1
                side_labels: set[str] = set()
                side_evidence = []
                for neighbor_id in sorted(adjacency.get(device_id, set())):
                    labels = set(labels_by_node.get(neighbor_id, set()))
                    side_labels.update(labels)
                    side_evidence.append(
                        f"{neighbor_id}={'|'.join(sorted(labels)) or '-'}"
                    )
                nop_details.append(
                    f"{logical_name}={'|'.join(sorted(side_labels)) or '-'}"
                )
                port_rows.append({
                    "file_name": parsed.path.name,
                    "rmu_name": rmu_name,
                    "frame_xml_id": frame_id,
                    "port_name": logical_name,
                    "port_xml_id": device_id,
                    "is_nop": "YES",
                    "status": "NOP_BOUNDARY",
                    "primary_feeder": "",
                    "candidate_feeders": " | ".join(sorted(side_labels)),
                    "error_type": "",
                    "evidence": " ; ".join(side_evidence),
                })
                continue

            non_nop_port_count += 1
            labels = set(labels_by_node.get(device_id, set()))
            all_non_nop_labels.update(labels)
            if len(labels) == 1:
                feeder = next(iter(labels))
                non_nop_feeders.add(feeder)
                status = "CONFIRMED"
                error_type = ""
                non_nop_details.append(f"{logical_name}={feeder}")
            elif not labels:
                feeder = ""
                status = "ERROR"
                error_type = "NO_FEEDER_ERROR"
                port_error_types.add(error_type)
                non_nop_details.append(f"{logical_name}=ERROR(NO_FEEDER)")
            else:
                feeder = ""
                status = "ERROR"
                error_type = "MULTI_FEEDER_ERROR"
                port_error_types.add(error_type)
                non_nop_details.append(
                    f"{logical_name}=ERROR({'|'.join(sorted(labels))})"
                )

            port_rows.append({
                "file_name": parsed.path.name,
                "rmu_name": rmu_name,
                "frame_xml_id": frame_id,
                "port_name": logical_name,
                "port_xml_id": device_id,
                "is_nop": "NO",
                "status": status,
                "primary_feeder": feeder,
                "candidate_feeders": " | ".join(sorted(labels)),
                "error_type": error_type,
                "evidence": "reachability=" + (" | ".join(sorted(labels)) or "NONE"),
            })

        if non_nop_port_count == 0:
            status = "ERROR"
            error_type = "NO_FEEDER_ERROR"
            primary = ""
            reason = "RMU没有可参与所属馈线判断的非NOP Y/Q开关；请检查NOP设置和图形拓扑。"
        elif port_error_types:
            status = "ERROR"
            error_type = " | ".join(sorted(port_error_types))
            primary = ""
            reason = (
                "至少一个非NOP Y/Q开关没有唯一所属馈线。正常设备必须且只能属于一条馈线；"
                "请检查附近NOP是否漏设、误设或拓扑连接是否被错误截断。"
            )
        elif len(non_nop_feeders) == 1:
            status = "CONFIRMED"
            error_type = ""
            primary = next(iter(non_nop_feeders))
            reason = (
                f"所有非NOP Y/Q开关均唯一且一致归属 {primary}；"
                "NOP端口仅作为馈线边界，不参与RMU所属馈线判断。"
            )
        elif len(non_nop_feeders) > 1:
            status = "ERROR"
            error_type = "MULTI_FEEDER_ERROR"
            primary = ""
            reason = (
                "同一RMU的非NOP Y/Q开关分别落入多个馈线。一个RMU只能属于一条馈线；"
                "请检查NOP开关是否漏设、识别错误或没有形成正确断点。"
            )
        else:
            status = "ERROR"
            error_type = "NO_FEEDER_ERROR"
            primary = ""
            reason = (
                "RMU的非NOP Y/Q开关未得到所属馈线。正常设备必须有唯一所属馈线；"
                "请检查NOP设置和拓扑连接。"
            )

        rows.append({
            "file_name": parsed.path.name,
            "rmu_name": rmu_name,
            "frame_xml_id": frame_id,
            "name_text_xml_id": _txt(name_info.get("text_xml_id")),
            "status": status,
            "error_type": error_type,
            "primary_feeder": primary,
            "candidate_feeders": " | ".join(sorted(all_non_nop_labels)),
            "port_count": len(frame_ports),
            "non_nop_port_count": non_nop_port_count,
            "nop_port_count": nop_port_count,
            "non_nop_port_feeders": " ; ".join(non_nop_details),
            "nop_port_sides": " ; ".join(nop_details),
            "reason": reason,
        })

    return rows, port_rows


def analyze_whole_graph_topology_file(
    path: Path,
    *,
    extra_edges: Iterable[tuple[str, str]] | None = None,
):
    """Analyze feeder ownership for every electrical object in one G file.

    Pure graphics analysis only: no Oracle access, no model/table lookup, no G
    writeback.  Red RMU NOPs and external pole-switch NOPs are hard boundaries.
    The NOP switch itself deliberately receives no feeder ownership; its
    neighbour sides are reported separately.
    """
    path = Path(path)
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    frames = list(parser.find_rmu_frames(parsed))
    rmu_names = _rmu_name_map(parser, parsed, frames)

    by_id, adjacency, repaired_count = _build_whole_graph(parsed)
    terminal_repaired_count, terminal_repaired_rows = _repair_rmu_terminal_geometry(
        parser, parsed, frames, by_id, adjacency
    )
    applied_extra_edges: list[tuple[str, str]] = []
    for a, b in list(extra_edges or []):
        a = _txt(a)
        b = _txt(b)
        if not a or not b or a not in by_id or b not in by_id or a == b:
            continue
        FeederOwnershipResolver._add_edge(adjacency, a, b)
        applied_extra_edges.append(tuple(sorted((a, b))))

    boundary_nodes, nop_rows = _whole_nop_boundaries(
        parser, parsed, frames, rmu_names
    )
    source_rows, _source_by_breaker, anchors, background_jump_rows, source_validation_rows = _all_feeder_anchors(
        parsed, frames, rmu_names, adjacency, boundary_nodes
    )
    source_breaker_ids = {
        _txt(row.get("breaker_xml_id"))
        for row in source_rows
        if _txt(row.get("breaker_xml_id"))
    }
    labels_by_node, evidence_by_node = _propagate_anchor_labels(
        anchors, adjacency, boundary_nodes, source_breaker_ids
    )
    nop_rows = _enrich_nop_sides(nop_rows, by_id, adjacency, labels_by_node)

    device_rows = []
    for xml_id, obj in sorted(by_id.items(), key=lambda item: int(item[1].xml_index)):
        if xml_id in boundary_nodes:
            # Business rule for this new whole-graph analyzer: NOP switches are
            # boundaries only.  Do not assign a feeder to the NOP switch itself.
            continue
        labels = set(labels_by_node.get(xml_id, set()))
        if len(labels) == 1:
            status = "CONFIRMED"
            error_type = ""
            primary = next(iter(labels))
            reason = "该非NOP设备与唯一馈线锚点在同一不跨越红色NOP的电气拓扑区域。"
        elif len(labels) > 1:
            status = "ERROR"
            error_type = "MULTI_FEEDER_ERROR"
            primary = ""
            reason = (
                "非NOP设备同时可达多个馈线。正常情况下一个设备只能属于一条馈线；"
                "请检查附近NOP是否漏设、误设、未被识别或没有形成正确断点。"
            )
        else:
            status = "ERROR"
            error_type = "NO_FEEDER_ERROR"
            primary = ""
            reason = (
                "非NOP设备没有可达馈线。正常情况下该设备必须属于一条馈线；"
                "请检查附近NOP是否误设、漏设或拓扑是否被错误截断。"
            )

        device_rows.append({
            "file_name": path.name,
            "xml_id": xml_id,
            "tag": obj.tag,
            "display_name": _display_name_for_network_object(obj, parsed),
            "status": status,
            "error_type": error_type,
            "primary_feeder": primary,
            "candidate_feeders": " | ".join(sorted(labels)),
            "topology_degree": len(adjacency.get(xml_id, set())),
            "anchor_evidence": " | ".join(sorted(evidence_by_node.get(xml_id, set()))),
            "link": _txt(obj.attrs.get("link")),
            "node_area": _txt(obj.attrs.get("node_area")),
            "devref": _txt(obj.attrs.get("devref")),
            "reason": reason,
        })

    rmu_rows, rmu_port_rows = _analyze_rmu_ownership(
        parser, parsed, frames, rmu_names, boundary_nodes, labels_by_node, adjacency
    )

    feeder_labels = sorted({
        _txt(row.get("feeder_label")) for row in anchors if _txt(row.get("feeder_label"))
    })
    summary = {
        "file_name": path.name,
        "network_object_count": len(by_id),
        "device_count": len(device_rows),
        "confirmed_count": sum(1 for x in device_rows if x["status"] == "CONFIRMED"),
        # Backward-compatible counters retained for the worker/UI contract.
        "conflict_count": sum(1 for x in device_rows if x.get("error_type") == "MULTI_FEEDER_ERROR"),
        "unresolved_count": sum(1 for x in device_rows if x.get("error_type") == "NO_FEEDER_ERROR"),
        "multi_feeder_error_count": sum(1 for x in device_rows if x.get("error_type") == "MULTI_FEEDER_ERROR"),
        "no_feeder_error_count": sum(1 for x in device_rows if x.get("error_type") == "NO_FEEDER_ERROR"),
        "topology_error_count": sum(1 for x in device_rows if x["status"] == "ERROR"),
        "rmu_count": len(rmu_rows),
        "rmu_confirmed_count": sum(1 for x in rmu_rows if x["status"] == "CONFIRMED"),
        "rmu_error_count": sum(1 for x in rmu_rows if x["status"] == "ERROR"),
        "feeder_labels": feeder_labels,
        "feeder_count": len(feeder_labels),
        "anchor_count": len(anchors),
        "main_station_anchor_count": sum(
            1 for x in anchors if x.get("anchor_type") == "MAIN_STATION_CBREAKER"
        ),
        "line_anchor_count": sum(
            1 for x in anchors if x.get("anchor_type") == "LINE_FEEDER_TEXT"
        ),
        "source_candidate_count": len(source_validation_rows),
        "source_selected_count": sum(
            1 for x in source_validation_rows if x.get("status") == "SOURCE_SELECTED"
        ),
        "source_rejected_count": sum(
            1 for x in source_validation_rows if str(x.get("status", "")).startswith("SOURCE_REJECTED")
        ),
        "source_error_count": sum(
            1 for x in source_validation_rows if str(x.get("status", "")).endswith("ERROR")
        ),
        "excluded_background_jump_label_count": len(background_jump_rows),
        "nop_boundary_count": len(boundary_nodes),
        "pole_nop_count": sum(1 for x in nop_rows if x.get("nop_type") == "POLE_NOP"),
        "rmu_nop_count": sum(1 for x in nop_rows if x.get("nop_type") == "RMU_NOP"),
        "strict_geometry_repair_count": repaired_count + terminal_repaired_count,
        "line_geometry_repair_count": repaired_count,
        "rmu_terminal_geometry_repair_count": terminal_repaired_count,
    }
    return {
        "summary": summary,
        "source_rows": source_rows,
        "anchor_rows": anchors,
        "source_validation_rows": source_validation_rows,
        "background_jump_rows": background_jump_rows,
        "nop_rows": nop_rows,
        "rmu_rows": rmu_rows,
        "rmu_port_rows": rmu_port_rows,
        "device_rows": device_rows,
        "terminal_repair_rows": terminal_repaired_rows,
        "debug": {
            "parser": parser,
            "parsed": parsed,
            "frames": frames,
            "rmu_names": rmu_names,
            "by_id": by_id,
            "adjacency": adjacency,
            "boundary_nodes": boundary_nodes,
            "labels_by_node": labels_by_node,
            "evidence_by_node": evidence_by_node,
            "anchors": anchors,
            "source_breaker_ids": source_breaker_ids,
            "applied_extra_edges": applied_extra_edges,
        },
    }



def _clone_adjacency(adjacency: dict[str, set[str]]) -> dict[str, set[str]]:
    return {str(key): set(values) for key, values in adjacency.items()}


def _graph_components(
    adjacency: dict[str, set[str]],
    blocked_nodes: set[str],
):
    component_of: dict[str, int] = {}
    components: list[set[str]] = []
    for start in adjacency:
        if start in blocked_nodes or start in component_of:
            continue
        idx = len(components)
        nodes: set[str] = set()
        queue = deque([start])
        component_of[start] = idx
        while queue:
            current = queue.popleft()
            nodes.add(current)
            for nxt in adjacency.get(current, set()):
                if nxt in blocked_nodes or nxt in component_of:
                    continue
                component_of[nxt] = idx
                queue.append(nxt)
        components.append(nodes)
    return component_of, components


def _node_error_counts(
    by_id: dict[str, GObject],
    boundary_nodes: set[str],
    labels_by_node: dict[str, set[str]],
):
    no_feeder = 0
    multi_feeder = 0
    for xml_id in by_id:
        if xml_id in boundary_nodes:
            continue
        labels = set(labels_by_node.get(xml_id, set()))
        if not labels:
            no_feeder += 1
        elif len(labels) > 1:
            multi_feeder += 1
    return no_feeder, multi_feeder


def _line_endpoint_entries(
    by_id: dict[str, GObject],
    component_of: dict[str, int],
    blocked_nodes: set[str],
):
    entries = []
    for xml_id, obj in by_id.items():
        if xml_id in blocked_nodes or obj.tag not in LINE_TAGS:
            continue
        component = component_of.get(xml_id)
        if component is None:
            continue
        for endpoint_index, point in enumerate(_endpoints(obj)):
            entries.append({
                "xml_id": xml_id,
                "tag": obj.tag,
                "component": component,
                "endpoint_index": int(endpoint_index),
                "x": float(point[0]),
                "y": float(point[1]),
            })
    return entries


def _find_endpoint_gap_candidates(
    *,
    by_id: dict[str, GObject],
    adjacency: dict[str, set[str]],
    boundary_nodes: set[str],
    labels_by_node: dict[str, set[str]],
    diagnostic_max_distance: float = 12.0,
):
    """Find likely missing line-to-line endpoint links.

    Auto repair is intentionally narrow: one side must be in a component that
    already has exactly one feeder, the other side must currently have no
    feeder, and the endpoint gap must be only slightly wider than the proven
    3G strict tolerance.  Larger gaps are reported for inspection but are not
    automatically changed.
    """
    component_of, components = _graph_components(adjacency, boundary_nodes)
    component_labels: list[set[str]] = []
    for nodes in components:
        labels: set[str] = set()
        for node in nodes:
            labels.update(labels_by_node.get(node, set()))
        component_labels.append(labels)

    entries = _line_endpoint_entries(by_id, component_of, boundary_nodes)
    if not entries:
        return []

    cell_size = max(1.0, float(diagnostic_max_distance))
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for idx, item in enumerate(entries):
        key = (
            int(math.floor(item["x"] / cell_size)),
            int(math.floor(item["y"] / cell_size)),
        )
        grid[key].append(idx)

    pairs: dict[tuple[tuple[str, int], tuple[str, int]], dict] = {}
    for idx, item in enumerate(entries):
        cx = int(math.floor(item["x"] / cell_size))
        cy = int(math.floor(item["y"] / cell_size))
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for other_idx in grid.get((gx, gy), []):
                    if other_idx <= idx:
                        continue
                    other = entries[other_idx]
                    if item["xml_id"] == other["xml_id"]:
                        continue
                    if item["component"] == other["component"]:
                        continue
                    if other["xml_id"] in adjacency.get(item["xml_id"], set()):
                        continue
                    distance = math.hypot(item["x"] - other["x"], item["y"] - other["y"])
                    if distance <= ENDPOINT_TOLERANCE or distance > diagnostic_max_distance:
                        continue
                    labels_a = component_labels[item["component"]]
                    labels_b = component_labels[other["component"]]
                    # The only auto-repairable business situation is a feeder-
                    # confirmed component beside an otherwise feeder-less island.
                    if not (
                        (len(labels_a) == 1 and len(labels_b) == 0)
                        or (len(labels_b) == 1 and len(labels_a) == 0)
                    ):
                        continue
                    if len(labels_a) == 1:
                        anchor_side, island_side = item, other
                        feeder = next(iter(labels_a))
                        island_component = other["component"]
                    else:
                        anchor_side, island_side = other, item
                        feeder = next(iter(labels_b))
                        island_component = item["component"]
                    pair_key = tuple(sorted((
                        (item["xml_id"], item["endpoint_index"]),
                        (other["xml_id"], other["endpoint_index"]),
                    )))
                    pairs[pair_key] = {
                        "left_xml_id": item["xml_id"],
                        "left_tag": item["tag"],
                        "left_endpoint": item["endpoint_index"],
                        "left_x": item["x"],
                        "left_y": item["y"],
                        "right_xml_id": other["xml_id"],
                        "right_tag": other["tag"],
                        "right_endpoint": other["endpoint_index"],
                        "right_x": other["x"],
                        "right_y": other["y"],
                        "distance": float(distance),
                        "feeder_label": feeder,
                        "island_component": island_component,
                        "island_node_count": len(components[island_component]),
                        "auto_distance_ok": distance <= WHOLE_GRAPH_AUTO_REPAIR_MAX_DISTANCE,
                        "anchor_xml_id": anchor_side["xml_id"],
                        "island_xml_id": island_side["xml_id"],
                    }

    rows = list(pairs.values())
    # Reciprocal uniqueness is evaluated only inside the automatic repair
    # radius.  A further-away diagnostic candidate is still shown in the HTML
    # but does not make a nearby unique 3-4.5G connection unsafe.
    endpoint_to_auto_pairs: dict[tuple[str, int], list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        if not row["auto_distance_ok"]:
            continue
        endpoint_to_auto_pairs[(row["left_xml_id"], row["left_endpoint"])].append(idx)
        endpoint_to_auto_pairs[(row["right_xml_id"], row["right_endpoint"])].append(idx)
    for idx, row in enumerate(rows):
        left_key = (row["left_xml_id"], row["left_endpoint"])
        right_key = (row["right_xml_id"], row["right_endpoint"])
        row["reciprocal_unique"] = bool(
            row["auto_distance_ok"]
            and len(endpoint_to_auto_pairs.get(left_key, [])) == 1
            and len(endpoint_to_auto_pairs.get(right_key, [])) == 1
        )
        if not row["auto_distance_ok"]:
            row["candidate_status"] = "REVIEW_DISTANCE_TOO_LARGE"
        elif not row["reciprocal_unique"]:
            row["candidate_status"] = "REVIEW_AMBIGUOUS_ENDPOINT"
        else:
            row["candidate_status"] = "SAFE_CANDIDATE"
    rows.sort(key=lambda row: (float(row["distance"]), row["left_xml_id"], row["right_xml_id"]))
    return rows


def _simulate_safe_topology_repairs(analysis: dict):
    """Iteratively accept only repairs that strictly improve topology safety."""
    debug = analysis["debug"]
    by_id = debug["by_id"]
    boundary_nodes = set(debug["boundary_nodes"])
    anchors = list(debug["anchors"])
    source_breaker_ids = set(debug["source_breaker_ids"])
    adjacency = _clone_adjacency(debug["adjacency"])

    accepted_edges: list[tuple[str, str]] = []
    repair_rows: dict[tuple[tuple[str, int], tuple[str, int]], dict] = {}

    for pass_index in range(1, WHOLE_GRAPH_AUTO_REPAIR_MAX_PASSES + 1):
        labels_by_node, _ = _propagate_anchor_labels(
            anchors, adjacency, boundary_nodes, source_breaker_ids
        )
        no_before, multi_before = _node_error_counts(by_id, boundary_nodes, labels_by_node)
        candidates = _find_endpoint_gap_candidates(
            by_id=by_id,
            adjacency=adjacency,
            boundary_nodes=boundary_nodes,
            labels_by_node=labels_by_node,
        )
        if not candidates:
            break

        applied_this_pass = False
        for candidate in candidates:
            key = tuple(sorted((
                (candidate["left_xml_id"], int(candidate["left_endpoint"])),
                (candidate["right_xml_id"], int(candidate["right_endpoint"])),
            )))
            row = repair_rows.setdefault(key, dict(candidate))
            row.update({k: v for k, v in candidate.items() if k not in row or row[k] in (None, "")})
            row.setdefault("repair_status", candidate["candidate_status"])
            row.setdefault("repair_reason", "")
            row.setdefault("errors_before", no_before + multi_before)
            row.setdefault("errors_after", "")
            row.setdefault("pass_index", pass_index)

            if not candidate["reciprocal_unique"]:
                if candidate["candidate_status"] == "REVIEW_DISTANCE_TOO_LARGE":
                    row["repair_reason"] = (
                        f"端点距离 {candidate['distance']:.3f}G 超过自动修复上限 "
                        f"{WHOLE_GRAPH_AUTO_REPAIR_MAX_DISTANCE:.1f}G，仅报告供人工确认。"
                    )
                else:
                    row["repair_reason"] = "端点附近存在多个合理候选，不能自动猜测连接。"
                continue

            trial = _clone_adjacency(adjacency)
            FeederOwnershipResolver._add_edge(
                trial, candidate["left_xml_id"], candidate["right_xml_id"]
            )
            trial_labels, _ = _propagate_anchor_labels(
                anchors, trial, boundary_nodes, source_breaker_ids
            )
            no_after, multi_after = _node_error_counts(by_id, boundary_nodes, trial_labels)
            improves = (no_after + multi_after) < (no_before + multi_before)
            safe_multi = multi_after <= multi_before
            left_labels = set(trial_labels.get(candidate["left_xml_id"], set()))
            right_labels = set(trial_labels.get(candidate["right_xml_id"], set()))
            endpoint_unique = len(left_labels) == 1 and left_labels == right_labels

            row["errors_before"] = no_before + multi_before
            row["errors_after"] = no_after + multi_after
            row["no_feeder_before"] = no_before
            row["no_feeder_after"] = no_after
            row["multi_feeder_before"] = multi_before
            row["multi_feeder_after"] = multi_after

            if not (improves and safe_multi and endpoint_unique):
                row["repair_status"] = "REVIEW_SIMULATION_REJECTED"
                row["repair_reason"] = (
                    "模拟补链没有同时满足：拓扑错误减少、不新增多馈线、补链两端归属同一唯一馈线；"
                    "因此不自动修改 G。"
                )
                continue

            adjacency = trial
            edge = tuple(sorted((candidate["left_xml_id"], candidate["right_xml_id"])))
            if edge not in accepted_edges:
                accepted_edges.append(edge)
            row["repair_status"] = "AUTO_FIXED"
            row["repair_reason"] = (
                f"唯一近邻端点，距离 {candidate['distance']:.3f}G；模拟补链后错误从 "
                f"{no_before + multi_before} 降至 {no_after + multi_after}，且未新增多馈线冲突。"
            )
            row["applied_feeder"] = next(iter(left_labels)) if left_labels else candidate["feeder_label"]
            applied_this_pass = True
            # Recompute components and ownership before considering another gap.
            break

        if not applied_this_pass:
            break

    final_labels, _ = _propagate_anchor_labels(
        anchors, adjacency, boundary_nodes, source_breaker_ids
    )
    no_after, multi_after = _node_error_counts(by_id, boundary_nodes, final_labels)
    rows = list(repair_rows.values())
    rows.sort(key=lambda row: (
        0 if row.get("repair_status") == "AUTO_FIXED" else 1,
        float(row.get("distance") or 0.0),
        row.get("left_xml_id", ""),
        row.get("right_xml_id", ""),
    ))
    return accepted_edges, rows, no_after, multi_after


def _append_topology_reference(
    element: ET.Element,
    attr_name: str,
    own_endpoint: int,
    other_endpoint: int,
    other_xml_id: str,
):
    raw = _txt(element.get(attr_name))
    items = [item.strip() for item in raw.split(";") if item.strip()]
    for item in items:
        parts = [part.strip() for part in item.split(",")]
        if parts and parts[-1] == str(other_xml_id):
            return False
    items.append(f"{int(own_endpoint)},{int(other_endpoint)},{other_xml_id}")
    element.set(attr_name, ";".join(items))
    return True


def _fixed_g_name(source: Path) -> str:
    name = source.name
    suffix = ".sln.pic.g"
    if name.lower().endswith(suffix):
        return name[:-len(suffix)] + ".topology-fixed.sln.pic.g"
    return source.stem + ".topology-fixed.g"


def _write_fixed_g_file(source: Path, target: Path, repair_rows: list[dict]) -> Path | None:
    applied = [row for row in repair_rows if row.get("repair_status") == "AUTO_FIXED"]
    if not applied:
        return None
    tree = ET.parse(source)
    root = tree.getroot()
    elements_by_id = {
        _txt(element.get("id")): element
        for element in root.iter()
        if _txt(element.get("id"))
    }
    for row in applied:
        left_id = _txt(row.get("left_xml_id"))
        right_id = _txt(row.get("right_xml_id"))
        left = elements_by_id.get(left_id)
        right = elements_by_id.get(right_id)
        if left is None or right is None:
            raise ValueError(f"自动拓扑修复对象不存在：{left_id} ↔ {right_id}")
        left_ep = int(row.get("left_endpoint", 0))
        right_ep = int(row.get("right_endpoint", 0))
        for attr in ("link", "node_area"):
            _append_topology_reference(left, attr, left_ep, right_ep, right_id)
            _append_topology_reference(right, attr, right_ep, left_ep, left_id)

    target.parent.mkdir(parents=True, exist_ok=True)
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target


def _feeder_color_map(feeders: list[str]) -> dict[str, str]:
    palette = [
        "#1976d2", "#ef6c00", "#2e7d32", "#8e24aa", "#d32f2f",
        "#00838f", "#6d4c41", "#5e35b1", "#558b2f", "#c2185b",
    ]
    return {label: palette[idx % len(palette)] for idx, label in enumerate(sorted(feeders))}


def _line_points_for_svg(obj: GObject):
    segments = _segments(obj)
    if not segments:
        return []
    points = [segments[0][0]]
    points.extend(seg[1] for seg in segments)
    return points


def _write_topology_svg(
    path: Path,
    analysis: dict,
    repair_rows: list[dict],
    *,
    after: bool,
):
    debug = analysis["debug"]
    parsed: ParsedG = debug["parsed"]
    by_id: dict[str, GObject] = debug["by_id"]
    device_map = {row["xml_id"]: row for row in analysis["device_rows"]}
    feeders = analysis["summary"].get("feeder_labels", [])
    color_map = _feeder_color_map(feeders)

    boxes = [obj.box for obj in by_id.values()]
    boxes.extend(frame.frame.box for frame in debug.get("frames", []))
    if not boxes:
        min_x = min_y = 0.0
        max_x = max_y = 1000.0
    else:
        min_x = min(box.left for box in boxes) - 80.0
        min_y = min(box.top for box in boxes) - 80.0
        max_x = max(box.right for box in boxes) + 80.0
        max_y = max(box.bottom for box in boxes) + 80.0
    width = max(100.0, max_x - min_x)
    height = max(100.0, max_y - min_y)

    def esc_attr(value):
        return html.escape(str(value), quote=True)

    svg = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{min_x:.1f} {min_y:.1f} {width:.1f} {height:.1f}' role='img'>",
        "<rect x='0' y='0' width='100%' height='100%' fill='#ffffff'/>",
        "<style>.t{font-family:Segoe UI,Microsoft YaHei,sans-serif;font-size:28px;paint-order:stroke;stroke:#fff;stroke-width:5px;stroke-linejoin:round}.small{font-size:22px}.rmu{fill:none;stroke:#555;stroke-width:4;stroke-dasharray:12 8}.err{stroke:#555;stroke-width:4}.nop{stroke:#d81b60;stroke-width:8}.repair{stroke:#00a86b;stroke-width:10}.gap{stroke:#e53935;stroke-width:8;stroke-dasharray:18 12}</style>",
    ]

    for xml_id, obj in sorted(by_id.items(), key=lambda kv: int(kv[1].xml_index)):
        row = device_map.get(xml_id, {})
        feeder = _txt(row.get("primary_feeder"))
        color = color_map.get(feeder, "#555555") if feeder else "#555555"
        if obj.tag in LINE_TAGS:
            pts = _line_points_for_svg(obj)
            if len(pts) >= 2:
                points = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                svg.append(
                    f"<polyline points='{points}' fill='none' stroke='{color}' stroke-width='5' stroke-linejoin='round' stroke-linecap='round'/>"
                )
        elif obj.tag == "Pole":
            svg.append(f"<circle cx='{obj.box.cx:.1f}' cy='{obj.box.cy:.1f}' r='7' fill='{color}'/>")
        elif obj.tag in {"CBreaker", "CBreakerDis", "Disconnector", "BusDis", "ZhaiWaiJieDiDaoZha"}:
            svg.append(
                f"<circle cx='{obj.box.cx:.1f}' cy='{obj.box.cy:.1f}' r='5' fill='{color}' opacity='0.85'/>")

    rmu_names = debug.get("rmu_names", {})
    for frame in debug.get("frames", []):
        box = frame.frame.box
        info = rmu_names.get(_frame_key(frame), {})
        name = _txt(info.get("name")) or _txt(frame.frame.xml_id)
        svg.append(
            f"<rect class='rmu' x='{box.x:.1f}' y='{box.y:.1f}' width='{box.w:.1f}' height='{box.h:.1f}'/>"
        )
        svg.append(
            f"<text class='t small' x='{box.right + 12:.1f}' y='{box.cy:.1f}' fill='#333'>{esc_attr(name)}</text>"
        )

    for row in analysis.get("anchor_rows", []):
        node = by_id.get(_txt(row.get("node_xml_id")))
        if node is None:
            continue
        label = _txt(row.get("feeder_label"))
        color = color_map.get(label, "#111")
        svg.append(
            f"<circle cx='{node.box.cx:.1f}' cy='{node.box.cy:.1f}' r='10' fill='{color}'/>"
        )
        svg.append(
            f"<text class='t' x='{node.box.cx + 14:.1f}' y='{node.box.cy - 14:.1f}' fill='#111'>{esc_attr(label)}</text>"
        )

    for nop in analysis.get("nop_rows", []):
        for switch_id in [x.strip() for x in _txt(nop.get("switch_xml_id")).split("|") if x.strip()]:
            obj = by_id.get(switch_id)
            if obj is None:
                continue
            x, y = obj.box.cx, obj.box.cy
            size = 16.0
            svg.append(f"<line class='nop' x1='{x-size:.1f}' y1='{y-size:.1f}' x2='{x+size:.1f}' y2='{y+size:.1f}'/>")
            svg.append(f"<line class='nop' x1='{x-size:.1f}' y1='{y+size:.1f}' x2='{x+size:.1f}' y2='{y-size:.1f}'/>")

    for row in repair_rows:
        if row.get("repair_status") != "AUTO_FIXED":
            continue
        x1, y1 = float(row["left_x"]), float(row["left_y"])
        x2, y2 = float(row["right_x"]), float(row["right_y"])
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        if after:
            svg.append(f"<line class='repair' x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}'/>")
            svg.append(f"<circle cx='{mx:.1f}' cy='{my:.1f}' r='13' fill='#00a86b'/>")
            svg.append(f"<text class='t small' x='{mx+18:.1f}' y='{my-18:.1f}' fill='#007a4d'>已修复</text>")
        else:
            svg.append(f"<line class='gap' x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}'/>")
            size = 18.0
            svg.append(f"<line class='gap' x1='{mx-size:.1f}' y1='{my-size:.1f}' x2='{mx+size:.1f}' y2='{my+size:.1f}'/>")
            svg.append(f"<line class='gap' x1='{mx-size:.1f}' y1='{my+size:.1f}' x2='{mx+size:.1f}' y2='{my-size:.1f}'/>")
            svg.append(f"<text class='t small' x='{mx+20:.1f}' y='{my-20:.1f}' fill='#c62828'>断点 {esc_attr(row.get('left_xml_id'))}↔{esc_attr(row.get('right_xml_id'))}</text>")

    svg.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(svg), encoding="utf-8")
    return path

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
        status_text = _txt(row.get("status")).upper()
        is_error = (
            status_text == "ERROR"
            or status_text.endswith("ERROR")
            or bool(_txt(row.get("error_type")))
        )
        tr_class = " class='error-row'" if is_error else ""
        body.append(
            f"<tr{tr_class}>" + "".join(
                f"<td>{_esc(row.get(key, ''))}</td>" for key, _ in columns
            ) + "</tr>"
        )
    if not body:
        body.append(f"<tr><td colspan='{len(columns)}'>无记录</td></tr>")
    return (
        f"<section><h2>{_esc(title)}</h2><div class='table-wrap'><table>"
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody>"
        f"</table></div></section>"
    )


def _write_html(
    path: Path,
    before_analysis: dict,
    after_analysis: dict,
    repair_rows: list[dict],
    *,
    before_svg_path: Path,
    after_svg_path: Path,
    fixed_g_path: Path | None,
):
    before = before_analysis["summary"]
    after = after_analysis["summary"]
    feeders = "、".join(after["feeder_labels"]) or "-"
    auto_fixed = [row for row in repair_rows if row.get("repair_status") == "AUTO_FIXED"]
    review_rows = [row for row in repair_rows if row.get("repair_status") != "AUTO_FIXED"]

    blocks = [
        "<article>",
        f"<h1>{_esc(after['file_name'])}</h1>",
        "<div class='cards'>",
        f"<div><b>识别馈线</b><span>{_esc(feeders)}</span></div>",
        f"<div><b>最终馈线源</b><span>{after['anchor_count']}</span></div>",
        f"<div><b>源候选 / 选中</b><span>{after.get('source_candidate_count', 0)} / {after.get('source_selected_count', 0)}</span></div>",
        f"<div><b>源唯一性异常</b><span>{after.get('source_error_count', 0)}</span></div>",
        f"<div><b>排除背景跳转标签</b><span>{after.get('excluded_background_jump_label_count', 0)}</span></div>",
        f"<div><b>修复前拓扑异常</b><span>{before['topology_error_count']}</span></div>",
        f"<div><b>修复后拓扑异常</b><span>{after['topology_error_count']}</span></div>",
        f"<div><b>自动修复连接</b><span>{len(auto_fixed)}</span></div>",
        f"<div><b>待人工确认断点</b><span>{len(review_rows)}</span></div>",
        f"<div><b>修复前无馈线</b><span>{before['no_feeder_error_count']}</span></div>",
        f"<div><b>修复后无馈线</b><span>{after['no_feeder_error_count']}</span></div>",
        f"<div><b>修复前多馈线</b><span>{before['multi_feeder_error_count']}</span></div>",
        f"<div><b>修复后多馈线</b><span>{after['multi_feeder_error_count']}</span></div>",
        f"<div><b>RMU确认 / 异常</b><span>{after['rmu_confirmed_count']} / {after['rmu_error_count']}</span></div>",
        f"<div><b>RMU / 柱上 NOP</b><span>{after['rmu_nop_count']} / {after['pole_nop_count']}</span></div>",
        "</div>",
    ]

    if auto_fixed:
        fixed_name = fixed_g_path.name if fixed_g_path else "-"
        blocks.append(
            "<div class='ok'><b>已自动修复拓扑连接。</b> "
            f"共补充 {len(auto_fixed)} 处唯一且经模拟验证安全的连接；"
            f"修复后的 G 文件：<code>{_esc(fixed_name)}</code>。"
            "原始 G 文件未被覆盖。</div>"
        )
    elif before["topology_error_count"]:
        blocks.append(
            "<div class='alert'>检测到拓扑异常，但没有找到满足“唯一近邻 + 模拟后错误减少 + 不新增多馈线”"
            "全部条件的自动修复连接。请查看下方断点诊断和拓扑异常设备。</div>"
        )
    else:
        blocks.append("<div class='ok'>整图非NOP设备及RMU所属馈线唯一性检查通过，无需自动修复。</div>")

    blocks.append(
        "<section><div class='diagram-heading'><h2>修复前拓扑图</h2>"
        "<div class='diagram-controls' aria-label='修复前拓扑图缩放控制'>"
        "<button type='button' data-zoom-action='out' title='缩小'>− 缩小</button>"
        "<span class='zoom-value' aria-live='polite'>100%</span>"
        "<button type='button' data-zoom-action='in' title='放大'>+ 放大</button>"
        "<button type='button' data-zoom-action='reset'>重置</button>"
        "<button type='button' data-zoom-action='fit'>适应窗口</button>"
        "<button type='button' data-zoom-action='fullscreen'>全屏查看</button>"
        "</div></div>"
        "<p class='legend'>红色虚线/× = 程序判定的可安全修复断点；灰色区域通常表示尚未得到唯一馈线。可用按钮或 Ctrl+鼠标滚轮独立缩放本图。</p>"
        f"<div class='topology-viewer' data-topology-viewer data-zoom='100'><div class='diagram'><img src='{_esc(before_svg_path.name)}' alt='修复前拓扑图'></div></div></section>"
    )
    blocks.append(
        "<section><div class='diagram-heading'><h2>修复后拓扑图</h2>"
        "<div class='diagram-controls' aria-label='修复后拓扑图缩放控制'>"
        "<button type='button' data-zoom-action='out' title='缩小'>− 缩小</button>"
        "<span class='zoom-value' aria-live='polite'>100%</span>"
        "<button type='button' data-zoom-action='in' title='放大'>+ 放大</button>"
        "<button type='button' data-zoom-action='reset'>重置</button>"
        "<button type='button' data-zoom-action='fit'>适应窗口</button>"
        "<button type='button' data-zoom-action='fullscreen'>全屏查看</button>"
        "</div></div>"
        "<p class='legend'>绿色粗线/圆点 = 本次自动补充的拓扑连接；所有馈线颜色在修复前后保持一致。可用按钮或 Ctrl+鼠标滚轮独立缩放本图。</p>"
        f"<div class='topology-viewer' data-topology-viewer data-zoom='100'><div class='diagram'><img src='{_esc(after_svg_path.name)}' alt='修复后拓扑图'></div></div></section>"
    )

    blocks.append(_html_table("拓扑连接修复 / 断点诊断", repair_rows, [
        ("repair_status", "处理结果"), ("left_xml_id", "对象A XML"),
        ("left_tag", "对象A类型"), ("left_endpoint", "A端点"),
        ("right_xml_id", "对象B XML"), ("right_tag", "对象B类型"),
        ("right_endpoint", "B端点"), ("distance", "端点距离(G)"),
        ("feeder_label", "连接侧馈线"), ("island_node_count", "受影响孤立节点"),
        ("errors_before", "修复前错误"), ("errors_after", "修复后错误"),
        ("repair_reason", "判定依据"),
    ]))
    blocks.append(_html_table("馈线源唯一性检查（一个主站出线 / 一个文字主站源只能有一个名字）", after_analysis.get("source_validation_rows", []), [
        ("source_type", "源类型"), ("feeder_label", "主站/馈线名称"),
        ("node_xml_id", "拓扑节点XML"), ("text_xml_id", "文字XML"),
        ("component_id", "拓扑区域"), ("topology_degree", "节点邻接数"),
        ("nop_adjacent", "是否NOP侧区域"), ("main_station_labels", "区域内主网设备源"),
        ("status", "唯一性状态"), ("reason", "判定说明"),
    ]))
    blocks.append(_html_table("最终馈线锚点（仅唯一源参与传播）", after_analysis["anchor_rows"], [
        ("anchor_type", "锚点类型"), ("feeder_label", "馈线"),
        ("node_xml_id", "拓扑节点XML"), ("text_xml_id", "文字XML"),
        ("raw_text", "原始文字"), ("distance", "距离"),
        ("nearest_device_xml_id", "最近设备XML"),
        ("nearest_device_tag", "最近设备类型"),
        ("nearest_device_distance", "最近设备距离"),
    ]))
    blocks.append(_html_table("已排除的背景跳转标签（绝不作为馈线锚点）", after_analysis.get("background_jump_rows", []), [
        ("background_xml_id", "背景XML"), ("background_tag", "背景类型"),
        ("label_text_xml_id", "主网文字XML"), ("label_text", "背景内主网文字"),
        ("target_text_xml_id", "目标文字XML"), ("target_text", "括号目标"),
        ("target_rmu_name", "目标环网柜名称"), ("group_status", "识别状态"),
    ]))
    blocks.append(_html_table("RMU 所属馈线（按非NOP Y/Q开关唯一一致性判断）", after_analysis["rmu_rows"], [
        ("rmu_name", "RMU名称"), ("frame_xml_id", "RMU框XML"),
        ("status", "状态"), ("primary_feeder", "所属馈线"),
        ("error_type", "异常类型"), ("non_nop_port_feeders", "非NOP开关所属馈线"),
        ("nop_port_sides", "NOP端口两侧馈线"), ("port_count", "端口数"),
        ("non_nop_port_count", "非NOP端口数"), ("nop_port_count", "NOP端口数"),
        ("reason", "判定说明"),
    ]))
    blocks.append(_html_table("红色 NOP 边界（修复后；NOP开关本身不判所属馈线）", after_analysis["nop_rows"], [
        ("nop_type", "NOP类型"), ("nop_text_xml_id", "NOP Text XML"),
        ("rmu_name", "RMU"), ("switch_name", "开关名称/端口"),
        ("switch_xml_id", "边界开关XML"), ("switch_tag", "开关类型"),
        ("side_feeders", "各侧所属馈线"), ("source_side_summary", "各侧源唯一性"),
        ("feeder_labels", "两侧涉及馈线"), ("boundary_status", "边界分析状态"),
        ("status", "识别状态"),
    ]))
    before_errors = [row for row in before_analysis["device_rows"] if row.get("status") == "ERROR"]
    after_errors = [row for row in after_analysis["device_rows"] if row.get("status") == "ERROR"]
    blocks.append(_html_table("修复前拓扑异常设备", before_errors, [
        ("xml_id", "XML_ID"), ("tag", "设备类型"), ("display_name", "图形名称"),
        ("error_type", "异常类型"), ("candidate_feeders", "检测到的馈线"),
        ("topology_degree", "拓扑邻接数"), ("reason", "异常说明"),
    ]))
    blocks.append(_html_table("拓扑异常设备（非NOP设备必须且只能有一个所属馈线）", after_errors, [
        ("xml_id", "XML_ID"), ("tag", "设备类型"), ("display_name", "图形名称"),
        ("error_type", "异常类型"), ("candidate_feeders", "检测到的馈线"),
        ("topology_degree", "拓扑邻接数"), ("reason", "异常说明"),
    ]))
    blocks.append(_html_table("修复后整图设备所属馈线", after_analysis["device_rows"], [
        ("xml_id", "XML_ID"), ("tag", "设备类型"), ("display_name", "图形名称"),
        ("status", "状态"), ("error_type", "异常类型"), ("primary_feeder", "所属馈线"),
        ("candidate_feeders", "候选馈线"), ("topology_degree", "拓扑邻接数"),
        ("anchor_evidence", "馈线锚点证据"), ("reason", "判定说明"),
    ]))
    blocks.append("</article>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>整图馈线拓扑分析与自动修复报告</title><style>
body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#16332c;background:#f7faf8}
article{background:#fff;border:1px solid #dbe8e2;border-radius:12px;padding:20px;margin-bottom:24px}
h1{margin:0 0 14px;color:#075f4a}h2{font-size:17px;margin:24px 0 10px;color:#075f4a}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px}
.cards div{border:1px solid #dbe8e2;background:#f3f9f6;border-radius:8px;padding:10px}.cards b{display:block;font-size:12px;color:#567168}.cards span{display:block;margin-top:4px;font-weight:600}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d9e5df;padding:7px 8px;text-align:left;white-space:nowrap}th{background:#eaf5f0;color:#174f42;position:sticky;top:0}
.note{padding:12px 14px;border-left:4px solid #0b7b60;background:#edf8f4;margin-bottom:18px}
.alert{margin:14px 0;padding:12px 14px;border-left:4px solid #c62828;background:#fff1f1;color:#8b1d1d;font-weight:600}.ok{margin:14px 0;padding:12px 14px;border-left:4px solid #138a64;background:#effaf6;color:#14614d;font-weight:600}.error-row td{background:#fff2f2;color:#941f1f}
.diagram-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.diagram-heading h2{margin-bottom:10px}.diagram-controls{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.diagram-controls button{border:1px solid #b9d3c8;background:#fff;color:#075f4a;border-radius:6px;padding:6px 10px;font:inherit;font-size:12px;font-weight:600;cursor:pointer}.diagram-controls button:hover{background:#edf8f4}.diagram-controls button:active{transform:translateY(1px)}.zoom-value{display:inline-block;min-width:54px;text-align:center;font-weight:700;color:#174f42}.topology-viewer{background:#fff;border-radius:10px}.diagram{border:1px solid #d9e5df;border-radius:10px;padding:10px;background:#fff;overflow:auto;max-width:100%}.diagram img{display:block;width:100%;max-width:none;height:auto;transform-origin:top left}.topology-viewer{min-width:0}section:fullscreen{background:#f7faf8;padding:14px;overflow:hidden}section:fullscreen .topology-viewer{height:calc(100vh - 125px);display:flex;flex-direction:column}section:fullscreen .diagram{flex:1;max-height:none}section:fullscreen .diagram img{max-height:none}.legend{color:#567168;font-size:13px}code{background:#eef4f1;padding:2px 6px;border-radius:4px}
</style></head><body><div class='note'>本模块只针对“整图馈线拓扑分析”新增断点诊断与安全自动修复；既有“环网柜馈线拓扑分析”和“馈线段所属馈线分析”逻辑不修改。馈线源执行严格唯一性规则：主网 Bay/CBreaker 源优先；如果现场只在线路末端写主站/馈线名称（例如 TRUB-BH21）而没有主站设备，则该文字只能在无主网设备源的末端拓扑区域作为唯一兜底源。同一个主站/馈线名称不允许在多个位置同时成为源，同一个源端拓扑区域也不允许出现两个不同主站名字；重复或冲突候选只报告、不传播。带可见背景色、且与“(目标环网柜名称)”成组显示的主网跳转标签会在馈线锚点识别前被强制排除，绝不参与馈线计算。NOP 每一侧也必须最终只得到一个源名称；一侧出现多个名称直接判为源/NOP拓扑异常。自动补链仍只在唯一近邻且模拟安全时写入安全副本，原始 G 永不覆盖。</div>"""
        + "".join(blocks)
        + """<script>
(function(){
  const STEP=20, MIN=20, MAX=400;
  function viewerForControl(control){
    const section=control.closest('section');
    return section ? section.querySelector('[data-topology-viewer]') : null;
  }
  function controlsForViewer(viewer){
    const section=viewer.closest('section');
    return section ? section.querySelector('.diagram-controls') : null;
  }
  function setZoom(viewer, value, resetScroll){
    const img=viewer.querySelector('.diagram img');
    if(!img) return;
    const zoom=Math.max(MIN, Math.min(MAX, Math.round(value/STEP)*STEP));
    viewer.dataset.zoom=String(zoom);
    img.style.width=zoom+'%';
    const controls=controlsForViewer(viewer);
    if(controls){
      const label=controls.querySelector('.zoom-value');
      if(label) label.textContent=zoom+'%';
    }
    if(resetScroll){
      const pane=viewer.querySelector('.diagram');
      if(pane){pane.scrollLeft=0; pane.scrollTop=0;}
    }
  }
  document.querySelectorAll('[data-topology-viewer]').forEach(function(viewer){
    setZoom(viewer, Number(viewer.dataset.zoom||100), false);
    const pane=viewer.querySelector('.diagram');
    if(pane){
      pane.addEventListener('wheel', function(ev){
        if(!ev.ctrlKey) return;
        ev.preventDefault();
        const current=Number(viewer.dataset.zoom||100);
        setZoom(viewer, current + (ev.deltaY<0 ? STEP : -STEP), false);
      }, {passive:false});
    }
  });
  document.addEventListener('click', function(ev){
    const btn=ev.target.closest('[data-zoom-action]');
    if(!btn) return;
    const viewer=viewerForControl(btn);
    if(!viewer) return;
    const action=btn.dataset.zoomAction;
    const current=Number(viewer.dataset.zoom||100);
    if(action==='in') setZoom(viewer, current+STEP, false);
    else if(action==='out') setZoom(viewer, current-STEP, false);
    else if(action==='reset' || action==='fit') setZoom(viewer, 100, true);
    else if(action==='fullscreen'){
      const section=viewer.closest('section') || viewer;
      if(document.fullscreenElement===section){
        if(document.exitFullscreen) document.exitFullscreen();
      }else if(section.requestFullscreen){
        section.requestFullscreen();
      }
    }
  });
})();
</script></body></html>""",
        encoding="utf-8",
    )

def process_whole_graph_topology_analysis(
    files: Iterable[Path],
    report_dir: Path,
    *,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> WholeGraphTopologyResult:
    log = log or (lambda _msg: None)
    progress = progress or (lambda _p, _m="": None)
    paths = [Path(p) for p in files]
    if len(paths) != 1:
        raise ValueError("整图馈线拓扑分析一次只处理 1 个 G 文件，请只选择一个 .g 文件。")

    source = paths[0]
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    progress(5, f"正在解析原始 G 图：{source.name}")
    before_analysis = analyze_whole_graph_topology_file(source)
    before_summary = before_analysis["summary"]

    progress(30, "正在定位无馈线孤立区与疑似断点")
    accepted_edges, repair_rows, _sim_no_after, _sim_multi_after = _simulate_safe_topology_repairs(
        before_analysis
    )
    auto_fixed_rows = [row for row in repair_rows if row.get("repair_status") == "AUTO_FIXED"]
    review_rows = [row for row in repair_rows if row.get("repair_status") != "AUTO_FIXED"]

    fixed_g_path: Path | None = None
    if auto_fixed_rows:
        progress(50, f"正在生成拓扑修复安全副本：{len(auto_fixed_rows)} 处连接")
        fixed_g_path = report_dir / _fixed_g_name(source)
        _write_fixed_g_file(source, fixed_g_path, repair_rows)
        if fixed_g_path is None or not fixed_g_path.exists():
            raise RuntimeError("已判定存在可自动修复连接，但修复后的 G 文件未成功生成。")
        after_analysis = analyze_whole_graph_topology_file(fixed_g_path)
        after_summary = after_analysis["summary"]

        # Final hard guard: generated G may only be accepted when it does not
        # introduce a new multi-feeder error and actually improves the total
        # topology error count.  The original source is never touched either way.
        if (
            after_summary["multi_feeder_error_count"] > before_summary["multi_feeder_error_count"]
            or after_summary["topology_error_count"] >= before_summary["topology_error_count"]
        ):
            fixed_g_path.unlink(missing_ok=True)
            fixed_g_path = None
            for row in auto_fixed_rows:
                row["repair_status"] = "REVIEW_FINAL_VALIDATION_REJECTED"
                row["repair_reason"] = (
                    "生成修复版 G 后的完整复核未通过：拓扑错误没有下降或新增多馈线冲突。"
                    "已撤销自动修复输出，原始 G 未修改。"
                )
            accepted_edges = []
            after_analysis = before_analysis
            after_summary = before_summary
            log("[安全回滚] 自动修复最终复核未通过，已删除修复版 G；原始 G 未修改。")
        else:
            log(
                f"[自动修复] 已安全补充 {len(auto_fixed_rows)} 处拓扑连接；"
                f"拓扑异常 {before_summary['topology_error_count']} -> {after_summary['topology_error_count']}，"
                f"无馈线 {before_summary['no_feeder_error_count']} -> {after_summary['no_feeder_error_count']}，"
                f"多馈线 {before_summary['multi_feeder_error_count']} -> {after_summary['multi_feeder_error_count']}。"
            )
            log(f"[修复后 G] {fixed_g_path}")
    else:
        after_analysis = before_analysis
        after_summary = before_summary
        if before_summary["topology_error_count"]:
            log("[断点诊断] 未发现满足全部安全条件的自动修复连接；请查看 HTML 断点诊断。")

    progress(70, "正在生成修复前 / 修复后拓扑图")
    before_svg = report_dir / "whole_graph_topology_before.svg"
    after_svg = report_dir / "whole_graph_topology_after.svg"
    _write_topology_svg(before_svg, before_analysis, repair_rows, after=False)
    _write_topology_svg(after_svg, after_analysis, repair_rows, after=True)

    progress(82, "正在生成整图拓扑分析与修复报告")
    device_csv = report_dir / "whole_graph_device_feeders.csv"
    nop_csv = report_dir / "whole_graph_nop_boundaries.csv"
    anchor_csv = report_dir / "whole_graph_feeder_anchors.csv"
    rmu_csv = report_dir / "whole_graph_rmu_feeders.csv"
    repair_csv = report_dir / "whole_graph_topology_repairs.csv"
    html_path = report_dir / "whole_graph_topology_report.html"

    _write_csv(device_csv, after_analysis["device_rows"], [
        "file_name", "xml_id", "tag", "display_name", "status", "error_type",
        "primary_feeder", "candidate_feeders", "topology_degree",
        "anchor_evidence", "link", "node_area", "devref", "reason",
    ])
    _write_csv(nop_csv, after_analysis["nop_rows"], [
        "nop_text_xml_id", "nop_text", "nop_type", "rmu_name", "frame_xml_id",
        "switch_xml_id", "switch_name", "switch_name_text_xml_id", "switch_tag",
        "switch_distance", "nop_side", "alignment_axis", "alignment_delta",
        "side_count", "side_feeders", "source_side_summary", "feeder_labels", "boundary_status", "status",
    ])
    _write_csv(anchor_csv, after_analysis["anchor_rows"], [
        "anchor_type", "node_xml_id", "feeder_label", "text_xml_id", "raw_text",
        "distance", "nearest_device_xml_id", "nearest_device_tag",
        "nearest_device_distance", "status",
    ])
    _write_csv(rmu_csv, after_analysis["rmu_rows"], [
        "file_name", "rmu_name", "frame_xml_id", "name_text_xml_id",
        "status", "primary_feeder", "candidate_feeders", "error_type",
        "port_count", "non_nop_port_count", "nop_port_count",
        "non_nop_port_feeders", "nop_port_sides", "reason",
    ])
    _write_csv(repair_csv, repair_rows, [
        "repair_status", "left_xml_id", "left_tag", "left_endpoint", "left_x", "left_y",
        "right_xml_id", "right_tag", "right_endpoint", "right_x", "right_y",
        "distance", "feeder_label", "island_node_count", "reciprocal_unique",
        "errors_before", "errors_after", "no_feeder_before", "no_feeder_after",
        "multi_feeder_before", "multi_feeder_after", "applied_feeder", "repair_reason",
    ])
    _write_html(
        html_path,
        before_analysis,
        after_analysis,
        repair_rows,
        before_svg_path=before_svg,
        after_svg_path=after_svg,
        fixed_g_path=fixed_g_path,
    )

    s = after_analysis["summary"]
    log(
        f"[{source.name}] 馈线={','.join(s['feeder_labels']) or '-'}；"
        f"锚点={s['anchor_count']}（沿线名称={s['line_anchor_count']}）；"
        f"设备={s['device_count']}；确认={s['confirmed_count']}；"
        f"拓扑异常={s['topology_error_count']}（无馈线={s['no_feeder_error_count']}，多馈线={s['multi_feeder_error_count']}）；"
        f"RMU={s['rmu_count']}（确认={s['rmu_confirmed_count']}，异常={s['rmu_error_count']}）；"
        f"自动修复={sum(1 for row in repair_rows if row.get('repair_status') == 'AUTO_FIXED')}；"
        f"待人工确认断点={sum(1 for row in repair_rows if row.get('repair_status') != 'AUTO_FIXED')}。"
    )
    progress(100, "整图馈线拓扑分析与自动修复完成")

    return WholeGraphTopologyResult(
        html_path=html_path,
        device_csv_path=device_csv,
        nop_csv_path=nop_csv,
        anchor_csv_path=anchor_csv,
        rmu_csv_path=rmu_csv,
        repair_csv_path=repair_csv,
        before_svg_path=before_svg,
        after_svg_path=after_svg,
        fixed_g_path=fixed_g_path,
        file_count=1,
        device_count=s["device_count"],
        confirmed_count=s["confirmed_count"],
        conflict_count=s["conflict_count"],
        unresolved_count=s["unresolved_count"],
        feeder_count=s["feeder_count"],
        nop_boundary_count=s["nop_boundary_count"],
        pole_nop_count=s["pole_nop_count"],
        rmu_nop_count=s["rmu_nop_count"],
        topology_error_count=s["topology_error_count"],
        no_feeder_error_count=s["no_feeder_error_count"],
        multi_feeder_error_count=s["multi_feeder_error_count"],
        rmu_count=s["rmu_count"],
        rmu_confirmed_count=s["rmu_confirmed_count"],
        rmu_error_count=s["rmu_error_count"],
        repair_candidate_count=len(repair_rows),
        repair_applied_count=sum(1 for row in repair_rows if row.get("repair_status") == "AUTO_FIXED"),
        before_topology_error_count=before_summary["topology_error_count"],
        after_topology_error_count=s["topology_error_count"],
    )

