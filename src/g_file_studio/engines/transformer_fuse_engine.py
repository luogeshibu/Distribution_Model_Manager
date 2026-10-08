from __future__ import annotations

import copy
import math
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from g_file_studio.services.id_rule_service import IdRule
from g_file_studio.services.paths import resource_path


TARGET_MARKER = "TRANSFORMER_OH"
DEFAULT_TEMPLATE_PATH = resource_path("resources/templates/transform_fuse_mode.sln.pic.g")
_CONDUCTOR_TAGS = {"ConnectLine", "FeedLine"}


@dataclass(frozen=True)
class _TemplateVariant:
    merge: ET.Element
    frame: ET.Element
    transformer: ET.Element
    fuse: ET.Element
    internal_line: ET.Element
    element_order: tuple[str, ...]
    free_anchor: tuple[float, float]
    extension_direction: tuple[int, int]
    transformer_pin: int
    transformer_line_endpoint: int
    fuse_internal_pin: int
    fuse_internal_line_endpoint: int
    fuse_free_pin: int


@dataclass(frozen=True)
class _Connection:
    conductor: ET.Element
    device_pin: int
    conductor_endpoint: int
    inferred: bool = False


@dataclass
class TransformerFuseFileResult:
    file_name: str
    replaced: int = 0
    skipped_unconnected: int = 0
    skipped_multi_connected: int = 0
    skipped_invalid_connection: int = 0
    matched_transformers: int = 0
    rows: list[dict[str, str]] = field(default_factory=list)


@dataclass
class TransformerFuseBatchResult:
    files: list[TransformerFuseFileResult] = field(default_factory=list)

    @property
    def replaced(self) -> int:
        return sum(item.replaced for item in self.files)

    @property
    def skipped_unconnected(self) -> int:
        return sum(item.skipped_unconnected for item in self.files)

    @property
    def skipped_multi_connected(self) -> int:
        return sum(item.skipped_multi_connected for item in self.files)

    @property
    def skipped_invalid_connection(self) -> int:
        return sum(item.skipped_invalid_connection for item in self.files)

    @property
    def matched_transformers(self) -> int:
        return sum(item.matched_transformers for item in self.files)


