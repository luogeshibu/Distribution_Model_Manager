
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
from dmm.config.defaults import DEFAULT_DEVICE_RULES, DEFAULT_NAME_POSITIONS
from dmm.domain.gfile.parser import GParser
from dmm.domain.rmu.validator import RmuValidator
from dmm.infrastructure.gfile.writeback import GWriteBackService

class RmuModelModule(ModelModule):
    module_id = "RMU"
    display_name = "RMU 环网柜模型"
    description = "RMU 环网柜模型校验、关联预览及安全回写。"
    SUPPORTED_OPERATIONS = ("VALIDATE", "PREVIEW_ASSOCIATION", "APPLY_ASSOCIATION")

    def _new_validator(self, db, settings, log_callback):
        rules = settings["_runtime_rules"]
        parser = GParser(
            required_rmu_tags=rules.keys(),
            label_regex=RMU_LABEL_PATTERN,
            max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
            overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
        )
        return RmuValidator(
            db,
            parser,
            rules,
            breaker_name_source=settings.get("breaker_name_source", "P_NAME_STRING"),
            log=log_callback,
        )

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        positions = [k for k,v in settings["rmu_name_positions"].items() if v]
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
                "rmu_name_positions": dict(settings.get("rmu_name_positions", {})),
                "breaker_name_source": settings.get("breaker_name_source", "P_NAME_STRING"),
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
        if not preview_data:
            raise RuntimeError("没有可执行的模型关联预览。")

        current_snapshot = {
            "rmu_name_positions": dict(settings.get("rmu_name_positions", {})),
            "breaker_name_source": settings.get("breaker_name_source", "P_NAME_STRING"),
            "device_rules": dict(settings.get("device_rules", {})),
        }
        if current_snapshot != preview_data.get("settings_snapshot", {}):
            raise RuntimeError("RMU 配置在关联预览后发生变化，请重新生成关联预览。")

        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        output_g_dir = Path(output_g_dir)
        output_g_dir.mkdir(parents=True, exist_ok=True)

        # Verify source files have not changed since preview.
        for g_file, fingerprint in preview_data.get("file_fingerprints", {}).items():
            path = Path(g_file)
            stat = path.stat()
            if (
                stat.st_size != fingerprint.get("size")
                or stat.st_mtime_ns != fingerprint.get("mtime_ns")
            ):
                raise RuntimeError(
                    f"G 文件在关联预览后发生变化，禁止处理，请重新生成预览：{g_file}"
                )

        changes_by_file = preview_data.get("changes_by_file", {})

        # Copy every selected G file, even if a file needs no model change.
        copied = {}
        for source in files:
            source = Path(source)
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

        for source_file, changes in changes_by_file.items():
            source_path = Path(source_file)
            target = copied.get(str(source_path.resolve()))
            if target is None:
                raise RuntimeError(f"无法定位 G 文件安全副本：{source_file}")

            if not changes:
                continue

            result = service.apply_attribute_changes(
                target,
                changes,
                create_backup=False,
            )
            result["source_g_file"] = str(source_path)
            result["output_g_file"] = str(target)
            results.append(result)
            log_callback(
                f"安全副本处理完成：{target}；修改设备数={result['applied_count']}"
            )

        return {
            "output_g_dir": str(output_g_dir),
            "copied_files": [str(v) for v in copied.values()],
            "results": results,
            "applied_count": sum(int(x.get("applied_count", 0)) for x in results),
        }

