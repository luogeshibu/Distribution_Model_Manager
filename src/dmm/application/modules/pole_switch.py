from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from pathlib import Path

from dmm.application.modules.base import ModelModule
from dmm.config.constants import RMU_LABEL_EDGE_TOLERANCE
from dmm.domain.gfile.parser import GParser, GObject, ParsedG
from dmm.domain.rmu.validator import int_or_none, norm
from dmm.infrastructure.gfile.writeback import GWriteBackService


POLE_SWITCH_TABLE_ID = 13502
POLE_SWITCH_DOMAIN = 40
POLE_SWITCH_TAG = "CBreakerDis"

# The complete devref is the recognition authority.  The short family name
# is only a report/display value and must never be searched in arbitrary XML
# attributes such as key_name or p_NameString.
POLE_SWITCH_DEVREFS = {
    "#RMU_LBS_NON.zwk.icn.g:RMU_LBS_NON": "LBS_NON",
    "#RMU_LBS_S.zwk.icn.g:RMU_LBS_S": "LBS_S",
    "#SEC_S_H.zwk.icn.g:SEC_S_H": "SEC_S_H",
    "#AR_S.zwk.icn.g:AR_S": "AR_S",
}

POLE_SWITCH_NAME_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.\-/]{0,127}$"
)

_NON_NAME_LABELS = {
    "SMART",
    "SMR",
    "NOP",
    "N.O.P",
    "N-O-P",
    "N_O_P",
    "F.C",
    "FC",
    "BUS",
    "G",
    "I",
}


