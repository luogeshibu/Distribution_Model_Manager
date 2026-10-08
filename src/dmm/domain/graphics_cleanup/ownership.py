from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .makkah_parser import Box, GObject, ParsedG
from .master_station_frames import find_master_station_frames


SOURCE_BREAKER_TAG = "CBreaker"
FEEDLINE_TAG = "FeedLine"
LINE_TAGS = {"FeedLine", "ConnectLine", "Bus"}
NETWORK_TAGS = {
    "FeedLine",
    "ConnectLine",
    "Bus",
    "CBreaker",
    "CBreakerDis",
    "Disconnector",
    "GroundDisconnector",
    "ZhaiWaiJieDiDaoZha",
    "BusDis",
    "TransformerDis",
}
MODEL_EVIDENCE_TAGS = {"CBreakerDis", "TransformerDis"}
NOP_SWITCH_TAGS = {"CBreakerDis", "Disconnector", "CBreaker"}

# Deliberately strict geometry repair.  The old topology implementation used
# much larger distance tolerances and could bridge two nearby but electrically
# separate ring-feeder branches.  These values are G-coordinate units.
ENDPOINT_TOLERANCE = 3.0
ENDPOINT_TO_SEGMENT_TOLERANCE = 2.0
NOP_SWITCH_SEARCH_DISTANCE = 330.0
SOURCE_LABEL_SEARCH_DISTANCE = 220.0
LOCAL_EVIDENCE_FALLBACK_DISTANCE = 35.0


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int_or_none(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_engineering_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _norm(value).upper())


def _box_distance(first: Box, second: Box) -> float:
    dx = max(first.left - second.right, second.left - first.right, 0.0)
    dy = max(first.top - second.bottom, second.top - first.bottom, 0.0)
    return math.hypot(dx, dy)


def _point_to_segment_distance(px, py, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return math.hypot(px - qx, py - qy)


def _polyline_points(obj: GObject) -> List[Tuple[float, float]]:
    raw = _norm(obj.attrs.get("d"))
    points = []
    if raw:
        for x, y in re.findall(
            r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
            raw,
        ):
            points.append((float(x), float(y)))
    if len(points) >= 2:
        return points
    box = obj.box
    if box.w >= box.h:
        return [(box.left, box.cy), (box.right, box.cy)]
    return [(box.cx, box.top), (box.cx, box.bottom)]


def _segments(obj: GObject):
    pts = _polyline_points(obj)
    return list(zip(pts[:-1], pts[1:]))


def _endpoints(obj: GObject):
    pts = _polyline_points(obj)
    return [pts[0], pts[-1]] if len(pts) >= 2 else []


def _reference_ids(obj: GObject) -> Set[str]:
    """Return explicit object IDs referenced by link/node_area attributes."""
    refs: Set[str] = set()
    for attr in ("link", "node_area"):
        raw = _norm(obj.attrs.get(attr))
        if not raw:
            continue
        for item in raw.split(";"):
            parts = [part.strip() for part in item.split(",")]
            if not parts:
                continue
            candidate = parts[-1]
            if candidate:
                refs.add(candidate)
    return refs


def _extract_feeder_token(text: str) -> str:
    value = _norm(text).upper().replace("\n", " ")
    match = re.search(
        r"\b([A-Z]{2,}[A-Z0-9]*)(?:[-_\s]+)(\d{1,3})\b",
        value,
    )
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}"


def _is_nop_text(text: str) -> bool:
    compact = re.sub(r"[\s._-]+", "", _norm(text).upper())
    return compact == "NOP"


