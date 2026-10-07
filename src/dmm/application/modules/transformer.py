from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.domain.gfile.parser import GParser, GObject, ParsedG
from dmm.domain.gfile.element_catalog import devref_matches_file
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService
from dmm.application.modules.pole_switch import (
    DEFAULT_DEVICE_TEXT_MAX_DISTANCE,
    POLE_SWITCH_NAME_RE,
    PoleSwitchParser,
    _normalized_transformer_element_files,
)


TRANSFORMER_TABLE_ID = 13505
TRANSFORMER_DOMAIN = 1
TRANSFORMER_TAG_FALLBACK = "TransformerDis"
TRANSFORMER_MODEL_TEXT_MAX_DISTANCE = 200.0
# Kept as a compatibility alias for older callers/tests. Runtime recognition
# now uses the operator-maintained ``transformer_element_files`` list only.
TRANSFORMER_DIRECT_ELEMENT_FILE = "Transformer_OH.pb.icn.g"


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
    """Recognize direct Transformer_OH.pb.icn.g first, then catalog fallback."""

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
        """Makkah Transformer_OH name candidate.

        Names are not restricted by color, background, pure-numeric style, or
        alphanumeric composition.  Reuse the shared Makkah Text-noise filter:
        obvious non-name annotations and pure decimal numeric values are
        excluded, while integer/alphabetic/alphanumeric labels remain eligible.
        """
        return cls._global_text_is_nameable(obj)

    @staticmethod
    def _transformer_model_anchor_direction(device: GObject, text_obj: GObject) -> str:
        """Classify TOP/RIGHT/GLOBAL from rectangle-edge relation only."""
        if text_obj.box.bottom <= device.box.top:
            return "top"
        if text_obj.box.left >= device.box.right:
            return "right"
        if text_obj.box.top >= device.box.bottom:
            return "bottom"
        if text_obj.box.right <= device.box.left:
            return "left"
        return "near"

    @classmethod
    def _transformer_model_direction_priority(cls, device: GObject, text_obj: GObject) -> int:
        """Jeddah priority: top first, then right, then global fallback."""
        direction = cls._transformer_model_anchor_direction(device, text_obj)
        if direction == "top":
            return 0
        if direction == "right":
            return 1
        return 2

    @staticmethod
    def _transformer_model_priority_label(priority: int) -> str:
        return {0: "TOP", 1: "RIGHT", 2: "GLOBAL"}.get(int(priority), "GLOBAL")

    @classmethod
    def _transformer_recognition_source(
        cls,
        obj: GObject,
        element_catalog=None,
        name_settings=None,
    ) -> str:
        """Return configured devref recognition source for one pole transformer.

        Makkah no longer consults Element Management classifications. Exact
        file basenames in ``transformer_element_files`` are the sole identity
        source.
        """
        del element_catalog
        devref = str(obj.attrs.get("devref") or "")
        for file_name in _normalized_transformer_element_files(name_settings):
            if devref_matches_file(devref, file_name):
                return "CONFIGURED_ELEMENT_FILE"
        return ""

    @classmethod
    def _is_transformer_object(
        cls,
        obj: GObject,
        element_catalog=None,
        name_settings=None,
    ) -> bool:
        return bool(
            cls._transformer_recognition_source(
                obj,
                element_catalog,
                name_settings,
            )
        )

    @staticmethod
    def _transformer_model_text_anchor_distance(device: GObject, text_obj: GObject) -> float:
        """Shortest rectangle-edge distance used by the Makkah model.

        The historical function name is kept for compatibility, but center
        points and Text.x/Text.y anchors are no longer used.
        """
        return device.box.edge_distance(text_obj.box)

    def discover_with_center_anchor_names(
        self,
        parsed: ParsedG,
        element_catalog=None,
        name_settings=None,
    ):
        """Transformer_OH name allocation using rectangle minimum-edge distance.

        Legacy compatibility rule retained for callers that still need the
        pre-v4.1.67 any-direction nearest-white-Text behavior.  FUSE no longer
        uses this path; it now calls discover_for_transformer_model() so its
        selected Transformer_OH follows the same Jeddah TOP -> RIGHT -> GLOBAL
        naming rule as the standalone transformer model.

        Legacy behavior:
        1. collect every Transformer_OH in the drawing;
        2. collect eligible white Text objects globally, with no direction rule;
        3. create candidates within the existing 200-unit limit using
           Transformer rectangle -> Text rectangle minimum-edge distance;
        4. allocate Text one-to-one by global nearest distance;
        5. database validation is performed later and never changes ownership.

        This method remains deliberately separate for backward-compatible
        internal callers; it is not used by the current FUSE model.
        """
        devices = [
            obj
            for obj in parsed.objects
            if self._is_transformer_object(obj, element_catalog, name_settings)
        ]
        texts = [
            obj
            for obj in parsed.objects
            if self._global_text_is_nameable(obj)
        ]

        ranked = {}
        candidate_pairs = []
        for device in devices:
            items = []
            for text_obj in texts:
                distance = self._transformer_model_text_anchor_distance(
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
                "recognition_source": self._transformer_recognition_source(obj, element_catalog, name_settings),
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
        """Discover Makkah pole transformers with global nearest Text ownership.

        Rules:
        1. collect every Transformer_OH in the current G drawing;
        2. collect all broadly valid Text objects globally; color/background and
           letter/digit format are not restrictions, while pure decimals are excluded;
        3. use rectangle-to-rectangle minimum-edge distance only, max 200;
        4. sort every device/Text pair globally by physical distance;
        5. each device may receive one Text and each Text XML object may be consumed
           only once. Once a Text is assigned it never re-enters the candidate pool.
        """
        devices = [
            obj
            for obj in parsed.objects
            if self._is_transformer_object(obj, element_catalog, name_settings)
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
                distance = self._transformer_model_text_anchor_distance(device, text_obj)
                if distance > float(TRANSFORMER_MODEL_TEXT_MAX_DISTANCE):
                    continue
                direction = self._transformer_model_anchor_direction(device, text_obj)
                item = {
                    "priority": 0,
                    "priority_label": "GLOBAL",
                    "distance": float(distance),
                    "text_order": int(text_obj.xml_index),
                    "device_order": int(device.xml_index),
                    "text": self._text_value(text_obj),
                    "text_obj": text_obj,
                    "direction": direction,
                }
                items.append(item)
                candidate_pairs.append(item)
            items.sort(key=lambda item: (item["distance"], item["text_order"]))
            ranked[device.xml_index] = items

        # Global greedy nearest one-to-one allocation. A consumed Text ID is
        # permanently removed from the current model run and cannot be reused.
        candidate_pairs.sort(key=lambda item: (
            item["distance"],
            item["text_order"],
            item["device_order"],
        ))
        assigned_by_device = {}
        assigned_text_ids = set()
        for item in candidate_pairs:
            device_id = item["device_order"]
            text_id = item["text_order"]
            if device_id in assigned_by_device or text_id in assigned_text_ids:
                continue
            assigned_by_device[device_id] = item
            assigned_text_ids.add(text_id)

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
                    "priority": "GLOBAL",
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
                "recognition_source": self._transformer_recognition_source(obj, element_catalog, name_settings),
                "graphical_name": selected.get("text", "") if selected else "",
                "name_source": "MAKKAH_GLOBAL_NEAREST_TEXT" if selected else "",
                "name_distance": round(float(selected["distance"]), 3) if selected else "",
                "name_direction": selected.get("direction", "") if selected else "",
                "name_priority": "GLOBAL" if selected else "",
                "name_xml_id": str(text_obj.xml_id or "") if text_obj else "",
                "name_candidates": name_candidates,
                "name_distance_basis": "RECTANGLE_MIN_EDGE_DISTANCE",
                "name_candidate_rule": "GLOBAL_NEAREST;TEXT_ID_ONE_TO_ONE;PURE_DECIMAL_EXCLUDED;RECTANGLE_MIN_EDGE_DISTANCE;MAX_DISTANCE=200",
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
            name_settings,
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
            text_filter=None,
            direction_priority=None,
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
            text_filter=None,
            direction_priority=None,
        )
        rows = []
        for obj in parsed.objects:
            if not self._is_transformer_object(obj, element_catalog, name_settings):
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
                "recognition_source": self._transformer_recognition_source(obj, element_catalog, name_settings),
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
        "麦加柱上变压器只识别用户维护的精确 devref 图元文件名单；名称不限制颜色、背景、纯数字或字母数字格式，"
        "整张 G 图按矩形最小边缘距离做全局最近 Text 匹配，"
        "最大距离 200，纯小数 Text 直接排除，Text 全局一对一。"
        "数据库只按 13505.NAME 唯一匹配，不判断 FEEDER_ID；唯一后直接按 Domain=1 计算并回写 KeyID。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "CONFIGURED_TRANSFORMER_ELEMENT_FILES": {
                "table_id": TRANSFORMER_TABLE_ID,
                "domain": TRANSFORMER_DOMAIN,
                "match_mode": "MAKKAH_CONFIGURED_DEVREF_GLOBAL_TEXT_NAME_ONLY_NO_FEEDER",
                "description": (
                    "只识别用户维护的精确 devref 图元文件名单；名称不限制颜色、背景或字母数字格式，"
                    "矩形最小边缘距离最大200，全局一对一且已分配 Text 不再参与后续设备计算，纯小数排除。数据库只按13505.NAME唯一匹配，"
                    "不解析、不要求、不校验FEEDER_ID。"
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
        # Existing linked TransformerDis objects in the supplied G files use
        # two parallel model slots. Preserve that established write-back
        # contract; do not write unsuffixed TransformerDis attributes.
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
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"
            return
        row["current_model_status"] = "DECODED"

    def _resolve_row(self, row, db):
        name = str(row.get("graphical_name") or "").strip()
        row.update({
            "selected_device_name": name,
            "table_id": TRANSFORMER_TABLE_ID,
            "table_name": "dms_tr_device",
            "configured_domain": TRANSFORMER_DOMAIN,
            "db_match_count": 0,
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
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
                "TRANSFORMER_NAME_NOT_FOUND: 未找到 Transformer_OH 图元对应的最近 Text。",
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
            "expected_keyid": expected,
        })
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

    @staticmethod
    def _log_found_device(log_callback, index, row):
        """Write every discovered overhead-transformer device to the console."""
        if not log_callback:
            return
        name = str(row.get("selected_device_name") or row.get("graphical_name") or "").strip() or "<未找到名称>"
        xml_id = str(row.get("xml_id") or "").strip() or "-"
        text_id = str(row.get("name_xml_id") or "").strip() or "-"
        distance = row.get("name_distance", "")
        distance_text = str(distance).strip() if distance not in (None, "") else "-"
        db_id = str(row.get("db_device_id") or "").strip() or "-"
        status = str(row.get("status") or "").strip() or "-"
        ready = str(row.get("association_ready") or "NO").strip() or "NO"
        reason = str(row.get("reason") or "").strip() or "-"
        log_callback(
            f"[柱上变压器][找到设备] #{index} 名称={name}；"
            f"XML_ID={xml_id}；Text_ID={text_id}；距离={distance_text}；"
            f"DB_ID={db_id}；状态={status}；可关联={ready}；原因={reason}"
        )

    def _analyze_file(self, db, g_file, settings=None, log_callback=None, progress_callback=None):
        parsed = GParser().parse(g_file)
        discovered, _context = TransformerParser().discover_for_transformer_model(
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
                progress_callback(
                    index,
                    total,
                    f"正在处理柱上变压器 {index}/{len(discovered)}",
                )
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 柱上变压器识别完成："
                f"configured_transformers={len(discovered)}；"
                f"名称唯一可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "TRANSFORMER",
            "transformer_rows": rows,
            "summary": {
                "transformer_count": len(rows),
                "transformer_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "transformer_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "transformer_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "transformer_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
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
                "transformer_element_files": list(
                    settings.get("transformer_element_files")
                    or _normalized_transformer_element_files(settings)
                ),
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
            for change in changes:
                base = dict(change.get("validated_row", {}) or {})
                current = self._resolve_row(dict(base), db)
                if current.get("association_ready") != "YES" or current.get("writeback_needed") != "YES":
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
                stem, suffix, index = target.stem, target.suffix, 2
                while True:
                    candidate = output_dir / f"{stem}_{index}{suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1
            target.write_bytes(source.read_bytes())
            result = writer.apply_attribute_changes(target, changes, create_backup=False)
            applied += int(result.get("applied_count", 0))
            copied_files.append(str(target))

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
            "operation_reports": operation_reports,
            "rules": self._rules(),
        }
