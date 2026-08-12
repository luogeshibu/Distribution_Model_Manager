from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.domain.feeder.validator import FeederValidator
from dmm.domain.gfile.parser import GParser
from dmm.infrastructure.gfile.writeback import GWriteBackService


class FeederModelModule(ModelModule):
    module_id = "FEEDER"
    display_name = "馈线模型"
    description = (
        "馈线模型校验、关联预览及安全回写。当前版本处理单馈线 G 图，"
        "以 <Bus> 附近最近有效文字识别馈线，失败时回退到文件名；"
        "馈线段图元使用 <FeedLine>。"
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
            report = validator.validate_file(g_file)
            reports.append(report)

            feeder_text = (
                f"馈线={report.get('feeder_name') or report.get('feeder_hint') or '-'}；"
                f"FeedLine={len(report.get('feedline_rows', []))}；"
                f"状态={report.get('status')}"
            )
            log_callback(f"[{g_file.name}] {feeder_text}")

            for key in aggregate:
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
                    "section_name": row.get("assigned_section_name", ""),
                    "device_id": row.get("assigned_device_id", ""),
                    "expected_keyid": row.get("expected_keyid", ""),
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
            raise RuntimeError("没有可执行的馈线模型关联预览。")

        current_snapshot = {
            "feeder_table_id": int(
                settings.get("feeder_table_id", 13500)
            ),
            "section_table_id": int(
                settings.get("section_table_id", 13503)
            ),
            "section_domain": int(
                settings.get("section_domain", 1)
            ),
        }
        if current_snapshot != preview_data.get(
            "settings_snapshot",
            {},
        ):
            raise RuntimeError(
                "馈线模型配置在关联预览后发生变化，请重新生成预览。"
            )

        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        output_g_dir = Path(output_g_dir)
        output_g_dir.mkdir(parents=True, exist_ok=True)

        for g_file, fingerprint in preview_data.get(
            "file_fingerprints",
            {},
        ).items():
            path = Path(g_file)
            stat = path.stat()
            if (
                stat.st_size != fingerprint.get("size")
                or stat.st_mtime_ns != fingerprint.get("mtime_ns")
            ):
                raise RuntimeError(
                    "G 文件在关联预览后发生变化，禁止处理，请重新生成预览："
                    f"{g_file}"
                )

        changes_by_file = preview_data.get("changes_by_file", {})

        copied = {}
        for source in files:
            source = Path(source)
            target = output_g_dir / source.name

            if target.exists():
                idx = 2
                while True:
                    candidate = output_g_dir / (
                        f"{source.stem}_{idx}{source.suffix}"
                    )
                    if not candidate.exists():
                        target = candidate
                        break
                    idx += 1

            shutil.copy2(source, target)
            copied[str(source.resolve())] = target
            log_callback(
                f"安全复制 G 文件：{source} -> {target}"
            )

        service = GWriteBackService(log=log_callback)
        results = []

        for source_file, changes in changes_by_file.items():
            source_path = Path(source_file)
            target = copied.get(str(source_path.resolve()))
            if target is None:
                raise RuntimeError(
                    f"无法定位 G 文件安全副本：{source_file}"
                )

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
                f"馈线模型安全副本处理完成：{target}；"
                f"修改FeedLine数={result['applied_count']}"
            )

        return {
            "output_g_dir": str(output_g_dir),
            "copied_files": [
                str(value)
                for value in copied.values()
            ],
            "results": results,
            "applied_count": sum(
                int(item.get("applied_count", 0))
                for item in results
            ),
        }
