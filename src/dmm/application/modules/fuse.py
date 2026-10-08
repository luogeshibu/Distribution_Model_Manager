from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.application.modules.feeder_context import (
    add_feeder_fields,
    enforce_device_feeder_membership,
    resolve_drawing_feeder,
)
from dmm.application.modules.transformer import TransformerParser
from dmm.domain.gfile.element_catalog import classification_is, resolve_element_record
from dmm.domain.gfile.parser import GObject, GParser, ParsedG
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService


FUSE_TABLE_ID = 13513
FUSE_DOMAIN = 40
FUSE_CLASSIFICATION = "FUSE"
FUSE_NAME_PREFIX = "FUSE"


class FuseParser:
    """Recognize element-catalog FUSE objects and bind each to its nearest pole transformer.

    Fuse identity is deliberately derived from the nearest TRANSFORMER_OH-classified device instead of
    the fuse object's XML key_name/p_NameString.  The sequence is strict:
    first lock the geometrically nearest Transformer_OH, then use that
    transformer's Jeddah standalone naming rule (pure-numeric + white +
    no-background Text, TOP -> RIGHT -> GLOBAL, rectangle minimum-edge distance <= 300).
    """

    @staticmethod
    def _is_fuse_object(obj: GObject, element_catalog=None) -> bool:
        record = resolve_element_record(
            str(obj.attrs.get("devref") or ""),
            element_catalog,
        )
        return classification_is(record, FUSE_CLASSIFICATION)

    @staticmethod
    def _box_distance(a: GObject, b_row: dict) -> float:
        """Shortest rectangle-to-rectangle distance in G-file coordinate units."""
        ax1, ay1 = float(a.box.x), float(a.box.y)
        ax2, ay2 = ax1 + float(a.box.w), ay1 + float(a.box.h)
        bx1, by1 = float(b_row.get("x") or 0), float(b_row.get("y") or 0)
        bx2 = bx1 + float(b_row.get("w") or 0)
        by2 = by1 + float(b_row.get("h") or 0)
        dx = max(bx1 - ax2, ax1 - bx2, 0.0)
        dy = max(by1 - ay2, ay1 - by2, 0.0)
        return math.hypot(dx, dy)

    def discover(self, parsed: ParsedG, element_catalog=None, name_settings=None):
        # FUSE always chooses the nearest Transformer_OH first.  Each transformer's
        # graphical name is prepared with exactly the same Jeddah rule used by the
        # standalone pole-transformer model: global pure-numeric/white/no-background
        # Text pool, TOP -> RIGHT -> GLOBAL direction priority, rectangle-to-
        # rectangle minimum-edge distance, <= 300, with one-to-one Text ownership.
        transformer_rows, transformer_context = TransformerParser().discover_for_transformer_model(
            parsed,
            element_catalog,
            name_settings,
        )

        # One FUSE may own at most one Transformer_OH, and one Transformer_OH may
        # be owned by at most one FUSE.  The rule is intentionally strict:
        # each FUSE first nominates only its single geometrically nearest
        # Transformer_OH.  If several FUSE objects nominate the same transformer,
        # the closest FUSE wins and all other claims remain unmatched; they do
        # NOT fall back to a second-nearest transformer.  This preserves the
        # field rule "FUSE -> its nearest transformer" and prevents the same
        # transformer/name from being reused by multiple FUSE objects.
        fuse_objects = [
            obj for obj in parsed.objects
            if self._is_fuse_object(obj, element_catalog)
        ]
        nearest_claims = []
        for fuse_index, obj in enumerate(fuse_objects):
            ranked = []
            for transformer_index, transformer in enumerate(transformer_rows):
                ranked.append((
                    self._box_distance(obj, transformer),
                    transformer_index,
                    transformer,
                ))
            ranked.sort(key=lambda item: (item[0], item[1]))
            if ranked:
                distance, transformer_index, transformer = ranked[0]
                nearest_claims.append((
                    distance,
                    transformer_index,
                    fuse_index,
                    obj,
                    transformer,
                ))
            else:
                nearest_claims.append((
                    float("inf"),
                    -1,
                    fuse_index,
                    obj,
                    {},
                ))

        claims_by_transformer = defaultdict(list)
        for claim in nearest_claims:
            transformer = claim[4]
            transformer_xml_id = str(transformer.get("xml_id") or "").strip()
            if transformer_xml_id:
                claims_by_transformer[transformer_xml_id].append(claim)

        winning_fuse_by_transformer = {}
        for transformer_xml_id, claims in claims_by_transformer.items():
            # Shortest FUSE->transformer distance wins.  XML/G order is only a
            # deterministic tie-breaker when two distances are exactly equal.
            winner = min(claims, key=lambda item: (item[0], item[2]))
            winning_fuse_by_transformer[transformer_xml_id] = winner[2]

        rows = []
        for distance, _transformer_index, fuse_index, obj, nearest in nearest_claims:
            transformer_xml_id = str(nearest.get("xml_id") or "").strip()
            assigned = bool(
                transformer_xml_id
                and winning_fuse_by_transformer.get(transformer_xml_id) == fuse_index
            )
            competing_claims = claims_by_transformer.get(transformer_xml_id, [])
            owner_fuse_xml_id = ""
            if transformer_xml_id and not assigned:
                owner_index = winning_fuse_by_transformer.get(transformer_xml_id)
                if owner_index is not None and 0 <= owner_index < len(fuse_objects):
                    owner_fuse_xml_id = str(fuse_objects[owner_index].xml_id or "").strip()

            transformer_name = (
                str(nearest.get("graphical_name") or "").strip()
                if assigned
                else ""
            )
            derived_name = (
                f"{FUSE_NAME_PREFIX}{transformer_name}"
                if transformer_name
                else ""
            )
            attrs = obj.attrs
            rows.append({
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": str(attrs.get("devref") or "").strip(),
                # Keep the nearest candidate visible in reports even for an
                # unmatched FUSE so statistics explain why it was not processed.
                "nearest_transformer_xml_id": transformer_xml_id,
                "nearest_transformer_name": transformer_name,
                "nearest_transformer_distance": "" if math.isinf(distance) else distance,
                "transformer_assignment_status": (
                    "MATCHED"
                    if assigned
                    else ("NO_TRANSFORMER" if not transformer_xml_id else "NOT_ASSIGNED")
                ),
                "transformer_assignment_reason": (
                    "NEAREST_TRANSFORMER_ASSIGNED"
                    if assigned
                    else (
                        "NO_TRANSFORMER_OH_IN_DRAWING"
                        if not transformer_xml_id
                        else "NEAREST_TRANSFORMER_ALREADY_ASSIGNED_TO_CLOSER_FUSE"
                    )
                ),
                "transformer_owner_fuse_xml_id": owner_fuse_xml_id,
                "transformer_claim_count": len(competing_claims),
                "transformer_name_direction": str(nearest.get("name_direction") or "").strip() if assigned else "",
                "transformer_name_priority": str(nearest.get("name_priority") or "").strip() if assigned else "",
                "transformer_name_distance": nearest.get("name_distance", "") if assigned else "",
                "transformer_name_xml_id": str(nearest.get("name_xml_id") or "").strip() if assigned else "",
                "nearest_transformer_name_candidates": list(nearest.get("name_candidates") or []) if assigned else [],
                "transformer_name_distance_basis": str(nearest.get("name_distance_basis") or "").strip() if assigned else "",
                "derived_fuse_name": derived_name,
                "selected_device_name": derived_name,
                "current_keyid": str(attrs.get("keyid") or "").strip(),
                "status": "",
                "severity": "",
                "reason": "",
            })
        return rows, {
            "transformer_rows": transformer_rows,
            "transformer_context": transformer_context,
            "matched_fuse_count": sum(1 for row in rows if row.get("transformer_assignment_status") == "MATCHED"),
            "unmatched_fuse_count": sum(1 for row in rows if row.get("transformer_assignment_status") != "MATCHED"),
        }


