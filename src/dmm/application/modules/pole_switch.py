from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.constants import RMU_LABEL_EDGE_TOLERANCE, RMU_LABEL_PATTERN
from dmm.domain.gfile.element_catalog import (
    classification_is,
    color_preference_penalty,
    name_format_penalty,
    resolve_element_record,
)
from dmm.domain.gfile.parser import GParser, GObject, ParsedG
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService


POLE_SWITCH_TABLE_ID = 13502
POLE_SWITCH_DOMAIN = 40
POLE_SWITCH_TAG = "CBreakerDis"

# The recognition authority is the CBreakerDis tag plus a keyword contained
# in its devref attribute. Never search these keywords in key_name, graphical
# text, p_NameString, or any other attribute.
POLE_SWITCH_DEVREF_KEYWORDS = ("LBS", "SEC", "AR")

# The fixed-mode resolver scans the G file's Text objects for each marked
# device. Devices do not compete for a label; the same nearest Text may be
# returned for multiple independently parsed devices.
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


def _point_to_box_distance(x: float, y: float, obj: GObject) -> float:
    box = obj.box
    dx = max(float(box.left) - x, 0.0, x - float(box.right))
    dy = max(float(box.top) - y, 0.0, y - float(box.bottom))
    return math.hypot(dx, dy)


