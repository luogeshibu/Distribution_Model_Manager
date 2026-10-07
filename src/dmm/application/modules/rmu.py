
from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.constants import (
    RMU_LABEL_SEARCH_MAX_DISTANCE,
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
    RMU_RELAY_SIGNAL_CODE,
    RMU_RELAY_SIGNAL_DOMAIN,
    RMU_RELAY_SIGNAL_TABLE_ID,
    RMU_RELAY_SIGNAL_TAG,
    RMU_CHANNEL_STATUS_TABLE_ID,
    RMU_CHANNEL_STATUS_DOMAIN,
)
from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_RMU_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
    resolve_rmu_name_positions,
)
from dmm.domain.gfile.parser import GParser
from dmm.domain.graphics_cleanup.rmu_feeder_topology import analyze_rmu_feeder_topology_file
from dmm.domain.feeder.ring_discovery import discover_makkah_ring_feeders
from dmm.domain.rmu.validator import RmuValidator, KEYID_STEP, norm, int_or_none
from dmm.infrastructure.gfile.writeback import GWriteBackService

class RmuModelModule(ModelModule):
    module_id = "RMU"
    display_name = "RMU 环网柜模型"
    description = "RMU 环网柜模型校验、候选选择及安全回写。"
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    @staticmethod
    def _runtime_device_rules(settings):
        """Return editable RMU rules plus the EFI signal database rule.

        EFI G-symbol discovery comes from the Element Management classification
        RMU_PWBH_EFI.  The downstream database CODE/table/domain behavior is
        unchanged; table ID and domain remain operator-editable.
        """
        rules = dict(settings.get("_runtime_rules", {}) or {})
        configured = dict(
            rules.get(RMU_RELAY_SIGNAL_TAG)
            or (settings.get("device_rules", {}) or {}).get(
                RMU_RELAY_SIGNAL_TAG, {}
            )
        )
        relay_rule = {
            "table_id": RMU_RELAY_SIGNAL_TABLE_ID,
            "domain": RMU_RELAY_SIGNAL_DOMAIN,
            "match_mode": "FIXED_GFILE_EFI_INDICATOR",
            "description": (
                "图元分类 RMU_PWBH_EFI -> "
                "dms_relay_sig.CODE=EFI INDICATOR"
            ),
            "fixed_code": RMU_RELAY_SIGNAL_CODE,
            "voltype_required": False,
        }
        for key in ("table_id", "domain"):
            if key in configured:
                relay_rule[key] = int(configured[key])
        rules[RMU_RELAY_SIGNAL_TAG] = relay_rule
        return rules

    def _new_validator(self, db, settings, log_callback, feeder_context_by_frame=None):
        rules = self._runtime_device_rules(settings)
        parser = GParser(
            # RMU structure is a hard rule: the rectangle must contain all
            # three core G object types, regardless of configurable table IDs.
            required_rmu_tags={
                "CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"
            },
            label_regex=RMU_LABEL_PATTERN,
            max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
            overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
            excluded_rmu_name_strings=settings.get(
                "rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS
            ),
            exclude_numeric_decimal_rmu_names=True,
            exclude_phone_like_rmu_names=True,
            exclude_hyphenated_rmu_names=True,
            prefer_pure_numeric_rmu_names=False,
        )
        return RmuValidator(
            db,
            parser,
            rules,
            breaker_name_source="GRAPHICAL_TEXT",
            log=log_callback,
            element_catalog=settings.get("element_catalog", {}),
            feeder_context_by_frame=feeder_context_by_frame,
            force_rmu_feeder_correction=bool(
                settings.get("force_rmu_feeder_correction", False)
            ),
        )

    @staticmethod
    def _log_found_rmus(log_callback, report):
        """Write every detected RMU and its detected in-frame devices to Console."""
        if not log_callback:
            return
        for rmu_index, rmu in enumerate(report.get("rmu_results", []), start=1):
            rmu_name = str(rmu.get("rmu_name") or "").strip() or "<未找到名称>"
            frame_xml = str(rmu.get("frame_xml_id") or "").strip() or "-"
            rmu_id = str(rmu.get("rmu_id") or "").strip() or "-"
            status = str(rmu.get("rmu_status") or "").strip() or "-"
            eligible = "YES" if rmu.get("association_eligible") else "NO"
            reason = str(rmu.get("rmu_reason") or "").strip() or "-"
            log_callback(
                f"[RMU][找到设备] #{rmu_index} 名称={rmu_name}；"
                f"FrameXML={frame_xml}；DB_ID={rmu_id}；状态={status}；"
                f"可关联={eligible}；原因={reason}"
            )
            for device_index, row in enumerate(rmu.get("device_rows", []), start=1):
                if not row.get("xml_id"):
                    continue
                object_type = str(row.get("object_type") or "").strip() or "-"
                device_name = str(row.get("selected_device_name") or row.get("graphical_name") or "").strip() or "<未找到名称>"
                xml_id = str(row.get("xml_id") or "").strip() or "-"
                db_id = str(row.get("db_device_id") or "").strip() or "-"
                row_status = str(row.get("status") or "").strip() or "-"
                ready = str(row.get("association_ready") or "NO").strip() or "NO"
                row_reason = str(row.get("reason") or "").strip() or "-"
                log_callback(
                    f"[RMU][柜内设备] RMU={rmu_name} #{device_index} "
                    f"类型={object_type}；名称={device_name}；XML_ID={xml_id}；"
                    f"DB_ID={db_id}；状态={row_status}；可关联={ready}；"
                    f"原因={row_reason}"
                )

    @staticmethod
    def _norm_feeder_label(value):
        return "".join(ch for ch in str(value or "").upper() if ch.isalnum())

    def _build_rmu_feeder_context(self, db, g_file, settings, log_callback):
        """Map RMU frame XML IDs to topology-confirmed 13500 feeder IDs."""
        topology = analyze_rmu_feeder_topology_file(Path(g_file))
        feeders = discover_makkah_ring_feeders(
            db,
            Path(g_file),
            feeder_table_id=int(settings.get("feeder_table_id", 13500)),
            station_table_id=405,
            log_callback=None,
        )
        by_label = {}
        for feeder in feeders:
            label = self._norm_feeder_label(feeder.get("_ring_label") or feeder.get("display_name"))
            if label:
                by_label.setdefault(label, []).append(dict(feeder))

        context = {}
        for row in topology.get("rmu_rows", []):
            frame_id = str(row.get("frame_xml_id") or "").strip()
            primary = str(row.get("primary_feeder") or "").strip()
            status = str(row.get("status") or "").strip()
            ownership = str(row.get("ownership_status") or "").strip()
            item = {
                "topology_status": status,
                "ownership_status": ownership,
                "primary_feeder": primary,
                "feeder_id": None,
                "error": "",
            }
            if not primary or status in {"CONFLICT", "UNRESOLVED"}:
                item["error"] = (
                    f"RMU_FEEDER_TOPOLOGY_{status or 'UNRESOLVED'}: "
                    f"primary_feeder={primary or '-'}"
                )
            else:
                matches = by_label.get(self._norm_feeder_label(primary), [])
                if len(matches) == 1 and matches[0].get("id") not in (None, ""):
                    item["feeder_id"] = int(matches[0]["id"])
                    item["feeder_record"] = matches[0]
                else:
                    item["error"] = (
                        f"RMU_TOPOLOGY_FEEDER_DB_NOT_UNIQUE: feeder={primary}; "
                        f"count={len(matches)}"
                    )
            if frame_id:
                context[frame_id] = item
            log_callback(
                f"[RMU][所属馈线] FrameXML={frame_id or '-'}；"
                f"RMU={row.get('rmu_name') or '-'}；拓扑={status or '-'}；"
                f"馈线={primary or '-'}；FEEDER_ID={item.get('feeder_id') or '-'}；"
                f"结果={'PASS' if item.get('feeder_id') else item.get('error') or 'FAIL'}"
            )
        return context

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        # Makkah fixed RMU-name policy is authoritative in GParser: assign
        # RIGHT first, then BOTTOM for unresolved RMUs, then GLOBAL nearest
        # fallback, always within the parser's 300-unit hard limit.
        # RMU-specific lexical exclusions (NOP/SFI/DAS/OK, phone-like,
        # hyphenated and pure-decimal noise) remain in the parser.
        positions = ("top", "right", "global")
        reports = []
        aggregate = {
            "rmu_frames":0, "rmu_pass":0, "rmu_fail":0,
            "rmu_association_eligible":0,
            "elements":0, "element_pass":0, "element_warn":0, "element_fail":0,
        }
        total_files = max(len(files), 1)
        for idx, g_file in enumerate(files, start=1):
            log_callback(f"[{idx}/{len(files)}] 正在处理：{g_file.name}")
            feeder_context = self._build_rmu_feeder_context(
                db, g_file, settings, log_callback
            )
            validator = self._new_validator(
                db, settings, log_callback, feeder_context_by_frame=feeder_context
            )

            def _file_progress(current, total, message):
                if progress_callback:
                    fraction = (idx - 1 + (current / max(total, 1))) / total_files
                    # Module work occupies 5%~95% of the overall task.
                    percent = 5 + int(fraction * 90)
                    progress_callback(min(percent, 95), f"{g_file.name}：{message}")

            report = validator.validate_file(
                g_file,
                positions,
                progress_callback=_file_progress,
            )
            reports.append(report)
            self._log_found_rmus(log_callback, report)
            for key in aggregate:
                aggregate[key] += report["summary"].get(key, 0)
        return reports, aggregate, self._runtime_device_rules(settings)

    @staticmethod
    def _attributes_for_row(row):
        if row.get("association_kind") == "RMU_CHANNEL_STATUS":
            # Same Channel Status field pattern as the Jazan edition.  Domain
            # 40 is only for KeyID construction/verification; the graphical
            # Status object itself uses state=39 and voltype=-1.
            return {
                "app": "6600000",
                "voltype": "-1",
                "p_ReportType": "1",
                "state": "39",
                "keyid": str(row["expected_keyid"]),
            }

        if row.get("object_type") == RMU_RELAY_SIGNAL_TAG:
            # The classified RMU_PWBH_EFI pwbh stores the EFI value link in
            # slot 1. Keep the established downstream writeback unchanged.
            return {
                "app": "6500000",
                "app1": "6500000",
                "voltype1": "0",
                "p_ReportType1": "1",
                "state1": "41",
                "keyid1": str(row["expected_keyid"]),
            }

        bv_id = str(row.get("db_bv_id", "") or "").strip()
        if not bv_id:
            raise ValueError(
                f"{row.get('object_type')}:{row.get('xml_id')}: "
                "数据库 BV_ID 为空，禁止生成模型回写。"
            )

        attrs = {
            "app": "6500000",
            # voltype 必须使用当前实际匹配数据库设备的 BV_ID。
            "voltype": bv_id,
            "p_ReportType": "1",
            "keyid": str(row["expected_keyid"]),
        }
        if row["object_type"] == "BusDis":
            attrs["state"] = "15"
        else:
            attrs["state"] = "41"
        return attrs

    @staticmethod
    def _remove_attributes_for_row(row):
        if row.get("association_kind") == "RMU_CHANNEL_STATUS":
            # A few older field samples carried EFI slot-1 attributes on this
            # Status object.  Jazan cleans them during rewrite; Makkah now does
            # the same so the resulting Channel Status attributes are exact.
            return ["app1", "voltype1", "p_ReportType1", "state1", "keyid1"]
        return []

    def preview_association(self, db, files, settings, log_callback, progress_callback=None):
        reports, summary, rules = self.validate(db, files, settings, log_callback, progress_callback)
        changes_by_file = defaultdict(list)
        rows = []
        skipped_rmus = []

        for report in reports:
            g_file = report["g_file"]
            for rmu in report.get("rmu_results", []):
                if not rmu.get("association_eligible"):
                    skipped_rmus.append({
                        "g_file": g_file,
                        "rmu_name": rmu.get("rmu_name", ""),
                        "rmu_id": rmu.get("rmu_id", ""),
                        "reasons": rmu.get("association_block_reasons", []),
                    })
                    continue

                if (
                    rmu.get("feeder_correction_needed") == "YES"
                    and bool(settings.get("force_rmu_feeder_correction", False))
                ):
                    pseudo_xml = f"RMU_FEEDER:{rmu.get('frame_xml_id') or rmu.get('frame_index')}"
                    pseudo_row = {
                        "rmu_name": rmu.get("rmu_name", ""),
                        "rmu_id": rmu.get("rmu_id", ""),
                        "object_type": "RMU_FEEDER_ID",
                        "xml_id": pseudo_xml,
                        "logical_code": rmu.get("topology_primary_feeder", ""),
                        "selected_device_name": "RMU 所属馈线",
                        "db_code": str(rmu.get("current_rmu_feeder_id", "") or ""),
                        "db_device_id": rmu.get("rmu_id", ""),
                        "expected_keyid": "",
                        "current_keyid": "",
                        "model_linked": "YES",
                        "model_link_correct": "NO",
                        "model_link_status": "13501.FEEDER_ID 与图形拓扑不一致",
                        "association_action": "修正 13501.FEEDER_ID",
                        "writeback_needed": "YES",
                        "association_ready": "YES",
                        "status": "WARN",
                        "severity": "FEEDER_CORRECTION",
                        "reason": (
                            f"RMU_FEEDER_ID_CORRECTION: {rmu.get('current_rmu_feeder_id') or 'NULL'} "
                            f"-> {rmu.get('topology_feeder_id')} ({rmu.get('topology_primary_feeder')})"
                        ),
                        "topology_status": rmu.get("topology_status", ""),
                        "topology_primary_feeder": rmu.get("topology_primary_feeder", ""),
                        "topology_feeder_id": rmu.get("topology_feeder_id", ""),
                        "current_rmu_feeder_id": rmu.get("current_rmu_feeder_id", ""),
                        "feeder_correction_needed": "YES",
                        "db_only_action": "RMU_FEEDER_ID_CORRECTION",
                    }
                    rmu.setdefault("device_rows", []).append(pseudo_row)
                    changes_by_file[g_file].append({
                        "xml_id": pseudo_xml,
                        "tag": "RMU_FEEDER_ID",
                        "attributes": {},
                        "remove_attributes": [],
                        "rmu_name": rmu.get("rmu_name", ""),
                        "rmu_id": rmu.get("rmu_id", ""),
                        "device_name": "RMU 所属馈线",
                        "device_id": rmu.get("rmu_id", ""),
                        "expected_keyid": "",
                        "frame_index": rmu.get("frame_index", ""),
                        "validated_row": dict(pseudo_row),
                        "association_kind": "RMU_FEEDER_ID_CORRECTION",
                        "db_only_action": "RMU_FEEDER_ID_CORRECTION",
                        "topology_primary_feeder": rmu.get("topology_primary_feeder", ""),
                        "topology_feeder_id": rmu.get("topology_feeder_id", ""),
                        "current_rmu_feeder_id": rmu.get("current_rmu_feeder_id", ""),
                        "feeder_correction_needed": "YES",
                    })
                    rows.append(dict(pseudo_row))

                for row in rmu.get("device_rows", []):
                    if row.get("db_only_action") == "RMU_FEEDER_ID_CORRECTION":
                        continue
                    if not row.get("xml_id"):
                        continue
                    if row.get("association_ready") != "YES":
                        continue

                    # Correctly linked models are intentionally skipped.
                    if row.get("writeback_needed") != "YES":
                        if row.get("model_link_correct") == "YES":
                            log_callback(
                                f"无需关联：RMU={row.get('rmu_name')} "
                                f"{row.get('object_type')} "
                                f"{row.get('selected_device_name')} 已正确关联。"
                            )
                        continue

                    attrs = self._attributes_for_row(row)
                    change = {
                        "xml_id": row["xml_id"],
                        "tag": row["object_type"],
                        "attributes": attrs,
                        "remove_attributes": self._remove_attributes_for_row(row),
                        "rmu_name": row.get("rmu_name", ""),
                        "rmu_id": row.get("rmu_id", ""),
                        "device_name": row.get("selected_device_name", ""),
                        "device_id": row.get("db_device_id", ""),
                        "expected_keyid": row.get("expected_keyid", ""),
                        "frame_index": rmu.get("frame_index", ""),
                        # Preserve the exact validated device row so execution
                        # can re-check ONLY the selected database facts without
                        # rescanning every RMU/device in the G file.
                        "validated_row": dict(row),
                        "association_kind": row.get("association_kind", ""),
                        "topology_primary_feeder": rmu.get("topology_primary_feeder", ""),
                        "topology_feeder_id": rmu.get("topology_feeder_id", ""),
                        "current_rmu_feeder_id": rmu.get("current_rmu_feeder_id", ""),
                        "feeder_correction_needed": rmu.get("feeder_correction_needed", "NO"),
                    }
                    changes_by_file[g_file].append(change)

                    preview_row = dict(row)
                    if row.get("association_kind") == "RMU_CHANNEL_STATUS":
                        preview_row["reason"] = (
                            "PREVIEW_WRITE channel_status app=6600000 "
                            "voltype=-1 p_ReportType=1 state=39 "
                            f"keyid={attrs['keyid']}；table=13566 domain=40"
                        )
                    elif row.get("object_type") == RMU_RELAY_SIGNAL_TAG:
                        preview_row["reason"] = (
                            "PREVIEW_WRITE app1=6500000 voltype1=0 "
                            f"p_ReportType1=1 state1=41 "
                            f"keyid1={attrs['keyid1']}"
                        )
                    else:
                        preview_row["reason"] = (
                            f"PREVIEW_WRITE app=6500000 "
                            f"voltype={attrs['voltype']} p_ReportType=1 "
                            f"state={attrs['state']} keyid={attrs['keyid']}"
                        )
                    rows.append(preview_row)

        preview_summary = dict(summary)
        preview_summary["association_change_count"] = sum(len(v) for v in changes_by_file.values())
        preview_summary["association_skipped_rmu_count"] = len(skipped_rmus)
        preview_summary["already_linked_correct_count"] = sum(
            1
            for report in reports
            for rmu in report.get("rmu_results", [])
            for row in rmu.get("device_rows", [])
            if row.get("model_link_correct") == "YES"
        )

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

        return {
            "reports": reports,
            "rows": rows,
            "summary": preview_summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
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
                    settings.get("rmu_name_positions", DEFAULT_RMU_NAME_POSITIONS)
                ),
                "breaker_name_source": "GRAPHICAL_TEXT",
                "device_rules": dict(settings.get("device_rules", {})),
                "force_rmu_feeder_correction": bool(
                    settings.get("force_rmu_feeder_correction", False)
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
        """
        Apply only user-selected RMU devices.

        Full G/RMU validation is intentionally NOT repeated here.  The
        execution phase performs a lightweight database re-check only for the
        selected RMUs/devices, refreshes ID/BV_ID/Expected KeyID if the current
        database record changed, then writes the selected XML IDs in Workspace
        safety copies.
        """
        if not preview_data:
            raise RuntimeError("没有可执行的模型关联结果。")

        expected_snapshot = dict(
            preview_data.get("settings_snapshot", {}) or {}
        )
        # v3.6.6 removed the configurable switch-name source.  Normalize old
        # preview/settings snapshots so legacy P_NAME_STRING values cannot
        # falsely trigger a configuration-changed error.
        expected_snapshot["breaker_name_source"] = "GRAPHICAL_TEXT"

        current_snapshot = {
            "rmu_name_detection_mode": str(
                settings.get(
                    "rmu_name_detection_mode",
                    DEFAULT_RMU_NAME_DETECTION_MODE,
                )
                or DEFAULT_RMU_NAME_DETECTION_MODE
            ).upper(),
            "rmu_name_positions": dict(
                settings.get("rmu_name_positions", DEFAULT_RMU_NAME_POSITIONS)
            ),
            "breaker_name_source": "GRAPHICAL_TEXT",
            "device_rules": dict(settings.get("device_rules", {})),
            "force_rmu_feeder_correction": bool(
                settings.get("force_rmu_feeder_correction", False)
            ),
        }
        if current_snapshot != expected_snapshot:
            raise RuntimeError(
                "RMU 配置在模型校验后发生变化，请重新执行模型校验。"
            )

        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        changes_by_file = preview_data.get("changes_by_file", {}) or {}
        if not changes_by_file:
            raise RuntimeError("当前没有已选择的设备。")

        output_g_dir = Path(output_g_dir)
        output_g_dir.mkdir(parents=True, exist_ok=True)

        # Selected source files must still be unchanged since validation.
        for g_file, fingerprint in (
            preview_data.get("file_fingerprints", {}) or {}
        ).items():
            path = Path(g_file)
            stat = path.stat()
            if (
                stat.st_size != fingerprint.get("size")
                or stat.st_mtime_ns != fingerprint.get("mtime_ns")
            ):
                raise RuntimeError(
                    "G 文件在模型校验后发生变化，请重新校验："
                    f"{g_file}"
                )

        selected_count = sum(
            len(v) for v in changes_by_file.values()
        )
        selected_rmus = {
            str(change.get("rmu_name", "") or "")
            for changes in changes_by_file.values()
            for change in changes
        }
        selected_by_rmu = defaultdict(int)
        for _changes in changes_by_file.values():
            for _change in _changes:
                selected_by_rmu[str(_change.get("rmu_name", "") or "")] += 1
        started_rmus = set()
        log_callback(
            f"执行模型关联：仅复核已选择的 {len(selected_rmus)} 个环网柜、"
            f"{selected_count} 个设备，不再重新扫描整张 G 图。"
        )

        runtime_rules = self._runtime_device_rules(settings)
        rmu_cache = {}
        device_cache = {}
        executable = defaultdict(list)
        execution_rows = []

        def make_fail(change, base_row, reason):
            row = dict(base_row)
            row.update({
                "_execution_source_file": str(change.get("_source_file", "") or ""),
                "status": "FAIL",
                "severity": "ERROR",
                "reason": reason,
                "association_ready": "NO",
                "writeback_needed": "NO",
                "association_action": "执行时跳过",
                "model_link_status": "执行时数据库事实发生变化，未写回",
                "_execution_result": "SKIPPED",
            })
            execution_rows.append((change, row))
            log_callback(
                f"跳过：RMU={change.get('rmu_name')} "
                f"{change.get('tag')} "
                f"{change.get('device_name')}；{reason}"
            )

        # --------------------------------------------------------------
        # Optional 13501 FEEDER_ID correction.  The update is permitted only
        # when preview proved the already-linked RMU identity and the operator
        # explicitly enabled the dedicated force switch.
        # --------------------------------------------------------------
        force_feeder_fix = bool(settings.get("force_rmu_feeder_correction", False))
        corrected_rmus = set()
        database_update_count = 0
        for _changes in changes_by_file.values():
            for _change in _changes:
                if str(_change.get("feeder_correction_needed", "NO")) != "YES":
                    continue
                rmu_id = int_or_none(_change.get("rmu_id"))
                target_feeder = int_or_none(_change.get("topology_feeder_id"))
                old_feeder = int_or_none(_change.get("current_rmu_feeder_id"))
                key = (rmu_id, target_feeder)
                if key in corrected_rmus:
                    continue
                if not force_feeder_fix:
                    raise RuntimeError(
                        f"RMU={_change.get('rmu_name')} 当前所属馈线与拓扑不一致；"
                        "请开启【强制修正已关联 RMU 所属馈线】后重新校验。"
                    )
                if rmu_id is None or target_feeder is None:
                    raise RuntimeError(
                        f"RMU={_change.get('rmu_name')} 缺少有效 RMU_ID/目标 FEEDER_ID，禁止修改数据库。"
                    )
                updated = db.update_rmu_feeder_id(rmu_id, old_feeder, target_feeder)
                corrected_rmus.add(key)
                database_update_count += 1
                log_callback(
                    f"[RMU][FEEDER_ID修正] RMU={_change.get('rmu_name')}；ID={rmu_id}；"
                    f"{old_feeder if old_feeder is not None else 'NULL'} -> {target_feeder}；"
                    f"结果={updated.get('feeder_id')}"
                )

        # --------------------------------------------------------------
        # Lightweight DB re-check: only selected devices.
        # --------------------------------------------------------------
        for source_file, changes in changes_by_file.items():
            for original_change in changes:
                change = dict(original_change)
                change["_source_file"] = str(source_file)
                base_row = dict(change.get("validated_row", {}) or {})
                if change.get("db_only_action") == "RMU_FEEDER_ID_CORRECTION":
                    db_row = dict(base_row)
                    db_row.update({
                        "_execution_source_file": str(source_file),
                        "status": "PASS",
                        "severity": "PASS",
                        "reason": "RMU_FEEDER_ID_CORRECTION_SUCCESS",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "association_action": "已修正 13501.FEEDER_ID",
                        "model_link_status": "数据库所属馈线已按图形拓扑修正",
                        "_execution_result": "SUCCESS",
                    })
                    execution_rows.append((change, db_row))
                    continue
                rmu_name = str(
                    change.get("rmu_name")
                    or base_row.get("rmu_name")
                    or ""
                ).strip()
                tag = str(change.get("tag", "") or "")
                logical_name = str(
                    base_row.get("logical_code")
                    or change.get("device_name")
                    or ""
                ).strip()

                if rmu_name not in started_rmus:
                    started_rmus.add(rmu_name)
                    log_callback(
                        f"正在执行环网柜模型关联：RMU={rmu_name}；"
                        f"已选设备={selected_by_rmu.get(rmu_name, 0)}"
                    )

                expected_feeder_id = int_or_none(
                    change.get("topology_feeder_id") or base_row.get("topology_feeder_id")
                )
                cache_key = (rmu_name, expected_feeder_id)
                if cache_key not in rmu_cache:
                    try:
                        rmu_cache[cache_key] = db.get_rmu_records(
                            rmu_name, feeder_id=expected_feeder_id
                        ) if expected_feeder_id is not None else db.get_rmu_records(rmu_name)
                    except TypeError:
                        rows = db.get_rmu_records(rmu_name)
                        rmu_cache[cache_key] = [
                            r for r in rows
                            if expected_feeder_id is None
                            or int_or_none(r.get("feeder_id")) == expected_feeder_id
                        ]
                    log_callback(
                        f"复核环网柜 {rmu_name}：FEEDER_ID={expected_feeder_id or '-'}；"
                        f"数据库记录数={len(rmu_cache[cache_key])}"
                    )

                rmu_records = rmu_cache[cache_key]

                if len(rmu_records) != 1:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_RMU_NOT_UNIQUE: 当前记录数={len(rmu_records)}",
                    )
                    continue

                rmu_id = int_or_none(rmu_records[0].get("id"))
                if rmu_id is None:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_RMU_ID_INVALID",
                    )
                    continue

                association_kind = str(
                    change.get("association_kind")
                    or base_row.get("association_kind")
                    or ""
                )
                if association_kind == "RMU_CHANNEL_STATUS":
                    # Same execution-time recheck as Jazan after the Makkah
                    # RMU has been uniquely resolved.  Re-run the exact channel
                    # SQL so a stale preview can never write an old KeyID.
                    try:
                        channel_rows = db.get_channel_status_keyids_by_combined_id(rmu_id)
                    except Exception as exc:
                        make_fail(
                            change,
                            base_row,
                            f"EXEC_CHANNEL_STATUS_QUERY_FAILED: {exc}",
                        )
                        continue
                    if len(channel_rows) != 1:
                        make_fail(
                            change,
                            base_row,
                            "EXEC_CHANNEL_STATUS_NOT_UNIQUE: "
                            f"RMU_ID={rmu_id}, count={len(channel_rows)}",
                        )
                        continue

                    channel_row = channel_rows[0]
                    expected_keyid = int_or_none(channel_row.get("new_id"))
                    if expected_keyid is None:
                        make_fail(
                            change,
                            base_row,
                            "EXEC_CHANNEL_STATUS_KEYID_INVALID",
                        )
                        continue
                    channel_id = int_or_none(channel_row.get("channel_id"))
                    if channel_id is None:
                        make_fail(
                            change,
                            base_row,
                            "EXEC_CHANNEL_STATUS_CHANNEL_ID_INVALID",
                        )
                        continue
                    try:
                        verified = db.verify_keyid(expected_keyid) or {}
                    except Exception as exc:
                        make_fail(
                            change,
                            base_row,
                            f"EXEC_CHANNEL_STATUS_KEYID_VERIFY_ERROR: {exc}",
                        )
                        continue
                    if not (
                        int_or_none(verified.get("device_id")) == channel_id
                        and int_or_none(verified.get("tab_no")) == RMU_CHANNEL_STATUS_TABLE_ID
                        and int_or_none(verified.get("col_no")) == RMU_CHANNEL_STATUS_DOMAIN
                    ):
                        make_fail(
                            change,
                            base_row,
                            "EXEC_CHANNEL_STATUS_KEYID_VERIFY_FAILED: "
                            f"device={verified.get('device_id')} "
                            f"table={verified.get('tab_no')} "
                            f"domain={verified.get('col_no')}",
                        )
                        continue

                    refreshed_row = dict(base_row)
                    refreshed_row.update({
                        "_execution_source_file": str(source_file),
                        "rmu_id": rmu_id,
                        "db_device_id": channel_id,
                        "db_code": str(channel_row.get("chan_name") or "").strip(),
                        "db_name": str(channel_row.get("chan_name") or "").strip(),
                        "db_combined_id": rmu_id,
                        "table_id": RMU_CHANNEL_STATUS_TABLE_ID,
                        "table_name": "dms_channel_info",
                        "configured_domain": RMU_CHANNEL_STATUS_DOMAIN,
                        "expected_keyid": expected_keyid,
                        "expected_keyid_verified": "YES",
                        "status": "PASS",
                        "severity": "PASS",
                        "reason": "ASSOCIATION_WRITE_READY",
                        "association_ready": "YES",
                        "writeback_needed": "YES",
                        "association_action": "准备执行",
                        "_execution_result": "READY",
                    })
                    refreshed_change = dict(change)
                    refreshed_change["attributes"] = self._attributes_for_row(refreshed_row)
                    refreshed_change["remove_attributes"] = self._remove_attributes_for_row(refreshed_row)
                    refreshed_change["device_id"] = channel_id
                    refreshed_change["expected_keyid"] = expected_keyid
                    refreshed_change["rmu_id"] = rmu_id
                    refreshed_change["validated_row"] = refreshed_row
                    executable[str(source_file)].append(refreshed_change)
                    execution_rows.append((refreshed_change, refreshed_row))
                    continue

                rule = runtime_rules.get(tag)
                if not rule:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_RULE_NOT_FOUND: {tag}",
                    )
                    continue

                table_id = int(rule["table_id"])
                domain = int(rule["domain"])
                cache_key = (rmu_id, table_id)

                if cache_key not in device_cache:
                    if tag == RMU_RELAY_SIGNAL_TAG:
                        device_cache[cache_key] = (
                            db.get_relay_signals_by_combined_id(
                                rmu_id,
                                RMU_RELAY_SIGNAL_CODE,
                                table_id=table_id,
                            )
                        )
                    else:
                        device_cache[cache_key] = (
                            db.get_devices_by_combined_id(
                                table_id,
                                rmu_id,
                            )
                        )

                table_name, db_rows = device_cache[cache_key]
                matches = [
                    db_row
                    for db_row in db_rows
                    if norm(db_row.get("code")) == logical_name
                ]

                if len(matches) == 0:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_DEVICE_NOT_FOUND: CODE={logical_name}",
                    )
                    continue
                if len(matches) > 1:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_DEVICE_CODE_DUPLICATE: CODE={logical_name}, "
                        f"count={len(matches)}",
                    )
                    continue

                dev = matches[0]
                if norm(dev.get("code")) != logical_name:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_CODE_LOGICAL_MISMATCH: "
                        f"CODE={norm(dev.get('code'))}, "
                        f"图上逻辑名称={logical_name}",
                    )
                    continue

                if int_or_none(dev.get("combined_id")) != rmu_id:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_DEVICE_RMU_MISMATCH",
                    )
                    continue

                device_id = int_or_none(dev.get("id"))
                bv_id = str(dev.get("bv_id", "") or "").strip()
                if device_id is None:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_DEVICE_ID_INVALID",
                    )
                    continue
                if tag != RMU_RELAY_SIGNAL_TAG and not bv_id:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_BV_ID_EMPTY",
                    )
                    continue

                expected_keyid = (
                    int(device_id) + int(domain) * KEYID_STEP
                )
                try:
                    verified = db.verify_keyid(expected_keyid)
                    verified_ok = (
                        int_or_none(verified.get("device_id"))
                        == device_id
                        and int_or_none(verified.get("tab_no"))
                        == table_id
                        and int_or_none(verified.get("col_no"))
                        == domain
                    )
                except Exception as exc:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_EXPECTED_KEYID_VERIFY_ERROR: {exc}",
                    )
                    continue

                if not verified_ok:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_EXPECTED_KEYID_VERIFY_FAILED",
                    )
                    continue

                refreshed_row = dict(base_row)
                refreshed_row.update({
                    "_execution_source_file": str(source_file),
                    "rmu_id": rmu_id,
                    "db_device_id": device_id,
                    "db_code": norm(dev.get("code")),
                    "db_name": norm(dev.get("name")),
                    "db_combined_id": int_or_none(
                        dev.get("combined_id")
                    ),
                    "db_bv_id": bv_id,
                    "expected_keyid": expected_keyid,
                    "expected_keyid_verified": "YES",
                    "table_id": table_id,
                    "table_name": table_name,
                    "configured_domain": domain,
                    "status": "PASS",
                    "severity": "PASS",
                    "reason": "ASSOCIATION_WRITE_READY",
                    "association_ready": "YES",
                    "writeback_needed": "YES",
                    "association_action": "准备执行",
                    "_execution_result": "READY",
                })

                refreshed_change = dict(change)
                refreshed_change["attributes"] = (
                    self._attributes_for_row(refreshed_row)
                )
                refreshed_change["device_id"] = device_id
                refreshed_change["expected_keyid"] = expected_keyid
                refreshed_change["rmu_id"] = rmu_id
                refreshed_change["validated_row"] = refreshed_row

                executable[str(source_file)].append(
                    refreshed_change
                )
                execution_rows.append(
                    (refreshed_change, refreshed_row)
                )

                old_id = int_or_none(change.get("device_id"))
                if old_id != device_id:
                    log_callback(
                        f"数据库设备已更新：RMU={rmu_name} "
                        f"{tag} {logical_name}，"
                        f"DeviceID {old_id} -> {device_id}"
                    )

        # --------------------------------------------------------------
        # Copy only files that still have selected valid devices.
        # --------------------------------------------------------------
        source_map = {
            str(Path(f).resolve()): Path(f)
            for f in files
        }
        copied = {}

        for source_file, changes in executable.items():
            if not changes:
                continue
            source = source_map.get(
                str(Path(source_file).resolve()),
                Path(source_file),
            )
            target = output_g_dir / source.name

            if target.exists():
                index = 2
                while True:
                    candidate = (
                        output_g_dir
                        / f"{source.stem}_{index}{source.suffix}"
                    )
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1

            log_callback(
                f"正在复制 G 文件到安全输出目录：{source.name}"
            )
            shutil.copy2(source, target)
            copied[str(source.resolve())] = target
            log_callback(
                f"安全复制 G 文件：{source.name} -> {target}"
            )

        # --------------------------------------------------------------
        # Precise XML-ID write-back only.
        # --------------------------------------------------------------
        service = GWriteBackService(log=log_callback)
        results = []
        success_keys = set()

        for source_file, changes in executable.items():
            target = copied.get(
                str(Path(source_file).resolve())
            )
            if target is None or not changes:
                continue

            log_callback(
                f"正在回写 G 文件安全副本：{target.name}；"
                f"待写设备数={len(changes)}"
            )
            result = service.apply_attribute_changes(
                target,
                changes,
                create_backup=False,
            )
            result["source_g_file"] = str(source_file)
            result["output_g_file"] = str(target)
            results.append(result)

            for change in changes:
                success_keys.add((
                    str(source_file),
                    str(change.get("tag", "")),
                    str(change.get("xml_id", "")),
                ))

            log_callback(
                f"写回完成：{target.name}；"
                f"修改设备数={result.get('applied_count', 0)}"
            )

        # Mark execution rows.
        for change, row in execution_rows:
            if row.get("_execution_result") != "READY":
                continue
            key = (
                str(
                    next(
                        (
                            source_file
                            for source_file, changes
                            in executable.items()
                            if change in changes
                        ),
                        "",
                    )
                ),
                str(change.get("tag", "")),
                str(change.get("xml_id", "")),
            )
            if key in success_keys:
                row.update({
                    "status": "PASS",
                    "severity": "PASS",
                    "reason": "ASSOCIATION_WRITE_SUCCESS",
                    "model_linked": "YES",
                    "model_link_correct": "YES",
                    "model_link_status": "本次模型关联成功",
                    "association_action": "已完成",
                    "writeback_needed": "NO",
                    "_execution_result": "SUCCESS",
                })

        # --------------------------------------------------------------
        # Build compact reports: selected RMUs/devices only.
        # --------------------------------------------------------------
        report_map = {}

        for source_file, changes in changes_by_file.items():
            report = {
                "g_file": str(source_file),
                "file_name": Path(source_file).name,
                "rmu_results": [],
            }
            rmu_map = {}

            for change in changes:
                rmu_name = str(
                    change.get("rmu_name", "") or ""
                )
                frame_index = change.get("frame_index", "")
                rmu_key = (frame_index, rmu_name)

                if rmu_key not in rmu_map:
                    records = next((
                        value for (name, _feeder), value in rmu_cache.items()
                        if name == rmu_name
                    ), [])
                    rmu_map[rmu_key] = {
                        "frame_index": frame_index,
                        "frame_xml_id": "",
                        "rmu_name": rmu_name,
                        "rmu_status": "PASS",
                        "rmu_severity": "PASS",
                        "rmu_reason": "ASSOCIATION_EXECUTED",
                        "rmu_db_count": len(records),
                        "rmu_records": records,
                        "rmu_ids": [
                            int_or_none(rec.get("id"))
                            for rec in records
                            if int_or_none(rec.get("id"))
                            is not None
                        ],
                        "rmu_id": (
                            int_or_none(records[0].get("id"))
                            if len(records) == 1
                            else ""
                        ),
                        "device_rows": [],
                        "db_inventory": {},
                        "g_inventory": {},
                        "inventory_issues": [],
                        "db_integrity_issues": [],
                        "association_eligible": (
                            len(records) == 1
                        ),
                        "association_block_reasons": [],
                        "device_block_reasons": [],
                        "label_candidates": [],
                    }
                    report["rmu_results"].append(
                        rmu_map[rmu_key]
                    )

                # Find the execution row for this selected XML.
                selected_row = None
                for exec_change, exec_row in execution_rows:
                    if (
                        str(exec_change.get("_source_file", ""))
                        == str(source_file)
                        and str(exec_change.get("xml_id", ""))
                        == str(change.get("xml_id", ""))
                        and str(exec_change.get("tag", ""))
                        == str(change.get("tag", ""))
                        and str(
                            exec_change.get("rmu_name", "")
                        )
                        == rmu_name
                    ):
                        selected_row = exec_row
                        break

                if selected_row is None:
                    selected_row = dict(
                        change.get("validated_row", {}) or {}
                    )

                rmu_map[rmu_key]["device_rows"].append(
                    selected_row
                )

            for rmu in report["rmu_results"]:
                rows = rmu["device_rows"]
                success = sum(
                    1
                    for row in rows
                    if row.get("_execution_result") == "SUCCESS"
                )
                fail = len(rows) - success

                if fail == 0:
                    rmu["rmu_status"] = "PASS"
                    rmu["rmu_severity"] = "PASS"
                    rmu["rmu_reason"] = (
                        "ASSOCIATION_EXECUTED_SUCCESS"
                    )
                elif success:
                    rmu["rmu_status"] = "WARN"
                    rmu["rmu_severity"] = "PARTIAL"
                    rmu["rmu_reason"] = (
                        "ASSOCIATION_EXECUTED_PARTIAL_SUCCESS"
                    )
                else:
                    rmu["rmu_status"] = "FAIL"
                    rmu["rmu_severity"] = "ERROR"
                    rmu["rmu_reason"] = (
                        "ASSOCIATION_EXECUTION_FAILED"
                    )

            if report["rmu_results"]:
                report_map[str(source_file)] = report

        g_applied_count = sum(
            int(result.get("applied_count", 0))
            for result in results
        )
        applied_count = g_applied_count + database_update_count
        skipped_count = sum(
            1
            for _, row in execution_rows
            if row.get("_execution_result") == "SKIPPED"
        )

        log_callback(
            f"本次模型关联完成：选中={selected_count}，"
            f"成功={applied_count}，跳过={skipped_count}。"
        )

        return {
            "output_g_dir": str(output_g_dir),
            "copied_files": [
                str(path) for path in copied.values()
            ],
            "results": results,
            "applied_count": applied_count,
            "g_applied_count": g_applied_count,
            "database_update_count": database_update_count,
            "skipped_count": skipped_count,
            "selected_count": selected_count,
            "operation_reports": list(report_map.values()),
            "rules": dict(runtime_rules),
        }
