#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

from dmm.domain.gfile.parser import GParser, RmuFrame, GObject
from dmm.config.constants import (
    RMU_RELAY_SIGNAL_CODE,
    RMU_RELAY_SIGNAL_DEVREF,
    RMU_RELAY_SIGNAL_TAG,
    RMU_RELAY_SIGNAL_TABLE_ID,
)
from dmm.infrastructure.database.oracle import OracleClient

KEYID_STEP = 2 ** 32


def norm(v) -> str:
    return "" if v is None else str(v).strip()


def int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def is_no_rmu_name(value) -> bool:
    """Return whether a graphical RMU name is a Jazan NO placeholder.

    ``NO`` and names beginning with ``NO-`` are placeholders which are
    resolved from the drawing feeder and an unused database RMU.  ``NOP`` is
    deliberately not included: it is the Normally Open Point status label
    and is filtered by the parser before RMU name resolution.
    """
    key = norm(value).casefold()
    return key == "no" or key.startswith("no-")


def resolve_duplicate_name_records(
    records,
    entity_code,
    source_feeder_id=None,
):
    """Resolve same-name rows with an optional drawing-level FEEDER_ID.

    Jazan exports can contain the same RMU NAME on different feeders.  The
    feeder is inferred once from a uniquely identified RMU in the same G file;
    that value is then used to choose the concrete parent row before querying
    child tables by COMBINED_ID.
    """
    all_records = list(records or [])
    requested_feeder = int_or_none(source_feeder_id)

    if requested_feeder is not None:
        matching_records = [
            row
            for row in all_records
            if int_or_none(row.get("feeder_id")) == requested_feeder
        ]
        if len(matching_records) == 1:
            return {
                "records": matching_records,
                "all_records": all_records,
                "status": (
                    "DUPLICATE_RESOLVED_BY_DIAGRAM_FEEDER"
                    if len(all_records) > 1
                    else "UNIQUE_NAME"
                ),
                "reason": (
                    f"{entity_code}_DUPLICATE_NAME_RESOLVED_BY_DIAGRAM_FEEDER: "
                    f"按本张G图推断的 FEEDER_ID={requested_feeder} 选择数据库记录。"
                    if len(all_records) > 1
                    else ""
                ),
                "feeder_ids": sorted({
                    feeder_id
                    for feeder_id in (
                        int_or_none(row.get("feeder_id"))
                        for row in all_records
                    )
                    if feeder_id is not None
                }),
            }
        if len(matching_records) > 1:
            return {
                "records": matching_records,
                "all_records": all_records,
                "status": "DUPLICATE_SAME_FEEDER",
                "reason": (
                    f"{entity_code}_DUPLICATE_NAME_SAME_FEEDER: "
                    f"按本张G图 FEEDER_ID={requested_feeder} 筛选后仍有 "
                    f"{len(matching_records)} 条同名记录。"
                ),
                "feeder_ids": sorted({
                    feeder_id
                    for feeder_id in (
                        int_or_none(row.get("feeder_id"))
                        for row in all_records
                    )
                    if feeder_id is not None
                }),
            }
        return {
            "records": [],
            "all_records": all_records,
            "status": "DUPLICATE_DIAGRAM_FEEDER_NOT_FOUND",
            "reason": (
                f"{entity_code}_DUPLICATE_NAME_DIAGRAM_FEEDER_NOT_FOUND: "
                f"本张G图推断的 FEEDER_ID={requested_feeder} 在同名数据库记录中不存在。"
            ),
            "feeder_ids": sorted({
                feeder_id
                for feeder_id in (
                    int_or_none(row.get("feeder_id"))
                    for row in all_records
                )
                if feeder_id is not None
            }),
        }

    if len(all_records) <= 1:
        return {
            "records": all_records,
            "all_records": all_records,
            "status": "UNIQUE_NAME",
            "reason": "",
            "feeder_ids": sorted({
                feeder_id
                for feeder_id in (
                    int_or_none(row.get("feeder_id"))
                    for row in all_records
                )
                if feeder_id is not None
            }),
        }

    feeder_values = [int_or_none(row.get("feeder_id")) for row in all_records]
    feeder_ids = sorted({item for item in feeder_values if item is not None})
    if any(item is None for item in feeder_values):
        return {
            "records": all_records,
            "all_records": all_records,
            "status": "DUPLICATE_FEEDER_UNRESOLVED",
            "reason": (
                f"{entity_code}_DUPLICATE_NAME_FEEDER_UNRESOLVED: "
                "名称存在多条数据库记录，但其中存在空的 FEEDER_ID。"
            ),
            "feeder_ids": feeder_ids,
        }

    if len(set(feeder_values)) == len(feeder_values):
        return {
            # The existing association pipeline requires one target row.  The
            # duplicate is safe because FEEDER_ID separates the records; keep
            # the first database row as the concrete target while retaining
            # all rows for diagnostics.
            "records": [all_records[0]],
            "all_records": all_records,
            "status": "DUPLICATE_RESOLVED_BY_FEEDER",
            "reason": (
                f"{entity_code}_DUPLICATE_NAME_DIFFERENT_FEEDER: "
                f"名称重复，但 FEEDER_ID 分别为={','.join(str(x) for x in feeder_values)}。"
            ),
            "feeder_ids": feeder_ids,
        }

    return {
        "records": all_records,
        "all_records": all_records,
        "status": "DUPLICATE_SAME_FEEDER",
        "reason": (
            f"{entity_code}_DUPLICATE_NAME_SAME_FEEDER: "
            f"名称重复，且 FEEDER_ID={','.join(str(x) for x in feeder_values)} 中存在重复。"
        ),
        "feeder_ids": feeder_ids,
    }


