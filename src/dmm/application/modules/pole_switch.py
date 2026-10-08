from __future__ import annotations

import re
from collections import defaultdict, deque
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.application.modules.feeder_context import (
    add_feeder_fields,
    enforce_device_feeder_membership,
    resolve_drawing_feeder,
)
from dmm.config.constants import RMU_LABEL_EDGE_TOLERANCE, RMU_LABEL_PATTERN
from dmm.domain.gfile.element_catalog import (
    classification_is,
    resolve_element_record,
)
from dmm.domain.gfile.parser import (
    GParser,
    GObject,
    ParsedG,
    box_min_edge_distance,
    box_relative_direction,
)
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService


POLE_SWITCH_TABLE_ID = 13502
POLE_SWITCH_DOMAIN = 40
# A graphical Text farther than this from a target device is not a valid
# device name candidate for either pole switches or pole transformers.
DEFAULT_DEVICE_TEXT_MAX_DISTANCE = 200.0
POLE_SWITCH_TEXT_MAX_DISTANCE = 200.0
JEDDAH_NAME_PRIORITY = ("top", "right", "global")

# Jeddah pole-switch names must carry an explicit Text color, but the exact
# shade is not authoritative.  Field drawings use many different red/dark-red
# shades and may also contain other colored device-name Text.  Only white (and
# missing/default color, which renders as white) is forbidden.
_POLE_SWITCH_WHITE_COLORS = frozenset({
    "WHITE", "255,255,255", "255,255,255,255", "#FFFFFF", "#FFFFFFFF",
})

# The recognition authority is ONLY the user-maintained element classification.
# Any G XML element whose devref resolves to an element catalog row classified
# as LBS / SEC / AR is a pole-switch target. The concrete XML tag is deliberately
# irrelevant; never infer pole-switch identity from key_name, p_NameString, the
# tag name itself, or devref text substrings.
POLE_SWITCH_DEVREF_KEYWORDS = ("LBS", "SEC", "AR")

# The fixed-mode resolver scans the G file's Text objects for all marked
# target devices together. Target devices compete globally for Text ownership;
# the nearest device wins, while separate Text objects may contain the same
# displayed name and can be assigned to their corresponding nearby devices.
GLOBAL_NAMEABLE_DEVICE_TAGS = frozenset({
    "CBreaker",
    "CBreakerDis",
    "Disconnector",
    "GroundDisconnector",
    "PowerTransformer",
    "Transformer",
    "TransformerDis",
    "ZhaiWaiJieDiDaoZha",
})

POLE_SWITCH_NAME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.\-/]{0,127}$"
)


_COMPOUND_POLE_SWITCH_NAME_RE = re.compile(
    r"^(?P<prefix>ARC|AR|LBS|SEC)(?P<left>\d+)-(?P<right>\d+)$",
    re.IGNORECASE,
)


def normalize_pole_switch_db_lookup_name(value: str, device_family: str = "") -> str:
    """Build the 13501 lookup name without changing the graphical Text.

    The long-standing Jeddah rule is preserved for ordinary AR/LBS/SEC names:
    dots, hyphens and whitespace are removed only for the database lookup
    (``SEC-2385`` -> ``SEC2385``).

    A second, explicit business-name form also exists in drawings and in the
    database: ``<family><digits>-<digits>``, for example
    ``LBS96527-21240`` or ``LBS33513-97376``.  When the element is classified
    as the matching AR/LBS/SEC family and the graphical name matches that exact
    compound form, the hyphen is part of the business name and must be kept for
    the 13501 lookup.

    The optional ``device_family`` keeps this exception classification-driven.
    Callers that do not provide a family retain the historical normalization
    behavior unchanged.
    """
    raw = str(value or "").strip()
    family = str(device_family or "").strip().upper()
    match = _COMPOUND_POLE_SWITCH_NAME_RE.fullmatch(raw)
    if family in {"AR", "LBS", "SEC"} and match:
        prefix = match.group("prefix").upper()
        prefix_matches_family = (
            (family == "AR" and prefix in {"AR", "ARC"})
            or prefix == family
        )
        if prefix_matches_family:
            return raw
    return re.sub(r"[.\-\s]+", "", raw)

# Device names may contain spaces and may be split into visual lines in
# Text.ts, for example ``AUTO RECLOSER\n101601``.  Keep the complete label
# after whitespace normalization instead of treating it as two names.
GRAPHICAL_DEVICE_NAME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.\-/]*(?:\s+[A-Za-z0-9][A-Za-z0-9_.\-/]*){0,15}$"
)

_NON_NAME_LABELS = {
    "SMART",
    "SMR",
    "NOP",
    "N.O.P",
    "N-O-P",
    "N_O_P",
    "F.C",
    "FC",
    "BUS",
    "G",
    "I",
}

# These are visible Text annotations, not device names.  They must be
# filtered before nearest-name selection; otherwise a unit such as ``kV`` can
# become the name of a distant AR/LBS/SEC or TransformerDis.
_NON_DEVICE_TEXT_EXACT = {
    "A",
    "V",
    "KV",
    "KA",
    "MA",
    "HZ",
    "KW",
    "MW",
    "KVA",
    "MVA",
}


def _marked_pole_switch_family(value: str, element_catalog=None) -> str:
    """Resolve pole-switch type from the user's element mark only.

    The drawing's devref/file name is an instance locator.  It is not a
    reliable business classification because different sites use different
    element file names.  A missing or unclassified catalog record therefore
    cannot become a pole switch through a substring coincidence.
    """
    catalog_record = resolve_element_record(value, element_catalog)
    for keyword in POLE_SWITCH_DEVREF_KEYWORDS:
        if classification_is(catalog_record, keyword):
            return keyword
    return ""


def _devref_model_label(value: str, keyword: str) -> str:
    raw = str(value or "").strip()
    tail = raw.rsplit(":", 1)[-1].strip()
    tail = re.sub(r"\.zwk\.icn\.g$", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"^RMU_", "", tail, flags=re.IGNORECASE)
    return tail or keyword



