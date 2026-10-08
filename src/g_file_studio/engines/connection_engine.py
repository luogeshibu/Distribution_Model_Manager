from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


LINE_TAGS = {"ConnectLine", "FeedLine"}
CONDUCTOR_TAGS = {"BusDis", "Bus"}
NON_CONNECTABLE_TAGS = {
    "Merge",
    "rect",
    "Text",
    "DText",
    "Status",
    "pwbh",
    "Item",
    "Color",
    "Font",
    "Theme",
}
KNOWN_DEVICE_TAGS = {
    "CBreaker",
    "CBreakerDis",
    "Disconnector",
    "GroundDisconnector",
    "ZhaiWaiJieDiDaoZha",
    "EnergyConsumer",
    "Transformer",
    "Transformer2",
    "Fuse",
    "LoadBreakSwitch",
}
POINT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass
class LineInfo:
    element: ET.Element
    element_id: str
    tag: str
    points: list[Point]

    @property
    def endpoints(self) -> tuple[Point, Point]:
        return self.points[0], self.points[-1]


@dataclass
class DeviceInfo:
    element: ET.Element
    element_id: str
    tag: str
    left: float
    top: float
    right: float
    bottom: float
    x: float
    y: float
    width: float
    height: float
    rotation: int
    devref: str

    @property
    def signature(self) -> tuple[str, str, int, float, float]:
        """Exact icon family used for learning ports.

        Width/height are part of the signature because the same ``tag``/``devref`` may occur with
        different icon templates. Mixing those templates was one source of wrong port numbers in
        v2.16.0.
        """
        return (
            self.tag,
            self.devref,
            self.rotation,
            round(abs(self.width), 3),
            round(abs(self.height), 3),
        )


@dataclass(frozen=True)
class PortAnchor:
    x_offset: float
    y_offset: float
    port_index: int


@dataclass
class ConnectionRepairResult:
    input_path: Path
    direct_element_count: int = 0
    line_count: int = 0
    conductor_count: int = 0
    device_count: int = 0
    aligned_device_count: int = 0
    aligned_device_ids: list[str] = field(default_factory=list)
    adjusted_line_endpoint_count: int = 0
    adjusted_line_ids: list[str] = field(default_factory=list)
    inferred_relation_count: int = 0
    added_reference_count: int = 0
    updated_reference_count: int = 0
    removed_reference_count: int = 0
    changed_element_count: int = 0
    changed_attribute_count: int = 0
    changed_element_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# These templates are verified against the user's manually aligned reference G files.
# Offsets are relative to the element's x/y and describe the real icon ports, not the XML bbox edge.
_BUILTIN_PORTS: dict[tuple[str, int], tuple[PortAnchor, ...]] = {
    ("circuit_breaker", 270): (
        PortAnchor(6.0, 12.0, 0),
        PortAnchor(26.0, 12.0, 1),
    ),
    ("load_breaker", 270): (
        PortAnchor(4.0, 15.0, 0),
        PortAnchor(24.0, 15.0, 1),
    ),
    ("external_ground", 90): (PortAnchor(15.0, 26.0, 0),),
    ("external_ground", 270): (PortAnchor(15.0, 2.0, 0),),
}


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _layer(root: ET.Element) -> ET.Element:
    for child in list(root):
        if _local_name(child.tag) == "Layer":
            return child
    raise ValueError("G 文件缺少直属 <Layer> 元素。")


def _number(value: str | None) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _round_half_up(value: float) -> float:
    if value >= 0:
        return float(math.floor(value + 0.5))
    return float(math.ceil(value - 0.5))


def _path_points(element: ET.Element) -> list[Point]:
    raw = (element.get("d") or "").strip()
    values = [float(value) for value in POINT_RE.findall(raw)]
    if len(values) >= 4 and len(values) % 2 == 0:
        return [Point(values[index], values[index + 1]) for index in range(0, len(values), 2)]

    x1 = _number(element.get("x1"))
    y1 = _number(element.get("y1"))
    x2 = _number(element.get("x2"))
    y2 = _number(element.get("y2"))
    if None not in (x1, y1, x2, y2):
        return [Point(x1, y1), Point(x2, y2)]  # type: ignore[arg-type]
    return []


