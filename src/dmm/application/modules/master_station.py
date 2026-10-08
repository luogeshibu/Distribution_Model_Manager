from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.application.modules.feeder_context import (
    add_feeder_fields,
    candidate_from_record,
    enforce_device_feeder_membership,
    resolve_drawing_feeder,
)
from dmm.application.modules.jeddah_scope import (
    assess_jeddah_drawing_scope,
    apply_jeddah_scope_block,
    scope_report_fields,
)
from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES
from dmm.domain.gfile.parser import GParser
from dmm.domain.rmu.validator import int_or_none
from dmm.infrastructure.gfile.writeback import GWriteBackService


KEYID_STEP = 1 << 32
TARGET_TAGS = ("CBreaker", "Disconnector", "GroundDisconnector")
MASTER_STATION_WRITE_ATTRIBUTES = frozenset(
    {"app", "voltype", "p_ReportType", "state", "keyid"}
)
RMU_ANCHOR_TAGS = {
    "CBreakerDis", "BusDis", "ZhaiWaiJieDiDaoZha", "pwbh",
}


def _object_identity(obj):
    return str(obj.xml_id or f"{obj.tag}:{obj.xml_index}").strip()


def _connect_line_node_ids(obj):
    """Return object IDs referenced by a ConnectLine node_area/link value."""
    values = []
    for key in ("node_area", "link"):
        raw = str(obj.attrs.get(key) or "")
        values.extend(re.findall(r"(?:^|;)\s*\d+\s*,\s*\d+\s*,\s*([^;]+)", raw))
    return {str(value).strip() for value in values if str(value).strip()}


def _record_assignment_order(record):
    """Order already BAY_ID-filtered DB rows by NAME suffix only.

    The prefix (for example ``D331``) is intentionally ignored.  The only
    database naming markers used for the three-way disconnector layout are
    ``_1``, ``_2`` and ``_T``.  No G-file name and no database CODE is used.
    """
    value = str(record.get("name") or "").strip().upper()
    if re.search(r"_1$", value):
        priority = 0
    elif re.search(r"_2$", value):
        priority = 1
    elif re.search(r"_T$", value):
        priority = 2
    else:
        priority = 3
    return priority, int_or_none(record.get("id")) or 0


def _record_name_marker(record):
    value = str(record.get("name") or "").strip().upper()
    match = re.search(r"_(1|2|T)$", value)
    return match.group(1) if match else ""


