from __future__ import annotations

import colorsys
import csv
import html
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from dmm.domain.feeder.ownership import (
    FeederOwnershipResolver,
    LINE_TAGS,
    _endpoints,
    _reference_ids,
)
from dmm.domain.gfile.master_station_frames import find_master_station_frames
from dmm.domain.gfile.parser import GObject, ParsedG, RmuFrame
from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    _assign_nops_to_frames,
    _frame_key,
    _new_makkah_parser,
    _named_yq_switches,
)


@dataclass
class RmuFeederTopologyResult:
    html_path: Path
    rmu_csv_path: Path
    port_csv_path: Path
    file_count: int
    rmu_count: int
    unique_count: int
    nop_boundary_count: int
    conflict_count: int
    unresolved_count: int
    source_feeder_count: int
    source_entry_nop_feeder_count: int


def _txt(value) -> str:
    return "" if value is None else str(value).strip()


def _esc(value) -> str:
    return html.escape(_txt(value), quote=True)




def _color_rgb_candidates(value: str) -> list[tuple[int, int, int]]:
    """Parse common G-file color encodings into plausible RGB triples.

    Field drawings use both ``R,G,B`` / ``R,G,B,A`` and hex strings.  Eight
    digit hex values are ambiguous in legacy files (ARGB vs RGBA), so both
    interpretations are returned and the caller may accept either one.
    """
    raw = _txt(value).lower().replace(" ", "")
    if not raw:
        return []

    result: list[tuple[int, int, int]] = []

    if raw.startswith("#"):
        hex_value = raw[1:]
        if len(hex_value) == 6:
            try:
                result.append(tuple(int(hex_value[i : i + 2], 16) for i in (0, 2, 4)))
            except ValueError:
                return []
        elif len(hex_value) == 8:
            # Accept both AARRGGBB and RRGGBBAA because both occur in legacy
            # exports.  Duplicate triples are removed below.
            for rgb_hex in (hex_value[2:8], hex_value[0:6]):
                try:
                    result.append(tuple(int(rgb_hex[i : i + 2], 16) for i in (0, 2, 4)))
                except ValueError:
                    continue
    else:
        parts = raw.split(",")
        if len(parts) in {3, 4}:
            try:
                nums = [int(part) for part in parts]
            except ValueError:
                nums = []
            if nums and all(0 <= n <= 255 for n in nums):
                if len(nums) == 3:
                    result.append((nums[0], nums[1], nums[2]))
                else:
                    # R,G,B,A is the normal form; keep A,R,G,B compatibility
                    # as well for old drawings.
                    result.append((nums[0], nums[1], nums[2]))
                    result.append((nums[1], nums[2], nums[3]))

    unique: list[tuple[int, int, int]] = []
    for rgb in result:
        if rgb not in unique:
            unique.append(rgb)
    return unique


def _rgb_is_red_range(rgb: tuple[int, int, int]) -> bool:
    """Return True when RGB is visibly in the configured red range.

    Red is intentionally a range rather than an exact ``#ff0000`` match.
    HSV keeps green/yellow/blue hues out, while the RGB dominance checks add a
    second guard against low-saturation or ambiguous colors.
    """
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    hue = h * 360.0
    red_hue = hue <= 20.0 or hue >= 340.0
    return (
        red_hue
        and s >= 0.45
        and v >= 0.30
        and r > g * 1.5
        and r > b * 1.5
    )


def _is_red_nop_text(obj: GObject) -> bool:
    """Return True when the visible NOP label color is in the red range.

    Makkah topology still ignores non-red NOP annotations, but red is no longer
    limited to exact ``255,0,0`` / ``#ff0000``.  A visible color from ``lc`` or
    ``lcc`` is accepted when it falls in the red HSV range (H 0..20 or
    340..360, S >= 45%, V >= 30%) and red remains at least 1.5x stronger than
    both green and blue.  ``fc`` stays intentionally ignored because field G
    files may keep it green regardless of the visible text color.
    """
    for attr in ("lc", "lcc"):
        for rgb in _color_rgb_candidates(obj.attrs.get(attr, "")):
            if _rgb_is_red_range(rgb):
                return True
    return False


RMU_TOPOLOGY_EXTRA_NETWORK_TAGS = {"Pole"}


def _add_explicit_pole_topology(parsed: ParsedG, by_id, adjacency):
    """Add Pole junctions to the RMU feeder topology graph from explicit G refs only.

    Field Makkah drawings can split one feeder run into multiple FeedLine objects
    whose continuity is expressed through ``Pole.node_area`` / ``Pole.link``.
    The legacy ownership graph intentionally omits Pole, so an RMU source path
    can otherwise stop at the first pole even though the G file carries an
    explicit electrical reference chain.

    This repair is deliberately narrow:
      * only ``Pole`` objects are added;
      * only explicit ``link`` / ``node_area`` references create edges;
      * no Pole proximity / geometry guessing is performed;
      * the shared feeder-section topology resolver is left unchanged.
    """
    added_nodes = 0
    added_edges: set[tuple[str, str]] = set()

    for obj in parsed.objects:
        xml_id = _txt(obj.xml_id)
        if not xml_id or obj.tag not in RMU_TOPOLOGY_EXTRA_NETWORK_TAGS:
            continue
        if xml_id not in by_id:
            by_id[xml_id] = obj
            added_nodes += 1

    # Re-scan every object now present in this RMU-only graph.  This captures
    # both directions used in field files: FeedLine -> Pole and Pole -> FeedLine.
    for obj in list(by_id.values()):
        obj_id = _txt(obj.xml_id)
        if not obj_id:
            continue
        for ref in _reference_ids(obj):
            if ref not in by_id or ref == obj_id:
                continue
            pair = tuple(sorted((obj_id, ref)))
            if ref not in adjacency.get(obj_id, set()):
                FeederOwnershipResolver._add_edge(adjacency, obj_id, ref)
                added_edges.add(pair)

    for xml_id in by_id:
        adjacency.setdefault(xml_id, set())

    return added_nodes, len(added_edges)


