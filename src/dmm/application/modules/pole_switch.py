from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.constants import RMU_LABEL_EDGE_TOLERANCE, RMU_LABEL_PATTERN
from dmm.config.defaults import (
    DEFAULT_POLE_SWITCH_ELEMENT_FILES,
    DEFAULT_POLE_SWITCH_ELEMENT_RULES,
    DEFAULT_TRANSFORMER_ELEMENT_FILES,
)
from dmm.domain.gfile.element_catalog import devref_matches_file
from dmm.domain.gfile.parser import GParser, GObject, ParsedG
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService


POLE_SWITCH_TABLE_ID = 13502
POLE_SWITCH_DOMAIN = 40
# A graphical Text farther than this from a target device is not a valid
# device name candidate for either pole switches or pole transformers.
DEFAULT_DEVICE_TEXT_MAX_DISTANCE = 200.0
POLE_SWITCH_TEXT_MAX_DISTANCE = 200.0
JEDDAH_NAME_PRIORITY = ("top", "right", "global")

# Makkah name recognition does not restrict Text color.  Device-name
# selection is geometry-driven (TOP -> RIGHT -> GLOBAL, <= 200) after the
# common noise filters have removed obvious non-name annotations.

# Makkah standalone pole-switch identity is maintained as an exact devref-file
# list in local/shared settings. Every configured file is a pole switch; users
# do not maintain AR/LBS/SEC classifications. Element Management classifications
# are not part of this model.
POLE_SWITCH_DEVREF_KEYWORDS = ("LBS", "SEC", "AR")  # legacy compatibility only
# The operator-maintained file list is authoritative. There is deliberately no
# devref-prefix, XML-tag, shape, color, or cross-model exclusion at device
# recognition time: if the selected devref filename matches, it is a pole
# switch for this module.

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


def normalize_pole_switch_db_lookup_name(value: str, device_family: str = "") -> str:
    """Return the Makkah pole-switch graphical name *unchanged* for 13501.

    The G-file Text value is the authoritative database lookup value.  Do not
    trim, collapse whitespace, remove hyphens/dots, change case, or otherwise
    standardize it before querying ``dms_combined_device.NAME``.

    ``device_family`` is retained only for backward API compatibility and is
    intentionally ignored.
    """
    del device_family
    return str(value or "")

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


def _normalize_devref_file_name(value: str) -> str:
    file_name = str(value or "").strip().replace("\\", "/")
    file_name = file_name.rsplit("/", 1)[-1].lstrip("#")
    if ":" in file_name:
        file_name = file_name.split(":", 1)[0]
    return file_name.strip()


def _normalized_pole_switch_element_files(settings=None):
    """Return operator-maintained pole-switch devref file names.

    New v4.1.94 settings store a simple list under ``pole_switch_element_files``.
    Older v4.1.93 ``pole_switch_element_rules`` entries are migrated by taking
    only ``file_name`` and ignoring their AR/LBS/SEC family. An explicit empty
    list intentionally disables discovery.
    """
    source = None
    if isinstance(settings, dict) and "pole_switch_element_files" in settings:
        source = settings.get("pole_switch_element_files")
    elif isinstance(settings, dict) and "pole_switch_element_rules" in settings:
        source = settings.get("pole_switch_element_rules")
    if source is None:
        source = DEFAULT_POLE_SWITCH_ELEMENT_FILES
    if not isinstance(source, (list, tuple)):
        return []

    values = []
    seen = set()
    for item in source:
        if isinstance(item, dict):
            value = item.get("file_name") or item.get("name") or ""
        else:
            value = item
        file_name = _normalize_devref_file_name(value)
        if not file_name:
            continue
        folded = file_name.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        values.append(file_name)
    return values


