from __future__ import annotations

import html
import os
import re
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from dmm.config.constants import (
    RMU_LABEL_EDGE_TOLERANCE,
    RMU_LABEL_PATTERN,
    RMU_LABEL_SEARCH_MAX_DISTANCE,
)
from dmm.config.defaults import DEFAULT_RMU_NAME_EXCLUSIONS, DEFAULT_RMU_NAME_POSITIONS
from dmm.domain.gfile.master_station_frames import find_master_station_frames
from dmm.domain.gfile.parser import Box, GObject, GParser, ParsedG


# Canonical invisible Poke copied from the working GFileStudio RMU Poke
# implementation supplied by the user.  Dynamic geometry/ahref/metadata are
# overlaid below.  The object stays in the leading Poke band of the Layer so it
# does not cover the rendered label/device graphics.
_CANONICAL_POKE_ATTRS: dict[str, str] = {
    "LevelEnd": "16", "LevelStart": "0",
    **{f"PlaneState{i}": ("1" if i == 0 else "0") for i in range(50)},
    "Pos": "0", "RectStyle": "0", "ShadowType": "0", "Style": "",
    "af": "2147483647", "af2": "2147483647", "af3": "2147483647", "af4": "2147483647",
    "aliasType": "", "app": "", "clip": "false", "devref": "", "domain": "",
    "eventRegister": "", "fc": "0,255,0", "fcc": "#00ff00", "fm": "0",
    "isDisplay": "1", "lc": "0,0,255", "lcc": "#0000ff", "ls": "0", "lw": "1",
    "onMouseHoverEnterAction": "", "onMouseHoverLeaveAction": "",
    "onMouseLeftDoubleClickAciton": "", "onMouseLeftOneClickAction": "",
    "onMouseRightDoubleClickAction": "", "onMouseRightOneClickAction": "",
    "opacity": "1", "p_AssFlag": "128", "p_DyColorFlag": "0", "p_EngcodeString": "",
    "p_FatherObjId": "", "p_Hint": "", "p_ProcName": "", "p_RectStyle": "0",
    "p_SelfDefString": "", "p_ShowModeMask": "3", "p_SubPos": "0", "rain_bow": "0",
    "rotate": "0", "switchapp": "1", "switchappflag": "1",
    "tfr": "rotate(0) scale(1,1)", "trend_color": "0",
}

_FRAME_POKE_METADATA = {
    "gfs_frame_role", "gfs_frame_component", "gfs_frame_type"
}


@dataclass
class PokeRecord:
    file_name: str
    poke_type: str
    source_name: str
    source_text_id: str = ""
    station: str = ""
    feeder: str = ""
    rmu_name: str = ""
    smart: str = ""
    poke_id: str = ""
    target_ahref: str = ""
    action: str = "skipped"
    reason: str = ""


@dataclass
class PokeProcessResult:
    output_files: list[Path]
    records: list[PokeRecord]
    csv_path: Path
    html_path: Path
    added: int
    updated: int
    unchanged: int
    skipped: int


def _norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _local_name(tag: Any) -> str:
    value = str(tag or "")
    return value.rsplit("}", 1)[-1]


def _float(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name, default))
    except (TypeError, ValueError):
        return default


def _box(element: ET.Element) -> Box | None:
    width = _float(element, "w", _float(element, "width", 0.0))
    height = _float(element, "h", _float(element, "height", 0.0))
    if width <= 0 or height <= 0:
        return None
    return Box(_float(element, "x"), _float(element, "y"), width, height)


def _number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _intersects(a: Box, b: Box) -> bool:
    return not (
        a.right <= b.left
        or b.right <= a.left
        or a.bottom <= b.top
        or b.bottom <= a.top
    )


def _contains_center(container: Box, inner: Box) -> bool:
    return (
        container.left <= inner.cx <= container.right
        and container.top <= inner.cy <= container.bottom
    )


