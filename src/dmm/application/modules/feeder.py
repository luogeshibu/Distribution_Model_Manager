from __future__ import annotations

import shutil
import re
from collections import defaultdict, Counter
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.domain.feeder.validator import FeederValidator, natural_section_key, int_or_none
from dmm.domain.gfile.parser import GParser
from dmm.domain.gfile.master_station_frames import find_master_station_frames
from dmm.domain.feeder.ring_discovery import discover_makkah_ring_feeders
from dmm.domain.graphics_cleanup.feedline_feeder_topology import (
    analyze_feedline_feeder_topology_file,
)
from dmm.infrastructure.gfile.writeback import GWriteBackService
from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier
from dmm.config.defaults import (
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
    DEFAULT_NAME_POSITIONS,
    resolve_rmu_name_positions,
)


class FeederModelModule(ModelModule):
    module_id = "FEEDER"
    display_name = "馈线模型"
    description = (
        "麦加环网图馈线关联：先扫描所有最内层且含 CBreaker 的主网 Bay 框，"
        "唯一确认图中各主网馈线；再复用图形工作区的 FeedLine 拓扑归属逻辑，"
        "按 link/node_area、严格几何补链和红色 NOP 支路级断点，为每条 FeedLine "
        "确定唯一所属馈线。随后只在该所属馈线下复用已有 13503；若数量不足，"
        "也只在该所属馈线下创建实际缺少的 dms_section_device。冲突/未确定的 "
        "FeedLine 不猜测、不跨馈线分配。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _validator(db, settings, log_callback):
        effective_positions = resolve_rmu_name_positions(
            settings.get(
                "rmu_name_detection_mode",
                DEFAULT_RMU_NAME_DETECTION_MODE,
            ),
            settings.get("feeder_rmu_name_positions", DEFAULT_NAME_POSITIONS),
        )
        return FeederValidator(
            db=db,
            parser=GParser(),
            section_table_id=int(
                settings.get("section_table_id", 13503)
            ),
            section_domain=int(
                settings.get("section_domain", 1)
            ),
            feeder_table_id=int(
                settings.get("feeder_table_id", 13500)
            ),
            rmu_name_positions={position: True for position in effective_positions},
            rmu_name_exclusions=settings.get("rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS),
            allow_feeder_override=bool(settings.get("allow_feeder_override", False)),
            log=log_callback,
        )

    @staticmethod
    def _rules(settings):
        return {
            "FeedLine": {
                "table_id": int(
                    settings.get("section_table_id", 13503)
                ),
                "domain": int(
                    settings.get("section_domain", 1)
                ),
                "description": "馈线段 / dms_section_device",
            }
        }

    @staticmethod
    def _normalize_lookup_text(value):
        """Normalize case/separators while preserving numeric text exactly.

        Leading zeros are business-significant:
        AJWD 6 != AJWD 06.
        """
        return "".join(
            ch
            for ch in str(value or "").upper()
            if ch.isalnum()
        )

    @staticmethod
    def _normalize_feedline_ls(ls_value):
        value = str(ls_value or "").strip()
        if value == "": return "", 3, False, True
        if value == "1": return "1", 1, False, True
        if value == "2": return "2", 0, False, True
        try: number = int(value)
        except Exception: return value, None, False, False
        if number > 2: return "2", 0, True, True
        return value, None, False, False

    @classmethod
    def _section_type_from_ls(cls, ls_value):
        return cls._normalize_feedline_ls(ls_value)[1]

    @staticmethod
    def _section_prefix(feeder_record, section_rows=None):
        """Return the legacy SEC-name prefix used by dms_section_device.

        The feeder's station reference is a *full* engineering station name
        (for example ``JED CTL AJWD``), while legacy section NAME values use
        only the station/business code (``AJWD_43_SEC001``).  Using the full
        station name would incorrectly generate ``JED_CTL_AJWD_43_SEC001`` and
        make existing Oracle rows look missing.

        Existing section rows belonging to the resolved FEEDER_ID are the
        strongest source of truth.  When they expose one unambiguous
        ``*_SECnnn`` prefix, preserve it exactly.  If the feeder has no section
        rows yet, fall back to the last token of station_name plus feeder.name.
        """
        prefixes = {}
        for section in section_rows or []:
            name = str(section.get("name") or "").strip()
            match = re.match(r"^(.+)_SEC\d{3}$", name, flags=re.IGNORECASE)
            if not match:
                continue
            prefix = match.group(1).strip()
            if prefix:
                prefixes.setdefault(prefix.upper(), prefix)

        if len(prefixes) == 1:
            return next(iter(prefixes.values()))

        station = str(feeder_record.get("station_name") or "").strip()
        feeder_name = str(feeder_record.get("name") or "").strip()
        if not station or not feeder_name:
            return ""

        def clean(value):
            value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
            return value.strip("_")

        station_tokens = [
            token for token in re.split(r"[^A-Za-z0-9]+", station)
            if token
        ]
        if not station_tokens:
            return ""
        station_code = station_tokens[-1]
        return f"{clean(station_code)}_{clean(feeder_name)}"

    @staticmethod
    def _drawing_profile(g_file, settings=None):
        """Classify a G drawing, with an explicit user override when requested.

        AUTO remains topology-first.  SINGLE/MULTI are deliberate operator
        confirmations for the current file set and are recorded in the profile
        so reports/logs retain both the automatic result and the final result.
        """
        profile = FeederDrawingTopologyClassifier(GParser()).classify(g_file)
        auto_type = str(profile.get("drawing_type") or "AMBIGUOUS")
        auto_reason = str(profile.get("classification_reason") or "")
        mode = str((settings or {}).get("feeder_drawing_mode", "AUTO") or "AUTO").upper()
        profile["automatic_drawing_type"] = auto_type
        profile["automatic_classification_reason"] = auto_reason
        profile["drawing_mode"] = mode
        profile["drawing_type_overridden"] = "NO"
        if mode == "SINGLE":
            profile["drawing_type"] = "SINGLE_FEEDER"
            profile["classification_reason"] = "USER_CONFIRMED_SINGLE_FEEDER"
            profile["drawing_type_overridden"] = "YES"
        elif mode == "MULTI":
            profile["drawing_type"] = "MULTI_FEEDER_COMPOSITE"
            profile["classification_reason"] = "USER_CONFIRMED_MULTI_FEEDER_COMPOSITE"
            profile["drawing_type_overridden"] = "YES"
        return profile

    @staticmethod
    def _root_facid(parsed):
        return str(parsed.root.attrib.get("facID", "") or "").strip()

    def _build_single_file_fingerprint(self, db, g_file, profile, settings, log_callback):
        """Create a trusted fingerprint from nearest associated equipment."""
        validator = self._validator(db, settings, log_callback)
        automatic = validator.validate_file(
            g_file,
            drawing_mode=str(
                settings.get("feeder_drawing_mode", "AUTO") or "AUTO"
            ).upper(),
        )
        feeder_ids = sorted({
            int_or_none(report.get("feeder_id"))
            for report in automatic.get("feeder_regions", []) or []
            if int_or_none(report.get("feeder_id")) is not None
        })
        if len(feeder_ids) != 1:
            log_callback(
                f"[{Path(g_file).name}] 单馈线指纹跳过："
                "最近已关联设备未能唯一确定馈线"
            )
            return None
        feeder_id = feeder_ids[0]
        feeder = db.get_feeder_info(feeder_id) or {}
        parsed = profile["parsed"]
        ids = {
            str(obj.xml_id)
            for obj in parsed.objects
            if obj.tag == "FeedLine" and str(obj.xml_id or "").strip()
        }
        if not ids:
            return None
        return {
            "g_file": str(g_file),
            "file_name": Path(g_file).name,
            "feeder_id": feeder_id,
            "feeder_name": str(feeder.get("display_name") or feeder.get("name") or feeder_id),
            "feedline_ids": ids,
            "feedline_count": len(ids),
            "resolution_source": "NEAREST_ASSOCIATED_DEVICE",
        }

    def _audit_current_feedline_owner(self, db, obj, settings, owner_cache):
        row = {
            "object_type": "FeedLine",
            "xml_id": obj.xml_id,
            "ls": str(obj.attrs.get("ls", "") or ""),
            "current_keyid": obj.keyid or "",
            "current_device_id": "",
            "current_table_id": "",
            "current_domain": "",
            "current_db_name": "",
            "current_db_code": "",
            "current_bv_id": "",
            "current_feeder_id": "",
            "current_feeder_name": "",
            "model_linked": "YES" if obj.keyid else "NO",
            "model_link_correct": "",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "status": "WARN",
            "severity": "UNLINKED" if not obj.keyid else "AUDIT",
            "reason": "MODEL_NOT_LINKED" if not obj.keyid else "",
            "x": float(obj.box.cx),
            "y": float(obj.box.cy),
        }
        if not obj.keyid:
            return row
        try:
            keyid = int(obj.keyid)
            verified = db.verify_keyid(keyid)
        except Exception as exc:
            row.update(status="FAIL", severity="KEYID_ERROR", reason=f"KEYID_VERIFY_ERROR: {exc}")
            return row
        did = int_or_none(verified.get("device_id"))
        tab = int_or_none(verified.get("tab_no"))
        dom = int_or_none(verified.get("col_no"))
        row["current_device_id"] = did or ""
        row["current_table_id"] = tab or ""
        row["current_domain"] = dom or ""
        if tab != int(settings.get("section_table_id", 13503)) or dom != int(settings.get("section_domain", 1)):
            row.update(
                status="FAIL", severity="TABLE_DOMAIN_MISMATCH",
                reason=(f"MODEL_TABLE_DOMAIN_MISMATCH: table={tab}, domain={dom}; "
                        f"expected={int(settings.get('section_table_id',13503))}/{int(settings.get('section_domain',1))}")
            )
            return row
        if did is None:
            row.update(status="FAIL", severity="DEVICE_ID_ERROR", reason="KEYID_DEVICE_ID_EMPTY")
            return row
        section = db.get_device_by_id(int(settings.get("section_table_id",13503)), did)
        if not section:
            row.update(status="FAIL", severity="SECTION_NOT_FOUND", reason=f"SECTION_NOT_FOUND: {did}")
            return row
        owner_id = int_or_none(section.get("feeder_id"))
        row["current_db_name"] = section.get("name", "")
        row["current_db_code"] = section.get("code", "")
        row["current_bv_id"] = section.get("bv_id", "")
        row["current_feeder_id"] = owner_id or ""
        if owner_id is not None:
            if owner_id not in owner_cache:
                owner_cache[owner_id] = db.get_feeder_info(owner_id) or {}
            owner = owner_cache[owner_id]
            row["current_feeder_name"] = str(owner.get("display_name") or owner.get("name") or owner_id)
        row.update(status="PASS", severity="AUDIT", reason="CURRENT_LINK_RESOLVED")
        return row

    def _build_composite_regions(self, db, g_file, profile, fingerprints, settings, validator, log_callback):
        """Audit a merged overview drawing without using root facID.

        Exact single-file FeedLine XML-ID fingerprints provide authoritative
        expected feeder identity. Remaining FeedLines are grouped by existing
        FeedLine/ConnectLine topology components and checked for owner consistency.
        Composite regions are audit-only in this release: no automatic rewrite.
        """
        parsed = profile["parsed"]
        feedlines = [obj for obj in parsed.objects if obj.tag == "FeedLine"]
        by_id = {str(obj.xml_id): obj for obj in feedlines}
        composite_ids = set(by_id)

        candidates=[]
        for fp in fingerprints:
            base=set(fp["feedline_ids"])
            overlap=base & composite_ids
            if not base or not overlap:
                continue
            ratio=len(overlap)/len(base)
            if ratio >= 0.95:
                item=dict(fp)
                item["matched_ids"]=overlap
                item["match_ratio"]=ratio
                item["identity_confidence"]="EXACT" if ratio == 1.0 else "HIGH"
                candidates.append(item)
        candidates.sort(key=lambda x:(x["identity_confidence"]!="EXACT", -len(x["matched_ids"]), x["file_name"]))

        # Detect fingerprint overlap. Overlapping fingerprints cannot both be
        # authoritative for the same FeedLine.
        claim_count=Counter()
        for c in candidates:
            for xid in c["matched_ids"]:
                claim_count[xid]+=1

        regions=[]
        claimed=set()
        region_no=0
        owner_cache={}

        def finalize_region(objects, *, expected_id=None, expected_name="", source="UNKNOWN", evidence="", confidence="UNKNOWN"):
            nonlocal region_no
            region_no += 1
            objects=sorted(objects, key=validator._feedline_sort_key)
            rows=[]
            for order,obj in enumerate(objects,1):
                row=self._audit_current_feedline_owner(db,obj,settings,owner_cache)
                row["order_index"]=order
                row["topology_region"]=region_no
                rows.append(row)
            owners=Counter(int_or_none(r.get("current_feeder_id")) for r in rows if int_or_none(r.get("current_feeder_id")) is not None)
            majority_id = owners.most_common(1)[0][0] if owners else None
            majority_count = owners.most_common(1)[0][1] if owners else 0
            distinct_owners=len(owners)
            effective_expected=expected_id
            effective_name=expected_name
            if effective_expected is None and majority_id is not None:
                effective_expected=majority_id
                owner=owner_cache.get(majority_id) or db.get_feeder_info(majority_id) or {}
                owner_cache[majority_id]=owner
                effective_name=str(owner.get("display_name") or owner.get("name") or majority_id)

            anomaly_count=0
            unlinked_count=0
            for row in rows:
                owner=int_or_none(row.get("current_feeder_id"))
                if row.get("model_linked") == "NO":
                    unlinked_count += 1
                    row.update(
                        status="WARN", severity="UNLINKED",
                        model_link_correct="NO" if expected_id is not None else "UNKNOWN",
                        reason=("COMPOSITE_UNLINKED: 区域内 FeedLine 未关联"),
                    )
                    continue
                if row.get("status") == "FAIL":
                    anomaly_count += 1
                    continue
                if expected_id is not None:
                    if owner == expected_id:
                        row.update(status="PASS", severity="PASS", model_link_correct="YES", reason="COMPOSITE_EXPECTED_FEEDER_MATCH")
                    else:
                        anomaly_count += 1
                        sev="FEEDER_MISMATCH" if confidence=="EXACT" else "SUSPECT_FEEDER_MISMATCH"
                        row.update(
                            status="FAIL" if confidence=="EXACT" else "WARN",
                            severity=sev,
                            model_link_correct="NO",
                            reason=(f"{sev}: current_feeder_id={owner or '-'}; expected_feeder_id={expected_id}"),
                        )
                else:
                    if distinct_owners <= 1:
                        row.update(status="PASS", severity="TOPOLOGY_CONSISTENT", model_link_correct="UNKNOWN", reason="TOPOLOGY_OWNER_CONSISTENT_INFERRED")
                    elif owner == majority_id:
                        row.update(status="WARN", severity="TOPOLOGY_MAJORITY", model_link_correct="UNKNOWN", reason=f"TOPOLOGY_CONFLICT_MAJORITY_REFERENCE: majority_feeder_id={majority_id}")
                    else:
                        anomaly_count += 1
                        row.update(status="FAIL", severity="TOPOLOGY_FEEDER_CONFLICT", model_link_correct="NO", reason=f"TOPOLOGY_FEEDER_CONFLICT: current_feeder_id={owner}; majority_feeder_id={majority_id}")

            if expected_id is not None:
                if confidence=="EXACT" and anomaly_count:
                    status,severity="FAIL","EXACT_FINGERPRINT_CONFLICT"
                elif confidence=="HIGH":
                    status,severity="WARN","HIGH_FINGERPRINT_REVIEW"
                elif unlinked_count:
                    status,severity="WARN","EXACT_FINGERPRINT_UNLINKED"
                else:
                    status,severity="PASS","PASS"
            else:
                if distinct_owners > 1:
                    status,severity="FAIL","TOPOLOGY_FEEDER_CONFLICT"
                elif distinct_owners == 1:
                    status,severity="PASS","TOPOLOGY_CONSISTENT_INFERRED"
                else:
                    status,severity="WARN","UNKNOWN"

            report={
                "report_type":"FEEDER",
                "g_file":str(g_file),
                "file_name":Path(g_file).name,
                "drawing_type":"MULTI_FEEDER_COMPOSITE",
                "region_index":region_no,
                "region_identity_confidence":confidence,
                "feeder_resolution_source":source,
                "feeder_resolution_evidence":evidence,
                "fingerprint_match_ratio":round(float((len(objects) and 1.0) if confidence=="EXACT" else 0.0),4),
                "feeder_id":effective_expected or "",
                "feeder_name":effective_name,
                "current_feeder_ids":", ".join(str(x) for x in sorted(owners)),
                "current_feeder_count":distinct_owners,
                "majority_feeder_id":majority_id or "",
                "majority_feeder_count":majority_count,
                "anomaly_count":anomaly_count,
                "feedline_rows":rows,
                "association_eligible":False,
                "status":status,
                "severity":severity,
                "reason":(
                    f"COMPOSITE_AUDIT: identity={source}/{confidence}; "
                    f"FeedLine={len(rows)}; current_feeders={distinct_owners}; "
                    f"anomaly={anomaly_count}; unlinked={unlinked_count}"
                ),
            }
            report["summary"]={
                "feeder_files":1,
                "feeders_resolved":1 if effective_expected else 0,
                "feedlines":len(rows),
                "feedline_pass":sum(1 for r in rows if r.get("status")=="PASS"),
                "feedline_warn":sum(1 for r in rows if r.get("status")=="WARN"),
                "feedline_fail":sum(1 for r in rows if r.get("status")=="FAIL"),
                "association_ready":0,
            }
            return report

        for c in candidates:
            ids={x for x in c["matched_ids"] if claim_count[x]==1}
            if not ids:
                continue
            # Only EXACT uniquely-owned fingerprint regions are authoritative.
            confidence=c["identity_confidence"]
            source="SINGLE_FILE_FINGERPRINT"
            evidence=f"{c['file_name']} | {len(ids)}/{c['feedline_count']} | {confidence}"
            objects=[by_id[x] for x in ids]
            regions.append(finalize_region(
                objects,
                expected_id=c["feeder_id"] if confidence=="EXACT" else None,
                expected_name=c["feeder_name"] if confidence=="EXACT" else "",
                source=source,
                evidence=evidence,
                confidence=confidence,
            ))
            claimed.update(ids)

        # Remaining FeedLines: topology consistency audit only.
        remaining=[obj for obj in feedlines if str(obj.xml_id) not in claimed]
        if remaining:
            topo=validator._feedline_topology_components(parsed,{})
            groups=defaultdict(list)
            for obj in remaining:
                component=(topo.get(str(obj.xml_id)) or {}).get("topology_component")
                groups[component or f"ORPHAN_{obj.xml_id}"].append(obj)
            for comp,objs in sorted(groups.items(), key=lambda item:min(validator._feedline_sort_key(x) for x in item[1])):
                regions.append(finalize_region(
                    objs,
                    source="TOPOLOGY_COMPONENT",
                    evidence=f"component={comp}",
                    confidence="INFERRED",
                ))

        log_callback(
            f"[{Path(g_file).name}] 组合大图审计：Bus={profile['bus_count']}；"
            f"FeedLine={len(feedlines)}；指纹候选={len(candidates)}；区域={len(regions)}。"
        )
        return regions

    @staticmethod
    def _filename_feeder_parts(g_file, station_hint=""):
        """Return (station_hint, feeder_token, base_name) for one G filename.

        Supported examples:
            JED-NTH-ABH-03.sln.pic.g       -> JED-NTH-ABH / 03
            JED-NTH-ABH-AH303.sln.pic.g    -> JED-NTH-ABH / AH303
            ...sln.pic(20260831-143200).g   -> same logical base

        An operator-provided station_hint (ABH or JED-NTH-ABH) overrides only
        the station lookup text; the feeder token is always extracted from
        each file independently, which keeps single-file and batch processing
        on the exact same resolver path.
        """
        name = Path(g_file).name
        base = re.sub(
            r"\.sln\.pic(?:\([^)]*\))?\.g$",
            "",
            name,
            flags=re.I,
        )
        if base == name:
            base = re.sub(r"\.g$", "", name, flags=re.I)

        parts = [x for x in re.split(r"[-_\s]+", base) if x]
        if len(parts) < 2:
            return str(station_hint or "").strip(), "", base

        token = str(parts[-1]).strip()
        # A feeder token must carry a number. This rejects suffixes such as
        # MERGED/TEST while accepting both 03 and AH303.
        if not re.fullmatch(r"(?=.*\d)[A-Za-z0-9]+", token):
            return str(station_hint or "").strip(), "", base

        auto_station = "-".join(parts[:-1]).strip("-_")
        station = str(station_hint or "").strip() or auto_station
        return station, token, base

    @classmethod
    def _station_record_matches(cls, record, station_hint):
        target = cls._normalize_lookup_text(station_hint)
        station = cls._normalize_lookup_text(record.get("station_name", ""))
        if not target or not station:
            return False
        # A short substation name such as ABH may identify a database display
        # station such as JED NTH ABH.  Conversely, a filename/site identifier
        # such as JED-NTH-ABH may need to resolve to the actual 405/substation
        # name ABH.  Candidate generation below tries both forms explicitly;
        # this predicate only decides whether one candidate fits one row.
        return station == target or station.endswith(target) or target.endswith(station)

    @classmethod
    def _station_hint_candidates(cls, station_hint):
        """Return ordered station lookup candidates without guessing feeder data.

        Examples:
            ABH         -> [ABH]
            JED-NTH-ABH -> [JED-NTH-ABH, ABH]

        The full operator/file identifier is always tried first.  The final
        segment is a controlled fallback for deployments where region prefixes
        (JED/NTH/...) are not part of 405/substation.NAME.
        """
        raw = str(station_hint or "").strip().strip("-_")
        if not raw:
            return []
        out = []
        for value in (raw, re.split(r"[-_\s]+", raw)[-1]):
            value = str(value or "").strip()
            norm = cls._normalize_lookup_text(value)
            if value and norm and all(cls._normalize_lookup_text(x) != norm for x in out):
                out.append(value)
        return out

    def _station_feeder_rows(self, db, station_hint, feeder_table_id, feeder_token=""):
        """Resolve feeder rows owned by exactly one station candidate.

        Compatibility/precision order:
          1. Try station+token through the existing Oracle helper.  This keeps
             older deployments where station and feeder text are searchable
             only as one display string (for example JED-CTL-ADF + 16).
          2. Try station-only and resolve numeric/full feeder tokens inside the
             returned station set.  This supports production ABH where the
             filename site is JED-NTH-ABH but 405/substation.NAME is ABH and
             feeder NAME/CODE is AH303.

        The full site identifier is tried before the short final segment.
        """
        attempts = []
        candidates = self._station_hint_candidates(station_hint)
        token_norm = self._normalize_lookup_text(feeder_token)

        def accept_rows(rows, candidate):
            station_rows = [
                dict(row) for row in rows
                if self._station_record_matches(row, candidate)
            ]
            if not station_rows:
                return []
            station_ids = {
                int_or_none(row.get("st_id"))
                for row in station_rows
                if int_or_none(row.get("st_id")) is not None
            }
            if len(station_ids) > 1:
                return []
            return station_rows

        if token_norm:
            for candidate in candidates:
                candidate_norm = self._normalize_lookup_text(candidate)
                attempts.append(f"{candidate}+{feeder_token}")
                rows = db.find_feeders_by_name_hint(
                    f"{candidate_norm}{token_norm}",
                    table_id=feeder_table_id,
                )
                station_rows = accept_rows(rows, candidate)
                if station_rows:
                    return station_rows, candidate, attempts

        for candidate in candidates:
            candidate_norm = self._normalize_lookup_text(candidate)
            attempts.append(candidate)
            rows = db.find_feeders_by_name_hint(
                candidate_norm,
                table_id=feeder_table_id,
            )
            station_rows = accept_rows(rows, candidate)
            if station_rows:
                return station_rows, candidate, attempts
        return [], "", attempts

    @classmethod
    def _feeder_record_tokens(cls, record):
        out = []
        for key in ("name", "code", "graph_name"):
            value = cls._normalize_lookup_text(record.get(key, ""))
            if value and value not in out:
                out.append(value)
        return out

    def _resolve_filename_feeder(
        self,
        db,
        g_file,
        station_hint,
        feeder_table_id,
        log_callback,
    ):
        station, token, base = self._filename_feeder_parts(
            g_file, station_hint
        )
        if not token:
            return None, (
                "FILENAME_FEEDER_TOKEN_NOT_FOUND: "
                f"文件名={Path(g_file).name}；无法提取末尾馈线编号/完整馈线号。"
            )
        if not station:
            return None, (
                "FILENAME_STATION_NOT_FOUND: "
                f"文件名={Path(g_file).name}；无法确定变电站标识。"
            )

        token_norm = self._normalize_lookup_text(token)
        station_rows, matched_station, station_attempts = self._station_feeder_rows(
            db, station, feeder_table_id, token
        )

        if not station_rows:
            log_callback(
                f"[{Path(g_file).name}] 文件名馈线识别失败："
                f"变电站输入/解析值={station!r}；"
                f"已尝试={','.join(station_attempts) or '-'}；"
                "数据库未找到唯一站点下的馈线记录。"
            )
            return None, (
                "FILENAME_STATION_NOT_UNIQUE_OR_NOT_FOUND: "
                f"station={station}; attempts={station_attempts}; station_feeders=0"
            )

        has_letters = bool(re.search(r"[A-Za-z]", token))
        matched = {}
        for row in station_rows:
            business_tokens = self._feeder_record_tokens(row)
            if has_letters:
                ok = token_norm in business_tokens
            else:
                # Numeric short form such as 03 is resolved only inside the
                # already-confirmed station.  Leading zeroes are significant.
                # Example: AH303 endswith 03 -> candidate; AH3 does not.
                ok = any(
                    candidate.endswith(token_norm)
                    and len(candidate) > len(token_norm)
                    for candidate in business_tokens
                ) or token_norm in business_tokens
            if ok:
                rid = int_or_none(row.get("id"))
                if rid is not None:
                    matched[rid] = row

        values = list(matched.values())
        if len(values) != 1:
            candidate_names = ", ".join(
                str(x.get("display_name") or x.get("name") or x.get("id"))
                for x in values[:8]
            )
            log_callback(
                f"[{Path(g_file).name}] 文件名馈线识别失败："
                f"变电站={(matched_station or station)!r}；馈线token={token!r}；"
                f"匹配数={len(values)}；候选={candidate_names or '-'}。"
            )
            return None, (
                "FILENAME_FEEDER_NOT_EXACTLY_ONE: "
                f"station={station}; token={token}; matched={len(values)}"
            )

        record = dict(values[0])
        resolved_name = str(
            record.get("name")
            or record.get("code")
            or record.get("display_name")
            or record.get("id")
        )
        evidence = (
            f"station_input={station}; station_db={matched_station or station}; "
            f"token={token}; resolved={resolved_name}; file={base}"
        )
        record["_resolution_source"] = "FILENAME"
        record["_resolution_evidence"] = evidence
        record["_filename_station"] = matched_station or station
        record["_filename_token"] = token
        log_callback(
            f"[{Path(g_file).name}] 文件名馈线识别通过："
            f"变电站={matched_station or station}；文件馈线号={token} -> "
            f"{record.get('display_name') or record.get('name')} "
            "(13500 站内唯一匹配)"
        )
        return record, ""

    def _resolve_file_feeder_result(
        self,
        db,
        g_file,
        settings,
        log_callback,
    ):
        """Resolve one file's target feeder from exactly the selected source.

        v4.1.38 keeps decoupled FACID / FILENAME / MANUAL.  A populated
        root facID is current-state evidence only unless FACID is selected.
        File-name mode works identically for one file and a whole directory;
        every file independently extracts its own feeder token and is checked
        for one unique database feeder under the resolved station.
        """
        parsed = GParser().parse(g_file)
        requested_mode = str(
            settings.get("feeder_resolution_mode", "FACID") or "FACID"
        ).upper()
        manual = str(
            settings.get("manual_feeder_name", "") or ""
        ).strip()
        station_hint = str(
            settings.get("feeder_station_hint", "") or ""
        ).strip()
        feeder_table_id = int(
            settings.get("feeder_table_id", 13500)
        )

        def enrich(record, source, evidence=""):
            row = dict(record)
            row["_resolution_source"] = source
            row["_resolution_evidence"] = evidence
            return row

        def normalized_display(record):
            return self._normalize_lookup_text(
                record.get("display_name")
                or (
                    f"{record.get('station_name', '')} "
                    f"{record.get('name', '')}"
                )
            )

        def exact_by_text(value, source):
            value = str(value or "").strip()
            if not value:
                return None, f"{source}_EMPTY"

            target = self._normalize_lookup_text(value)
            if not target:
                return None, f"{source}_EMPTY"

            rows = db.find_feeders_by_name_hint(
                target,
                table_id=feeder_table_id,
            )

            matched = {}
            for row in rows:
                db_name = normalized_display(row)
                # Full DB engineering name or an exact business suffix is
                # allowed. Numeric characters are never canonicalized.
                if db_name == target or db_name.endswith(target):
                    rid = int_or_none(row.get("id"))
                    if rid is not None:
                        matched[rid] = row

            values = list(matched.values())
            if len(values) != 1:
                if source == "MANUAL" and len(values) == 0:
                    log_callback(
                        f"[{Path(g_file).name}] 人工输入馈线不存在：{value!r}；"
                        "本次人工输入是绝对目标，不会回退使用当前 facID 或文件名。"
                    )
                    return None, (
                        "MANUAL_FEEDER_NOT_FOUND: "
                        f"输入馈线不存在={value}"
                    )
                if source == "MANUAL":
                    log_callback(
                        f"[{Path(g_file).name}] 人工输入馈线不唯一：{value!r}；"
                        f"数据库精确匹配数={len(values)}；禁止自动选择。"
                    )
                    return None, (
                        "MANUAL_FEEDER_NOT_UNIQUE: "
                        f"输入={value}; matched={len(values)}"
                    )
                log_callback(
                    f"[{Path(g_file).name}] 馈线精准匹配失败："
                    f"{source}={value!r}；精确匹配数={len(values)}。"
                    "AJWD 6 与 AJWD 06 按不同馈线处理。"
                )
                return None, (
                    f"{source}_NOT_EXACTLY_ONE: "
                    f"输入={value}; matched={len(values)}"
                )

            record = values[0]
            log_callback(
                f"[{Path(g_file).name}] 馈线精准匹配通过："
                f"{source}={value!r} -> "
                f"{record.get('display_name') or record.get('name')} "
                "(13500 唯一精准匹配)"
            )
            return enrich(record, source, value), ""

        raw_facid = str(
            parsed.root.attrib.get("facID", "") or ""
        ).strip()

        if requested_mode == "FACID":
            if not raw_facid:
                return None, (
                    "FACID_EMPTY: 当前选择仅使用 G 根节点 facID，"
                    "但该文件 facID 为空。"
                )
            try:
                fac_id = int(raw_facid)
            except Exception:
                return None, f"FACID_INVALID: facID={raw_facid!r}"
            if fac_id <= 0:
                return None, f"FACID_INVALID: facID={raw_facid!r}"
            record = db.get_feeder_info(
                fac_id,
                table_id=feeder_table_id,
            )
            if not record:
                return None, (
                    f"FACID_NOT_FOUND_IN_DMS_FEEDER_DEVICE: {fac_id}"
                )
            log_callback(
                f"[{Path(g_file).name}] 使用 G.facID={fac_id} -> "
                f"{record.get('display_name') or record.get('name')} "
                "(FACID / 13500 精确ID匹配)"
            )
            return enrich(record, "FACID_FORCED", str(fac_id)), ""

        if requested_mode == "FILENAME":
            record, error = self._resolve_filename_feeder(
                db,
                g_file,
                station_hint,
                feeder_table_id,
                log_callback,
            )
        elif requested_mode == "MANUAL":
            record, error = exact_by_text(manual, "MANUAL")
        else:
            return None, f"UNKNOWN_FEEDER_RESOLUTION_MODE: {requested_mode}"

        if not record:
            return None, error

        target_id = int_or_none(record.get("id"))
        allow_override = bool(settings.get("allow_feeder_override", False))
        if raw_facid and target_id is not None and raw_facid != str(target_id):
            if allow_override:
                log_callback(
                    f"[{Path(g_file).name}] 当前 G.facID={raw_facid} 与本次"
                    f"{requested_mode}目标 FEEDER_ID={target_id} 不同；"
                    "已启用人工覆盖，将在模型关联时允许覆盖根 facID 和错误馈线段关联。"
                )
            else:
                log_callback(
                    f"[{Path(g_file).name}] 当前 G.facID={raw_facid} 与本次"
                    f"{requested_mode}目标 FEEDER_ID={target_id} 不同；"
                    "未启用人工覆盖，现有跨馈线关系将保持阻断。"
                )
        return record, ""

    def _resolve_file_feeder(
        self,
        db,
        g_file,
        settings,
        log_callback,
    ):
        """Compatibility helper: return only the resolved feeder record."""
        record, _error = self._resolve_file_feeder_result(
            db,
            g_file,
            settings,
            log_callback,
        )
        return record

    @staticmethod
    def _unresolved_file_report(g_file, reason):
        parsed = GParser().parse(g_file)
        feedlines = [
            obj for obj in parsed.objects
            if obj.tag == "FeedLine"
        ]
        rows = []
        for idx, obj in enumerate(
            sorted(
                feedlines,
                key=lambda item: (
                    round(item.box.y, 6),
                    round(item.box.x, 6),
                    item.xml_index,
                ),
            ),
            start=1,
        ):
            rows.append({
                "order_index": idx,
                "object_type": "FeedLine",
                "xml_id": obj.xml_id,
                "ls": str(obj.attrs.get("ls", "") or ""),
                "current_keyid": obj.keyid,
                "association_ready": "NO",
                "writeback_needed": "NO",
                "status": "FAIL",
                "severity": "BLOCKED",
                "reason": reason,
            })
        report = {
            "report_type": "FEEDER",
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "drawing_type": "SINGLE_FEEDER",
            "region_index": 1,
            "region_assignment_method": "FACID/FILENAME/MANUAL",
            "feeder_hint": "",
            "feeder_hint_source": "UNRESOLVED",
            "feeder_resolution_source": "UNRESOLVED",
            "feeder_resolution_evidence": "",
            "station_name": "",
            "station_bv_id": "",
            "feeder_records": [],
            "feeder_id": "",
            "feeder_name": "",
            "feedline_rows": rows,
            "association_eligible": False,
            "status": "FAIL",
            "severity": "BLOCKED",
            "reason": reason,
        }
        report["summary"] = FeederValidator._summary(report)
        return {
            "report_type": "FEEDER_FILE",
            "g_file": str(parsed.path),
            "file_name": parsed.path.name,
            "drawing_type": "SINGLE_FEEDER",
            "feeder_regions": [report],
            "status": "FAIL",
        }

    def _prepare_single_feeder_rows(self, report, g_file, log_callback):
        """Prepare FeedLine rows without using topology to validate sections.

        Existing FeedLine links are never compared with SEC001/SEC002 order.
        Geometry order is used only when the whole single-feeder drawing is
        brand-new (all FeedLines have no KeyID), where it provides the initial
        deterministic allocation order.  Otherwise existing database ownership
        and Domain are the only section-link validation facts.
        """
        for row in report.get("feedline_rows", []) or []:
            original = str(row.get("ls", "") or "").strip()
            normalized, section_type, changed, valid = self._normalize_feedline_ls(original)
            row["ls_original"] = original
            row["ls_normalized"] = normalized
            row["ls_normalization_needed"] = "YES" if changed else "NO"
            row["planned_section_type"] = section_type if section_type is not None else ""
            if changed:
                row["ls"] = normalized
            # Explicitly remove v4.1.1 topology-name fields from the active
            # validation path. Older reports/tests may still know the keys,
            # but they are not used to decide section identity anymore.
            row.pop("topology_section_name", None)
            row.pop("topology_status", None)
            row.pop("topology_endpoints", None)
            if not valid:
                row.update(
                    status="FAIL",
                    severity="ERROR",
                    association_ready="NO",
                    writeback_needed="NO",
                    reason=f"INVALID_FEEDLINE_LS: ls={original!r}",
                )
        log_callback(
            f"[{Path(g_file).name}] 馈线段校验仅检查同馈线归属与Domain；"
            "已有正确关联不检查SEC/几何顺序。未关联或失效关联按当前馈线"
            "未占用数据库记录顺序从小到大分配；数量不足时只创建实际短缺数量；"
            "ls>2 仍按2参与建库。"
        )
        return report

    # Backward-compatible private alias for callers/tests from v4.1.1.
    # The method no longer performs topology-based naming.
    def _annotate_single_feeder_topology(self, report, g_file, log_callback):
        return self._prepare_single_feeder_rows(report, g_file, log_callback)

    def _augment_section_creation_plan(
        self,
        db,
        report,
        settings,
        log_callback,
    ):
        """Plan only genuinely missing feeder sections.

        v4.1.14 keeps validation limited to same-feeder ownership + Domain.
        Existing correct links are locked and never reordered.  Any remaining
        unlinked/stale FeedLines may consume the current feeder's unused 13503
        rows in deterministic DB sequence; if those rows are insufficient, the
        planner creates only the genuine shortage.

        A completely new drawing still uses the G FeedLine order for the first
        allocation.  Partial/existing drawings use that order only to decide
        which unresolved FeedLine receives the next free DB record; it is never
        used to challenge an already-correct association.
        """
        report["section_create_plan"] = []
        # Makkah fixed rule: once any one feeder in the current ring drawing
        # is confirmed, every missing 13503 section required by this G file
        # must be planned for creation.  This is not operator-optional.
        feeder_id = int_or_none(report.get("feeder_id"))
        if feeder_id is None:
            return report

        feeder = db.get_feeder_info(
            feeder_id,
            table_id=int(settings.get("feeder_table_id", 13500)),
        ) or {}

        # A feeder-only drawing (zero FeedLine) is a valid model.
        if not (report.get("feedline_rows") or []):
            report["section_prefix"] = self._section_prefix(feeder, [])
            report["section_station_name"] = feeder.get("station_name", "")
            report["section_create_plan"] = []
            report["summary"] = FeederValidator._summary(report)
            return report

        section_table_id = int(settings.get("section_table_id", 13503))
        expected_domain = int(settings.get("section_domain", 1))
        _, section_rows = db.get_sections_by_feeder_id(
            feeder_id,
            table_id=section_table_id,
        )
        prefix = self._section_prefix(feeder, section_rows)
        station_id = int_or_none(feeder.get("st_id"))
        voltage = (
            db.get_preferred_feeder_section_voltage(station_id)
            if station_id is not None else None
        ) or {}
        bv_id = voltage.get("bv_id")
        nominal_voltage = voltage.get("nomvol")
        if not prefix or bv_id in (None, ""):
            report["section_create_plan_error"] = (
                "无法确定馈线段命名前缀，或无法从 feeder.ST_ID -> "
                "402/voltagelevel -> 401/basevoltage 找到允许的 "
                "110/33/13.8kV 电压等级，禁止自动创建馈线段。"
            )
            return report

        section_by_id = {
            int(row["id"]): row
            for row in section_rows
            if int_or_none(row.get("id")) is not None
        }
        existing_names = {
            str(row.get("name") or "").strip().upper()
            for row in section_rows
            if str(row.get("name") or "").strip()
        }
        planned_names = set()
        assignment_mode = str(
            report.get("section_assignment_mode") or "NEW_DRAWING_ORDER"
        ).upper()

        # Sections already held by validated G links or already allocated by
        # FeederValidator are unavailable to any other FeedLine.
        occupied_ids = set()
        for existing_row in report.get("feedline_rows", []) or []:
            candidate_id = int_or_none(
                existing_row.get("assigned_device_id")
                or existing_row.get("current_device_id")
            )
            if candidate_id is None:
                continue
            if (
                existing_row.get("model_link_correct") == "YES"
                or existing_row.get("relink_same_section") == "YES"
                or (
                    existing_row.get("association_ready") == "YES"
                    and not str(existing_row.get("reason", "")).startswith("SECTION_NOT_AVAILABLE")
                )
            ):
                occupied_ids.add(candidate_id)

        def preserve_existing_target(row, device_id):
            """Keep the exact DB row already validated/allocated upstream."""
            device_id = int_or_none(device_id)
            if device_id is None:
                return False
            target = section_by_id.get(device_id)
            if not target:
                return False
            if int_or_none(target.get("feeder_id")) != feeder_id:
                return False

            target_name = str(
                target.get("name")
                or row.get("assigned_section_name")
                or row.get("current_db_name")
                or ""
            ).strip()
            row["db_create_needed"] = "NO"
            row["assigned_device_id"] = device_id
            row["assigned_section_name"] = target_name
            row["planned_section_name"] = target_name
            row["assigned_bv_id"] = target.get("bv_id", row.get("assigned_bv_id", bv_id))
            return True

        def first_unused_create_name():
            suffix = 1
            while True:
                candidate = f"{prefix}_SEC{suffix:03d}"
                ckey = candidate.upper()
                if ckey not in existing_names and ckey not in planned_names:
                    return candidate
                suffix += 1

        def next_create_name(order_index):
            # Only a completely new drawing may derive SEC suffix from the G
            # geometry order.  Existing/partial models use the first unused
            # suffix so creation cannot imply a positional reorder.
            if assignment_mode != "NEW_DRAWING_ORDER":
                return first_unused_create_name()

            target_name = f"{prefix}_SEC{order_index:03d}"
            key = target_name.upper()
            if key not in existing_names and key not in planned_names:
                return target_name
            return first_unused_create_name()

        plans = []
        for row in report.get("feedline_rows", []) or []:
            order_index = int(row.get("order_index") or 0)
            if order_index <= 0:
                continue

            section_type = self._section_type_from_ls(row.get("ls", ""))
            row["planned_section_type"] = (
                section_type if section_type is not None else ""
            )

            current_owner = int_or_none(row.get("current_feeder_id"))
            if (
                row.get("model_linked") == "YES"
                and current_owner is not None
                and current_owner != feeder_id
                and not bool(settings.get("allow_feeder_override", False))
            ):
                row.update(
                    status="FAIL",
                    severity="FEEDER_MISMATCH",
                    association_ready="NO",
                    writeback_needed="NO",
                    model_link_correct="NO",
                    db_create_needed="NO",
                    reason=(
                        "CURRENT_MODEL_FEEDER_MISMATCH: "
                        f"FeedLine XML={row.get('xml_id') or '-'} 当前关联"
                        f"feeder_id={current_owner}，但本图期望feeder_id={feeder_id}；"
                        "未启用人工覆盖，禁止自动跨馈线重关联。"
                    ),
                )
                continue

            # v4.1.12: the validator is the authority for an already-correct
            # link. Geometry/SEC order must NOT turn it into a RELINK.
            if row.get("model_link_correct") == "YES":
                if preserve_existing_target(row, row.get("current_device_id") or row.get("assigned_device_id")):
                    row.update(
                        status="PASS",
                        severity="PASS",
                        association_ready="YES",
                        writeback_needed="NO",
                        reason="MODEL_ALREADY_LINKED_CORRECT",
                    )
                    continue

            # Domain-only repair also preserves the same 13503 device_id.
            if row.get("relink_same_section") == "YES":
                if preserve_existing_target(row, row.get("current_device_id") or row.get("assigned_device_id")):
                    row["db_create_needed"] = "NO"
                    continue

            # Unlinked/stale rows may already have been assigned one of the
            # current feeder's genuinely free DB sections by FeederValidator.
            # Preserve that exact validated allocation; do not replace it by a
            # positional SEC target.
            if (
                row.get("association_ready") == "YES"
                and int_or_none(row.get("assigned_device_id")) is not None
                and not str(row.get("reason", "")).startswith("SECTION_NOT_AVAILABLE")
            ):
                if preserve_existing_target(row, row.get("assigned_device_id")):
                    continue

            # Hard validation errors (wrong table, duplicate link, invalid
            # KeyID, etc.) are not converted into create operations.
            if not str(row.get("reason", "")).startswith("SECTION_NOT_AVAILABLE"):
                row.setdefault("db_create_needed", "NO")
                continue

            if section_type is None:
                row.update(
                    status="FAIL",
                    severity="ERROR",
                    association_ready="NO",
                    writeback_needed="NO",
                    db_create_needed="NO",
                    reason=(
                        f"UNKNOWN_FEEDLINE_LS: ls={row.get('ls')!r}; "
                        "允许值：2->0, 1->1, 空->3"
                    ),
                )
                continue

            # Compatibility path: direct callers may present a row as
            # SECTION_NOT_AVAILABLE before FeederValidator has allocated the
            # exact positional SEC row. If that row exists and is genuinely
            # free, use it rather than creating a duplicate. Never steal a
            # section already occupied by another valid G association.
            positional_name = f"{prefix}_SEC{order_index:03d}"
            positional_matches = (
                [
                    sec for sec in section_rows
                    if str(sec.get("name") or "").strip().upper() == positional_name.upper()
                ]
                if assignment_mode == "NEW_DRAWING_ORDER"
                else []
            )
            free_positional = [
                sec for sec in positional_matches
                if int_or_none(sec.get("id")) not in occupied_ids
            ]
            if len(positional_matches) > 1:
                row.update(
                    status="FAIL",
                    severity="ERROR",
                    association_ready="NO",
                    writeback_needed="NO",
                    db_create_needed="NO",
                    reason=(
                        f"SECTION_NAME_DUPLICATE: {positional_name} "
                        f"数据库存在{len(positional_matches)}条"
                    ),
                )
                continue
            if len(free_positional) == 1:
                target = free_positional[0]
                target_id = int_or_none(target.get("id"))
                if target_id is not None:
                    expected = FeederValidator._make_expected_keyid(
                        target_id, expected_domain
                    )
                    row["planned_section_name"] = positional_name
                    row["assigned_section_name"] = positional_name
                    row["assigned_device_id"] = target_id
                    row["assigned_bv_id"] = target.get("bv_id", bv_id)
                    row["expected_keyid"] = expected
                    row["expected_keyid_verified"] = "YES"
                    row["db_create_needed"] = "NO"
                    row["association_ready"] = "YES"
                    row["writeback_needed"] = "YES"
                    row["model_link_correct"] = ""
                    if row.get("model_linked") == "YES":
                        row["status"] = "WARN"
                        row["severity"] = "RELINK"
                        row["reason"] = "STALE_SECTION_RELINK_READY: 已匹配当前馈线现有未占用馈线段"
                    else:
                        row["status"] = "WARN"
                        row["severity"] = "UNLINKED"
                        row["reason"] = "MODEL_NOT_LINKED_READY_FOR_ASSOCIATION"
                    occupied_ids.add(target_id)
                    continue

            # Only a genuine shortage becomes CREATE_PENDING. Keep the old
            # SECnnn naming convention, but never collide with an existing
            # same-feeder section that is already validly associated.
            target_name = next_create_name(order_index)
            planned_names.add(target_name.upper())
            row["planned_section_name"] = target_name
            plan = {
                "name": target_name,
                "bv_id": int(bv_id),
                "section_type": int(section_type),
                "order_index": order_index,
                "xml_id": row.get("xml_id", ""),
            }
            plans.append(plan)
            row["db_create_needed"] = "YES"
            row["assigned_section_name"] = target_name
            row["assigned_bv_id"] = int(bv_id)
            row.update(
                status="WARN",
                severity="CREATE_PENDING",
                association_ready="YES",
                writeback_needed="YES",
                reason=(
                    f"DB_SECTION_CREATE_PENDING: {target_name}; "
                    f"ls={row.get('ls')!r} -> SECTION_TYPE={section_type}"
                ),
            )

        report["section_prefix"] = prefix
        report["section_station_name"] = feeder.get("station_name", "")
        report["section_station_bv_id"] = bv_id
        report["section_nominal_voltage_kv"] = nominal_voltage
        report["section_voltagelevel_name"] = voltage.get(
            "voltagelevel_name", ""
        )
        report["section_create_plan"] = plans
        if plans:
            log_callback(
                f"[{Path(report.get('g_file', '')).name}] "
                f"馈线={report.get('feeder_name') or feeder.get('display_name')}; "
                f"数据库缺失馈线段计划={len(plans)}；"
                f"命名规则={prefix}_SECnnn；"
                f"创建电压等级={nominal_voltage}kV；BV_ID={bv_id}"
            )
        report["summary"] = FeederValidator._summary(report)
        return report

    @classmethod
    def _ring_filename_feeder_labels(cls, g_file):
        """Return feeder-like labels encoded by *this* Makkah ring filename.

        Ring drawings commonly contain several feeder tokens in one filename,
        for example ``...-GVCM-04-MOB3ARF-06-ARF3-21.sln.pic.g``.  Makkah
        only needs one database-unique feeder from the current drawing, so
        these tokens are valid fallback evidence when a main-station Bay frame
        cannot be recognised.
        """
        name = Path(g_file).name
        stem = re.sub(r"\.sln\.pic(?:\([^)]*\))?\.g$", "", name, flags=re.I)
        stem = re.sub(r"\.g$", "", stem, flags=re.I)
        out = []
        seen = set()
        for match in re.finditer(
            r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{1,15})[-_](\d{1,3})(?!\d)",
            stem,
        ):
            prefix = str(match.group(1) or "").upper()
            if prefix in {"MAK", "XXX", "PART", "PIC", "SLN"}:
                continue
            label = f"{prefix}-{match.group(2)}"
            key = cls._normalize_lookup_text(label)
            if key and key not in seen:
                seen.add(key)
                out.append(label)
        return out

    def _unique_ring_feeder_by_label(self, db, label, feeder_table_id):
        """Resolve one exact feeder label to exactly one 13500 record."""
        try:
            rows = db.find_feeders_by_name_hint(label, table_id=feeder_table_id)
        except Exception:
            return None
        unique = {}
        normalized_label = self._normalize_lookup_text(label)
        for row in rows:
            rid = int_or_none(row.get("id"))
            if rid is None:
                continue
            display = self._normalize_lookup_text(
                row.get("display_name")
                or f"{row.get('station_name','')} {row.get('name','')}"
            )
            business = {
                self._normalize_lookup_text(row.get("name", "")),
                self._normalize_lookup_text(row.get("code", "")),
                self._normalize_lookup_text(row.get("graph_name", "")),
            }
            if (
                display == normalized_label
                or display.endswith(normalized_label)
                or normalized_label in business
            ):
                unique[rid] = row
        if len(unique) != 1:
            return None
        return dict(next(iter(unique.values())))

    def _resolve_any_ring_feeder(self, db, g_file, settings, log_callback):
        """Resolve all strict main-network feeders and keep a stable fallback.

        The authoritative Makkah chain is:
        CBreaker frame -> nearest frame title -> substation.NAME ->
        substation.ID -> dms_feeder_device.ST_ID -> feeder NAME/CODE.
        """
        feeder_table_id = int(settings.get("feeder_table_id", 13500))
        candidates = discover_makkah_ring_feeders(
            db,
            g_file,
            feeder_table_id=feeder_table_id,
            station_table_id=405,
            log_callback=None,
        )
        if not candidates:
            return None, []

        selected = dict(candidates[0])
        log_callback(
            f"[{Path(g_file).name}] 麦加馈线模型已确认主网馈线={len(candidates)} 条；"
            f"首条={selected.get('_ring_label') or selected.get('display_name') or selected.get('name')} -> "
            f"FEEDER_ID={selected.get('id')}；ST_ID={selected.get('st_id')}。"
            "下一步将按 FeedLine 拓扑逐条确定所属馈线；复用和新建 13503 都限定在"
            "该 FeedLine 自己的所属馈线内，不再使用跨馈线统一资源池。"
        )
        return selected, [dict(row) for row in candidates]

    @staticmethod
    def _ring_candidate_display(feeder):
        return str(
            feeder.get("_ring_label")
            or feeder.get("display_name")
            or feeder.get("name")
            or feeder.get("id")
            or ""
        ).strip()

    def _validate_makkah_ring_feeder_pool(
        self,
        db,
        g_file,
        candidates,
        settings,
        log_callback,
    ):
        """Validate a Makkah ring drawing using per-FeedLine topology ownership.

        v4.1.124 rule:
        - first reuse the independent ``FeedLine -> feeder`` topology analyser;
        - a FeedLine may be associated only when topology resolves exactly one
          main-network feeder label;
        - that label must map to exactly one database-confirmed 13500 feeder;
        - existing/free 13503 rows are consumed only from that exact feeder;
        - genuine shortages are created under that exact feeder, never under a
          drawing-wide fallback feeder and never from a cross-feeder pool.

        Conflict/unresolved topology is intentionally blocked instead of being
        guessed. Existing links are preserved only when their 13503.FEEDER_ID
        matches the topology-resolved feeder (Domain-only errors keep the same
        13503.ID and only repair the KeyID domain).
        """
        g_file = Path(g_file)
        parsed = GParser().parse(g_file)
        validator = self._validator(db, settings, log_callback)
        section_table_id = int(settings.get("section_table_id", 13503))
        expected_domain = int(settings.get("section_domain", 1))
        feeder_table_id = int(settings.get("feeder_table_id", 13500))

        candidate_rows = [dict(item) for item in (candidates or [])]
        candidate_by_id = {}
        candidate_order = []
        candidate_ids_by_label = defaultdict(set)
        for feeder in candidate_rows:
            feeder_id = int_or_none(feeder.get("id"))
            if feeder_id is None:
                continue
            if feeder_id not in candidate_by_id:
                candidate_by_id[feeder_id] = feeder
                candidate_order.append(feeder_id)
            # The topology analyser and ring discovery both use the exact Bay
            # title.  Keep a few deterministic aliases for older/test records,
            # but never fuzzy-match a topology label to a different feeder.
            aliases = [
                feeder.get("_ring_label"),
                feeder.get("display_name"),
            ]
            station_name = str(feeder.get("station_name") or "").strip()
            feeder_name = str(feeder.get("name") or "").strip()
            feeder_code = str(feeder.get("code") or "").strip()
            if station_name and feeder_name:
                aliases.append(f"{station_name}-{feeder_name}")
            if station_name and feeder_code:
                aliases.append(f"{station_name}-{feeder_code}")
            for alias in aliases:
                normalized = self._normalize_lookup_text(alias)
                if normalized:
                    candidate_ids_by_label[normalized].add(feeder_id)

        feedlines = sorted(
            [obj for obj in parsed.objects if obj.tag == "FeedLine"],
            key=validator._feedline_sort_key,
        )
        selected = candidate_rows[0] if candidate_rows else {}
        selected_id = int_or_none(selected.get("id"))
        selected_name = self._ring_candidate_display(selected)

        try:
            topology = analyze_feedline_feeder_topology_file(g_file)
        except Exception as exc:
            topology = {
                "summary": {
                    "feedline_count": len(feedlines),
                    "confirmed_count": 0,
                    "conflict_count": 0,
                    "unresolved_count": len(feedlines),
                    "source_feeder_labels": [],
                    "nop_boundary_count": 0,
                    "strict_geometry_repair_count": 0,
                },
                "feedline_rows": [],
            }
            topology_error = str(exc)
        else:
            topology_error = ""

        topology_rows = {
            str(row.get("feedline_xml_id") or ""): dict(row)
            for row in (topology.get("feedline_rows") or [])
            if str(row.get("feedline_xml_id") or "")
        }
        topo_summary = dict(topology.get("summary") or {})

        report = {
            "report_type": "FEEDER",
            "g_file": str(g_file),
            "file_name": g_file.name,
            "drawing_type": "MAKKAH_RING_MULTI_FEEDER_TOPOLOGY",
            "drawing_mode": "MAKKAH_RING",
            "region_index": 1,
            "region_assignment_method": "FEEDLINE_TOPOLOGY_OWNER",
            "feeder_resolution_source": "FEEDLINE_TOPOLOGY_OWNER",
            "feeder_resolution_evidence": (
                "复用图形工作区馈线段所属馈线分析：主网CBreaker + link/node_area + "
                "严格几何补链 + 红色NOP支路级断点；每条FeedLine只使用唯一可达馈线。"
            ),
            "feeder_records": candidate_rows,
            # Legacy summary fields keep a deterministic first feeder only;
            # each FeedLine carries its real target in assigned_feeder_*.
            "feeder_id": selected_id or "",
            "feeder_name": selected_name,
            "ring_candidate_feeder_count": len(candidate_order),
            "ring_candidate_feeder_ids": ", ".join(str(x) for x in candidate_order),
            "ring_candidate_feeder_names": ", ".join(
                self._ring_candidate_display(candidate_by_id[x]) for x in candidate_order
            ),
            "ring_candidate_feeders": [
                {
                    "feeder_id": feeder_id,
                    "feeder_name": self._ring_candidate_display(candidate_by_id[feeder_id]),
                    "station_name": candidate_by_id[feeder_id].get("station_name", ""),
                    "st_id": candidate_by_id[feeder_id].get("st_id", ""),
                    "db_code": candidate_by_id[feeder_id].get("code", ""),
                    "db_name": candidate_by_id[feeder_id].get("name", ""),
                }
                for feeder_id in candidate_order
            ],
            "main_source_feeder_count": len(topo_summary.get("source_feeder_labels") or []),
            "main_source_feeder_ids": ", ".join(str(x) for x in candidate_order),
            "nop_boundary_count": int(topo_summary.get("nop_boundary_count") or 0),
            "strict_geometry_repair_count": int(topo_summary.get("strict_geometry_repair_count") or 0),
            "feedline_topology_confirmed_count": int(topo_summary.get("confirmed_count") or 0),
            "feedline_topology_conflict_count": int(topo_summary.get("conflict_count") or 0),
            "feedline_topology_unresolved_count": int(topo_summary.get("unresolved_count") or 0),
            "feedline_rows": [],
            "section_create_plan": [],
            "section_create_targets": [],
            "association_eligible": bool(candidate_order) and not topology_error,
            "status": "PASS" if candidate_order and not topology_error else "FAIL",
            "severity": "PASS" if candidate_order and not topology_error else "BLOCKED",
            "reason": "",
            "feeder_root_writeback_needed": "NO",
            "feeder_root_current_facid": self._root_facid(parsed),
            "feeder_root_expected_facid": "",
        }

        if not candidate_order or topology_error:
            if topology_error:
                block_reason = f"FEEDLINE_TOPOLOGY_ANALYSIS_FAILED: {topology_error}"
            else:
                block_reason = "MAKKAH_RING_FEEDER_NOT_FOUND"
            report.update(
                association_eligible=False,
                status="FAIL",
                severity="BLOCKED",
                reason=block_reason,
            )
            for order, obj in enumerate(feedlines, start=1):
                row = validator._new_row(obj, order)
                row.update(
                    status="FAIL", severity="BLOCKED",
                    association_ready="NO", writeback_needed="NO",
                    db_create_needed="NO", reason=block_reason,
                )
                report["feedline_rows"].append(row)
            report["summary"] = FeederValidator._summary(report)
            return report

        # Query each database-confirmed feeder independently. There is no
        # cross-feeder allocation pool in v4.1.124.
        sections_by_feeder = {}
        total_section_count = 0
        for feeder_id in candidate_order:
            try:
                _, db_rows = db.get_sections_by_feeder_id(
                    feeder_id, table_id=section_table_id
                )
            except TypeError:
                _, db_rows = db.get_sections_by_feeder_id(feeder_id)
            db_rows = [dict(row) for row in (db_rows or [])]
            db_rows.sort(key=natural_section_key)
            for section in db_rows:
                section.setdefault("feeder_id", feeder_id)
            sections_by_feeder[feeder_id] = db_rows
            total_section_count += len(db_rows)
        report["available_count"] = total_section_count

        owner_cache = {}
        current_meta = {}
        valid_usage = defaultdict(list)
        for obj in feedlines:
            meta = {
                "device_id": None, "table_id": None, "domain": None,
                "section": None, "owner_id": None, "verify_error": "",
            }
            if obj.keyid:
                try:
                    verified = db.verify_keyid(int(obj.keyid))
                    did = int_or_none(verified.get("device_id"))
                    tab = int_or_none(verified.get("tab_no"))
                    dom = int_or_none(verified.get("col_no"))
                    section = None
                    owner_id = None
                    if did is not None and tab == section_table_id:
                        section = db.get_device_by_id(section_table_id, did)
                        if section:
                            section = dict(section)
                            owner_id = int_or_none(section.get("feeder_id"))
                    meta.update({
                        "device_id": did, "table_id": tab, "domain": dom,
                        "section": section, "owner_id": owner_id,
                    })
                    if (
                        section is not None
                        and owner_id in candidate_by_id
                        and tab == section_table_id
                        and did is not None
                    ):
                        valid_usage[did].append(str(obj.xml_id))
                except Exception as exc:
                    meta["verify_error"] = str(exc)
            current_meta[str(obj.xml_id)] = meta

        duplicate_ids = {did for did, ids in valid_usage.items() if len(ids) > 1}
        used_ids_by_feeder = defaultdict(set)
        pending_by_feeder = defaultdict(list)
        rows = []

        def feeder_display_name(feeder_id):
            if feeder_id in candidate_by_id:
                return self._ring_candidate_display(candidate_by_id[feeder_id])
            if feeder_id is None:
                return ""
            if feeder_id not in owner_cache:
                try:
                    owner_cache[feeder_id] = db.get_feeder_info(
                        feeder_id, table_id=feeder_table_id
                    ) or {}
                except TypeError:
                    owner_cache[feeder_id] = db.get_feeder_info(feeder_id) or {}
                except Exception:
                    owner_cache[feeder_id] = {}
            owner = owner_cache[feeder_id]
            return str(owner.get("display_name") or owner.get("name") or feeder_id)

        for order, obj in enumerate(feedlines, start=1):
            row = validator._new_row(obj, order)
            original_ls = str(obj.attrs.get("ls", "") or "").strip()
            normalized_ls, section_type, ls_changed, ls_valid = self._normalize_feedline_ls(original_ls)
            topo = topology_rows.get(str(obj.xml_id), {})
            topo_status = str(topo.get("status") or "UNRESOLVED").upper()
            topo_primary = str(topo.get("primary_feeder") or "").strip()
            topo_candidates = str(topo.get("candidate_feeders") or "").strip()
            topo_reason = str(topo.get("reason") or "").strip()
            row.update({
                "ls_original": original_ls,
                "ls": normalized_ls if ls_changed else original_ls,
                "ls_normalized": normalized_ls,
                "ls_normalization_needed": "YES" if ls_changed else "NO",
                "planned_section_type": section_type if section_type is not None else "",
                "ring_valid_feeder_ids": report["ring_candidate_feeder_ids"],
                "ownership_status": topo_status,
                "ownership_method": "FEEDLINE_TOPOLOGY_OWNER",
                "topology_primary_feeder": topo_primary,
                "topology_candidate_feeders": topo_candidates,
                "ownership_evidence": topo_reason,
            })

            meta = current_meta.get(str(obj.xml_id), {})
            did = int_or_none(meta.get("device_id"))
            tab = int_or_none(meta.get("table_id"))
            dom = int_or_none(meta.get("domain"))
            section = meta.get("section")
            owner_id = int_or_none(meta.get("owner_id"))
            row["current_device_id"] = did or ""
            row["current_table_id"] = tab or ""
            row["current_domain"] = dom if dom is not None else ""
            row["current_feeder_id"] = owner_id or ""
            row["current_feeder_name"] = feeder_display_name(owner_id)
            if section:
                row["current_db_name"] = str(section.get("name") or "")
                row["current_db_code"] = str(section.get("code") or "")
                row["current_bv_id"] = section.get("bv_id", "")

            if not ls_valid:
                row.update(
                    status="FAIL", severity="ERROR", model_link_correct="NO",
                    association_ready="NO", writeback_needed="NO",
                    db_create_needed="NO",
                    reason=f"INVALID_FEEDLINE_LS: ls={original_ls!r}",
                )
                rows.append(row)
                continue

            if topo_status != "CONFIRMED" or not topo_primary:
                row.update(
                    status="FAIL",
                    severity="TOPOLOGY_CONFLICT" if topo_status == "CONFLICT" else "TOPOLOGY_UNRESOLVED",
                    model_link_correct="",
                    association_ready="NO",
                    writeback_needed="NO",
                    db_create_needed="NO",
                    reason=(
                        f"FEEDLINE_TOPOLOGY_{topo_status}: "
                        f"{topo_reason or '无法唯一确定所属馈线，禁止自动关联/建库。'}"
                    ),
                )
                rows.append(row)
                continue

            target_ids = candidate_ids_by_label.get(
                self._normalize_lookup_text(topo_primary), set()
            )
            if len(target_ids) != 1:
                row.update(
                    status="FAIL", severity="TOPOLOGY_FEEDER_DB_NOT_UNIQUE",
                    model_link_correct="",
                    association_ready="NO", writeback_needed="NO",
                    db_create_needed="NO",
                    reason=(
                        "TOPOLOGY_FEEDER_DB_NOT_UNIQUE: "
                        f"图形所属馈线={topo_primary!r}；数据库确认匹配数={len(target_ids)}。"
                    ),
                )
                rows.append(row)
                continue

            target_feeder_id = next(iter(target_ids))
            row["assigned_feeder_id"] = target_feeder_id
            row["assigned_feeder_name"] = feeder_display_name(target_feeder_id)
            row["topology_target_feeder_id"] = target_feeder_id

            valid_target_owner = (
                section is not None
                and owner_id == target_feeder_id
                and tab == section_table_id
                and did is not None
            )
            duplicate = did is not None and did in duplicate_ids
            if valid_target_owner and not duplicate and dom == expected_domain:
                used_ids_by_feeder[target_feeder_id].add(did)
                row.update({
                    "assigned_device_id": did,
                    "assigned_section_name": str(section.get("name") or ""),
                    "assigned_bv_id": section.get("bv_id", ""),
                    "expected_keyid": int(obj.keyid),
                    "expected_keyid_verified": "YES",
                    "db_create_needed": "NO",
                    "model_link_correct": "YES",
                    "association_ready": "YES",
                    "writeback_needed": "NO",
                    "status": "PASS",
                    "severity": "PASS",
                    "reason": (
                        "MODEL_ALREADY_LINKED_TO_TOPOLOGY_FEEDER: "
                        f"{topo_primary} -> FEEDER_ID={target_feeder_id}"
                    ),
                })
            elif valid_target_owner and not duplicate and dom != expected_domain:
                used_ids_by_feeder[target_feeder_id].add(did)
                expected_keyid, verified_ok, _ = validator._verify_expected_keyid(did)
                bv_id = str(section.get("bv_id", "") or "").strip()
                row.update({
                    "assigned_device_id": did,
                    "assigned_section_name": str(section.get("name") or ""),
                    "assigned_bv_id": section.get("bv_id", ""),
                    "expected_keyid": expected_keyid,
                    "expected_keyid_verified": "YES" if verified_ok else "NO",
                    "relink_same_section": "YES",
                    "db_create_needed": "NO",
                    "model_link_correct": "NO",
                })
                if not bv_id:
                    row.update(
                        status="FAIL", severity="ERROR",
                        association_ready="NO", writeback_needed="NO",
                        reason="BV_ID_EMPTY: 当前馈线段BV_ID为空，禁止重写模型",
                    )
                elif not verified_ok:
                    row.update(
                        status="FAIL", severity="ERROR",
                        association_ready="NO", writeback_needed="NO",
                        reason="EXPECTED_KEYID_VERIFY_FAILED",
                    )
                else:
                    row.update(
                        status="WARN", severity="RELINK",
                        association_ready="YES", writeback_needed="YES",
                        reason=(
                            "DOMAIN_RELINK_READY: 当前13503已属于拓扑确认馈线 "
                            f"{topo_primary}/FEEDER_ID={target_feeder_id}，仅Domain错误 "
                            f"current={dom}, expected={expected_domain}；保持原13503.ID不变。"
                        ),
                    )
            else:
                row["model_link_correct"] = "NO" if obj.keyid else ""
                row["db_create_needed"] = "NO"
                row["status"] = "WARN"
                row["severity"] = "DUPLICATE_LINK" if duplicate else ("RELINK" if obj.keyid else "UNLINKED")
                if duplicate:
                    row["reason"] = (
                        "DUPLICATE_LINK: 同一13503被多个FeedLine重复使用；"
                        f"device_id={did}; XML={','.join(valid_usage.get(did, []))}; "
                        f"本FeedLine拓扑目标={topo_primary}/FEEDER_ID={target_feeder_id}。"
                    )
                elif obj.keyid and owner_id not in (None, target_feeder_id):
                    row["reason"] = (
                        "MODEL_RELINK_REQUIRED_TO_TOPOLOGY_FEEDER: "
                        f"当前FEEDER_ID={owner_id or '-'}；"
                        f"拓扑目标={topo_primary}/FEEDER_ID={target_feeder_id}。"
                    )
                elif obj.keyid:
                    row["reason"] = (
                        "MODEL_RELINK_REQUIRED: 当前13503不存在、表号不正确或无法验证；"
                        f"拓扑目标={topo_primary}/FEEDER_ID={target_feeder_id}。"
                    )
                else:
                    row["reason"] = (
                        "MODEL_NOT_LINKED: "
                        f"拓扑目标={topo_primary}/FEEDER_ID={target_feeder_id}。"
                    )
                pending_by_feeder[target_feeder_id].append(row)
            rows.append(row)

        # Allocate only inside each FeedLine's topology-resolved feeder.
        shortage_by_feeder = defaultdict(list)
        for feeder_id in candidate_order:
            available = []
            for section in sections_by_feeder.get(feeder_id, []):
                did = int_or_none(section.get("id"))
                if did is None or did in used_ids_by_feeder.get(feeder_id, set()):
                    continue
                available.append(section)
            available.sort(key=natural_section_key)
            pending = sorted(
                pending_by_feeder.get(feeder_id, []),
                key=lambda row: int(row.get("order_index") or 10**9),
            )
            pool_index = 0
            for row in pending:
                if pool_index >= len(available):
                    shortage_by_feeder[feeder_id].append(row)
                    continue
                section = available[pool_index]
                pool_index += 1
                did = int_or_none(section.get("id"))
                if did is None:
                    shortage_by_feeder[feeder_id].append(row)
                    continue
                expected_keyid, verified_ok, _ = validator._verify_expected_keyid(did)
                bv_id = str(section.get("bv_id", "") or "").strip()
                row.update({
                    "assigned_feeder_id": feeder_id,
                    "assigned_feeder_name": feeder_display_name(feeder_id),
                    "assigned_device_id": did,
                    "assigned_section_name": str(section.get("name") or ""),
                    "planned_section_name": str(section.get("name") or ""),
                    "assigned_bv_id": section.get("bv_id", ""),
                    "expected_keyid": expected_keyid,
                    "expected_keyid_verified": "YES" if verified_ok else "NO",
                    "db_create_needed": "NO",
                })
                if not bv_id:
                    row.update(
                        status="FAIL", severity="ERROR", association_ready="NO",
                        writeback_needed="NO", reason="BV_ID_EMPTY",
                    )
                elif not verified_ok:
                    row.update(
                        status="FAIL", severity="ERROR", association_ready="NO",
                        writeback_needed="NO", reason="EXPECTED_KEYID_VERIFY_FAILED",
                    )
                else:
                    row.update(
                        status="WARN",
                        severity="RELINK" if row.get("model_linked") == "YES" else "UNLINKED",
                        association_ready="YES", writeback_needed="YES",
                        reason=(
                            "MODEL_RELINK_READY_FROM_TOPOLOGY_FEEDER"
                            if row.get("model_linked") == "YES"
                            else "MODEL_NOT_LINKED_READY_FROM_TOPOLOGY_FEEDER"
                        ) + f": FEEDER_ID={feeder_id}",
                    )

        # Plan genuine shortages independently under every topology owner.
        plans = []
        create_targets = []
        for feeder_id in candidate_order:
            shortage = shortage_by_feeder.get(feeder_id, [])
            if not shortage:
                continue

            feeder = dict(candidate_by_id[feeder_id])
            try:
                db_feeder = db.get_feeder_info(feeder_id, table_id=feeder_table_id) or {}
            except TypeError:
                db_feeder = db.get_feeder_info(feeder_id) or {}
            except Exception:
                db_feeder = {}
            feeder.update(db_feeder)
            feeder.setdefault("id", feeder_id)
            feeder.setdefault("st_id", candidate_by_id[feeder_id].get("st_id"))
            existing_sections = sections_by_feeder.get(feeder_id, [])
            prefix = self._section_prefix(feeder, existing_sections)
            station_id = int_or_none(feeder.get("st_id"))
            try:
                voltage = (
                    db.get_preferred_feeder_section_voltage(station_id)
                    if station_id is not None else None
                ) or {}
            except Exception:
                voltage = {}
            bv_id = voltage.get("bv_id")

            if not prefix or bv_id in (None, ""):
                for row in shortage:
                    row.update(
                        status="FAIL", severity="ERROR", association_ready="NO",
                        writeback_needed="NO", db_create_needed="NO",
                        reason=(
                            "SECTION_NOT_AVAILABLE_AND_TARGET_FEEDER_CREATE_METADATA_UNRESOLVED: "
                            f"FEEDER_ID={feeder_id}；无法取得有效命名前缀/BV_ID。"
                        ),
                    )
                continue

            existing_names = {
                str(item.get("name") or "").strip().upper()
                for item in existing_sections
                if str(item.get("name") or "").strip()
            }
            planned_names = set()

            def next_name():
                suffix = 1
                while True:
                    name = f"{prefix}_SEC{suffix:03d}"
                    key = name.upper()
                    if key not in existing_names and key not in planned_names:
                        planned_names.add(key)
                        return name
                    suffix += 1

            target_plan_count = 0
            for row in shortage:
                section_type = self._section_type_from_ls(row.get("ls", ""))
                if section_type is None:
                    row.update(
                        status="FAIL", severity="ERROR", association_ready="NO",
                        writeback_needed="NO", db_create_needed="NO",
                        reason=f"UNKNOWN_FEEDLINE_LS: ls={row.get('ls')!r}",
                    )
                    continue
                planned_name = next_name()
                row.update({
                    "assigned_feeder_id": feeder_id,
                    "assigned_feeder_name": feeder_display_name(feeder_id),
                    "assigned_device_id": "",
                    "assigned_section_name": planned_name,
                    "planned_section_name": planned_name,
                    "assigned_bv_id": int(bv_id),
                    "planned_section_type": section_type,
                    "expected_keyid": "",
                    "expected_keyid_verified": "",
                    "db_create_needed": "YES",
                    "association_ready": "YES",
                    "writeback_needed": "YES",
                    "status": "WARN",
                    "severity": "CREATE_PENDING",
                    "reason": (
                        f"DB_SECTION_CREATE_PENDING_FOR_TOPOLOGY_FEEDER: {planned_name}; "
                        f"FEEDER_ID={feeder_id}; topology={row.get('topology_primary_feeder')}; "
                        f"ls={row.get('ls')!r} -> SECTION_TYPE={section_type}"
                    ),
                })
                plans.append({
                    "name": planned_name,
                    "feeder_id": feeder_id,
                    "feeder_name": feeder_display_name(feeder_id),
                    "bv_id": int(bv_id),
                    "section_type": section_type,
                    "order_index": row.get("order_index", ""),
                    "xml_id": row.get("xml_id", ""),
                })
                target_plan_count += 1

            if target_plan_count:
                create_targets.append({
                    "feeder_id": feeder_id,
                    "feeder_name": feeder_display_name(feeder_id),
                    "prefix": prefix,
                    "bv_id": int(bv_id),
                    "nomvol": voltage.get("nomvol", ""),
                    "station_name": feeder.get("station_name", ""),
                    "planned_create_count": target_plan_count,
                })

        report["feedline_rows"] = rows
        report["section_create_plan"] = plans
        report["section_create_targets"] = create_targets
        report["planned_create_count"] = len(plans)
        if len(create_targets) == 1:
            target = create_targets[0]
            report["section_prefix"] = target["prefix"]
            report["section_station_bv_id"] = target["bv_id"]
            report["section_nominal_voltage_kv"] = target["nomvol"]
            report["section_station_name"] = target["station_name"]
        elif len(create_targets) > 1:
            report["section_prefix"] = " | ".join(
                f"{item['feeder_id']}:{item['prefix']}" for item in create_targets
            )
            report["section_station_bv_id"] = " | ".join(
                f"{item['feeder_id']}:{item['bv_id']}" for item in create_targets
            )
            report["section_nominal_voltage_kv"] = " | ".join(
                f"{item['feeder_id']}:{item['nomvol']}" for item in create_targets
            )
            report["section_station_name"] = " | ".join(
                str(item.get("station_name") or "") for item in create_targets
            )

        fail_count = sum(1 for row in rows if row.get("status") == "FAIL")
        ready_count = sum(
            1 for row in rows
            if row.get("association_ready") == "YES" and row.get("writeback_needed") == "YES"
        )
        linked_correct = sum(1 for row in rows if row.get("model_link_correct") == "YES")
        report["status"] = "WARN" if fail_count or ready_count else "PASS"
        report["severity"] = "PARTIAL_ERROR" if fail_count else ("ASSOCIATION_READY" if ready_count else "PASS")
        report["reason"] = (
            f"MAKKAH_RING_TOPOLOGY_FEEDER_VALIDATED: feeders={len(candidate_order)}; "
            f"topology_confirmed={report['feedline_topology_confirmed_count']}; "
            f"topology_conflict={report['feedline_topology_conflict_count']}; "
            f"topology_unresolved={report['feedline_topology_unresolved_count']}; "
            f"already_correct={linked_correct}; ready={ready_count}; "
            f"create={len(plans)}; create_feeders={len(create_targets)}; errors={fail_count}"
        )
        report["summary"] = FeederValidator._summary(report)

        creation_text = ", ".join(
            f"{item['feeder_name'] or item['feeder_id']}:{item['planned_create_count']}"
            for item in create_targets
        ) or "0"
        log_callback(
            f"[{g_file.name}] 麦加馈线拓扑归属校验：有效馈线={len(candidate_order)}；"
            f"FeedLine拓扑确认={report['feedline_topology_confirmed_count']}；"
            f"冲突={report['feedline_topology_conflict_count']}；"
            f"未确定={report['feedline_topology_unresolved_count']}；"
            f"已正确关联={linked_correct}；待关联/修复={ready_count}；"
            f"按所属馈线新建13503={len(plans)}（{creation_text}）；错误={fail_count}。"
        )
        return report

    def validate(
        self,
        db,
        files,
        settings,
        log_callback,
        progress_callback=None,
    ):
        reports = []
        aggregate = {
            "feeder_files": 0,
            "feeders_resolved": 0,
            "feedlines": 0,
            "feedline_pass": 0,
            "feedline_warn": 0,
            "feedline_fail": 0,
            "association_ready": 0,
        }
        total = max(len(files), 1)
        for idx, g_file in enumerate(files, start=1):
            g_file = Path(g_file)
            log_callback(f"[{idx}/{len(files)}] 正在处理麦加环网图馈线：{g_file.name}")
            feeder, candidates = self._resolve_any_ring_feeder(
                db, g_file, settings, log_callback
            )
            if feeder is None:
                file_report = self._unresolved_file_report(
                    g_file,
                    "MAKKAH_RING_FEEDER_NOT_FOUND: 当前环网图所有含 CBreaker 的主网 Bay 框均未通过 Station -> ST_ID -> dms_feeder_device 唯一确认到馈线。",
                )
                region_reports = file_report.get("feeder_regions") or [file_report]
                for report in region_reports:
                    report["drawing_type"] = "MAKKAH_RING_MULTI_FEEDER_POOL"
                    report["ring_candidate_feeder_count"] = 0
                    report["ring_candidate_feeder_ids"] = ""
                    report["ring_candidate_feeder_names"] = ""
            else:
                report = self._validate_makkah_ring_feeder_pool(
                    db, g_file, candidates, settings, log_callback
                )
                region_reports = [report]

            reports.extend(region_reports)
            aggregate["feeder_files"] += 1
            for report in region_reports:
                log_callback(
                    f"[{g_file.name}] 已确认馈线={report.get('ring_candidate_feeder_names') or report.get('feeder_name') or '-'}；"
                    f"FeedLine={len(report.get('feedline_rows', []))}；状态={report.get('status')}"
                )
                summary = report.get("summary", {}) or {}
                for key in aggregate:
                    if key != "feeder_files":
                        aggregate[key] += int(summary.get(key, 0) or 0)
            if progress_callback:
                progress_callback(int(idx * 100 / total))
        return reports, aggregate, self._rules(settings)

    @staticmethod
    def _attributes_for_row(row):
        bv_id = str(row.get("assigned_bv_id", "") or "").strip()
        if not bv_id:
            raise ValueError(
                f"FeedLine:{row.get('xml_id')}: "
                "数据库 BV_ID 为空，禁止生成模型回写。"
            )
        return {
            "app": "6500000",
            "p_ReportType": "1",
            "state": "20",
            "voltype": bv_id,
            "keyid": str(row["expected_keyid"]),
        }

    def preview_association(
        self,
        db,
        files,
        settings,
        log_callback,
        progress_callback=None,
    ):
        reports, summary, rules = self.validate(
            db,
            files,
            settings,
            log_callback,
            progress_callback,
        )

        changes_by_file = defaultdict(list)
        rows = []
        skipped_rmus = []

        for report in reports:
            g_file = report["g_file"]

            root_candidate_ready = (
                report.get("drawing_type") == "SINGLE_FEEDER"
                and report.get("feeder_root_writeback_needed") == "YES"
            )
            if not report.get("association_eligible"):
                skipped_rmus.append({
                    "g_file": g_file,
                    "rmu_name": report.get("feeder_name", ""),
                    "rmu_id": report.get("feeder_id", ""),
                    "reasons": [report.get("reason", "")],
                })
                # Section/model errors may block FeedLine association, but a
                # separately validated SINGLE_FEEDER root relationship remains
                # selectable. Only stop here when no root candidate exists.
                if not root_candidate_ready:
                    continue

            # v4.1.8 single-feeder root association is independent from section
            # objects. If MANUAL/FILENAME uniquely resolved the feeder and the
            # G root facID is empty, expose a selectable G-root association
            # object whether or not FeedLine objects exist. Breaker/Busbar and
            # section-link state do not gate this feeder-master writeback.
            if report.get("feeder_root_writeback_needed") == "YES":
                current_root_facid = str(
                    report.get("feeder_root_current_facid", "") or ""
                ).strip()
                root_override = bool(current_root_facid)
                root_row = {
                    "object_type": "G",
                    "xml_id": "root",
                    "order_index": "-",
                    "model_linked": "YES" if root_override else "NO",
                    "model_link_correct": "NO" if root_override else "",
                    "status": "WARN",
                    "severity": "RELINK" if root_override else "UNLINKED",
                    "association_ready": "YES",
                    "writeback_needed": "YES",
                    "assigned_section_name": "G根节点 facID",
                    "assigned_device_id": report.get("feeder_id", ""),
                    "expected_keyid": "",
                    "reason": (
                        (
                            "FEEDER_ROOT_FACID_OVERRIDE_READY: "
                            f"current facID={current_root_facid} -> "
                            f"target={report.get('feeder_id', '')}; "
                            "已启用人工覆盖，仅修改安全输出副本。"
                        )
                        if root_override
                        else (
                            "FEEDER_ROOT_FACID_WRITEBACK_READY: "
                            f"facID -> {report.get('feeder_id', '')}; "
                            "仅关联馈线本体，不创建馈线段。"
                        )
                    ),
                }
                report["feeder_root_candidate_row"] = dict(root_row)
                change = {
                    "change_kind": "FEEDER_ROOT_FACID",
                    "xml_id": "root",
                    "tag": "G",
                    "attributes": {
                        "facID": str(report.get("feeder_id", "") or "")
                    },
                    "feeder_name": report.get("feeder_name", ""),
                    "feeder_id": report.get("feeder_id", ""),
                    "region_index": report.get("region_index", ""),
                    "section_name": "",
                    "device_id": report.get("feeder_id", ""),
                    "expected_keyid": "",
                    "db_create_needed": "NO",
                    "planned_section_name": "",
                    "planned_section_type": "",
                    "validated_row": dict(root_row),
                }
                changes_by_file[g_file].append(change)
                rows.append(dict(root_row))

            if not report.get("association_eligible"):
                # Root candidate above remains executable; FeedLine rows stay
                # blocked by their validation result.
                continue

            for row in report.get("feedline_rows", []):
                if row.get("association_ready") != "YES":
                    continue

                if row.get("writeback_needed") != "YES":
                    if row.get("model_link_correct") == "YES":
                        log_callback(
                            f"无需关联：FeedLine XML={row.get('xml_id')} "
                            f"已经属于本图已确认馈线 "
                            f"{row.get('current_feeder_name') or report.get('feeder_name')}。"
                        )
                    continue

                if row.get("db_create_needed") == "YES":
                    attrs = {
                        "app": "6500000",
                        "p_ReportType": "1",
                        "state": "20",
                        "voltype": str(row.get("assigned_bv_id", "") or ""),
                        # Final Expected KeyID is calculated only AFTER the
                        # database row has been created and re-queried.
                        "keyid": "",
                    }
                else:
                    attrs = self._attributes_for_row(row)
                if row.get("ls_normalization_needed") == "YES":
                    attrs["ls"] = str(row.get("ls_normalized") or "2")
                target_feeder_id = (
                    row.get("assigned_feeder_id")
                    or row.get("current_feeder_id")
                    or report.get("feeder_id", "")
                )
                target_feeder_name = (
                    row.get("assigned_feeder_name")
                    or row.get("current_feeder_name")
                    or report.get("feeder_name", "")
                )
                change = {
                    "xml_id": row["xml_id"],
                    "tag": "FeedLine",
                    "attributes": attrs,
                    "feeder_name": target_feeder_name,
                    "feeder_id": target_feeder_id,
                    "region_index": report.get("region_index", ""),
                    "section_name": row.get("assigned_section_name", ""),
                    "device_id": row.get("assigned_device_id", ""),
                    "expected_keyid": row.get("expected_keyid", ""),
                    "db_create_needed": row.get("db_create_needed", "NO"),
                    "planned_section_name": row.get("planned_section_name", ""),
                    "planned_section_type": row.get("planned_section_type", ""),
                    "validated_row": dict(row),
                }
                changes_by_file[g_file].append(change)

                preview_row = dict(row)
                if row.get("db_create_needed") == "YES":
                    preview_row["reason"] = (
                        "PREVIEW_CREATE_THEN_WRITE "
                        f"name={row.get('planned_section_name')} "
                        f"section_type={row.get('planned_section_type')} "
                        f"app=6500000 p_ReportType=1 state=20 "
                        f"voltype={attrs['voltype']} keyid=<创建后计算>"
                    )
                else:
                    preview_row["reason"] = (
                        "PREVIEW_WRITE "
                        f"app=6500000 p_ReportType=1 state=20 "
                        f"voltype={attrs['voltype']} "
                        f"keyid={attrs['keyid']}"
                    )
                rows.append(preview_row)

        preview_summary = dict(summary)
        preview_summary["association_change_count"] = sum(
            len(value)
            for value in changes_by_file.values()
        )
        preview_summary["association_skipped_feeder_count"] = len(
            skipped_rmus
        )

        ls_normalization_by_file = defaultdict(list)
        for report in reports:
            source_file = str(report.get("g_file", "") or "")
            if not source_file:
                continue
            for row in report.get("feedline_rows", []) or []:
                if row.get("ls_normalization_needed") == "YES":
                    ls_normalization_by_file[source_file].append({
                        "xml_id": str(row.get("xml_id", "") or ""),
                        "tag": "FeedLine",
                        "attributes": {
                            "ls": str(row.get("ls_normalized") or "2")
                        },
                    })

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }

        return {
            "reports": reports,
            "rows": rows,
            "summary": preview_summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
            "ls_normalization_by_file": dict(ls_normalization_by_file),
            # Kept for current generic GUI compatibility.
            "skipped_rmus": skipped_rmus,
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "rmu_name_detection_mode": str(
                    settings.get(
                        "rmu_name_detection_mode",
                        DEFAULT_RMU_NAME_DETECTION_MODE,
                    )
                    or DEFAULT_RMU_NAME_DETECTION_MODE
                ).upper(),
                "rmu_name_positions": dict(
                    settings.get("feeder_rmu_name_positions", {})
                ),
                "feeder_table_id": int(
                    settings.get("feeder_table_id", 13500)
                ),
                "section_table_id": int(
                    settings.get("section_table_id", 13503)
                ),
                "section_domain": int(
                    settings.get("section_domain", 1)
                ),
                "feeder_resolution_mode": str(
                    settings.get("feeder_resolution_mode", "FACID")
                ).upper(),
                "manual_feeder_name": str(
                    settings.get("manual_feeder_name", "") or ""
                ).strip(),
                "feeder_station_hint": str(
                    settings.get("feeder_station_hint", "") or ""
                ).strip(),
                "allow_feeder_override": bool(
                    settings.get("allow_feeder_override", False)
                ),
                "feeder_drawing_mode": str(
                    settings.get("feeder_drawing_mode", "AUTO") or "AUTO"
                ).upper(),
                "auto_create_missing_sections": bool(
                    settings.get("auto_create_missing_sections", True)
                ),
            },
        }

    def apply_association(
        self,
        db,
        files,
        settings,
        preview_data,
        log_callback,
        output_g_dir=None,
    ):
        """Apply ONLY the FeedLine rows selected by the user.

        The validated feeder-name/FEEDER_ID decision remains the authority. At
        execution time the selected region's current dms_section_device pool
        is refreshed and allocations are recalculated against UNSELECTED
        existing links. This is especially important for duplicate links:
        selecting one duplicate means the unselected duplicate keeps the old
        section and the selected FeedLine is moved to another available
        section; selecting both returns both to the allocation pool.
        """
        if not preview_data:
            raise RuntimeError("没有可执行的馈线模型校验候选结果。")

        current_snapshot = {
            "rmu_name_detection_mode": str(
                settings.get(
                    "rmu_name_detection_mode",
                    DEFAULT_RMU_NAME_DETECTION_MODE,
                )
                or DEFAULT_RMU_NAME_DETECTION_MODE
            ).upper(),
            "rmu_name_positions": dict(
                settings.get("feeder_rmu_name_positions", {})
            ),
            "feeder_table_id": int(settings.get("feeder_table_id", 13500)),
            "section_table_id": int(settings.get("section_table_id", 13503)),
            "section_domain": int(settings.get("section_domain", 1)),
            "feeder_resolution_mode": str(
                settings.get("feeder_resolution_mode", "FACID")
            ).upper(),
            "manual_feeder_name": str(
                settings.get("manual_feeder_name", "") or ""
            ).strip(),
            "feeder_station_hint": str(
                settings.get("feeder_station_hint", "") or ""
            ).strip(),
            "allow_feeder_override": bool(
                settings.get("allow_feeder_override", False)
            ),
            "feeder_drawing_mode": str(
                settings.get("feeder_drawing_mode", "AUTO") or "AUTO"
            ).upper(),
            "auto_create_missing_sections": bool(
                settings.get("auto_create_missing_sections", True)
            ),
        }
        validated_snapshot = dict(
            preview_data.get("settings_snapshot", {}) or {}
        )
        # Backward compatible with older in-memory/test previews that do not
        # contain newly introduced feeder settings: only keys present in the
        # validation snapshot participate in the consistency check.
        # v4.1.38: the selected feeder source is always explicit.  Every
        # source-specific setting therefore participates in the validation ->
        # execution consistency check; no populated facID silently overrides it.
        ignored_snapshot_keys = set()
        if any(
            current_snapshot.get(key) != value
            for key, value in validated_snapshot.items()
            if key in current_snapshot and key not in ignored_snapshot_keys
        ):
            raise RuntimeError(
                "馈线模型配置在模型校验后发生变化，请重新执行模型校验。"
            )

        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        changes_by_file = preview_data.get("changes_by_file", {}) or {}
        if not changes_by_file:
            raise RuntimeError("当前没有勾选任何可关联馈线段。")

        output_g_dir = Path(output_g_dir)
        output_g_dir.mkdir(parents=True, exist_ok=True)

        for g_file, fingerprint in preview_data.get("file_fingerprints", {}).items():
            path = Path(g_file)
            stat = path.stat()
            if (
                stat.st_size != fingerprint.get("size")
                or stat.st_mtime_ns != fingerprint.get("mtime_ns")
            ):
                raise RuntimeError(
                    "G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验："
                    f"{g_file}"
                )

        validator = self._validator(db, settings, log_callback)
        section_table_id = int(settings.get("section_table_id", 13503))
        section_domain = int(settings.get("section_domain", 1))

        # Report lookup lets execution see ALL rows in a topology region while
        # changing only the selected XML IDs.
        report_lookup = {}
        for report in preview_data.get("reports", []) or []:
            key = (
                str(report.get("g_file", "") or ""),
                str(report.get("region_index", "") or ""),
            )
            report_lookup[key] = report

        recalculated = defaultdict(list)
        skipped = []
        database_created_count = 0
        facid_writeback_by_file = {}

        for source_file, changes in changes_by_file.items():
            grouped = defaultdict(list)
            source_selected_feedline_xml_ids = set()
            for change in changes or []:
                grouped[(
                    str(change.get("region_index", "") or ""),
                    str(change.get("feeder_id", "") or ""),
                )].append(dict(change))
                if str(change.get("tag", "") or "").upper() == "FEEDLINE":
                    source_selected_feedline_xml_ids.add(
                        str(change.get("xml_id", "") or "")
                    )

            for (region_index, feeder_id_text), selected_changes in grouped.items():
                log_callback(
                    f"正在执行馈线模型关联：文件={Path(source_file).name}；"
                    f"区域={region_index or '-'}；FEEDER_ID={feeder_id_text or '-'}；"
                    f"已选对象={len(selected_changes)}"
                )
                feeder_id = int_or_none(feeder_id_text)
                if feeder_id is None:
                    for change in selected_changes:
                        skipped.append((change, "EXEC_FEEDER_ID_INVALID"))
                    continue

                report = report_lookup.get((
                    str(source_file), region_index,
                ))
                if report is None:
                    for change in selected_changes:
                        skipped.append((change, "EXEC_TOPOLOGY_REGION_NOT_FOUND"))
                    continue

                root_changes = [
                    change for change in selected_changes
                    if str(change.get("change_kind", "")).upper()
                    == "FEEDER_ROOT_FACID"
                    or (
                        str(change.get("tag", "")).upper() == "G"
                        and str(change.get("xml_id", "")) == "root"
                    )
                ]
                feedline_changes = [
                    change for change in selected_changes
                    if change not in root_changes
                ]

                resolution_source = str(
                    report.get("feeder_resolution_source")
                    or report.get("feeder_hint_source")
                    or ""
                ).upper()
                root_writeback_flag = str(
                    report.get("feeder_root_writeback_needed", "") or ""
                ).upper()
                root_writeback_allowed = (
                    str(report.get("drawing_type") or "SINGLE_FEEDER")
                    == "SINGLE_FEEDER"
                    and resolution_source in {"FILENAME", "MANUAL"}
                    and (
                        root_writeback_flag == "YES"
                        # Backward compatibility for previews created by
                        # v4.1.7/tests: an explicit G-root change itself is
                        # sufficient evidence when the new flag is absent.
                        or (not root_writeback_flag and bool(root_changes))
                    )
                )

                # v4.1.8: the G-root feeder association is independent of
                # FeedLine/section validation. A section-level/model-level
                # failure may block FeedLine changes, but it must not block the
                # explicitly validated SINGLE_FEEDER -> FEEDER_ID root link.
                if not report.get("association_eligible") and feedline_changes:
                    for change in feedline_changes:
                        skipped.append((
                            change,
                            f"EXEC_REGION_BLOCKED: {report.get('reason', '')}",
                        ))
                    feedline_changes = []

                if root_changes and not root_writeback_allowed:
                    for change in root_changes:
                        skipped.append((
                            change,
                            "EXEC_FEEDER_ROOT_BLOCKED: 仅允许已确认的单馈线图"
                            "使用 MANUAL/FILENAME 唯一馈线结果回写根 facID",
                        ))
                    root_changes = []

                # Selecting any executable FeedLine under a name-resolved
                # SINGLE_FEEDER also writes the root facID, preserving the
                # historical convenience. Selecting the dedicated root row
                # writes only the feeder master relationship.
                should_write_root = root_writeback_allowed and bool(
                    root_changes or (feedline_changes and report.get("association_eligible"))
                )
                if should_write_root:
                    parsed_exec = GParser().parse(source_file)
                    current_root_facid = str(
                        parsed_exec.root.attrib.get("facID", "") or ""
                    ).strip()
                    if (
                        current_root_facid
                        and current_root_facid != str(feeder_id)
                        and not bool(settings.get("allow_feeder_override", False))
                    ):
                        raise RuntimeError(
                            "执行阶段发现当前 G.facID 与目标馈线不同，且未启用人工覆盖："
                            f"{source_file} | current={current_root_facid} | target={feeder_id}"
                        )
                    if current_root_facid != str(feeder_id):
                        facid_writeback_by_file[str(source_file)] = feeder_id

                if not root_changes and not feedline_changes:
                    continue

                # A feeder-root-only selection has no 13503 work.
                if root_changes and not feedline_changes:
                    log_callback(
                        f"馈线区域{region_index}：FEEDER_ID={feeder_id}；"
                        "本次仅关联馈线根节点facID；Breaker/Busbar/FeedLine"
                        "状态不参与该根关联。"
                    )
                    continue

                _, section_rows = db.get_sections_by_feeder_id(
                    feeder_id,
                    table_id=section_table_id,
                )
                section_rows = sorted(section_rows, key=natural_section_key)

                # Reserve database records currently used by rows that are
                # UNSELECTED in the whole source file.  A FeedLine selected in
                # another target-feeder group may be moving away from this
                # feeder, so its old 13503 must not remain falsely protected.
                protected_ids = set()
                for row in report.get("feedline_rows", []) or []:
                    if (
                        str(row.get("xml_id", "") or "")
                        in source_selected_feedline_xml_ids
                    ):
                        continue
                    did = int_or_none(row.get("current_device_id"))
                    owner = int_or_none(row.get("current_feeder_id"))
                    tab = int_or_none(row.get("current_table_id"))
                    dom = int_or_none(row.get("current_domain"))
                    if (
                        did is not None
                        and owner == feeder_id
                        and tab == section_table_id
                    ):
                        # A domain-wrong KeyID still references this exact
                        # feeder section. Keep it reserved when the row is not
                        # selected so another FeedLine cannot steal it.
                        protected_ids.add(did)

                available = [
                    section for section in section_rows
                    if int_or_none(section.get("id")) not in protected_ids
                ]
                available.sort(key=natural_section_key)

                # Database preparation is driven by the selected FeedLine's
                # exact planned SEC name, not merely by "pool size".  Example:
                # G order #2 requires ..._SEC002.  If DB has SEC010 but not
                # SEC002, SEC002 is still missing and must be created.
                # Makkah fixed rule: missing 13503 rows are always created
                # for selected FeedLines after one drawing-local feeder has
                # been uniquely confirmed.
                if True:
                    existing_names = {
                        str(section.get("name") or "").strip().upper()
                        for section in section_rows
                    }
                    create_defs = []
                    seen_create_names = set()
                    for change in feedline_changes:
                        row = dict(
                            change.get("validated_row", {}) or {}
                        )
                        if (
                            change.get("db_create_needed") != "YES"
                            and row.get("db_create_needed") != "YES"
                        ):
                            continue
                        planned_name = str(
                            change.get("planned_section_name")
                            or row.get("planned_section_name")
                            or row.get("assigned_section_name")
                            or ""
                        ).strip()
                        if not planned_name:
                            continue
                        key = planned_name.upper()
                        if key in existing_names or key in seen_create_names:
                            continue
                        section_type = change.get(
                            "planned_section_type",
                            row.get("planned_section_type", ""),
                        )
                        bv_id = row.get(
                            "assigned_bv_id",
                            "",
                        )
                        if section_type in (None, ""):
                            skipped.append((
                                change,
                                "EXEC_SECTION_TYPE_UNKNOWN",
                            ))
                            continue
                        if bv_id in (None, ""):
                            skipped.append((
                                change,
                                "EXEC_BV_ID_EMPTY_FOR_CREATE",
                            ))
                            continue
                        seen_create_names.add(key)
                        create_defs.append({
                            "name": planned_name,
                            "bv_id": int(bv_id),
                            "section_type": int(section_type),
                        })

                    if create_defs:
                        log_callback(
                            f"馈线区域{region_index}：准备创建选中 FeedLine "
                            f"对应的缺失馈线段 {len(create_defs)} 条；"
                            "唯一写表=13503/dms_section_device。"
                        )
                        created = db.create_missing_sections(
                            feeder_id,
                            create_defs,
                            table_id=section_table_id,
                            area_id=0,
                        )
                        database_created_count += len(created)
                        for item in created:
                            log_callback(
                                "数据库新增馈线段："
                                f"ID={item.get('id')} "
                                f"NAME={item.get('name')} "
                                f"FEEDER_ID={item.get('feeder_id')} "
                                f"BV_ID={item.get('bv_id')} "
                                f"SECTION_TYPE={item.get('section_type')}"
                            )

                        # Database fact is the authority. Re-query after COMMIT
                        # before any Expected KeyID is calculated or G is edited.
                        _, section_rows = db.get_sections_by_feeder_id(
                            feeder_id,
                            table_id=section_table_id,
                        )
                        section_rows = sorted(
                            section_rows,
                            key=natural_section_key,
                        )
                        available = [
                            section for section in section_rows
                            if int_or_none(section.get("id"))
                            not in protected_ids
                        ]
                        available.sort(key=natural_section_key)

                feedline_changes.sort(
                    key=lambda change: int(
                        (change.get("validated_row", {}) or {}).get(
                            "order_index", 10**9
                        )
                    )
                )

                log_callback(
                    f"馈线区域{region_index}：FEEDER_ID={feeder_id}；"
                    f"勾选FeedLine={len(feedline_changes)}；"
                    f"未选中已占用数据库段={len(protected_ids)}；"
                    f"当前可分配数据库段={len(available)}"
                )

                remaining_available = list(available)
                for change in feedline_changes:
                    row0 = dict(
                        change.get("validated_row", {}) or {}
                    )
                    planned_name = str(
                        change.get("planned_section_name")
                        or row0.get("planned_section_name")
                        or ""
                    ).strip()

                    section = None
                    preserve_same_section = str(
                        row0.get("relink_same_section", "") or ""
                    ).upper() == "YES"
                    create_needed = str(
                        change.get("db_create_needed")
                        or row0.get("db_create_needed")
                        or "NO"
                    ).upper() == "YES"
                    assigned_id = int_or_none(
                        row0.get("assigned_device_id")
                        or change.get("device_id")
                    )

                    # v4.1.11: validation has already selected an exact existing
                    # 13503 row for ordinary UNLINKED/RELINK rows. Preserve that
                    # exact device_id at execution instead of forcing a
                    # positional SEC name match. This is essential for legacy
                    # feeders whose existing section NAME values are topology
                    # names rather than *_SECnnn. CREATE rows intentionally have
                    # no assigned existing id and are resolved by the newly
                    # created planned name below.
                    if not create_needed and assigned_id is not None:
                        exact_id_matches = [
                            item for item in remaining_available
                            if int_or_none(item.get("id")) == assigned_id
                        ]
                        if len(exact_id_matches) == 1:
                            section = exact_id_matches[0]
                        else:
                            skipped.append((
                                change,
                                "EXEC_ASSIGNED_SECTION_NOT_AVAILABLE: "
                                f"device_id={assigned_id}",
                            ))
                            continue
                    elif preserve_same_section:
                        # Backward-compatible safety branch for older preview
                        # data that may not carry assigned_device_id.
                        preserve_id = int_or_none(
                            row0.get("assigned_device_id")
                            or row0.get("current_device_id")
                        )
                        exact_id_matches = [
                            item for item in remaining_available
                            if int_or_none(item.get("id")) == preserve_id
                        ]
                        if len(exact_id_matches) == 1:
                            section = exact_id_matches[0]
                        else:
                            skipped.append((
                                change,
                                "EXEC_DOMAIN_RELINK_SECTION_NOT_AVAILABLE: "
                                f"device_id={preserve_id or '-'}",
                            ))
                            continue
                    elif planned_name:
                        exact_matches = [
                            item
                            for item in remaining_available
                            if str(
                                item.get("name") or ""
                            ).strip().upper()
                            == planned_name.upper()
                        ]
                        if len(exact_matches) > 1:
                            skipped.append((
                                change,
                                "EXEC_SECTION_NAME_DUPLICATE: "
                                f"{planned_name}",
                            ))
                            continue
                        if len(exact_matches) == 1:
                            section = exact_matches[0]

                    # Preserve the original remaining-section fallback for
                    # legacy/relink rows that do not carry a planned SEC name.
                    if section is None and not planned_name and not preserve_same_section:
                        section = (
                            remaining_available[0]
                            if remaining_available
                            else None
                        )

                    if section is None:
                        skipped.append((
                            change,
                            "EXEC_PLANNED_SECTION_NOT_AVAILABLE: "
                            f"{planned_name or '-'}",
                        ))
                        continue

                    remaining_available.remove(section)
                    device_id = int_or_none(section.get("id"))
                    if device_id is None:
                        skipped.append((change, "EXEC_SECTION_DEVICE_ID_INVALID"))
                        continue

                    expected_keyid, verified_ok, _ = (
                        validator._verify_expected_keyid(device_id)
                    )
                    bv_id = str(section.get("bv_id", "") or "").strip()
                    if not bv_id:
                        skipped.append((change, "EXEC_BV_ID_EMPTY"))
                        continue
                    if not verified_ok:
                        skipped.append((change, "EXEC_EXPECTED_KEYID_VERIFY_FAILED"))
                        continue

                    row = dict(change.get("validated_row", {}) or {})
                    row.update({
                        "assigned_device_id": device_id,
                        "assigned_section_name": str(section.get("name", "") or "").strip(),
                        "assigned_bv_id": bv_id,
                        "expected_keyid": expected_keyid,
                        "expected_keyid_verified": "YES",
                        "association_ready": "YES",
                        "writeback_needed": "YES",
                    })
                    refreshed = dict(change)
                    refreshed["device_id"] = device_id
                    refreshed["section_name"] = row["assigned_section_name"]
                    refreshed["expected_keyid"] = expected_keyid
                    refreshed["validated_row"] = row
                    refreshed["attributes"] = self._attributes_for_row(row)
                    if row.get("ls_normalization_needed") == "YES":
                        refreshed["attributes"]["ls"] = str(row.get("ls_normalized") or "2")
                    recalculated[str(source_file)].append(refreshed)

        for change, reason in skipped:
            log_callback(
                f"跳过 FeedLine XML={change.get('xml_id')}: {reason}"
            )

        if not recalculated and not facid_writeback_by_file:
            raise RuntimeError(
                "所有勾选馈线对象在执行时均被阻断，没有可安全写回的对象。"
            )

        # Copy only source files that contain selected executable FeedLine
        # changes or a validated feeder-root facID writeback.
        source_map = {
            str(Path(source).resolve()): Path(source)
            for source in files
        }
        copied = {}
        executable_source_files = set(recalculated) | set(facid_writeback_by_file)
        for source_file in executable_source_files:
            source = source_map.get(
                str(Path(source_file).resolve()),
                Path(source_file),
            )
            target = output_g_dir / source.name
            if target.exists():
                idx = 2
                while True:
                    candidate = output_g_dir / f"{source.stem}_{idx}{source.suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    idx += 1
            log_callback(
                f"正在复制 G 文件到安全输出目录：{source.name}"
            )
            shutil.copy2(source, target)
            copied[str(source.resolve())] = target
            log_callback(f"安全复制 G 文件：{source} -> {target}")

        service = GWriteBackService(log=log_callback)
        results = []
        for source_file in executable_source_files:
            changes = list(recalculated.get(source_file, []) or [])
            target = copied.get(str(Path(source_file).resolve()))
            if target is None:
                raise RuntimeError(f"无法定位 G 文件安全副本：{source_file}")
            if changes:
                log_callback(
                    f"正在回写 G 文件安全副本：{target.name}；"
                    f"待写FeedLine数={len(changes)}"
                )
                result = service.apply_attribute_changes(
                    target,
                    changes,
                    create_backup=False,
                )
            else:
                result = {
                    "g_file": str(target),
                    "backup": "",
                    "applied_count": 0,
                    "changes": [],
                }
            normalization_changes = list(
                (preview_data.get("ls_normalization_by_file", {}) or {}).get(
                    str(source_file), []
                ) or []
            )
            if normalization_changes:
                # Normalize every ls>2 FeedLine in this output file, including
                # unselected rows. This is a model precondition, not an
                # association-choice side effect.
                service.apply_attribute_changes(
                    target,
                    normalization_changes,
                    create_backup=False,
                )
                result["ls_normalized_count"] = len(normalization_changes)
            else:
                result["ls_normalized_count"] = 0

            feeder_id_for_root = facid_writeback_by_file.get(str(source_file))
            if feeder_id_for_root is not None:
                root_result = service.apply_root_g_attributes(
                    target,
                    {"facID": str(feeder_id_for_root)},
                    create_backup=False,
                )
                result["facid_written"] = True
                result["facid_before"] = (
                    root_result.get("before", {}) or {}
                ).get("facID")
                result["facid_after"] = str(feeder_id_for_root)
                result.setdefault("changes", []).append({
                    "tag": "G",
                    "xml_id": "root",
                    "before": {
                        "facID": result.get("facid_before")
                    },
                    "after": {
                        "facID": str(feeder_id_for_root)
                    },
                })
                result["applied_count"] = int(
                    result.get("applied_count", 0)
                ) + 1
                log_callback(
                    f"G 根节点 facID 回写完成：{target}；"
                    f"facID={feeder_id_for_root}。"
                )
            else:
                result["facid_written"] = False

            result["source_g_file"] = str(source_file)
            result["output_g_file"] = str(target)
            results.append(result)
            log_callback(
                f"馈线模型安全副本处理完成：{target}；"
                f"修改FeedLine数={result['applied_count']}；"
                f"根facID回写={'YES' if result.get('facid_written') else 'NO'}；"
                f"ls>2归一化={result.get('ls_normalized_count', 0)}"
            )

        # Build an operation-scoped report from the already validated
        # topology snapshot plus the lightweight execution refresh above.
        # Do NOT rerun the whole drawing after write-back.
        operation_report_map = {}

        def _report_key(source_file, change):
            return (
                str(source_file),
                str(change.get("region_index", "") or ""),
                str(change.get("feeder_id", "") or ""),
            )

        def _ensure_operation_report(source_file, change):
            key = _report_key(source_file, change)
            if key in operation_report_map:
                return operation_report_map[key]

            original = report_lookup.get((
                str(source_file),
                str(change.get("region_index", "") or ""),
            ), {}) or {}
            report = {
                k: v
                for k, v in original.items()
                if k != "feedline_rows"
            }
            report["feeder_id"] = change.get("feeder_id", report.get("feeder_id", ""))
            report["feeder_name"] = change.get("feeder_name", report.get("feeder_name", ""))
            report["report_type"] = "FEEDER"
            report["g_file"] = str(source_file)
            report["file_name"] = Path(source_file).name
            report["feedline_rows"] = []
            report["reason"] = "ASSOCIATION_EXECUTION_RESULT"
            report["status"] = "PASS"
            report["severity"] = "PASS"
            operation_report_map[key] = report
            return report

        applied_lookup = {}
        for source_file, changes in recalculated.items():
            for change in changes:
                applied_lookup[
                    (
                        str(source_file),
                        str(change.get("xml_id", "") or ""),
                    )
                ] = change
        for source_file, feeder_id in facid_writeback_by_file.items():
            applied_lookup[(str(source_file), "root")] = {
                "change_kind": "FEEDER_ROOT_FACID",
                "xml_id": "root",
                "tag": "G",
                "feeder_id": feeder_id,
                "device_id": feeder_id,
                "section_name": "G根节点 facID",
                "expected_keyid": "",
                "attributes": {"facID": str(feeder_id)},
                "validated_row": {
                    "object_type": "G",
                    "xml_id": "root",
                    "status": "PASS",
                    "severity": "PASS",
                    "reason": "FEEDER_ROOT_FACID_ASSOCIATION_EXECUTED",
                },
            }

        for source_file, selected_changes in changes_by_file.items():
            for selected in selected_changes or []:
                report = _ensure_operation_report(
                    source_file,
                    selected,
                )
                applied = applied_lookup.get(
                    (
                        str(source_file),
                        str(selected.get("xml_id", "") or ""),
                    )
                )
                if applied is not None:
                    row = dict(
                        applied.get("validated_row", {}) or {}
                    )
                    is_root_change = (
                        str(applied.get("change_kind", "")).upper()
                        == "FEEDER_ROOT_FACID"
                    )
                    row.update({
                        "status": "PASS",
                        "severity": "PASS",
                        "reason": "ASSOCIATION_EXECUTED_SUCCESS",
                        "model_linked": "YES",
                        "model_link_correct": "YES",
                        "current_keyid": applied.get(
                            "expected_keyid",
                            row.get("expected_keyid", ""),
                        ),
                        "current_device_id": applied.get(
                            "device_id",
                            row.get("assigned_device_id", ""),
                        ),
                        "current_feeder_id": applied.get(
                            "feeder_id",
                            row.get("current_feeder_id", ""),
                        ),
                        "current_table_id": ("" if is_root_change else section_table_id),
                        "current_domain": ("" if is_root_change else section_domain),
                        "current_section_name": applied.get(
                            "section_name",
                            row.get("assigned_section_name", ""),
                        ),
                        "current_bv_id": (
                            applied.get("attributes", {}) or {}
                        ).get("voltype", row.get("assigned_bv_id", "")),
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "_execution_result": "SUCCESS",
                    })
                else:
                    reason = next(
                        (
                            why
                            for change, why in skipped
                            if (
                                str(change.get("xml_id", ""))
                                == str(selected.get("xml_id", ""))
                                and str(
                                    change.get("region_index", "")
                                )
                                == str(
                                    selected.get("region_index", "")
                                )
                                and str(change.get("feeder_id", ""))
                                == str(selected.get("feeder_id", ""))
                            )
                        ),
                        "ASSOCIATION_EXECUTION_SKIPPED",
                    )
                    row = dict(
                        selected.get("validated_row", {}) or {}
                    )
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "reason": reason,
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "_execution_result": "SKIPPED",
                    })
                    report["status"] = "WARN"
                    report["severity"] = "PARTIAL"
                    report["reason"] = (
                        "ASSOCIATION_EXECUTION_PARTIAL_OR_SKIPPED"
                    )

                report["feedline_rows"].append(row)

        applied_count = sum(
            int(item.get("applied_count", 0))
            for item in results
        )
        selected_count = sum(
            len(v) for v in changes_by_file.values()
        )

        log_callback(
            f"本次馈线模型关联完成：选中对象={selected_count}，"
            f"成功={applied_count}，跳过={len(skipped)}，"
            f"数据库新增馈线段={database_created_count}。"
        )

        return {
            "output_g_dir": str(output_g_dir),
            "copied_files": [str(value) for value in copied.values()],
            "results": results,
            "selected_count": selected_count,
            "skipped_count": len(skipped),
            "applied_count": applied_count,
            "database_created_count": database_created_count,
            "operation_reports": list(
                operation_report_map.values()
            ),
            "rules": dict(preview_data.get("rules", {}) or {}),
        }
