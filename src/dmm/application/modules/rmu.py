
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
)
from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
    DEFAULT_RMU_PROTECTION_SCOPE,
    resolve_rmu_name_positions,
)
from dmm.domain.gfile.parser import GParser
from dmm.domain.gfile.element_catalog import classification_is
from dmm.domain.rmu.validator import RmuValidator, KEYID_STEP, norm, int_or_none
from dmm.application.modules.jeddah_scope import apply_association_block
from dmm.application.modules.feeder_context import resolve_drawing_feeder
from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier
from dmm.infrastructure.gfile.writeback import GWriteBackService

class RmuModelModule(ModelModule):
    module_id = "RMU"
    display_name = "RMU 环网柜模型"
    description = "RMU 环网柜模型校验、候选选择及安全回写。"
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    @staticmethod
    def _block_duplicate_graph_names(report):
        """Block every RMU when the same graphical RMU name repeats in one G file."""
        grouped = defaultdict(list)
        for rmu in report.get("rmu_results", []) or []:
            name = norm(rmu.get("rmu_name"))
            if name:
                grouped[name].append(rmu)

        for name, rmus in grouped.items():
            if len(rmus) <= 1:
                continue
            reason = (
                "RMU_DUPLICATE_GRAPH_NAME: 当前 G 图中环网柜名称重复，"
                f"名称={name}，出现次数={len(rmus)}；禁止这些环网柜关联。"
            )
            for rmu in rmus:
                rmu["association_eligible"] = False
                rmu["rmu_status"] = "FAIL"
                rmu["rmu_severity"] = "ERROR"
                rmu["rmu_reason"] = reason
                if reason not in rmu.setdefault("association_block_reasons", []):
                    rmu["association_block_reasons"].append(reason)
                apply_association_block(
                    rmu.get("device_rows", []),
                    reason,
                )

        rmus = report.get("rmu_results", []) or []
        summary = report.get("summary", {}) or {}
        summary.update({
            "rmu_pass": sum(1 for r in rmus if r.get("rmu_status") == "PASS"),
            "rmu_fail": sum(1 for r in rmus if r.get("rmu_status") == "FAIL"),
            "rmu_association_eligible": sum(
                1 for r in rmus if r.get("association_eligible")
            ),
            "element_pass": sum(
                1 for r in rmus for row in r.get("device_rows", [])
                if row.get("status") == "PASS"
            ),
            "element_warn": sum(
                1 for r in rmus for row in r.get("device_rows", [])
                if row.get("status") in ("WARN", "RELINK", "RMU_RELINK")
            ),
            "element_fail": sum(
                1 for r in rmus for row in r.get("device_rows", [])
                if row.get("status") in ("FAIL", "RMU_LINK", "BLOCKED")
            ),
        })
        report["summary"] = summary

    @staticmethod
    def _runtime_device_rules(settings):
        """Return editable RMU rules plus the classification-driven EFI rule.

        EFI graphics are discovered from the RMU_PWBH_EFI element mark; the
        concrete element-definition file name is intentionally not fixed.
        Table ID and domain remain operator-editable association settings.
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
            "match_mode": "ELEMENT_CLASSIFICATION_EFI_INDICATOR",
            "description": (
                "element classification RMU_PWBH_EFI -> "
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

    def _new_validator(self, db, settings, log_callback):
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
        )
        return RmuValidator(
            db,
            parser,
            rules,
            breaker_name_source="GRAPHICAL_TEXT",
            protection_scope=settings.get(
                "rmu_protection_scope", DEFAULT_RMU_PROTECTION_SCOPE
            ),
            element_catalog=settings.get("element_catalog", {}) or {},
            log=log_callback,
        )

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        # Jeddah hard rule: RMU cabinet names are frame-external TOP labels only.
        # Right/left/bottom/global fallback is forbidden; missing TOP means FAIL.
        positions = ("top",)
        validator = self._new_validator(db, settings, log_callback)
        marked_records = [
            rec for rec in ((settings.get("element_catalog", {}) or {}).get("records", []) or [])
            if isinstance(rec, dict)
            and classification_is(rec, "RMU_PWBH_EFI")
        ]
        log_callback(
            "RMU 保护/EFI 分类标记：RMU_PWBH_EFI；"
            f"已加载标记图元记录={len(marked_records)}；"
            "运行时按当前 G devref 精确匹配任意一条标记记录，不依赖具体图元文件名。"
        )
        reports = []
        aggregate = {
            "rmu_frames":0, "rmu_pass":0, "rmu_fail":0,
            "rmu_association_eligible":0,
            "elements":0, "element_pass":0, "element_warn":0, "element_fail":0,
        }
        total_files = max(len(files), 1)
        for idx, g_file in enumerate(files, start=1):
            log_callback(f"[{idx}/{len(files)}] 正在处理：{g_file.name}")

            def _file_progress(current, total, message):
                if progress_callback:
                    fraction = (idx - 1 + (current / max(total, 1))) / total_files
                    # Module work occupies 5%~95% of the overall task.
                    percent = 5 + int(fraction * 90)
                    progress_callback(min(percent, 95), f"{g_file.name}：{message}")

            # Jeddah hard rule: the G filename is the one and only feeder
            # source for every RMU drawing.  Drawing topology and any device
            # (RMU / breaker / transformer / facID) never choose or override
            # the feeder.
            parsed_for_feeder = validator.parser.parse(g_file)
            drawing_profile = FeederDrawingTopologyClassifier().classify(
                parsed_for_feeder
            )
            drawing_type = str(
                drawing_profile.get("drawing_type") or "AMBIGUOUS"
            ).upper()
            feeder_resolution = resolve_drawing_feeder(
                db,
                parsed_for_feeder,
                settings,
                log_callback=log_callback,
            )
            required_feeder_id = (
                int_or_none(feeder_resolution.get("feeder_id"))
                if feeder_resolution.get("ready")
                else None
            )

            report = validator.validate_file(
                g_file,
                positions,
                progress_callback=_file_progress,
                required_feeder_id=required_feeder_id,
            )
            report["drawing_type"] = drawing_type
            report["feeder_context_required"] = "YES"

            feeder = feeder_resolution.get("feeder") or {}
            feeder_db_name = str(feeder.get("name") or feeder.get("code") or "").strip()
            feeder_full_name = str(feeder.get("display_name") or "").strip()
            if not feeder_full_name:
                feeder_full_name = " ".join(
                    value for value in (
                        str(feeder.get("subcontrolarea_path") or "").strip(),
                        str(feeder.get("station_name") or "").strip(),
                        feeder_db_name,
                    ) if value
                ).strip()
            if not feeder_full_name:
                feeder_full_name = feeder_db_name
            report.update({
                "feeder_context_ready": (
                    "YES" if feeder_resolution.get("ready") else "NO"
                ),
                "feeder_context_message": (
                    feeder_resolution.get("reason")
                    or "图级馈线已由 G 文件名 → 405/substation → 13500/dms_feeder_device 唯一确定。"
                ),
                "feeder_resolution_source": feeder_resolution.get(
                    "feeder_source", ""
                ),
                "feeder_resolution_evidence": feeder_resolution.get(
                    "feeder_evidence", ""
                ),
                "feeder_id": feeder_resolution.get("feeder_id") or "",
                # Operator/report-facing feeder name must use the complete
                # database-verified hierarchy whenever Oracle exposes it, e.g.
                # ``JED CTL ADF AH334``.  Keep the raw 13500 NAME separately
                # so reports can show both the business path and AH334 itself.
                "subcontrolarea_path": str(feeder.get("subcontrolarea_path") or "").strip(),
                "station_name": str(feeder.get("station_name") or "").strip(),
                "feeder_db_name": feeder_db_name,
                "feeder_code": str(feeder.get("code") or "").strip(),
                "feeder_graph_name": str(feeder.get("graph_name") or "").strip(),
                "feeder_name": feeder_full_name,
                "feeder_path": feeder_full_name,
                "graph_feeder_ids": [
                    feeder_resolution.get("feeder_id")
                ] if feeder_resolution.get("feeder_id") is not None else [],
            })
            for rmu in report.get("rmu_results", []) or []:
                rmu.update({
                    "feeder_resolution_source": report.get(
                        "feeder_resolution_source", ""
                    ),
                    "feeder_resolution_evidence": report.get(
                        "feeder_resolution_evidence", ""
                    ),
                    "feeder_id": report.get("feeder_id", ""),
                    "subcontrolarea_path": report.get("subcontrolarea_path", ""),
                    "station_name": report.get("station_name", ""),
                    "feeder_db_name": report.get("feeder_db_name", ""),
                    "feeder_code": report.get("feeder_code", ""),
                    "feeder_graph_name": report.get("feeder_graph_name", ""),
                    "feeder_name": report.get("feeder_name", ""),
                    "feeder_path": report.get("feeder_path", ""),
                })
                for row in rmu.get("device_rows", []) or []:
                    row.setdefault(
                        "feeder_resolution_source",
                        report.get("feeder_resolution_source", ""),
                    )
                    row.setdefault("feeder_id", report.get("feeder_id", ""))
                    row.setdefault("subcontrolarea_path", report.get("subcontrolarea_path", ""))
                    row.setdefault("station_name", report.get("station_name", ""))
                    row.setdefault("feeder_db_name", report.get("feeder_db_name", ""))
                    row.setdefault("feeder_code", report.get("feeder_code", ""))
                    row.setdefault("feeder_graph_name", report.get("feeder_graph_name", ""))
                    row.setdefault("feeder_name", report.get("feeder_name", ""))
                    row.setdefault("feeder_path", report.get("feeder_path", ""))

            if not feeder_resolution.get("ready"):
                reason = (
                    "RMU_GRAPH_FEEDER_NOT_RESOLVED: 文件名必须先唯一确定图级馈线；"
                    + str(
                        feeder_resolution.get("reason")
                        or "馈线不存在，请检查该图的馈线是否已创建。"
                    )
                )
                for rmu in report.get("rmu_results", []) or []:
                    rmu["association_eligible"] = False
                    rmu["rmu_status"] = "FAIL"
                    rmu["rmu_severity"] = "ERROR"
                    rmu["rmu_reason"] = reason
                    if reason not in rmu.setdefault(
                        "association_block_reasons", []
                    ):
                        rmu["association_block_reasons"].append(reason)
                    apply_association_block(
                        rmu.get("device_rows", []), reason
                    )

            self._block_duplicate_graph_names(report)
            for rmu in report.get("rmu_results", []) or []:
                candidate = next((
                    item for item in (rmu.get("label_candidates", []) or [])
                    if item.get("selected_by_rule") == "YES"
                ), None) or ((rmu.get("label_candidates", []) or [{}])[0])
                log_callback(
                    f"[发现环网柜] 文件={Path(g_file).name}；"
                    f"名称={rmu.get('rmu_name') or '-'}；"
                    f"方向={candidate.get('directions') or '-'}；"
                    f"距离={candidate.get('distance') if candidate.get('distance') not in (None, '') else '-'}；"
                    f"框XML_ID={rmu.get('frame_xml_id') or '-'}；"
                    f"数据库匹配={rmu.get('rmu_db_count', 0)}；"
                    f"RMU_ID={(rmu.get('rmu_ids') or ['-'])[0] if rmu.get('rmu_ids') else '-'}。"
                )
            reports.append(report)
            for key in aggregate:
                aggregate[key] += report["summary"].get(key, 0)
        return reports, aggregate, self._runtime_device_rules(settings)

    @staticmethod
    def _attributes_for_row(row):
        if row.get("policy_clear_link") == "YES":
            attrs = dict(row.get("policy_clear_attributes", {}) or {})
            if not attrs:
                raise ValueError(
                    f"{row.get('object_type')}:{row.get('xml_id')}: "
                    "策略要求清除保护/EFI关联，但未找到可安全清空的现有属性。"
                )
            return attrs

        if row.get("object_type") == RMU_RELAY_SIGNAL_TAG:
            # RMU_PWBH_EFI signals store the EFI value link in slot 1. Keep the
            # same field mapping already used by the site model.
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

                for row in rmu.get("device_rows", []):
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
                        "mandatory_policy_change": (
                            row.get("mandatory_policy_change") == "YES"
                        ),
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
                    }
                    changes_by_file[g_file].append(change)

                    preview_row = dict(row)
                    if row.get("policy_clear_link") == "YES":
                        preview_row["reason"] = (
                            "PREVIEW_POLICY_CLEAR_NONSMART_EFI: "
                            + ", ".join(f"{k}={v!r}" for k, v in attrs.items())
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
                "rmu_name_detection_mode": "FIXED",
                "rmu_name_positions": {"top": True, "right": False, "left": False, "bottom": False, "global": False},
                "rmu_protection_scope": str(
                    settings.get("rmu_protection_scope", DEFAULT_RMU_PROTECTION_SCOPE)
                    or DEFAULT_RMU_PROTECTION_SCOPE
                ).strip().upper(),
                "breaker_name_source": "GRAPHICAL_TEXT",
                "device_rules": dict(settings.get("device_rules", {})),
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
        # RMU cabinet-name direction is a fixed engineering rule rather than a
        # user setting. Normalize every preview snapshot to the current TOP-only
        # rule so cached legacy direction settings can never widen recognition.
        expected_snapshot["rmu_name_detection_mode"] = "FIXED"
        expected_snapshot["rmu_name_positions"] = {
            "top": True, "right": False, "left": False,
            "bottom": False, "global": False,
        }
        expected_snapshot.setdefault(
            "rmu_protection_scope",
            str(
                settings.get("rmu_protection_scope", DEFAULT_RMU_PROTECTION_SCOPE)
                or DEFAULT_RMU_PROTECTION_SCOPE
            ).strip().upper(),
        )

        current_snapshot = {
            "rmu_name_detection_mode": "FIXED",
            "rmu_name_positions": {"top": True, "right": False, "left": False, "bottom": False, "global": False},
            "rmu_protection_scope": str(
                settings.get("rmu_protection_scope", DEFAULT_RMU_PROTECTION_SCOPE)
                or DEFAULT_RMU_PROTECTION_SCOPE
            ).strip().upper(),
            "breaker_name_source": "GRAPHICAL_TEXT",
            "device_rules": dict(settings.get("device_rules", {})),
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
        rmu_total_count_cache = {}
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
        # Lightweight DB re-check: only selected devices.
        # --------------------------------------------------------------
        for source_file, changes in changes_by_file.items():
            for original_change in changes:
                change = dict(original_change)
                change["_source_file"] = str(source_file)
                base_row = dict(change.get("validated_row", {}) or {})
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

                validated_feeder_id = int_or_none(
                    base_row.get("required_feeder_id")
                    or base_row.get("feeder_id")
                )
                if validated_feeder_id is None:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_FILENAME_FEEDER_NOT_RESOLVED: 文件名馈线为空，禁止执行关联",
                    )
                    continue
                rmu_cache_key = (rmu_name, validated_feeder_id)
                if rmu_cache_key not in rmu_cache:
                    all_rmu_records = db.get_rmu_records(rmu_name)
                    rmu_total_count_cache[rmu_cache_key] = len(all_rmu_records)
                    rmu_cache[rmu_cache_key] = (
                        RmuValidator._filter_rmu_records_by_feeder(
                            all_rmu_records, validated_feeder_id
                        )
                    )
                    if validated_feeder_id is not None:
                        log_callback(
                            f"复核环网柜 {rmu_name}：同名总数={len(all_rmu_records)}；"
                            f"当前图级 FEEDER_ID={validated_feeder_id}；"
                            f"当前馈线内匹配={len(rmu_cache[rmu_cache_key])}"
                        )
                    else:
                        log_callback(
                            f"复核环网柜 {rmu_name}："
                            f"数据库记录数={len(rmu_cache[rmu_cache_key])}"
                        )

                rmu_records = rmu_cache[rmu_cache_key]
                if len(rmu_records) != 1:
                    make_fail(
                        change,
                        base_row,
                        (
                            f"EXEC_RMU_FEEDER_MATCH_NOT_UNIQUE: 图级 FEEDER_ID={validated_feeder_id}；"
                            f"当前馈线内同名记录数={len(rmu_records)}"
                            if validated_feeder_id is not None
                            else f"EXEC_RMU_NOT_UNIQUE: 当前记录数={len(rmu_records)}"
                        ),
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

                # SMART_ONLY policy cleanup is an unassociation operation, not
                # a database-device association. The validation snapshot has
                # already proven this exact G object is a non-smart RMU EFI
                # signal, and the source-file fingerprint is unchanged.
                if base_row.get("policy_clear_link") == "YES":
                    if (
                        current_snapshot.get("rmu_protection_scope") != "SMART_ONLY"
                        or str(base_row.get("rmu_is_smart", "NO")).upper() == "YES"
                        or tag != RMU_RELAY_SIGNAL_TAG
                    ):
                        make_fail(
                            change,
                            base_row,
                            "EXEC_POLICY_CLEAR_CONDITION_CHANGED",
                        )
                        continue

                    refreshed_row = dict(base_row)
                    refreshed_row.update({
                        "_execution_source_file": str(source_file),
                        "rmu_id": rmu_id,
                        "status": "RELINK",
                        "severity": "POLICY_CLEAR",
                        "reason": "SMART_ONLY_CLEAR_NONSMART_EFI_READY",
                        "association_ready": "YES",
                        "writeback_needed": "YES",
                        "association_action": "准备清除非智能环网柜保护/EFI关联",
                        "_execution_result": "READY",
                    })
                    refreshed_change = dict(change)
                    refreshed_change["attributes"] = self._attributes_for_row(refreshed_row)
                    refreshed_change["validated_row"] = refreshed_row
                    refreshed_change["mandatory_policy_change"] = True
                    executable[str(source_file)].append(refreshed_change)
                    execution_rows.append((refreshed_change, refreshed_row))
                    log_callback(
                        f"策略清理准备：RMU={rmu_name}；EFI XML_ID={change.get('xml_id')}；"
                        "仅SMART策略下清除非智能环网柜已有保护/EFI关联。"
                    )
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

                # Child-device scope is two-dimensional: current RMU + the
                # filename-resolved feeder.  EFI relay rows remain CODE based
                # and are ownership-checked by COMBINED_ID; the ordinary RMU
                # device tables must carry FEEDER_ID explicitly.
                if tag == RMU_RELAY_SIGNAL_TAG:
                    scoped_rows = list(db_rows or [])
                else:
                    scoped_rows = [
                        db_row for db_row in (db_rows or [])
                        if int_or_none(db_row.get("feeder_id")) == validated_feeder_id
                    ]

                match_field = ""
                match_value = logical_name
                matches = []

                if tag == "CBreakerDis":
                    preferred_name = str(
                        base_row.get("graphical_name")
                        or base_row.get("selected_device_name")
                        or logical_name
                        or ""
                    ).strip()
                    name_matches = [
                        r for r in scoped_rows
                        if norm(r.get("name")) == norm(preferred_name)
                    ]
                    if len(name_matches) > 1:
                        make_fail(
                            change, base_row,
                            f"EXEC_BREAKER_NAME_DUPLICATE: NAME={preferred_name}, count={len(name_matches)}",
                        )
                        continue
                    if len(name_matches) == 1:
                        matches = name_matches
                        match_field = "NAME"
                        match_value = preferred_name
                    else:
                        matches = [
                            r for r in scoped_rows
                            if norm(r.get("code")) == norm(preferred_name)
                        ]
                        match_field = "CODE"
                        match_value = preferred_name
                elif tag == "ZhaiWaiJieDiDaoZha":
                    paired = norm(base_row.get("paired_breaker_name"))
                    if not paired:
                        make_fail(change, base_row, "EXEC_GROUND_BREAKER_PAIR_NOT_RESOLVED")
                        continue
                    preferred_name = paired if paired.startswith(("KY", "KQ")) else f"K{paired}"
                    fallback_code = f"{paired}D"
                    name_matches = [
                        r for r in scoped_rows
                        if norm(r.get("name")) == preferred_name
                    ]
                    if len(name_matches) > 1:
                        make_fail(
                            change, base_row,
                            f"EXEC_GROUND_NAME_DUPLICATE: NAME={preferred_name}, count={len(name_matches)}",
                        )
                        continue
                    if len(name_matches) == 1:
                        matches = name_matches
                        match_field = "NAME"
                        match_value = preferred_name
                    else:
                        matches = [
                            r for r in scoped_rows
                            if norm(r.get("code")) == fallback_code
                        ]
                        match_field = "CODE"
                        match_value = fallback_code
                else:
                    matches = [
                        db_row
                        for db_row in scoped_rows
                        if norm(db_row.get("code")) == logical_name
                    ]
                    match_field = "CODE"
                    match_value = logical_name

                if len(matches) == 0:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_DEVICE_NOT_FOUND_IN_RMU_FEEDER: {match_field}={match_value}; "
                        f"RMU_ID={rmu_id}; FEEDER_ID={validated_feeder_id}",
                    )
                    continue
                if len(matches) > 1:
                    make_fail(
                        change,
                        base_row,
                        f"EXEC_DEVICE_{match_field}_DUPLICATE: {match_field}={match_value}, "
                        f"count={len(matches)}",
                    )
                    continue

                dev = matches[0]

                if int_or_none(dev.get("combined_id")) != rmu_id:
                    make_fail(
                        change,
                        base_row,
                        "EXEC_DEVICE_RMU_MISMATCH",
                    )
                    continue

                if (
                    tag != RMU_RELAY_SIGNAL_TAG
                    and int_or_none(dev.get("feeder_id")) != validated_feeder_id
                ):
                    make_fail(
                        change,
                        base_row,
                        "EXEC_DEVICE_FEEDER_MISMATCH: "
                        f"设备FEEDER_ID={dev.get('feeder_id')}; "
                        f"文件名馈线FEEDER_ID={validated_feeder_id}",
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
                    "db_feeder_id": dev.get("feeder_id", ""),
                    "required_feeder_id": validated_feeder_id,
                    "db_match_field": match_field,
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
                if row.get("policy_clear_link") == "YES":
                    row.update({
                        "status": "PASS",
                        "severity": "PASS",
                        "reason": "SMART_ONLY_CLEAR_NONSMART_EFI_SUCCESS",
                        "model_linked": "NO",
                        "model_link_correct": "YES",
                        "model_link_status": "非智能环网柜保护/EFI关联已按仅SMART策略清除",
                        "association_action": "已清除",
                        "writeback_needed": "NO",
                        "_execution_result": "SUCCESS",
                    })
                else:
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
                    validated_base = dict(change.get("validated_row", {}) or {})
                    validated_feeder_id = int_or_none(
                        validated_base.get("feeder_id")
                    )
                    rmu_cache_key = (rmu_name, validated_feeder_id)
                    records = rmu_cache.get(rmu_cache_key, [])
                    rmu_map[rmu_key] = {
                        "frame_index": frame_index,
                        "frame_xml_id": "",
                        "rmu_name": rmu_name,
                        "rmu_is_smart": validated_base.get("rmu_is_smart", ""),
                        "rmu_smart_marker_types": validated_base.get("rmu_smart_marker_types", ""),
                        "rmu_protection_scope": validated_base.get(
                            "rmu_protection_scope", current_snapshot.get("rmu_protection_scope", "")
                        ),
                        "rmu_status": "PASS",
                        "rmu_severity": "PASS",
                        "rmu_reason": "ASSOCIATION_EXECUTED",
                        "feeder_resolution_source": validated_base.get(
                            "feeder_resolution_source", ""
                        ),
                        "feeder_id": validated_feeder_id or "",
                        "feeder_name": validated_base.get("feeder_name", ""),
                        "rmu_db_total_count": rmu_total_count_cache.get(
                            rmu_cache_key, len(records)
                        ),
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

        applied_count = sum(
            int(result.get("applied_count", 0))
            for result in results
        )
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
            "skipped_count": skipped_count,
            "selected_count": selected_count,
            "operation_reports": list(report_map.values()),
            "rules": dict(runtime_rules),
        }