def _overlap_area(a: Box, b: Box) -> float:
    width = max(0.0, min(a.right, b.right) - max(a.left, b.left))
    height = max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
    return width * height


def _area(box: Box) -> float:
    return max(0.0, box.w) * max(0.0, box.h)


def _all_used_ids(root: ET.Element) -> set[str]:
    return {
        value
        for element in root.iter()
        if (value := str(element.get("id") or "").strip())
    }


def _allocate_poke_id(root: ET.Element, used_ids: set[str]) -> str:
    values = []
    for element in root.iter():
        if _local_name(element.tag).lower() != "poke":
            continue
        value = str(element.get("id") or "").strip()
        if value.isdigit() and len(value) == 8 and value.startswith("17"):
            values.append(int(value))
    candidate = max(values) + 1 if values else 17000001
    while str(candidate) in used_ids or candidate > 17999999:
        candidate += 1
        if candidate > 17999999:
            raise ValueError("<poke> ID 17xxxxxx 可用范围已耗尽。")
    result = str(candidate)
    used_ids.add(result)
    return result


def _layers(root: ET.Element) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag).lower() == "layer"]


def _find_element(root: ET.Element, tag: str, xml_id: str) -> ET.Element | None:
    wanted_tag = str(tag or "").lower()
    wanted_id = str(xml_id or "").strip()
    for element in root.iter():
        if _local_name(element.tag).lower() != wanted_tag:
            continue
        if wanted_id and str(element.get("id") or "").strip() != wanted_id:
            continue
        return element
    return None


def _find_layer_for_element(root: ET.Element, target: ET.Element) -> ET.Element | None:
    for layer in _layers(root):
        if target is layer:
            return layer
        for child in layer.iter():
            if child is target:
                return layer
    return None


def _new_poke(poke_id: str) -> ET.Element:
    poke = ET.Element("poke", dict(_CANONICAL_POKE_ATTRS))
    poke.set("id", poke_id)
    return poke


def _move_poke_to_background(layer: ET.Element, poke: ET.Element) -> bool:
    children = list(layer)
    if poke not in children:
        insert_at = 0
        while insert_at < len(children) and _local_name(children[insert_at].tag).lower() == "poke":
            insert_at += 1
        layer.insert(insert_at, poke)
        return True

    old_index = children.index(poke)
    leading_end = 0
    while leading_end < len(children) and _local_name(children[leading_end].tag).lower() == "poke":
        leading_end += 1
    if old_index < leading_end:
        return False
    layer.remove(poke)
    layer.insert(leading_end, poke)
    return True


def _repair_poke(poke: ET.Element) -> bool:
    changed = False
    for key in _FRAME_POKE_METADATA:
        if key in poke.attrib:
            poke.attrib.pop(key, None)
            changed = True
    # Keep existing metadata not owned by this module, but normalize runtime
    # properties to the proven RMU Poke baseline.
    for key, value in _CANONICAL_POKE_ATTRS.items():
        if poke.get(key) != value:
            poke.set(key, value)
            changed = True
    return changed


def _ensure_poke(
    poke: ET.Element,
    *,
    target: str,
    box: Box,
    metadata: dict[str, str],
) -> bool:
    changed = _repair_poke(poke)
    desired = {
        "ahref": str(target),
        "x": _number(box.x),
        "y": _number(box.y),
        "w": _number(box.w),
        "h": _number(box.h),
        **{key: str(value) for key, value in metadata.items()},
    }
    for key, value in desired.items():
        if poke.get(key) != value:
            poke.set(key, value)
            changed = True
    return changed