def _norm_devref(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def _point_to_box_distance(x: float, y: float, obj: GObject) -> float:
    box = obj.box
    dx = max(float(box.left) - x, 0.0, x - float(box.right))
    dy = max(float(box.top) - y, 0.0, y - float(box.bottom))
    return math.hypot(dx, dy)


class PoleSwitchParser:
    """Recognize standalone pole switches and preserve topology evidence."""

    def __init__(self):
        self.rmu_parser = GParser(
            required_rmu_tags={
                "CBreakerDis",
                "ZhaiWaiJieDiDaoZha",
                "BusDis",
            },
            overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
        )

    @staticmethod
    def _refs(obj: GObject):
        refs = []
        for attr_name in ("link", "node_area"):
            raw = str(obj.attrs.get(attr_name) or "")
            for part in raw.split(";"):
                bits = [item.strip() for item in part.split(",")]
                if len(bits) >= 3 and bits[2]:
                    refs.append(bits[2])
        return list(dict.fromkeys(refs))

    @staticmethod
    def _text_value(obj: GObject) -> str:
        return str(obj.attrs.get("ts") or "").strip()

    @staticmethod
    def _is_valid_name(text: str) -> bool:
        value = str(text or "").strip()
        if not value or not any(char.isalnum() for char in value):
            return False
        if value.upper() in _NON_NAME_LABELS:
            return False
        if re.fullmatch(r"[YQ]\d+", value.replace(" ", "").upper()):
            return False
        # Pure numeric labels in this drawing are transformer/line numbers,
        # not the pole-switch names requested by this module.
        if value.isdigit():
            return False
        return bool(POLE_SWITCH_NAME_RE.fullmatch(value))

    @staticmethod
    def _model_family(model: str) -> str:
        model = str(model or "").upper()
        if model.startswith("RMU_LBS"):
            return "LBS"
        if model.startswith("SEC"):
            return "SEC"
        if model.startswith("AR"):
            return "AR"
        return ""

    @classmethod
    def _family_matches_name(cls, model: str, text: str) -> bool:
        family = cls._model_family(model)
        compact = re.sub(r"[^A-Z0-9]", "", str(text or "").upper())
        return bool(family and compact.startswith(family))

    def _rmu_frame_objects(self, parsed: ParsedG):
        return self.rmu_parser.find_rmu_frames(parsed)

    @staticmethod
    def _is_inside_rmu(obj: GObject, frames) -> bool:
        return any(
            frame.frame.box.center_contains(obj.box, tolerance=1.0)
            for frame in frames
        )

    def _build_topology(self, parsed: ParsedG):
        by_id = {
            str(obj.xml_id): obj
            for obj in parsed.objects
            if str(obj.xml_id or "")
        }
        graph = defaultdict(set)
        for obj in parsed.objects:
            xml_id = str(obj.xml_id or "")
            if not xml_id:
                continue
            for ref in self._refs(obj):
                if ref not in by_id:
                    continue
                graph[xml_id].add(ref)
                graph[ref].add(xml_id)

        components = {}
        visited = set()
        for xml_id in by_id:
            if xml_id in visited:
                continue
            queue = deque([xml_id])
            visited.add(xml_id)
            members = []
            while queue:
                current = queue.popleft()
                members.append(current)
                for nxt in graph.get(current, ()):
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append(nxt)
            component_id = "TOPOLOGY_" + min(members)
            member_set = set(members)
            for member in members:
                components[member] = {
                    "component_id": component_id,
                    "member_ids": member_set,
                }
        return by_id, graph, components

    def find_nearest_name(self, parsed: ParsedG, target: GObject, model: str, frames=()):
        candidates = []
        for obj in parsed.objects:
            if obj.tag.lower() != "text":
                continue
            # A standalone switch must not borrow a label from an RMU that is
            # nearby in the drawing.  RMU-internal labels are valid names for
            # the RMU module, but are not candidates for this module.
            if frames and self._is_inside_rmu(obj, frames):
                continue
            text = self._text_value(obj)
            if not self._is_valid_name(text):
                continue
            distance = _point_to_box_distance(
                target.box.cx,
                target.box.cy,
                obj,
            )
            # Distance is the primary rule required by the pole-switch
            # drawing convention.  Family consistency is only a tie-breaker;
            # it must never make a farther label beat the nearest label.
            family_penalty = 0 if self._family_matches_name(model, text) else 1
            candidates.append((
                distance,
                family_penalty,
                obj.xml_index,
                text,
                obj,
            ))
        if not candidates:
            return None, []
        candidates.sort(key=lambda item: item[:3])
        chosen = candidates[0]
        return {
            "text": chosen[3],
            "distance": round(float(chosen[0]), 3),
            "direction": self._direction(target, chosen[4]),
            "xml_id": chosen[4].xml_id,
            "object": chosen[4],
        }, [
            {
                "text": item[3],
                "distance": round(float(item[0]), 3),
                "family_match": "YES" if item[1] == 0 else "NO",
                "xml_id": item[4].xml_id,
            }
            for item in candidates[:10]
        ]

    @staticmethod
    def _direction(target: GObject, label: GObject) -> str:
        if label.box.cy < target.box.top:
            return "top"
        if label.box.cy > target.box.bottom:
            return "bottom"
        if label.box.cx < target.box.left:
            return "left"
        if label.box.cx > target.box.right:
            return "right"
        return "near"

    def discover(self, parsed: ParsedG):
        frames = self._rmu_frame_objects(parsed)
        by_id, graph, components = self._build_topology(parsed)
        rows = []
        for obj in parsed.objects:
            if obj.tag != POLE_SWITCH_TAG:
                continue
            raw_devref = str(obj.attrs.get("devref") or "").strip()
            model = next(
                (
                    model_name
                    for devref, model_name in POLE_SWITCH_DEVREFS.items()
                    if _norm_devref(raw_devref) == _norm_devref(devref)
                ),
                "",
            )
            if not model or self._is_inside_rmu(obj, frames):
                continue

            label, _label_candidates = self.find_nearest_name(
                parsed,
                obj,
                model,
                frames,
            )
            component = components.get(str(obj.xml_id), {})
            member_ids = component.get("member_ids", set())
            member_tags = [
                by_id[member].tag
                for member in member_ids
                if member in by_id
            ]
            row = {
                "object_type": obj.tag,
                "xml_id": obj.xml_id,
                "x": obj.box.x,
                "y": obj.box.y,
                "w": obj.box.w,
                "h": obj.box.h,
                "devref": raw_devref,
                "device_model": model,
                "device_family": self._model_family(model),
                "key_name": str(obj.attrs.get("key_name") or "").strip(),
                "current_keyid": obj.keyid,
                "inside_rmu": "NO",
                "topology_component": component.get("component_id", ""),
                "topology_member_count": len(member_ids),
                "topology_member_ids": ",".join(sorted(member_ids)),
                "topology_member_tags": ",".join(sorted(set(member_tags))),
                "topology_neighbor_count": len(graph.get(str(obj.xml_id), set())),
                "topology_neighbor_ids": ",".join(
                    sorted(graph.get(str(obj.xml_id), set()))
                ),
                "graphical_name": label.get("text", "") if label else "",
                "name_source": "NEAREST_GRAPHICAL_TEXT" if label else "",
                "name_distance": label.get("distance", "") if label else "",
                "name_direction": label.get("direction", "") if label else "",
                "name_xml_id": label.get("xml_id", "") if label else "",
                "status": "",
                "severity": "",
                "reason": "",
            }
            rows.append(row)
        return rows


class PoleSwitchModelModule(ModelModule):
    module_id = "POLE_SWITCH"
    display_name = "柱上开关模型"
    description = (
        "识别 G 文件中环网柜外的 LBS / AR / SEC 柱上开关，"
        "按图上邻近名称关联 13501 / 13502 并安全回写 KeyID。"
    )
    SUPPORTED_OPERATIONS = (
        "VALIDATE",
        "PREVIEW_ASSOCIATION",
        "APPLY_ASSOCIATION",
    )

    @staticmethod
    def _rules():
        return {
            "CBreakerDis": {
                "table_id": POLE_SWITCH_TABLE_ID,
                "domain": POLE_SWITCH_DOMAIN,
                "match_mode": "COMBINED_CODE_TO_ID_THEN_CB_COMBINED_ID",
                "description": "柱上开关：13501 NAME/CODE -> 13501 ID -> 13502 combined_id",
            }
        }

    @staticmethod
    def _attributes_for_row(row):
        bv_id = str(row.get("db_bv_id") or "").strip()
        if not bv_id:
            raise ValueError(
                f"{row.get('object_type')}:{row.get('xml_id')}: "
                "数据库 dms_cb_device BV_ID 为空，禁止生成模型回写。"
            )
        return {
            "app": "6500000",
            "voltype": bv_id,
            "p_ReportType": "1",
            "state": "41",
            "keyid": str(row["expected_keyid"]),
        }

    @staticmethod
    def _make_expected_keyid(device_id):
        # Keep the same D5000 encoding used by RMU CBreakerDis:
        # KeyID = device_id + (domain << 32).
        device_id = int(device_id)
        if device_id < 0:
            raise ValueError(f"Invalid device_id: {device_id}")
        return device_id + (POLE_SWITCH_DOMAIN << 32)

    @staticmethod
    def _normalize_name(value):
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

    @classmethod
    def _record_matches_family(cls, record, family):
        family = re.sub(r"[^A-Z0-9]", "", str(family or "").upper())
        if not family:
            return False
        values = (
            record.get("code"),
            record.get("name"),
            record.get("name_alias"),
        )
        return any(
            re.sub(r"[^A-Z0-9]", "", str(value or "").upper()) == family
            for value in values
        )

    def _current_link_fields(self, row, db):
        current_keyid = int_or_none(row.get("current_keyid"))
        if current_keyid is None:
            if row.get("current_keyid"):
                row["current_model_status"] = "INVALID_KEYID"
            else:
                row["current_model_status"] = "UNLINKED"
            row["model_linked"] = "YES" if row.get("current_keyid") else "NO"
            return

        row["model_linked"] = "YES"
        try:
            decoded = db.verify_keyid(current_keyid)
            row["current_device_id"] = int_or_none(decoded.get("device_id"))
            row["current_table_id"] = int_or_none(decoded.get("tab_no"))
            row["current_domain"] = int_or_none(decoded.get("col_no"))
            if row["current_device_id"] is not None:
                current = db.get_device_by_id(
                    POLE_SWITCH_TABLE_ID,
                    row["current_device_id"],
                )
                if current:
                    row["current_db_name"] = norm(current.get("name"))
                    row["current_db_code"] = norm(current.get("code"))
                    row["current_combined_id"] = str(
                        current.get("combined_id") or ""
                    ).strip()
        except Exception as exc:
            row["current_model_status"] = f"VERIFY_ERROR: {exc}"
            return
        row["current_model_status"] = "DECODED"

    def _resolve_row(self, row, db):
        name = str(row.get("graphical_name") or "").strip()
        row.update({
            "logical_code": name,
            "selected_device_name": name,
            "table_id": POLE_SWITCH_TABLE_ID,
            "table_name": "dms_cb_device",
            "configured_domain": POLE_SWITCH_DOMAIN,
            "match_mode": "COMBINED_CODE_TO_ID_THEN_CB_COMBINED_ID",
            "combined_db_match_count": 0,
            "cb_parent_match_count": 0,
            "cb_db_match_count": 0,
            "db_combined_id": "",
            "combined_match_field": "",
            "db_device_id": "",
            "db_code": "",
            "db_name": "",
            "db_bv_id": "",
            "expected_keyid": "",
            "expected_keyid_verified": "NO",
            "model_link_correct": "NO",
            "model_link_status": "",
            "association_action": "",
            "writeback_needed": "NO",
            "association_ready": "NO",
        })
        self._current_link_fields(row, db)

        if not name:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_NAME_NOT_FOUND: 未找到柱上开关邻近图上名称。",
            })
            return row

        combined_records = db.get_combined_device_records(name)
        row["combined_db_match_count"] = len(combined_records)
        if len(combined_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_COMBINED_NAME_NOT_UNIQUE: "
                    f"13501 NAME/CODE={name}；匹配数={len(combined_records)}。"
                ),
            })
            return row

        combined = combined_records[0]
        combined_id = int_or_none(combined.get("id"))
        if combined_id is None:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_COMBINED_ID_INVALID: 13501 ID 无效。",
            })
            return row
        row["db_combined_id"] = combined_id
        row["combined_name"] = name
        row["combined_db_code"] = str(combined.get("code") or "").strip()
        row["combined_db_name"] = str(combined.get("name") or "").strip()
        row["combined_match_field"] = str(
            combined.get("_matched_field") or "NAME_OR_CODE"
        )

        cb_parent_records = db.get_cb_devices_by_combined_device_id(
            combined_id
        )
        row["cb_parent_match_count"] = len(cb_parent_records)

        # A standalone parent normally has one child CBreakerDis. If a
        # parent has multiple children, use the devref-derived device family
        # (SEC / AR / LBS) to select exactly one child; never choose by row
        # order because RMU parents contain several Y/Q switches.
        family = str(row.get("device_family") or "").strip().upper()
        family_records = [
            device
            for device in cb_parent_records
            if self._record_matches_family(device, family)
        ]
        cb_records = (
            family_records
            if len(cb_parent_records) != 1
            else cb_parent_records
        )
        row["cb_db_match_count"] = len(cb_records)
        if len(cb_records) != 1:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_CB_NOT_UNIQUE: "
                    f"13502 combined_id={combined_id}；父设备记录数="
                    f"{len(cb_parent_records)}；按设备族={family}筛选后="
                    f"{len(cb_records)}。"
                ),
            })
            return row

        device = cb_records[0]
        device_id = int_or_none(device.get("id"))
        if device_id is None:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_DEVICE_ID_INVALID: 13502 ID 无效。",
            })
            return row
        if int_or_none(device.get("combined_id")) != combined_id:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": (
                    "POLE_SWITCH_CB_COMBINED_ID_MISMATCH: "
                    f"数据库={device.get('combined_id')}; 13501.ID={combined_id}。"
                ),
            })
            return row

        bv_id = str(device.get("bv_id") or "").strip()
        if not bv_id:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_BV_ID_EMPTY: 13502 BV_ID 为空。",
            })
            return row

        expected = self._make_expected_keyid(device_id)
        row.update({
            "db_device_id": device_id,
            "db_code": norm(device.get("code")),
            "db_name": norm(device.get("name")),
            "db_cb_combined_id": str(device.get("combined_id") or "").strip(),
            "db_bv_id": bv_id,
            "expected_keyid": expected,
        })
        try:
            decoded = db.verify_keyid(expected)
            verified = (
                int_or_none(decoded.get("device_id")) == device_id
                and int_or_none(decoded.get("tab_no")) == POLE_SWITCH_TABLE_ID
                and int_or_none(decoded.get("col_no")) == POLE_SWITCH_DOMAIN
            )
        except Exception as exc:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": f"POLE_SWITCH_EXPECTED_KEYID_VERIFY_ERROR: {exc}",
            })
            return row
        row["expected_keyid_verified"] = "YES" if verified else "NO"
        if not verified:
            row.update({
                "status": "FAIL",
                "severity": "ERROR",
                "reason": "POLE_SWITCH_EXPECTED_KEYID_VERIFY_FAILED: 13502/domain=40。",
            })
            return row

        if int_or_none(row.get("current_keyid")) == expected:
            row.update({
                "status": "PASS",
                "severity": "PASS",
                "model_link_correct": "YES",
                "model_link_status": "当前 KeyID 正确",
                "association_action": "无需回写",
                "writeback_needed": "NO",
                "association_ready": "YES",
                "reason": "POLE_SWITCH_MODEL_LINK_CORRECT",
            })
        else:
            row.update({
                "status": "RELINK" if row.get("current_keyid") else "UNLINKED",
                "severity": "RELINK" if row.get("current_keyid") else "WARN",
                "model_link_correct": "NO",
                "model_link_status": (
                    "当前 KeyID 为空，尚未关联"
                    if not row.get("current_keyid")
                    else "当前 KeyID 不是目标 13502/domain=40"
                ),
                "association_action": "关联柱上开关" if not row.get("current_keyid") else "重新关联柱上开关",
                "writeback_needed": "YES",
                "association_ready": "YES",
                "reason": "POLE_SWITCH_ASSOCIATION_READY",
            })
        return row

    def _analyze_file(self, db, g_file, log_callback=None, progress_callback=None):
        parsed = GParser().parse(g_file)
        discovered = PoleSwitchParser().discover(parsed)
        rows = []
        total = max(len(discovered), 1)
        for index, row in enumerate(discovered, start=1):
            resolved = self._resolve_row(dict(row), db)
            resolved["file_name"] = Path(g_file).name
            rows.append(resolved)
            if progress_callback:
                progress_callback(index, total, f"正在处理柱上开关 {index}/{len(discovered)}")
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 柱上开关识别完成："
                f"devref目标={len(discovered)}；数据库可关联="
                f"{sum(1 for row in rows if row.get('association_ready') == 'YES')}"
            )
        return {
            "g_file": str(Path(g_file)),
            "file_name": Path(g_file).name,
            "report_type": "POLE_SWITCH",
            "pole_switch_rows": rows,
            "summary": {
                "pole_switch_count": len(rows),
                "pole_switch_pass": sum(1 for row in rows if row.get("status") == "PASS"),
                "pole_switch_fail": sum(1 for row in rows if row.get("status") == "FAIL"),
                "pole_switch_unlinked": sum(1 for row in rows if row.get("status") == "UNLINKED"),
                "pole_switch_relink": sum(1 for row in rows if row.get("status") == "RELINK"),
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
            db,
            files,
            settings,
            log_callback,
            progress_callback,
        )
        changes_by_file = defaultdict(list)
        rows = []
        for report in reports:
            for row in report.get("pole_switch_rows", []):
                if row.get("association_ready") != "YES" or row.get("writeback_needed") != "YES":
                    continue
                change = {
                    "xml_id": row["xml_id"],
                    "tag": POLE_SWITCH_TAG,
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
                    "PREVIEW_WRITE app=6500000 voltype="
                    f"{row.get('db_bv_id', '')} p_ReportType=1 state=41 "
                    f"keyid={row.get('expected_keyid', '')}"
                )
                rows.append(output_row)

        fingerprints = {}
        for g_file in changes_by_file:
            path = Path(g_file)
            stat = path.stat()
            fingerprints[g_file] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        summary = dict(summary)
        summary["association_change_count"] = sum(
            len(items) for items in changes_by_file.values()
        )
        return {
            "reports": reports,
            "rows": rows,
            "summary": summary,
            "rules": rules,
            "changes_by_file": dict(changes_by_file),
            "file_fingerprints": fingerprints,
            "settings_snapshot": {
                "pole_switch_table_id": POLE_SWITCH_TABLE_ID,
                "pole_switch_domain": POLE_SWITCH_DOMAIN,
            },
        }

    def apply_association(self, db, files, settings, preview_data, log_callback, output_g_dir=None):
        if not preview_data or not preview_data.get("changes_by_file"):
            raise RuntimeError("没有可执行的柱上开关模型关联结果。")
        if not output_g_dir:
            raise RuntimeError("未提供安全 G 文件输出目录。")

        changes_by_file = preview_data.get("changes_by_file", {})
        execution_rows = []
        executable = defaultdict(list)
        selected_count = sum(len(items) for items in changes_by_file.values())
        source_map = {str(Path(item).resolve()): Path(item) for item in files}

        for source_file, fingerprint in (
            preview_data.get("file_fingerprints", {}) or {}
        ).items():
            path = Path(source_file)
            stat = path.stat()
            if (
                stat.st_size != fingerprint.get("size")
                or stat.st_mtime_ns != fingerprint.get("mtime_ns")
            ):
                raise RuntimeError(
                    "G 文件在模型校验后发生变化，禁止使用旧结果，请重新校验："
                    f"{source_file}"
                )

        for source_file, changes in changes_by_file.items():
            for change in changes:
                base = dict(change.get("validated_row", {}) or {})
                current = self._resolve_row(dict(base), db)
                if (
                    current.get("association_ready") != "YES"
                    or current.get("writeback_needed") != "YES"
                ):
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
                stem = target.stem
                suffix = target.suffix
                index = 2
                while True:
                    candidate = output_dir / f"{stem}_{index}{suffix}"
                    if not candidate.exists():
                        target = candidate
                        break
                    index += 1
            source_bytes = source.read_bytes()
            target.write_bytes(source_bytes)
            result = writer.apply_attribute_changes(
                target,
                changes,
                create_backup=False,
            )
            applied += int(result.get("applied_count", 0))
            copied_files.append(str(target))

        operation_reports = []
        by_file = defaultdict(list)
        for change, row in execution_rows:
            item = dict(row)
            item["status"] = (
                "PASS" if row.get("_execution_result") == "READY" else "FAIL"
            )
            item["severity"] = item["status"]
            item["reason"] = (
                "ASSOCIATION_EXECUTED"
                if item["status"] == "PASS"
                else item.get("reason", "EXECUTION_SKIPPED")
            )
            by_file[str(change.get("_source_file") or "")].append(item)
        for source_file, rows in by_file.items():
            operation_reports.append({
                "g_file": source_file,
                "file_name": Path(source_file).name,
                "report_type": "POLE_SWITCH",
                "pole_switch_rows": rows,
                "summary": {"pole_switch_count": len(rows)},
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
