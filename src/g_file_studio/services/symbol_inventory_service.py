from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import escape
from itertools import permutations
from pathlib import Path
from typing import Callable

from g_file_studio.engines.id_engine import direct_layer_elements, local_name
from g_file_studio.engines.rmu_identification_engine import (
    assign_global_text_owners,
    identify_rmus,
)
from g_file_studio.engines.smart_profile_engine import (
    _center_inside,
    _custom_rule_matches,
    _device_role,
    _find_rect,
    _rmu_class,
    _marker_texts,
    apply_smart_profile_to_tree,
)
from g_file_studio.models import InputMode, ProcessingResult
from g_file_studio.processors.common import discover_g_inputs
from g_file_studio.services.database_service import OracleDatabaseService, TopologyFeederAnchorContext
from g_file_studio.services.site_profile_service import (
    SiteSmartProfile,
    authoritative_geometry_templates,
)


SYMBOL_USAGE_VALUES = (
    "设备",
    "设备组成图元",
    "状态图元",
    "标签/辅助图元",
    "测量/信号",
    "Poke/跳转",
    "其他",
)
DEVICE_LEVEL_VALUES = (
    "独立设备",
    "组合设备",
    "设备内部部件",
    "辅助关联",
    "不计入设备",
)


def infer_symbol_usage(*, role: str = "", source_file: str = "", element_tag: str = "") -> str:
    """Best-effort classification for a newly uploaded standard icon.

    Classification is editable in the standard table and becomes authoritative once
    saved.  Strong naming conventions are used only as an initial default.
    """
    text = " ".join((role, source_file, element_tag)).upper()
    filename = Path(source_file).name.lower()
    if ".zt.icn.g" in filename or any(token in text for token in ("STATUS", "状态")):
        return "状态图元"
    if "POKE" in text:
        return "Poke/跳转"
    if any(token in text for token in ("MEASURE", "ANALOG", "SIGNAL", "测量", "信号")):
        return "测量/信号"
    if any(token in text for token in ("LABEL", "TAG", "标识", "标签")):
        return "标签/辅助图元"
    return "设备"




def infer_device_type(*, role: str = "", source_file: str = "", element_tag: str = "", element_id: str = "") -> str:
    """Infer only strong business type names; user-edited standard metadata remains authoritative."""
    seed = " ".join((role, source_file, element_tag, element_id)).upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", seed)
    rules = (
        (("TRANSFORMER",), "Transformer"),
        (("CIRCUIT_BREAKER", "CIRCUITBREAKER"), "Circuit Breaker"),
        (("LOAD_BREAKER_SWITCH", "LOADBREAKERSWITCH", "RMU_LBS"), "LBS"),
        (("GROUND_DISCONNECTOR", "GROUNDDISCONNECTOR", "JIEDIDAOZHA"), "Ground Disconnector"),
        (("RECLOSER", "_REC_", "OREC", "SREC", "AUTO_RECLOSER", "AUTORECLOSER"), "Recloser"),
        (("FUSE", "FZ001"), "Fuse"),
        (("SFI",), "SFI"),
        (("GENERATOR",), "Generator"),
        (("DISCONNECTOR",), "Disconnector"),
        (("BUS",), "Bus"),
    )
    for tokens, label in rules:
        if any(token in normalized for token in tokens):
            return label
    return (role or element_id or element_tag or "自定义图元").strip()

def _migration_device_type_from_values(
    *,
    device_type: str = "",
    standard_file: str = "",
    standard_devref: str = "",
    actual_devref: str = "",
    element_tag: str = "",
) -> str:
    """Normalize profile/business names to stable ADMS-SLD migration categories.

    The original ``设备类型`` is intentionally preserved for compatibility and
    auditability.  This normalized value is a second, migration-oriented view so
    future source comparisons do not need to know every historical spelling used
    by an icon/profile.
    """
    raw_type = (device_type or "").strip()
    seed = " ".join((raw_type, standard_file, standard_devref, actual_devref, element_tag)).upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", seed)
    type_norm = re.sub(r"[^A-Z0-9]+", "_", raw_type.upper()).strip("_")

    if type_norm == "RMU" or re.search(r"(?:^|_)RMU(?:_|$)", normalized):
        # RMU_LBS is a component, not an RMU composite.  Let the LBS rule below win.
        if "RMU_LBS" not in normalized and "LOAD_BREAKER" not in normalized:
            return "RMU"
    if "TRANSFORMER" in normalized:
        return "TRANSFORMER"
    if any(token in normalized for token in ("LOAD_BREAKER_SWITCH", "LOADBREAKERSWITCH", "RMU_LBS")) or type_norm == "LBS":
        return "LBS"
    if "FUSE" in normalized or type_norm == "FUSE":
        return "FUSE"
    if any(token in normalized for token in (
        "RECLOSER", "AUTO_RECLOSER", "AUTORECLOSER", "_REC_", "OREC", "SREC",
    )) or type_norm in {"REC", "RECLOSER", "AUTO_RECLOSER"}:
        return "REC"
    if "SFI" in normalized or type_norm == "SFI":
        return "SFI"
    if any(token in normalized for token in ("CIRCUIT_BREAKER", "CIRCUITBREAKER")) or type_norm in {"CB", "CIRCUIT_BREAKER"}:
        return "CB"
    if any(token in normalized for token in ("GROUND_DISCONNECTOR", "GROUNDDISCONNECTOR", "JIEDIDAOZHA", "JIE_DI_DAO_ZHA")):
        return "GROUND_DISCONNECTOR"
    if "DISCONNECTOR" in normalized:
        return "DISCONNECTOR"
    if "GENERATOR" in normalized:
        return "GENERATOR"
    if "BUS" in normalized and type_norm == "BUS":
        return "BUS"
    if type_norm:
        return type_norm
    return "UNKNOWN"


def _smart_type_from_row(row: dict[str, object]) -> tuple[str, str]:
    """Return (SMART/NORMAL/UNKNOWN, evidence source) for migration output."""
    scope = str(row.get("SMART/NORMAL", "") or "").strip().upper()
    if scope == "SMR":
        scope = "SMART"
    if scope in {"SMART", "NORMAL"}:
        return scope, "Profile/Context"

    seed = " ".join((
        str(row.get("实际devref", "") or ""),
        str(row.get("标准devref", "") or ""),
        str(row.get("标准图元文件", "") or ""),
    )).upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", seed)
    if any(token in normalized for token in ("NON_SMART", "NONSMART", "NO_SMART", "NOSMART")):
        return "NORMAL", "devref"
    if "SMART" in normalized:
        return "SMART", "devref"
    return "UNKNOWN", ""


def _device_form(row: dict[str, object]) -> str:
    # v2.18.126: actual RMU containment is authoritative.  A configured icon may
    # historically be marked as an independent device, but once the concrete G
    # instance is physically resolved inside an RMU frame it is an RMU component
    # for migration inventory purposes and must never be promoted to a main device.
    if str(row.get("所属RMU", "") or "").strip():
        return "RMU_COMPONENT"
    level = str(row.get("设备层级", "") or "").strip()
    if level == "组合设备":
        return "COMPOSITE"
    if level == "设备内部部件":
        return "DEVICE_COMPONENT"
    if level == "独立设备":
        return "STANDALONE"
    return re.sub(r"\s+", "_", level.upper()) if level else "UNKNOWN"


def _is_primary_device_row(row: dict[str, object]) -> bool:
    """Return whether one extracted row is a migration-level main device.

    ParentRMU is the hard boundary: any concrete object assigned to an RMU is an
    internal component, regardless of the profile's historical DeviceLevel value.
    This keeps the detailed audit rows without double-counting RMU internals as
    standalone migration equipment.
    """
    if str(row.get("所属RMU", "") or "").strip():
        return False
    level = str(row.get("设备层级", "") or "").strip()
    usage = str(row.get("图元用途", "") or "").strip()
    return (
        level in {"独立设备", "组合设备"}
        or (usage == "设备" and level != "设备内部部件")
    )



_FEEDER_REPEAT_RE = re.compile(
    r"(?i)\b([A-Z][A-Z0-9]{2,})[\s_-]+0*(\d{1,3})\s+\1[_-]0*\2(?:_|-|\b)"
)
_FEEDER_PAIR_RE = re.compile(
    r"(?i)(?<![A-Z0-9])([A-Z][A-Z0-9]{2,})[\s_-]+0*(\d{1,3})(?![\d.])"
)
# Some device identities use the compact form ``AH330`` rather than the
# space-separated form used by older feeder labels.  This is deliberately a
# separate pattern: it is only used for an orphan component after the
# CBreaker/BAY topology has already been validated.
_COMPACT_FEEDER_TOKEN_RE = re.compile(
    r"(?i)(?<![A-Z0-9])([A-Z]{2,})[-_ ]*0*(\d{1,3})(?!\d)"
)
_NON_DEVICE_FEEDER_TAGS = {
    "ConnectLine", "FeedLine", "Text", "DText", "rect", "line", "image",
    "Status", "pwbh", "poke", "Layer", "Group", "G",
}


def _normalize_feeder_label(code: str, number: str | int) -> str:
    try:
        numeric = int(str(number).strip())
    except (TypeError, ValueError):
        return ""
    code = re.sub(r"[^A-Z0-9]+", "", str(code or "").upper())
    if not code or numeric < 0 or numeric > 999:
        return ""
    width = 2 if numeric < 100 else len(str(numeric))
    return f"{code}-{numeric:0{width}d}"


def _feeder_text(element: ET.Element) -> str:
    return " ".join(
        str(element.get(name) or "")
        for name in ("key_name", "p_EngcodeString", "p_NameString", "aliasType")
    ).strip()


def _feeder_identity_labels(value: str) -> set[str]:
    """Return compact feeder identities such as ``AH330`` from one value."""
    labels: set[str] = set()
    for code, number in _COMPACT_FEEDER_TOKEN_RE.findall(str(value or "")):
        label = _normalize_feeder_label(code, number)
        if label:
            labels.add(re.sub(r"[^A-Z0-9]+", "", label.upper()))
    return labels


def _element_feeder_identity_labels(element: ET.Element) -> set[str]:
    identity_text = " ".join(
        value
        for value in (
            str(element.get("key_name1") or ""),
            str(element.get("key_name2") or ""),
            _feeder_text(element),
        )
        if value
    )
    return _feeder_identity_labels(identity_text)


def _feedline_feeder_labels(element: ET.Element) -> set[str]:
    if local_name(element.tag) != "FeedLine":
        return set()
    text = _feeder_text(element)
    labels = {
        _normalize_feeder_label(code, number)
        for code, number in _FEEDER_REPEAT_RE.findall(text)
    }
    return {label for label in labels if label}


def _generic_feeder_labels(element: ET.Element, valid_prefixes: set[str]) -> set[str]:
    text = _feeder_text(element)
    if not text:
        return set()
    result: set[str] = set()
    for code, number in _FEEDER_PAIR_RE.findall(text):
        code = code.upper()
        if valid_prefixes and code not in valid_prefixes:
            continue
        label = _normalize_feeder_label(code, number)
        if label:
            result.add(label)
    return result


def _topology_refs(value: str) -> list[str]:
    refs: list[str] = []
    for segment in str(value or "").split(";"):
        fields = [field.strip() for field in segment.split(",") if field.strip()]
        if fields and fields[-1].isdigit():
            refs.append(fields[-1])
    return refs


def _build_topology_graph(elements: list[ET.Element]) -> tuple[dict[str, ET.Element], dict[str, set[str]]]:
    """Build the electrical graph from explicit references plus conservative geometry.

    G files are not perfectly uniform across sites.  Most objects carry reciprocal
    ``link/node_area`` references, but some feeder heads contain visually connected
    CBreaker/GroundDisconnector duplicates where one side of the reciprocal reference
    is missing.  For feeder tracing we therefore add *only* conservative electrical
    geometry edges:

    - ConnectLine / FeedLine / ACLine endpoint <-> endpoint (small tolerance)
    - a line endpoint touching another line segment (T-junction)
    - a line endpoint lying inside/at the bounding box of an electrical object

    Interior line crossings are not connected unless an endpoint actually terminates
    there.  Text, frames, images and other presentation objects never participate.
    """
    by_id = {
        (element.get("id") or "").strip(): element
        for element in elements
        if (element.get("id") or "").strip()
    }
    graph: dict[str, set[str]] = defaultdict(set)
    for element_id, element in by_id.items():
        for attr in ("link", "node_area"):
            for ref_id in _topology_refs(element.get(attr) or ""):
                if ref_id in by_id and ref_id != element_id:
                    graph[element_id].add(ref_id)
                    graph[ref_id].add(element_id)

    line_tags = {"ConnectLine", "FeedLine", "ACLine"}
    excluded_object_tags = {
        "Text", "DText", "rect", "ellipse", "image", "poke", "Status", "pwbh",
        "Merge", "G", "Layer", "Theme", "Color", "Font", "Item",
    }
    point_re = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")

    line_points: dict[str, list[tuple[float, float]]] = {}
    for element_id, element in by_id.items():
        if local_name(element.tag) not in line_tags:
            continue
        points = [(float(x), float(y)) for x, y in point_re.findall(element.get("d") or "")]
        if len(points) >= 2:
            line_points[element_id] = points

    # Small endpoint hash: reconnect exact/small-gap line fragments without ever
    # joining arbitrary nearby parallel lines.
    endpoint_tolerance = 3.0
    endpoint_cell = 6.0
    endpoint_index: dict[tuple[int, int], list[tuple[str, float, float]]] = defaultdict(list)
    endpoints: list[tuple[str, float, float]] = []
    for line_id, points in line_points.items():
        for x, y in (points[0], points[-1]):
            endpoints.append((line_id, x, y))
            endpoint_index[(math.floor(x / endpoint_cell), math.floor(y / endpoint_cell))].append((line_id, x, y))
    for line_id, x, y in endpoints:
        cx, cy = math.floor(x / endpoint_cell), math.floor(y / endpoint_cell)
        for gx in range(cx - 1, cx + 2):
            for gy in range(cy - 1, cy + 2):
                for other_id, ox, oy in endpoint_index.get((gx, gy), ()):
                    if other_id == line_id:
                        continue
                    if (x - ox) ** 2 + (y - oy) ** 2 <= endpoint_tolerance ** 2:
                        graph[line_id].add(other_id)
                        graph[other_id].add(line_id)

    # Segment hash supports endpoint -> segment T-junctions.  We intentionally do
    # not connect segment-interior to segment-interior crossings.
    segment_cell = 64.0
    segment_index: dict[tuple[int, int], list[tuple[str, float, float, float, float]]] = defaultdict(list)
    for line_id, points in line_points.items():
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            min_x, max_x = sorted((x1, x2))
            min_y, max_y = sorted((y1, y2))
            gx0, gx1 = math.floor((min_x - endpoint_tolerance) / segment_cell), math.floor((max_x + endpoint_tolerance) / segment_cell)
            gy0, gy1 = math.floor((min_y - endpoint_tolerance) / segment_cell), math.floor((max_y + endpoint_tolerance) / segment_cell)
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    segment_index[(gx, gy)].append((line_id, x1, y1, x2, y2))

    def point_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return math.hypot(px - x1, py - y1)
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        qx, qy = x1 + t * dx, y1 + t * dy
        return math.hypot(px - qx, py - qy)

    for line_id, x, y in endpoints:
        cell = (math.floor(x / segment_cell), math.floor(y / segment_cell))
        for other_id, x1, y1, x2, y2 in segment_index.get(cell, ()):
            if other_id == line_id:
                continue
            if point_segment_distance(x, y, x1, y1, x2, y2) <= endpoint_tolerance:
                graph[line_id].add(other_id)
                graph[other_id].add(line_id)

    # Electrical-object bounding boxes.  An endpoint landing inside a symbol is a
    # strong terminal signal even if the source forgot the reciprocal node_area.
    # This is what repairs feeder-head examples where the DB-linked duplicate icon
    # is visually connected but missing one XML reference.
    object_cell = 64.0
    object_index: dict[tuple[int, int], list[tuple[str, float, float, float, float]]] = defaultdict(list)
    object_margin = 2.0
    for element_id, element in by_id.items():
        tag = local_name(element.tag)
        if tag in line_tags or tag in excluded_object_tags:
            continue
        if not any((element.get("keyid"), element.get("devref"), element.get("node_area"), element.get("link"))) and tag not in {"Bus", "BusDis"}:
            continue
        try:
            x = float(element.get("x") or 0)
            y = float(element.get("y") or 0)
            w = float(element.get("w") or 0)
            h = float(element.get("h") or 0)
        except (TypeError, ValueError):
            continue
        if w <= 0 and h <= 0:
            continue
        x1, y1 = x - object_margin, y - object_margin
        x2, y2 = x + max(w, 1.0) + object_margin, y + max(h, 1.0) + object_margin
        gx0, gx1 = math.floor(x1 / object_cell), math.floor(x2 / object_cell)
        gy0, gy1 = math.floor(y1 / object_cell), math.floor(y2 / object_cell)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                object_index[(gx, gy)].append((element_id, x1, y1, x2, y2))

    for line_id, x, y in endpoints:
        cell = (math.floor(x / object_cell), math.floor(y / object_cell))
        for object_id, x1, y1, x2, y2 in object_index.get(cell, ()):
            if object_id == line_id:
                continue
            if x1 <= x <= x2 and y1 <= y <= y2:
                graph[line_id].add(object_id)
                graph[object_id].add(line_id)

    return by_id, graph


@dataclass
class _FeederRootBranch:
    """One electrical branch below a station Bus.

    The nearest associated CBreaker below the Bus is the database feeder head.
    Every other non-Bus object in ``node_ids`` is downstream topology and must
    inherit that CBreaker's BAY. Disconnector/GroundDisconnector are ordinary
    downstream objects rather than required feeder roots.
    """

    branch_id: str
    bus_ids: tuple[str, ...]
    entry_nodes: tuple[str, ...]
    node_ids: frozenset[str]
    anchor_nodes: dict[str, str]
    anchor_keyids: dict[str, str]