def _component_labels(component_by_id, labels_by_component, xml_id: str) -> set[str]:
    comp = component_by_id.get(str(xml_id or ""))
    if comp is None:
        return set()
    return set(labels_by_component.get(comp, set()))


def _rmu_name_map(parser, parsed: ParsedG, frames: list[RmuFrame]):
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed,
        frames,
        ("right", "bottom", "global"),
    )
    result = {}
    for frame in frames:
        candidates = list(assigned.get(_frame_key(frame), []))
        if candidates:
            candidate = candidates[0]
            result[_frame_key(frame)] = {
                "name": _txt(candidate.text),
                "text_xml_id": _txt(candidate.obj.xml_id),
                "direction": _txt(candidate.direction),
                "distance": round(float(candidate.score), 3),
            }
        else:
            result[_frame_key(frame)] = {
                "name": "",
                "text_xml_id": "",
                "direction": "",
                "distance": "",
            }
    return result


def _source_anchors(parsed: ParsedG):
    rows = []
    source_by_breaker: dict[str, str] = {}
    for frame_info in find_master_station_frames(parsed):
        breakers = list(frame_info.breakers)
        label = _txt(frame_info.feeder_label)
        breaker_id = _txt(frame_info.breaker.xml_id) if len(breakers) == 1 and frame_info.breaker else ""
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



def _nop_relative_side(frame: RmuFrame, nop: GObject) -> str:
    """Return the NOP label side relative to the assigned RMU frame."""
    box = frame.frame.box
    if float(nop.box.cx) < float(box.x):
        return "LEFT"
    if float(nop.box.cx) > float(box.x + box.w):
        return "RIGHT"
    if float(nop.box.cy) < float(box.y):
        return "TOP"
    if float(nop.box.cy) > float(box.y + box.h):
        return "BOTTOM"
    return "INSIDE"


def _nearest_nop_device(parser, parsed: ParsedG, frame: RmuFrame, nop: GObject):
    """Resolve the NOP switch only from named Y*/Q* switches inside this RMU.

    Makkah drawings place the NOP text beside the physical switch row.  For a
    left/right NOP, the switch on the same horizontal row is authoritative:
    minimize center-Y difference first, then use the actual geometric distance
    only to break a row tie.  This is important for Q1-style cases where Q1 is
    horizontally aligned with the NOP but a Y switch is slightly closer by raw
    rectangle-edge distance.

    For a top/bottom NOP the rule is mirrored (center-X alignment first).  If a
    text happens to overlap the RMU frame, fall back to geometric distance.
    Candidates are always restricted to ``_named_yq_switches(..., frame)``, so
    a switch from another cabinet can never win.
    """
    side = _nop_relative_side(frame, nop)
    candidates = []
    for device, logical_name in _named_yq_switches(parser, parsed, frame):
        edge_distance = float(nop.box.edge_distance(device.box))
        center_distance = math.hypot(
            float(nop.box.cx) - float(device.box.cx),
            float(nop.box.cy) - float(device.box.cy),
        )
        y_delta = abs(float(nop.box.cy) - float(device.box.cy))
        x_delta = abs(float(nop.box.cx) - float(device.box.cx))
        xml_order = int(device.xml_index)
        if side in {"LEFT", "RIGHT"}:
            sort_key = (y_delta, edge_distance, x_delta, center_distance, xml_order)
            alignment_axis = "Y"
            alignment_delta = y_delta
        elif side in {"TOP", "BOTTOM"}:
            sort_key = (x_delta, edge_distance, y_delta, center_distance, xml_order)
            alignment_axis = "X"
            alignment_delta = x_delta
        else:
            sort_key = (edge_distance, center_distance, y_delta, x_delta, xml_order)
            alignment_axis = "DISTANCE"
            alignment_delta = edge_distance
        candidates.append((
            sort_key,
            device,
            logical_name,
            edge_distance,
            side,
            alignment_axis,
            alignment_delta,
        ))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    _, device, logical_name, edge_distance, side, axis, alignment_delta = candidates[0]
    return device, logical_name, edge_distance, side, axis, alignment_delta


def _rmu_port_index(parser, parsed: ParsedG, frames: list[RmuFrame], rmu_names):
    """Build switch XML -> RMU/port metadata for every named Y*/Q* switch."""
    result = {}
    for frame in frames:
        name_info = rmu_names.get(_frame_key(frame), {})
        for device, logical_name in _named_yq_switches(parser, parsed, frame):
            device_id = _txt(device.xml_id)
            if not device_id:
                continue
            result[device_id] = {
                "rmu_name": _txt(name_info.get("name")),
                "frame_xml_id": _txt(frame.frame.xml_id),
                "port_name": logical_name,
                "port_xml_id": device_id,
            }
    return result


# G exports from Makkah sometimes draw a visually connected line all the way to
# an RMU Y/Q switch or its BusDis, but omit link/node_area on one or both
# objects.  The legacy graph only repairs line<->line geometry, so such a
# perfectly visible connection becomes electrically disconnected in the
# analyzer.  Field symbols place the actual terminal a few G units *inside*
# the object's bounding box (commonly 4 units), hence 6 is deliberately tight
# while still covering the exported terminal geometry.
RMU_TERMINAL_GEOMETRY_TOLERANCE = 6.0


def _point_to_box_terminal_distance(point, box) -> float:
    """Distance from a line endpoint to the nearest boundary of a device box.

    An endpoint inside the symbol is not automatically distance zero: the
    terminal must still be close to one of the four box edges.  This prevents a
    line endpoint passing through the middle of a large symbol from becoming a
    false electrical connection.
    """
    px, py = float(point[0]), float(point[1])
    if box.left <= px <= box.right and box.top <= py <= box.bottom:
        return min(
            abs(px - box.left),
            abs(px - box.right),
            abs(py - box.top),
            abs(py - box.bottom),
        )
    dx = max(box.left - px, px - box.right, 0.0)
    dy = max(box.top - py, py - box.bottom, 0.0)
    return math.hypot(dx, dy)