def _text_has_background(obj: GObject) -> bool:
    """Read an explicit Text background flag when one is exported."""
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
        if value and value not in {"0", "false", "none", "null", "transparent"}:
            return True
    return False


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
        if obj.tag == "CBreakerDis":
            return bool(_marked_pole_switch_family(devref, element_catalog))
        if obj.tag == "TransformerDis":
            record = resolve_element_record(devref, element_catalog)
            return classification_is(record, "TRANSFORMER_OH")
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
    ):
        """Find and one-to-one assign the nearest eligible Text per device.

        This is shared by pole switches and TransformerDis. The scan is
        global across the G file so a device can find a label outside its
        local XML block. Text ownership is exclusive: one Text can belong to
        only one device, and competing devices are resolved by physical
        distance. The current module still returns only its own devices, while
        marked pole switches and marked pole transformers share the ownership
        pool. No RMU reservation or connection-topology analysis is performed
        in this fixed-mode name lookup.
        """

        reserved_text_ids = set()

        devices = []
        for obj in parsed.objects:
            requested = device_filter is None or device_filter(obj)
            shared_name_lock = self._is_cross_module_nameable_device(
                obj,
                element_catalog,
            )
            if not requested and not shared_name_lock:
                continue
            if not self._is_nameable_device(obj):
                continue
            # TransformerDis is not a generic nameable device.  Only the
            # element explicitly marked Transformer_OH may participate in
            # the transformer name assignment; otherwise an unmarked
            # transformer symbol could steal a nearby Text.
            if obj.tag == "TransformerDis":
                record = resolve_element_record(
                    str(obj.attrs.get("devref") or ""),
                    element_catalog,
                )
                if not classification_is(record, "TRANSFORMER_OH"):
                    continue
            devices.append(obj)
        name_settings = dict(name_settings or {})
        configured_format = str(name_settings.get("name_format") or "").strip()
        if configured_format:
            name_format = configured_format
        else:
            name_format = (
                "NUMERIC"
                if bool(name_settings.get("name_numeric", False))
                else "AUTO"
            )
        color_preferences = name_settings.get("name_colors", ["WHITE"])
        if not isinstance(color_preferences, (list, tuple, set)):
            color_preferences = [color_preferences]
        background_preference = bool(
            name_settings.get("name_has_background", False)
        )

        # These three settings are hard eligibility filters. A Text that does
        # not satisfy the configured format, color, or background rule cannot
        # be selected by any device.
        texts = []
        for obj in parsed.objects:
            if obj.xml_index in reserved_text_ids:
                continue
            if not self._global_text_is_nameable(obj):
                continue
            if name_format_penalty(self._text_value(obj), name_format) != 0:
                continue
            text_color = str(
                obj.attrs.get("lc")
                or obj.attrs.get("lcc")
                or ""
            )
            if color_preference_penalty(text_color, color_preferences) != 0:
                continue
            if _text_has_background(obj) != background_preference:
                continue
            texts.append(obj)

        if not devices or not texts:
            return defaultdict(list)

        ranked = {}
        for device in devices:
            anchors = [(device.box.cx, device.box.cy)]
            items = []
            for text_obj in texts:
                distance = min(
                    _point_to_box_distance(px, py, text_obj)
                    for px, py in anchors
                )
                items.append((
                    0,
                    0,
                    float(distance),
                    text_obj.xml_index,
                    self._text_value(text_obj),
                    text_obj,
                ))
            if nearest_only:
                # After hard filtering, physical proximity is the only
                # meaningful preference.  A farther matching Text must not
                # beat a nearer matching Text.
                items.sort(key=lambda item: (item[2], item[3]))
            else:
                items.sort(key=lambda item: (item[0], item[1], item[2]))
            ranked[device.xml_index] = items

        # Allocate Text objects one-to-one.  A Text that has already been
        # assigned to one device must not be reused by another nearby device.
        # Resolve the global competition by physical distance first, then by
        # stable XML order so the result does not depend on parser iteration
        # details.  Each device contributes only its nearest eligible Text;
        # if that Text is already owned by another device, this device stays
        # unnamed instead of falling back to a farther label.
        candidate_pairs = []
        for device in devices:
            items = ranked.get(device.xml_index, [])
            if not items:
                continue
            item = items[0]
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
        if label.box.cy < target.box.top:
            return "top"
        if label.box.cy > target.box.bottom:
            return "bottom"
        if label.box.cx < target.box.left:
            return "left"
        if label.box.cx > target.box.right:
            return "right"
        return "near"

    def discover(self, parsed: ParsedG, element_catalog=None, name_settings=None):
        global_name_owners = self.build_global_name_owners(
            parsed,
            element_catalog,
            name_settings,
            nearest_only=True,
            device_filter=lambda obj: (
                obj.tag == "CBreakerDis"
                and bool(
                    _marked_pole_switch_family(
                        str(obj.attrs.get("devref") or ""),
                        element_catalog,
                    )
                )
            ),
        )
        rows = []
        for obj in parsed.objects:
            if obj.tag != POLE_SWITCH_TAG:
                continue
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
                model,
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
                "device_family": self._model_family(model),
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
                "name_direction": label.get("direction", "") if label else "",
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
        "识别图元管理中标记为 LBS / AR / SEC 的柱上开关，"
        "按整张 G 图中距离最近的 Text 直接解析名称，关联 13501 / 13502 并安全回写 KeyID。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "CBreakerDis": {
                "table_id": POLE_SWITCH_TABLE_ID,
                "domain": POLE_SWITCH_DOMAIN,
                "match_mode": "CBREAKERDIS_ELEMENT_MARK_NEAREST_TEXT",
                "description": "柱上开关：CBreakerDis 且图元管理分类标记为 LBS/SEC/AR；每个设备独立取最近合规 Text；13501 ID -> 13502 combined_id",
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
        name = str(row.get("graphical_name") or "").strip()
        row.update({
            "logical_code": name,
            "selected_device_name": name,
            "table_id": POLE_SWITCH_TABLE_ID,
            "table_name": "dms_cb_device",
            "configured_domain": POLE_SWITCH_DOMAIN,
            "match_mode": "CBREAKERDIS_ELEMENT_MARK_NEAREST_TEXT",
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

        combined_records = db.get_combined_device_records(name)
        row["combined_db_match_count"] = len(combined_records)
        if len(combined_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_COMBINED_NAME_NOT_UNIQUE: "
                    f"13501 NAME/CODE={name}；匹配数={len(combined_records)}。"
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
        row["combined_name"] = name
        row["combined_db_code"] = str(combined.get("code") or "").strip()
        row["combined_db_name"] = str(combined.get("name") or "").strip()
        row["combined_match_field"] = str(
            combined.get("_matched_field") or "NAME_OR_CODE"
        )

        cb_parent_records = db.get_cb_devices_by_combined_device_id(
            combined_id
        )
        row["cb_parent_match_count"] = len(cb_parent_records)

        # A standalone parent normally has one child CBreakerDis. If a
        # parent has multiple children, use the devref-derived device family
        # (SEC / AR / LBS) to select exactly one child; never choose by row
        # order because RMU parents contain several Y/Q switches.
        family = str(row.get("device_family") or "").strip().upper()
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
                    "tag": POLE_SWITCH_TAG,
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