def _discover_feeder_root_branches(elements: list[ET.Element]) -> list[_FeederRootBranch]:
    """Discover feeder branches from station Bus -> top CBreaker(407).

    The station ``Bus`` is used only to find where a feeder starts.  It is removed
    from the downstream graph, so traversal cannot run sideways along the common
    bus into another feeder.  ``BusDis`` remains an ordinary traversable topology
    node because it is the internal bus inside RMUs.

    A branch becomes DB-queryable when its Bus-side connected component contains a
    CBreaker. If several CBreakers occur in that component, only the instance
    nearest to the Bus entry is selected. Downstream CBreakers are not queried.
    """
    by_id, graph = _build_topology_graph(elements)
    bus_ids = {
        element_id
        for element_id, element in by_id.items()
        if local_name(element.tag) == "Bus"
    }
    anchor_table_by_tag = {"CBreaker": "BREAKER"}

    # Build connected components with station Bus nodes removed. This naturally
    # follows ConnectLine / FeedLine / BusDis chains to their real terminal while
    # keeping different Bus branches from joining sideways.
    non_bus_nodes = set(by_id) - bus_ids
    components: list[set[str]] = []
    seen: set[str] = set()
    for node in sorted(non_bus_nodes):
        if node in seen:
            continue
        stack = [node]
        component = {node}
        seen.add(node)
        while stack:
            current = stack.pop()
            for neighbour in sorted(graph.get(current, ())):
                if neighbour in bus_ids or neighbour in component:
                    continue
                component.add(neighbour)
                seen.add(neighbour)
                stack.append(neighbour)
        components.append(component)

    result: list[_FeederRootBranch] = []
    for index, component in enumerate(components, start=1):
        adjacent_buses = sorted({
            neighbour
            for node in component
            for neighbour in graph.get(node, ())
            if neighbour in bus_ids
        })
        entry_nodes = sorted({
            node
            for node in component
            if any(neighbour in bus_ids for neighbour in graph.get(node, ()))
        })
        if not entry_nodes:
            # A few G files omit the station-Bus reference entirely. CBreaker is
            # still a valid root in that case, but only a single root is accepted
            # so two disconnected feeder identities are never guessed together.
            isolated_roots = [
                node for node in component
                if local_name(by_id[node].tag) == "CBreaker"
            ]
            if len(isolated_roots) != 1:
                continue
            entry_nodes = isolated_roots

        # Distance from the Bus-side attachment. Select the first CBreaker, never
        # an arbitrary downstream CBreaker as a second database root.
        distances: dict[str, int] = {}
        queue = list(entry_nodes)
        for node in queue:
            distances[node] = 0
        head = 0
        while head < len(queue):
            current = queue[head]
            head += 1
            for neighbour in graph.get(current, ()):
                if neighbour in bus_ids or neighbour not in component or neighbour in distances:
                    continue
                distances[neighbour] = distances[current] + 1
                queue.append(neighbour)

        candidates: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for node in component:
            element = by_id.get(node)
            if element is None:
                continue
            table = anchor_table_by_tag.get(local_name(element.tag))
            if table:
                candidates[table].append((distances.get(node, 10**9), node))

        ranked = sorted(candidates.get("BREAKER", []), key=lambda item: (item[0], item[1]))
        if not ranked:
            # Auxiliary/PT branches and branches without a CBreaker are not feeder roots.
            continue
        best_distance = ranked[0][0]
        tied = [node for distance, node in ranked if distance == best_distance]
        if len(tied) > 1:
            # Some Saudi total drawings contain an overlaid legacy copy of the
            # feeder-head icon. The DB-linked copy has keyid/key_name while the
            # visual duplicate is blank. Prefer that uniquely linked copy; do not
            # guess when two linked copies remain.
            linked = [
                node for node in tied
                if str(by_id[node].get("keyid") or "").strip()
            ]
            if len(linked) == 1:
                tied = linked
            elif len(linked) > 1:
                named = [
                    node for node in linked
                    if str(by_id[node].get("key_name") or "").strip()
                ]
                if len(named) == 1:
                    tied = named
        if len(tied) != 1:
            continue
        anchor_nodes = {"BREAKER": tied[0]}

        anchor_keyids = {
            table: str(by_id[node].get("keyid") or "").strip()
            for table, node in anchor_nodes.items()
        }
        branch_id = (
            f"BUS:{','.join(adjacent_buses)}:BR:{index}"
            if adjacent_buses
            else f"NO_BUS:CB:{tied[0]}:BR:{index}"
        )
        result.append(_FeederRootBranch(
            branch_id=branch_id,
            bus_ids=tuple(adjacent_buses),
            entry_nodes=tuple(entry_nodes),
            node_ids=frozenset(component),
            anchor_nodes=anchor_nodes,
            anchor_keyids=anchor_keyids,
        ))

    return result


def _feeder_anchor_keyids_for_db(elements: list[ET.Element]) -> dict[str, list[str]]:
    """Return only Bus-head CBreaker(407) keyids that are allowed to hit Oracle."""
    result = {"BREAKER": [], "DISCONNECTOR": [], "GROUNDDISCONNECTOR": []}
    seen: dict[str, set[str]] = {table: set() for table in result}
    for branch in _discover_feeder_root_branches(elements):
        for table in result:
            keyid = str(branch.anchor_keyids.get(table, "") or "").strip()
            if keyid and keyid not in seen[table]:
                seen[table].add(keyid)
                result[table].append(keyid)
    return result


def _learn_feeder_dictionary(elements: list[ET.Element]) -> tuple[set[str], set[str]]:
    """Learn valid feeder labels/prefixes from electrical objects, never file metadata.

    FeedLine identities are the strongest vocabulary seed.  If a drawing has no
    usable FeedLine identity, repeated device evidence (>=3 concrete devices) seeds
    the vocabulary instead.  This deliberately excludes file name/facID/facName and
    free-standing header Text from feeder assignment.
    """
    feedline_labels: set[str] = set()
    prefix_counter: Counter[str] = Counter()
    for element in elements:
        for label in _feedline_feeder_labels(element):
            feedline_labels.add(label)
            prefix_counter[label.split("-", 1)[0]] += 1

    valid_prefixes = set(prefix_counter)
    if valid_prefixes:
        return feedline_labels, valid_prefixes

    # Fallback for sites whose G files do not encode feeder identity on FeedLine:
    # accept only prefixes repeated by at least three device-like XML objects.
    raw_pairs: list[tuple[str, str]] = []
    candidate_prefixes: Counter[str] = Counter()
    for element in elements:
        if local_name(element.tag) in _NON_DEVICE_FEEDER_TAGS:
            continue
        for code, number in _FEEDER_PAIR_RE.findall(_feeder_text(element)):
            label = _normalize_feeder_label(code, number)
            if not label:
                continue
            prefix = label.split("-", 1)[0]
            raw_pairs.append((prefix, label))
            candidate_prefixes[prefix] += 1
    valid_prefixes = {prefix for prefix, count in candidate_prefixes.items() if count >= 3}
    return {label for prefix, label in raw_pairs if prefix in valid_prefixes}, valid_prefixes


def _feeder_row_center(row: dict[str, object]) -> tuple[float, float]:
    def number(name: str) -> float:
        try:
            return float(row.get(name, 0) or 0)
        except (TypeError, ValueError):
            return 0.0
    return number("x") + number("w") / 2.0, number("y") + number("h") / 2.0


def _empty_feeder_fields(row: dict[str, object]) -> None:
    row["所属馈线"] = ""
    row["馈线判断来源"] = "NO_DEVICE_EVIDENCE"
    row["馈线置信度"] = ""
    row["馈线证据设备数"] = 0
    row["馈线Cluster"] = ""
    row["馈线冲突"] = ""


def _set_feeder_fields(
    row: dict[str, object],
    feeder: str,
    source: str,
    confidence: str,
    evidence_count: int,
    *,
    conflict: str = "",
) -> None:
    row["所属馈线"] = feeder
    row["馈线判断来源"] = source
    row["馈线置信度"] = confidence
    row["馈线证据设备数"] = int(evidence_count or 0)
    row["馈线Cluster"] = f"FC:{feeder}" if feeder else ""
    row["馈线冲突"] = conflict


def _infer_feeder_membership(
    *,
    elements: list[ET.Element],
    contexts: list[_RmuContext],
    device_rows: list[dict[str, object]],
    symbol_rows: list[dict[str, object]],
    unmapped_rows: list[dict[str, object]] | None = None,
    anchor_contexts: dict[tuple[str, str], TopologyFeederAnchorContext] | None = None,
    anchor_issues: dict[tuple[str, str], str] | None = None,
    database_lookup_enabled: bool = False,
    feeder_root_branches: list[_FeederRootBranch] | None = None,
) -> dict[str, object]:
    """Assign feeder ownership from each CBreaker's BAY through topology.

    Final field rule (v2.18.146):

    1. ``Bus`` is only the starting boundary used to split the drawing into feeder
       branches.  We never derive the feeder name from Bus metadata.
    2. In each Bus-side branch, only the nearest CBreaker(407) may query Oracle.
       No downstream device keyid is queried, including CBreaker-like devices.
    3. CBreaker(407) is the only feeder root. If its BAY is missing or unresolved,
       that branch remains blank; no other device can substitute for it.
    4. Once the branch has a feeder seed, *every* downstream topology object reachable
       below that Bus entry inherits the feeder through ConnectLine / FeedLine /
       BusDis and device nodes until the component's natural topology terminal.
       Downstream keyid/DB association state is completely irrelevant.
    5. Bus itself is excluded from ownership assignment. For a genuinely isolated
       component, a compact device identity such as ``AH330`` may be used only when
       it matches exactly one already-validated CBreaker BAY feeder. This is an
       explicit, auditable fallback; spatial, facID/facName, filename and generic
       FeedLine-text guessing remain forbidden.
    """
    anchor_contexts = dict(anchor_contexts or {})
    anchor_issues = dict(anchor_issues or {})
    warnings: list[str] = []
    all_assignable_rows = (*device_rows, *symbol_rows, *(unmapped_rows or []))
    for row in all_assignable_rows:
        _empty_feeder_fields(row)
        row["馈线判断来源"] = "NO_DB_TOPOLOGY_EVIDENCE"
        row["馈线站名"] = ""
        row["馈线BayID"] = ""
        row["馈线锚点表"] = ""
        row["馈线锚点keyid"] = ""

    by_id, _graph = _build_topology_graph(elements)
    branches = list(feeder_root_branches or _discover_feeder_root_branches(elements))
    context_by_rect = {context.rect_id: context for context in contexts if context.rect_id}

    if database_lookup_enabled and not branches:
        anchor_like_count = sum(
            1
            for element in elements
            if local_name(element.tag) in {"CBreaker", "Disconnector", "GroundDisconnector"}
        )
        if anchor_like_count:
            for row in all_assignable_rows:
                row["馈线判断来源"] = "NO_DB_CBREAKER_ANCHOR"
            warnings.append(
                "所属馈线未分析：没有识别到 Bus 下的 CBreaker(407) 馈线入口。"
                "FeederName 保持空白；"
                "请优先确认 CBreaker 及其连接关系。"
            )
            primary_total = sum(1 for row in device_rows if _is_primary_device_row(row))
            return {
                "feeder_count": 0,
                "primary_total": primary_total,
                "primary_resolved": 0,
                "direct_anchor_count": 0,
                "unresolved": primary_total,
                "anchor_total": 0,
                "anchor_unresolved": 0,
                "validated_bay_count": 0,
                "feeder_root_branch_count": 0,
                "element_feeder_fields": {},
                "warnings": warnings,
            }

    members_by_rect: dict[str, list[ET.Element]] = defaultdict(list)
    if contexts:
        for element in elements:
            if local_name(element.tag) == "rect":
                continue
            matches = [context for context in contexts if _center_inside(element, context.rect)]
            if matches:
                context = min(
                    matches,
                    key=lambda item: max(1.0, _float(item.rect, "w") * _float(item.rect, "h")),
                )
                members_by_rect[context.rect_id].append(element)

    def associated_node_ids(row: dict[str, object]) -> set[str]:
        element_id = str(row.get("ElementID", "") or "").strip()
        if (
            str(row.get("迁移设备类型", "") or row.get("设备类型", "")).upper() == "RMU"
            and element_id in context_by_rect
        ):
            return {
                str(element.get("id") or "").strip()
                for element in members_by_rect.get(element_id, [])
                if str(element.get("id") or "").strip()
            }
        return {element_id} if element_id and element_id in by_id else set()

    def feeder_display_name(ctx: TopologyFeederAnchorContext) -> str:
        station = str(ctx.station_name or "").strip()
        feeder = str(ctx.feeder_name or "").strip()
        return f"{station} {feeder}".strip() if station and feeder else (station or feeder)

    # Validate branch heads. Only the selected *top* CBreaker(407) keyids are ever
    # consulted. Downstream elements, including downstream CBreaker instances, are
    # topology-only and never hit Oracle.
    valid_branches: list[tuple[_FeederRootBranch, TopologyFeederAnchorContext, int]] = []
    anchor_total = 0
    anchor_unresolved = 0
    for branch in branches:
        branch_contexts: list[TopologyFeederAnchorContext] = []
        branch_failures: list[str] = []
        for table in ("BREAKER",):
            anchor_total += 1
            keyid = str(branch.anchor_keyids.get(table, "") or "").strip()
            if not keyid:
                anchor_unresolved += 1
                branch_failures.append(f"{table}: keyid为空")
                continue
            ctx = anchor_contexts.get((table, keyid))
            if ctx is None:
                anchor_unresolved += 1
                detail = anchor_issues.get((table, keyid), "数据库未关联")
                branch_failures.append(f"{table}: {detail}")
                continue
            branch_contexts.append(ctx)

        # An unassociated CBreaker is the explicit exception: without its BAY there
        # is no safe feeder seed, so this branch remains blank.
        if not branch_contexts:
            if database_lookup_enabled:
                warnings.append(
                    f"馈线入口 {branch.branch_id} 未建立：顶部 CBreaker(407) 未取得有效 BAY。"
                    f"{'；'.join(branch_failures)}。该入口以下 FeederName 留空，请优先完成入口设备关联。"
                )
            continue

        # The feeder-head CBreaker is the authoritative root. Its Bus-side terminal
        # is upstream and the whole Bus-removed component owns the opposite side.
        by_table_ctx = {str(ctx.table_name or "").upper(): ctx for ctx in branch_contexts}
        breaker_ctx = by_table_ctx.get("BREAKER")

        selected_ctx = breaker_ctx
        evidence_count = 1

        station = str(selected_ctx.station_name or "").strip() if selected_ctx else ""
        feeder = str(selected_ctx.feeder_name or "").strip() if selected_ctx else ""
        if not selected_ctx or not str(selected_ctx.bay_id or "").strip() or not station or not feeder:
            if database_lookup_enabled:
                warnings.append(
                    f"馈线入口 {branch.branch_id} 未建立：BAY/SUBSTATION 名称为空，"
                    "该入口以下 FeederName 留空。"
                )
            continue

        valid_branches.append((branch, selected_ctx, evidence_count))
        if database_lookup_enabled and branch_failures:
            warnings.append(f"馈线入口 {branch.branch_id} 已由 CBreaker(407) 确认 {station} {feeder}；"
                            f"其他非根设备不参与 BAY 关联。{'；'.join(branch_failures)}")

    if database_lookup_enabled and branches and not valid_branches:
        warnings.append(
            "所属馈线未分析：所有 Bus 入口均没有可用的 CBreaker(407) BAY 锚点，"
            "或已关联锚点存在 BAY 冲突。请优先完成入口设备关联；文件其他内容继续解析。"
        )

    # A node belongs to exactly one Bus-removed connected component in a valid
    # drawing.  Map every downstream topology node to its validated feeder branch.
    branch_by_node: dict[str, tuple[_FeederRootBranch, TopologyFeederAnchorContext, int]] = {}
    topology_conflicts: set[str] = set()
    for branch, ctx, evidence_count in valid_branches:
        for node in branch.node_ids:
            existing = branch_by_node.get(node)
            if existing is None:
                branch_by_node[node] = (branch, ctx, evidence_count)
                continue
            if str(existing[1].bay_id or "") != str(ctx.bay_id or ""):
                topology_conflicts.add(node)
                branch_by_node.pop(node, None)

    # A small number of real G files contain a device pair whose local
    # ConnectLine component is detached from the rest of the drawing. Do not
    # assign it by proximity. Instead, use the device's own compact feeder
    # identity only when that identity maps to exactly one validated CBreaker
    # feeder in this file. This fixes cases such as TransformerDis 99959/99960
    # (key_name1 contains AH330) while keeping genuinely unknown orphan objects
    # blank and visible for topology repair.
    identity_fallback_nodes: set[str] = set()
    bus_ids = {
        element_id
        for element_id, element in by_id.items()
        if local_name(element.tag) == "Bus"
    }
    validated_by_identity: dict[str, list[tuple[_FeederRootBranch, TopologyFeederAnchorContext, int]]] = defaultdict(list)
    for assignment in valid_branches:
        branch, ctx, evidence_count = assignment
        # The context is not a G object, so use its feeder name directly in the
        # compact-token parser.
        identities = _feeder_identity_labels(str(ctx.feeder_name or ""))
        for identity in identities:
            validated_by_identity[identity].append(assignment)

    assigned_nodes = set(branch_by_node)
    orphan_nodes = set(by_id) - bus_ids - assigned_nodes - topology_conflicts
    seen_orphan: set[str] = set()
    for start in sorted(orphan_nodes):
        if start in seen_orphan:
            continue
        component: set[str] = {start}
        stack = [start]
        seen_orphan.add(start)
        while stack:
            current = stack.pop()
            for neighbour in sorted(_graph.get(current, ())):
                if neighbour in bus_ids or neighbour in assigned_nodes or neighbour in topology_conflicts or neighbour in seen_orphan:
                    continue
                seen_orphan.add(neighbour)
                component.add(neighbour)
                stack.append(neighbour)

        # Require a concrete device identity in the component. A line-only
        # fragment must stay unresolved rather than inheriting a nearby feeder.
        component_labels: set[str] = set()
        for node in component:
            element = by_id.get(node)
            if element is None or local_name(element.tag) in _NON_DEVICE_FEEDER_TAGS:
                continue
            component_labels.update(_element_feeder_identity_labels(element))
        candidates = {
            id(assignment): assignment
            for label in component_labels
            for assignment in validated_by_identity.get(label, ())
        }
        if len(candidates) != 1:
            continue
        branch, ctx, evidence_count = next(iter(candidates.values()))
        matched_labels = component_labels & _feeder_identity_labels(str(ctx.feeder_name or ""))
        if len(matched_labels) != 1:
            continue
        matched_label = next(iter(matched_labels))
        for node in component:
            branch_by_node[node] = (branch, ctx, evidence_count)
            identity_fallback_nodes.add(node)
        warnings.append(
            f"孤立拓扑组件 {','.join(sorted(component))} 未直接连接 CBreaker；"
            f"依据设备标识 {matched_label} 唯一匹配已确认馈线 {ctx.feeder_name}，"
            "已归入该馈线，判断来源为设备标识兜底。"
        )

    def apply_branch(
        row: dict[str, object],
        branch: _FeederRootBranch,
        ctx: TopologyFeederAnchorContext,
        evidence_count: int,
        *,
        direct: bool = False,
        identity_fallback: bool = False,
    ) -> None:
        evidence_count = max(1, int(evidence_count or 0))
        source = (
            "DB_CBREAKER_FEEDER_IDENTITY"
            if identity_fallback
            else ("DB_CBREAKER_BAY" if direct else "DB_CBREAKER_TOPOLOGY")
        )
        _set_feeder_fields(
            row,
            feeder_display_name(ctx),
            source,
            "MEDIUM" if identity_fallback else "HIGH",
            evidence_count,
        )
        row["馈线站名"] = ctx.station_name
        row["馈线BayID"] = ctx.bay_id
        row["馈线锚点表"] = "BREAKER(407)"
        row["馈线锚点keyid"] = "/".join(
            str(branch.anchor_keyids.get(table, "") or "")
            for table in ("BREAKER",)
        )
        row["馈线Cluster"] = f"FC:{ctx.station_name}:{ctx.feeder_name}"

    primary_rows = [row for row in device_rows if _is_primary_device_row(row)]
    primary_row_ids = {id(row) for row in primary_rows}
    rmu_by_name: dict[str, dict[str, object]] = {}

    for row in primary_rows:
        nodes = associated_node_ids(row)
        candidates = {
            id(branch): (branch, ctx, evidence_count)
            for node in nodes
            if node not in topology_conflicts
            for branch, ctx, evidence_count in ([branch_by_node[node]] if node in branch_by_node else [])
        }
        if len(candidates) != 1:
            if len(candidates) > 1:
                row["馈线判断来源"] = "DB_TOPOLOGY_CONFLICT"
            continue
        branch, ctx, evidence_count = next(iter(candidates.values()))
        direct_nodes = set(branch.anchor_nodes.values())
        apply_branch(
            row,
            branch,
            ctx,
            evidence_count,
            direct=bool(nodes & direct_nodes),
            identity_fallback=bool(nodes & identity_fallback_nodes),
        )
        if str(row.get("迁移设备类型", "") or row.get("设备类型", "")).upper() == "RMU":
            name = str(row.get("实例名称", "") or "").strip()
            if name:
                rmu_by_name[name] = row

    # RMU internal parts inherit the composite RMU.  Every other downstream detail
    # row is assigned strictly by membership in the validated Bus-root component;
    # its keyid/DB association is intentionally irrelevant.
    for row in device_rows:
        if id(row) in primary_row_ids:
            continue
        parent_name = str(row.get("所属RMU", "") or "").strip()
        parent = rmu_by_name.get(parent_name)
        if parent and str(parent.get("所属馈线", "") or "").strip():
            _set_feeder_fields(
                row,
                str(parent.get("所属馈线", "") or ""),
                "PARENT_RMU",
                str(parent.get("馈线置信度", "") or "HIGH"),
                int(parent.get("馈线证据设备数", 0) or 0),
            )
            for field in ("馈线站名", "馈线BayID", "馈线锚点表", "馈线锚点keyid", "馈线Cluster"):
                row[field] = parent.get(field, "")
            continue
        nodes = associated_node_ids(row)
        candidates = {
            id(branch): (branch, ctx, evidence_count)
            for node in nodes
            if node not in topology_conflicts
            for branch, ctx, evidence_count in ([branch_by_node[node]] if node in branch_by_node else [])
        }
        if len(candidates) == 1:
            branch, ctx, evidence_count = next(iter(candidates.values()))
            apply_branch(
                row,
                branch,
                ctx,
                evidence_count,
                direct=False,
                identity_fallback=bool(nodes & identity_fallback_nodes),
            )

    detail_by_element = {
        str(row.get("ElementID", "") or "").strip(): row
        for row in device_rows
        if str(row.get("ElementID", "") or "").strip()
    }
    for row in symbol_rows:
        element_id = str(row.get("ElementID", "") or "").strip()
        source_row = detail_by_element.get(element_id)
        if source_row is None:
            source_row = rmu_by_name.get(str(row.get("所属RMU", "") or "").strip())
        if source_row and str(source_row.get("所属馈线", "") or "").strip():
            _set_feeder_fields(
                row,
                str(source_row.get("所属馈线", "") or ""),
                str(source_row.get("馈线判断来源", "") or ""),
                str(source_row.get("馈线置信度", "") or "HIGH"),
                int(source_row.get("馈线证据设备数", 0) or 0),
            )
            for field in ("馈线站名", "馈线BayID", "馈线锚点表", "馈线锚点keyid", "馈线Cluster"):
                row[field] = source_row.get(field, "")

    # Unmapped objects still belong to the electrical topology. Keep their feeder
    # fields populated for the audit sheet; their symbol classification remains
    # unresolved and is not changed here.
    for row in unmapped_rows or []:
        nodes = associated_node_ids(row)
        candidates = {
            id(branch): (branch, ctx, evidence_count)
            for node in nodes
            if node not in topology_conflicts
            for branch, ctx, evidence_count in ([branch_by_node[node]] if node in branch_by_node else [])
        }
        if len(candidates) == 1:
            branch, ctx, evidence_count = next(iter(candidates.values()))
            apply_branch(
                row,
                branch,
                ctx,
                evidence_count,
                direct=bool(nodes & set(branch.anchor_nodes.values())),
                identity_fallback=bool(nodes & identity_fallback_nodes),
            )

    # Keep the topology result available to the complete XML inventory.  This is
    # intentionally keyed by element id rather than by parsed device rows: lines,
    # BusDis, text annotations and unrecognised graphic objects must inherit the
    # same CBreaker BAY as long as they are electrically attached to that branch.
    element_feeder_fields: dict[str, dict[str, object]] = {}
    for node, assignment in branch_by_node.items():
        if node in topology_conflicts:
            continue
        _branch, ctx, evidence_count = assignment
        identity_fallback = node in identity_fallback_nodes
        element_feeder_fields[node] = {
            "所属馈线": feeder_display_name(ctx),
            "馈线站名": ctx.station_name,
            "馈线BayID": ctx.bay_id,
            "馈线判断来源": "DB_CBREAKER_FEEDER_IDENTITY" if identity_fallback else "DB_CBREAKER_TOPOLOGY",
            "馈线置信度": "MEDIUM" if identity_fallback else "HIGH",
            "馈线证据设备数": evidence_count,
            "馈线锚点表": "BREAKER(407)",
            "馈线锚点keyid": str(_branch.anchor_keyids.get("BREAKER", "") or ""),
            "馈线Cluster": f"FC:{ctx.station_name}:{ctx.feeder_name}",
            "馈线冲突": "",
        }

    resolved_count = sum(1 for row in primary_rows if str(row.get("所属馈线", "") or "").strip())
    feeder_names = {
        str(row.get("所属馈线", "") or "").strip()
        for row in primary_rows
        if str(row.get("所属馈线", "") or "").strip()
    }
    return {
        "feeder_count": len(feeder_names),
        "primary_total": len(primary_rows),
        "primary_resolved": resolved_count,
        "direct_anchor_count": sum(item[2] for item in valid_branches),
        "unresolved": len(primary_rows) - resolved_count,
        "anchor_total": anchor_total,
        "anchor_unresolved": anchor_unresolved,
        "validated_bay_count": len(valid_branches),
        "feeder_root_branch_count": len(branches),
        "element_feeder_fields": element_feeder_fields,
        "warnings": warnings,
    }

