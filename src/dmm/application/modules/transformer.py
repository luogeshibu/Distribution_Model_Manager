from __future__ import annotations

import re
from collections import defaultdict, deque
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.application.modules.feeder_context import (
    enforce_device_feeder_membership,
    resolve_drawing_feeder,
)
from dmm.domain.gfile.parser import (
    GParser,
    GObject,
    ParsedG,
    box_min_edge_distance,
    box_relative_direction,
)
from dmm.domain.gfile.element_catalog import (
    classification_is,
    element_key_candidates,
    normalize_element_key,
    resolve_element_record,
)
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService
from dmm.application.modules.pole_switch import (
    DEFAULT_DEVICE_TEXT_MAX_DISTANCE,
    POLE_SWITCH_NAME_RE,
    PoleSwitchParser,
)


TRANSFORMER_TABLE_ID = 13505
TRANSFORMER_DOMAIN = 1
TRANSFORMER_TAG_FALLBACK = "TransformerDis"
TRANSFORMER_PRIMARY_ELEMENT_FILE = "Transformer_OH.pb.icn.g"
TRANSFORMER_MODEL_TEXT_MAX_DISTANCE = 300.0


def resolve_transformer_graphical_name(row, db, used_text_ids=None):
    """Resolve one Transformer_OH name using the transformer module's own rules.

    Geometry produces an ordered candidate list from the whole G drawing, in any
    direction, while retaining the transformer distance limit. Only white Text
    is eligible. Database uniqueness in 13505 is then used to choose among those
    geometrically valid candidates. This keeps colored annotations (for example
    a nearby red LBS name) from becoming a transformer name.
    """
    used_text_ids = used_text_ids if used_text_ids is not None else set()
    candidates = list(row.get("name_candidates") or [])
    if not candidates and str(row.get("graphical_name") or "").strip():
        candidates = [{
            "text": str(row.get("graphical_name") or "").strip(),
            "distance": row.get("name_distance", ""),
            "direction": str(row.get("name_direction") or "").strip(),
            "xml_id": str(row.get("name_xml_id") or "").strip(),
        }]

    trace = []
    selected = None
    selected_record = None
    for candidate in candidates:
        text = str(candidate.get("text") or "").strip()
        text_xml_id = str(candidate.get("xml_id") or "").strip()
        if not text:
            continue
        if text_xml_id and text_xml_id in used_text_ids:
            trace.append(f"{text}:TEXT_ALREADY_USED")
            continue
        records = []
        try:
            records = db.get_transformer_devices_by_name(
                text,
                feeder_id=None,
                table_id=TRANSFORMER_TABLE_ID,
            ) or []
        except Exception as exc:
            trace.append(f"{text}:DB_ERROR:{exc}")
            continue
        trace.append(f"{text}:MATCH={len(records)}")
        if len(records) != 1:
            continue
        selected = candidate
        selected_record = records[0]
        if text_xml_id:
            used_text_ids.add(text_xml_id)
        break

    if selected is not None:
        row["graphical_name"] = str(selected.get("text") or "").strip()
        row["name_source"] = "NEAREST_GRAPHICAL_TEXT_DB_UNIQUE"
        row["name_distance"] = selected.get("distance", "")
        row["name_direction"] = str(selected.get("direction") or "").strip()
        row["name_xml_id"] = str(selected.get("xml_id") or "").strip()
        row["name_db_match_count"] = 1
        row["name_db_device_id"] = int_or_none((selected_record or {}).get("id"))
        row["name_db_feeder_id"] = str((selected_record or {}).get("feeder_id") or "").strip()
        row["name_resolution_status"] = "UNIQUE_13505"
    else:
        row["name_db_match_count"] = 0
        row["name_db_device_id"] = ""
        row["name_db_feeder_id"] = ""
        row["name_resolution_status"] = "NO_UNIQUE_13505_CANDIDATE"
    row["name_resolution_trace"] = ";".join(trace)
    return row


