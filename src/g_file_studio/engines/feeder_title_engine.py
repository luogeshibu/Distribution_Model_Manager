from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.engines.frame_engine import Box, format_number
from g_file_studio.engines.id_engine import local_name
from g_file_studio.engines.margin_engine import subtree_box


_NUMBER_TEXT_RE = re.compile(r"^\(?\s*[+-]?\d+(?:\.\d+)?\s*\)?$")
_FEEDER_STYLE_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)+$")
_ALPHA_DIGIT_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9._/-]+$")
_DEVICE_LABEL_RE = re.compile(r"^(?:Y\d+|Q\d+|D\d+|K\d+|SMART|SMR|NO|N\.O\.P)$", re.IGNORECASE)
_UNIT_LABELS = {
    "A",
    "V",
    "KV",
    "KA",
    "W",
    "KW",
    "MW",
    "VAR",
    "KVAR",
    "MVAR",
    "HZ",
    "PF",
}
_DESCRIPTION_TOKENS = (
    "UPDATED",
    "MEASUREMENT",
    "MEASURMENT",
    "STATUS",
    "VALUE",
    "ALARM",
    "WARNING",
)


@dataclass(frozen=True)
class BusSegment:
    element: ET.Element
    element_id: str
    left: float
    right: float
    y: float

    @property
    def length(self) -> float:
        return self.right - self.left

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0


@dataclass
class BusGroup:
    segments: list[BusSegment]

    @property
    def left(self) -> float:
        return min(item.left for item in self.segments)

    @property
    def right(self) -> float:
        return max(item.right for item in self.segments)

    @property
    def top_y(self) -> float:
        return min(item.y for item in self.segments)

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(item.element_id for item in self.segments)


@dataclass(frozen=True)
class TitleCandidate:
    element: ET.Element
    element_id: str
    text: str
    box: Box
    font_size: float
    score: float


@dataclass(frozen=True)
class FeederTitleMove:
    text_id: str
    text: str
    bus_ids: tuple[str, ...]
    old_x: str
    old_y: str
    new_x: str
    new_y: str
    score: float