def _migration_device_row(row: dict[str, object]) -> dict[str, object]:
    migration_type = _migration_device_type_from_values(
        device_type=str(row.get("设备类型", "") or ""),
        standard_file=str(row.get("标准图元文件", "") or ""),
        standard_devref=str(row.get("标准devref", "") or ""),
        actual_devref=str(row.get("实际devref", "") or ""),
        element_tag=str(row.get("XML元素", "") or ""),
    )
    smart_type, smart_source = _smart_type_from_row(row)
    device_name = str(row.get("实例名称", "") or "").strip()
    confidence = str(row.get("名称置信度", "") or "").strip().upper()
    validation = str(row.get("标准校验", "") or "").strip().upper()
    if not device_name:
        quality = "FAIL:NAME_MISSING"
    elif migration_type == "UNKNOWN":
        quality = "FAIL:TYPE_UNKNOWN"
    elif validation == "MISMATCH":
        quality = "WARN:SYMBOL_MISMATCH"
    elif confidence == "LOW":
        quality = "WARN:LOW_NAME_CONFIDENCE"
    else:
        quality = "PASS"
    return {
        "GFile": row.get("GFile", ""),
        "facID": row.get("facID", ""),
        "facName": row.get("facName", ""),
        "FeederName": row.get("所属馈线", ""),
        "FeederStation": row.get("馈线站名", ""),
        "FeederBayID": row.get("馈线BayID", ""),
        "FeederSource": row.get("馈线判断来源", ""),
        "FeederConfidence": row.get("馈线置信度", ""),
        "FeederEvidenceCount": row.get("馈线证据设备数", 0),
        "FeederAnchorTable": row.get("馈线锚点表", ""),
        "FeederAnchorKeyID": row.get("馈线锚点keyid", ""),
        "FeederCluster": row.get("馈线Cluster", ""),
        "FeederConflict": row.get("馈线冲突", ""),
        "DeviceType": migration_type,
        "DeviceName": device_name,
        "IsSmart": "YES" if smart_type == "SMART" else ("NO" if smart_type == "NORMAL" else ""),
        "SmartType": smart_type,
        "SmartSource": smart_source,
        "DeviceForm": _device_form(row),
        "ParentRMU": row.get("所属RMU", ""),
        "RMUType": row.get("RMU类型", ""),
        "DeviceSubtype": row.get("设备子类型", ""),
        "ProfileDeviceType": row.get("设备类型", ""),
        "XML Element": row.get("XML元素", ""),
        "ElementID": row.get("ElementID", ""),
        "keyid": row.get("keyid", ""),
        "key_name": row.get("key_name", ""),
        "key_name1": row.get("key_name1", ""),
        "key_name2": row.get("key_name2", ""),
        "p_NameString": row.get("p_NameString", ""),
        "p_EngcodeString": row.get("p_EngcodeString", ""),
        "link": row.get("link", ""),
        "node_area": row.get("node_area", ""),
        "StandardFile": row.get("标准图元文件", ""),
        "StandardDevref": row.get("标准devref", ""),
        "ActualDevref": row.get("实际devref", ""),
        "SymbolValidation": row.get("标准校验", ""),
        "ValidationIssue": row.get("异常类型", ""),
        "NameSource": row.get("名称来源", ""),
        "NameConfidence": row.get("名称置信度", ""),
        "DisplayLabel": row.get("图中文字标签", ""),
        "DisplayLabelDistance": row.get("标签距离", ""),
        "QualityStatus": quality,
        "x": row.get("x", ""),
        "y": row.get("y", ""),
        "w": row.get("w", ""),
        "h": row.get("h", ""),
    }


def _migration_type_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, Counter] = defaultdict(Counter)
    files: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        dtype = str(row.get("DeviceType", "") or "UNKNOWN")
        groups[dtype]["total"] += 1
        if str(row.get("DeviceName", "") or "").strip():
            groups[dtype]["named"] += 1
        if str(row.get("IsSmart", "") or "") == "YES":
            groups[dtype]["smart"] += 1
        elif str(row.get("IsSmart", "") or "") == "NO":
            groups[dtype]["normal"] += 1
        else:
            groups[dtype]["unknown_smart"] += 1
        if str(row.get("QualityStatus", "") or "") == "PASS":
            groups[dtype]["pass"] += 1
        files[dtype].add(str(row.get("GFile", "") or ""))
    return [
        {
            "DeviceType": dtype,
            "Count": counts["total"],
            "Named": counts["named"],
            "SMART": counts["smart"],
            "NORMAL": counts["normal"],
            "SmartUnknown": counts["unknown_smart"],
            "QualityPASS": counts["pass"],
            "Files": len(files[dtype]),
        }
        for dtype, counts in sorted(groups.items(), key=lambda item: (-item[1]["total"], item[0]))
    ]


def default_device_level(symbol_usage: str) -> str:
    if symbol_usage == "设备":
        return "独立设备"
    if symbol_usage == "设备组成图元":
        return "设备内部部件"
    if symbol_usage in {"状态图元", "测量/信号", "标签/辅助图元", "Poke/跳转"}:
        return "辅助关联"
    return "不计入设备"


@dataclass(frozen=True)
class StandardDefinition:
    uid: str
    scope: str
    symbol_usage: str
    device_type: str
    device_subtype: str
    device_level: str
    element_tag: str
    standard_devref: str
    standard_file: str
    match_attr: str
    match_value: str
    builtin_role: str = ""
    classification_marker: str = ""


@dataclass(frozen=True)
class _RmuContext:
    name: str
    rmu_type: str
    scope: str
    rect_id: str
    rect: ET.Element


_OBSERVED_TAG_DEVICE_FALLBACKS: dict[str, tuple[str, str, str, str]] = {
    # tag: (symbol usage, business type, subtype, device level)
    "TransformerDis": ("设备", "Transformer", "", "独立设备"),
    "Transformer2": ("设备", "Transformer", "", "独立设备"),
    "PT": ("设备", "VT", "", "独立设备"),
    "Capacitor": ("设备", "Capacitor", "", "独立设备"),
    "CBreaker": ("设备", "Circuit Breaker", "", "独立设备"),
    "Disconnector": ("设备", "Disconnector", "", "独立设备"),
    "GroundDisconnector": ("设备", "Ground Disconnector", "", "独立设备"),
    # CBreakerDis is commonly an RMU internal switch. If a new devref is not
    # present in GLOBAL yet, keep it in the device/component inventory rather
    # than silently placing it only in the unmapped sheet.
    "CBreakerDis": ("设备组成图元", "CBreakerDis", "", "设备内部部件"),
    "ZhaiWaiJieDiDaoZha": ("设备组成图元", "Ground Disconnector", "", "设备内部部件"),
    "Protect": ("设备组成图元", "Protection", "", "设备内部部件"),
}


def _observed_tag_fallback_definition(tag: str, actual_devref: str) -> StandardDefinition | None:
    metadata = _OBSERVED_TAG_DEVICE_FALLBACKS.get(tag)
    if metadata is None:
        return None
    usage, device_type, subtype, level = metadata
    return StandardDefinition(
        uid=f"observed-tag:{tag}",
        scope="OBSERVED_TAG_FALLBACK",
        symbol_usage=usage,
        device_type=device_type,
        device_subtype=subtype,
        device_level=level,
        element_tag=tag,
        standard_devref=actual_devref,
        standard_file="XML标签兜底（待补GLOBAL标准）",
        match_attr="XML元素",
        match_value=tag,
    )


_OBSERVED_CONTENT_METADATA: dict[str, tuple[str, str, str, str]] = {
    **_OBSERVED_TAG_DEVICE_FALLBACKS,
    "Bus": ("连接/拓扑", "Bus", "站内母线边界", "辅助关联"),
    "BusDis": ("连接/拓扑", "BusDis", "内部母线", "辅助关联"),
    "ConnectLine": ("连接/拓扑", "ConnectLine", "电气连接线", "辅助关联"),
    "FeedLine": ("连接/拓扑", "FeedLine", "馈线连接线", "辅助关联"),
    "line": ("连接/拓扑", "line", "图形线", "辅助关联"),
}


def _observed_content_metadata(tag: str) -> dict[str, str]:
    usage, device_type, subtype, level = _OBSERVED_CONTENT_METADATA.get(
        tag, ("", "", "", "")
    )
    return {
        "图元用途": usage,
        "设备类型": device_type,
        "设备子类型": subtype,
        "设备层级": level,
    }


