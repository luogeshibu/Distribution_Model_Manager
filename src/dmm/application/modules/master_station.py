from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES
from dmm.domain.gfile.parser import GParser
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
        "以每个 CBreaker 为锚点查找最近的 RMU 矩形框，只检查该框内部设备或保护信号的已有关联，"
        "再反查厂站/馈线并按 G 文件 key_name 中的 CODE 精确关联主站设备表；不分析拓扑。"
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
            "Bus": "10",
            "CBreaker": "41",
            "Disconnector": "31",
            "GroundDisconnector": "31",
        }.get(str(row.get("object_type") or ""), "41")
        return {
            "app": "6500000",
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

    def _resolve_object(self, obj, db, rules, context=None, context_error="", context_meta=None):
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
        if not code:
            row["reason"] = "MASTER_STATION_CODE_NOT_FOUND: G 图元 key_name 中未找到设备 CODE。"
            return row
        if table_id <= 0:
            row["reason"] = "MASTER_STATION_TABLE_NOT_CONFIGURED: 该图元尚未配置数据库表号。"
            return row
        try:
            table_name, records = db.get_devices_by_code(table_id, code)
            records = [
                record for record in records
                if self._record_matches_context(record, context, db)
            ]
            row["table_name"] = table_name
        except Exception as exc:
            row["reason"] = f"MASTER_STATION_TABLE_LOOKUP_ERROR: {exc}"
            return row
        row["db_match_count"] = len(records)
        if len(records) != 1:
            row["reason"] = (
                "MASTER_STATION_CODE_NOT_UNIQUE: "
                f"table={table_id} CODE={code} 匹配记录数={len(records)}。"
            )
            return row

        record = records[0]
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
        rules = self._rules(settings)
        frames = GParser().find_rmu_frames(parsed)
        breakers = [obj for obj in parsed.objects if obj.tag == "CBreaker"]
        context_cache = {}
        if log_callback:
            if frames:
                log_callback(
                    f"[{Path(g_file).name}] 主站设备关联按局部范围执行："
                    f"断路器={len(breakers)}；环网柜矩形框={len(frames)}；"
                    "每个对象只使用最近断路器对应 RMU 框内的已有关联。"
                )
            else:
                log_callback(
                    f"[{Path(g_file).name}] 主站设备关联阻断："
                    "G 文件未找到环网柜矩形框，该图环网柜请手动关联。"
                )
        objects = [obj for obj in parsed.objects if obj.tag in TARGET_TAGS]
        rows = []
        total = max(len(objects), 1)
        for index, obj in enumerate(objects, 1):
            obj.attrs["_file_name"] = Path(g_file).name
            context, context_error, context_meta = self._resolve_local_context(
                parsed, obj, breakers, frames, db, context_cache
            )
            if log_callback and context:
                log_callback(
                    f"[{Path(g_file).name}] {obj.tag} XML ID={obj.xml_id or '-'}："
                    f"最近 RMU 框={context.get('rmu_frame_xml_id') or '-'}；"
                    f"关联锚点={context.get('context_anchor_type') or '-'}"
                    f"/{context.get('context_anchor_xml_id') or '-'}；"
                    f"馈线={context.get('feeder_code') or context.get('feeder_id') or '-'}。"
                )
            row = self._resolve_object(
                obj, db, rules, context, context_error, context_meta
            )
            rows.append(row)
            if progress_callback:
                progress_callback(index, total, f"正在处理主站设备 {index}/{len(objects)}")
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
                "mode": "nearest_cbreaker_nearest_rmu",
                "rmu_frame_count": len(frames),
                "cbreaker_count": len(breakers),
                "message": "每个对象按最近断路器对应的最近环网柜框内关联反查。",
            },
            "summary": {
                "master_station_count": len(rows),
                "master_station_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "master_station_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "master_station_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "master_station_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES" and row.get("writeback_needed") == "YES"),
                "feeder_context_ready": "LOCAL_PER_RMU",
                "feeder_context_message": "未使用全局设备兜底；无 RMU 或框内无有效关联时逐对象阻断。",
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
            for change in changes:
                row = dict(change.get("validated_row", {}) or {})
                if row.get("association_ready") != "YES":
                    row["_execution_result"] = "SKIPPED"
                    execution_rows.append((change, row))
                    continue
                refreshed = dict(change)
                refreshed["attributes"] = self._attributes_for_row(row)
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