@dataclass
class FeederTitleResult:
    file_path: Path
    bus_segment_count: int = 0
    bus_group_count: int = 0
    candidate_count: int = 0
    moved_count: int = 0
    unchanged_count: int = 0
    skipped_no_candidate_count: int = 0
    skipped_ambiguous_count: int = 0
    skipped_collision_count: int = 0
    moves: list[FeederTitleMove] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _float_value(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _line_points(element: ET.Element) -> tuple[float, float, float, float] | None:
    values = [element.get(name) for name in ("x1", "y1", "x2", "y2")]
    if all(value not in (None, "") for value in values):
        try:
            return tuple(float(value) for value in values)  # type: ignore[return-value]
        except (TypeError, ValueError):
            pass

    numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", element.get("d", ""))
    if len(numbers) >= 4:
        try:
            return tuple(float(value) for value in numbers[:4])  # type: ignore[return-value]
        except ValueError:
            return None
    return None


def _collect_horizontal_buses(layer: ET.Element) -> list[BusSegment]:
    result: list[BusSegment] = []
    for element in list(layer):
        if local_name(element.tag) != "Bus":
            continue
        points = _line_points(element)
        if points is None:
            continue
        x1, y1, x2, y2 = points
        if abs(y1 - y2) > 1.5:
            continue
        left, right = sorted((x1, x2))
        if right - left < 40.0:
            continue
        result.append(
            BusSegment(
                element=element,
                element_id=(element.get("id") or "<无ID>").strip() or "<无ID>",
                left=left,
                right=right,
                y=(y1 + y2) / 2.0,
            )
        )
    return result


def _segments_belong_together(left: BusSegment, right: BusSegment) -> bool:
    y_distance = abs(left.y - right.y)
    if y_distance > 35.0:
        return False
    overlap = max(0.0, min(left.right, right.right) - max(left.left, right.left))
    shorter = max(1.0, min(left.length, right.length))
    if overlap / shorter < 0.65:
        return False
    length_ratio = min(left.length, right.length) / max(left.length, right.length)
    if length_ratio < 0.65:
        return False
    center_tolerance = max(12.0, max(left.length, right.length) * 0.15)
    return abs(left.center_x - right.center_x) <= center_tolerance


def _group_buses(segments: list[BusSegment]) -> list[BusGroup]:
    groups: list[list[BusSegment]] = []
    for segment in sorted(segments, key=lambda item: (item.y, item.left, item.right)):
        matching_indexes = [
            index
            for index, group in enumerate(groups)
            if any(_segments_belong_together(segment, current) for current in group)
        ]
        if not matching_indexes:
            groups.append([segment])
            continue
        target = matching_indexes[0]
        groups[target].append(segment)
        for index in reversed(matching_indexes[1:]):
            groups[target].extend(groups[index])
            del groups[index]
    return [BusGroup(segments=group) for group in groups]


def _is_excluded_text(text: str) -> bool:
    stripped = text.strip()
    upper = stripped.upper()
    if not stripped:
        return True
    if _NUMBER_TEXT_RE.fullmatch(stripped):
        return True
    if _DEVICE_LABEL_RE.fullmatch(stripped):
        return True
    if upper in _UNIT_LABELS:
        return True
    return False


def _font_size(element: ET.Element) -> float:
    return max(
        _float_value(element, "fs", 0.0),
        _float_value(element, "p_FontHeight", 0.0),
        _float_value(element, "p_FontWidth", 0.0),
    )


def _box_inside_any_rect(box: Box, rect_boxes: list[Box]) -> bool:
    return any(
        rect.left <= box.center_x <= rect.right
        and rect.top <= box.center_y <= rect.bottom
        for rect in rect_boxes
    )


def _candidate_score(
    group: BusGroup,
    element: ET.Element,
    box: Box,
    text: str,
    font_size: float,
    rect_boxes: list[Box],
) -> float | None:
    if font_size < 24.0:
        return None
    if not any(char.isalpha() for char in text):
        return None
    if abs(_float_value(element, "rotate", 0.0)) > 0.01:
        return None

    vertical_gap = 0.0 if box.top <= group.top_y <= box.bottom else min(
        abs(box.top - group.top_y), abs(box.bottom - group.top_y)
    )
    horizontal_gap = max(0.0, group.left - box.right, box.left - group.right)
    max_vertical_gap = max(180.0, group.width * 1.5)
    max_horizontal_gap = max(220.0, group.width * 1.75)
    if vertical_gap > max_vertical_gap or horizontal_gap > max_horizontal_gap:
        return None

    center_distance = abs(box.center_x - group.center_x)
    score = (
        vertical_gap * 2.0
        + center_distance * 0.6
        + horizontal_gap * 1.2
        - min(font_size, 60.0) * 1.5
    )

    upper = text.upper()
    if _FEEDER_STYLE_RE.fullmatch(text):
        score -= 80.0
    elif _ALPHA_DIGIT_RE.fullmatch(text):
        score -= 45.0
    else:
        score += 65.0

    if "_" in text:
        score += 140.0
    if any(token in upper for token in _DESCRIPTION_TOKENS):
        score += 160.0
    if box.width > group.width * 2.2:
        score += 80.0
    if _box_inside_any_rect(box, rect_boxes):
        score += 200.0
    return score


def _collect_candidates(
    layer: ET.Element,
    group: BusGroup,
    rect_boxes: list[Box],
) -> list[TitleCandidate]:
    result: list[TitleCandidate] = []
    for element in list(layer):
        if local_name(element.tag) != "Text":
            continue
        text = (element.get("ts") or "").strip()
        if _is_excluded_text(text):
            continue
        box = subtree_box(element)
        if box is None or box.width <= 0.0 or box.height <= 0.0:
            continue
        font_size = _font_size(element)
        score = _candidate_score(group, element, box, text, font_size, rect_boxes)
        if score is None:
            continue
        result.append(
            TitleCandidate(
                element=element,
                element_id=(element.get("id") or "<无ID>").strip() or "<无ID>",
                text=text,
                box=box,
                font_size=font_size,
                score=score,
            )
        )
    result.sort(key=lambda item: (item.score, item.element_id))
    return result


def _intersection_area(left: Box, right: Box) -> float:
    width = max(0.0, min(left.right, right.right) - max(left.left, right.left))
    height = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
    return width * height


def _target_box(group: BusGroup, text_box: Box, gap: float) -> Box:
    left = group.center_x - text_box.width / 2.0
    top = group.top_y - text_box.height - gap
    return Box(left=left, top=top, right=left + text_box.width, bottom=top + text_box.height)


def _find_safe_target(
    group: BusGroup,
    candidate: TitleCandidate,
    text_boxes: list[tuple[ET.Element, Box]],
) -> Box | None:
    for gap in (18.0, 30.0, 42.0, 54.0, 66.0, 78.0, 90.0):
        target = _target_box(group, candidate.box, gap)
        collision = False
        for other, other_box in text_boxes:
            if other is candidate.element:
                continue
            overlap = _intersection_area(target, other_box)
            if overlap <= 0.0:
                continue
            smaller_area = max(1.0, min(target.width * target.height, other_box.width * other_box.height))
            if overlap / smaller_area >= 0.10:
                collision = True
                break
        if not collision:
            return target
    return None


def move_feeder_titles_above_buses(
    tree: ET.ElementTree,
    file_path: Path,
) -> FeederTitleResult:
    """将主母线附近唯一可确认的馈线名称移动到母线正上方。

    识别完全基于 Bus/Text 的几何和文字属性；不读取模型关联字段。
    仅修改被识别 Text 的 x/y。
    """

    result = FeederTitleResult(file_path=file_path)
    root = tree.getroot()
    layers = [element for element in list(root) if local_name(element.tag) == "Layer"]
    if not layers:
        result.warnings.append("G 根节点下没有直属 Layer。")
        return result

    for layer in layers:
        segments = _collect_horizontal_buses(layer)
        groups = _group_buses(segments)
        result.bus_segment_count += len(segments)
        result.bus_group_count += len(groups)

        rect_boxes = [
            box
            for element in list(layer)
            if local_name(element.tag) == "rect"
            if (box := subtree_box(element)) is not None
        ]
        text_boxes = [
            (element, box)
            for element in list(layer)
            if local_name(element.tag) == "Text"
            if (box := subtree_box(element)) is not None
        ]

        candidates_by_group: list[list[TitleCandidate]] = [
            _collect_candidates(layer, group, rect_boxes) for group in groups
        ]
        result.candidate_count += sum(len(items) for items in candidates_by_group)

        best_group_for_text: dict[int, tuple[int, float]] = {}
        for group_index, candidates in enumerate(candidates_by_group):
            for candidate in candidates:
                key = id(candidate.element)
                current = best_group_for_text.get(key)
                if current is None or candidate.score < current[1]:
                    best_group_for_text[key] = (group_index, candidate.score)

        claimed_texts: set[int] = set()
        for group_index, (group, candidates) in enumerate(zip(groups, candidates_by_group)):
            if not candidates:
                result.skipped_no_candidate_count += 1
                result.warnings.append(
                    f"母线组 {','.join(group.ids)} 未找到合适的馈线名称 Text。"
                )
                continue

            best = candidates[0]
            second_score = candidates[1].score if len(candidates) > 1 else math.inf
            mutual_best = best_group_for_text.get(id(best.element), (-1, math.inf))[0] == group_index
            clearly_better = second_score - best.score >= 45.0
            acceptable = best.score <= 260.0
            if not mutual_best or not acceptable or (len(candidates) > 1 and not clearly_better):
                result.skipped_ambiguous_count += 1
                preview = ", ".join(
                    f"{item.element_id}:{item.text}({item.score:.1f})"
                    for item in candidates[:3]
                )
                result.warnings.append(
                    f"母线组 {','.join(group.ids)} 候选不唯一，已跳过：{preview}。"
                )
                continue
            if id(best.element) in claimed_texts:
                result.skipped_ambiguous_count += 1
                result.warnings.append(
                    f"母线组 {','.join(group.ids)} 的候选 Text {best.element_id} 已被其他母线组使用。"
                )
                continue

            target = _find_safe_target(group, best, text_boxes)
            if target is None:
                result.skipped_collision_count += 1
                result.warnings.append(
                    f"馈线名称 Text {best.element_id} 在母线上方找不到无文字冲突的位置，已跳过。"
                )
                continue

            claimed_texts.add(id(best.element))
            old_x = best.element.get("x", "")
            old_y = best.element.get("y", "")
            new_x = format_number(target.left)
            new_y = format_number(target.top)
            if old_x == new_x and old_y == new_y:
                result.unchanged_count += 1
                continue

            before = dict(best.element.attrib)
            best.element.set("x", new_x)
            best.element.set("y", new_y)
            changed_keys = {
                key
                for key in set(before) | set(best.element.attrib)
                if before.get(key) != best.element.attrib.get(key)
            }
            if not changed_keys.issubset({"x", "y"}):
                best.element.attrib.clear()
                best.element.attrib.update(before)
                result.warnings.append(
                    f"馈线名称 Text {best.element_id} 出现非坐标属性变化，已回滚。"
                )
                continue

            result.moves.append(
                FeederTitleMove(
                    text_id=best.element_id,
                    text=best.text,
                    bus_ids=group.ids,
                    old_x=old_x,
                    old_y=old_y,
                    new_x=new_x,
                    new_y=new_y,
                    score=best.score,
                )
            )
            result.moved_count += 1

    return result