def _device_info(element: ET.Element, element_id: str, tag: str) -> DeviceInfo | None:
    x = _number(element.get("x"))
    y = _number(element.get("y"))
    w = _number(element.get("w") or element.get("width"))
    h = _number(element.get("h") or element.get("height"))
    if None in (x, y, w, h):
        return None
    x2 = x + w  # type: ignore[operator]
    y2 = y + h  # type: ignore[operator]
    rotation_value = _number(element.get("rotate")) or 0.0
    rotation = int(round(rotation_value)) % 360
    return DeviceInfo(
        element=element,
        element_id=element_id,
        tag=tag,
        left=min(x, x2),  # type: ignore[arg-type]
        top=min(y, y2),  # type: ignore[arg-type]
        right=max(x, x2),  # type: ignore[arg-type]
        bottom=max(y, y2),  # type: ignore[arg-type]
        x=x,  # type: ignore[arg-type]
        y=y,  # type: ignore[arg-type]
        width=w,  # type: ignore[arg-type]
        height=h,  # type: ignore[arg-type]
        rotation=rotation,
        devref=(element.get("devref") or "").strip(),
    )


def _is_connectable_device(element: ET.Element) -> bool:
    tag = _local_name(element.tag)
    if tag in NON_CONNECTABLE_TAGS or tag in LINE_TAGS or tag in CONDUCTOR_TAGS:
        return False
    if tag in KNOWN_DEVICE_TAGS:
        return True
    return (element.get("composeType") or "").strip() == "GIcon"


def _point_distance(left: Point, right: Point) -> float:
    return math.hypot(left.x - right.x, left.y - right.y)


def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return _point_distance(point, start)
    ratio = ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    projected = Point(start.x + ratio * dx, start.y + ratio * dy)
    return _point_distance(point, projected)


def _point_on_polyline(point: Point, points: list[Point], tolerance: float) -> bool:
    return any(
        _point_to_segment_distance(point, points[index], points[index + 1]) <= tolerance
        for index in range(len(points) - 1)
    )


def _device_boundary_distance(point: Point, device: DeviceInfo, tolerance: float) -> float | None:
    if not (
        device.left - tolerance <= point.x <= device.right + tolerance
        and device.top - tolerance <= point.y <= device.bottom + tolerance
    ):
        return None
    if device.left <= point.x <= device.right and device.top <= point.y <= device.bottom:
        return min(
            abs(point.x - device.left),
            abs(point.x - device.right),
            abs(point.y - device.top),
            abs(point.y - device.bottom),
        )
    clamped_x = min(max(point.x, device.left), device.right)
    clamped_y = min(max(point.y, device.top), device.bottom)
    return math.hypot(point.x - clamped_x, point.y - clamped_y)


def _parse_groups(value: str | None) -> list[tuple[str, str, str]]:
    groups: list[tuple[str, str, str]] = []
    for raw_group in (value or "").split(";"):
        raw_group = raw_group.strip()
        if not raw_group:
            continue
        parts = [part.strip() for part in raw_group.split(",", 2)]
        if len(parts) == 3:
            groups.append((parts[0], parts[1], parts[2]))
    return groups


def _existing_port(element: ET.Element, target_id: str) -> int | None:
    for own_port, _target_port, current_id in _parse_groups(element.get("node_area")):
        if current_id == target_id:
            try:
                return int(own_port)
            except ValueError:
                return None
    return None


def _add_group_if_target_missing(
    element: ET.Element,
    attribute: str,
    own_port: int,
    target_port: int,
    target_id: str,
) -> bool:
    """Append a relation only when the target is absent.

    Existing target relations are frozen byte-for-byte, including their port numbers. This is the
    central conservative rule introduced after the v2.16.0 regression.
    """
    groups = _parse_groups(element.get(attribute))
    if any(group[2] == target_id for group in groups):
        return False
    groups.append((str(own_port), str(target_port), target_id))
    element.set(attribute, ";".join(",".join(group) for group in groups))
    return True


def _target_groups(element: ET.Element, attribute: str, target_id: str) -> list[tuple[str, str, str]]:
    return [group for group in _parse_groups(element.get(attribute)) if group[2] == target_id]


def _device_kind(device: DeviceInfo) -> str | None:
    ref = device.devref.lower()
    if "external_grounddisconnector_new" in ref:
        return "external_ground"
    if "circuit_breaker" in ref:
        return "circuit_breaker"
    if "load_breaker_switch" in ref:
        return "load_breaker"
    return None


