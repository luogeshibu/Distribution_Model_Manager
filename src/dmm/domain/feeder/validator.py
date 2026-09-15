from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dmm.domain.gfile.parser import GParser, GObject, ParsedG, Box
from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier
from dmm.config.constants import (
    RMU_LABEL_SEARCH_MAX_DISTANCE,
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
)
from dmm.config.defaults import DEFAULT_DEVICE_RULES, DEFAULT_NAME_POSITIONS, DEFAULT_RMU_NAME_EXCLUSIONS
from dmm.domain.rmu.validator import RmuValidator


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


def section_allocation_key(row: Dict[str, Any]):
    """Deterministic order for assigning currently-unused DB sections.

    Business rule (v4.1.14):
      * if NAME carries an explicit SEC/SECTION number, use that number;
      * otherwise use the database device ID from small to large.

    This order is used only to allocate *unresolved* FeedLines. It never
    reorders or invalidates an already-correct existing association.
    """
    name = norm(row.get("name"))
    upper = name.upper()
    device_id = int_or_none(row.get("id"))
    safe_id = device_id if device_id is not None else 10**30

    m = re.search(r"(?:SEC|SECTION)[_-]?(\d+)", upper)
    if m:
        return (0, int(m.group(1)), safe_id, upper)

    return (1, safe_id, upper)


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
        rmu_device_rules: Optional[Dict[str, Dict[str, Any]]] = None,
        rmu_name_positions: Optional[Dict[str, bool]] = None,
        rmu_name_exclusions: Optional[Iterable[str]] = None,
        allow_feeder_override: bool = False,
        log=None,
    ):
        self.db = db
        self.parser = parser or GParser()
        self.section_table_id = int(section_table_id)
        self.section_domain = int(section_domain)
        self.feeder_table_id = int(feeder_table_id)
        self.rmu_device_rules = dict(rmu_device_rules or DEFAULT_DEVICE_RULES)
        self.rmu_name_positions = dict(rmu_name_positions or DEFAULT_NAME_POSITIONS)
        self.rmu_name_exclusions = list(rmu_name_exclusions or DEFAULT_RMU_NAME_EXCLUSIONS)
        self.allow_feeder_override = bool(allow_feeder_override)
        self.log = log or (lambda msg: None)

    @staticmethod
    def _text_value(obj: GObject) -> str:
        return norm(obj.attrs.get("ts"))

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
    def _extract_feeder_token(text: str) -> str:
        """
        Extract a clean feeder token from engineering text.

        Examples:
            "ABH-03"          -> "ABH-03"
            "BAY NO\\nABH-17" -> "ABH-17"
            "AJWD_07"         -> "AJWD-07"

        This is intentionally generic: letters + optional letters/digits +
        separator + final numeric feeder suffix.
        """
        value = norm(text).upper().replace("\n", " ")
        match = re.search(
            r"\b([A-Z]{2,}[A-Z0-9]*)(?:[-_\s]+)(\d{1,3})\b",
            value,
        )
        if not match:
            return ""
        return f"{match.group(1)}-{match.group(2)}"

    @classmethod
    def _feeder_anchor_quality(cls, text: str) -> int:
        """
        Higher score = more likely to be an actual feeder title.

        Clean standalone titles such as ABH-03 are preferred over descriptive
        text such as "BAY NO ABH-03".
        """
        value = norm(text).upper().replace("\n", " ").strip()
        token = cls._extract_feeder_token(value)
        if not token:
            return 0

        normalized_value = re.sub(r"\s+", " ", value)
        if normalized_value == token:
            return 100
        if normalized_value.replace("_", "-") == token:
            return 100
        if "BAY NO" in normalized_value:
            return 20
        return 50

    @classmethod
    def _canonicalize_anchor_candidates(
        cls,
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Clean composite drawing feeder anchors BEFORE database lookup.

        Rules:
        - Extract a canonical feeder token from G Text itself.
        - Prefer clean feeder-title text over nearby "BAY NO ..." annotations.
        - Keep genuinely separate duplicate clean titles (e.g. two ABH-26
          source blocks) so the duplicate can be reported instead of hidden.
        """
        cleaned = []
        for candidate in candidates:
            token = cls._extract_feeder_token(candidate.get("hint", ""))
            quality = cls._feeder_anchor_quality(candidate.get("hint", ""))
            if not token or quality <= 0:
                continue

            item = dict(candidate)
            item["raw_hint"] = candidate.get("hint", "")
            item["hint"] = token
            item["normalized_hint"] = normalize_engineering_name(token)
            item["anchor_quality"] = quality
            cleaned.append(item)

        cleaned.sort(
            key=lambda item: (
                -int(item.get("anchor_quality", 0)),
                float(item.get("x", 0)),
                float(item.get("y", 0)),
            )
        )

        # A low-quality descriptive label is dropped when a better anchor for
        # the same feeder exists nearby. Clean duplicated feeder titles remain.
        accepted = []
        for candidate in cleaned:
            token = candidate["normalized_hint"]
            quality = int(candidate.get("anchor_quality", 0))
            duplicate_of_better = False
            for existing in accepted:
                if existing["normalized_hint"] != token:
                    continue
                dx = abs(
                    float(existing.get("x", 0))
                    - float(candidate.get("x", 0))
                )
                if (
                    int(existing.get("anchor_quality", 0)) > quality
                    and dx <= 3000.0
                ):
                    duplicate_of_better = True
                    break
            if not duplicate_of_better:
                accepted.append(candidate)

        accepted.sort(
            key=lambda item: (
                float(item.get("x", 0)),
                float(item.get("y", 0)),
            )
        )
        return accepted


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
            if obj.tag.lower() == "text"
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
            "ls": str(obj.attrs.get("ls", "") or ""),
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
            "relink_same_section": "NO",
            "relink_missing_section": "NO",
            "status": "FAIL",
            "severity": "ERROR",
            "reason": "",
        }


    def _infer_feeder_from_existing_links(
        self,
        feedlines: List[GObject],
        normalized_hint: str,
    ) -> Dict[str, Any]:
        """
        Infer region feeder ownership from already-linked FeedLines.

        This is a strong fallback for composite drawings:
        KeyID -> dms_section_device -> feeder_id -> feeder info.

        The fallback is only accepted when all resolvable existing links in the
        region point to ONE feeder and that feeder name is compatible with the
        G title token when a title token is available.
        """
        owners = defaultdict(list)

        for obj in feedlines:
            if not obj.keyid:
                continue

            current_keyid = int_or_none(obj.keyid)
            if current_keyid is None:
                continue

            try:
                verified = self.db.verify_keyid(current_keyid)
            except Exception:
                continue

            device_id = int_or_none(verified.get("device_id"))
            table_id = int_or_none(verified.get("tab_no"))
            if (
                device_id is None
                or table_id != self.section_table_id
            ):
                continue

            try:
                section = self.db.get_device_by_id(
                    self.section_table_id,
                    device_id,
                )
            except Exception:
                section = None
            if not section:
                continue

            feeder_id = int_or_none(section.get("feeder_id"))
            if feeder_id is None:
                continue
            owners[feeder_id].append(
                {
                    "xml_id": obj.xml_id,
                    "device_id": device_id,
                    "section": section,
                }
            )

        if not owners:
            return {
                "status": "NOT_FOUND",
                "records": [],
                "owner_ids": [],
            }

        if len(owners) > 1:
            return {
                "status": "MULTIPLE",
                "records": [],
                "owner_ids": sorted(owners),
                "owner_counts": {
                    str(k): len(v)
                    for k, v in owners.items()
                },
            }

        feeder_id = next(iter(owners))
        try:
            feeder = self.db.get_feeder_info(feeder_id)
        except Exception:
            feeder = None

        if not feeder:
            return {
                "status": "OWNER_INFO_NOT_FOUND",
                "records": [],
                "owner_ids": [feeder_id],
            }

        display_name = norm(
            feeder.get("display_name")
            or feeder.get("name")
        )
        feeder_norm = normalize_engineering_name(display_name)

        if (
            normalized_hint
            and feeder_norm
            and normalized_hint not in feeder_norm
        ):
            return {
                "status": "TITLE_OWNER_MISMATCH",
                "records": [],
                "owner_ids": [feeder_id],
                "owner_name": display_name,
                "title_hint": normalized_hint,
            }

        record = dict(feeder)
        record["id"] = feeder_id
        record["display_name"] = display_name
        record["_resolved_by"] = "EXISTING_FEEDLINE_KEYID"

        return {
            "status": "MATCHED",
            "records": [record],
            "owner_ids": [feeder_id],
            "owner_name": display_name,
            "linked_count": len(owners[feeder_id]),
        }

    def _resolve_region_feeder_records(
        self,
        feeder_hint: Dict[str, Any],
        feedlines: List[GObject],
    ) -> Dict[str, Any]:
        """
        Resolve one region feeder.

        Priority:
        1. G title -> feeder master database unique match.
        2. Existing FeedLine KeyIDs in this spatial region -> feeder ownership.

        Database resolution failure does not erase the G title; the report
        preserves the title and explains which confirmation step failed.
        """
        hint_norm = feeder_hint.get("normalized_hint", "")
        direct_records = []
        direct_error = ""

        if hint_norm:
            try:
                direct_records = self.db.find_feeders_by_name_hint(
                    hint_norm,
                    table_id=self.feeder_table_id,
                )
            except Exception as exc:
                direct_error = str(exc)
                direct_records = []

        if len(direct_records) == 1:
            return {
                "records": direct_records,
                "source": "G_TITLE_DB_UNIQUE",
                "direct_match_count": 1,
                "direct_error": direct_error,
            }

        linked = self._infer_feeder_from_existing_links(
            feedlines,
            hint_norm,
        )

        if linked.get("status") == "MATCHED":
            return {
                "records": linked["records"],
                "source": "EXISTING_FEEDLINE_KEYID",
                "direct_match_count": len(direct_records),
                "direct_error": direct_error,
                "linked_inference": linked,
            }

        return {
            "records": direct_records,
            "source": "UNRESOLVED",
            "direct_match_count": len(direct_records),
            "direct_error": direct_error,
            "linked_inference": linked,
        }

    def _validate_parsed_region(
        self,
        parsed: ParsedG,
        feedlines: Optional[List[GObject]] = None,
        feeder_hint: Optional[Dict[str, Any]] = None,
        region_meta: Optional[Dict[str, Any]] = None,
        forced_feeder_record: Optional[Dict[str, Any]] = None,
        forced_source: str = "",
    ) -> Dict[str, Any]:
        feedlines = sorted(
            list(feedlines) if feedlines is not None else [
                obj for obj in parsed.objects if obj.tag == FEEDLINE_TAG
            ],
            key=self._feedline_sort_key,
        )

        feeder_hint = feeder_hint or self.resolve_feeder_hint(parsed)
        region_meta = dict(region_meta or {})
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
            "drawing_type": region_meta.get("drawing_type", "SINGLE_FEEDER"),
            "region_index": region_meta.get("region_index", 1),
            "region_left": region_meta.get("region_left", ""),
            "region_right": region_meta.get("region_right", ""),
            "region_anchor_x": region_meta.get("region_anchor_x", ""),
            "region_assignment_method": region_meta.get(
                "region_assignment_method", "WHOLE_FILE"
            ),
            "duplicate_feeder_anchor": bool(
                region_meta.get("duplicate_feeder_anchor", False)
            ),
        }

        # Do not reject the whole feeder merely because this drawing has no
        # FeedLine objects.  A feeder master record (13500) can still be
        # uniquely confirmed from facID / filename / manual input and the G
        # root facID can still be associated to that feeder.  FeedLine absence
        # only means there are no 13503 section objects to validate in this
        # drawing.  The no-FeedLine decision is therefore made *after* feeder
        # resolution below.

        hint_norm = feeder_hint.get("normalized_hint", "")
        if not hint_norm and not forced_feeder_record:
            report["reason"] = (
                "FEEDER_NAME_NOT_FOUND: 无法从 Bus 附近文字或文件名识别馈线名称"
            )
            for idx, obj in enumerate(feedlines, start=1):
                row = self._new_row(obj, idx)
                row["reason"] = "FEEDER_NAME_NOT_FOUND"
                report["feedline_rows"].append(row)
            report["summary"] = self._summary(report)
            return report

        if forced_feeder_record:
            feeder_resolution = {
                "records": [dict(forced_feeder_record)],
                "source": forced_source or "FORCED_FEEDER",
                "direct_match_count": 1,
                "direct_error": "",
                "linked_inference": {},
            }
        else:
            feeder_resolution = self._resolve_region_feeder_records(
                feeder_hint,
                feedlines,
            )
        feeder_records = feeder_resolution.get("records", [])
        report["feeder_records"] = feeder_records
        if forced_feeder_record:
            report["region_assignment_method"] = (
                forced_source or "FORCED_FEEDER"
            )
            report["feeder_hint_source"] = forced_source or "FORCED_FEEDER"
        report["feeder_resolution_source"] = feeder_resolution.get(
            "source",
            "",
        )
        report["feeder_direct_db_match_count"] = feeder_resolution.get(
            "direct_match_count",
            0,
        )
        report["feeder_direct_db_error"] = feeder_resolution.get(
            "direct_error",
            "",
        )
        report["linked_feeder_inference"] = feeder_resolution.get(
            "linked_inference",
            {},
        )

        if report.get("duplicate_feeder_anchor"):
            report["reason"] = (
                "DUPLICATE_FEEDER_ANCHOR_IN_COMPOSITE: "
                f"组合图中馈线标识 {feeder_hint.get('hint') or '-'} "
                "出现多个独立空间锚点，禁止自动分配该区域馈线段"
            )
            for idx, obj in enumerate(feedlines, start=1):
                row = self._new_row(obj, idx)
                row["reason"] = report["reason"]
                row["drawing_type"] = report["drawing_type"]
                row["region_index"] = report["region_index"]
                row["region_assignment_method"] = report[
                    "region_assignment_method"
                ]
                report["feedline_rows"].append(row)
            report["summary"] = self._summary(report)
            return report

        if len(feeder_records) != 1:
            linked_info = report.get("linked_feeder_inference", {}) or {}
            linked_status = linked_info.get("status", "")
            linked_detail = ""
            if linked_status == "MULTIPLE":
                linked_detail = (
                    f"；该空间区域已有KeyID反查到多个feeder_id="
                    f"{linked_info.get('owner_ids', [])}"
                )
            elif linked_status == "TITLE_OWNER_MISMATCH":
                linked_detail = (
                    f"；已有KeyID反查馈线={linked_info.get('owner_name', '-')}"
                    "，与图上馈线标题不一致"
                )
            elif linked_status and linked_status != "NOT_FOUND":
                linked_detail = f"；已有KeyID反查状态={linked_status}"

            report["reason"] = (
                "FEEDER_NOT_UNIQUE_IN_DATABASE: "
                f"图上馈线={feeder_hint.get('hint') or '-'}；"
                f"数据库直接匹配数="
                f"{report.get('feeder_direct_db_match_count', 0)}"
                f"{linked_detail}"
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

        # v4.1.8: feeder-master/root association is a separate concern from
        # FeedLine section validation.  Once a SINGLE_FEEDER drawing has been
        # assigned to one unique feeder through MANUAL/FILENAME and root facID
        # is empty, expose root facID writeback regardless of Breaker/Busbar or
        # FeedLine presence/link state. Composite drawings never enter this
        # single-region path.
        root_facid = str(parsed.root.attrib.get("facID", "") or "").strip()
        source_upper = str(
            report.get("feeder_resolution_source")
            or forced_source
            or source
            or ""
        ).upper()
        root_target_differs = bool(root_facid) and root_facid != str(feeder_id)
        root_writeback = (
            report.get("drawing_type", "SINGLE_FEEDER") == "SINGLE_FEEDER"
            and source_upper in {"FILENAME", "MANUAL"}
            and (
                not root_facid
                or (root_target_differs and self.allow_feeder_override)
            )
        )
        report["feeder_root_writeback_needed"] = (
            "YES" if root_writeback else "NO"
        )
        report["feeder_root_current_facid"] = root_facid
        report["feeder_root_expected_facid"] = str(feeder_id)
        report["feeder_override_enabled"] = (
            "YES" if self.allow_feeder_override else "NO"
        )
        report["feeder_root_conflict"] = (
            "YES" if root_target_differs else "NO"
        )

        if (
            root_target_differs
            and source_upper in {"FILENAME", "MANUAL"}
            and not self.allow_feeder_override
        ):
            report["association_eligible"] = False
            report["status"] = "FAIL"
            report["severity"] = "FEEDER_MISMATCH"
            report["reason"] = (
                "FEEDER_ROOT_FACID_CONFLICT: "
                f"当前 G.facID={root_facid}；本次{source_upper}解析目标 FEEDER_ID={feeder_id}；"
                "未启用“允许覆盖现有 facID 和馈线段关联”，禁止生成跨馈线回写候选。"
            )
            for idx, obj in enumerate(feedlines, start=1):
                row = self._new_row(obj, idx)
                row.update({
                    "status": "FAIL",
                    "severity": "FEEDER_MISMATCH",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": report["reason"],
                })
                report["feedline_rows"].append(row)
            report["summary"] = self._summary(report)
            return report

        # v4.1.7: feeder-only drawings are valid.  When a feeder has already
        # been uniquely resolved but this G file contains zero FeedLine
        # objects, keep the feeder fact in the report instead of returning the
        # historical FEEDLINE_NOT_FOUND_IN_G_FILE failure.  For name-based
        # resolution an empty root facID becomes an explicit feeder-root
        # association candidate; no dms_section_device row is created.
        if not feedlines:
            report["association_eligible"] = True
            if root_writeback:
                report["status"] = "WARN"
                report["severity"] = "UNLINKED"
                report["reason"] = (
                    "FEEDER_ROOT_FACID_WRITEBACK_READY: "
                    f"FEEDER_ID={feeder_id}; 数据库馈线={feeder_name}; "
                    "G文件无FeedLine，仅需将根节点facID关联到已唯一确认的馈线；"
                    "不会创建13503馈线段。"
                )
            else:
                report["status"] = "PASS"
                report["severity"] = "PASS"
                report["reason"] = (
                    "FEEDER_CONFIRMED_NO_FEEDLINE: "
                    f"FEEDER_ID={feeder_id}; 数据库馈线={feeder_name}; "
                    "G文件无FeedLine，无馈线段需要校验或创建。"
                )
            report["summary"] = self._summary(report)
            return report

        _, section_rows = self.db.get_sections_by_feeder_id(
            feeder_id,
            table_id=self.section_table_id,
        )
        section_rows = sorted(section_rows, key=section_allocation_key)
        sections_by_id = {
            int(row["id"]): row
            for row in section_rows
            if int_or_none(row.get("id")) is not None
        }

        # v4.1.14 validation contract:
        #   1) existing FeedLine links are checked only for feeder ownership
        #      and KeyID domain; no SEC/name/geometry/order validation is used;
        #   2) unresolved FeedLines are allowed to consume the current feeder's
        #      unused 13503 rows in a deterministic database sequence;
        #   3) if NAME contains SECnnn, that engineering number defines the
        #      sequence; otherwise database device ID is used from small to large;
        #   4) only the genuinely missing remainder is marked for creation.
        # Existing correct links are always preserved and never re-ordered.
        all_feedlines_unlinked = all(not obj.keyid for obj in feedlines)
        report["section_assignment_mode"] = (
            "NEW_DRAWING_ORDER" if all_feedlines_unlinked
            else "PRESERVE_EXISTING_DB_SEQUENCE"
        )

        # Any existing KeyID that resolves to a section in the current feeder
        # reserves that section, even when the Domain is wrong.  Multiple G
        # FeedLines pointing to the same same-feeder section are intentionally
        # not rejected here: per the current business rule, existing-link
        # validation is limited to feeder ownership + Domain only.
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

            # Device/table must still be valid. A wrong TABLE is not safe to
            # auto-repair because the same numeric device_id can belong to a
            # different model table. Domain-only errors are handled below.
            if (
                current_device_id is None
                or current_table_id != self.section_table_id
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
                # v4.1.11: a KeyID that still decodes to the configured
                # 13503 table but whose device_id no longer exists is a stale
                # section link, not an unrecoverable table/feeder error. The
                # feeder itself has already been uniquely confirmed for this
                # SINGLE_FEEDER region, so this FeedLine may be reassigned
                # only within the same feeder's currently available section
                # pool. If that pool is exhausted, the normal missing-section
                # creation planner will create only the remaining shortage.
                row.update({
                    "model_link_correct": "NO",
                    "relink_missing_section": "YES",
                    "status": "WARN",
                    "severity": "RELINK",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": (
                        "STALE_SECTION_LINK: 当前KeyID对应的13503设备已不存在；"
                        "将在当前已确认馈线内优先使用剩余馈线段，数量不足时仅创建缺少数量。"
                    ),
                })
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

            # Cross-feeder links are normally a hard error.  v4.1.38 keeps an
            # explicit operator override: only when enabled may this existing
            # FeedLine be returned to the target feeder's allocation pool.
            if current_feeder_id != feeder_id:
                if self.allow_feeder_override:
                    row.update({
                        "model_link_correct": "NO",
                        "override_cross_feeder": "YES",
                        "status": "WARN",
                        "severity": "RELINK",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "reason": (
                            "CURRENT_MODEL_FEEDER_OVERRIDE_REQUESTED: "
                            f"当前FeedLine实际feeder_id={current_feeder_id or '-'}；"
                            f"目标feeder_id={feeder_id}；已启用人工覆盖，"
                            "将在目标馈线现有/新建馈线段中重新分配。"
                        ),
                    })
                    rows.append(row)
                    continue
                row["reason"] = (
                    "CURRENT_MODEL_FEEDER_MISMATCH: "
                    f"当前FeedLine实际feeder_id={current_feeder_id or '-'}；"
                    f"期望feeder_id={feeder_id}；未启用人工覆盖。"
                )
                rows.append(row)
                continue

            # Same feeder + valid 13503 record is sufficient for ownership.
            # Do not compare SEC number, DB NAME, geometry order, or duplicate
            # use here.  Domain is the only remaining existing-link check.
            reserved_db_ids.add(current_device_id)

            # v4.1.10: same 13503 record + same feeder + wrong domain is a
            # repairable KeyID encoding error. Preserve the exact section
            # device_id and rewrite only the KeyID using the configured domain.
            if current_domain != self.section_domain:
                expected_keyid, verified_ok, _ = self._verify_expected_keyid(
                    current_device_id
                )
                row["expected_keyid"] = expected_keyid
                row["expected_keyid_verified"] = "YES" if verified_ok else "NO"
                row["relink_same_section"] = "YES"
                if not norm(row.get("assigned_bv_id")):
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "model_link_correct": "NO",
                        "reason": "BV_ID_EMPTY: 当前馈线段BV_ID为空，禁止重写模型",
                    })
                elif not verified_ok:
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "model_link_correct": "NO",
                        "reason": "EXPECTED_KEYID_VERIFY_FAILED",
                    })
                else:
                    row.update({
                        "status": "WARN",
                        "severity": "RELINK",
                        "association_ready": "YES",
                        "writeback_needed": "YES",
                        "model_link_correct": "NO",
                        "reason": (
                            "DOMAIN_RELINK_READY: 当前馈线段和feeder_id均正确，"
                            f"仅域号错误 current_domain={current_domain}, "
                            f"expected_domain={self.section_domain}；"
                            "保持device_id不变并重写KeyID。"
                        ),
                    })
                rows.append(row)
                continue

            row["expected_keyid"] = current_keyid
            row["expected_keyid_verified"] = "YES"
            row["model_link_correct"] = "YES"
            row["association_ready"] = "YES"
            row["writeback_needed"] = "NO"
            row["status"] = "PASS"
            row["severity"] = "PASS"
            row["reason"] = "MODEL_ALREADY_LINKED_CORRECT"
            rows.append(row)

        # ---------------------------------------------------------------
        # Second pass: unresolved FeedLines.
        #
        # v4.1.14: once valid existing links are locked, unresolved/stale
        # FeedLines may continue to use the current feeder's unoccupied DB
        # sections in deterministic sequence.  This is allocation, not
        # validation: it never changes the already-correct links above.
        #
        # Allocation sequence:
        #   explicit SECnnn in NAME -> SEC number ascending;
        #   otherwise               -> database device ID ascending.
        # If DB rows are insufficient, only the remaining shortage is marked
        # SECTION_NOT_AVAILABLE so the creation planner creates exactly that
        # many new sections.
        # ---------------------------------------------------------------
        available = [
            row for row in section_rows
            if int_or_none(row.get("id")) not in reserved_db_ids
        ]
        available.sort(key=section_allocation_key)

        pending = [
            row for row in rows
            if (
                row.get("model_linked") == "NO"
                or row.get("relink_missing_section") == "YES"
                or row.get("override_cross_feeder") == "YES"
            )
        ]

        def assign_existing_section(row, section, *, reason_mode):
            device_id = int_or_none(section.get("id"))
            if device_id is None:
                row.update({
                    "status": "FAIL",
                    "severity": "ERROR",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": "SECTION_DEVICE_ID_INVALID",
                })
                return False

            expected_keyid, verified_ok, _ = self._verify_expected_keyid(
                device_id
            )
            row["assigned_device_id"] = device_id
            row["assigned_section_name"] = norm(section.get("name"))
            row["assigned_bv_id"] = section.get("bv_id", "")
            row["expected_keyid"] = expected_keyid
            row["expected_keyid_verified"] = "YES" if verified_ok else "NO"

            if not norm(row.get("assigned_bv_id")):
                row.update({
                    "status": "FAIL",
                    "severity": "ERROR",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": (
                        "BV_ID_EMPTY: 数据库馈线段 BV_ID 为空，"
                        "无法写入 FeedLine voltype"
                    ),
                })
                return False

            if not verified_ok:
                row.update({
                    "status": "FAIL",
                    "severity": "ERROR",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": "EXPECTED_KEYID_VERIFY_FAILED",
                })
                return False

            row["model_link_correct"] = ""
            row["association_ready"] = "YES"
            row["writeback_needed"] = "YES"
            row["status"] = "WARN"
            if row.get("override_cross_feeder") == "YES":
                row["severity"] = "RELINK"
                row["reason"] = (
                    "CROSS_FEEDER_OVERRIDE_READY: 已明确启用人工覆盖；"
                    "该 FeedLine 将改关联到本次选择的目标馈线，并使用目标馈线未占用数据库记录。"
                )
            elif row.get("relink_missing_section") == "YES":
                row["severity"] = "RELINK"
                row["reason"] = (
                    "STALE_SECTION_RELINK_READY: 旧13503设备已不存在；"
                    + (
                        "全新图按FeedLine顺序使用数据库现有馈线段。"
                        if reason_mode == "NEW_DRAWING_ORDER"
                        else "保留已有正确关联，并按数据库剩余记录顺序从小到大重新关联。"
                    )
                )
            else:
                row["severity"] = "UNLINKED"
                row["reason"] = (
                    "MODEL_NOT_LINKED_READY_FOR_ASSOCIATION: 全新图按顺序关联"
                    if reason_mode == "NEW_DRAWING_ORDER"
                    else "MODEL_NOT_LINKED_DB_SEQUENCE_READY: 保留已有正确关联；按当前馈线未占用数据库记录顺序从小到大关联"
                )
            reserved_db_ids.add(device_id)
            return True

        reason_mode = (
            "NEW_DRAWING_ORDER" if all_feedlines_unlinked
            else "PRESERVE_EXISTING_DB_SEQUENCE"
        )

        # Pair the unresolved G rows (already in G top-to-bottom / left-to-right
        # order) with the free DB rows in deterministic database sequence.
        for row, section in zip(pending, available):
            assign_existing_section(row, section, reason_mode=reason_mode)

        # Whatever remains after exhausting existing same-feeder DB rows is a
        # genuine shortage.  Mark every remaining row so the creation planner
        # creates exactly the missing count, then association execution can
        # write those newly created KeyIDs back to the corresponding FeedLines.
        if len(pending) > len(available):
            shortage = len(pending) - len(available)
            for row in pending[len(available):]:
                row.update({
                    "status": "FAIL",
                    "severity": "ERROR",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": (
                        "SECTION_NOT_AVAILABLE: "
                        f"当前馈线未占用数据库馈线段不足，实际短缺={shortage}；"
                        "仅创建缺少数量后继续按当前未关联FeedLine顺序关联"
                    ),
                })

        for row in rows:
            row["drawing_type"] = report.get("drawing_type", "SINGLE_FEEDER")
            row["region_index"] = report.get("region_index", 1)
            row["region_assignment_method"] = report.get(
                "region_assignment_method", "WHOLE_FILE"
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

    def _candidate_feeder_anchor_texts(self, parsed: ParsedG) -> List[Dict[str, Any]]:
        """
        Find feeder-name text anchors around Bus objects.

        Composite drawings generated by the project keep feeder names directly
        above their source Bus. Long horizontal Bus objects may span several
        merged feeder blocks, therefore every plausible text above that Bus is
        retained instead of taking only one nearest text.
        """
        buses = [obj for obj in parsed.objects if obj.tag == "Bus"]
        texts = [
            obj for obj in parsed.objects
            if obj.tag.lower() == "text"
            and self._is_reasonable_feeder_label(self._text_value(obj))
        ]

        found = {}

        # Composite files produced by the merge tool place feeder titles on a
        # common top band. A title can sit inside the intentional gap between
        # two Bus segments, so Bus containment alone would miss it (for
        # example a feeder title centered between two translated source
        # drawings). Preserve reasonable engineering labels on that top band
        # and let the database unique-match step decide whether they are real
        # feeder names.
        if buses:
            top_bus_y = min(bus.box.top for bus in buses)
            for txt in texts:
                if txt.box.cy <= top_bus_y + 40.0 and txt.box.bottom >= top_bus_y - 120.0:
                    text = self._text_value(txt)
                    key = (txt.xml_id, txt.xml_index)
                    found[key] = {
                        "hint": text,
                        "normalized_hint": normalize_engineering_name(text),
                        "source": "TOP_BAND_TEXT",
                        "text_xml_id": txt.xml_id,
                        "bus_xml_id": "",
                        "distance": round(abs(top_bus_y - txt.box.cy), 3),
                        "x": float(txt.box.cx),
                        "y": float(txt.box.cy),
                    }

        for bus in buses:
            for txt in texts:
                text = self._text_value(txt)
                # Feeder labels are expected above a Bus. For a long merged Bus
                # use horizontal containment; for a compact Bus use proximity.
                gap = bus.box.top - txt.box.bottom
                if gap < -25.0:
                    continue

                if bus.box.w >= 100.0:
                    ok = (
                        bus.box.left - 220.0 <= txt.box.cx <= bus.box.right + 220.0
                        and gap <= 280.0
                    )
                    score = max(gap, 0.0) + abs(txt.box.cy - bus.box.cy) * 0.05
                else:
                    dx = abs(txt.box.cx - bus.box.cx)
                    ok = dx <= 480.0 and gap <= 420.0
                    score = math.hypot(dx, max(gap, 0.0))

                if not ok:
                    continue

                key = (txt.xml_id, txt.xml_index)
                candidate = {
                    "hint": text,
                    "normalized_hint": normalize_engineering_name(text),
                    "source": "BUS_REGION_TEXT",
                    "text_xml_id": txt.xml_id,
                    "bus_xml_id": bus.xml_id,
                    "distance": round(float(score), 3),
                    "x": float(txt.box.cx),
                    "y": float(txt.box.cy),
                }
                old = found.get(key)
                if old is None or candidate["distance"] < old["distance"]:
                    found[key] = candidate

        return sorted(found.values(), key=lambda item: (item["x"], item["y"]))


    def detect_drawing_layout(
        self,
        parsed: ParsedG,
        drawing_mode: str = "AUTO",
    ) -> Dict[str, Any]:
        """
        Detect SINGLE_FEEDER / MULTI_FEEDER_COMPOSITE / AMBIGUOUS.

        Critical rule:
        The G file itself determines spatial feeder anchors.
        Database lookup CONFIRMS an anchor; it no longer decides whether a
        clearly visible G feeder title exists.

        This prevents a temporary DB lookup mismatch from collapsing a large
        composite drawing into one unresolved region.
        """
        mode = norm(drawing_mode).upper() or "AUTO"

        raw_candidates = self._candidate_feeder_anchor_texts(parsed)
        g_anchors = self._canonicalize_anchor_candidates(raw_candidates)

        # Database confirmation is metadata only at layout-detection time.
        db_cache = {}
        for anchor in g_anchors:
            hint = anchor["normalized_hint"]
            try:
                if hint not in db_cache:
                    db_cache[hint] = self.db.find_feeders_by_name_hint(
                        hint,
                        table_id=self.feeder_table_id,
                    )
                records = db_cache[hint]
            except Exception as exc:
                records = []
                anchor["db_anchor_lookup_error"] = str(exc)

            anchor["feeder_records"] = records
            anchor["db_match_count"] = len(records)

            if len(records) == 1:
                anchor["feeder_id"] = int_or_none(records[0].get("id"))
                anchor["feeder_name"] = norm(
                    records[0].get("display_name")
                    or records[0].get("name")
                )
                anchor["db_anchor_status"] = "MATCHED"
            elif len(records) == 0:
                anchor["feeder_id"] = ""
                anchor["feeder_name"] = ""
                anchor["db_anchor_status"] = "NOT_FOUND"
            else:
                anchor["feeder_id"] = ""
                anchor["feeder_name"] = ""
                anchor["db_anchor_status"] = "NOT_UNIQUE"

        # Duplicate G feeder title is determined from the actual G title, not
        # only from database feeder_id. This catches merged-source title errors
        # even when the DB resolver cannot identify the feeder yet.
        by_token = defaultdict(list)
        for anchor in g_anchors:
            by_token[anchor["normalized_hint"]].append(anchor)

        for group in by_token.values():
            duplicate = len(group) > 1
            for anchor in group:
                anchor["duplicate_feeder_anchor"] = duplicate

        bus_count = sum(
            1 for obj in parsed.objects
            if obj.tag == "Bus"
        )
        feedline_count = sum(
            1 for obj in parsed.objects
            if obj.tag == FEEDLINE_TAG
        )

        topology_profile = FeederDrawingTopologyClassifier(self.parser).classify(parsed)

        if mode == "SINGLE":
            drawing_type = "SINGLE_FEEDER"
        elif mode == "MULTI":
            drawing_type = (
                "MULTI_FEEDER_COMPOSITE"
                if len(g_anchors) >= 2
                or int(topology_profile.get("feeder_source_branch_count", 0)) >= 2
                else "AMBIGUOUS"
            )
        else:
            # AUTO uses electrical topology first. Multiple raw <Bus> objects
            # are never sufficient by themselves because some are 6x6 junction
            # points rather than physical busbars.
            drawing_type = topology_profile["drawing_type"]

        if self.log:
            self.log(
                f"[{parsed.path.name}] G馈线标题候选="
                f"{len(raw_candidates)}；清洗后锚点={len(g_anchors)}；"
                f"数据库唯一确认="
                f"{sum(1 for x in g_anchors if x.get('db_match_count') == 1)}"
            )
            if g_anchors:
                self.log(
                    f"[{parsed.path.name}] G馈线锚点："
                    + ", ".join(
                        str(x.get("hint", ""))
                        for x in g_anchors
                    )
                )

        return {
            "drawing_type": drawing_type,
            "requested_mode": mode,
            "anchor_candidates": raw_candidates,
            "anchors": g_anchors,
            "bus_count": bus_count,
            "feedline_count": feedline_count,
            "g_anchor_count": len(g_anchors),
            "db_resolved_anchor_count": sum(
                1
                for x in g_anchors
                if x.get("db_match_count") == 1
            ),
            "classification_reason": topology_profile.get("classification_reason", ""),
            "effective_busbar_count": topology_profile.get("effective_busbar_count", 0),
            "feeder_source_branch_count": topology_profile.get("feeder_source_branch_count", 0),
            "bus_source_branch_count": topology_profile.get("bus_source_branch_count", 0),
            "bus_tie_branch_count": topology_profile.get("bus_tie_branch_count", 0),
            "topology_feeder_title_count": topology_profile.get("feeder_title_count", 0),
        }


    @staticmethod
    def _object_endpoints(obj: GObject) -> List[Tuple[float, float]]:
        """Return first/last geometry points for topology consistency checks."""
        raw = norm(obj.attrs.get("d"))
        points = []
        if raw:
            for x, y in re.findall(
                r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
                raw,
            ):
                points.append((float(x), float(y)))
        if len(points) >= 2:
            return [points[0], points[-1]]

        box = obj.box
        if box.w >= box.h:
            return [(box.left, box.cy), (box.right, box.cy)]
        return [(box.cx, box.top), (box.cx, box.bottom)]

    def _feedline_topology_components(
        self,
        parsed: ParsedG,
        feedline_region: Dict[str, int],
        tolerance: float = 8.0,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build a lightweight connectivity graph from FeedLine/ConnectLine path
        endpoints. It is a consistency guard, not the primary feeder splitter:
        future drawings may intentionally connect two feeders, so a component
        crossing regions is reported but never used to merge the regions.
        """
        objects = [
            obj for obj in parsed.objects
            if obj.tag in {"FeedLine", "ConnectLine"}
        ]
        parent = list(range(len(objects)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        point_map = defaultdict(list)
        scale = max(float(tolerance), 0.1)
        for index, obj in enumerate(objects):
            for x, y in self._object_endpoints(obj):
                key = (round(x / scale), round(y / scale))
                point_map[key].append(index)

        for members in point_map.values():
            if len(members) <= 1:
                continue
            first = members[0]
            for other in members[1:]:
                union(first, other)

        component_members = defaultdict(list)
        for index, obj in enumerate(objects):
            component_members[find(index)].append(obj)

        result = {}
        component_no = 0
        for members in component_members.values():
            feed_members = [obj for obj in members if obj.tag == FEEDLINE_TAG]
            if not feed_members:
                continue
            component_no += 1
            regions = {
                feedline_region.get(obj.xml_id)
                for obj in feed_members
                if feedline_region.get(obj.xml_id) is not None
            }
            regions.discard(None)
            cross = len(regions) > 1
            for obj in feed_members:
                result[obj.xml_id] = {
                    "topology_component": component_no,
                    "topology_cross_region": "YES" if cross else "NO",
                    "topology_region_count": len(regions),
                    "topology_feedline_count": len(feed_members),
                }
        return result

    @staticmethod
    def _build_spatial_regions(anchors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anchors = sorted(anchors, key=lambda item: item["x"])
        regions = []
        for index, anchor in enumerate(anchors, start=1):
            left = -math.inf if index == 1 else (
                anchors[index - 2]["x"] + anchor["x"]
            ) / 2.0
            right = math.inf if index == len(anchors) else (
                anchor["x"] + anchors[index]["x"]
            ) / 2.0
            item = dict(anchor)
            item.update({
                "region_index": index,
                "left": left,
                "right": right,
            })
            regions.append(item)
        return regions

    # ------------------------------------------------------------------
    # RMU-anchored feeder topology (v3.6)
    # ------------------------------------------------------------------
    @staticmethod
    def _point_to_segment_distance(px, py, ax, ay, bx, by):
        dx = bx - ax
        dy = by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        qx = ax + t * dx
        qy = ay + t * dy
        return math.hypot(px - qx, py - qy)

    @classmethod
    def _segments_intersect_or_close(cls, a, b, tolerance=10.0):
        (a1, a2) = a
        (b1, b2) = b
        distances = [
            cls._point_to_segment_distance(a1[0], a1[1], b1[0], b1[1], b2[0], b2[1]),
            cls._point_to_segment_distance(a2[0], a2[1], b1[0], b1[1], b2[0], b2[1]),
            cls._point_to_segment_distance(b1[0], b1[1], a1[0], a1[1], a2[0], a2[1]),
            cls._point_to_segment_distance(b2[0], b2[1], a1[0], a1[1], a2[0], a2[1]),
        ]
        return min(distances) <= tolerance

    @staticmethod
    def _polyline_points(obj: GObject) -> List[Tuple[float, float]]:
        raw = norm(obj.attrs.get("d"))
        points = []
        if raw:
            for token in raw.split():
                if "," not in token:
                    continue
                x, y = token.split(",", 1)
                try:
                    points.append((float(x), float(y)))
                except ValueError:
                    pass
        if len(points) >= 2:
            return points
        b = obj.box
        if b.w >= b.h:
            return [(b.left, b.cy), (b.right, b.cy)]
        return [(b.cx, b.top), (b.cx, b.bottom)]

    @classmethod
    def _object_segments(cls, obj: GObject):
        pts = cls._polyline_points(obj)
        return list(zip(pts[:-1], pts[1:]))

    @staticmethod
    def _is_network_object(obj: GObject) -> bool:
        tag = obj.tag.lower()
        if tag in {"feedline", "connectline", "bus"}:
            return True
        electrical_tokens = (
            "breaker", "disconnector", "daozha", "busdis",
            "switch", "aclinesegment", "aclsegment",
        )
        return any(token in tag for token in electrical_tokens)

    @classmethod
    def _network_objects_connected(cls, a: GObject, b: GObject, tolerance=12.0):
        # Fast bounding-box rejection first.
        if (
            a.box.right + tolerance < b.box.left
            or b.box.right + tolerance < a.box.left
            or a.box.bottom + tolerance < b.box.top
            or b.box.bottom + tolerance < a.box.top
        ):
            return False
        for seg_a in cls._object_segments(a):
            for seg_b in cls._object_segments(b):
                if cls._segments_intersect_or_close(seg_a, seg_b, tolerance):
                    return True
        return False

    @classmethod
    def _object_touches_box(cls, obj: GObject, box: Box, tolerance=18.0):
        expanded = Box(
            box.x - tolerance,
            box.y - tolerance,
            box.w + tolerance * 2,
            box.h + tolerance * 2,
        )
        if not (
            obj.box.right >= expanded.left
            and obj.box.left <= expanded.right
            and obj.box.bottom >= expanded.top
            and obj.box.top <= expanded.bottom
        ):
            return False
        # For RMUs, any conductive object entering/inside the frame is a useful
        # topology attachment point.
        for pt in cls._polyline_points(obj):
            if (
                expanded.left <= pt[0] <= expanded.right
                and expanded.top <= pt[1] <= expanded.bottom
            ):
                return True
        return expanded.center_contains(obj.box, tolerance=0)

    def _inspect_rmu_anchor(
        self,
        rmu_parsed: ParsedG,
        frame,
        frame_index: int,
        preassigned_name_candidates=None,
        preassigned_smart_markers=None,
    ):
        """Return trusted/untrusted RMU feeder-reference information."""
        rmu_parser = GParser(
            required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
            label_regex=RMU_LABEL_PATTERN,
            max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
            overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
            excluded_rmu_name_strings=self.rmu_name_exclusions,
        )
        validator = RmuValidator(
            self.db,
            rmu_parser,
            self.rmu_device_rules,
            breaker_name_source="GRAPHICAL_TEXT",
            log=lambda _msg: None,
        )
        positions = [
            key for key, enabled in self.rmu_name_positions.items() if enabled
        ] or ["top"]
        resolved = validator._resolve_rmu_name(
            rmu_parsed,
            frame,
            positions,
            preassigned_candidates=preassigned_name_candidates,
        )
        type_info = rmu_parser.classify_rmu_type(rmu_parsed, frame)
        smart_info = (
            (preassigned_smart_markers or {}).get(
                frame.frame.xml_id,
                {
                    "is_smart": False,
                    "markers": [],
                    "marker_types": [],
                },
            )
        )
        result = {
            "frame_index": frame_index,
            "frame_xml_id": frame.frame.xml_id,
            "rmu_name": "",
            "rmu_type": type_info.get("rmu_type", "UNKNOWN"),
            "rmu_type_source": type_info.get("source", "UNRESOLVED"),
            "rmu_type_text": type_info.get("text_type", "UNKNOWN"),
            "rmu_type_devref": type_info.get("devref_type", "UNKNOWN"),
            "rmu_type_consistent": "YES" if type_info.get("consistent") else "NO",
            "rmu_is_smart": "YES" if smart_info.get("is_smart") else "NO",
            "rmu_smart_marker_types": ", ".join(
                smart_info.get("marker_types", [])
            ),
            "rmu_id": "",
            "feeder_id": "",
            "trusted": False,
            "reason": "",
            "linked_evidence": 0,
            "wrong_link_count": 0,
            "frame": frame,
        }
        selected = resolved.get("selected")
        if not selected:
            rows = resolved.get("candidate_rows", [])
            if rows:
                result["rmu_name"] = rows[0].get("name", "")
            result["reason"] = (
                "RMU_REFERENCE_IGNORED: 环网柜名称数据库记录不是唯一1条"
            )
            return result

        result["rmu_name"] = selected.get("name", "")
        records = selected.get("db_records", []) or []
        if len(records) != 1:
            result["reason"] = (
                f"RMU_REFERENCE_IGNORED: 环网柜数据库记录数={len(records)}"
            )
            return result

        record = records[0]
        rmu_id = int_or_none(record.get("id"))
        feeder_id = int_or_none(record.get("feeder_id"))
        result["rmu_id"] = rmu_id or ""
        result["feeder_id"] = feeder_id or ""
        if rmu_id is None or feeder_id is None:
            result["reason"] = "RMU_REFERENCE_IGNORED: RMU ID或FEEDER_ID为空"
            return result

        contained = [
            obj for obj in rmu_parsed.objects
            if obj.tag in self.rmu_device_rules
            and frame.frame.box.center_contains(obj.box, tolerance=2.0)
        ]
        linked = [obj for obj in contained if obj.keyid]
        if not linked:
            result["reason"] = "RMU_REFERENCE_IGNORED: 环网柜当前未关联任何模型"
            return result

        correct_evidence = 0
        wrong = 0
        for obj in linked:
            rule = self.rmu_device_rules.get(obj.tag, {})
            try:
                keyid = int(obj.keyid)
                verified = self.db.verify_keyid(keyid)
                did = int_or_none(verified.get("device_id"))
                tab = int_or_none(verified.get("tab_no"))
                dom = int_or_none(verified.get("col_no"))
                if (
                    did is None
                    or tab != int(rule.get("table_id", -1))
                    or dom != int(rule.get("domain", -1))
                ):
                    wrong += 1
                    continue
                current = self.db.get_device_by_id(tab, did)
                if not current or int_or_none(current.get("combined_id")) != rmu_id:
                    wrong += 1
                    continue
                correct_evidence += 1
            except Exception:
                wrong += 1

        result["linked_evidence"] = correct_evidence
        result["wrong_link_count"] = wrong
        if wrong:
            result["reason"] = (
                f"RMU_REFERENCE_IGNORED: 当前已有模型中存在{wrong}条错误关联"
            )
            return result
        if correct_evidence == 0:
            result["reason"] = (
                "RMU_REFERENCE_IGNORED: 没有可验证的正确模型作为馈线依据"
            )
            return result

        result["trusted"] = True
        result["reason"] = (
            f"TRUSTED_RMU_REFERENCE: 已验证{correct_evidence}条现有模型，"
            f"FEEDER_ID={feeder_id}"
        )
        return result

    def _build_topology_regions(self, parsed: ParsedG, rmu_anchors: List[Dict[str, Any]]):
        network = [obj for obj in parsed.objects if self._is_network_object(obj)]
        n = len(network)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        # Spatial hash avoids an O(N^2) scan on large merged drawings.
        cell_size = 600.0
        buckets = defaultdict(list)
        for i, obj in enumerate(network):
            left = int(math.floor((obj.box.left - 15) / cell_size))
            right = int(math.floor((obj.box.right + 15) / cell_size))
            top = int(math.floor((obj.box.top - 15) / cell_size))
            bottom = int(math.floor((obj.box.bottom + 15) / cell_size))
            for gx in range(left, right + 1):
                for gy in range(top, bottom + 1):
                    buckets[(gx, gy)].append(i)

        checked = set()
        for members in buckets.values():
            for a_pos in range(len(members)):
                a = members[a_pos]
                for b_pos in range(a_pos + 1, len(members)):
                    b = members[b_pos]
                    pair = (min(a, b), max(a, b))
                    if pair in checked:
                        continue
                    checked.add(pair)
                    if self._network_objects_connected(network[a], network[b]):
                        union(a, b)

        # One RMU cabinet electrically bridges the branches touching its frame.
        anchor_component_indexes = {}
        for anchor_index, anchor in enumerate(rmu_anchors):
            frame_box = anchor["frame"].frame.box
            touched = [
                i for i, obj in enumerate(network)
                if self._object_touches_box(obj, frame_box)
            ]
            if touched:
                first = touched[0]
                for other in touched[1:]:
                    union(first, other)
            anchor_component_indexes[anchor_index] = touched

        grouped = defaultdict(list)
        for i, obj in enumerate(network):
            grouped[find(i)].append(obj)

        # Recalculate after RMU unions.
        roots = {i: find(i) for i in range(n)}
        regions = {}
        for root, objs in grouped.items():
            actual_root = find(root)
            regions.setdefault(actual_root, {
                "network_objects": [],
                "feedlines": [],
                "rmu_anchors": [],
            })
            regions[actual_root]["network_objects"].extend(objs)
        for region in regions.values():
            region["feedlines"] = sorted(
                [o for o in region["network_objects"] if o.tag == FEEDLINE_TAG],
                key=self._feedline_sort_key,
            )

        for anchor_index, touched in anchor_component_indexes.items():
            if not touched:
                continue
            root = find(touched[0])
            regions.setdefault(root, {
                "network_objects": [], "feedlines": [], "rmu_anchors": []
            })["rmu_anchors"].append(rmu_anchors[anchor_index])

        # Keep only regions containing FeedLine; isolated device fragments are irrelevant.
        result = [r for r in regions.values() if r.get("feedlines")]
        result.sort(
            key=lambda r: self._feedline_sort_key(r["feedlines"][0])
            if r.get("feedlines") else (10**18, 10**18, 10**18)
        )
        for idx, region in enumerate(result, start=1):
            region["region_index"] = idx
        return result

    def _coalesce_regions_by_confirmed_feeder(self, regions: List[Dict[str, Any]]):
        """
        Merge disconnected drawing fragments that are independently confirmed
        by trusted RMUs to the SAME FEEDER_ID.

        This guarantees one shared dms_section_device candidate pool per
        feeder, preventing the same SECxxx record from being allocated once in
        each disconnected fragment.
        """
        grouped = {}
        order = []
        for original_index, region in enumerate(regions, start=1):
            trusted = [a for a in region.get("rmu_anchors", []) if a.get("trusted")]
            feeder_ids = {
                int(a["feeder_id"]) for a in trusted
                if int_or_none(a.get("feeder_id")) is not None
            }
            if len(feeder_ids) == 1:
                key = ("FEEDER", next(iter(feeder_ids)))
            else:
                # Conflict/no-reference components must remain isolated; they
                # are blocked independently and never get merged by guesswork.
                key = ("COMPONENT", original_index)

            if key not in grouped:
                grouped[key] = {
                    "network_objects": [],
                    "feedlines": [],
                    "rmu_anchors": [],
                    "source_component_count": 0,
                }
                order.append(key)
            target = grouped[key]
            target["network_objects"].extend(region.get("network_objects", []))
            target["feedlines"].extend(region.get("feedlines", []))
            target["rmu_anchors"].extend(region.get("rmu_anchors", []))
            target["source_component_count"] += 1

        result = []
        for key in order:
            region = grouped[key]
            # Deduplicate by XML index in case an RMU bridge caused a repeated
            # object reference during component consolidation.
            dedup = {obj.xml_index: obj for obj in region["feedlines"]}
            region["feedlines"] = sorted(dedup.values(), key=self._feedline_sort_key)
            result.append(region)

        result.sort(
            key=lambda r: self._feedline_sort_key(r["feedlines"][0])
            if r.get("feedlines") else (10**18, 10**18, 10**18)
        )
        for idx, region in enumerate(result, start=1):
            region["region_index"] = idx
        return result
    def _validate_rmu_topology_region(self, parsed: ParsedG, region: Dict[str, Any]):
        feedlines = sorted(region.get("feedlines", []), key=self._feedline_sort_key)
        anchors = region.get("rmu_anchors", [])
        trusted = [a for a in anchors if a.get("trusted")]
        ignored = [a for a in anchors if not a.get("trusted")]
        feeder_ids = sorted({int(a["feeder_id"]) for a in trusted if int_or_none(a.get("feeder_id")) is not None})

        report = {
            "report_type": "FEEDER",
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "drawing_type": "RMU_TOPOLOGY",
            "region_index": region.get("region_index", 1),
            "region_assignment_method": "RMU_TOPOLOGY+FEEDER_ID",
            "feeder_hint": "",
            "feeder_normalized_hint": "",
            "feeder_hint_source": "NOT_USED",
            "feeder_records": [],
            "feeder_id": "",
            "feeder_name": "",
            "feedline_rows": [],
            "association_eligible": False,
            "status": "FAIL",
            "severity": "ERROR",
            "reason": "",
            "trusted_rmu_count": len(trusted),
            "ignored_rmu_count": len(ignored),
            "trusted_rmu_names": ", ".join(
                f"{a.get('rmu_name', '')}({a.get('rmu_type', 'UNKNOWN')})"
                for a in trusted
            ),
            "trusted_feeder_ids": ", ".join(str(x) for x in feeder_ids),
            "ignored_rmu_details": " | ".join(
                f"{a.get('rmu_name') or '-'}({a.get('rmu_type', 'UNKNOWN')}):{a.get('reason')}"
                for a in ignored
            ),
            "rmu_reference_rows": [
                {k: v for k, v in a.items() if k != "frame"} for a in anchors
            ],
        }

        def blocked(reason):
            report["reason"] = reason
            for idx, obj in enumerate(feedlines, start=1):
                row = self._new_row(obj, idx)
                row.update({
                    "drawing_type": report["drawing_type"],
                    "region_index": report["region_index"],
                    "region_assignment_method": report["region_assignment_method"],
                    "topology_component": report["region_index"],
                    "status": "FAIL",
                    "severity": "BLOCKED",
                    "reason": reason,
                })
                report["feedline_rows"].append(row)
            report["summary"] = self._summary(report)
            return report

        if not trusted:
            return blocked(
                "NO_TRUSTED_RMU_REFERENCE: 当前连接区域没有可信已关联环网柜，禁止自动关联馈线段"
            )
        if len(feeder_ids) > 1:
            detail = ", ".join(
                f"{a.get('rmu_name')}->{a.get('feeder_id')}" for a in trusted
            )
            return blocked(
                "FEEDER_RMU_CONFLICT: 当前连接区域的可信环网柜来自不同FEEDER_ID，"
                f"禁止自动关联，请人工确认。{detail}"
            )
        if len(feeder_ids) != 1:
            return blocked("FEEDER_ID_NOT_CONFIRMED_BY_RMU")

        feeder_id = feeder_ids[0]
        report["feeder_id"] = feeder_id
        try:
            feeder = self.db.get_feeder_info(feeder_id) or {}
        except Exception:
            feeder = {}
        report["feeder_name"] = norm(feeder.get("display_name") or feeder.get("name"))
        report["feeder_records"] = [feeder] if feeder else []

        _, section_rows = self.db.get_sections_by_feeder_id(
            feeder_id, table_id=self.section_table_id
        )
        section_rows = sorted(section_rows, key=natural_section_key)
        section_by_id = {
            int(row["id"]): row for row in section_rows
            if int_or_none(row.get("id")) is not None
        }

        rows = []
        used = set()
        pending = []

        # Pre-scan current FeedLine links so duplicate use of the SAME
        # dms_section_device is treated as a repairable model problem on ALL
        # duplicated G rows, not just on the later row encountered.
        current_link_meta = {}
        linked_device_usage = defaultdict(list)
        for obj in feedlines:
            if not obj.keyid:
                continue
            meta = {
                "device_id": None,
                "table_id": None,
                "domain": None,
                "current": None,
                "owner_id": None,
                "verify_error": "",
            }
            try:
                current_keyid = int(obj.keyid)
                verified = self.db.verify_keyid(current_keyid)
                did = int_or_none(verified.get("device_id"))
                tab = int_or_none(verified.get("tab_no"))
                dom = int_or_none(verified.get("col_no"))
                current = (
                    self.db.get_device_by_id(self.section_table_id, did)
                    if did is not None and tab == self.section_table_id
                    else None
                )
                owner_id = int_or_none((current or {}).get("feeder_id"))
                meta.update({
                    "device_id": did,
                    "table_id": tab,
                    "domain": dom,
                    "current": current,
                    "owner_id": owner_id,
                })
                if (
                    current is not None
                    and did in section_by_id
                    and owner_id == feeder_id
                    and tab == self.section_table_id
                ):
                    # Count usage regardless of domain so two G objects that
                    # reference the same section remain a duplicate even when
                    # one/both KeyIDs carry a wrong domain.
                    linked_device_usage[did].append(obj.xml_id)
            except Exception as exc:
                meta["verify_error"] = str(exc)
            current_link_meta[obj.xml_id] = meta

        duplicate_device_ids = {
            did for did, xml_ids in linked_device_usage.items()
            if len(xml_ids) > 1
        }

        # First pass: preserve unique correct links; duplicated correct links
        # are all exposed as selectable DUPLICATE_LINK repair candidates.
        for idx, obj in enumerate(feedlines, start=1):
            row = self._new_row(obj, idx)
            row.update({
                "drawing_type": report["drawing_type"],
                "region_index": report["region_index"],
                "region_assignment_method": report["region_assignment_method"],
                "topology_component": report["region_index"],
            })
            if not obj.keyid:
                row["status"] = "WARN"
                row["severity"] = "UNLINKED"
                row["reason"] = "MODEL_NOT_LINKED"
                rows.append(row)
                pending.append(row)
                continue

            meta = current_link_meta.get(obj.xml_id, {})
            did = int_or_none(meta.get("device_id"))
            tab = int_or_none(meta.get("table_id"))
            dom = int_or_none(meta.get("domain"))
            current = meta.get("current")
            owner_id = int_or_none(meta.get("owner_id"))
            row["current_device_id"] = did or ""
            row["current_table_id"] = tab or ""
            row["current_domain"] = dom if dom is not None else ""
            if meta.get("verify_error"):
                row["reason"] = (
                    f"CURRENT_KEYID_VERIFY_ERROR: {meta.get('verify_error')}"
                )

            if current:
                row["current_db_name"] = norm(current.get("name"))
                row["current_db_code"] = norm(current.get("code"))
                row["current_bv_id"] = current.get("bv_id", "")
                row["current_feeder_id"] = owner_id or ""

            duplicate_current_link = (
                did is not None and did in duplicate_device_ids
            )
            domain_only_wrong = (
                current is not None
                and did in section_by_id
                and owner_id == feeder_id
                and tab == self.section_table_id
                and dom != self.section_domain
                and did not in used
                and not duplicate_current_link
            )
            correct = (
                current is not None
                and did in section_by_id
                and owner_id == feeder_id
                and tab == self.section_table_id
                and dom == self.section_domain
                and did not in used
                and not duplicate_current_link
            )
            if duplicate_current_link:
                duplicate_xmls = linked_device_usage.get(did, [])
                row.update({
                    "model_link_correct": "NO",
                    "status": "WARN",
                    "severity": "DUPLICATE_LINK",
                    "reason": (
                        "DUPLICATE_LINK: 同一数据库馈线段被多个FeedLine重复关联；"
                        f"device_id={did}; XML={','.join(duplicate_xmls)}。"
                        "数据库事实仍唯一，可选择需要重新分配的FeedLine。"
                    ),
                })
                pending.append(row)
            elif domain_only_wrong:
                used.add(did)
                expected, ok, _ = self._verify_expected_keyid(did)
                bv_id = norm(current.get("bv_id"))
                row.update({
                    "assigned_device_id": did,
                    "assigned_section_name": norm(current.get("name")),
                    "assigned_bv_id": current.get("bv_id", ""),
                    "expected_keyid": expected,
                    "expected_keyid_verified": "YES" if ok else "NO",
                    "relink_same_section": "YES",
                    "model_link_correct": "NO",
                })
                if not bv_id:
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "reason": "BV_ID_EMPTY: 当前馈线段BV_ID为空，禁止重写模型",
                    })
                elif not ok:
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "reason": "EXPECTED_KEYID_VERIFY_FAILED",
                    })
                else:
                    row.update({
                        "status": "WARN",
                        "severity": "RELINK",
                        "association_ready": "YES",
                        "writeback_needed": "YES",
                        "reason": (
                            "DOMAIN_RELINK_READY: 当前13503馈线段和feeder_id均正确，"
                            f"仅域号错误 current_domain={dom}, "
                            f"expected_domain={self.section_domain}；"
                            "保持device_id不变并重写KeyID。"
                        ),
                    })
            elif correct:
                used.add(did)
                row.update({
                    "assigned_device_id": did,
                    "assigned_section_name": norm(current.get("name")),
                    "assigned_bv_id": current.get("bv_id", ""),
                    "expected_keyid": int(obj.keyid),
                    "expected_keyid_verified": "YES",
                    "model_link_correct": "YES",
                    "association_ready": "YES",
                    "writeback_needed": "NO",
                    "status": "PASS",
                    "severity": "PASS",
                    "reason": "MODEL_ALREADY_LINKED_CORRECT",
                })
            else:
                row.update({
                    "model_link_correct": "NO",
                    "status": "WARN",
                    "severity": "RELINK",
                    "reason": (
                        "MODEL_RELINK_REQUIRED: 当前FeedLine旧关联不属于本连接区域确认的馈线、"
                        "表号/域号不正确或重复占用，将从剩余馈线段中重新分配"
                    ),
                })
                pending.append(row)
            rows.append(row)

        available = [
            section for section in section_rows
            if int_or_none(section.get("id")) not in used
        ]
        available.sort(key=natural_section_key)
        pending.sort(key=lambda row: self._feedline_sort_key(
            next(obj for obj in feedlines if obj.xml_id == row["xml_id"])
        ))

        for row, section in zip(pending, available):
            did = int_or_none(section.get("id"))
            if did is None:
                row.update({"status": "FAIL", "severity": "ERROR", "reason": "SECTION_DEVICE_ID_INVALID"})
                continue
            expected, ok, _ = self._verify_expected_keyid(did)
            bv_id = norm(section.get("bv_id"))
            row.update({
                "assigned_device_id": did,
                "assigned_section_name": norm(section.get("name")),
                "assigned_bv_id": section.get("bv_id", ""),
                "expected_keyid": expected,
                "expected_keyid_verified": "YES" if ok else "NO",
            })
            if not bv_id:
                row.update({"status": "FAIL", "severity": "ERROR", "reason": "BV_ID_EMPTY", "association_ready": "NO", "writeback_needed": "NO"})
            elif not ok:
                row.update({"status": "FAIL", "severity": "ERROR", "reason": "EXPECTED_KEYID_VERIFY_FAILED", "association_ready": "NO", "writeback_needed": "NO"})
            else:
                relink = row.get("model_linked") == "YES"
                duplicate_link = row.get("severity") == "DUPLICATE_LINK"
                row.update({
                    "association_ready": "YES",
                    "writeback_needed": "YES",
                    "status": "WARN",
                    "severity": (
                        "DUPLICATE_LINK"
                        if duplicate_link
                        else ("RELINK" if relink else "UNLINKED")
                    ),
                    "reason": (
                        "DUPLICATE_LINK_REASSIGN_READY: 当前数据库馈线段被多个FeedLine重复占用；"
                        "该行可由用户选择重新分配。"
                        if duplicate_link
                        else (
                            "MODEL_RELINK_READY"
                            if relink
                            else "MODEL_NOT_LINKED_READY_FOR_ASSOCIATION"
                        )
                    ),
                })

        if len(pending) > len(available):
            for row in pending[len(available):]:
                row.update({
                    "status": "FAIL", "severity": "ERROR",
                    "association_ready": "NO", "writeback_needed": "NO",
                    "reason": "SECTION_NOT_AVAILABLE: 数据库剩余馈线段数量不足",
                })

        report["feedline_rows"] = rows
        report["association_eligible"] = True
        fail_count = sum(1 for row in rows if row.get("status") == "FAIL")
        ready_count = sum(1 for row in rows if row.get("association_ready") == "YES" and row.get("writeback_needed") == "YES")
        report["status"] = "WARN" if fail_count else "PASS"
        report["severity"] = "PARTIAL_ERROR" if fail_count else "PASS"
        report["reason"] = (
            f"FEEDER_RMU_TOPOLOGY_CONFIRMED: FEEDER_ID={feeder_id}; "
            f"可信RMU={len(trusted)}; 忽略RMU={len(ignored)}; 可关联={ready_count}; 错误={fail_count}"
        )
        report["summary"] = self._summary(report)
        return report
    def validate_file_with_feeder_record(
        self,
        g_path: str | Path,
        feeder_record: Dict[str, Any],
        *,
        source: str = "FACID",
    ) -> Dict[str, Any]:
        """Validate the whole G file against one already-confirmed feeder."""
        parsed = self.parser.parse(g_path)
        feedlines = [
            obj for obj in parsed.objects
            if obj.tag == FEEDLINE_TAG
        ]
        display = norm(
            feeder_record.get("display_name")
            or feeder_record.get("name")
        )
        hint = {
            "hint": display,
            "normalized_hint": normalize_engineering_name(display),
            "source": source,
            "text_xml_id": "",
            "bus_xml_id": "",
            "distance": "",
        }
        report = self._validate_parsed_region(
            parsed,
            feedlines=feedlines,
            feeder_hint=hint,
            region_meta={
                "drawing_type": "SINGLE_FEEDER",
                "region_index": 1,
                "region_assignment_method": source,
            },
            forced_feeder_record=feeder_record,
            forced_source=source,
        )
        return {
            "report_type": "FEEDER_FILE",
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "drawing_type": "SINGLE_FEEDER",
            "feeder_regions": [report],
            "rmu_reference_rows": [],
            "status": report.get("status", "FAIL"),
        }

    def validate_file(self, g_path: str | Path, drawing_mode: str = "AUTO") -> Dict[str, Any]:
        """
        Validate FeedLine models by RMU-derived FEEDER_ID and G topology.

        Feeder-name text and drawing-mode classification are no longer used as
        automatic-association evidence.  The same algorithm handles a single
        feeder drawing and a merged overview drawing.
        """
        parsed = self.parser.parse(g_path)

        rmu_parser = GParser(
            required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
            label_regex=RMU_LABEL_PATTERN,
            max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
            overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
            excluded_rmu_name_strings=self.rmu_name_exclusions,
        )
        rmu_parsed = rmu_parser.parse(g_path)
        frames = rmu_parser.find_rmu_frames(rmu_parsed)
        rmu_positions = [
            key
            for key, enabled in self.rmu_name_positions.items()
            if enabled
        ] or ["top"]
        preassigned_name_candidates = (
            rmu_parser.assign_rmu_label_candidates_globally(
                rmu_parsed,
                frames,
                rmu_positions,
            )
        )
        preassigned_smart_markers = (
            rmu_parser.assign_rmu_smart_markers_globally(
                rmu_parsed,
                frames,
            )
        )
        rmu_anchors = [
            self._inspect_rmu_anchor(
                rmu_parsed,
                frame,
                idx,
                preassigned_name_candidates=preassigned_name_candidates,
                preassigned_smart_markers=preassigned_smart_markers,
            )
            for idx, frame in enumerate(frames, start=1)
        ]

        trusted_count = sum(1 for a in rmu_anchors if a.get("trusted"))
        ignored_count = len(rmu_anchors) - trusted_count
        self.log(
            f"[{parsed.path.name}] RMU拓扑馈线识别：环网柜={len(rmu_anchors)}；"
            f"可信参考={trusted_count}；忽略参考={ignored_count}"
        )
        for anchor in rmu_anchors:
            self.log(
                f"[{parsed.path.name}] RMU框XML={anchor.get('frame_xml_id') or '-'}；"
                f"类型={anchor.get('rmu_type') or 'UNKNOWN'}；"
                f"智能={anchor.get('rmu_is_smart') or 'NO'}；"
                f"RMU={anchor.get('rmu_name') or '-'}；"
                f"类型={anchor.get('rmu_type') or 'UNKNOWN'}；"
                f"FEEDER_ID={anchor.get('feeder_id') or '-'}；"
                f"参考={'YES' if anchor.get('trusted') else 'NO'}；"
                f"{anchor.get('reason')}"
            )

        regions = self._build_topology_regions(parsed, rmu_anchors)
        regions = self._coalesce_regions_by_confirmed_feeder(regions)
        region_reports = [
            self._validate_rmu_topology_region(parsed, region)
            for region in regions
        ]

        # Any FeedLine that somehow never entered a component is explicitly
        # blocked instead of silently ignored.
        assigned_ids = {
            row.get("xml_id")
            for report in region_reports
            for row in report.get("feedline_rows", [])
        }
        all_feedlines = [obj for obj in parsed.objects if obj.tag == FEEDLINE_TAG]
        orphan = [obj for obj in all_feedlines if obj.xml_id not in assigned_ids]
        if orphan:
            orphan_region = {
                "region_index": len(region_reports) + 1,
                "feedlines": orphan,
                "rmu_anchors": [],
            }
            region_reports.append(
                self._validate_rmu_topology_region(parsed, orphan_region)
            )

        self.log(
            f"[{parsed.path.name}] 拓扑连接区域={len(region_reports)}；"
            f"FeedLine={len(all_feedlines)}"
        )
        for report in region_reports:
            self.log(
                f"[{parsed.path.name}] 连接区域{report.get('region_index')}；"
                f"可信RMU={report.get('trusted_rmu_count', 0)}；"
                f"FEEDER_ID={report.get('feeder_id') or '-'}；"
                f"FeedLine={len(report.get('feedline_rows', []))}；"
                f"状态={report.get('status')}"
            )

        return {
            "report_type": "FEEDER_FILE",
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "drawing_type": "RMU_TOPOLOGY",
            "feeder_regions": region_reports,
            "rmu_reference_rows": [
                {k: v for k, v in a.items() if k != "frame"}
                for a in rmu_anchors
            ],
            "status": (
                "FAIL" if any(r.get("status") == "FAIL" for r in region_reports)
                else "WARN" if any(r.get("status") == "WARN" for r in region_reports)
                else "PASS"
            ),
        }

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
