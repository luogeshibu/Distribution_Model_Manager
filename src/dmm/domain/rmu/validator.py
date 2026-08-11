#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

from dmm.domain.gfile.parser import GParser, RmuFrame, GObject
from dmm.infrastructure.database.oracle import OracleClient

KEYID_STEP = 2 ** 32


def norm(v) -> str:
    return "" if v is None else str(v).strip()


def int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


class RmuValidator:
    def __init__(
        self,
        db: OracleClient,
        parser: GParser,
        device_rules: Dict[str, Dict[str, Any]],
        breaker_name_source: str = "P_NAME_STRING",
        log=None,
    ):
        self.db = db
        self.parser = parser
        self.device_rules = device_rules
        self.breaker_name_source = breaker_name_source
        self.log = log or (lambda msg: None)

    def _resolve_rmu_name(self, parsed, frame: RmuFrame, positions: Sequence[str]):
        all_candidates = self.parser.find_label_candidates(
            parsed,
            frame,
            positions,
        )
        frame.label_candidates = all_candidates

        if not all_candidates:
            return {
                "status": "FAIL",
                "reason": "RMU_NAME_NOT_FOUND",
                "candidate_rows": [],
                "selected": None,
            }

        # --------------------------------------------------------------
        # RMU name selection rule
        # --------------------------------------------------------------
        # 1. Candidate ownership has already been resolved by GParser:
        #    one Text can belong to only one nearest RMU frame.
        #
        # 2. If this RMU has ONLY ONE candidate in the selected direction,
        #    use it directly, regardless of color.
        #
        # 3. If this RMU has MULTIPLE candidates:
        #       - if green candidates exist -> choose nearest green;
        #       - otherwise -> choose nearest candidate regardless of color.
        #
        # Green is therefore only a disambiguation rule for "multiple names",
        # not a global priority rule.
        # --------------------------------------------------------------
        ordered = sorted(
            all_candidates,
            key=lambda c: (
                c.score,
                c.obj.xml_index,
                c.text,
            ),
        )

        if len(ordered) == 1:
            chosen = ordered[0]
            selection_reason = "SINGLE_NEAREST_LABEL"
        else:
            green_candidates = [c for c in ordered if c.is_green]
            if green_candidates:
                chosen = min(
                    green_candidates,
                    key=lambda c: (
                        c.score,
                        c.obj.xml_index,
                        c.text,
                    ),
                )
                selection_reason = "MULTIPLE_LABELS_GREEN_PRIORITY"
            else:
                chosen = ordered[0]
                selection_reason = "MULTIPLE_LABELS_NEAREST_FALLBACK"

        candidate_rows = []
        selected_row = None

        for c in all_candidates:
            records = self.db.get_rmu_records(c.text)
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
                "selected_by_rule": "YES" if c is chosen else "NO",
                "selection_reason": (
                    selection_reason if c is chosen else ""
                ),
            }
            candidate_rows.append(row)

            if c is chosen:
                selected_row = row

        records = self.db.get_rmu_records(chosen.text)

        if len(records) == 1:
            return {
                "status": "PASS",
                "reason": (
                    "RMU_CONFIRMED_SINGLE_LABEL"
                    if len(ordered) == 1
                    else (
                        "RMU_CONFIRMED_GREEN_LABEL"
                        if chosen.is_green
                        else "RMU_CONFIRMED_NEAREST_LABEL"
                    )
                ),
                "candidate_rows": candidate_rows,
                "selected": selected_row,
            }

        if len(records) > 1:
            return {
                "status": "FAIL",
                "reason": "RMU_DUPLICATE_IN_DATABASE",
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
    def _default_device_row(rmu_name, rmu_id, elem, rule, db_set):
        return {
            "rmu_name": rmu_name,
            "rmu_id": rmu_id,
            "object_type": elem.tag,
            "xml_id": elem.xml_id,
            "p_name_string": elem.p_name,
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
        row["status"] = "RMU_LINK"
        row["severity"] = "RMU_LINK_MISMATCH"
        row["reason"] = reason
        row["association_ready"] = "NO"

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

        - one logical p_NameString may correspond to only one G target row;
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
            logical_name = norm(row.get("p_name_string"))
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
                "G_PNAME_NOT_ONE_TO_ONE: "
                f"p_NameString={logical_name} 在同一环网柜内被多个G图元使用；"
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

    def _evaluate_current_model(self, row, elem, device_id, rule, rmu_id):
        """
        Evaluate an existing KeyID for a UNIQUE RMU.

        Feeder is intentionally NOT checked.

        Hard validation rules:
        - expected database device must already be uniquely resolved by CODE;
        - logical p_NameString/CODE validation must already have passed;
        - invalid/unresolvable KeyID is an error;
        - existing KeyID must resolve to the expected device/table/domain;
        - existing KeyID must belong to the current RMU;
        - existing KeyID must equal Expected KeyID.
        """
        if not elem.keyid:
            row["model_linked"] = "NO"
            row["model_link_correct"] = ""
            row["model_link_status"] = "未关联"
            row["association_action"] = "需要关联"
            row["writeback_needed"] = "YES"
            row["association_ready"] = "YES"
            row["status"] = "WARN"
            row["severity"] = "UNLINKED"
            row["reason"] = "MODEL_NOT_LINKED"
            return

        row["model_linked"] = "YES"
        row["writeback_needed"] = "NO"

        current_keyid = int_or_none(elem.keyid)
        if current_keyid is None:
            row["model_link_correct"] = "NO"
            row["model_link_status"] = "已关联，但KeyID格式错误"
            row["association_action"] = "禁止自动关联"
            self._set_fail(row, "CURRENT_KEYID_INVALID")
            return

        try:
            curv = self.db.verify_keyid(current_keyid)
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

            rmu_match = (
                current_combined_id is not None
                and rmu_id is not None
                and current_combined_id == int(rmu_id)
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

        except Exception as exc:
            row["model_link_correct"] = "NO"
            row["model_link_status"] = "已关联，但KeyID无法反向验证"
            row["association_action"] = "禁止自动关联"
            self._set_fail(
                row,
                f"CURRENT_KEYID_VERIFY_ERROR: {exc}"
            )
            return

        if (
            row.get("current_rmu_match") != "YES"
            or row.get("current_rmu_name_match") != "YES"
        ):
            row["model_link_correct"] = "NO"
            row["model_link_status"] = "已关联，但关联到了其他环网柜"
            row["association_action"] = "禁止自动关联，请检查现有模型"
            self._set_rmu_link_issue(
                row,
                "CURRENT_MODEL_RMU_MISMATCH: "
                f"当前图形环网柜={row.get('rmu_name') or '-'}；"
                f"当前KeyID设备所属环网柜={row.get('current_rmu_name') or '-'}；"
                f"当前combined_id={row.get('current_combined_id') or '-'}；"
                f"期望combined_id={rmu_id or '-'}"
            )
            return

        reasons = []

        if int_or_none(row.get("current_device_id")) != int(device_id):
            reasons.append(
                f"DEVICE_ID不匹配(current={row.get('current_device_id')}, "
                f"expected={device_id})"
            )

        if int_or_none(row.get("current_table_id")) != int(rule["table_id"]):
            reasons.append(
                f"TABLE_ID不匹配(current={row.get('current_table_id')}, "
                f"expected={rule['table_id']})"
            )

        if int_or_none(row.get("current_domain")) != int(rule["domain"]):
            reasons.append(
                f"DOMAIN不匹配(current={row.get('current_domain')}, "
                f"expected={rule['domain']})"
            )

        if current_keyid != int(row["expected_keyid"]):
            reasons.append(
                f"KEYID不匹配(current={current_keyid}, "
                f"expected={row['expected_keyid']})"
            )

        if reasons:
            row["model_link_correct"] = "NO"
            row["model_link_status"] = "模型已关联但关联错误"
            row["association_action"] = "禁止自动关联，请检查现有模型"
            self._set_fail(
                row,
                "MODEL_LINK_WRONG: " + "; ".join(reasons)
            )
            return

        row["model_link_correct"] = "YES"
        row["model_link_status"] = "模型已关联且正确"
        row["association_action"] = "模型已关联，无需关联"
        row["association_ready"] = "YES"
        row["status"] = "PASS"
        row["severity"] = "PASS"
        row["reason"] = "MODEL_ALREADY_LINKED_CORRECT"


    def _inspect_current_link_without_unique_rmu(
        self,
        row,
        elem,
        rmu_reason,
    ):
        """
        RMU database identity is missing or duplicated.

        Summary-level RMU status remains a hard ERROR.

        Device policy:
        - no current KeyID -> hard FAIL, automatic association forbidden;
        - current KeyID exists -> inspect the manual link instead of discarding it;
        - current linked CODE must equal the logical p_NameString;
        - current linked device must belong to an RMU whose NAME equals the
          current G-file RMU name;
        - a correct existing manual link is allowed to remain even though the
          RMU database name itself is duplicated.
        """
        row["association_ready"] = "NO"
        row["writeback_needed"] = "NO"

        if not elem.keyid:
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

        current_keyid = int_or_none(elem.keyid)
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
            if expected_rmu_name and current_rmu_name:
                row["current_rmu_name_match"] = (
                    "YES"
                    if expected_rmu_name == current_rmu_name
                    else "NO"
                )
            else:
                row["current_rmu_name_match"] = "NO"

            # There is no unique expected RMU ID in this branch.
            row["current_rmu_match"] = "N/A"

            # Existing model belongs to another RMU -> hard error.
            if row.get("current_rmu_name_match") != "YES":
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
            or norm(row.get("p_name_string"))
        )

        if not expected_code:
            self._set_fail(row, "P_NAME_STRING_EMPTY")
            return

        if not row.get("db_code"):
            self._set_fail(row, "DB_CODE_EMPTY")
            return

        if row.get("db_code") != expected_code:
            self._set_fail(
                row,
                "CURRENT_LINK_CODE_MISMATCH: "
                f"CODE={row.get('db_code')}, PNAME={expected_code}"
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
        Additional consistency rule for a non-unique RMU name.

        The RMU summary still fails because the RMU name is not unique.
        However, if G elements already contain manual KeyIDs, inspect the
        existing model rather than discarding it.

        All successfully resolved existing KeyIDs inside this G RMU must point
        to ONE AND THE SAME actual dms_combined_device record.  Having the same
        RMU NAME is not enough: if some devices point to duplicate RMU ID A and
        others point to duplicate RMU ID B, the existing model is inconsistent.

        Feeder information is deliberately not involved.
        """
        linked_rows = [
            row for row in rmu_result.get("device_rows", [])
            if row.get("model_linked") == "YES"
        ]
        if not linked_rows:
            return

        resolved_rows = []
        current_rmu_ids = set()

        for row in linked_rows:
            current_id = int_or_none(row.get("current_combined_id"))
            current_name = norm(row.get("current_rmu_name"))
            if current_id is not None:
                current_rmu_ids.add(current_id)
                resolved_rows.append(row)

            # Per-row validation already detects a different RMU name. Keep
            # that hard error; this method adds the cross-device ID check.
            expected_name = norm(rmu_result.get("rmu_name"))
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

        if len(current_rmu_ids) <= 1:
            return

        ids_text = ",".join(str(value) for value in sorted(current_rmu_ids))
        issue = (
            "NONUNIQUE_RMU_EXISTING_LINKS_SPAN_MULTIPLE_RMUS: "
            f"同一G图环网柜内已关联设备实际来自多个环网柜ID：{ids_text}"
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
            row["association_action"] = "禁止自动处理，请检查已有模型关联"
            self._set_rmu_link_issue(
                row,
                "CURRENT_MODEL_RMU_ID_INCONSISTENT: "
                f"当前图形环网柜={rmu_result.get('rmu_name') or '-'}；"
                f"本环网柜已关联设备涉及多个combined_id={ids_text}"
            )

    def _append_unresolved_rmu_device_rows(
        self,
        parsed,
        frame,
        rmu_result,
        resolved_reason,
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

        breakers = elements_by_tag.get("CBreakerDis", [])
        grounds = elements_by_tag.get("ZhaiWaiJieDiDaoZha", [])
        buses = elements_by_tag.get("BusDis", [])

        graph_names = {}
        if self.breaker_name_source == "GRAPHICAL_TEXT":
            graph_names = self.parser.resolve_breaker_graphical_names(
                parsed,
                frame,
                breakers,
            )

        breaker_names = {}
        for br in breakers:
            if self.breaker_name_source == "GRAPHICAL_TEXT":
                info = graph_names.get(br.xml_id, {})
                breaker_names[br.xml_id] = (
                    norm(info.get("name"))
                    if info.get("status") == "PASS"
                    else ""
                )
            else:
                breaker_names[br.xml_id] = br.p_name

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
            return row

        for elem in breakers:
            row = make_row(elem)
            if self.breaker_name_source == "GRAPHICAL_TEXT":
                info = graph_names.get(elem.xml_id, {})
                selected = (
                    norm(info.get("name"))
                    if info.get("status") == "PASS"
                    else ""
                )
                row["selected_name_source"] = "GRAPHICAL_TEXT"
                row["graphical_name"] = selected
                row["p_name_string"] = selected
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
            else:
                row["selected_name_source"] = "P_NAME_STRING"
                row["p_name_string"] = elem.p_name
                row["selected_device_name"] = elem.p_name

            self._inspect_current_link_without_unique_rmu(
                row,
                elem,
                resolved_reason,
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

            if self.breaker_name_source == "GRAPHICAL_TEXT":
                row["p_name_string"] = expected_code
            else:
                row["p_name_string"] = elem.p_name

            if not breaker_name:
                self._set_fail(
                    row,
                    "GROUND_BREAKER_PAIR_NOT_RESOLVED",
                )
            else:
                self._inspect_current_link_without_unique_rmu(
                    row,
                    elem,
                    resolved_reason,
                )
            rmu_result["device_rows"].append(row)

        for elem in buses:
            row = make_row(elem)
            if self.breaker_name_source == "GRAPHICAL_TEXT":
                row["selected_name_source"] = "FIXED_BUS"
                row["p_name_string"] = "BUS"
                row["selected_device_name"] = "BUS"
            else:
                row["selected_name_source"] = "P_NAME_STRING"
                row["p_name_string"] = elem.p_name
                row["selected_device_name"] = elem.p_name

            self._inspect_current_link_without_unique_rmu(
                row,
                elem,
                resolved_reason,
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

    def _validate_breaker(self, row, elem, db_set, rule, selected_name, graphical_name):
        row["graphical_name"] = graphical_name
        row["selected_name_source"] = self.breaker_name_source
        row["selected_device_name"] = selected_name

        # In graphical-name mode, the visible G-file text becomes the logical
        # p_NameString used by every downstream comparison.  The XML attribute
        # p_NameString is intentionally ignored in this mode.
        if self.breaker_name_source == "GRAPHICAL_TEXT":
            effective_p_name = selected_name
        else:
            effective_p_name = elem.p_name
        row["p_name_string"] = effective_p_name

        if not selected_name:
            self._set_fail(row, "BREAKER_NAME_NOT_RESOLVED")
            return

        matches = self._find_by_code(db_set["rows"], selected_name)
        row["db_match_count"] = len(matches)
        if len(matches) == 0:
            self._set_fail(row, f"DEVICE_NOT_FOUND: CODE={selected_name}; 数据库中不存在该设备")
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
        if not effective_p_name:
            self._set_fail(row, "P_NAME_STRING_EMPTY")
            return
        if code != effective_p_name:
            self._set_fail(row, f"CBREAKER_CODE_PNAME_MISMATCH (CODE={code}, PNAME={effective_p_name})")
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

        # When graphical-name mode is selected, the logical p_NameString of a
        # ground disconnector is derived only from its paired breaker: breaker+D.
        # The G XML p_NameString attribute is not used for validation.
        if self.breaker_name_source == "GRAPHICAL_TEXT":
            effective_p_name = expected_code
        else:
            effective_p_name = elem.p_name
        row["p_name_string"] = effective_p_name

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
        if not effective_p_name:
            self._set_fail(row, "P_NAME_STRING_EMPTY")
            return
        if code != effective_p_name:
            self._set_fail(row, f"GROUND_CODE_PNAME_MISMATCH (CODE={code}, PNAME={effective_p_name})")
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
        # In graphical-name mode BusDis does not read G p_NameString.  The
        # business rule defines the logical p_NameString as the fixed value BUS.
        if self.breaker_name_source == "GRAPHICAL_TEXT":
            effective_p_name = "BUS"
            row["selected_name_source"] = "FIXED_BUS"
        else:
            effective_p_name = elem.p_name
            row["selected_name_source"] = "P_NAME_STRING"

        row["p_name_string"] = effective_p_name
        row["selected_device_name"] = effective_p_name

        if not effective_p_name:
            self._set_fail(row, "P_NAME_STRING_EMPTY")
            return

        matches = self._find_by_code(db_set["rows"], effective_p_name)
        row["db_match_count"] = len(matches)
        if len(matches) == 0:
            self._set_fail(row, f"DEVICE_NOT_FOUND: CODE={effective_p_name}; 数据库中不存在该设备")
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
        if code != effective_p_name:
            self._set_fail(row, f"BUS_CODE_PNAME_MISMATCH (CODE={code}, PNAME={effective_p_name})")
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

    def validate_file(self, g_path: str | Path, positions: Sequence[str], progress_callback=None) -> Dict[str, Any]:
        parsed = self.parser.parse(g_path)
        frames = self.parser.find_rmu_frames(parsed)

        report = {
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "breaker_name_source": self.breaker_name_source,
            "rmu_frame_count": len(frames),
            "rmu_results": [],
            "summary": {},
        }

        for index, frame in enumerate(frames, start=1):
            if progress_callback:
                progress_callback(index - 1, max(len(frames), 1), f"正在处理环网柜 {index}/{len(frames)}")
            self.log(
                f"[{parsed.path.name}] 环网柜 {index}/{len(frames)}："
                f"矩形框 XML ID={frame.frame.xml_id}"
            )
            rmu_result = {
                "frame_index": index,
                "frame_xml_id": frame.frame.xml_id,
                "rmu_name": "",
                "rmu_status": "",
                "rmu_severity": "",
                "rmu_reason": "",
                "rmu_db_count": 0,
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

            try:
                resolved = self._resolve_rmu_name(parsed, frame, positions)
            except Exception as exc:
                rmu_result["rmu_status"] = "FAIL"
                rmu_result["rmu_reason"] = f"RMU_LOOKUP_ERROR: {exc}"
                report["rmu_results"].append(rmu_result)
                continue

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
                rmu_result["rmu_db_count"] = display_candidate["db_count"]
                rmu_result["rmu_records"] = display_candidate["db_records"]
                rmu_result["rmu_ids"] = [
                    int_or_none(rec.get("id"))
                    for rec in display_candidate["db_records"]
                    if int_or_none(rec.get("id")) is not None
                ]

            if resolved["status"] != "PASS":
                self.log(
                    f"  当前环网柜校验未通过：{resolved['reason']}；"
                    f"数据库记录数={rmu_result.get('rmu_db_count', 0)}。"
                )
                rmu_result["association_block_reasons"].append(
                    "环网柜ID不唯一或环网柜数据库记录无效，请先检查环网柜模型。"
                )
                self._append_unresolved_rmu_device_rows(
                    parsed,
                    frame,
                    rmu_result,
                    resolved["reason"],
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

            elements = self.parser.find_target_objects_in_frame(
                parsed, frame, self.device_rules.keys()
            )
            elements_by_tag = defaultdict(list)
            for elem in elements:
                elements_by_tag[elem.tag].append(elem)

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

            graph_names = {}
            if self.breaker_name_source == "GRAPHICAL_TEXT":
                graph_names = self.parser.resolve_breaker_graphical_names(
                    parsed, frame, breakers
                )

            # Resolve authoritative breaker names.
            breaker_names = {}
            for br in breakers:
                if self.breaker_name_source == "GRAPHICAL_TEXT":
                    info = graph_names.get(br.xml_id, {})
                    breaker_names[br.xml_id] = norm(info.get("name")) if info.get("status") == "PASS" else ""
                else:
                    breaker_names[br.xml_id] = br.p_name

            # Pair ground symbols to breakers by nearest one-to-one geometry.
            ground_to_breaker = self.parser.pair_objects_nearest(grounds, breakers)
            breaker_by_id = {b.xml_id: b for b in breakers}

            # CBreakerDis
            for elem in breakers:
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(rmu_result["rmu_name"], rmu_id, elem, rule, db_set)
                graphical_name = norm(graph_names.get(elem.xml_id, {}).get("name"))
                selected_name = breaker_names.get(elem.xml_id, "")
                if self.breaker_name_source == "GRAPHICAL_TEXT":
                    info = graph_names.get(elem.xml_id, {})
                    if info.get("status") != "PASS":
                        row["selected_name_source"] = "GRAPHICAL_TEXT"
                        row["graphical_name"] = graphical_name
                        # Graphical mode never falls back to the XML p_NameString.
                        row["p_name_string"] = ""
                        self._set_fail(row, info.get("reason", "GRAPHICAL_NAME_NOT_RESOLVED"))
                    else:
                        self._validate_breaker(row, elem, db_set, rule, selected_name, graphical_name)
                else:
                    self._validate_breaker(row, elem, db_set, rule, selected_name, graphical_name)
                rmu_result["device_rows"].append(row)

            # Ground disconnectors
            for elem in grounds:
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(rmu_result["rmu_name"], rmu_id, elem, rule, db_set)
                br_id = ground_to_breaker.get(elem.xml_id, "")
                breaker_name = breaker_names.get(br_id, "")
                self._validate_ground(row, elem, db_set, rule, breaker_name)
                rmu_result["device_rows"].append(row)

            # Bus
            for elem in buses:
                rule = self.device_rules[elem.tag]
                db_set = db_sets[elem.tag]
                row = self._default_device_row(rmu_result["rmu_name"], rmu_id, elem, rule, db_set)
                self._validate_bus(row, elem, db_set, rule)
                rmu_result["device_rows"].append(row)

            # Enforce hard one-to-one mapping after all G target rows have
            # been resolved. This catches duplicate logical p_NameString values
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

            if unique_reasons:
                rmu_result["rmu_status"] = "FAIL"
                rmu_result["rmu_severity"] = "ERROR"
                rmu_result["rmu_reason"] = "RMU_MODEL_DATA_INVALID"
            elif device_reasons:
                rmu_result["rmu_status"] = "WARN"
                rmu_result["rmu_severity"] = "DEVICE_ERROR"
                rmu_result["rmu_reason"] = "RMU_PARTIAL_DEVICE_ERRORS"
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
                if d.get("status") == "WARN"
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