class RmuValidator:
    def __init__(
        self,
        db: OracleClient,
        parser: GParser,
        device_rules: Dict[str, Dict[str, Any]],
        breaker_name_source: str = "GRAPHICAL_TEXT",
        log=None,
    ):
        self.db = db
        self.parser = parser
        self.device_rules = device_rules
        # Field rule: switch names are always taken from visible G text.
        # The XML p_NameString attribute is never a device-name source.
        # Keep the constructor argument only for backward compatibility with
        # older callers/settings, but intentionally ignore its value.
        self.breaker_name_source = "GRAPHICAL_TEXT"
        self.log = log or (lambda msg: None)

    @staticmethod
    def _is_normal_relay_signal(elem):
        """Match only the explicitly designated EFI G element."""
        if elem.tag != RMU_RELAY_SIGNAL_TAG:
            return False
        devref = norm(elem.attrs.get("devref"))
        file_part = devref.lstrip("#").split(":", 1)[0].replace("\\", "/")
        return file_part.rsplit("/", 1)[-1].casefold() == RMU_RELAY_SIGNAL_DEVREF

    @staticmethod
    def _relay_keyid(elem):
        """NariPd_Normal uses slot 1 for the EFI value KeyID."""
        return norm(elem.attrs.get("keyid1"))

    def _resolve_rmu_name(
        self,
        parsed,
        frame: RmuFrame,
        positions: Sequence[str],
        preassigned_candidates=None,
        source_feeder_id=None,
    ):
        frame_key = (frame.frame.xml_index, frame.frame.xml_id)
        if preassigned_candidates is None:
            all_candidates = self.parser.find_label_candidates(
                parsed,
                frame,
                positions,
            )
        else:
            all_candidates = list(
                preassigned_candidates.get(frame_key, [])
            )
        frame.label_candidates = all_candidates

        if not all_candidates:
            return {
                "status": "FAIL",
                "reason": (
                    "RMU_NAME_NOT_PARSED: "
                    "在指定的环网柜名称方向内未解析到有效名称文字"
                ),
                "candidate_rows": [],
                "selected": None,
            }

        # --------------------------------------------------------------
        # RMU name selection rule
        # --------------------------------------------------------------
        # 1. Candidate ownership has already been resolved by GParser:
        #    one Text can belong to only one nearest RMU frame.
        #
        # 2. The parser has already reduced the selected-direction candidates
        #    to one nearest Text. Color is not a naming priority.
        # --------------------------------------------------------------
        ordered = sorted(
            all_candidates,
            key=lambda c: (
                c.score,
                c.obj.xml_index,
                c.text,
            ),
        )

        chosen = ordered[0]
        selection_reason = "SINGLE_NEAREST_DIRECTION_LABEL"

        chosen_name = norm(getattr(chosen, "text", ""))
        if not chosen_name:
            return {
                "status": "FAIL",
                "reason": (
                    "RMU_NAME_NOT_PARSED: "
                    "已找到候选文字对象，但解析后的环网柜名称为空"
                ),
                "candidate_rows": [],
                "selected": None,
            }

        candidate_rows = []
        selected_row = None
        resolution_cache = {}

        def resolve_records(name):
            key = norm(name)
            if key not in resolution_cache:
                raw_records = self.db.get_rmu_records(key)
                resolution_cache[key] = resolve_duplicate_name_records(
                    raw_records,
                    "RMU",
                    source_feeder_id=source_feeder_id,
                )
            return resolution_cache[key]

        for c in all_candidates:
            resolution = resolve_records(c.text)
            records = resolution["records"]
            row = {
                "name": c.text,
                "directions": c.direction,
                "best_score": c.score,
                "distance": c.gap,
                "color": c.color,
                "is_green": "YES" if c.is_green else "NO",
                "xml_id": c.obj.xml_id,
                "db_count": len(records),
                "db_records": records,
                "db_all_records": resolution["all_records"],
                "db_all_count": len(resolution["all_records"]),
                "db_feeder_ids": resolution["feeder_ids"],
                "db_resolution": resolution["status"],
                "selected_by_rule": "YES" if c is chosen else "NO",
                "selection_reason": (
                    selection_reason if c is chosen else ""
                ),
            }
            candidate_rows.append(row)

            if c is chosen:
                selected_row = row

        resolution = resolve_records(chosen_name)
        records = resolution["records"]

        if len(records) == 1:
            return {
                "status": "PASS",
                "reason": (
                    resolution["reason"]
                    if resolution["status"] in {
                        "DUPLICATE_RESOLVED_BY_FEEDER",
                        "DUPLICATE_RESOLVED_BY_DIAGRAM_FEEDER",
                    }
                    else (
                        "RMU_CONFIRMED_SINGLE_LABEL"
                        if len(ordered) == 1
                        else (
                            "RMU_CONFIRMED_GREEN_LABEL"
                            if chosen.is_green
                            else "RMU_CONFIRMED_NEAREST_LABEL"
                        )
                    )
                ),
                "candidate_rows": candidate_rows,
                "selected": selected_row,
            }

        if resolution.get("reason") and resolution.get("status") != "UNIQUE_NAME":
            return {
                "status": "FAIL",
                "reason": resolution["reason"],
                "candidate_rows": candidate_rows,
                "selected": selected_row,
            }

        if len(resolution["all_records"]) > 1:
            return {
                "status": "FAIL",
                "reason": resolution["reason"] or "RMU_DUPLICATE_IN_DATABASE",
                "candidate_rows": candidate_rows,
                "selected": selected_row,
            }

        return {
            "status": "FAIL",
            "reason": "RMU_NOT_FOUND_IN_DATABASE",
            "candidate_rows": candidate_rows,
            "selected": selected_row,
        }

    @staticmethod
    def _default_device_row(
        rmu_name,
        rmu_id,
        elem,
        rule,
        db_set,
    ):
        return {
            "rmu_name": rmu_name,
            "rmu_id": rmu_id,
            "object_type": elem.tag,
            "xml_id": elem.xml_id,
            "logical_code": "",
            "graphical_name": "",
            "selected_name_source": "",
            "selected_device_name": "",
            "paired_breaker_name": "",
            "table_id": int(rule["table_id"]),
            "table_name": db_set.get("table_name", ""),
            "configured_domain": int(rule["domain"]),
            "match_mode": rule.get("match_mode", ""),
            "db_match_count": 0,
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_combined_id": "",
            "db_bv_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "",
            "current_keyid": elem.keyid,
            "current_device_id": "",
            "current_table_id": "",
            "current_domain": "",
            "current_table_name": "",
            "current_db_code": "",
            "current_db_name": "",
            "current_combined_id": "",
            "current_rmu_name": "",
            "current_rmu_match": "",
            "current_rmu_name_match": "",
            "model_linked": "YES" if elem.keyid else "NO",
            "model_link_correct": "",
            "model_link_status": "",
            "association_action": "",
            "writeback_needed": "NO",
            "association_ready": "NO",
            "status": "",
            "severity": "",
            "reason": "",
        }

    @staticmethod
    def _find_by_code(rows, code: str):
        return [r for r in rows if norm(r.get("code")) == norm(code)]

    @staticmethod
    def _set_fail(row, reason):
        row["status"] = "FAIL"
        row["severity"] = "ERROR"
        row["reason"] = reason
        row["association_ready"] = "NO"

    @staticmethod
    def _set_manual_duplicate_block(row, reason):
        row["status"] = "BLOCKED"
        row["severity"] = "MANUAL_DUPLICATE_BLOCK"
        row["reason"] = reason
        row["association_ready"] = "NO"

    @staticmethod
    def _set_rmu_link_issue(row, reason):
        """
        Hard RMU-link issue.

        Reserved for cases where the database truth itself is ambiguous
        (for example a non-unique RMU).  A UNIQUE RMU whose old G KeyID points
        elsewhere is handled by RMU_RELINK instead and remains writable.
        """
        row["status"] = "RMU_LINK"
        row["severity"] = "RMU_LINK_MISMATCH"
        row["reason"] = reason
        row["association_ready"] = "NO"

    @staticmethod
    def _set_relink(row, reason):
        """
        Correctable stale/wrong existing model.

        The current database target has already passed all hard rules:
        unique RMU, CODE == logical CODE, unique device in this RMU,
        correct RMU ownership and a valid Expected KeyID.
        """
        row["status"] = "RELINK"
        row["severity"] = "MODEL_RELINK"
        row["reason"] = reason
        row["model_link_correct"] = "NO"
        row["model_link_status"] = "旧模型关联已过期或错误，可重新关联"
        row["association_action"] = "重新关联（覆盖旧模型关联）"
        row["writeback_needed"] = "YES"
        row["association_ready"] = "YES"

    @staticmethod
    def _set_rmu_relink(row, reason):
        """
        Correctable existing model that currently points to another RMU.

        Because the current target device in the UNIQUE expected RMU has
        already been uniquely resolved from CODE/图上逻辑CODE, the old
        cross-RMU KeyID can be safely replaced.
        """
        row["status"] = "RMU_RELINK"
        row["severity"] = "RMU_RELINK"
        row["reason"] = reason
        row["model_link_correct"] = "NO"
        row["model_link_status"] = "当前模型关联到了其他环网柜，可重新关联"
        row["association_action"] = "重新关联到当前环网柜（覆盖旧模型关联）"
        row["writeback_needed"] = "YES"
        row["association_ready"] = "YES"

    @staticmethod
    def _make_expected_keyid(device_id, domain):
        """
        Build D5000 KeyID from database device ID and domain/column number.

        D5000 encoding used by this project:
            KeyID = DeviceID + (Domain << 32)

        Examples:
            domain = 0  -> KeyID == DeviceID
            domain = 40 -> DeviceID + 40 * 2^32
        """
        device_id = int(device_id)
        domain = int(domain)

        if device_id < 0:
            raise ValueError(f"Invalid device_id: {device_id}")
        if domain < 0:
            raise ValueError(f"Invalid domain: {domain}")

        return device_id + (domain << 32)

    def _verify_expected_keyid(self, row, device_id, rule):
        expected = self._make_expected_keyid(device_id, int(rule["domain"]))
        row["expected_keyid"] = expected
        try:
            v = self.db.verify_keyid(expected)
            ok = (
                int_or_none(v.get("device_id")) == device_id
                and int_or_none(v.get("tab_no")) == int(rule["table_id"])
                and int_or_none(v.get("col_no")) == int(rule["domain"])
            )
            row["expected_keyid_verified"] = "YES" if ok else "NO"
            if not ok:
                self._set_fail(
                    row,
                    "EXPECTED_KEYID_VERIFY_FAILED "
                    f"(device={v.get('device_id')}, table={v.get('tab_no')}, domain={v.get('col_no')})",
                )
                return False
            return True
        except Exception as exc:
            self._set_fail(row, f"EXPECTED_KEYID_VERIFY_ERROR: {exc}")
            return False

    def _validate_expected_device_ownership(self, row, dev, rmu_id):
        """
        Hard rule: the database device selected by CODE must belong to the
        current UNIQUE RMU.

        Even though normal database rows are queried by combined_id first, this
        explicit check makes RMU ownership a non-bypassable validation rule.
        """
        expected_rmu_id = int_or_none(rmu_id)
        actual_rmu_id = int_or_none(dev.get("combined_id"))

        if expected_rmu_id is None:
            self._set_fail(row, "EXPECTED_RMU_ID_INVALID")
            return False

        if actual_rmu_id is None:
            self._set_fail(
                row,
                "DEVICE_RMU_ID_EMPTY: "
                f"CODE={row.get('db_code') or row.get('selected_device_name') or '-'}"
            )
            return False

        if actual_rmu_id != expected_rmu_id:
            row["model_link_correct"] = "NO"
            row["association_action"] = "禁止自动关联，请检查数据库设备归属"
            self._set_rmu_link_issue(
                row,
                "DATABASE_DEVICE_RMU_MISMATCH: "
                f"CODE={row.get('db_code') or '-'}；"
                f"设备combined_id={actual_rmu_id}；"
                f"当前环网柜ID={expected_rmu_id}"
            )
            return False

        return True

    def _validate_one_to_one_device_mapping(self, rmu_result):
        """
        Hard one-to-one rule inside one G-file RMU.

        - one logical CODE may correspond to only one G target row;
        - one database device ID may be consumed by only one G target row;
        - missing database device is allowed to exist as a data-quality
          condition, but the corresponding G row remains FAIL and therefore
          blocks automatic association;
        - unrelated extra database rows are ignored.
        """
        rows = [
            row for row in rmu_result.get("device_rows", [])
            if row.get("xml_id")
        ]

        by_logical_name = defaultdict(list)
        by_device_id = defaultdict(list)

        for row in rows:
            logical_name = norm(row.get("logical_code"))
            if logical_name:
                by_logical_name[logical_name].append(row)

            device_id = int_or_none(row.get("db_device_id"))
            if device_id is not None:
                by_device_id[device_id].append(row)

        for logical_name, mapped_rows in by_logical_name.items():
            if len(mapped_rows) <= 1:
                continue

            xml_ids = ",".join(
                str(row.get("xml_id") or "-")
                for row in mapped_rows
            )
            issue = (
                "G_LOGICAL_CODE_NOT_ONE_TO_ONE: "
                f"逻辑CODE={logical_name} 在同一环网柜内被多个G图元使用；"
                f"XML_ID={xml_ids}"
            )
            rmu_result["inventory_issues"].append(issue)
            rmu_result.setdefault("device_block_reasons", []).append(issue)

            for row in mapped_rows:
                row["model_link_correct"] = "NO"
                row["association_ready"] = "NO"
                row["writeback_needed"] = "NO"
                self._set_fail(row, issue)

        for device_id, mapped_rows in by_device_id.items():
            if len(mapped_rows) <= 1:
                continue

            xml_ids = ",".join(
                str(row.get("xml_id") or "-")
                for row in mapped_rows
            )
            codes = ",".join(
                str(row.get("db_code") or "-")
                for row in mapped_rows
            )
            issue = (
                "DATABASE_DEVICE_NOT_ONE_TO_ONE: "
                f"同一个数据库设备ID={device_id} 被多个G图元占用；"
                f"CODE={codes}；XML_ID={xml_ids}"
            )
            rmu_result["db_integrity_issues"].append(issue)
            rmu_result.setdefault("device_block_reasons", []).append(issue)

            for row in mapped_rows:
                row["model_link_correct"] = "NO"
                row["association_ready"] = "NO"
                row["writeback_needed"] = "NO"
                self._set_fail(row, issue)

    def _evaluate_current_model(
        self,
        row,
        elem,
        device_id,
        rule,
        rmu_id,
        current_keyid_value=None,
        require_bv_id=True,
    ):
        """
        Evaluate the CURRENT G model only after the CURRENT DATABASE target
        has already passed all hard business rules.

        Hard truth comes from the current database:
        - RMU name resolved uniquely;
        - logical CODE / selected name resolved;
        - exactly one CODE match exists inside that RMU;
        - CODE == logical CODE;
        - matched database device belongs to the current RMU;
        - Expected KeyID is valid.

        Therefore an old G association is diagnostic, not authoritative.
        A stale/deleted device ID, old KeyID, wrong table/domain, or an old
        link to another RMU is CORRECTABLE and may be overwritten.

        Only failures in the CURRENT database target are hard blockers; those
        are handled before this method is called.
        """
        current_keyid_text = (
            elem.keyid
            if current_keyid_value is None
            else norm(current_keyid_value)
        )

        # No current model: normal association candidate.
        if not current_keyid_text:
            row["model_linked"] = "NO"
            row["model_link_correct"] = ""
            row["model_link_status"] = "未关联"

            if require_bv_id and not norm(row.get("db_bv_id")):
                row["association_action"] = "禁止自动关联"
                row["writeback_needed"] = "NO"
                row["association_ready"] = "NO"
                self._set_fail(
                    row,
                    "BV_ID_EMPTY: 数据库设备 BV_ID 为空，无法写入 voltype"
                )
                return

            row["association_action"] = "需要关联"
            row["writeback_needed"] = "YES"
            row["association_ready"] = "YES"
            row["status"] = "WARN"
            row["severity"] = "UNLINKED"
            row["reason"] = "MODEL_NOT_LINKED"
            return

        row["model_linked"] = "YES"
        row["writeback_needed"] = "NO"

        # Any corrective write-back needs the CURRENT target BV_ID.
        if require_bv_id and not norm(row.get("db_bv_id")):
            row["model_link_correct"] = "NO"
            row["model_link_status"] = "当前模型需要修复，但数据库BV_ID为空"
            row["association_action"] = "禁止自动关联"
            self._set_fail(
                row,
                "BV_ID_EMPTY: 数据库设备 BV_ID 为空，无法重新写入 voltype"
            )
            return

        current_keyid = int_or_none(current_keyid_text)

        # A malformed old keyid is not a hard database error.  The current
        # target is already uniquely known, so simply replace the old model.
        if current_keyid is None:
            row["current_keyid"] = current_keyid_text
            self._set_relink(
                row,
                "CURRENT_KEYID_INVALID: 当前G文件KeyID格式错误；"
                "数据库当前目标设备唯一且有效，允许重新关联"
            )
            return

        current_verify_error = ""
        try:
            curv = self.db.verify_keyid(current_keyid)
        except Exception as exc:
            curv = {}
            current_verify_error = str(exc)

        # Old device may have been deleted/recreated.  Failure to reverse an
        # old KeyID is therefore a RELINK condition, not FAIL.
        if current_verify_error:
            self._set_relink(
                row,
                "CURRENT_KEYID_STALE_OR_UNRESOLVABLE: "
                f"{current_verify_error}；数据库当前目标设备唯一且有效，允许重新关联"
            )
            return

        current_device_id = int_or_none(curv.get("device_id"))
        current_table_id = int_or_none(curv.get("tab_no"))
        current_domain = int_or_none(curv.get("col_no"))

        row["current_device_id"] = curv.get("device_id", "")
        row["current_table_id"] = curv.get("tab_no", "")
        row["current_domain"] = curv.get("col_no", "")

        current_record = None
        if current_device_id is not None and current_table_id is not None:
            try:
                current_record = self.db.get_device_by_id(
                    current_table_id,
                    current_device_id,
                )
            except Exception as exc:
                row["current_record_error"] = str(exc)

        if current_record:
            row["current_table_name"] = current_record.get("_table_name", "")
            row["current_db_code"] = norm(current_record.get("code"))
            row["current_db_name"] = norm(current_record.get("name"))
            row["current_combined_id"] = current_record.get(
                "combined_id", ""
            )

        current_combined_id = int_or_none(
            row.get("current_combined_id")
        )

        current_rmu = None
        if current_combined_id is not None:
            try:
                current_rmu = self.db.get_rmu_by_id(
                    current_combined_id
                )
            except Exception as exc:
                row["current_rmu_lookup_error"] = str(exc)

        current_rmu_name = norm((current_rmu or {}).get("name"))
        row["current_rmu_name"] = current_rmu_name

        expected_rmu_id = int_or_none(rmu_id)
        rmu_match = (
            current_combined_id is not None
            and expected_rmu_id is not None
            and current_combined_id == expected_rmu_id
        )
        row["current_rmu_match"] = "YES" if rmu_match else "NO"

        expected_rmu_name = norm(row.get("rmu_name"))
        rmu_name_match = (
            bool(expected_rmu_name)
            and bool(current_rmu_name)
            and expected_rmu_name == current_rmu_name
        )
        row["current_rmu_name_match"] = (
            "YES" if rmu_name_match else "NO"
        )

        # If the old model can be resolved and explicitly belongs to another
        # RMU, show a dedicated correctable status.
        if (
            current_combined_id is not None
            and expected_rmu_id is not None
            and current_combined_id != expected_rmu_id
        ):
            self._set_rmu_relink(
                row,
                "CURRENT_MODEL_RMU_MISMATCH_RELINK: "
                f"当前图形环网柜={row.get('rmu_name') or '-'}；"
                f"旧KeyID设备所属环网柜={current_rmu_name or '-'}；"
                f"旧combined_id={current_combined_id}；"
                f"目标combined_id={expected_rmu_id}；"
                "数据库当前目标设备已通过CODE/图上逻辑CODE及RMU归属校验，允许强制重新关联"
            )
            return

        reasons = []

        if current_device_id != int(device_id):
            reasons.append(
                f"DEVICE_ID已变化(current={current_device_id}, "
                f"expected={device_id})"
            )

        if current_table_id != int(rule["table_id"]):
            reasons.append(
                f"TABLE_ID不匹配(current={current_table_id}, "
                f"expected={rule['table_id']})"
            )

        if current_domain != int(rule["domain"]):
            reasons.append(
                f"DOMAIN不匹配(current={current_domain}, "
                f"expected={rule['domain']})"
            )

        if current_keyid != int(row["expected_keyid"]):
            reasons.append(
                f"KEYID已变化或不匹配(current={current_keyid}, "
                f"expected={row['expected_keyid']})"
            )

        # If the old record itself disappeared, its RMU ownership cannot be
        # verified.  Since the CURRENT database target is valid, repair it.
        if current_record is None:
            reasons.append(
                "旧KeyID对应数据库记录已不存在或无法读取"
            )

        # Any old-model mismatch is now a correctable RELINK state.
        if reasons:
            self._set_relink(
                row,
                "MODEL_RELINK_REQUIRED: " + "; ".join(reasons)
                + "；数据库当前目标设备唯一且符合规则，允许重新关联"
            )
            return

        # Current keyid/table/domain/device all match expected.  At this point
        # current_record should be the same current database target, therefore
        # ownership is also expected to match. If ownership cannot be proven,
        # repair rather than hard-fail.
        if (
            row.get("current_rmu_match") != "YES"
            or row.get("current_rmu_name_match") != "YES"
        ):
            self._set_relink(
                row,
                "CURRENT_MODEL_RMU_UNVERIFIED: "
                "当前KeyID基础信息与期望一致，但旧模型环网柜归属无法完整验证；"
                "数据库当前目标设备唯一且有效，允许重新关联"
            )
            return

        row["model_link_correct"] = "YES"
        row["model_link_status"] = "模型已关联且正确"
        row["association_action"] = "模型已关联，无需关联"
        row["association_ready"] = "YES"
        row["writeback_needed"] = "NO"
        row["status"] = "PASS"
        row["severity"] = "PASS"
        row["reason"] = "MODEL_ALREADY_LINKED_CORRECT"

    def _inspect_current_link_without_unique_rmu(
        self,
        row,
        elem,
        rmu_reason,
        current_keyid_value=None,
        rule=None,
    ):
        """
        RMU database identity is missing or duplicated.

        Summary-level RMU status remains a hard ERROR.

        Device policy:
        - no current KeyID -> hard FAIL, automatic association forbidden;
        - current KeyID exists -> inspect the manual link instead of discarding it;
        - current linked CODE must equal the logical CODE;
        - current linked device must belong to an RMU whose NAME equals the
          current G-file RMU name;
        - a correct existing manual link is allowed to remain even though the
          RMU database name itself is duplicated.
        """
        row["association_ready"] = "NO"
        row["writeback_needed"] = "NO"

        current_keyid_text = (
            elem.keyid
            if current_keyid_value is None
            else norm(current_keyid_value)
        )

        if not current_keyid_text:
            row["model_linked"] = "NO"
            row["model_link_correct"] = ""
            row["model_link_status"] = "未关联"
            row["association_action"] = "禁止自动关联"
            self._set_fail(
                row,
                f"{rmu_reason}: 环网柜数据库记录为0条或多条，"
                "当前设备未关联，禁止自动关联"
            )
            return

        row["model_linked"] = "YES"
        row["model_link_correct"] = "NO"
        row["model_link_status"] = "已人工关联，正在检查"
        row["association_action"] = "检查现有人工关联"

        current_keyid = int_or_none(current_keyid_text)
        if current_keyid is None:
            self._set_fail(row, "CURRENT_KEYID_INVALID")
            return

        try:
            curv = self.db.verify_keyid(current_keyid)
            did = int_or_none(curv.get("device_id"))
            tab = int_or_none(curv.get("tab_no"))

            row["current_device_id"] = curv.get("device_id", "")
            row["current_table_id"] = curv.get("tab_no", "")
            row["current_domain"] = curv.get("col_no", "")

            if did is None or tab is None:
                self._set_fail(
                    row,
                    "CURRENT_KEYID_DEVICE_NOT_FOUND"
                )
                return

            rec = self.db.get_device_by_id(tab, did)
            if not rec:
                self._set_fail(
                    row,
                    "CURRENT_KEYID_DEVICE_NOT_FOUND"
                )
                return

            row["current_table_name"] = rec.get("_table_name", "")
            row["current_db_code"] = norm(rec.get("code"))
            row["current_db_name"] = norm(rec.get("name"))
            row["current_combined_id"] = rec.get("combined_id", "")

            # Also expose the manually-linked DB device in normal DB columns.
            row["db_device_id"] = rec.get("id", did)
            row["db_code"] = norm(rec.get("code"))
            row["db_name"] = norm(rec.get("name"))
            row["db_combined_id"] = rec.get("combined_id", "")
            row["db_bv_id"] = rec.get("bv_id", "")

            current_combined_id = int_or_none(
                row.get("current_combined_id")
            )
            current_rmu = None
            if current_combined_id is not None:
                try:
                    current_rmu = self.db.get_rmu_by_id(
                        current_combined_id
                    )
                except Exception:
                    current_rmu = None

            current_rmu_name = norm((current_rmu or {}).get("name"))
            row["current_rmu_name"] = current_rmu_name

            expected_rmu_name = norm(row.get("rmu_name"))
            if expected_rmu_name:
                row["current_rmu_name_match"] = (
                    "YES"
                    if current_rmu_name
                    and expected_rmu_name == current_rmu_name
                    else "NO"
                )
            else:
                # The G-file RMU name was not resolved.  Do not label an
                # otherwise valid existing KeyID as "linked to another RMU"
                # merely because there is no textual RMU name to compare.
                # The cross-device consistency pass below will determine
                # whether all existing links point to one actual RMU.
                row["current_rmu_name_match"] = "N/A"

            # There is no unique expected RMU ID in this branch.
            row["current_rmu_match"] = "N/A"

            # Only an actually resolved G-file RMU name can prove that the
            # current model belongs to another RMU.  If the name is missing,
            # keep inspecting the current link and infer RMU identity from the
            # set of existing device links afterwards.
            if (
                expected_rmu_name
                and row.get("current_rmu_name_match") != "YES"
            ):
                row["model_link_status"] = (
                    "已人工关联，但关联到了其他环网柜"
                )
                row["association_action"] = (
                    "禁止自动关联，请检查现有人工模型"
                )
                self._set_rmu_link_issue(
                    row,
                    "CURRENT_MODEL_RMU_MISMATCH: "
                    f"当前图形环网柜={expected_rmu_name or '-'}；"
                    f"当前KeyID设备所属环网柜={current_rmu_name or '-'}；"
                    f"当前combined_id={current_combined_id or '-'}"
                )
                return

        except Exception as exc:
            self._set_fail(
                row,
                f"CURRENT_KEYID_VERIFY_ERROR: {exc}"
            )
            return

        expected_code = (
            norm(row.get("selected_device_name"))
            or norm(row.get("logical_code"))
        )

        if not expected_code:
            self._set_fail(row, "LOGICAL_CODE_EMPTY")
            return

        if not row.get("db_code"):
            self._set_fail(row, "DB_CODE_EMPTY")
            return

        if row.get("db_code") != expected_code:
            self._set_fail(
                row,
                "CURRENT_LINK_CODE_MISMATCH: "
                f"CODE={row.get('db_code')}, LOGICAL_CODE={expected_code}"
            )
            return

        # Even for an existing manual KeyID, CODE must remain unique inside
        # the actual RMU that owns the linked database device.
        current_combined_id = int_or_none(row.get("current_combined_id"))
        current_table_id = int_or_none(row.get("current_table_id"))
        current_device_id = int_or_none(row.get("current_device_id"))

        if current_combined_id is None or current_table_id is None:
            self._set_fail(
                row,
                "CURRENT_LINK_RMU_OR_TABLE_INVALID"
            )
            return

        try:
            relay_table_id = int(
                (rule or {}).get("table_id", RMU_RELAY_SIGNAL_TABLE_ID)
            )
            if (
                row.get("object_type") == RMU_RELAY_SIGNAL_TAG
                and current_table_id == relay_table_id
            ):
                _, owner_rows = self.db.get_relay_signals_by_combined_id(
                    current_combined_id,
                    RMU_RELAY_SIGNAL_CODE,
                    table_id=current_table_id,
                )
            else:
                _, owner_rows = self.db.get_devices_by_combined_id(
                    current_table_id,
                    current_combined_id,
                )
        except Exception as exc:
            self._set_fail(
                row,
                f"CURRENT_LINK_CODE_UNIQUENESS_QUERY_FAILED: {exc}"
            )
            return

        same_code_rows = self._find_by_code(owner_rows, expected_code)
        row["db_match_count"] = len(same_code_rows)

        if len(same_code_rows) == 0:
            self._set_fail(
                row,
                f"CURRENT_LINK_CODE_NOT_FOUND_IN_OWNER_RMU: CODE={expected_code}"
            )
            return

        if len(same_code_rows) > 1:
            self._set_fail(
                row,
                "CURRENT_LINK_CODE_DUPLICATE_IN_OWNER_RMU: "
                f"CODE={expected_code}; COUNT={len(same_code_rows)}"
            )
            return

        unique_device_id = int_or_none(same_code_rows[0].get("id"))
        if (
            unique_device_id is None
            or current_device_id is None
            or unique_device_id != current_device_id
        ):
            self._set_fail(
                row,
                "CURRENT_LINK_DEVICE_NOT_UNIQUE_CODE_TARGET: "
                f"CODE={expected_code}; "
                f"KeyID_DEVICE={current_device_id or '-'}; "
                f"UNIQUE_CODE_DEVICE={unique_device_id or '-'}"
            )
            return

        # Manual link itself is correct by current business rules.
        row["model_link_correct"] = "YES"
        row["association_ready"] = "YES"
        row["model_link_status"] = (
            "已人工关联，CODE与环网柜归属校验通过"
        )
        row["association_action"] = (
            "保留人工关联；RMU数据库记录异常需人工复核"
        )
        row["status"] = "PASS"
        row["severity"] = "PASS"
        row["reason"] = (
            f"{rmu_reason}: EXISTING_MANUAL_LINK_VALID"
        )


    def _validate_nonunique_rmu_existing_links(self, rmu_result):
        """
        Cross-check existing manual KeyIDs when the RMU identity cannot be
        uniquely established from the G-file name.

        This covers both:
        - a parsed RMU name that is duplicated/not uniquely usable in DB; and
        - an RMU name that was not parsed (or whose parsing raised an error).

        Existing links are inspected instead of being discarded.  All
        successfully resolved KeyIDs inside one G RMU must point to ONE AND
        THE SAME actual dms_combined_device record.  For a missing G-file RMU
        name, that common combined_id is also used as an evidence-only RMU
        identity hint for the report.  It does NOT enable automatic creation
        or reassociation while the graphical RMU name remains unresolved.

        Feeder information is deliberately not involved.
        """
        linked_rows = [
            row for row in rmu_result.get("device_rows", [])
            if row.get("model_linked") == "YES"
        ]
        if not linked_rows:
            return

        expected_name = norm(rmu_result.get("rmu_name"))
        reason_text = norm(rmu_result.get("rmu_reason"))
        reason_code = reason_text.split(":", 1)[0] if reason_text else ""

        resolved_rows = []
        current_rmu_ids = set()
        current_rmu_names = set()

        for row in linked_rows:
            current_id = int_or_none(row.get("current_combined_id"))
            current_name = norm(row.get("current_rmu_name"))
            if current_id is not None:
                current_rmu_ids.add(current_id)
                resolved_rows.append(row)
            if current_name:
                current_rmu_names.add(current_name)

            # If the G-file RMU name was actually resolved, keep the original
            # hard name-mismatch check.  When it was not resolved there is no
            # textual target to compare against, so only the cross-device
            # combined_id consistency rule below is meaningful.
            if current_name and expected_name and current_name != expected_name:
                row["model_link_correct"] = "NO"
                row["association_ready"] = "NO"
                row["model_link_status"] = "已关联，但关联到了其他环网柜"
                row["association_action"] = "禁止自动关联，请检查现有模型"
                self._set_rmu_link_issue(
                    row,
                    "CURRENT_MODEL_RMU_NAME_MISMATCH: "
                    f"当前图形环网柜={expected_name}；"
                    f"当前KeyID设备所属环网柜={current_name}；"
                    f"当前combined_id={current_id or '-'}"
                )

        if len(current_rmu_ids) > 1:
            ids_text = ",".join(
                str(value) for value in sorted(current_rmu_ids)
            )
            if expected_name:
                issue = (
                    "NONUNIQUE_RMU_EXISTING_LINKS_SPAN_MULTIPLE_RMUS: "
                    f"同一G图环网柜内已关联设备实际来自多个环网柜ID：{ids_text}"
                )
            else:
                issue = (
                    "UNRESOLVED_RMU_EXISTING_LINKS_SPAN_MULTIPLE_RMUS: "
                    "图上环网柜名称未可靠解析，且柜内已关联设备实际来自"
                    f"多个数据库环网柜ID：{ids_text}；无法反推出唯一环网柜。"
                )
            rmu_result["db_integrity_issues"].append(issue)
            rmu_result["association_block_reasons"].append(issue)

            for row in resolved_rows:
                row["model_link_correct"] = "NO"
                row["association_ready"] = "NO"
                row["writeback_needed"] = "NO"
                row["model_link_status"] = (
                    "已关联，但同一环网柜内设备来自多个数据库环网柜"
                )
                row["association_action"] = (
                    "禁止自动处理，请检查已有模型关联"
                )
                self._set_rmu_link_issue(
                    row,
                    "CURRENT_MODEL_RMU_ID_INCONSISTENT: "
                    f"当前图形环网柜={expected_name or '-'}；"
                    f"本环网柜已关联设备涉及多个combined_id={ids_text}"
                )
            return

        # v4.1.17: RMU name was not parsed, but all resolvable existing
        # device links point to the same actual database RMU.  Preserve the
        # red RMU-level name warning, while explicitly reporting that the
        # existing RMU ownership is consistent and does not need reassociation.
        if not expected_name and len(current_rmu_ids) == 1:
            inferred_id = next(iter(current_rmu_ids))
            inferred_name = (
                next(iter(current_rmu_names))
                if len(current_rmu_names) == 1
                else ""
            )
            rmu_result["inferred_rmu_id"] = inferred_id
            rmu_result["inferred_rmu_name"] = inferred_name

            all_device_rows = [
                row for row in rmu_result.get("device_rows", [])
                if row.get("xml_id")
            ]
            unlinked_rows = [
                row for row in all_device_rows
                if row.get("model_linked") != "YES"
            ]
            linked_without_owner = [
                row for row in linked_rows
                if int_or_none(row.get("current_combined_id")) is None
            ]
            all_devices_confirmed = (
                bool(all_device_rows)
                and not unlinked_rows
                and not linked_without_owner
                and len(resolved_rows) == len(all_device_rows)
            )

            parse_label = (
                "图上环网柜名称解析/核验异常"
                if reason_code in {
                    "RMU_NAME_RESOLUTION_ERROR",
                    "RMU_LOOKUP_ERROR",
                }
                else "图上环网柜名称未解析出来"
            )
            rmu_ref = (
                f"ID={inferred_id}，NAME={inferred_name or '-'}"
            )
            if all_devices_confirmed:
                consistency_text = (
                    "柜内所有设备的现有KeyID均可反查，并且全部来自同一个"
                    f"数据库环网柜（{rmu_ref}）；因此现有RMU归属关联一致且正确，"
                    "无需重新关联。"
                )
            else:
                consistency_text = (
                    "当前能够反查的已关联设备均来自同一个数据库环网柜"
                    f"（{rmu_ref}），现有已关联设备的RMU归属一致；"
                    f"另有未关联设备={len(unlinked_rows)}，"
                    f"无法反查所属RMU的已关联设备={len(linked_without_owner)}。"
                )

            advice = (
                f"{parse_label}；{consistency_text}"
                f"请检查图上的环网柜名称是否应为“{inferred_name or '-'}”。"
            )
            rmu_result["rmu_reason"] = (
                f"{reason_code or 'RMU_NAME_NOT_PARSED'}: {advice}"
            )

            # Replace the generic identity blocker with a precise message.
            # The row stays red because the graphical RMU name is unresolved;
            # however, existing consistent links are explicitly preserved.
            old_blocks = list(rmu_result.get("association_block_reasons", []))
            filtered_blocks = [
                block for block in old_blocks
                if not str(block).startswith((
                    "RMU_NAME_NOT_PARSED:",
                    "RMU_NAME_RESOLUTION_ERROR:",
                    "RMU_IDENTITY_INVALID:",
                ))
            ]
            filtered_blocks.append(
                f"{reason_code or 'RMU_NAME_NOT_PARSED'}: "
                f"{parse_label}；已通过柜内现有KeyID反查到唯一数据库环网柜"
                f"（{rmu_ref}）。{consistency_text}"
                "由于图上名称仍未可靠解析，禁止自动新增或改绑；"
                "现有一致关联无需修改。"
            )
            rmu_result["association_block_reasons"] = filtered_blocks

            for row in resolved_rows:
                # Do not overwrite genuine device-level errors.  Only improve
                # the explanation for rows whose existing manual link already
                # passed the per-device checks.
                if (
                    row.get("status") == "PASS"
                    and row.get("model_link_correct") == "YES"
                ):
                    row["model_link_status"] = (
                        "模型已关联且正确；图上RMU名称未解析，但柜内设备归属一致"
                    )
                    row["association_action"] = (
                        "保留现有关联；请核对图上环网柜名称"
                    )
                    row["reason"] = (
                        "RMU_NAME_UNRESOLVED_EXISTING_LINK_VALID: "
                        f"当前KeyID设备所属环网柜ID={inferred_id}；"
                        f"环网柜NAME={inferred_name or '-'}；"
                        "当前设备关联无需修改。"
                    )
            return

        # Exactly one actual RMU ID with a resolved expected RMU name is
        # consistent; per-row checks have already handled any name mismatch.
        return

    def _append_unresolved_rmu_device_rows(
        self,
        parsed,
        frame,
        rmu_result,
        resolved_reason,
        skip_db_lookup=False,
    ):
        """
        Expose G-file device rows even when RMU DB identity is 0/multiple.

        The same logical device-name rules are used as in normal validation so
        an existing manually-linked KeyID can still be checked correctly.
        """
        elements = self.parser.find_target_objects_in_frame(
            parsed,
            frame,
            self.device_rules.keys(),
        )
        elements_by_tag = defaultdict(list)
        for elem in elements:
            elements_by_tag[elem.tag].append(elem)

        # The relay-signal rule is exact: other pwbh symbols are not RMU
        # devices and must not enter the association report.
        elements_by_tag[RMU_RELAY_SIGNAL_TAG] = [
            elem
            for elem in elements_by_tag.get(RMU_RELAY_SIGNAL_TAG, [])
            if self._is_normal_relay_signal(elem)
        ]

        breakers = elements_by_tag.get("CBreakerDis", [])
        grounds = elements_by_tag.get("ZhaiWaiJieDiDaoZha", [])
        buses = elements_by_tag.get("BusDis", [])

        graph_names = self.parser.resolve_breaker_graphical_names(
            parsed,
            frame,
            breakers,
        )

        breaker_names = {}
        for br in breakers:
            info = graph_names.get(br.xml_id, {})
            breaker_names[br.xml_id] = (
                norm(info.get("name"))
                if info.get("status") == "PASS"
                else ""
            )

        ground_to_breaker = self.parser.pair_objects_nearest(
            grounds,
            breakers,
        )

        def make_row(elem):
            rule = self.device_rules[elem.tag]
            row = self._default_device_row(
                rmu_result.get("rmu_name", ""),
                "",
                elem,
                rule,
                {"table_name": ""},
            )
            if elem.tag == RMU_RELAY_SIGNAL_TAG:
                relay_keyid = self._relay_keyid(elem)
                row["current_keyid"] = relay_keyid
                row["model_linked"] = "YES" if relay_keyid else "NO"
            return row

        for elem in breakers:
            row = make_row(elem)
            info = graph_names.get(elem.xml_id, {})
            selected = (
                norm(info.get("name"))
                if info.get("status") == "PASS"
                else ""
            )
            row["selected_name_source"] = "GRAPHICAL_TEXT"
            row["graphical_name"] = selected
            # Internal compatibility field: this is the logical name derived
            # from visible G text, not from any raw XML naming attribute.
            row["logical_code"] = selected
            row["selected_device_name"] = selected
            if not selected:
                self._set_fail(
                    row,
                    info.get(
                        "reason",
                        "GRAPHICAL_NAME_NOT_RESOLVED",
                    ),
                )
                rmu_result["device_rows"].append(row)
                continue

            if skip_db_lookup:
                self._set_fail(row, resolved_reason)
            else:
                self._inspect_current_link_without_unique_rmu(
                    row,
                    elem,
                    resolved_reason,
                    rule=self.device_rules[elem.tag],
                )
            rmu_result["device_rows"].append(row)

        for elem in grounds:
            row = make_row(elem)
            br_id = ground_to_breaker.get(elem.xml_id, "")
            breaker_name = breaker_names.get(br_id, "")
            expected_code = (
                breaker_name + "D"
                if breaker_name
                else ""
            )
            row["selected_name_source"] = "PAIRED_CBREAKER_PLUS_D"
            row["paired_breaker_name"] = breaker_name
            row["selected_device_name"] = expected_code

            # Ground-disconnector logical name is always derived from the
            # paired graphical breaker name: breaker + D.
            row["logical_code"] = expected_code

            if not breaker_name:
                self._set_fail(
                    row,
                    "GROUND_BREAKER_PAIR_NOT_RESOLVED",
                )
            else:
                if skip_db_lookup:
                    self._set_fail(row, resolved_reason)
                else:
                    self._inspect_current_link_without_unique_rmu(
                        row,
                        elem,
                        resolved_reason,
                        rule=self.device_rules[elem.tag],
                    )
            rmu_result["device_rows"].append(row)

        for elem in buses:
            row = make_row(elem)
            row["selected_name_source"] = "FIXED_BUS"
            row["logical_code"] = "BUS"
            row["selected_device_name"] = "BUS"

            if skip_db_lookup:
                self._set_fail(row, resolved_reason)
            else:
                self._inspect_current_link_without_unique_rmu(
                    row,
                    elem,
                    resolved_reason,
                    rule=self.device_rules[elem.tag],
                )
            rmu_result["device_rows"].append(row)

        for elem in elements_by_tag.get(RMU_RELAY_SIGNAL_TAG, []):
            row = make_row(elem)
            row["selected_name_source"] = "FIXED_EFI_INDICATOR"
            row["logical_code"] = RMU_RELAY_SIGNAL_CODE
            row["selected_device_name"] = RMU_RELAY_SIGNAL_CODE
            row["graphical_name"] = norm(elem.attrs.get("key_name1"))
            if skip_db_lookup:
                self._set_fail(row, resolved_reason)
            else:
                self._inspect_current_link_without_unique_rmu(
                    row,
                    elem,
                    resolved_reason,
                    current_keyid_value=self._relay_keyid(elem),
                    rule=self.device_rules[elem.tag],
                )
            rmu_result["device_rows"].append(row)


    def _fill_db_fields(self, row, dev):
        row.update({
            "db_device_id": dev.get("id", ""),
            "db_code": norm(dev.get("code")),
            "db_name": norm(dev.get("name")),
            "db_combined_id": dev.get("combined_id", ""),
            "db_bv_id": dev.get("bv_id", ""),
        })

    def _validate_relay_signal(self, row, elem, db_set, rule):
        """Validate NariPd_Normal against dms_relay_sig.CODE exactly."""
        row["selected_name_source"] = "FIXED_EFI_INDICATOR"
        row["logical_code"] = RMU_RELAY_SIGNAL_CODE
        row["selected_device_name"] = RMU_RELAY_SIGNAL_CODE
        row["graphical_name"] = norm(elem.attrs.get("key_name1"))

        matches = self._find_by_code(db_set.get("rows", []), RMU_RELAY_SIGNAL_CODE)
        row["db_match_count"] = len(matches)
        if len(matches) == 0:
            self._set_fail(
                row,
                "RELAY_SIGNAL_NOT_FOUND: "
                f"table={rule['table_id']}.CODE={RMU_RELAY_SIGNAL_CODE} "
                "在当前环网柜中不存在",
            )
            return
        if len(matches) > 1:
            self._set_fail(
                row,
                "RELAY_SIGNAL_CODE_DUPLICATE: "
                f"table={rule['table_id']}.CODE={RMU_RELAY_SIGNAL_CODE} "
                f"存在{len(matches)}条记录",
            )
            return

        dev = matches[0]
        self._fill_db_fields(row, dev)
        if norm(dev.get("code")) != RMU_RELAY_SIGNAL_CODE:
            self._set_fail(row, "RELAY_SIGNAL_CODE_MISMATCH")
            return

        device_id = int_or_none(dev.get("id"))
        if device_id is None:
            self._set_fail(row, "RELAY_SIGNAL_DEVICE_ID_INVALID")
            return
        if not self._validate_expected_device_ownership(
            row, dev, row.get("rmu_id")
        ):
            return
        if not self._verify_expected_keyid(row, device_id, rule):
            return

        self._evaluate_current_model(
            row,
            elem,
            device_id,
            rule,
            row.get("rmu_id"),
            current_keyid_value=self._relay_keyid(elem),
            require_bv_id=False,
        )

    def _validate_breaker(self, row, elem, db_set, rule, selected_name, graphical_name):
        row["graphical_name"] = graphical_name
        row["selected_name_source"] = self.breaker_name_source
        row["selected_device_name"] = selected_name

        # In graphical-name mode, the visible G-file text becomes the logical
        # logical CODE used by every downstream comparison. The raw XML naming attribute is intentionally ignored.
        logical_code = selected_name
        row["logical_code"] = logical_code

        if not selected_name:
            self._set_fail(
                row,
                "BREAKER_GRAPHICAL_NAME_NOT_RESOLVED: "
                "未能从环网柜内图上文字唯一识别开关名称，请检查该环网柜命名方式",
            )
            return

        matches = self._find_by_code(db_set["rows"], selected_name)
        row["db_match_count"] = len(matches)
        if len(matches) == 0:
            self._set_fail(
                row,
                f"BREAKER_GRAPHICAL_NAME_DB_CODE_NOT_FOUND: "
                f"图上名称={selected_name}；数据库中不存在对应 CODE；"
                "请检查该环网柜开关命名方式",
            )
            return
        if len(matches) > 1:
            self._set_fail(
                row,
                f"BREAKER_GRAPHICAL_NAME_DB_CODE_DUPLICATE: "
                f"图上名称={row.get('selected_device_name')}；"
                "数据库存在多条相同 CODE，请检查该环网柜命名方式或数据库设备",
            )
            return

        dev = matches[0]
        self._fill_db_fields(row, dev)
        code = norm(dev.get("code"))

        if not code:
            self._set_fail(row, "DB_CODE_EMPTY")
            return
        if not logical_code:
            self._set_fail(row, "LOGICAL_CODE_EMPTY")
            return
        if code != logical_code:
            self._set_fail(row, f"CBREAKER_CODE_LOGICAL_MISMATCH (CODE={code}, LOGICAL_CODE={logical_code})")
            return

        device_id = int_or_none(dev.get("id"))
        if device_id is None:
            self._set_fail(row, "DEVICE_ID_INVALID")
            return

        if not self._validate_expected_device_ownership(
            row,
            dev,
            row.get("rmu_id"),
        ):
            return

        if not self._verify_expected_keyid(row, device_id, rule):
            return

        self._evaluate_current_model(row, elem, device_id, rule, row.get("rmu_id"))

    def _validate_ground(self, row, elem, db_set, rule, breaker_name):
        row["selected_name_source"] = "PAIRED_CBREAKER_PLUS_D"
        row["paired_breaker_name"] = breaker_name
        expected_code = (breaker_name + "D") if breaker_name else ""
        row["selected_device_name"] = expected_code

        # When graphical-name mode is selected, the logical CODE of a
        # ground disconnector is derived only from its paired breaker: breaker+D.
        # The raw G XML naming attribute is not used for validation.
        logical_code = expected_code
        row["logical_code"] = logical_code

        if not breaker_name:
            self._set_fail(row, "GROUND_BREAKER_PAIR_NOT_RESOLVED")
            return

        matches = self._find_by_code(db_set["rows"], expected_code)
        row["db_match_count"] = len(matches)
        if len(matches) == 0:
            self._set_fail(row, f"DEVICE_NOT_FOUND: CODE={expected_code}; 数据库中不存在该设备")
            return
        if len(matches) > 1:
            self._set_fail(row, f"DEVICE_CODE_DUPLICATE: CODE={row.get('selected_device_name')}; 数据库中存在多条匹配设备")
            return

        dev = matches[0]
        self._fill_db_fields(row, dev)
        code = norm(dev.get("code"))
        if not code:
            self._set_fail(row, "DB_CODE_EMPTY")
            return
        if code != expected_code:
            self._set_fail(row, f"GROUND_CODE_EXPECTED_MISMATCH (CODE={code}, EXPECTED={expected_code})")
            return
        if not logical_code:
            self._set_fail(row, "LOGICAL_CODE_EMPTY")
            return
        if code != logical_code:
            self._set_fail(row, f"GROUND_CODE_LOGICAL_MISMATCH (CODE={code}, LOGICAL_CODE={logical_code})")
            return

        device_id = int_or_none(dev.get("id"))
        if device_id is None:
            self._set_fail(row, "DEVICE_ID_INVALID")
            return

        if not self._validate_expected_device_ownership(
            row,
            dev,
            row.get("rmu_id"),
        ):
            return
        if not self._verify_expected_keyid(row, device_id, rule):
            return
        self._evaluate_current_model(row, elem, device_id, rule, row.get("rmu_id"))

    def _validate_bus(self, row, elem, db_set, rule):
        # BusDis never reads the raw G XML naming attribute.  The
        # business rule defines the logical CODE as the fixed value BUS.
        logical_code = "BUS"
        row["selected_name_source"] = "FIXED_BUS"

        row["logical_code"] = logical_code
        row["selected_device_name"] = logical_code

        if not logical_code:
            self._set_fail(row, "LOGICAL_CODE_EMPTY")
            return

        matches = self._find_by_code(db_set["rows"], logical_code)
        row["db_match_count"] = len(matches)
        if len(matches) == 0:
            self._set_fail(row, f"DEVICE_NOT_FOUND: CODE={logical_code}; 数据库中不存在该设备")
            return
        if len(matches) > 1:
            self._set_fail(row, f"DEVICE_CODE_DUPLICATE: CODE={row.get('selected_device_name')}; 数据库中存在多条匹配设备")
            return

        dev = matches[0]
        self._fill_db_fields(row, dev)
        code = norm(dev.get("code"))
        if not code:
            self._set_fail(row, "DB_CODE_EMPTY")
            return
        if code != logical_code:
            self._set_fail(row, f"BUS_CODE_LOGICAL_MISMATCH (CODE={code}, LOGICAL_CODE={logical_code})")
            return

        device_id = int_or_none(dev.get("id"))
        if device_id is None:
            self._set_fail(row, "DEVICE_ID_INVALID")
            return

        if not self._validate_expected_device_ownership(
            row,
            dev,
            row.get("rmu_id"),
        ):
            return
        if not self._verify_expected_keyid(row, device_id, rule):
            return
        self._evaluate_current_model(row, elem, device_id, rule, row.get("rmu_id"))

    @staticmethod
    def _rmu_identity_block_reason(reason, frame_xml_id, rmu_name=""):
        """Return a user-facing RMU-level hard blocker with a precise cause."""
        reason_text = norm(reason)
        code = reason_text.split(":", 1)[0] if reason_text else ""
        frame_ref = norm(frame_xml_id) or "-"
        name_ref = norm(rmu_name)

        if code in {"RMU_NAME_NOT_PARSED", "RMU_NAME_NOT_FOUND"}:
            return (
                "RMU_NAME_NOT_PARSED: "
                f"矩形框XML ID={frame_ref} 未解析出环网柜名称；"
                "请检查环网柜名称方向配置、图内名称文字及其与矩形框的位置关系。"
                "环网柜身份未确定，禁止该RMU及柜内设备自动关联。"
            )

        if code in {"RMU_NAME_RESOLUTION_ERROR", "RMU_LOOKUP_ERROR"}:
            detail = reason_text.split(":", 1)[1].strip() if ":" in reason_text else reason_text
            return (
                "RMU_NAME_RESOLUTION_ERROR: "
                f"矩形框XML ID={frame_ref} 环网柜名称解析/核验异常；"
                f"详情={detail or '-'}；"
                "环网柜身份未可靠确定，禁止该RMU及柜内设备自动关联。"
            )

        if code in {
            "RMU_DUPLICATE_IN_DATABASE",
            "RMU_DUPLICATE_NAME_SAME_FEEDER",
            "RMU_DUPLICATE_NAME_FEEDER_UNRESOLVED",
            "RMU_DUPLICATE_NAME_DIAGRAM_FEEDER_NOT_FOUND",
            "RMU_GRAPHICAL_NAME_DUPLICATE",
            "RMU_NO_PLACEHOLDER_FEEDER_NOT_RESOLVED",
            "RMU_NO_PLACEHOLDER_NO_UNUSED_DB_RECORD",
            "RMU_NO_PLACEHOLDER_QUERY_FAILED",
        }:
            detail = reason_text.split(":", 1)[1].strip() if ":" in reason_text else ""
            return (
                f"{code}: "
                f"已解析环网柜名称={name_ref or '-'}；{detail or '数据库存在多条无法唯一确定的同名记录'}；"
                + (
                    "NO占位环网柜没有可用的唯一数据库目标，禁止自动关联。"
                    if code.startswith("RMU_NO_PLACEHOLDER_")
                    else "环网柜图上名称必须唯一，禁止自动关联。"
                )
            )

        if code == "RMU_DIAGRAM_FEEDER_NOT_RESOLVED":
            return (
                "RMU_DIAGRAM_FEEDER_NOT_RESOLVED: "
                f"环网柜名称={name_ref or '-'}；"
                "同名环网柜属于不同FEEDER_ID，但本张G图没有可唯一确定馈线的环网柜，"
                "禁止自动选择COMBINED_ID。"
            )

        if code == "RMU_NOT_FOUND_IN_DATABASE":
            return (
                "RMU_NOT_FOUND_IN_DATABASE: "
                f"已解析环网柜名称={name_ref or '-'}，但数据库中未找到唯一对应记录；"
                "请检查数据库模型或图内环网柜名称，禁止自动关联。"
            )

        return (
            f"RMU_IDENTITY_INVALID: 矩形框XML ID={frame_ref}；"
            f"环网柜名称={name_ref or '-'}；原因={reason_text or 'UNKNOWN'}；"
            "环网柜身份无法可靠确定，禁止该RMU及柜内设备自动关联。"
        )

    @staticmethod
    def _no_placeholder_resolution(
        choice,
        record,
        feeder_id,
        pool_count=0,
        assignment_index=0,
        matched_by_name=False,
        error_code="",
    ):
        """Build the normal resolver shape for a Jazan NO placeholder."""
        name = norm(choice.get("name"))
        selected_records = [record] if record else []
        candidate = {
            "name": name,
            "directions": "",
            "best_score": "",
            "distance": "",
            "color": "",
            "is_green": "NO",
            "xml_id": choice.get("frame_xml_id", ""),
            "db_count": len(selected_records),
            "db_records": selected_records,
            "db_all_records": selected_records,
            "db_all_count": len(selected_records),
            "db_feeder_ids": [feeder_id] if feeder_id is not None else [],
            "db_resolution": "NO_PLACEHOLDER_FEEDER_POOL",
            "selected_by_rule": "YES",
            "selection_reason": "JAZAN_NO_PLACEHOLDER_FEEDER_POOL",
            "no_placeholder": "YES",
            "no_assignment_source": (
                "EXACT_DATABASE_NAME_IN_FEEDER_POOL"
                if matched_by_name
                else "UNUSED_DATABASE_RMU_IN_FEEDER_POOL"
            ),
            "no_assignment_index": assignment_index,
            "no_assignment_pool_count": pool_count,
        }

        if record:
            record_id = record.get("id", "")
            reason = (
                "RMU_NO_PLACEHOLDER_ASSIGNED: "
                f"图上名称={name}；按同图 FEEDER_ID={feeder_id} 从未占用的"
                f"数据库环网柜中分配 RMU_ID={record_id}；"
                f"本图NO占位环网柜分配序号={assignment_index}；"
                f"可用数据库环网柜数={pool_count}；"
                "同一个数据库环网柜不会重复分配。"
            )
            return {
                "status": "PASS",
                "reason": reason,
                "candidate_rows": [candidate],
                "selected": candidate,
            }

        if error_code:
            reason = error_code
        elif feeder_id is None:
            reason = (
                "RMU_NO_PLACEHOLDER_FEEDER_NOT_RESOLVED: "
                f"图上名称={name}；本张G图没有可唯一确定的FEEDER_ID，"
                "无法从同馈线数据库环网柜中分配目标。"
            )
        else:
            reason = (
                "RMU_NO_PLACEHOLDER_NO_UNUSED_DB_RECORD: "
                f"图上名称={name}；同图FEEDER_ID={feeder_id}下没有未占用的"
                "数据库环网柜可分配；不能重复使用已经分配给其它图形环网柜的记录。"
            )
        return {
            "status": "FAIL",
            "reason": reason,
            "candidate_rows": [candidate],
            "selected": candidate,
        }

    def validate_file(
        self,
        g_path: str | Path,
        positions: Sequence[str],
        progress_callback=None,
        external_feeder_ids=None,
        external_feeder_source=None,
    ) -> Dict[str, Any]:
        parsed = self.parser.parse(g_path)
        frames = self.parser.find_rmu_frames(parsed)
        name_assignment_error = ""
        try:
            preassigned_name_candidates = (
                self.parser.assign_rmu_label_candidates_globally(
                    parsed,
                    frames,
                    positions,
                )
            )
        except Exception as exc:
            # Name parsing must never abort the whole RMU report.  Convert the
            # parser/resolution failure into a per-RMU red FAIL instead.
            preassigned_name_candidates = {}
            name_assignment_error = (
                f"RMU_NAME_RESOLUTION_ERROR: {type(exc).__name__}: {exc}"
            )
            self.log(
                f"[{parsed.path.name}] 环网柜名称候选解析异常：{name_assignment_error}"
            )

        preassigned_smart_markers = (
            self.parser.assign_rmu_smart_markers_globally(
                parsed,
                frames,
            )
        )

        # Jazan rule: infer the feeder once from a uniquely identified RMU in
        # this G file.  The G root facID is deliberately not used here.  A
        # duplicate RMU NAME can then be resolved against this drawing-level
        # FEEDER_ID before its child tables are queried by COMBINED_ID.
        pre_resolved_names = {}
        diagram_feeder_candidates = []
        diagram_feeder_source = None
        graphical_name_choices = {}
        graphical_name_groups = defaultdict(list)

        # This pass is deliberately database-free.  A repeated RMU name in
        # the drawing is a Jazan graphical warning and must be reported before
        # any database lookup for that name is attempted.
        for frame_index, frame in enumerate(frames, start=1):
            frame_key = (frame.frame.xml_index, frame.frame.xml_id)
            candidates = list(
                preassigned_name_candidates.get(frame_key, [])
                if not name_assignment_error
                else []
            )
            ordered = sorted(
                candidates,
                key=lambda c: (
                    c.score,
                    c.obj.xml_index,
                    c.text,
                ),
            )
            chosen = ordered[0] if ordered else None
            chosen_name = norm(getattr(chosen, "text", "")) if chosen else ""
            if chosen_name:
                choice = {
                    "frame_index": frame_index,
                    "frame_xml_id": frame.frame.xml_id,
                    "name": chosen_name,
                }
                graphical_name_choices[frame.frame.xml_id] = choice
                graphical_name_groups[chosen_name.casefold()].append(choice)

        graphical_duplicate_groups = {
            key: items
            for key, items in graphical_name_groups.items()
            if len(items) > 1
        }

        if not name_assignment_error:
            for frame_index, frame in enumerate(frames, start=1):
                graphical_choice = graphical_name_choices.get(frame.frame.xml_id)
                duplicate_items = (
                    graphical_duplicate_groups.get(
                        graphical_choice["name"].casefold(), []
                    )
                    if graphical_choice
                    else []
                )
                # Ordinary repeated graphical names remain an immediate
                # warning.  NO / NO-* is the Jazan placeholder exception:
                # several placeholders are allowed and compete for distinct
                # unused database RMUs on the drawing feeder.
                if duplicate_items and not is_no_rmu_name(
                    graphical_choice["name"]
                ):
                    duplicate_name = graphical_choice["name"]
                    duplicate_indexes = ",".join(
                        str(item["frame_index"]) for item in duplicate_items
                    )
                    pre_resolved_names[frame.frame.xml_id] = {
                        "status": "FAIL",
                        "reason": (
                            "RMU_GRAPHICAL_NAME_DUPLICATE: "
                            f"本张G图中环网柜名称“{duplicate_name}”出现 "
                            f"{len(duplicate_items)} 次（环网柜序号：{duplicate_indexes}）；"
                            "按Jazan规则直接告警，不查询该名称的数据库记录。"
                        ),
                        "candidate_rows": [],
                        "selected": None,
                    }
                    continue
                if graphical_choice and is_no_rmu_name(
                    graphical_choice["name"]
                ):
                    pre_resolved_names[frame.frame.xml_id] = {
                        "status": "PENDING_NO_PLACEHOLDER",
                        "reason": "",
                        "candidate_rows": [],
                        "selected": None,
                    }
                    continue
                try:
                    resolved = self._resolve_rmu_name(
                        parsed,
                        frame,
                        positions,
                        preassigned_candidates=preassigned_name_candidates,
                    )
                except Exception as exc:
                    resolved = {
                        "status": "FAIL",
                        "reason": (
                            "RMU_NAME_RESOLUTION_ERROR: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                        "candidate_rows": [],
                        "selected": None,
                    }
                pre_resolved_names[frame.frame.xml_id] = resolved

                selected = resolved.get("selected")
                if resolved.get("status") != "PASS" or not selected:
                    continue
                all_records = list(
                    selected.get("db_all_records")
                    or selected.get("db_records")
                    or []
                )
                # Only a single database parent row can independently prove
                # the drawing feeder.  Duplicate-name rows are resolved in
                # the second pass using this feeder.
                if len(all_records) == 1:
                    feeder_id = int_or_none(all_records[0].get("feeder_id"))
                    if feeder_id is not None:
                        diagram_feeder_candidates.append(feeder_id)
                        if diagram_feeder_source is None:
                            diagram_feeder_source = {
                                "device_type": "RMU",
                                "frame_index": frame_index,
                                "frame_xml_id": frame.frame.xml_id,
                                "rmu_name": selected.get("name", ""),
                                "rmu_id": all_records[0].get("id", ""),
                                "feeder_id": all_records[0].get("feeder_id", ""),
                            }

        external_ids = sorted({
            feeder_id
            for feeder_id in (
                int_or_none(value) for value in (external_feeder_ids or [])
            )
            if feeder_id is not None
        })
        if external_ids:
            diagram_feeder_candidates.extend(external_ids)
            if diagram_feeder_source is None and external_feeder_source:
                diagram_feeder_source = dict(external_feeder_source)

        diagram_feeder_ids = sorted(set(diagram_feeder_candidates))
        diagram_feeder_id = (
            diagram_feeder_ids[0]
            if len(diagram_feeder_ids) == 1
            else None
        )
        if diagram_feeder_id is not None:
            diagram_feeder_resolution = (
                "UNIQUE_RMU_IN_SAME_G_FILE"
                if diagram_feeder_source
                and diagram_feeder_source.get("device_type") == "RMU"
                else "UNIQUE_DEVICE_IN_SAME_G_FILE"
            )
            self.log(
                f"[{parsed.path.name}] 按同图唯一设备推断馈线："
                f"FEEDER_ID={diagram_feeder_id}；"
                "后续同名设备按该馈线筛选。"
            )
        elif len(diagram_feeder_ids) > 1:
            diagram_feeder_resolution = "CONFLICTING_UNIQUE_RMU_FEEDERS"
            self.log(
                f"[{parsed.path.name}] 同图唯一环网柜推断出多个FEEDER_ID："
                f"{','.join(str(x) for x in diagram_feeder_ids)}；"
                "不使用G.facID，重名环网柜无法自动选定。"
            )
        else:
            diagram_feeder_resolution = "NO_UNIQUE_RMU_FEEDER"

        # Resolve ordinary duplicate database names against the feeder before
        # allocating NO placeholders.  Their concrete RMU IDs are reserved so
        # the placeholder pool cannot reuse an RMU already represented by a
        # normal graphical name in this drawing.
        if diagram_feeder_id is not None and not name_assignment_error:
            for frame in frames:
                choice = graphical_name_choices.get(frame.frame.xml_id)
                if not choice or is_no_rmu_name(choice.get("name")):
                    continue
                duplicate_items = graphical_duplicate_groups.get(
                    choice["name"].casefold(), []
                )
                if duplicate_items:
                    continue
                resolved_before = pre_resolved_names.get(
                    frame.frame.xml_id, {}
                )
                selected_before = resolved_before.get("selected") or {}
                all_before = list(
                    selected_before.get("db_all_records")
                    or selected_before.get("db_records")
                    or []
                )
                if len(all_before) <= 1:
                    continue
                try:
                    pre_resolved_names[frame.frame.xml_id] = (
                        self._resolve_rmu_name(
                            parsed,
                            frame,
                            positions,
                            preassigned_candidates=preassigned_name_candidates,
                            source_feeder_id=diagram_feeder_id,
                        )
                    )
                except Exception as exc:
                    pre_resolved_names[frame.frame.xml_id] = {
                        "status": "FAIL",
                        "reason": (
                            "RMU_NAME_RESOLUTION_ERROR: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                        "candidate_rows": [],
                        "selected": None,
                    }

        reserved_rmu_ids = set()
        for resolved in pre_resolved_names.values():
            if resolved.get("status") != "PASS":
                continue
            selected = resolved.get("selected") or {}
            records = selected.get("db_records") or []
            if len(records) == 1:
                record_id = int_or_none(records[0].get("id"))
                if record_id is not None:
                    reserved_rmu_ids.add(record_id)

        # Jazan placeholder allocation.  A NO / NO-* graphical label is not
        # looked up as an ordinary RMU NAME.  Instead, all database parent
        # rows belonging to the feeder inferred from another RMU form a pool.
        # Exact database-name matches win; otherwise the remaining rows are
        # assigned deterministically in database-id/name order.  Each row is
        # removed from the pool immediately, so two graphical placeholders can
        # never receive the same combined-device ID.
        no_placeholder_frames = [
            (frame, graphical_name_choices.get(frame.frame.xml_id))
            for frame in frames
            if graphical_name_choices.get(frame.frame.xml_id)
            and is_no_rmu_name(
                graphical_name_choices[frame.frame.xml_id].get("name")
            )
        ]
        if no_placeholder_frames:
            if diagram_feeder_id is None:
                for frame, choice in no_placeholder_frames:
                    pre_resolved_names[frame.frame.xml_id] = (
                        self._no_placeholder_resolution(
                            choice,
                            None,
                            None,
                        )
                    )
            else:
                try:
                    pool_loader = getattr(
                        self.db,
                        "get_rmu_records_by_feeder_id",
                        None,
                    )
                    if not callable(pool_loader):
                        raise AttributeError(
                            "数据库客户端未实现按FEEDER_ID读取环网柜记录"
                        )
                    pool = list(pool_loader(diagram_feeder_id) or [])
                    available = [
                        row for row in pool
                        if int_or_none(row.get("id")) is not None
                        and int_or_none(row.get("id")) not in reserved_rmu_ids
                    ]
                    available.sort(
                        key=lambda row: (
                            norm(row.get("name")).casefold(),
                            int_or_none(row.get("id"))
                            if int_or_none(row.get("id")) is not None
                            else 2**63 - 1,
                        )
                    )
                    pool_count = len(available)
                    for assignment_index, (frame, choice) in enumerate(
                        no_placeholder_frames,
                        start=1,
                    ):
                        selected_record = None
                        matched_by_name = False
                        choice_name = norm(choice.get("name"))
                        for row in available:
                            if norm(row.get("name")).casefold() == choice_name.casefold():
                                selected_record = row
                                matched_by_name = True
                                break
                        if selected_record is None and available:
                            selected_record = available[0]
                        if selected_record is not None:
                            available.remove(selected_record)
                            selected_id = int_or_none(
                                selected_record.get("id")
                            )
                            if selected_id is not None:
                                reserved_rmu_ids.add(selected_id)
                        pre_resolved_names[frame.frame.xml_id] = (
                            self._no_placeholder_resolution(
                                choice,
                                selected_record,
                                diagram_feeder_id,
                                pool_count=pool_count,
                                assignment_index=assignment_index,
                                matched_by_name=matched_by_name,
                            )
                        )
                except Exception as exc:
                    error_code = (
                        "RMU_NO_PLACEHOLDER_QUERY_FAILED: "
                        f"按FEEDER_ID={diagram_feeder_id}读取NO占位环网柜池失败："
                        f"{type(exc).__name__}: {exc}"
                    )
                    for frame, choice in no_placeholder_frames:
                        pre_resolved_names[frame.frame.xml_id] = (
                            self._no_placeholder_resolution(
                                choice,
                                None,
                                diagram_feeder_id,
                                error_code=error_code,
                            )
                        )

        report = {
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "breaker_name_source": self.breaker_name_source,
            "rmu_frame_count": len(frames),
            "diagram_feeder_id": diagram_feeder_id or "",
            "diagram_feeder_ids": diagram_feeder_ids,
            "diagram_feeder_resolution": diagram_feeder_resolution,
            "diagram_feeder_source": diagram_feeder_source or {},
            "rmu_results": [],
            "summary": {},
        }

        for index, frame in enumerate(frames, start=1):
            if progress_callback:
                progress_callback(
                    index - 1,
                    max(len(frames), 1),
                    f"正在处理环网柜 {index}/{len(frames)}",
                )

            type_info = self.parser.classify_rmu_type(parsed, frame)
            smart_info = preassigned_smart_markers.get(
                frame.frame.xml_id,
                {
                    "is_smart": False,
                    "markers": [],
                    "marker_types": [],
                },
            )

            self.log(
                f"[{parsed.path.name}] 环网柜 {index}/{len(frames)}："
                f"矩形框 XML ID={frame.frame.xml_id}；"
                f"类型={type_info.get('rmu_type', 'UNKNOWN')}；"
                f"类型来源={type_info.get('source', 'UNRESOLVED')}；"
                f"智能={'YES' if smart_info.get('is_smart') else 'NO'}；"
                f"智能标识={','.join(smart_info.get('marker_types', [])) or '-'}"
            )
            if not type_info.get("consistent", True):
                if type_info.get("devref_status") != "PASS":
                    self.log(
                        f"  RMU devref模板结构校验异常："
                        f"图内文字={type_info.get('text_type')}；"
                        f"devref类型={type_info.get('devref_type')}；"
                        f"Y类模板={','.join(type_info.get('devref_templates_y', [])) or '-'}；"
                        f"Q类模板={','.join(type_info.get('devref_templates_q', [])) or '-'}；"
                        f"原因={type_info.get('devref_reason') or '-'}；"
                        f"最终类型来源={type_info.get('source', 'UNRESOLVED')}。"
                    )
                else:
                    self.log(
                        f"  RMU类型交叉校验不一致："
                        f"图内文字={type_info.get('text_type')}；"
                        f"devref={type_info.get('devref_type')}；"
                        "最终按有效devref类型。"
                    )

            graphical_choice = graphical_name_choices.get(frame.frame.xml_id)
            rmu_result = {
                "frame_index": index,
                "frame_xml_id": frame.frame.xml_id,
                "rmu_name": "",
                "rmu_type": type_info.get("rmu_type", "UNKNOWN"),
                "rmu_type_source": type_info.get("source", "UNRESOLVED"),
                "rmu_type_text": type_info.get("text_type", "UNKNOWN"),
                "rmu_type_devref": type_info.get("devref_type", "UNKNOWN"),
                "rmu_type_consistent": "YES" if type_info.get("consistent") else "NO",
                "rmu_type_check_status": (
                    "PASS" if type_info.get("consistent") else "WARN"
                ),
                "rmu_type_check_reason": (
                    ""
                    if type_info.get("consistent")
                    else (
                        (
                            "RMU_DEVREF_TEMPLATE_INVALID: "
                            f"环网柜={{RMU_NAME}}；"
                            "仅检查柜内CBreakerDis，ZhaiWaiJieDiDaoZha等其它图元不参与；"
                            f"Y类devref模板={','.join(type_info.get('devref_templates_y', [])) or '-'}；"
                            f"Q类devref模板={','.join(type_info.get('devref_templates_q', [])) or '-'}；"
                            f"devref类型={type_info.get('devref_type', 'UNKNOWN')}；"
                            f"原因={type_info.get('devref_reason') or '-'}；"
                            f"最终类型来源={type_info.get('source', 'UNRESOLVED')}。"
                            "请检查同类Y/Q开关是否混用了不同devref模板。"
                        )
                        if type_info.get("devref_status") != "PASS"
                        else (
                            "RMU_TYPE_CROSS_CHECK_MISMATCH: "
                            f"环网柜={{RMU_NAME}}；"
                            f"柜内Y/Q文字类型={type_info.get('text_type', 'UNKNOWN')}；"
                            f"devref类型={type_info.get('devref_type', 'UNKNOWN')}；"
                            "最终采用有效devref类型，请检查该环网柜的Y/Q文字命名与开关devref模板是否一致。"
                        )
                    )
                ),
                "rmu_type_labels": ", ".join(type_info.get("text_labels", [])),
                "rmu_is_smart": "YES" if smart_info.get("is_smart") else "NO",
                "rmu_smart_marker_types": ", ".join(
                    smart_info.get("marker_types", [])
                ),
                "rmu_smart_markers": smart_info.get("markers", []),
                "rmu_status": "",
                "rmu_severity": "",
                "rmu_reason": "",
                "rmu_db_count": 0,
                "rmu_db_all_count": 0,
                "rmu_feeder_id": "",
                "diagram_feeder_id": diagram_feeder_id or "",
                "rmu_id": "",
                "graphical_duplicate": (
                    "YES"
                    if graphical_choice
                    and not is_no_rmu_name(graphical_choice["name"])
                    and graphical_choice["name"].casefold()
                    in graphical_duplicate_groups
                    else "NO"
                ),
                "no_placeholder": (
                    "YES"
                    if graphical_choice
                    and is_no_rmu_name(graphical_choice["name"])
                    else "NO"
                ),
                "no_assignment_status": "",
                "no_assignment_source": "",
                "no_assignment_index": "",
                "no_assignment_pool_count": "",
                "graphical_duplicate_count": (
                    len(
                        graphical_duplicate_groups.get(
                            graphical_choice["name"].casefold(), []
                        )
                    )
                    if graphical_choice
                    and not is_no_rmu_name(graphical_choice["name"])
                    else 0
                ),
                "graphical_duplicate_frame_indexes": ",".join(
                    str(item["frame_index"])
                    for item in (
                        graphical_duplicate_groups.get(
                            graphical_choice["name"].casefold(), []
                        )
                        if graphical_choice
                        and not is_no_rmu_name(graphical_choice["name"])
                        else []
                    )
                ),
                "diagram_feeder_source": (
                    "YES"
                    if diagram_feeder_source
                    and frame.frame.xml_id == diagram_feeder_source.get("frame_xml_id")
                    else "NO"
                ),
                "rmu_records": [],
                "rmu_ids": [],
                "device_rows": [],
                "db_inventory": {},
                "g_inventory": {},
                "inventory_issues": [],
                "db_integrity_issues": [],
                "association_eligible": False,
                # RMU-level blockers only. Device-level failures must NEVER
                # disable association of other valid devices in a unique RMU.
                "association_block_reasons": [],
                "device_block_reasons": [],
                "label_candidates": [],
            }
            if graphical_choice:
                rmu_result["rmu_name"] = graphical_choice["name"]

            if name_assignment_error:
                resolved = {
                    "status": "FAIL",
                    "reason": name_assignment_error,
                    "candidate_rows": [],
                    "selected": None,
                }
            else:
                resolved = pre_resolved_names.get(frame.frame.xml_id, {})
                selected_before_feeder = resolved.get("selected")
                all_records_before_feeder = list(
                    (selected_before_feeder or {}).get("db_all_records")
                    or (selected_before_feeder or {}).get("db_records")
                    or []
                )

                try:
                    is_graphical_duplicate = (
                        rmu_result.get("graphical_duplicate") == "YES"
                    )
                    is_no_placeholder = (
                        rmu_result.get("no_placeholder") == "YES"
                    )
                    if is_graphical_duplicate or is_no_placeholder:
                        # The graphical duplicate warning is authoritative;
                        # a NO placeholder assignment is also authoritative;
                        # do not re-query the placeholder by its literal name.
                        pass
                    elif diagram_feeder_id is not None:
                        # Re-resolve the name with the feeder inferred from a
                        # unique RMU elsewhere in this same G file.
                        resolved = self._resolve_rmu_name(
                            parsed,
                            frame,
                            positions,
                            preassigned_candidates=preassigned_name_candidates,
                            source_feeder_id=diagram_feeder_id,
                        )
                    elif len(all_records_before_feeder) > 1:
                        # Different FEEDER_ID values are not themselves an
                        # abnormal duplicate, but without a drawing feeder
                        # there is no safe COMBINED_ID to use for write-back.
                        resolved = dict(resolved)
                        resolved["status"] = "FAIL"
                        resolved["reason"] = (
                            "RMU_DIAGRAM_FEEDER_NOT_RESOLVED: "
                            "同名环网柜属于不同FEEDER_ID，但本张G图没有"
                            "可唯一确定馈线的环网柜。"
                        )
                    # With one parent row, the pre-pass result is already
                    # authoritative and does not require a second query.
                except Exception as exc:
                    resolved = {
                        "status": "FAIL",
                        "reason": (
                            "RMU_NAME_RESOLUTION_ERROR: "
                            f"{type(exc).__name__}: {exc}"
                        ),
                        "candidate_rows": [],
                        "selected": None,
                    }

            rmu_result["label_candidates"] = resolved["candidate_rows"]
            rmu_result["rmu_status"] = resolved["status"]
            rmu_result["rmu_reason"] = resolved["reason"]
            if resolved["status"] == "PASS":
                rmu_result["rmu_severity"] = "PASS"
            else:
                rmu_result["rmu_severity"] = "ERROR"

            selected = resolved.get("selected")
            display_candidate = selected
            if display_candidate is None and resolved.get("candidate_rows"):
                display_candidate = resolved["candidate_rows"][0]
            if display_candidate:
                rmu_result["rmu_name"] = display_candidate["name"]
                if rmu_result.get("rmu_type_check_reason"):
                    rmu_result["rmu_type_check_reason"] = (
                        rmu_result["rmu_type_check_reason"].replace(
                            "{RMU_NAME}",
                            str(rmu_result["rmu_name"] or "-"),
                        )
                    )
                    self.log(
                        "  柜型交叉验证告警："
                        + rmu_result["rmu_type_check_reason"]
                    )
                rmu_result["rmu_db_count"] = display_candidate["db_count"]
                rmu_result["rmu_db_all_count"] = display_candidate.get(
                    "db_all_count",
                    display_candidate["db_count"],
                )
                rmu_result["rmu_records"] = display_candidate["db_records"]
                rmu_result["rmu_ids"] = [
                    int_or_none(rec.get("id"))
                    for rec in display_candidate["db_records"]
                    if int_or_none(rec.get("id")) is not None
                ]
                if display_candidate["db_records"]:
                    rmu_result["rmu_feeder_id"] = (
                        display_candidate["db_records"][0].get("feeder_id", "")
                    )
                rmu_result["no_assignment_status"] = (
                    "ASSIGNED"
                    if display_candidate.get("no_placeholder") == "YES"
                    and display_candidate["db_records"]
                    else (
                        "NOT_ASSIGNED"
                        if display_candidate.get("no_placeholder") == "YES"
                        else ""
                    )
                )
                rmu_result["no_assignment_source"] = display_candidate.get(
                    "no_assignment_source", ""
                )
                rmu_result["no_assignment_index"] = display_candidate.get(
                    "no_assignment_index", ""
                )
                rmu_result["no_assignment_pool_count"] = display_candidate.get(
                    "no_assignment_pool_count", ""
                )

            if (
                rmu_result.get("rmu_type_check_reason")
                and "{RMU_NAME}" in rmu_result["rmu_type_check_reason"]
            ):
                fallback_rmu_ref = (
                    rmu_result.get("rmu_name")
                    or f"矩形框XML={frame.frame.xml_id}"
                )
                rmu_result["rmu_type_check_reason"] = (
                    rmu_result["rmu_type_check_reason"].replace(
                        "{RMU_NAME}",
                        str(fallback_rmu_ref),
                    )
                )
                self.log(
                    "  柜型交叉验证告警："
                    + rmu_result["rmu_type_check_reason"]
                )

            if resolved["status"] != "PASS":
                self.log(
                    f"  当前环网柜校验未通过：{resolved['reason']}；"
                    f"数据库记录数={rmu_result.get('rmu_db_count', 0)}。"
                )
                rmu_result["association_block_reasons"].append(
                    self._rmu_identity_block_reason(
                        resolved["reason"],
                        frame.frame.xml_id,
                        rmu_result.get("rmu_name", ""),
                    )
                )
                self._append_unresolved_rmu_device_rows(
                    parsed,
                    frame,
                    rmu_result,
                    resolved["reason"],
                    skip_db_lookup=(
                        rmu_result.get("graphical_duplicate") == "YES"
                        or (
                            rmu_result.get("no_placeholder") == "YES"
                            and resolved.get("status") != "PASS"
                        )
                    ),
                )
                self._validate_nonunique_rmu_existing_links(rmu_result)
                self._validate_one_to_one_device_mapping(rmu_result)

                # RMU identity itself is 0/multiple: whole-RMU automatic
                # association is forbidden, even if some manual KeyIDs are
                # individually correct.
                rmu_result["association_eligible"] = False

                # Keep statistics meaningful even when RMU identity is
                # non-unique. Device rows may still contain valid/invalid
                # manually linked models that were inspected above.
                g_rows = [
                    row for row in rmu_result["device_rows"]
                    if row.get("xml_id")
                ]
                rmu_result["linked_correct_count"] = sum(
                    1 for row in g_rows
                    if row.get("model_link_correct") == "YES"
                )
                rmu_result["unlinked_count"] = sum(
                    1 for row in g_rows
                    if row.get("model_linked") == "NO"
                )
                rmu_result["linked_wrong_count"] = sum(
                    1 for row in g_rows
                    if (
                        row.get("model_linked") == "YES"
                        and row.get("model_link_correct") == "NO"
                    )
                )

                report["rmu_results"].append(rmu_result)
                continue

            rmu_record = selected["db_records"][0]
            rmu_id = int_or_none(rmu_record.get("id"))
            rmu_result["rmu_id"] = rmu_id
            rmu_result["rmu_ids"] = [rmu_id] if rmu_id is not None else []

            # Query all configured DB device sets for the RMU.
            db_sets = {}
            for tag, rule in self.device_rules.items():
                try:
                    if tag == RMU_RELAY_SIGNAL_TAG:
                        table_name, rows = self.db.get_relay_signals_by_combined_id(
                            rmu_id,
                            RMU_RELAY_SIGNAL_CODE,
                            table_id=int(rule["table_id"]),
                        )
                    else:
                        table_name, rows = self.db.get_devices_by_combined_id(
                            int(rule["table_id"]), rmu_id
                        )
                    db_sets[tag] = {
                        "table_id": int(rule["table_id"]),
                        "table_name": table_name,
                        "domain": int(rule["domain"]),
                        "rows": rows,
                    }
                    rmu_result["db_inventory"][tag] = {
                        "table_id": int(rule["table_id"]),
                        "table_name": table_name,
                        "domain": int(rule["domain"]),
                        "count": len(rows),
                    }
                except Exception as exc:
                    db_sets[tag] = {
                        "table_id": int(rule["table_id"]),
                        "table_name": "",
                        "domain": int(rule["domain"]),
                        "rows": [],
                        "error": str(exc),
                    }
                    rmu_result["db_inventory"][tag] = {
                        "table_id": int(rule["table_id"]),
                        "table_name": "",
                        "domain": int(rule["domain"]),
                        "count": 0,
                        "error": str(exc),
                    }
                    rmu_result["device_block_reasons"].append(
                        f"DEVICE_TABLE_QUERY_FAILED:{tag}"
                    )

            self.log(
                f"  环网柜设备查询：RMU_ID={rmu_id}；"
                f"FEEDER_ID={rmu_result.get('rmu_feeder_id') or '-'}；"
                + "; ".join(
                    f"{tag}={info.get('table_name') or '-'}"
                    f"/rows={info.get('count', 0)}"
                    for tag, info in rmu_result["db_inventory"].items()
                )
            )

            elements = self.parser.find_target_objects_in_frame(
                parsed, frame, self.device_rules.keys()
            )
            elements_by_tag = defaultdict(list)
            for elem in elements:
                elements_by_tag[elem.tag].append(elem)

            # Only the explicitly named Normal pwbh object is a relay signal.
            # Other pwbh objects in the same RMU are unrelated graphics.
            elements_by_tag[RMU_RELAY_SIGNAL_TAG] = [
                elem
                for elem in elements_by_tag.get(RMU_RELAY_SIGNAL_TAG, [])
                if self._is_normal_relay_signal(elem)
            ]

            # The G file is authoritative for device validation.
            #
            # Do NOT compare the complete database inventory count with the G
            # object count.  A combined_id may legitimately contain historical
            # or otherwise unrelated DB records.  Only CODE values requested by
            # actual G elements are validated below.
            for tag in self.device_rules:
                rmu_result["g_inventory"][tag] = len(elements_by_tag[tag])

            breakers = elements_by_tag.get("CBreakerDis", [])
            grounds = elements_by_tag.get("ZhaiWaiJieDiDaoZha", [])
            buses = elements_by_tag.get("BusDis", [])

            graph_names = self.parser.resolve_breaker_graphical_names(
                parsed,
                frame,
                breakers,
            )

            # Visible text inside the RMU is the ONLY breaker-name source.
            breaker_names = {}
            for br in breakers:
                info = graph_names.get(br.xml_id, {})
                breaker_names[br.xml_id] = (
                    norm(info.get("name"))
                    if info.get("status") == "PASS"
                    else ""
                )

            # Pair ground symbols to breakers by nearest one-to-one geometry.
            ground_to_breaker = self.parser.pair_objects_nearest(grounds, breakers)
            breaker_by_id = {b.xml_id: b for b in breakers}

            # CBreakerDis
            for elem in breakers:
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(
                    rmu_result["rmu_name"],
                    rmu_id,
                    elem,
                    rule,
                    db_set,
                )
                graphical_name = norm(graph_names.get(elem.xml_id, {}).get("name"))
                selected_name = breaker_names.get(elem.xml_id, "")
                info = graph_names.get(elem.xml_id, {})
                if info.get("status") != "PASS":
                    row["selected_name_source"] = "GRAPHICAL_TEXT"
                    row["graphical_name"] = graphical_name
                    row["logical_code"] = ""
                    self._set_fail(
                        row,
                        info.get(
                            "reason",
                            "GRAPHICAL_NAME_NOT_RESOLVED",
                        ),
                    )
                else:
                    self._validate_breaker(
                        row,
                        elem,
                        db_set,
                        rule,
                        selected_name,
                        graphical_name,
                    )
                rmu_result["device_rows"].append(row)

            # Ground disconnectors
            for elem in grounds:
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(
                    rmu_result["rmu_name"],
                    rmu_id,
                    elem,
                    rule,
                    db_set,
                )
                br_id = ground_to_breaker.get(elem.xml_id, "")
                breaker_name = breaker_names.get(br_id, "")
                self._validate_ground(row, elem, db_set, rule, breaker_name)
                rmu_result["device_rows"].append(row)

            # Bus
            for elem in buses:
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(
                    rmu_result["rmu_name"],
                    rmu_id,
                    elem,
                    rule,
                    db_set,
                )
                self._validate_bus(row, elem, db_set, rule)
                rmu_result["device_rows"].append(row)

            # Fixed EFI relay signal inside the RMU.
            for elem in elements_by_tag.get(RMU_RELAY_SIGNAL_TAG, []):
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(
                    rmu_result["rmu_name"],
                    rmu_id,
                    elem,
                    rule,
                    db_set,
                )
                row["current_keyid"] = self._relay_keyid(elem)
                row["model_linked"] = (
                    "YES" if row["current_keyid"] else "NO"
                )
                self._validate_relay_signal(row, elem, db_set, rule)
                rmu_result["device_rows"].append(row)

            # Enforce hard one-to-one mapping after all G target rows have
            # been resolved. This catches duplicate logical CODE values
            # or multiple G elements consuming the same database device.
            self._validate_one_to_one_device_mapping(rmu_result)

            # Database rows that are not requested by any G element are
            # intentionally ignored and are not emitted into device details.
            # Device details must contain G-file elements only.

            # Relevant model quantity check.
            #
            # For each G object type, every G element must resolve to one unique
            # database device through CODE.  Unrelated database records do not
            # participate in this count.
            for tag in self.device_rules:
                typed_rows = [
                    row for row in rmu_result["device_rows"]
                    if row.get("xml_id") and row.get("object_type") == tag
                ]
                matched_ids = [
                    int_or_none(row.get("db_device_id"))
                    for row in typed_rows
                    if int_or_none(row.get("db_device_id")) is not None
                ]
                unique_matched_ids = set(matched_ids)

                g_count = len(typed_rows)
                matched_count = len(unique_matched_ids)

                rmu_result["db_inventory"].setdefault(tag, {})
                rmu_result["db_inventory"][tag]["relevant_match_count"] = matched_count
                rmu_result["db_inventory"][tag]["g_required_count"] = g_count

                if matched_count != g_count:
                    issue = (
                        f"RELEVANT_DEVICE_MATCH_COUNT_MISMATCH:"
                        f"{tag}:G={g_count}:MATCHED={matched_count}"
                    )
                    rmu_result["inventory_issues"].append(issue)

            # Link-state statistics are reported per RMU.
            g_rows = [r for r in rmu_result["device_rows"] if r.get("xml_id")]
            rmu_result["linked_correct_count"] = sum(
                1 for r in g_rows if r.get("model_link_correct") == "YES"
            )
            rmu_result["unlinked_count"] = sum(
                1 for r in g_rows if r.get("model_linked") == "NO"
            )
            rmu_result["linked_wrong_count"] = sum(
                1 for r in g_rows
                if r.get("model_linked") == "YES" and r.get("model_link_correct") == "NO"
            )

            # Device-level failures are collected separately. They block only
            # the affected G elements, never other valid devices in this
            # UNIQUE RMU.
            row_blocks = [
                r for r in g_rows
                if r.get("association_ready") != "YES"
            ]
            for r in row_blocks:
                rmu_result["device_block_reasons"].append(
                    f"{r.get('object_type')}:{r.get('xml_id')}:{r.get('reason')}"
                )

            # Deduplicate RMU-level blockers.
            seen = set()
            unique_reasons = []
            for reason in rmu_result["association_block_reasons"]:
                if reason not in seen:
                    seen.add(reason)
                    unique_reasons.append(reason)
            rmu_result["association_block_reasons"] = unique_reasons

            # Deduplicate device-level blockers.
            seen = set()
            device_reasons = []
            for reason in rmu_result["device_block_reasons"]:
                if reason not in seen:
                    seen.add(reason)
                    device_reasons.append(reason)
            rmu_result["device_block_reasons"] = device_reasons

            # This branch is reached only when the RMU NAME resolved uniquely.
            # Therefore the RMU remains eligible for PARTIAL association even
            # when some device rows fail. preview_association() will write only
            # rows with association_ready=YES and writeback_needed=YES.
            rmu_result["association_eligible"] = not unique_reasons

            action_required = any(
                row.get("status") in ("WARN", "RELINK", "RMU_RELINK")
                for row in g_rows
            )

            if unique_reasons:
                rmu_result["rmu_status"] = "FAIL"
                rmu_result["rmu_severity"] = "ERROR"
                rmu_result["rmu_reason"] = "RMU_MODEL_DATA_INVALID"
            elif device_reasons:
                rmu_result["rmu_status"] = "WARN"
                rmu_result["rmu_severity"] = "DEVICE_ERROR"
                rmu_result["rmu_reason"] = "RMU_PARTIAL_DEVICE_ERRORS"
            elif action_required:
                rmu_result["rmu_status"] = "WARN"
                rmu_result["rmu_severity"] = "ASSOCIATION_ACTION_REQUIRED"
                rmu_result["rmu_reason"] = "RMU_ASSOCIATION_ACTION_REQUIRED"
            elif rmu_result.get("rmu_type_check_status") == "WARN":
                rmu_result["rmu_status"] = "WARN"
                rmu_result["rmu_severity"] = "TYPE_CROSS_CHECK_WARNING"
                rmu_result["rmu_reason"] = (
                    rmu_result.get("rmu_type_check_reason")
                    or "RMU_TYPE_CROSS_CHECK_MISMATCH"
                )
            else:
                rmu_result["rmu_status"] = "PASS"
                rmu_result["rmu_severity"] = "PASS"
                rmu_result["rmu_reason"] = "RMU_MODEL_DATA_VALID"

            report["rmu_results"].append(rmu_result)

        rmus = report["rmu_results"]
        device_rows = [d for r in rmus for d in r.get("device_rows", [])]
        report["summary"] = {
            "rmu_frames": len(frames),
            "rmu_pass": sum(1 for r in rmus if r.get("rmu_status") == "PASS"),
            "rmu_fail": sum(1 for r in rmus if r.get("rmu_status") == "FAIL"),
            "rmu_association_eligible": sum(1 for r in rmus if r.get("association_eligible")),
            "elements": len([d for d in device_rows if d.get("xml_id")]),
            "element_pass": sum(1 for d in device_rows if d.get("status") == "PASS"),
            "element_warn": sum(
                1 for d in device_rows
                if d.get("status") in ("WARN", "RELINK", "RMU_RELINK")
            ),
            "element_fail": sum(
                1 for d in device_rows
                if d.get("status") in ("FAIL", "RMU_LINK", "BLOCKED")
            ),
            "model_linked_correct": sum(
                1 for d in device_rows if d.get("model_link_correct") == "YES"
            ),
            "model_unlinked": sum(
                1 for d in device_rows if d.get("model_linked") == "NO"
            ),
            "model_linked_wrong": sum(
                1 for d in device_rows
                if d.get("model_linked") == "YES" and d.get("model_link_correct") == "NO"
            ),
        }
        if progress_callback:
            progress_callback(max(len(frames), 1), max(len(frames), 1), "当前 G 文件处理完成")
        return report
