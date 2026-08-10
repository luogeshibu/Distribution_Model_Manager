#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from dmm.config.constants import (
    BREAKER_LABEL_SEARCH_MAX_DISTANCE,
    BREAKER_LABEL_AMBIGUITY_DELTA,
)


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def left(self): return self.x
    @property
    def right(self): return self.x + self.w
    @property
    def top(self): return self.y
    @property
    def bottom(self): return self.y + self.h
    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def area(self): return max(0.0, self.w) * max(0.0, self.h)

    def center_contains(self, other: "Box", tolerance: float = 0.0) -> bool:
        return (
            self.left - tolerance <= other.cx <= self.right + tolerance
            and self.top - tolerance <= other.cy <= self.bottom + tolerance
        )

    def contains_box(self, other: "Box", tolerance: float = 0.0) -> bool:
        return (
            self.left - tolerance <= other.left
            and self.top - tolerance <= other.top
            and self.right + tolerance >= other.right
            and self.bottom + tolerance >= other.bottom
        )


@dataclass
class GObject:
    tag: str
    attrs: Dict[str, str]
    box: Box
    xml_index: int

    @property
    def xml_id(self) -> str:
        return self.attrs.get("id", "")

    @property
    def p_name(self) -> str:
        return (self.attrs.get("p_NameString") or "").strip()

    @property
    def keyid(self) -> str:
        return (self.attrs.get("keyid") or "").strip()


@dataclass
class LabelCandidate:
    text: str
    direction: str
    score: float
    obj: GObject
    is_green: bool = False
    color: str = ""
    gap: float = 0.0


@dataclass
class RmuFrame:
    frame: GObject
    label_candidates: List[LabelCandidate] = field(default_factory=list)


@dataclass
class ParsedG:
    path: Path
    root: ET.Element
    layer: ET.Element
    objects: List[GObject]


def _normalized_color_value(value: str) -> str:
    return (value or "").strip().lower().replace(" ", "")


def _text_primary_color(obj: GObject) -> str:
    """
    D5000 Text objects in the supplied G files expose their visible text color
    primarily through `lc` / `lcc`.

    Examples from the project files:
        lc="0,255,0"  / lcc="#00ff00" -> green
        lc="255,255,255"               -> white
        lc="255,170,0"                 -> orange

    `fc` is intentionally not used as the primary discriminator because it is
    often green even when the visible text itself is not green.
    """
    lc = _normalized_color_value(obj.attrs.get("lc", ""))
    lcc = _normalized_color_value(obj.attrs.get("lcc", ""))
    if lc:
        return lc
    return lcc


def _is_green_text(obj: GObject) -> bool:
    lc = _normalized_color_value(obj.attrs.get("lc", ""))
    lcc = _normalized_color_value(obj.attrs.get("lcc", ""))
    return (
        lc in {"0,255,0", "0,255,0,255"}
        or lcc in {"#00ff00", "#ff00ff00", "#00ff00ff"}
    )