def _candidate_related_pokes(
    layer: ET.Element,
    *,
    target: str,
    box: Box,
    marker_key: str,
    source_text_id: str,
    forbidden_markers: tuple[str, ...] = (),
) -> list[ET.Element]:
    target_key = str(target or "").strip().casefold()
    text_id = str(source_text_id or "").strip()
    result: list[ET.Element] = []
    seen: set[int] = set()

    def add(poke: ET.Element):
        key = id(poke)
        if key not in seen:
            seen.add(key)
            result.append(poke)

    for element in list(layer):
        if _local_name(element.tag).lower() != "poke":
            continue
        if any(str(element.get(key) or "").strip() == "1" for key in forbidden_markers):
            continue
        if str(element.get(marker_key) or "").strip() == "1":
            # A Poke created by this module is always reusable for its own
            # label/role; exact Text metadata makes reruns deterministic.
            meta_text_id = str(
                element.get("dmm_source_text_id")
                or element.get("dmm_feeder_text_id")
                or element.get("dmm_rmu_text_id")
                or element.get("gfs_rmu_text_id")
                or ""
            ).strip()
            if text_id and meta_text_id == text_id:
                add(element)
                continue
        current_target = str(element.get("ahref") or "").strip().casefold()
        if target_key and current_target == target_key:
            add(element)
            continue
        poke_box = _box(element)
        if poke_box is not None and (
            _intersects(poke_box, box) or _contains_center(poke_box, box)
        ):
            add(element)
    return result


def _choose_primary_poke(
    candidates: list[ET.Element],
    *,
    target: str,
    box: Box,
) -> ET.Element:
    target_key = str(target or "").strip().casefold()

    def score(element: ET.Element):
        pbox = _box(element) or box
        exact = 0 if str(element.get("ahref") or "").strip().casefold() == target_key else 1
        overlap = -_overlap_area(pbox, box)
        size_delta = abs(_area(pbox) - _area(box))
        return exact, overlap + size_delta * 1e-6, str(element.get("id") or "")

    return sorted(candidates, key=score)[0]


def _upsert_label_poke(
    root: ET.Element,
    layer: ET.Element,
    *,
    target: str,
    box: Box,
    marker_key: str,
    source_text_id: str,
    metadata: dict[str, str],
    used_ids: set[str],
    forbidden_markers: tuple[str, ...] = (),
) -> tuple[str, str, int]:
    candidates = _candidate_related_pokes(
        layer,
        target=target,
        box=box,
        marker_key=marker_key,
        source_text_id=source_text_id,
        forbidden_markers=forbidden_markers,
    )
    removed = 0
    if candidates:
        poke = _choose_primary_poke(candidates, target=target, box=box)
        for extra in candidates:
            if extra is poke:
                continue
            layer.remove(extra)
            removed += 1
        changed = _ensure_poke(
            poke,
            target=target,
            box=box,
            metadata={
                marker_key: "1",
                "dmm_source_text_id": source_text_id,
                **metadata,
            },
        )
        moved = _move_poke_to_background(layer, poke)
        action = "updated" if changed or moved or removed else "unchanged"
        return str(poke.get("id") or ""), action, removed

    poke_id = _allocate_poke_id(root, used_ids)
    poke = _new_poke(poke_id)
    _ensure_poke(
        poke,
        target=target,
        box=box,
        metadata={
            marker_key: "1",
            "dmm_source_text_id": source_text_id,
            **metadata,
        },
    )
    _move_poke_to_background(layer, poke)
    return poke_id, "added", 0


def _exact_station(rows: Iterable[dict], station_hint: str) -> dict | None:
    exact = [dict(row) for row in (rows or []) if _norm(row.get("name")) == _norm(station_hint)]
    return exact[0] if len(exact) == 1 else None