def _repair_rmu_terminal_geometry(
    parser,
    parsed: ParsedG,
    frames: list[RmuFrame],
    by_id,
    adjacency,
):
    """Strictly repair missing line<->RMU/source-device terminal edges.

    Only three classes of device are eligible:
      * named RMU Y*/Q* ``CBreakerDis`` switches;
      * ``BusDis`` objects physically inside a recognized RMU frame;
      * the unique ``CBreaker`` inside a recognized main-station Bay frame.

    A repair is created only when a *line endpoint* is within 6 G units of a
    device-box boundary.  Line segments merely passing nearby never connect.
    If the same endpoint is equally close to multiple devices, no edge is
    guessed.  This is intentionally narrower than generic proximity matching.
    """
    targets: dict[str, GObject] = {}

    # RMU terminal switches plus the in-cabinet distribution bus.
    for frame in frames:
        for device, _logical_name in _named_yq_switches(parser, parsed, frame):
            if _txt(device.xml_id) in by_id:
                targets[_txt(device.xml_id)] = device
        for obj in parsed.objects:
            obj_box = obj.box
            if (
                obj.tag == "BusDis"
                and _txt(obj.xml_id) in by_id
                and frame.frame.box.center_contains(obj_box, tolerance=1.0)
            ):
                targets[_txt(obj.xml_id)] = obj

    # Source breakers are also legitimate geometric terminals.  Restrict them
    # to the unique breaker inside an actual main-station frame so ordinary
    # breaker symbols elsewhere in the drawing are never pulled in by geometry.
    for frame_info in find_master_station_frames(parsed):
        if len(frame_info.breakers) == 1 and frame_info.breaker is not None:
            breaker_id = _txt(frame_info.breaker.xml_id)
            if breaker_id in by_id:
                targets[breaker_id] = frame_info.breaker

    if not targets:
        return 0, []

    line_objects = [obj for obj in by_id.values() if obj.tag in LINE_TAGS]
    repaired_pairs: set[tuple[str, str]] = set()
    repaired_rows: list[dict] = []

    for line in line_objects:
        for endpoint_index, point in enumerate(_endpoints(line)):
            candidates = []
            for target_id, target in targets.items():
                if target_id == line.xml_id:
                    continue
                distance = _point_to_box_terminal_distance(point, target.box)
                if distance <= RMU_TERMINAL_GEOMETRY_TOLERANCE:
                    candidates.append((distance, int(target.xml_index), target_id, target))
            if not candidates:
                continue
            candidates.sort(key=lambda item: (item[0], item[1]))
            best_distance = float(candidates[0][0])
            # Ambiguous geometric terminal: do not invent an electrical edge.
            equally_best = [
                item for item in candidates
                if abs(float(item[0]) - best_distance) <= 0.25
            ]
            if len(equally_best) != 1:
                continue
            _distance, _order, target_id, target = equally_best[0]
            if target_id in adjacency.get(line.xml_id, set()):
                continue
            pair = tuple(sorted((_txt(line.xml_id), target_id)))
            if pair in repaired_pairs:
                continue
            repaired_pairs.add(pair)
            FeederOwnershipResolver._add_edge(adjacency, line.xml_id, target_id)
            repaired_rows.append({
                "line_xml_id": _txt(line.xml_id),
                "line_tag": line.tag,
                "endpoint_index": endpoint_index,
                "target_xml_id": target_id,
                "target_tag": target.tag,
                "distance": round(best_distance, 3),
            })

    return len(repaired_pairs), repaired_rows


def _first_rmu_ports_from_source(
    breaker_id: str,
    adjacency,
    port_index,
    source_breaker_ids: set[str],
):
    """Find the first RMU Y/Q port(s) electrically reached from a source breaker.

    Traversal stops when it reaches an RMU port, so a downstream RMU can never
    hide the identity of the source-entry RMU.  Other main-station source
    breakers are treated as barriers to prevent a station bus from leaking into
    a neighbouring feeder's outgoing path.
    """
    breaker_id = _txt(breaker_id)
    if not breaker_id:
        return []
    queue = deque([(breaker_id, 0)])
    visited = {breaker_id}
    found = []
    first_hops = None
    while queue:
        current, hops = queue.popleft()
        if first_hops is not None and hops > first_hops:
            break
        if current != breaker_id and current in port_index:
            found.append((hops, current, port_index[current]))
            first_hops = hops if first_hops is None else first_hops
            continue
        for nxt in adjacency.get(current, ()):
            if nxt in visited:
                continue
            if nxt in source_breaker_ids and nxt != breaker_id:
                continue
            visited.add(nxt)
            queue.append((nxt, hops + 1))
    return found


