from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from dmm.domain.gfile.master_station_frames import find_master_station_frames
from dmm.domain.gfile.parser import GParser


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def compare_makkah_ring_feeders(
    db,
    g_file,
    *,
    feeder_table_id: int = 13500,
    station_table_id: int = 405,
) -> List[Dict[str, Any]]:
    """List every feeder label shown by the Makkah ring drawing and its DB result.

    This function is intentionally report-oriented: each visible feeder label is
    retained even when the matching 405/13500 database record is missing or not
    unique.  The returned rows contain only result data needed by HTML/CSV
    reports; association decisions remain inside the model modules.
    """
    path = Path(g_file)
    parsed = GParser().parse(path)
    frames = find_master_station_frames(parsed)
    rows: List[Dict[str, Any]] = []
    seen = set()

    for frame_order, frame in enumerate(frames, start=1):
        label = str(frame.feeder_label or "").strip()
        if len(frame.breakers) != 1 or not label:
            continue

        station_hint = str(frame.station_hint or "").strip()
        feeder_hint = str(frame.feeder_hint or "").strip()
        if not station_hint or not feeder_hint:
            continue

        dedupe_key = _norm(label)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        item: Dict[str, Any] = {
            "file_name": path.name,
            "graph_feeder": label,
            "graph_station": station_hint,
            "graph_feeder_code": feeder_hint,
            "db_station_id": "",
            "db_station_name": "",
            "db_feeder_id": "",
            "db_code": "",
            "db_name": "",
            "db_st_id": "",
            "match_result": "NOT_FOUND",
            "_frame_order": frame_order,
        }

        try:
            station_rows = db.find_stations_by_name_hint(
                station_hint,
                table_id=int(station_table_id),
            )
        except TypeError:
            station_rows = db.find_stations_by_name_hint(station_hint)
        except Exception:
            item["match_result"] = "DB_ERROR"
            rows.append(item)
            continue

        exact_stations = [
            row for row in (station_rows or [])
            if _norm(row.get("name")) == _norm(station_hint)
        ]
        if len(exact_stations) == 0:
            item["match_result"] = "STATION_NOT_FOUND"
            rows.append(item)
            continue
        if len(exact_stations) > 1:
            item["match_result"] = "STATION_MULTIPLE"
            rows.append(item)
            continue

        station = dict(exact_stations[0])
        station_id = station.get("id")
        item["db_station_id"] = station_id if station_id not in (None, "") else ""
        item["db_station_name"] = station.get("name", "")
        if station_id in (None, ""):
            item["match_result"] = "STATION_NOT_FOUND"
            rows.append(item)
            continue

        try:
            feeder_rows = db.get_feeders_by_station(
                station_id,
                table_id=int(feeder_table_id),
            )
        except TypeError:
            feeder_rows = db.get_feeders_by_station(station_id)
        except Exception:
            item["match_result"] = "DB_ERROR"
            rows.append(item)
            continue

        feeder_key = _norm(feeder_hint)
        exact_feeders = [
            dict(row)
            for row in (feeder_rows or [])
            if feeder_key in {_norm(row.get("name")), _norm(row.get("code"))}
        ]
        unique_by_id = {
            str(row.get("id")): row
            for row in exact_feeders
            if row.get("id") not in (None, "")
        }
        if len(unique_by_id) == 0:
            item["match_result"] = "FEEDER_NOT_FOUND"
            rows.append(item)
            continue
        if len(unique_by_id) > 1:
            item["match_result"] = "FEEDER_MULTIPLE"
            rows.append(item)
            continue

        feeder = dict(next(iter(unique_by_id.values())))
        item.update({
            "db_feeder_id": feeder.get("id", ""),
            "db_code": feeder.get("code", ""),
            "db_name": feeder.get("name", ""),
            "db_st_id": feeder.get("st_id", station_id),
            "match_result": "MATCH",
        })
        rows.append(item)

    return rows


