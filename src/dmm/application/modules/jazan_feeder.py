"""Shared Jazan drawing-level feeder evidence.

Jazan exports may repeat a device NAME on different feeders.  Before any
module resolves a duplicate name, this helper looks for a graphical device
whose name is unique in the drawing and whose database name lookup returns
exactly one row.  Its FEEDER_ID is drawing-level evidence for all modules.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from dmm.domain.gfile.parser import GParser
from dmm.domain.rmu.validator import int_or_none, is_no_rmu_name, norm
from dmm.config.defaults import (
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_DETECTION_MODE,
    resolve_rmu_name_positions,
)


def _normal_name(value: str) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _is_placeholder_name(value: str) -> bool:
    return is_no_rmu_name(value)


def collect_non_rmu_feeder_candidates(
    db,
    g_file,
    settings=None,
    log_callback=None,
):
    """Collect unique feeder evidence from pole switches and transformers.

    RMU evidence is intentionally collected by ``RmuValidator`` itself.  By
    keeping the non-RMU scan here, the RMU validator can safely consume this
    helper without creating a module import cycle.
    """
    settings = dict(settings or {})
    parsed = GParser().parse(g_file)
    catalog = settings.get("element_catalog", {})

    # Imports are local because pole_switch/transformer both depend on the
    # common domain validators used above.
    from dmm.application.modules.pole_switch import PoleSwitchParser
    from dmm.application.modules.transformer import TransformerParser

    pole_rows = PoleSwitchParser().discover(parsed, catalog, settings)
    transformer_rows, _context = TransformerParser().discover(
        parsed,
        catalog,
        settings,
    )
    candidates = []
    for device_type, rows in (
        ("POLE_SWITCH", pole_rows),
        ("TRANSFORMER", transformer_rows),
    ):
        for row in rows:
            name = str(row.get("graphical_name") or "").strip()
            if not name or _is_placeholder_name(name):
                continue
            candidates.append({
                "device_type": device_type,
                "xml_id": str(row.get("xml_id") or ""),
                "name": name,
                "normalized_name": _normal_name(name),
            })

    name_counts = Counter(item["normalized_name"] for item in candidates)
    evidence = []
    for item in candidates:
        if name_counts[item["normalized_name"]] != 1:
            continue
        try:
            if item["device_type"] == "POLE_SWITCH":
                records = db.get_combined_device_records(item["name"])
            else:
                records = db.get_transformer_devices_by_name(
                    item["name"],
                    table_id=13505,
                )
        except Exception as exc:
            if log_callback:
                log_callback(
                    f"[{Path(g_file).name}] 查询{item['device_type']}"
                    f"名称={item['name']}失败：{exc}"
                )
            continue
        if len(records or []) != 1:
            continue
        record = records[0]
        feeder_id = int_or_none(record.get("feeder_id"))
        if feeder_id is None:
            continue
        evidence.append({
            "device_type": item["device_type"],
            "xml_id": item["xml_id"],
            "device_name": item["name"],
            "device_id": record.get("id", ""),
            "feeder_id": feeder_id,
            "database_name": norm(record.get("name")),
        })

    feeder_ids = sorted({item["feeder_id"] for item in evidence})
    if log_callback and evidence:
        log_callback(
            f"[{Path(g_file).name}] 非环网柜唯一设备馈线证据："
            + "; ".join(
                f"{item['device_type']}={item['device_name']}"
                f" -> FEEDER_ID={item['feeder_id']}"
                for item in evidence
            )
        )
    return {
        "feeder_ids": feeder_ids,
        "evidence": evidence,
    }


def resolve_drawing_feeder_context(db, g_file, settings=None, log_callback=None):
    """Resolve the shared Jazan feeder context for one G file."""
    settings = dict(settings or {})
    result = {
        "feeder": None,
        "feeder_source": "NO_UNIQUE_DEVICE_FEEDER",
        "diagram_feeder_id": "",
        "diagram_feeder_resolution": "NO_UNIQUE_DEVICE_FEEDER",
        "diagram_feeder_source": {},
    }
    positions = resolve_rmu_name_positions(
        settings.get(
            "rmu_name_detection_mode",
            DEFAULT_RMU_NAME_DETECTION_MODE,
        ),
        settings.get("rmu_name_positions", DEFAULT_NAME_POSITIONS),
    )
    if not positions:
        return result

    try:
        external = collect_non_rmu_feeder_candidates(
            db,
            g_file,
            settings,
            log_callback,
        )
        external_ids = external.get("feeder_ids", [])
        evidence = external.get("evidence", [])
        external_source = dict(evidence[0]) if evidence else {}

        from dmm.application.modules.rmu import RmuModelModule

        validator = RmuModelModule()._new_validator(
            db,
            settings,
            log_callback or (lambda _message: None),
        )
        rmu_report = validator.validate_file(
            g_file,
            positions,
            external_feeder_ids=external_ids,
            external_feeder_source=external_source,
        )
    except Exception as exc:
        if log_callback:
            log_callback(
                f"[{Path(g_file).name}] 积攒现场馈线推断失败：{exc}"
            )
        result["diagram_feeder_resolution"] = "FEEDER_INFERENCE_ERROR"
        result["diagram_feeder_source"] = {"error": str(exc)}
        return result

    feeder_id = int_or_none(rmu_report.get("diagram_feeder_id"))
    source = dict(rmu_report.get("diagram_feeder_source") or {})
    result.update({
        "diagram_feeder_id": feeder_id or "",
        "diagram_feeder_resolution": str(
            rmu_report.get("diagram_feeder_resolution")
            or "NO_UNIQUE_DEVICE_FEEDER"
        ),
        "diagram_feeder_source": source,
    })
    if feeder_id is None:
        return result

    feeder_name = ""
    get_feeder_info = getattr(db, "get_feeder_info", None)
    if callable(get_feeder_info):
        try:
            feeder_info = get_feeder_info(feeder_id) or {}
            feeder_name = str(
                feeder_info.get("display_name")
                or feeder_info.get("name")
                or ""
            ).strip()
        except Exception:
            feeder_name = ""
    if feeder_name:
        source["feeder_name"] = feeder_name
        result["diagram_feeder_source"] = source
    result["feeder"] = {"id": feeder_id, "display_name": feeder_name}
    result["diagram_feeder_name"] = feeder_name
    result["feeder_source"] = "UNIQUE_DEVICE_IN_SAME_G_FILE"
    return result
