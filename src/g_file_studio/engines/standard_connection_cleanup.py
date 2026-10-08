from __future__ import annotations

import math
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from g_file_studio.engines.id_engine import local_name


@dataclass
class ConnectionCleanupIssue:
    issue_type: str
    element_id: str = ""
    line_id: str = ""
    reason: str = ""
    current: str = ""
    expected: str = ""


@dataclass
class ConnectionCleanupResult:
    removed_redundant_lines: int = 0
    straightened_lines: int = 0
    moved_devices: int = 0
    connected_endpoints: int = 0
    repaired_topology_links: int = 0
    removed_line_ids: list[str] = field(default_factory=list)
    straightened_line_ids: list[str] = field(default_factory=list)
    moved_device_ids: list[str] = field(default_factory=list)
    issues: list[ConnectionCleanupIssue] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(
            self.removed_redundant_lines
            or self.straightened_lines
            or self.moved_devices
            or self.connected_endpoints
            or self.repaired_topology_links
        )


@dataclass(frozen=True)
class _PinConnection:
    port_index: int
    pin: tuple[float, float]
    line: ET.Element
    endpoint_index: int
    snap_distance: float = 0.0


@dataclass(frozen=True)
class _ThroughLineProof:
    line: ET.Element
    device: ET.Element
    pin_connections: tuple[_PinConnection, ...] = ()
    proof: str = "legacy"


def _rotation(element: ET.Element) -> int:
    raw = (element.get("rotate") or "").strip()
    if raw:
        try:
            return int(round(float(raw))) % 360
        except ValueError:
            pass
    raw_tfr = element.get("tfr") or ""
    import re
    match = re.search(r"rotate\(\s*([-+]?\d+(?:\.\d+)?)", raw_tfr)
    if match:
        try:
            return int(round(float(match.group(1)))) % 360
        except ValueError:
            pass
    return 0