def _profile_definitions(profile: SiteSmartProfile) -> list[StandardDefinition]:
    profile = profile.normalized()
    catalog = profile.symbol_catalog
    definitions: list[StandardDefinition] = []

    builtins = (
        ("builtin-smart-lbs", "SMART", "LBS", "CBreakerDis", profile.smart_lbs_devref),
        ("builtin-smart-breaker", "SMART", "Circuit Breaker", "CBreakerDis", profile.smart_breaker_devref),
        ("builtin-smart-ground", "SMART", "接地刀闸", "ZhaiWaiJieDiDaoZha", profile.smart_ground_devref),
        ("builtin-normal-lbs", "NORMAL", "LBS", "CBreakerDis", profile.normal_lbs_devref),
        ("builtin-normal-breaker", "NORMAL", "Circuit Breaker", "CBreakerDis", profile.normal_breaker_devref),
        ("builtin-normal-ground", "NORMAL", "接地刀闸", "ZhaiWaiJieDiDaoZha", profile.normal_ground_devref),
    )
    for uid, scope, role, tag, devref in builtins:
        devref = str(devref or "").strip()
        if not devref:
            continue
        meta = catalog.get(devref, {})
        definitions.append(StandardDefinition(
            uid=uid,
            scope=scope,
            symbol_usage="设备组成图元",
            device_type=role,
            device_subtype="",
            device_level="设备内部部件",
            element_tag=tag,
            standard_devref=devref,
            standard_file=Path(str(meta.get("source_file", "") or "")).name,
            match_attr="系统RMU规则",
            match_value="Y*" if role == "LBS" else ("Q*" if role == "Circuit Breaker" else "RMU内接地刀闸"),
            builtin_role="LBS" if role == "LBS" else ("BREAKER" if role == "Circuit Breaker" else "GROUND"),
            classification_marker=str(meta.get("classification_marker", meta.get("category_marker", "")) or "").strip(),
        ))

    for index, raw in enumerate(profile.custom_symbols):
        if not bool(raw.get("enabled", True)):
            continue
        devref = str(raw.get("standard_devref", "") or "").strip()
        if not devref:
            continue
        meta = catalog.get(devref, {})
        role = str(raw.get("role", "") or "").strip() or str(meta.get("element_id", "") or "").strip() or "自定义图元"
        usage = str(raw.get("symbol_usage", "") or "").strip()
        if usage not in SYMBOL_USAGE_VALUES:
            usage = infer_symbol_usage(role=role, source_file=str(meta.get("source_file", "") or ""), element_tag=str(raw.get("element_tag", "") or ""))
        level = str(raw.get("device_level", "") or "").strip()
        if level not in DEVICE_LEVEL_VALUES:
            level = default_device_level(usage)
        definitions.append(StandardDefinition(
            uid=str(raw.get("uid", "") or f"custom-{index + 1}"),
            scope=str(raw.get("scope", "ANY") or "ANY").strip().upper() or "ANY",
            symbol_usage=usage,
            device_type=str(raw.get("device_type", "") or "").strip() or infer_device_type(
                role=role, source_file=str(meta.get("source_file", "") or ""),
                element_tag=str(raw.get("element_tag", "") or ""), element_id=str(meta.get("element_id", "") or ""),
            ),
            device_subtype=str(raw.get("device_subtype", "") or "").strip(),
            device_level=level,
            element_tag=str(raw.get("element_tag", "") or "").strip(),
            standard_devref=devref,
            standard_file=Path(str(meta.get("source_file", raw.get("source_file", "")) or "")).name,
            match_attr=str(raw.get("match_attr", "devref") or "devref").strip(),
            match_value=str(raw.get("match_value", "") or "").strip(),
            classification_marker=str(raw.get("classification_marker", raw.get("category_marker", meta.get("classification_marker", meta.get("category_marker", "")))) or "").strip(),
        ))
    return definitions