def apply_main_feeder_pokes(
    parsed: ParsedG,
    db,
    *,
    file_name: str,
    log=None,
) -> list[PokeRecord]:
    """Create Poke regions on all Makkah main-network feeder title Texts.

    Target rule required by the site:
        graph label GVCM-AH304
        -> 405/SUBSTATION NAME=GVCM
        -> SUBSTATION.GRAPH_NAME
        -> <graph_name>?locateLabel=AH304&&scaleFlag=true
    """
    log = log or (lambda _msg: None)
    root = parsed.root
    used_ids = _all_used_ids(root)
    records: list[PokeRecord] = []

    for frame in find_master_station_frames(parsed):
        label_obj = frame.label_obj
        if label_obj is None or len(frame.breakers) != 1 or not frame.feeder_label:
            continue
        text_element = _find_element(root, "text", label_obj.xml_id)
        if text_element is None:
            records.append(PokeRecord(
                file_name=file_name,
                poke_type="MAIN_FEEDER",
                source_name=frame.feeder_label,
                source_text_id=label_obj.xml_id,
                station=frame.station_hint,
                feeder=frame.feeder_hint,
                reason="未能定位馈线标题 Text XML 对象。",
            ))
            continue
        text_box = _box(text_element)
        layer = _find_layer_for_element(root, text_element)
        if text_box is None or layer is None:
            records.append(PokeRecord(
                file_name=file_name,
                poke_type="MAIN_FEEDER",
                source_name=frame.feeder_label,
                source_text_id=label_obj.xml_id,
                station=frame.station_hint,
                feeder=frame.feeder_hint,
                reason="馈线标题 Text 几何或 Layer 无效。",
            ))
            continue

        try:
            rows = db.find_stations_by_name_hint(frame.station_hint, table_id=405)
        except TypeError:
            rows = db.find_stations_by_name_hint(frame.station_hint)
        station = _exact_station(rows, frame.station_hint)
        if station is None:
            records.append(PokeRecord(
                file_name=file_name,
                poke_type="MAIN_FEEDER",
                source_name=frame.feeder_label,
                source_text_id=label_obj.xml_id,
                station=frame.station_hint,
                feeder=frame.feeder_hint,
                reason="405/SUBSTATION 站名未唯一匹配。",
            ))
            continue

        graph_name = str(station.get("graph_name") or "").strip()
        if not graph_name:
            # Defensive fallback for older DB adapters that returned the row
            # without GRAPH_NAME.  It remains a SELECT-only lookup.
            get_station = getattr(db, "get_station_info", None)
            if callable(get_station):
                info = get_station(station.get("id")) or {}
                graph_name = str(info.get("graph_name") or "").strip()
        if not graph_name:
            records.append(PokeRecord(
                file_name=file_name,
                poke_type="MAIN_FEEDER",
                source_name=frame.feeder_label,
                source_text_id=label_obj.xml_id,
                station=frame.station_hint,
                feeder=frame.feeder_hint,
                reason="405/SUBSTATION.GRAPH_NAME 为空。",
            ))
            continue

        separator = "&" if "?" in graph_name else "?"
        target = f"{graph_name}{separator}locateLabel={frame.feeder_hint}&&scaleFlag=true"
        poke_id, action, removed = _upsert_label_poke(
            root,
            layer,
            target=target,
            box=text_box,
            marker_key="dmm_main_feeder_poke",
            source_text_id=label_obj.xml_id,
            metadata={
                "dmm_feeder_text_id": label_obj.xml_id,
                "dmm_feeder_label": frame.feeder_label,
                "dmm_station_name": frame.station_hint,
                "dmm_feeder_code": frame.feeder_hint,
            },
            used_ids=used_ids,
            forbidden_markers=(
                "gfs_rmu_poke", "gfs_device_poke", "gfs_station_poke",
                "dmm_smart_rmu_poke",
            ),
        )
        reason = "已新增馈线标题 Poke。" if action == "added" else (
            "已修复/更新馈线标题 Poke。" if action == "updated" else "现有馈线标题 Poke 已符合要求。"
        )
        if removed:
            reason += f" 同时清理重复 Poke {removed} 个。"
        records.append(PokeRecord(
            file_name=file_name,
            poke_type="MAIN_FEEDER",
            source_name=frame.feeder_label,
            source_text_id=label_obj.xml_id,
            station=frame.station_hint,
            feeder=frame.feeder_hint,
            poke_id=poke_id,
            target_ahref=target,
            action=action,
            reason=reason,
        ))
        log(f"[主网馈线Poke] {frame.feeder_label} -> {target} ({action})")

    return records