class FeederOwnershipResolver:
    """Resolve FeedLine -> FEEDER_ID for Makkah multi-feeder ring drawings.

    The resolver intentionally does *not* try to reconstruct the whole drawing
    perfectly.  It combines several conservative evidence sources:

    1. main-station ``CBreaker`` + nearby feeder title -> database FEEDER_ID;
    2. already-associated RMU/switch/transformer models -> FEEDER_ID;
    3. explicit G ``link`` / ``node_area`` relations;
    4. only very strict endpoint geometry repairs for missing XML links;
    5. NOP labels become propagation barriers.

    If one strict electrical component contains evidence for more than one
    feeder, the component is a CONFLICT and is never auto-associated.  Missing
    evidence is UNRESOLVED instead of being guessed from a distant object.
    """

    def __init__(
        self,
        db,
        feeder_table_id: int = 13500,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.db = db
        self.feeder_table_id = int(feeder_table_id)
        self.log = log or (lambda _msg: None)

    @staticmethod
    def _add_edge(adjacency: Dict[str, Set[str]], a: str, b: str):
        if not a or not b or a == b:
            return
        adjacency[a].add(b)
        adjacency[b].add(a)

    def _source_anchor_candidates(self, parsed: ParsedG) -> List[Dict[str, Any]]:
        """Resolve source feeders from CBreaker Bay frames.

        Makkah rule: a source breaker is usable only when it sits inside an
        innermost rectangle and that frame has a nearby feeder title with no
        background, such as MNA4-12 / ARF2-07. Text color is ignored; format,
        distance and one-to-one Bay/title ownership prevent unrelated labels
        from becoming feeder anchors.
        """
        anchors = []
        for frame_info in find_master_station_frames(parsed):
            if len(frame_info.breakers) != 1:
                anchors.append({
                    "breaker_xml_id": "",
                    "breaker": None,
                    "frame_xml_id": frame_info.frame.xml_id,
                    "label": frame_info.feeder_label,
                    "normalized_label": _normalize_engineering_name(frame_info.feeder_label),
                    "text_xml_id": frame_info.label_obj.xml_id if frame_info.label_obj else "",
                    "distance": (
                        round(frame_info.label_distance, 3)
                        if frame_info.label_distance is not None else ""
                    ),
                    "feeder_id": "",
                    "feeder_name": "",
                    "db_match_count": 0,
                    "status": "SOURCE_CBREAKER_NOT_UNIQUE",
                })
                continue

            breaker = frame_info.breaker
            if not frame_info.feeder_label:
                anchors.append({
                    "breaker_xml_id": breaker.xml_id,
                    "breaker": breaker,
                    "frame_xml_id": frame_info.frame.xml_id,
                    "label": "",
                    "normalized_label": "",
                    "text_xml_id": "",
                    "distance": "",
                    "feeder_id": "",
                    "feeder_name": "",
                    "db_match_count": 0,
                    "status": "SOURCE_WHITE_LABEL_NOT_FOUND",
                })
                continue

            try:
                records = self.db.find_feeders_by_name_hint(
                    frame_info.feeder_label,
                    table_id=self.feeder_table_id,
                )
            except Exception as exc:
                records = []
                lookup_error = str(exc)
            else:
                lookup_error = ""

            anchor = {
                "breaker_xml_id": breaker.xml_id,
                "breaker": breaker,
                "frame_xml_id": frame_info.frame.xml_id,
                "label": frame_info.feeder_label,
                "raw_label": str(frame_info.label_obj.attrs.get("ts") or "").strip()
                if frame_info.label_obj else "",
                "normalized_label": _normalize_engineering_name(frame_info.feeder_label),
                "text_xml_id": frame_info.label_obj.xml_id if frame_info.label_obj else "",
                "distance": (
                    round(frame_info.label_distance, 3)
                    if frame_info.label_distance is not None else ""
                ),
                "feeder_id": "",
                "feeder_name": "",
                "db_match_count": len(records),
                "status": "",
                "lookup_error": lookup_error,
            }
            if len(records) == 1 and _int_or_none(records[0].get("id")) is not None:
                anchor["feeder_id"] = int(records[0]["id"])
                anchor["feeder_name"] = _norm(
                    records[0].get("display_name") or records[0].get("name")
                )
                anchor["status"] = "SOURCE_CONFIRMED"
            elif len(records) == 0:
                anchor["status"] = "SOURCE_DB_NOT_FOUND"
            else:
                anchor["status"] = "SOURCE_DB_NOT_UNIQUE"
            anchors.append(anchor)
        return anchors

    @staticmethod
    def _nop_boundary_nodes(parsed: ParsedG) -> Tuple[Set[str], List[Dict[str, Any]]]:
        switches = [obj for obj in parsed.objects if obj.tag in NOP_SWITCH_TAGS]
        boundaries: Set[str] = set()
        rows = []
        for text_obj in parsed.objects:
            if text_obj.tag.lower() != "text" or not _is_nop_text(text_obj.attrs.get("ts", "")):
                continue
            candidates = []
            for obj in switches:
                distance = text_obj.box.edge_distance(obj.box)
                if distance <= NOP_SWITCH_SEARCH_DISTANCE:
                    # RMU/load-breaker objects are preferred over station source
                    # breakers when a label is close to both.
                    priority = 0 if obj.tag == "CBreakerDis" else 1
                    candidates.append((priority, distance, obj.xml_index, obj))
            if not candidates:
                rows.append({
                    "text_xml_id": text_obj.xml_id,
                    "x": round(text_obj.box.cx, 3),
                    "y": round(text_obj.box.cy, 3),
                    "switch_xml_ids": [],
                    "status": "NOP_SWITCH_NOT_FOUND",
                })
                continue
            candidates.sort(key=lambda item: (item[0], item[1], item[2]))
            best_priority = candidates[0][0]
            same_priority = [item for item in candidates if item[0] == best_priority]
            best_distance = same_priority[0][1]
            # If the label is exactly between two Y/Q switches, blocking both is
            # safer than choosing one and allowing feeder ownership to cross.
            selected = [
                item[3]
                for item in same_priority
                if item[1] <= best_distance + 20.0
            ]
            ids = []
            for obj in selected:
                if obj.xml_id:
                    boundaries.add(obj.xml_id)
                    ids.append(obj.xml_id)
            rows.append({
                "text_xml_id": text_obj.xml_id,
                "x": round(text_obj.box.cx, 3),
                "y": round(text_obj.box.cy, 3),
                "switch_xml_ids": ids,
                "distance": round(best_distance, 3),
                "status": "NOP_BOUNDARY" if ids else "NOP_SWITCH_NOT_FOUND",
            })
        return boundaries, rows

    @staticmethod
    def _build_graph(parsed: ParsedG) -> Tuple[Dict[str, GObject], Dict[str, Set[str]], int]:
        network = [
            obj for obj in parsed.objects
            if obj.tag in NETWORK_TAGS and obj.xml_id
        ]
        by_id = {obj.xml_id: obj for obj in network}
        adjacency: Dict[str, Set[str]] = defaultdict(set)

        # Strongest evidence: explicit G references.
        for obj in network:
            for ref in _reference_ids(obj):
                if ref in by_id:
                    FeederOwnershipResolver._add_edge(adjacency, obj.xml_id, ref)

        # Strict geometric repair only for line-like objects.  This repairs the
        # common Makkah export defect where two line endpoints are identical but
        # link/node_area is missing, without joining merely-nearby parallel lines.
        line_objects = [obj for obj in network if obj.tag in LINE_TAGS]
        endpoint_grid: Dict[Tuple[int, int], List[Tuple[str, Tuple[float, float]]]] = defaultdict(list)
        grid = ENDPOINT_TOLERANCE
        repaired_pairs: Set[Tuple[str, str]] = set()

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
                                if other_id not in adjacency.get(obj.xml_id, set()) and pair not in repaired_pairs:
                                    repaired_pairs.add(pair)
                                    FeederOwnershipResolver._add_edge(adjacency, *pair)

        # T-junction repair: a line endpoint may terminate in the middle of a
        # second line.  Index segments in coarse cells and require <=2 units.
        segment_cell_size = 80.0
        segment_grid: Dict[Tuple[int, int], List[Tuple[str, Tuple[Tuple[float, float], Tuple[float, float]]]]] = defaultdict(list)
        for obj in line_objects:
            for seg in _segments(obj):
                (a, b) = seg
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
                    (a, b) = seg
                    if _point_to_segment_distance(
                        point[0], point[1], a[0], a[1], b[0], b[1]
                    ) <= ENDPOINT_TO_SEGMENT_TOLERANCE:
                        pair = tuple(sorted((obj.xml_id, other_id)))
                        if other_id not in adjacency.get(obj.xml_id, set()) and pair not in repaired_pairs:
                            repaired_pairs.add(pair)
                            FeederOwnershipResolver._add_edge(adjacency, *pair)

        for xml_id in by_id:
            adjacency.setdefault(xml_id, set())
        return by_id, adjacency, len(repaired_pairs)

    @staticmethod
    def _box_overlaps(first: Box, second: Box, tolerance: float = 4.0) -> bool:
        return not (
            first.right + tolerance < second.left
            or second.right + tolerance < first.left
            or first.bottom + tolerance < second.top
            or second.bottom + tolerance < first.top
        )

    def resolve(
        self,
        parsed: ParsedG,
        rmu_anchors: Iterable[Dict[str, Any]],
        model_reference_for_object: Callable[[GObject], Optional[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        source_anchors = self._source_anchor_candidates(parsed)
        boundary_nodes, nop_rows = self._nop_boundary_nodes(parsed)
        by_id, adjacency, repaired_edge_count = self._build_graph(parsed)

        evidence: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        def add_evidence(xml_id: str, feeder_id, source: str, label: str, detail: str = ""):
            fid = _int_or_none(feeder_id)
            if not xml_id or fid is None or xml_id in boundary_nodes:
                return
            item = {
                "feeder_id": fid,
                "source": source,
                "label": _norm(label),
                "detail": _norm(detail),
                "xml_id": xml_id,
            }
            key = (fid, source, _norm(label), _norm(detail))
            if key not in {
                (x.get("feeder_id"), x.get("source"), x.get("label"), x.get("detail"))
                for x in evidence[xml_id]
            }:
                evidence[xml_id].append(item)

        for anchor in source_anchors:
            if anchor.get("status") == "SOURCE_CONFIRMED":
                add_evidence(
                    anchor.get("breaker_xml_id", ""),
                    anchor.get("feeder_id"),
                    "MAIN_CBREAKER",
                    anchor.get("label", ""),
                    anchor.get("feeder_name", ""),
                )

        # Already-associated pole switch / transformer objects are independent
        # feeder facts.  Only objects with a current keyid trigger DB lookups.
        for obj in parsed.objects:
            if obj.tag not in MODEL_EVIDENCE_TAGS or not obj.xml_id:
                continue
            if not any(_norm(obj.attrs.get(key)) for key in ("keyid", "keyid1", "keyid2")):
                continue
            ref = model_reference_for_object(obj)
            if ref and _int_or_none(ref.get("feeder_id")) is not None:
                add_evidence(
                    obj.xml_id,
                    ref.get("feeder_id"),
                    "ASSOCIATED_DEVICE",
                    ref.get("device_name", ""),
                    f"table={ref.get('table_id', '')};device={ref.get('device_id', '')}",
                )

        # A trusted RMU provides FEEDER_ID evidence locally, but it does not
        # electrically merge every branch inside its frame.  We seed only the
        # network objects that physically touch/enter that cabinet; NOP switch
        # nodes are excluded above, so propagation cannot cross the open point.
        trusted_rmus = [
            anchor for anchor in rmu_anchors
            if anchor.get("trusted") and _int_or_none(anchor.get("feeder_id")) is not None
        ]
        network_objects = list(by_id.values())
        for anchor in trusted_rmus:
            frame_ref = anchor.get("frame")
            frame_obj = getattr(frame_ref, "frame", frame_ref)
            if not frame_obj:
                continue
            for obj in network_objects:
                if self._box_overlaps(obj.box, frame_obj.box, tolerance=4.0):
                    add_evidence(
                        obj.xml_id,
                        anchor.get("feeder_id"),
                        "TRUSTED_RMU",
                        anchor.get("rmu_name", ""),
                        f"frame={anchor.get('frame_xml_id', '')}",
                    )

        # Build connected components with NOP switch nodes removed.  Removing a
        # boundary node, rather than merely tagging it, creates a hard feeder
        # propagation stop on both of its terminals.
        component_by_id: Dict[str, int] = {}
        components: Dict[int, List[str]] = {}
        component_no = 0
        for xml_id in by_id:
            if xml_id in boundary_nodes or xml_id in component_by_id:
                continue
            component_no += 1
            stack = [xml_id]
            component_by_id[xml_id] = component_no
            members = []
            while stack:
                current = stack.pop()
                members.append(current)
                for nxt in adjacency.get(current, ()):
                    if nxt in boundary_nodes or nxt in component_by_id:
                        continue
                    component_by_id[nxt] = component_no
                    stack.append(nxt)
            components[component_no] = members

        component_evidence: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        for comp, members in components.items():
            seen = set()
            for xml_id in members:
                for item in evidence.get(xml_id, []):
                    key = (
                        item.get("feeder_id"), item.get("source"),
                        item.get("xml_id"), item.get("label"),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    component_evidence[comp].append(item)

        evidence_objects = [
            (by_id[xml_id], item)
            for xml_id, items in evidence.items()
            if xml_id in by_id
            for item in items
        ]

        ownership: Dict[str, Dict[str, Any]] = {}
        for obj in [item for item in parsed.objects if item.tag == FEEDLINE_TAG]:
            comp = component_by_id.get(obj.xml_id)
            items = list(component_evidence.get(comp, [])) if comp is not None else []
            method = "STRICT_TOPOLOGY"

            if not items:
                # Last-resort local evidence is intentionally very tight.  It
                # never searches for a globally nearest device.
                nearby = []
                for evidence_obj, evidence_item in evidence_objects:
                    distance = _box_distance(obj.box, evidence_obj.box)
                    if distance <= LOCAL_EVIDENCE_FALLBACK_DISTANCE:
                        nearby.append((distance, evidence_item))
                if nearby:
                    nearby.sort(key=lambda pair: pair[0])
                    items = [dict(item, local_distance=round(distance, 3)) for distance, item in nearby]
                    method = "LOCAL_GEOMETRY_FALLBACK"

            feeder_ids = sorted({
                int(item["feeder_id"])
                for item in items
                if _int_or_none(item.get("feeder_id")) is not None
            })
            sources = sorted({str(item.get("source") or "") for item in items if item.get("source")})
            labels = []
            for item in items:
                label = _norm(item.get("label")) or str(item.get("feeder_id", ""))
                token = f"{item.get('source')}:{label}"
                if token not in labels:
                    labels.append(token)

            if len(feeder_ids) > 1:
                status = "CONFLICT"
                feeder_id = ""
                reason = (
                    "FEEDER_OWNERSHIP_CONFLICT: 同一严格连接区域检测到多个FEEDER_ID="
                    + ",".join(str(x) for x in feeder_ids)
                    + "；未检测到足以隔离它们的NOP边界，禁止自动关联。"
                )
            elif len(feeder_ids) == 1:
                feeder_id = feeder_ids[0]
                if "MAIN_CBREAKER" in sources or len({item.get("xml_id") for item in items}) >= 2:
                    status = "CONFIRMED"
                else:
                    status = "INHERITED"
                reason = (
                    f"FEEDER_OWNERSHIP_{status}: FEEDER_ID={feeder_id}; "
                    f"evidence={' | '.join(labels[:8]) or '-'}"
                )
            else:
                status = "UNRESOLVED"
                feeder_id = ""
                reason = (
                    "FEEDER_OWNERSHIP_UNRESOLVED: 当前FeedLine所在严格连接区域没有主网馈线源"
                    "或已关联设备证据；不按全图最近距离猜测。"
                )

            ownership[obj.xml_id] = {
                "xml_id": obj.xml_id,
                "feeder_id": feeder_id,
                "status": status,
                "method": method,
                "component": comp or "",
                "evidence_sources": ",".join(sources),
                "evidence": " | ".join(labels[:8]),
                "evidence_count": len(items),
                "candidate_feeder_ids": ",".join(str(x) for x in feeder_ids),
                "reason": reason,
            }

        resolved_source_ids = sorted({
            int(anchor["feeder_id"])
            for anchor in source_anchors
            if _int_or_none(anchor.get("feeder_id")) is not None
        })
        summary = {
            "source_cbreaker_count": len(source_anchors),
            "resolved_source_anchor_count": sum(
                1 for anchor in source_anchors if anchor.get("status") == "SOURCE_CONFIRMED"
            ),
            "resolved_source_feeder_count": len(resolved_source_ids),
            "resolved_source_feeder_ids": resolved_source_ids,
            "nop_text_count": len(nop_rows),
            "nop_boundary_switch_count": len(boundary_nodes),
            "strict_geometry_repair_count": repaired_edge_count,
            "feedline_count": len(ownership),
            "confirmed_count": sum(1 for row in ownership.values() if row["status"] == "CONFIRMED"),
            "inherited_count": sum(1 for row in ownership.values() if row["status"] == "INHERITED"),
            "conflict_count": sum(1 for row in ownership.values() if row["status"] == "CONFLICT"),
            "unresolved_count": sum(1 for row in ownership.values() if row["status"] == "UNRESOLVED"),
        }
        return {
            "ownership": ownership,
            "source_anchors": [
                {k: v for k, v in anchor.items() if k != "breaker"}
                for anchor in source_anchors
            ],
            "nop_boundaries": nop_rows,
            "boundary_nodes": sorted(boundary_nodes),
            "summary": summary,
        }