class TransformerParser(PoleSwitchParser):
    """Recognize Jeddah pole transformers with a fixed-symbol-first rule.

    Priority 1 is the standard ``Transformer_OH.pb.icn.g`` element referenced
    by the G object itself. It is accepted directly and does not depend on the
    local Element Management cache. Priority 2 is the user-maintained
    ``TRANSFORMER_OH`` classification, which remains a fallback for alternate
    or site-specific transformer symbols.
    """

    @staticmethod
    def _is_valid_name(text: str) -> bool:
        """Accept numeric transformer names such as 97803.

        The pole-switch parser deliberately rejects pure numeric labels because
        they are not valid pole-switch names in its drawings. Transformer
        names are different: the database and supplied G files use numeric
        Text values, so numeric labels must remain eligible here.
        """
        value = str(text or "").strip()
        if not value or not any(char.isalnum() for char in value):
            return False
        if value.upper() in {
            "SMART", "SMR", "NOP", "N.O.P", "N-O-P", "N_O_P",
            "F.C", "FC", "BUS", "G", "I",
        }:
            return False
        if re.fullmatch(r"[YQ]\d+", value.replace(" ", "").upper()):
            return False
        return bool(POLE_SWITCH_NAME_RE.fullmatch(value))

    @staticmethod
    def _text_value(obj: GObject) -> str:
        return re.sub(r"\s+", " ", str(obj.attrs.get("ts") or "")).strip()


    @staticmethod
    def _is_white_name_text(obj: GObject) -> bool:
        """Return True only for white/default-white visible Text.

        D5000 uses lc as the primary visible text color and lcc as a fallback.
        Missing color attributes render as the default white in the supplied G
        files, so they remain eligible.
        """
        raw = str(obj.attrs.get("lc") or obj.attrs.get("lcc") or "").strip()
        normalized = re.sub(r"\s+", "", raw).upper()
        return normalized in {
            "",
            "255,255,255",
            "255,255,255,255",
            "#FFFFFF",
            "#FFFFFFFF",
        }

    @classmethod
    def _is_transformer_model_name_text(cls, obj: GObject) -> bool:
        """Jeddah standalone pole-transformer name candidate.

        The standalone Transformer_OH model uses a deliberately strict Text
        pool: the visible label must be pure ASCII digits, white (or default
        white), and must not declare an opaque/background fill.  The scan is
        still global across the whole G drawing.

        FUSE now reuses this same standalone Jeddah name rule after it has
        first locked its nearest Transformer_OH.  Feeder-context naming remains
        on its legacy shared path.
        """
        if obj.tag.lower() != "text":
            return False
        value = cls._text_value(obj)
        if not re.fullmatch(r"[0-9]+", value):
            return False
        if not cls._is_white_name_text(obj):
            return False

        # Real Jeddah G files normally omit a background attribute entirely.
        # Accept explicit transparent/off values, but reject any explicit
        # enabled/opaque background.  Do not inspect ``fc``: in D5000 Text it
        # is not the visible text background and real white-name labels often
        # carry fc=0,255,0.
        background_keys = (
            "background", "bg", "bgcolor", "backgroundcolor",
            "fill", "fillcolor", "fill_color",
        )
        transparent_values = {
            "", "0", "false", "none", "transparent", "null",
            "0,0,0,0", "#00000000",
        }
        attrs_lower = {str(key).lower(): value for key, value in obj.attrs.items()}
        for key in background_keys:
            if key not in attrs_lower:
                continue
            raw = re.sub(r"\s+", "", str(attrs_lower.get(key) or "")).lower()
            if raw not in transparent_values:
                return False
        return True

    @staticmethod
    def _transformer_model_rect_direction(device: GObject, text_obj: GObject) -> str:
        """Classify name direction from the two rectangles only.

        TOP/RIGHT/BOTTOM/LEFT require edge adjacency on that side. Diagonal
        placements are GLOBAL fallback candidates. No center-point vector or
        Text x/y anchor is used.
        """
        return box_relative_direction(device.box, text_obj.box)

    @classmethod
    def _transformer_model_direction_priority(cls, device: GObject, text_obj: GObject) -> int:
        """Jeddah priority: top first, then right, then global fallback."""
        direction = cls._transformer_model_rect_direction(device, text_obj)
        if direction == "top":
            return 0
        if direction == "right":
            return 1
        return 2

    @staticmethod
    def _transformer_model_priority_label(priority: int) -> str:
        return {0: "TOP", 1: "RIGHT", 2: "GLOBAL"}.get(int(priority), "GLOBAL")

    @staticmethod
    def _uses_primary_transformer_element(obj: GObject) -> bool:
        """Return True for the standard Jeddah pole-transformer element file."""
        devref = str(obj.attrs.get("devref") or "")
        primary_key = normalize_element_key(TRANSFORMER_PRIMARY_ELEMENT_FILE)
        return primary_key in set(element_key_candidates(devref))

    @classmethod
    def _transformer_recognition_source(cls, obj: GObject, element_catalog=None) -> str:
        """Return the first matching recognition source in strict priority order."""
        if cls._uses_primary_transformer_element(obj):
            return "PRIMARY_ELEMENT_FILE"
        record = resolve_element_record(
            str(obj.attrs.get("devref") or ""),
            element_catalog,
        )
        if classification_is(record, "TRANSFORMER_OH"):
            return "TRANSFORMER_OH_CLASSIFICATION_FALLBACK"
        return ""

    @classmethod
    def _is_transformer_object(cls, obj: GObject, element_catalog=None) -> bool:
        return bool(cls._transformer_recognition_source(obj, element_catalog))

    @staticmethod
    def _transformer_model_edge_distance(device: GObject, text_obj: GObject) -> float:
        """Shortest distance between transformer and Text rectangle edges."""
        return box_min_edge_distance(device.box, text_obj.box)

    def discover_with_edge_distance_names(
        self,
        parsed: ParsedG,
        element_catalog=None,
        name_settings=None,
    ):
        """Transformer_OH name allocation using rectangle minimum-edge distance.

        This compatibility path keeps the historical any-direction white-Text
        behavior, but its geometry is unified with the current models: device
        rectangle to Text rectangle minimum-edge distance, never center distance.
        """
        del name_settings

        devices = [
            obj
            for obj in parsed.objects
            if self._is_transformer_object(obj, element_catalog)
        ]
        texts = [
            obj
            for obj in parsed.objects
            if self._global_text_is_nameable(obj)
            and self._is_white_name_text(obj)
        ]

        ranked = {}
        candidate_pairs = []
        for device in devices:
            items = []
            for text_obj in texts:
                distance = self._transformer_model_edge_distance(
                    device, text_obj
                )
                if distance > float(DEFAULT_DEVICE_TEXT_MAX_DISTANCE):
                    continue
                item = (
                    0,
                    0,
                    float(distance),
                    text_obj.xml_index,
                    self._text_value(text_obj),
                    text_obj,
                )
                items.append(item)
                candidate_pairs.append((
                    float(distance),
                    text_obj.xml_index,
                    device.xml_index,
                    text_obj,
                    item,
                ))
            items.sort(key=lambda item: (item[2], item[3]))
            ranked[device.xml_index] = items

        # Global one-to-one nearest allocation, exactly within this target
        # family.  A device and a Text may each be consumed only once.
        candidate_pairs.sort(key=lambda item: (item[0], item[1], item[2]))
        owners = defaultdict(list)
        assigned_devices = set()
        assigned_text_ids = set()
        for _distance, _text_order, device_xml_index, text_obj, candidate in candidate_pairs:
            if device_xml_index in assigned_devices:
                continue
            if text_obj.xml_index in assigned_text_ids:
                continue
            owners[device_xml_index].append(candidate)
            assigned_devices.add(device_xml_index)
            assigned_text_ids.add(text_obj.xml_index)

        rows = []
        for obj in devices:
            label, _candidates = self.find_nearest_name(
                parsed,
                obj,
                "",
                (),
                owners,
            )
            attrs = obj.attrs
            name_candidates = []
            for (
                _format_penalty,
                _color_penalty,
                distance,
                _xml_index,
                text,
                text_obj,
            ) in ranked.get(obj.xml_index, []):
                name_candidates.append({
                    "text": text,
                    "distance": round(float(distance), 3),
                    "direction": self._direction(obj, text_obj),
                    "xml_id": str(text_obj.xml_id or ""),
                })
            rows.append({
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": str(attrs.get("devref") or "").strip(),
                "recognition_source": self._transformer_recognition_source(obj, element_catalog),
                "graphical_name": label.get("text", "") if label else "",
                "name_source": "GLOBAL_NEAREST_WHITE_TEXT" if label else "",
                "name_distance": label.get("distance", "") if label else "",
                "name_direction": label.get("direction", "") if label else "",
                "name_xml_id": label.get("xml_id", "") if label else "",
                "name_candidates": name_candidates,
                "name_distance_basis": "RECTANGLE_MIN_EDGE_DISTANCE",
                "current_keyid1": str(attrs.get("keyid1") or "").strip(),
                "current_keyid2": str(attrs.get("keyid2") or "").strip(),
                "status": "",
                "severity": "",
                "reason": "",
            })

        return rows, {}

    def discover_for_transformer_model(
        self,
        parsed: ParsedG,
        element_catalog=None,
        name_settings=None,
    ):
        """Discover Jeddah pole transformers with top/right/global name priority.

        Standalone pole-transformer rules:
        1. scan the complete drawing for the standard Transformer_OH.pb.icn.g
           element first; for any other element, accept TRANSFORMER_OH
           classification only as the fallback recognition path;
        2. scan the complete drawing for Text that is pure numeric, white and
           has no background;
        3. keep a 300-unit limit using rectangle-to-rectangle minimum-edge distance;
        4. rank direction tiers strictly as TOP -> RIGHT -> GLOBAL;
        5. inside the same tier, shorter distance wins;
        6. preserve one-to-one Text ownership across all recognized pole transformers;
           if devices compete for one Text, the closer device still wins.

        This remains separate from ``discover_with_edge_distance_names`` for
        legacy callers.  The current FUSE model intentionally reuses this Jeddah
        TOP -> RIGHT -> GLOBAL path after selecting its nearest transformer.
        """
        del name_settings

        devices = [
            obj
            for obj in parsed.objects
            if self._is_transformer_object(obj, element_catalog)
        ]
        texts = [
            obj
            for obj in parsed.objects
            if self._is_transformer_model_name_text(obj)
        ]

        ranked = {}
        candidate_pairs = []
        for device in devices:
            items = []
            for text_obj in texts:
                distance = self._transformer_model_edge_distance(device, text_obj)
                if distance > float(TRANSFORMER_MODEL_TEXT_MAX_DISTANCE):
                    continue
                direction = self._transformer_model_rect_direction(device, text_obj)
                priority = self._transformer_model_direction_priority(device, text_obj)
                item = {
                    "priority": int(priority),
                    "priority_label": self._transformer_model_priority_label(priority),
                    "distance": float(distance),
                    "text_order": int(text_obj.xml_index),
                    "device_order": int(device.xml_index),
                    "text": self._text_value(text_obj),
                    "text_obj": text_obj,
                    "direction": direction,
                }
                items.append(item)
                candidate_pairs.append(item)
            items.sort(key=lambda item: (
                item["priority"],
                item["distance"],
                item["text_order"],
            ))
            ranked[device.xml_index] = items

        # Preserve the existing global one-to-one ownership rule while adding
        # a per-transformer direction preference.  Each recognized transformer proposes
        # candidates in TOP -> RIGHT -> GLOBAL order.  If two transformers want
        # the same Text, the physically closer transformer keeps it (stable XML
        # order is the tie-breaker), and the losing transformer continues with
        # its next candidate.  This keeps the old "closer device owns the Text"
        # behavior instead of letting a distant TOP claim steal a label from a
        # much closer transformer.
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
                item = items[next_candidate_index[device_xml_index]]
                next_candidate_index[device_xml_index] += 1
                text_xml_index = item["text_order"]
                incumbent = owner_by_text.get(text_xml_index)
                if incumbent is None:
                    owner_by_text[text_xml_index] = item
                    assigned_by_device[device_xml_index] = item
                    break

                challenger_key = (item["distance"], item["device_order"])
                incumbent_key = (
                    incumbent["distance"],
                    incumbent["device_order"],
                )
                if challenger_key < incumbent_key:
                    old_device = incumbent["device_order"]
                    assigned_by_device.pop(old_device, None)
                    owner_by_text[text_xml_index] = item
                    assigned_by_device[device_xml_index] = item
                    queue.append(old_device)
                    break
                # This Text stays with the closer transformer; continue with
                # the next candidate for the current device.

        rows = []
        for obj in devices:
            selected = assigned_by_device.get(obj.xml_index)
            attrs = obj.attrs
            name_candidates = []
            for item in ranked.get(obj.xml_index, []):
                text_obj = item["text_obj"]
                name_candidates.append({
                    "text": item["text"],
                    "distance": round(float(item["distance"]), 3),
                    "direction": item["direction"],
                    "priority": item["priority_label"],
                    "xml_id": str(text_obj.xml_id or ""),
                })

            text_obj = selected.get("text_obj") if selected else None
            rows.append({
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": str(attrs.get("devref") or "").strip(),
                "recognition_source": self._transformer_recognition_source(obj, element_catalog),
                "graphical_name": selected.get("text", "") if selected else "",
                "name_source": "JEDDAH_TOP_RIGHT_GLOBAL_NUMERIC_WHITE_NO_BACKGROUND" if selected else "",
                "name_distance": round(float(selected["distance"]), 3) if selected else "",
                "name_direction": selected.get("direction", "") if selected else "",
                "name_priority": selected.get("priority_label", "") if selected else "",
                "name_xml_id": str(text_obj.xml_id or "") if text_obj is not None else "",
                "name_candidates": name_candidates,
                "name_distance_basis": "RECTANGLE_MIN_EDGE_DISTANCE",
                "name_candidate_rule": "PURE_NUMERIC_WHITE_NO_BACKGROUND;TOP>RIGHT>GLOBAL;RECTANGLE_MIN_EDGE_DISTANCE;MAX_DISTANCE=300",
                "current_keyid1": str(attrs.get("keyid1") or "").strip(),
                "current_keyid2": str(attrs.get("keyid2") or "").strip(),
                "status": "",
                "severity": "",
                "reason": "",
            })

        return rows, {}

    def discover(self, parsed: ParsedG, element_catalog=None, name_settings=None):
        # Allocate names once for the complete set of Transformer_OH devices
        # in this G file.  The pool is intentionally limited to the requested
        # transformer devices: other modules must not reserve or consume a
        # transformer name, but two transformers must never share one Text.
        device_filter = lambda obj: self._is_transformer_object(
            obj,
            element_catalog,
        )
        global_name_owners = self.build_global_name_owners(
            parsed,
            element_catalog,
            name_settings,
            nearest_only=True,
            device_filter=device_filter,
            # Transformer recognition is independent from other modules, but
            # ownership is exclusive inside this target-device family.
            include_shared_devices=False,
            lock_text_ownership=True,
            max_text_distance=DEFAULT_DEVICE_TEXT_MAX_DISTANCE,
            allowed_directions=None,
            text_filter=self._is_white_name_text,
        )
        # Keep every geometrically valid white candidate in any direction as
        # well. The transformer module (and modules that explicitly reuse its
        # naming rule, such as FUSE) can then skip unrelated nearby labels that
        # do not uniquely resolve in 13505.
        all_name_candidates = self.build_global_name_owners(
            parsed,
            element_catalog,
            name_settings,
            nearest_only=True,
            device_filter=device_filter,
            include_shared_devices=False,
            lock_text_ownership=False,
            max_text_distance=DEFAULT_DEVICE_TEXT_MAX_DISTANCE,
            allowed_directions=None,
            text_filter=self._is_white_name_text,
        )
        rows = []
        for obj in parsed.objects:
            if not self._is_transformer_object(obj, element_catalog):
                continue

            label, _candidates = self.find_nearest_name(
                parsed,
                obj,
                "",
                (),
                global_name_owners,
            )
            attrs = obj.attrs
            name_candidates = []
            for _format_penalty, _color_penalty, distance, _xml_index, text, text_obj in all_name_candidates.get(obj.xml_index, []):
                name_candidates.append({
                    "text": text,
                    "distance": round(float(distance), 3),
                    "direction": self._direction(obj, text_obj),
                    "xml_id": str(text_obj.xml_id or ""),
                })
            rows.append({
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": str(attrs.get("devref") or "").strip(),
                "recognition_source": self._transformer_recognition_source(obj, element_catalog),
                "graphical_name": label.get("text", "") if label else "",
                "name_source": "NEAREST_GRAPHICAL_TEXT" if label else "",
                "name_distance": label.get("distance", "") if label else "",
                "name_direction": label.get("direction", "") if label else "",
                "name_xml_id": label.get("xml_id", "") if label else "",
                "name_candidates": name_candidates,
                "current_keyid1": str(attrs.get("keyid1") or "").strip(),
                "current_keyid2": str(attrs.get("keyid2") or "").strip(),
                "status": "",
                "severity": "",
                "reason": "",
            })

        return rows, {}


