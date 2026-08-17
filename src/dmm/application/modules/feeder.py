from __future__ import annotations

import shutil
import re
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
        "馈线模型校验、数据库缺失馈线段补齐及安全回写。"
        "馈线必须先由 G 根节点 facID、文件名或人工输入唯一确认到 "
        "13500 / dms_feeder_device；不再使用 馈线名称识别确定馈线。"
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

    @staticmethod
    def _normalize_lookup_text(value):
        return "".join(
            ch for ch in str(value or "").upper()
            if ch.isalnum()
        )

    @staticmethod
    def _section_type_from_ls(ls_value):
        value = str(ls_value or "").strip()
        mapping = {
            "2": 0,
            "1": 1,
            "": 3,
        }
        return mapping.get(value)

    @staticmethod
    def _section_prefix(feeder_record):
        station = str(
            feeder_record.get("station_name") or ""
        ).strip()
        feeder_name = str(
            feeder_record.get("name") or ""
        ).strip()
        if not station or not feeder_name:
            return ""
        def clean(value):
            value = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
            return value.strip("_")
        return f"{clean(station)}_{clean(feeder_name)}"

    def _resolve_file_feeder_result(
        self,
        db,
        g_file,
        settings,
        log_callback,
    ):
        """Resolve exactly one feeder without using RMU topology.

        Allowed evidence only:
          1. G root facID -> exact dms_feeder_device.ID lookup
          2. filename -> exact normalized station+feeder display-name match
          3. manual feeder name -> exact normalized station+feeder display-name match

        AUTO order:
          facID -> filename -> manual input

        A resolved facID is also cross-checked against any usable filename/manual
        feeder name. If a supplied name conflicts with the facID feeder, the
        file is blocked rather than silently creating sections under the wrong
        feeder.
        """
        parser = GParser()
        parsed = parser.parse(g_file)
        mode = str(
            settings.get("feeder_resolution_mode", "AUTO") or "AUTO"
        ).upper()
        manual = str(
            settings.get("manual_feeder_name", "") or ""
        ).strip()
        feeder_table_id = int(
            settings.get("feeder_table_id", 13500)
        )

        def enrich(record, source, evidence=""):
            if not record:
                return None
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

        def filename_hint():
            name = Path(g_file).name
            lower = name.lower()
            suffix = ".sln.pic.g"
            base = (
                name[:-len(suffix)]
                if lower.endswith(suffix)
                else Path(name).stem
            )
            return re.sub(r"[-_]+", " ", base).strip()

        def exact_by_text(value, source):
            value = str(value or "").strip()
            if not value:
                return None, "EMPTY"
            target = self._normalize_lookup_text(value)
            if not target:
                return None, "EMPTY"

            # Filename can contain a control-center prefix that is not part of
            # SUBSTATION.NAME, e.g. JED-CTL-ADF-16 while DB station+feeder is
            # ADF 16. Query several engineering suffixes, then accept only a
            # normalized full/suffix match and require one unique feeder ID.
            tokens = [
                token
                for token in re.split(r"[^A-Za-z0-9]+", value.upper())
                if token
            ]
            query_hints = [target]
            for count in range(2, min(len(tokens), 5) + 1):
                suffix = self._normalize_lookup_text(
                    " ".join(tokens[-count:])
                )
                if suffix and suffix not in query_hints:
                    query_hints.append(suffix)

            candidates = {}
            for hint in query_hints:
                for row in db.find_feeders_by_name_hint(
                    hint,
                    table_id=feeder_table_id,
                ):
                    rid = int_or_none(row.get("id"))
                    if rid is not None:
                        candidates[rid] = row

            matched = []
            for row in candidates.values():
                db_name = normalized_display(row)
                if (
                    db_name == target
                    or target.endswith(db_name)
                    or db_name.endswith(target)
                ):
                    matched.append(row)

            if len(matched) != 1:
                log_callback(
                    f"[{Path(g_file).name}] 馈线名称匹配失败："
                    f"{source}={value!r}；有效匹配数={len(matched)}；"
                    f"候选数={len(candidates)}"
                )
                return None, (
                    f"{source}_NOT_UNIQUE_OR_NOT_FOUND: "
                    f"输入={value}; matched={len(matched)}"
                )

            log_callback(
                f"[{Path(g_file).name}] 馈线名称匹配通过："
                f"{source}={value!r} -> "
                f"{matched[0].get('display_name') or matched[0].get('name')} "
                "(标准化全名/后缀唯一匹配)"
            )
            return enrich(matched[0], source, value), ""

        def by_facid():
            raw = str(parsed.root.attrib.get("facID", "") or "").strip()
            try:
                fac_id = int(raw)
            except Exception:
                return None, "FACID_EMPTY_OR_INVALID"
            if fac_id <= 0:
                return None, "FACID_EMPTY_OR_INVALID"

            record = db.get_feeder_info(
                fac_id,
                table_id=feeder_table_id,
            )
            if not record:
                log_callback(
                    f"[{Path(g_file).name}] G.facID={fac_id} "
                    "在 dms_feeder_device 中不存在或不唯一。"
                )
                return None, "FACID_NOT_FOUND_IN_DMS_FEEDER_DEVICE"

            log_callback(
                f"[{Path(g_file).name}] G.facID={fac_id} -> "
                f"{record.get('display_name') or record.get('name')} "
                "(13500 精确ID匹配)"
            )
            return enrich(record, "FACID", str(fac_id)), ""

        file_hint = filename_hint()

        if mode == "FACID":
            return by_facid()
        if mode == "FILENAME":
            return exact_by_text(file_hint, "FILENAME")
        if mode == "MANUAL":
            return exact_by_text(manual, "MANUAL")

        # AUTO: exact facID first.
        fac_record, fac_error = by_facid()
        if fac_record:
            # A filename is normally always present, so use it as a business
            # name cross-check when it exactly maps to a feeder. If it contains
            # a feeder-like name that maps uniquely to a different feeder, block.
            file_record, file_error = exact_by_text(
                file_hint,
                "FILENAME",
            )
            if file_record and int(file_record["id"]) != int(fac_record["id"]):
                raise RuntimeError(
                    "FEEDER_NAME_FACID_MISMATCH: "
                    f"facID->{fac_record.get('display_name')}; "
                    f"文件名->{file_record.get('display_name')}。"
                    "禁止创建馈线段。"
                )

            # Manual input, when present, is an explicit user assertion and MUST
            # match the facID feeder exactly.
            if manual:
                manual_record, manual_error = exact_by_text(
                    manual,
                    "MANUAL",
                )
                if not manual_record:
                    raise RuntimeError(
                        "MANUAL_FEEDER_NAME_NOT_MATCHED: "
                        f"{manual_error}。禁止创建馈线段。"
                    )
                if int(manual_record["id"]) != int(fac_record["id"]):
                    raise RuntimeError(
                        "MANUAL_FEEDER_NAME_FACID_MISMATCH: "
                        f"facID->{fac_record.get('display_name')}; "
                        f"人工输入->{manual_record.get('display_name')}。"
                        "禁止创建馈线段。"
                    )

            return fac_record, ""

        # facID cannot resolve -> filename, then manual.
        file_record, file_error = exact_by_text(
            file_hint,
            "FILENAME",
        )
        if file_record:
            if manual:
                manual_record, manual_error = exact_by_text(
                    manual,
                    "MANUAL",
                )
                if not manual_record:
                    raise RuntimeError(
                        "MANUAL_FEEDER_NAME_NOT_MATCHED: "
                        f"{manual_error}。禁止创建馈线段。"
                    )
                if int(manual_record["id"]) != int(file_record["id"]):
                    raise RuntimeError(
                        "MANUAL_FEEDER_NAME_FILENAME_MISMATCH: "
                        f"文件名->{file_record.get('display_name')}; "
                        f"人工输入->{manual_record.get('display_name')}。"
                        "禁止创建馈线段。"
                    )
            return file_record, ""

        if manual:
            manual_record, manual_error = exact_by_text(
                manual,
                "MANUAL",
            )
            if manual_record:
                return manual_record, ""
            return None, manual_error

        return None, (
            f"FEEDER_NOT_RESOLVED: {fac_error}; {file_error}; "
            "请检查 G.facID、文件名，或人工输入唯一馈线名称。"
        )

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

    def _augment_section_creation_plan(
        self,
        db,
        report,
        settings,
        log_callback,
    ):
        """Turn pure DB-shortage rows into selectable create+link candidates."""
        report["section_create_plan"] = []
        if not bool(settings.get("auto_create_missing_sections", True)):
            return report

        feeder_id = int_or_none(report.get("feeder_id"))
        if feeder_id is None:
            return report

        feeder = db.get_feeder_info(
            feeder_id,
            table_id=int(settings.get("feeder_table_id", 13500)),
        ) or {}
        prefix = self._section_prefix(feeder)
        station_id = int_or_none(feeder.get("st_id"))
        voltage = (
            db.get_preferred_feeder_section_voltage(station_id)
            if station_id is not None else None
        ) or {}
        bv_id = voltage.get("bv_id")
        nominal_voltage = voltage.get("nomvol")
        if not prefix or bv_id in (None, ""):
            report["section_create_plan_error"] = (
                "无法从 feeder.ST_ID -> 402/voltagelevel -> "
                "401/basevoltage 找到允许的 110/33/13.8kV 电压等级，"
                "禁止自动创建馈线段。"
            )
            return report

        _, section_rows = db.get_sections_by_feeder_id(
            feeder_id,
            table_id=int(settings.get("section_table_id", 13503)),
        )
        by_name = {}
        for section in section_rows:
            key = str(section.get("name") or "").strip().upper()
            by_name.setdefault(key, []).append(section)

        plans = []
        for row in report.get("feedline_rows", []) or []:
            order_index = int(row.get("order_index") or 0)
            if order_index <= 0:
                continue
            target_name = f"{prefix}_SEC{order_index:03d}"
            matches = by_name.get(target_name.upper(), [])
            row["planned_section_name"] = target_name

            if len(matches) > 1:
                row.update({
                    "status": "FAIL",
                    "severity": "ERROR",
                    "association_ready": "NO",
                    "writeback_needed": "NO",
                    "reason": (
                        f"SECTION_NAME_DUPLICATE: {target_name} "
                        f"数据库存在{len(matches)}条"
                    ),
                })
                continue

            section_type = self._section_type_from_ls(
                row.get("ls", "")
            )
            row["planned_section_type"] = (
                section_type if section_type is not None else ""
            )

            # Existing DB record -> never recreate it.
            if len(matches) == 1:
                row["db_create_needed"] = "NO"
                continue

            if section_type is None:
                if str(row.get("reason", "")).startswith(
                    "SECTION_NOT_AVAILABLE"
                ):
                    row.update({
                        "status": "FAIL",
                        "severity": "ERROR",
                        "association_ready": "NO",
                        "writeback_needed": "NO",
                        "reason": (
                            f"UNKNOWN_FEEDLINE_LS: ls={row.get('ls')!r}; "
                            "允许值：2->0, 1->1, 空->3"
                        ),
                    })
                continue

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

            # The current validator correctly reports DB shortage as blocked.
            # With auto-create enabled, that specific shortage becomes a
            # selectable CREATE_THEN_LINK candidate. Other errors stay blocked.
            if str(row.get("reason", "")).startswith(
                "SECTION_NOT_AVAILABLE"
            ):
                row.update({
                    "status": "WARN",
                    "severity": "CREATE_PENDING",
                    "association_ready": "YES",
                    "writeback_needed": "YES",
                    "reason": (
                        f"DB_SECTION_CREATE_PENDING: {target_name}; "
                        f"ls={row.get('ls')!r} -> SECTION_TYPE={section_type}"
                    ),
                })

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
                f"前缀={prefix}；"
                f"创建电压等级={nominal_voltage}kV；BV_ID={bv_id}"
            )
        # Refresh summary after changing shortage rows into selectable rows.
        report["summary"] = FeederValidator._summary(report)
        return report

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
            feeder_record, feeder_error = self._resolve_file_feeder_result(
                db,
                g_file,
                settings,
                log_callback,
            )
            if feeder_record:
                resolution_source = str(
                    feeder_record.get("_resolution_source")
                    or "FACID"
                )
                resolution_evidence = str(
                    feeder_record.get("_resolution_evidence")
                    or ""
                )
                file_report = validator.validate_file_with_feeder_record(
                    g_file,
                    feeder_record,
                    source=resolution_source,
                )
                # Feeder reports are now explicitly based only on
                # facID / filename / manual input.  Keep those facts directly
                # on each feeder report so HTML/CSV never need RMU context.
                for _report in file_report.get("feeder_regions", []) or []:
                    _report["feeder_resolution_source"] = resolution_source
                    _report["feeder_resolution_evidence"] = resolution_evidence
                    _report["station_name"] = feeder_record.get(
                        "station_name", ""
                    )
                    _report["station_bv_id"] = feeder_record.get(
                        "station_bv_id", ""
                    )
            else:
                file_report = self._unresolved_file_report(
                    g_file,
                    feeder_error
                    or "FEEDER_NOT_RESOLVED",
                )
            region_reports = file_report.get("feeder_regions") or [file_report]
            region_reports = [
                self._augment_section_creation_plan(
                    db,
                    report,
                    settings,
                    log_callback,
                )
                for report in region_reports
            ]
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
                "feeder_resolution_mode": str(
                    settings.get("feeder_resolution_mode", "AUTO")
                ).upper(),
                "manual_feeder_name": str(
                    settings.get("manual_feeder_name", "") or ""
                ).strip(),
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
            "feeder_table_id": int(settings.get("feeder_table_id", 13500)),
            "section_table_id": int(settings.get("section_table_id", 13503)),
            "section_domain": int(settings.get("section_domain", 1)),
            "feeder_resolution_mode": str(
                settings.get("feeder_resolution_mode", "AUTO")
            ).upper(),
            "manual_feeder_name": str(
                settings.get("manual_feeder_name", "") or ""
            ).strip(),
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
        if any(
            current_snapshot.get(key) != value
            for key, value in validated_snapshot.items()
            if key in current_snapshot
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
                str(report.get("feeder_id", "") or ""),
            )
            report_lookup[key] = report

        recalculated = defaultdict(list)
        skipped = []
        database_created_count = 0

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

                # Database preparation is driven by the selected FeedLine's
                # exact planned SEC name, not merely by "pool size".  Example:
                # G order #2 requires ..._SEC002.  If DB has SEC010 but not
                # SEC002, SEC002 is still missing and must be created.
                if bool(
                    settings.get(
                        "auto_create_missing_sections",
                        True,
                    )
                ):
                    existing_names = {
                        str(section.get("name") or "").strip().upper()
                        for section in section_rows
                    }
                    create_defs = []
                    seen_create_names = set()
                    for change in selected_changes:
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

                remaining_available = list(available)
                for change in selected_changes:
                    row0 = dict(
                        change.get("validated_row", {}) or {}
                    )
                    planned_name = str(
                        change.get("planned_section_name")
                        or row0.get("planned_section_name")
                        or ""
                    ).strip()

                    section = None
                    if planned_name:
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
                    if section is None and not planned_name:
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
