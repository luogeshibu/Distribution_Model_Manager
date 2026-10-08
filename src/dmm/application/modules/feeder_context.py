"""Strict, explainable Jeddah feeder resolution shared by model modules.

For production drawing resolution, the G filename is the only authoritative
feeder source: filename -> 405/substation -> 13500/dms_feeder_device. Graphical
devices may be inspected for their own association, but never select or
override the drawing FEEDER_ID.
"""

from __future__ import annotations

import re

from dmm.config.constants import (
    RMU_LABEL_SEARCH_MAX_DISTANCE,
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
)
from dmm.config.defaults import (
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    DEFAULT_RMU_NAME_EXCLUSIONS,
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
    """Resolve one drawing feeder using the same first-unique priority rule.

    This compatibility helper accepts already-normalized/pre-resolved
    candidates.  It scans RMU -> Pole Switch -> Transformer and uses the first
    candidate in that order that has a name, an effective unique-match state
    (when db_match_count is supplied), and a valid FEEDER_ID.  If a family has
    no usable candidate, resolution falls through to the next family.
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

    selected = None
    selected_kind = ""
    for kind in _PRIORITY:
        for item in normalized:
            if item.get("kind") != kind:
                continue
            count = item.get("db_match_count")
            if count is not None and int_or_none(count) != 1:
                continue
            if not str(item.get("name") or "").strip():
                continue
            if int_or_none(item.get("feeder_id")) is None:
                continue
            selected = item
            selected_kind = kind
            break
        if selected:
            break

    if selected is None:
        for item in normalized:
            count = item.get("db_match_count")
            if count is not None and int_or_none(count) != 1:
                continue
            if int_or_none(item.get("feeder_id")) is None:
                continue
            selected = item
            selected_kind = str(item.get("kind") or "OTHER")
            break

    evidence = "; ".join(
        f"{item['kind']}:{item['name'] or item['identity'] or '-'}"
        f"=>FEEDER_ID={item['feeder_id'] or '-'}"
        f"[{item['source'] or 'DATABASE'}]"
        for item in normalized
    )
    if selected is None:
        return {
            "ready": False,
            "feeder": {},
            "feeder_id": "",
            "feeder_source": "UNRESOLVED",
            "feeder_evidence": evidence or "没有候选设备能够唯一提供有效 FEEDER_ID",
            "feeder_anchor": "",
            "reason": (
                "GRAPH_FEEDER_NOT_RESOLVED: 已按 环网柜 → 柱上开关 → 柱上变压器 "
                "顺序检查，但没有可用的唯一候选设备。"
            ),
            "candidates": normalized,
        }

    feeder_id = int_or_none(selected.get("feeder_id"))
    feeder = db.get_feeder_info(feeder_id) if db is not None else None
    if not feeder:
        return {
            "ready": False,
            "feeder": {},
            "feeder_id": feeder_id or "",
            "feeder_source": f"GRAPH_{selected_kind}",
            "feeder_evidence": evidence,
            "feeder_anchor": f"{selected_kind}:{selected.get('name') or selected.get('identity') or '-'}",
            "reason": f"GRAPH_FEEDER_NOT_FOUND: FEEDER_ID={feeder_id} 无法读取 13500 馈线。",
            "candidates": normalized,
        }
    return {
        "ready": True,
        "feeder": feeder,
        "feeder_id": feeder_id,
        "feeder_source": f"GRAPH_UNIQUE_{selected_kind}",
        "feeder_evidence": evidence,
        "feeder_anchor": f"{selected_kind}:{selected.get('name') or selected.get('identity') or '-'}",
        "reason": "",
        "candidates": normalized,
    }


def rmu_positions_from_settings(settings=None):
    """Return the hard-coded Jeddah RMU cabinet-name direction used everywhere."""
    del settings
    return ("top",)


def add_feeder_fields(row, resolution):
    """Add user-facing feeder source/evidence fields to a report row."""
    resolution = resolution or {}
    feeder = resolution.get("feeder") or {}
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
    row.update({
        "feeder_resolution_source": resolution.get("feeder_source", "UNRESOLVED"),
        "feeder_resolution_evidence": resolution.get("feeder_evidence", ""),
        "feeder_anchor": resolution.get("feeder_anchor", ""),
        "feeder_id": resolution.get("feeder_id", ""),
        "station_id": feeder.get("st_id", feeder.get("station_id", "")),
        "station_subarea_id": feeder.get("station_subarea_id", resolution.get("station_subarea_id", "")),
        "subcontrolarea_path": str(feeder.get("subcontrolarea_path") or resolution.get("subcontrolarea_path") or "").strip(),
        "station_name": str(feeder.get("station_name") or "").strip(),
        "feeder_db_name": feeder_db_name,
        "feeder_code": str(feeder.get("code") or "").strip(),
        "feeder_graph_name": str(feeder.get("graph_name") or "").strip(),
        "feeder_name": feeder_full_name,
        "feeder_path": feeder_full_name,
    })
    return row



def _feeder_resolution_result(*, ready, source, evidence, reason, candidates, db=None, feeder_id=None, anchor=""):
    """Build one normalized graph-feeder resolution result."""
    feeder = {}
    resolved_id = int_or_none(feeder_id)
    if ready and resolved_id is not None and db is not None:
        try:
            feeder = db.get_feeder_info(resolved_id) or {}
        except Exception:
            feeder = {}
        if not feeder:
            return {
                "ready": False,
                "feeder": {},
                "feeder_id": resolved_id,
                "feeder_source": source,
                "feeder_evidence": evidence,
                "feeder_anchor": anchor,
                "reason": f"GRAPH_FEEDER_NOT_FOUND: FEEDER_ID={resolved_id} 无法读取 13500 馈线。",
                "candidates": candidates,
            }
    return {
        "ready": bool(ready),
        "feeder": feeder,
        "feeder_id": resolved_id if resolved_id is not None else "",
        "feeder_source": source,
        "feeder_evidence": evidence,
        "feeder_anchor": anchor,
        "reason": reason,
        "candidates": candidates,
    }


def _station_control_area_context(db, station):
    """Resolve station.SUBAREA_ID -> subcontrolarea.ID for report enrichment.

    The control area is not inferred from the filename AREA token.  It comes
    only from the database relation exposed by the unique 405/substation row.
    Failure to enrich the path does not invalidate an otherwise unique
    station+feeder match; reports then fall back to "station feeder".
    """
    station = dict(station or {})
    subarea_id = int_or_none(station.get("subarea_id"))
    if subarea_id is None:
        return {
            "subarea_id": "",
            "path": "",
            "record": {},
            "status": "SUBAREA_ID_EMPTY",
        }
    if db is None or not hasattr(db, "get_subcontrolarea_info"):
        return {
            "subarea_id": subarea_id,
            "path": "",
            "record": {},
            "status": "SUBCONTROLAREA_API_UNAVAILABLE",
        }
    try:
        record = db.get_subcontrolarea_info(subarea_id, table_id=404) or {}
    except TypeError:
        # Compatibility with small test doubles / older adapters that expose
        # the same method without the optional table_id argument.
        try:
            record = db.get_subcontrolarea_info(subarea_id) or {}
        except Exception:
            record = {}
    except Exception:
        record = {}
    return {
        "subarea_id": subarea_id,
        "path": str(record.get("path") or "").strip(),
        "record": dict(record),
        "status": "OK" if record else "SUBCONTROLAREA_NOT_FOUND",
    }


def _jeddah_filename_parts(parsed):
    """Parse the authoritative Jeddah feeder filename.

    Supported business formats:
        JED-<AREA>-<STATION>-<NN>.sln.pic.g
        JED-<AREA>-<STATION>-AG<NN>.sln.pic.g

    Examples:
        JED-NTH-ABH-03.sln.pic.g   -> station=ABH, token=03,
                                      feeder_name=AH303
        JED-XXX-MDN-AG06.sln.pic.g -> station=MDN, token=AG06,
                                      feeder_name=AG406

    For the legacy two-digit form, ``AH3`` is added by the program.  For the
    new ``AGNN`` form, the program inserts ``4`` after ``AG`` so ``AG06``
    becomes database feeder NAME ``AG406``.  Timestamped
    ``.sln.pic(<...>).g`` snapshots are accepted because they keep the same
    logical business filename.
    """
    name = str(getattr(getattr(parsed, "path", None), "name", "") or "").strip()
    logical = re.sub(r"\.sln\.pic(?:\([^)]*\))?\.g$", "", name, flags=re.I)
    if logical == name:
        logical = re.sub(r"\.g$", "", name, flags=re.I)

    match = re.fullmatch(
        r"JED-([A-Z]{3})-([A-Z0-9]+)-((?:AG)?\d{2})",
        logical,
        flags=re.I,
    )
    if not match:
        return {
            "valid": False,
            "file_name": name,
            "logical_name": logical,
            "reason": (
                "JED_FILENAME_INVALID: 吉达馈线文件名必须以 JED-三位区域代码 开头，并符合 "
                "JED-<三位区域代码>-<站名>-<两位馈线号>.sln.pic.g 或 "
                "JED-<三位区域代码>-<站名>-AG<两位馈线号>.sln.pic.g，"
                f"当前文件名={name or '-'}；请先修改文件名后重新校验。"
            ),
        }

    area = str(match.group(1) or "").upper()
    station = str(match.group(2) or "").upper()
    feeder_token = str(match.group(3) or "").upper()
    if feeder_token.startswith("AG"):
        suffix = feeder_token[2:]
        feeder_name = f"AG4{suffix}"
        feeder_rule = "AG4"
    else:
        suffix = feeder_token
        feeder_name = f"AH3{suffix}"
        feeder_rule = "AH3"
    return {
        "valid": True,
        "file_name": name,
        "logical_name": logical,
        "area": area,
        "station_name": station,
        "feeder_token": feeder_token,
        "feeder_suffix": suffix,
        "feeder_rule": feeder_rule,
        "feeder_name": feeder_name,
    }


def _resolve_jeddah_filename_fallback(db, parsed, *, candidates=None):
    """Authoritative Jeddah feeder resolver: filename -> 405 -> 13500.

    The G filename is the only feeder-identification source. RMU, Pole Switch,
    Pole Transformer, root facID and manual feeder input are never used to
    infer the drawing feeder.

    Resolution chain:
      1. Parse ``JED-<AREA>-<STATION>-<NN>`` or
         ``JED-<AREA>-<STATION>-AG<NN>``.
      2. Exact 405/substation.NAME == <STATION>; exactly one row is required.
      3. Build feeder NAME by filename token:
         - ``NN`` -> ``AH3`` + ``NN`` (03 -> AH303)
         - ``AGNN`` -> ``AG4`` + ``NN`` (AG06 -> AG406)
      4. Exact 13500/dms_feeder_device.ST_ID == station.ID and NAME == the
         generated feeder name; exactly one row is required.
    """
    exposed = list(candidates or [])
    info = _jeddah_filename_parts(parsed)
    if not info.get("valid"):
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_INVALID",
            evidence=f"file={info.get('file_name') or '-'}",
            reason=info.get("reason") or "JED_FILENAME_INVALID",
            candidates=exposed,
            anchor="",
        ) | {"fallback_allowed": False}

    station_name = str(info.get("station_name") or "")
    feeder_name = str(info.get("feeder_name") or "")
    file_name = str(info.get("file_name") or "")

    if db is None or not hasattr(db, "find_substations_by_name"):
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_405_UNAVAILABLE",
            evidence=f"file={file_name}; station={station_name}; feeder={feeder_name}",
            reason=(
                "FILENAME_DB_API_MISSING: 数据库访问层缺少 405/substation "
                "精确 NAME 查询接口，无法按文件名判定馈线，禁止关联。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}",
        ) | {"fallback_allowed": False}

    try:
        stations = db.find_substations_by_name(station_name, table_id=405) or []
    except Exception as exc:
        stations = []
        station_error = str(exc)
    else:
        station_error = ""

    file_candidate = {
        "kind": "FILENAME",
        "identity": file_name,
        "name": feeder_name,
        "station_name": station_name,
        "db_match_count": 0,
        "db_id": None,
        "feeder_id": None,
        "source": "JED_FILENAME->405.NAME->13500(ST_ID+NAME)",
    }
    exposed.append(file_candidate)

    if len(stations) != 1:
        file_candidate["db_match_count"] = len(stations)
        detail = f"; error={station_error}" if station_error else ""
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_405_NOT_UNIQUE",
            evidence=(
                f"file={file_name}; 405.NAME={station_name}; "
                f"station_matches={len(stations)}{detail}"
            ),
            reason=(
                "FILENAME_STATION_NOT_EXACTLY_ONE: "
                f"405/substation.NAME={station_name} 匹配 {len(stations)} 条；"
                "必须恰好 1 条，禁止继续关联。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}->405.NAME={station_name}",
        ) | {"fallback_allowed": False}

    station = dict(stations[0])
    station_id = int_or_none(station.get("id"))
    if station_id is None:
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_405_ID_EMPTY",
            evidence=f"file={file_name}; 405.NAME={station_name}; station_id=-",
            reason=(
                "FILENAME_STATION_ID_EMPTY: "
                f"405/substation.NAME={station_name} 的唯一记录 ID 为空；禁止继续关联。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}->405.NAME={station_name}",
        ) | {"fallback_allowed": False}

    control_area = _station_control_area_context(db, station)
    control_area_path = str(control_area.get("path") or "").strip()
    station_subarea_id = control_area.get("subarea_id", "")
    file_candidate.update({
        "station_id": station_id,
        "station_subarea_id": station_subarea_id,
        "subcontrolarea_path": control_area_path,
    })

    if not hasattr(db, "find_feeders_by_station_and_name"):
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_13500_UNAVAILABLE",
            evidence=(
                f"file={file_name}; 405.NAME={station_name}; ST_ID={station_id}; "
                f"13500.NAME={feeder_name}"
            ),
            reason=(
                "FILENAME_DB_API_MISSING: 数据库访问层缺少 "
                "13500/dms_feeder_device 按 ST_ID + NAME 精确查询接口，禁止关联。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}->ST_ID={station_id}->NAME={feeder_name}",
        ) | {"fallback_allowed": False}

    try:
        feeders = db.find_feeders_by_station_and_name(
            station_id,
            feeder_name,
            table_id=13500,
        ) or []
    except Exception as exc:
        feeders = []
        feeder_error = str(exc)
    else:
        feeder_error = ""

    file_candidate["db_match_count"] = len(feeders)
    if len(feeders) == 0:
        detail = f"; error={feeder_error}" if feeder_error else ""
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_13500_NOT_FOUND",
            evidence=(
                f"file={file_name}; 405.NAME={station_name}; ST_ID={station_id}; "
                f"13500.NAME={feeder_name}; feeder_matches=0{detail}"
            ),
            reason=(
                "FILENAME_FEEDER_NOT_FOUND: "
                f"13500/dms_feeder_device 中未找到 ST_ID={station_id} 且 NAME={feeder_name} 的馈线。"
                "馈线不存在，请检查该图的馈线是否已创建。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}->ST_ID={station_id}->NAME={feeder_name}",
        ) | {"fallback_allowed": False}
    if len(feeders) > 1:
        detail = f"; error={feeder_error}" if feeder_error else ""
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_13500_NOT_UNIQUE",
            evidence=(
                f"file={file_name}; 405.NAME={station_name}; ST_ID={station_id}; "
                f"13500.NAME={feeder_name}; feeder_matches={len(feeders)}{detail}"
            ),
            reason=(
                "FILENAME_FEEDER_NOT_UNIQUE: "
                f"13500/dms_feeder_device 中 ST_ID={station_id} 且 NAME={feeder_name} "
                f"匹配 {len(feeders)} 条；数据库馈线不唯一，禁止关联。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}->ST_ID={station_id}->NAME={feeder_name}",
        ) | {"fallback_allowed": False}

    feeder = dict(feeders[0])
    feeder_id = int_or_none(feeder.get("id"))
    if feeder_id is None:
        return _feeder_resolution_result(
            ready=False,
            source="FILENAME_13500_ID_EMPTY",
            evidence=(
                f"file={file_name}; 405.NAME={station_name}; ST_ID={station_id}; "
                f"13500.NAME={feeder_name}; FEEDER_ID=-"
            ),
            reason=(
                "FILENAME_FEEDER_ID_EMPTY: "
                f"13500 中 ST_ID={station_id}、NAME={feeder_name} 的唯一记录 ID 为空；"
                "禁止关联。"
            ),
            candidates=exposed,
            anchor=f"FILE:{file_name}->ST_ID={station_id}->NAME={feeder_name}",
        ) | {"fallback_allowed": False}

    file_candidate.update({
        "db_id": feeder_id,
        "feeder_id": feeder_id,
        "selected_for_feeder": True,
    })
    evidence = (
        f"file={file_name}; filename_area={info.get('area')}; station_token={station_name}; "
        f"405.ID={station_id}; 405.SUBAREA_ID={station_subarea_id or '-'}; "
        f"subcontrolarea_path={control_area_path or '-'}; "
        f"filename_token={info.get('feeder_token')}; "
        f"filename_suffix={info.get('feeder_suffix')}; "
        f"program_prefix={info.get('feeder_rule')}; 13500.NAME={feeder_name}; "
        f"FEEDER_ID={feeder_id}"
    )
    result = _feeder_resolution_result(
        ready=True,
        source="FILENAME_405_13500",
        evidence=evidence,
        reason="",
        candidates=exposed,
        db=db,
        feeder_id=feeder_id,
        anchor=f"FILE:{file_name}->405:{station_name}({station_id})->13500:{feeder_name}",
    )

    # The unique 405 row is authoritative for station + SUBAREA_ID, and the
    # exact 13500 row is authoritative for the feeder.  Merge those facts into
    # the operator-facing feeder record instead of relying on a later generic
    # feeder lookup to reconstruct the hierarchy.
    resolved_feeder = dict(result.get("feeder") or {})
    resolved_feeder.update({
        "id": feeder_id,
        "st_id": station_id,
        "station_id": station_id,
        "station_name": str(station.get("name") or station_name).strip(),
        "station_subarea_id": station_subarea_id,
        "name": str(feeder.get("name") or feeder_name).strip(),
        "code": str(feeder.get("code") or resolved_feeder.get("code") or "").strip(),
        "graph_name": str(feeder.get("graph_name") or resolved_feeder.get("graph_name") or "").strip(),
    })
    if control_area_path:
        resolved_feeder["subcontrolarea_path"] = control_area_path
    else:
        resolved_feeder.setdefault(
            "subcontrolarea_path",
            str((result.get("feeder") or {}).get("subcontrolarea_path") or "").strip(),
        )

    full_name = " ".join(
        value for value in (
            str(resolved_feeder.get("subcontrolarea_path") or "").strip(),
            str(resolved_feeder.get("station_name") or "").strip(),
            str(resolved_feeder.get("name") or "").strip(),
        ) if value
    ).strip()
    if full_name:
        resolved_feeder["display_name"] = full_name

    result["feeder"] = resolved_feeder
    result["station"] = station
    result["subcontrolarea"] = dict(control_area.get("record") or {})
    result["station_subarea_id"] = station_subarea_id
    result["subcontrolarea_path"] = str(resolved_feeder.get("subcontrolarea_path") or "").strip()
    result["fallback_allowed"] = False
    return result


def _resolve_family_candidates(db, kind, candidates, *, all_candidates=None):
    """Resolve one device family by the first usable unique database match.

    Candidates are evaluated in their stable graphical order.  A candidate is
    usable only when its graphical name resolves to exactly one row in the
    corresponding database table and that row exposes a non-empty FEEDER_ID.
    The first usable candidate wins immediately; later devices in the same
    family are not required to agree with it.

    When every candidate in this family is non-unique / missing / unusable,
    the caller may continue to the next family (RMU -> Pole Switch -> Pole
    Transformer).  A unique candidate that points to a missing 13500 feeder is
    treated as a database-integrity error and does not fall through silently.
    """
    candidates = list(candidates or [])
    evidence = "; ".join(
        f"{kind}:{item.get('name') or '-'}"
        f"=>match={item.get('db_match_count', 0)}"
        f"=>FEEDER_ID={item.get('feeder_id') or '-'}"
        f"[{item.get('source') or '-'}]"
        for item in candidates
    )
    exposed_candidates = list(all_candidates if all_candidates is not None else candidates)

    for item in candidates:
        if item.get("db_match_count") != 1:
            continue
        feeder_id = int_or_none(item.get("feeder_id"))
        if feeder_id is None:
            continue
        item["selected_for_feeder"] = True
        anchor = f"{kind}:{item.get('name') or item.get('identity') or '-'}"
        result = _feeder_resolution_result(
            ready=True,
            source=f"GRAPH_UNIQUE_{kind}",
            evidence=evidence,
            reason="",
            candidates=exposed_candidates,
            db=db,
            feeder_id=feeder_id,
            anchor=anchor,
        )
        if result.get("ready"):
            result["fallback_allowed"] = False
            return result
        # The graphical/device row itself was unique, but its FEEDER_ID could
        # not be resolved in 13500.  Do not mask this data-integrity problem by
        # choosing another device family.
        result["fallback_allowed"] = False
        return result

    return _feeder_resolution_result(
        ready=False,
        source=f"GRAPH_{kind}_UNRESOLVED",
        evidence=evidence,
        reason=(
            f"GRAPH_{kind}_FEEDER_NOT_RESOLVED: 当前图内已检查的 {kind} "
            "均未能通过名称在对应数据库表中唯一匹配并提供有效 FEEDER_ID；"
            "继续检查下一优先级设备。"
        ),
        candidates=exposed_candidates,
        feeder_id=None,
        anchor="",
    ) | {"fallback_allowed": True}


def _graphical_rmu_candidates(db, parsed, settings=None):
    """Recognize RMUs and stop after the first unique usable 13501 record."""
    from dmm.domain.gfile.parser import GParser

    settings = settings or {}
    parser = GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
        overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
        excluded_rmu_name_strings=settings.get("rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS),
    )
    frames = parser.find_rmu_frames(parsed)
    positions = rmu_positions_from_settings(settings)
    try:
        assigned = parser.assign_rmu_label_candidates_globally(parsed, frames, positions)
    except Exception:
        assigned = {}

    candidates = []
    for frame in frames:
        frame_key = (frame.frame.xml_index, frame.frame.xml_id)
        labels = assigned.get(frame_key, []) or []
        name = str(labels[0].text if labels else "").strip()
        rows = []
        if name and db is not None and hasattr(db, "get_rmu_records"):
            try:
                rows = db.get_rmu_records(name) or []
            except Exception:
                rows = []
        record = rows[0] if len(rows) == 1 else {}
        feeder_id = int_or_none(record.get("feeder_id")) if record else None
        candidate = {
            "kind": "RMU",
            "identity": f"FRAME_{frame.frame.xml_id or frame.frame.xml_index}",
            "name": name,
            "db_match_count": len(rows),
            "db_id": int_or_none(record.get("id")) if record else None,
            "feeder_id": feeder_id,
            "name_direction": str(labels[0].direction if labels else ""),
            "name_distance": float(labels[0].gap if labels else 0.0) if labels else "",
            "source": "RMU_GRAPH_NAME->13501.NAME",
        }
        candidates.append(candidate)
        if len(rows) == 1 and feeder_id is not None:
            break
    return frames, candidates


def _graphical_pole_switch_candidates(db, parsed, settings=None):
    """Recognize marked pole switches and stop at the first unique 13501 row."""
    from dmm.application.modules.pole_switch import (
        PoleSwitchParser,
        normalize_pole_switch_db_lookup_name,
    )

    settings = settings or {}
    rows = PoleSwitchParser().discover(
        parsed,
        settings.get("element_catalog", {}) or {},
        settings,
    )
    candidates = []
    for item in rows:
        name = str(item.get("graphical_name") or "").strip()
        family = str(item.get("device_family") or "").strip().upper()
        query_name = normalize_pole_switch_db_lookup_name(name, family)
        records = []
        if query_name and db is not None and hasattr(db, "get_combined_device_records"):
            try:
                records = db.get_combined_device_records(query_name) or []
            except Exception:
                records = []
        record = records[0] if len(records) == 1 else {}
        feeder_id = int_or_none(record.get("feeder_id")) if record else None
        candidate = {
            "kind": "POLE_SWITCH",
            "identity": str(item.get("xml_id") or ""),
            "name": name,
            "query_name": query_name,
            "db_match_count": len(records),
            "db_id": int_or_none(record.get("id")) if record else None,
            "feeder_id": feeder_id,
            "name_direction": str(item.get("name_direction") or ""),
            "name_distance": item.get("name_distance", ""),
            "source": "POLE_SWITCH_GRAPH_NAME->13501.NAME/CODE",
        }
        candidates.append(candidate)
        if len(records) == 1 and feeder_id is not None:
            break
    return rows, candidates


def _graphical_transformer_candidates(db, parsed, settings=None):
    """Recognize marked pole transformers and stop at the first unique 13505 row."""
    from dmm.application.modules.transformer import (
        TRANSFORMER_TABLE_ID,
        TransformerParser,
        resolve_transformer_graphical_name,
    )

    settings = settings or {}
    rows, _context = TransformerParser().discover(
        parsed,
        settings.get("element_catalog", {}) or {},
        settings,
    )
    candidates = []
    used_transformer_name_text_ids = set()
    for item in rows:
        resolve_transformer_graphical_name(
            item,
            db,
            used_transformer_name_text_ids,
        )
        name = str(item.get("graphical_name") or "").strip()
        records = []
        if name and db is not None and hasattr(db, "get_transformer_devices_by_name"):
            try:
                records = db.get_transformer_devices_by_name(
                    name,
                    feeder_id=None,
                    table_id=TRANSFORMER_TABLE_ID,
                ) or []
            except Exception:
                records = []
        record = records[0] if len(records) == 1 else {}
        feeder_id = int_or_none(record.get("feeder_id")) if record else None
        candidate = {
            "kind": "TRANSFORMER",
            "identity": str(item.get("xml_id") or ""),
            "name": name,
            "db_match_count": len(records),
            "db_id": int_or_none(record.get("id")) if record else None,
            "feeder_id": feeder_id,
            "name_direction": str(item.get("name_direction") or ""),
            "name_distance": item.get("name_distance", ""),
            "source": "TRANSFORMER_GRAPH_NAME->13505.NAME",
        }
        candidates.append(candidate)
        if len(records) == 1 and feeder_id is not None:
            break
    return rows, candidates


def _candidate_log_outcome(item, result):
    """Return a short operator-facing result for one feeder candidate."""
    if item.get("selected_for_feeder"):
        return "采用：数据库唯一匹配"
    count = int(item.get("db_match_count") or 0)
    if count == 0:
        return "跳过：数据库无匹配记录"
    if count > 1:
        return f"跳过：数据库匹配 {count} 条，不唯一"
    if int_or_none(item.get("feeder_id")) is None:
        return "跳过：唯一记录 FEEDER_ID 为空"
    return "已检查"


def resolve_drawing_feeder(db, parsed, settings=None, log_callback=None):
    """Resolve the Jeddah drawing feeder from the G filename only.

    Authoritative rule:
      1. The filename must be either
         ``JED-<3-letter AREA>-<STATION>-<NN>.sln.pic.g`` or
         ``JED-<3-letter AREA>-<STATION>-AG<NN>.sln.pic.g``.
         An invalid name is a hard error and the operator must rename the file.
      2. ``<STATION>`` exact-matches 405/substation.NAME and must return one row.
      3. The program builds feeder NAME from the final token:
         ``NN`` -> ``AH3NN``; ``AGNN`` -> ``AG4NN``.
      4. 13500/dms_feeder_device must contain exactly one row where
         ST_ID == 405.ID and NAME == the generated feeder name.
      5. The resulting 13500.ID is the drawing FEEDER_ID. Every later device
         association must prove that its database target belongs to this feeder.

    RMU, Pole Switch, Pole Transformer, G-root facID, source CBreaker text and
    manual feeder input are diagnostics/current state only; they never select
    or override the drawing feeder.
    """
    del settings
    result = _resolve_jeddah_filename_fallback(db, parsed, candidates=[])
    result["candidates"] = list(result.get("candidates") or [])

    if log_callback:
        for item in result.get("candidates", []):
            log_callback(
                f"[馈线识别] 唯一来源=文件名；"
                f"文件={item.get('identity') or '-'}；"
                f"目标NAME={item.get('name') or '-'}；"
                f"数据库匹配={item.get('db_match_count', 0)}；"
                f"FEEDER_ID={item.get('feeder_id') or '-'}。"
            )
        if result.get("ready"):
            feeder = result.get("feeder") or {}
            log_callback(
                "[发现馈线] 文件名唯一确定："
                f"FEEDER_ID={result.get('feeder_id')}；"
                f"CODE={feeder.get('code') or '-'}；"
                f"NAME={feeder.get('name') or feeder.get('display_name') or '-'}；"
                f"站点={feeder.get('station_name') or '-'}；"
                f"路径={result.get('feeder_anchor') or '-'}。"
            )
            log_callback(
                "图级馈线识别通过：唯一来源=文件名 -> 405/substation -> 13500/dms_feeder_device；"
                f"FEEDER_ID={result.get('feeder_id')}。"
            )
        else:
            log_callback(
                "图级馈线识别失败："
                f"{result.get('reason') or 'FILENAME_FEEDER_NOT_RESOLVED'}"
            )
    return result

def enforce_device_feeder_membership(row, resolution, *, device_feeder_id, reason_prefix):
    """Require a non-RMU target device to belong to the resolved drawing feeder."""
    add_feeder_fields(row, resolution)
    row["feeder_membership_verified"] = "NO"
    if not resolution.get("ready"):
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "reason": resolution.get("reason") or f"{reason_prefix}_GRAPH_FEEDER_NOT_RESOLVED",
        })
        return row

    graph_feeder_id = int_or_none(resolution.get("feeder_id"))
    target_feeder_id = int_or_none(device_feeder_id)
    if target_feeder_id is None:
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "reason": (
                f"{reason_prefix}_FEEDER_ID_EMPTY: 目标设备数据库 FEEDER_ID 为空，"
                f"无法证明其属于图级馈线 {graph_feeder_id}."
            ),
        })
        return row
    if graph_feeder_id is None or target_feeder_id != graph_feeder_id:
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "reason": (
                f"{reason_prefix}_FEEDER_MISMATCH: 目标设备 FEEDER_ID={target_feeder_id}，"
                f"图级 FEEDER_ID={graph_feeder_id or '-'}；禁止关联。"
            ),
        })
        return row
    row["feeder_membership_verified"] = "YES"
    return row