def _builtin_ports(device: DeviceInfo) -> tuple[PortAnchor, ...] | None:
    kind = _device_kind(device)
    if kind is None:
        return None
    return _BUILTIN_PORTS.get((kind, device.rotation))


def _dynamic_port_templates(
    devices: list[DeviceInfo],
    lines_by_id: dict[str, LineInfo],
) -> dict[tuple[str, str, int, float, float], tuple[PortAnchor, ...]]:
    """Learn port offsets without renumbering ports.

    Only reciprocal, internally consistent device/line references are accepted as training data.
    Crucially, the device's existing ``own_port`` is retained. v2.16.0 sorted offsets and assigned
    fresh port numbers, which could swap port 0/1 on otherwise correct breakers and disconnectors.
    """
    samples: dict[
        tuple[str, str, int, float, float],
        dict[int, dict[tuple[int, int], set[str]]],
    ] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    signature_counts = Counter(device.signature for device in devices)

    for device in devices:
        for own_port_raw, target_endpoint_raw, target_id in _parse_groups(
            device.element.get("node_area")
        ):
            line = lines_by_id.get(target_id)
            if line is None:
                continue
            try:
                own_port = int(own_port_raw)
                endpoint_index = int(target_endpoint_raw)
            except ValueError:
                continue
            if own_port < 0 or endpoint_index not in (0, 1):
                continue

            reciprocal = False
            for attribute in ("node_area", "link"):
                for line_endpoint, target_port, current_id in _parse_groups(
                    line.element.get(attribute)
                ):
                    if (
                        current_id == device.element_id
                        and line_endpoint == str(endpoint_index)
                        and target_port == str(own_port)
                    ):
                        reciprocal = True
                        break
                if reciprocal:
                    break
            if not reciprocal:
                continue

            point = line.endpoints[endpoint_index]
            dx = _round_half_up(point.x - device.x)
            dy = _round_half_up(point.y - device.y)
            if abs(dx) > max(80.0, abs(device.width) + 30.0):
                continue
            if abs(dy) > max(80.0, abs(device.height) + 30.0):
                continue
            samples[device.signature][own_port][(int(dx), int(dy))].add(device.element_id)

    learned: dict[tuple[str, str, int, float, float], tuple[PortAnchor, ...]] = {}
    for signature, ports in samples.items():
        device_count = max(1, signature_counts[signature])
        anchors: list[PortAnchor] = []
        for port_index, offsets in sorted(ports.items()):
            ranked = sorted(
                ((len(device_ids), offset) for offset, device_ids in offsets.items()),
                key=lambda item: (-item[0], item[1][1], item[1][0]),
            )
            if not ranked:
                continue
            support, (dx, dy) = ranked[0]
            # A single exact reciprocal sample is acceptable for a one-off signature. Repeated
            # signatures require at least two matching devices or 25% support, whichever is larger.
            minimum_support = 1 if device_count == 1 else max(2, math.ceil(device_count * 0.25))
            if support < minimum_support:
                continue
            anchors.append(PortAnchor(float(dx), float(dy), port_index))
        if anchors:
            learned[signature] = tuple(sorted(anchors, key=lambda item: item.port_index))
    return learned

def _ports_for_device(
    device: DeviceInfo,
    learned: dict[tuple[str, str, int, float, float], tuple[PortAnchor, ...]],
) -> tuple[PortAnchor, ...] | None:
    # A reciprocal template learned from the actual drawing is safer than a generic built-in icon
    # rule and preserves that file's real port numbering.
    return learned.get(device.signature) or _builtin_ports(device)


def _line_endpoint_references_device(line: LineInfo, device_id: str) -> bool:
    return any(
        target_id == device_id
        for _own, _target, target_id in _parse_groups(
            line.element.get("node_area") or line.element.get("link")
        )
    )


def _device_references_line(device: DeviceInfo, line_id: str) -> bool:
    return any(
        target_id == line_id
        for _own, _target, target_id in _parse_groups(device.element.get("node_area"))
    )