def _apply_source_entry_nop_rule(
    source_rows: list[dict],
    source_by_breaker: dict[str, str],
    adjacency,
    port_index,
    boundary_nodes: set[str],
):
    """Annotate whether a source feeder meets an NOP at its first RMU entry.

    This function no longer removes the feeder globally.  The RMU topology
    module is branch based: FeedLine/ConnectLine/Bus/BusDis are traversal
    media, and only the *specific* branch that reaches a red-NOP Y*/Q* switch
    stops there.  Any other route of the same feeder remains free to continue.

    The returned source map therefore contains every confirmed source feeder.
    ``source_entry_nop_labels`` is report-only evidence that at least one direct
    source-entry branch terminates immediately at an NOP switch.
    """
    source_breaker_ids = {
        _txt(row.get("breaker_xml_id"))
        for row in source_rows
        if _txt(row.get("breaker_xml_id"))
    }
    direct_source_by_port: dict[str, set[str]] = defaultdict(set)
    source_entry_nop_labels: set[str] = set()

    for row in source_rows:
        breaker_id = _txt(row.get("breaker_xml_id"))
        feeder_label = _txt(row.get("feeder_label"))
        row["first_rmu_name"] = ""
        row["first_rmu_frame_xml_id"] = ""
        row["entry_port_name"] = ""
        row["entry_port_xml_id"] = ""
        row["entry_path_hops"] = ""
        row["entry_port_is_nop"] = ""
        row["candidate_status"] = "NOT_CONFIRMED"
        row["candidate_reason"] = ""

        if row.get("status") != "SOURCE_CONFIRMED" or not breaker_id or not feeder_label:
            continue

        first_ports = _first_rmu_ports_from_source(
            breaker_id, adjacency, port_index, source_breaker_ids
        )
        if len(first_ports) != 1:
            row["candidate_status"] = (
                "SOURCE_ENTRY_AMBIGUOUS" if first_ports else "SOURCE_ENTRY_NOT_FOUND"
            )
            row["candidate_reason"] = (
                "主网出线到首个RMU的Y/Q开关无法唯一确定；不做全局排除，后续仍按真实拓扑逐支路传播。"
            )
            continue

        hops, port_id, meta = first_ports[0]
        row["first_rmu_name"] = meta.get("rmu_name", "")
        row["first_rmu_frame_xml_id"] = meta.get("frame_xml_id", "")
        row["entry_port_name"] = meta.get("port_name", "")
        row["entry_port_xml_id"] = port_id
        row["entry_path_hops"] = hops
        is_nop = port_id in boundary_nodes
        row["entry_port_is_nop"] = "YES" if is_nop else "NO"
        direct_source_by_port[port_id].add(feeder_label)
        if is_nop:
            source_entry_nop_labels.add(feeder_label)
            row["candidate_status"] = "ENTRY_BRANCH_STOPPED_AT_NOP"
            row["candidate_reason"] = (
                f"首个直连RMU={meta.get('rmu_name','')}，主网入线开关={meta.get('port_name','')}，"
                "该开关是红色NOP所属开关；仅这一路在此停止，不全局删除该馈线，若存在其它拓扑支路仍继续传播。"
            )
        else:
            row["candidate_status"] = "PROPAGATE"
            row["candidate_reason"] = (
                f"首个直连RMU={meta.get('rmu_name','')}，主网入线开关={meta.get('port_name','')}，"
                "该开关不是NOP；从该支路继续沿连接线、FeedLine和配网母线传播。"
            )

    confirmed_sources = {
        breaker_id: label
        for breaker_id, label in source_by_breaker.items()
        if breaker_id and label
    }
    return confirmed_sources, source_entry_nop_labels, direct_source_by_port


def _propagate_feeder_reachability(
    source_by_breaker: dict[str, str],
    adjacency,
    boundary_nodes: set[str],
):
    """Propagate feeder labels through electrical topology, branch by branch.

    FeedLine, ConnectLine, Bus/BusDis and other network objects are only graph
    traversal media.  No line is assigned to an RMU and no line ownership is a
    business output of this module.

    A red-NOP Y*/Q* switch is a hard barrier for *that path only*.  The search
    never enters the boundary switch, while all other queued branches of the
    same feeder continue normally.  Other source breakers are treated as
    barriers so a station bus cannot leak one feeder label through a neighbour
    outgoing breaker.
    """
    labels_by_node: dict[str, set[str]] = defaultdict(set)
    source_breakers = set(source_by_breaker)

    for breaker_id, feeder_label in sorted(source_by_breaker.items()):
        breaker_id = _txt(breaker_id)
        feeder_label = _txt(feeder_label)
        if not breaker_id or not feeder_label:
            continue
        queue = deque([breaker_id])
        visited = {breaker_id}
        while queue:
            current = queue.popleft()
            labels_by_node[current].add(feeder_label)
            for nxt in adjacency.get(current, ()):
                if nxt in visited:
                    continue
                if nxt in boundary_nodes:
                    # The current branch stops at the NOP switch.  We do not
                    # enter/cross it, but other branches already in the queue
                    # continue normally.
                    continue
                if nxt in source_breakers and nxt != breaker_id:
                    continue
                visited.add(nxt)
                queue.append(nxt)

    return labels_by_node


def _neighbor_reachability_labels(adjacency, boundary_id: str, labels_by_node):
    labels: set[str] = set()
    neighbor_nodes: set[str] = set()
    for neighbor in adjacency.get(boundary_id, ()):
        neighbor_nodes.add(neighbor)
        labels.update(labels_by_node.get(neighbor, set()))
    return labels, neighbor_nodes


