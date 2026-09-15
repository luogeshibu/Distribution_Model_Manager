
from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.constants import (
    RMU_LABEL_SEARCH_MAX_DISTANCE,
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
)
from dmm.config.defaults import (
    DEFAULT_DEVICE_RULES,
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
    resolve_rmu_name_positions,
)
from dmm.domain.gfile.parser import GParser
from dmm.domain.rmu.validator import RmuValidator, KEYID_STEP, norm, int_or_none
from dmm.infrastructure.gfile.writeback import GWriteBackService

class RmuModelModule(ModelModule):
    module_id = "RMU"
    display_name = "RMU 环网柜模型"
    description = "RMU 环网柜模型校验、候选选择及安全回写。"
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    def _new_validator(self, db, settings, log_callback):
        rules = settings["_runtime_rules"]
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
            log=log_callback,
        )

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        positions = resolve_rmu_name_positions(
            settings.get(
                "rmu_name_detection_mode",
                DEFAULT_RMU_NAME_DETECTION_MODE,
            ),
            settings.get("rmu_name_positions", DEFAULT_NAME_POSITIONS),
        )
        validator = self._new_validator(db, settings, log_callback)
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

            report = validator.validate_file(
                g_file,
                positions,
                progress_callback=_file_progress,
            )
            reports.append(report)
            for key in aggregate:
                aggregate[key] += report["summary"].get(key, 0)
        return reports, aggregate, settings["_runtime_rules"]

    @staticmethod
    def _attributes_for_row(row):
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
                "rmu_name_positions": dict(settings.get("rmu_name_positions", {})),
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

        current_snapshot = {
            "rmu_name_detection_mode": str(
                settings.get(
                    "rmu_name_detection_mode",
                    DEFAULT_RMU_NAME_DETECTION_MODE,
                )
                or DEFAULT_RMU_NAME_DETECTION_MODE
            ).upper(),
            "rmu_name_positions": dict(
                settings.get("rmu_name_positions", {})
            ),
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

        runtime_rules = settings.get("_runtime_rules", {}) or {}
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

                if rmu_name not in rmu_cache:
                    rmu_cache[rmu_name] = db.get_rmu_records(rmu_name)
                    log_callback(
                        f"复核环网柜 {rmu_name}："
                        f"数据库记录数={len(rmu_cache[rmu_name])}"
                    )

                rmu_records = rmu_cache[rmu_name]
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
                if not bv_id:
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
                    records = rmu_cache.get(rmu_name, [])
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