def _pole_switch_text_color(obj: GObject) -> str:
    """Return the explicitly configured visible Text color.

    D5000 drawings use ``lc`` first and ``lcc`` as fallback.  An empty return
    value means the Text has no explicit color and therefore renders as the
    default white; such Text cannot be a pole-switch name.
    """
    raw = str(obj.attrs.get("lc") or obj.attrs.get("lcc") or "").strip()
    return re.sub(r"\s+", "", raw).upper()


def _pole_switch_text_color_rank(obj: GObject):
    """Accept any explicitly colored non-white Text as a device name.

    The exact shade is deliberately ignored.  The only color rule is:
    the Text must explicitly carry a color and that color must not be white.
    Direction (TOP -> RIGHT -> GLOBAL), distance and one-to-one ownership decide
    between otherwise valid candidates.
    """
    color = _pole_switch_text_color(obj)
    if not color or color in _POLE_SWITCH_WHITE_COLORS:
        return None
    return 0


class PoleSwitchParser:
    """Recognize standalone pole switches and preserve topology evidence."""

    def __init__(self):
        self.rmu_parser = GParser(
            required_rmu_tags={
                "CBreakerDis",
                "ZhaiWaiJieDiDaoZha",
                "BusDis",
            },
            label_regex=RMU_LABEL_PATTERN,
            overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
        )

    @staticmethod
    def _refs(obj: GObject):
        refs = []
        for attr_name in ("link", "node_area"):
            raw = str(obj.attrs.get(attr_name) or "")
            for part in raw.split(";"):
                bits = [item.strip() for item in part.split(",")]
                if len(bits) >= 3 and bits[2]:
                    refs.append(bits[2])
        return list(dict.fromkeys(refs))

    @staticmethod
    def _text_value(obj: GObject) -> str:
        # Text.ts may contain an XML line break plus alignment spaces.  The
        # visible label is one name, so expose it as one normalized string.
        return re.sub(r"\s+", " ", str(obj.attrs.get("ts") or "")).strip()

    @staticmethod
    def _is_valid_name(text: str) -> bool:
        value = str(text or "").strip()
        if not value or not any(char.isalnum() for char in value):
            return False
        if value.upper() in _NON_NAME_LABELS:
            return False
        if re.fullmatch(r"[YQ]\d+", value.replace(" ", "").upper()):
            return False
        # Pure numeric labels in this drawing are transformer/line numbers,
        # not the pole-switch names requested by this module.
        if value.isdigit():
            return False
        return bool(POLE_SWITCH_NAME_RE.fullmatch(value))

    @staticmethod
    def _model_family(model: str) -> str:
        model = str(model or "").upper()
        if "LBS" in model:
            return "LBS"
        if "SEC" in model:
            return "SEC"
        if "AR" in model:
            return "AR"
        if "BREAKER" in model:
            return "BREAKER"
        return ""

    @classmethod
    def _family_matches_name(cls, model: str, text: str) -> bool:
        family = cls._model_family(model)
        compact = re.sub(r"[^A-Z0-9]", "", str(text or "").upper())
        return bool(family and compact.startswith(family))

    def _rmu_frame_objects(self, parsed: ParsedG):
        return self.rmu_parser.find_rmu_frames(parsed)

    @staticmethod
    def _is_inside_rmu(obj: GObject, frames) -> bool:
        return any(
            frame.frame.box.center_contains(obj.box, tolerance=1.0)
            for frame in frames
        )

    def _build_topology(self, parsed: ParsedG):
        by_id = {
            str(obj.xml_id): obj
            for obj in parsed.objects
            if str(obj.xml_id or "")
        }
        graph = defaultdict(set)
        for obj in parsed.objects:
            xml_id = str(obj.xml_id or "")
            if not xml_id:
                continue
            for ref in self._refs(obj):
                if ref not in by_id:
                    continue
                graph[xml_id].add(ref)
                graph[ref].add(xml_id)

        components = {}
        visited = set()
        for xml_id in by_id:
            if xml_id in visited:
                continue
            queue = deque([xml_id])
            visited.add(xml_id)
            members = []
            while queue:
                current = queue.popleft()
                members.append(current)
                for nxt in graph.get(current, ()):
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            component_id = "TOPOLOGY_" + min(members)
            member_set = set(members)
            for member in members:
                components[member] = {
                    "component_id": component_id,
                    "member_ids": member_set,
                }
        return by_id, graph, components

    @staticmethod
    def _is_nameable_device(obj: GObject) -> bool:
        if not str(obj.xml_id or "").strip():
            return False
        if obj.tag in GLOBAL_NAMEABLE_DEVICE_TAGS:
            return True
        # Keep the global pass extensible for device symbols not yet listed
        # above: a non-structural G object carrying devref is a named symbol.
        if obj.tag.lower() in {
            "text",
            "dtext",
            "connectline",
            "feedline",
            "bus",
            "busdis",
            "line",
            "rect",
        }:
            return False
        return bool(str(obj.attrs.get("devref") or "").strip())

    @staticmethod
    def _is_cross_module_nameable_device(obj: GObject, element_catalog=None) -> bool:
        """Identify marked pole switches and pole transformers for Text locks.

        The pole-switch and transformer modules run independently, but their
        graphical names still follow one ownership rule within the same G
        drawing.  Including both families in the allocation pool prevents a
        Text claimed by one family from being reused by the other family.
        """
        devref = str(obj.attrs.get("devref") or "")
        # Pole-switch identity comes only from the Element Management
        # classification.  Do not constrain the XML tag here either.
        if _marked_pole_switch_family(devref, element_catalog):
            return True
        record = resolve_element_record(devref, element_catalog)
        if classification_is(record, "TRANSFORMER_OH"):
            # Transformer identity is classification-driven as well.  Do not
            # constrain the concrete G XML element tag: any object whose devref
            # resolves to TRANSFORMER_OH participates as a pole transformer.
            return True
        return False

    @staticmethod
    def _line_points(obj: GObject):
        raw = str(
            obj.attrs.get("d")
            or obj.attrs.get("points")
            or obj.attrs.get("path")
            or ""
        )
        pairs = re.findall(
            r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
            raw,
        )
        if pairs:
            return [(float(x), float(y)) for x, y in pairs]
        # Some exports store a whitespace-separated polyline without commas.
        numbers = re.findall(r"-?\d+(?:\.\d+)?", raw)
        if len(numbers) >= 4 and len(numbers) % 2 == 0:
            return [
                (float(numbers[index]), float(numbers[index + 1]))
                for index in range(0, len(numbers), 2)
            ]
        return []

    @staticmethod
    def _global_text_is_nameable(obj: GObject) -> bool:
        """Accept visible Text labels without using DText or structural labels."""
        value = str(obj.attrs.get("ts") or "").strip()
        if obj.tag.lower() != "text" or not value or not any(char.isalnum() for char in value):
            return False
        normalized = re.sub(r"\s+", " ", value).strip()
        upper = re.sub(r"\s+", "", normalized).upper()
        if upper in _NON_NAME_LABELS or re.fullmatch(r"[YQ]\d+", upper):
            return False
        if upper in _NON_DEVICE_TEXT_EXACT:
            return False
        if re.fullmatch(r"N[._-]?O[._-]?P", upper):
            return False
        if re.fullmatch(r"F[._-]?C", upper):
            return False
        return bool(GRAPHICAL_DEVICE_NAME_RE.fullmatch(normalized))

    def build_global_name_owners(
        self,
        parsed: ParsedG,
        element_catalog=None,
        name_settings=None,
        nearest_only=False,
        device_filter=None,
        include_shared_devices=True,
        lock_text_ownership=True,
        max_text_distance=DEFAULT_DEVICE_TEXT_MAX_DISTANCE,
        allowed_directions=None,
        text_filter=None,
        direction_priority=None,
        text_color_ranker=None,
        color_priority_first=False,
    ):
        """Find eligible Text objects for the requested device family.

        This is shared by pole switches and pole transformers. The scan is
        global across the G file so a device can find a label outside its
        local XML block. Device-to-Text distance is always the shortest
        rectangle-edge distance; center-point distance is not used.  By default Text ownership is exclusive and marked
        cross-module devices share the same pool.  A module that explicitly
        opts out can receive only its requested device family and reuse a
        nearest Text without creating a global name lock.
        """

        reserved_text_ids = set()

        devices = []
        for obj in parsed.objects:
            requested = device_filter is None or device_filter(obj)
            shared_name_lock = (
                include_shared_devices
                and self._is_cross_module_nameable_device(
                    obj,
                    element_catalog,
                )
            )
            if not requested and not shared_name_lock:
                continue
            # An explicitly requested device_filter is authoritative for this
            # scan.  Pole-switch recognition is classification-driven, so the
            # XML element tag must never disqualify a classified LBS/SEC/AR
            # object.  Shared/legacy devices still use the generic structural
            # guard to avoid treating drawing primitives as devices.
            if not requested and not self._is_nameable_device(obj):
                continue
            if requested and not str(obj.xml_id or "").strip():
                continue
            # A TRANSFORMER_OH classification is authoritative regardless of
            # the concrete XML tag.  Keep one legacy guard only for an
            # unclassified TransformerDis symbol so it cannot steal Text from
            # a classified device when a generic/shared scan is requested.
            record = resolve_element_record(
                str(obj.attrs.get("devref") or ""),
                element_catalog,
            )
            is_marked_transformer = classification_is(record, "TRANSFORMER_OH")
            if obj.tag == "TransformerDis" and not is_marked_transformer:
                continue
            devices.append(obj)
        # Operator-configurable name-format/background filters are not used by
        # the shared geometric scanner. Callers can still impose fixed model
        # rules through allowed_directions/text_filter (for example pole
        # transformers use any direction but white Text only). Basic Text
        # sanity exclusions for units/structural annotations remain active.
        del name_settings
        texts = []
        text_color_ranks = {}
        for obj in parsed.objects:
            if obj.xml_index in reserved_text_ids:
                continue
            if not self._global_text_is_nameable(obj):
                continue
            if text_filter is not None and not text_filter(obj):
                continue
            color_rank = 0
            if text_color_ranker is not None:
                color_rank = text_color_ranker(obj)
                if color_rank is None:
                    continue
            text_color_ranks[obj.xml_index] = int(color_rank)
            texts.append(obj)

        if not devices or not texts:
            return defaultdict(list)

        ranked = {}
        for device in devices:
            items = []
            for text_obj in texts:
                # ``allowed_directions`` is a hard filter retained for legacy
                # callers. ``direction_priority`` keeps every direction eligible
                # but ranks preferred directions before GLOBAL fallback.  Both
                # direction and distance are rectangle based.
                direction = self._direction(device, text_obj)
                if (
                    allowed_directions is not None
                    and direction not in allowed_directions
                ):
                    continue
                distance = box_min_edge_distance(device.box, text_obj.box)
                if distance > float(max_text_distance):
                    continue
                priority = 0
                if direction_priority:
                    normalized_priority = [
                        str(value or "").strip().casefold()
                        for value in direction_priority
                        if str(value or "").strip()
                        and str(value or "").strip().casefold() != "global"
                    ]
                    try:
                        priority = normalized_priority.index(direction)
                    except ValueError:
                        priority = len(normalized_priority)
                items.append((
                    int(priority),
                    int(text_color_ranks.get(text_obj.xml_index, 0)),
                    float(distance),
                    text_obj.xml_index,
                    self._text_value(text_obj),
                    text_obj,
                ))
            if direction_priority:
                if color_priority_first:
                    # Pole-switch Text has already been hard-filtered to
                    # explicitly colored, non-white candidates. Keep the
                    # Jeddah TOP -> RIGHT -> GLOBAL direction order.
                    items.sort(key=lambda item: (item[1], item[0], item[2], item[3]))
                else:
                    items.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
            elif nearest_only:
                # After hard filtering, physical proximity is the only
                # meaningful preference.  A farther matching Text must not
                # beat a nearer matching Text.
                items.sort(key=lambda item: (item[2], item[3]))
            else:
                items.sort(key=lambda item: (item[0], item[1], item[2]))
            ranked[device.xml_index] = items

        if not lock_text_ownership:
            return defaultdict(
                list,
                {
                    device_id: list(items)
                    for device_id, items in ranked.items()
                },
            )

        # Allocate Text objects one-to-one. A Text XML object already assigned
        # to one device must not be reused by another nearby device. The same
        # displayed value is allowed when it comes from different Text objects
        # at different positions in the drawing.
        if direction_priority:
            # Each device proposes candidates in its configured ranking order
            # (for Jeddah pole switches: explicitly colored non-white Text,
            # then TOP -> RIGHT -> GLOBAL). If two
            # devices compete for the same Text, keep the historical ownership
            # rule: the physically closer device wins and the other device
            # continues with its next candidate.
            next_candidate_index = {device.xml_index: 0 for device in devices}
            queue = deque(device.xml_index for device in devices)
            assigned_by_device = {}
            owner_by_text = {}
            while queue:
                device_xml_index = queue.popleft()
                if device_xml_index in assigned_by_device:
                    continue
                items = ranked.get(device_xml_index, [])
                while next_candidate_index[device_xml_index] < len(items):
                    candidate = items[next_candidate_index[device_xml_index]]
                    next_candidate_index[device_xml_index] += 1
                    text_obj = candidate[-1]
                    text_id = text_obj.xml_index
                    incumbent = owner_by_text.get(text_id)
                    if incumbent is None:
                        owner_by_text[text_id] = (device_xml_index, candidate)
                        assigned_by_device[device_xml_index] = candidate
                        break

                    incumbent_device, incumbent_candidate = incumbent
                    challenger_key = (float(candidate[2]), device_xml_index)
                    incumbent_key = (float(incumbent_candidate[2]), incumbent_device)
                    if challenger_key < incumbent_key:
                        assigned_by_device.pop(incumbent_device, None)
                        owner_by_text[text_id] = (device_xml_index, candidate)
                        assigned_by_device[device_xml_index] = candidate
                        queue.append(incumbent_device)
                        break
                    # The Text remains owned by the closer device; continue
                    # through this device's RIGHT/GLOBAL fallback candidates.

            owners = defaultdict(list)
            for device_xml_index, candidate in assigned_by_device.items():
                owners[device_xml_index].append(candidate)
            return owners

        # Legacy global-nearest ownership used by callers without a direction
        # priority: resolve competition by physical distance first, then stable
        # XML order.
        candidate_pairs = []
        for device in devices:
            items = ranked.get(device.xml_index, [])
            for item in items:
                candidate_pairs.append((
                    float(item[2]),
                    item[3],
                    device.xml_index,
                    item[-1],
                    item,
                ))
        candidate_pairs.sort(key=lambda item: (item[0], item[1], item[2]))

        owners = defaultdict(list)
        assigned_devices = set()
        assigned_text_ids = set()
        for (
            _distance,
            _text_order,
            device_xml_index,
            text_obj,
            candidate,
        ) in candidate_pairs:
            if device_xml_index in assigned_devices:
                continue
            text_id = text_obj.xml_index
            if text_id in assigned_text_ids:
                continue
            owners[device_xml_index].append(candidate)
            assigned_devices.add(device_xml_index)
            assigned_text_ids.add(text_id)
        return owners

    def find_nearest_name(
        self,
        parsed: ParsedG,
        target: GObject,
        model: str,
        frames=(),
        global_name_owners=None,
    ):
        del parsed, frames
        owners = global_name_owners or {}
        candidates = [
            (
                format_penalty,
                color_penalty,
                distance,
                0 if self._family_matches_name(model, text) else 1,
                xml_index,
                text,
                text_obj,
            )
            for format_penalty, color_penalty, distance, xml_index, text, text_obj in owners.get(
                target.xml_index,
                [],
            )
        ]
        if not candidates:
            return None, []
        candidates.sort(key=lambda item: (item[0], item[1], item[2], item[3], item[4]))
        chosen = candidates[0]
        return {
            "text": chosen[5],
            "distance": round(float(chosen[2]), 3),
            "direction": self._direction(target, chosen[6]),
            "xml_id": chosen[6].xml_id,
            "object": chosen[6],
        }, [
            {
                "text": item[5],
                "distance": round(float(item[2]), 3),
                "family_match": "YES" if item[3] == 0 else "NO",
                "xml_id": item[6].xml_id,
            }
            for item in candidates[:10]
        ]

    @staticmethod
    def _direction(target: GObject, label: GObject) -> str:
        # Direction is derived from rectangle placement only.  Diagonal labels
        # remain GLOBAL fallback candidates; no center-point vector is used.
        return box_relative_direction(target.box, label.box)

    def discover(self, parsed: ParsedG, element_catalog=None, name_settings=None):
        global_name_owners = self.build_global_name_owners(
            parsed,
            element_catalog,
            name_settings,
            nearest_only=True,
            device_filter=lambda obj: bool(
                _marked_pole_switch_family(
                    str(obj.attrs.get("devref") or ""),
                    element_catalog,
                )
            ),
            # Pole-switch recognition is independent and classification-only.
            # Any XML element whose devref resolves to an LBS/SEC/AR catalog
            # mark participates; the concrete XML tag is intentionally ignored.
            include_shared_devices=False,
            lock_text_ownership=True,
            max_text_distance=POLE_SWITCH_TEXT_MAX_DISTANCE,
            allowed_directions=None,
            direction_priority=JEDDAH_NAME_PRIORITY,
            text_color_ranker=_pole_switch_text_color_rank,
            color_priority_first=True,
        )
        rows = []
        for obj in parsed.objects:
            raw_devref = str(obj.attrs.get("devref") or "").strip()
            devref_keyword = _marked_pole_switch_family(
                raw_devref,
                element_catalog,
            )
            if not devref_keyword:
                continue
            model = _devref_model_label(raw_devref, devref_keyword)

            label, _label_candidates = self.find_nearest_name(
                parsed,
                obj,
                devref_keyword,
                (),
                global_name_owners,
            )
            row = {
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": raw_devref,
                "device_model": model,
                # Classification is authoritative even when the devref/root
                # name itself contains none of the words LBS/SEC/AR.
                "device_family": devref_keyword,
                "key_name": str(obj.attrs.get("key_name") or "").strip(),
                "current_keyid": obj.keyid,
                "inside_rmu": "NOT_ANALYZED",
                "topology_component": "",
                "topology_member_count": 0,
                "topology_member_ids": "",
                "topology_member_tags": "",
                "topology_neighbor_count": 0,
                "topology_neighbor_ids": "",
                "graphical_name": label.get("text", "") if label else "",
                "name_source": "NEAREST_GRAPHICAL_TEXT" if label else "",
                "name_distance": label.get("distance", "") if label else "",
                "name_distance_basis": "RECTANGLE_MIN_EDGE_DISTANCE" if label else "",
                "name_direction": label.get("direction", "") if label else "",
                "name_priority": (
                    "TOP" if label and label.get("direction") == "top"
                    else "RIGHT" if label and label.get("direction") == "right"
                    else "GLOBAL" if label else ""
                ),
                "name_xml_id": label.get("xml_id", "") if label else "",
                "status": "",
                "severity": "",
                "reason": "",
            }
            rows.append(row)
        return rows


