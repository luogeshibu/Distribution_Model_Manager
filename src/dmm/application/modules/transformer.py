from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.domain.gfile.parser import GParser, GObject, ParsedG
from dmm.domain.gfile.element_catalog import (
    classification_is,
    resolve_element_record,
)
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService
from dmm.application.modules.pole_switch import (
    POLE_SWITCH_NAME_RE,
    PoleSwitchParser,
)


TRANSFORMER_TABLE_ID = 13505
TRANSFORMER_DOMAIN = 1
TRANSFORMER_TAG = "TransformerDis"
TRANSFORMER_SOURCE_TAG = "CBreaker"


class TransformerParser(PoleSwitchParser):
    """Recognize only element-catalog entries marked Transformer_OH."""

    @staticmethod
    def _is_valid_name(text: str) -> bool:
        """Accept numeric transformer names such as 97803.

        The pole-switch parser deliberately rejects pure numeric labels because
        they are not valid pole-switch names in its drawings. Transformer
        names are different: the database and supplied G files use numeric
        Text values, so numeric labels must remain eligible here.
        """
        value = str(text or "").strip()
        if not value or not any(char.isalnum() for char in value):
            return False
        if value.upper() in {
            "SMART", "SMR", "NOP", "N.O.P", "N-O-P", "N_O_P",
            "F.C", "FC", "BUS", "G", "I",
        }:
            return False
        if re.fullmatch(r"[YQ]\d+", value.replace(" ", "").upper()):
            return False
        return bool(POLE_SWITCH_NAME_RE.fullmatch(value))

    @staticmethod
    def _text_value(obj: GObject) -> str:
        return re.sub(r"\s+", " ", str(obj.attrs.get("ts") or "")).strip()

    @staticmethod
    def _root_int(parsed: ParsedG, attribute: str):
        return int_or_none(parsed.root.attrib.get(attribute))

    @classmethod
    def _is_transformer_object(cls, obj: GObject, element_catalog=None) -> bool:
        record = resolve_element_record(
            str(obj.attrs.get("devref") or ""),
            element_catalog,
        )
        return classification_is(record, "TRANSFORMER_OH")

    @classmethod
    def _topology_source_keyids(cls, parsed: ParsedG, element_catalog=None):
        """Find source CBreaker keyids per TransformerDis topology branch."""
        by_id = {
            str(obj.xml_id): obj
            for obj in parsed.objects
            if str(obj.xml_id or "").strip()
        }
        graph = defaultdict(set)
        for obj in parsed.objects:
            xml_id = str(obj.xml_id or "").strip()
            if not xml_id:
                continue
            for ref in cls._refs(obj):
                ref = str(ref).strip()
                if not ref or ref not in by_id:
                    continue
                graph[xml_id].add(ref)
                graph[ref].add(xml_id)

        breakers_by_id = {
            xml_id: obj
            for xml_id, obj in by_id.items()
            if obj.tag == TRANSFORMER_SOURCE_TAG
            and str(obj.attrs.get("keyid") or "").strip()
        }
        result = {}
        for transformer in parsed.objects:
            if not cls._is_transformer_object(transformer, element_catalog):
                continue
            transformer_id = str(transformer.xml_id or "").strip()
            if not transformer_id:
                continue
            queue = [transformer_id]
            visited = {transformer_id}
            source_ids = []
            while queue:
                current = queue.pop(0)
                if current in breakers_by_id:
                    source_ids.append(
                        str(breakers_by_id[current].attrs.get("keyid") or "").strip()
                    )
                    # A source CBreaker is an anchor. Do not walk through it
                    # into another source branch.
                    continue
                for neighbor in graph.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            result[transformer_id] = list(dict.fromkeys(source_ids))

        all_source_keyids = [
            str(obj.attrs.get("keyid") or "").strip()
            for obj in breakers_by_id.values()
            if str(obj.attrs.get("keyid") or "").strip()
        ]
        # Sparse/legacy drawings may not expose explicit refs.  A single main
        # CBreaker remains a safe fallback; multiple unconnected breakers are
        # intentionally left unresolved instead of guessing.
        if len(all_source_keyids) == 1:
            for transformer_id, source_ids in result.items():
                if not source_ids:
                    result[transformer_id] = list(all_source_keyids)
        return result, all_source_keyids

    def discover(self, parsed: ParsedG, element_catalog=None, name_settings=None):
        global_name_owners = self.build_global_name_owners(
            parsed,
            element_catalog,
            name_settings,
            nearest_only=True,
            device_filter=lambda obj: self._is_transformer_object(
                obj,
                element_catalog,
            ),
        )
        # Feeder resolution is intentionally fixed-mode: use only the G-root
        # facID (with the unique facName fallback below). No topology branch
        # or CBreaker traversal is performed during model association.
        source_keyids_by_transformer = {}
        all_source_keyids = []
        rows = []
        for obj in parsed.objects:
            if not self._is_transformer_object(obj, element_catalog):
                continue

            label, _candidates = self.find_nearest_name(
                parsed,
                obj,
                "",
                (),
                global_name_owners,
            )
            attrs = obj.attrs
            rows.append({
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": str(attrs.get("devref") or "").strip(),
                "graphical_name": label.get("text", "") if label else "",
                "name_source": "NEAREST_GRAPHICAL_TEXT" if label else "",
                "name_distance": label.get("distance", "") if label else "",
                "name_direction": label.get("direction", "") if label else "",
                "name_xml_id": label.get("xml_id", "") if label else "",
                "source_cbreaker_keyids": source_keyids_by_transformer.get(
                    str(obj.xml_id), []
                ),
                "current_keyid1": str(attrs.get("keyid1") or "").strip(),
                "current_keyid2": str(attrs.get("keyid2") or "").strip(),
                "source_cbreaker_count": 0,
                "source_cbreaker_keyid": "",
                "status": "",
                "severity": "",
                "reason": "",
            })

        source_keyids = all_source_keyids
        source_keyid = ""
        if source_keyids:
            source_keyid = source_keyids[0]
        root_fac_id = self._root_int(parsed, "facID")
        root_fac_name = str(parsed.root.attrib.get("facName") or "").strip()
        context = {
            "root_fac_id": root_fac_id,
            "root_fac_name": root_fac_name,
            "source_cbreaker_count": 0,
            "source_cbreaker_keyid": source_keyid,
            "source_cbreaker_keyids": source_keyids,
            "source_cbreaker_keyids_by_transformer": source_keyids_by_transformer,
        }
        for row in rows:
            row["source_cbreaker_count"] = 0
            row["source_cbreaker_keyid"] = source_keyid
        return rows, context


