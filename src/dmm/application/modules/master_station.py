from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES
from dmm.domain.gfile.parser import GParser
from dmm.domain.gfile.master_station_frames import (
    find_master_station_frames,
    objects_inside_frame,
)
from dmm.domain.rmu.validator import int_or_none
from dmm.infrastructure.gfile.writeback import GWriteBackService


KEYID_STEP = 1 << 32
TARGET_TAGS = ("Bus", "CBreaker", "Disconnector", "GroundDisconnector")
RMU_ANCHOR_TAGS = {
    "CBreakerDis", "BusDis", "ZhaiWaiJieDiDaoZha", "pwbh",
}
CODE_PATTERNS = {
    "CBreaker": re.compile(r"\b(B[A-Z0-9]+(?:_[A-Z0-9]+)?)\s+id\b", re.I),
    "Disconnector": re.compile(r"\b(D[A-Z0-9]+(?:_[A-Z0-9]+)?)\s+id\b", re.I),
    "GroundDisconnector": re.compile(r"\b(K[A-Z0-9]+(?:_[A-Z0-9]+)?)\s+id\b", re.I),
}


def _code_from_key_name(tag, key_name):
    value = str(key_name or "").strip()
    match = CODE_PATTERNS.get(tag)
    if match:
        found = match.search(value)
        if found:
            return found.group(1)
    if tag == "Bus":
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value)
        if tokens:
            # busbarsection ... AHBB1 AHBB1 id -> AHBB1
            usable = [item for item in tokens if item.casefold() not in {"busbarsection", "id"}]
            return usable[-1] if usable else ""
    return ""