def _exact_nop_boundaries(parser, parsed: ParsedG, frames: list[RmuFrame], rmu_names):
    assignments_all, unmatched_all = _assign_nops_to_frames(parsed, frames)

    # Makkah topology rule: ONLY red NOP labels are topology boundaries.
    # Any non-red NOP text is a graphical annotation and is ignored completely:
    # it does not belong to an RMU, does not select a Y*/Q* switch, does not
    # create a boundary, does not trigger source-entry feeder exclusion, and
    # does not appear in the NOP summary/report. Visible text color is read from
    # lc/lcc; fc is intentionally ignored.
    assignments = [
        (nop, frame) for nop, frame in assignments_all
        if _is_red_nop_text(nop)
    ]
    unmatched = [nop for nop in unmatched_all if _is_red_nop_text(nop)]

    boundary_nodes: set[str] = set()
    rows = []
    for nop, frame in assignments:
        match = _nearest_nop_device(parser, parsed, frame, nop)
        name_info = rmu_names.get(_frame_key(frame), {})
        if match is None:
            rows.append({
                "nop_text_xml_id": _txt(nop.xml_id),
                "nop_text": _txt(nop.attrs.get("ts")),
                "rmu_name": _txt(name_info.get("name")),
                "frame_xml_id": _txt(frame.frame.xml_id),
                "switch_xml_id": "",
                "switch_name": "",
                "switch_distance": "",
                "y_delta": "",
                "nop_side": _nop_relative_side(frame, nop),
                "alignment_axis": "",
                "alignment_delta": "",
                "status": "NOP_SWITCH_NOT_FOUND",
            })
            continue
        device, logical_name, switch_distance, nop_side, alignment_axis, alignment_delta = match
        switch_id = _txt(device.xml_id)
        if switch_id:
            boundary_nodes.add(switch_id)
        rows.append({
            "nop_text_xml_id": _txt(nop.xml_id),
            "nop_text": _txt(nop.attrs.get("ts")),
            "rmu_name": _txt(name_info.get("name")),
            "frame_xml_id": _txt(frame.frame.xml_id),
            "switch_xml_id": switch_id,
            "switch_name": logical_name,
            "switch_distance": round(float(switch_distance), 3),
            "y_delta": round(abs(float(nop.box.cy) - float(device.box.cy)), 3),
            "nop_side": nop_side,
            "alignment_axis": alignment_axis,
            "alignment_delta": round(float(alignment_delta), 3),
            "status": "NOP_BOUNDARY" if switch_id else "NOP_SWITCH_NOT_FOUND",
        })
    for nop in unmatched:
        rows.append({
            "nop_text_xml_id": _txt(nop.xml_id),
            "nop_text": _txt(nop.attrs.get("ts")),
            "rmu_name": "",
            "frame_xml_id": "",
            "switch_xml_id": "",
            "switch_name": "",
            "switch_distance": "",
            "y_delta": "",
            "nop_side": "",
            "alignment_axis": "",
            "alignment_delta": "",
            "status": "NOP_RMU_NOT_FOUND",
        })
    return boundary_nodes, rows


def _components(by_id, adjacency, boundary_nodes: set[str]):
    component_by_id: dict[str, int] = {}
    members_by_component: dict[int, list[str]] = {}
    seq = 0
    for xml_id in by_id:
        if xml_id in boundary_nodes or xml_id in component_by_id:
            continue
        seq += 1
        stack = [xml_id]
        component_by_id[xml_id] = seq
        members = []
        while stack:
            cur = stack.pop()
            members.append(cur)
            for nxt in adjacency.get(cur, ()):
                if nxt in boundary_nodes or nxt in component_by_id:
                    continue
                component_by_id[nxt] = seq
                stack.append(nxt)
        members_by_component[seq] = members
    return component_by_id, members_by_component


def _labels_by_component(component_by_id, source_by_breaker: dict[str, str]):
    out: dict[int, set[str]] = defaultdict(set)
    for breaker_id, label in source_by_breaker.items():
        comp = component_by_id.get(breaker_id)
        if comp is not None and label:
            out[comp].add(label)
    return out


def _neighbor_labels(adjacency, boundary_id, component_by_id, labels_by_component):
    labels: set[str] = set()
    components: set[int] = set()
    for neighbor in adjacency.get(boundary_id, ()):
        comp = component_by_id.get(neighbor)
        if comp is None:
            continue
        components.add(comp)
        labels.update(labels_by_component.get(comp, set()))
    return labels, components


def _resolve_nop_rmu_ownership(
    non_nop_labels: set[str],
    boundary_labels: set[str],
    source_entry_stop_labels: set[str],
    conflict_ports: int = 0,
):
    """Resolve the cabinet owner without letting the feeder through NOP own the RMU.

    The feeder connected through the NOP switch terminates at that switch.  For
    cabinet ownership we therefore use the feeder consistently visible on the
    *non-NOP* Y*/Q* ports.  Feeder labels seen only across the NOP boundary are
    reported as stopped feeders and are not allowed to claim the RMU.

    This is deliberately conservative: if the non-NOP ports do not provide one
    unique feeder, ownership stays unresolved/conflicting instead of guessing.
    """
    active = {str(x).strip() for x in non_nop_labels if str(x).strip()}
    boundary = {str(x).strip() for x in boundary_labels if str(x).strip()}
    source_stops = {str(x).strip() for x in source_entry_stop_labels if str(x).strip()}

    if conflict_ports or len(active) > 1:
        stopped = (boundary | source_stops) - active
        return "", stopped, "CONFLICT_NON_NOP_PORTS"
    if len(active) == 1:
        owner = next(iter(active))
        stopped = (boundary | source_stops) - {owner}
        return owner, stopped, "RESOLVED_BY_NON_NOP_PORTS"
    return "", (boundary | source_stops), "UNRESOLVED_NON_NOP_PORTS"