class TransformerModelModule(ModelModule):
    module_id = "TRANSFORMER"
    display_name = "柱上变压器模型"
    description = (
        "只识别图元管理中标记为 Transformer_OH 的图元；被标记图元直接视为柱上变压器，"
        "每个设备独立取最近合规 Text，馈线固定使用 G 根 facID 查询，必要时仅用唯一 facName 兜底，"
        "按 13505 / dms_tr_device 计算双 KeyID 并安全回写。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            TRANSFORMER_TAG: {
                "table_id": TRANSFORMER_TABLE_ID,
                "domain": TRANSFORMER_DOMAIN,
                "match_mode": "TRANSFORMERDIS_NEAREST_TEXT_AND_ROOT_FACID",
                "description": (
                    "仅使用图元管理标记 Transformer_OH 的图元，直接视为柱上变压器；"
                    "每个变压器直接解析整张 G 图中最近的 Text，不依赖现场图元文件名；"
                    "G 根 facID 确认馈线；目标表为 13505，Domain=1"
                ),
            }
        }

    @staticmethod
    def _make_expected_keyid(device_id):
        device_id = int(device_id)
        if device_id < 0:
            raise ValueError(f"Invalid transformer device_id: {device_id}")
        return device_id + (TRANSFORMER_DOMAIN << 32)

    @staticmethod
    def _attributes_for_row(row):
        expected = str(row["expected_keyid"])
        # Existing linked TransformerDis objects in the supplied G files use
        # two parallel model slots. Preserve that established write-back
        # contract; do not write unsuffixed TransformerDis attributes.
        return {
            "app1": "6500000",
            "app2": "6500000",
            "voltype1": "0",
            "voltype2": "0",
            "p_ReportType1": "1",
            "p_ReportType2": "1",
            "state1": "18",
            "state2": "18",
            "keyid1": expected,
            "keyid2": expected,
        }

    @staticmethod
    def _resolve_feeder(db, context):
        root_fac_id = int_or_none(context.get("root_fac_id"))
        if root_fac_id is not None:
            feeder = db.get_feeder_info(root_fac_id)
            if feeder:
                return feeder, "G_ROOT_FACID"

        # Last-resort label fallback remains unique-only after the fixed
        # facID lookup. It does not inspect topology.
        hint = str(context.get("root_fac_name") or "").strip()
        if hint:
            candidates = db.find_feeders_by_name_hint(hint)
            unique = {}
            for candidate in candidates:
                candidate_id = int_or_none(candidate.get("id"))
                if candidate_id is not None:
                    unique[candidate_id] = candidate
            if len(unique) == 1:
                return next(iter(unique.values())), "G_ROOT_FACNAME_UNIQUE"
        return None, "UNRESOLVED"

    @staticmethod
    def _current_keyids(row):
        return [
            int_or_none(row.get("current_keyid1")),
            int_or_none(row.get("current_keyid2")),
        ]

    def _current_link_fields(self, row, db):
        keyid1 = str(row.get("current_keyid1") or "").strip()
        keyid2 = str(row.get("current_keyid2") or "").strip()
        row["current_keyid"] = keyid1 or keyid2
        current_keyid = int_or_none(row.get("current_keyid"))
        row["model_linked"] = "YES" if row.get("current_keyid") else "NO"
        if current_keyid is None:
            row["current_model_status"] = (
                "INVALID_KEYID" if row.get("current_keyid") else "UNLINKED"
            )
            return
        try:
            decoded = db.verify_keyid(current_keyid)
            row["current_device_id"] = int_or_none(decoded.get("device_id"))
            row["current_table_id"] = int_or_none(decoded.get("tab_no"))
            row["current_domain"] = int_or_none(decoded.get("col_no"))
            current_id = row.get("current_device_id")
            if current_id is not None:
                current = db.get_transformer_device_by_id(
                    TRANSFORMER_TABLE_ID,
                    current_id,
                )
                if current:
                    row["current_db_name"] = norm(current.get("name"))
                    row["current_db_code"] = norm(current.get("code"))
                    row["current_feeder_id"] = str(
                        current.get("feeder_id") or ""
                    ).strip()
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"
            return
        row["current_model_status"] = "DECODED"

    def _resolve_row(self, row, db, feeder, feeder_source):
        name = str(row.get("graphical_name") or "").strip()
        feeder_id = int_or_none((feeder or {}).get("id"))
        row.update({
            "selected_device_name": name,
            "feeder_resolution_source": feeder_source,
            "source_feeder_id": feeder_id or "",
            "source_feeder_name": str((feeder or {}).get("display_name") or "").strip(),
            "feeder_id": feeder_id or "",
            "feeder_name": str((feeder or {}).get("display_name") or "").strip(),
            "table_id": TRANSFORMER_TABLE_ID,
            "table_name": "dms_tr_device",
            "configured_domain": TRANSFORMER_DOMAIN,
            "db_match_count": 0,
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_feeder_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "NO",
            "model_link_correct": "NO",
            "model_link_status": "",
            "association_action": "",
            "writeback_needed": "NO",
            "association_ready": "NO",
        })
        self._current_link_fields(row, db)

        if feeder_id is None:
            return self._fail(
                row,
                "TRANSFORMER_FEEDER_NOT_RESOLVED: G 根 facID 和唯一 facName 均未能解析到 13500 馈线。",
            )
        if not name:
            return self._fail(
                row,
                "TRANSFORMER_NAME_NOT_FOUND: 未找到 Transformer_OH 图元对应的最近 Text。",
            )

        records = db.get_transformer_devices_by_name(
            name,
            feeder_id=feeder_id,
            table_id=TRANSFORMER_TABLE_ID,
        )
        row["db_match_count"] = len(records)
        if len(records) != 1:
            return self._fail(
                row,
                "TRANSFORMER_DATABASE_NOT_UNIQUE: "
                f"dms_tr_device NAME={name} 且 FEEDER_ID={feeder_id}；匹配数={len(records)}。",
            )

        device = records[0]
        device_id = int_or_none(device.get("id"))
        if device_id is None:
            return self._fail(row, "TRANSFORMER_DEVICE_ID_INVALID: 13505.ID 无效。")
        expected = self._make_expected_keyid(device_id)
        row.update({
            "db_device_id": device_id,
            "db_code": norm(device.get("code")),
            "db_name": norm(device.get("name")),
            "db_feeder_id": str(device.get("feeder_id") or "").strip(),
            "expected_keyid": expected,
        })
        try:
            decoded = db.verify_keyid(expected)
            verified = (
                int_or_none(decoded.get("device_id")) == device_id
                and int_or_none(decoded.get("tab_no")) == TRANSFORMER_TABLE_ID
                and int_or_none(decoded.get("col_no")) == TRANSFORMER_DOMAIN
            )
        except Exception as exc:
            return self._fail(
                row,
                f"TRANSFORMER_EXPECTED_KEYID_VERIFY_ERROR: {exc}",
            )
        row["expected_keyid_verified"] = "YES" if verified else "NO"
        if not verified:
            return self._fail(
                row,
                "TRANSFORMER_EXPECTED_KEYID_VERIFY_FAILED: 13505/domain=1。",
            )

        current_keys = self._current_keyids(row)
        if current_keys[0] == expected and current_keys[1] == expected:
            row.update({
                "status": "PASS",
                "severity": "PASS",
                "model_link_correct": "YES",
                "model_link_status": "当前 keyid1/keyid2 均正确",
                "association_action": "无需回写",
                "writeback_needed": "NO",
                "association_ready": "YES",
                "reason": "TRANSFORMER_MODEL_LINK_CORRECT",
            })
        else:
            has_current = bool(row.get("current_keyid1") or row.get("current_keyid2"))
            row.update({
                "status": "RELINK" if has_current else "UNLINKED",
                "severity": "RELINK" if has_current else "WARN",
                "model_link_status": (
                    "当前 keyid1/keyid2 为空，尚未关联"
                    if not has_current
                    else "当前 keyid1/keyid2 不是目标 13505/domain=1"
                ),
                "association_action": "重新关联柱上变压器" if has_current else "关联柱上变压器",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "reason": "TRANSFORMER_ASSOCIATION_READY",
            })
        return row

    @staticmethod
    def _fail(row, reason):
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "reason": reason,
            "association_ready": "NO",
            "writeback_needed": "NO",
        })
        return row

    def _analyze_file(self, db, g_file, settings=None, log_callback=None, progress_callback=None):
        parsed = GParser().parse(g_file)
        discovered, context = TransformerParser().discover(
            parsed,
            (settings or {}).get("element_catalog", {}),
            settings or {},
        )
        rows = []
        total = max(len(discovered), 1)
        for index, row in enumerate(discovered, start=1):
            row_context = dict(context)
            row_source_keyids = list(row.get("source_cbreaker_keyids") or [])
            if row_source_keyids:
                row_context["source_cbreaker_keyids"] = row_source_keyids
            feeder, feeder_source = self._resolve_feeder(db, row_context)
            resolved = self._resolve_row(dict(row), db, feeder, feeder_source)
            resolved["file_name"] = Path(g_file).name
            rows.append(resolved)
            if progress_callback:
                progress_callback(
                    index,
                    total,
                    f"正在处理柱上变压器 {index}/{len(discovered)}",
                )
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 柱上变压器识别完成："
                f"TransformerDis={len(discovered)}；"
                f"主网CBreaker={context.get('source_cbreaker_count', 0)}；"
                f"数据库可关联={sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "TRANSFORMER",
            "transformer_rows": rows,
            "summary": {
                "transformer_count": len(rows),
                "transformer_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "transformer_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "transformer_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "transformer_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
                "association_ready_count": sum(1 for row in rows if row.get("association_ready") == "YES"),
            },
        }

    def validate(self, db, files, settings, log_callback, progress_callback=None):
        reports = []
        aggregate = defaultdict(int)
        total_files = max(len(files), 1)
        for file_index, g_file in enumerate(files, start=1):
            report = self._analyze_file(
                db,
                g_file,
                settings,
                log_callback,
                lambda current, total, message: progress_callback(
                    int(((file_index - 1) + current / max(total, 1)) / total_files * 90) + 5,
                    message,
                ) if progress_callback else None,
            )
            reports.append(report)
            for key, value in report["summary"].items():
                aggregate[key] += value
        return reports, dict(aggregate), self._rules()

    def preview_association(self, db, files, settings, log_callback, progress_callback=None):
        reports, summary, rules = self.validate(
            db, files, settings, log_callback, progress_callback
        )
        changes_by_file = defaultdict(list)
        rows = []
        for report in reports:
            for row in report.get("transformer_rows", []):
                if row.get("association_ready") != "YES" or row.get("writeback_needed") != "YES":
                    continue
                change = {
                    "xml_id": row["xml_id"],
                    "tag": row.get("object_type") or TRANSFORMER_TAG,
                    "_source_file": report["g_file"],
                    "attributes": self._attributes_for_row(row),
                    "device_name": row.get("selected_device_name", ""),
                    "device_id": row.get("db_device_id", ""),
                    "expected_keyid": row.get("expected_keyid", ""),
                    "validated_row": dict(row),
                }
                changes_by_file[report["g_file"]].append(change)
                output_row = dict(row)
                output_row["reason"] = (
                    "PREVIEW_WRITE app1/app2=6500000 voltype1/voltype2=0 "
                    "p_ReportType1/p_ReportType2=1 state1/state2=18 "
                    f"keyid1/keyid2={row.get('expected_keyid', '')}"
                )
                rows.append(output_row)

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        summary = dict(summary)
        summary["association_change_count"] = sum(len(items) for items in changes_by_file.values())
        return {
            "reports": reports,
            "rows": rows,
            "summary": summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "transformer_table_id": TRANSFORMER_TABLE_ID,
                "transformer_domain": TRANSFORMER_DOMAIN,
                "element_catalog": settings.get("element_catalog", {}),
            },
        }

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        if not preview_data or not preview_data.get("changes_by_file"):
            raise RuntimeError("没有可执行的柱上变压器模型关联结果。")
        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        changes_by_file = preview_data.get("changes_by_file", {})
        execution_rows = []
        executable = defaultdict(list)
        selected_count = sum(len(items) for items in changes_by_file.values())
        source_map = {str(Path(item).resolve()): Path(item) for item in files}
        for source_file, fingerprint in (preview_data.get("file_fingerprints", {}) or {}).items():
            path = Path(source_file)
            stat = path.stat()
            if stat.st_size != fingerprint.get("size") or stat.st_mtime_ns != fingerprint.get("mtime_ns"):
                raise RuntimeError(f"G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验：{source_file}")

        for source_file, changes in changes_by_file.items():
            for change in changes:
                base = dict(change.get("validated_row", {}) or {})
                current = self._resolve_row(
                    dict(base),
                    db,
                    {
                        "id": base.get("feeder_id"),
                        "display_name": base.get("feeder_name"),
                    },
                    base.get("feeder_resolution_source", "G_ROOT_FACID"),
                )
                if current.get("association_ready") != "YES" or current.get("writeback_needed") != "YES":
                    current["_execution_result"] = "SKIPPED"
                    execution_rows.append((change, current))
                    continue
                refreshed = dict(change)
                refreshed["attributes"] = self._attributes_for_row(current)
                refreshed["validated_row"] = current
                executable[source_file].append(refreshed)
                current["_execution_result"] = "READY"
                execution_rows.append((refreshed, current))

        output_dir = Path(output_g_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        copied_files = []
        applied = 0
        writer = GWriteBackService(log=log_callback)
        for source_file, changes in executable.items():
            if not changes:
                continue
            source = source_map.get(str(Path(source_file).resolve()), Path(source_file))
            target = output_dir / source.name
            if target.exists():
                stem, suffix, index = target.stem, target.suffix, 2
                while True:
                    candidate = output_dir / f"{stem}_{index}{suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1
            target.write_bytes(source.read_bytes())
            result = writer.apply_attribute_changes(target, changes, create_backup=False)
            applied += int(result.get("applied_count", 0))
            copied_files.append(str(target))

        operation_reports = []
        by_file = defaultdict(list)
        for change, row in execution_rows:
            item = dict(row)
            item["status"] = "PASS" if row.get("_execution_result") == "READY" else "FAIL"
            item["severity"] = item["status"]
            item["reason"] = "ASSOCIATION_EXECUTED" if item["status"] == "PASS" else item.get("reason", "EXECUTION_SKIPPED")
            by_file[str(change.get("_source_file") or "")].append(item)
        for source_file, rows in by_file.items():
            operation_reports.append({
                "g_file": source_file,
                "file_name": Path(source_file).name,
                "report_type": "TRANSFORMER",
                "transformer_rows": rows,
                "summary": {"transformer_count": len(rows)},
            })
        return {
            "selected_count": selected_count,
            "applied_count": applied,
            "skipped_count": max(selected_count - applied, 0),
            "output_g_dir": str(output_dir),
            "copied_files": copied_files,
            "operation_reports": operation_reports,
            "rules": self._rules(),
        }
