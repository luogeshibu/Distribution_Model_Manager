from __future__ import annotations

import csv
import html
import math
import os
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from dmm.domain.gfile.parser import Box, GObject, ParsedG
from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    _assign_nops_to_frames,
    _frame_key,
    _is_nop_text,
    _new_makkah_parser,
)


# Makkah field rule: only FeedLine geometry may be changed. RMU name Text,
# NOP/N.O.P Text, RMU symbols, and topology attributes (link/node_area/keyid)
# remain untouched. A colliding near-vertical FeedLine segment is routed to the
# RIGHT of the protected Text rectangle while preserving both original segment
# endpoints.
DEFAULT_TEXT_CLEARANCE = 20
DEFAULT_FEEDER_SPACING = 50
DEFAULT_CORRIDOR_TOLERANCE = 220
DEFAULT_MAX_RIGHT_SHIFT = 500
_VERTICAL_TOLERANCE = 3.0
_PATH_COORD_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class ProtectedText:
    kind: str  # RMU_NAME / NOP
    text: str
    xml_id: str
    box: Box
    frame_box: Box | None = None
    side: str = "auto"  # left / right / auto


@dataclass(frozen=True)
class VerticalTrack:
    owner_id: str
    x: float
    ymin: float
    ymax: float


@dataclass(frozen=True)
class FeederSegmentCandidate:
    owner_id: str
    xml_index: int
    segment_index: int
    a: tuple[float, float]
    b: tuple[float, float]
    old_x: float
    ymin: float
    ymax: float
    line_width: float
    side: str
    anchor_x: float
    required_x: float
    hit_ids: tuple[str, ...]

    @property
    def span(self) -> float:
        return max(0.0, float(self.ymax) - float(self.ymin))


@dataclass
class FeederAvoidanceFileRecord:
    file_name: str
    feedline_count: int = 0
    protected_rmu_name_count: int = 0
    protected_nop_count: int = 0
    colliding_feedline_count: int = 0
    moved_feedline_count: int = 0
    moved_segment_count: int = 0
    staggered_segment_count: int = 0
    unresolved_collision_count: int = 0
    skipped_side_count: int = 0
    max_shift_used: int = 0
    text_clearance: int = DEFAULT_TEXT_CLEARANCE
    feeder_spacing: int = DEFAULT_FEEDER_SPACING
    corridor_tolerance: int = DEFAULT_CORRIDOR_TOLERANCE
    max_right_shift: int = DEFAULT_MAX_RIGHT_SHIFT
    process_right: bool = True
    process_left: bool = True
    status: str = "NO_COLLISION"


@dataclass
class FeederAvoidanceResult:
    output_files: list[Path]
    records: list[FeederAvoidanceFileRecord]
    csv_path: Path
    html_path: Path
    colliding_feedline_count: int
    moved_feedline_count: int
    moved_segment_count: int
    staggered_segment_count: int
    unresolved_collision_count: int
    skipped_side_count: int


def _format_number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"非有限数值：{value}")
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", "-0.0"} else text


def _parse_path_points(value: str) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y in _PATH_COORD_PATTERN.findall(value or "")]


def _serialize_path_points(points: Sequence[tuple[float, float]]) -> str:
    return " ".join(f"{_format_number(x)},{_format_number(y)}" for x, y in points)


