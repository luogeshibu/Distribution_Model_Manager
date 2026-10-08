from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.engines.id_engine import local_name
from g_file_studio.engines.rmu_identification_engine import identify_rmus
from g_file_studio.engines.standard_connection_cleanup import (
    _authoritative_pin_points,
    _ensure_device_line_reciprocal,
)


_LINE_TAGS = {"ConnectLine", "FeedLine", "BusDis", "Bus", "ACLine", "line"}
_POINT_RE = re.compile(
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*,\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)
_NON_OBSTACLE_TAGS = _LINE_TAGS | {
    "Text", "DText", "Status", "poke", "rect", "ellipse", "image", "Layer",
    "Merge", "G", "Theme",
}


@dataclass(frozen=True)
class OrthogonalizationIssue:
    element_id: str
    element_type: str
    reason: str


@dataclass(frozen=True)
class _DeviceConnection:
    line: ET.Element
    endpoint: int
    pin: int | None
    point: tuple[float, float]


@dataclass(frozen=True)
class _StandardPinCandidate:
    device: ET.Element
    device_id: str
    pin_index: int
    point: tuple[float, float]


@dataclass(frozen=True)
class _RmuOutgoingBranch:
    line: ET.Element
    endpoint: int
    side: str
    point: tuple[float, float]
    rect_id: str
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class _RmuSwitchCorridor:
    """One RMU cabinet exit traced back to its real LBS/CB outgoing Pin."""

    branch: _RmuOutgoingBranch
    device: ET.Element
    device_id: str
    pin_index: int
    pin_point: tuple[float, float]
    path_lines: tuple[ET.Element, ...]


@dataclass(frozen=True)
class _RmuSwitchExitPath:
    """Topology path from one RMU LBS/CB outgoing Pin to the first cabinet exit.

    ``steps`` stores ``(line, entry_endpoint)`` pairs in switch -> outside order.
    Unlike :class:`_RmuOutgoingBranch`, this representation does not require the
    cabinet exit to be a terminal point of a line.  That matters for production
    FeedLine paths which enter the cabinet at one endpoint, leave through the left
    side, then continue around the drawing and terminate somewhere completely
    different.
    """

    rect_id: str
    rect: tuple[float, float, float, float]
    device: ET.Element
    device_id: str
    pin_index: int
    pin_point: tuple[float, float]
    side: str
    steps: tuple[tuple[ET.Element, int], ...]


@dataclass
class OrthogonalizationResult:
    inspected_lines: int = 0
    changed_lines: int = 0
    changed_segments: int = 0
    aligned_devices: int = 0
    aligned_lines: int = 0
    connection_aligned_lines: int = 0
    repaired_dangling_endpoints: int = 0
    repaired_topology_links: int = 0
    ambiguous_dangling_endpoints: int = 0
    rmu_outgoing_aligned_junctions: int = 0
    rmu_outgoing_extended_lines: int = 0
    rebuilt_lines: int = 0
    skipped_lines: int = 0
    changed_line_ids: list[str] = field(default_factory=list)
    aligned_device_ids: list[str] = field(default_factory=list)
    rebuilt_line_ids: list[str] = field(default_factory=list)
    endpoint_repair_details: list[str] = field(default_factory=list)
    rmu_outgoing_alignment_details: list[str] = field(default_factory=list)
    issues: list[OrthogonalizationIssue] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(
            self.changed_lines
            or self.aligned_devices
            or self.aligned_lines
            or self.repaired_dangling_endpoints
            or self.repaired_topology_links
            or self.rmu_outgoing_aligned_junctions
            or self.rmu_outgoing_extended_lines
            or self.rebuilt_lines
        )


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _format(value: float) -> str:
    if abs(value - round(value)) <= 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _points(element: ET.Element) -> list[tuple[float, float]] | None:
    raw = element.get("d") or ""
    matches = list(_POINT_RE.finditer(raw))
    if re.search(r"[^\s;]", _POINT_RE.sub("", raw)):
        # Do not rewrite an unfamiliar path-command dialect by accident.
        return None
    points = [(float(match.group(1)), float(match.group(2))) for match in matches]
    if len(points) < 2:
        return None
    return points


def _referenced_ids(element: ET.Element) -> set[str]:
    result: set[str] = set()
    for key in ("link", "node_area"):
        for token in (element.get(key) or "").split(";"):
            parts = [part.strip() for part in token.split(",")]
            if len(parts) >= 3 and parts[2]:
                result.add(parts[2])
    return result


def _endpoint_references(element: ET.Element) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {0: set(), 1: set()}
    for key in ("link", "node_area"):
        for token in (element.get(key) or "").split(";"):
            parts = [part.strip() for part in token.split(",")]
            if len(parts) < 3 or not parts[2]:
                continue
            try:
                endpoint = int(parts[0])
            except ValueError:
                continue
            if endpoint in result:
                result[endpoint].add(parts[2])
    return result


def _endpoint_reference_tokens(
    element: ET.Element,
    endpoint: int,
) -> list[tuple[int | None, str]]:
    """Return ``(other_port, other_id)`` references for one line endpoint."""
    rows: list[tuple[int | None, str]] = []
    seen: set[tuple[int | None, str]] = set()
    for key in ("link", "node_area"):
        for token in (element.get(key) or "").split(";"):
            parts = [part.strip() for part in token.split(",")]
            if len(parts) < 3 or not parts[2]:
                continue
            try:
                own_endpoint = int(parts[0])
            except ValueError:
                continue
            if own_endpoint != endpoint:
                continue
            try:
                other_port: int | None = int(parts[1])
            except (ValueError, IndexError):
                other_port = None
            row = (other_port, parts[2])
            if row not in seen:
                rows.append(row)
                seen.add(row)
    return rows


def _reciprocal_device_targets(
    devices: dict[str, ET.Element],
    *,
    line_id: str,
    endpoint: int,
) -> list[tuple[ET.Element, int]]:
    """Recover device->line topology when the line-side reference is missing."""
    if not line_id:
        return []
    rows: list[tuple[ET.Element, int]] = []
    seen: set[tuple[str, int]] = set()
    for device_id, device in devices.items():
        for key in ("node_area", "link"):
            for token in (device.get(key) or "").split(";"):
                parts = [part.strip() for part in token.split(",")]
                if len(parts) < 3 or parts[2] != line_id:
                    continue
                try:
                    pin_index = int(parts[0])
                    line_endpoint = int(parts[1])
                except ValueError:
                    continue
                if line_endpoint != endpoint:
                    continue
                signature = (device_id, pin_index)
                if signature not in seen:
                    rows.append((device, pin_index))
                    seen.add(signature)
    return rows


def _terminal_axis_compatible(
    points: list[tuple[float, float]],
    endpoint: int,
    target: tuple[float, float],
    *,
    axis_tolerance: float,
) -> bool:
    """Require an unreferenced snap to continue the existing terminal direction.

    This is the primary false-positive guard.  A visually dangling vertical wire may
    extend only to a Pin on the same X and beyond the current endpoint; the same rule
    applies horizontally.  Small diagonal legacy stubs are accepted only when the
    target itself lies on one endpoint axis and is very close.
    """
    if len(points) < 2:
        return False
    current = points[0] if endpoint == 0 else points[-1]
    inner = points[1] if endpoint == 0 else points[-2]
    vx = current[0] - inner[0]
    vy = current[1] - inner[1]
    tx = target[0] - current[0]
    ty = target[1] - current[1]
    if abs(vy) <= axis_tolerance and abs(vx) > axis_tolerance:
        return abs(ty) <= axis_tolerance and tx * vx >= -(axis_tolerance ** 2)
    if abs(vx) <= axis_tolerance and abs(vy) > axis_tolerance:
        return abs(tx) <= axis_tolerance and ty * vy >= -(axis_tolerance ** 2)
    # For a tiny historical skew, only accept a target that is itself strictly on
    # one endpoint axis. The normal orthogonalization pass will remove the skew.
    return (
        abs(tx) <= axis_tolerance or abs(ty) <= axis_tolerance
    ) and math.hypot(tx, ty) <= max(8.0, axis_tolerance * 4.0)


def _snap_line_endpoint_to_pin(
    line: ET.Element,
    endpoint: int,
    target: tuple[float, float],
    *,
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
    excluded_ids: set[str],
    axis_tolerance: float,
) -> bool:
    """Move one line endpoint to an exact Pin while preserving an orthogonal route."""
    points = _points(line)
    if points is None or len(points) < 2:
        return False
    current = points[0] if endpoint == 0 else points[-1]
    if math.hypot(current[0] - target[0], current[1] - target[1]) <= 1e-9:
        return False

    if endpoint == 0:
        neighbor = points[1]
        prefix: list[tuple[float, float]] = []
        suffix = points[2:]
        route = _orthogonal_route(
            target,
            neighbor,
            [item for item in obstacles if item[0] not in excluded_ids],
            axis_tolerance=axis_tolerance,
        )
        if route is None:
            return False
        proposed = prefix + route[0] + suffix
    else:
        neighbor = points[-2]
        prefix = points[:-2]
        route = _orthogonal_route(
            neighbor,
            target,
            [item for item in obstacles if item[0] not in excluded_ids],
            axis_tolerance=axis_tolerance,
        )
        if route is None:
            return False
        proposed = prefix + route[0]

    proposed = _simplify(proposed)
    usable_obstacles = [item for item in obstacles if item[0] not in excluded_ids]
    if _line_hits_obstacles(proposed, usable_obstacles, set()):
        return False
    _rewrite_points(line, proposed)
    return True


