"""Strict, explainable feeder resolution shared by model modules.

The model modules must not infer a drawing feeder from topology.  They may
use a uniquely resolved database object already represented in the drawing.
This module only normalizes those candidates and applies the same precedence
and uniqueness rule everywhere.
"""

from __future__ import annotations

from dmm.config.defaults import (
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    resolve_rmu_name_positions,
)
from dmm.domain.rmu.validator import int_or_none


_PRIORITY = ("RMU", "POLE_SWITCH", "TRANSFORMER")


def _candidate(kind, *, identity="", name="", feeder=None, source=""):
    return {
        "kind": str(kind or "OTHER").upper(),
        "identity": str(identity or "").strip(),
        "name": str(name or "").strip(),
        "feeder_id": int_or_none(feeder),
        "source": str(source or "").strip(),
    }


def candidate_from_record(
    db,
    record,
    *,
    kind,
    identity="",
    name="",
    source="DATABASE_RECORD",
):
    """Build a candidate from a database row.

    Most device tables expose FEEDER_ID directly.  The 407/408/409 tables
    commonly expose BAY_ID instead, so the only permitted fallback is the
    exact BAY -> station -> 13500 feeder lookup.
    """
    record = record or {}
    feeder_id = int_or_none(record.get("feeder_id"))
    if feeder_id is None:
        bay_id = int_or_none(record.get("bay_id"))
        if bay_id is not None and db is not None:
            try:
                bay = db.get_bay_by_id(bay_id) or {}
                hint = str(
                    bay.get("code") or bay.get("graph_name") or bay.get("name") or ""
                ).strip()
                station_id = int_or_none(bay.get("st_id"))
                feeders = db.find_feeders_by_bay(hint, station_id)
                if len(feeders) == 1:
                    feeder_id = int_or_none(feeders[0].get("id"))
            except Exception:
                feeder_id = None
    return _candidate(
        kind,
        identity=identity or record.get("id") or record.get("code"),
        name=name or record.get("name") or record.get("code"),
        feeder=feeder_id,
        source=source,
    )


def candidate_from_keyid(
    db,
    keyid,
    *,
    kind="RMU",
    source="G_KEYID",
    name="",
    keep_unresolved=False,
):
    """Resolve a current G-file KeyID to its owning RMU feeder."""
    value = int_or_none(keyid)
    if value is None or db is None or not hasattr(db, "verify_keyid"):
        return (
            _candidate(kind, identity=keyid, name=name, source=source)
            if keep_unresolved and value is not None
            else None
        )
    try:
        decoded = db.verify_keyid(value) or {}
        table_id = int_or_none(decoded.get("tab_no"))
        device_id = int_or_none(decoded.get("device_id"))
        if table_id is None or device_id is None:
            return (
                _candidate(kind, identity=keyid, name=name, source=source)
                if keep_unresolved
                else None
            )
        device = db.get_device_by_id(table_id, device_id) or {}
        if not device:
            return (
                _candidate(kind, identity=keyid, name=name, source=source)
                if keep_unresolved
                else None
            )
        if table_id == 13501:
            rmu = device
        else:
            combined_id = int_or_none(device.get("combined_id"))
            if combined_id is None or not hasattr(db, "get_rmu_by_id"):
                return (
                    _candidate(kind, identity=keyid, name=name, source=source)
                    if keep_unresolved
                    else None
                )
            rmu = db.get_rmu_by_id(combined_id) or {}
            if not rmu and keep_unresolved:
                return _candidate(kind, identity=keyid, name=name, source=source)
        return candidate_from_record(
            db,
            rmu,
            kind=kind,
            identity=rmu.get("id"),
            name=name or rmu.get("name") or rmu.get("code"),
            source=f"{source}:TABLE_{table_id}:DEVICE_{device_id}",
        )
    except Exception:
        return (
            _candidate(kind, identity=keyid, name=name, source=source)
            if keep_unresolved
            else None
        )