def _new_rmu_parser(settings: dict) -> GParser:
    return GParser(
        required_rmu_tags={"CBreakerDis", "ZhaiWaiJieDiDaoZha", "BusDis"},
        label_regex=RMU_LABEL_PATTERN,
        max_distance=RMU_LABEL_SEARCH_MAX_DISTANCE,
        overlap_tolerance=RMU_LABEL_EDGE_TOLERANCE,
        excluded_rmu_name_strings=settings.get(
            "rmu_name_exclusions", DEFAULT_RMU_NAME_EXCLUSIONS
        ),
        exclude_numeric_decimal_rmu_names=True,
        exclude_phone_like_rmu_names=True,
        exclude_hyphenated_rmu_names=True,
        prefer_pure_numeric_rmu_names=False,
    )


def apply_smart_rmu_pokes(
    output_path: Path,
    db,
    settings: dict,
    *,
    log=None,
) -> list[PokeRecord]:
    """Copy the proven GFileStudio RMU Poke behavior into DMM.

    DMM keeps its own RMU recognition as the authority.  Only RMUs assigned a
    SMART/SMR marker receive a Poke.  The target filename follows the exact
    GFileStudio database chain:
        DMS_COMBINED_DEVICE.NAME -> FEEDER_ID -> DMS_FEEDER_DEVICE
        -> SUBSTATION -> SUBCONTROLAREA
        -> <subcontrolarea>-<station>-<feeder>-<RMU>.com.pic.g
    """
    log = log or (lambda _msg: None)
    parser = _new_rmu_parser(settings)
    parsed = parser.parse(output_path)
    root = parsed.root
    frames = parser.find_rmu_frames(parsed)
    positions_cfg = settings.get("rmu_name_positions", DEFAULT_RMU_NAME_POSITIONS) or DEFAULT_RMU_NAME_POSITIONS
    positions = [name for name in ("top", "right", "left", "bottom") if positions_cfg.get(name)]
    assignments = parser.assign_rmu_label_candidates_globally(parsed, frames, positions or ["right"])
    smart_map = parser.assign_rmu_smart_markers_globally(parsed, frames)

    smart_names: list[str] = []
    frame_names: dict[tuple[int, str], tuple[str, GObject]] = {}
    for frame in frames:
        key = (frame.frame.xml_index, frame.frame.xml_id)
        candidates = assignments.get(key, [])
        if not candidates:
            continue
        candidate = candidates[0]
        name = str(candidate.text or "").strip()
        if not name:
            continue
        frame_names[key] = (name, candidate.obj)
        if bool((smart_map.get(frame.frame.xml_id) or {}).get("is_smart")):
            smart_names.append(name)

    contexts: dict[str, dict] = {}
    issues: dict[str, str] = {}
    resolver = getattr(db, "resolve_rmu_poke_contexts", None)
    if smart_names and callable(resolver):
        contexts, issues = resolver(smart_names)

    smart_name_counts = Counter(
        " ".join(name.split()).casefold() for name in smart_names if str(name).strip()
    )
    used_ids = _all_used_ids(root)
    records: list[PokeRecord] = []
    for frame in frames:
        key = (frame.frame.xml_index, frame.frame.xml_id)
        smart_info = smart_map.get(frame.frame.xml_id) or {}
        if not bool(smart_info.get("is_smart")):
            continue
        name_info = frame_names.get(key)
        if not name_info:
            records.append(PokeRecord(
                file_name=output_path.name,
                poke_type="SMART_RMU",
                source_name="",
                rmu_name="",
                smart="YES",
                reason=f"智能 RMU rect={frame.frame.xml_id or '-'} 未识别到唯一柜名。",
            ))
            continue
        rmu_name, name_obj = name_info
        lookup_key = " ".join(rmu_name.split()).casefold()
        # Match GFileStudio RMU-Poke safety behavior exactly: two intelligent
        # cabinets with the same visible RMU name would produce the same detail
        # ahref, so neither one is safe to bind automatically.
        if smart_name_counts.get(lookup_key, 0) > 1:
            records.append(PokeRecord(
                file_name=output_path.name,
                poke_type="SMART_RMU",
                source_name=rmu_name,
                source_text_id=name_obj.xml_id,
                rmu_name=rmu_name,
                smart="YES",
                reason=f"智能 RMU 柜名 {rmu_name!r} 在同一文件中重复，Poke 目标无法唯一。",
            ))
            continue
        context = contexts.get(lookup_key)
        issue = issues.get(lookup_key, "")
        if not context:
            records.append(PokeRecord(
                file_name=output_path.name,
                poke_type="SMART_RMU",
                source_name=rmu_name,
                source_text_id=name_obj.xml_id,
                rmu_name=rmu_name,
                smart="YES",
                reason=issue or "数据库未解析到智能 RMU 所属馈线。",
            ))
            continue

        prefix = str(context.get("feeder_full_name") or "").strip()
        if not prefix:
            records.append(PokeRecord(
                file_name=output_path.name,
                poke_type="SMART_RMU",
                source_name=rmu_name,
                source_text_id=name_obj.xml_id,
                rmu_name=rmu_name,
                smart="YES",
                reason="数据库馈线完整业务名为空。",
            ))
            continue
        target = f"{prefix}-{rmu_name}.com.pic.g"
        text_element = _find_element(root, "text", name_obj.xml_id)
        if text_element is None:
            records.append(PokeRecord(
                file_name=output_path.name,
                poke_type="SMART_RMU",
                source_name=rmu_name,
                source_text_id=name_obj.xml_id,
                rmu_name=rmu_name,
                smart="YES",
                target_ahref=target,
                reason="未能定位 RMU 名称 Text XML 对象。",
            ))
            continue
        text_box = _box(text_element)
        layer = _find_layer_for_element(root, text_element)
        if text_box is None or layer is None:
            records.append(PokeRecord(
                file_name=output_path.name,
                poke_type="SMART_RMU",
                source_name=rmu_name,
                source_text_id=name_obj.xml_id,
                rmu_name=rmu_name,
                smart="YES",
                target_ahref=target,
                reason="RMU 名称 Text 几何或 Layer 无效。",
            ))
            continue

        poke_id, action, removed = _upsert_label_poke(
            root,
            layer,
            target=target,
            box=text_box,
            marker_key="gfs_rmu_poke",
            source_text_id=name_obj.xml_id,
            metadata={
                "gfs_rmu_name": rmu_name,
                "gfs_rmu_text_id": name_obj.xml_id,
                "dmm_smart_rmu_poke": "1",
                "dmm_rmu_text_id": name_obj.xml_id,
                "dmm_rmu_name": rmu_name,
            },
            used_ids=used_ids,
            forbidden_markers=(
                "gfs_device_poke", "gfs_station_poke", "dmm_main_feeder_poke",
            ),
        )
        reason = "已新增智能 RMU Poke。" if action == "added" else (
            "已修复/更新智能 RMU Poke。" if action == "updated" else "现有智能 RMU Poke 已符合要求。"
        )
        if removed:
            reason += f" 同时清理重复 Poke {removed} 个。"
        records.append(PokeRecord(
            file_name=output_path.name,
            poke_type="SMART_RMU",
            source_name=rmu_name,
            source_text_id=name_obj.xml_id,
            rmu_name=rmu_name,
            smart="YES",
            poke_id=poke_id,
            target_ahref=target,
            action=action,
            reason=reason,
        ))
        log(f"[智能RMU Poke] {rmu_name} -> {target} ({action})")

    _write_tree_atomic(root, output_path)
    return records