class FuseModelModule(ModelModule):
    module_id = "FUSE"
    display_name = "熔断器模型"
    description = (
        "只识别图元管理中分类为 FUSE 的图元；每个熔断器只提名几何位置最近的 Transformer_OH 柱上变压器，"
        "同一柱上变压器只能分配给一个 FUSE，冲突时距离更近的 FUSE 获得该变压器，其余 FUSE 仅统计、不关联，且不再改找第二近变压器；"
        "已分配的 FUSE 继续以该柱上变压器自身为中心找名称，并完全采用吉达柱上变压器模型规则：全图候选必须为纯数字、白色、无背景 Text，"
        "方向优先级固定为上方 → 右方 → 全局兜底，同级按柱上变压器矩形框与 Text 矩形框的最小边缘距离最近，最大距离 300；随后校验 13505 唯一性，"
        "并以 FUSE + 变压器名称作为熔断器 NAME，在 13513 / dms_disconnector_device 中按图级馈线唯一匹配，Domain=40 安全关联。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "FUSE(classification)": {
                "table_id": FUSE_TABLE_ID,
                "table_name": "dms_disconnector_device",
                "domain": FUSE_DOMAIN,
                "match_mode": "FUSE_MARK->ONE_TO_ONE_NEAREST_TRANSFORMER_OH->FUSE+TRANSFORMER_NAME",
                "description": (
                    "图元管理分类 FUSE → 每个 FUSE 只提名最近 Transformer_OH；同一变压器只允许一个 FUSE 使用，"
                    "冲突时最近的 FUSE 获得变压器，其他 FUSE 仅统计且不再寻找第二近变压器 → 已分配变压器按柱上变压器模型规则找名称：全图纯数字、白色、无背景 Text，"
                    "方向优先级上方 → 右方 → 全局兜底，同级按柱上变压器矩形框与 Text 矩形框的最小边缘距离最近，最大距离 300 → 校验 13505 唯一性 → NAME='FUSE'+变压器名称 → 13513/dms_disconnector_device，"
                    "且 FEEDER_ID 必须等于图级馈线；Domain=40。"
                ),
            }
        }

    @staticmethod
    def _make_expected_keyid(device_id):
        device_id = int(device_id)
        if device_id < 0:
            raise ValueError(f"Invalid fuse device_id: {device_id}")
        return device_id + (FUSE_DOMAIN << 32)

    @staticmethod
    def _attributes_for_row(row):
        return {
            "app": "6500000",
            "voltype": str(row.get("db_bv_id") or "0"),
            "p_ReportType": "1",
            "state": "41",
            "keyid": str(row["expected_keyid"]),
        }

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

    def _current_link_fields(self, row, db):
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
            if current_id is not None and row.get("current_table_id") == FUSE_TABLE_ID:
                current = db.get_device_by_id(FUSE_TABLE_ID, current_id)
                if current:
                    row["current_db_name"] = norm(current.get("name"))
                    row["current_db_code"] = norm(current.get("code"))
                    row["current_feeder_id"] = str(current.get("feeder_id") or "").strip()
            row["current_model_status"] = "DECODED"
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"

    def _resolve_transformer_name_for_fuse(
        self, row, db, feeder_resolution, used_transformer_name_text_ids=None
    ):
        """Validate the name already selected for the nearest transformer.

        Geometry is authoritative for name ownership and is completed before
        this method runs by ``discover_for_transformer_model``.  Therefore FUSE
        does not re-rank Text by database uniqueness and does not steal a Text
        allocated to another Transformer_OH.  It validates only the selected
        TOP/RIGHT/GLOBAL graphical name in 13505, matching the standalone
        pole-transformer model's semantics.
        """
        name = str(row.get("nearest_transformer_name") or "").strip()
        text_xml_id = str(row.get("transformer_name_xml_id") or "").strip()

        # Compatibility for lightweight tests/previews without transformer DB API.
        if not hasattr(db, "get_transformer_devices_by_name"):
            row["derived_fuse_name"] = f"{FUSE_NAME_PREFIX}{name}" if name else ""
            return row

        if not name:
            row["transformer_name_resolution_status"] = "NO_GRAPHICAL_NAME"
            row["transformer_name_resolution_trace"] = ""
            row["nearest_transformer_db_device_id"] = ""
            row["nearest_transformer_feeder_id"] = ""
            row["derived_fuse_name"] = ""
            row["transformer_feeder_mismatch"] = "NO"
            return row

        if used_transformer_name_text_ids is not None and text_xml_id:
            if text_xml_id in used_transformer_name_text_ids:
                row["transformer_name_resolution_status"] = "TEXT_ALREADY_USED"
                row["transformer_name_resolution_trace"] = f"{name}:TEXT_ALREADY_USED"
                row["nearest_transformer_name"] = ""
                row["nearest_transformer_db_device_id"] = ""
                row["nearest_transformer_feeder_id"] = ""
                row["derived_fuse_name"] = ""
                row["transformer_feeder_mismatch"] = "NO"
                return row

        try:
            records = db.get_transformer_devices_by_name(
                name,
                feeder_id=None,
                table_id=13505,
            ) or []
            row["transformer_name_resolution_trace"] = f"{name}:MATCH={len(records)}"
        except Exception as exc:
            records = []
            row["transformer_name_resolution_trace"] = f"{name}:DB_ERROR:{exc}"

        # The graphical name belongs to the Transformer_OH and must remain
        # visible even when 13505 validation fails.  The standalone
        # transformer report behaves the same way: geometry determines the
        # displayed name; database uniqueness only determines whether the row
        # is safe to associate.  Do not erase the graphical name here.
        row["transformer_13505_match_count"] = len(records)
        if len(records) == 1:
            record = records[0]
            row["transformer_name_resolution_status"] = "UNIQUE_13505"
            row["nearest_transformer_db_device_id"] = int_or_none(record.get("id"))
            row["nearest_transformer_feeder_id"] = str(record.get("feeder_id") or "").strip()
            if used_transformer_name_text_ids is not None and text_xml_id:
                used_transformer_name_text_ids.add(text_xml_id)
        else:
            # Keep both the fixed Transformer_OH and its graphically selected
            # Text name.  A non-unique 13505 result blocks association later,
            # but must not be misreported as "name not found".
            row["transformer_name_resolution_status"] = "NO_UNIQUE_13505_CANDIDATE"
            row["nearest_transformer_db_device_id"] = ""
            row["nearest_transformer_feeder_id"] = ""

        row["derived_fuse_name"] = f"{FUSE_NAME_PREFIX}{name}" if name else ""

        graph_feeder_id = int_or_none(feeder_resolution.get("feeder_id")) if feeder_resolution.get("ready") else None
        transformer_feeder_id = int_or_none(row.get("nearest_transformer_feeder_id"))
        if (
            graph_feeder_id is not None
            and transformer_feeder_id is not None
            and transformer_feeder_id != graph_feeder_id
        ):
            row["transformer_feeder_mismatch"] = "YES"
        else:
            row["transformer_feeder_mismatch"] = "NO"
        return row

    def _resolve_row(
        self,
        row,
        db,
        feeder_resolution,
        used_transformer_name_text_ids=None,
    ):
        # FUSE objects without a unique one-to-one transformer assignment are
        # statistics-only rows.  Do not query 13505/13513, do not decode KeyID,
        # and never let them enter preview/apply.
        if row.get("transformer_assignment_status") not in (None, "", "MATCHED"):
            add_feeder_fields(row, feeder_resolution)
            row.update({
                "selected_device_name": "",
                "table_id": FUSE_TABLE_ID,
                "table_name": "dms_disconnector_device",
                "configured_domain": FUSE_DOMAIN,
                "db_match_count": 0,
                "db_device_id": "",
                "db_code": "",
                "db_name": "",
                "db_feeder_id": "",
                "db_bv_id": "",
                "expected_keyid": "",
                "expected_keyid_verified": "NO",
                "model_link_correct": "NO",
                "model_link_status": "未分配独占柱上变压器，仅统计",
                "association_action": "仅统计，不处理",
                "association_ready": "NO",
                "writeback_needed": "NO",
                "status": "INFO",
                "severity": "INFO",
                "reason": (
                    "FUSE_TRANSFORMER_NOT_ASSIGNED: 最近 Transformer_OH 已分配给距离更近的 FUSE；"
                    f"占用FUSE_XML_ID={row.get('transformer_owner_fuse_xml_id') or '-'}。"
                    if row.get("transformer_assignment_status") == "NOT_ASSIGNED"
                    else "FUSE_TRANSFORMER_NOT_FOUND: 当前图中没有可供该 FUSE 使用的 Transformer_OH。"
                ),
            })
            return row

        self._resolve_transformer_name_for_fuse(
            row,
            db,
            feeder_resolution,
            used_transformer_name_text_ids,
        )
        fuse_name = str(row.get("derived_fuse_name") or "").strip()
        row.update({
            "selected_device_name": fuse_name,
            "table_id": FUSE_TABLE_ID,
            "table_name": "dms_disconnector_device",
            "configured_domain": FUSE_DOMAIN,
            "db_match_count": 0,
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_feeder_id": "",
            "db_bv_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "NO",
            "model_link_correct": "NO",
            "model_link_status": "",
            "association_action": "",
            "association_ready": "NO",
            "writeback_needed": "NO",
        })
        self._current_link_fields(row, db)

        if not str(row.get("nearest_transformer_xml_id") or "").strip():
            return self._fail(
                row,
                "FUSE_NEAREST_TRANSFORMER_NOT_FOUND: 当前 FUSE 图元附近未找到 Transformer_OH 柱上变压器。",
            )
        if not str(row.get("nearest_transformer_name") or "").strip():
            return self._fail(
                row,
                "FUSE_TRANSFORMER_NAME_NOT_FOUND: 最近 Transformer_OH 按柱上变压器模型的“纯数字 + 白色 + 无背景、上方 → 右方 → 全局、矩形框最小边缘距离、最大 300”规则未找到图形名称。",
            )
        if row.get("transformer_name_resolution_status") == "NO_UNIQUE_13505_CANDIDATE":
            return self._fail(
                row,
                "FUSE_TRANSFORMER_DATABASE_NOT_UNIQUE: "
                f"最近柱上变压器图上名称={row.get('nearest_transformer_name') or '-'}；"
                f"13505匹配数={row.get('transformer_13505_match_count', 0)}。"
                "图形名称及 FUSE 计算名称继续保留用于报告，但 13505 目标不唯一，禁止进入关联流程。",
            )
        if row.get("transformer_feeder_mismatch") == "YES":
            return self._fail(
                row,
                "FUSE_TRANSFORMER_FEEDER_MISMATCH: 最近柱上变压器的 13505.FEEDER_ID 与当前图级馈线不一致。",
            )
        if not feeder_resolution.get("ready"):
            enforce_device_feeder_membership(
                row,
                feeder_resolution,
                device_feeder_id=None,
                reason_prefix="FUSE",
            )
            return row

        graph_feeder_id = int_or_none(feeder_resolution.get("feeder_id"))
        records = db.get_disconnector_devices_by_name(
            fuse_name,
            feeder_id=graph_feeder_id,
            table_id=FUSE_TABLE_ID,
        )
        row["db_match_count"] = len(records)
        if len(records) != 1:
            enforce_device_feeder_membership(
                row,
                feeder_resolution,
                device_feeder_id=None,
                reason_prefix="FUSE",
            )
            return self._fail(
                row,
                "FUSE_DATABASE_NOT_UNIQUE: "
                f"13513/dms_disconnector_device NAME={fuse_name}，"
                f"FEEDER_ID={graph_feeder_id}；匹配数={len(records)}。",
            )

        device = records[0]
        device_id = int_or_none(device.get("id"))
        if device_id is None:
            return self._fail(row, "FUSE_DEVICE_ID_INVALID: 13513.ID 无效。")
        bv_id = str(device.get("bv_id") or "").strip()
        if not bv_id:
            return self._fail(row, "FUSE_BV_ID_EMPTY: 13513.BV_ID 为空，禁止回写 voltype。")

        expected = self._make_expected_keyid(device_id)
        row.update({
            "db_device_id": device_id,
            "db_code": norm(device.get("code")),
            "db_name": norm(device.get("name")),
            "db_feeder_id": str(device.get("feeder_id") or "").strip(),
            "db_bv_id": bv_id,
            "expected_keyid": expected,
        })

        enforce_device_feeder_membership(
            row,
            feeder_resolution,
            device_feeder_id=row.get("db_feeder_id"),
            reason_prefix="FUSE",
        )
        if row.get("association_ready") == "NO" and row.get("status") == "FAIL":
            return row

        try:
            decoded = db.verify_keyid(expected)
            verified = (
                int_or_none(decoded.get("device_id")) == device_id
                and int_or_none(decoded.get("tab_no")) == FUSE_TABLE_ID
                and int_or_none(decoded.get("col_no")) == FUSE_DOMAIN
            )
        except Exception as exc:
            return self._fail(row, f"FUSE_EXPECTED_KEYID_VERIFY_ERROR: {exc}")
        row["expected_keyid_verified"] = "YES" if verified else "NO"
        if not verified:
            return self._fail(
                row,
                "FUSE_EXPECTED_KEYID_VERIFY_FAILED: Expected KeyID 未通过 13513/domain=40 校验。",
            )

        if int_or_none(row.get("current_keyid")) == expected:
            row.update({
                "status": "PASS",
                "severity": "PASS",
                "model_link_correct": "YES",
                "model_link_status": "当前 KeyID 正确",
                "association_action": "无需回写",
                "writeback_needed": "NO",
                "association_ready": "YES",
                "reason": "FUSE_MODEL_LINK_CORRECT",
            })
        else:
            has_current = bool(str(row.get("current_keyid") or "").strip())
            row.update({
                "status": "RELINK" if has_current else "UNLINKED",
                "severity": "RELINK" if has_current else "WARN",
                "model_link_correct": "NO",
                "model_link_status": (
                    "当前 KeyID 为空，尚未关联"
                    if not has_current
                    else "当前 KeyID 不是目标 13513/domain=40"
                ),
                "association_action": "重新关联熔断器" if has_current else "关联熔断器",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "reason": "FUSE_ASSOCIATION_READY",
            })
        return row

    def _analyze_file(self, db, g_file, settings=None, log_callback=None, progress_callback=None):
        settings = settings or {}
        parsed = GParser().parse(g_file)
        feeder_resolution = resolve_drawing_feeder(
            db,
            parsed,
            settings,
            log_callback=log_callback,
        )
        discovered, _context = FuseParser().discover(
            parsed,
            settings.get("element_catalog", {}) or {},
            settings,
        )
        rows = []
        used_transformer_name_text_ids = set()
        total = max(len(discovered), 1)
        for index, row in enumerate(discovered, start=1):
            resolved = self._resolve_row(
                dict(row),
                db,
                feeder_resolution,
                used_transformer_name_text_ids,
            )
            resolved["file_name"] = Path(g_file).name
            rows.append(resolved)
            if log_callback:
                log_callback(
                    f"[发现熔断器] 文件={Path(g_file).name}；"
                    f"XML_ID={resolved.get('xml_id') or '-'}；"
                    f"变压器分配={resolved.get('transformer_assignment_status') or '-'}；"
                    f"最近柱上变压器={resolved.get('nearest_transformer_name') or '-'}；"
                    f"变压器XML_ID={resolved.get('nearest_transformer_xml_id') or '-'}；"
                    f"设备距离={resolved.get('nearest_transformer_distance') if resolved.get('nearest_transformer_distance') not in (None, '') else '-'}；"
                    f"变压器占用FUSE={resolved.get('transformer_owner_fuse_xml_id') or '-'}；"
                    f"分配说明={resolved.get('transformer_assignment_reason') or '-'}；"
                    f"变压器名称方向={resolved.get('transformer_name_direction') or '-'}；"
                    f"变压器名称距离={resolved.get('transformer_name_distance') if resolved.get('transformer_name_distance') not in (None, '') else '-'}；"
                    f"变压器名称判定={resolved.get('transformer_name_resolution_trace') or '-'}；"
                    f"熔断器名称={resolved.get('derived_fuse_name') or '-'}；"
                    f"DB_ID={resolved.get('db_device_id') or '-'}；"
                    f"FEEDER_ID={resolved.get('db_feeder_id') or '-'}；"
                    f"状态={resolved.get('status') or '-'}。"
                )
            if progress_callback:
                progress_callback(index, total, f"正在处理熔断器 {index}/{len(discovered)}")

        feeder = feeder_resolution.get("feeder") or {}
        feeder_id = feeder_resolution.get("feeder_id", "")
        feeder_name = str(feeder.get("display_name") or feeder.get("name") or "").strip()
        report = {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "FUSE",
            "fuse_rows": rows,
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
                "图级馈线唯一由 G 文件名 → 405/substation → 13500/dms_feeder_device 确认；"
                "每个熔断器的 13513.FEEDER_ID 必须与该图级馈线完全一致。"
                if feeder_resolution.get("ready")
                else feeder_resolution.get("reason", "图级馈线无法确认。")
            ),
            "summary": {
                "fuse_count": len(rows),
                "fuse_transformer_matched": sum(1 for row in rows if row.get("transformer_assignment_status") == "MATCHED"),
                "fuse_transformer_unmatched": sum(1 for row in rows if row.get("transformer_assignment_status") != "MATCHED"),
                "fuse_statistics_only": sum(1 for row in rows if row.get("transformer_assignment_status") != "MATCHED"),
                "fuse_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "fuse_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "fuse_statistics_only_info": sum(1 for row in rows if row.get("status") == "INFO"),
                "fuse_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "fuse_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES"),
                "feeder_context_ready": "YES" if feeder_resolution.get("ready") else "NO",
            },
        }
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 熔断器识别完成：FUSE总数={len(discovered)}；"
                f"已独占匹配柱上变压器={sum(1 for row in rows if row.get('transformer_assignment_status') == 'MATCHED')}；"
                f"仅统计不处理={sum(1 for row in rows if row.get('transformer_assignment_status') != 'MATCHED')}；"
                f"图级馈线={feeder_id or '-'}；"
                f"数据库可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
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
            db,
            files,
            settings,
            log_callback,
            progress_callback,
        )
        changes_by_file = defaultdict(list)
        rows = []
        for report in reports:
            for row in report.get("fuse_rows", []):
                if row.get("association_ready") != "YES" or row.get("writeback_needed") != "YES":
                    continue
                change = {
                    "xml_id": row["xml_id"],
                    "tag": row.get("object_type") or "ZhaiWaiDaoZha",
                    "_source_file": report["g_file"],
                    "attributes": self._attributes_for_row(row),
                    "device_name": row.get("derived_fuse_name", ""),
                    "device_id": row.get("db_device_id", ""),
                    "expected_keyid": row.get("expected_keyid", ""),
                    "validated_row": dict(row),
                }
                changes_by_file[report["g_file"]].append(change)
                output_row = dict(row)
                output_row["reason"] = (
                    "PREVIEW_WRITE app=6500000 "
                    f"voltype={row.get('db_bv_id') or '0'} p_ReportType=1 state=41 "
                    f"keyid={row.get('expected_keyid', '')}"
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
                "fuse_table_id": FUSE_TABLE_ID,
                "fuse_domain": FUSE_DOMAIN,
                "element_catalog": settings.get("element_catalog", {}),
            },
        }

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        if not preview_data or not preview_data.get("changes_by_file"):
            raise RuntimeError("没有可执行的熔断器模型关联结果。")
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
                raise RuntimeError(
                    f"G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验：{source_file}"
                )

        refreshed_reports_by_file = {}
        for source_file, changes in changes_by_file.items():
            # Re-run feeder resolution, nearest-transformer selection, 13513 lookup and
            # KeyID verification immediately before writing selected XML IDs.
            refreshed_report = self._analyze_file(
                db,
                Path(source_file),
                settings,
                log_callback,
            )
            refreshed_reports_by_file[str(source_file)] = refreshed_report
            refreshed_by_xml = {
                str(row.get("xml_id") or ""): row
                for row in refreshed_report.get("fuse_rows", [])
            }
            for change in changes:
                current = dict(refreshed_by_xml.get(str(change.get("xml_id") or ""), {}))
                if (
                    not current
                    or current.get("association_ready") != "YES"
                    or current.get("writeback_needed") != "YES"
                ):
                    if not current:
                        current = dict(change.get("validated_row", {}) or {})
                        current["reason"] = "FUSE_EXECUTION_TARGET_NOT_FOUND"
                    current["_execution_result"] = "SKIPPED"
                    execution_rows.append((change, current))
                    continue
                refreshed = dict(change)
                refreshed["tag"] = current.get("object_type") or refreshed.get("tag")
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
            item["reason"] = (
                "ASSOCIATION_EXECUTED"
                if item["status"] == "PASS"
                else item.get("reason", "EXECUTION_SKIPPED")
            )
            by_file[str(change.get("_source_file") or "")].append(item)
        for source_file, rows in by_file.items():
            refreshed_report = refreshed_reports_by_file.get(str(source_file), {}) or {}
            operation_reports.append({
                "g_file": source_file,
                "file_name": Path(source_file).name,
                "report_type": "FUSE",
                "fuse_rows": rows,
                # Keep the compact feeder-decision card in the operation-scoped
                # result report as well.  The full internal evidence stays hidden.
                "feeder_resolution_source": refreshed_report.get("feeder_resolution_source", "UNRESOLVED"),
                "feeder_anchor": refreshed_report.get("feeder_anchor", ""),
                "feeder_id": refreshed_report.get("feeder_id", ""),
                "station_id": refreshed_report.get("station_id", ""),
                "station_name": refreshed_report.get("station_name", ""),
                "subcontrolarea_path": refreshed_report.get("subcontrolarea_path", ""),
                "feeder_code": refreshed_report.get("feeder_code", ""),
                "feeder_graph_name": refreshed_report.get("feeder_graph_name", ""),
                "feeder_name": refreshed_report.get("feeder_name", ""),
                "feeder_path": refreshed_report.get("feeder_path", ""),
                "feeder_context_ready": refreshed_report.get("feeder_context_ready", "NO"),
                "feeder_context_message": refreshed_report.get("feeder_context_message", ""),
                "summary": {"fuse_count": len(rows)},
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
