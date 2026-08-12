from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dmm.domain.gfile.parser import GParser, GObject, ParsedG


FEEDLINE_TAG = "FeedLine"
DEFAULT_SECTION_TABLE_ID = 13503
DEFAULT_SECTION_DOMAIN = 1
DEFAULT_FEEDER_TABLE_ID = 13500


def norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def int_or_none(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_engineering_name(value: Any) -> str:
    """AJWD-07 / AJWD_07 / AJWD 07 -> AJWD07."""
    return re.sub(r"[^A-Z0-9]", "", norm(value).upper())


def natural_section_key(row: Dict[str, Any]):
    """
    Prefer engineering section number such as SEC001/SEC013.
    Fall back to all trailing digits, then name and ID.
    """
    name = norm(row.get("name"))
    upper = name.upper()

    m = re.search(r"(?:SEC|SECTION)[_-]?(\d+)", upper)
    if m:
        return (0, int(m.group(1)), upper, int_or_none(row.get("id")) or 0)

    nums = re.findall(r"(\d+)", upper)
    if nums:
        return (1, int(nums[-1]), upper, int_or_none(row.get("id")) or 0)

    return (2, 10**18, upper, int_or_none(row.get("id")) or 0)


class FeederValidator:
    """
    Single-feeder G-file validator.

    Current scope deliberately does NOT support multi-feeder overview drawings.

    Feeder identity:
      1) locate <Bus> objects;
      2) find the nearest engineering Text around any Bus;
      3) if no reliable Bus-near Text exists, extract a specific token from
         the G filename;
      4) normalize punctuation and resolve dms_feeder_device by NAME contains.

    FeedLine mapping:
      - already-linked FeedLine: only verify its current KeyID resolves to
        table/domain and a section belonging to the resolved feeder;
      - unlinked FeedLine: take remaining database dms_section_device records,
        sort database records by engineering section sequence, sort G FeedLine
        objects top-to-bottom then left-to-right, and pair one-to-one;
      - existing correct links consume their database records first, so
        "middle gaps" are filled from the remaining section sequence.
    """

    def __init__(
        self,
        db,
        parser: Optional[GParser] = None,
        section_table_id: int = DEFAULT_SECTION_TABLE_ID,
        section_domain: int = DEFAULT_SECTION_DOMAIN,
        feeder_table_id: int = DEFAULT_FEEDER_TABLE_ID,
        log=None,
    ):
        self.db = db
        self.parser = parser or GParser()
        self.section_table_id = int(section_table_id)
        self.section_domain = int(section_domain)
        self.feeder_table_id = int(feeder_table_id)
        self.log = log or (lambda msg: None)

    @staticmethod
    def _text_value(obj: GObject) -> str:
        return norm(obj.attrs.get("ts") or obj.attrs.get("p_NameString"))

    @staticmethod
    def _is_reasonable_feeder_label(text: str) -> bool:
        """
        Keep engineering tokens/phrases containing letters and digits.
        Exclude common RMU/device labels.
        """
        value = norm(text)
        if not value or len(value) > 80:
            return False

        upper = value.upper()
        if upper in {"SMART", "NOP", "N.O.P", "BUS", "Q1", "Y1", "Y2", "Y3"}:
            return False

        if re.fullmatch(r"\d+", upper):
            return False

        if re.fullmatch(r"[QY]\d+[A-Z]?", upper):
            return False

        return bool(re.search(r"[A-Z]", upper) and re.search(r"\d", upper))

    @staticmethod
    def _specific_filename_candidates(path: Path) -> List[str]:
        """
        Extract specific feeder-like tokens from filenames.
        Example:
            JED-CTL-AJWD-07.sln.pic.g -> AJWD-07
            JED-NTH-ABN-02.sln.pic.g  -> ABN-02
        """
        stem = path.name
        stem = re.sub(r"\.sln\.pic(?:\(\d+\))?\.g$", "", stem, flags=re.I)
        stem = re.sub(r"\.g$", "", stem, flags=re.I)

        candidates = []
        for match in re.finditer(r"([A-Za-z]{2,12})[-_\s]+(\d{1,5})", stem):
            token = f"{match.group(1)}-{match.group(2)}"
            # Avoid generic project prefixes accidentally paired with a number.
            if match.group(1).upper() not in {"JED", "NTH", "CTL", "DMS"}:
                candidates.append(token)

        # Prefer the most specific / latest token in the filename.
        uniq = []
        for value in reversed(candidates):
            if normalize_engineering_name(value) not in {
                normalize_engineering_name(x) for x in uniq
            }:
                uniq.append(value)
        return uniq

    def resolve_feeder_hint(self, parsed: ParsedG) -> Dict[str, Any]:
        buses = [obj for obj in parsed.objects if obj.tag == "Bus"]
        texts = [
            obj for obj in parsed.objects
            if obj.tag.lower() in {"text", "dtext"}
            and self._is_reasonable_feeder_label(self._text_value(obj))
        ]

        candidates = []
        for bus in buses:
            for txt in texts:
                distance = math.hypot(
                    bus.box.cx - txt.box.cx,
                    bus.box.cy - txt.box.cy,
                )
                # Above the Bus is preferred, but nearby left/right/below is
                # still accepted because engineering drawings vary.
                vertical_penalty = 0.0 if txt.box.cy <= bus.box.cy else 30.0
                score = distance + vertical_penalty
                candidates.append((score, distance, txt, bus))

        if candidates:
            candidates.sort(
                key=lambda item: (
                    item[0],
                    item[1],
                    item[2].xml_index,
                )
            )
            score, distance, txt, bus = candidates[0]
            value = self._text_value(txt)
            if distance <= 400.0:
                return {
                    "hint": value,
                    "normalized_hint": normalize_engineering_name(value),
                    "source": "BUS_NEAREST_TEXT",
                    "text_xml_id": txt.xml_id,
                    "bus_xml_id": bus.xml_id,
                    "distance": round(distance, 3),
                }

        filename_candidates = self._specific_filename_candidates(parsed.path)
        if filename_candidates:
            value = filename_candidates[0]
            return {
                "hint": value,
                "normalized_hint": normalize_engineering_name(value),
                "source": "FILE_NAME",
                "text_xml_id": "",
                "bus_xml_id": "",
                "distance": "",
            }

        return {
            "hint": "",
            "normalized_hint": "",
            "source": "NOT_FOUND",
            "text_xml_id": "",
            "bus_xml_id": "",
            "distance": "",
        }

    @staticmethod
    def _feedline_sort_key(obj: GObject):
        """
        User rule: top-to-bottom, then left-to-right.
        XML order is the final deterministic tie-breaker.
        """
        return (
            round(obj.box.y, 6),
            round(obj.box.x, 6),
            obj.xml_index,
        )

    @staticmethod
    def _make_expected_keyid(device_id: int, domain: int) -> int:
        return int(device_id) + (int(domain) << 32)

    def _verify_expected_keyid(self, device_id: int) -> Tuple[int, bool, Dict[str, Any]]:
        expected = self._make_expected_keyid(
            device_id,
            self.section_domain,
        )
        verified = self.db.verify_keyid(expected)
        ok = (
            int_or_none(verified.get("device_id")) == int(device_id)
            and int_or_none(verified.get("tab_no")) == self.section_table_id
            and int_or_none(verified.get("col_no")) == self.section_domain
        )
        return expected, ok, verified

    def _new_row(self, obj: GObject, order_index: int) -> Dict[str, Any]:
        return {
            "order_index": order_index,
            "object_type": FEEDLINE_TAG,
            "xml_id": obj.xml_id,
            "current_keyid": obj.keyid,
            "current_device_id": "",
            "current_table_id": "",
            "current_domain": "",
            "current_db_name": "",
            "current_db_code": "",
            "current_feeder_id": "",
            "current_feeder_name": "",
            "assigned_device_id": "",
            "assigned_section_name": "",
            "assigned_bv_id": "",
            "current_bv_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "",
            "model_linked": "YES" if obj.keyid else "NO",
            "model_link_correct": "",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "status": "FAIL",
            "severity": "ERROR",
            "reason": "",
        }

    def validate_file(self, g_path: str | Path) -> Dict[str, Any]:
        parsed = self.parser.parse(g_path)
        feedlines = sorted(
            [obj for obj in parsed.objects if obj.tag == FEEDLINE_TAG],
            key=self._feedline_sort_key,
        )

        feeder_hint = self.resolve_feeder_hint(parsed)
        report = {
            "report_type": "FEEDER",
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "feeder_hint": feeder_hint.get("hint", ""),
            "feeder_normalized_hint": feeder_hint.get("normalized_hint", ""),
            "feeder_hint_source": feeder_hint.get("source", ""),
            "feeder_hint_text_xml_id": feeder_hint.get("text_xml_id", ""),
            "feeder_hint_bus_xml_id": feeder_hint.get("bus_xml_id", ""),
            "feeder_hint_distance": feeder_hint.get("distance", ""),
            "feeder_records": [],
            "feeder_id": "",
            "feeder_name": "",
            "feedline_rows": [],
            "association_eligible": False,
            "status": "FAIL",
            "severity": "ERROR",
            "reason": "",
            "summary": {},
        }

        if not feedlines:
            report["reason"] = "FEEDLINE_NOT_FOUND_IN_G_FILE"
            report["summary"] = self._summary(report)
            return report

        hint_norm = feeder_hint.get("normalized_hint", "")
        if not hint_norm:
            report["reason"] = (
                "FEEDER_NAME_NOT_FOUND: 无法从 Bus 附近文字或文件名识别馈线名称"
            )
            for idx, obj in enumerate(feedlines, start=1):
                row = self._new_row(obj, idx)
                row["reason"] = "FEEDER_NAME_NOT_FOUND"
                report["feedline_rows"].append(row)
            report["summary"] = self._summary(report)
            return report

        feeder_records = self.db.find_feeders_by_name_hint(
            hint_norm,
            table_id=self.feeder_table_id,
        )
        report["feeder_records"] = feeder_records

        if len(feeder_records) != 1:
            report["reason"] = (
                "FEEDER_NOT_UNIQUE_IN_DATABASE: "
                f"图上馈线={feeder_hint.get('hint') or '-'}；"
                f"数据库匹配数={len(feeder_records)}"
            )
            for idx, obj in enumerate(feedlines, start=1):
                row = self._new_row(obj, idx)
                row["reason"] = report["reason"]
                report["feedline_rows"].append(row)
            report["summary"] = self._summary(report)
            return report

        feeder = feeder_records[0]
        feeder_id = int_or_none(feeder.get("id"))
        feeder_name = norm(
            feeder.get("display_name")
            or feeder.get("name")
        )
        report["feeder_id"] = feeder_id or ""
        report["feeder_name"] = feeder_name

        if feeder_id is None:
            report["reason"] = "FEEDER_ID_INVALID"
            report["summary"] = self._summary(report)
            return report

        _, section_rows = self.db.get_sections_by_feeder_id(
            feeder_id,
            table_id=self.section_table_id,
        )
        section_rows = sorted(section_rows, key=natural_section_key)
        sections_by_id = {
            int(row["id"]): row
            for row in section_rows
            if int_or_none(row.get("id")) is not None
        }

        used_db_ids = set()
        # Any existing KeyID that already resolves to a database section in
        # the current feeder reserves that section, even when the link has a
        # domain error.  We never allocate the same DB section to another
        # unlinked FeedLine while an existing G object still references it.
        reserved_db_ids = set()
        rows = []

        # ---------------------------------------------------------------
        # First pass: validate existing KeyIDs.
        # ---------------------------------------------------------------
        for idx, obj in enumerate(feedlines, start=1):
            row = self._new_row(obj, idx)

            if not obj.keyid:
                row["status"] = "WARN"
                row["severity"] = "UNLINKED"
                row["reason"] = "MODEL_NOT_LINKED"
                rows.append(row)
                continue

            current_keyid = int_or_none(obj.keyid)
            if current_keyid is None:
                row["reason"] = "CURRENT_KEYID_INVALID"
                rows.append(row)
                continue

            try:
                verified = self.db.verify_keyid(current_keyid)
            except Exception as exc:
                row["reason"] = f"CURRENT_KEYID_VERIFY_ERROR: {exc}"
                rows.append(row)
                continue

            current_device_id = int_or_none(verified.get("device_id"))
            current_table_id = int_or_none(verified.get("tab_no"))
            current_domain = int_or_none(verified.get("col_no"))

            row["current_device_id"] = current_device_id or ""
            row["current_table_id"] = current_table_id or ""
            row["current_domain"] = (
                current_domain if current_domain is not None else ""
            )

            # If the KeyID at least points into the configured section table,
            # inspect the actual DB row before checking domain. This lets us
            # reserve an already-referenced section and prevents accidental
            # duplicate assignment to another G FeedLine.
            current_record = None
            if (
                current_device_id is not None
                and current_table_id == self.section_table_id
            ):
                current_record = self.db.get_device_by_id(
                    self.section_table_id,
                    current_device_id,
                )
                if current_record:
                    current_owner = int_or_none(
                        current_record.get("feeder_id")
                    )
                    if current_owner == feeder_id:
                        reserved_db_ids.add(current_device_id)

            if (
                current_device_id is None
                or current_table_id != self.section_table_id
                or current_domain != self.section_domain
            ):
                row["reason"] = (
                    "MODEL_LINK_WRONG: "
                    f"current_table={current_table_id}, "
                    f"expected_table={self.section_table_id}; "
                    f"current_domain={current_domain}, "
                    f"expected_domain={self.section_domain}"
                )
                rows.append(row)
                continue

            if current_record is None:
                current_record = self.db.get_device_by_id(
                    self.section_table_id,
                    current_device_id,
                )
            if not current_record:
                row["reason"] = "CURRENT_SECTION_NOT_FOUND_IN_DATABASE"
                rows.append(row)
                continue

            current_feeder_id = int_or_none(current_record.get("feeder_id"))
            row["current_db_name"] = norm(current_record.get("name"))
            row["current_db_code"] = norm(current_record.get("code"))
            row["current_bv_id"] = current_record.get("bv_id", "")
            row["current_feeder_id"] = current_feeder_id or ""
            if current_feeder_id == feeder_id:
                row["current_feeder_name"] = feeder_name
            elif current_feeder_id is not None:
                try:
                    owner = self.db.get_feeder_info(current_feeder_id)
                except Exception:
                    owner = None
                row["current_feeder_name"] = norm(
                    (owner or {}).get("name")
                )
            row["assigned_device_id"] = current_device_id
            row["assigned_section_name"] = norm(current_record.get("name"))
            row["assigned_bv_id"] = current_record.get("bv_id", "")
            row["expected_keyid"] = current_keyid
            row["expected_keyid_verified"] = "YES"

            if current_feeder_id != feeder_id:
                row["reason"] = (
                    "CURRENT_MODEL_FEEDER_MISMATCH: "
                    f"当前FeedLine实际feeder_id={current_feeder_id or '-'}；"
                    f"期望feeder_id={feeder_id}"
                )
                rows.append(row)
                continue

            if current_device_id in used_db_ids:
                row["reason"] = (
                    "DUPLICATE_SECTION_LINK: "
                    f"数据库馈线段ID={current_device_id} 被多个FeedLine重复使用"
                )
                rows.append(row)
                continue

            used_db_ids.add(current_device_id)
            reserved_db_ids.add(current_device_id)
            row["model_link_correct"] = "YES"
            row["association_ready"] = "YES"
            row["writeback_needed"] = "NO"
            row["status"] = "PASS"
            row["severity"] = "PASS"
            row["reason"] = "MODEL_ALREADY_LINKED_CORRECT"
            rows.append(row)

        # If one existing DB section is used by multiple G FeedLines, mark ALL
        # rows using it as errors, not only the later duplicate.
        linked_by_device = defaultdict(list)
        for row in rows:
            if (
                row.get("model_linked") == "YES"
                and int_or_none(row.get("assigned_device_id")) is not None
            ):
                linked_by_device[int(row["assigned_device_id"])].append(row)

        for device_id, mapped in linked_by_device.items():
            if len(mapped) <= 1:
                continue
            for row in mapped:
                row["model_link_correct"] = "NO"
                row["association_ready"] = "NO"
                row["writeback_needed"] = "NO"
                row["status"] = "FAIL"
                row["severity"] = "ERROR"
                row["reason"] = (
                    "DUPLICATE_SECTION_LINK: "
                    f"数据库馈线段ID={device_id} 被多个FeedLine重复使用"
                )
            # Keep the duplicated section reserved. Existing G objects
            # still reference it and are not auto-overwritten.
            used_db_ids.discard(device_id)
            reserved_db_ids.add(device_id)

        # ---------------------------------------------------------------
        # Second pass: assign only UNLINKED FeedLines from unused DB rows.
        # Existing wrong links are not silently overwritten.
        # ---------------------------------------------------------------
        available = [
            row for row in section_rows
            if int_or_none(row.get("id")) not in reserved_db_ids
        ]
        available.sort(key=natural_section_key)

        unlinked = [
            row for row in rows
            if row.get("model_linked") == "NO"
        ]

        for row, section in zip(unlinked, available):
            device_id = int_or_none(section.get("id"))
            if device_id is None:
                row["status"] = "FAIL"
                row["severity"] = "ERROR"
                row["reason"] = "SECTION_DEVICE_ID_INVALID"
                continue

            expected_keyid, verified_ok, _ = self._verify_expected_keyid(
                device_id
            )

            row["assigned_device_id"] = device_id
            row["assigned_section_name"] = norm(section.get("name"))
            row["assigned_bv_id"] = section.get("bv_id", "")
            row["expected_keyid"] = expected_keyid
            row["expected_keyid_verified"] = "YES" if verified_ok else "NO"

            if not norm(row.get("assigned_bv_id")):
                row["status"] = "FAIL"
                row["severity"] = "ERROR"
                row["association_ready"] = "NO"
                row["writeback_needed"] = "NO"
                row["reason"] = (
                    "BV_ID_EMPTY: 数据库馈线段 BV_ID 为空，"
                    "无法写入 FeedLine voltype"
                )
                continue

            if not verified_ok:
                row["status"] = "FAIL"
                row["severity"] = "ERROR"
                row["reason"] = "EXPECTED_KEYID_VERIFY_FAILED"
                continue

            row["model_link_correct"] = ""
            row["association_ready"] = "YES"
            row["writeback_needed"] = "YES"
            row["status"] = "WARN"
            row["severity"] = "UNLINKED"
            row["reason"] = "MODEL_NOT_LINKED_READY_FOR_ASSOCIATION"

        if len(unlinked) > len(available):
            for row in unlinked[len(available):]:
                row["status"] = "FAIL"
                row["severity"] = "ERROR"
                row["association_ready"] = "NO"
                row["writeback_needed"] = "NO"
                row["reason"] = (
                    "SECTION_NOT_AVAILABLE: "
                    "数据库中可用馈线段数量不足，当前FeedLine禁止自动关联"
                )

        report["feedline_rows"] = rows
        report["association_eligible"] = True

        fail_count = sum(1 for row in rows if row.get("status") == "FAIL")
        ready_count = sum(
            1 for row in rows
            if row.get("association_ready") == "YES"
            and row.get("writeback_needed") == "YES"
        )

        if fail_count:
            report["status"] = "WARN"
            report["severity"] = "PARTIAL_ERROR"
            report["reason"] = (
                "FEEDER_PARTIAL_DEVICE_ERRORS: "
                f"FeedLine错误={fail_count}；仍可自动关联={ready_count}"
            )
        else:
            report["status"] = "PASS"
            report["severity"] = "PASS"
            report["reason"] = "FEEDER_MODEL_DATA_VALID"

        report["summary"] = self._summary(report)
        return report

    @staticmethod
    def _summary(report: Dict[str, Any]) -> Dict[str, int]:
        rows = report.get("feedline_rows", [])
        return {
            "feeder_files": 1,
            "feeders_resolved": 1 if report.get("feeder_id") else 0,
            "feedlines": len(rows),
            "feedline_pass": sum(1 for row in rows if row.get("status") == "PASS"),
            "feedline_warn": sum(1 for row in rows if row.get("status") == "WARN"),
            "feedline_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
            "association_ready": sum(
                1 for row in rows
                if row.get("association_ready") == "YES"
                and row.get("writeback_needed") == "YES"
            ),
        }