def _write_tree_atomic(root: ET.Element, output_path: Path) -> None:
    output_path = Path(output_path)
    temp = output_path.with_name(output_path.name + ".tmp_poke")
    tree = ET.ElementTree(root)
    tree.write(temp, encoding="utf-8", xml_declaration=True)
    # Refuse to replace the safe copy unless the emitted XML is readable.
    ET.parse(temp)
    os.replace(temp, output_path)


def _write_csv(records: list[PokeRecord], path: Path) -> Path:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(PokeRecord.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    return path


def _write_html(records: list[PokeRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        ("file_name", "G文件"),
        ("poke_type", "Poke类型"),
        ("source_name", "图形名称"),
        ("station", "站名"),
        ("feeder", "馈线"),
        ("rmu_name", "RMU"),
        ("smart", "智能"),
        ("poke_id", "Poke ID"),
        ("target_ahref", "目标 ahref"),
        ("action", "处理结果"),
        ("reason", "说明"),
    ]
    rows = []
    for record in records:
        data = asdict(record)
        cells = "".join(f"<td>{html.escape(str(data.get(key, '') or ''))}</td>" for key, _label in fields)
        rows.append(f"<tr class='{html.escape(record.action)}'>{cells}</tr>")
    header = "".join(f"<th>{html.escape(label)}</th>" for _key, label in fields)
    content = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>Poke 跳转处理报告</title>
<style>
body{{font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;margin:24px;background:#f3f7f5;color:#17372e}}
h1{{color:#006b52}} table{{border-collapse:collapse;width:100%;background:white;font-size:12px}}
th,td{{border:1px solid #d3e3dc;padding:7px 9px;text-align:left;white-space:nowrap}}th{{background:#006b52;color:white}}.added{{background:#eaf8f2}}.updated{{background:#fff8de}}.skipped{{background:#fff0f0}}
</style></head><body><h1>Poke 跳转处理报告</h1><table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    path.write_text(content, encoding="utf-8")
    return path


def process_poke_files(
    db,
    files: Iterable[Path],
    settings: dict,
    output_dir: Path,
    report_dir: Path,
    *,
    enable_main_feeder: bool = True,
    enable_smart_rmu: bool = True,
    log=None,
    progress=None,
) -> PokeProcessResult:
    log = log or (lambda _msg: None)
    files = [Path(path) for path in files]
    if not files:
        raise ValueError("没有可处理的 G 文件。")
    if not (enable_main_feeder or enable_smart_rmu):
        raise ValueError("请至少启用一种 Poke 跳转处理。")

    output_dir = Path(output_dir)
    report_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    all_records: list[PokeRecord] = []
    output_files: list[Path] = []

    for index, source in enumerate(files, start=1):
        if progress:
            progress(int((index - 1) / max(1, len(files)) * 90), f"正在处理 {source.name}")
        target = output_dir / source.name
        shutil.copy2(source, target)
        log(f"[安全副本] {source} -> {target}")

        parser = GParser()
        parsed = parser.parse(target)
        file_records: list[PokeRecord] = []
        if enable_main_feeder:
            file_records.extend(
                apply_main_feeder_pokes(parsed, db, file_name=target.name, log=log)
            )
            # Persist feeder Pokes before re-parsing for RMU processing.  This
            # also keeps the RMU parser independent from newly inserted Pokes.
            _write_tree_atomic(parsed.root, target)

        if enable_smart_rmu:
            file_records.extend(
                apply_smart_rmu_pokes(target, db, settings, log=log)
            )
            # Smart-RMU processing persists the same safe output copy after
            # applying its Pokes.  The original input is never modified.

        output_files.append(target)
        all_records.extend(file_records)

    csv_path = _write_csv(all_records, report_dir / "poke_report.csv")
    html_path = _write_html(all_records, report_dir / "poke_report.html")
    if progress:
        progress(100, "Poke 跳转处理完成")
    counts = {name: sum(1 for row in all_records if row.action == name) for name in ("added", "updated", "unchanged", "skipped")}
    return PokeProcessResult(
        output_files=output_files,
        records=all_records,
        csv_path=csv_path,
        html_path=html_path,
        added=counts["added"],
        updated=counts["updated"],
        unchanged=counts["unchanged"],
        skipped=counts["skipped"],
    )
