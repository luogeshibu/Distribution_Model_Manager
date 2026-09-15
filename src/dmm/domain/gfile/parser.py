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
from dmm.domain.gfile.xml_diagnostics import build_gfile_xml_error


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
    def xml_p_name_string(self) -> str:
        """Raw XML p_NameString value; parsing/debug only, never business naming."""
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
        excluded_rmu_name_strings: Iterable[str] | str | None = None,
    ):
        self.required_rmu_tags = set(required_rmu_tags or {
            "CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"
        })
        self.label_re = re.compile(label_regex)
        if isinstance(excluded_rmu_name_strings, str):
            exclusion_values = re.split(r"[,;\n\r]+", excluded_rmu_name_strings)
        else:
            exclusion_values = list(excluded_rmu_name_strings or [])
        self.excluded_rmu_name_strings = {
            re.sub(r"\s+", " ", str(value or "").strip()).casefold()
            for value in exclusion_values
            if str(value or "").strip()
        }
        self.max_distance = float(max_distance)
        self.overlap_tolerance = float(overlap_tolerance)

    def parse(self, path: str | Path) -> ParsedG:
        path = Path(path)
        # Strict XML parsing by design.  The parser obeys the source XML
        # declaration and does not guess/fallback to another encoding.  Invalid
        # exports are rejected with a detailed source-file diagnostic instead of
        # being silently converted.
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except (ET.ParseError, UnicodeError, LookupError) as exc:
            raise build_gfile_xml_error(path, exc) from exc
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

    def classify_rmu_type(self, parsed: ParsedG, frame: RmuFrame | GObject) -> Dict[str, object]:
        """Identify RMU cabinet type such as 2L1T.

        Field workflow rule (v4.1.21):
        1. Text inside the RMU rectangle remains one independent source:
           visible Y* labels count as L ways and Q* labels count as T ways.
        2. The devref source ONLY inspects ``CBreakerDis`` objects.  Ground
           disconnectors (``ZhaiWaiJieDiDaoZha``), BusDis and every other
           object type are intentionally excluded.
        3. No site-specific devref keywords are interpreted.  The program does
           not care whether a template is named ``Load_Breaker``, ``RMU_LBS``,
           ``Circuit_Breaker``, ``RMU_BRK`` or anything else.  It only checks
           the structural relationship inside this RMU:

             * all Y-way CBreakerDis objects must use one identical devref
               template;
             * all Q-way CBreakerDis objects must use one identical devref
               template;
             * when both Y and Q groups exist, their templates must differ so
               that the two classes are actually distinguishable.

           The Y/Q role is taken first from the CBreakerDis ``p_NameString``
           (Y1/Y2/... or Q1/Q2/...).  If a particular element does not carry a
           usable p_NameString, its already-supported visible graphical name is
           used only as a fallback for determining that element's Y/Q role.
        4. If the devref structure is complete and valid, its type participates
           in the normal text/devref cross-check.  When text and devref disagree
           the valid devref result is authoritative, preserving the existing
           field rule.  If the devref structure itself is ambiguous/incomplete,
           it is reported as UNKNOWN and is never guessed from template words;
           a valid text result may still be used as the final display type.
        """
        rect = frame.frame if isinstance(frame, RmuFrame) else frame
        inside = [
            obj for obj in parsed.objects
            if rect.box.center_contains(obj.box, tolerance=1.0)
        ]

        text_labels = []
        for obj in inside:
            if obj.tag.lower() != "text":
                continue
            value = self._text_value(obj).strip().upper()
            if re.fullmatch(r"Y\d+", value) or re.fullmatch(r"Q\d+", value):
                text_labels.append(value)

        # Avoid duplicate rendering labels for one way, and keep a stable
        # engineering order: Y1,Y2,Y3... then Q1,Q2,Q3...
        text_labels = list(dict.fromkeys(text_labels))

        def _way_key(value: str):
            prefix = 0 if value.startswith("Y") else 1
            try:
                number = int(value[1:])
            except Exception:
                number = 10**9
            return (prefix, number)

        text_labels = sorted(text_labels, key=_way_key)
        text_l = sum(1 for value in text_labels if value.startswith("Y"))
        text_t = sum(1 for value in text_labels if value.startswith("Q"))

        # ------------------------------------------------------------------
        # DEVREF structural classification
        # ------------------------------------------------------------------
        # IMPORTANT: only CBreakerDis participates.  In particular,
        # ZhaiWaiJieDiDaoZha devrefs such as RMU_ES must never affect 2L1T /
        # 3L1T cabinet-type inference.
        breakers = [obj for obj in inside if obj.tag == "CBreakerDis"]

        def _canonical_devref(value: str) -> str:
            """Return a comparable template name without interpreting it.

            D5000 references normally look like:
              #RMU_LBS_NON.zwk.icn.g:RMU_LBS_NON
              #Load_Breaker_Switch_SMART.zwk.icn.g:Load_Breaker_Switch_SMART

            We keep only the referenced terminal template token when possible.
            Escaped underscores/colons are normalized for defensive equality
            comparison.  No semantic keyword mapping is performed.
            """
            raw = (value or "").strip()
            if not raw:
                return ""
            raw = raw.replace(r"\_", "_").replace(r"\:", ":")
            terminal = raw.rsplit(":", 1)[-1].strip() if ":" in raw else raw
            terminal = terminal.lstrip("#").strip()
            if ".zwk.icn.g" in terminal.lower():
                # Handles a non-standard reference that has no ':' suffix.
                terminal = re.split(r"\.zwk\.icn\.g", terminal, flags=re.I)[0]
            return terminal.strip()

        # Determine each CBreakerDis logical Y/Q role.  p_NameString is an
        # element-local structural cue; graphical text is only a fallback when
        # that cue is absent/non-standard.
        graphical_names = None

        def _breaker_role(obj: GObject) -> str:
            nonlocal graphical_names
            raw_name = (obj.xml_p_name_string or "").strip().upper()
            if re.fullmatch(r"Y\d+", raw_name):
                return "Y"
            if re.fullmatch(r"Q\d+", raw_name):
                return "Q"
            if graphical_names is None:
                try:
                    graphical_names = self.resolve_breaker_graphical_names(
                        parsed,
                        frame,
                        breakers,
                    )
                except Exception:
                    graphical_names = {}
            info = graphical_names.get(obj.xml_id, {}) if graphical_names else {}
            visible = (
                str(info.get("name") or "").strip().upper()
                if info.get("status") == "PASS"
                else ""
            )
            if re.fullmatch(r"Y\d+", visible):
                return "Y"
            if re.fullmatch(r"Q\d+", visible):
                return "Q"
            return ""

        devref_groups = {"Y": [], "Q": []}
        devref_unknown = []
        devref_issues = []
        breaker_details = []

        for obj in breakers:
            role = _breaker_role(obj)
            raw_devref = (obj.attrs.get("devref") or "").strip()
            template = _canonical_devref(raw_devref)
            detail = {
                "xml_id": obj.xml_id,
                "xml_p_name_string": obj.xml_p_name_string,
                "role": role or "UNKNOWN",
                "devref": raw_devref,
                "template": template,
            }
            breaker_details.append(detail)

            if not role:
                devref_unknown.append(detail)
                devref_issues.append(
                    f"CBreakerDis XML ID={obj.xml_id or '-'} 无法确定Y/Q同类分组"
                )
                continue
            if not template:
                devref_unknown.append(detail)
                devref_issues.append(
                    f"{obj.xml_p_name_string or obj.xml_id or '-'} 的devref为空"
                )
                continue
            devref_groups[role].append((template, detail))

        def _unique_templates(role: str):
            # case-insensitive equality, while retaining the first original
            # spelling for report readability.
            seen = {}
            for template, _detail in devref_groups[role]:
                seen.setdefault(template.casefold(), template)
            return list(seen.values())

        y_templates = _unique_templates("Y")
        q_templates = _unique_templates("Q")

        if len(y_templates) > 1:
            devref_issues.append(
                "Y类CBreakerDis的devref模板不一致：" + ", ".join(y_templates)
            )
        if len(q_templates) > 1:
            devref_issues.append(
                "Q类CBreakerDis的devref模板不一致：" + ", ".join(q_templates)
            )
        if (
            len(y_templates) == 1
            and len(q_templates) == 1
            and y_templates[0].casefold() == q_templates[0].casefold()
        ):
            devref_issues.append(
                "Y类与Q类CBreakerDis使用相同devref模板，无法通过devref区分两类开关："
                + y_templates[0]
            )

        devref_l = len(devref_groups["Y"])
        devref_t = len(devref_groups["Q"])
        breaker_count = len(breakers)
        classified_breaker_count = devref_l + devref_t

        # A usable devref type requires every CBreakerDis to have a role and a
        # devref, internal homogeneity in each role group, and distinct Y/Q
        # templates when both groups are present.
        devref_complete = (
            breaker_count > 0
            and classified_breaker_count == breaker_count
            and not devref_unknown
            and len(y_templates) <= 1
            and len(q_templates) <= 1
            and not (
                len(y_templates) == 1
                and len(q_templates) == 1
                and y_templates[0].casefold() == q_templates[0].casefold()
            )
        )
        devref_found = devref_complete and (devref_l + devref_t) > 0

        text_found = (text_l + text_t) > 0
        text_complete = text_found and (text_l + text_t) == breaker_count

        def fmt(l_count: int, t_count: int) -> str:
            parts = []
            if l_count:
                parts.append(f"{l_count}L")
            if t_count:
                parts.append(f"{t_count}T")
            return "".join(parts) or "UNKNOWN"

        text_type = fmt(text_l, text_t)
        devref_type = fmt(devref_l, devref_t) if devref_found else "UNKNOWN"

        if text_found and devref_found:
            if text_type == devref_type:
                rmu_type = text_type
                source = "TEXT_YQ"
            else:
                rmu_type = devref_type
                source = "DEVREF"
        elif devref_found:
            rmu_type = devref_type
            source = "DEVREF"
        elif text_found:
            rmu_type = text_type
            source = "TEXT_YQ"
        else:
            rmu_type = "UNKNOWN"
            source = "UNRESOLVED"

        if devref_found:
            consistent = (
                not text_found
                or text_type == devref_type
            )
        else:
            # CBreakerDis always exists in a recognized RMU frame.  If its
            # devref structure cannot be validated, expose that as a cross-check
            # warning rather than pretending the devref source passed.
            consistent = False if breaker_count else True

        if devref_found:
            devref_status = "PASS"
            devref_reason = "DEVREF_TEMPLATE_GROUPS_VALID"
        else:
            devref_status = "WARN"
            devref_reason = (
                "；".join(dict.fromkeys(devref_issues))
                if devref_issues
                else "DEVREF_TEMPLATE_GROUPS_INCOMPLETE"
            )

        return {
            "rmu_type": rmu_type,
            "source": source,
            "text_type": text_type,
            "devref_type": devref_type,
            "consistent": consistent,
            "text_labels": text_labels,
            "text_l_count": text_l,
            "text_t_count": text_t,
            "text_complete": text_complete,
            "devref_l_count": devref_l,
            "devref_t_count": devref_t,
            "breaker_count": breaker_count,
            "devref_complete": devref_complete,
            "devref_status": devref_status,
            "devref_reason": devref_reason,
            "devref_templates_y": y_templates,
            "devref_templates_q": q_templates,
            "devref_breakers": breaker_details,
            "unknown_devrefs": devref_unknown,
        }


    def assign_rmu_smart_markers_globally(
        self,
        parsed: ParsedG,
        frames: Sequence[RmuFrame],
    ) -> Dict[str, Dict[str, object]]:
        """
        Globally assign SMART / SMR markers to the nearest RMU.

        Rules:
        - SMART and SMR are searched across the entire G drawing.
        - SMART is commonly inside the cabinet; SMR can be outside.
        - There is no maximum-distance cutoff.
        - Each SMART/SMR text belongs to exactly one nearest RMU.
        - One or both marker types mean the RMU is smart.
        """
        result: Dict[str, Dict[str, object]] = {
            frame.frame.xml_id: {
                "is_smart": False,
                "markers": [],
                "marker_types": [],
            }
            for frame in frames
        }
        if not frames:
            return result

        def distance_to_rect(px: float, py: float, box: Box) -> float:
            if px < box.left:
                dx = box.left - px
            elif px > box.right:
                dx = px - box.right
            else:
                dx = 0.0

            if py < box.top:
                dy = box.top - py
            elif py > box.bottom:
                dy = py - box.bottom
            else:
                dy = 0.0

            return (dx * dx + dy * dy) ** 0.5

        markers = []
        for obj in parsed.objects:
            if obj.tag.lower() != "text":
                continue
            value = self._text_value(obj).strip().upper()
            if value not in {"SMART", "SMR"}:
                continue
            markers.append((obj, value))

        for obj, marker_type in markers:
            ranked = []
            for order, frame in enumerate(frames):
                box = frame.frame.box
                distance = distance_to_rect(obj.box.cx, obj.box.cy, box)
                center_distance = (
                    (obj.box.cx - box.cx) ** 2
                    + (obj.box.cy - box.cy) ** 2
                ) ** 0.5
                ranked.append(
                    (
                        distance,
                        center_distance,
                        order,
                        frame,
                    )
                )

            _, distance_center, _, owner = min(
                ranked,
                key=lambda item: (item[0], item[1], item[2]),
            )
            owner_box = owner.frame.box
            edge_distance = distance_to_rect(
                obj.box.cx,
                obj.box.cy,
                owner_box,
            )
            item = {
                "type": marker_type,
                "text": marker_type,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "distance": round(edge_distance, 3),
                "inside": owner_box.center_contains(
                    obj.box,
                    tolerance=1.0,
                ),
                "center_distance": round(distance_center, 3),
            }
            bucket = result[owner.frame.xml_id]
            bucket["markers"].append(item)

        for bucket in result.values():
            marker_types = sorted(
                {item["type"] for item in bucket["markers"]},
                key=lambda value: (0 if value == "SMART" else 1, value),
            )
            bucket["marker_types"] = marker_types
            bucket["is_smart"] = bool(marker_types)
            bucket["markers"].sort(
                key=lambda item: (
                    item["distance"],
                    item["center_distance"],
                    item["xml_id"],
                )
            )

        return result


    def _text_value(self, obj: GObject) -> str:
        return (obj.attrs.get("ts") or "").strip()

    def _valid_rmu_name_text(self, obj: GObject) -> bool:
        """Basic RMU cabinet-name candidate filter from GFileStudio.

        Color is not a hard condition.  Exclude short labels that clearly
        belong to RMU internal devices/status, while allowing numeric,
        alphanumeric, hyphen, underscore and dot engineering cabinet names.
        """
        value = self._text_value(obj)
        if not value or not any(ch.isalnum() for ch in value):
            return False

        # User-configured exclusions are exact strings (case-insensitive after
        # trimming/collapsing whitespace).  They are checked BEFORE the RMU
        # name regex so operational annotations such as DAS/OK can be listed
        # explicitly even when punctuation would already make them invalid.
        exclusion_key = re.sub(r"\s+", " ", value.strip()).casefold()
        if exclusion_key in self.excluded_rmu_name_strings:
            return False

        if not self.label_re.fullmatch(value):
            return False
        compact = re.sub(r"\s+", "", value).upper()
        if re.fullmatch(r"Y\d+", compact) or re.fullmatch(r"Q\d+", compact):
            return False

        # N.O.P = Normally Open Point.  It is an operating-status marker near
        # an RMU, not an RMU cabinet name.  Field drawings use variants such as
        # N.O.P / NOP / N-O-P / N_O_P, so normalize punctuation before testing.
        status_token = re.sub(r"[\s._-]+", "", value).upper()
        if status_token == "NOP":
            return False

        if compact in {"SMART", "SMR", "G", "I"}:
            return False
        return True

    def assign_rmu_label_candidates_globally(
        self,
        parsed: ParsedG,
        frames: Sequence[RmuFrame],
        positions: Sequence[str],
    ) -> Dict[tuple[int, str], List[LabelCandidate]]:
        """Globally assign RMU name Text objects to RMU frames.

        Business rules:
        1. ONLY user-selected directions participate.
        2. Search the entire G drawing in those directions. There is NO
           cabinet-name maximum-distance cut-off.
        3. Every Text has at most one RMU owner. Ownership goes to the
           nearest geometrically compatible RMU across the whole drawing.
        4. A text near a corner may match multiple selected directions for one
           RMU; only that RMU's best direction is retained.
        5. Color never affects ownership. Green is used later by the validator
           only when one RMU owns multiple candidate names.

        This mirrors the supplied GFileStudio global RMU-name assignment model,
        while extending the selected-direction search to true global distance
        as requested for merged/large drawings.
        """
        normalized_positions = tuple(
            str(position).strip().lower()
            for position in positions
            if str(position).strip().lower()
            in {"top", "bottom", "left", "right"}
        )
        if not normalized_positions:
            return {}

        tol = self.overlap_tolerance

        def relation(r: Box, b: Box, direction: str):
            score = None
            gap = None
            axis_offset = None

            if direction == "top":
                gap = r.top - b.bottom
                axis_offset = abs(b.cx - r.cx)
                if (
                    r.left - tol <= b.cx <= r.right + tol
                    and b.cy < r.top
                ):
                    if gap >= -tol:
                        score = max(0.0, gap) + axis_offset * 0.08
                    else:
                        # Large-font Text objects may report a bounding box
                        # that overlaps the RMU even though the visible label
                        # and its center are clearly above the frame (e.g.
                        # BABJ 38995).  Preserve the legacy edge-gap score for
                        # normal labels and use center-gap only for this overlap
                        # fallback.
                        gap = r.top - b.cy
                        score = max(0.0, gap) + axis_offset * 0.08

            elif direction == "bottom":
                gap = b.top - r.bottom
                axis_offset = abs(b.cx - r.cx)
                if (
                    r.left - tol <= b.cx <= r.right + tol
                    and b.cy > r.bottom
                ):
                    if gap >= -tol:
                        score = max(0.0, gap) + axis_offset * 0.08
                    else:
                        gap = b.cy - r.bottom
                        score = max(0.0, gap) + axis_offset * 0.08

            elif direction == "left":
                gap = r.left - b.right
                axis_offset = abs(b.cy - r.cy)
                if (
                    r.top - tol <= b.cy <= r.bottom + tol
                    and b.cx < r.left
                ):
                    if gap >= -tol:
                        score = max(0.0, gap) + axis_offset * 0.08
                    else:
                        gap = r.left - b.cx
                        score = max(0.0, gap) + axis_offset * 0.08

            elif direction == "right":
                gap = b.left - r.right
                axis_offset = abs(b.cy - r.cy)
                if (
                    r.top - tol <= b.cy <= r.bottom + tol
                    and b.cx > r.right
                ):
                    if gap >= -tol:
                        score = max(0.0, gap) + axis_offset * 0.08
                    else:
                        gap = b.cx - r.right
                        score = max(0.0, gap) + axis_offset * 0.08

            return score, gap, axis_offset

        result: Dict[tuple[int, str], List[LabelCandidate]] = {
            (frame.frame.xml_index, frame.frame.xml_id): []
            for frame in frames
        }

        for obj in parsed.objects:
            if obj.tag.lower() != "text":
                continue

            text = self._text_value(obj)
            if not self._valid_rmu_name_text(obj):
                continue

            b = obj.box
            if b.w <= 0:
                b = Box(b.x, b.y, 1.0, max(b.h, 1.0))
            if b.h <= 0:
                b = Box(b.x, b.y, max(b.w, 1.0), 1.0)

            is_green = _is_green_text(obj)
            color = _text_primary_color(obj)

            # Keep one best selected direction PER RMU for this text.
            per_frame = []
            for frame in frames:
                best = None
                for direction_index, direction in enumerate(normalized_positions):
                    score, gap, axis_offset = relation(
                        frame.frame.box,
                        b,
                        direction,
                    )
                    if score is None:
                        continue
                    rank = (
                        score,
                        abs(float(gap or 0.0)),
                        float(axis_offset or 0.0),
                        direction_index,
                    )
                    candidate = (
                        rank,
                        frame,
                        direction,
                        float(score),
                        float(gap or 0.0),
                    )
                    if best is None or rank < best[0]:
                        best = candidate
                if best is not None:
                    per_frame.append(best)

            if not per_frame:
                continue

            # Global one-owner rule: each text belongs to ONE nearest RMU.
            owner = min(
                per_frame,
                key=lambda item: (
                    item[0],
                    item[1].frame.xml_index,
                    item[1].frame.xml_id,
                ),
            )
            _rank, owner_frame, direction, score, gap = owner
            owner_key = (
                owner_frame.frame.xml_index,
                owner_frame.frame.xml_id,
            )
            result.setdefault(owner_key, []).append(
                LabelCandidate(
                    text=text,
                    direction=direction,
                    score=score,
                    obj=obj,
                    is_green=is_green,
                    color=color,
                    gap=gap,
                )
            )

        for candidates in result.values():
            candidates.sort(
                key=lambda c: (
                    c.score,
                    c.obj.xml_index,
                    c.text,
                    c.direction,
                )
            )
        return result

    def find_label_candidates(
        self,
        parsed: ParsedG,
        frame: RmuFrame,
        positions: Sequence[str],
    ) -> List[LabelCandidate]:
        """Return globally-owned RMU name candidates for one frame.

        Bulk callers should use :meth:`assign_rmu_label_candidates_globally`
        once and reuse its result.
        """
        all_frames = self.find_rmu_frames(parsed)
        assigned = self.assign_rmu_label_candidates_globally(
            parsed,
            all_frames,
            positions,
        )
        key = (frame.frame.xml_index, frame.frame.xml_id)
        return list(assigned.get(key, []))

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
            if obj.tag.lower() != "text":
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