def _same_point(a: tuple[float, float], b: tuple[float, float], tol: float = 1e-9) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _simplify_orthogonal_points(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    compact: list[tuple[float, float]] = []
    for point in points:
        if compact and _same_point(compact[-1], point):
            continue
        compact.append(point)

    changed = True
    while changed and len(compact) >= 3:
        changed = False
        result = [compact[0]]
        for idx in range(1, len(compact) - 1):
            a = result[-1]
            b = compact[idx]
            c = compact[idx + 1]
            same_x = abs(a[0] - b[0]) <= _VERTICAL_TOLERANCE and abs(b[0] - c[0]) <= _VERTICAL_TOLERANCE
            same_y = abs(a[1] - b[1]) <= _VERTICAL_TOLERANCE and abs(b[1] - c[1]) <= _VERTICAL_TOLERANCE
            if same_x or same_y:
                changed = True
                continue
            result.append(b)
        result.append(compact[-1])
        compact = result
    return compact


def _expanded_box(box: Box, padding: float) -> Box:
    padding = max(0.0, float(padding))
    return Box(box.x - padding, box.y - padding, box.w + 2 * padding, box.h + 2 * padding)


def _segment_intersects_box(
    a: tuple[float, float],
    b: tuple[float, float],
    box: Box,
    *,
    tolerance: float = _VERTICAL_TOLERANCE,
) -> bool:
    x1, y1 = a
    x2, y2 = b
    if abs(x1 - x2) <= tolerance:
        x = (x1 + x2) / 2.0
        return (
            box.left <= x <= box.right
            and max(min(y1, y2), box.top) <= min(max(y1, y2), box.bottom)
        )
    if abs(y1 - y2) <= tolerance:
        y = (y1 + y2) / 2.0
        return (
            box.top <= y <= box.bottom
            and max(min(x1, x2), box.left) <= min(max(x1, x2), box.right)
        )

    # FeedLine paths should be orthogonal. For a rare non-orthogonal segment,
    # use a conservative bounding-box test and leave it unresolved instead of
    # attempting a geometry guess.
    return not (
        max(x1, x2) < box.left
        or min(x1, x2) > box.right
        or max(y1, y2) < box.top
        or min(y1, y2) > box.bottom
    )


def _is_near_vertical(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) <= _VERTICAL_TOLERANCE and abs(a[1] - b[1]) > _VERTICAL_TOLERANCE


def _element_map(parsed: ParsedG) -> dict[int, ET.Element]:
    return {
        idx: element
        for idx, element in enumerate(parsed.layer.iter())
        if element is not parsed.layer
    }


def _protected_texts(parsed: ParsedG) -> list[ProtectedText]:
    parser = _new_makkah_parser()
    frames = parser.find_rmu_frames(parsed)
    assigned = parser.assign_rmu_label_candidates_globally(
        parsed,
        frames,
        ("right", "bottom", "global"),
    )

    protected: list[ProtectedText] = []
    consumed: set[tuple[int, str]] = set()
    for frame in frames:
        candidates = assigned.get(_frame_key(frame), [])
        if not candidates:
            continue
        obj = candidates[0].obj
        key = (obj.xml_index, obj.xml_id)
        if key in consumed:
            continue
        consumed.add(key)
        protected.append(
            ProtectedText(
                kind="RMU_NAME",
                text=str(candidates[0].text or "").strip(),
                xml_id=str(obj.xml_id or ""),
                box=obj.box,
                frame_box=frame.frame.box,
                side=(
                    candidates[0].direction
                    if candidates[0].direction in {"left", "right"}
                    else "auto"
                ),
            )
        )

    nop_assignments, unmatched_nops = _assign_nops_to_frames(parsed, list(frames))
    for obj, frame in nop_assignments:
        key = (obj.xml_index, obj.xml_id)
        if key in consumed:
            continue
        consumed.add(key)
        protected.append(
            ProtectedText(
                kind="NOP",
                text=str(obj.attrs.get("ts") or "").strip(),
                xml_id=str(obj.xml_id or ""),
                box=obj.box,
                frame_box=frame.frame.box,
                side="left" if obj.box.cx < frame.frame.box.cx else "right",
            )
        )
    for obj in unmatched_nops:
        key = (obj.xml_index, obj.xml_id)
        if key in consumed:
            continue
        consumed.add(key)
        protected.append(
            ProtectedText(
                kind="NOP",
                text=str(obj.attrs.get("ts") or "").strip(),
                xml_id=str(obj.xml_id or ""),
                box=obj.box,
            )
        )
    return protected


def _vertical_ranges_overlap(ymin: float, ymax: float, track: VerticalTrack) -> bool:
    return max(float(ymin), float(track.ymin)) < min(float(ymax), float(track.ymax)) - _VERTICAL_TOLERANCE


def _candidate_ranges_overlap(a: FeederSegmentCandidate, b: FeederSegmentCandidate) -> bool:
    # Adjacent RMU-to-RMU feeder spans are allowed to share one visual track.
    # Only a real Y-range overlap consumes another outward lane.
    return max(float(a.ymin), float(b.ymin)) < min(float(a.ymax), float(b.ymax)) - _VERTICAL_TOLERANCE


def _protected_outward_side(item: ProtectedText, old_x: float) -> str:
    if item.side in {"left", "right"}:
        return item.side
    if item.frame_box is not None:
        return "right" if float(old_x) >= item.frame_box.cx else "left"
    # Unmatched NOP fallback: escape through the nearest horizontal side of
    # the Text box. This is only used when no RMU ownership was available.
    return "left" if float(old_x) <= item.box.cx else "right"


def _median(values: Sequence[float], default: float) -> float:
    items = sorted(float(value) for value in values)
    if not items:
        return float(default)
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return (items[middle - 1] + items[middle]) / 2.0


def _cluster_candidates(
    candidates: Sequence[FeederSegmentCandidate],
    tolerance: float,
) -> list[list[FeederSegmentCandidate]]:
    """Group feeder segments that belong to the same RMU visual corridor.

    The anchor is normally the owning RMU column centre, not the current line
    X. That keeps a long outer feeder and short adjacent feeders in the same
    routing family even when their original trunks are already staggered.
    """
    if not candidates:
        return []
    tolerance = max(0.0, float(tolerance))
    ordered = sorted(
        candidates,
        key=lambda item: (item.anchor_x, item.ymin, item.ymax, item.owner_id, item.segment_index),
    )
    groups: list[list[FeederSegmentCandidate]] = []
    centers: list[float] = []
    for item in ordered:
        if not groups:
            groups.append([item])
            centers.append(float(item.anchor_x))
            continue
        distances = [abs(float(item.anchor_x) - center) for center in centers]
        best_index = min(range(len(distances)), key=distances.__getitem__)
        if distances[best_index] <= tolerance:
            groups[best_index].append(item)
            centers[best_index] = sum(member.anchor_x for member in groups[best_index]) / len(groups[best_index])
        else:
            groups.append([item])
            centers.append(float(item.anchor_x))
    return groups


def _assign_candidate_lanes(
    candidates: Sequence[FeederSegmentCandidate],
) -> list[list[FeederSegmentCandidate]]:
    """Colour vertical intervals from inside to outside.

    Short adjacent RMU-to-RMU spans are assigned first, so disjoint adjacent
    spans reuse lane 0 and visually align. Longer feeders that cross those
    spans necessarily overlap them and are therefore placed on lane 1, 2, ...
    farther away from the RMU column.
    """
    lanes: list[list[FeederSegmentCandidate]] = []
    ordered = sorted(
        candidates,
        key=lambda item: (item.span, item.ymin, item.ymax, item.owner_id, item.segment_index),
    )
    for item in ordered:
        placed = False
        for lane in lanes:
            if any(_candidate_ranges_overlap(item, existing) for existing in lane):
                continue
            lane.append(item)
            placed = True
            break
        if not placed:
            lanes.append([item])
    for lane in lanes:
        lane.sort(key=lambda item: (item.ymin, item.ymax, item.owner_id, item.segment_index))
    return lanes


def _lane_hits_text(
    x: float,
    lane: Sequence[FeederSegmentCandidate],
    protected: Sequence[ProtectedText],
    *,
    clearance: float,
) -> list[Box]:
    blockers: list[Box] = []
    for item in protected:
        for candidate in lane:
            expanded = _expanded_box(item.box, clearance)
            if not expanded.left <= float(x) <= expanded.right:
                continue
            if max(candidate.ymin, expanded.top) < min(candidate.ymax, expanded.bottom) - _VERTICAL_TOLERANCE:
                blockers.append(expanded)
                break
    return blockers


def _lane_hits_fixed_track(
    x: float,
    lane: Sequence[FeederSegmentCandidate],
    fixed_tracks: Sequence[VerticalTrack],
    *,
    spacing: float,
) -> list[VerticalTrack]:
    if spacing <= 0:
        return []
    owners = {item.owner_id for item in lane}
    blockers: list[VerticalTrack] = []
    for track in fixed_tracks:
        if track.owner_id in owners:
            continue
        if abs(float(x) - float(track.x)) >= spacing - 1e-9:
            continue
        if any(_vertical_ranges_overlap(candidate.ymin, candidate.ymax, track) for candidate in lane):
            blockers.append(track)
    return blockers


def _plan_group_tracks(
    group: Sequence[FeederSegmentCandidate],
    protected: Sequence[ProtectedText],
    fixed_tracks: Sequence[VerticalTrack],
    *,
    feeder_spacing: float,
    text_clearance: float,
) -> dict[tuple[int, int], tuple[float, int]]:
    if not group:
        return {}
    side = group[0].side
    if side not in {"left", "right"}:
        return {}
    lanes = _assign_candidate_lanes(group)
    spacing = max(1.0, float(feeder_spacing))
    clearance = max(0.0, float(text_clearance))

    if side == "right":
        base = max(item.required_x for item in group)
    else:
        base = min(item.required_x for item in group)

    lane_positions: list[float] = []
    result: dict[tuple[int, int], tuple[float, int]] = {}
    for lane_index, lane in enumerate(lanes):
        if side == "right":
            target = base if not lane_positions else lane_positions[-1] + spacing
        else:
            target = base if not lane_positions else lane_positions[-1] - spacing

        # Push the whole lane outward together. This preserves the requested
        # alignment for adjacent RMU spans while still clearing other Text and
        # untouched feeder tracks.
        for _ in range(max(24, len(protected) + len(fixed_tracks) + 8)):
            next_target = float(target)
            text_blockers = _lane_hits_text(
                target, lane, protected, clearance=clearance
            )
            if text_blockers:
                if side == "right":
                    next_target = max(next_target, max(box.right for box in text_blockers))
                else:
                    next_target = min(next_target, min(box.left for box in text_blockers))

            track_blockers = _lane_hits_fixed_track(
                next_target, lane, fixed_tracks, spacing=spacing
            )
            if track_blockers:
                if side == "right":
                    next_target = max(
                        next_target,
                        max(float(track.x) + spacing for track in track_blockers),
                    )
                else:
                    next_target = min(
                        next_target,
                        min(float(track.x) - spacing for track in track_blockers),
                    )

            if abs(next_target - target) <= 1e-9:
                break
            target = next_target
        else:
            continue

        lane_positions.append(float(target))
        for item in lane:
            result[(item.xml_index, item.segment_index)] = (float(target), lane_index)
    return result


def _plan_candidate_tracks(
    candidates: Sequence[FeederSegmentCandidate],
    protected: Sequence[ProtectedText],
    fixed_tracks: Sequence[VerticalTrack],
    *,
    feeder_spacing: float,
    corridor_tolerance: float,
    text_clearance: float,
) -> dict[tuple[int, int], tuple[float, int]]:
    result: dict[tuple[int, int], tuple[float, int]] = {}
    for side in ("right", "left"):
        side_candidates = [item for item in candidates if item.side == side]
        for group in _cluster_candidates(side_candidates, corridor_tolerance):
            result.update(
                _plan_group_tracks(
                    group,
                    protected,
                    fixed_tracks,
                    feeder_spacing=feeder_spacing,
                    text_clearance=text_clearance,
                )
            )
    return result


def _route_vertical_segment_to_x(
    a: tuple[float, float],
    b: tuple[float, float],
    target_x: float,
    protected: Sequence[ProtectedText],
    *,
    clearance: float,
) -> list[tuple[float, float]] | None:
    if not _is_near_vertical(a, b):
        return None
    routed = [
        a,
        (float(target_x), a[1]),
        (float(target_x), b[1]),
        b,
    ]
    expanded = [_expanded_box(item.box, clearance) for item in protected]
    for p1, p2 in ((routed[0], routed[1]), (routed[2], routed[3])):
        if any(_segment_intersects_box(p1, p2, box) for box in expanded):
            return None
    return routed


def _update_feedline_bounds(element: ET.Element, points: Sequence[tuple[float, float]]) -> None:
    if not points:
        return
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    try:
        line_width = abs(float(element.get("lw", "3")))
    except (TypeError, ValueError):
        line_width = 3.0
    pad = max(0.0, line_width)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    element.set("x", _format_number(min_x - pad))
    element.set("y", _format_number(min_y - pad))
    element.set("w", _format_number((max_x - min_x) + pad * 2.0))
    element.set("h", _format_number((max_y - min_y) + pad * 2.0))


def avoid_feedline_text_overlap(
    parsed: ParsedG,
    *,
    text_clearance: float = DEFAULT_TEXT_CLEARANCE,
    feeder_spacing: float = DEFAULT_FEEDER_SPACING,
    corridor_tolerance: float = DEFAULT_CORRIDOR_TOLERANCE,
    max_right_shift: float = DEFAULT_MAX_RIGHT_SHIFT,
    process_right: bool = True,
    process_left: bool = True,
) -> dict[str, int]:
    """Move only colliding FeedLine vertical trunks into readable side lanes.

    Field rule for Makkah ring diagrams:
    * RMU names and NOP/N.O.P Text never move;
    * only FeedLine segments that actually hit protected Text are candidates;
    * adjacent RMU-to-RMU spans may share one X lane and therefore align;
    * a feeder span that crosses those adjacent spans is assigned the next
      outward lane, then the next, so long/non-adjacent feeders stay visually
      distinguishable;
    * right-side families expand to +X, left-side families mirror to -X.
    """
    if float(text_clearance) < 0:
        raise ValueError("文字安全间距不能小于 0。")
    if float(feeder_spacing) < 0:
        raise ValueError("错落轨道间距不能小于 0。")
    if float(corridor_tolerance) < 0:
        raise ValueError("同列判定范围不能小于 0。")
    if float(max_right_shift) <= 0:
        raise ValueError("最大外移距离必须大于 0。")

    protected = _protected_texts(parsed)
    elements = _element_map(parsed)
    feedlines = [obj for obj in parsed.objects if obj.tag.lower() == "feedline"]

    colliding_feedlines: set[str] = set()
    moved_feedlines: set[str] = set()
    moved_segment_count = 0
    staggered_segment_count = 0
    unresolved_collision_count = 0
    skipped_side_count = 0
    max_shift_used = 0.0

    candidates: list[FeederSegmentCandidate] = []
    candidate_keys: set[tuple[int, int]] = set()

    # Pass 1: collect every protected-Text collision first. Global collection is
    # important: lane allocation must see the whole RMU column before deciding
    # which feeders are adjacent (same lane) and which span across them (outer
    # lanes). A sequential one-line-at-a-time move is what previously collapsed
    # unrelated feeders onto one visual trunk.
    for obj in feedlines:
        owner_id = str(obj.xml_id or obj.xml_index)
        element = elements.get(obj.xml_index)
        if element is None:
            continue
        points = _parse_path_points(element.get("d", ""))
        if len(points) < 2:
            continue
        try:
            line_width = abs(float(element.get("lw", "3")))
        except (TypeError, ValueError):
            line_width = 3.0
        collision_padding = max(0.0, line_width / 2.0)
        collision_boxes = [
            (item, _expanded_box(item.box, collision_padding))
            for item in protected
        ]

        for segment_index, (a, b) in enumerate(zip(points, points[1:])):
            hits = [
                item
                for item, box in collision_boxes
                if _segment_intersects_box(a, b, box)
            ]
            if not hits:
                continue

            colliding_feedlines.add(owner_id)
            if not _is_near_vertical(a, b):
                # The user asked for side-lane movement of feeder trunks, not
                # arbitrary polyline rewriting. Leave horizontal/diagonal hits
                # untouched and report them.
                unresolved_collision_count += 1
                continue

            old_x = (float(a[0]) + float(b[0])) / 2.0
            sides = {_protected_outward_side(item, old_x) for item in hits}
            if len(sides) != 1:
                unresolved_collision_count += 1
                continue
            side = next(iter(sides))
            if (side == "right" and not process_right) or (side == "left" and not process_left):
                skipped_side_count += 1
                continue

            expanded_hits = [
                _expanded_box(item.box, float(text_clearance))
                for item in hits
            ]
            if side == "right":
                required_x = max(box.right for box in expanded_hits)
            else:
                required_x = min(box.left for box in expanded_hits)

            frame_centers = [
                item.frame_box.cx
                for item in hits
                if item.frame_box is not None
            ]
            anchor_x = _median(frame_centers, old_x)
            ymin, ymax = sorted((float(a[1]), float(b[1])))
            candidate = FeederSegmentCandidate(
                owner_id=owner_id,
                xml_index=int(obj.xml_index),
                segment_index=int(segment_index),
                a=a,
                b=b,
                old_x=float(old_x),
                ymin=float(ymin),
                ymax=float(ymax),
                line_width=float(line_width),
                side=side,
                anchor_x=float(anchor_x),
                required_x=float(required_x),
                hit_ids=tuple(str(item.xml_id or "") for item in hits),
            )
            candidates.append(candidate)
            candidate_keys.add((int(obj.xml_index), int(segment_index)))

    # Untouched vertical trunks remain fixed obstacles. Candidate segments are
    # deliberately excluded because they are about to receive their own shared
    # lane plan.
    fixed_tracks: list[VerticalTrack] = []
    for obj in feedlines:
        element = elements.get(obj.xml_index)
        if element is None:
            continue
        points = _parse_path_points(element.get("d", ""))
        owner_id = str(obj.xml_id or obj.xml_index)
        for segment_index, (a, b) in enumerate(zip(points, points[1:])):
            if not _is_near_vertical(a, b):
                continue
            if (int(obj.xml_index), int(segment_index)) in candidate_keys:
                continue
            ymin, ymax = sorted((float(a[1]), float(b[1])))
            fixed_tracks.append(
                VerticalTrack(
                    owner_id=owner_id,
                    x=(float(a[0]) + float(b[0])) / 2.0,
                    ymin=float(ymin),
                    ymax=float(ymax),
                )
            )

    plans = _plan_candidate_tracks(
        candidates,
        protected,
        fixed_tracks,
        feeder_spacing=float(feeder_spacing),
        corridor_tolerance=float(corridor_tolerance),
        text_clearance=float(text_clearance),
    )
    candidate_by_key = {
        (item.xml_index, item.segment_index): item
        for item in candidates
    }

    # Pass 2: apply the precomputed lane plan. Endpoints stay exactly where
    # they were; only the intermediate vertical trunk moves to the selected X.
    for obj in feedlines:
        element = elements.get(obj.xml_index)
        if element is None:
            continue
        points = _parse_path_points(element.get("d", ""))
        if len(points) < 2:
            continue
        rebuilt: list[tuple[float, float]] = [points[0]]
        line_changed = False

        for segment_index, (a, b) in enumerate(zip(points, points[1:])):
            key = (int(obj.xml_index), int(segment_index))
            candidate = candidate_by_key.get(key)
            if candidate is None:
                rebuilt.append(b)
                continue
            plan = plans.get(key)
            if plan is None:
                unresolved_collision_count += 1
                rebuilt.append(b)
                continue
            target_x, lane_index = plan
            shift = abs(float(target_x) - float(candidate.old_x))
            if shift > float(max_right_shift) + 1e-9:
                unresolved_collision_count += 1
                rebuilt.append(b)
                continue
            if candidate.side == "right" and target_x <= candidate.old_x + 1e-9:
                unresolved_collision_count += 1
                rebuilt.append(b)
                continue
            if candidate.side == "left" and target_x >= candidate.old_x - 1e-9:
                unresolved_collision_count += 1
                rebuilt.append(b)
                continue

            routed = _route_vertical_segment_to_x(
                a,
                b,
                target_x,
                protected,
                clearance=float(text_clearance),
            )
            if routed is None:
                unresolved_collision_count += 1
                rebuilt.append(b)
                continue

            rebuilt.extend(routed[1:])
            line_changed = True
            moved_segment_count += 1
            if lane_index > 0:
                staggered_segment_count += 1
            max_shift_used = max(max_shift_used, shift)

        if line_changed:
            rebuilt = _simplify_orthogonal_points(rebuilt)
            new_d = _serialize_path_points(rebuilt)
            if new_d != element.get("d", ""):
                element.set("d", new_d)
                _update_feedline_bounds(element, rebuilt)
                moved_feedlines.add(str(obj.xml_id or obj.xml_index))

    return {
        "feedline_count": len(feedlines),
        "protected_rmu_name_count": sum(1 for item in protected if item.kind == "RMU_NAME"),
        "protected_nop_count": sum(1 for item in protected if item.kind == "NOP"),
        "colliding_feedline_count": len(colliding_feedlines),
        "moved_feedline_count": len(moved_feedlines),
        "moved_segment_count": moved_segment_count,
        "staggered_segment_count": staggered_segment_count,
        "unresolved_collision_count": unresolved_collision_count,
        "skipped_side_count": skipped_side_count,
        "max_shift_used": int(math.ceil(max_shift_used)),
    }


def _write_tree_atomic(root: ET.Element, output_path: Path) -> None:
    output_path = Path(output_path)
    temp = output_path.with_name(output_path.name + ".tmp_feeder_avoidance")
    ET.ElementTree(root).write(temp, encoding="utf-8", xml_declaration=True)
    ET.parse(temp)
    os.replace(temp, output_path)


def _write_csv(records: list[FeederAvoidanceFileRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(FeederAvoidanceFileRecord.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    return path


def _write_html(records: list[FeederAvoidanceFileRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        row_class = "pass" if record.moved_feedline_count else ("warn" if record.unresolved_collision_count else "info")
        rows.append(
            f"<tr class='{row_class}'>"
            f"<td>{html.escape(record.file_name)}</td>"
            f"<td>{record.feedline_count}</td>"
            f"<td>{record.protected_rmu_name_count}/{record.protected_nop_count}</td>"
            f"<td>{record.colliding_feedline_count}</td>"
            f"<td>{record.moved_feedline_count}</td>"
            f"<td>{record.moved_segment_count}</td>"
            f"<td>{record.staggered_segment_count}</td>"
            f"<td>{record.unresolved_collision_count}</td>"
            f"<td>{record.skipped_side_count}</td>"
            f"<td>{record.max_shift_used}</td>"
            f"<td>{record.text_clearance}</td>"
            f"<td>{record.feeder_spacing}</td>"
            f"<td>{record.corridor_tolerance}</td>"
            f"<td>{'是' if record.process_right else '否'}/{'是' if record.process_left else '否'}</td>"
            f"<td>{html.escape(record.status)}</td></tr>"
        )
    content = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>馈线避让调整报告</title>
<style>
body{{font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;margin:24px;background:#f3f7f5;color:#17372e}}
h1{{color:#006b52}} .rule{{background:#eaf8f2;border:1px solid #b8dfd1;padding:12px 14px;margin-bottom:16px;border-radius:8px;line-height:1.7}}
table{{border-collapse:collapse;width:100%;background:white;font-size:12px}}th,td{{border:1px solid #d3e3dc;padding:7px 9px;text-align:left;white-space:nowrap}}th{{background:#006b52;color:white}}.pass{{background:#eaf8f2}}.warn{{background:#fff4df}}.info{{background:#eaf3ff}}
</style></head><body><h1>馈线避让调整报告</h1>
<div class='rule'>仅修改 FeedLine 几何路径。RMU 名称和 NOP / N.O.P Text 均保持原位；只有 FeedLine 压住这些文字时才参与调整。同一 RMU 列中，相邻 RMU 之间、Y 范围不重叠的馈线共用同一条内侧轨道并保持对齐；跨越其它 RMU 的长馈线因为与这些区间重叠，会依次分配到更外侧轨道。右侧轨道向 +X 外扩，左侧轨道向 -X 镜像外扩。原线段两端连接点及 link / node_area / keyid 等拓扑属性不修改。</div>
<table><thead><tr><th>G文件</th><th>FeedLine</th><th>保护文字 RMU/NOP</th><th>碰撞馈线</th><th>移动馈线</th><th>移动线段</th><th>外层轨道线段</th><th>未解决碰撞</th><th>侧向关闭跳过</th><th>最大外移</th><th>文字安全间距</th><th>轨道间距</th><th>同列范围</th><th>右/左处理</th><th>状态</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    path.write_text(content, encoding="utf-8")
    return path


def process_feeder_avoidance(
    files: Iterable[Path],
    output_dir: Path,
    report_dir: Path,
    *,
    text_clearance: int = DEFAULT_TEXT_CLEARANCE,
    feeder_spacing: int = DEFAULT_FEEDER_SPACING,
    corridor_tolerance: int = DEFAULT_CORRIDOR_TOLERANCE,
    max_right_shift: int = DEFAULT_MAX_RIGHT_SHIFT,
    process_right: bool = True,
    process_left: bool = True,
    log=None,
    progress=None,
) -> FeederAvoidanceResult:
    if int(text_clearance) < 0:
        raise ValueError("文字安全间距不能小于 0。")
    if int(feeder_spacing) < 0:
        raise ValueError("错落轨道间距不能小于 0。")
    if int(corridor_tolerance) < 0:
        raise ValueError("同列判定范围不能小于 0。")
    if int(max_right_shift) <= 0:
        raise ValueError("最大外移距离必须大于 0。")

    log = log or (lambda _message: None)
    files = [Path(path) for path in files]
    if not files:
        raise ValueError("没有可处理的 G 文件。")

    output_dir = Path(output_dir)
    report_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    output_files: list[Path] = []
    records: list[FeederAvoidanceFileRecord] = []
    totals = {
        "colliding_feedline_count": 0,
        "moved_feedline_count": 0,
        "moved_segment_count": 0,
        "staggered_segment_count": 0,
        "unresolved_collision_count": 0,
        "skipped_side_count": 0,
    }

    parser = _new_makkah_parser()
    for index, source in enumerate(files, start=1):
        if progress:
            progress(
                int((index - 1) / max(1, len(files)) * 95),
                f"正在执行馈线避让：{source.name}",
            )
        target = output_dir / source.name
        shutil.copy2(source, target)
        log(f"[安全副本] {source} -> {target}")

        parsed = parser.parse(target)
        counts = avoid_feedline_text_overlap(
            parsed,
            text_clearance=float(text_clearance),
            feeder_spacing=float(feeder_spacing),
            corridor_tolerance=float(corridor_tolerance),
            max_right_shift=float(max_right_shift),
            process_right=bool(process_right),
            process_left=bool(process_left),
        )
        _write_tree_atomic(parsed.root, target)

        for key in totals:
            totals[key] += int(counts[key])
        if counts["moved_feedline_count"]:
            status = "MOVED"
        elif counts["unresolved_collision_count"]:
            status = "UNRESOLVED"
        elif counts["colliding_feedline_count"]:
            status = "COLLISION_NO_SAFE_RIGHT_ROUTE"
        else:
            status = "NO_COLLISION"

        record = FeederAvoidanceFileRecord(
            file_name=target.name,
            feedline_count=int(counts["feedline_count"]),
            protected_rmu_name_count=int(counts["protected_rmu_name_count"]),
            protected_nop_count=int(counts["protected_nop_count"]),
            colliding_feedline_count=int(counts["colliding_feedline_count"]),
            moved_feedline_count=int(counts["moved_feedline_count"]),
            moved_segment_count=int(counts["moved_segment_count"]),
            staggered_segment_count=int(counts["staggered_segment_count"]),
            unresolved_collision_count=int(counts["unresolved_collision_count"]),
            skipped_side_count=int(counts["skipped_side_count"]),
            max_shift_used=int(counts["max_shift_used"]),
            text_clearance=int(text_clearance),
            feeder_spacing=int(feeder_spacing),
            corridor_tolerance=int(corridor_tolerance),
            max_right_shift=int(max_right_shift),
            process_right=bool(process_right),
            process_left=bool(process_left),
            status=status,
        )
        records.append(record)
        output_files.append(target)
        log(
            f"[馈线避让] {target.name}: FeedLine={record.feedline_count}, "
            f"保护文字(RMU/NOP)={record.protected_rmu_name_count}/{record.protected_nop_count}, "
            f"碰撞馈线={record.colliding_feedline_count}, 移动馈线={record.moved_feedline_count}, "
            f"移动线段={record.moved_segment_count}, 外层轨道线段={record.staggered_segment_count}, "
            f"未解决={record.unresolved_collision_count}, 侧向关闭跳过={record.skipped_side_count}, "
            f"最大外移={record.max_shift_used} G, 轨道间距={record.feeder_spacing} G, "
            f"同列范围={record.corridor_tolerance} G, 右/左={record.process_right}/{record.process_left}"
        )

    csv_path = _write_csv(records, report_dir / "feeder_avoidance_report.csv")
    html_path = _write_html(records, report_dir / "feeder_avoidance_report.html")
    if progress:
        progress(100, "馈线避让调整完成")
    return FeederAvoidanceResult(
        output_files=output_files,
        records=records,
        csv_path=csv_path,
        html_path=html_path,
        **totals,
    )