def analyze_rmu_feeder_topology_file(path: Path):
    parser = _new_makkah_parser()
    parsed = parser.parse(path)
    frames = list(parser.find_rmu_frames(parsed))
    rmu_names = _rmu_name_map(parser, parsed, frames)
    source_rows, source_by_breaker_all = _source_anchors(parsed)
    boundary_nodes, nop_rows = _exact_nop_boundaries(parser, parsed, frames, rmu_names)
    _by_id, adjacency, repaired_count = FeederOwnershipResolver._build_graph(parsed)
    pole_node_count, pole_edge_count = _add_explicit_pole_topology(
        parsed, _by_id, adjacency
    )
    terminal_repaired_count, terminal_repaired_rows = _repair_rmu_terminal_geometry(
        parser, parsed, frames, _by_id, adjacency
    )

    # Source-entry NOP is report evidence only.  The actual ownership engine is
    # branch-local propagation and never deletes a feeder globally.
    port_index = _rmu_port_index(parser, parsed, frames, rmu_names)
    source_by_breaker, source_entry_nop_labels, direct_source_by_port = _apply_source_entry_nop_rule(
        source_rows, source_by_breaker_all, adjacency, port_index, boundary_nodes
    )

    # Core rule: start from each main-station feeder source and walk through the
    # electrical graph.  FeedLine / ConnectLine / Bus / BusDis are paths only.
    # A red-NOP switch blocks only the path that reaches that exact switch.
    labels_by_node = _propagate_feeder_reachability(
        source_by_breaker, adjacency, boundary_nodes
    )

    # Enrich NOP rows with feeder labels visible on the electrical neighbours
    # of the blocked switch.  The switch itself is intentionally not traversed.
    nop_by_switch = {}
    for row in nop_rows:
        switch_id = _txt(row.get("switch_xml_id"))
        labels, neighbor_nodes = (
            _neighbor_reachability_labels(adjacency, switch_id, labels_by_node)
            if switch_id else (set(), set())
        )
        row["feeder_labels"] = " | ".join(sorted(labels))
        row["neighbor_node_count"] = len(neighbor_nodes)
        source_entry_feeders = sorted(direct_source_by_port.get(switch_id, set())) if switch_id else []
        row["source_entry_feeders"] = " | ".join(source_entry_feeders)
        row["source_entry_effect"] = (
            "STOP BRANCH " + " | ".join(source_entry_feeders)
            if source_entry_feeders else ""
        )
        if row.get("status") == "NOP_BOUNDARY":
            if len(labels) >= 2:
                row["analysis_status"] = "CONFIRMED_BOUNDARY"
            elif len(labels) == 1:
                row["analysis_status"] = "PARTIAL_BOUNDARY"
            else:
                row["analysis_status"] = "UNRESOLVED_BOUNDARY"
        else:
            row["analysis_status"] = row.get("status")
        if switch_id:
            nop_by_switch[switch_id] = row

    port_rows = []
    rmu_rows = []
    for frame in frames:
        name_info = rmu_names.get(_frame_key(frame), {})
        rmu_name = _txt(name_info.get("name"))
        frame_ports = list(_named_yq_switches(parser, parsed, frame))
        rmu_labels: set[str] = set()
        non_nop_labels: set[str] = set()
        boundary_labels: set[str] = set()
        source_entry_stop_labels: set[str] = set()
        boundary_ports = []
        boundary_port_ids = []
        unresolved_ports = 0
        conflict_ports = 0
        frame_port_rows = []

        for device, logical_name in frame_ports:
            device_id = _txt(device.xml_id)
            if device_id in boundary_nodes:
                labels, neighbor_nodes = _neighbor_reachability_labels(
                    adjacency, device_id, labels_by_node
                )
                rmu_labels.update(labels)
                boundary_labels.update(labels)
                boundary_ports.append(logical_name)
                boundary_port_ids.append(device_id)
                source_entry_stop_labels.update(direct_source_by_port.get(device_id, set()))
                if len(labels) >= 2:
                    port_status = "NOP_BOUNDARY"
                elif len(labels) == 1:
                    port_status = "NOP_BOUNDARY_PARTIAL"
                else:
                    port_status = "UNRESOLVED"
                    unresolved_ports += 1
                nop_info = nop_by_switch.get(device_id, {})
                evidence = (
                    f"NOP={nop_info.get('nop_text_xml_id','')}; "
                    f"blocked_switch={logical_name}; neighbour_nodes={len(neighbor_nodes)}"
                )
            else:
                labels = set(labels_by_node.get(device_id, set()))
                rmu_labels.update(labels)
                non_nop_labels.update(labels)
                if len(labels) == 1:
                    port_status = "RESOLVED"
                elif len(labels) > 1:
                    port_status = "CONFLICT"
                    conflict_ports += 1
                else:
                    port_status = "UNRESOLVED"
                    unresolved_ports += 1
                evidence = "reachability=" + (" | ".join(sorted(labels)) or "NONE")

            frame_port_rows.append({
                "file_name": path.name,
                "rmu_name": rmu_name,
                "frame_xml_id": _txt(frame.frame.xml_id),
                "port_name": logical_name,
                "port_xml_id": device_id,
                "status": port_status,
                "feeder_labels": " | ".join(sorted(labels)),
                "evidence": evidence,
            })

        primary = ""
        stopped_feeders: set[str] = set()
        ownership_status = ""
        if boundary_ports:
            primary, stopped_feeders, ownership_status = _resolve_nop_rmu_ownership(
                non_nop_labels, boundary_labels, source_entry_stop_labels, conflict_ports
            )
            rmu_labels.update(source_entry_stop_labels)
            if primary or len(rmu_labels) >= 2:
                status = "NOP_BOUNDARY"
            elif len(rmu_labels) == 1:
                status = "NOP_BOUNDARY_PARTIAL"
            else:
                status = "UNRESOLVED"
        elif len(rmu_labels) == 1 and conflict_ports == 0:
            status = "UNIQUE"
            primary = next(iter(rmu_labels))
            ownership_status = "UNIQUE"
        elif len(rmu_labels) > 1 or conflict_ports:
            status = "CONFLICT"
            ownership_status = "CONFLICT"
        else:
            status = "UNRESOLVED"
            ownership_status = "UNRESOLVED"

        stopped_text = " | ".join(sorted(stopped_feeders))
        for port_row in frame_port_rows:
            port_row["rmu_owner_feeder"] = primary
            port_row["stopped_feeders"] = stopped_text
            if port_row["port_xml_id"] in boundary_nodes:
                port_row["ownership_role"] = "NOP_STOP_BOUNDARY"
            elif boundary_ports:
                port_row["ownership_role"] = "RMU_OWNER_SIDE"
            else:
                port_row["ownership_role"] = "NORMAL"
        port_rows.extend(frame_port_rows)

        for switch_id in boundary_port_ids:
            nop_info = nop_by_switch.get(switch_id)
            if nop_info is not None:
                nop_info["rmu_owner_feeder"] = primary
                nop_info["stopped_feeders"] = stopped_text
                nop_info["ownership_status"] = ownership_status
                nop_info["ownership_reason"] = (
                    f"只有走到NOP开关={nop_info.get('switch_name','')}的支路停止；"
                    f"同柜非NOP Y/Q端口唯一一致馈线={primary}，作为RMU所属馈线。"
                    if primary else
                    "只有NOP支路被切断；同柜非NOP Y/Q端口未形成唯一一致馈线，RMU所属馈线不自动猜测。"
                )

        rmu_rows.append({
            "file_name": path.name,
            "rmu_name": rmu_name,
            "frame_xml_id": _txt(frame.frame.xml_id),
            "name_text_xml_id": _txt(name_info.get("text_xml_id")),
            "status": status,
            "ownership_status": ownership_status,
            "primary_feeder": primary,
            "stopped_feeders": stopped_text,
            "feeder_labels": " | ".join(sorted(rmu_labels)),
            "nop_ports": ",".join(boundary_ports),
            "port_count": len(frame_ports),
            "unresolved_port_count": unresolved_ports,
            "name_direction": _txt(name_info.get("direction")),
            "name_distance": name_info.get("distance", ""),
        })

    summary = {
        "file_name": path.name,
        "source_count": len(source_rows),
        "confirmed_source_count": sum(1 for x in source_rows if x["status"] == "SOURCE_CONFIRMED"),
        "source_feeder_labels": sorted(set(source_by_breaker_all.values())),
        "source_entry_nop_feeder_labels": sorted(source_entry_nop_labels),
        "source_entry_nop_count": len(source_entry_nop_labels),
        "rmu_count": len(rmu_rows),
        "unique_count": sum(1 for x in rmu_rows if x["status"] == "UNIQUE"),
        "nop_boundary_count": sum(1 for x in rmu_rows if x["status"] == "NOP_BOUNDARY"),
        "nop_boundary_partial_count": sum(1 for x in rmu_rows if x["status"] == "NOP_BOUNDARY_PARTIAL"),
        "nop_owner_resolved_count": sum(
            1 for x in rmu_rows
            if x.get("nop_ports") and x.get("ownership_status") == "RESOLVED_BY_NON_NOP_PORTS"
        ),
        "conflict_count": sum(1 for x in rmu_rows if x["status"] == "CONFLICT"),
        "unresolved_count": sum(1 for x in rmu_rows if x["status"] == "UNRESOLVED"),
        "nop_text_count": len(nop_rows),
        "boundary_switch_count": len(boundary_nodes),
        "strict_geometry_repair_count": repaired_count + terminal_repaired_count,
        "line_geometry_repair_count": repaired_count,
        "pole_topology_node_count": pole_node_count,
        "pole_topology_edge_count": pole_edge_count,
        "rmu_terminal_geometry_repair_count": terminal_repaired_count,
    }
    return {
        "summary": summary,
        "source_rows": source_rows,
        "nop_rows": nop_rows,
        "rmu_rows": rmu_rows,
        "port_rows": port_rows,
        "terminal_repair_rows": terminal_repaired_rows,
    }