class PoleSwitchModelModule(ModelModule):
    module_id = "POLE_SWITCH"
    display_name = "柱上开关模型"
    description = (
        "识别图元管理中标记为 LBS / AR / SEC 的柱上开关；图上名称仍按原有几何规则查找，"
        "名称 Text 必须显式设置颜色且不能是白色，颜色深浅/具体色值不再限制；按上方 → 右方 → 全局兜底，"
        "设备矩形框与 Text 矩形框按最小边缘距离计算且不超过 200，不再使用中心点距离，同一 Text 不重复使用；只有进入数据库查询前，才删除名称中的点号、横杠和空格"
        "（如 SEC-2385 → SEC2385），但“设备族+数字-数字”的复合业务名（如 LBS96527-21240）保留横杠直接查询；图上原始名称绝不改写。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "LBS_SEC_AR_CLASSIFICATION": {
                "table_id": POLE_SWITCH_TABLE_ID,
                "domain": POLE_SWITCH_DOMAIN,
                "match_mode": "ELEMENT_CLASSIFICATION_LBS_SEC_AR_NEAREST_TEXT",
                "description": "柱上开关只认图元管理中的 LBS/SEC/AR 分类标记，不限制 G XML 元素类型；找到被分类的对应图元后，名称 Text 必须有明确颜色且不能是白色；TOP→RIGHT→GLOBAL，设备矩形框与 Text 矩形框按最小边缘距离计算且不超过 200，不再使用中心点距离，同级按距离最近并保持 Text 一对一；查询 13501 前普通名称删除点号、横杠和空格（SEC-2385/SEC 2385/SEC.2385 → SEC2385）；若分类与名称前缀一致且名称严格为“AR/LBS/SEC(+AR可含ARC)+数字-数字”，则保留中间横杠直接查询（如 LBS96527-21240）；数据库仍按既有 13501→13502 链路校验。",
            }
        }

    @staticmethod
    def _attributes_for_row(row):
        bv_id = str(row.get("db_bv_id") or "").strip()
        if not bv_id:
            raise ValueError(
                f"{row.get('object_type')}:{row.get('xml_id')}: "
                "数据库 dms_cb_device BV_ID 为空，禁止生成模型回写。"
            )
        return {
            "app": "6500000",
            "voltype": bv_id,
            "p_ReportType": "1",
            "state": "41",
            "keyid": str(row["expected_keyid"]),
        }

    @staticmethod
    def _make_expected_keyid(device_id):
        # Keep the same D5000 encoding used by RMU CBreakerDis:
        # KeyID = device_id + (domain << 32).
        device_id = int(device_id)
        if device_id < 0:
            raise ValueError(f"Invalid device_id: {device_id}")
        return device_id + (POLE_SWITCH_DOMAIN << 32)

    @staticmethod
    def _normalize_name(value):
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

    @classmethod
    def _record_matches_family(cls, record, family):
        family = re.sub(r"[^A-Z0-9]", "", str(family or "").upper())
        if not family:
            return False
        values = (
            record.get("code"),
            record.get("name"),
            record.get("name_alias"),
        )
        return any(
            re.sub(r"[^A-Z0-9]", "", str(value or "").upper()) == family
            for value in values
        )

    def _current_link_fields(self, row, db):
        current_keyid = int_or_none(row.get("current_keyid"))
        if current_keyid is None:
            if row.get("current_keyid"):
                row["current_model_status"] = "INVALID_KEYID"
            else:
                row["current_model_status"] = "UNLINKED"
            row["model_linked"] = "YES" if row.get("current_keyid") else "NO"
            return

        row["model_linked"] = "YES"
        try:
            decoded = db.verify_keyid(current_keyid)
            row["current_device_id"] = int_or_none(decoded.get("device_id"))
            row["current_table_id"] = int_or_none(decoded.get("tab_no"))
            row["current_domain"] = int_or_none(decoded.get("col_no"))
            if row["current_device_id"] is not None:
                current = db.get_device_by_id(
                    POLE_SWITCH_TABLE_ID,
                    row["current_device_id"],
                )
                if current:
                    row["current_db_name"] = norm(current.get("name"))
                    row["current_db_code"] = norm(current.get("code"))
                    row["current_combined_id"] = str(
                        current.get("combined_id") or ""
                    ).strip()
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"
            return
        row["current_model_status"] = "DECODED"

    @staticmethod
    def _fail(row, reason):
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "reason": reason,
            "association_ready": "NO",
            "writeback_needed": "NO",
        })
        return row

    def _resolve_row(self, row, db):
        name = str(row.get("graphical_name") or "").strip()
        family = str(row.get("device_family") or "").strip().upper()
        query_name = normalize_pole_switch_db_lookup_name(name, family)
        row.update({
            # Keep every graphical/business field exactly as drawn.  The compact
            # value is used only for the database lookup below.
            "logical_code": name,
            "selected_device_name": name,
            "database_query_name": query_name,
            "table_id": POLE_SWITCH_TABLE_ID,
            "table_name": "dms_cb_device",
            "configured_domain": POLE_SWITCH_DOMAIN,
            "match_mode": "ELEMENT_CLASSIFICATION_LBS_SEC_AR_NEAREST_TEXT",
            "combined_db_match_count": 0,
            "cb_parent_match_count": 0,
            "cb_db_match_count": 0,
            "db_combined_id": "",
            "combined_db_feeder_id": "",
            "combined_match_field": "",
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_bv_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "NO",
            "model_link_correct": "NO",
            "model_link_status": "",
            "association_action": "",
            "writeback_needed": "NO",
            "association_ready": "NO",
        })
        self._current_link_fields(row, db)

        if not name:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_NAME_NOT_FOUND: 在该柱上开关 200 距离范围内，"
                    "没有找到有明确颜色且非白色的可用名称 Text（优先上方，其次右方，最后全局），因此未查询数据库。"
                ),
            })
            return row

        combined_records = db.get_combined_device_records(query_name)
        row["combined_db_match_count"] = len(combined_records)
        row["combined_name"] = query_name
        if len(combined_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_COMBINED_NAME_NOT_UNIQUE: "
                    f"图上名称={name or '-'}；数据库查询名称={query_name or '-'}；"
                    f"在 13501 的 NAME/CODE 中匹配到 {len(combined_records)} 条，必须唯一，因此本条不处理。"
                ),
            })
            return row

        combined = combined_records[0]
        combined_id = int_or_none(combined.get("id"))
        if combined_id is None:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_COMBINED_ID_INVALID: 13501 ID 无效。",
            })
            return row
        row["db_combined_id"] = combined_id
        row["combined_name"] = query_name
        row["combined_db_code"] = str(combined.get("code") or "").strip()
        row["combined_db_name"] = str(combined.get("name") or "").strip()
        combined_feeder_id = combined.get("feeder_id")
        row["combined_db_feeder_id"] = str(combined_feeder_id or "").strip()
        row["combined_match_field"] = str(
            combined.get("_matched_field") or "NAME_OR_CODE"
        )

        cb_parent_records = db.get_cb_devices_by_combined_device_id(
            combined_id
        )
        row["cb_parent_match_count"] = len(cb_parent_records)

        # A standalone 13501 parent normally has one 13502 child. If a
        # parent has multiple children, use the classification-derived device family
        # (SEC / AR / LBS) to select exactly one child; never choose by row
        # order because RMU parents contain several Y/Q switches.
        family_records = [
            device
            for device in cb_parent_records
            if self._record_matches_family(device, family)
        ]
        cb_records = (
            family_records
            if len(cb_parent_records) != 1
            else cb_parent_records
        )
        row["cb_db_match_count"] = len(cb_records)
        if len(cb_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_CB_NOT_UNIQUE: "
                    f"13502 combined_id={combined_id}；父设备记录数="
                    f"{len(cb_parent_records)}；按设备族={family}筛选后="
                    f"{len(cb_records)}。"
                ),
            })
            return row

        device = cb_records[0]
        device_id = int_or_none(device.get("id"))
        if device_id is None:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_DEVICE_ID_INVALID: 13502 ID 无效。",
            })
            return row
        if int_or_none(device.get("combined_id")) != combined_id:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_CB_COMBINED_ID_MISMATCH: "
                    f"数据库={device.get('combined_id')}; 13501.ID={combined_id}。"
                ),
            })
            return row

        combined_feeder_id = int_or_none(row.get("combined_db_feeder_id"))
        device_feeder_id = int_or_none(device.get("feeder_id"))
        row["db_feeder_id"] = str(device.get("feeder_id") or "").strip()
        if combined_feeder_id is None or device_feeder_id is None:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_FEEDER_ID_EMPTY: 13501 和 13502 必须都有有效 feeder_id；"
                    f"13501={row.get('combined_db_feeder_id') or '-'}；"
                    f"13502={row.get('db_feeder_id') or '-'}。"
                ),
            })
            return row
        if combined_feeder_id != device_feeder_id:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_13501_13502_FEEDER_MISMATCH: 13501 和 13502 feeder_id 不一致；"
                    f"13501={combined_feeder_id}；13502={device_feeder_id}。"
                ),
            })
            return row

        bv_id = str(device.get("bv_id") or "").strip()
        if not bv_id:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_BV_ID_EMPTY: 13502 BV_ID 为空。",
            })
            return row

        expected = self._make_expected_keyid(device_id)
        row.update({
            "db_device_id": device_id,
            "db_code": norm(device.get("code")),
            "db_name": norm(device.get("name")),
            "db_cb_combined_id": str(device.get("combined_id") or "").strip(),
            "db_bv_id": bv_id,
            "db_feeder_id": str(device.get("feeder_id") or "").strip(),
            "expected_keyid": expected,
        })
        try:
            decoded = db.verify_keyid(expected)
            verified = (
                int_or_none(decoded.get("device_id")) == device_id
                and int_or_none(decoded.get("tab_no")) == POLE_SWITCH_TABLE_ID
                and int_or_none(decoded.get("col_no")) == POLE_SWITCH_DOMAIN
            )
        except Exception as exc:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": f"POLE_SWITCH_EXPECTED_KEYID_VERIFY_ERROR: {exc}",
            })
            return row
        row["expected_keyid_verified"] = "YES" if verified else "NO"
        if not verified:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_EXPECTED_KEYID_VERIFY_FAILED: 13502/domain=40。",
            })
            return row

        if int_or_none(row.get("current_keyid")) == expected:
            row.update({
                "status": "PASS",
                "severity": "PASS",
                "model_link_correct": "YES",
                "model_link_status": "当前 KeyID 正确",
                "association_action": "无需回写",
                "writeback_needed": "NO",
                "association_ready": "YES",
                "reason": "POLE_SWITCH_MODEL_LINK_CORRECT",
            })
        else:
            row.update({
                "status": "RELINK" if row.get("current_keyid") else "UNLINKED",
                "severity": "RELINK" if row.get("current_keyid") else "WARN",
                "model_link_correct": "NO",
                "model_link_status": (
                    "当前 KeyID 为空，尚未关联"
                    if not row.get("current_keyid")
                    else "当前 KeyID 不是目标 13502/domain=40"
                ),
                "association_action": "关联柱上开关" if not row.get("current_keyid") else "重新关联柱上开关",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "reason": "POLE_SWITCH_ASSOCIATION_READY",
            })
        return row

    def _analyze_file(self, db, g_file, settings=None, log_callback=None, progress_callback=None):
        settings = settings or {}
        parsed = GParser().parse(g_file)
        feeder_resolution = resolve_drawing_feeder(
            db, parsed, settings, log_callback=log_callback
        )
        discovered = PoleSwitchParser().discover(
            parsed,
            settings.get("element_catalog", {}),
            settings,
        )
        rows = []
        total = max(len(discovered), 1)
        for index, row in enumerate(discovered, start=1):
            resolved = self._resolve_row(dict(row), db)
            resolved["file_name"] = Path(g_file).name
            target_feeder_id = (
                resolved.get("db_feeder_id")
                or resolved.get("combined_db_feeder_id")
            )
            enforce_device_feeder_membership(
                resolved,
                feeder_resolution,
                device_feeder_id=target_feeder_id,
                reason_prefix="POLE_SWITCH",
            )
            rows.append(resolved)
            if log_callback:
                log_callback(
                    f"[发现柱上开关] 文件={Path(g_file).name}；"
                    f"XML_ID={resolved.get('xml_id') or '-'}；"
                    f"名称={resolved.get('graphical_name') or '-'}；"
                    f"方向={resolved.get('name_direction') or '-'}；"
                    f"距离={resolved.get('name_distance') if resolved.get('name_distance') not in (None, '') else '-'}；"
                    f"DB_ID={resolved.get('db_device_id') or '-'}；"
                    f"FEEDER_ID={target_feeder_id or '-'}；"
                    f"状态={resolved.get('status') or '-'}。"
                )
            if progress_callback:
                progress_callback(index, total, f"正在处理柱上开关 {index}/{len(discovered)}")
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 柱上开关识别完成："
                f"devref目标={len(discovered)}；"
                f"图级馈线={feeder_resolution.get('feeder_id') or '-'}；"
                f"数据库可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )

        feeder = feeder_resolution.get("feeder") or {}
        feeder_id = feeder_resolution.get("feeder_id", "")
        feeder_name = str(feeder.get("display_name") or feeder.get("name") or "").strip()
        candidate_ids = sorted({
            int_or_none(item.get("feeder_id"))
            for item in feeder_resolution.get("candidates", []) or []
            if int_or_none(item.get("feeder_id")) is not None
        })
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "POLE_SWITCH",
            "pole_switch_rows": rows,
            "feeder_resolution_source": feeder_resolution.get("feeder_source", "UNRESOLVED"),
            "feeder_resolution_evidence": feeder_resolution.get("feeder_evidence", ""),
            "feeder_anchor": feeder_resolution.get("feeder_anchor", ""),
            "feeder_id": feeder_id,
            "station_id": feeder.get("st_id", ""),
            "station_name": str(feeder.get("station_name") or "").strip(),
            "subcontrolarea_path": str(feeder.get("subcontrolarea_path") or "").strip(),
            "feeder_code": str(feeder.get("code") or "").strip(),
            "feeder_graph_name": str(feeder.get("graph_name") or "").strip(),
            "feeder_name": feeder_name,
            "feeder_path": " / ".join(
                value for value in (
                    str(feeder.get("subcontrolarea_path") or "").strip(),
                    str(feeder.get("station_name") or "").strip(),
                    str(feeder.get("name") or "").strip(),
                ) if value
            ),
            "feeder_context_ready": "YES" if feeder_resolution.get("ready") else "NO",
            "feeder_context_message": (
                "图级馈线已由 G 文件名 → 405/substation → 13500/dms_feeder_device 唯一确认；"
                "每个柱上开关还必须证明自身数据库 FEEDER_ID 与图级馈线一致。"
                if feeder_resolution.get("ready")
                else feeder_resolution.get("reason", "图级馈线无法唯一确认。")
            ),
            "graph_feeder_ids": candidate_ids,
            "graph_feeder_count": len(candidate_ids),
            "summary": {
                "pole_switch_count": len(rows),
                "pole_switch_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "pole_switch_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "pole_switch_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "pole_switch_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES"),
                "feeder_context_ready": "YES" if feeder_resolution.get("ready") else "NO",
            },
        }

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        reports = []
        aggregate = defaultdict(int)
        total_files = max(len(files), 1)
        for file_index, g_file in enumerate(files, start=1):
            report = self._analyze_file(
                db,
                g_file,
                settings,
                log_callback,
                lambda current, total, message: progress_callback(
                    int(((file_index - 1) + current / max(total, 1)) / total_files * 90) + 5,
                    message,
                ) if progress_callback else None,
            )
            reports.append(report)
            for key, value in report["summary"].items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    aggregate[key] += value
        return reports, dict(aggregate), self._rules()

    def preview_association(self, db, files, settings, log_callback, progress_callback=None):
        reports, summary, rules = self.validate(
            db,
            files,
            settings,
            log_callback,
            progress_callback,
        )
        changes_by_file = defaultdict(list)
        rows = []
        for report in reports:
            for row in report.get("pole_switch_rows", []):
                if row.get("association_ready") != "YES" or row.get("writeback_needed") != "YES":
                    continue
                change = {
                    "xml_id": row["xml_id"],
                    # Preserve the actual G XML tag. Pole-switch identity comes
                    # from LBS/SEC/AR classification, not from a fixed tag.
                    "tag": str(row.get("object_type") or "").strip(),
                    "_source_file": report["g_file"],
                    "attributes": self._attributes_for_row(row),
                    "device_name": row.get("selected_device_name", ""),
                    "device_id": row.get("db_device_id", ""),
                    "expected_keyid": row.get("expected_keyid", ""),
                    "validated_row": dict(row),
                }
                changes_by_file[report["g_file"]].append(change)
                output_row = dict(row)
                output_row["reason"] = (
                    "PREVIEW_WRITE app=6500000 voltype="
                    f"{row.get('db_bv_id', '')} p_ReportType=1 state=41 "
                    f"keyid={row.get('expected_keyid', '')}"
                )
                rows.append(output_row)

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        summary = dict(summary)
        summary["association_change_count"] = sum(
            len(items) for items in changes_by_file.values()
        )
        return {
            "reports": reports,
            "rows": rows,
            "summary": summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "pole_switch_table_id": POLE_SWITCH_TABLE_ID,
                "pole_switch_domain": POLE_SWITCH_DOMAIN,
                "element_catalog": settings.get("element_catalog", {}),
            },
        }

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        if not preview_data or not preview_data.get("changes_by_file"):
            raise RuntimeError("没有可执行的柱上开关模型关联结果。")
        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        changes_by_file = preview_data.get("changes_by_file", {})
        execution_rows = []
        executable = defaultdict(list)
        selected_count = sum(len(items) for items in changes_by_file.values())
        source_map = {str(Path(item).resolve()): Path(item) for item in files}

        for source_file, fingerprint in (
            preview_data.get("file_fingerprints", {}) or {}
        ).items():
            path = Path(source_file)
            stat = path.stat()
            if (
                stat.st_size != fingerprint.get("size")
                or stat.st_mtime_ns != fingerprint.get("mtime_ns")
            ):
                raise RuntimeError(
                    "G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验："
                    f"{source_file}"
                )

        for source_file, changes in changes_by_file.items():
            refreshed_report = self._analyze_file(
                db, Path(source_file), settings, log_callback
            )
            refreshed_by_xml = {
                str(row.get("xml_id") or ""): row
                for row in refreshed_report.get("pole_switch_rows", [])
            }
            for change in changes:
                current = dict(
                    refreshed_by_xml.get(str(change.get("xml_id") or ""), {})
                )
                if (
                    not current
                    or current.get("association_ready") != "YES"
                    or current.get("writeback_needed") != "YES"
                ):
                    if not current:
                        current = dict(change.get("validated_row", {}) or {})
                        current["reason"] = "POLE_SWITCH_EXECUTION_TARGET_NOT_FOUND"
                    current["_execution_result"] = "SKIPPED"
                    execution_rows.append((change, current))
                    continue
                refreshed = dict(change)
                refreshed["attributes"] = self._attributes_for_row(current)
                refreshed["validated_row"] = current
                executable[source_file].append(refreshed)
                current["_execution_result"] = "READY"
                execution_rows.append((refreshed, current))

        output_dir = Path(output_g_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        copied_files = []
        applied = 0
        writer = GWriteBackService(log=log_callback)
        for source_file, changes in executable.items():
            if not changes:
                continue
            source = source_map.get(str(Path(source_file).resolve()), Path(source_file))
            target = output_dir / source.name
            if target.exists():
                stem = target.stem
                suffix = target.suffix
                index = 2
                while True:
                    candidate = output_dir / f"{stem}_{index}{suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1
            source_bytes = source.read_bytes()
            target.write_bytes(source_bytes)
            result = writer.apply_attribute_changes(
                target,
                changes,
                create_backup=False,
            )
            applied += int(result.get("applied_count", 0))
            copied_files.append(str(target))

        operation_reports = []
        by_file = defaultdict(list)
        for change, row in execution_rows:
            item = dict(row)
            item["status"] = (
                "PASS" if row.get("_execution_result") == "READY" else "FAIL"
            )
            item["severity"] = item["status"]
            item["reason"] = (
                "ASSOCIATION_EXECUTED"
                if item["status"] == "PASS"
                else item.get("reason", "EXECUTION_SKIPPED")
            )
            by_file[str(change.get("_source_file") or "")].append(item)
        for source_file, rows in by_file.items():
            operation_reports.append({
                "g_file": source_file,
                "file_name": Path(source_file).name,
                "report_type": "POLE_SWITCH",
                "pole_switch_rows": rows,
                "summary": {"pole_switch_count": len(rows)},
            })

        return {
            "selected_count": selected_count,
            "applied_count": applied,
            "skipped_count": max(selected_count - applied, 0),
            "output_g_dir": str(output_dir),
            "copied_files": copied_files,
            "operation_reports": operation_reports,
            "rules": self._rules(),
        }