class MasterStationModelModule(ModelModule):
    module_id = "MASTER_STATION"
    display_name = "配网主站设备关联"
    description = (
        "按含 CBreaker 的主网矩形框识别 Bay：每个框只使用最近的无背景合法馈线标题（颜色不限）"
        "（如 MNA4-12 / ARF2-07 / SHM1-AH341_X），解析变电站和完整馈线编号后确定唯一 BAY_ID；"
        "框内 Bus 只按已确认 ST_ID 从 410/busbarsection 任意取未使用记录；"
        "CBreaker / Disconnector / GroundDisconnector 继续按对应 BAY_ID 关联，不分析全图拓扑。"
    )
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    @staticmethod
    def _rules(settings=None):
        saved = (settings or {}).get("master_station_rules", {}) or {}
        result = {}
        for tag, default in DEFAULT_MASTER_STATION_RULES.items():
            item = dict(default)
            item.update(saved.get(tag, {}) or {})
            # v4.1.74: Bus 410 / Domain 40 is now a fixed Makkah rule.
            # Older Workspace settings may still persist the previous placeholder
            # table_id=0; do not allow that stale value to disable Bus linking.
            if tag == "Bus":
                item["table_id"] = 410
                item["domain"] = 40
                item["table_name"] = "busbarsection"
                item["description"] = "主站母线段"
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
            "Bus": "10",
            "CBreaker": "41",
            "Disconnector": "31",
            "GroundDisconnector": "31",
        }.get(str(row.get("object_type") or ""), "41")
        object_type = str(row.get("object_type") or "")
        return {
            # Main-network equipment follows the field DBI/G-file convention:
            # Bus / CBreaker / Disconnector / GroundDisconnector all write
            # app=100000.  State remains type-specific below.
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
            return {
                "source": source,
                "source_keyid": parsed_keyid,
                "source_table_id": table_id,
                "source_device_id": device_id,
                "source_domain": domain or "",
                "rmu_id": rmu_id,
                "rmu_name": str((rmu or {}).get("name") or "").strip(),
                "bay_id": bay_id or "",
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
        x, y = obj.box.cx, obj.box.cy
        dx = max(frame.frame.box.left - x, 0.0, x - frame.frame.box.right)
        dy = max(frame.frame.box.top - y, 0.0, y - frame.frame.box.bottom)
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
                hint = str(bay.get("code") or bay.get("name") or "").strip()
                station_id = int_or_none(bay.get("st_id"))
                candidates = db.find_feeders_by_bay(hint, station_id)
                if len(candidates) == 1:
                    return int_or_none(candidates[0].get("id")) == context_feeder
            except Exception:
                pass

        context_station = int_or_none(context.get("station_id"))
        record_station = int_or_none(record.get("st_id"))
        if context_station is not None and record_station is not None:
            return context_station == record_station
        return True

    @staticmethod
    def _norm_business(value):
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @staticmethod
    def _numeric_token_equal(left, right):
        a = str(left or "").strip()
        b = str(right or "").strip()
        if not a.isdigit() or not b.isdigit():
            return False
        try:
            return int(a) == int(b)
        except ValueError:
            return False

    @classmethod
    def _select_station(cls, rows, station_hint):
        hint = cls._norm_business(station_hint)
        exact = [row for row in rows if cls._norm_business(row.get("name")) == hint]
        if exact:
            return exact if len(exact) != 1 else exact
        suffix = [
            row for row in rows
            if cls._norm_business(row.get("name")).endswith(hint)
        ]
        return suffix

    @classmethod
    def _rank_feeder_like_rows(cls, rows, full_label, feeder_hint):
        """Return only the unique best-rank feeder/Bay candidates.

        Full visible labels are strongest.  Local feeder numbers (07 vs 7)
        are accepted only inside the already-resolved station.
        """
        full_norm = cls._norm_business(full_label)
        feeder_norm = cls._norm_business(feeder_hint)
        ranked = []
        for row in rows:
            values = [
                str(row.get("graph_name") or "").strip(),
                str(row.get("code") or "").strip(),
                str(row.get("name") or "").strip(),
            ]
            norms = [cls._norm_business(value) for value in values if value]
            rank = None
            if full_norm and full_norm in norms:
                rank = 0
            elif feeder_norm and feeder_norm in norms:
                rank = 1
            elif any(
                cls._numeric_token_equal(value, feeder_hint)
                for value in values
            ):
                rank = 2
            elif full_norm and any(
                norm and full_norm.endswith(norm) for norm in norms
            ):
                rank = 3
            if rank is not None:
                ranked.append((rank, row))
        if not ranked:
            return []
        best = min(rank for rank, _row in ranked)
        return [row for rank, row in ranked if rank == best]

    @classmethod
    def _resolve_frame_context(cls, frame_info, db, cache):
        """Resolve one CBreaker frame to station -> feeder -> BAY_ID.

        The frame itself is the business boundary.  No nearest-RMU or global
        topology fallback is allowed.
        """
        cache_key = frame_info.frame.xml_index
        if cache_key in cache:
            return cache[cache_key]

        meta = {
            "master_frame_xml_id": frame_info.frame.xml_id,
            "master_frame_xml_index": frame_info.frame.xml_index,
            "source_breaker_xml_id": (
                frame_info.breaker.xml_id if frame_info.breaker else ""
            ),
            "source_breaker_count": len(frame_info.breakers),
            "feeder_label": frame_info.feeder_label,
            "feeder_label_text_xml_id": (
                frame_info.label_obj.xml_id if frame_info.label_obj else ""
            ),
            "feeder_label_distance": (
                round(frame_info.label_distance, 3)
                if frame_info.label_distance is not None else ""
            ),
        }

        if len(frame_info.breakers) != 1:
            result = (
                None,
                "MASTER_STATION_FRAME_CBREAKER_NOT_UNIQUE: "
                f"主网框内 CBreaker 数量={len(frame_info.breakers)}，"
                "无法唯一确定 Bay，禁止自动关联。",
                meta,
            )
            cache[cache_key] = result
            return result

        if not frame_info.feeder_label:
            result = (
                None,
                "MASTER_STATION_WHITE_FEEDER_LABEL_NOT_FOUND: "
                "主网框附近未找到 200 G 距离以内、无背景且格式合法的馈线名称（颜色不限）"
                "（格式如 MNA4-12 / ARF2-07 / SHM1-AH341_X），禁止借用其它框标题。",
                meta,
            )
            cache[cache_key] = result
            return result

        try:
            stations = db.find_stations_by_name_hint(frame_info.station_hint)
        except Exception as exc:
            result = (
                None,
                f"MASTER_STATION_STATION_LOOKUP_ERROR: {exc}",
                meta,
            )
            cache[cache_key] = result
            return result
        stations = cls._select_station(stations, frame_info.station_hint)
        if len(stations) != 1:
            result = (
                None,
                "MASTER_STATION_STATION_NOT_UNIQUE: "
                f"名称={frame_info.station_hint} 匹配变电站数={len(stations)}。",
                meta,
            )
            cache[cache_key] = result
            return result
        station = stations[0]
        station_id = int_or_none(station.get("id"))
        if station_id is None:
            result = (None, "MASTER_STATION_STATION_ID_INVALID", meta)
            cache[cache_key] = result
            return result

        # Bay is the authoritative main-network ownership key.  Resolve it
        # directly inside the already-confirmed station using the visible
        # MNA4-12 / ARF2-07 caption.  Feeder-table resolution is useful for
        # reporting and feeder ownership, but is not allowed to block direct
        # station-device association once the Bay itself is unique.
        try:
            bays = db.get_bays_by_station(station_id)
        except Exception as exc:
            result = (
                None,
                f"MASTER_STATION_BAY_LOOKUP_ERROR: {exc}",
                meta,
            )
            cache[cache_key] = result
            return result
        bay_candidates = cls._rank_feeder_like_rows(
            bays,
            frame_info.feeder_label,
            frame_info.feeder_hint,
        )
        if len(bay_candidates) != 1:
            result = (
                None,
                "MASTER_STATION_BAY_NOT_UNIQUE: "
                f"{frame_info.feeder_label} 在变电站 {station.get('name') or frame_info.station_hint} "
                f"内匹配 Bay 数={len(bay_candidates)}。",
                meta,
            )
            cache[cache_key] = result
            return result
        bay = bay_candidates[0]
        bay_id = int_or_none(bay.get("id"))
        if bay_id is None:
            result = (None, "MASTER_STATION_BAY_ID_INVALID", meta)
            cache[cache_key] = result
            return result

        # Feeder information is best-effort context after the Bay is known.
        # Main-station device association remains Bay-driven even if 13500 uses
        # a naming convention that does not uniquely match the visible title.
        feeder = {}
        feeder_id = None
        try:
            feeders = cls._rank_feeder_like_rows(
                db.get_feeders_by_station(station_id),
                frame_info.feeder_label,
                frame_info.feeder_hint,
            )
            if len(feeders) == 1:
                feeder = feeders[0]
                feeder_id = int_or_none(feeder.get("id"))
            elif hasattr(db, "find_feeders_by_bay"):
                bay_hint = str(bay.get("code") or bay.get("name") or "").strip()
                by_bay = db.find_feeders_by_bay(bay_hint, station_id)
                if len(by_bay) == 1:
                    feeder = by_bay[0]
                    feeder_id = int_or_none(feeder.get("id"))
        except Exception:
            feeder = {}
            feeder_id = None

        try:
            _breaker_table, breaker_rows = db.get_devices_by_bay(407, bay_id)
        except Exception as exc:
            result = (
                None,
                f"MASTER_STATION_BREAKER_BAY_LOOKUP_ERROR: {exc}",
                meta,
            )
            cache[cache_key] = result
            return result
        if len(breaker_rows) != 1:
            result = (
                None,
                "MASTER_STATION_BREAKER_BAY_NOT_UNIQUE: "
                f"BAY_ID={bay_id} 对应 breaker 数={len(breaker_rows)}，"
                "无法把图内 CBreaker 唯一落到数据库设备。",
                meta,
            )
            cache[cache_key] = result
            return result
        breaker_row = breaker_rows[0]
        breaker_bay = int_or_none(breaker_row.get("bay_id"))
        breaker_station = int_or_none(breaker_row.get("st_id"))
        if breaker_bay != bay_id or (
            breaker_station is not None and breaker_station != station_id
        ):
            result = (
                None,
                "MASTER_STATION_BREAKER_BAY_CONTEXT_MISMATCH: "
                "breaker.ST_ID/BAY_ID 与标题解析出的变电站/Bay 不一致。",
                meta,
            )
            cache[cache_key] = result
            return result

        context = {
            "source": "CBREAKER_FRAME_WHITE_LABEL_BAY",
            "master_frame_xml_id": frame_info.frame.xml_id,
            "master_frame_xml_index": frame_info.frame.xml_index,
            "source_breaker_xml_id": frame_info.breaker.xml_id,
            "source_breaker_db_id": int_or_none(breaker_row.get("id")) or "",
            "source_breaker_db_code": str(breaker_row.get("code") or "").strip(),
            "feeder_label": frame_info.feeder_label,
            "feeder_label_text_xml_id": (
                frame_info.label_obj.xml_id if frame_info.label_obj else ""
            ),
            "feeder_label_distance": meta["feeder_label_distance"],
            "station_id": station_id,
            "station_name": str(station.get("name") or "").strip(),
            "feeder_id": feeder_id,
            "feeder_code": str(feeder.get("code") or "").strip(),
            "feeder_name": str(
                feeder.get("graph_name") or feeder.get("name") or ""
            ).strip(),
            "bay_id": bay_id,
            "bay_code": str(bay.get("code") or "").strip(),
            "bay_name": str(bay.get("name") or "").strip(),
        }
        result = (context, "", meta)
        cache[cache_key] = result
        return result

    def _resolve_object(
        self, obj, db, rules, context=None, context_error="", context_meta=None,
        assigned_record=None, assigned_table_name="", assignment_error="",
    ):
        tag = obj.tag
        rule = dict(rules.get(tag, {}) or {})
        table_id = int(rule.get("table_id", 0) or 0)
        domain = int(rule.get("domain", 40) or 0)
        code = _code_from_key_name(tag, obj.attrs.get("key_name"))
        row = {
            "file_name": obj.attrs.get("_file_name", ""),
            "object_type": tag,
            "xml_id": obj.xml_id,
            "key_name": obj.attrs.get("key_name", ""),
            "logical_code": code,
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
                "context_master_frame_xml_id": context_meta.get("master_frame_xml_id", ""),
                "context_source_breaker_xml_id": context_meta.get("source_breaker_xml_id", ""),
                "context_source_breaker_count": context_meta.get("source_breaker_count", ""),
                "context_feeder_label": context_meta.get("feeder_label", ""),
                "context_feeder_label_text_xml_id": context_meta.get("feeder_label_text_xml_id", ""),
                "context_feeder_label_distance": context_meta.get("feeder_label_distance", ""),
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
                "context_bay_code": context.get("bay_code", ""),
                "context_bay_name": context.get("bay_name", ""),
                "context_master_frame_xml_id": context.get("master_frame_xml_id", ""),
                "context_source_breaker_xml_id": context.get("source_breaker_xml_id", ""),
                "context_source_breaker_db_id": context.get("source_breaker_db_id", ""),
                "context_source_breaker_db_code": context.get("source_breaker_db_code", ""),
                "context_feeder_label": context.get("feeder_label", ""),
                "context_feeder_label_text_xml_id": context.get("feeder_label_text_xml_id", ""),
                "context_feeder_label_distance": context.get("feeder_label_distance", ""),
            })
        if context_error:
            row["reason"] = str(context_error)
            return row

        self._current_link(row, db)
        if table_id <= 0:
            row["reason"] = "MASTER_STATION_TABLE_NOT_CONFIGURED: 该图元尚未配置数据库表号。"
            return row
        bay_id = int_or_none((context or {}).get("bay_id"))
        station_id = int_or_none((context or {}).get("station_id"))
        if tag == "Bus":
            if station_id is None:
                row["reason"] = "MASTER_STATION_STATION_CONTEXT_MISSING: 当前主网框没有唯一 ST_ID。"
                return row
        elif bay_id is None:
            row["reason"] = "MASTER_STATION_BAY_CONTEXT_MISSING: 当前主网框没有唯一 BAY_ID。"
            return row

        if assignment_error and tag == "Bus":
            row["reason"] = str(assignment_error)
            return row

        if assigned_record is not None and tag == "Bus":
            records = [dict(assigned_record)]
            if assigned_table_name:
                row["table_name"] = str(assigned_table_name)
        else:
            try:
                if tag == "Bus" and hasattr(db, "get_devices_by_station"):
                    table_name, records = db.get_devices_by_station(table_id, station_id)
                else:
                    table_name, records = db.get_devices_by_bay(table_id, bay_id)
                row["table_name"] = table_name
            except Exception as exc:
                scope = "STATION" if tag == "Bus" else "BAY"
                row["reason"] = f"MASTER_STATION_{scope}_DEVICE_LOOKUP_ERROR: {exc}"
                return row

        # CBreaker is already the authoritative breaker used to prove the Bay.
        # Use that exact DB row instead of relying on key_name, which is empty in
        # the supplied Makkah G files.
        if tag == "CBreaker":
            expected_breaker_id = int_or_none((context or {}).get("source_breaker_db_id"))
            if expected_breaker_id is not None:
                records = [
                    record for record in records
                    if int_or_none(record.get("id")) == expected_breaker_id
                ]

        # Bus assignments are prepared once per main-network frame before this
        # method is called.  Bus intentionally ignores BAY_ID: table 410 is
        # filtered only by the confirmed station ST_ID, then graphics are paired
        # with any unused busbarsection rows in a stable arbitrary order.
        #
        # Disconnector/GroundDisconnector may legitimately have multiple rows in
        # one Bay, so their graphical key_name CODE may disambiguate.  Never
        # guess by order or global distance when CODE is absent.
        if len(records) > 1 and code and tag not in {"CBreaker", "Bus"}:
            code_records = [
                record for record in records
                if str(record.get("code") or "").strip() == code
            ]
            if code_records:
                records = code_records

        row["db_match_count"] = len(records)
        if len(records) != 1:
            row["reason"] = (
                "MASTER_STATION_BAY_DEVICE_NOT_UNIQUE: "
                f"table={table_id} BAY_ID={bay_id}"
                + (f" CODE={code}" if code else "")
                + f" 匹配记录数={len(records)}；禁止按顺序或距离猜测。"
            )
            return row

        record = records[0]
        device_id = int_or_none(record.get("id"))
        if device_id is None:
            row["reason"] = "MASTER_STATION_DEVICE_ID_INVALID: 数据库 ID 无效。"
            return row
        record_bay = int_or_none(record.get("bay_id"))
        if tag != "Bus" and record_bay is not None and record_bay != bay_id:
            row["reason"] = "MASTER_STATION_DEVICE_BAY_MISMATCH: 设备 BAY_ID 与主网框 BAY_ID 不一致。"
            return row
        if tag == "Bus":
            record_station = int_or_none(record.get("st_id"))
            context_station = int_or_none((context or {}).get("station_id"))
            if (
                record_station is not None
                and context_station is not None
                and record_station != context_station
            ):
                row["reason"] = (
                    "MASTER_STATION_BUS_STATION_MISMATCH: "
                    "410/busbarsection.ST_ID 与主网框变电站不一致。"
                )
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
                "reason": (
                    "MASTER_STATION_BUS_ASSOCIATION_READY_BY_STATION"
                    if tag == "Bus" else "MASTER_STATION_ASSOCIATION_READY_BY_BAY"
                ),
            })
        return row

    @staticmethod
    def _prepare_bus_assignments(db, bus_objects, table_id, domain, context):
        """Allocate table-410 Bus rows from the confirmed station only.

        Makkah Bus association deliberately ignores BAY_ID.  After the main
        frame has established a unique station ST_ID, all 410/busbarsection rows
        under that station are candidates.  Each graphical Bus receives any one
        unused row.  Existing valid links are preserved first; remaining Bus
        elements use stable XML order and database-ID order so repeated runs do
        not reshuffle the arbitrary mapping.
        """
        bus_objects = list(bus_objects or [])
        if not bus_objects:
            return {}, "", ""

        station_id = int_or_none((context or {}).get("station_id"))
        if station_id is None:
            return {}, "", "MASTER_STATION_STATION_CONTEXT_MISSING: 当前主网框没有唯一 ST_ID。"

        try:
            if hasattr(db, "get_devices_by_station"):
                table_name, records = db.get_devices_by_station(int(table_id), station_id)
            else:
                # Compatibility for older adapters/test doubles.  Production
                # OracleDatabase provides get_devices_by_station().
                bay_id = int_or_none((context or {}).get("bay_id"))
                table_name, records = db.get_devices_by_bay(int(table_id), bay_id)
        except Exception as exc:
            return {}, "", f"MASTER_STATION_STATION_DEVICE_LOOKUP_ERROR: {exc}"

        records = [
            dict(item) for item in (records or [])
            if int_or_none(item.get("st_id")) in (None, station_id)
        ]
        if len(records) < len(bus_objects):
            return (
                {},
                str(table_name or "busbarsection"),
                "MASTER_STATION_BUS_COUNT_MISMATCH: "
                f"ST_ID={station_id} 图形 Bus 数={len(bus_objects)}，"
                f"410/busbarsection 可用数={len(records)}；可用记录不足。",
            )

        buses = sorted(bus_objects, key=lambda obj: int(getattr(obj, "xml_index", 0) or 0))
        records = sorted(
            records,
            key=lambda item: (
                int_or_none(item.get("id")) is None,
                int_or_none(item.get("id")) or 0,
                str(item.get("code") or ""),
                str(item.get("name") or ""),
            ),
        )
        record_by_id = {
            int_or_none(item.get("id")): item
            for item in records
            if int_or_none(item.get("id")) is not None
        }
        assignments = {}
        used_ids = set()

        # Preserve an existing valid 410/Domain-40 link when the device belongs
        # to this station, regardless of its BAY_ID.
        for obj in buses:
            current_keyid = int_or_none(getattr(obj, "keyid", None))
            if current_keyid is None:
                continue
            try:
                decoded = db.verify_keyid(current_keyid)
            except Exception:
                continue
            if (
                int_or_none(decoded.get("tab_no")) != int(table_id)
                or int_or_none(decoded.get("col_no")) != int(domain)
            ):
                continue
            device_id = int_or_none(decoded.get("device_id"))
            if device_id in record_by_id and device_id not in used_ids:
                assignments[obj.xml_index] = record_by_id[device_id]
                used_ids.add(device_id)

        remaining_buses = [obj for obj in buses if obj.xml_index not in assignments]
        remaining_records = [
            item for item in records
            if int_or_none(item.get("id")) not in used_ids
        ]
        for obj, record in zip(remaining_buses, remaining_records):
            assignments[obj.xml_index] = record

        return assignments, str(table_name or "busbarsection"), ""

    def _analyze_file(self, db, g_file, settings, log_callback, progress_callback=None):
        parsed = GParser().parse(g_file)
        rules = self._rules(settings)
        frames = find_master_station_frames(parsed)
        context_cache = {}

        target_objects = [obj for obj in parsed.objects if obj.tag in TARGET_TAGS]
        framed_items = []
        seen = set()
        for frame_info in frames:
            inside = objects_inside_frame(parsed, frame_info.frame, TARGET_TAGS)
            for obj in inside:
                if obj.xml_index in seen:
                    continue
                seen.add(obj.xml_index)
                framed_items.append((frame_info, obj))
        outside_count = sum(1 for obj in target_objects if obj.xml_index not in seen)

        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 主站 Bay 框识别："
                f"含 CBreaker 的最内层矩形框={len(frames)}；"
                f"框内目标图元={len(framed_items)}；框外忽略={outside_count}。"
            )

        rows = []
        total = max(len(framed_items), 1)
        current = 0
        for frame_info in frames:
            context, context_error, context_meta = self._resolve_frame_context(
                frame_info, db, context_cache
            )
            if log_callback:
                if context:
                    log_callback(
                        f"[{Path(g_file).name}] 主网框 XML ID={frame_info.frame.xml_id or '-'}："
                        f"无背景合法标题（颜色不限）={context.get('feeder_label') or '-'}；"
                        f"变电站={context.get('station_name') or context.get('station_id') or '-'}；"
                        f"馈线={context.get('feeder_name') or context.get('feeder_code') or context.get('feeder_id') or '-'}；"
                        f"BAY_ID={context.get('bay_id') or '-'}。"
                    )
                else:
                    log_callback(
                        f"[{Path(g_file).name}] 主网框 XML ID={frame_info.frame.xml_id or '-'}："
                        f"{context_error}"
                    )

            frame_objects = objects_inside_frame(parsed, frame_info.frame, TARGET_TAGS)
            bus_objects = [obj for obj in frame_objects if obj.tag == "Bus"]
            bus_assignments = {}
            bus_table_name = ""
            bus_assignment_error = ""
            if context and bus_objects:
                bus_rule = dict(rules.get("Bus", {}) or {})
                bus_assignments, bus_table_name, bus_assignment_error = self._prepare_bus_assignments(
                    db,
                    bus_objects,
                    int(bus_rule.get("table_id", 410) or 410),
                    int(bus_rule.get("domain", 40) or 40),
                    context,
                )

            for obj in frame_objects:
                if any(existing.get("_xml_index") == obj.xml_index for existing in rows):
                    continue
                current += 1
                obj.attrs["_file_name"] = Path(g_file).name
                row = self._resolve_object(
                    obj, db, rules, context, context_error, context_meta,
                    assigned_record=bus_assignments.get(obj.xml_index) if obj.tag == "Bus" else None,
                    assigned_table_name=bus_table_name if obj.tag == "Bus" else "",
                    assignment_error=bus_assignment_error if obj.tag == "Bus" else "",
                )
                row["_xml_index"] = obj.xml_index
                rows.append(row)
                if progress_callback:
                    progress_callback(
                        current,
                        total,
                        f"正在处理主站 Bay 框设备 {current}/{len(framed_items)}",
                    )

        for row in rows:
            row.pop("_xml_index", None)

        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 配网主站设备识别完成：图元={len(rows)}；"
                f"可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "MASTER_STATION",
            "master_station_rows": rows,
            "association_context": {
                "mode": "cbreaker_frame_white_label_bay",
                "master_frame_count": len(frames),
                "framed_target_count": len(framed_items),
                "outside_frame_ignored_count": outside_count,
                "message": (
                    "只处理含 CBreaker 的最内层主网矩形框；"
                    "每框使用最近的无背景合法馈线标题（颜色不限）解析变电站/馈线/BAY_ID；"
                    "Bus 仅按已确认 ST_ID 从 410/busbarsection 任意一对一选择，"
                    "CBreaker/Disconnector/GroundDisconnector 继续按 BAY_ID 关联。"
                ),
            },
            "summary": {
                "master_station_count": len(rows),
                "master_station_frame_count": len(frames),
                "master_station_outside_frame_ignored": outside_count,
                "master_station_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "master_station_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "master_station_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "master_station_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(
                    1 for row in rows
                    if row.get("association_ready") == "YES"
                    and row.get("writeback_needed") == "YES"
                ),
                "feeder_context_ready": "FRAME_BAY",
                "feeder_context_message": (
                    "CBreaker 框 + 无背景合法馈线标题（颜色不限） -> 变电站/馈线/BAY_ID；"
                    "不依赖环网柜已有 KeyID，也不执行全图拓扑推断。"
                ),
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
                output_row["reason"] = "PREVIEW_WRITE: 仅修改目标图元已有 app/voltype/p_ReportType/state/keyid 属性。"
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
            # Execution is not allowed to trust a stale validation snapshot.
            # Re-run the current database/Bay/ST_ID checks once for this file,
            # then require every selected XML object to resolve to the SAME
            # target table/domain/device/Expected-KeyID that the user reviewed.
            refreshed_report = self._analyze_file(
                db, source_file, settings, log_callback, progress_callback=None
            )
            refreshed_rows = {
                (str(item.get("object_type") or ""), str(item.get("xml_id") or "")): item
                for item in refreshed_report.get("master_station_rows", [])
            }
            for change in changes:
                row = dict(change.get("validated_row", {}) or {})
                key = (str(row.get("object_type") or ""), str(row.get("xml_id") or ""))
                fresh = dict(refreshed_rows.get(key, {}) or {})
                if not fresh:
                    row["_execution_result"] = "SKIPPED"
                    row["reason"] = (
                        "MASTER_STATION_EXECUTION_RECHECK_MISSING: "
                        "执行前重新校验时未找到当前目标图元。"
                    )
                    execution_rows.append((change, row))
                    continue
                if fresh.get("association_ready") != "YES" or fresh.get("writeback_needed") != "YES":
                    row["_execution_result"] = "SKIPPED"
                    row["reason"] = (
                        "MASTER_STATION_EXECUTION_RECHECK_BLOCKED: "
                        + str(fresh.get("reason") or "数据库当前目标不再满足自动关联条件。")
                    )
                    execution_rows.append((change, row))
                    continue

                original_target = (
                    int_or_none(row.get("table_id")),
                    int_or_none(row.get("configured_domain")),
                    int_or_none(row.get("db_device_id")),
                    int_or_none(row.get("expected_keyid")),
                )
                current_target = (
                    int_or_none(fresh.get("table_id")),
                    int_or_none(fresh.get("configured_domain")),
                    int_or_none(fresh.get("db_device_id")),
                    int_or_none(fresh.get("expected_keyid")),
                )
                if current_target != original_target:
                    row["_execution_result"] = "SKIPPED"
                    row["reason"] = (
                        "MASTER_STATION_EXECUTION_TARGET_CHANGED: "
                        f"校验目标={original_target}，执行前数据库目标={current_target}；"
                        "禁止在未重新确认的情况下写入不同目标。"
                    )
                    execution_rows.append((change, row))
                    continue

                refreshed = dict(change)
                refreshed["validated_row"] = fresh
                # BV_ID is taken from the freshly rechecked DB row, while the
                # approved target identity remains unchanged.
                refreshed["attributes"] = self._attributes_for_row(fresh)
                executable[source_file].append(refreshed)
                fresh["_execution_result"] = "READY"
                execution_rows.append((refreshed, fresh))

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