class TransformerModelModule(ModelModule):
    module_id = "TRANSFORMER"
    display_name = "柱上变压器模型"
    description = (
        "柱上变压器设备类型按两级规则识别：优先直接识别 devref 指向 Transformer_OH.pb.icn.g 的标准图元，"
        "无需依赖图元管理分类；未命中标准图元时，再以图元管理 TRANSFORMER_OH 分类标记作为兜底。"
        "识别完成后再全局收集纯数字、白色、无背景 Text；"
        "名称方向优先级固定为上方 → 右方 → 全局兜底，同级按距离最近，一对一且距离不超过 300；"
        "距离统一按柱上变压器矩形框与 Text 矩形框的最小边缘距离计算，方向也按矩形相对位置判断，不再使用中心点距离或 Text 锚点距离；"
        "图形距离分配完成后才用已分配名称查询 13505 / dms_tr_device，数据库不参与名称归属竞争，"
        "再计算双 KeyID 并安全回写。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "TRANSFORMER_OH_PRIMARY_THEN_CLASSIFICATION": {
                "table_id": TRANSFORMER_TABLE_ID,
                "domain": TRANSFORMER_DOMAIN,
                "match_mode": "PRIMARY_ELEMENT_FILE_THEN_TRANSFORMER_OH_CLASSIFICATION",
                "description": (
                    "设备类型识别优先检查 devref 是否精确指向 Transformer_OH.pb.icn.g；命中后直接视为柱上变压器，"
                    "不要求图元管理存在 TRANSFORMER_OH 标记；其它图元只有在图元管理被标记为 TRANSFORMER_OH 时才作为兜底进入柱上变压器模型。"
                    "识别完成后全局收集纯数字、白色且无背景的 Text；非纯数字、非白色或带背景 Text 直接排除；"
                    "方向优先级固定为上方 > 右方 > 全局兜底，距离上限 300；同一方向优先级内按距离最近；"
                    "距离按柱上变压器矩形框与 Text 矩形框的最小边缘距离计算，方向按矩形相对位置判断，并在全部目标变压器之间保持一对一 Text 归属；数据库不参与 Text 归属；"
                    "名称分配完成后再查询 13505 验证唯一目标；目标表为 13505，Domain=1"
                ),
            }
        }

    @staticmethod
    def _make_expected_keyid(device_id):
        device_id = int(device_id)
        if device_id < 0:
            raise ValueError(f"Invalid transformer device_id: {device_id}")
        return device_id + (TRANSFORMER_DOMAIN << 32)

    @staticmethod
    def _attributes_for_row(row):
        expected = str(row["expected_keyid"])
        # Existing linked pole-transformer objects use two parallel model slots.
        # Preserve that established write-back contract regardless of the
        # concrete XML tag; do not write unsuffixed attributes.
        return {
            "app1": "6500000",
            "app2": "6500000",
            "voltype1": "0",
            "voltype2": "0",
            "p_ReportType1": "1",
            "p_ReportType2": "1",
            "state1": "18",
            "state2": "18",
            "keyid1": expected,
            "keyid2": expected,
        }

    @staticmethod
    def _current_keyids(row):
        return [
            int_or_none(row.get("current_keyid1")),
            int_or_none(row.get("current_keyid2")),
        ]

    def _current_link_fields(self, row, db):
        keyid1 = str(row.get("current_keyid1") or "").strip()
        keyid2 = str(row.get("current_keyid2") or "").strip()
        row["current_keyid"] = keyid1 or keyid2
        current_keyid = int_or_none(row.get("current_keyid"))
        row["model_linked"] = "YES" if row.get("current_keyid") else "NO"
        if current_keyid is None:
            row["current_model_status"] = (
                "INVALID_KEYID" if row.get("current_keyid") else "UNLINKED"
            )
            return
        try:
            decoded = db.verify_keyid(current_keyid)
            row["current_device_id"] = int_or_none(decoded.get("device_id"))
            row["current_table_id"] = int_or_none(decoded.get("tab_no"))
            row["current_domain"] = int_or_none(decoded.get("col_no"))
            current_id = row.get("current_device_id")
            if current_id is not None:
                current = db.get_transformer_device_by_id(
                    TRANSFORMER_TABLE_ID,
                    current_id,
                )
                if current:
                    row["current_db_name"] = norm(current.get("name"))
                    row["current_db_code"] = norm(current.get("code"))
                    row["current_feeder_id"] = str(
                        current.get("feeder_id") or ""
                    ).strip()
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"
            return
        row["current_model_status"] = "DECODED"

    def _resolve_row(self, row, db):
        name = str(row.get("graphical_name") or "").strip()
        row.update({
            "selected_device_name": name,
            "feeder_resolution_source": "TRANSFORMER_DEVICE",
            "source_feeder_id": "",
            "source_feeder_name": "",
            "feeder_id": "",
            "feeder_name": "",
            "table_id": TRANSFORMER_TABLE_ID,
            "table_name": "dms_tr_device",
            "configured_domain": TRANSFORMER_DOMAIN,
            "db_match_count": 0,
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_feeder_id": "",
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
            return self._fail(
                row,
                "TRANSFORMER_NAME_NOT_FOUND: 未获得柱上变压器图元的可用 Text；候选 Text 可能已分配给更近的变压器，无法查询 13505 柱上变压器设备。",
            )

        records = db.get_transformer_devices_by_name(
            name,
            feeder_id=None,
            table_id=TRANSFORMER_TABLE_ID,
        )
        row["db_match_count"] = len(records)
        if len(records) != 1:
            return self._fail(
                row,
                "TRANSFORMER_DATABASE_NOT_UNIQUE: "
                f"dms_tr_device NAME={name}；匹配数={len(records)}。",
            )

        device = records[0]
        device_id = int_or_none(device.get("id"))
        if device_id is None:
            return self._fail(row, "TRANSFORMER_DEVICE_ID_INVALID: 13505.ID 无效。")
        expected = self._make_expected_keyid(device_id)
        row.update({
            "db_device_id": device_id,
            "db_code": norm(device.get("code")),
            "db_name": norm(device.get("name")),
            "db_feeder_id": str(device.get("feeder_id") or "").strip(),
            "expected_keyid": expected,
        })
        row["feeder_id"] = row["db_feeder_id"]
        row["source_feeder_id"] = row["db_feeder_id"]
        try:
            decoded = db.verify_keyid(expected)
            verified = (
                int_or_none(decoded.get("device_id")) == device_id
                and int_or_none(decoded.get("tab_no")) == TRANSFORMER_TABLE_ID
                and int_or_none(decoded.get("col_no")) == TRANSFORMER_DOMAIN
            )
        except Exception as exc:
            return self._fail(
                row,
                f"TRANSFORMER_EXPECTED_KEYID_VERIFY_ERROR: {exc}",
            )
        row["expected_keyid_verified"] = "YES" if verified else "NO"
        if not verified:
            return self._fail(
                row,
                "TRANSFORMER_EXPECTED_KEYID_VERIFY_FAILED: 13505/domain=1。",
            )

        current_keys = self._current_keyids(row)
        if current_keys[0] == expected and current_keys[1] == expected:
            row.update({
                "status": "PASS",
                "severity": "PASS",
                "model_link_correct": "YES",
                "model_link_status": "当前 keyid1/keyid2 均正确",
                "association_action": "无需回写",
                "writeback_needed": "NO",
                "association_ready": "YES",
                "reason": "TRANSFORMER_MODEL_LINK_CORRECT",
            })
        else:
            has_current = bool(row.get("current_keyid1") or row.get("current_keyid2"))
            row.update({
                "status": "RELINK" if has_current else "UNLINKED",
                "severity": "RELINK" if has_current else "WARN",
                "model_link_status": (
                    "当前 keyid1/keyid2 为空，尚未关联"
                    if not has_current
                    else "当前 keyid1/keyid2 不是目标 13505/domain=1"
                ),
                "association_action": "重新关联柱上变压器" if has_current else "关联柱上变压器",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "reason": "TRANSFORMER_ASSOCIATION_READY",
            })
        return row

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

    def _analyze_file(self, db, g_file, settings=None, log_callback=None, progress_callback=None):
        settings = settings or {}
        parsed = GParser().parse(g_file)
        feeder_resolution = resolve_drawing_feeder(
            db, parsed, settings, log_callback=log_callback
        )
        discovered, _context = TransformerParser().discover_for_transformer_model(
            parsed,
            settings.get("element_catalog", {}),
            settings,
        )
        rows = []
        total = max(len(discovered), 1)
        for index, row in enumerate(discovered, start=1):
            # IMPORTANT: the standalone pole-transformer model owns its names
            # by geometry only. discover_for_transformer_model() has already
            # considered all recognized pole-transformer devices plus the global pool of
            # pure-numeric, white, no-background Text objects, applied the
            # TOP -> RIGHT -> GLOBAL direction priority, measured rectangle-to-
            # rectangle minimum-edge distance, and performed one-to-one allocation
            # within the existing <= 300 limit. Do not let 13505 uniqueness
            # alter that ownership here.
            prepared = dict(row)
            if str(prepared.get("graphical_name") or "").strip():
                prepared["name_source"] = "JEDDAH_TOP_RIGHT_GLOBAL_NUMERIC_WHITE_NO_BACKGROUND"
            resolved = self._resolve_row(prepared, db)
            resolved["file_name"] = Path(g_file).name
            enforce_device_feeder_membership(
                resolved,
                feeder_resolution,
                device_feeder_id=resolved.get("db_feeder_id"),
                reason_prefix="TRANSFORMER",
            )
            rows.append(resolved)
            if log_callback:
                log_callback(
                    f"[发现柱上变压器] 文件={Path(g_file).name}；"
                    f"XML_ID={resolved.get('xml_id') or '-'}；"
                    f"名称={resolved.get('graphical_name') or '-'}；"
                    f"方向={resolved.get('name_direction') or '-'}；"
                    f"距离={resolved.get('name_distance') if resolved.get('name_distance') not in (None, '') else '-'}；"
                    f"DB_ID={resolved.get('db_device_id') or '-'}；"
                    f"FEEDER_ID={resolved.get('db_feeder_id') or '-'}；"
                    f"状态={resolved.get('status') or '-'}。"
                )
            if progress_callback:
                progress_callback(
                    index,
                    total,
                    f"正在处理柱上变压器 {index}/{len(discovered)}",
                )
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 柱上变压器识别完成："
                f"POLE_TRANSFORMER={len(discovered)}；"
                f"图级馈线={feeder_resolution.get('feeder_id') or '-'}；"
                f"数据库可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        feeder = feeder_resolution.get("feeder") or {}
        feeder_id = feeder_resolution.get("feeder_id", "")
        feeder_name = str(
            feeder.get("display_name")
            or feeder.get("name")
            or ""
        ).strip()
        candidate_ids = sorted({
            int_or_none(item.get("feeder_id"))
            for item in feeder_resolution.get("candidates", []) or []
            if int_or_none(item.get("feeder_id")) is not None
        })
        report = {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "TRANSFORMER",
            "transformer_rows": rows,
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
                "每个柱上变压器还必须证明自身数据库 FEEDER_ID 与图级馈线一致。"
                if feeder_resolution.get("ready")
                else feeder_resolution.get("reason", "图级馈线无法唯一确认。")
            ),
            "graph_feeder_ids": candidate_ids,
            "graph_feeder_count": len(candidate_ids),
            "summary": {
                "transformer_count": len(rows),
                "transformer_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "transformer_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "transformer_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "transformer_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES"),
                "feeder_context_ready": "YES" if feeder_resolution.get("ready") else "NO",
            },
        }
        return report

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
            db, files, settings, log_callback, progress_callback
        )
        changes_by_file = defaultdict(list)
        rows = []
        for report in reports:
            for row in report.get("transformer_rows", []):
                if row.get("association_ready") != "YES" or row.get("writeback_needed") != "YES":
                    continue
                change = {
                    "xml_id": row["xml_id"],
                    "tag": row.get("object_type") or TRANSFORMER_TAG_FALLBACK,
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
                    "PREVIEW_WRITE app1/app2=6500000 voltype1/voltype2=0 "
                    "p_ReportType1/p_ReportType2=1 state1/state2=18 "
                    f"keyid1/keyid2={row.get('expected_keyid', '')}"
                )
                rows.append(output_row)

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        summary = dict(summary)
        summary["association_change_count"] = sum(len(items) for items in changes_by_file.values())
        return {
            "reports": reports,
            "rows": rows,
            "summary": summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "transformer_table_id": TRANSFORMER_TABLE_ID,
                "transformer_domain": TRANSFORMER_DOMAIN,
                "element_catalog": settings.get("element_catalog", {}),
            },
        }

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        if not preview_data or not preview_data.get("changes_by_file"):
            raise RuntimeError("没有可执行的柱上变压器模型关联结果。")
        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        changes_by_file = preview_data.get("changes_by_file", {})
        execution_rows = []
        executable = defaultdict(list)
        selected_count = sum(len(items) for items in changes_by_file.values())
        source_map = {str(Path(item).resolve()): Path(item) for item in files}
        for source_file, fingerprint in (preview_data.get("file_fingerprints", {}) or {}).items():
            path = Path(source_file)
            stat = path.stat()
            if stat.st_size != fingerprint.get("size") or stat.st_mtime_ns != fingerprint.get("mtime_ns"):
                raise RuntimeError(f"G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验：{source_file}")

        for source_file, changes in changes_by_file.items():
            refreshed_report = self._analyze_file(
                db, Path(source_file), settings, log_callback
            )
            refreshed_by_xml = {
                str(row.get("xml_id") or ""): row
                for row in refreshed_report.get("transformer_rows", [])
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
                        current["reason"] = "TRANSFORMER_EXECUTION_TARGET_NOT_FOUND"
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
        write_results = []
        writer = GWriteBackService(log=log_callback)
        for source_file, changes in executable.items():
            if not changes:
                continue
            source = source_map.get(str(Path(source_file).resolve()), Path(source_file))
            target = output_dir / source.name
            if target.exists():
                stem, suffix, index = target.stem, target.suffix, 2
                while True:
                    candidate = output_dir / f"{stem}_{index}{suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1
            target.write_bytes(source.read_bytes())

            for change in changes:
                expected = str((change.get("attributes") or {}).get("keyid1") or "").strip()
                log_callback(
                    "[柱上变压器回写] "
                    f"XML ID={change.get('xml_id', '')}；"
                    f"Expected KeyID={expected}；输出={target}"
                )

            result = writer.apply_attribute_changes(target, changes, create_backup=False)
            actual_applied = int(result.get("applied_count", 0))
            if actual_applied != len(changes):
                raise RuntimeError(
                    "柱上变压器 G 文件回写数量异常："
                    f"计划={len(changes)}，实际={actual_applied}，文件={target}"
                )

            # Hard post-write verification: a successful association is not
            # accepted until keyid1/keyid2 can be read back from the output G.
            # This catches any silent write-path regression immediately.
            verified = writer.verify_attribute_changes(
                target,
                changes,
                required_attributes=("keyid1", "keyid2"),
            )
            if not verified.get("ok"):
                detail = "; ".join(verified.get("errors", []) or [])
                raise RuntimeError(
                    "柱上变压器 KeyID 回写后复核失败："
                    f"{detail or target}"
                )

            for change in changes:
                expected = str((change.get("attributes") or {}).get("keyid1") or "").strip()
                log_callback(
                    "[柱上变压器回写确认] "
                    f"XML ID={change.get('xml_id', '')}；"
                    f"keyid1/keyid2={expected}；已从输出 G 复核成功"
                )

            result = dict(result)
            result["source_g_file"] = str(source)
            result["output_g_file"] = str(target)
            write_results.append(result)
            applied += actual_applied
            copied_files.append(str(target))

        if selected_count > 0 and applied == 0:
            skipped_reasons = []
            for _change, row in execution_rows:
                if row.get("_execution_result") == "SKIPPED":
                    skipped_reasons.append(
                        f"XML ID={row.get('xml_id', '')}: {row.get('reason', 'EXECUTION_SKIPPED')}"
                    )
            raise RuntimeError(
                "已选择柱上变压器，但没有任何对象实际写入 G 文件。"
                + ((" 原因：" + "; ".join(skipped_reasons)) if skipped_reasons else "")
            )

        operation_reports = []
        by_file = defaultdict(list)
        for change, row in execution_rows:
            item = dict(row)
            item["status"] = "PASS" if row.get("_execution_result") == "READY" else "FAIL"
            item["severity"] = item["status"]
            item["reason"] = "ASSOCIATION_EXECUTED" if item["status"] == "PASS" else item.get("reason", "EXECUTION_SKIPPED")
            by_file[str(change.get("_source_file") or "")].append(item)
        for source_file, rows in by_file.items():
            operation_reports.append({
                "g_file": source_file,
                "file_name": Path(source_file).name,
                "report_type": "TRANSFORMER",
                "transformer_rows": rows,
                "summary": {"transformer_count": len(rows)},
            })
        return {
            "selected_count": selected_count,
            "applied_count": applied,
            "skipped_count": max(selected_count - applied, 0),
            "output_g_dir": str(output_dir),
            "copied_files": copied_files,
            "results": write_results,
            "operation_reports": operation_reports,
            "rules": self._rules(),
        }