def _normalized_pole_switch_element_rules(settings=None):
    """Legacy compatibility view of pole-switch configuration.

    The active model no longer uses family for recognition or database
    disambiguation. This helper remains so older settings/tests can be read
    without breaking during migration.
    """
    legacy_source = None
    if isinstance(settings, dict) and "pole_switch_element_rules" in settings:
        legacy_source = settings.get("pole_switch_element_rules")
    if legacy_source is None:
        legacy_source = DEFAULT_POLE_SWITCH_ELEMENT_RULES
    if not isinstance(legacy_source, (list, tuple)):
        legacy_source = []

    family_by_file = {}
    for item in legacy_source:
        if not isinstance(item, dict):
            continue
        file_name = _normalize_devref_file_name(item.get("file_name") or item.get("name"))
        family = str(item.get("family") or "").strip().upper()
        if file_name and family in POLE_SWITCH_DEVREF_KEYWORDS:
            family_by_file[file_name.casefold()] = family

    rules = []
    for file_name in _normalized_pole_switch_element_files(settings):
        family = family_by_file.get(file_name.casefold(), "")
        rules.append({"file_name": file_name, "family": family})
    return rules


def _is_configured_pole_switch_devref(value: str, settings=None) -> bool:
    """Return True exactly when devref is in the user-selected switch list.

    The configured filename list is the sole device-recognition authority. No
    XML tag, RMU_* prefix, color, geometry, internal structure, or transformer
    list overlap is allowed to veto a user-selected pole-switch element.
    """
    raw = str(value or "")
    return any(
        devref_matches_file(raw, file_name)
        for file_name in _normalized_pole_switch_element_files(settings)
    )


def _normalized_transformer_element_files(settings=None):
    source = None
    if isinstance(settings, dict) and "transformer_element_files" in settings:
        source = settings.get("transformer_element_files")
    if source is None:
        source = DEFAULT_TRANSFORMER_ELEMENT_FILES
    if not isinstance(source, (list, tuple)):
        return []
    values = []
    seen = set()
    for value in source:
        file_name = str(value or "").strip().replace("\\", "/")
        file_name = file_name.rsplit("/", 1)[-1].lstrip("#")
        if ":" in file_name:
            file_name = file_name.split(":", 1)[0]
        if not file_name:
            continue
        key = file_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(file_name)
    return values


def _marked_pole_switch_family(value: str, settings=None) -> str:
    """Legacy family metadata only; not used by active v4.1.94 model logic."""
    if not _is_configured_pole_switch_devref(value, settings):
        return ""
    raw = str(value or "")
    for rule in _normalized_pole_switch_element_rules(settings):
        if devref_matches_file(raw, rule["file_name"]):
            return str(rule.get("family") or "").strip().upper()
    return ""


def _devref_model_label(value: str, keyword: str) -> str:
    raw = str(value or "").strip()
    tail = raw.rsplit(":", 1)[-1].strip()
    tail = re.sub(r"\.zwk\.icn\.g$", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"^RMU_", "", tail, flags=re.IGNORECASE)
    return tail or keyword