def compare_makkah_ring_feeders_for_files(
    db,
    files,
    settings,
    log_callback=None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return report-ready graph-feeder/database comparison rows for all files."""
    feeder_table_id = int(settings.get("feeder_table_id", 13500))
    out: Dict[str, List[Dict[str, Any]]] = {}
    for g_file in files:
        path = Path(g_file)
        rows = compare_makkah_ring_feeders(
            db,
            path,
            feeder_table_id=feeder_table_id,
            station_table_id=405,
        )
        out[str(path)] = rows
        if log_callback:
            if rows:
                for row in rows:
                    suffix = (
                        f"；FEEDER_ID={row.get('db_feeder_id')}"
                        if row.get("db_feeder_id") not in (None, "")
                        else ""
                    )
                    log_callback(
                        f"[图形馈线] {path.name}：{row.get('graph_feeder')} -> "
                        f"{row.get('match_result')}{suffix}"
                    )
            else:
                log_callback(f"[图形馈线] {path.name}：未发现馈线。")
    return out


def attach_makkah_ring_feeder_inventory(
    reports,
    inventory_by_file: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Attach per-file feeder comparison rows to arbitrary model reports."""
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for source_path, rows in (inventory_by_file or {}).items():
        by_name[Path(source_path).name] = [dict(row) for row in (rows or [])]

    for report in reports or []:
        file_name = Path(str(report.get("file_name", "") or "")).name
        report["graph_feeder_inventory"] = [
            dict(row) for row in by_name.get(file_name, [])
        ]


def discover_makkah_ring_feeders(
    db,
    g_file,
    *,
    feeder_table_id: int = 13500,
    station_table_id: int = 405,
    log_callback=None,
) -> List[Dict[str, Any]]:
    """Return every database-confirmed feeder exposed by main-network Bay frames.

    Makkah business rule:
      1. identify the innermost Rect frames containing CBreaker;
      2. keep the existing frame-title rule (nearest valid no-background Text; color ignored,
         rectangle edge distance <= 200, one Text used by at most one frame);
      3. parse a title such as ``GVCM-AH304`` into station ``GVCM`` and
         feeder token ``AH304``;
      4. resolve exactly one 405/substation row whose NAME equals GVCM;
      5. query 13500/dms_feeder_device with ``ST_ID = substation.ID`` and
         resolve exactly one feeder whose NAME or CODE equals AH304.

    Only this two-stage Station -> ST_ID -> feeder lookup is authoritative for
    the ring-feeder list.  File names, root facID and free-standing Text are not
    used to manufacture additional feeders.
    """
    parsed = GParser().parse(g_file)
    frames = find_master_station_frames(parsed)
    confirmed: List[Dict[str, Any]] = []
    seen_feeder_ids = set()
    rejected = []

    for frame_order, frame in enumerate(frames, start=1):
        label = str(frame.feeder_label or "").strip()
        if len(frame.breakers) != 1 or not label:
            continue

        station_hint = str(frame.station_hint or "").strip()
        feeder_hint = str(frame.feeder_hint or "").strip()
        if not station_hint or not feeder_hint:
            continue

        try:
            station_rows = db.find_stations_by_name_hint(
                station_hint,
                table_id=int(station_table_id),
            )
        except TypeError:
            # Test doubles / legacy adapters may omit the optional table_id.
            station_rows = db.find_stations_by_name_hint(station_hint)
        except Exception as exc:
            rejected.append((label, f"SUBSTATION_QUERY_FAILED:{exc}"))
            continue

        exact_stations = [
            row for row in (station_rows or [])
            if _norm(row.get("name")) == _norm(station_hint)
        ]
        if len(exact_stations) != 1:
            rejected.append((label, f"SUBSTATION_NOT_UNIQUE:{len(exact_stations)}"))
            continue

        station = dict(exact_stations[0])
        station_id = station.get("id")
        if station_id in (None, ""):
            rejected.append((label, "SUBSTATION_ID_EMPTY"))
            continue

        try:
            feeder_rows = db.get_feeders_by_station(
                station_id,
                table_id=int(feeder_table_id),
            )
        except TypeError:
            feeder_rows = db.get_feeders_by_station(station_id)
        except Exception as exc:
            rejected.append((label, f"FEEDER_QUERY_FAILED:{exc}"))
            continue

        feeder_key = _norm(feeder_hint)
        exact_feeders = []
        for row in feeder_rows or []:
            if feeder_key in {_norm(row.get("name")), _norm(row.get("code"))}:
                exact_feeders.append(dict(row))

        unique_by_id = {}
        for row in exact_feeders:
            rid = row.get("id")
            if rid in (None, ""):
                continue
            unique_by_id[str(rid)] = row
        if len(unique_by_id) != 1:
            rejected.append((label, f"FEEDER_NOT_UNIQUE:{len(unique_by_id)}"))
            continue

        feeder = dict(next(iter(unique_by_id.values())))
        feeder_id = feeder.get("id")
        if str(feeder_id) in seen_feeder_ids:
            continue
        seen_feeder_ids.add(str(feeder_id))

        feeder.update({
            "station_name": station.get("name", station_hint),
            "station_code": station.get("code", ""),
            "st_id": station_id,
            "display_name": label,
            "_ring_label": label,
            "_ring_station_hint": station_hint,
            "_ring_feeder_hint": feeder_hint,
            "_ring_frame_order": frame_order,
            "_ring_frame_xml_id": frame.frame.xml_id,
            "_ring_frame_xml_index": frame.frame.xml_index,
            "_ring_label_xml_id": frame.label_obj.xml_id if frame.label_obj else "",
            "_ring_label_xml_index": frame.label_obj.xml_index if frame.label_obj else None,
            "_ring_label_distance": frame.label_distance,
        })
        confirmed.append(feeder)

    confirmed.sort(key=lambda row: (
        int(row.get("_ring_frame_order", 0) or 0),
        int(row.get("_ring_frame_xml_index", 0) or 0),
    ))

    if log_callback:
        file_name = Path(g_file).name
        log_callback(
            f"[环网图馈线扫描] {file_name}：主网候选框={len(frames)}；"
            f"数据库确认馈线={len(confirmed)}"
        )
        for index, feeder in enumerate(confirmed, start=1):
            distance = feeder.get("_ring_label_distance")
            distance_text = "-" if distance in (None, "") else f"{float(distance):.1f}"
            log_callback(
                f"[环网图馈线] #{index} 标题={feeder.get('_ring_label')}；"
                f"变电站={feeder.get('station_name')}；ST_ID={feeder.get('st_id')}；"
                f"馈线={feeder.get('_ring_feeder_hint')}；FEEDER_ID={feeder.get('id')}；"
                f"标题距离={distance_text}"
            )
        if not confirmed:
            log_callback(f"[环网图馈线] {file_name}：未确认到任何有效馈线。")
        for label, reason in rejected:
            log_callback(
                f"[环网图馈线未确认] 标题={label}；原因={reason}"
            )

    return confirmed


def log_makkah_ring_feeders_for_files(
    db,
    files,
    settings,
    log_callback,
) -> Dict[str, List[Dict[str, Any]]]:
    """Log the full ring-feeder list once before *any* model runs."""
    feeder_table_id = int(settings.get("feeder_table_id", 13500))
    out: Dict[str, List[Dict[str, Any]]] = {}
    for g_file in files:
        path = Path(g_file)
        rows = discover_makkah_ring_feeders(
            db,
            path,
            feeder_table_id=feeder_table_id,
            station_table_id=405,
            log_callback=log_callback,
        )
        out[str(path)] = rows
    return out