def _authoritative_pin_points(
    device: ET.Element,
    geometry_templates: dict[str, list[dict[str, object]]] | None,
    *,
    dimension_tolerance: float = 3.0,
) -> tuple[tuple[int, tuple[float, float]], ...]:
    """Resolve standard pin coordinates in drawing space for one placed device.

    The geometry payload comes from the ACTIVE/GLOBAL symbol standard.  We only use
    it when the placed symbol already matches the authoritative width/height closely;
    this prevents a stale/mismatched icon from teaching topology repair.
    """
    if not geometry_templates:
        return ()
    devref = (device.get("devref") or "").strip()
    rows = geometry_templates.get(devref) or []
    if not isinstance(rows, list):
        return ()
    rotation = _rotation(device)
    width = _number(device.get("w"))
    height = _number(device.get("h"))
    x = _number(device.get("x"))
    y = _number(device.get("y"))
    candidates: list[tuple[float, dict[str, object]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            row_rotation = int(row.get("rotation", 0)) % 360
            row_width = float(row.get("width", width) or width)
            row_height = float(row.get("height", height) or height)
        except (TypeError, ValueError):
            continue
        if row_rotation != rotation:
            continue
        offsets = row.get("anchor_offsets", [])
        if not isinstance(offsets, list) or not offsets:
            continue
        delta = abs(row_width - width) + abs(row_height - height)
        candidates.append((delta, row))
    if not candidates:
        return ()
    delta, selected = min(candidates, key=lambda item: item[0])
    if delta > dimension_tolerance * 2:
        return ()
    result: list[tuple[int, tuple[float, float]]] = []
    for index, pair in enumerate(selected.get("anchor_offsets", [])):
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            return ()
        try:
            px = x + float(pair[0])
            py = y + float(pair[1])
        except (TypeError, ValueError):
            return ()
        result.append((index, (px, py)))
    return tuple(result)


def _append_reference_token(
    element: ET.Element,
    key: str,
    own_index: int,
    other_index: int,
    other_id: str,
) -> bool:
    if not other_id:
        return False
    token = f"{own_index},{other_index},{other_id}"
    raw = element.get(key) or ""
    tokens = [item.strip() for item in raw.split(";") if item.strip()]
    for existing in tokens:
        parts = [part.strip() for part in existing.split(",")]
        if len(parts) >= 3 and parts[2] == other_id:
            # Existing topology to the same element wins; do not duplicate it just
            # because historical endpoint indices differ in old drawings.
            return False
    tokens.append(token)
    element.set(key, ";".join(tokens))
    return True


def _ensure_device_line_reciprocal(
    device: ET.Element,
    line: ET.Element,
    *,
    port_index: int,
    line_endpoint_index: int,
) -> int:
    device_id = (device.get("id") or "").strip()
    line_id = (line.get("id") or "").strip()
    if not device_id or not line_id:
        return 0
    changed = 0
    if _append_reference_token(device, "node_area", port_index, line_endpoint_index, line_id):
        changed += 1
    # Devices in production G files normally use node_area only.  If a particular
    # device already carries link, keep the two attributes synchronized.
    if device.get("link") is not None and _append_reference_token(
        device, "link", port_index, line_endpoint_index, line_id
    ):
        changed += 1
    if _append_reference_token(line, "node_area", line_endpoint_index, port_index, device_id):
        changed += 1
    if _append_reference_token(line, "link", line_endpoint_index, port_index, device_id):
        changed += 1
    return changed


def _pin_axis(device: ET.Element, pin: tuple[float, float]) -> str:
    box = _box(device)
    if box is None:
        return ""
    left, top, right, bottom = box
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    return "H" if abs(pin[0] - cx) >= abs(pin[1] - cy) else "V"


def _line_covers_two_pins(
    line: ET.Element,
    first: tuple[float, float],
    second: tuple[float, float],
    *,
    tolerance: float = 1.5,
) -> bool:
    segment = _segment(line)
    if segment is None:
        return False
    orientation = _orientation(segment)
    (x1, y1), (x2, y2) = segment
    if orientation == "H":
        if abs(first[1] - second[1]) > tolerance:
            return False
        y = (y1 + y2) / 2.0
        if abs(y - first[1]) > tolerance or abs(y - second[1]) > tolerance:
            return False
        lo, hi = sorted((x1, x2))
        pin_lo, pin_hi = sorted((first[0], second[0]))
        return lo < pin_lo - tolerance and hi > pin_hi + tolerance
    if orientation == "V":
        if abs(first[0] - second[0]) > tolerance:
            return False
        x = (x1 + x2) / 2.0
        if abs(x - first[0]) > tolerance or abs(x - second[0]) > tolerance:
            return False
        lo, hi = sorted((y1, y2))
        pin_lo, pin_hi = sorted((first[1], second[1]))
        return lo < pin_lo - tolerance and hi > pin_hi + tolerance
    return False


def _side_line_for_pin(
    lines: list[ET.Element],
    *,
    through: ET.Element,
    device: ET.Element,
    pin: tuple[float, float],
    exact_tolerance: float = 1.75,
    max_gap: float = 8.0,
) -> tuple[ET.Element, int, float] | None:
    """Find one line endpoint that is (or can safely be snapped) to a standard pin."""
    axis = _pin_axis(device, pin)
    box = _box(device)
    if not axis or box is None:
        return None
    left, top, right, bottom = box
    cx = (left + right) / 2.0
    cy = (top + bottom) / 2.0
    candidates: list[tuple[float, ET.Element, int]] = []
    for line in lines:
        if line is through:
            continue
        endpoints = _endpoints(line)
        if endpoints is None:
            continue
        for endpoint_index, point in enumerate(endpoints):
            if _endpoint_axis(line, endpoint_index) != axis:
                continue
            dx = point[0] - pin[0]
            dy = point[1] - pin[1]
            if axis == "H":
                if abs(dy) > exact_tolerance:
                    continue
                distance = abs(dx)
                # Candidate must approach the pin from outside the device, not from
                # the opposite side through the symbol body.
                if pin[0] < cx and point[0] > pin[0] + exact_tolerance:
                    continue
                if pin[0] > cx and point[0] < pin[0] - exact_tolerance:
                    continue
            else:
                if abs(dx) > exact_tolerance:
                    continue
                distance = abs(dy)
                if pin[1] < cy and point[1] > pin[1] + exact_tolerance:
                    continue
                if pin[1] > cy and point[1] < pin[1] - exact_tolerance:
                    continue
            if distance <= max_gap:
                candidates.append((distance, line, endpoint_index))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], (row[1].get("id") or ""), row[2]))
    best = candidates[0]
    # Do not guess when two different lines are equally plausible for the same pin.
    if len(candidates) > 1 and abs(candidates[1][0] - best[0]) <= 0.25 and candidates[1][1] is not best[1]:
        return None
    return best[1], best[2], best[0]


