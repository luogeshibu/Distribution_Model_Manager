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
        candidates = self.parser.find_label_candidates(parsed, frame, positions)
        frame.label_candidates = candidates

        if not candidates:
            return {
                "status": "FAIL",
                "reason": "RMU_NAME_NOT_FOUND",
                "candidate_rows": [],
                "selected": None,
            }

        by_text = defaultdict(list)
        for c in candidates:
            by_text[c.text].append(c)

        candidate_rows = []
        unique_db_candidates = []
        duplicate_db_candidates = []

        for text, items in sorted(by_text.items(), key=lambda kv: min(x.score for x in kv[1])):
            records = self.db.get_rmu_records(text)
            row = {
                "name": text,
                "directions": ",".join(sorted(set(x.direction for x in items))),
                "best_score": min(x.score for x in items),
                "db_count": len(records),
                "db_records": records,
            }
            candidate_rows.append(row)
            if len(records) == 1:
                unique_db_candidates.append(row)
            elif len(records) > 1:
                duplicate_db_candidates.append(row)

        best = candidate_rows[0]
        if best["db_count"] > 1:
            return {
                "status": "FAIL",
                "reason": "RMU_DUPLICATE_IN_DATABASE",
                "candidate_rows": candidate_rows,
                "selected": best,
            }

        if len(unique_db_candidates) == 1:
            return {
                "status": "PASS",
                "reason": "RMU_CONFIRMED",
                "candidate_rows": candidate_rows,
                "selected": unique_db_candidates[0],
            }

        if len(unique_db_candidates) > 1:
            return {
                "status": "FAIL",
                "reason": "RMU_NAME_AMBIGUOUS",
                "candidate_rows": candidate_rows,
                "selected": None,
            }

        if duplicate_db_candidates:
            return {
                "status": "FAIL",
                "reason": "RMU_DUPLICATE_IN_DATABASE",
                "candidate_rows": candidate_rows,
                "selected": duplicate_db_candidates[0],
            }

        return {
            "status": "FAIL",
            "reason": "RMU_NOT_FOUND_IN_DATABASE",
            "candidate_rows": candidate_rows,
            "selected": None,
        }

    @staticmethod
    def _make_expected_keyid(device_id: int, domain: int) -> int:
        return int(device_id) + int(domain) * KEYID_STEP

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
            "db_feeder_id": "",
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
            "current_rmu_match": "",
            "model_linked": "YES" if elem.keyid else "NO",
            "model_link_correct": "",
            "model_link_status": "",
            "association_action": "",
            "writeback_needed": "NO",
            "association_ready": "NO",
            "status": "",
            "reason": "",
        }

    @staticmethod
    def _find_by_code(rows, code: str):
        return [r for r in rows if norm(r.get("code")) == norm(code)]

    @staticmethod
    def _set_fail(row, reason):
        row["status"] = "FAIL"
        row["reason"] = reason
        row["association_ready"] = "NO"

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

    def _evaluate_current_model(self, row, elem, device_id, rule, rmu_id):
        """
        Evaluate the model already written on the G element.

        Rules:
        - no keyid: model is not linked; safe to write after all RMU checks pass;
        - correct current keyid: model already linked, no write-back is needed;
        - any existing but wrong/unresolvable keyid: report detailed error and
          do NOT overwrite automatically;
        - current referenced DB record COMBINED_ID must equal the unique RMU ID.
        """
        if not elem.keyid:
            # Database model matching and current G-link state are two different
            # concepts.  If CODE uniquely matches this G element, the model data
            # is valid even when KeyID has not been written yet.
            row["model_linked"] = "NO"
            row["model_link_correct"] = ""
            row["model_link_status"] = "未关联"
            row["association_action"] = "需要关联"
            row["writeback_needed"] = "YES"
            row["status"] = "PASS"
            row["reason"] = "DEVICE_MODEL_MATCHED; MODEL_NOT_LINKED"
            row["association_ready"] = "YES"
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
                row["current_combined_id"] = current_record.get("combined_id", "")

            current_combined_id = int_or_none(row.get("current_combined_id"))
            rmu_match = (
                current_combined_id is not None
                and rmu_id is not None
                and current_combined_id == int(rmu_id)
            )
            row["current_rmu_match"] = "YES" if rmu_match else "NO"

        except Exception as exc:
            row["model_link_correct"] = "NO"
            row["model_link_status"] = "已关联，但KeyID无法反向验证"
            row["association_action"] = "禁止自动关联"
            self._set_fail(row, f"CURRENT_KEYID_VERIFY_ERROR: {exc}")
            return

        reasons = []

        if int_or_none(row.get("current_device_id")) != int(device_id):
            reasons.append(
                f"DEVICE_ID不匹配(current={row.get('current_device_id')}, expected={device_id})"
            )

        if int_or_none(row.get("current_table_id")) != int(rule["table_id"]):
            reasons.append(
                f"TABLE_ID不匹配(current={row.get('current_table_id')}, expected={rule['table_id']})"
            )

        if int_or_none(row.get("current_domain")) != int(rule["domain"]):
            reasons.append(
                f"DOMAIN不匹配(current={row.get('current_domain')}, expected={rule['domain']})"
            )

        if row.get("current_rmu_match") != "YES":
            reasons.append(
                f"所属环网柜ID不匹配(current={row.get('current_combined_id')}, expected={rmu_id})"
            )

        if current_keyid != int(row["expected_keyid"]):
            reasons.append(
                f"KEYID不匹配(current={current_keyid}, expected={row['expected_keyid']})"
            )

        if not reasons:
            row["model_link_correct"] = "YES"
            row["model_link_status"] = "模型已关联且正确"
            row["association_action"] = "模型已关联，无需关联"
            row["association_ready"] = "YES"
            row["status"] = "PASS"
            row["reason"] = "MODEL_ALREADY_LINKED_CORRECT"
            return

        row["model_link_correct"] = "NO"
        row["model_link_status"] = "模型已关联但关联错误"
        row["association_action"] = "禁止自动关联，请检查现有模型"
        self._set_fail(row, "MODEL_LINK_WRONG: " + "; ".join(reasons))

    def _inspect_current_link_without_unique_rmu(self, row, elem, rmu_reason):
        """
        RMU itself is not unique/not valid.  We can still report whether the
        G element contains a KeyID and what that KeyID points to, but by
        business rule the link can never be accepted as correct.
        """
        row["association_ready"] = "NO"
        row["writeback_needed"] = "NO"

        if not elem.keyid:
            row["model_linked"] = "NO"
            row["model_link_correct"] = ""
            row["model_link_status"] = "未关联"
            row["association_action"] = "禁止关联，先处理环网柜唯一性"
            row["status"] = "FAIL"
            row["reason"] = f"RMU_ID_NOT_UNIQUE_OR_INVALID:{rmu_reason}"
            return

        row["model_linked"] = "YES"
        row["model_link_correct"] = "NO"
        row["model_link_status"] = "已关联，但环网柜不唯一，关联判定错误"
        row["association_action"] = "禁止自动关联"
        current_keyid = int_or_none(elem.keyid)

        if current_keyid is not None:
            try:
                curv = self.db.verify_keyid(current_keyid)
                row["current_device_id"] = curv.get("device_id", "")
                row["current_table_id"] = curv.get("tab_no", "")
                row["current_domain"] = curv.get("col_no", "")

                did = int_or_none(curv.get("device_id"))
                tab = int_or_none(curv.get("tab_no"))
                if did is not None and tab is not None:
                    try:
                        rec = self.db.get_device_by_id(tab, did)
                    except Exception:
                        rec = None
                    if rec:
                        row["current_table_name"] = rec.get("_table_name", "")
                        row["current_db_code"] = norm(rec.get("code"))
                        row["current_db_name"] = norm(rec.get("name"))
                        row["current_combined_id"] = rec.get("combined_id", "")
            except Exception as exc:
                row["current_record_error"] = str(exc)

        row["status"] = "FAIL"
        row["reason"] = (
            f"RMU_ID_NOT_UNIQUE_OR_INVALID:{rmu_reason}; "
            "环网柜本身不唯一/无效，当前模型关联不能判定为正确"
        )

    def _append_unresolved_rmu_device_rows(self, parsed, frame, rmu_result, resolved_reason):
        """Expose current model-link state even when the RMU DB identity is invalid."""
        elements = self.parser.find_target_objects_in_frame(
            parsed,
            frame,
            self.device_rules.keys(),
        )
        for elem in elements:
            rule = self.device_rules[elem.tag]
            db_set = {
                "table_name": "",
            }
            row = self._default_device_row(
                rmu_result.get("rmu_name", ""),
                "",
                elem,
                rule,
                db_set,
            )
            # No authoritative expected DB model can be selected while RMU is invalid.
            row["selected_name_source"] = "RMU_NOT_UNIQUE"
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
            "db_feeder_id": dev.get("feeder_id", ""),
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
            self._set_fail(row, f"DEVICE_NOT_FOUND (expected CODE={selected_name})")
            return
        if len(matches) > 1:
            self._set_fail(row, "DEVICE_DUPLICATE_IN_RMU")
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
            self._set_fail(row, f"DEVICE_NOT_FOUND (expected CODE={expected_code})")
            return
        if len(matches) > 1:
            self._set_fail(row, "DEVICE_DUPLICATE_IN_RMU")
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
            self._set_fail(row, f"DEVICE_NOT_FOUND (expected CODE={effective_p_name})")
            return
        if len(matches) > 1:
            self._set_fail(row, "DEVICE_DUPLICATE_IN_RMU")
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
                "rmu_reason": "",
                "rmu_db_count": 0,
                "rmu_records": [],
                "rmu_ids": [],
                "feeder": None,
                "station": None,
                "device_rows": [],
                "db_inventory": {},
                "g_inventory": {},
                "inventory_issues": [],
                "db_integrity_issues": [],
                "association_eligible": False,
                "association_block_reasons": [],
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
                report["rmu_results"].append(rmu_result)
                continue

            rmu_record = selected["db_records"][0]
            rmu_id = int_or_none(rmu_record.get("id"))
            feeder_id = rmu_record.get("feeder_id")
            rmu_result["rmu_id"] = rmu_id
            rmu_result["rmu_ids"] = [rmu_id] if rmu_id is not None else []
            rmu_result["feeder_id"] = feeder_id
            rmu_result["graph_name_db"] = norm(rmu_record.get("graph_name"))

            if feeder_id not in (None, ""):
                feeder = self.db.get_feeder_info(feeder_id)
                rmu_result["feeder"] = feeder
                if feeder and feeder.get("st_id") not in (None, ""):
                    rmu_result["station"] = self.db.get_station_info(feeder.get("st_id"))

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
                    rmu_result["association_block_reasons"].append(
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

            # RMU association can proceed only when every target has a valid DB
            # model and its existing G link is either correct or absent.
            row_blocks = [
                r for r in g_rows
                if r.get("association_ready") != "YES"
            ]
            if row_blocks:
                for r in row_blocks:
                    rmu_result["association_block_reasons"].append(
                        f"{r.get('object_type')}:{r.get('xml_id')}:{r.get('reason')}"
                    )

            # Deduplicate reasons while preserving order.
            seen = set()
            unique_reasons = []
            for reason in rmu_result["association_block_reasons"]:
                if reason not in seen:
                    seen.add(reason)
                    unique_reasons.append(reason)
            rmu_result["association_block_reasons"] = unique_reasons
            rmu_result["association_eligible"] = not unique_reasons

            if unique_reasons:
                rmu_result["rmu_status"] = "FAIL"
                rmu_result["rmu_reason"] = "RMU_MODEL_DATA_INVALID"
            else:
                # RMU DB identity itself was already PASS.  WARN/PASS at device
                # level only describes current model-link state, not data validity.
                rmu_result["rmu_status"] = "PASS"
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
            "element_warn": sum(1 for d in device_rows if d.get("status") == "WARN"),
            "element_fail": sum(1 for d in device_rows if d.get("status") == "FAIL"),
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
