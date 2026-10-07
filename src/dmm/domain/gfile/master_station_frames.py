from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from dmm.domain.gfile.parser import GObject, ParsedG


# Makkah main-network feeder captions are ordinary Text objects such as
# ``MNA4-12`` / ``ARF2-07``. Text color is intentionally NOT a matching
# condition because field drawings may export these labels in red/white/other
# colors. A space or underscore is also accepted because older drawings contain
# forms such as ``BHA1 10``. Feeder suffixes ``_X`` / ``_Y`` are part of
# the feeder code and must be preserved, e.g. ``SHM1-AH341_X`` ->
# station ``SHM1`` + feeder ``AH341_X``.
MASTER_FEEDER_LABEL_RE = re.compile(
    r"^([A-Z]{2,}[A-Z0-9]*)[-_\s]+((?:[A-Z]{1,6}\d{1,6}(?:_[XY])?)|(?:\d{1,6}))$",
    re.IGNORECASE,
)
MASTER_FRAME_LABEL_MAX_DISTANCE = 200.0


def _norm_color(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def is_white_text(obj: GObject) -> bool:
    """Return True only when the visible Text line color is white."""
    if obj.tag.lower() != "text":
        return False
    lc = _norm_color(obj.attrs.get("lc", ""))
    lcc = _norm_color(obj.attrs.get("lcc", ""))
    return (
        lc in {"255,255,255", "255,255,255,255"}
        or lcc in {"#ffffff", "#ffffffff"}
    )


def text_has_background(obj: GObject) -> bool:
    """Read an explicit Text background flag when one is exported.

    The supplied Makkah files normally omit a background attribute for plain
    labels.  Omitted/transparent/false therefore means *no background*.
    """
    for key in (
        "background",
        "bg",
        "bk",
        "bkcolor",
        "bk_color",
        "p_BackColor",
        "backColor",
    ):
        if key not in obj.attrs:
            continue
        value = str(obj.attrs.get(key) or "").strip().casefold()
        if value and value not in {
            "0",
            "false",
            "none",
            "null",
            "transparent",
        }:
            return True
    return False


def parse_master_feeder_label(value: str) -> Optional[Tuple[str, str, str]]:
    """Parse titles such as ``MNA4-12``, ``GVCM-AH304`` or ``SHM1-AH341_X``.

    Returns ``(canonical, station_hint, feeder_hint)``.
    """
    raw = re.sub(r"\s+", " ", str(value or "").strip().upper())
    match = MASTER_FEEDER_LABEL_RE.fullmatch(raw)
    if not match:
        return None
    station_hint = match.group(1).upper()
    feeder_hint = match.group(2)
    canonical = f"{station_hint}-{feeder_hint}"
    return canonical, station_hint, feeder_hint


def distance_object_to_frame(obj: GObject, frame: GObject) -> float:
    """Shortest rectangle-to-rectangle edge distance."""
    return obj.box.edge_distance(frame.box)


@dataclass
class MasterStationFrame:
    frame: GObject
    breakers: List[GObject] = field(default_factory=list)
    label_obj: Optional[GObject] = None
    feeder_label: str = ""
    station_hint: str = ""
    feeder_hint: str = ""
    label_distance: Optional[float] = None

    @property
    def breaker(self) -> Optional[GObject]:
        return self.breakers[0] if len(self.breakers) == 1 else None


def _breakers_inside(parsed: ParsedG, rect: GObject) -> List[GObject]:
    return [
        obj
        for obj in parsed.objects
        if obj.tag == "CBreaker"
        and rect.box.center_contains(obj.box, tolerance=1.0)
    ]


def find_master_station_frames(
    parsed: ParsedG,
    *,
    label_max_distance: float = MASTER_FRAME_LABEL_MAX_DISTANCE,
    excluded_text_ids: Iterable[str] | None = None,
) -> List[MasterStationFrame]:
    """Find innermost rectangular main-network Bay frames.

    Business rule for Makkah:
      * the rectangle must contain a ``CBreaker``;
      * large outer rectangles are discarded when they contain a smaller valid
        CBreaker rectangle;
      * the frame name is the nearest feeder-like Text with **no background**;
        Text color is ignored;
      * a far-away title is not borrowed from another Bay.
    """
    candidates: List[Tuple[GObject, List[GObject]]] = []
    for obj in parsed.objects:
        if obj.tag.lower() != "rect" or obj.box.w <= 0 or obj.box.h <= 0:
            continue
        breakers = _breakers_inside(parsed, obj)
        if breakers:
            candidates.append((obj, breakers))

    final: List[Tuple[GObject, List[GObject]]] = []
    for cand, breakers in candidates:
        contains_smaller = False
        for other, _other_breakers in candidates:
            if other is cand or other.box.area >= cand.box.area:
                continue
            if cand.box.contains_box(other.box, tolerance=1.0):
                contains_smaller = True
                break
        if not contains_smaller:
            final.append((cand, breakers))

    excluded_text_ids = {str(value or "").strip() for value in (excluded_text_ids or []) if str(value or "").strip()}

    valid_labels = []
    for obj in parsed.objects:
        if obj.tag.lower() != "text":
            continue
        if str(obj.xml_id or "").strip() in excluded_text_ids:
            continue
        parsed_label = parse_master_feeder_label(obj.attrs.get("ts", ""))
        if not parsed_label:
            continue
        if text_has_background(obj):
            continue
        valid_labels.append((obj, parsed_label))

    # Global one-to-one frame/title allocation. Once a Text is consumed by a
    # Bay frame it is removed from the candidate pool for all remaining frames.
    pairs = []
    for frame, _breakers in final:
        for text_obj, parsed_label in valid_labels:
            distance = distance_object_to_frame(text_obj, frame)
            if distance <= float(label_max_distance):
                pairs.append((
                    float(distance),
                    int(text_obj.xml_index),
                    int(frame.xml_index),
                    frame,
                    text_obj,
                    parsed_label,
                ))
    pairs.sort(key=lambda item: (item[0], item[1], item[2]))
    assigned_frames = {}
    assigned_texts = set()
    for distance, _text_order, _frame_order, frame, text_obj, parsed_label in pairs:
        frame_key = (frame.xml_index, frame.xml_id)
        text_key = (text_obj.xml_index, text_obj.xml_id)
        if frame_key in assigned_frames or text_key in assigned_texts:
            continue
        assigned_frames[frame_key] = (distance, text_obj, parsed_label)
        assigned_texts.add(text_key)

    result: List[MasterStationFrame] = []
    for frame, breakers in final:
        item = MasterStationFrame(frame=frame, breakers=list(breakers))
        assigned = assigned_frames.get((frame.xml_index, frame.xml_id))
        if assigned:
            distance, text_obj, parsed_label = assigned
            canonical, station_hint, feeder_hint = parsed_label
            item.label_obj = text_obj
            item.feeder_label = canonical
            item.station_hint = station_hint
            item.feeder_hint = feeder_hint
            item.label_distance = float(distance)
        result.append(item)

    result.sort(key=lambda item: (
        item.frame.box.y,
        item.frame.box.x,
        item.frame.xml_index,
    ))
    return result


def objects_inside_frame(parsed: ParsedG, frame: GObject, tags=None) -> List[GObject]:
    allowed = set(tags or [])
    return [
        obj
        for obj in parsed.objects
        if (not allowed or obj.tag in allowed)
        and frame.box.center_contains(obj.box, tolerance=1.0)
    ]
