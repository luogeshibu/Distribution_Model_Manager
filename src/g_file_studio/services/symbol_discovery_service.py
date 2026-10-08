from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Callable

from g_file_studio.engines.id_engine import direct_layer_elements, local_name
from g_file_studio.models import InputMode
from g_file_studio.processors.common import discover_g_inputs
from g_file_studio.services.symbol_inventory_service import infer_device_type, infer_symbol_usage


def _number(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _devref_file(devref: str) -> str:
    value = str(devref or "").strip().lstrip("#")
    return value.split(":", 1)[0].strip() if value else ""


def _devref_subject(devref: str) -> str:
    value = str(devref or "").strip().lstrip("#")
    return value.split(":", 1)[1].strip() if ":" in value else ""


def infer_scope_from_graphic_symbol(devref: str) -> str:
    """Conservative SMART/NORMAL suggestion from an observed devref.

    This is discovery metadata only; it never becomes authoritative until the user
    uploads a real symbol-definition G and saves the row into the standard profile.
    """
    seed = re.sub(r"[^A-Z0-9]+", "_", str(devref or "").upper()).strip("_")
    if re.search(r"(?:^|_)(?:NON|NO)_?SMART(?:_|$)", seed) or re.search(r"(?:^|_)NORMAL(?:_|$)", seed):
        return "NORMAL"
    if re.search(r"(?:^|_)SMART(?:_|$)", seed):
        return "SMART"
    return "ANY"


def _sample_name(element: ET.Element) -> str:
    for attr in ("key_name", "p_NameString", "name", "NameString"):
        value = str(element.get(attr) or "").strip()
        if value:
            return value
    return ""


def _candidate_usage(*, device_type: str, source_file: str, element_tag: str, sample_names: list[str]) -> str:
    usage = infer_symbol_usage(role=device_type, source_file=source_file, element_tag=element_tag)
    # Strong RMU-internal evidence. These are only discovery suggestions; the
    # user's saved classification remains authoritative after the real icon G is
    # uploaded.
    seed = re.sub(r"[^A-Z0-9]+", "_", f"{source_file} {device_type}".upper()).strip("_")
    if element_tag == "ZhaiWaiJieDiDaoZha":
        return "设备组成图元"
    if element_tag == "CBreakerDis" and "RMU_LBS" in seed:
        return "设备组成图元"
    compact = [str(value).strip().upper() for value in sample_names if str(value).strip()]
    if element_tag == "CBreakerDis" and device_type in {"LBS", "Circuit Breaker"}:
        if any(re.fullmatch(r"[YQ]\s*\d+", value) for value in compact):
            return "设备组成图元"
    return usage


def discover_graphic_symbols(
    source_path: Path,
    input_mode: InputMode,
    *,
    log: Callable[[str], None] = print,
    progress: Callable[[int], None] | None = None,
) -> dict[str, object]:
    """Discover referenced icon instances from business/graphic G files.

    The result is *not* a standard. It only groups observed ``devref`` values and
    supplies classification suggestions so the user can selectively upload the real
    authoritative icon G afterwards. Geometry from the business drawing is kept only
    as observation evidence and must never be used as the standard w/h/AlignCenter/Pins.
    """
    files = discover_g_inputs(Path(source_path), input_mode)
    if progress:
        progress(0)

    buckets: dict[tuple[str, str], dict[str, object]] = {}
    parse_warnings: list[str] = []
    total = max(1, len(files))

    for file_index, file_path in enumerate(files, 1):
        try:
            tree = ET.parse(file_path)
        except Exception as exc:
            parse_warnings.append(f"{file_path.name}: XML 解析失败：{exc}")
            if progress:
                progress(round(file_index * 100 / total))
            continue

        elements = direct_layer_elements(tree.getroot())
        file_hits = 0
        for element in elements:
            devref = str(element.get("devref") or "").strip()
            if not devref:
                continue
            tag = local_name(element.tag)
            key = (tag, devref)
            row = buckets.setdefault(key, {
                "candidate_key": f"{tag}|{devref}",
                "element_tag": tag,
                "observed_devref": devref,
                "observed_symbol_file": _devref_file(devref),
                "observed_subject": _devref_subject(devref),
                "count": 0,
                "files": set(),
                "sample_names": [],
                "sample_positions": [],
                "compose_types": Counter(),
                "observed_sizes": Counter(),
            })
            row["count"] = int(row["count"]) + 1
            row["files"].add(file_path.name)
            file_hits += 1

            sample_name = _sample_name(element)
            if sample_name and sample_name not in row["sample_names"] and len(row["sample_names"]) < 8:
                row["sample_names"].append(sample_name)
            if len(row["sample_positions"]) < 5:
                x = _number(element.get("x"))
                y = _number(element.get("y"))
                element_id = str(element.get("id") or "").strip()
                row["sample_positions"].append({
                    "file": file_path.name,
                    "element_id": element_id,
                    "x": x,
                    "y": y,
                })
            compose_type = str(element.get("composeType") or "").strip()
            if compose_type:
                row["compose_types"][compose_type] += 1
            width = _number(element.get("w"))
            height = _number(element.get("h"))
            if width > 0 and height > 0:
                row["observed_sizes"][(round(width, 6), round(height, 6))] += 1

        log(f"[图形 G 图元发现] {file_index}/{len(files)} {file_path.name}：发现引用实例 {file_hits} 个。")
        if progress:
            progress(round(file_index * 100 / total))

    candidates: list[dict[str, object]] = []
    for (_tag, _devref), raw in buckets.items():
        source_file = str(raw["observed_symbol_file"] or "")
        subject = str(raw["observed_subject"] or "")
        element_tag = str(raw["element_tag"] or "")
        device_type = infer_device_type(
            role=subject,
            source_file=source_file,
            element_tag=element_tag,
            element_id=subject,
        )
        usage = _candidate_usage(
            device_type=device_type,
            source_file=source_file,
            element_tag=element_tag,
            sample_names=list(raw["sample_names"]),
        )
        files_sorted = sorted(str(item) for item in raw["files"])
        size_counter: Counter = raw["observed_sizes"]
        observed_sizes = [
            {"w": width, "h": height, "count": count}
            for (width, height), count in sorted(size_counter.items(), key=lambda item: (-item[1], item[0]))[:8]
        ]
        compose_counter: Counter = raw["compose_types"]
        candidates.append({
            "candidate_key": str(raw["candidate_key"]),
            "element_tag": element_tag,
            "observed_devref": str(raw["observed_devref"]),
            "observed_symbol_file": source_file,
            "observed_subject": subject,
            "count": int(raw["count"]),
            "files": files_sorted,
            "sample_names": list(raw["sample_names"]),
            "sample_positions": list(raw["sample_positions"]),
            "compose_types": dict(compose_counter),
            "observed_sizes": observed_sizes,
            "suggested_scope": infer_scope_from_graphic_symbol(str(raw["observed_devref"])),
            "suggested_usage": usage,
            "suggested_device_type": device_type,
        })

    candidates.sort(key=lambda row: (-int(row.get("count", 0)), str(row.get("observed_devref", "")).casefold()))
    if progress:
        progress(100)
    return {
        "files": [str(path) for path in files],
        "file_count": len(files),
        "candidate_count": len(candidates),
        "instance_count": sum(int(row.get("count", 0)) for row in candidates),
        "candidates": candidates,
        "warnings": parse_warnings,
    }