class MasterStationModelModule(ModelModule):
    module_id = "MASTER_STATION"
    display_name = "配网主站设备关联"
    description = (
        "主站设备所属厂站/馈线只由 G 文件名唯一确定：文件名 → 405/substation → "
        "13500/dms_feeder_device；再由该馈线在 406/Bay 中定位唯一 BAY_ID，并按原有规则关联 "
        "407/408/409。主站图元本身不解析可见 CODE/NAME，仅对多个 Disconnector 做 Bus 侧左右顺序判定。"
    )
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    @staticmethod
    def _rules(settings=None):
        saved = (settings or {}).get("master_station_rules", {}) or {}
        result = {}
        for tag, default in DEFAULT_MASTER_STATION_RULES.items():
            item = dict(default)
            item.update(saved.get(tag, {}) or {})
            result[tag] = item
        return result

    @classmethod
    def _attributes_for_row(cls, row):
        bv_id = str(row.get("db_bv_id") or "").strip()
        if not bv_id:
            raise ValueError(
                f"{row.get('object_type')}:{row.get('xml_id')}: "
                "目标数据库 BV_ID 为空，禁止生成主站设备模型回写。"
            )
        state = {
            "CBreaker": "41",
            "Disconnector": "31",
            "GroundDisconnector": "31",
        }.get(str(row.get("object_type") or ""), "41")
        return {
            "app": "100000",
            "voltype": bv_id,
            "p_ReportType": "1",
            "state": state,
            "keyid": str(row["expected_keyid"]),
        }

    @staticmethod
    def _expected_keyid(device_id, domain):
        device_id = int(device_id)
        domain = int(domain)
        if device_id < 0 or domain < 0:
            raise ValueError("主站设备 ID 或域号无效")
        return device_id + domain * KEYID_STEP

    @staticmethod
    def _current_link(row, db):
        current_keyid = int_or_none(row.get("current_keyid"))
        if current_keyid is None:
            row.update({
                "model_linked": "YES" if row.get("current_keyid") else "NO",
                "current_model_status": "INVALID_KEYID" if row.get("current_keyid") else "UNLINKED",
            })
            return
        row["model_linked"] = "YES"
        try:
            decoded = db.verify_keyid(current_keyid)
            row["current_device_id"] = int_or_none(decoded.get("device_id"))
            row["current_table_id"] = int_or_none(decoded.get("tab_no"))
            row["current_domain"] = int_or_none(decoded.get("col_no"))
            if row.get("current_device_id") is not None and row.get("current_table_id") is not None:
                raw_reader = getattr(db, "get_raw_device_by_id", None)
                current = (
                    raw_reader(row["current_table_id"], row["current_device_id"])
                    if raw_reader
                    else db.get_device_by_id(row["current_table_id"], row["current_device_id"])
                )
                if current:
                    row["current_db_code"] = str(current.get("code") or "").strip()
                    row["current_db_name"] = str(current.get("name") or "").strip()
            row["current_model_status"] = "DECODED"
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"

    @staticmethod
    def _context_from_keyid(db, keyid):
        """Resolve one existing model link into station/feeder context."""
        parsed_keyid = int_or_none(keyid)
        if parsed_keyid is None:
            return None, "KeyID 为空或不是数字"
        try:
            decoded = db.verify_keyid(parsed_keyid)
            table_id = int_or_none(decoded.get("tab_no"))
            device_id = int_or_none(decoded.get("device_id"))
            domain = int_or_none(decoded.get("col_no"))
            if table_id is None or device_id is None:
                return None, "KeyID 无法反解出表号和设备 ID"
            raw_reader = getattr(db, "get_raw_device_by_id", None)
            row = (
                raw_reader(table_id, device_id)
                if raw_reader
                else db.get_device_by_id(table_id, device_id)
            )
            if not row:
                return None, f"表 {table_id} 中找不到设备 {device_id}"

            bay_id = int_or_none(row.get("bay_id"))
            source = f"KeyID 反解：表 {table_id} / 设备 {device_id}"

            # RMU 上下文必须直接落到 13501 dms_combined_device：
            # 内部设备/保护信号只提供 COMBINED_ID，RMU 的 FEEDER_ID 才是
            # 厂站/馈线判定依据。禁止再用整图设备、Bay 模糊匹配兜底。
            rmu = None
            rmu_id = ""
            if table_id == 13501:
                rmu = row
                rmu_id = device_id
            else:
                combined_id = int_or_none(row.get("combined_id"))
                if combined_id is None:
                    return None, (
                        f"表 {table_id} / 设备 {device_id} 没有 COMBINED_ID，"
                        "无法直接定位 13501 环网柜"
                    )
                if not hasattr(db, "get_rmu_by_id"):
                    return None, "数据库连接不支持直接查询 13501 环网柜"
                rmu = db.get_rmu_by_id(combined_id) or {}
                if not rmu:
                    return None, f"13501 环网柜 {combined_id} 不存在或无法读取"
                rmu_id = int_or_none(rmu.get("id")) or combined_id
            source += f" → 13501 dms_combined_device.ID={rmu_id}"

            feeder_id = int_or_none(rmu.get("feeder_id"))
            if feeder_id is None:
                return None, f"13501 环网柜 {rmu_id} 的 FEEDER_ID 为空，无法确定厂站和馈线"
            if not hasattr(db, "get_feeder_info"):
                return None, "数据库连接不支持按 FEEDER_ID 查询馈线"
            feeder = db.get_feeder_info(feeder_id) or {}
            if not feeder:
                return None, f"馈线 {feeder_id} 不存在或无法读取"

            station_id = int_or_none(feeder.get("st_id"))
            station = None
            if station_id is not None and hasattr(db, "get_station_info"):
                station = db.get_station_info(station_id) or {}
            bay = None
            if bay_id is not None and hasattr(db, "get_bay_by_id"):
                bay = db.get_bay_by_id(bay_id) or {}
            if bay_id is None and station_id is not None and hasattr(db, "find_bays_by_feeder"):
                feeder_hint = str(
                    feeder.get("code") or feeder.get("name") or feeder.get("graph_name") or ""
                ).strip()
                bay_rows = db.find_bays_by_feeder(feeder_hint, station_id)
                if len(bay_rows) == 1:
                    bay = bay_rows[0]
                    bay_id = int_or_none(bay.get("id"))
                elif len(bay_rows) > 1:
                    return None, (
                        f"馈线 {feeder_id} 在厂站 {station_id} 下对应多个 BAY_ID，"
                        "无法安全确定间隔。"
                    )
            return {
                "source": source,
                "source_keyid": parsed_keyid,
                "source_table_id": table_id,
                "source_device_id": device_id,
                "source_domain": domain or "",
                "rmu_id": rmu_id,
                "rmu_name": str((rmu or {}).get("name") or "").strip(),
                "bay_id": bay_id or "",
                "bay_code": str((bay or {}).get("code") or "").strip(),
                "bay_name": str((bay or {}).get("name") or "").strip(),
                "station_id": station_id or "",
                "station_name": str((station or {}).get("name") or "").strip(),
                "feeder_id": feeder_id,
                "feeder_code": str(feeder.get("code") or "").strip(),
                "feeder_name": str(
                    feeder.get("display_name") or feeder.get("name") or ""
                ).strip(),
            }, ""
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _distance_to_box(obj, frame):
        """Distance from an object's center to an RMU rectangle."""
        box = frame.frame.box if hasattr(frame, "frame") else frame.box
        x, y = obj.box.cx, obj.box.cy
        dx = max(box.left - x, 0.0, x - box.right)
        dy = max(box.top - y, 0.0, y - box.bottom)
        return math.hypot(dx, dy)

    @staticmethod
    def _distance_between_objects(left, right):
        return math.hypot(left.box.cx - right.box.cx, left.box.cy - right.box.cy)

    @classmethod
    def _nearest_rmu_frame(cls, breaker, frames):
        if not frames:
            return None
        return min(
            frames,
            key=lambda frame: (
                cls._distance_to_box(breaker, frame),
                frame.frame.box.area,
                frame.frame.xml_index,
            ),
        )

    @classmethod
    def _resolve_rmu_context(cls, parsed, frame, db, cache):
        """Resolve context using only associations inside one RMU frame."""
        cache_key = frame.frame.xml_index
        if cache_key in cache:
            return cache[cache_key]

        anchors = [
            obj for obj in parsed.objects
            if obj.tag in RMU_ANCHOR_TAGS
            and frame.frame.box.center_contains(obj.box, tolerance=1.0)
        ]
        failures = []
        seen = set()
        for obj in anchors:
            for key in ("keyid", "keyid1", "keyid2"):
                value = str(obj.attrs.get(key) or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                context, error = cls._context_from_keyid(db, value)
                if context:
                    context.update({
                        "rmu_frame_xml_id": frame.frame.xml_id,
                        "rmu_frame_xml_index": frame.frame.xml_index,
                        "context_anchor_type": obj.tag,
                        "context_anchor_xml_id": obj.xml_id,
                        "context_anchor_keyid": value,
                    })
                    cache[cache_key] = (context, "", {
                        "rmu_frame_xml_id": frame.frame.xml_id,
                        "rmu_id": context.get("rmu_id", ""),
                        "rmu_name": context.get("rmu_name", ""),
                        "context_anchor_type": obj.tag,
                        "context_anchor_xml_id": obj.xml_id,
                        "context_anchor_keyid": value,
                    })
                    return cache[cache_key]
                if error:
                    failures.append(f"{obj.tag}:{error}")

        detail = failures[0] if failures else "框内没有 CBreakerDis、BusDis、接地刀闸或 pwbh 的有效 KeyID"
        result = (
            None,
            "MASTER_STATION_RMU_ASSOCIATION_REQUIRED: "
            f"最近环网柜（矩形框 XML ID={frame.frame.xml_id or '-'}）内部没有可反查的已关联设备或保护信号；"
            f"{detail}。请手动关联该环网柜或其内部设备/保护信号。",
            {
                "rmu_frame_xml_id": frame.frame.xml_id,
                "rmu_id": "",
                "rmu_name": "",
                "context_anchor_type": "",
                "context_anchor_xml_id": "",
                "context_anchor_keyid": "",
            },
        )
        cache[cache_key] = result
        return result

    @classmethod
    def _resolve_local_context(cls, parsed, obj, breakers, frames, db, cache):
        """Map a target to its nearest breaker and then to that breaker's RMU."""
        if not frames:
            return None, (
                "MASTER_STATION_RMU_NOT_FOUND: G 文件未找到符合条件的环网柜矩形框；"
                "该图环网柜请手动关联。"
            ), {}
        if not breakers:
            return None, (
                "MASTER_STATION_CBREAKER_NOT_FOUND: G 文件没有断路器锚点，"
                "无法确定最近环网柜；该图环网柜请手动关联。"
            ), {}

        breaker = obj if obj.tag == "CBreaker" else min(
            breakers,
            key=lambda candidate: cls._distance_between_objects(obj, candidate),
        )
        frame = cls._nearest_rmu_frame(breaker, frames)
        if frame is None:
            return None, "MASTER_STATION_RMU_NOT_FOUND: 未找到断路器对应的最近环网柜；该图环网柜请手动关联。", {}
        return cls._resolve_rmu_context(parsed, frame, db, cache)

    @staticmethod
    def _context_from_filename_feeder(db, feeder_resolution):
        """Build the master-station Bay context from the filename feeder only.

        Jeddah production rule: the drawing feeder has already been resolved by
        ``resolve_drawing_feeder`` using filename -> 405 -> 13500.  The
        master-station module must not inspect an RMU, an existing RMU KeyID,
        or any other graphical device to decide the feeder.  The remaining
        legacy Bay/device association is preserved: use the resolved feeder's
        station and business feeder name/code to locate exactly one 406/Bay.
        """
        resolution = feeder_resolution or {}
        if not resolution.get("ready"):
            return None, (
                resolution.get("reason")
                or "MASTER_STATION_GRAPH_FEEDER_NOT_RESOLVED: 无法按文件名唯一确定图级馈线。"
            ), {}

        feeder = dict(resolution.get("feeder") or {})
        feeder_id = int_or_none(resolution.get("feeder_id"))
        station_id = int_or_none(feeder.get("st_id"))
        if feeder_id is None:
            return None, "MASTER_STATION_FEEDER_ID_EMPTY: 文件名解析出的图级 FEEDER_ID 为空。", {}
        if station_id is None:
            return None, (
                "MASTER_STATION_STATION_ID_EMPTY: 文件名解析出的 13500 馈线 ST_ID 为空，"
                "无法定位 406/Bay。"
            ), {}
        if not hasattr(db, "find_bays_by_feeder"):
            return None, "MASTER_STATION_BAY_API_MISSING: 数据库连接不支持按馈线定位 406/Bay。", {}

        # The filename resolver already calculated the authoritative business
        # feeder NAME (for example AH323 or AG406). Prefer that exact name;
        # retain the existing 13500 CODE/NAME/GRAPH_NAME fallback only for
        # compatibility with older rows whose returned representation differs.
        hints = []
        for item in resolution.get("candidates") or []:
            if str(item.get("kind") or "").upper() == "FILENAME":
                value = str(item.get("name") or "").strip()
                if value:
                    hints.append(value)
        for key in ("code", "name", "graph_name"):
            value = str(feeder.get(key) or "").strip()
            if value:
                hints.append(value)
        hints = list(dict.fromkeys(hints))
        if not hints:
            return None, (
                "MASTER_STATION_FEEDER_NAME_EMPTY: 文件名已确定 FEEDER_ID，"
                "但没有可用于定位 406/Bay 的馈线名称/代码。"
            ), {}

        matched_hint = ""
        bays = []
        for hint in hints:
            try:
                rows = db.find_bays_by_feeder(hint, station_id) or []
            except Exception as exc:
                return None, f"MASTER_STATION_BAY_QUERY_FAILED: 406/Bay 查询失败：{exc}", {}
            if rows:
                matched_hint = hint
                bays = rows
                break

        if len(bays) == 0:
            return None, (
                "MASTER_STATION_BAY_NOT_FOUND: "
                f"文件名已确定 FEEDER_ID={feeder_id} / ST_ID={station_id}，"
                f"但 406/Bay 未找到馈线 {hints[0]} 对应的间隔。"
            ), {}
        if len(bays) > 1:
            return None, (
                "MASTER_STATION_BAY_NOT_UNIQUE: "
                f"文件名已确定 FEEDER_ID={feeder_id} / ST_ID={station_id}，"
                f"但 406/Bay 对馈线 {matched_hint or hints[0]} 匹配 {len(bays)} 条；"
                "无法安全确定 BAY_ID。"
            ), {}

        bay = dict(bays[0])
        bay_id = int_or_none(bay.get("id"))
        if bay_id is None:
            return None, "MASTER_STATION_BAY_ID_EMPTY: 唯一 406/Bay 记录 ID 为空。", {}

        station = {}
        if hasattr(db, "get_station_info"):
            try:
                station = db.get_station_info(station_id) or {}
            except Exception:
                station = {}
        station_name = str(
            feeder.get("station_name") or station.get("name") or ""
        ).strip()
        context = {
            "source": (
                f"{resolution.get('feeder_source') or 'FILENAME_405_13500'}"
                f" -> 406/Bay({matched_hint or hints[0]})"
            ),
            "source_keyid": "",
            "source_table_id": "",
            "source_device_id": "",
            "source_domain": "",
            "rmu_id": "",
            "rmu_name": "",
            "bay_id": bay_id,
            "bay_code": str(bay.get("code") or "").strip(),
            "bay_name": str(bay.get("name") or "").strip(),
            "station_id": station_id,
            "station_name": station_name,
            "feeder_id": feeder_id,
            "feeder_code": str(feeder.get("code") or "").strip(),
            "feeder_name": str(
                feeder.get("display_name") or feeder.get("name") or matched_hint or hints[0]
            ).strip(),
            "filename_feeder_name": hints[0],
        }
        meta = {
            "rmu_frame_xml_id": "",
            "rmu_id": "",
            "rmu_name": "",
            "context_anchor_type": "FILENAME_FEEDER",
            "context_anchor_xml_id": "",
            "context_anchor_keyid": "",
        }
        return context, "", meta

    @staticmethod
    def _record_matches_context(record, context, db=None):
        if not context:
            return False
        context_feeder = int_or_none(context.get("feeder_id"))
        record_feeder = int_or_none(record.get("feeder_id"))
        if context_feeder is not None and record_feeder is not None:
            return context_feeder == record_feeder

        # 407/408/409 expose BAY_ID instead of FEEDER_ID.  Resolve the
        # candidate Bay using the same database relation used for the anchor.
        record_bay = int_or_none(record.get("bay_id"))
        if context_feeder is not None and record_bay is not None and db is not None:
            try:
                bay = db.get_bay_by_id(record_bay) or {}
                hint = str(
                    bay.get("code") or bay.get("graph_name") or bay.get("name") or ""
                ).strip()
                station_id = int_or_none(bay.get("st_id"))
                candidates = db.find_feeders_by_bay(hint, station_id)
                if len(candidates) == 1:
                    return int_or_none(candidates[0].get("id")) == context_feeder
            except Exception:
                pass
        # A station-only match is not enough: one station may own multiple
        # feeders.  Feeder ownership must be proven explicitly.
        return False

    @classmethod
    def _ordered_disconnectors(cls, parsed, disconnectors):
        """Order disconnectors as left Bus-side, right Bus-side, remaining."""
        buses = [obj for obj in parsed.objects if obj.tag == "Bus"]
        if not buses:
            return sorted(
                disconnectors,
                key=lambda obj: (obj.box.x, obj.box.y, obj.xml_index),
            )

        direct = []
        for obj in disconnectors:
            best_distance = None
            obj_id = _object_identity(obj)
            for line in parsed.objects:
                if line.tag != "ConnectLine":
                    continue
                node_ids = _connect_line_node_ids(line)
                if obj_id not in node_ids:
                    continue
                for bus in buses:
                    if _object_identity(bus) in node_ids:
                        distance = cls._distance_to_box(obj, bus)
                        best_distance = (
                            distance if best_distance is None
                            else min(best_distance, distance)
                        )
            if best_distance is not None:
                direct.append((best_distance, obj))

        if len(direct) >= 2:
            bus_side = [obj for _, obj in sorted(
                direct,
                key=lambda item: (item[0], item[1].box.x, item[1].box.y, item[1].xml_index),
            )[:2]]
        else:
            distances = []
            for obj in disconnectors:
                distance = min(cls._distance_to_box(obj, bus) for bus in buses)
                distances.append((distance, obj))
            bus_side = [obj for _, obj in sorted(
                distances,
                key=lambda item: (item[0], item[1].box.x, item[1].box.y, item[1].xml_index),
            )[:2]]

        bus_side = sorted(
            bus_side,
            key=lambda obj: (obj.box.x, obj.box.y, obj.xml_index),
        )
        selected = {_object_identity(obj) for obj in bus_side}
        remaining = sorted(
            [obj for obj in disconnectors if _object_identity(obj) not in selected],
            key=lambda obj: (obj.box.y, obj.box.x, obj.xml_index),
        )
        return bus_side + remaining

    @classmethod
    def _assign_bay_records(cls, parsed, objects, contexts, records_by_bay, rules):
        """Assign BAY_ID-filtered database rows without parsing G CODE/NAME."""
        groups = defaultdict(list)
        errors = {}
        assignments = {}
        for obj in objects:
            context = contexts.get(_object_identity(obj), ({}, "", {}))[0] or {}
            rule = rules.get(obj.tag, {})
            table_id = int(rule.get("table_id", 0) or 0)
            bay_id = int_or_none(context.get("bay_id"))
            groups[(obj.tag, table_id, bay_id)].append(obj)

        for (tag, table_id, bay_id), group in groups.items():
            records = list(records_by_bay.get((table_id, bay_id), []))
            if bay_id is None:
                message = (
                    "MASTER_STATION_BAY_ID_NOT_FOUND: 已关联上下文没有 BAY_ID，"
                    "无法按间隔定位主站设备。"
                )
                for obj in group:
                    errors[_object_identity(obj)] = message
                continue
            if not records:
                message = (
                    f"MASTER_STATION_BAY_NOT_MATCHED: 表 {table_id} 中 BAY_ID={bay_id} "
                    "没有设备记录。"
                )
                for obj in group:
                    errors[_object_identity(obj)] = message
                continue

            if tag == "Disconnector" and len(group) > 1:
                if len(records) != len(group):
                    message = (
                        "MASTER_STATION_DISCONNECTOR_COUNT_MISMATCH: "
                        f"同一 BAY_ID={bay_id} 的 G 隔离开关={len(group)}，"
                        f"数据库隔离开关={len(records)}，拒绝猜测关联。"
                    )
                    for obj in group:
                        errors[_object_identity(obj)] = message
                    continue
                expected_markers = {"1", "2"} if len(records) == 2 else {"1", "2", "T"}
                markers = [_record_name_marker(record) for record in records]
                if len(records) not in (2, 3) or set(markers) != expected_markers or len(set(markers)) != len(markers):
                    message = (
                        "MASTER_STATION_DISCONNECTOR_NAME_MARKER_INVALID: "
                        f"BAY_ID={bay_id} 的数据库 NAME 必须能唯一识别 "
                        f"{', '.join(sorted(expected_markers))}，当前={', '.join(markers) or '-'}。"
                    )
                    for obj in group:
                        errors[_object_identity(obj)] = message
                    continue
                ordered_objects = cls._ordered_disconnectors(parsed, group)
                ordered_records = sorted(records, key=_record_assignment_order)
                for obj, record in zip(ordered_objects, ordered_records):
                    assignments[_object_identity(obj)] = record
                continue

            if len(group) != 1 or len(records) != 1:
                message = (
                    f"MASTER_STATION_BAY_NOT_UNIQUE: 表 {table_id} / BAY_ID={bay_id} "
                    f"G对象={len(group)}，数据库记录={len(records)}。"
                )
                for obj in group:
                    errors[_object_identity(obj)] = message
                continue
            assignments[_object_identity(group[0])] = records[0]

        return assignments, errors

    def _resolve_object(
        self,
        obj,
        db,
        rules,
        context=None,
        context_error="",
        context_meta=None,
        target_record=None,
        target_records_count=0,
        target_lookup_error="",
    ):
        tag = obj.tag
        rule = dict(rules.get(tag, {}) or {})
        table_id = int(rule.get("table_id", 0) or 0)
        domain = int(rule.get("domain", 40) or 0)
        row = {
            "file_name": obj.attrs.get("_file_name", ""),
            "object_type": tag,
            "xml_id": obj.xml_id,
            "key_name": obj.attrs.get("key_name", ""),
            "logical_code": "",
            "current_keyid": obj.keyid,
            "table_id": table_id,
            "configured_domain": domain,
            "table_name": rule.get("table_name", ""),
            "db_match_count": 0,
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_bv_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "NO",
            "model_linked": "NO",
            "model_link_correct": "NO",
            "writeback_needed": "NO",
            "association_ready": "NO",
            "status": "FAIL",
            "severity": "ERROR",
            "reason": "",
        }
        if context_meta:
            row.update({
                "context_rmu_frame_xml_id": context_meta.get("rmu_frame_xml_id", ""),
                "context_rmu_id": context_meta.get("rmu_id", ""),
                "context_rmu_name": context_meta.get("rmu_name", ""),
                "context_anchor_type": context_meta.get("context_anchor_type", ""),
                "context_anchor_xml_id": context_meta.get("context_anchor_xml_id", ""),
                "context_anchor_keyid": context_meta.get("context_anchor_keyid", ""),
            })
        if context:
            row.update({
                "context_source": context.get("source", ""),
                "context_station_id": context.get("station_id", ""),
                "context_station_name": context.get("station_name", ""),
                "context_feeder_id": context.get("feeder_id", ""),
                "context_feeder_code": context.get("feeder_code", ""),
                "context_feeder_name": context.get("feeder_name", ""),
                "context_bay_id": context.get("bay_id", ""),
                "context_rmu_frame_xml_id": context.get("rmu_frame_xml_id", ""),
                "context_rmu_id": context.get("rmu_id", ""),
                "context_rmu_name": context.get("rmu_name", ""),
                "context_anchor_type": context.get("context_anchor_type", ""),
                "context_anchor_xml_id": context.get("context_anchor_xml_id", ""),
                "context_anchor_keyid": context.get("context_anchor_keyid", ""),
            })
        if context_error:
            row["reason"] = (
                f"{context_error}"
            )
            return row
        self._current_link(row, db)
        if table_id <= 0:
            row["reason"] = "MASTER_STATION_TABLE_NOT_CONFIGURED: 该图元尚未配置数据库表号。"
            return row
        if target_lookup_error:
            row["reason"] = target_lookup_error
            return row
        if target_record is None:
            row["reason"] = (
                "MASTER_STATION_BAY_RECORD_NOT_SELECTED: "
                f"表 {table_id} 未按 BAY_ID 选出唯一目标设备。"
            )
            return row

        record = target_record
        row["table_name"] = record.get("_table_name", rule.get("table_name", ""))
        row["db_match_count"] = target_records_count
        device_id = int_or_none(record.get("id"))
        if device_id is None:
            row["reason"] = "MASTER_STATION_DEVICE_ID_INVALID: 数据库 ID 无效。"
            return row
        expected = self._expected_keyid(device_id, domain)
        row.update({
            "db_device_id": device_id,
            "db_code": str(record.get("code") or "").strip(),
            "db_name": str(record.get("name") or "").strip(),
            "db_bv_id": str(record.get("bv_id") or "").strip(),
            "expected_keyid": expected,
        })
        try:
            decoded = db.verify_keyid(expected)
            row["expected_keyid_verified"] = (
                "YES"
                if int_or_none(decoded.get("device_id")) == device_id
                and int_or_none(decoded.get("tab_no")) == table_id
                and int_or_none(decoded.get("col_no")) == domain
                else "NO"
            )
        except Exception as exc:
            row["reason"] = f"MASTER_STATION_EXPECTED_KEYID_VERIFY_ERROR: {exc}"
            return row
        if row["expected_keyid_verified"] != "YES":
            row["reason"] = "MASTER_STATION_EXPECTED_KEYID_VERIFY_FAILED: 目标表号/域号校验失败。"
            return row
        if not row["db_bv_id"]:
            row["reason"] = "MASTER_STATION_BV_ID_EMPTY: 数据库 BV_ID 为空。"
            return row

        if int_or_none(row.get("current_keyid")) == expected:
            row.update({
                "status": "PASS",
                "severity": "PASS",
                "model_link_correct": "YES",
                "model_link_status": "当前 KeyID 正确",
                "association_action": "无需回写",
                "association_ready": "YES",
                "reason": "MASTER_STATION_MODEL_LINK_CORRECT",
            })
        else:
            row.update({
                "status": "RELINK" if row.get("current_keyid") else "UNLINKED",
                "severity": "RELINK" if row.get("current_keyid") else "WARN",
                "model_link_status": "当前 KeyID 为空，尚未关联" if not row.get("current_keyid") else "当前 KeyID 不是目标设备",
                "association_action": "关联主站设备" if not row.get("current_keyid") else "重新关联主站设备",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "reason": "MASTER_STATION_ASSOCIATION_READY",
            })
        return row

    def _analyze_file(self, db, g_file, settings, log_callback, progress_callback=None):
        parsed = GParser().parse(g_file)
        drawing_scope = assess_jeddah_drawing_scope(parsed)
        rules = self._rules(settings)
        # RMU geometry/KeyID is no longer an input to master-station feeder
        # resolution.  Keep these counts only as non-authoritative diagnostics
        # so existing report fields remain compatible.
        frames = GParser().find_rmu_frames(parsed)
        breakers = [obj for obj in parsed.objects if obj.tag == "CBreaker"]
        objects = [obj for obj in parsed.objects if obj.tag in TARGET_TAGS]

        feeder_resolution = resolve_drawing_feeder(
            db, parsed, settings or {}, log_callback=log_callback
        )
        filename_context, filename_context_error, filename_context_meta = (
            self._context_from_filename_feeder(db, feeder_resolution)
        )

        # Every main-station object in this single-feeder drawing uses the
        # exact same filename-derived station/feeder/Bay context.  No RMU,
        # existing RMU KeyID or other graphical device is allowed to override
        # or supply the FEEDER_ID.
        resolved_contexts = {}
        for obj in objects:
            resolved_contexts[_object_identity(obj)] = (
                dict(filename_context or {}) if filename_context else None,
                str(filename_context_error or ""),
                dict(filename_context_meta or {}),
            )

        records_by_bay = {}
        # Existing device association remains unchanged: once the filename
        # feeder resolves the unique 406/Bay, 407/408/409 are queried by that
        # BAY_ID and the original uniqueness/count/order rules are applied.
        for obj in objects:
            context = resolved_contexts[_object_identity(obj)][0] or {}
            rule = rules.get(obj.tag, {})
            table_id = int(rule.get("table_id", 0) or 0)
            bay_id = int_or_none(context.get("bay_id"))
            if bay_id is None or table_id <= 0:
                continue
            cache_key = (table_id, bay_id)
            if cache_key not in records_by_bay:
                try:
                    _table_name, records_by_bay[cache_key] = db.get_devices_by_bay_id(
                        table_id, bay_id
                    )
                except Exception:
                    records_by_bay[cache_key] = []

        # G-root facID is intentionally not read for feeder identification or
        # association gating.  The G filename is the only authoritative feeder
        # source for the master-station module.
        facid_check = {
            "graph_facid": "",
            "facid_check": "NOT_USED",
            "facid_consistent": True,
            "facid_reason": "G.facID 不参与馈线识别或设备归属判断。",
        }

        graph_context = {}
        if filename_context:
            feeder = feeder_resolution.get("feeder") or {}
            feeder_db_name = str(feeder.get("name") or "").strip()
            feeder_code = str(feeder.get("code") or "").strip()
            location_parts = [
                str(filename_context.get("station_name") or "").strip(),
                feeder_db_name,
                feeder_code,
            ]
            location_parts = list(dict.fromkeys(item for item in location_parts if item))
            graph_context = {
                "source": filename_context.get("source", ""),
                "feeder_id": filename_context.get("feeder_id", ""),
                "feeder_code": filename_context.get("feeder_code", ""),
                "feeder_graph_name": str(feeder.get("graph_name") or "").strip(),
                "feeder_db_name": feeder_db_name,
                "feeder_name": filename_context.get("feeder_name", ""),
                "station_id": filename_context.get("station_id", ""),
                "station_name": filename_context.get("station_name", ""),
                "bay_id": filename_context.get("bay_id", ""),
                "bay_code": filename_context.get("bay_code", ""),
                "bay_name": filename_context.get("bay_name", ""),
                "location_label": " ".join(location_parts),
            }

        assignments, assignment_errors = self._assign_bay_records(
            parsed, objects, resolved_contexts, records_by_bay, rules
        )
        if log_callback:
            if filename_context:
                log_callback(
                    f"[{Path(g_file).name}] 主站设备上下文已由文件名确定："
                    f"ST_ID={filename_context.get('station_id') or '-'}；"
                    f"FEEDER_ID={filename_context.get('feeder_id') or '-'}；"
                    f"BAY_ID={filename_context.get('bay_id') or '-'}。"
                )
            else:
                log_callback(
                    f"[{Path(g_file).name}] 主站设备关联阻断："
                    f"{filename_context_error or '文件名馈线/Bay上下文无法唯一确定。'}"
                )
        rows = []
        total = max(len(objects), 1)
        for index, obj in enumerate(objects, 1):
            obj.attrs["_file_name"] = Path(g_file).name
            context, context_error, context_meta = resolved_contexts[_object_identity(obj)]
            assignment_error = assignment_errors.get(_object_identity(obj), "")
            if not context_error and assignment_error:
                context_error = assignment_error
            if log_callback and context:
                log_callback(
                    f"[{Path(g_file).name}] {obj.tag} XML ID={obj.xml_id or '-'}："
                    f"文件名馈线={context.get('filename_feeder_name') or context.get('feeder_name') or '-'}；"
                    f"FEEDER_ID={context.get('feeder_id') or '-'}；"
                    f"BAY_ID={context.get('bay_id') or '-'}。"
                )
            target_record = assignments.get(_object_identity(obj))
            row = self._resolve_object(
                obj,
                db,
                rules,
                context,
                context_error,
                context_meta,
                target_record=target_record,
                target_records_count=len(records_by_bay.get((
                    int(rules.get(obj.tag, {}).get("table_id", 0) or 0),
                    int_or_none((context or {}).get("bay_id")),
                ), [])),
                target_lookup_error=assignment_error,
            )
            if target_record is not None:
                target_candidate = candidate_from_record(
                    db,
                    target_record,
                    kind="MASTER_STATION",
                    identity=target_record.get("id"),
                    name=target_record.get("name") or target_record.get("code"),
                    source=f"MASTER_{obj.tag}_TARGET",
                )
                enforce_device_feeder_membership(
                    row,
                    feeder_resolution,
                    device_feeder_id=target_candidate.get("feeder_id"),
                    reason_prefix="MASTER_STATION",
                )
            else:
                add_feeder_fields(row, feeder_resolution)
                if not feeder_resolution.get("ready"):
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "reason": feeder_resolution.get("reason") or row.get("reason"),
                    })
            rows.append(row)
            if progress_callback:
                progress_callback(index, total, f"正在处理主站设备 {index}/{len(objects)}")
        if not drawing_scope["association_allowed"]:
            apply_jeddah_scope_block(rows, drawing_scope)
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 配网主站设备识别完成：图元={len(rows)}；"
                f"可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "MASTER_STATION",
            **scope_report_fields(drawing_scope),
            "graph_facid": facid_check["graph_facid"],
            "facid_check": facid_check["facid_check"],
            "facid_consistent": facid_check["facid_consistent"],
            "facid_reason": facid_check["facid_reason"],
            "master_station_rows": rows,
            "association_context": {
                "mode": "filename_feeder_with_target_membership",
                "rmu_frame_count": len(frames),
                "cbreaker_count": len(breakers),
                "feeder_resolution_source": feeder_resolution.get("feeder_source", "UNRESOLVED"),
                "feeder_resolution_evidence": feeder_resolution.get("feeder_evidence", ""),
                "feeder_anchor": feeder_resolution.get("feeder_anchor", ""),
                "station_id": graph_context.get("station_id", ""),
                "station_name": graph_context.get("station_name", ""),
                "feeder_code": graph_context.get("feeder_code", ""),
                "feeder_graph_name": graph_context.get("feeder_graph_name", ""),
                "feeder_db_name": graph_context.get("feeder_db_name", ""),
                "feeder_id": feeder_resolution.get("feeder_id", ""),
                "graph_facid": facid_check["graph_facid"],
                "facid_check": facid_check["facid_check"],
                "facid_reason": facid_check["facid_reason"],
                "feeder_name": graph_context.get("feeder_name", ""),
                "bay_id": graph_context.get("bay_id", ""),
                "bay_code": graph_context.get("bay_code", ""),
                "bay_name": graph_context.get("bay_name", ""),
                "location_label": graph_context.get("location_label", ""),
                "feeder_path": " / ".join(
                    value for value in (
                        graph_context.get("station_name", ""),
                        graph_context.get("feeder_code", "")
                        or graph_context.get("feeder_name", ""),
                    ) if value
                ),
                "message": filename_context_error or feeder_resolution.get("reason") or "图级 FEEDER_ID 已由 G 文件名 → 405/substation → 13500/dms_feeder_device 唯一确认；406/Bay 由该馈线唯一定位，所有 407/408/409 目标仍必须证明属于该馈线。",
            },
            "summary": {
                "master_station_count": len(rows),
                "master_station_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "master_station_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "master_station_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "master_station_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES" and row.get("writeback_needed") == "YES"),
                "feeder_context_ready": "YES" if feeder_resolution.get("ready") and filename_context else "NO",
                "feeder_context_message": filename_context_error or feeder_resolution.get("reason") or "图级 FEEDER_ID 与 406/Bay 已由文件名馈线上下文唯一确认。",
            },
        }

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        reports = []
        aggregate = defaultdict(int)
        total_files = max(len(files), 1)
        for file_index, g_file in enumerate(files, 1):
            report = self._analyze_file(
                db, g_file, settings, log_callback,
                lambda current, total, message: progress_callback(
                    int(((file_index - 1) + current / max(total, 1)) / total_files * 90) + 5,
                    message,
                ) if progress_callback else None,
            )
            reports.append(report)
            for key, value in report["summary"].items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    aggregate[key] += value
        return reports, dict(aggregate), self._rules(settings)

    def preview_association(self, db, files, settings, log_callback, progress_callback=None):
        reports, summary, rules = self.validate(db, files, settings, log_callback, progress_callback)
        changes_by_file = defaultdict(list)
        rows = []
        for report in reports:
            for row in report.get("master_station_rows", []):
                if row.get("association_ready") != "YES" or row.get("writeback_needed") != "YES":
                    continue
                change = {
                    "xml_id": row["xml_id"],
                    "tag": row["object_type"],
                    "_source_file": report["g_file"],
                    "attributes": self._attributes_for_row(row),
                    "validated_row": dict(row),
                }
                changes_by_file[report["g_file"]].append(change)
                output_row = dict(row)
                output_row["reason"] = (
                    "PREVIEW_WRITE: 仅回写 G 图元中已经存在的主站字段 "
                    "app/voltype/p_ReportType/state/keyid；G 图元没有的字段不写入。"
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
            "settings_snapshot": {"master_station_rules": rules},
        }

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        if not preview_data or not preview_data.get("changes_by_file"):
            raise RuntimeError("没有可执行的配网主站设备关联结果。")
        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")
        source_map = {str(Path(item).resolve()): Path(item) for item in files}
        for source_file, fingerprint in (preview_data.get("file_fingerprints", {}) or {}).items():
            path = Path(source_file)
            stat = path.stat()
            if stat.st_size != fingerprint.get("size") or stat.st_mtime_ns != fingerprint.get("mtime_ns"):
                raise RuntimeError(f"G 文件在模型校验后发生变化，禁止使用旧结果：{source_file}")
        executable = defaultdict(list)
        execution_rows = []
        for source_file, changes in preview_data.get("changes_by_file", {}).items():
            refreshed_report = self._analyze_file(
                db, Path(source_file), settings, log_callback
            )
            refreshed_by_xml = {
                str(row.get("xml_id") or ""): row
                for row in refreshed_report.get("master_station_rows", [])
            }
            for change in changes:
                row = dict(
                    refreshed_by_xml.get(str(change.get("xml_id") or ""), {})
                )
                if not row or row.get("association_ready") != "YES":
                    if not row:
                        row = dict(change.get("validated_row", {}) or {})
                        row["reason"] = "MASTER_STATION_EXECUTION_TARGET_NOT_FOUND"
                    row["_execution_result"] = "SKIPPED"
                    execution_rows.append((change, row))
                    continue
                refreshed = dict(change)
                refreshed["attributes"] = self._attributes_for_row(row)
                refreshed["validated_row"] = row
                executable[source_file].append(refreshed)
                row["_execution_result"] = "READY"
                execution_rows.append((refreshed, row))

        output_dir = Path(output_g_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        copied_files = []
        applied = 0
        writer = GWriteBackService(log=log_callback)
        for source_file, changes in executable.items():
            source = source_map.get(str(Path(source_file).resolve()), Path(source_file))
            target = output_dir / source.name
            if target.exists():
                index = 2
                while True:
                    candidate = output_dir / f"{target.stem}_{index}{target.suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1
            target.write_bytes(source.read_bytes())
            result = writer.apply_attribute_changes(
                target,
                changes,
                create_backup=False,
                only_existing_attributes=True,
                allowed_attributes=MASTER_STATION_WRITE_ATTRIBUTES,
            )
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
                "report_type": "MASTER_STATION",
                "master_station_rows": rows,
                "summary": {"master_station_count": len(rows)},
            })
        selected = sum(len(items) for items in preview_data["changes_by_file"].values())
        return {
            "selected_count": selected,
            "applied_count": applied,
            "skipped_count": max(selected - applied, 0),
            "output_g_dir": str(output_dir),
            "copied_files": copied_files,
            "operation_reports": operation_reports,
            "rules": self._rules(settings),
        }
