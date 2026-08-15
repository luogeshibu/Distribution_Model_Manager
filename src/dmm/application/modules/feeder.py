from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.domain.feeder.validator import FeederValidator, natural_section_key, int_or_none
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.gfile.writeback import GWriteBackService


class FeederModelModule(ModelModule):
    module_id = "FEEDER"
    display_name = "馈线模型"
    description = (
        "馈线模型校验、候选选择及安全回写。单馈线图和组合大图统一"
        "使用可信 RMU、FEEDER_ID 与 G 图连接拓扑确定 FeedLine 归属；"
        "馈线名称不参与自动关联判断。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _validator(db, settings, log_callback):
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

    def validate(
        self,
        db,
        files,
        settings,
        log_callback,
        progress_callback=None,
    ):
        validator = self._validator(db, settings, log_callback)
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
            log_callback(
                f"[{idx}/{len(files)}] 正在处理馈线模型：{g_file.name}"
            )
            file_report = validator.validate_file(
                g_file,
                drawing_mode=settings.get("drawing_mode", "AUTO"),
            )
            region_reports = file_report.get("feeder_regions") or [file_report]
            reports.extend(region_reports)

            drawing_type = file_report.get(
                "drawing_type",
                region_reports[0].get("drawing_type", "SINGLE_FEEDER")
                if region_reports else "SINGLE_FEEDER",
            )
            log_callback(
                f"[{g_file.name}] 图纸类型={drawing_type}；"
                f"识别馈线区域={len(region_reports)}"
            )
            aggregate["feeder_files"] += 1
            for report in region_reports:
                feeder_text = (
                    f"区域{report.get('region_index', 1)} "
                    f"馈线={report.get('feeder_name') or report.get('feeder_hint') or '-'}；"
                    f"FeedLine={len(report.get('feedline_rows', []))}；"
                    f"状态={report.get('status')}"
                )
                log_callback(f"[{g_file.name}] {feeder_text}")

                for key in aggregate:
                    if key == "feeder_files":
                        continue
                    aggregate[key] += int(
                        report.get("summary", {}).get(key, 0)
                    )

            if progress_callback:
                percent = 5 + int((idx / total) * 90)
                progress_callback(
                    min(percent, 95),
                    f"{g_file.name}：馈线模型校验完成",
                )

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
            # FeedLine voltype 使用 dms_section_device.BV_ID。
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

            if not report.get("association_eligible"):
                skipped_rmus.append({
                    "g_file": g_file,
                    "rmu_name": report.get("feeder_name", ""),
                    "rmu_id": report.get("feeder_id", ""),
                    "reasons": [report.get("reason", "")],
                })
                continue

            for row in report.get("feedline_rows", []):
                if row.get("association_ready") != "YES":
                    continue

                if row.get("writeback_needed") != "YES":
                    if row.get("model_link_correct") == "YES":
                        log_callback(
                            f"无需关联：FeedLine XML={row.get('xml_id')} "
                            f"已经属于馈线 {report.get('feeder_name')}。"
                        )
                    continue

                attrs = self._attributes_for_row(row)
                change = {
                    "xml_id": row["xml_id"],
                    "tag": "FeedLine",
                    "attributes": attrs,
                    "feeder_name": report.get("feeder_name", ""),
                    "feeder_id": report.get("feeder_id", ""),
                    "region_index": report.get("region_index", ""),
                    "section_name": row.get("assigned_section_name", ""),
                    "device_id": row.get("assigned_device_id", ""),
                    "expected_keyid": row.get("expected_keyid", ""),
                    "validated_row": dict(row),
                }
                changes_by_file[g_file].append(change)

                preview_row = dict(row)
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
            # Kept for current generic GUI compatibility.
            "skipped_rmus": skipped_rmus,
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "feeder_table_id": int(
                    settings.get("feeder_table_id", 13500)
                ),
                "section_table_id": int(
                    settings.get("section_table_id", 13503)
                ),
                "section_domain": int(
                    settings.get("section_domain", 1)
                ),
                "drawing_mode": str(
                    settings.get("drawing_mode", "AUTO")
                ).upper(),
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

        The validated topology/FEEDER_ID decision remains the authority. At
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
            "feeder_table_id": int(settings.get("feeder_table_id", 13500)),
            "section_table_id": int(settings.get("section_table_id", 13503)),
            "section_domain": int(settings.get("section_domain", 1)),
            "drawing_mode": str(settings.get("drawing_mode", "AUTO")).upper(),
        }
        if current_snapshot != preview_data.get("settings_snapshot", {}):
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
                str(report.get("feeder_id", "") or ""),
            )
            report_lookup[key] = report

        recalculated = defaultdict(list)
        skipped = []

        for source_file, changes in changes_by_file.items():
            grouped = defaultdict(list)
            for change in changes or []:
                grouped[(
                    str(change.get("region_index", "") or ""),
                    str(change.get("feeder_id", "") or ""),
                )].append(dict(change))

            for (region_index, feeder_id_text), selected_changes in grouped.items():
                feeder_id = int_or_none(feeder_id_text)
                if feeder_id is None:
                    for change in selected_changes:
                        skipped.append((change, "EXEC_FEEDER_ID_INVALID"))
                    continue

                report = report_lookup.get((
                    str(source_file), region_index, feeder_id_text,
                ))
                if report is None:
                    for change in selected_changes:
                        skipped.append((change, "EXEC_TOPOLOGY_REGION_NOT_FOUND"))
                    continue

                # The full validation already blocked inconsistent trusted-RMU
                # regions. Never bypass that decision during selective write.
                if not report.get("association_eligible"):
                    for change in selected_changes:
                        skipped.append((
                            change,
                            f"EXEC_REGION_BLOCKED: {report.get('reason', '')}",
                        ))
                    continue

                _, section_rows = db.get_sections_by_feeder_id(
                    feeder_id,
                    table_id=section_table_id,
                )
                section_rows = sorted(section_rows, key=natural_section_key)

                selected_xml_ids = {
                    str(change.get("xml_id", "") or "")
                    for change in selected_changes
                }

                # Reserve database records currently used by UNSELECTED G rows
                # when their current KeyID still resolves to this feeder/table/
                # domain. This gives duplicate selection intuitive semantics.
                protected_ids = set()
                for row in report.get("feedline_rows", []) or []:
                    if str(row.get("xml_id", "") or "") in selected_xml_ids:
                        continue
                    did = int_or_none(row.get("current_device_id"))
                    owner = int_or_none(row.get("current_feeder_id"))
                    tab = int_or_none(row.get("current_table_id"))
                    dom = int_or_none(row.get("current_domain"))
                    if (
                        did is not None
                        and owner == feeder_id
                        and tab == section_table_id
                        and dom == section_domain
                    ):
                        protected_ids.add(did)

                available = [
                    section for section in section_rows
                    if int_or_none(section.get("id")) not in protected_ids
                ]
                available.sort(key=natural_section_key)

                selected_changes.sort(
                    key=lambda change: int(
                        (change.get("validated_row", {}) or {}).get(
                            "order_index", 10**9
                        )
                    )
                )

                log_callback(
                    f"馈线区域{region_index}：FEEDER_ID={feeder_id}；"
                    f"勾选FeedLine={len(selected_changes)}；"
                    f"未选中已占用数据库段={len(protected_ids)}；"
                    f"当前可分配数据库段={len(available)}"
                )

                for pos, change in enumerate(selected_changes):
                    if pos >= len(available):
                        skipped.append((
                            change,
                            "EXEC_SECTION_NOT_AVAILABLE: 当前数据库剩余馈线段不足",
                        ))
                        continue

                    section = available[pos]
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
                    recalculated[str(source_file)].append(refreshed)

        for change, reason in skipped:
            log_callback(
                f"跳过 FeedLine XML={change.get('xml_id')}: {reason}"
            )

        if not recalculated:
            raise RuntimeError(
                "所有勾选馈线段在执行时均被阻断，没有可安全写回的对象。"
            )

        # Copy only source files that contain selected executable changes.
        source_map = {
            str(Path(source).resolve()): Path(source)
            for source in files
        }
        copied = {}
        for source_file in recalculated:
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
            shutil.copy2(source, target)
            copied[str(source.resolve())] = target
            log_callback(f"安全复制 G 文件：{source} -> {target}")

        service = GWriteBackService(log=log_callback)
        results = []
        for source_file, changes in recalculated.items():
            target = copied.get(str(Path(source_file).resolve()))
            if target is None:
                raise RuntimeError(f"无法定位 G 文件安全副本：{source_file}")
            result = service.apply_attribute_changes(
                target,
                changes,
                create_backup=False,
            )
            result["source_g_file"] = str(source_file)
            result["output_g_file"] = str(target)
            results.append(result)
            log_callback(
                f"馈线模型安全副本处理完成：{target}；"
                f"修改FeedLine数={result['applied_count']}"
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

            original = report_lookup.get(key, {}) or {}
            report = {
                k: v
                for k, v in original.items()
                if k != "feedline_rows"
            }
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
                        "current_table_id": section_table_id,
                        "current_domain": section_domain,
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
            f"本次馈线模型关联完成：选中={selected_count}，"
            f"成功={applied_count}，跳过={len(skipped)}。"
        )

        return {
            "output_g_dir": str(output_g_dir),
            "copied_files": [str(value) for value in copied.values()],
            "results": results,
            "selected_count": selected_count,
            "skipped_count": len(skipped),
            "applied_count": applied_count,
            "operation_reports": list(
                operation_report_map.values()
            ),
            "rules": dict(preview_data.get("rules", {}) or {}),
        }