def _local_name(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _parse_ref_groups(value: str | None) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    for raw_group in str(value or "").split(";"):
        parts = [part.strip() for part in raw_group.split(",")]
        if len(parts) < 3:
            continue
        try:
            first = int(parts[0])
            second = int(parts[1])
        except ValueError:
            continue
        target_id = parts[2]
        if target_id:
            result.append((first, second, target_id))
    return result


def _format_ref_groups(groups: Iterable[tuple[int, int, str]]) -> str:
    return ";".join(f"{first},{second},{target}" for first, second, target in groups)


def _parse_points(value: str | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for token in str(value or "").split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            points.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    return points


def _number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _translate_point_list(value: str | None, dx: float, dy: float) -> str:
    points = _parse_points(value)
    if not points:
        return str(value or "")
    return " ".join(f"{_number(x + dx)},{_number(y + dy)}" for x, y in points)


def _element_center(element: ET.Element) -> tuple[float, float]:
    x = float(element.get("x") or 0.0)
    y = float(element.get("y") or 0.0)
    w = float(element.get("w") or 0.0)
    h = float(element.get("h") or 0.0)
    return x + w / 2.0, y + h / 2.0


def _template_variants(template_path: Path = DEFAULT_TEMPLATE_PATH) -> tuple[_TemplateVariant, ...]:
    """Read the four canonical combinations and derive exact Fuse pin anchors.

    The template intentionally contains four orientations.  Each pair connects one
    of the two Fuse pins to the short internal ConnectLine, so across the four
    examples both pin indices are observable for each Fuse rotation.  We use those
    observed line endpoints to derive the *exact* world offset of pin 0/1 instead of
    guessing from the visible rect/group bounding box.  This keeps the reused
    external conductor endpoint pixel-perfect on the Fuse free pin.
    """
    tree = ET.parse(template_path)
    root = tree.getroot()
    layer = next((item for item in root.iter() if _local_name(item.tag) == "Layer"), None)
    if layer is None:
        raise ValueError(f"柱上变压器熔断器模板没有 Layer：{template_path}")

    children = list(layer)
    raw_groups: list[dict[str, object]] = []
    observed_fuse_pin_offsets: dict[tuple[int, int], tuple[float, float]] = {}
    index = 0
    while index < len(children):
        if _local_name(children[index].tag) != "Merge":
            index += 1
            continue
        end = index + 1
        while end < len(children) and _local_name(children[end].tag) != "Merge":
            end += 1
        group = children[index:end]
        merge = group[0]
        frame = next((item for item in group if _local_name(item.tag) == "rect"), None)
        transformer = next((item for item in group if _local_name(item.tag) == "TransformerDis"), None)
        fuse = next((item for item in group if _local_name(item.tag) == "ZhaiWaiDaoZha"), None)
        line = next((item for item in group if _local_name(item.tag) == "ConnectLine"), None)
        if transformer is not None and fuse is not None and line is not None and frame is not None:
            line_links = _parse_ref_groups(line.get("link") or line.get("node_area"))
            transformer_link = next(
                (item for item in line_links if item[2] == str(transformer.get("id") or "")),
                None,
            )
            fuse_link = next(
                (item for item in line_links if item[2] == str(fuse.get("id") or "")),
                None,
            )
            line_points = _parse_points(line.get("d"))
            if transformer_link is None or fuse_link is None or len(line_points) < 2:
                raise ValueError("柱上变压器熔断器模板内部连接关系不完整。")
            fuse_internal_pin = int(fuse_link[1])
            fuse_line_endpoint = int(fuse_link[0])
            if fuse_internal_pin not in (0, 1) or fuse_line_endpoint not in (0, 1):
                raise ValueError("柱上变压器熔断器模板的 Fuse Pin/Line endpoint 必须是 0/1。")
            fuse_x = float(fuse.get("x") or 0.0)
            fuse_y = float(fuse.get("y") or 0.0)
            connected_world = line_points[0] if fuse_line_endpoint == 0 else line_points[-1]
            rotation = int(round(float(fuse.get("rotate") or 0.0))) % 360
            observed_fuse_pin_offsets[(rotation, fuse_internal_pin)] = (
                connected_world[0] - fuse_x,
                connected_world[1] - fuse_y,
            )
            raw_groups.append({
                "merge": merge,
                "frame": frame,
                "element_order": tuple(_local_name(item.tag) for item in group),
                "transformer": transformer,
                "fuse": fuse,
                "line": line,
                "transformer_link": transformer_link,
                "fuse_link": fuse_link,
                "connected_world": connected_world,
                "rotation": rotation,
            })
        index = end

    result: list[_TemplateVariant] = []
    for raw in raw_groups:
        merge = raw["merge"]
        frame = raw["frame"]
        element_order = raw["element_order"]
        transformer = raw["transformer"]
        fuse = raw["fuse"]
        line = raw["line"]
        transformer_link = raw["transformer_link"]
        fuse_link = raw["fuse_link"]
        connected_world = raw["connected_world"]
        rotation = int(raw["rotation"])
        assert isinstance(merge, ET.Element)
        assert isinstance(frame, ET.Element)
        assert isinstance(element_order, tuple)
        assert isinstance(transformer, ET.Element)
        assert isinstance(fuse, ET.Element)
        assert isinstance(line, ET.Element)
        assert isinstance(transformer_link, tuple)
        assert isinstance(fuse_link, tuple)
        assert isinstance(connected_world, tuple)

        fuse_internal_pin = int(fuse_link[1])
        fuse_free_pin = 1 - fuse_internal_pin
        free_offset = observed_fuse_pin_offsets.get((rotation, fuse_free_pin))
        if free_offset is None:
            raise ValueError(
                f"柱上变压器熔断器模板无法推导 Fuse rotate={rotation} pin={fuse_free_pin} 的坐标。"
            )
        fuse_x = float(fuse.get("x") or 0.0)
        fuse_y = float(fuse.get("y") or 0.0)
        free_anchor = (fuse_x + free_offset[0], fuse_y + free_offset[1])

        vx = connected_world[0] - free_anchor[0]
        vy = connected_world[1] - free_anchor[1]
        if abs(vx) >= abs(vy):
            direction = ((1, 0) if vx > 0 else (-1, 0))
        else:
            direction = ((0, 1) if vy > 0 else (0, -1))

        result.append(
            _TemplateVariant(
                merge=copy.deepcopy(merge),
                frame=copy.deepcopy(frame),
                transformer=copy.deepcopy(transformer),
                fuse=copy.deepcopy(fuse),
                internal_line=copy.deepcopy(line),
                element_order=element_order,
                free_anchor=free_anchor,
                extension_direction=direction,
                transformer_pin=int(transformer_link[1]),
                transformer_line_endpoint=int(transformer_link[0]),
                fuse_internal_pin=fuse_internal_pin,
                fuse_internal_line_endpoint=int(fuse_link[0]),
                fuse_free_pin=fuse_free_pin,
            )
        )

    directions = {item.extension_direction for item in result}
    if len(result) != 4 or directions != {(1, 0), (-1, 0), (0, 1), (0, -1)}:
        raise ValueError(
            "柱上变压器熔断器模板必须包含上/下/左/右四种方向组合。"
        )
    return tuple(result)

def _marker_identity_sets(
    marker_entries: Iterable[tuple[str, str, str] | dict[str, str]],
) -> tuple[set[str], set[str], set[str]]:
    devrefs: set[str] = set()
    file_names: set[str] = set()
    element_ids: set[str] = set()
    for entry in marker_entries:
        if isinstance(entry, dict):
            file_name = str(entry.get("file_name", "") or "").strip()
            devref = str(entry.get("devref", "") or "").strip()
            marker = str(entry.get("classification_marker", "") or "").strip()
            element_id = str(entry.get("element_id", "") or "").strip()
        else:
            values = tuple(entry)
            file_name = str(values[0] if len(values) > 0 else "").strip()
            devref = str(values[1] if len(values) > 1 else "").strip()
            marker = str(values[2] if len(values) > 2 else "").strip()
            element_id = str(values[3] if len(values) > 3 else "").strip()
        if marker.casefold() != TARGET_MARKER.casefold():
            continue
        if devref:
            devrefs.add(devref.lstrip("#").casefold())
        if file_name:
            file_names.add(PurePosixPath(file_name.replace("\\", "/")).name.casefold())
        if element_id:
            element_ids.add(element_id.casefold())
    return devrefs, file_names, element_ids


def _devref_parts(devref: str) -> tuple[str, str]:
    raw = str(devref or "").strip().lstrip("#")
    if ":" in raw:
        path_part, element_id = raw.rsplit(":", 1)
    else:
        path_part, element_id = raw, ""
    file_name = PurePosixPath(path_part.replace("\\", "/")).name
    return file_name, element_id


def _is_classified_transformer(
    element: ET.Element,
    identities: tuple[set[str], set[str], set[str]],
) -> bool:
    if _local_name(element.tag) != "TransformerDis":
        return False
    devrefs, file_names, element_ids = identities
    raw_devref = str(element.get("devref") or "").strip().lstrip("#")
    if raw_devref and raw_devref.casefold() in devrefs:
        return True
    file_name, element_id = _devref_parts(raw_devref)
    if file_name and file_name.casefold() in file_names:
        return True
    if element_id and element_id.casefold() in element_ids:
        return True
    return False


def _connection_records(layer: ET.Element, device: ET.Element) -> list[_Connection]:
    element_id = str(device.get("id") or "").strip()
    by_id = {
        str(item.get("id") or "").strip(): item
        for item in list(layer)
        if str(item.get("id") or "").strip()
    }
    found: dict[tuple[str, int, int], _Connection] = {}

    for attribute in ("node_area", "link"):
        for device_pin, line_endpoint, conductor_id in _parse_ref_groups(device.get(attribute)):
            conductor = by_id.get(conductor_id)
            if conductor is None or _local_name(conductor.tag) not in _CONDUCTOR_TAGS:
                continue
            found[(conductor_id, device_pin, line_endpoint)] = _Connection(
                conductor=conductor,
                device_pin=device_pin,
                conductor_endpoint=line_endpoint,
            )

    for conductor in list(layer):
        if _local_name(conductor.tag) not in _CONDUCTOR_TAGS:
            continue
        conductor_id = str(conductor.get("id") or "").strip()
        for attribute in ("node_area", "link"):
            for line_endpoint, device_pin, target_id in _parse_ref_groups(conductor.get(attribute)):
                if target_id != element_id:
                    continue
                found[(conductor_id, device_pin, line_endpoint)] = _Connection(
                    conductor=conductor,
                    device_pin=device_pin,
                    conductor_endpoint=line_endpoint,
                )
    return list(found.values())


def _transformer_geometry_key(element: ET.Element) -> tuple[str, str, str, str, str]:
    """Return a stable visual signature for learning terminal coordinates.

    Some legacy NariPd transformer drawings have a visible conductor touching the
    transformer terminal but omit the reciprocal ``node_area/link`` reference.  We
    learn the pin offsets from correctly linked peers with the same symbol geometry
    and then use those offsets only as an exact geometric fallback.
    """
    return (
        str(element.get("devref") or "").strip().lstrip("#").casefold(),
        str(element.get("w") or "").strip(),
        str(element.get("h") or "").strip(),
        str(element.get("rotate") or "0").strip(),
        str(element.get("tfr") or "").strip(),
    )


def _endpoint_world(conductor: ET.Element, endpoint_index: int) -> tuple[float, float]:
    points = _parse_points(conductor.get("d"))
    if len(points) < 2 or endpoint_index not in (0, 1):
        raise ValueError("连接线缺少有效端点坐标。")
    return points[0] if endpoint_index == 0 else points[-1]


def _learn_transformer_pin_offsets(
    layer: ET.Element,
) -> dict[tuple[str, str, str, str, str], dict[int, tuple[float, float]]]:
    """Learn exact pin offsets from the file's already-correct reciprocal links.

    The fallback is deliberately conservative: it learns only pin indices 0/1 and
    only from actual ConnectLine/FeedLine endpoint coordinates.  For repeated
    observations the most common rounded offset wins, which protects against an
    occasional malformed reference in a large field drawing.
    """
    from collections import Counter, defaultdict

    samples: dict[
        tuple[str, str, str, str, str],
        dict[int, list[tuple[float, float]]],
    ] = defaultdict(lambda: defaultdict(list))

    for device in list(layer):
        if _local_name(device.tag) != "TransformerDis":
            continue
        try:
            base_x = float(device.get("x") or 0.0)
            base_y = float(device.get("y") or 0.0)
        except ValueError:
            continue
        key = _transformer_geometry_key(device)
        for connection in _connection_records(layer, device):
            if connection.device_pin not in (0, 1):
                continue
            try:
                anchor = _endpoint_world(connection.conductor, connection.conductor_endpoint)
            except ValueError:
                continue
            samples[key][connection.device_pin].append(
                (anchor[0] - base_x, anchor[1] - base_y)
            )

    learned: dict[
        tuple[str, str, str, str, str],
        dict[int, tuple[float, float]],
    ] = {}
    for key, by_pin in samples.items():
        pin_map: dict[int, tuple[float, float]] = {}
        for pin, values in by_pin.items():
            rounded = Counter((round(x, 6), round(y, 6)) for x, y in values)
            if rounded:
                pin_map[pin] = rounded.most_common(1)[0][0]
        if pin_map:
            learned[key] = pin_map
    return learned


def _augment_connections_from_geometry(
    layer: ET.Element,
    device: ET.Element,
    existing: list[_Connection],
    learned_offsets: dict[tuple[str, str, str, str, str], dict[int, tuple[float, float]]],
    *,
    tolerance: float = 0.01,
) -> list[_Connection]:
    """Add missing reciprocal connections when a conductor endpoint exactly touches a pin.

    This fixes field G files where the drawing is visually/topologically connected but
    the TransformerDis itself (and sometimes the line endpoint) lacks the reciprocal
    object ID.  It does *not* use proximity to the transformer bounding box.
    """
    offsets = learned_offsets.get(_transformer_geometry_key(device), {})
    if not offsets:
        return existing

    try:
        base_x = float(device.get("x") or 0.0)
        base_y = float(device.get("y") or 0.0)
    except ValueError:
        return existing

    found: dict[tuple[str, int, int], _Connection] = {}
    for connection in existing:
        conductor_id = str(connection.conductor.get("id") or "").strip()
        found[(conductor_id, connection.device_pin, connection.conductor_endpoint)] = connection

    for pin, (off_x, off_y) in offsets.items():
        anchor = (base_x + off_x, base_y + off_y)
        for conductor in list(layer):
            if _local_name(conductor.tag) not in _CONDUCTOR_TAGS:
                continue
            conductor_id = str(conductor.get("id") or "").strip()
            points = _parse_points(conductor.get("d"))
            if len(points) < 2:
                continue
            for endpoint_index, point in ((0, points[0]), (1, points[-1])):
                if math.hypot(point[0] - anchor[0], point[1] - anchor[1]) > tolerance:
                    continue
                key = (conductor_id, pin, endpoint_index)
                if key not in found:
                    found[key] = _Connection(
                        conductor=conductor,
                        device_pin=pin,
                        conductor_endpoint=endpoint_index,
                        inferred=True,
                    )
    return list(found.values())


def _endpoint_and_direction(
    conductor: ET.Element,
    endpoint_index: int,
) -> tuple[tuple[float, float], tuple[int, int]]:
    points = _parse_points(conductor.get("d"))
    if len(points) < 2 or endpoint_index not in (0, 1):
        raise ValueError("连接线缺少有效端点坐标。")
    endpoint = points[0] if endpoint_index == 0 else points[-1]
    neighbor = points[1] if endpoint_index == 0 else points[-2]
    dx = endpoint[0] - neighbor[0]
    dy = endpoint[1] - neighbor[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        raise ValueError("连接线端点与相邻折点重合，无法判断组合方向。")
    if abs(dx) >= abs(dy):
        return endpoint, ((1, 0) if dx > 0 else (-1, 0))
    return endpoint, ((0, 1) if dy > 0 else (0, -1))


class _IdAllocator:
    def __init__(self, layer: ET.Element, rules: dict[str, IdRule]) -> None:
        self.layer = layer
        self.rules = rules
        self.blocked = {
            str(item.get("id") or "").strip()
            for item in list(layer)
            if str(item.get("id") or "").strip()
        }
        self.seed: dict[str, str | None] = {}

    def allocate(self, tag: str) -> str:
        rule = self.rules.get(tag)
        if rule is None or not rule.enabled or not rule.verified:
            raise ValueError(
                f"新增 <{tag}> 需要已启用且已确认的全局 ID 规则。"
                "请先在‘ID 检查与修复’中确认该元素规则。"
            )
        if tag not in self.seed:
            values = [
                str(item.get("id") or "").strip()
                for item in list(self.layer)
                if _local_name(item.tag) == tag
                and rule.matches(str(item.get("id") or "").strip())
            ]
            self.seed[tag] = str(max(map(int, values))) if values else None
        candidate = rule.build_after(self.seed[tag])
        while candidate in self.blocked:
            candidate = rule.build_after(candidate)
        self.seed[tag] = candidate
        self.blocked.add(candidate)
        return candidate


def _replace_conductor_target(
    conductor: ET.Element,
    *,
    old_device_id: str,
    new_device_id: str,
    new_device_pin: int,
    endpoint_index: int,
) -> None:
    """Replace the reciprocal device reference without changing conductor geometry."""
    for attribute in ("link", "node_area"):
        groups = _parse_ref_groups(conductor.get(attribute))
        changed = False
        updated: list[tuple[int, int, str]] = []
        for own_endpoint, target_pin, target_id in groups:
            if target_id == old_device_id and own_endpoint == endpoint_index:
                updated.append((own_endpoint, new_device_pin, new_device_id))
                changed = True
            else:
                updated.append((own_endpoint, target_pin, target_id))
        if not changed:
            updated.append((endpoint_index, new_device_pin, new_device_id))
        conductor.set(attribute, _format_ref_groups(updated))


def _translate_element_xy(element: ET.Element, dx: float, dy: float) -> None:
    if element.get("x") is not None:
        element.set("x", _number(float(element.get("x") or 0.0) + dx))
    if element.get("y") is not None:
        element.set("y", _number(float(element.get("y") or 0.0) + dy))


def _translate_merge(element: ET.Element, dx: float, dy: float) -> None:
    _translate_element_xy(element, dx, dy)
    if element.get("mergex") is not None:
        element.set("mergex", _number(float(element.get("mergex") or 0.0) + dx))
    if element.get("mergey") is not None:
        element.set("mergey", _number(float(element.get("mergey") or 0.0) + dy))


def _copy_template_transformer_geometry(
    target: ET.Element,
    template: ET.Element,
    dx: float,
    dy: float,
) -> None:
    for key in (
        "devref",
        "composeType",
        "w",
        "h",
        "rotate",
        "tfr",
        "switchapp",
        "switchappflag",
        "clip",
        "isDisplay",
        "opacity",
    ):
        if template.get(key) is not None:
            target.set(key, str(template.get(key)))
    target.set("x", _number(float(template.get("x") or 0.0) + dx))
    target.set("y", _number(float(template.get("y") or 0.0) + dy))


def replace_transformer_oh_with_fuse_pairs(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    marker_entries: Iterable[tuple[str, str, str] | dict[str, str]],
    id_rules: dict[str, IdRule],
    template_path: Path = DEFAULT_TEMPLATE_PATH,
) -> TransformerFuseFileResult:
    """Replace classified TRANSFORMER_OH devices with exactly one connected pin.

    The original external ConnectLine/FeedLine geometry is never moved. Every conductor
    endpoint attached to the one connected Transformer pin remains exactly where it was
    and is re-targeted to the free Fuse terminal. The Transformer is moved outward
    according to the conductor direction, a new Fuse and short internal ConnectLine are
    inserted, and the Transformer is connected only to that internal line. Devices with
    zero connected pins or with both Transformer pins already connected are left
    untouched. Multiple conductors on the same Transformer pin are supported only when
    they share the same physical anchor and approach direction.
    """
    identities = _marker_identity_sets(marker_entries)
    if not any(identities):
        raise ValueError(
            "当前本地图元分类中没有 TRANSFORMER_OH。"
            "请先在主程序“图元管理”中刷新图元列表、确认该分类并保存到本地缓存。"
        )

    root = tree.getroot()
    layers = [item for item in list(root) if _local_name(item.tag) == "Layer"]
    if not layers:
        raise ValueError(f"{file_path.name} 的 G 根节点下没有直属 Layer。")

    variants = _template_variants(template_path)
    by_direction = {item.extension_direction: item for item in variants}
    result = TransformerFuseFileResult(file_name=file_path.name)

    for layer in layers:
        # Learn terminal geometry *before* any mutation.  This lets us recover legacy
        # one-ended transformers whose visible line touches the pin but whose reciprocal
        # node_area/link reference was never written into the G file.
        learned_pin_offsets = _learn_transformer_pin_offsets(layer)
        allocator = _IdAllocator(layer, id_rules)
        targets = [
            item for item in list(layer)
            if _is_classified_transformer(item, identities)
        ]
        result.matched_transformers += len(targets)

        # Freeze connectivity against the original layer before inserting any new
        # groups.  This prevents a newly inserted internal line from influencing the
        # geometric fallback for a later transformer in the same file.
        frozen_connections: dict[int, list[_Connection]] = {}
        for candidate in targets:
            direct = _connection_records(layer, candidate)
            frozen_connections[id(candidate)] = _augment_connections_from_geometry(
                layer,
                candidate,
                direct,
                learned_pin_offsets,
            )

        for transformer in targets:
            transformer_id = str(transformer.get("id") or "").strip()
            connections = frozen_connections[id(transformer)]
            if not connections:
                result.skipped_unconnected += 1
                result.rows.append({
                    "file": file_path.name,
                    "transformer_id": transformer_id,
                    "result": "SKIP_UNCONNECTED",
                    "detail": "TRANSFORMER_OH 两个端点都未检测到 ConnectLine/FeedLine（含精确几何端点回退）",
                })
                continue
            connected_pins = {connection.device_pin for connection in connections}
            if len(connected_pins) != 1:
                result.skipped_multi_connected += 1
                result.rows.append({
                    "file": file_path.name,
                    "transformer_id": transformer_id,
                    "result": "SKIP_MULTI_CONNECTED",
                    "detail": (
                        f"检测到 {len(connected_pins)} 个已连接 Transformer 端点 / "
                        f"{len(connections)} 条线路；两个端点均已连接时不替换"
                    ),
                })
                continue

            try:
                endpoint_rows = [
                    (
                        connection,
                        *_endpoint_and_direction(
                            connection.conductor,
                            connection.conductor_endpoint,
                        ),
                    )
                    for connection in connections
                ]
                anchor = endpoint_rows[0][1]
                direction = endpoint_rows[0][2]
                for _connection, other_anchor, _other_direction in endpoint_rows[1:]:
                    if math.hypot(other_anchor[0] - anchor[0], other_anchor[1] - anchor[1]) > 1e-6:
                        raise ValueError(
                            "同一 Transformer 端点关联了多条线路，但物理端点坐标不一致；"
                            "无法在不移动原线路的前提下同时接到同一个 Fuse 端点。"
                        )
                # Multiple branches may approach the same terminal from different
                # directions.  The physical anchor is authoritative; use the first
                # conductor only to choose which of the four canonical framed variants
                # extends away from that anchor.
                variant = by_direction[direction]
            except Exception as exc:
                result.skipped_invalid_connection += 1
                result.rows.append({
                    "file": file_path.name,
                    "transformer_id": transformer_id,
                    "result": "SKIP_INVALID_CONNECTION",
                    "detail": str(exc),
                })
                continue

            connection = connections[0]

            merge_id = allocator.allocate("Merge")
            frame_id = allocator.allocate("rect")
            fuse_id = allocator.allocate("ZhaiWaiDaoZha")
            internal_line_id = allocator.allocate("ConnectLine")
            dx = anchor[0] - variant.free_anchor[0]
            dy = anchor[1] - variant.free_anchor[1]

            old_index = list(layer).index(transformer)
            old_devref = str(transformer.get("devref") or "")

            # Copy the whole canonical device group, including the Merge marker and
            # dashed rectangular frame.  The user-provided template is authoritative:
            # dimensions, line style, colors, rotation, order and mergesize are kept.
            merge = copy.deepcopy(variant.merge)
            merge.set("id", merge_id)
            _translate_merge(merge, dx, dy)

            frame = copy.deepcopy(variant.frame)
            frame.set("id", frame_id)
            _translate_element_xy(frame, dx, dy)

            # Keep the Transformer business identity/attributes, but normalize its
            # visual definition/geometry to the canonical combination template.
            _copy_template_transformer_geometry(
                transformer,
                variant.transformer,
                dx,
                dy,
            )
            transformer_group = (
                variant.transformer_pin,
                variant.transformer_line_endpoint,
                internal_line_id,
            )
            transformer.set("node_area", _format_ref_groups([transformer_group]))
            if "link" in transformer.attrib:
                transformer.set("link", _format_ref_groups([transformer_group]))

            fuse = copy.deepcopy(variant.fuse)
            fuse.set("id", fuse_id)
            _translate_element_xy(fuse, dx, dy)
            fuse_groups = [
                (
                    variant.fuse_internal_pin,
                    variant.fuse_internal_line_endpoint,
                    internal_line_id,
                ),
                *[
                    (
                        variant.fuse_free_pin,
                        external.conductor_endpoint,
                        str(external.conductor.get("id") or ""),
                    )
                    for external in connections
                ],
            ]
            fuse.set("node_area", _format_ref_groups(fuse_groups))
            if "link" in fuse.attrib:
                fuse.set("link", _format_ref_groups(fuse_groups))

            internal_line = copy.deepcopy(variant.internal_line)
            internal_line.set("id", internal_line_id)
            _translate_element_xy(internal_line, dx, dy)
            internal_line.set("d", _translate_point_list(internal_line.get("d"), dx, dy))
            line_groups = [
                (
                    variant.transformer_line_endpoint,
                    variant.transformer_pin,
                    transformer_id,
                ),
                (
                    variant.fuse_internal_line_endpoint,
                    variant.fuse_internal_pin,
                    fuse_id,
                ),
            ]
            internal_line.set("link", _format_ref_groups(line_groups))
            internal_line.set("node_area", _format_ref_groups(line_groups))

            for external in connections:
                _replace_conductor_target(
                    external.conductor,
                    old_device_id=transformer_id,
                    new_device_id=fuse_id,
                    new_device_pin=variant.fuse_free_pin,
                    endpoint_index=external.conductor_endpoint,
                )

            replacement_by_tag = {
                "Merge": merge,
                "rect": frame,
                "TransformerDis": transformer,
                "ZhaiWaiDaoZha": fuse,
                "ConnectLine": internal_line,
            }
            if len(variant.element_order) != 5 or set(variant.element_order) != set(replacement_by_tag):
                raise ValueError("柱上变压器熔断器模板组合元素不是 Merge/rect/Transformer/Fuse/ConnectLine。")

            layer.remove(transformer)
            for offset, tag in enumerate(variant.element_order):
                layer.insert(old_index + offset, replacement_by_tag[tag])

            result.replaced += 1
            result.rows.append({
                "file": file_path.name,
                "transformer_id": transformer_id,
                "result": "REPLACED",
                "detail": (
                    f"{old_devref} → 完整 Merge + 矩形框 + Transformer_OH + Fuse 组合；"
                    f"Transformer 仅端点 {connection.device_pin} 已连接，共 {len(connections)} 条线路；"
                    f"其中几何回退识别 {sum(1 for item in connections if item.inferred)} 条；"
                    f"所有原线路端点保持坐标不变并改接 Fuse {fuse_id} 空闲 Pin；"
                    f"Merge {merge_id} / rect {frame_id} / 内部 ConnectLine {internal_line_id}"
                ),
            })

    return result


def write_tree_atomic(tree: ET.ElementTree, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    temporary = output_path.with_name(output_path.name + ".tmp")
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    ET.parse(temporary)
    os.replace(temporary, output_path)