def _write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _html_table(title: str, rows: list[dict], columns: list[tuple[str, str]]) -> str:
    header = "".join(f"<th>{_esc(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        tds = "".join(f"<td>{_esc(row.get(key, ''))}</td>" for key, _ in columns)
        body_rows.append(f"<tr>{tds}</tr>")
    if not body_rows:
        body_rows.append(f"<tr><td colspan='{len(columns)}'>无记录</td></tr>")
    return (
        f"<section><h2>{_esc(title)}</h2><div class='table-wrap'><table>"
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        f"</table></div></section>"
    )


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
            f"<div><b>RMU</b><span>{s['rmu_count']}</span></div>"
            f"<div><b>唯一归属</b><span>{s['unique_count']}</span></div>"
            f"<div><b>NOP边界柜</b><span>{s['nop_boundary_count']}</span></div>"
            f"<div><b>NOP柜归属已确定</b><span>{s.get('nop_owner_resolved_count', 0)}</span></div>"
            f"<div><b>冲突</b><span>{s['conflict_count']}</span></div>"
            f"<div><b>未确定</b><span>{s['unresolved_count']}</span></div>"
            f"<div><b>红色NOP / 边界开关</b><span>{s['nop_text_count']} / {s['boundary_switch_count']}</span></div>"
            f"<div><b>线路严格补链</b><span>{s.get('line_geometry_repair_count', 0)}</span></div>"
            f"<div><b>Pole拓扑节点</b><span>{s.get('pole_topology_node_count', 0)} / 边{s.get('pole_topology_edge_count', 0)}</span></div>"
            f"<div><b>RMU端子补链</b><span>{s.get('rmu_terminal_geometry_repair_count', 0)}</span></div>"
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
        blocks.append(_html_table("NOP所属RMU / 开关汇总", item["nop_rows"], [
            ("nop_text", "NOP"), ("nop_text_xml_id", "NOP Text XML"),
            ("rmu_name", "所属RMU"), ("frame_xml_id", "RMU框XML"),
            ("switch_name", "NOP对应Y/Q开关"), ("switch_xml_id", "开关XML"),
            ("nop_side", "NOP相对RMU方位"), ("alignment_axis", "对齐轴"),
            ("alignment_delta", "对齐差"), ("switch_distance", "NOP到开关距离"),
            ("y_delta", "中心Y差"), ("source_entry_feeders", "主网直接到达该NOP支路"),
            ("source_entry_effect", "入口支路影响"), ("feeder_labels", "NOP两侧可达馈线"),
            ("rmu_owner_feeder", "RMU所属馈线"), ("stopped_feeders", "在NOP处截止馈线"),
            ("ownership_status", "RMU归属判定"), ("analysis_status", "分析状态"),
        ]))
        blocks.append(_html_table("RMU所属馈线", item["rmu_rows"], [
            ("rmu_name", "RMU名称"), ("frame_xml_id", "RMU框XML"),
            ("status", "拓扑状态"), ("ownership_status", "RMU归属判定"),
            ("primary_feeder", "RMU所属馈线"), ("stopped_feeders", "在NOP处截止馈线"),
            ("feeder_labels", "涉及馈线"), ("nop_ports", "NOP端口"),
            ("port_count", "Y/Q端口数"), ("unresolved_port_count", "未确定端口数"),
        ]))
        blocks.append(_html_table("RMU端口拓扑证据", item["port_rows"], [
            ("rmu_name", "RMU"), ("port_name", "端口"),
            ("port_xml_id", "端口XML"), ("status", "状态"),
            ("feeder_labels", "从主网可达馈线"), ("ownership_role", "端口角色"),
            ("rmu_owner_feeder", "RMU所属馈线"), ("stopped_feeders", "NOP截止馈线"),
            ("evidence", "拓扑证据"),
        ]))
        blocks.append("</article>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>环网柜馈线拓扑分析报告</title><style>
body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#16332c;background:#f7faf8}
article{background:#fff;border:1px solid #dbe8e2;border-radius:12px;padding:20px;margin-bottom:24px}
h1{margin:0 0 14px;color:#075f4a}h2{font-size:17px;margin:24px 0 10px;color:#075f4a}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px}
.cards div{border:1px solid #dbe8e2;background:#f3f9f6;border-radius:8px;padding:10px}.cards b{display:block;font-size:12px;color:#567168}.cards span{display:block;margin-top:4px;font-weight:600}
.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d9e5df;padding:7px 8px;text-align:left;white-space:nowrap}th{background:#eaf5f0;color:#174f42;position:sticky;top:0}
.note{padding:12px 14px;border-left:4px solid #0b7b60;background:#edf8f4;margin-bottom:18px}
</style></head><body><div class='note'>本模块只判断RMU所属馈线。FeedLine、ConnectLine、Bus、BusDis及其它网络对象仅作为电气拓扑寻路介质，不把FeedLine归属到RMU，也不输出FeedLine业务归属。分析从每条主网馈线CBreaker出发，沿真实link/node_area和严格几何补链持续传播；若G文件缺少引用，仅允许“线端点↔RMU Y/Q、RMU BusDis、主站Bay唯一CBreaker”在6个G单位以内做严格端子补链，线段仅靠近设备或端点深入图元内部都不会补链；只处理红色NOP（按HSV+RGB颜色范围识别，不要求纯#ff0000），非红色NOP全部忽略。只有当前传播路径实际碰到红色NOP对应的Y*/Q*开关时，该一路才在该开关处停止，其它支路继续传播。NOP只能在所属RMU框内匹配Y*/Q*开关；左右侧NOP优先按水平中心Y对齐，上下侧按中心X对齐。RMU所属馈线仅根据其Y*/Q*端口从主网可达的馈线证据判定。不会修改G文件，也不会连接、查询或写入Oracle数据库。</div>"""
        + "".join(blocks)
        + "</body></html>",
        encoding="utf-8",
    )


def process_rmu_feeder_topology_analysis(
    files: Iterable[Path],
    report_dir: Path,
    *,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> RmuFeederTopologyResult:
    log = log or (lambda _msg: None)
    progress = progress or (lambda _p, _m="": None)
    paths = [Path(p) for p in files]
    if not paths:
        raise ValueError("请至少选择一个 G 文件。")
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    analyses = []
    all_rmus: list[dict] = []
    all_ports: list[dict] = []
    for idx, path in enumerate(paths, start=1):
        progress(max(1, int((idx - 1) * 90 / len(paths))), f"正在分析 {path.name}")
        analysis = analyze_rmu_feeder_topology_file(path)
        analyses.append(analysis)
        all_rmus.extend(analysis["rmu_rows"])
        all_ports.extend(analysis["port_rows"])
        s = analysis["summary"]
        log(
            f"[{path.name}] 主网馈线={','.join(s['source_feeder_labels']) or '-'}；"
            f"入口支路遇NOP={','.join(s.get('source_entry_nop_feeder_labels', [])) or '-'}；"
            f"RMU={s['rmu_count']}；唯一归属={s['unique_count']}；"
            f"NOP边界柜={s['nop_boundary_count']}；冲突={s['conflict_count']}；"
            f"未确定={s['unresolved_count']}"
        )

    rmu_csv = report_dir / "rmu_feeder_topology.csv"
    port_csv = report_dir / "rmu_port_feeder_topology.csv"
    html_path = report_dir / "rmu_feeder_topology_report.html"
    _write_csv(rmu_csv, all_rmus, [
        "file_name", "rmu_name", "frame_xml_id", "name_text_xml_id", "status",
        "ownership_status", "primary_feeder", "stopped_feeders", "feeder_labels", "nop_ports", "port_count",
        "unresolved_port_count", "name_direction", "name_distance",
    ])
    _write_csv(port_csv, all_ports, [
        "file_name", "rmu_name", "frame_xml_id", "port_name", "port_xml_id",
        "status", "feeder_labels", "ownership_role", "rmu_owner_feeder", "stopped_feeders", "evidence",
    ])
    _write_html(html_path, analyses)
    progress(100, "环网柜馈线拓扑分析完成")

    return RmuFeederTopologyResult(
        html_path=html_path,
        rmu_csv_path=rmu_csv,
        port_csv_path=port_csv,
        file_count=len(paths),
        rmu_count=len(all_rmus),
        unique_count=sum(1 for x in all_rmus if x["status"] == "UNIQUE"),
        nop_boundary_count=sum(1 for x in all_rmus if x["status"] == "NOP_BOUNDARY"),
        conflict_count=sum(1 for x in all_rmus if x["status"] == "CONFLICT"),
        unresolved_count=sum(1 for x in all_rmus if x["status"] == "UNRESOLVED"),
        source_feeder_count=len({
            feeder
            for analysis in analyses
            for feeder in analysis["summary"]["source_feeder_labels"]
        }),
        source_entry_nop_feeder_count=len({
            feeder
            for analysis in analyses
            for feeder in analysis["summary"].get("source_entry_nop_feeder_labels", [])
        }),
    )