def rmu_keyid_candidates(db, parsed, *, source="RMU_FRAME_KEYID", positions=None):
    """Collect deduplicated RMU candidates from recognized RMU rectangles."""
    try:
        from dmm.domain.gfile.parser import GParser

        parser = GParser()
        frames = parser.find_rmu_frames(parsed)
    except Exception:
        frames = []
        parser = None
    try:
        if parser is None:
            raise ValueError("RMU frame parser unavailable")
        selected_positions = tuple(positions or ("top",))
        assigned_names = parser.assign_rmu_label_candidates_globally(
            parsed,
            frames,
            selected_positions,
        )
    except Exception:
        assigned_names = {}
    candidates = []
    seen = set()
    anchor_tags = {"CBreakerDis", "BusDis", "ZhaiWaiJieDiDaoZha", "pwbh"}
    for frame in frames:
        frame_key = (frame.frame.xml_index, frame.frame.xml_id)
        frame_names = assigned_names.get(frame_key, [])
        frame_name = str(frame_names[0].text if frame_names else "").strip()
        frame_candidate_count = 0
        for obj in parsed.objects:
            if obj.tag not in anchor_tags:
                continue
            if not frame.frame.box.center_contains(obj.box, tolerance=1.0):
                continue
            for key in ("keyid", "keyid1", "keyid2"):
                value = str(obj.attrs.get(key) or "").strip()
                seen_key = (frame_key, value)
                if not value or seen_key in seen:
                    continue
                seen.add(seen_key)
                candidate = candidate_from_keyid(
                    db,
                    value,
                    kind="RMU",
                    name=frame_name,
                    keep_unresolved=True,
                    source=f"{source}:{obj.tag}:{obj.xml_id or '-'}:{key}",
                )
                if candidate:
                    # Preserve the G-frame scope so the same database RMU
                    # name used by two different rectangles is not silently
                    # deduplicated before the duplicate-name guard runs.
                    candidate["identity"] = (
                        f"{candidate.get('identity') or value}@"
                        f"FRAME_{frame.frame.xml_id or frame.frame.xml_index}"
                    )
                    candidates.append(candidate)
                    frame_candidate_count += 1
        if not frame_candidate_count:
            # A recognized RMU rectangle is still a higher-priority feeder
            # source even when none of its anchor objects currently carries a
            # usable KeyID.  Keep an unresolved candidate so the resolver
            # blocks instead of falling through to a lower-priority device.
            candidates.append({
                "kind": "RMU",
                "identity": f"UNLINKED_FRAME_{frame.frame.xml_id or frame.frame.xml_index}",
                "name": frame_name,
                "feeder_id": None,
                "source": f"{source}:UNLINKED_FRAME:{frame.frame.xml_id or frame.frame.xml_index}",
            })
    return candidates