def _repair_dangling_endpoints_to_standard_pins(
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    result: OrthogonalizationResult,
    *,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
    max_snap_distance: float = 40.0,
    axis_tolerance: float = 1.5,
) -> None:
    """Attach small visual gaps to authoritative standard Pins and repair topology.

    The algorithm uses the current server/GLOBAL icon geometry, not device-box
    guessing. Existing line/device references win.  A reference-free endpoint is
    repaired only when exactly one unoccupied standard Pin can be reached by
    continuing the terminal segment in its current direction.  This makes the
    operation suitable for production SLDs where nearby bays can be dense.
    """
    if not geometry_templates:
        return

    devices = {
        (element.get("id") or "").strip(): element
        for element in _device_elements(elements)
        if (element.get("id") or "").strip()
    }
    pins_by_device: dict[str, dict[int, tuple[float, float]]] = {}
    pin_rows: list[_StandardPinCandidate] = []
    for device_id, device in devices.items():
        standard_pins = _authoritative_pin_points(device, geometry_templates)
        if not standard_pins:
            continue
        pins_by_device[device_id] = {index: point for index, point in standard_pins}
        pin_rows.extend(
            _StandardPinCandidate(device, device_id, index, point)
            for index, point in standard_pins
        )
    if not pin_rows:
        return

    # Spatial hash keeps a large SLD linear-ish instead of checking every endpoint
    # against every device Pin.
    cell_size = max(8.0, float(max_snap_distance))
    pin_grid: dict[tuple[int, int], list[_StandardPinCandidate]] = {}
    for candidate in pin_rows:
        key = (
            math.floor(candidate.point[0] / cell_size),
            math.floor(candidate.point[1] / cell_size),
        )
        pin_grid.setdefault(key, []).append(candidate)

    def nearby(point: tuple[float, float]) -> list[_StandardPinCandidate]:
        cx = math.floor(point[0] / cell_size)
        cy = math.floor(point[1] / cell_size)
        rows: list[_StandardPinCandidate] = []
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                rows.extend(pin_grid.get((gx, gy), ()))
        return rows

    # A standard electrical Pin is treated as one connection point. Existing
    # topology and exact geometry both reserve it so a second dangling wire cannot
    # be attached accidentally.
    occupied: dict[tuple[str, int], set[str]] = {}
    line_by_id = {
        (line.get("id") or "").strip(): line
        for line in line_elements
        if (line.get("id") or "").strip()
    }
    for line_id, line in line_by_id.items():
        for endpoint in (0, 1):
            for pin_index, other_id in _endpoint_reference_tokens(line, endpoint):
                if other_id in pins_by_device and pin_index in pins_by_device[other_id]:
                    occupied.setdefault((other_id, int(pin_index)), set()).add(line_id)
    for device_id, device in devices.items():
        for key in ("node_area", "link"):
            for token in (device.get(key) or "").split(";"):
                parts = [part.strip() for part in token.split(",")]
                if len(parts) < 3 or parts[2] not in line_by_id:
                    continue
                try:
                    pin_index = int(parts[0])
                except ValueError:
                    continue
                if pin_index in pins_by_device.get(device_id, {}):
                    occupied.setdefault((device_id, pin_index), set()).add(parts[2])

    # Geometry-only old drawings sometimes have no references at all. Reserve Pins
    # that already have a line endpoint essentially on top of them.
    for line_id, line in line_by_id.items():
        points = _points(line)
        if points is None:
            continue
        for endpoint, point in ((0, points[0]), (1, points[-1])):
            for candidate in nearby(point):
                if math.hypot(point[0] - candidate.point[0], point[1] - candidate.point[1]) <= 1.25:
                    occupied.setdefault((candidate.device_id, candidate.pin_index), set()).add(line_id)

    obstacles = _build_obstacles(elements)
    repairable = {"ConnectLine", "FeedLine", "BusDis", "Bus", "ACLine"}
    for line in line_elements:
        if local_name(line.tag) not in repairable:
            continue
        line_id = (line.get("id") or "").strip()
        if not line_id:
            continue
        points = _points(line)
        if points is None:
            continue
        for endpoint in (0, 1):
            # Refresh because endpoint 0 may have been modified before endpoint 1.
            points = _points(line)
            if points is None:
                continue
            point = points[0] if endpoint == 0 else points[-1]
            raw_refs = _endpoint_reference_tokens(line, endpoint)
            raw_device_ids = {
                other_id for _pin_index, other_id in raw_refs if other_id in devices
            }
            referenced_device_rows = [
                (devices[other_id], pin_index)
                for pin_index, other_id in raw_refs
                if other_id in devices and pin_index is not None
            ]
            non_device_refs = [
                other_id for _pin_index, other_id in raw_refs if other_id not in devices
            ]
            reciprocal_rows = _reciprocal_device_targets(
                devices, line_id=line_id, endpoint=endpoint
            )

            explicit_rows: list[tuple[ET.Element, int]] = []
            seen_explicit: set[tuple[str, int]] = set()
            for device, pin_index in referenced_device_rows + reciprocal_rows:
                device_id = (device.get("id") or "").strip()
                signature = (device_id, int(pin_index))
                if signature not in seen_explicit:
                    explicit_rows.append((device, int(pin_index)))
                    seen_explicit.add(signature)

            selected: _StandardPinCandidate | None = None
            distance = float("inf")
            if explicit_rows:
                # Conflicting topology is never guessed through.
                if len(explicit_rows) != 1:
                    result.ambiguous_dangling_endpoints += 1
                    result.issues.append(OrthogonalizationIssue(
                        element_id=line_id,
                        element_type=local_name(line.tag),
                        reason=f"端点 {endpoint} 同时指向多个设备/Pin，未自动修复。",
                    ))
                    continue
                device, pin_index = explicit_rows[0]
                device_id = (device.get("id") or "").strip()
                target = pins_by_device.get(device_id, {}).get(pin_index)
                if target is None:
                    continue
                distance = math.hypot(point[0] - target[0], point[1] - target[1])
                if distance > max_snap_distance:
                    result.issues.append(OrthogonalizationIssue(
                        element_id=line_id,
                        element_type=local_name(line.tag),
                        reason=(
                            f"端点 {endpoint} 已引用设备 {device_id} Pin {pin_index}，但距标准 Pin "
                            f"{distance:.1f} > {max_snap_distance:g}，为避免大范围误拉线而跳过。"
                        ),
                    ))
                    continue
                selected = _StandardPinCandidate(device, device_id, pin_index, target)
            else:
                # If the endpoint already points to another line/junction it is not a
                # dangling device endpoint and must not be stolen by a nearby symbol.
                if non_device_refs:
                    continue
                if len(raw_device_ids) > 1:
                    result.ambiguous_dangling_endpoints += 1
                    result.issues.append(OrthogonalizationIssue(
                        element_id=line_id,
                        element_type=local_name(line.tag),
                        reason=f"端点 {endpoint} 已引用多个设备但缺少明确 Pin，未自动猜测。",
                    ))
                    continue
                constrained_device_id = next(iter(raw_device_ids)) if raw_device_ids else ""
                candidates: list[tuple[float, _StandardPinCandidate]] = []
                for candidate in nearby(point):
                    if constrained_device_id and candidate.device_id != constrained_device_id:
                        continue
                    dist = math.hypot(
                        point[0] - candidate.point[0], point[1] - candidate.point[1]
                    )
                    if dist > max_snap_distance:
                        continue
                    if not _terminal_axis_compatible(
                        points, endpoint, candidate.point, axis_tolerance=axis_tolerance
                    ):
                        continue
                    owners = occupied.get((candidate.device_id, candidate.pin_index), set())
                    if owners and owners != {line_id}:
                        continue
                    candidates.append((dist, candidate))
                candidates.sort(key=lambda item: (item[0], item[1].device_id, item[1].pin_index))
                if len(candidates) != 1:
                    if len(candidates) > 1:
                        result.ambiguous_dangling_endpoints += 1
                        result.issues.append(OrthogonalizationIssue(
                            element_id=line_id,
                            element_type=local_name(line.tag),
                            reason=(
                                f"端点 {endpoint} 在 {max_snap_distance:g} 范围内存在 "
                                f"{len(candidates)} 个方向兼容且未占用的标准 Pin，存在歧义，未自动连接。"
                            ),
                        ))
                    continue
                distance, selected = candidates[0]

            assert selected is not None
            owners = occupied.get((selected.device_id, selected.pin_index), set())
            if owners and owners != {line_id}:
                continue
            excluded = _referenced_ids(line) | {selected.device_id}
            geometry_changed = _snap_line_endpoint_to_pin(
                line,
                endpoint,
                selected.point,
                obstacles=obstacles,
                excluded_ids=excluded,
                axis_tolerance=axis_tolerance,
            )
            # Exact geometry with missing reciprocal topology is also a valid repair.
            refreshed = _points(line)
            if refreshed is None:
                continue
            actual = refreshed[0] if endpoint == 0 else refreshed[-1]
            if math.hypot(actual[0] - selected.point[0], actual[1] - selected.point[1]) > 1e-6:
                result.issues.append(OrthogonalizationIssue(
                    element_id=line_id,
                    element_type=local_name(line.tag),
                    reason=(
                        f"端点 {endpoint} 到设备 {selected.device_id} Pin {selected.pin_index} 的安全延长路线"
                        "会穿越其他设备，未自动连接。"
                    ),
                ))
                continue
            topology_changed = _ensure_device_line_reciprocal(
                selected.device,
                line,
                port_index=selected.pin_index,
                line_endpoint_index=endpoint,
            )
            if geometry_changed:
                result.repaired_dangling_endpoints += 1
            if topology_changed:
                result.repaired_topology_links += topology_changed
            if geometry_changed or topology_changed:
                occupied.setdefault((selected.device_id, selected.pin_index), set()).add(line_id)
                result.endpoint_repair_details.append(
                    f"<{local_name(line.tag)}> id={line_id} 端点 {endpoint} -> "
                    f"设备 {selected.device_id} Pin {selected.pin_index} "
                    f"({selected.point[0]:g},{selected.point[1]:g})，原间隙 {distance:.1f}；"
                    "已补齐 reciprocal link/node_area。"
                )


_RMU_OUTGOING_LINE_TYPES = {"ConnectLine", "FeedLine", "ACLine"}


def _point_inside_rect(
    point: tuple[float, float],
    rect: tuple[float, float, float, float],
    *,
    tolerance: float = 1.0,
) -> bool:
    x, y = point
    left, top, right, bottom = rect
    return (
        left - tolerance <= x <= right + tolerance
        and top - tolerance <= y <= bottom + tolerance
    )


def _outside_side(
    point: tuple[float, float],
    rect: tuple[float, float, float, float],
    *,
    tolerance: float = 1.0,
) -> str | None:
    x, y = point
    left, top, right, bottom = rect
    candidates: list[tuple[float, str]] = []
    if x < left - tolerance:
        candidates.append((left - x, "left"))
    if x > right + tolerance:
        candidates.append((x - right, "right"))
    if y < top - tolerance:
        candidates.append((top - y, "top"))
    if y > bottom + tolerance:
        candidates.append((y - bottom, "bottom"))
    if not candidates:
        return None
    # A corner can technically be outside on two axes. The nearest cabinet side is
    # the branch exit direction and keeps the decision deterministic.
    return min(candidates, key=lambda item: (item[0], item[1]))[1]


def _rmu_outgoing_branches(
    tree: ET.ElementTree,
    line_elements: list[ET.Element],
) -> list[_RmuOutgoingBranch]:
    """Return every electrical line that exits a recognized RMU cabinet.

    The detection deliberately does not depend on Y1/Y2/... labels.  Once a cabinet
    is recognized, *all* ConnectLine/FeedLine/ACLine branches whose terminal path
    crosses from the cabinet interior to one exterior side are considered outgoing.
    This is the contract requested for Jeddah drawings: Y1 is not special and a
    3L/4L cabinet gets the same treatment for every outgoing way.
    """
    try:
        recognized = identify_rmus(
            tree,
            Path("<orthogonalize-memory>"),
            name_positions=("top", "right", "bottom", "left"),
            name_resolution_mode="auto_cluster",
        )
    except Exception:
        return []
    rows: list[_RmuOutgoingBranch] = []
    seen: set[tuple[str, int, str]] = set()
    for cabinet in recognized.items:
        rect = (
            float(cabinet.rect_x),
            float(cabinet.rect_y),
            float(cabinet.rect_x + cabinet.rect_w),
            float(cabinet.rect_y + cabinet.rect_h),
        )
        for line in line_elements:
            if local_name(line.tag) not in _RMU_OUTGOING_LINE_TYPES:
                continue
            points = _points(line)
            if points is None or len(points) < 2:
                continue
            first_inside = _point_inside_rect(points[0], rect)
            last_inside = _point_inside_rect(points[-1], rect)
            if first_inside == last_inside:
                continue
            endpoint = 1 if first_inside else 0
            point = points[-1] if endpoint == 1 else points[0]
            side = _outside_side(point, rect)
            if side is None:
                continue
            # The terminal segment itself must point through that side. This filters
            # unrelated long lines that merely happen to cross a cabinet rectangle.
            neighbor = points[-2] if endpoint == 1 else points[1]
            if side in {"left", "right"}:
                if abs(neighbor[1] - point[1]) > 2.0:
                    continue
            else:
                if abs(neighbor[0] - point[0]) > 2.0:
                    continue
            line_id = (line.get("id") or "").strip()
            signature = (line_id or str(id(line)), endpoint, cabinet.rect_id)
            if signature in seen:
                continue
            seen.add(signature)
            rows.append(
                _RmuOutgoingBranch(
                    line=line,
                    endpoint=endpoint,
                    side=side,
                    point=point,
                    rect_id=cabinet.rect_id,
                    rect=rect,
                )
            )
    return rows


def _cluster_rmu_outgoing_branches(
    branches: list[_RmuOutgoingBranch],
    *,
    cabinet_axis_tolerance: float = 24.0,
) -> list[list[_RmuOutgoingBranch]]:
    """Cluster stacked/side-by-side RMUs so sibling outgoing ways share one axis."""
    groups: list[list[_RmuOutgoingBranch]] = []
    for side in ("left", "right", "top", "bottom"):
        side_rows = [row for row in branches if row.side == side]
        if not side_rows:
            continue
        # Left/right exits align within a vertical cabinet column; top/bottom exits
        # align within a horizontal cabinet row.
        def cabinet_axis(row: _RmuOutgoingBranch) -> float:
            left, top, right, bottom = row.rect
            return (left + right) / 2.0 if side in {"left", "right"} else (top + bottom) / 2.0

        side_rows.sort(key=lambda row: (cabinet_axis(row), row.rect_id, row.point))
        current: list[_RmuOutgoingBranch] = []
        center = 0.0
        for row in side_rows:
            axis = cabinet_axis(row)
            if not current or abs(axis - center) <= cabinet_axis_tolerance:
                current.append(row)
                center = sum(cabinet_axis(item) for item in current) / len(current)
            else:
                groups.append(current)
                current = [row]
                center = axis
        if current:
            groups.append(current)
    return groups



def _is_rmu_switch_device(element: ET.Element) -> bool:
    """Return True for the LBS/CB symbols that own an RMU outgoing way.

    Do not use Y1/Y2/Q1 text here.  Jeddah drawings can contain more ways and the
    authoritative distinction is the actual symbol devref.
    """
    if local_name(element.tag) != "CBreakerDis":
        return False
    devref = re.sub(r"[^A-Z0-9]+", "_", (element.get("devref") or "").upper())
    return any(
        token in devref
        for token in (
            "LOAD_BREAKER_SWITCH",
            "LOADBREAKERSWITCH",
            "CIRCUIT_BREAKER",
            "CIRCUITBREAKER",
            "RMU_LBS",
            "RMU_BRK",
        )
    )


def _device_center_in_rect(
    element: ET.Element,
    rect: tuple[float, float, float, float],
    *,
    tolerance: float = 2.0,
) -> bool:
    width = _number(element.get("w")) or 0.0
    height = _number(element.get("h")) or 0.0
    if width <= 0 or height <= 0:
        return False
    x = _number(element.get("x")) or 0.0
    y = _number(element.get("y")) or 0.0
    cx = x + width / 2.0
    cy = y + height / 2.0
    left, top, right, bottom = rect
    return (
        left - tolerance <= cx <= right + tolerance
        and top - tolerance <= cy <= bottom + tolerance
    )


def _pin_faces_rmu_exit_side(
    device: ET.Element,
    point: tuple[float, float],
    side: str,
    *,
    tolerance: float = 2.0,
) -> bool:
    """Reject a bus-side switch Pin when tracing an RMU cabinet exit."""
    width = _number(device.get("w")) or 0.0
    height = _number(device.get("h")) or 0.0
    x = _number(device.get("x")) or 0.0
    y = _number(device.get("y")) or 0.0
    cx = x + width / 2.0
    cy = y + height / 2.0
    if side == "left":
        return point[0] <= cx + tolerance
    if side == "right":
        return point[0] >= cx - tolerance
    if side == "top":
        return point[1] <= cy + tolerance
    return point[1] >= cy - tolerance