def _snap_line_endpoint_to_pin(
    line: ET.Element,
    endpoint_index: int,
    pin: tuple[float, float],
) -> bool:
    return _rewrite_polyline_endpoint(line, endpoint_index, pin)


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _box(element: ET.Element) -> tuple[float, float, float, float] | None:
    width = _number(element.get("w"))
    height = _number(element.get("h"))
    if width <= 0 or height <= 0:
        return None
    x = _number(element.get("x"))
    y = _number(element.get("y"))
    return x, y, x + width, y + height


def _points(element: ET.Element) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for token in (element.get("d") or "").replace(";", " ").split():
        if "," not in token:
            continue
        left, right = token.split(",", 1)
        try:
            result.append((float(left), float(right)))
        except ValueError:
            continue
    return result


def _segment(element: ET.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    points = _points(element)
    if len(points) != 2:
        return None
    return points[0], points[1]


def _endpoints(element: ET.Element) -> tuple[tuple[float, float], tuple[float, float]] | None:
    points = _points(element)
    if len(points) < 2:
        return None
    return points[0], points[-1]


def _endpoint_axis(element: ET.Element, endpoint_index: int, tolerance: float = 0.01) -> str:
    points = _points(element)
    if len(points) < 2:
        return ""
    if endpoint_index == 0:
        pair = (points[0], points[1])
    else:
        pair = (points[-2], points[-1])
    return _orientation(pair, tolerance=tolerance)


def _line_like_elements(elements: list[ET.Element]) -> list[ET.Element]:
    return [
        element for element in elements
        if local_name(element.tag) in {"ConnectLine", "FeedLine", "BusDis"}
        and len(_points(element)) >= 2
    ]


def _orientation(segment: tuple[tuple[float, float], tuple[float, float]], tolerance: float = 0.01) -> str:
    (x1, y1), (x2, y2) = segment
    if abs(y1 - y2) <= tolerance:
        return "H"
    if abs(x1 - x2) <= tolerance:
        return "V"
    return "D"


def _line_text(segment: tuple[tuple[float, float], tuple[float, float]]) -> str:
    (x1, y1), (x2, y2) = segment
    return f"({_format_number(x1)},{_format_number(y1)})→({_format_number(x2)},{_format_number(y2)})"


def _distance_point_to_box(point: tuple[float, float], box: tuple[float, float, float, float]) -> float:
    x, y = point
    left, top, right, bottom = box
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    return math.hypot(dx, dy)


def _referenced_ids(element: ET.Element) -> set[str]:
    result: set[str] = set()
    for key in ("node_area", "link"):
        for token in (element.get(key) or "").split(";"):
            parts = [part.strip() for part in token.split(",")]
            if len(parts) >= 3 and parts[2]:
                result.add(parts[2])
    return result


def _remove_reference_ids(root: ET.Element, removed_ids: set[str]) -> None:
    if not removed_ids:
        return
    for element in root.iter():
        for key in ("node_area", "link"):
            raw = element.get(key)
            if raw is None:
                continue
            kept: list[str] = []
            for token in raw.split(";"):
                parts = [part.strip() for part in token.split(",")]
                if len(parts) >= 3 and parts[2] in removed_ids:
                    continue
                if token.strip():
                    kept.append(token.strip())
            element.set(key, ";".join(kept))


def _rewrite_line_geometry(line: ET.Element, start: tuple[float, float], end: tuple[float, float]) -> None:
    x1, y1 = start
    x2, y2 = end
    line.set("d", f"{_format_number(x1)},{_format_number(y1)} {_format_number(x2)},{_format_number(y2)}")
    # ConnectLine bounds in business G files reserve a 3-unit visual margin around
    # the actual segment. Keeping this convention avoids changing hit-test behavior.
    line.set("x", _format_number(min(x1, x2) - 3.0))
    line.set("y", _format_number(min(y1, y2) - 3.0))
    line.set("w", _format_number(abs(x2 - x1) + 6.0))
    line.set("h", _format_number(abs(y2 - y1) + 6.0))


def _rewrite_polyline_endpoint(
    element: ET.Element,
    endpoint_index: int,
    point: tuple[float, float],
) -> bool:
    points = _points(element)
    if len(points) < 2:
        return False
    index = 0 if endpoint_index == 0 else len(points) - 1
    current = points[index]
    if math.hypot(current[0] - point[0], current[1] - point[1]) <= 0.01:
        return False
    points[index] = point
    element.set(
        "d",
        " ".join(f"{_format_number(x)},{_format_number(y)}" for x, y in points),
    )
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    element.set("x", _format_number(min(xs) - 3.0))
    element.set("y", _format_number(min(ys) - 3.0))
    element.set("w", _format_number(max(xs) - min(xs) + 6.0))
    element.set("h", _format_number(max(ys) - min(ys) + 6.0))
    return True


def _eligible_devices(
    elements: list[ET.Element],
    eligible_devrefs: set[str],
) -> list[ET.Element]:
    rows: list[ET.Element] = []
    for element in elements:
        devref = (element.get("devref") or "").strip()
        if not devref or (eligible_devrefs and devref not in eligible_devrefs):
            continue
        if local_name(element.tag) == "ConnectLine" or _box(element) is None:
            continue
        rows.append(element)
    return rows


def _find_redundant_through_lines(
    elements: list[ET.Element],
    devices: list[ET.Element],
    *,
    geometry_templates: dict[str, list[dict[str, object]]] | None = None,
    axis_tolerance: float = 1.25,
    edge_tolerance: float = 18.0,
    pin_gap_tolerance: float = 8.0,
) -> list[_ThroughLineProof]:
    """Find device-through ConnectLines that can be removed without breaking wiring.

    Preferred proof is authoritative standard pin geometry: when a two-pin standard
    device already has one side fragment terminating at each standard pin, a long
    line crossing both pins is a visual/topological bypass and can be removed.  The
    side fragments do *not* need historical reciprocal link/node_area because old
    NON-SMART drawings often omitted those device references; normalization repairs
    them before deleting the bypass.

    When no authoritative pin geometry is available, retain the older conservative
    reciprocal-topology proof for backward compatibility.
    """
    lines = [element for element in elements if local_name(element.tag) == "ConnectLine" and _segment(element)]
    side_elements = _line_like_elements(elements)
    found: list[_ThroughLineProof] = []
    seen_lines: set[int] = set()

    for device in devices:
        # Strong proof: ACTIVE/GLOBAL standard supplies exactly two electrical pins.
        standard_pins = _authoritative_pin_points(device, geometry_templates)
        if len(standard_pins) == 2:
            pin_points = (standard_pins[0][1], standard_pins[1][1])
            for line in lines:
                if id(line) in seen_lines or not _line_covers_two_pins(line, *pin_points):
                    continue
                connections: list[_PinConnection] = []
                used_side_lines: set[int] = set()
                valid = True
                for port_index, pin in standard_pins:
                    side = _side_line_for_pin(
                        side_elements,
                        through=line,
                        device=device,
                        pin=pin,
                        max_gap=pin_gap_tolerance,
                    )
                    if side is None:
                        valid = False
                        break
                    side_line, endpoint_index, snap_distance = side
                    if id(side_line) in used_side_lines:
                        valid = False
                        break
                    used_side_lines.add(id(side_line))
                    connections.append(_PinConnection(
                        port_index=port_index,
                        pin=pin,
                        line=side_line,
                        endpoint_index=endpoint_index,
                        snap_distance=snap_distance,
                    ))
                if valid and len(connections) == 2:
                    found.append(_ThroughLineProof(
                        line=line,
                        device=device,
                        pin_connections=tuple(connections),
                        proof="standard-pins",
                    ))
                    seen_lines.add(id(line))

        # Compatibility proof: if no standard-pin proof claimed a line, preserve the
        # v2.18.136 reciprocal link/node_area rule.
        box = _box(device)
        if box is None:
            continue
        left, top, right, bottom = box
        device_refs = _referenced_ids(device)
        for line in lines:
            if id(line) in seen_lines:
                continue
            line_id = (line.get("id") or "").strip()
            if line_id and line_id in device_refs:
                continue
            segment = _segment(line)
            if segment is None:
                continue
            orientation = _orientation(segment)
            (x1, y1), (x2, y2) = segment
            if orientation == "H":
                y = (y1 + y2) / 2.0
                lo, hi = sorted((x1, x2))
                if not (top - axis_tolerance <= y <= bottom + axis_tolerance):
                    continue
                if not (lo < left - axis_tolerance and hi > right + axis_tolerance):
                    continue
                left_frag: ET.Element | None = None
                right_frag: ET.Element | None = None
                for other in lines:
                    if other is line:
                        continue
                    other_seg = _segment(other)
                    if other_seg is None or _orientation(other_seg) != "H":
                        continue
                    (ox1, oy1), (ox2, oy2) = other_seg
                    if abs(((oy1 + oy2) / 2.0) - y) > axis_tolerance:
                        continue
                    olo, ohi = sorted((ox1, ox2))
                    if abs(olo - lo) <= axis_tolerance and left - edge_tolerance <= ohi <= right + edge_tolerance:
                        left_frag = other
                    if abs(ohi - hi) <= axis_tolerance and left - edge_tolerance <= olo <= right + edge_tolerance:
                        right_frag = other
                if left_frag is not None and right_frag is not None:
                    left_id = (left_frag.get("id") or "").strip()
                    right_id = (right_frag.get("id") or "").strip()
                    device_id = (device.get("id") or "").strip()
                    reciprocal = (
                        left_id in device_refs
                        and right_id in device_refs
                        and device_id in _referenced_ids(left_frag)
                        and device_id in _referenced_ids(right_frag)
                    )
                    if reciprocal:
                        found.append(_ThroughLineProof(line=line, device=device, proof="reciprocal"))
                        seen_lines.add(id(line))
            elif orientation == "V":
                x = (x1 + x2) / 2.0
                lo, hi = sorted((y1, y2))
                if not (left - axis_tolerance <= x <= right + axis_tolerance):
                    continue
                if not (lo < top - axis_tolerance and hi > bottom + axis_tolerance):
                    continue
                top_frag: ET.Element | None = None
                bottom_frag: ET.Element | None = None
                for other in lines:
                    if other is line:
                        continue
                    other_seg = _segment(other)
                    if other_seg is None or _orientation(other_seg) != "V":
                        continue
                    (ox1, oy1), (ox2, oy2) = other_seg
                    if abs(((ox1 + ox2) / 2.0) - x) > axis_tolerance:
                        continue
                    olo, ohi = sorted((oy1, oy2))
                    if abs(olo - lo) <= axis_tolerance and top - edge_tolerance <= ohi <= bottom + edge_tolerance:
                        top_frag = other
                    if abs(ohi - hi) <= axis_tolerance and top - edge_tolerance <= olo <= bottom + edge_tolerance:
                        bottom_frag = other
                if top_frag is not None and bottom_frag is not None:
                    top_id = (top_frag.get("id") or "").strip()
                    bottom_id = (bottom_frag.get("id") or "").strip()
                    device_id = (device.get("id") or "").strip()
                    reciprocal = (
                        top_id in device_refs
                        and bottom_id in device_refs
                        and device_id in _referenced_ids(top_frag)
                        and device_id in _referenced_ids(bottom_frag)
                    )
                    if reciprocal:
                        found.append(_ThroughLineProof(line=line, device=device, proof="reciprocal"))
                        seen_lines.add(id(line))
    return found

def inspect_standard_device_connections(
    tree: ET.ElementTree,
    *,
    eligible_devrefs: Iterable[str],
    single_pin_devrefs: Iterable[str] = (),
    geometry_templates: dict[str, list[dict[str, object]]] | None = None,
    max_snap_offset: float = 8.0,
) -> ConnectionCleanupResult:
    root = tree.getroot()
    elements = list(root.iter())
    eligible = {str(value).strip() for value in eligible_devrefs if str(value).strip()}
    single_pin = {str(value).strip() for value in single_pin_devrefs if str(value).strip()}
    devices = _eligible_devices(elements, eligible)
    result = ConnectionCleanupResult()

    for proof in _find_redundant_through_lines(
        elements,
        devices,
        geometry_templates=geometry_templates,
        pin_gap_tolerance=max_snap_offset,
    ):
        line = proof.line
        device = proof.device
        segment = _segment(line)
        if proof.proof == "standard-pins":
            reason = "ACTIVE/GLOBAL 标准确认该设备有两个电气 Pin，且两侧连接线已分别到达对应 Pin；当前长 ConnectLine 仍跨越两个 Pin，属于旁路贯穿线。"
        else:
            reason = "设备两侧已经存在双向拓扑确认的独立连接线，但仍有一条长 ConnectLine 直接贯穿设备图元。"
        result.issues.append(ConnectionCleanupIssue(
            issue_type="重复贯穿连接线",
            element_id=(device.get("id") or "").strip(),
            line_id=(line.get("id") or "").strip(),
            reason=reason,
            current=_line_text(segment) if segment else "",
            expected="删除贯穿线，由设备两侧 Pin 连接线承载真实拓扑",
        ))
        for connection in proof.pin_connections:
            if connection.snap_distance > 0.01:
                result.issues.append(ConnectionCleanupIssue(
                    issue_type="设备连接端点未到Pin",
                    element_id=(device.get("id") or "").strip(),
                    line_id=(connection.line.get("id") or "").strip(),
                    reason=f"连接线端点距离标准 Pin {connection.snap_distance:g}，可在安全阈值内自动吸附。",
                    current=_line_text(_segment(connection.line)) if _segment(connection.line) else "",
                    expected=f"端点吸附到 ({_format_number(connection.pin[0])},{_format_number(connection.pin[1])})",
                ))

    if single_pin:
        lines = [element for element in elements if local_name(element.tag) == "ConnectLine" and _segment(element)]
        for device in devices:
            devref = (device.get("devref") or "").strip()
            if devref not in single_pin:
                continue
            box = _box(device)
            if box is None:
                continue
            candidates: list[tuple[float, ET.Element, int]] = []
            for line in lines:
                segment = _segment(line)
                if segment is None or _orientation(segment) != "D":
                    continue
                for endpoint_index, point in enumerate(segment):
                    distance = _distance_point_to_box(point, box)
                    if distance <= 1.5:
                        candidates.append((distance, line, endpoint_index))
            if len(candidates) != 1:
                continue
            _distance, line, endpoint_index = candidates[0]
            segment = _segment(line)
            assert segment is not None
            near = segment[endpoint_index]
            far = segment[1 - endpoint_index]
            dx = abs(near[0] - far[0])
            dy = abs(near[1] - far[1])
            minor = min(dx, dy)
            if minor <= 0.01 or minor > max_snap_offset:
                continue
            if dx >= dy:
                snapped = (near[0], far[1])
                orientation = "水平"
            else:
                snapped = (far[0], near[1])
                orientation = "垂直"
            result.issues.append(ConnectionCleanupIssue(
                issue_type="设备连接线非正交",
                element_id=(device.get("id") or "").strip(),
                line_id=(line.get("id") or "").strip(),
                reason=f"单连接点设备的连接线接近{orientation}，偏移 {minor:g}，可安全吸附为{orientation}。",
                current=_line_text(segment),
                expected=_line_text((snapped, far) if endpoint_index == 0 else (far, snapped)),
            ))
    return result

def normalize_standard_device_connections(
    tree: ET.ElementTree,
    *,
    eligible_devrefs: Iterable[str],
    single_pin_devrefs: Iterable[str] = (),
    geometry_templates: dict[str, list[dict[str, object]]] | None = None,
    max_snap_offset: float = 8.0,
) -> ConnectionCleanupResult:
    """Normalize connection geometry using authoritative standard-device pins.

    Two-pin devices are treated as real electrical interruptions, not decorative
    overlays. If a long ConnectLine bypasses both standard pins while two side
    fragments already approach those pins, the side fragments are snapped to the
    exact pin coordinates, missing reciprocal link/node_area references are repaired,
    and only then is the bypass line removed. This keeps both the visual drawing and
    the XML topology connected.

    One-pin devices retain the existing small-skew orthogonal snap behaviour.
    Ambiguous/missing evidence is never guessed.
    """
    root = tree.getroot()
    elements = list(root.iter())
    eligible = {str(value).strip() for value in eligible_devrefs if str(value).strip()}
    single_pin = {str(value).strip() for value in single_pin_devrefs if str(value).strip()}
    devices = _eligible_devices(elements, eligible)
    result = ConnectionCleanupResult()

    redundant = _find_redundant_through_lines(
        elements,
        devices,
        geometry_templates=geometry_templates,
        pin_gap_tolerance=max_snap_offset,
    )
    removed_ids: set[str] = set()
    parent_by_child = {child: parent for parent in root.iter() for child in list(parent)}
    for proof in redundant:
        line = proof.line
        device = proof.device
        line_id = (line.get("id") or "").strip()
        segment = _segment(line)

        if proof.pin_connections:
            for connection in proof.pin_connections:
                if _snap_line_endpoint_to_pin(
                    connection.line,
                    connection.endpoint_index,
                    connection.pin,
                ):
                    result.connected_endpoints += 1
                result.repaired_topology_links += _ensure_device_line_reciprocal(
                    device,
                    connection.line,
                    port_index=connection.port_index,
                    line_endpoint_index=connection.endpoint_index,
                )
            reason = (
                "标准双 Pin 已确认：两侧连接线已吸附到设备 Pin，并补齐 reciprocal "
                "link/node_area；随后删除绕过设备的贯穿 ConnectLine。"
            )
        else:
            reason = "设备两侧已有双向拓扑确认的独立连接线，删除直接贯穿设备的重复 ConnectLine。"

        result.issues.append(ConnectionCleanupIssue(
            issue_type="重复贯穿连接线",
            element_id=(device.get("id") or "").strip(),
            line_id=line_id,
            reason=reason,
            current=_line_text(segment) if segment else "",
            expected="删除贯穿线并由设备 Pin 承载连接",
        ))
        parent = parent_by_child.get(line)
        if parent is None:
            continue
        parent.remove(line)
        if line_id:
            removed_ids.add(line_id)
            result.removed_line_ids.append(line_id)
        result.removed_redundant_lines += 1
    _remove_reference_ids(root, removed_ids)

    # Rebuild after deletion so removed bypass segments cannot participate in the
    # one-pin orthogonal correction pass.
    elements = list(root.iter())
    devices = _eligible_devices(elements, eligible)
    if single_pin:
        lines = [element for element in elements if local_name(element.tag) == "ConnectLine" and _segment(element)]
        for device in devices:
            devref = (device.get("devref") or "").strip()
            if devref not in single_pin:
                continue
            box = _box(device)
            if box is None:
                continue
            candidates: list[tuple[float, ET.Element, int]] = []
            for line in lines:
                segment = _segment(line)
                if segment is None or _orientation(segment) != "D":
                    continue
                for endpoint_index, point in enumerate(segment):
                    distance = _distance_point_to_box(point, box)
                    if distance <= 1.5:
                        candidates.append((distance, line, endpoint_index))
            if len(candidates) != 1:
                continue
            _distance, line, endpoint_index = candidates[0]
            segment = _segment(line)
            if segment is None:
                continue
            near = segment[endpoint_index]
            far = segment[1 - endpoint_index]
            dx = abs(near[0] - far[0])
            dy = abs(near[1] - far[1])
            minor = min(dx, dy)
            if minor <= 0.01 or minor > max_snap_offset:
                continue
            if dx >= dy:
                snapped = (near[0], far[1])
            else:
                snapped = (far[0], near[1])
            delta_x = snapped[0] - near[0]
            delta_y = snapped[1] - near[1]
            if endpoint_index == 0:
                _rewrite_line_geometry(line, snapped, far)
            else:
                _rewrite_line_geometry(line, far, snapped)
            device.set("x", _format_number(_number(device.get("x")) + delta_x))
            device.set("y", _format_number(_number(device.get("y")) + delta_y))
            line_id = (line.get("id") or "").strip()
            device_id = (device.get("id") or "").strip()
            result.straightened_lines += 1
            result.moved_devices += 1
            if line_id:
                result.straightened_line_ids.append(line_id)
            if device_id:
                result.moved_device_ids.append(device_id)
            result.issues.append(ConnectionCleanupIssue(
                issue_type="设备连接线正交修复",
                element_id=device_id,
                line_id=line_id,
                reason="单连接点标准设备的轻微斜线已吸附为水平/垂直，并同步平移设备保持连接点相对关系。",
                current=_line_text(segment),
                expected=_line_text(_segment(line)) if _segment(line) else "",
            ))
    return result

def normalize_standard_device_connections_file(
    source_path: Path,
    output_path: Path,
    *,
    eligible_devrefs: Iterable[str],
    single_pin_devrefs: Iterable[str] = (),
    geometry_templates: dict[str, list[dict[str, object]]] | None = None,
    max_snap_offset: float = 8.0,
) -> ConnectionCleanupResult:
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.parse(source_path)
    result = normalize_standard_device_connections(
        tree,
        eligible_devrefs=eligible_devrefs,
        single_pin_devrefs=single_pin_devrefs,
        geometry_templates=geometry_templates,
        max_snap_offset=max_snap_offset,
    )
    if result.changed:
        if hasattr(ET, "indent"):
            ET.indent(tree, space="    ")
        tmp = output_path.with_name(output_path.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        ET.parse(tmp)
        os.replace(tmp, output_path)
    elif source_path.resolve() != output_path.resolve():
        shutil.copy2(source_path, output_path)
    return result