def resolve_graph_feeder(db, candidates):
    """Resolve one drawing feeder using strict precedence and uniqueness.

    Presence of a higher-priority device family is itself significant.  An
    unresolved RMU therefore cannot silently fall through to a pole switch or
    transformer.  Selected candidates must have non-empty unique names and
    their valid feeder IDs must collapse to exactly one value.
    """
    normalized = []
    seen = set()
    for item in candidates or []:
        if not item:
            continue
        value = dict(item)
        value["kind"] = str(value.get("kind") or "OTHER").upper()
        value["feeder_id"] = int_or_none(value.get("feeder_id"))
        value["identity"] = str(value.get("identity") or "").strip()
        value["name"] = str(value.get("name") or "").strip()
        value["source"] = str(value.get("source") or "").strip()
        dedupe_key = (
            value["kind"],
            value["identity"],
            value["feeder_id"],
            value["name"].casefold(),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(value)

    selected_kind = ""
    selected = []
    for kind in _PRIORITY:
        # Presence itself is significant.  If a higher-priority RMU exists
        # but is not linked/readable, never silently fall back to another
        # device family and create a false feeder assignment.
        selected = [item for item in normalized if item["kind"] == kind]
        if selected:
            selected_kind = kind
            break
    if not selected:
        selected = [
            item for item in normalized if item["feeder_id"] is not None
        ]
        selected_kind = "OTHER" if selected else ""

    names = {}
    for item in selected:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        names.setdefault(name.casefold(), []).append(item)
    duplicate_names = {
        key: values for key, values in names.items() if len(values) > 1
    }
    if duplicate_names and selected_kind == "RMU":
        duplicate_text = "; ".join(
            f"{values[0].get('name') or key}"
            f"（{len(values)}个环网柜）"
            for key, values in duplicate_names.items()
        )
        return {
            "ready": False,
            "feeder": {},
            "feeder_id": "",
            "feeder_source": "GRAPH_RMU_NAME_DUPLICATE",
            "feeder_evidence": "; ".join(
                f"RMU:{item['name'] or item['identity']}=>FEEDER_ID="
                f"{item['feeder_id'] or '-'}[{item['source'] or 'DATABASE'}]"
                for item in selected
            ),
            "reason": (
                "GRAPH_RMU_NAME_DUPLICATE: 图内环网柜名称重复，禁止关联："
                + duplicate_text
            ),
            "candidates": normalized,
        }

    # Only uniquely named devices are valid feeder evidence.  This keeps a
    # repeated graphical name from making a feeder decision for pole switches
    # or transformers as well.
    selected = [
        item for item in selected
        if str(item.get("name") or "").strip()
        and len(names.get(str(item.get("name")).strip().casefold(), [])) == 1
    ]
    feeder_ids = sorted({item["feeder_id"] for item in selected if item["feeder_id"] is not None})
    evidence_items = [
        f"{item['kind']}:{item['name'] or item['identity'] or '-'}"
        f"=>FEEDER_ID={item['feeder_id']}"
        f"[{item['source'] or 'DATABASE'}]"
        for item in selected
    ]
    evidence = "; ".join(evidence_items)

    if not selected or not feeder_ids:
        return {
            "ready": False,
            "feeder": {},
            "feeder_id": "",
            "feeder_source": "UNRESOLVED",
            "feeder_evidence": evidence or "没有唯一候选设备能够提供有效 FEEDER_ID",
            "reason": (
                f"GRAPH_FEEDER_NOT_RESOLVED: 图内存在{selected_kind or '设备'}，"
                "但没有找到名称唯一且已建模、可提供有效 FEEDER_ID 的设备；"
                "无法确定配网图馈线信息。"
            ),
            "candidates": normalized,
        }
    if len(feeder_ids) != 1:
        return {
            "ready": False,
            "feeder": {},
            "feeder_id": "",
            "feeder_source": f"GRAPH_{selected_kind}_FEEDER_CONFLICT",
            "feeder_evidence": evidence,
            "reason": (
                "GRAPH_FEEDER_NOT_UNIQUE: 图内唯一命名候选解析出多个 FEEDER_ID："
                + ", ".join(str(value) for value in feeder_ids)
            ),
            "candidates": normalized,
        }

    feeder_id = feeder_ids[0]
    feeder = db.get_feeder_info(feeder_id) if db is not None else None
    if not feeder:
        return {
            "ready": False,
            "feeder": {},
            "feeder_id": feeder_id,
            "feeder_source": f"GRAPH_{selected_kind}",
            "feeder_evidence": evidence,
            "reason": f"GRAPH_FEEDER_NOT_FOUND: FEEDER_ID={feeder_id} 无法读取 13500 馈线。",
            "candidates": normalized,
        }
    anchor = selected[0] if selected else {}
    anchor_label = " ".join(
        value for value in (
            "环网柜" if anchor.get("kind") == "RMU" else "设备",
            str(anchor.get("name") or anchor.get("identity") or "").strip(),
        ) if value
    )
    return {
        "ready": True,
        "feeder": feeder,
        "feeder_id": feeder_id,
        "feeder_source": f"GRAPH_UNIQUE_{selected_kind}",
        "feeder_evidence": evidence,
        "feeder_anchor": anchor_label,
        "reason": "",
        "candidates": normalized,
    }


def rmu_positions_from_settings(settings=None):
    """Resolve the configured RMU label directions for shared feeder checks."""
    settings = settings or {}
    return resolve_rmu_name_positions(
        settings.get("rmu_name_detection_mode", DEFAULT_RMU_NAME_DETECTION_MODE),
        settings.get("rmu_name_positions", DEFAULT_NAME_POSITIONS),
    )


def add_feeder_fields(row, resolution):
    """Add user-facing feeder source/evidence fields to a report row."""
    resolution = resolution or {}
    feeder = resolution.get("feeder") or {}
    row.update({
        "feeder_resolution_source": resolution.get("feeder_source", "UNRESOLVED"),
        "feeder_resolution_evidence": resolution.get("feeder_evidence", ""),
        "feeder_anchor": resolution.get("feeder_anchor", ""),
        "feeder_id": resolution.get("feeder_id", ""),
        "station_id": feeder.get("st_id", ""),
        "station_name": str(feeder.get("station_name") or "").strip(),
        "feeder_code": str(feeder.get("code") or "").strip(),
        "feeder_graph_name": str(feeder.get("graph_name") or "").strip(),
        "feeder_name": str(
            feeder.get("display_name") or feeder.get("name") or ""
        ).strip(),
        "feeder_path": " / ".join(
            value for value in (
                str(feeder.get("station_name") or "").strip(),
                str(feeder.get("code") or feeder.get("name") or "").strip(),
            ) if value
        ),
    })
    return row