def _float(element: ET.Element, name: str) -> float:
    try:
        return float(element.get(name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _center(element: ET.Element) -> tuple[float, float]:
    return (_float(element, "x") + _float(element, "w") / 2.0, _float(element, "y") + _float(element, "h") / 2.0)


def _text_value(element: ET.Element) -> str:
    for attr in ("ts", "text", "value", "caption"):
        value = (element.get(attr) or "").strip()
        if value:
            return value
    return ""


_GENERIC_DEVICE_LABEL = re.compile(r"^(?:Y|Q)\s*\d+$", re.I)


_GLOBAL_NAME_EXACT_EXCLUSIONS = {
    "SMART", "SMR", "N.O.P", "N.O.P.", "NOP", "F", "F.C", "F.C.", "FC",
}

# These XML elements are topology/annotation primitives, never equipment.  Keep
# this guard next to the global name matcher as a second line of defence: a
# future standard rule must not accidentally make a feeder line or bus eligible
# for a Text device-name assignment.
_NON_DEVICE_NAME_TAGS = {
    "ConnectLine", "FeedLine", "BusDis", "Bus", "ACLine", "line", "Line",
    "Text", "DText", "Status", "rect", "ellipse", "image", "Layer", "G",
    "Group", "Merge", "Theme", "pwbh", "poke",
}

_NON_DEVICE_NAME_TAGS_CASEFOLD = {tag.casefold() for tag in _NON_DEVICE_NAME_TAGS}


def _is_global_device_name_text(text: ET.Element) -> bool:
    """Return whether one static Text label can participate in device naming.

    Geometry remains the primary association rule for non-RMU devices.  This helper
    filters only text that is clearly an annotation rather than a device name; the
    later global scorer may use learned family/color evidence as a tie-breaker, but
    never turns a topology label or dynamic measurement into a device name.
    """
    if local_name(text.tag) != "Text":
        return False
    value = _text_value(text).strip()
    if not value:
        return False
    compact = re.sub(r"\s+", "", value.upper())
    if compact in _GLOBAL_NAME_EXACT_EXCLUSIONS:
        return False
    if _GENERIC_DEVICE_LABEL.fullmatch(value):
        return False
    # Parenthesized numeric IDs are secondary endpoint/station annotations in the
    # Saudi SLDs (e.g. ``(97636)``), not the primary equipment name.
    if re.fullmatch(r"\(\s*\d+\s*\)", value):
        return False
    return True


def _is_nameable_device_element(element: ET.Element) -> bool:
    """Return whether an XML element is allowed to receive a Text name."""
    tag = local_name(element.tag)
    return (
        tag not in _NON_DEVICE_NAME_TAGS
        and tag.casefold() not in _NON_DEVICE_NAME_TAGS_CASEFOLD
        and bool((element.get("devref") or "").strip())
    )


def _polyline_points(element: ET.Element) -> list[tuple[float, float]]:
    raw = element.get("d") or ""
    return [
        (float(x), float(y))
        for x, y in re.findall(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", raw)
    ]


def _graph_reference_ids(value: str) -> set[str]:
    result: set[str] = set()
    for group in (value or "").split(";"):
        parts = [part.strip() for part in group.split(",") if part.strip()]
        if len(parts) >= 3:
            result.add(parts[-1])
    return result


def _point_to_box_distance(px: float, py: float, element: ET.Element) -> float:
    x, y = _float(element, "x"), _float(element, "y")
    w, h = max(0.0, _float(element, "w")), max(0.0, _float(element, "h"))
    if w <= 0.0 or h <= 0.0:
        cx, cy = _center(element)
        return math.hypot(px - cx, py - cy)
    dx = max(x - px, 0.0, px - (x + w))
    dy = max(y - py, 0.0, py - (y + h))
    return math.hypot(dx, dy)


def _build_connection_index(
    elements: list[ET.Element],
) -> tuple[dict[str, ET.Element], dict[str, list[ET.Element]]]:
    """Index connection lines both by line id and by referenced device id."""
    line_by_id: dict[str, ET.Element] = {}
    attached: dict[str, list[ET.Element]] = defaultdict(list)
    for element in elements:
        tag = local_name(element.tag)
        if tag != "ConnectLine":
            continue
        line_id = (element.get("id") or "").strip()
        if line_id:
            line_by_id[line_id] = element
        refs = _graph_reference_ids(element.get("node_area") or "") | _graph_reference_ids(element.get("link") or "")
        for ref in refs:
            attached[ref].append(element)
    return line_by_id, attached


def _device_anchor_points(
    element: ET.Element,
    line_by_id: dict[str, ET.Element],
    attached_lines: dict[str, list[ET.Element]],
) -> list[tuple[float, float]]:
    """Return electrical/visual anchors closest to the concrete device symbol.

    GIcon x/y/w/h is often a large logical bounding box and its center is not the
    rendered electrical symbol.  ConnectLine endpoints are much closer to what the
    operator visually considers "the device".  This is especially important for
    rotated TransformerDis instances.
    """
    lines: list[ET.Element] = []
    seen: set[int] = set()
    refs = _graph_reference_ids(element.get("node_area") or "") | _graph_reference_ids(element.get("link") or "")
    for ref in refs:
        line = line_by_id.get(ref)
        if line is not None and id(line) not in seen:
            lines.append(line)
            seen.add(id(line))
    element_id = (element.get("id") or "").strip()
    for line in attached_lines.get(element_id, []):
        if id(line) not in seen:
            lines.append(line)
            seen.add(id(line))

    anchors: list[tuple[float, float]] = []
    for line in lines:
        points = _polyline_points(line)
        if not points:
            continue
        endpoints = [points[0], points[-1]]
        # Pick the endpoint physically touching/nearest the symbol, not the remote
        # bus/branch endpoint of the same ConnectLine.
        anchor = min(endpoints, key=lambda point: _point_to_box_distance(point[0], point[1], element))
        anchors.append(anchor)

    if not anchors:
        return [_center(element)]
    unique: list[tuple[float, float]] = []
    seen_points: set[tuple[float, float]] = set()
    for point in anchors:
        key = (round(point[0], 6), round(point[1], 6))
        if key not in seen_points:
            seen_points.add(key)
            unique.append(point)
    return unique


def _standalone_text_distance(
    element: ET.Element,
    text: ET.Element,
    line_by_id: dict[str, ET.Element],
    attached_lines: dict[str, list[ET.Element]],
) -> float:
    return min(
        _point_to_box_distance(px, py, text)
        for px, py in _device_anchor_points(element, line_by_id, attached_lines)
    )


def _text_color_bucket(text: ET.Element) -> str:
    """Normalize the rendered Text color for local name-pattern learning.

    G files commonly carry the same color in ``lc``/``lcc`` (and sometimes in
    ``fc``/``fcc``).  The bucket is intentionally coarse: the matcher only needs
    to learn conventions such as red equipment names versus white annotations.
    """
    for attr in ("lcc", "lc", "fcc", "fc"):
        raw = (text.get(attr) or "").strip().lower()
        if not raw:
            continue
        values: tuple[int, int, int] | None = None
        if raw.startswith("#"):
            value = raw[1:]
            if len(value) == 6:
                try:
                    values = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
                except ValueError:
                    values = None
        else:
            parts = [part.strip() for part in raw.split(",")]
            if len(parts) >= 3:
                try:
                    values = tuple(max(0, min(255, int(float(part)))) for part in parts[:3])  # type: ignore[assignment]
                except ValueError:
                    values = None
        if values is None:
            continue
        red, green, blue = values
        if red >= 180 and red >= green * 1.25 and red >= blue * 1.25:
            return "red"
        if blue >= 150 and blue >= red * 1.25 and blue >= green * 1.10:
            return "blue"
        if red >= 180 and green >= 180 and blue >= 120 and abs(red - green) <= 45:
            return "yellow"
        if min(values) >= 180:
            return "white"
        return "other"
    return "unknown"


def _name_family_for_target(
    element: ET.Element,
    definition: StandardDefinition | None,
    migration_type: str = "",
) -> str:
    """Return a stable family key used to learn naming conventions.

    Different standard icons can implement the same business equipment.  Prefer
    the normalized migration type so a family can learn from all of its variants;
    fall back to the configured device type/devref only when no migration type is
    available.
    """
    value = (migration_type or "").strip().upper()
    if value:
        return value
    if definition is not None:
        value = (definition.device_type or "").strip().upper()
        if value:
            return value
        value = (definition.standard_devref or element.get("devref") or "").strip().upper()
        if value:
            return re.sub(r"[^A-Z0-9]+", "_", value)
    return "UNKNOWN"


def _text_format_bucket(text: ET.Element) -> str:
    """Return a graphical character/style bucket for one visible Text.

    The bucket intentionally uses only rendered Text properties.  It never reads
    model-association attributes such as keyid/key_name/p_NameString.  Text shape
    is useful on sites where numeric equipment IDs, coded names, and descriptive
    names use different conventions.
    """
    value = re.sub(r"\s+", " ", _text_value(text).strip())
    if not value:
        return "unknown"
    if re.fullmatch(r"\d{3,8}", value):
        shape = "numeric"
    elif re.fullmatch(r"[A-Za-z]{1,8}[-_ ]?\d{1,8}", value):
        shape = "alpha_numeric_code"
    elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_./-]*", value):
        shape = "alpha_code"
    elif re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9 _./-]+", value):
        shape = "mixed_text"
    else:
        shape = "other"

    font = (text.get("ff") or text.get("font") or "").strip().casefold()
    try:
        size_value = float(text.get("fs") or text.get("p_FontHeight") or 0)
    except (TypeError, ValueError):
        size_value = 0.0
    size = str(int(round(size_value))) if size_value > 0 else "unknown_size"
    bold = str(text.get("bold") or text.get("p_BoldFontFlag") or "").strip().lower()
    italic = str(text.get("italic") or text.get("p_ItalicFontFlag") or "").strip().lower()
    weight = "bold" if bold in {"1", "true", "yes"} else "normal"
    slant = "italic" if italic in {"1", "true", "yes"} else "normal"
    return "|".join((shape, font or "unknown_font", size, weight, slant))


def _learn_name_modes(
    targets: list[ET.Element],
    texts: list[ET.Element],
    elements: list[ET.Element],
    target_families: dict[int, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Learn graphical name conventions from unambiguous global geometry.

    This is deliberately local and deterministic, not an opaque ML model.  A Text
    contributes only when it is clearly closer to one known equipment target than
    to every other target.  Thus a nearby label collision cannot teach the wrong
    color or character convention.  Each learned mode requires at least two
    observations and a clear majority.
    """
    candidates = [text for text in texts if _is_global_device_name_text(text)]
    if not targets or not candidates:
        return {}, {}
    line_by_id, attached_lines = _build_connection_index(elements)
    color_observations: dict[str, Counter[str]] = defaultdict(Counter)
    format_observations: dict[str, Counter[str]] = defaultdict(Counter)
    for text in candidates:
        ranked = sorted(
            [
                (
                    _standalone_text_distance(target, text, line_by_id, attached_lines),
                    target,
                )
                for target in targets
            ],
            key=lambda item: (item[0], id(item[1])),
        )
        if not ranked:
            continue
        best_distance, best_target = ranked[0]
        second_distance = ranked[1][0] if len(ranked) > 1 else float("inf")
        # A margin protects the learner from the exact collision cases this module
        # is meant to resolve.  Long but clearly isolated labels remain usable.
        if best_distance > 260.0 or second_distance - best_distance < 35.0:
            continue
        family = target_families.get(id(best_target), "UNKNOWN")
        color_bucket = _text_color_bucket(text)
        format_bucket = _text_format_bucket(text)
        if family == "UNKNOWN":
            continue
        if color_bucket != "unknown":
            color_observations[family][color_bucket] += 1
        if format_bucket != "unknown":
            format_observations[family][format_bucket] += 1

    def _dominant(observations: dict[str, Counter[str]]) -> dict[str, str]:
        result: dict[str, str] = {}
        for family, counts in observations.items():
            if not counts:
                continue
            bucket, count = counts.most_common(1)[0]
            total = sum(counts.values())
            if count >= 2 and count / max(1, total) >= 0.60:
                result[family] = bucket
        return result

    return _dominant(color_observations), _dominant(format_observations)


def _assign_global_standalone_names(
    devices: list[ET.Element],
    texts: list[ET.Element],
    elements: list[ET.Element],
    competing_targets: list[tuple[str, ET.Element]] | None = None,
    target_families: dict[str, str] | None = None,
    learned_color_modes: dict[str, str] | None = None,
    learned_format_modes: dict[str, str] | None = None,
    *,
    require_devref: bool = False,
) -> dict[int, tuple[str, str, str, int, float]]:
    """Assign visible names to all non-RMU devices by one global graphical rule.

    - search every eligible Text label in the whole G drawing;
    - no top/bottom/left/right preference and no directional penalty;
    - use the device-side electrical anchor when available;
    - each concrete Text object is owned by the nearest real device globally;
      optional RMU/unknown-device competitors are included in the same pool;
      a device then chooses its nearest Text among the labels it actually owns;
    - learned color/character conventions are soft tie-breakers only; they never
      override a clearly nearer graphical target;
    - there is intentionally no hard search radius.  Long-distance fallbacks remain
      visible through LOW confidence instead of silently becoming NAME_MISSING.
    """
    candidates = [text for text in texts if _is_global_device_name_text(text)]
    # Defend the global matcher independently of its callers.  This prevents a
    # topology primitive that happens to carry devref/custom metadata from ever
    # entering the Text-to-device assignment pool.
    if require_devref:
        devices = [device for device in devices if _is_nameable_device_element(device)]
    else:
        # Compatibility callers may pass synthetic test elements that model the
        # geometry only and intentionally omit a production ``devref``.
        devices = [device for device in devices if local_name(device.tag) not in _NON_DEVICE_NAME_TAGS]
    if not devices or not candidates:
        return {}
    line_by_id, attached_lines = _build_connection_index(elements)
    anchors_by_device = {
        id(device): _device_anchor_points(device, line_by_id, attached_lines)
        for device in devices
    }
    target_pairs = [(str(id(device)), device) for device in devices]
    target_pairs.extend(competing_targets or [])
    target_anchors = {
        str(id(device)): tuple(anchors_by_device[id(device)])
        for device in devices
    }
    # Competitors must use the same electrical-anchor distance as the primary
    # devices.  Otherwise a small component box can win merely because its XML
    # rectangle happens to be closer than its actual connection point.
    for target_key, target in target_pairs:
        if target_key not in target_anchors:
            target_anchors[target_key] = tuple(_device_anchor_points(target, line_by_id, attached_lines))

    def _adjust_score(text: ET.Element, target_key: str, distance: float) -> float:
        family = (target_families or {}).get(target_key, "")
        adjusted = distance
        expected_color = (learned_color_modes or {}).get(family, "")
        actual_color = _text_color_bucket(text)
        if expected_color and actual_color != "unknown":
            # Color is a learned tie-breaker, never a hard exclusion.  Keep the
            # correction bounded so a distant matching-color label cannot displace
            # an obviously nearer graphical label.
            adjusted += -20.0 if actual_color == expected_color else 20.0
        expected_format = (learned_format_modes or {}).get(family, "")
        actual_format = _text_format_bucket(text)
        if expected_format and actual_format != "unknown":
            # Character shape/font is weaker than geometry and color.  It is useful
            # for distinguishing numeric transformer IDs from nearby station or
            # device annotations when their positions are close.
            adjusted += -12.0 if actual_format == expected_format else 12.0
        return adjusted

    owners = assign_global_text_owners(
        candidates,
        target_pairs,
        target_anchors=target_anchors,
        score_adjuster=_adjust_score,
    )
    result: dict[int, tuple[str, str, str, int, float]] = {}
    for device in devices:
        target_key = str(id(device))
        owned = [owner for owner in owners.values() if owner.target_key == target_key]
        if not owned:
            continue
        owner = min(
            owned,
            key=lambda item: (
                item.distance,
                _text_value(item.text).casefold(),
                id(item.text),
            ),
        )
        value = _text_value(owner.text)
        if not value:
            continue
        confidence = "HIGH" if owner.distance <= 120.0 else (
            "MEDIUM" if owner.distance <= 240.0 else "LOW"
        )
        result[id(device)] = (
            value,
            "Nearby Text",
            confidence,
            id(owner.text),
            round(owner.distance, 2),
        )
    return result


def _assign_transformer_text_names(
    transformers: list[ET.Element],
    texts: list[ET.Element],
) -> dict[int, tuple[str, str, str, int, float]]:
    """Backward-compatible transformer-only name assignment entry point.

    The inventory now uses one global matcher for all standalone equipment.  Keep
    the former helper available for older integrations and regression tests while
    routing it through that same matcher.
    """
    candidates = [text for text in texts if _is_global_device_name_text(text)]
    if not transformers or not candidates:
        return {}

    line_by_id, attached_lines = _build_connection_index([*transformers, *texts])
    distances = [
        [
            min(
                _point_to_box_distance(px, py, text)
                for px, py in _device_anchor_points(transformer, line_by_id, attached_lines)
            )
            for text in candidates
        ]
        for transformer in transformers
    ]
    # The former public helper promised one visible label per transformer.  Keep
    # that contract for legacy callers by choosing the minimum-cost injective
    # assignment.  The production inventory uses the newer global ownership pass.
    target_count = min(len(transformers), len(candidates))
    best_assignment: tuple[int, ...] | None = None
    best_cost = float("inf")
    for text_indexes in permutations(range(len(candidates)), target_count):
        cost = sum(distances[row][text_indexes[row]] for row in range(target_count))
        if cost < best_cost:
            best_cost = cost
            best_assignment = text_indexes
    if best_assignment is None:
        return {}

    result: dict[int, tuple[str, str, str, int, float]] = {}
    for row, text_index in enumerate(best_assignment):
        distance = distances[row][text_index]
        confidence = "HIGH" if distance <= 120.0 else ("MEDIUM" if distance <= 240.0 else "LOW")
        text = candidates[text_index]
        result[id(transformers[row])] = (
            _text_value(text),
            "Nearby Text",
            confidence,
            id(text),
            round(distance, 2),
        )
    return result


def _nearest_display_label(
    element: ET.Element,
    texts: list[ET.Element],
    max_distance: float = 190.0,
    preferred_value: str = "",
    excluded_text_ids: set[int] | None = None,
) -> tuple[str, float | str]:
    """Return a nearby visible label for audit; never promotes it to DeviceName by itself."""
    cx, cy = _center(element)
    candidates: list[tuple[float, str]] = []
    preferred: list[tuple[float, str]] = []
    preferred_value = (preferred_value or "").strip()
    excluded_text_ids = excluded_text_ids or set()
    for text in texts:
        if id(text) in excluded_text_ids:
            continue
        value = _text_value(text)
        if not value or value.upper() in {"SMART", "SMR"}:
            continue
        tcx, tcy = _center(text)
        distance = math.hypot(tcx - cx, tcy - cy)
        if distance <= max_distance:
            item = (distance, value)
            candidates.append(item)
            if preferred_value and value == preferred_value:
                preferred.append(item)
    selected = preferred or candidates
    if not selected:
        return "", ""
    selected.sort(key=lambda item: (item[0], item[1]))
    return selected[0][1], round(selected[0][0], 2)


def _nearby_text_is_for_other_device(device_type: str, value: str) -> bool:
    """Block obvious annotation/name theft between adjacent device families."""
    value = (value or "").strip()
    if not value:
        return True
    upper = value.upper().replace(" ", "")
    dtype = _migration_device_type_from_values(device_type=device_type)
    if upper in {"SMART", "SMR"} or _GENERIC_DEVICE_LABEL.fullmatch(value):
        return True
    if re.fullmatch(r"F\.?C\.?", upper):
        # F.C is a diagram annotation for fuse cut-out, not a stable migration name.
        return True
    if upper.startswith("LBS-") and dtype != "LBS":
        return True
    if (upper.startswith("SFI-") or upper == "SFI") and dtype != "SFI":
        return True
    if (upper.startswith("REC-") or upper.startswith("AR-")) and dtype != "REC":
        return True
    # For families whose visible label has a strong naming convention, prefer a
    # missing name over stealing a nearby station/transformer annotation.
    if dtype == "LBS" and not re.match(r"^LBS(?:[-_]|$)", upper):
        return True
    if dtype == "SFI" and not re.match(r"^SFI(?:[-_]|$)", upper):
        return True
    # Grounding/disconnector/fuse symbols frequently sit next to another device's
    # name. Their migration name must come from explicit XML/profile metadata; F.C
    # and nearby station labels are display annotations, not safe identifiers.
    if dtype in {"FUSE", "GROUND_DISCONNECTOR", "DISCONNECTOR"}:
        return True
    return False


def _resolve_instance_name(
    element: ET.Element,
    *,
    device_type: str,
    rmu_name: str,
    texts: list[ET.Element],
    consumed_text_ids: set[int],
    include_text_id: bool = False,
) -> tuple[str, str, str] | tuple[str, str, str, int | None]:
    """Return a name from visible drawing Text only.

    XML association fields are intentionally not a naming source.  RMU internal
    Y/Q labels are allowed here because they are visible Text objects inside the
    identified cabinet; they are still resolved by geometry and one-to-one Text
    consumption below.
    """
    def result(
        name: str,
        source: str,
        confidence: str,
        text_id: int | None = None,
    ) -> tuple[str, str, str] | tuple[str, str, str, int | None]:
        if include_text_id:
            return name, source, confidence, text_id
        return name, source, confidence

    cx, cy = _center(element)
    ew = max(1.0, _float(element, "w"))
    allow_component_labels = bool(rmu_name)
    candidates: list[tuple[float, float, float, int, str, ET.Element]] = []
    for text in texts:
        if id(text) in consumed_text_ids:
            continue
        value = _text_value(text)
        if not value or value.upper() in {"SMART", "SMR"}:
            continue
        is_component_label = bool(_GENERIC_DEVICE_LABEL.fullmatch(value))
        if is_component_label and not allow_component_labels:
            continue
        if _nearby_text_is_for_other_device(device_type, value) and not is_component_label:
            continue
        tcx, tcy = _center(text)
        dx, dy = tcx - cx, tcy - cy
        distance = math.hypot(dx, dy)
        if distance > 180.0:
            continue
        if abs(dx) > max(145.0, ew * 2.5):
            continue
        # Slightly prefer labels above the symbol, while still allowing real files
        # where the business name is below or to the side.
        direction_penalty = 0.0 if dy <= 0 else 24.0
        score = distance + direction_penalty + abs(dx) * 0.25
        migration_type = _migration_device_type_from_values(device_type=device_type)
        if migration_type == "CB" and re.fullmatch(r"\d{1,8}", value.strip()):
            score -= 72.0
        elif migration_type == "LBS" and value.upper().startswith("LBS-"):
            score -= 24.0
        elif migration_type == "SFI" and value.upper().startswith("SFI"):
            score -= 24.0
        # Store dy as a final field so equipment such as transformers can prefer
        # the conventional label above the symbol without making that a hard rule.
        candidates.append((score, distance, abs(dx), id(text), value, text, dy))
    if not candidates:
        return result("", "", "LOW")
    migration_type = _migration_device_type_from_values(device_type=device_type)
    if migration_type == "CB":
        numeric = [item for item in candidates if re.fullmatch(r"\d{1,8}", item[4].strip())]
        if numeric:
            candidates = numeric
        else:
            preferred = [item for item in candidates if item[6] <= 20.0]
            if preferred:
                candidates = preferred
    else:
        preferred = [item for item in candidates if item[6] <= 20.0]
        if preferred:
            candidates = preferred
    candidates.sort(key=lambda item: (item[0], item[1], item[2], item[4]))
    best = candidates[0]
    # If two unrelated labels are effectively tied, do not invent a name.
    if len(candidates) > 1 and abs(candidates[1][0] - best[0]) < 5.0 and candidates[1][4] != best[4]:
        return result("", "Nearby Text ambiguous", "LOW")
    consumed_text_ids.add(best[3])
    confidence = "HIGH" if best[1] <= 120.0 else "MEDIUM"
    return result(best[4], "Nearby Text", confidence, best[3])




def _rmu_contexts(tree: ET.ElementTree, file_path: Path) -> tuple[list[_RmuContext], list[str]]:
    try:
        identification = identify_rmus(
            tree,
            file_path,
            name_positions=("top",),
            name_resolution_mode="selected_direction",
            smart_in_type=True,
        )
    except Exception as exc:  # extraction should continue even if composite RMU recognition is unavailable
        return [], [f"{file_path.name}: RMU 识别失败，图元实例仍继续提取：{exc}"]
    elements = direct_layer_elements(tree.getroot())
    rects = [element for element in elements if local_name(element.tag) == "rect"]
    smart_texts = _marker_texts(elements, "SMART")
    smr_texts = _marker_texts(elements, "SMR")
    result: list[_RmuContext] = []
    for item in identification.items:
        rect = _find_rect(rects, item)
        if rect is None:
            continue
        scope = _rmu_class(rect, smart_texts, smr_texts)
        if scope == "SMR":
            scope = "SMART"
        result.append(_RmuContext(
            name=item.name or "",
            rmu_type=item.rmu_type or "",
            scope=scope or "NORMAL",
            rect_id=item.rect_id or "",
            rect=rect,
        ))
    return result, list(identification.warnings)


def _context_for_element(element: ET.Element, contexts: list[_RmuContext]) -> _RmuContext | None:
    matches = [context for context in contexts if _center_inside(element, context.rect)]
    if not matches:
        return None
    # Nested/overlapping cabinets are resolved to the smallest containing frame.
    return min(matches, key=lambda c: max(1.0, _float(c.rect, "w") * _float(c.rect, "h")))


def _definition_matches(element: ET.Element, definition: StandardDefinition, context: _RmuContext | None) -> bool:
    tag = local_name(element.tag)
    if definition.element_tag and tag != definition.element_tag:
        return False
    if definition.scope in {"SMART", "NORMAL"} and (context is None or context.scope != definition.scope):
        return False
    if definition.builtin_role:
        if context is None:
            return False
        if definition.builtin_role == "GROUND":
            return tag == "ZhaiWaiJieDiDaoZha"
        return _device_role(element) == definition.builtin_role
    return _custom_rule_matches(
        element,
        {
            "enabled": True,
            "scope": definition.scope,
            "element_tag": definition.element_tag,
            "standard_devref": definition.standard_devref,
            "match_attr": definition.match_attr,
            "match_value": definition.match_value,
        },
        context.scope if context else None,
    )


def _select_definition(element: ET.Element, definitions: list[StandardDefinition], context: _RmuContext | None) -> tuple[StandardDefinition | None, str]:
    current = (element.get("devref") or "").strip()
    tag = local_name(element.tag)

    # An exact authoritative devref + XML element match is the strongest identity
    # signal.  SMART/NORMAL is an applicability/context hint and must not make an
    # otherwise exact configured symbol appear as "unmapped" merely because the
    # business instance is outside an RMU frame.  This is especially important for
    # standalone scoped symbols such as Fuse_NON_SMART.
    exact_identity = [
        definition for definition in definitions
        if current
        and current == definition.standard_devref
        and (not definition.element_tag or definition.element_tag == tag)
    ]
    if exact_identity:
        # If the element is inside a known RMU, prefer the definition whose scope is
        # explicitly applicable there (or ANY).  This keeps shared SMART/NORMAL
        # definitions deterministic without weakening exact identity matching.
        applicable = [
            definition for definition in exact_identity
            if definition.scope == "ANY" or (context is not None and definition.scope == context.scope)
        ]
        if len(applicable) == 1:
            return applicable[0], "exact-devref"
        if len(applicable) > 1:
            return None, "ambiguous-exact"

        # No RMU/context match exists.  A single exact configured definition still
        # identifies the symbol; scope alone must not demote it to UNMAPPED.
        if len(exact_identity) == 1:
            return exact_identity[0], "exact-devref"
        return None, "ambiguous-exact"

    matches = [definition for definition in definitions if _definition_matches(element, definition, context)]
    if len(matches) == 1:
        return matches[0], "business-rule"
    if not matches:
        # Key requirement for wrong-symbol detection: if only one configured standard
        # exists for this XML element in the applicable scope, the XML element itself
        # identifies the business class and the devref can be validated as wrong.
        candidates = [
            definition for definition in definitions
            if definition.element_tag == local_name(element.tag)
            and (definition.scope == "ANY" or (context is not None and definition.scope == context.scope))
        ]
        if len(candidates) == 1:
            return candidates[0], "unique-xml-fallback"
        return None, "unmapped"
    return None, "ambiguous-rule"


def _effective_device_level_for(
    definition: StandardDefinition,
    context: _RmuContext | None,
    migration_type: str,
) -> str:
    """Return the migration-effective device level for one concrete G instance."""
    effective_level = definition.device_level
    if context is not None and definition.symbol_usage in {"设备", "设备组成图元"}:
        return "设备内部部件"
    if (
        context is None
        and effective_level == "设备内部部件"
        and migration_type in {"LBS", "FUSE", "CB", "GROUND_DISCONNECTOR", "DISCONNECTOR", "REC", "SFI"}
    ):
        return "独立设备"
    return effective_level


def _validation_map(source: Path, profile: SiteSmartProfile) -> tuple[dict[str, list[dict[str, object]]], list[str]]:
    tree = ET.parse(source)
    managed = bool(profile.managed_standard_files)
    if not managed:
        # Legacy profiles may not carry authoritative pin/geometry extracted from a
        # user-uploaded icon definition. In that case inventory still validates the
        # devref directly, but never learns geometry from the business drawing.
        return {}, []
    try:
        result = apply_smart_profile_to_tree(
            tree,
            source,
            smart_lbs_devref=profile.smart_lbs_devref,
            smart_breaker_devref=profile.smart_breaker_devref,
            normal_lbs_devref=profile.normal_lbs_devref,
            normal_breaker_devref=profile.normal_breaker_devref,
            smart_ground_devref=profile.smart_ground_devref,
            normal_ground_devref=profile.normal_ground_devref,
            profile_geometry_templates=authoritative_geometry_templates(profile) if managed else profile.geometry_templates,
            custom_symbols=profile.custom_symbols,
            allow_source_geometry_fallback=not managed,
        )
    except Exception as exc:
        return {}, [f"{source.name}: 标准校验失败，已保留实例提取结果：{exc}"]
    by_id: dict[str, list[dict[str, object]]] = defaultdict(list)
    for detail in result.mismatch_details:
        element_id = str(detail.get("ElementID", "") or "").strip()
        if element_id and element_id != "-":
            by_id[element_id].append(dict(detail))
    return dict(by_id), list(result.warnings)


def extract_file_inventory(
    source: Path,
    profile: SiteSmartProfile,
    feeder_database_service: OracleDatabaseService | None = None,
    feeder_assignments: dict[str, dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[str]]:
    profile = profile.normalized()
    definitions = _profile_definitions(profile)
    tree = ET.parse(source)
    root = tree.getroot()
    elements = direct_layer_elements(root)
    contexts, warnings = _rmu_contexts(tree, source)
    validation_by_id, validation_warnings = _validation_map(source, profile)
    warnings.extend(validation_warnings)
    texts = [element for element in elements if local_name(element.tag) == "Text"]

    # Resolve symbol identity/context once.  RMU internals keep their dedicated
    # composite-device naming rules; every non-RMU business device participates in
    # one global nearest-text assignment, independent of XML iteration order.
    selection_cache: dict[int, tuple[_RmuContext | None, StandardDefinition | None, str]] = {}
    standalone_name_targets: list[ET.Element] = []
    standalone_target_ids: set[int] = set()
    standalone_target_families: dict[int, str] = {}
    for candidate in elements:
        current_devref = (candidate.get("devref") or "").strip()
        if not current_devref:
            continue
        if not _is_nameable_device_element(candidate):
            # ConnectLine/FeedLine/BusDis/Bus are topology primitives even when
            # legacy files attach devref-like metadata to them.
            continue
        candidate_context = _context_for_element(candidate, contexts)
        candidate_definition, candidate_match_source = _select_definition(candidate, definitions, candidate_context)
        selection_cache[id(candidate)] = (candidate_context, candidate_definition, candidate_match_source)
        if candidate_definition is None or candidate_context is not None:
            continue
        if candidate_definition.symbol_usage not in {"设备", "设备组成图元"}:
            continue
        tag = local_name(candidate.tag)
        migration_type = _migration_device_type_from_values(
            device_type=candidate_definition.device_type,
            standard_file=candidate_definition.standard_file,
            standard_devref=candidate_definition.standard_devref,
            actual_devref=current_devref,
            element_tag=tag,
        )
        if migration_type == "RMU":
            continue
        effective_level = _effective_device_level_for(candidate_definition, candidate_context, migration_type)
        if effective_level not in {"独立设备", "组合设备"}:
            continue
        standalone_name_targets.append(candidate)
        standalone_target_ids.add(id(candidate))
        standalone_target_families[id(candidate)] = _name_family_for_target(
            candidate, candidate_definition, migration_type
        )

    # Use the same global Text ownership pool as RMU recognition. RMU frames and
    # other *top-level business devices* compete with standalone devices.  Internal
    # CBreakerDis/LBS pieces and topology primitives are deliberately excluded;
    # otherwise a cabinet component can steal the name of a nearby pole device.
    global_competing_targets: list[tuple[str, ET.Element]] = [
        (f"rmu:{context.rect_id}", context.rect)
        for context in contexts
    ]
    known_standalone_ids = {id(device) for device in standalone_name_targets}
    for element in elements:
        if (
            id(element) in known_standalone_ids
            or not _is_nameable_device_element(element)
            or any(_center_inside(element, context.rect) for context in contexts)
        ):
            continue
        cached_definition = selection_cache.get(id(element))
        if cached_definition is None:
            element_context = _context_for_element(element, contexts)
            element_definition, element_match_source = _select_definition(
                element, definitions, element_context
            )
            selection_cache[id(element)] = (element_context, element_definition, element_match_source)
        else:
            element_context, element_definition, _element_match_source = cached_definition
        if element_definition is None or element_context is not None:
            continue
        if element_definition.symbol_usage not in {"设备", "设备组成图元"}:
            continue
        element_migration_type = _migration_device_type_from_values(
            device_type=element_definition.device_type,
            standard_file=element_definition.standard_file,
            standard_devref=element_definition.standard_devref,
            actual_devref=(element.get("devref") or "").strip(),
            element_tag=local_name(element.tag),
        )
        if element_migration_type == "RMU":
            continue
        element_level = _effective_device_level_for(
            element_definition, element_context, element_migration_type
        )
        if element_level not in {"独立设备", "组合设备"}:
            continue
        global_competing_targets.append((f"device:{id(element)}", element))
        standalone_target_families[id(element)] = _name_family_for_target(
            element, element_definition, element_migration_type
        )

    all_global_targets = list(standalone_name_targets) + [
        target for _key, target in global_competing_targets
        if local_name(target.tag) != "rect"
    ]
    learned_target_families = dict(standalone_target_families)
    for competing_key, competing_target in global_competing_targets:
        if local_name(competing_target.tag) == "rect":
            learned_target_families.setdefault(id(competing_target), "RMU")
    learned_color_modes, learned_format_modes = _learn_name_modes(
        all_global_targets,
        texts,
        elements,
        learned_target_families,
    )

    # Every standalone equipment family, including TransformerDis, participates
    # in the same global one-to-one Text ownership pass.  A transformer must not
    # reserve a nearby label before a visually closer CBreakerDis/SEC device gets
    # to compete for it.  This is the key rule for mixed pole-device drawings.
    generic_targets = list(standalone_name_targets)
    generic_competing_targets = list(global_competing_targets)
    generic_target_families = {
        str(id(device)): standalone_target_families.get(id(device), "")
        for device in generic_targets
    }
    generic_target_families.update({
        key: learned_target_families.get(id(target), "")
        for key, target in generic_competing_targets
    })
    generic_text_names = _assign_global_standalone_names(
        generic_targets,
        [
            text for text in texts
            if not any(_center_inside(text, context.rect) for context in contexts)
        ],
        elements,
        generic_competing_targets,
        target_families=generic_target_families,
        learned_color_modes=learned_color_modes,
        learned_format_modes=learned_format_modes,
        require_devref=True,
    )
    standalone_text_names = generic_text_names
    # Reserve the exact Text objects already assigned to non-RMU devices so legacy
    # fallback logic used for RMU internals/diagnostic symbols cannot steal them.
    consumed_text_ids: set[int] = {item[3] for item in standalone_text_names.values()}

    symbol_rows: list[dict[str, object]] = []
    device_rows: list[dict[str, object]] = []
    unmapped_rows: list[dict[str, object]] = []

    for element in elements:
        current_devref = (element.get("devref") or "").strip()
        if not current_devref:
            continue
        cached = selection_cache.get(id(element))
        if cached is None:
            context = _context_for_element(element, contexts)
            definition, match_source = _select_definition(element, definitions, context)
        else:
            context, definition, match_source = cached
        tag = local_name(element.tag)
        if definition is None:
            fallback_definition = _observed_tag_fallback_definition(tag, current_devref)
            if fallback_definition is None:
                unmapped_rows.append({
                    "GFile": source.name,
                    "XML元素": tag,
                    "ElementID": (element.get("id") or "").strip(),
                    "实际devref": current_devref,
                    "keyid": (element.get("keyid") or "").strip(),
                    "key_name": (element.get("key_name") or "").strip(),
                    "key_name1": (element.get("key_name1") or "").strip(),
                    "key_name2": (element.get("key_name2") or "").strip(),
                    "p_NameString": (element.get("p_NameString") or "").strip(),
                    "p_EngcodeString": (element.get("p_EngcodeString") or "").strip(),
                    "link": (element.get("link") or "").strip(),
                    "node_area": (element.get("node_area") or "").strip(),
                    "所属RMU": context.name if context else "",
                    "匹配状态": match_source,
                    "x": _float(element, "x"),
                    "y": _float(element, "y"),
                })
                continue
            definition = fallback_definition
            match_source = "XML_TAG_FALLBACK"

        global_name = standalone_text_names.get(id(element))
        if global_name is not None:
            name, name_source, name_confidence, _reserved_text_id, global_distance = global_name
            display_label, display_label_distance = name, global_distance
        elif id(element) in standalone_target_ids:
            # For non-RMU devices visible geometry/Text is authoritative.  Do not
            # fall back to model-association attributes when no eligible Text remains.
            name, name_source, name_confidence = "", "", "LOW"
            # No assigned name means no display name either.  A nearby Text is only
            # an equipment name after the global one-to-one ownership pass accepts
            # it; never expose an unassigned/foreign label as this device's name.
            display_label, display_label_distance = "", ""
        else:
            name, name_source, name_confidence, name_text_id = _resolve_instance_name(
                element,
                device_type=definition.device_type,
                rmu_name=context.name if context else "",
                texts=texts,
                consumed_text_ids=consumed_text_ids,
                include_text_id=True,
            )
            if name_source == "Nearby Text" and name and name_text_id is not None:
                # The audit label mirrors the exact Text that was assigned as the
                # actual name; it is not an independent nearest-text guess.
                display_label = name
                display_label_distance = _nearest_display_label(
                    element, [text for text in texts if id(text) == name_text_id]
                )[1]
            else:
                # Ambiguous or missing names remain blank.  In particular, do not
                # show a nearby label belonging to another device.
                display_label, display_label_distance = "", ""
        element_id = (element.get("id") or "").strip()
        validation_details = validation_by_id.get(element_id, []) if element_id else []
        issues = [str(item.get("IssueType", "") or "").strip() for item in validation_details if str(item.get("IssueType", "") or "").strip()]
        if current_devref != definition.standard_devref and not any("图元引用" in issue or "变体" in issue for issue in issues):
            issues.insert(0, "标准图元引用不一致")
        validation_status = "PASS" if not issues else "MISMATCH"
        migration_type = _migration_device_type_from_values(
            device_type=definition.device_type, standard_file=definition.standard_file,
            standard_devref=definition.standard_devref, actual_devref=current_devref, element_tag=tag,
        )
        # Actual RMU containment still has the highest hierarchy priority; only
        # non-RMU instances use the global nearest-text naming rule above.
        effective_level = _effective_device_level_for(definition, context, migration_type)
        row = {
            "GFile": source.name,
            "facID": (root.get("facID") or "").strip(),
            "facName": (root.get("facName") or "").strip(),
            "图元用途": definition.symbol_usage,
            "设备类型": definition.device_type,
            "迁移设备类型": migration_type,
            "设备子类型": definition.device_subtype,
            "设备层级": effective_level,
            "标准检查范围": definition.scope,
            "SMART/NORMAL": definition.scope if definition.scope in {"SMART", "NORMAL"} else (context.scope if context else ""),
            "实例名称": name,
            "名称来源": name_source,
            "名称置信度": name_confidence,
            "图中文字标签": display_label,
            "标签距离": display_label_distance,
            "所属RMU": context.name if context else "",
            "RMU类型": context.rmu_type if context else "",
            "XML元素": tag,
            "ElementID": element_id,
            "keyid": (element.get("keyid") or "").strip(),
            "key_name": (element.get("key_name") or "").strip(),
            "key_name1": (element.get("key_name1") or "").strip(),
            "key_name2": (element.get("key_name2") or "").strip(),
            "p_NameString": (element.get("p_NameString") or "").strip(),
            "p_EngcodeString": (element.get("p_EngcodeString") or "").strip(),
            "link": (element.get("link") or "").strip(),
            "标准图元文件": definition.standard_file,
            "标准devref": definition.standard_devref,
            "分类标记": definition.classification_marker,
            "实际devref": current_devref,
            "标准校验": validation_status,
            "异常类型": " + ".join(dict.fromkeys(issues)),
            "匹配来源": match_source,
            "x": _float(element, "x"),
            "y": _float(element, "y"),
            "w": _float(element, "w"),
            "h": _float(element, "h"),
            "node_area": (element.get("node_area") or "").strip(),
        }
        smart_type, smart_source = _smart_type_from_row(row)
        row["智能类型"] = smart_type
        row["是否智能"] = "YES" if smart_type == "SMART" else ("NO" if smart_type == "NORMAL" else "")
        row["智能判断来源"] = smart_source
        row["设备形态"] = _device_form(row)
        symbol_rows.append(row)
        if definition.symbol_usage in {"设备", "设备组成图元"}:
            device_rows.append(dict(row))

    # Composite RMUs are business devices even though they are not one uploaded icon.
    # They are emitted in the device sheet only; their internal uploaded symbols stay
    # independently visible and validated in 全部图元实例.
    for context in contexts:
        if not context.name:
            continue
        device_rows.append({
            "GFile": source.name,
            "facID": (root.get("facID") or "").strip(),
            "facName": (root.get("facName") or "").strip(),
            "图元用途": "设备",
            "设备类型": "RMU",
            "迁移设备类型": "RMU",
            "设备子类型": context.rmu_type,
            "设备层级": "组合设备",
            "设备形态": "COMPOSITE",
            "标准检查范围": "COMPOSITE",
            "SMART/NORMAL": context.scope,
            "智能类型": context.scope if context.scope in {"SMART", "NORMAL"} else "UNKNOWN",
            "是否智能": "YES" if context.scope == "SMART" else ("NO" if context.scope == "NORMAL" else ""),
            "智能判断来源": "RMU Context",
            "实例名称": context.name,
            "名称来源": "identify_rmus()",
            "名称置信度": "HIGH",
            "图中文字标签": context.name,
            "标签距离": 0,
            "所属RMU": "",
            "RMU类型": context.rmu_type,
            "XML元素": "组合识别",
            "ElementID": context.rect_id,
            "keyid": "",
            "key_name": "",
            "p_NameString": "",
            "标准图元文件": "组合设备（内部图元逐项校验）",
            "标准devref": "",
            "实际devref": "",
            "标准校验": "COMPOSITE",
            "异常类型": "",
            "匹配来源": "公共RMU识别",
            "x": _float(context.rect, "x"),
            "y": _float(context.rect, "y"),
            "w": _float(context.rect, "w"),
            "h": _float(context.rect, "h"),
            "node_area": "",
        })

    # Only the selected Bus-head CBreaker keyids are sent to Oracle. Downstream
    # device keyids are never queried; a valid CBreaker BAY is propagated through
    # the whole Bus-removed topology component.
    feeder_root_branches = _discover_feeder_root_branches(elements)
    anchor_contexts: dict[tuple[str, str], TopologyFeederAnchorContext] = {}
    anchor_issues: dict[tuple[str, str], str] = {}
    database_lookup_enabled = feeder_database_service is not None
    if feeder_database_service is not None:
        ids_by_table = _feeder_anchor_keyids_for_db(elements)
        try:
            anchor_contexts, anchor_issues = feeder_database_service.resolve_topology_feeder_anchors(ids_by_table)
        except Exception as exc:
            warnings.append(
                f"{source.name}: 所属馈线数据库锚点查询失败：{exc}。"
                "本文件所属馈线保持空白；其他图形内容继续解析。"
            )
            anchor_contexts = {}
            anchor_issues = {}
            database_lookup_enabled = False

    feeder_stats = _infer_feeder_membership(
        elements=elements,
        contexts=contexts,
        device_rows=device_rows,
        symbol_rows=symbol_rows,
        unmapped_rows=unmapped_rows,
        anchor_contexts=anchor_contexts,
        anchor_issues=anchor_issues,
        database_lookup_enabled=database_lookup_enabled,
        feeder_root_branches=feeder_root_branches,
    )
    if feeder_assignments is not None:
        feeder_assignments.update(
            {
                str(element_id): dict(fields)
                for element_id, fields in (feeder_stats.get("element_feeder_fields", {}) or {}).items()
                if str(element_id).strip()
            }
        )
    warnings.extend(str(item) for item in feeder_stats.get("warnings", []) if str(item).strip())

    return symbol_rows, device_rows, unmapped_rows, warnings



def _walk_structure(root: ET.Element):
    """Yield every XML node with stable hierarchy context.

    This is deliberately schema-neutral: the G format has many object families and
    nested containers, so the content inventory records the full tree instead of
    silently restricting itself to direct-layer graphical objects.
    """
    def visit(element: ET.Element, *, parent: ET.Element | None, depth: int, path: str):
        yield element, parent, depth, path
        sibling_counts: dict[str, int] = defaultdict(int)
        for child in list(element):
            tag = local_name(child.tag)
            sibling_counts[tag] += 1
            child_path = f"{path}/{tag}[{sibling_counts[tag]}]"
            yield from visit(child, parent=element, depth=depth + 1, path=child_path)

    root_tag = local_name(root.tag)
    yield from visit(root, parent=None, depth=0, path=f"/{root_tag}[1]")


def _contains_keyword(element: ET.Element, keywords: tuple[str, ...]) -> bool:
    haystack = " ".join(
        [local_name(element.tag), *[str(key) for key in element.attrib], *[str(value) for value in element.attrib.values()]]
    ).upper()
    return any(keyword in haystack for keyword in keywords)


def _content_category(element: ET.Element, mapped_row: dict[str, object] | None) -> str:
    tag = local_name(element.tag)
    if mapped_row is not None:
        usage = str(mapped_row.get("图元用途", "") or "").strip()
        return usage or "标准图元实例"
    if (element.get("devref") or "").strip():
        return "未定义图元"
    if tag in {"G", "Layer", "Group", "g", "layer", "group"}:
        return "结构/容器"
    if tag in {"Text", "DText"}:
        return "文本"
    if _contains_keyword(element, ("POKE", "JUMP", "NAVIGAT")):
        return "Poke/跳转"
    if _contains_keyword(element, ("MEASURE", "ANALOG", "SIGNAL", "TELEMET", "遥测", "量测")):
        return "量测/信号"
    if _contains_keyword(element, ("CONNECT", "CONNECTION", "LINE", "BUS", "LINK", "TOPO")):
        return "连接/拓扑"
    return "图形/其他对象"


def extract_file_content_inventory(
    source: Path,
    symbol_rows: list[dict[str, object]],
    device_rows: list[dict[str, object]],
    unmapped_rows: list[dict[str, object]],
    feeder_assignments: dict[str, dict[str, object]] | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Extract the complete XML/object hierarchy for one business G file."""
    tree = ET.parse(source)
    root = tree.getroot()
    mapped_by_id = {
        str(row.get("ElementID", "") or "").strip(): row
        for row in symbol_rows
        if str(row.get("ElementID", "") or "").strip()
    }
    unmapped_by_id = {
        str(row.get("ElementID", "") or "").strip(): row
        for row in unmapped_rows
        if str(row.get("ElementID", "") or "").strip()
    }
    rows: list[dict[str, object]] = []
    category_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    direct_count = len(direct_layer_elements(root))

    for element, parent, depth, path in _walk_structure(root):
        element_id = (element.get("id") or "").strip()
        mapped = mapped_by_id.get(element_id)
        category = _content_category(element, mapped)
        if mapped is None and element_id in unmapped_by_id:
            category = "未定义图元"
        tag = local_name(element.tag)
        text = _text_value(element)
        observed_metadata = _observed_content_metadata(tag)
        # Bus is a boundary only and deliberately never receives a feeder/BAY.
        # Every other XML object in a validated CBreaker component inherits the
        # topology assignment, including lines, BusDis and unmapped objects.
        feeder_fields = {}
        if tag != "Bus" and element_id:
            feeder_fields = dict((feeder_assignments or {}).get(element_id, {}))
        mapped_feeder = mapped if tag != "Bus" and mapped is not None else {}
        row = {
            "GFile": source.name,
            "facID": (root.get("facID") or "").strip(),
            "facName": (root.get("facName") or "").strip(),
            "层级深度": depth,
            "XML路径": path,
            "父XML元素": local_name(parent.tag) if parent is not None else "",
            "父ElementID": (parent.get("id") or "").strip() if parent is not None else "",
            "XML元素": tag,
            "ElementID": element_id,
            "内容分类": category,
            "图元用途": str(mapped.get("图元用途", "") if mapped else observed_metadata["图元用途"]),
            "设备类型": str(mapped.get("设备类型", "") if mapped else observed_metadata["设备类型"]),
            "设备子类型": str(mapped.get("设备子类型", "") if mapped else observed_metadata["设备子类型"]),
            "设备层级": str(mapped.get("设备层级", "") if mapped else observed_metadata["设备层级"]),
            "实例名称": str(mapped.get("实例名称", "") if mapped else ""),
            "所属RMU": str(mapped.get("所属RMU", "") if mapped else ""),
            "所属馈线": str(feeder_fields.get("所属馈线", mapped_feeder.get("所属馈线", ""))),
            "馈线站名": str(feeder_fields.get("馈线站名", mapped_feeder.get("馈线站名", ""))),
            "馈线BayID": str(feeder_fields.get("馈线BayID", mapped_feeder.get("馈线BayID", ""))),
            "馈线判断来源": str(feeder_fields.get("馈线判断来源", mapped_feeder.get("馈线判断来源", ""))),
            "馈线置信度": str(feeder_fields.get("馈线置信度", mapped_feeder.get("馈线置信度", ""))),
            "馈线锚点表": str(feeder_fields.get("馈线锚点表", mapped_feeder.get("馈线锚点表", ""))),
            "馈线锚点keyid": str(feeder_fields.get("馈线锚点keyid", mapped_feeder.get("馈线锚点keyid", ""))),
            "馈线Cluster": str(feeder_fields.get("馈线Cluster", mapped_feeder.get("馈线Cluster", ""))),
            "馈线证据设备数": feeder_fields.get("馈线证据设备数", mapped_feeder.get("馈线证据设备数", 0)),
            "馈线冲突": str(feeder_fields.get("馈线冲突", mapped_feeder.get("馈线冲突", ""))),
            "devref": (element.get("devref") or "").strip(),
            "keyid": (element.get("keyid") or "").strip(),
            "key_name": (element.get("key_name") or "").strip(),
            "key_name1": (element.get("key_name1") or "").strip(),
            "key_name2": (element.get("key_name2") or "").strip(),
            "p_NameString": (element.get("p_NameString") or "").strip(),
            "p_EngcodeString": (element.get("p_EngcodeString") or "").strip(),
            "link": (element.get("link") or "").strip(),
            "文本/值": text,
            "x": _float(element, "x"),
            "y": _float(element, "y"),
            "w": _float(element, "w"),
            "h": _float(element, "h"),
            "node_area": (element.get("node_area") or "").strip(),
            "子元素数": len(list(element)),
            "属性数": len(element.attrib),
            "全部属性": json.dumps(dict(element.attrib), ensure_ascii=False, sort_keys=True),
        }
        rows.append(row)
        category_counter[category] += 1
        tag_counter[tag] += 1

    primary_devices = [row for row in device_rows if _is_primary_device_row(row)]
    mismatch_count = sum(1 for row in symbol_rows if row.get("标准校验") == "MISMATCH")
    summary = {
        "GFile": source.name,
        "facID": (root.get("facID") or "").strip(),
        "facName": (root.get("facName") or "").strip(),
        "XML对象总数": len(rows),
        "直接图层对象": direct_count,
        "标准图元实例": len(symbol_rows),
        "业务设备总数": len(primary_devices),
        "设备/部件明细": len(device_rows),
        "RMU组合设备": sum(1 for row in primary_devices if str(row.get("设备类型", "")) == "RMU"),
        "文本对象": category_counter["文本"],
        "连接/拓扑对象": category_counter["连接/拓扑"],
        "Poke/跳转对象": category_counter["Poke/跳转"],
        "量测/信号对象": category_counter["量测/信号"],
        "未定义图元": len(unmapped_rows),
        "标准异常": mismatch_count,
        "XML元素类型数": len(tag_counter),
        "已识别所属馈线主设备": sum(1 for row in primary_devices if str(row.get("所属馈线", "") or "").strip()),
        "所属馈线数": len({str(row.get("所属馈线", "") or "").strip() for row in primary_devices if str(row.get("所属馈线", "") or "").strip()}),
        "所属馈线留空主设备": sum(1 for row in primary_devices if not str(row.get("所属馈线", "") or "").strip()),
        "根属性": json.dumps(dict(root.attrib), ensure_ascii=False, sort_keys=True),
    }
    return rows, summary


def _device_type_summary(device_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in device_rows:
        key = (
            str(row.get("设备类型", "") or "未分类"),
            str(row.get("设备子类型", "") or ""),
            str(row.get("设备层级", "") or ""),
        )
        item = groups.setdefault(key, {
            "设备类型": key[0], "设备子类型": key[1], "设备层级": key[2],
            "实例数": 0, "命名实例数": 0, "文件数": 0, "PASS": 0, "MISMATCH": 0,
            "示例名称": [], "_files": set(),
        })
        item["实例数"] = int(item["实例数"]) + 1
        name = str(row.get("实例名称", "") or "").strip()
        if name:
            item["命名实例数"] = int(item["命名实例数"]) + 1
            examples = item["示例名称"]
            if isinstance(examples, list) and name not in examples and len(examples) < 8:
                examples.append(name)
        status = str(row.get("标准校验", "") or "")
        if status in {"PASS", "MISMATCH"}:
            item[status] = int(item[status]) + 1
        files = item["_files"]
        if isinstance(files, set):
            files.add(str(row.get("GFile", "") or ""))
    result: list[dict[str, object]] = []
    for key in sorted(groups, key=lambda item: tuple(value.casefold() for value in item)):
        item = groups[key]
        files = item.pop("_files")
        item["文件数"] = len(files) if isinstance(files, set) else 0
        examples = item.get("示例名称", [])
        item["示例名称"] = "、".join(examples) if isinstance(examples, list) else str(examples)
        result.append(item)
    return result


def _xml_type_summary(content_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    counter: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for row in content_rows:
        key = (str(row.get("XML元素", "")), str(row.get("内容分类", "")))
        counter[key]["count"] += 1
        if str(row.get("devref", "")).strip():
            counter[key]["devref"] += 1
    return [
        {"XML元素": key[0], "内容分类": key[1], "对象数": counts["count"], "带devref对象": counts["devref"]}
        for key, counts in sorted(counter.items(), key=lambda item: (-item[1]["count"], item[0][0].casefold(), item[0][1].casefold()))
    ]


def _symbol_reference_summary(symbol_rows: list[dict[str, object]], unmapped_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    counter: dict[tuple[str, str, str, str], Counter] = defaultdict(Counter)
    for row in symbol_rows:
        key = (
            str(row.get("实际devref", "")), str(row.get("标准图元文件", "")),
            str(row.get("图元用途", "")), str(row.get("设备类型", "")),
        )
        counter[key]["total"] += 1
        counter[key][str(row.get("标准校验", ""))] += 1
    for row in unmapped_rows:
        key = (str(row.get("实际devref", "")), "", "未定义图元", "")
        counter[key]["total"] += 1
        counter[key]["UNMAPPED"] += 1
    return [
        {
            "实际devref": key[0], "标准图元文件": key[1], "图元用途": key[2], "设备类型": key[3],
            "实例数": counts["total"], "PASS": counts["PASS"], "MISMATCH": counts["MISMATCH"], "UNMAPPED": counts["UNMAPPED"],
        }
        for key, counts in sorted(counter.items(), key=lambda item: (-item[1]["total"], item[0][0].casefold()))
    ]


def _style_workbook(
    path: Path,
    symbol_rows: list[dict[str, object]],
    device_rows: list[dict[str, object]],
    unmapped_rows: list[dict[str, object]],
    definitions: list[StandardDefinition],
    *,
    content_rows: list[dict[str, object]] | None = None,
    file_summaries: list[dict[str, object]] | None = None,
) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    content_rows = list(content_rows or [])
    file_summaries = list(file_summaries or [])
    wb = Workbook()
    default = wb.active
    wb.remove(default)

    used_sheet_names: set[str] = set()

    def add_sheet(name: str, rows: list[dict[str, object]], columns: list[str]) -> None:
        safe_name = re.sub(r"[\\/*?:\[\]]+", "_", str(name or "Sheet")).strip() or "Sheet"
        base_name = safe_name[:31]
        sheet_name = base_name
        suffix = 2
        while sheet_name.casefold() in used_sheet_names:
            tail = f"_{suffix}"
            sheet_name = base_name[: 31 - len(tail)] + tail
            suffix += 1
        used_sheet_names.add(sheet_name.casefold())
        ws = wb.create_sheet(sheet_name)
        ws.append(columns)
        for row in rows:
            ws.append([row.get(column, "") for column in columns])
        header_fill = PatternFill("solid", fgColor="DCE6E3")
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        widths: dict[int, int] = {}
        # Width estimation is sampled for very large full-content sheets to keep report
        # generation responsive; all rows are still written to the workbook.
        sample_limit = min(ws.max_row, 3000)
        for row in ws.iter_rows(min_row=1, max_row=sample_limit):
            for cell in row:
                text = "" if cell.value is None else str(cell.value)
                widths[cell.column] = min(48, max(widths.get(cell.column, 8), len(text) + 2))
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for col, width in widths.items():
            ws.column_dimensions[get_column_letter(col)].width = max(10, width)
        ws.row_dimensions[1].height = 24

    primary_devices = [row for row in device_rows if _is_primary_device_row(row)]
    device_type_rows = _device_type_summary(primary_devices)
    xml_type_rows = _xml_type_summary(content_rows)
    reference_rows = _symbol_reference_summary(symbol_rows, unmapped_rows)
    migration_all_rows = [_migration_device_row(row) for row in device_rows]
    migration_primary_rows = [_migration_device_row(row) for row in primary_devices]
    migration_type_rows = _migration_type_summary(migration_primary_rows)

    overview_rows: list[dict[str, object]] = []
    if file_summaries:
        totals = Counter()
        for item in file_summaries:
            for field in (
                "XML对象总数", "直接图层对象", "标准图元实例", "业务设备总数", "设备/部件明细", "RMU组合设备",
                "文本对象", "连接/拓扑对象", "Poke/跳转对象", "量测/信号对象", "未定义图元", "标准异常",
                "已识别所属馈线主设备", "所属馈线留空主设备",
            ):
                totals[field] += int(item.get(field, 0) or 0)
        overview_rows = [
            {"指标": "G 文件数", "数量": len(file_summaries), "说明": "本次实际解析的业务 G 文件"},
            {"指标": "XML 对象总数", "数量": totals["XML对象总数"], "说明": "完整 XML 树中的全部节点/对象"},
            {"指标": "业务设备总数", "数量": totals["业务设备总数"], "说明": "独立设备 + 组合设备（包括 RMU、变压器及其他已分类设备）"},
            {"指标": "设备类型数", "数量": len(device_type_rows), "说明": "按设备类型/子类型/层级统计"},
            {"指标": "ADMS-SLD设备明细", "数量": len(migration_all_rows), "说明": "迁移标准化设备行：主设备 + RMU内部设备/部件"},
            {"指标": "ADMS-SLD主设备", "数量": len(migration_primary_rows), "说明": "独立设备 + RMU组合设备，不含RMU内部部件"},
            {"指标": "已识别所属馈线主设备", "数量": totals["已识别所属馈线主设备"], "说明": "仅查询馈线顶部 CBreaker(407)；有效 BAY 作为唯一权威根，Bus 之外整条下游真实拓扑直接继承馈线，不查询下游设备 keyid"},
            {"指标": "所属馈线留空主设备", "数量": totals["所属馈线留空主设备"], "说明": "没有任何设备证据或存在无法消解的馈线冲突时主动留空"},
            {"指标": "未命名迁移设备", "数量": sum(1 for row in migration_all_rows if not str(row.get("DeviceName", "")).strip()), "说明": "需要后续规则/标准补充的设备名称"},
            {"指标": "标准图元实例", "数量": totals["标准图元实例"], "说明": "已由 GLOBAL 标准识别的图元实例"},
            {"指标": "图元标准异常", "数量": totals["标准异常"], "说明": "devref / 几何 / Pins 等标准校验异常"},
            {"指标": "未定义图元", "数量": totals["未定义图元"], "说明": "业务 G 中存在 devref 但尚未映射到当前标准"},
            {"指标": "文本对象", "数量": totals["文本对象"], "说明": "Text / DText 内容"},
            {"指标": "连接/拓扑对象", "数量": totals["连接/拓扑对象"], "说明": "按 XML 标签/属性识别出的连接与拓扑候选"},
            {"指标": "Poke/跳转对象", "数量": totals["Poke/跳转对象"], "说明": "Poke / Jump / Navigation 相关对象"},
            {"指标": "量测/信号对象", "数量": totals["量测/信号对象"], "说明": "量测、模拟量、信号相关对象"},
        ]
    add_sheet("解析概览", overview_rows, ["指标", "数量", "说明"])
    add_sheet("文件汇总", file_summaries, [
        "GFile", "facID", "facName", "XML对象总数", "直接图层对象", "标准图元实例", "业务设备总数", "设备/部件明细",
        "RMU组合设备", "已识别所属馈线主设备", "所属馈线数", "所属馈线留空主设备",
        "文本对象", "连接/拓扑对象", "Poke/跳转对象", "量测/信号对象", "未定义图元", "标准异常", "XML元素类型数", "根属性",
    ])

    migration_columns = [
        "GFile", "facID", "facName", "FeederName",
        "DeviceType", "DeviceName", "IsSmart", "SmartType", "SmartSource",
        "DeviceForm", "ParentRMU", "RMUType", "DeviceSubtype", "ProfileDeviceType", "XML Element", "ElementID",
        "keyid", "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area", "StandardFile", "StandardDevref", "ActualDevref", "SymbolValidation",
        "ValidationIssue", "NameSource", "NameConfidence", "DisplayLabel", "DisplayLabelDistance", "QualityStatus", "x", "y", "w", "h",
    ]
    add_sheet("ADMS-SLD设备明细", migration_all_rows, migration_columns)
    add_sheet("ADMS-SLD主设备", migration_primary_rows, migration_columns)
    feeder_audit_columns = [
        "GFile", "DeviceType", "DeviceName", "XML Element", "ElementID", "keyid",
        "FeederName", "FeederStation", "FeederBayID", "FeederSource", "FeederConfidence",
        "FeederEvidenceCount", "FeederAnchorTable", "FeederAnchorKeyID", "FeederCluster", "FeederConflict",
    ]
    add_sheet("馈线关联审计", migration_all_rows, feeder_audit_columns)
    add_sheet("迁移设备类型统计", migration_type_rows, ["DeviceType", "Count", "Named", "SMART", "NORMAL", "SmartUnknown", "QualityPASS", "Files"])
    # Stable migration sheets are always created, even when empty, so downstream
    # comparison/import code can bind by sheet name without special-case discovery.
    known_types = ("RMU", "TRANSFORMER", "LBS", "FUSE", "REC", "SFI", "CB")
    for dtype in known_types:
        add_sheet(dtype, [row for row in migration_all_rows if str(row.get("DeviceType", "")) == dtype], migration_columns)
    extra_types = sorted({
        str(row.get("DeviceType", "") or "UNKNOWN")
        for row in migration_all_rows
        if str(row.get("DeviceType", "") or "UNKNOWN") not in set(known_types)
    })
    for dtype in extra_types:
        safe = re.sub(r"[\\/*?:\[\]]+", "_", dtype).strip() or "UNKNOWN"
        add_sheet(("DEV_" + safe)[:31], [row for row in migration_all_rows if str(row.get("DeviceType", "")) == dtype], migration_columns)
    add_sheet("RMU内部设备", [row for row in migration_all_rows if str(row.get("DeviceForm", "")) == "RMU_COMPONENT"], migration_columns)
    add_sheet("未命名设备", [row for row in migration_all_rows if not str(row.get("DeviceName", "")).strip()], migration_columns)
    add_sheet("其他设备", [row for row in migration_all_rows if str(row.get("DeviceType", "")) not in set(known_types)], migration_columns)

    device_columns = [
        "GFile", "facID", "facName", "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线证据设备数", "馈线锚点表", "馈线锚点keyid", "馈线Cluster", "馈线冲突",
        "设备类型", "迁移设备类型", "设备子类型", "实例名称", "标准检查范围", "SMART/NORMAL",
        "是否智能", "智能类型", "智能判断来源", "设备层级", "设备形态", "所属RMU",
        "标准图元文件", "标准devref", "实际devref", "标准校验", "异常类型", "XML元素", "ElementID", "keyid",
        "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area", "名称来源", "名称置信度", "图中文字标签", "标签距离", "x", "y", "w", "h",
    ]
    add_sheet("全部设备", primary_devices, device_columns)
    add_sheet("设备类型统计", device_type_rows, ["设备类型", "设备子类型", "设备层级", "实例数", "命名实例数", "文件数", "PASS", "MISMATCH", "示例名称"])
    # Compatibility/detail sheet: includes device components as well as primary devices.
    add_sheet("设备对比", device_rows, device_columns)

    instance_columns = [
        "GFile", "facID", "facName", "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线证据设备数", "馈线锚点表", "馈线锚点keyid", "馈线Cluster", "馈线冲突",
        "图元用途", "设备类型", "迁移设备类型", "设备子类型", "设备层级", "设备形态",
        "标准检查范围", "SMART/NORMAL", "是否智能", "智能类型", "智能判断来源",
        "实例名称", "名称来源", "名称置信度", "图中文字标签", "标签距离", "所属RMU", "RMU类型", "XML元素", "ElementID", "keyid",
        "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "标准图元文件", "标准devref", "实际devref", "标准校验", "异常类型",
        "匹配来源", "x", "y", "w", "h", "node_area",
    ]
    add_sheet("全部图元实例", symbol_rows, instance_columns)
    mismatch_rows = [row for row in symbol_rows if row.get("标准校验") == "MISMATCH"]
    add_sheet("图元校验异常", mismatch_rows, instance_columns)
    unmapped_columns = ["GFile", "XML元素", "ElementID", "实际devref", "keyid", "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area", "所属RMU", "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线锚点表", "馈线锚点keyid", "匹配状态", "x", "y"]
    add_sheet("未定义图元", unmapped_rows, unmapped_columns)
    add_sheet("图元引用统计", reference_rows, ["实际devref", "标准图元文件", "图元用途", "设备类型", "实例数", "PASS", "MISMATCH", "UNMAPPED"])

    content_columns = [
        "GFile", "facID", "facName", "层级深度", "XML路径", "父XML元素", "父ElementID", "XML元素", "ElementID", "内容分类",
        "图元用途", "设备类型", "设备子类型", "设备层级", "实例名称", "所属RMU", "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线证据设备数", "馈线锚点表", "馈线锚点keyid", "馈线Cluster", "馈线冲突",
        "devref", "keyid", "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area",
        "文本/值", "x", "y", "w", "h", "node_area", "子元素数", "属性数", "全部属性",
    ]
    add_sheet("全部内容清单", content_rows, content_columns)
    add_sheet("XML结构统计", xml_type_rows, ["XML元素", "内容分类", "对象数", "带devref对象"])
    add_sheet("文本内容", [r for r in content_rows if r.get("内容分类") == "文本"], content_columns)
    add_sheet("连接拓扑", [r for r in content_rows if r.get("内容分类") == "连接/拓扑"], content_columns)
    add_sheet("Poke跳转", [r for r in content_rows if r.get("内容分类") == "Poke/跳转"], content_columns)
    add_sheet("量测信号", [r for r in content_rows if r.get("内容分类") == "量测/信号"], content_columns)
    add_sheet("RMU组合设备", [r for r in primary_devices if str(r.get("设备类型", "")) == "RMU"], device_columns)

    summary = wb.create_sheet("图元统计")
    summary.append(["检查范围", "分类", "业务类型", "设备子类型", "标准图元文件", "标准devref", "实例数", "PASS", "MISMATCH"])
    counter: dict[tuple[str, str, str, str, str, str], Counter] = defaultdict(Counter)
    for definition in definitions:
        key = (
            definition.scope, definition.symbol_usage, definition.device_type,
            definition.device_subtype, definition.standard_file, definition.standard_devref,
        )
        counter[key]
    for row in symbol_rows:
        key = (
            str(row.get("标准检查范围", "")), str(row.get("图元用途", "")),
            str(row.get("设备类型", "")), str(row.get("设备子类型", "")),
            str(row.get("标准图元文件", "")), str(row.get("标准devref", "")),
        )
        counter[key]["total"] += 1
        counter[key][str(row.get("标准校验", ""))] += 1
    for key in sorted(counter, key=lambda item: tuple(str(value).casefold() for value in item)):
        counts = counter[key]
        summary.append([*key, counts["total"], counts["PASS"], counts["MISMATCH"]])
    for cell in summary[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DCE6E3")
    summary.freeze_panes = "A2"
    summary.auto_filter.ref = summary.dimensions
    for column, width in enumerate((14, 18, 24, 20, 34, 48, 12, 12, 12), 1):
        summary.column_dimensions[get_column_letter(column)].width = width

    wb.save(path)


def _html_table(title: str, rows: list[dict[str, object]], columns: list[str], *, open_by_default: bool = False) -> str:
    table_id = "t" + str(abs(hash((title, len(rows)))))
    open_attr = " open" if open_by_default else ""
    head = "".join(f"<th>{escape(col)}</th>" for col in columns)
    body_parts: list[str] = []
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col, "")
            text = "" if value is None else str(value)
            cells.append(f"<td title=\"{escape(text, quote=True)}\">{escape(text)}</td>")
        body_parts.append("<tr>" + "".join(cells) + "</tr>")
    return (
        f"<details{open_attr}><summary>{escape(title)} <span class='count'>{len(rows):,}</span></summary>"
        f"<div class='tools'><input type='search' placeholder='筛选本表…' oninput=\"filterTable('{table_id}',this.value)\"></div>"
        f"<div class='table-wrap'><table id='{table_id}'><thead><tr>{head}</tr></thead><tbody>{''.join(body_parts)}</tbody></table></div></details>"
    )


def _write_html_report(
    path: Path,
    *,
    profile: SiteSmartProfile,
    symbol_rows: list[dict[str, object]],
    device_rows: list[dict[str, object]],
    unmapped_rows: list[dict[str, object]],
    content_rows: list[dict[str, object]],
    file_summaries: list[dict[str, object]],
) -> None:
    primary_devices = [row for row in device_rows if _is_primary_device_row(row)]
    type_summary = _device_type_summary(primary_devices)
    xml_summary = _xml_type_summary(content_rows)
    reference_summary = _symbol_reference_summary(symbol_rows, unmapped_rows)
    mismatches = [row for row in symbol_rows if row.get("标准校验") == "MISMATCH"]
    rmu_rows = [row for row in primary_devices if str(row.get("设备类型", "")) == "RMU"]
    counts = {
        "G 文件": len(file_summaries),
        "全部 XML 对象": len(content_rows),
        "业务设备": len(primary_devices),
        "设备类型": len(type_summary),
        "标准图元实例": len(symbol_rows),
        "标准异常": len(mismatches),
        "未定义图元": len(unmapped_rows),
        "RMU": len(rmu_rows),
        "已识别所属馈线": sum(1 for row in primary_devices if str(row.get("所属馈线", "") or "").strip()),
        "所属馈线数": len({str(row.get("所属馈线", "") or "").strip() for row in primary_devices if str(row.get("所属馈线", "") or "").strip()}),
    }
    cards = "".join(
        f"<div class='card'><div class='value'>{value:,}</div><div class='label'>{escape(label)}</div></div>"
        for label, value in counts.items()
    )
    device_columns = [
        "GFile", "facID", "facName", "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线证据设备数", "馈线锚点表", "馈线锚点keyid", "馈线Cluster", "馈线冲突",
        "设备类型", "设备子类型", "实例名称", "设备层级", "SMART/NORMAL", "所属RMU",
        "标准图元文件", "标准devref", "实际devref", "标准校验", "异常类型", "XML元素", "ElementID", "keyid", "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area", "名称来源", "名称置信度", "x", "y", "w", "h",
    ]
    content_columns = [
        "GFile", "层级深度", "XML路径", "XML元素", "ElementID", "内容分类", "图元用途", "设备类型", "实例名称", "所属RMU",
        "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线证据设备数", "馈线锚点表", "馈线锚点keyid", "馈线Cluster", "馈线冲突", "devref", "keyid", "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area", "文本/值", "x", "y", "w", "h", "子元素数", "全部属性",
    ]
    symbol_columns = [
        "GFile", "图元用途", "设备类型", "设备子类型", "设备层级", "实例名称", "所属RMU", "所属馈线", "馈线站名", "馈线BayID", "馈线判断来源", "馈线置信度", "馈线锚点表", "馈线锚点keyid", "XML元素", "ElementID",
        "标准图元文件", "标准devref", "实际devref", "标准校验", "异常类型", "匹配来源", "x", "y", "w", "h",
    ]
    file_columns = [
        "GFile", "facID", "facName", "XML对象总数", "直接图层对象", "标准图元实例", "业务设备总数", "设备/部件明细", "RMU组合设备",
        "已识别所属馈线主设备", "所属馈线数", "所属馈线留空主设备", "文本对象", "连接/拓扑对象", "Poke/跳转对象", "量测/信号对象", "未定义图元", "标准异常", "XML元素类型数",
    ]
    sections = [
        _html_table("文件级解析汇总", file_summaries, file_columns, open_by_default=True),
        _html_table("设备类型统计（RMU、变压器及其他设备）", type_summary, ["设备类型", "设备子类型", "设备层级", "实例数", "命名实例数", "文件数", "PASS", "MISMATCH", "示例名称"], open_by_default=True),
        _html_table("ADMS-SLD 迁移设备明细", [_migration_device_row(row) for row in device_rows], [
            "GFile", "facID", "facName", "FeederName",
            "DeviceType", "DeviceName", "IsSmart", "SmartType", "DeviceForm", "ParentRMU",
            "DeviceSubtype", "XML Element", "ElementID", "keyid", "ActualDevref", "NameSource", "NameConfidence", "DisplayLabel", "QualityStatus"
        ], open_by_default=True),
        _html_table("全部业务设备", primary_devices, device_columns, open_by_default=True),
        _html_table("RMU 组合设备", rmu_rows, device_columns),
        _html_table("图元标准异常", mismatches, symbol_columns, open_by_default=bool(mismatches)),
        _html_table("未定义图元", unmapped_rows, ["GFile", "XML元素", "ElementID", "实际devref", "keyid", "key_name", "key_name1", "key_name2", "p_NameString", "p_EngcodeString", "link", "node_area", "所属RMU", "匹配状态", "x", "y"]),
        _html_table("全部标准图元实例", symbol_rows, symbol_columns),
        _html_table("图元引用统计", reference_summary, ["实际devref", "标准图元文件", "图元用途", "设备类型", "实例数", "PASS", "MISMATCH", "UNMAPPED"]),
        _html_table("XML 元素/结构统计", xml_summary, ["XML元素", "内容分类", "对象数", "带devref对象"]),
        _html_table("连接/拓扑对象", [r for r in content_rows if r.get("内容分类") == "连接/拓扑"], content_columns),
        _html_table("量测/信号对象", [r for r in content_rows if r.get("内容分类") == "量测/信号"], content_columns),
        _html_table("Poke/跳转对象", [r for r in content_rows if r.get("内容分类") == "Poke/跳转"], content_columns),
        _html_table("文本内容", [r for r in content_rows if r.get("内容分类") == "文本"], content_columns),
        _html_table("完整 G XML / 对象清单", content_rows, content_columns),
    ]
    profile_title = f"{profile.site_name} / {profile.profile_name} / V{profile.profile_version}"
    document = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>G 图形内容解析报告</title>
<style>
:root{{--bg:#f5f8f7;--panel:#fff;--ink:#15312b;--muted:#60736e;--line:#d9e5e1;--accent:#087f5b;--bad:#a61b1b}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 Arial,'Microsoft YaHei',sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}} h1{{margin:0 0 6px;font-size:28px}} .subtitle{{color:var(--muted);margin-bottom:20px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}} .card{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}}
.value{{font-size:24px;font-weight:700;color:var(--accent)}} .label{{color:var(--muted)}} .note{{background:#e9f6f1;border-left:4px solid var(--accent);padding:12px 14px;border-radius:8px;margin:16px 0}}
details{{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin:12px 0;overflow:hidden}} summary{{cursor:pointer;font-size:16px;font-weight:700;padding:14px 16px}}
.count{{font-weight:400;color:var(--muted);margin-left:8px}} .tools{{padding:0 16px 10px}} input{{width:min(520px,100%);padding:9px 12px;border:1px solid var(--line);border-radius:7px}}
.table-wrap{{overflow:auto;max-height:620px;border-top:1px solid var(--line)}} table{{border-collapse:collapse;width:max-content;min-width:100%}} th,td{{border-bottom:1px solid #edf2f0;border-right:1px solid #edf2f0;padding:7px 9px;text-align:left;vertical-align:top;max-width:360px;white-space:pre-wrap;word-break:break-word}}
th{{position:sticky;top:0;background:#e5efec;z-index:1}} tr:nth-child(even) td{{background:#fbfcfc}} .footer{{color:var(--muted);font-size:12px;margin-top:20px}}
</style>
<script>function filterTable(id,q){{q=(q||'').toLowerCase();document.querySelectorAll('#'+id+' tbody tr').forEach(function(r){{r.style.display=r.innerText.toLowerCase().includes(q)?'':'none';}});}}</script>
</head><body><main>
<h1>G 图形内容解析与拓扑分析报告</h1><div class='subtitle'>全量设备、图元、文本、量测/信号、Poke/跳转、连接/拓扑与完整 XML 层级清单</div>
<div class='note'><b>执行标准：</b>{escape(profile_title)}。业务 G 与服务器只读；报告只解析和校验，不修改源文件。设备类型以已确认的图元标准分类为准，RMU 继续作为组合设备单独汇总。所属馈线把 Bus 仅作为上游边界并排除在归属结果之外；每个分支只查询顶部 CBreaker(407) keyid，通过 long2_to_long1/get_tab_no + SYS_TABLE_INFO 校验后查询 BAY_ID → BAY.NAME/ST_ID → SUBSTATION.NAME。有效 CBreaker BAY 是唯一权威根，Bus 之外的连接线、BusDis、环网柜内部图元和未定义对象均继承同一馈线/BAY；不使用下游设备 keyid、文件名、facID/facName、FeedLine文字或空间距离补猜。CBreaker 未关联时，该分支 Feeder/BAY 保持空白并告警。</div>
<div class='cards'>{cards}</div>{''.join(sections)}
<div class='footer'>报告与 Excel 同次生成；“完整 G XML / 对象清单”记录每个 XML 节点的路径、父级、属性和业务分类，便于进一步追溯。</div>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def process_symbol_inventory(
    source_path: Path,
    input_mode: InputMode,
    output_dir: Path,
    profile: SiteSmartProfile,
    log: Callable[[str], None] = print,
    progress: Callable[[int], None] | None = None,
    feeder_database_service: OracleDatabaseService | None = None,
) -> ProcessingResult:
    files = discover_g_inputs(Path(source_path), input_mode)
    if not files:
        raise ValueError("没有找到可解析的 G 文件。")
    profile = profile.normalized()
    if not profile.authoritative_ready:
        raise ValueError("当前全局图元标准没有任何已配置的标准图元，请先到“服务器图元更新检查”维护标准。")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_symbols: list[dict[str, object]] = []
    all_devices: list[dict[str, object]] = []
    all_unmapped: list[dict[str, object]] = []
    all_content: list[dict[str, object]] = []
    file_summaries: list[dict[str, object]] = []
    warnings: list[str] = []
    total = max(1, len(files))
    if progress:
        progress(0)
    for index, source in enumerate(files, 1):
        log(f"[G 图形内容解析] {index}/{len(files)} {source.name}")
        feeder_assignments: dict[str, dict[str, object]] = {}
        symbol_rows, device_rows, unmapped_rows, file_warnings = extract_file_inventory(
            source,
            profile,
            feeder_database_service=feeder_database_service,
            feeder_assignments=feeder_assignments,
        )
        if feeder_database_service is not None:
            lookup_stats = getattr(feeder_database_service, "last_topology_feeder_lookup_stats", {}) or {}
            lookup_labels = (
                ("BREAKER", "CBreaker→BREAKER(407)"),
                ("DISCONNECTOR", "Disconnector→DISCONNECTOR(408)"),
                ("GROUNDDISCONNECTOR", "GroundDisconnector→GROUNDDISCONNECTOR(409)"),
            )
            for table_name, label in lookup_labels:
                stat = lookup_stats.get(table_name, {})
                requested = int(stat.get("requested", 0) or 0)
                decoded = int(stat.get("decoded", 0) or 0)
                table_valid = int(stat.get("table_valid", 0) or 0)
                device_matched = int(stat.get("device_matched", stat.get("matched", 0)) or 0)
                valid_bay = int(stat.get("valid_bay_id", 0) or 0)
                bay_matched = int(stat.get("bay_matched", 0) or 0)
                station_matched = int(stat.get("station_matched", 0) or 0)
                resolved = int(stat.get("resolved", 0) or 0)
                unresolved = int(stat.get("unmatched", 0) or 0)
                if requested:
                    log(
                        f"  [馈线数据库] {label}: G keyid {requested}；解码 {decoded}；表号校验 {table_valid}；"
                        f"设备表匹配 {device_matched}；BAY_ID有效 {valid_bay}；BAY匹配 {bay_matched}；"
                        f"厂站匹配 {station_matched}；有效锚点 {resolved}；未解析 {unresolved}。"
                    )
                    resolved_samples = stat.get("sample_resolved", []) or []
                    for sample in resolved_samples:
                        log(f"    锚点示例: {sample}")
                    samples = stat.get("sample_unmatched", []) or []
                    if samples:
                        log(f"    未解析示例 keyid: {', '.join(str(item) for item in samples)}")
        content_rows, file_summary = extract_file_content_inventory(
            source, symbol_rows, device_rows, unmapped_rows, feeder_assignments
        )
        all_symbols.extend(symbol_rows)
        all_devices.extend(device_rows)
        all_unmapped.extend(unmapped_rows)
        all_content.extend(content_rows)
        file_summaries.append(file_summary)
        warnings.extend(file_warnings)
        for warning in file_warnings:
            log(f"  [警告] {warning}")
        primary_count = int(file_summary.get("业务设备总数", 0) or 0)
        feeder_resolved = int(file_summary.get("已识别所属馈线主设备", 0) or 0)
        feeder_count = int(file_summary.get("所属馈线数", 0) or 0)
        log(
            f"  业务设备 {primary_count}；所属馈线 {feeder_resolved}/{primary_count}（{feeder_count} 条 Feeder Cluster）；"
            f"标准图元实例 {len(symbol_rows)}；完整 XML/对象 {len(content_rows)}；未定义图元 {len(unmapped_rows)}。"
        )
        if progress:
            progress(round(index * 82 / total))

    workbook = output_dir / "g-content-inventory.xlsx"
    html_report = output_dir / "g-content-analysis-report.html"
    definitions = _profile_definitions(profile)
    if progress:
        progress(86)
    log("[报告] 正在生成多 Sheet Excel：ADMS-SLD设备明细、RMU/TRANSFORMER/LBS/FUSE/REC/SFI/CB、全部内容与审计数据。")
    _style_workbook(
        workbook, all_symbols, all_devices, all_unmapped, definitions,
        content_rows=all_content, file_summaries=file_summaries,
    )
    if progress:
        progress(94)
    log("[报告] 正在生成独立 HTML 综合报告。")
    _write_html_report(
        html_report,
        profile=profile,
        symbol_rows=all_symbols,
        device_rows=all_devices,
        unmapped_rows=all_unmapped,
        content_rows=all_content,
        file_summaries=file_summaries,
    )
    if progress:
        progress(100)

    mismatch_count = sum(1 for row in all_symbols if row.get("标准校验") == "MISMATCH")
    primary_devices = [row for row in all_devices if _is_primary_device_row(row)]
    named_device_count = sum(1 for row in primary_devices if str(row.get("实例名称", "")).strip())
    device_type_count = len(_device_type_summary(primary_devices))
    return ProcessingResult(
        success=not mismatch_count,
        output_files=[workbook, html_report],
        warnings=warnings,
        statistics={
            "G文件数": len(files),
            "全部XML对象": len(all_content),
            "业务设备总数": len(primary_devices),
            "设备类型数": device_type_count,
            "ADMS-SLD设备明细": len(all_devices),
            "ADMS-SLD主设备": len(primary_devices),
            "已识别所属馈线主设备": sum(1 for row in primary_devices if str(row.get("所属馈线", "") or "").strip()),
            "所属馈线数": len({str(row.get("所属馈线", "") or "").strip() for row in primary_devices if str(row.get("所属馈线", "") or "").strip()}),
            "所属馈线留空主设备": sum(1 for row in primary_devices if not str(row.get("所属馈线", "") or "").strip()),
            "未命名迁移设备": sum(1 for row in all_devices if not str(row.get("实例名称", "")).strip()),
            "已配置标准图元实例": len(all_symbols),
            "设备/部件明细": len(all_devices),
            "设备已识别名称": named_device_count,
            "图元标准异常": mismatch_count,
            "未定义图元实例": len(all_unmapped),
            "excel_path": str(workbook),
            "html_path": str(html_report),
        },
    )