def _line_target_group(
    line: LineInfo,
    target_id: str,
) -> tuple[int, int] | None:
    for attribute in ("node_area", "link"):
        for own_port, target_port, current_id in _parse_groups(line.element.get(attribute)):
            if current_id != target_id:
                continue
            try:
                return int(own_port), int(target_port)
            except ValueError:
                return None
    return None


def _endpoint_has_other_device(
    line: LineInfo,
    endpoint_index: int,
    device_ids: set[str],
    current_device_id: str,
) -> bool:
    for attribute in ("node_area", "link"):
        for own_port, _target_port, target_id in _parse_groups(line.element.get(attribute)):
            if (
                own_port == str(endpoint_index)
                and target_id in device_ids
                and target_id != current_device_id
            ):
                return True
    return False


def _align_devices_horizontally(
    devices: list[DeviceInfo],
    lines: list[LineInfo],
    learned: dict[tuple[str, str, int, float, float], tuple[PortAnchor, ...]],
    *,
    max_horizontal_shift: float,
    vertical_tolerance: float,
    endpoint_tolerance: float,
) -> tuple[list[str], list[str]]:
    """Move only the device X coordinate, never line geometry.

    This emulates the useful part of an editor left/right nudge: the icon is aligned to existing
    line endpoints. Existing reciprocal relations are the primary evidence. A device with no
    relation is moved only when all selected port candidates imply one unique X shift. Every
    existing modeled connection is revalidated before the move is committed.
    """
    moved_devices: list[str] = []
    warnings: list[str] = []
    lines_by_id = {line.element_id: line for line in lines}
    device_ids = {device.element_id for device in devices}

    for device in devices:
        anchors = _ports_for_device(device, learned)
        if not anchors:
            continue
        anchor_by_port = {anchor.port_index: anchor for anchor in anchors}

        evidence: list[tuple[float, str, int, int]] = []
        seen_relations: set[tuple[str, int, int]] = set()
        unsafe_existing = False

        # Device-side references are authoritative and retain their existing port number.
        for own_port_raw, endpoint_raw, line_id in _parse_groups(
            device.element.get("node_area")
        ):
            line = lines_by_id.get(line_id)
            try:
                port_index = int(own_port_raw)
                endpoint_index = int(endpoint_raw)
            except ValueError:
                unsafe_existing = True
                continue
            anchor = anchor_by_port.get(port_index)
            if line is None or endpoint_index not in (0, 1) or anchor is None:
                # An existing connection that cannot be modeled must not be disturbed by a move.
                unsafe_existing = True
                continue
            point = line.endpoints[endpoint_index]
            dy = point.y - (device.y + anchor.y_offset)
            dx = point.x - (device.x + anchor.x_offset)
            if abs(dy) > vertical_tolerance or abs(dx) > max_horizontal_shift:
                unsafe_existing = True
                continue
            evidence.append((dx, line_id, endpoint_index, port_index))
            seen_relations.add((line_id, endpoint_index, port_index))

        # Complete evidence from line-side references when the device side is missing.
        for line in lines:
            relation = _line_target_group(line, device.element_id)
            if relation is None:
                continue
            endpoint_index, port_index = relation
            key = (line.element_id, endpoint_index, port_index)
            if key in seen_relations:
                continue
            anchor = anchor_by_port.get(port_index)
            if endpoint_index not in (0, 1) or anchor is None:
                unsafe_existing = True
                continue
            point = line.endpoints[endpoint_index]
            dy = point.y - (device.y + anchor.y_offset)
            dx = point.x - (device.x + anchor.x_offset)
            if abs(dy) > vertical_tolerance or abs(dx) > max_horizontal_shift:
                unsafe_existing = True
                continue
            evidence.append((dx, line.element_id, endpoint_index, port_index))
            seen_relations.add(key)

        if unsafe_existing:
            continue

        # No references: accept only unique, unclaimed nearby endpoints for the known ports.
        if not evidence:
            candidate_evidence: list[tuple[float, str, int, int]] = []
            ambiguous = False
            for anchor in anchors:
                candidates: list[tuple[float, float, str, int]] = []
                desired_y = device.y + anchor.y_offset
                desired_x = device.x + anchor.x_offset
                for line in lines:
                    for endpoint_index, point in enumerate(line.endpoints):
                        if _endpoint_has_other_device(
                            line, endpoint_index, device_ids, device.element_id
                        ):
                            continue
                        dy = abs(point.y - desired_y)
                        dx = point.x - desired_x
                        if dy > vertical_tolerance or abs(dx) > max_horizontal_shift:
                            continue
                        candidates.append((abs(dx), dy, line.element_id, endpoint_index))
                candidates.sort()
                if not candidates:
                    continue
                if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < 0.25:
                    ambiguous = True
                    break
                _abs_dx, _dy, line_id, endpoint_index = candidates[0]
                point = lines_by_id[line_id].endpoints[endpoint_index]
                candidate_evidence.append(
                    (point.x - desired_x, line_id, endpoint_index, anchor.port_index)
                )
            if ambiguous or not candidate_evidence:
                continue
            evidence = candidate_evidence

        shifts = [item[0] for item in evidence]
        # The editor's verified same-type nudge normalizes positive half-pixel X coordinates to the
        # lower integer. Do not choose the direction from a possibly malformed endpoint relation.
        # The proposed floor move is validated against every modeled existing relation below.
        fractional = device.x - math.floor(device.x)
        if abs(fractional - 0.5) > 1e-9:
            continue
        candidate_shift = math.floor(device.x) - device.x
        new_x = device.x + candidate_shift
        if abs(candidate_shift) > min(max_horizontal_shift, 0.51):
            continue

        # Per-device validation: every existing modeled relation must remain on its original port.
        valid = True
        for _dx, line_id, endpoint_index, port_index in evidence:
            anchor = anchor_by_port[port_index]
            point = lines_by_id[line_id].endpoints[endpoint_index]
            expected = Point(
                device.x + candidate_shift + anchor.x_offset,
                device.y + anchor.y_offset,
            )
            if _point_distance(point, expected) > endpoint_tolerance:
                valid = False
                break
        if not valid:
            warnings.append(
                f"设备 ID {device.element_id} 水平对齐验证失败，已回滚并保留原位置。"
            )
            continue

        device.element.set("x", _format_number(new_x))
        device.x = new_x
        device.left += candidate_shift
        device.right += candidate_shift
        moved_devices.append(device.element_id)

    return moved_devices, warnings