class GParser:
    """
    G-file parser.

    RMU recognition is structural, not size based:
      1. object must be a <rect>;
      2. rectangle must contain at least one object of every required RMU tag;
      3. if a qualifying rectangle contains another qualifying rectangle,
         keep the inner rectangle to avoid treating large layout frames as RMUs.
    """

    def __init__(
        self,
        required_rmu_tags: Iterable[str] | None = None,
        label_regex: str = r"^\d+$",
        max_distance: float = 120.0,
        overlap_tolerance: float = 20.0,
    ):
        self.required_rmu_tags = set(required_rmu_tags or {
            "CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"
        })
        self.label_re = re.compile(label_regex)
        self.max_distance = float(max_distance)
        self.overlap_tolerance = float(overlap_tolerance)

    def parse(self, path: str | Path) -> ParsedG:
        path = Path(path)
        tree = ET.parse(path)
        root = tree.getroot()
        layer = root.find("Layer")
        if layer is None:
            raise ValueError(f"No <Layer> found in G file: {path}")

        objs: List[GObject] = []
        for idx, elem in enumerate(layer.iter()):
            if elem is layer:
                continue
            attrs = dict(elem.attrib)
            box = Box(
                _f(attrs.get("x")),
                _f(attrs.get("y")),
                _f(attrs.get("w", attrs.get("width"))),
                _f(attrs.get("h", attrs.get("height"))),
            )
            objs.append(GObject(elem.tag, attrs, box, idx))
        return ParsedG(path, root, layer, objs)

    def _contained_required_tags(self, parsed: ParsedG, rect: GObject) -> set[str]:
        found = set()
        for obj in parsed.objects:
            if obj.tag not in self.required_rmu_tags:
                continue
            if rect.box.center_contains(obj.box, tolerance=1.0):
                found.add(obj.tag)
        return found

    def find_rmu_frames(self, parsed: ParsedG) -> List[RmuFrame]:
        candidates: List[GObject] = []

        for obj in parsed.objects:
            if obj.tag.lower() != "rect":
                continue
            if obj.box.w <= 0 or obj.box.h <= 0:
                continue
            found = self._contained_required_tags(parsed, obj)
            if self.required_rmu_tags.issubset(found):
                candidates.append(obj)

        # Keep innermost valid candidates. This prevents a large surrounding
        # rectangle containing several RMUs from being classified as one RMU.
        final: List[GObject] = []
        for cand in candidates:
            contains_smaller_valid = False
            for other in candidates:
                if other is cand:
                    continue
                if other.box.area >= cand.box.area:
                    continue
                if cand.box.contains_box(other.box, tolerance=1.0):
                    contains_smaller_valid = True
                    break
            if not contains_smaller_valid:
                final.append(cand)

        final.sort(key=lambda o: (o.box.y, o.box.x, o.xml_index))
        return [RmuFrame(frame=o) for o in final]

    def _text_value(self, obj: GObject) -> str:
        return (obj.attrs.get("ts") or obj.attrs.get("p_NameString") or "").strip()

    def find_label_candidates(
        self,
        parsed: ParsedG,
        frame: RmuFrame,
        positions: Sequence[str],
    ) -> List[LabelCandidate]:
        """
        Find RMU-name candidates owned by the current RMU frame.

        Critical ownership rule
        -----------------------
        A Text object may geometrically appear above/below more than one RMU
        when rows of RMUs are vertically aligned.  The same text must NEVER be
        reused by multiple RMU frames.

        Therefore each candidate Text is first assigned to the nearest
        compatible RMU frame in the selected direction.  Only the owner frame
        can use that Text.

        Color rule
        ----------
        - Green Text is allowed to be far from its owner RMU.
        - Non-green Text keeps the legacy max-distance guard.
        - After ownership filtering, green candidates are preferred by the
          validator; if this RMU owns no green candidate, the nearest ordinary
          label can be used.

        This fixes the case where one green "15953" above frame 2000120 was
        incorrectly reused by lower frame 2000155, whose own nearest label is
        "8723".
        """
        result: List[LabelCandidate] = []
        current_box = frame.frame.box
        tol = self.overlap_tolerance
        maxd = self.max_distance

        # All valid RMU frames are needed to decide ownership of a Text.
        all_frames = self.find_rmu_frames(parsed)

        def relation(r: Box, b: Box, direction: str, is_green: bool):
            direction = direction.lower()
            score = None
            gap = None

            if direction == "top":
                ok_axis = r.left - tol <= b.cx <= r.right + tol
                gap = r.top - b.bottom
                if ok_axis and gap >= -tol and (is_green or gap <= maxd):
                    score = abs(gap) + abs(b.cx - r.cx) * 0.08

            elif direction == "bottom":
                ok_axis = r.left - tol <= b.cx <= r.right + tol
                gap = b.top - r.bottom
                if ok_axis and gap >= -tol and (is_green or gap <= maxd):
                    score = abs(gap) + abs(b.cx - r.cx) * 0.08

            elif direction == "left":
                ok_axis = r.top - tol <= b.cy <= r.bottom + tol
                gap = r.left - b.right
                if ok_axis and gap >= -tol and (is_green or gap <= maxd):
                    score = abs(gap) + abs(b.cy - r.cy) * 0.08

            elif direction == "right":
                ok_axis = r.top - tol <= b.cy <= r.bottom + tol
                gap = b.left - r.right
                if ok_axis and gap >= -tol and (is_green or gap <= maxd):
                    score = abs(gap) + abs(b.cy - r.cy) * 0.08

            return score, gap

        current_frame_key = (
            frame.frame.xml_index,
            frame.frame.xml_id,
        )

        for obj in parsed.objects:
            if obj.tag.lower() not in ("text", "dtext"):
                continue

            text = self._text_value(obj)
            if not text or not self.label_re.fullmatch(text):
                continue

            b = obj.box
            if b.w <= 0:
                b = Box(b.x, b.y, 1.0, max(b.h, 1.0))
            if b.h <= 0:
                b = Box(b.x, b.y, max(b.w, 1.0), 1.0)

            is_green = _is_green_text(obj)
            color = _text_primary_color(obj)

            for direction in positions:
                direction = direction.lower()

                current_score, current_gap = relation(
                    current_box,
                    b,
                    direction,
                    is_green,
                )
                if current_score is None:
                    continue

                # Determine the ONE nearest RMU that owns this text for the
                # current direction.
                owners = []
                for candidate_frame in all_frames:
                    score, gap = relation(
                        candidate_frame.frame.box,
                        b,
                        direction,
                        is_green,
                    )
                    if score is None:
                        continue

                    owners.append(
                        (
                            score,
                            abs(gap or 0.0),
                            candidate_frame.frame.xml_index,
                            candidate_frame.frame.xml_id,
                        )
                    )

                if not owners:
                    continue

                owner = min(owners)
                owner_key = (owner[2], owner[3])

                if owner_key != current_frame_key:
                    # This text belongs to another, nearer RMU frame.
                    continue

                result.append(
                    LabelCandidate(
                        text=text,
                        direction=direction,
                        score=current_score,
                        obj=obj,
                        is_green=is_green,
                        color=color,
                        gap=float(current_gap or 0.0),
                    )
                )

        uniq = {}
        for c in result:
            key = (
                c.text,
                c.direction,
                c.obj.xml_id,
                c.obj.xml_index,
            )
            if key not in uniq or c.score < uniq[key].score:
                uniq[key] = c

        return sorted(
            uniq.values(),
            key=lambda c: (
                0 if c.is_green else 1,
                c.score,
                c.text,
                c.direction,
            ),
        )

    def find_target_objects_in_frame(
        self,
        parsed: ParsedG,
        frame: RmuFrame,
        target_tags: Iterable[str],
    ) -> List[GObject]:
        tagset = set(target_tags)
        r = frame.frame.box
        result = []
        for obj in parsed.objects:
            if obj.tag not in tagset:
                continue
            if r.center_contains(obj.box, tolerance=1.0):
                result.append(obj)
        return sorted(result, key=lambda o: (o.box.y, o.box.x, o.xml_index))
    def _text_objects_in_frame(self, parsed: ParsedG, frame: RmuFrame) -> List[GObject]:
        result = []
        r = frame.frame.box
        for obj in parsed.objects:
            if obj.tag.lower() not in ("text", "dtext"):
                continue
            text = self._text_value(obj)
            if not text:
                continue
            if r.center_contains(obj.box, tolerance=1.0):
                result.append(obj)
        return result

    def resolve_breaker_graphical_names(
        self,
        parsed: ParsedG,
        frame: RmuFrame,
        breakers: List[GObject],
        max_distance: float = BREAKER_LABEL_SEARCH_MAX_DISTANCE,
        ambiguity_delta: float = BREAKER_LABEL_AMBIGUITY_DELTA,
    ) -> Dict[str, Dict[str, object]]:
        """
        Resolve the visible label nearest to each CBreakerDis.

        The RMU drawings supplied for this project place the visible switch label
        inside the RMU frame and close to its CBreakerDis symbol.  We intentionally
        fail closed: no label, reused label or near-tie ambiguity is reported rather
        than guessed.
        """
        import math

        texts = []
        for obj in self._text_objects_in_frame(parsed, frame):
            text = self._text_value(obj).strip()
            upper = text.upper()
            if not text or upper == "SMART":
                continue
            # Device labels are short engineering tokens.  Exclude punctuation-only
            # and long prose-like strings, but keep names such as Q1, Y2, B6Y10.
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", text):
                continue
            texts.append((obj, text))

        pair_candidates = []
        per_breaker = {}
        for br in breakers:
            bx, by = br.box.cx, br.box.cy
            candidates = []
            for txt_obj, text in texts:
                dist = math.hypot(bx - txt_obj.box.cx, by - txt_obj.box.cy)
                if dist <= max_distance:
                    candidates.append((dist, txt_obj, text))
                    pair_candidates.append((dist, br, txt_obj, text))
            candidates.sort(key=lambda x: x[0])
            per_breaker[br.xml_id] = candidates

        # First reject local ambiguity before global one-to-one assignment.
        results: Dict[str, Dict[str, object]] = {}
        ambiguous_ids = set()
        for br in breakers:
            candidates = per_breaker.get(br.xml_id, [])
            if not candidates:
                results[br.xml_id] = {
                    "status": "FAIL",
                    "reason": "GRAPHICAL_NAME_NOT_FOUND",
                    "name": "",
                    "label_xml_id": "",
                    "distance": "",
                }
                continue
            if len(candidates) >= 2 and abs(candidates[1][0] - candidates[0][0]) <= ambiguity_delta:
                ambiguous_ids.add(br.xml_id)
                results[br.xml_id] = {
                    "status": "FAIL",
                    "reason": "GRAPHICAL_NAME_AMBIGUOUS",
                    "name": "",
                    "label_xml_id": "",
                    "distance": candidates[0][0],
                    "candidate_names": [c[2] for c in candidates[:3]],
                }

        # Global nearest-neighbour assignment prevents one visible Text label from
        # being assigned to two breakers.
        assigned_breakers = set()
        assigned_labels = set()
        for dist, br, txt_obj, text in sorted(pair_candidates, key=lambda x: x[0]):
            if br.xml_id in ambiguous_ids or br.xml_id in assigned_breakers:
                continue
            label_key = (txt_obj.xml_id, txt_obj.xml_index)
            if label_key in assigned_labels:
                continue
            assigned_breakers.add(br.xml_id)
            assigned_labels.add(label_key)
            results[br.xml_id] = {
                "status": "PASS",
                "reason": "GRAPHICAL_NAME_RESOLVED",
                "name": text,
                "label_xml_id": txt_obj.xml_id,
                "distance": round(dist, 3),
            }

        for br in breakers:
            if br.xml_id not in results:
                results[br.xml_id] = {
                    "status": "FAIL",
                    "reason": "GRAPHICAL_NAME_LABEL_CONFLICT",
                    "name": "",
                    "label_xml_id": "",
                    "distance": "",
                }

        return results

    def pair_objects_nearest(
        self,
        left_objects: List[GObject],
        right_objects: List[GObject],
    ) -> Dict[str, str]:
        """One-to-one spatial pairing by global nearest distance.

        Returns mapping left.xml_id -> right.xml_id.  This is used to associate a
        ground-disconnector symbol with the corresponding CBreakerDis inside the
        same RMU.  Count mismatches are handled separately by validator policy.
        """
        import math
        pairs = []
        for left in left_objects:
            for right in right_objects:
                dist = math.hypot(left.box.cx - right.box.cx, left.box.cy - right.box.cy)
                pairs.append((dist, left, right))
        used_left = set()
        used_right = set()
        result = {}
        for dist, left, right in sorted(pairs, key=lambda x: x[0]):
            if left.xml_id in used_left or right.xml_id in used_right:
                continue
            used_left.add(left.xml_id)
            used_right.add(right.xml_id)
            result[left.xml_id] = right.xml_id
        return result