def _distance_point_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Return the Euclidean distance from *point* to a finite line segment."""
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-12:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    cx = x1 + t * dx
    cy = y1 + t * dy
    return math.hypot(px - cx, py - cy)


def _distance_point_to_polyline(
    point: tuple[float, float],
    points: list[tuple[float, float]],
) -> float:
    if len(points) < 2:
        return float("inf")
    return min(
        _distance_point_to_segment(point, start, end)
        for start, end in zip(points, points[1:])
    )



def _device_pin_line_connections(
    device: ET.Element,
    line_by_id: dict[str, ET.Element],
) -> list[tuple[int, ET.Element, int]]:
    """Return unique ``(device_pin, line, line_endpoint)`` topology rows.

    RMU switch symbols usually carry the authoritative Pin-to-line relationship on
    the device itself.  Read both ``node_area`` and ``link`` because older Jeddah
    files are inconsistent about which attribute is populated.
    """
    rows: list[tuple[int, ET.Element, int]] = []
    seen: set[tuple[int, str, int]] = set()
    for key in ("node_area", "link"):
        for token in (device.get(key) or "").split(";"):
            parts = [part.strip() for part in token.split(",")]
            if len(parts) < 3 or not parts[2]:
                continue
            try:
                pin_index = int(parts[0])
                line_endpoint = int(parts[1])
            except ValueError:
                continue
            if line_endpoint not in (0, 1):
                continue
            line = line_by_id.get(parts[2])
            if line is None or local_name(line.tag) not in _RMU_OUTGOING_LINE_TYPES:
                continue
            signature = (pin_index, parts[2], line_endpoint)
            if signature in seen:
                continue
            seen.add(signature)
            rows.append((pin_index, line, line_endpoint))
    return rows


def _oriented_points_from_endpoint(
    line: ET.Element,
    entry_endpoint: int,
) -> list[tuple[float, float]] | None:
    points = _points(line)
    if points is None:
        return None
    return list(points if int(entry_endpoint) == 0 else reversed(points))


def _first_rmu_exit_side(
    oriented_points: list[tuple[float, float]],
    rect: tuple[float, float, float, float],
    *,
    tolerance: float = 1.0,
) -> str | None:
    """Return the first cabinet side crossed while walking switch -> outside."""
    if len(oriented_points) < 2:
        return None
    # The line endpoint attached to an RMU switch must start inside the cabinet.
    # A tiny placement error on the frame edge is tolerated.
    if not _point_inside_rect(oriented_points[0], rect, tolerance=max(3.0, tolerance)):
        return None
    for current, nxt in zip(oriented_points, oriented_points[1:]):
        current_inside = _point_inside_rect(current, rect, tolerance=tolerance)
        next_inside = _point_inside_rect(nxt, rect, tolerance=tolerance)
        if current_inside and not next_inside:
            return _outside_side(nxt, rect, tolerance=tolerance)
    return None


def _trace_switch_pin_to_rmu_exit(
    *,
    rect_id: str,
    rect: tuple[float, float, float, float],
    device: ET.Element,
    device_id: str,
    pin_index: int,
    pin_point: tuple[float, float],
    start_line: ET.Element,
    start_endpoint: int,
    line_by_id: dict[str, ET.Element],
    max_hops: int = 10,
    junction_tolerance: float = 32.0,
) -> _RmuSwitchExitPath | None:
    """Trace one LBS/CB Pin outward until *any segment* leaves its RMU frame.

    This is intentionally switch-centric.  The older boundary-centric algorithm
    could miss a valid way when the final FeedLine is a multi-bend route whose XML
    endpoints terminate at two distant RMUs.  In that case the local cabinet exit is
    an *interior vertex/segment* of the FeedLine, not a line endpoint.  Starting from
    the real switch Pin avoids that blind spot entirely.
    """
    queue: list[tuple[ET.Element, int, tuple[tuple[ET.Element, int], ...], int]] = [
        (start_line, int(start_endpoint), ((start_line, int(start_endpoint)),), 0)
    ]
    visited: set[tuple[str, int]] = set()
    candidates: list[_RmuSwitchExitPath] = []

    while queue:
        line, entry_endpoint, steps, hops = queue.pop(0)
        line_id = (line.get("id") or str(id(line))).strip()
        state = (line_id, int(entry_endpoint))
        if state in visited:
            continue
        visited.add(state)
        oriented = _oriented_points_from_endpoint(line, entry_endpoint)
        if oriented is None:
            continue

        side = _first_rmu_exit_side(oriented, rect, tolerance=1.0)
        if side is not None:
            candidates.append(
                _RmuSwitchExitPath(
                    rect_id=rect_id,
                    rect=rect,
                    device=device,
                    device_id=device_id,
                    pin_index=pin_index,
                    pin_point=pin_point,
                    side=side,
                    steps=steps,
                )
            )
            # First cabinet crossing is enough; do not walk through the external
            # feeder into another RMU.
            continue
        if hops >= max_hops:
            continue

        far_endpoint = 1 - int(entry_endpoint)
        junction = oriented[-1]
        path_ids = {(row[0].get("id") or str(id(row[0]))).strip() for row in steps}
        for other_port, other_id in _endpoint_reference_tokens(line, far_endpoint):
            if other_port not in (0, 1) or other_id in path_ids:
                continue
            other = line_by_id.get(other_id)
            if other is None or local_name(other.tag) not in _RMU_OUTGOING_LINE_TYPES:
                continue
            other_points = _points(other)
            if other_points is None:
                continue
            other_junction = other_points[int(other_port)]
            # The XML topology is authoritative, but production drawings can carry
            # a 1~several-unit stale geometric offset.  Large jumps are not local RMU
            # corridors and are deliberately ignored.
            if math.hypot(
                junction[0] - other_junction[0], junction[1] - other_junction[1]
            ) > junction_tolerance:
                continue
            queue.append(
                (
                    other,
                    int(other_port),
                    steps + ((other, int(other_port)),),
                    hops + 1,
                )
            )

    if not candidates:
        return None
    # Prefer the shortest topological route.  If two equally short paths leave the
    # cabinet on different sides, the drawing is ambiguous and must not be guessed.
    candidates.sort(
        key=lambda item: (
            len(item.steps),
            item.side,
            (item.steps[-1][0].get("id") or str(id(item.steps[-1][0]))),
        )
    )
    best = candidates[0]
    if len(candidates) > 1 and len(candidates[1].steps) == len(best.steps):
        other = candidates[1]
        if (
            other.side != best.side
            or (other.steps[-1][0].get("id") or "") != (best.steps[-1][0].get("id") or "")
        ):
            return None
    return best


def _rmu_switch_exit_paths(
    tree: ET.ElementTree,
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    *,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
) -> list[_RmuSwitchExitPath]:
    """Discover every RMU LBS/CB outgoing path from the device side outward."""
    try:
        recognized = identify_rmus(
            tree,
            Path("<orthogonalize-memory>"),
            name_positions=("top", "right", "bottom", "left"),
            name_resolution_mode="auto_cluster",
        )
    except Exception:
        return []
    line_by_id = {
        (line.get("id") or "").strip(): line
        for line in line_elements
        if (line.get("id") or "").strip()
    }
    paths: list[_RmuSwitchExitPath] = []
    seen: set[tuple[str, int, str]] = set()
    for cabinet in recognized.items:
        rect = (
            float(cabinet.rect_x),
            float(cabinet.rect_y),
            float(cabinet.rect_x + cabinet.rect_w),
            float(cabinet.rect_y + cabinet.rect_h),
        )
        switches = [
            element
            for element in elements
            if _is_rmu_switch_device(element) and _device_center_in_rect(element, rect)
        ]
        for device in switches:
            device_id = (device.get("id") or "").strip()
            if not device_id:
                continue
            authoritative = dict(_authoritative_pin_points(device, geometry_templates))
            for pin_index, line, line_endpoint in _device_pin_line_connections(device, line_by_id):
                line_points = _points(line)
                if line_points is None:
                    continue
                fallback_point = line_points[0] if line_endpoint == 0 else line_points[-1]
                pin_point = authoritative.get(pin_index, fallback_point)
                path = _trace_switch_pin_to_rmu_exit(
                    rect_id=cabinet.rect_id,
                    rect=rect,
                    device=device,
                    device_id=device_id,
                    pin_index=pin_index,
                    pin_point=pin_point,
                    start_line=line,
                    start_endpoint=line_endpoint,
                    line_by_id=line_by_id,
                )
                if path is None:
                    continue
                signature = (device_id, pin_index, path.side)
                if signature in seen:
                    continue
                seen.add(signature)
                paths.append(path)
    return paths


def _align_terminal_leg_to_axis(
    line: ET.Element,
    *,
    entry_endpoint: int,
    side: str,
    pin_point: tuple[float, float],
    max_cross_axis_adjust: float = 120.0,
) -> list[tuple[tuple[float, float], tuple[float, float], int]]:
    """Move only the RMU-side terminal leg of a long external feeder to Pin axis.

    Example (left exit)::

        639,3958 -> 602,3958 -> 602,4177 -> ...

    with a switch Pin at y=3960 becomes::

        639,3960 -> 602,3960 -> 602,4177 -> ...

    Thus the feeder/ConnectLine may be freely *lengthened* at its first elbow while
    the distant route and the drawing architecture remain unchanged.
    """
    points = _points(line)
    if points is None or len(points) < 2:
        return []
    reverse = int(entry_endpoint) == 1
    oriented = list(reversed(points)) if reverse else list(points)
    old_oriented = list(oriented)

    if side in {"left", "right"}:
        target = pin_point[1]
        # Normal case: the first segment is already horizontal.  Historical RMU
        # exits can also begin with a tiny perpendicular 1~8 unit stub and only then
        # turn horizontal (the exact 22522/Y1 defect).  In that case flatten the
        # tiny stub *and the whole following horizontal run* to the Pin row.
        if abs(oriented[1][1] - oriented[0][1]) <= 2.0:
            run_start = 0
            original_y = oriented[0][1]
        elif (
            len(oriented) >= 3
            and abs(oriented[1][0] - oriented[0][0]) <= 2.0
            and abs(oriented[1][1] - oriented[0][1]) <= 8.0
            and abs(oriented[2][1] - oriented[1][1]) <= 2.0
        ):
            run_start = 1
            original_y = oriented[1][1]
        else:
            return []
        if max(abs(oriented[i][1] - target) for i in range(0, run_start + 1)) > max_cross_axis_adjust:
            return []
        idx = run_start
        while idx + 1 < len(oriented) and abs(oriented[idx + 1][1] - original_y) <= 2.0:
            idx += 1
        idx = max(run_start + 1, idx) if len(oriented) > run_start + 1 else idx
        for pos in range(0, min(idx + 1, len(oriented))):
            oriented[pos] = (oriented[pos][0], target)
    else:
        target = pin_point[0]
        if abs(oriented[1][0] - oriented[0][0]) <= 2.0:
            run_start = 0
            original_x = oriented[0][0]
        elif (
            len(oriented) >= 3
            and abs(oriented[1][1] - oriented[0][1]) <= 2.0
            and abs(oriented[1][0] - oriented[0][0]) <= 8.0
            and abs(oriented[2][0] - oriented[1][0]) <= 2.0
        ):
            run_start = 1
            original_x = oriented[1][0]
        else:
            return []
        if max(abs(oriented[i][0] - target) for i in range(0, run_start + 1)) > max_cross_axis_adjust:
            return []
        idx = run_start
        while idx + 1 < len(oriented) and abs(oriented[idx + 1][0] - original_x) <= 2.0:
            idx += 1
        idx = max(run_start + 1, idx) if len(oriented) > run_start + 1 else idx
        for pos in range(0, min(idx + 1, len(oriented))):
            oriented[pos] = (target, oriented[pos][1])

    if oriented == old_oriented:
        return []
    rewritten = list(reversed(oriented)) if reverse else oriented
    rewritten = _simplify(rewritten)
    old_first, old_last = points[0], points[-1]
    _rewrite_points(line, rewritten)
    moves: list[tuple[tuple[float, float], tuple[float, float], int]] = []
    if old_first != rewritten[0]:
        moves.append((old_first, rewritten[0], 0))
    if old_last != rewritten[-1]:
        moves.append((old_last, rewritten[-1], 1))
    return moves


def _align_rmu_switch_exit_paths(
    tree: ET.ElementTree,
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    *,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
    changed_ids: set[str],
) -> tuple[int, list[str]]:
    """Normalize switch -> cabinet-exit corridors, including interior FeedLine exits.

    This pass solves the 22522/Y1 class of drawing defect where the short ConnectLine
    is on the real LBS Pin row (e.g. y=3960) but a preceding blue ConnectLine and the
    first FeedLine leg remain on y=3958.  The switch Pin is the authority; ConnectLine
    pieces are flattened to it and the external feeder's local terminal leg is moved
    to the same row/column.  No RMU device is moved.
    """
    line_by_id = {
        (line.get("id") or "").strip(): line
        for line in line_elements
        if (line.get("id") or "").strip()
    }
    changed = 0
    details: list[str] = []
    paths = _rmu_switch_exit_paths(
        tree,
        elements,
        line_elements,
        geometry_templates=geometry_templates,
    )
    for path in paths:
        path_changed: set[str] = set()
        steps = list(path.steps)
        if not steps:
            continue

        # Every intermediate ConnectLine belongs to the local RMU corridor and may be
        # straightened completely to the authoritative switch Pin axis.
        for line, _entry_endpoint in steps[:-1]:
            endpoint_moves = _rewrite_corridor_line_to_switch_axis(
                line,
                side=path.side,
                pin_point=path.pin_point,
                max_cross_axis_adjust=120.0,
            )
            if not endpoint_moves:
                continue
            line_id = (line.get("id") or "").strip()
            if line_id:
                changed_ids.add(line_id)
                path_changed.add(line_id)
            _repair_shifted_partner_neighbors(
                line,
                endpoint_moves,
                line_by_id=line_by_id,
                max_distance=128.0,
                changed_ids=changed_ids,
            )

        # The final line is the first line whose *interior segment* or endpoint exits
        # the cabinet.  It may be a very long FeedLine serving another RMU, so only
        # reshape its local terminal leg and first elbow instead of shifting the whole
        # feeder.
        exit_line, exit_entry_endpoint = steps[-1]
        endpoint_moves = _align_terminal_leg_to_axis(
            exit_line,
            entry_endpoint=exit_entry_endpoint,
            side=path.side,
            pin_point=path.pin_point,
            max_cross_axis_adjust=120.0,
        )
        if endpoint_moves:
            exit_id = (exit_line.get("id") or "").strip()
            if exit_id:
                changed_ids.add(exit_id)
                path_changed.add(exit_id)
            _repair_shifted_partner_neighbors(
                exit_line,
                endpoint_moves,
                line_by_id=line_by_id,
                max_distance=128.0,
                changed_ids=changed_ids,
            )

        # Finally pin the device-side endpoint itself to the standard coordinate.
        first_line, first_entry = steps[0]
        if _retarget_terminal_endpoint(
            first_line,
            int(first_entry),
            path.pin_point,
            max_distance=128.0,
            allow_small_retraction=128.0,
        ):
            first_id = (first_line.get("id") or "").strip()
            if first_id:
                changed_ids.add(first_id)
                path_changed.add(first_id)

        if path_changed:
            changed += len(path_changed)
            key_name = (path.device.get("key_name") or path.device.get("p_NameString") or "").strip()
            details.append(
                f"RMU {path.rect_id} {path.side} 出线（{key_name or '未命名'}，设备 "
                f"{path.device_id} Pin {path.pin_index}）从设备侧追踪到柜外；"
                f"按标准连接点 ({path.pin_point[0]:g},{path.pin_point[1]:g}) 校直 "
                f"{len(path_changed)} 条线路（含柜内中间 ConnectLine/柜外 FeedLine 终端腿）。"
            )
    return changed, details


def _rmu_geometric_next_lines(
    *,
    current_line: ET.Element,
    junction: tuple[float, float],
    branch: _RmuOutgoingBranch,
    line_by_id: dict[str, ET.Element],
    path_lines: tuple[ET.Element, ...],
    geometric_tolerance: float = 8.0,
) -> list[tuple[ET.Element, int, float]]:
    """Find unique-looking middle lines even when ``link/node_area`` is missing.

    Old Jeddah drawings occasionally contain this pattern::

        external FeedLine ---- boundary ConnectLine ===== middle ConnectLine ---- LBS

    where ``=====`` is a short geometric overlap (or a 1~5 unit visual gap) but the
    two ConnectLines have no reciprocal XML reference.  The electrical intent is
    still unambiguous because both pieces are on the RMU outgoing axis and the inner
    piece terminates at a standard LBS/CB Pin.

    This helper is deliberately conservative:
    * left/right exits only consider horizontal electrical lines;
    * top/bottom exits only consider vertical electrical lines;
    * the candidate must be inside/very near the same RMU frame;
    * the current junction must lie on, overlap, or be within a tiny distance of the
      candidate path;
    * traversal always continues *inward* toward the cabinet, never back outside.
    """
    expected_axis = "horizontal" if branch.side in {"left", "right"} else "vertical"
    path_ids = {
        (line.get("id") or str(id(line))).strip()
        for line in path_lines
    }
    rows: list[tuple[ET.Element, int, float]] = []
    for candidate in line_by_id.values():
        candidate_id = (candidate.get("id") or str(id(candidate))).strip()
        if candidate is current_line or candidate_id in path_ids:
            continue
        if local_name(candidate.tag) not in _RMU_OUTGOING_LINE_TYPES:
            continue
        candidate_points = _points(candidate)
        if candidate_points is None:
            continue
        if _straight_axis(candidate_points, tolerance=2.0) != expected_axis:
            continue
        # At least part of the line must belong to the same cabinet neighborhood.
        if not any(
            _point_inside_rect(point, branch.rect, tolerance=8.0)
            for point in candidate_points
        ):
            continue
        distance = _distance_point_to_polyline(junction, candidate_points)
        if distance > geometric_tolerance:
            continue

        first = candidate_points[0]
        last = candidate_points[-1]
        if branch.side == "left":
            next_endpoint = 0 if first[0] >= last[0] else 1
        elif branch.side == "right":
            next_endpoint = 0 if first[0] <= last[0] else 1
        elif branch.side == "top":
            next_endpoint = 0 if first[1] >= last[1] else 1
        else:  # bottom
            next_endpoint = 0 if first[1] <= last[1] else 1
        next_point = first if next_endpoint == 0 else last
        if not _point_inside_rect(next_point, branch.rect, tolerance=8.0):
            continue

        # The inward endpoint must actually progress farther into the cabinet than
        # the junction.  This keeps a nearby parallel external feeder from being
        # mistaken for the missing middle ConnectLine.
        if branch.side == "left" and next_point[0] <= junction[0] - 0.5:
            continue
        if branch.side == "right" and next_point[0] >= junction[0] + 0.5:
            continue
        if branch.side == "top" and next_point[1] <= junction[1] - 0.5:
            continue
        if branch.side == "bottom" and next_point[1] >= junction[1] + 0.5:
            continue
        rows.append((candidate, next_endpoint, distance))
    rows.sort(
        key=lambda item: (
            item[2],
            (item[0].get("id") or str(id(item[0]))),
            item[1],
        )
    )
    return rows


def _trace_rmu_branch_to_switch_pin(
    branch: _RmuOutgoingBranch,
    *,
    line_by_id: dict[str, ET.Element],
    devices_by_id: dict[str, ET.Element],
    geometry_templates: dict[str, list[dict[str, object]]] | None,
    max_hops: int = 6,
    junction_tolerance: float = 24.0,
) -> _RmuSwitchCorridor | None:
    """Trace an RMU boundary exit through intermediate lines to its LBS/CB Pin.

    A cabinet exit often looks like::

        FeedLine -- blue ConnectLine -- junction -- ConnectLine -- LBS/CB Pin
                                      |
                                      +-- grounding spur

    The old pass only aligned the boundary line with the external feeder.  This
    traversal follows reciprocal ``link/node_area`` references *through the middle
    ConnectLine(s)* and identifies the real outgoing Pin of the LBS/CircuitBreaker.
    Grounding spurs are naturally ignored because they do not terminate at an RMU
    switch device.
    """
    switch_devices = {
        device_id: device
        for device_id, device in devices_by_id.items()
        if _is_rmu_switch_device(device)
        and _device_center_in_rect(device, branch.rect)
    }
    if not switch_devices:
        return None

    start_points = _points(branch.line)
    if start_points is None:
        return None
    inside_endpoint = 1 - int(branch.endpoint)
    branch_inside_point = start_points[inside_endpoint]

    # (line, endpoint to inspect, complete line path, hops)
    queue: list[tuple[ET.Element, int, tuple[ET.Element, ...], int]] = [
        (branch.line, inside_endpoint, (branch.line,), 0)
    ]
    visited: set[tuple[str, int]] = set()
    candidates: list[tuple[int, float, _RmuSwitchCorridor]] = []

    while queue:
        line, endpoint, path_lines, hops = queue.pop(0)
        line_id = (line.get("id") or str(id(line))).strip()
        state = (line_id, int(endpoint))
        if state in visited:
            continue
        visited.add(state)
        points = _points(line)
        if points is None:
            continue
        junction = points[0] if endpoint == 0 else points[-1]

        found_switch_here = False
        queued_explicit_inward = False
        expected_axis = "horizontal" if branch.side in {"left", "right"} else "vertical"

        for other_port, other_id in _endpoint_reference_tokens(line, endpoint):
            if other_port is None:
                continue
            device = switch_devices.get(other_id)
            if device is not None:
                pin_index = int(other_port)
                pin_map = dict(_authoritative_pin_points(device, geometry_templates))
                pin_point = pin_map.get(pin_index, junction)
                if not _pin_faces_rmu_exit_side(device, pin_point, branch.side):
                    continue
                cross_delta = (
                    abs(pin_point[1] - branch_inside_point[1])
                    if branch.side in {"left", "right"}
                    else abs(pin_point[0] - branch_inside_point[0])
                )
                candidates.append(
                    (
                        hops,
                        cross_delta,
                        _RmuSwitchCorridor(
                            branch=branch,
                            device=device,
                            device_id=other_id,
                            pin_index=pin_index,
                            pin_point=pin_point,
                            path_lines=path_lines,
                        ),
                    )
                )
                found_switch_here = True
                continue

            other = line_by_id.get(other_id)
            if other is None or other_port not in (0, 1):
                continue
            if local_name(other.tag) not in _RMU_OUTGOING_LINE_TYPES:
                continue
            if hops >= max_hops:
                continue
            other_points = _points(other)
            if other_points is None:
                continue
            # An RMU left/right outgoing corridor is horizontal; top/bottom is
            # vertical.  Do not walk into a grounding spur just because old XML
            # recorded it on the same junction.
            if _straight_axis(other_points, tolerance=2.0) != expected_axis:
                continue
            other_junction = other_points[int(other_port)]
            # Explicit topology is authoritative, but a very large geometric gap
            # means this is not the local RMU corridor we are trying to normalize.
            if math.hypot(
                other_junction[0] - junction[0], other_junction[1] - junction[1]
            ) > junction_tolerance:
                continue
            next_endpoint = 1 - int(other_port)
            next_point = other_points[next_endpoint]
            # Trace inward only.  This prevents a cabinet exit from walking back out
            # through a neighbouring external feeder and finding a switch in another RMU.
            if not _point_inside_rect(next_point, branch.rect, tolerance=8.0):
                continue
            queue.append((other, next_endpoint, path_lines + (other,), hops + 1))
            queued_explicit_inward = True

        # Some production drawings have the correct visual corridor but omit the
        # reciprocal line-line link between the cabinet boundary ConnectLine and the
        # short ConnectLine attached to the LBS/CB.  When no explicit inward route
        # exists at this junction, bridge only a tiny, axis-compatible geometric
        # overlap/gap inside the same RMU.  This is intentionally a fallback: valid
        # topology always wins.
        if (
            not found_switch_here
            and not queued_explicit_inward
            and hops < max_hops
        ):
            for other, next_endpoint, _distance in _rmu_geometric_next_lines(
                current_line=line,
                junction=junction,
                branch=branch,
                line_by_id=line_by_id,
                path_lines=path_lines,
                geometric_tolerance=min(8.0, junction_tolerance),
            ):
                queue.append((other, next_endpoint, path_lines + (other,), hops + 1))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2].device_id, item[2].pin_index))
    best_hops, best_delta, best = candidates[0]
    # If two different switches are equally plausible at the same graph depth and
    # cross-axis distance, leave the corridor alone rather than guessing.
    if len(candidates) > 1:
        other_hops, other_delta, other = candidates[1]
        if (
            other_hops == best_hops
            and abs(other_delta - best_delta) <= 0.5
            and (other.device_id, other.pin_index) != (best.device_id, best.pin_index)
        ):
            return None
    return best


def _rewrite_corridor_line_to_switch_axis(
    line: ET.Element,
    *,
    side: str,
    pin_point: tuple[float, float],
    max_cross_axis_adjust: float = 48.0,
) -> list[tuple[tuple[float, float], tuple[float, float], int]]:
    """Straighten one corridor line onto the exact LBS/CB outgoing Pin axis.

    Only the cross-axis coordinate changes.  X extents of left/right exits and Y
    extents of top/bottom exits are preserved, so this operation lengthens/straightens
    existing connections instead of moving the RMU equipment itself.
    """
    points = _points(line)
    if points is None or len(points) < 2:
        return []
    old_first, old_last = points[0], points[-1]
    if side in {"left", "right"}:
        target = pin_point[1]
        if max(abs(y - target) for _x, y in points) > max_cross_axis_adjust:
            return []
        rewritten = [(x, target) for x, _y in points]
    else:
        target = pin_point[0]
        if max(abs(x - target) for x, _y in points) > max_cross_axis_adjust:
            return []
        rewritten = [(target, y) for _x, y in points]
    rewritten = _simplify(rewritten)
    if rewritten == points:
        return []
    _rewrite_points(line, rewritten)
    moves: list[tuple[tuple[float, float], tuple[float, float], int]] = []
    if old_first != rewritten[0]:
        moves.append((old_first, rewritten[0], 0))
    if old_last != rewritten[-1]:
        moves.append((old_last, rewritten[-1], 1))
    return moves


def _align_rmu_branch_to_switch_pin(
    corridor: _RmuSwitchCorridor,
    *,
    line_by_id: dict[str, ET.Element],
    changed_ids: set[str],
    max_cross_axis_adjust: float = 48.0,
) -> tuple[int, list[str]]:
    """Align boundary + intermediate ConnectLines to the owning LBS/CB Pin."""
    changed = 0
    details: list[str] = []
    for line in corridor.path_lines:
        old = _points(line)
        if old is None:
            continue
        endpoint_moves = _rewrite_corridor_line_to_switch_axis(
            line,
            side=corridor.branch.side,
            pin_point=corridor.pin_point,
            max_cross_axis_adjust=max_cross_axis_adjust,
        )
        if not endpoint_moves:
            continue
        line_id = (line.get("id") or "").strip()
        if line_id:
            changed_ids.add(line_id)
        changed += 1
        # Every moved junction must remain closed.  This also lengthens the external
        # vertical/horizontal feeder and any perpendicular grounding spur that shares
        # the junction.  The reciprocal topology itself is untouched.
        _repair_shifted_partner_neighbors(
            line,
            endpoint_moves,
            line_by_id=line_by_id,
            max_distance=max(56.0, max_cross_axis_adjust + 8.0),
            changed_ids=changed_ids,
        )
    if changed:
        key_name = (corridor.device.get("key_name") or corridor.device.get("p_NameString") or "").strip()
        details.append(
            f"RMU {corridor.branch.rect_id} {corridor.branch.side} 出线"
            f"（{key_name or '未命名'}，设备 {corridor.device_id} Pin {corridor.pin_index}）"
            f"已按标准连接点 ({corridor.pin_point[0]:g},{corridor.pin_point[1]:g}) 对齐；"
            f"含中间连接线 {len(corridor.path_lines)} 条。"
        )
    return changed, details


def _straight_axis(points: list[tuple[float, float]], *, tolerance: float = 1.5) -> str | None:
    if len(points) < 2:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if max(xs) - min(xs) <= tolerance:
        return "vertical"
    if max(ys) - min(ys) <= tolerance:
        return "horizontal"
    return None


def _point_on_polyline(
    point: tuple[float, float],
    points: list[tuple[float, float]],
    *,
    tolerance: float = 1.5,
) -> bool:
    x, y = point
    for start, end in zip(points, points[1:]):
        if abs(start[0] - end[0]) <= tolerance:
            if abs(x - start[0]) <= tolerance and min(start[1], end[1]) - tolerance <= y <= max(start[1], end[1]) + tolerance:
                return True
        elif abs(start[1] - end[1]) <= tolerance:
            if abs(y - start[1]) <= tolerance and min(start[0], end[0]) - tolerance <= x <= max(start[0], end[0]) + tolerance:
                return True
    return False


def _retarget_terminal_endpoint(
    line: ET.Element,
    endpoint: int,
    target: tuple[float, float],
    *,
    max_distance: float,
    axis_tolerance: float = 1.5,
    allow_small_retraction: float = 12.0,
) -> bool:
    """Move one terminal endpoint to target without introducing a diagonal segment."""
    points = _points(line)
    if points is None or len(points) < 2:
        return False
    index = 0 if endpoint == 0 else len(points) - 1
    neighbor_index = 1 if endpoint == 0 else len(points) - 2
    current = points[index]
    neighbor = points[neighbor_index]
    if math.hypot(current[0] - target[0], current[1] - target[1]) <= 1e-9:
        return False
    if math.hypot(current[0] - target[0], current[1] - target[1]) > max_distance:
        return False
    horizontal = abs(current[1] - neighbor[1]) <= axis_tolerance
    vertical = abs(current[0] - neighbor[0]) <= axis_tolerance
    if horizontal and abs(target[1] - neighbor[1]) <= axis_tolerance:
        proposed = (target[0], neighbor[1])
    elif vertical and abs(target[0] - neighbor[0]) <= axis_tolerance:
        proposed = (neighbor[0], target[1])
    else:
        return False
    old_length = math.hypot(current[0] - neighbor[0], current[1] - neighbor[1])
    new_length = math.hypot(proposed[0] - neighbor[0], proposed[1] - neighbor[1])
    if new_length + allow_small_retraction < old_length:
        return False
    points[index] = proposed
    _rewrite_points(line, _simplify(points))
    return True


def _shift_straight_partner_axis(
    line: ET.Element,
    *,
    target_axis: float,
    side: str,
    max_axis_shift: float,
) -> tuple[bool, list[tuple[tuple[float, float], tuple[float, float], int]]]:
    """Shift a straight external feeder axis by a small amount, preserving shape."""
    points = _points(line)
    if points is None:
        return False, []
    orientation = _straight_axis(points)
    expected = "vertical" if side in {"left", "right"} else "horizontal"
    if orientation != expected:
        return False, []
    current_axis = points[0][0] if orientation == "vertical" else points[0][1]
    delta = target_axis - current_axis
    if abs(delta) <= 1e-9:
        return False, []
    if abs(delta) > max_axis_shift:
        return False, []
    old_first, old_last = points[0], points[-1]
    if orientation == "vertical":
        shifted = [(target_axis, y) for _x, y in points]
    else:
        shifted = [(x, target_axis) for x, _y in points]
    _rewrite_points(line, shifted)
    return True, [(old_first, shifted[0], 0), (old_last, shifted[-1], 1)]


def _repair_shifted_partner_neighbors(
    line: ET.Element,
    endpoint_moves: list[tuple[tuple[float, float], tuple[float, float], int]],
    *,
    line_by_id: dict[str, ET.Element],
    max_distance: float,
    changed_ids: set[str],
) -> None:
    """Keep reciprocal line-line junctions closed after a tiny feeder-axis shift."""
    for old_point, new_point, endpoint in endpoint_moves:
        for other_port, other_id in _endpoint_reference_tokens(line, endpoint):
            if other_id not in line_by_id or other_port not in (0, 1):
                continue
            other = line_by_id[other_id]
            if local_name(other.tag) not in _RMU_OUTGOING_LINE_TYPES:
                continue
            other_points = _points(other)
            if other_points is None:
                continue
            other_point = other_points[0] if other_port == 0 else other_points[-1]
            # Only touch the reciprocal endpoint that was geometrically at (or very
            # close to) the old junction. This avoids interpreting Bus-style interior
            # references as terminal junctions.
            if math.hypot(other_point[0] - old_point[0], other_point[1] - old_point[1]) > max_distance:
                continue
            if _retarget_terminal_endpoint(
                other,
                int(other_port),
                new_point,
                max_distance=max_distance,
                allow_small_retraction=12.0,
            ):
                other_id_value = (other.get("id") or "").strip()
                if other_id_value:
                    changed_ids.add(other_id_value)


def _align_rmu_outgoing_lines(
    tree: ET.ElementTree,
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    result: OrthogonalizationResult,
    *,
    geometry_templates: dict[str, list[dict[str, object]]] | None = None,
    max_axis_shift: float = 12.0,
    max_extension: float = 120.0,
) -> None:
    """Align and close every recognized RMU outgoing way, never only Y1.

    For each cabinet column/row, all outgoing branch junctions on the same side use
    the outward-most existing axis.  Internal equipment is never moved.  The branch
    ConnectLine is lengthened outwards; a directly connected straight FeedLine /
    ConnectLine is shifted only by a small axis-normalization amount and its terminal
    end is extended to the exact branch junction.  Thus the visual architecture stays
    the same while broken/offset RMU exits become one straight corridor.
    """
    line_by_id = {
        (line.get("id") or "").strip(): line
        for line in line_elements
        if (line.get("id") or "").strip()
    }
    changed_ids: set[str] = set()
    aligned_junctions = 0
    details: list[str] = []

    devices_by_id = {
        (element.get("id") or "").strip(): element
        for element in elements
        if (element.get("id") or "").strip()
    }

    # v2.18.218: start from every real RMU LBS/CircuitBreaker outgoing Pin and walk
    # outward.  This catches multi-bend FeedLines whose local cabinet exit is an
    # interior vertex rather than a line endpoint (for example RMU 22522 / Y1).
    # The device Pin row/column is authoritative and the feeder/ConnectLine may be
    # lengthened locally to match it; RMU equipment itself is never moved.
    switch_path_changed, switch_path_details = _align_rmu_switch_exit_paths(
        tree,
        elements,
        line_elements,
        geometry_templates=geometry_templates,
        changed_ids=changed_ids,
    )
    aligned_junctions += switch_path_changed
    details.extend(switch_path_details)

    # Refresh branches after the switch-centric pass because it can change a local
    # FeedLine elbow / boundary ConnectLine before the legacy boundary pass runs.
    branches = _rmu_outgoing_branches(tree, line_elements)
    if not branches:
        if changed_ids:
            result.rmu_outgoing_extended_lines += len(changed_ids)
        result.rmu_outgoing_aligned_junctions += aligned_junctions
        result.rmu_outgoing_alignment_details.extend(details)
        return

    # Then make every RMU boundary corridor use the exact outgoing Pin ordinate of
    # its LBS/CircuitBreaker.  This deliberately traces through intermediate
    # ConnectLines: Y1/Y2/Q1 are presentation names only and are never hard-coded.
    # Once the internal corridor is on the switch Pin axis, the existing external
    # feeder alignment below simply grows the FeedLine/ConnectLine to that junction.
    for branch in branches:
        corridor = _trace_rmu_branch_to_switch_pin(
            branch,
            line_by_id=line_by_id,
            devices_by_id=devices_by_id,
            geometry_templates=geometry_templates,
        )
        if corridor is None:
            continue
        changed_count, corridor_details = _align_rmu_branch_to_switch_pin(
            corridor,
            line_by_id=line_by_id,
            changed_ids=changed_ids,
        )
        aligned_junctions += changed_count
        details.extend(corridor_details)

    for group in _cluster_rmu_outgoing_branches(branches):
        if not group:
            continue
        side = group[0].side
        coordinates = [
            row.point[0] if side in {"left", "right"} else row.point[1]
            for row in group
        ]
        if side == "left":
            target_axis = min(coordinates)
        elif side == "right":
            target_axis = max(coordinates)
        elif side == "top":
            target_axis = min(coordinates)
        else:
            target_axis = max(coordinates)

        for row in group:
            line = row.line
            points = _points(line)
            if points is None:
                continue
            current = points[0] if row.endpoint == 0 else points[-1]
            if side in {"left", "right"}:
                target = (target_axis, current[1])
            else:
                target = (current[0], target_axis)
            old_point = current
            branch_changed = _retarget_terminal_endpoint(
                line,
                row.endpoint,
                target,
                max_distance=max_extension,
                allow_small_retraction=0.0,
            )
            refreshed = _points(line)
            if refreshed is None:
                continue
            junction = refreshed[0] if row.endpoint == 0 else refreshed[-1]
            if branch_changed:
                line_id = (line.get("id") or "").strip()
                if line_id:
                    changed_ids.add(line_id)
                aligned_junctions += 1

            # The explicit line-line reference is authoritative for the outgoing
            # feeder.  Align every exit (Y1/Y2/Y3/Y4/... alike) rather than searching
            # for a particular Y label.
            for other_port, other_id in _endpoint_reference_tokens(line, row.endpoint):
                if other_id not in line_by_id or other_port not in (0, 1):
                    continue
                partner = line_by_id[other_id]
                if local_name(partner.tag) not in _RMU_OUTGOING_LINE_TYPES:
                    continue
                partner_points = _points(partner)
                if partner_points is None:
                    continue
                partner_endpoint = partner_points[0] if other_port == 0 else partner_points[-1]
                axis_shifted = False
                endpoint_moves: list[tuple[tuple[float, float], tuple[float, float], int]] = []
                if side in {"left", "right"} and abs(partner_endpoint[0] - junction[0]) > 1e-9:
                    axis_shifted, endpoint_moves = _shift_straight_partner_axis(
                        partner,
                        target_axis=junction[0],
                        side=side,
                        max_axis_shift=max_axis_shift,
                    )
                elif side in {"top", "bottom"} and abs(partner_endpoint[1] - junction[1]) > 1e-9:
                    axis_shifted, endpoint_moves = _shift_straight_partner_axis(
                        partner,
                        target_axis=junction[1],
                        side=side,
                        max_axis_shift=max_axis_shift,
                    )
                if axis_shifted:
                    partner_id = (partner.get("id") or "").strip()
                    if partner_id:
                        changed_ids.add(partner_id)
                    _repair_shifted_partner_neighbors(
                        partner,
                        endpoint_moves,
                        line_by_id=line_by_id,
                        max_distance=max(16.0, max_axis_shift * 2.0),
                        changed_ids=changed_ids,
                    )

                partner_points = _points(partner)
                if partner_points is None:
                    continue
                # If the feeder already crosses the junction, it is visually closed;
                # otherwise lengthen its referenced endpoint until it reaches the exit.
                if not _point_on_polyline(junction, partner_points):
                    if _retarget_terminal_endpoint(
                        partner,
                        int(other_port),
                        junction,
                        max_distance=max_extension,
                        allow_small_retraction=0.0,
                    ):
                        partner_id = (partner.get("id") or "").strip()
                        if partner_id:
                            changed_ids.add(partner_id)
                        aligned_junctions += 1
                final_partner = _points(partner)
                if final_partner is None or not _point_on_polyline(junction, final_partner):
                    continue
                if branch_changed or axis_shifted or math.hypot(
                    partner_endpoint[0] - junction[0], partner_endpoint[1] - junction[1]
                ) > 1e-6:
                    details.append(
                        f"RMU {row.rect_id} {side} 出线 <{local_name(line.tag)}> id={(line.get('id') or '').strip()} "
                        f"与 <{local_name(partner.tag)}> id={(partner.get('id') or '').strip()} 对齐到 "
                        f"({junction[0]:g},{junction[1]:g})。"
                    )

    if changed_ids:
        result.rmu_outgoing_extended_lines += len(changed_ids)
    result.rmu_outgoing_aligned_junctions += aligned_junctions
    result.rmu_outgoing_alignment_details.extend(details)

def _point_to_box_distance(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
) -> float:
    x, y = point
    left, top, right, bottom = box
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    return math.hypot(dx, dy)


def _nearest_box_boundary(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
) -> tuple[tuple[float, float], float]:
    x, y = point
    left, top, right, bottom = box
    candidates = [
        (max(left, min(right, x)), top),
        (max(left, min(right, x)), bottom),
        (left, max(top, min(bottom, y))),
        (right, max(top, min(bottom, y))),
    ]
    selected = min(candidates, key=lambda candidate: math.hypot(candidate[0] - x, candidate[1] - y))
    return selected, math.hypot(selected[0] - x, selected[1] - y)


def _device_elements(elements: list[ET.Element]) -> list[ET.Element]:
    return [
        element
        for element in elements
        if local_name(element.tag) not in _NON_OBSTACLE_TAGS
        and (element.get("devref") or "").strip()
        and _box(element) is not None
    ]


def _device_connections(
    elements: list[ET.Element],
    line_elements: list[ET.Element],
) -> dict[str, list[_DeviceConnection]]:
    """Resolve actual line endpoints attached to devices via node_area/link."""
    device_ids = {
        (element.get("id") or "").strip()
        for element in _device_elements(elements)
        if (element.get("id") or "").strip()
    }
    result: dict[str, list[_DeviceConnection]] = {}
    for line in line_elements:
        points = _points(line)
        if points is None:
            continue
        seen: set[tuple[str, int, int | None]] = set()
        # Older G files put the authoritative endpoint in link, newer files may
        # put it in node_area, and migrated files can contain both.  Merge both
        # attributes instead of treating them as alternatives.  The same token
        # in both attributes is deduplicated while different pins are retained.
        for key_name in ("link", "node_area"):
            for token in (line.get(key_name) or "").split(";"):
                parts = [part.strip() for part in token.split(",")]
                if len(parts) < 3 or parts[2] not in device_ids:
                    continue
                try:
                    endpoint = int(parts[0])
                except ValueError:
                    continue
                if endpoint not in (0, 1):
                    continue
                pin: int | None
                try:
                    pin = int(parts[1])
                except (ValueError, IndexError):
                    pin = None
                key = (parts[2], endpoint, pin)
                if key in seen:
                    continue
                seen.add(key)
                point = points[0] if endpoint == 0 else points[-1]
                result.setdefault(parts[2], []).append(
                    _DeviceConnection(line=line, endpoint=endpoint, pin=pin, point=point)
                )
    return result


def _standard_pin_for_connection(
    device: ET.Element,
    connection: _DeviceConnection,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
) -> tuple[float, float] | None:
    """Return the ACTIVE/GLOBAL standard pin for a topology connection."""
    if not geometry_templates:
        return None
    if connection.pin is None:
        return None
    pin_points = _authoritative_pin_points(device, geometry_templates)
    for pin_index, point in pin_points:
        if pin_index == connection.pin:
            return point
    return None


def _connection_is_trusted(
    device: ET.Element,
    connection: _DeviceConnection,
    *,
    endpoint_tolerance: float,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
) -> bool:
    """Require explicit standard-pin proximity when a standard is available."""
    if geometry_templates is None:
        return True
    expected = _standard_pin_for_connection(device, connection, geometry_templates)
    return expected is not None and math.hypot(
        connection.point[0] - expected[0], connection.point[1] - expected[1]
    ) <= endpoint_tolerance


def _shift_device_and_connections(
    device: ET.Element,
    delta: tuple[float, float],
    connections: list[_DeviceConnection],
) -> bool:
    """Move a device and every connected line endpoint by the same vector."""
    dx, dy = delta
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return False
    x = _number(device.get("x"))
    y = _number(device.get("y"))
    if x is None or y is None:
        return False
    device.set("x", _format(x + dx))
    device.set("y", _format(y + dy))
    seen: set[tuple[int, int]] = set()
    changed = False
    for connection in connections:
        key = (id(connection.line), connection.endpoint)
        if key in seen:
            continue
        seen.add(key)
        changed = _move_line_endpoint(connection.line, connection.endpoint, delta) or changed
    return changed


def _local_similar_device_groups(
    devices: list[ET.Element],
    connections: dict[str, list[_DeviceConnection]],
    *,
    tolerance: float,
) -> list[list[ET.Element]]:
    """Split one standard class into nearby, unambiguous rows or columns."""
    anchors: dict[int, tuple[float, float]] = {}
    for device in devices:
        device_id = (device.get("id") or "").strip()
        points = [item.point for item in connections.get(device_id, [])]
        if not points:
            continue
        anchors[id(device)] = (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )
    if len(anchors) < 2:
        return []

    # A class can appear in many independent parts of a large drawing.  The
    # gap is derived from the symbol size, so nearby repeated bays form a
    # group while distant instances of the same standard do not get pulled
    # into one global row/column.
    dimensions = [
        max((_box(device)[2] - _box(device)[0]), (_box(device)[3] - _box(device)[1]))
        for device in devices
        if _box(device) is not None
    ]
    local_gap = max(tolerance * 10.0, (max(dimensions) if dimensions else tolerance) * 6.0)
    groups: list[list[ET.Element]] = []
    for axis in ("x", "y"):
        eligible = [device for device in devices if id(device) in anchors]
        adjacency: dict[int, set[int]] = {id(device): set() for device in eligible}
        for index, first in enumerate(eligible):
            first_anchor = anchors[id(first)]
            for second in eligible[index + 1:]:
                second_anchor = anchors[id(second)]
                aligned_delta = abs(first_anchor[0] - second_anchor[0]) if axis == "x" else abs(first_anchor[1] - second_anchor[1])
                along_delta = abs(first_anchor[1] - second_anchor[1]) if axis == "x" else abs(first_anchor[0] - second_anchor[0])
                if aligned_delta <= tolerance and tolerance < along_delta <= local_gap:
                    adjacency[id(first)].add(id(second))
                    adjacency[id(second)].add(id(first))

        by_id = {id(device): device for device in eligible}
        visited: set[int] = set()
        for device in eligible:
            device_key = id(device)
            if device_key in visited or not adjacency[device_key]:
                continue
            stack = [device_key]
            visited.add(device_key)
            component: list[ET.Element] = []
            while stack:
                current = stack.pop()
                component.append(by_id[current])
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        stack.append(neighbor)
            xs = [anchors[id(item)][0] for item in component]
            ys = [anchors[id(item)][1] for item in component]
            if (
                len(component) >= 2
                and ((axis == "x" and max(xs) - min(xs) <= tolerance)
                     or (axis == "y" and max(ys) - min(ys) <= tolerance))
            ):
                groups.append(component)
    return groups


def _device_shift_is_safe(
    device: ET.Element,
    delta: tuple[float, float],
    devices: list[ET.Element],
) -> bool:
    box = _box(device)
    if box is None:
        return False
    shifted = (box[0] + delta[0], box[1] + delta[1], box[2] + delta[0], box[3] + delta[1])
    for other in devices:
        if other is device:
            continue
        other_box = _box(other)
        if other_box is not None and _boxes_overlap(shifted, other_box):
            return False
    return True


def _build_obstacles(
    elements: list[ET.Element],
) -> list[tuple[str, tuple[float, float, float, float]]]:
    return [
        ((element.get("id") or "").strip(), box)
        for element in elements
        if local_name(element.tag) not in _NON_OBSTACLE_TAGS
        and (box := _box(element)) is not None
    ]


def _line_hits_obstacles(
    points: list[tuple[float, float]],
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
    excluded_ids: set[str],
) -> bool:
    return any(
        _segment_hits_box(start, end, box)
        for start, end in zip(points, points[1:])
        for element_id, box in obstacles
        if element_id not in excluded_ids
    )


def _shifted_points(
    line: ET.Element,
    endpoint_index: int,
    delta: tuple[float, float],
) -> list[tuple[float, float]] | None:
    points = _points(line)
    if points is None:
        return None
    point_index = 0 if endpoint_index == 0 else len(points) - 1
    points[point_index] = (
        points[point_index][0] + delta[0],
        points[point_index][1] + delta[1],
    )
    return points


def _boxes_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    *,
    clearance: float = 0.5,
) -> bool:
    return (
        max(first[0], second[0]) < min(first[2], second[2]) - clearance
        and max(first[1], second[1]) < min(first[3], second[3]) - clearance
    )


def _move_line_endpoint(
    line: ET.Element,
    endpoint_index: int,
    delta: tuple[float, float],
) -> bool:
    points = _points(line)
    if points is None:
        return False
    point_index = 0 if endpoint_index == 0 else len(points) - 1
    old = points[point_index]
    moved = (old[0] + delta[0], old[1] + delta[1])
    if moved == old:
        return False
    points[point_index] = moved
    _rewrite_points(line, points)
    return True


def _align_similar_devices(
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    result: OrthogonalizationResult,
    *,
    tolerance: float,
    connections: dict[str, list[_DeviceConnection]],
    endpoint_tolerance: float,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
) -> None:
    """Snap repeated same-standard devices by their real connected pins."""
    devices = _device_elements(elements)
    by_key: dict[tuple[str, str, float, float, str], list[ET.Element]] = {}
    for device in devices:
        box = _box(device)
        if box is None:
            continue
        by_key.setdefault(
            (
                local_name(device.tag),
                (device.get("devref") or "").strip(),
                round(box[2] - box[0], 3),
                round(box[3] - box[1], 3),
                (device.get("rotate") or "").strip(),
            ),
            [],
        ).append(device)

    lines_by_device: dict[str, list[ET.Element]] = {}
    for line in line_elements:
        refs = _referenced_ids(line)
        for device_id in refs:
            lines_by_device.setdefault(device_id, []).append(line)

    local_groups: list[list[ET.Element]] = []
    for group in by_key.values():
        local_groups.extend(
            _local_similar_device_groups(group, connections, tolerance=tolerance)
        )

    # Resolve larger local arrays first.  A normal feeder bay is either a row
    # or a column; this ordering also makes the result deterministic if a
    # drawing contains an accidental crossing of two candidate groups.
    claimed_device_ids: set[str] = set()
    for group in sorted(local_groups, key=lambda items: (-len(items), (items[0].get("id") or ""))):
        group_ids = {
            (device.get("id") or "").strip()
            for device in group
            if (device.get("id") or "").strip()
        }
        # A drawing can contain a crossing row and column of the same symbol
        # class.  Do not move an instance twice using stale anchor coordinates;
        # the larger local array gets first claim and the other candidate is
        # left for the obstacle-aware line pass.
        if group_ids & claimed_device_ids:
            continue
        boxes = {id(device): _box(device) for device in group}
        anchors: dict[int, tuple[float, float]] = {}
        for device in group:
            device_id = (device.get("id") or "").strip()
            device_connections = connections.get(device_id, [])
            if any(
                not _connection_is_trusted(
                    device,
                    connection,
                    endpoint_tolerance=endpoint_tolerance,
                    geometry_templates=geometry_templates,
                )
                for connection in device_connections
            ):
                break
            points = [item.point for item in device_connections]
            if not points:
                break
            anchors[id(device)] = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
        if len(anchors) != len(group):
            continue
        x_values = [anchors[id(device)][0] for device in group]
        y_values = [anchors[id(device)][1] for device in group]
        x_spread = max(x_values) - min(x_values)
        y_spread = max(y_values) - min(y_values)
        if x_spread <= tolerance and y_spread > tolerance:
            axis = "x"
            target = sum(x_values) / len(x_values)
        elif y_spread <= tolerance and x_spread > tolerance:
            axis = "y"
            target = sum(y_values) / len(y_values)
        else:
            # Already coincident in both axes, or not a clear row/column.
            continue

        plans: list[tuple[ET.Element, float, float]] = []
        line_deltas: dict[int, list[tuple[ET.Element, int, tuple[float, float]]]] = {}
        safe = True
        for device in group:
            device_id = (device.get("id") or "").strip()
            if not device_id or not lines_by_device.get(device_id):
                safe = False
                break
            current_x, current_y = anchors[id(device)]
            delta = (target - current_x, 0.0) if axis == "x" else (0.0, target - current_y)
            if abs(delta[0]) <= 0.01 and abs(delta[1]) <= 0.01:
                continue
            for line in lines_by_device[device_id]:
                endpoint_refs = _endpoint_references(line)
                candidates = [
                    endpoint
                    for endpoint, refs in endpoint_refs.items()
                    if device_id in refs and len(refs) == 1
                ]
                if len(candidates) != 1:
                    safe = False
                    break
                line_deltas.setdefault(id(line), []).append((line, candidates[0], delta))
            if not safe:
                break
            plans.append((device, delta[0], delta[1]))
        if not safe or not plans:
            continue

        planned_boxes: dict[int, tuple[float, float, float, float]] = {}
        for device, dx, dy in plans:
            old_box = boxes[id(device)]
            if old_box is None:
                safe = False
                break
            planned_boxes[id(device)] = (
                old_box[0] + dx, old_box[1] + dy,
                old_box[2] + dx, old_box[3] + dy,
            )
        if not safe:
            continue
        planned_values = list(planned_boxes.values())
        if any(
            _boxes_overlap(first, second)
            for index, first in enumerate(planned_values)
            for second in planned_values[index + 1:]
        ):
            result.issues.append(OrthogonalizationIssue(
                element_id=", ".join((device.get("id") or "").strip() for device in group),
                element_type=local_name(group[0].tag),
                reason="同类设备对齐后会互相重叠，保守跳过该组。",
            ))
            continue
        for device in devices:
            if id(device) in planned_boxes:
                continue
            other_box = _box(device)
            if other_box is None:
                continue
            if any(_boxes_overlap(new_box, other_box) for new_box in planned_boxes.values()):
                safe = False
                break
        if not safe:
            result.issues.append(OrthogonalizationIssue(
                element_id=", ".join((device.get("id") or "").strip() for device in group),
                element_type=local_name(group[0].tag),
                reason="同类设备对齐后会与其他设备重叠，保守跳过该组。",
            ))
            continue

        for device, dx, dy in plans:
            device.set("x", _format((_number(device.get("x")) or 0.0) + dx))
            device.set("y", _format((_number(device.get("y")) or 0.0) + dy))
            device_id = (device.get("id") or "").strip()
            result.aligned_devices += 1
            if device_id:
                result.aligned_device_ids.append(device_id)
        for updates in line_deltas.values():
            changed_line = False
            for line, endpoint, delta in updates:
                changed_line = _move_line_endpoint(line, endpoint, delta) or changed_line
            if changed_line:
                result.aligned_lines += 1
        claimed_device_ids.update(group_ids)


def _align_mixed_device_connection_points(
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    result: OrthogonalizationResult,
    *,
    endpoint_tolerance: float,
    axis_tolerance: float,
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
    geometry_templates: dict[str, list[dict[str, object]]] | None,
    max_device_shift: float = 160.0,
) -> None:
    """Align explicit endpoints for unlike devices without moving network hubs.

    A diagonal two-device connection is made straight by moving only a leaf
    device (degree one) along the minor axis.  Multi-connected devices are not
    moved by this fallback: their line is handled by the obstacle-aware elbow
    pass instead.  This keeps a common junction stable while still correcting
    the common end-device case shown in field drawings.
    """
    devices = {
        (element.get("id") or "").strip(): element
        for element in _device_elements(elements)
        if (element.get("id") or "").strip()
    }
    connections = _device_connections(elements, line_elements)
    degree = {device_id: len(items) for device_id, items in connections.items()}
    moved_devices: set[str] = set()

    for line in line_elements:
        points = _points(line)
        if points is None or len(points) != 2:
            continue
        endpoint_refs = _endpoint_references(line)
        if any(len(endpoint_refs[index]) != 1 for index in (0, 1)):
            continue
        device_ids = [next(iter(endpoint_refs[index])) for index in (0, 1)]
        if device_ids[0] == device_ids[1] or any(device_id not in devices for device_id in device_ids):
            continue
        if device_ids[0] in moved_devices or device_ids[1] in moved_devices:
            continue
        if abs(points[0][0] - points[1][0]) <= axis_tolerance or abs(points[0][1] - points[1][1]) <= axis_tolerance:
            continue

        endpoint_distances = []
        for index, device_id in enumerate(device_ids):
            box = _box(devices[device_id])
            if box is None:
                endpoint_distances.append(float("inf"))
            else:
                endpoint_distances.append(_point_to_box_distance(points[index], box))
        if any(distance > endpoint_tolerance for distance in endpoint_distances):
            continue

        if geometry_templates is not None:
            trusted = True
            for index, device_id in enumerate(device_ids):
                matching = [
                    connection
                    for connection in connections.get(device_id, [])
                    if connection.line is line and connection.endpoint == index
                ]
                device = devices[device_id]
                if len(matching) != 1 or not _connection_is_trusted(
                    device,
                    matching[0],
                    endpoint_tolerance=endpoint_tolerance,
                    geometry_templates=geometry_templates,
                ):
                    trusted = False
                    break
            if not trusted:
                continue

        # Prefer moving a true leaf.  If both are leaves, move the second
        # endpoint deterministically; if neither is a leaf, preserve the hubs.
        candidates = sorted(
            (0, 1),
            key=lambda index: (degree.get(device_ids[index], 99), index),
        )
        selected_index = candidates[0]
        other_index = 1 - selected_index
        if degree.get(device_ids[selected_index], 99) > 1:
            continue

        selected = points[selected_index]
        other = points[other_index]
        if abs(other[0] - selected[0]) >= abs(other[1] - selected[1]):
            delta = (0.0, other[1] - selected[1])
        else:
            delta = (other[0] - selected[0], 0.0)
        if max(abs(delta[0]), abs(delta[1])) <= axis_tolerance:
            continue
        if max(abs(delta[0]), abs(delta[1])) > max_device_shift:
            result.issues.append(OrthogonalizationIssue(
                element_id=(line.get("id") or "").strip(),
                element_type=local_name(line.tag),
                reason="不同类设备连接点偏差过大，未移动设备，保留线路正交化处理。",
            ))
            continue

        device_id = device_ids[selected_index]
        device = devices[device_id]
        if not _device_shift_is_safe(device, delta, list(devices.values())):
            result.issues.append(OrthogonalizationIssue(
                element_id=(line.get("id") or "").strip(),
                element_type=local_name(line.tag),
                reason="不同类设备按连接点对齐会与其他设备重叠，未移动设备。",
            ))
            continue
        for connection in connections.get(device_id, []):
            shifted = _shifted_points(connection.line, connection.endpoint, delta)
            if shifted is None:
                continue
            if _line_hits_obstacles(
                shifted,
                obstacles,
                _referenced_ids(connection.line),
            ):
                result.issues.append(OrthogonalizationIssue(
                    element_id=(line.get("id") or "").strip(),
                    element_type=local_name(line.tag),
                    reason="不同类设备按连接点对齐后线路会穿过其他设备，保守不移动。",
                ))
                break
        else:
            if not _shift_device_and_connections(device, delta, connections[device_id]):
                continue
            moved_devices.add(device_id)
            result.aligned_devices += 1
            result.aligned_device_ids.append(device_id)
            result.connection_aligned_lines += 1
            result.aligned_lines += 1
            continue


def _rebuild_confirmed_lines(
    elements: list[ET.Element],
    line_elements: list[ET.Element],
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
    result: OrthogonalizationResult,
    *,
    endpoint_tolerance: float,
    axis_tolerance: float,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
) -> set[int]:
    """Re-route two-ended lines only when both endpoint device identities are explicit."""
    protected_lines: set[int] = set()
    devices = {
        (element.get("id") or "").strip(): element
        for element in _device_elements(elements)
        if (element.get("id") or "").strip()
    }
    for line in line_elements:
        original = _points(line)
        if original is None or len(original) != 2:
            continue
        endpoint_refs = _endpoint_references(line)
        if any(len(endpoint_refs[index]) != 1 for index in (0, 1)):
            continue
        device_ids = [next(iter(endpoint_refs[index])) for index in (0, 1)]
        if device_ids[0] == device_ids[1] or any(device_id not in devices for device_id in device_ids):
            continue
        targets: list[tuple[float, float]] = []
        safe = True
        for index, device_id in enumerate(device_ids):
            box = _box(devices[device_id])
            if box is None:
                safe = False
                break
            device = devices[device_id]
            endpoint_connection = [
                connection
                for connection in _device_connections(elements, [line]).get(device_id, [])
                if connection.endpoint == index
            ]
            target: tuple[float, float]
            if geometry_templates is not None:
                if len(endpoint_connection) != 1:
                    safe = False
                    break
                standard_pin = _standard_pin_for_connection(
                    device, endpoint_connection[0], geometry_templates
                )
                if standard_pin is None:
                    safe = False
                    break
                distance = math.hypot(
                    original[index][0] - standard_pin[0],
                    original[index][1] - standard_pin[1],
                )
                target = standard_pin
            else:
                target, distance = _nearest_box_boundary(original[index], box)
            if distance > endpoint_tolerance:
                safe = False
                break
            targets.append(target)
        if not safe:
            continue
        usable_obstacles = [item for item in obstacles if item[0] not in set(device_ids)]
        route = _orthogonal_route(
            targets[0], targets[1], usable_obstacles, axis_tolerance=axis_tolerance
        )
        if route is None:
            protected_lines.add(id(line))
            result.skipped_lines += 1
            result.issues.append(OrthogonalizationIssue(
                element_id=(line.get("id") or "").strip(),
                element_type=local_name(line.tag),
                reason="两端设备身份明确，但重画线路会穿过其他设备，保守保留原线路。",
            ))
            continue
        route_points, _added = route
        if route_points == original:
            continue
        _rewrite_points(line, route_points)
        result.rebuilt_lines += 1
        line_id = (line.get("id") or "").strip()
        if line_id:
            result.rebuilt_line_ids.append(line_id)
    return protected_lines


def _box(element: ET.Element) -> tuple[float, float, float, float] | None:
    x = _number(element.get("x"))
    y = _number(element.get("y"))
    width = _number(element.get("w"))
    height = _number(element.get("h"))
    if None in (x, y, width, height) or width <= 0 or height <= 0:
        return None
    assert x is not None and y is not None and width is not None and height is not None
    return x, y, x + width, y + height


def _segment_hits_box(
    start: tuple[float, float],
    end: tuple[float, float],
    box: tuple[float, float, float, float],
    *,
    clearance: float = 0.5,
) -> bool:
    """Return whether a segment crosses the interior or clearance of a box."""
    x1, y1 = start
    x2, y2 = end
    left, top, right, bottom = box
    left -= clearance
    top -= clearance
    right += clearance
    bottom += clearance
    if abs(y1 - y2) <= 1e-9:
        return top < y1 < bottom and max(min(x1, x2), left) < min(max(x1, x2), right)
    if abs(x1 - x2) <= 1e-9:
        return left < x1 < right and max(min(y1, y2), top) < min(max(y1, y2), bottom)
    # Alignment can temporarily produce a diagonal segment on a multi-connected
    # device.  It still must be checked against obstacles; returning False here
    # would make the line-collision guard ineffective for exactly that case.
    dx = x2 - x1
    dy = y2 - y1
    t_min, t_max = 0.0, 1.0
    for coordinate, delta, lower, upper in (
        (x1, dx, left, right),
        (y1, dy, top, bottom),
    ):
        if abs(delta) <= 1e-12:
            if lower <= coordinate <= upper:
                continue
            return False
        entering = (lower - coordinate) / delta
        leaving = (upper - coordinate) / delta
        if entering > leaving:
            entering, leaving = leaving, entering
        t_min = max(t_min, entering)
        t_max = min(t_max, leaving)
        if t_min > t_max:
            return False
    return t_min < t_max and t_max >= 0.0 and t_min <= 1.0


def _route_hits_obstacle(
    start: tuple[float, float],
    elbow: tuple[float, float],
    end: tuple[float, float],
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
) -> bool:
    return any(
        _segment_hits_box(a, b, box)
        for a, b in ((start, elbow), (elbow, end))
        for _element_id, box in obstacles
    )


def _orthogonal_route(
    start: tuple[float, float],
    end: tuple[float, float],
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
    *,
    axis_tolerance: float,
) -> tuple[list[tuple[float, float]], int] | None:
    dx = abs(end[0] - start[0])
    dy = abs(end[1] - start[1])
    # Tolerance is for matching/alignment, not the final route geometry.
    # Preserve both anchors and add an elbow even for sub-unit offsets.
    if dy <= 1e-9 or dx <= 1e-9:
        return [start, end], 0

    # Keep the dominant direction first.  The alternative is retained for cases
    # where the first elbow would cross a known device body.
    elbows = (
        [(end[0], start[1]), (start[0], end[1])]
        if dx >= dy
        else [(start[0], end[1]), (end[0], start[1])]
    )
    for elbow in elbows:
        if not _route_hits_obstacle(start, elbow, end, obstacles):
            return [start, elbow, end], 1
    return None


def _simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for point in points:
        if result and math.hypot(result[-1][0] - point[0], result[-1][1] - point[1]) <= 1e-9:
            continue
        result.append(point)
        while len(result) >= 3:
            a, b, c = result[-3:]
            if (abs(a[0] - b[0]) <= 1e-9 and abs(b[0] - c[0]) <= 1e-9) or (
                abs(a[1] - b[1]) <= 1e-9 and abs(b[1] - c[1]) <= 1e-9
            ):
                result.pop(-2)
            else:
                break
    return result


def _rewrite_points(element: ET.Element, points: list[tuple[float, float]]) -> None:
    element.set("d", " ".join(f"{_format(x)},{_format(y)}" for x, y in points))
    # Some Bus/BusDis writers also duplicate the endpoints in x1/y1/x2/y2.
    first_x, first_y = points[0]
    last_x, last_y = points[-1]
    for key, value in (
        ("x1", first_x), ("y1", first_y), ("x2", last_x), ("y2", last_y),
    ):
        if element.get(key) is not None:
            element.set(key, _format(value))


def _snapshot_geometry(
    elements: list[ET.Element],
    line_elements: list[ET.Element],
) -> dict[int, tuple[ET.Element, dict[str, str | None]]]:
    snapshot: dict[int, tuple[ET.Element, dict[str, str | None]]] = {}
    for element in _device_elements(elements):
        snapshot[id(element)] = (element, {key: element.get(key) for key in ("x", "y")})
    for line in line_elements:
        snapshot[id(line)] = (
            line,
            {key: line.get(key) for key in ("d", "x1", "y1", "x2", "y2")},
        )
    return snapshot


def _restore_geometry(
    snapshot: dict[int, tuple[ET.Element, dict[str, str | None]]],
) -> None:
    for element, attributes in snapshot.values():
        for key, value in attributes.items():
            if value is None:
                element.attrib.pop(key, None)
            else:
                element.set(key, value)


def _rollback_unsafe_alignment(
    line_elements: list[ET.Element],
    snapshot: dict[int, tuple[ET.Element, dict[str, str | None]]],
    result: OrthogonalizationResult,
    *,
    aligned_devices: int,
    aligned_lines: int,
    connection_aligned_lines: int,
    aligned_device_ids: int,
    obstacles: list[tuple[str, tuple[float, float, float, float]]],
) -> None:
    invalid_lines: list[ET.Element] = []
    for line in line_elements:
        before = snapshot.get(id(line))
        if before is None:
            continue
        old_attributes = before[1]
        if all(line.get(key) == value for key, value in old_attributes.items()):
            continue
        points = _points(line)
        if points is not None and _line_hits_obstacles(
            points,
            obstacles,
            _referenced_ids(line),
        ):
            invalid_lines.append(line)
    if not invalid_lines:
        return

    _restore_geometry(snapshot)
    result.aligned_devices = aligned_devices
    result.aligned_lines = aligned_lines
    result.connection_aligned_lines = connection_aligned_lines
    del result.aligned_device_ids[aligned_device_ids:]
    result.issues.extend(
        OrthogonalizationIssue(
            element_id=(line.get("id") or "").strip(),
            element_type=local_name(line.tag),
            reason="设备对齐后的线路会穿过其他设备，已回滚本次设备/线路对齐。",
        )
        for line in invalid_lines
    )


def _align_inline_switches(tree: ET.ElementTree, result: OrthogonalizationResult, *, tolerance: float) -> None:
    """Flatten small steps on an explicitly connected two-pin inline switch.

    Both far junctions must already share an exact axis. Never move those
    junctions, cabinet equipment, branched device pins, or unrelated crossings.
    """
    elements = list(tree.getroot().iter())
    lines = [e for e in elements if local_name(e.tag) in {"ConnectLine", "FeedLine"} and _points(e)]
    connections = _device_connections(elements, lines)
    rectangles = [_box(e) for e in elements if local_name(e.tag) == "rect" and _box(e)]
    for device in _device_elements(elements):
        if local_name(device.tag) != "CBreakerDis":
            continue
        device_id = device.get("id", "")
        attached = connections.get(device_id, [])
        if len(attached) != 2 or len({id(c.line) for c in attached}) != 2 or len({c.pin for c in attached}) != 2:
            continue
        box = _box(device)
        if any(r[0] <= box[0] and r[1] <= box[1] and r[2] >= box[2] and r[3] >= box[3] for r in rectangles):
            continue
        paths = [_points(c.line) for c in attached]
        near = [p[0] if c.endpoint == 0 else p[-1] for c,p in zip(attached,paths)]
        far = [p[-1] if c.endpoint == 0 else p[0] for c,p in zip(attached,paths)]
        axis = next((a for a in (0,1) if abs(near[0][a]-near[1][a]) < 1e-6 and abs(far[0][a]-far[1][a]) < 1e-6 and abs(near[0][1-a]-near[1][1-a]) > 1), None)
        if axis is None:
            continue
        target = far[0][axis]
        shift = target-near[0][axis]
        if abs(shift) <= 1e-6 or abs(shift) > tolerance:
            continue
        # The two runs must leave opposite sides, with no meaningful detour.
        if (far[0][1-axis]-near[0][1-axis])*(far[1][1-axis]-near[1][1-axis]) >= 0:
            continue
        if any(abs(p[axis]-target) > tolerance for path in paths for p in path):
            continue
        if any(any(p[1-axis] < min(path[0][1-axis],path[-1][1-axis])-1e-6 or p[1-axis] > max(path[0][1-axis],path[-1][1-axis])+1e-6 for p in path) for path in paths):
            continue
        if any(_endpoint_references(c.line)[c.endpoint] != {device_id} for c in attached):
            continue
        # An intermediate point shared with another line is a junction, not an elbow.
        interior = {p for path in paths for p in path[1:-1]}
        if any(p in interior for line in lines if all(line is not c.line for c in attached) for p in (_points(line) or [])):
            continue
        proposals = []
        for c, path in zip(attached, paths):
            points = list(path)
            index = 0 if c.endpoint == 0 else -1
            p = list(points[index]); p[axis] = target; points[index] = tuple(p)
            proposals.append([points[0],points[-1]])
        obstacles = _build_obstacles(elements)
        if any(_line_hits_obstacles(path, obstacles, _referenced_ids(c.line) | {device_id}) for c,path in zip(attached, proposals)):
            continue
        moved_box = list(box); moved_box[axis] += shift; moved_box[axis+2] += shift
        if any(oid != device_id and min(moved_box[2], b[2]) > max(moved_box[0], b[0]) and min(moved_box[3], b[3]) > max(moved_box[1], b[1]) for oid,b in obstacles):
            continue
        key = "x" if axis == 0 else "y"
        device.set(key, _format(float(device.get(key))+shift))
        result.aligned_devices += 1
        result.aligned_device_ids.append(device_id)
        for c,path in zip(attached,proposals):
            _rewrite_points(c.line,path)
            result.changed_lines += 1
            result.changed_line_ids.append(c.line.get("id", ""))


def orthogonalize_tree(
    tree: ET.ElementTree,
    *,
    axis_tolerance: float = 0.5,
    device_align_tolerance: float = 8.0,
    endpoint_tolerance: float = 18.0,
    geometry_templates: dict[str, list[dict[str, object]]] | None = None,
) -> OrthogonalizationResult:
    """Align repeated devices and safely normalize electrical line routes.

    Repeated same-standard devices are aligned only when they clearly form a
    row or column and every affected line endpoint identifies that device;
    the actual line endpoints are used as the alignment anchors.  A diagonal
    line between unlike devices may move only a small, unambiguous leaf device
    so its real connection point shares an axis with the other endpoint.
    Confirmed two-ended lines are then re-routed in place to the ACTIVE/GLOBAL
    standard Pin coordinates when available, preserving IDs and link/node_area.
    Before alignment, dangling electrical endpoints are also snapped to a unique,
    direction-compatible, unoccupied authoritative Pin within a small safety radius;
    missing reciprocal device/line topology is repaired at the same time. Recognized
    RMU cabinet exits are then aligned as complete outgoing ways (Y1/Y2/Q1/... are
    not hard-coded): reciprocal topology is traced through intermediate ConnectLines
    to the actual LOAD_BREAKER_SWITCH/CIRCUIT_BREAKER outgoing Pin, the whole internal
    corridor is put on that exact Pin axis, and the external ConnectLine/FeedLine is
    lengthened to the same junction rather than moving the RMU. Same-side external
    exits are also normalized to one outward axis.
    Without a standard geometry payload the legacy device-boundary fallback is
    retained.  Remaining diagonal segments become horizontal/vertical elbows.
    Any unsafe route is left unchanged.
    """
    root = tree.getroot()
    all_elements = list(root.iter())
    line_elements = [
        element for element in all_elements
        if local_name(element.tag) in _LINE_TAGS and _points(element) is not None
    ]
    result = OrthogonalizationResult(inspected_lines=len(line_elements))

    # First close small visual gaps to authoritative standard Pins. This pass is
    # intentionally before any device alignment: repaired reciprocal topology then
    # becomes trusted evidence for the alignment/re-route stages below.
    _repair_dangling_endpoints_to_standard_pins(
        all_elements,
        line_elements,
        result,
        geometry_templates=geometry_templates,
        max_snap_distance=max(40.0, endpoint_tolerance),
        axis_tolerance=max(1.5, axis_tolerance),
    )

    # RMU outgoing alignment is topology/geometry driven and applies to every
    # branch crossing a recognized cabinet boundary (Y1/Y2/Y3/Y4/... all alike).
    # It lengthens ConnectLine/FeedLine corridors before generic device alignment,
    # so no RMU equipment has to be moved merely to close or line up its exits.
    _align_rmu_outgoing_lines(
        tree,
        all_elements,
        line_elements,
        result,
        geometry_templates=geometry_templates,
        max_axis_shift=max(12.0, device_align_tolerance),
        max_extension=max(120.0, endpoint_tolerance * 4.0),
    )
    all_elements = list(root.iter())
    line_elements = [
        element for element in all_elements
        if local_name(element.tag) in _LINE_TAGS and _points(element) is not None
    ]

    # Device alignment must happen before route generation so the line follows
    # the final device position.  The endpoint coordinates in d, together with
    # node_area/link endpoint references, are the authoritative topology
    # anchors.  Refresh the element list after every geometry pass because
    # endpoint geometry and obstacle boxes have changed in place.
    alignment_snapshot = _snapshot_geometry(all_elements, line_elements)
    alignment_checkpoint = (
        result.aligned_devices,
        result.aligned_lines,
        result.connection_aligned_lines,
        len(result.aligned_device_ids),
    )
    connections = _device_connections(all_elements, line_elements)
    _align_similar_devices(
        all_elements,
        line_elements,
        result,
        tolerance=device_align_tolerance,
        connections=connections,
        endpoint_tolerance=endpoint_tolerance,
        geometry_templates=geometry_templates,
    )
    all_elements = list(root.iter())
    line_elements = [
        element for element in all_elements
        if local_name(element.tag) in _LINE_TAGS and _points(element) is not None
    ]
    obstacles_before_mixed = _build_obstacles(all_elements)
    _align_mixed_device_connection_points(
        all_elements,
        line_elements,
        result,
        endpoint_tolerance=endpoint_tolerance,
        axis_tolerance=axis_tolerance,
        obstacles=obstacles_before_mixed,
        geometry_templates=geometry_templates,
    )
    all_elements = list(root.iter())
    line_elements = [
        element for element in all_elements
        if local_name(element.tag) in _LINE_TAGS and _points(element) is not None
    ]

    obstacles = _build_obstacles(all_elements)
    _rollback_unsafe_alignment(
        line_elements,
        alignment_snapshot,
        result,
        aligned_devices=alignment_checkpoint[0],
        aligned_lines=alignment_checkpoint[1],
        connection_aligned_lines=alignment_checkpoint[2],
        aligned_device_ids=alignment_checkpoint[3],
        obstacles=obstacles,
    )
    # A rollback restores device positions and line paths, so refresh both the
    # obstacle set and topology view before any confirmed route is regenerated.
    all_elements = list(root.iter())
    line_elements = [
        element for element in all_elements
        if local_name(element.tag) in _LINE_TAGS and _points(element) is not None
    ]
    obstacles = _build_obstacles(all_elements)

    protected_lines = _rebuild_confirmed_lines(
        all_elements,
        line_elements,
        obstacles,
        result,
        endpoint_tolerance=endpoint_tolerance,
        axis_tolerance=axis_tolerance,
        geometry_templates=geometry_templates,
    )
    # Rebuild may have changed a line's path.  The following pass handles any
    # remaining multi-segment or unconfirmed diagonal routes.
    for element in line_elements:
        if id(element) in protected_lines:
            continue
        original = _points(element)
        assert original is not None
        if all(
            abs(a[0] - b[0]) <= 1e-9 or abs(a[1] - b[1]) <= 1e-9
            for a, b in zip(original, original[1:])
        ):
            continue

        referenced = _referenced_ids(element)
        usable_obstacles = [item for item in obstacles if item[0] not in referenced]
        transformed: list[tuple[float, float]] = [original[0]]
        added_segments = 0
        safe = True
        for start, end in zip(original, original[1:]):
            route = _orthogonal_route(
                start,
                end,
                usable_obstacles,
                axis_tolerance=axis_tolerance,
            )
            if route is None:
                safe = False
                break
            route_points, added = route
            transformed.extend(route_points[1:])
            added_segments += added
        if not safe:
            result.skipped_lines += 1
            result.issues.append(OrthogonalizationIssue(
                element_id=(element.get("id") or "").strip(),
                element_type=local_name(element.tag),
                reason="两个横平竖直走线方案都会穿过已识别设备图元，保守跳过。",
            ))
            continue

        transformed = _simplify(transformed)
        if transformed == original:
            continue
        _rewrite_points(element, transformed)
        result.changed_lines += 1
        result.changed_segments += added_segments
        element_id = (element.get("id") or "").strip()
        if element_id:
            result.changed_line_ids.append(element_id)

    # Generic device/route cleanup above can legitimately rewrite a neighbouring
    # ConnectLine after the first RMU pass.  RMU exits have a stricter contract:
    # the cabinet-boundary line, every middle ConnectLine, and the real
    # LOAD_BREAKER_SWITCH/CIRCUIT_BREAKER outgoing Pin must finish on one exact
    # axis.  Run the RMU pass once more as the final geometry operation so a 1-unit
    # historical kink cannot reappear in the saved file.  The pass is idempotent;
    # already-correct corridors are untouched.
    final_elements = list(root.iter())
    final_line_elements = [
        element for element in final_elements
        if local_name(element.tag) in _LINE_TAGS and _points(element) is not None
    ]
    _align_rmu_outgoing_lines(
        tree,
        final_elements,
        final_line_elements,
        result,
        geometry_templates=geometry_templates,
        max_axis_shift=max(12.0, device_align_tolerance),
        max_extension=max(120.0, endpoint_tolerance * 4.0),
    )

    _align_inline_switches(tree, result, tolerance=min(8.0, device_align_tolerance))

    return result