def repair_tree_connections(
    tree: ET.ElementTree,
    input_path: Path,
    *,
    endpoint_tolerance: float = 2.0,
    device_tolerance: float = 8.0,
    align_device_ports: bool = True,
    max_horizontal_shift: float = 8.0,
    vertical_alignment_tolerance: float = 1.1,
) -> ConnectionRepairResult:
    """Conservatively align devices and fill only missing connection references.

    Existing ``node_area``/``link`` target groups are never removed, renumbered, reordered, or
    replaced. Device alignment changes only ``x`` and is committed per device only after all known
    existing ports still match their original line endpoints. Line paths and bounding boxes are
    never changed.
    """
    del device_tolerance  # retained for API compatibility
    layer = _layer(tree.getroot())
    elements = list(layer)
    result = ConnectionRepairResult(input_path=input_path, direct_element_count=len(elements))

    lines: list[LineInfo] = []
    conductors: list[LineInfo] = []
    devices: list[DeviceInfo] = []
    by_id: dict[str, ET.Element] = {}

    for element in elements:
        element_id = (element.get("id") or "").strip()
        if not element_id:
            continue
        by_id[element_id] = element
        tag = _local_name(element.tag)
        if tag in LINE_TAGS or tag in CONDUCTOR_TAGS:
            points = _path_points(element)
            if len(points) < 2:
                result.warnings.append(f"<{tag}> ID {element_id} 缺少有效路径坐标，已跳过。")
                continue
            info = LineInfo(element, element_id, tag, points)
            if tag in LINE_TAGS:
                lines.append(info)
            else:
                conductors.append(info)
            continue
        if _is_connectable_device(element):
            info = _device_info(element, element_id, tag)
            if info is not None:
                devices.append(info)

    result.line_count = len(lines)
    result.conductor_count = len(conductors)
    result.device_count = len(devices)

    lines_by_id = {line.element_id: line for line in lines}
    conductors_by_id = {item.element_id: item for item in conductors}
    devices_by_id = {item.element_id: item for item in devices}
    line_ids = set(lines_by_id)
    device_ids = set(devices_by_id)
    conductor_ids = set(conductors_by_id)

    # Freeze every original recognized target group for final safety verification.
    original_groups: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for element_id, element in by_id.items():
        for attribute in ("node_area", "link"):
            original_groups[(element_id, attribute)] = _parse_groups(element.get(attribute))

    learned = _dynamic_port_templates(devices, lines_by_id)
    if align_device_ports:
        moved, alignment_warnings = _align_devices_horizontally(
            devices,
            lines,
            learned,
            max_horizontal_shift=max_horizontal_shift,
            vertical_tolerance=vertical_alignment_tolerance,
            endpoint_tolerance=endpoint_tolerance,
        )
        result.aligned_device_ids = sorted(moved)
        result.aligned_device_count = len(moved)
        result.warnings.extend(alignment_warnings)

    changed_elements: set[str] = set(result.aligned_device_ids)
    changed_attributes: set[tuple[str, str]] = {
        (element_id, "x") for element_id in result.aligned_device_ids
    }

    def mark_changed(element: ET.Element, attribute: str) -> None:
        element_id = (element.get("id") or "").strip()
        changed_elements.add(element_id)
        changed_attributes.add((element_id, attribute))

    def add_only(
        element: ET.Element,
        attribute: str,
        own: int,
        target: int,
        target_id: str,
    ) -> bool:
        changed = _add_group_if_target_missing(element, attribute, own, target, target_id)
        if changed:
            result.added_reference_count += 1
            mark_changed(element, attribute)
        return changed

    inferred_relations: set[tuple[str, int, str, int]] = set()

    # 1) Complete reciprocal device/line references from either existing side. Never reinterpret
    # or renumber an existing relation.
    for device in devices:
        for own_port_raw, endpoint_raw, line_id in _parse_groups(
            device.element.get("node_area")
        ):
            line = lines_by_id.get(line_id)
            try:
                own_port = int(own_port_raw)
                endpoint_index = int(endpoint_raw)
            except ValueError:
                continue
            if line is None or endpoint_index not in (0, 1):
                continue
            inferred_relations.add((line_id, endpoint_index, device.element_id, own_port))
            add_only(line.element, "node_area", endpoint_index, own_port, device.element_id)
            add_only(line.element, "link", endpoint_index, own_port, device.element_id)

    for line in lines:
        seen: set[tuple[int, int, str]] = set()
        for attribute in ("node_area", "link"):
            for endpoint_raw, target_port_raw, target_id in _parse_groups(
                line.element.get(attribute)
            ):
                if target_id not in device_ids:
                    continue
                try:
                    endpoint_index = int(endpoint_raw)
                    device_port = int(target_port_raw)
                except ValueError:
                    continue
                if endpoint_index not in (0, 1):
                    continue
                relation = (endpoint_index, device_port, target_id)
                if relation in seen:
                    continue
                seen.add(relation)
                inferred_relations.add(
                    (line.element_id, endpoint_index, target_id, device_port)
                )
                add_only(
                    devices_by_id[target_id].element,
                    "node_area",
                    device_port,
                    endpoint_index,
                    line.element_id,
                )

    # Existing device ports are reserved. New geometry-based relations may use only a free port.
    used_ports: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for device in devices:
        for own_port_raw, _endpoint_raw, line_id in _parse_groups(
            device.element.get("node_area")
        ):
            try:
                used_ports[device.element_id][int(own_port_raw)].add(line_id)
            except ValueError:
                continue

    # 2) Add a brand-new device relation only for a unique exact port match.
    candidates_by_endpoint: dict[
        tuple[str, int], list[tuple[float, DeviceInfo, PortAnchor]]
    ] = defaultdict(list)
    for line in lines:
        for endpoint_index, point in enumerate(line.endpoints):
            # Preserve endpoints already assigned to a device.
            if any(
                own == str(endpoint_index) and target_id in device_ids
                for attribute in ("node_area", "link")
                for own, _target, target_id in _parse_groups(line.element.get(attribute))
            ):
                continue
            for device in devices:
                anchors = _ports_for_device(device, learned)
                if not anchors:
                    continue
                for anchor in anchors:
                    if used_ports[device.element_id][anchor.port_index]:
                        continue
                    port_point = Point(
                        device.x + anchor.x_offset,
                        device.y + anchor.y_offset,
                    )
                    distance = _point_distance(point, port_point)
                    if distance <= endpoint_tolerance:
                        candidates_by_endpoint[(line.element_id, endpoint_index)].append(
                            (distance, device, anchor)
                        )

    selected_device_ports: set[tuple[str, int]] = set()
    for (line_id, endpoint_index), candidates in sorted(candidates_by_endpoint.items()):
        candidates.sort(key=lambda item: (item[0], item[1].element_id, item[2].port_index))
        if not candidates:
            continue
        if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < 0.25:
            result.warnings.append(
                f"连接线 ID {line_id} 端点 {endpoint_index} 存在多个等距设备候选，已跳过。"
            )
            continue
        _distance, device, anchor = candidates[0]
        port_key = (device.element_id, anchor.port_index)
        if port_key in selected_device_ports or used_ports[device.element_id][anchor.port_index]:
            continue
        selected_device_ports.add(port_key)
        line = lines_by_id[line_id]
        add_only(line.element, "node_area", endpoint_index, anchor.port_index, device.element_id)
        add_only(line.element, "link", endpoint_index, anchor.port_index, device.element_id)
        add_only(device.element, "node_area", anchor.port_index, endpoint_index, line_id)
        inferred_relations.add((line_id, endpoint_index, device.element_id, anchor.port_index))

    # 3) Complete and add conductor relations conservatively.
    for line in lines:
        for attribute in ("node_area", "link"):
            for endpoint_raw, target_port_raw, target_id in _parse_groups(
                line.element.get(attribute)
            ):
                if target_id not in conductor_ids:
                    continue
                try:
                    endpoint_index = int(endpoint_raw)
                    conductor_port = int(target_port_raw)
                except ValueError:
                    continue
                if endpoint_index not in (0, 1):
                    continue
                add_only(
                    conductors_by_id[target_id].element,
                    "node_area",
                    conductor_port,
                    endpoint_index,
                    line.element_id,
                )

        for endpoint_index, point in enumerate(line.endpoints):
            existing_conductor = any(
                own == str(endpoint_index) and target_id in conductor_ids
                for attribute in ("node_area", "link")
                for own, _target, target_id in _parse_groups(line.element.get(attribute))
            )
            if existing_conductor:
                continue
            matches = [
                conductor
                for conductor in conductors
                if _point_on_polyline(point, conductor.points, endpoint_tolerance)
            ]
            if len(matches) != 1:
                continue
            conductor = matches[0]
            add_only(line.element, "node_area", endpoint_index, 0, conductor.element_id)
            add_only(line.element, "link", endpoint_index, 0, conductor.element_id)
            add_only(conductor.element, "node_area", 0, endpoint_index, line.element_id)

    # 4) Complete reciprocal line junctions only when one side already declares the relation.
    for line in lines:
        for attribute in ("node_area", "link"):
            for own_raw, target_raw, target_id in _parse_groups(line.element.get(attribute)):
                target_line = lines_by_id.get(target_id)
                if target_line is None:
                    continue
                try:
                    own_endpoint = int(own_raw)
                    target_endpoint = int(target_raw)
                except ValueError:
                    continue
                if own_endpoint not in (0, 1) or target_endpoint not in (0, 1):
                    continue
                add_only(
                    target_line.element,
                    "node_area",
                    target_endpoint,
                    own_endpoint,
                    line.element_id,
                )
                add_only(
                    target_line.element,
                    "link",
                    target_endpoint,
                    own_endpoint,
                    line.element_id,
                )

    # Final invariant: every original target group must remain exactly present. Any violation is a
    # programming error; fail the file instead of outputting a topology regression.
    for (element_id, attribute), groups in original_groups.items():
        current = _parse_groups(by_id[element_id].get(attribute))
        for group in groups:
            if group not in current:
                raise ValueError(
                    f"连接点保守校验失败：图元 {element_id} 的 {attribute} 原连接 {group} 被改动。"
                )

    result.inferred_relation_count = len(inferred_relations)
    result.changed_element_ids = sorted(changed_elements)
    result.changed_element_count = len(changed_elements)
    result.changed_attribute_count = len(changed_attributes)
    # Conservative mode deliberately never updates/removes existing groups or line geometry.
    result.updated_reference_count = 0
    result.removed_reference_count = 0
    result.adjusted_line_ids = []
    result.adjusted_line_endpoint_count = 0
    return result