def _point_to_box_distance(x: float, y: float, obj: GObject) -> float:
    box = obj.box
    dx = max(float(box.left) - x, 0.0, x - float(box.right))
    dy = max(float(box.top) - y, 0.0, y - float(box.bottom))
    return math.hypot(dx, dy)



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
        value = re.sub(r"\s+", " ", str(text or "").strip())
        if not value or not any(char.isalnum() for char in value):
            return False
        upper = re.sub(r"\s+", "", value).upper()
        if upper in _NON_NAME_LABELS or upper in _NON_DEVICE_TEXT_EXACT:
            return False
        if re.fullmatch(r"[YQ]\d+", upper):
            return False
        # Pure decimal numeric annotations (coordinates/measurements such as
        # 21.449047) are never device names in Makkah. Integer names remain
        # fully eligible.
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)+", value):
            return False
        return True

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
    def _is_cross_module_nameable_device(obj: GObject, element_catalog=None, name_settings=None) -> bool:
        """Identify marked pole switches and pole transformers for Text locks.

        The pole-switch and transformer modules run independently, but their
        graphical names still follow one ownership rule within the same G
        drawing.  Including both families in the allocation pool prevents a
        Text claimed by one family from being reused by the other family.
        """
        del element_catalog
        devref = str(obj.attrs.get("devref") or "")
        if _is_configured_pole_switch_devref(devref, name_settings):
            return True
        return any(
            devref_matches_file(devref, file_name)
            for file_name in _normalized_transformer_element_files(name_settings)
        )

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

    @classmethod
    def _device_anchor_points(cls, device: GObject, parsed: ParsedG):
        """Use ConnectLine endpoints as visual/electrical anchors.

        A GIcon's bounding box is often much larger than the rendered symbol.
        GFileStudio therefore measures name distance from the endpoint that
        actually touches the device.  Lines remain topology evidence only and
        are never treated as nameable objects.
        """
        by_id = {
            str(obj.xml_id): obj
            for obj in parsed.objects
            if str(obj.xml_id or "").strip()
        }
        attached = defaultdict(list)
        line_by_id = {}
        for line in parsed.objects:
            if line.tag != "ConnectLine":
                continue
            if line.xml_id:
                line_by_id[str(line.xml_id)] = line
            for ref in cls._refs(line):
                attached[ref].append(line)

        lines = []
        seen = set()
        for ref in cls._refs(device):
            line = line_by_id.get(ref)
            if line is not None and id(line) not in seen:
                lines.append(line)
                seen.add(id(line))
        for line in attached.get(str(device.xml_id), []):
            if id(line) not in seen:
                lines.append(line)
                seen.add(id(line))

        anchors = []
        for line in lines:
            points = cls._line_points(line)
            if not points:
                continue
            endpoints = (points[0], points[-1])
            anchor = min(
                endpoints,
                key=lambda point: _point_to_box_distance(point[0], point[1], device),
            )
            anchors.append(anchor)
        if not anchors:
            return [(device.box.cx, device.box.cy)]
        unique = []
        seen_points = set()
        for point in anchors:
            key = (round(point[0], 6), round(point[1], 6))
            if key not in seen_points:
                unique.append(point)
                seen_points.add(key)
        return unique

    @staticmethod
    def _global_text_is_nameable(obj: GObject) -> bool:
        """Return whether a Text may participate in Makkah device naming.

        Makkah deliberately does not constrain color, background, pure-numeric
        versus alphanumeric style, or letter/digit composition.  The only
        common lexical filters are obvious operational/unit annotations and
        pure decimal numeric noise.
        """
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
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)+", normalized):
            return False
        return True

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

        This is shared by pole switches and TransformerDis. The scan is
        global across the G file so a device can find a label outside its
        local XML block.  By default Text ownership is exclusive and marked
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
                    name_settings,
                )
            )
            if not requested and not shared_name_lock:
                continue
            # An explicitly requested device_filter is authoritative for this
            # scan. Pole-switch recognition is configured-file-driven, so the
            # XML element tag must never disqualify a configured AR/LBS/SEC
            # object. Shared/legacy devices still use the generic structural
            # guard to avoid treating drawing primitives as devices.
            if not requested and not self._is_nameable_device(obj):
                continue
            if requested and not str(obj.xml_id or "").strip():
                continue
            # A configured pole-transformer devref is authoritative regardless
            # of the concrete XML tag. Keep one legacy guard only for an
            # unconfigured TransformerDis symbol so it cannot steal Text from
            # a configured device when a generic/shared scan is requested.
            devref = str(obj.attrs.get("devref") or "")
            is_marked_transformer = any(
                devref_matches_file(devref, file_name)
                for file_name in _normalized_transformer_element_files(name_settings)
            )
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
                # callers.  ``direction_priority`` is different: it keeps every
                # direction eligible, but ranks preferred directions before the
                # global fallback.  Pole switches use TOP -> RIGHT -> GLOBAL.
                direction = self._direction(device, text_obj)
                if (
                    allowed_directions is not None
                    and direction not in allowed_directions
                ):
                    continue
                distance = device.box.edge_distance(text_obj.box)
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
            # Keep the exact G-file Text.ts alongside the normalized visible
            # label.  Makkah pole-switch DB lookup uses raw_text unchanged;
            # transformer/fuse callers can keep using the normalized ``text``.
            "raw_text": str(chosen[6].attrs.get("ts") or ""),
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
        # Direction is inferred from rectangle edges only; center points are
        # not part of Makkah name recognition.
        if label.box.bottom <= target.box.top:
            return "top"
        if label.box.left >= target.box.right:
            return "right"
        if label.box.top >= target.box.bottom:
            return "bottom"
        if label.box.right <= target.box.left:
            return "left"
        return "near"

    def discover(self, parsed: ParsedG, element_catalog=None, name_settings=None):
        global_name_owners = self.build_global_name_owners(
            parsed,
            element_catalog,
            name_settings,
            nearest_only=True,
            device_filter=lambda obj: _is_configured_pole_switch_devref(
                str(obj.attrs.get("devref") or ""),
                name_settings,
            ),
            # Pole-switch recognition is driven only by the configured exact
            # devref file rules; concrete XML tag remains irrelevant.
            include_shared_devices=False,
            lock_text_ownership=True,
            max_text_distance=POLE_SWITCH_TEXT_MAX_DISTANCE,
            allowed_directions=None,
            direction_priority=None,
            text_color_ranker=None,
            color_priority_first=False,
        )
        rows = []
        for obj in parsed.objects:
            raw_devref = str(obj.attrs.get("devref") or "").strip()
            if not _is_configured_pole_switch_devref(raw_devref, name_settings):
                continue
            # Device family is intentionally not part of recognition anymore.
            # Keep legacy metadata only for old settings/report compatibility;
            # database association never uses it.
            legacy_family = _marked_pole_switch_family(raw_devref, name_settings)
            model = _devref_model_label(raw_devref, legacy_family or "POLE_SWITCH")

            label, _label_candidates = self.find_nearest_name(
                parsed,
                obj,
                "",
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
                # Retained only as legacy metadata for old v4.1.93 settings.
                # It is not shown to users and never participates in matching.
                "device_family": legacy_family,
                "key_name": str(obj.attrs.get("key_name") or "").strip(),
                "current_keyid": obj.keyid,
                "inside_rmu": "NOT_ANALYZED",
                "topology_component": "",
                "topology_member_count": 0,
                "topology_member_ids": "",
                "topology_member_tags": "",
                "topology_neighbor_count": 0,
                "topology_neighbor_ids": "",
                "graphical_name": label.get("raw_text", label.get("text", "")) if label else "",
                "name_source": "NEAREST_GRAPHICAL_TEXT" if label else "",
                "name_distance": label.get("distance", "") if label else "",
                "name_direction": label.get("direction", "") if label else "",
                "name_priority": "GLOBAL" if label else "",
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
        "麦加柱上开关只认用户维护的精确 devref 图元文件名单；"
        "名称不限制颜色、背景、纯数字或字母数字格式，整张 G 图做全局最近匹配，"
        "同一优先级内使用矩形最小边缘距离最近的 Text，最大距离 200；纯小数 Text 直接排除。"
        "数据库关联不判断 FEEDER_ID：只用名称唯一匹配 13501，再唯一定位 13502 子设备并安全回写 KeyID。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "CONFIGURED_POLE_SWITCH_ELEMENT_FILES": {
                "table_id": POLE_SWITCH_TABLE_ID,
                "domain": POLE_SWITCH_DOMAIN,
                "match_mode": "MAKKAH_CONFIGURED_DEVREF_GLOBAL_TEXT_NAME_ONLY_NO_FEEDER",
                "description": (
                    "只认用户维护的精确 devref 文件名；名单中的每个图元都直接视为柱上开关，不再区分 AR/LBS/SEC。"
                    "名称不限制颜色、背景或字母数字格式，矩形最小边缘距离最大200、Text全局一对一且一旦分配即退出候选池；"
                    "纯小数排除。数据库查询直接使用 G 文件原始 Text 名称，不删除空格、横线、点号等字符；只使用13501.NAME，不使用CODE兜底、不判断FEEDER_ID；13501唯一后要求13502子设备也唯一。"
                ),
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

    def _resolve_row(self, row, db):
        # Preserve the exact graphical Text value for the Makkah 13501 NAME query.
        name = str(row.get("graphical_name") or "")
        query_name = normalize_pole_switch_db_lookup_name(name)
        row.update({
            "logical_code": name,
            "selected_device_name": name,
            "database_query_name": query_name,
            "table_id": POLE_SWITCH_TABLE_ID,
            "table_name": "dms_cb_device",
            "configured_domain": POLE_SWITCH_DOMAIN,
            "match_mode": "MAKKAH_CONFIGURED_DEVREF_GLOBAL_TEXT_NAME_ONLY_NO_FEEDER",
            "combined_db_match_count": 0,
            "cb_parent_match_count": 0,
            "cb_db_match_count": 0,
            "db_combined_id": "",
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
                "reason": "POLE_SWITCH_NAME_NOT_FOUND: 未找到柱上开关邻近图上名称。",
            })
            return row

        combined_records = db.get_combined_device_records(query_name)
        row["combined_db_match_count"] = len(combined_records)
        if len(combined_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_COMBINED_NAME_NOT_UNIQUE: "
                    f"图上名称={name}；数据库查询NAME={query_name}；匹配数={len(combined_records)}。"
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
        row["combined_match_field"] = str(
            combined.get("_matched_field") or "NAME"
        )

        cb_parent_records = db.get_cb_devices_by_combined_device_id(
            combined_id
        )
        row["cb_parent_match_count"] = len(cb_parent_records)

        # v4.1.94 intentionally has no AR/LBS/SEC classification. A uniquely
        # matched 13501 parent must therefore have exactly one 13502 child.
        # Never choose an arbitrary child, because that could create different
        # associations for the same drawing/database state.
        cb_records = list(cb_parent_records)
        row["cb_db_match_count"] = len(cb_records)
        if len(cb_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_CB_NOT_UNIQUE: "
                    f"13502 combined_id={combined_id}；子设备记录数={len(cb_records)}；"
                    "柱上开关不再按 AR/LBS/SEC 分类消歧，必须唯一后才能关联。"
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

    @staticmethod
    def _log_found_device(log_callback, index, row):
        """Write every discovered pole-switch device to the run console."""
        if not log_callback:
            return
        name = str(row.get("selected_device_name") or row.get("graphical_name") or "").strip() or "<未找到名称>"
        model = str(row.get("device_model") or row.get("device_family") or "").strip() or "-"
        xml_id = str(row.get("xml_id") or "").strip() or "-"
        text_id = str(row.get("name_xml_id") or "").strip() or "-"
        distance = row.get("name_distance", "")
        distance_text = str(distance).strip() if distance not in (None, "") else "-"
        db_id = str(row.get("db_device_id") or "").strip() or "-"
        status = str(row.get("status") or "").strip() or "-"
        ready = str(row.get("association_ready") or "NO").strip() or "NO"
        reason = str(row.get("reason") or "").strip() or "-"
        log_callback(
            f"[柱上开关][找到设备] #{index} 名称={name}；模型={model}；"
            f"XML_ID={xml_id}；Text_ID={text_id}；距离={distance_text}；"
            f"DB_ID={db_id}；状态={status}；可关联={ready}；原因={reason}"
        )

    def _analyze_file(self, db, g_file, settings=None, log_callback=None, progress_callback=None):
        parsed = GParser().parse(g_file)
        discovered = PoleSwitchParser().discover(
            parsed,
            (settings or {}).get("element_catalog", {}),
            settings or {},
        )
        rows = []
        total = max(len(discovered), 1)
        for index, row in enumerate(discovered, start=1):
            resolved = self._resolve_row(dict(row), db)
            resolved["file_name"] = Path(g_file).name
            rows.append(resolved)
            self._log_found_device(log_callback, index, resolved)
            if progress_callback:
                progress_callback(index, total, f"正在处理柱上开关 {index}/{len(discovered)}")
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 柱上开关识别完成："
                f"devref目标={len(discovered)}；数据库可关联="
                f"{sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "POLE_SWITCH",
            "pole_switch_rows": rows,
            "summary": {
                "pole_switch_count": len(rows),
                "pole_switch_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "pole_switch_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "pole_switch_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "pole_switch_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES"),
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
                    "tag": row.get("object_type") or "CBreakerDis",
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
                "pole_switch_element_files": list(
                    _normalized_pole_switch_element_files(settings)
                ),
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
            for change in changes:
                base = dict(change.get("validated_row", {}) or {})
                current = self._resolve_row(dict(base), db)
                if (
                    current.get("association_ready") != "YES"
                    or current.get("writeback_needed") != "YES"
                ):
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
