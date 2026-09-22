"""Common Jeddah association scope rules.

Jeddah associations are valid only for a single-line drawing containing one
set of main-network devices.  Keep this check in one place so every model
module applies the same safety boundary before it creates writeback changes.
"""

from __future__ import annotations

from dmm.domain.feeder.topology import FeederDrawingTopologyClassifier
from dmm.domain.feeder.topology import FeederTopologyResolver


JEDDAH_MAIN_DEVICE_TAGS = (
    "CBreaker",
    "Disconnector",
    "GroundDisconnector",
)


def check_graph_facid(parsed, feeder_id):
    """Compare a resolved feeder with the G root facID when facID is set."""

    graph_facid = str(parsed.root.attrib.get("facID") or "").strip()
    resolved = str(feeder_id or "").strip()
    if not graph_facid:
        return {
            "graph_facid": "",
            "facid_check": "EMPTY_ALLOWED",
            "facid_consistent": True,
            "facid_reason": "G 根节点 facID 为空，允许按已解析馈线继续校验。",
        }
    if not resolved:
        return {
            "graph_facid": graph_facid,
            "facid_check": "FEEDER_UNRESOLVED",
            "facid_consistent": True,
            "facid_reason": "尚未解析出目标 FEEDER_ID，由现有馈线解析规则继续处理。",
        }
    consistent = graph_facid == resolved
    return {
        "graph_facid": graph_facid,
        "facid_check": "MATCH" if consistent else "MISMATCH",
        "facid_consistent": consistent,
        "facid_reason": (
            "G 根节点 facID 与目标 FEEDER_ID 一致。"
            if consistent else
            "JEDDAH_FACID_FEEDER_MISMATCH: G 根节点 facID="
            f"{graph_facid}，目标 FEEDER_ID={resolved}，禁止关联。"
        ),
    }


def assess_jeddah_drawing_scope(parsed):
    """Return the common single-line/main-device association decision."""

    profile = FeederDrawingTopologyClassifier().classify(parsed)
    counts = {
        tag: sum(1 for obj in parsed.objects if obj.tag == tag)
        for tag in JEDDAH_MAIN_DEVICE_TAGS
    }
    by_id = {
        str(obj.xml_id): obj
        for obj in parsed.objects
        if str(obj.xml_id or "").strip()
    }
    graph = {xml_id: set() for xml_id in by_id}
    for obj in parsed.objects:
        xml_id = str(obj.xml_id or "").strip()
        if not xml_id:
            continue
        for ref in FeederTopologyResolver._refs(obj):
            ref = str(ref).strip()
            if ref in by_id:
                graph[xml_id].add(ref)
                graph[ref].add(xml_id)

    # Only an effective, connected Bus counts.  Small isolated Bus objects
    # are connection points and must not make an otherwise valid drawing fail.
    effective_buses = [
        obj for obj in parsed.objects
        if obj.tag == "Bus"
        and FeederDrawingTopologyClassifier._is_effective_busbar(obj)
        and str(obj.xml_id or "").strip()
    ]
    # Group effective Buses by their connected electrical component.  A
    # double-bus bay therefore remains one main-device group, while separate
    # bays in a composite drawing become separate groups.
    bus_groups = {}
    for bus in effective_buses:
        start = str(bus.xml_id)
        component = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for nxt in graph.get(current, ()):
                if nxt not in component:
                    component.add(nxt)
                    stack.append(nxt)
        component_counts = {
            tag: sum(
                1 for xml_id in component
                if by_id[xml_id].tag == tag
            )
            for tag in JEDDAH_MAIN_DEVICE_TAGS
        }
        if sum(component_counts.values()) > 0:
            component_key = frozenset(component)
            group = bus_groups.setdefault(
                component_key,
                {
                    "bus_xml_ids": [],
                    "main_device_counts": component_counts,
                },
            )
            group["bus_xml_ids"].append(start)
    associated_groups = list(bus_groups.values())
    associated_bus_count = sum(
        len(group["bus_xml_ids"]) for group in associated_groups
    )
    main_group = associated_groups[0] if len(associated_groups) == 1 else None
    main_group_counts = (
        dict(main_group["main_device_counts"]) if main_group else {}
    )
    blockers = []
    if profile.get("drawing_type") != "SINGLE_FEEDER":
        blockers.append(
            "JEDDAH_SINGLE_LINE_ONLY: 当前 G 图不是单线图（只允许一个馈线），"
            "禁止在合成图或环网图中关联。"
        )
    duplicate_tags = [
        f"{tag}={count}"
        for tag, count in counts.items()
        if tag in {"CBreaker", "GroundDisconnector"} and count > 1
    ]
    if duplicate_tags:
        blockers.append(
            "JEDDAH_MAIN_DEVICE_GROUP_MULTIPLE: 当前 G 图检测到多组主网设备（"
            + ", ".join(duplicate_tags)
            + "），禁止关联。"
        )
    if len(associated_groups) != 1:
        blockers.append(
            "JEDDAH_MAIN_BUS_GROUP_NOT_UNIQUE: 必须只有一个与主网设备相连的"
            "主网设备组；双母线属于同一组，孤立 Bus 不计入；"
            f"当前找到 {len(associated_groups)} 组。"
        )
    elif associated_bus_count not in {1, 2}:
        blockers.append(
            "JEDDAH_MAIN_BUS_COUNT_INVALID: 单母线或双母线才允许关联；"
            f"当前主网 Bus 数量={associated_bus_count}。"
        )
    if main_group is not None:
        if main_group_counts != counts:
            blockers.append(
                "JEDDAH_MAIN_DEVICE_GROUP_NOT_UNIQUE: 存在未归属于同一主网 Bus 组的主网设备，"
                "禁止关联。"
            )
        if (
            main_group_counts.get("CBreaker", 0) != 1
            or main_group_counts.get("GroundDisconnector", 0) != 1
            or main_group_counts.get("Disconnector", 0) < 1
        ):
            blockers.append(
                "JEDDAH_MAIN_BUS_DEVICE_SET_INVALID: 主网设备组必须包含一个"
                " CBreaker、至少一个 Disconnector 和一个 GroundDisconnector；"
                + ", ".join(
                    f"{tag}={main_group_counts.get(tag, 0)}"
                    for tag in JEDDAH_MAIN_DEVICE_TAGS
                )
                + "。"
            )
    elif not associated_groups:
        blockers.append(
            "JEDDAH_MAIN_BUS_DEVICE_SET_INVALID: 未找到与主网设备相连的有效 Bus。"
        )
    return {
        "drawing_type": profile.get("drawing_type", "AMBIGUOUS"),
        "classification_reason": profile.get("classification_reason", ""),
        "classification_confidence": profile.get("classification_confidence", ""),
        "main_device_counts": counts,
        "associated_bus_count": associated_bus_count,
        "associated_bus_xml_id": (
            ", ".join(main_group["bus_xml_ids"]) if main_group else ""
        ),
        "associated_bus_main_device_counts": (
            main_group_counts if main_group else {}
        ),
        "main_bus_layout": (
            "DOUBLE_BUS" if associated_bus_count == 2
            else "SINGLE_BUS" if associated_bus_count == 1
            else ""
        ),
        "association_allowed": not blockers,
        # Keep the row-level/report message short.  The complete list remains
        # available for diagnostics and can be shown on demand.
        "block_reason": blockers[0] if blockers else "",
        "block_reasons": blockers,
    }


def apply_jeddah_scope_block(rows, scope):
    """Make already-discovered rows non-executable when scope is blocked."""

    reason = scope.get("block_reason") or "JEDDAH_ASSOCIATION_SCOPE_BLOCKED"
    for row in rows or []:
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "reason": reason,
        })


def apply_association_block(rows, reason):
    """Block association rows for a non-topology hard constraint."""

    for row in rows or []:
        row.update({
            "status": "FAIL",
            "severity": "ERROR",
            "association_ready": "NO",
            "writeback_needed": "NO",
            "reason": reason or "ASSOCIATION_BLOCKED",
        })


def scope_report_fields(scope):
    """Small stable report payload shared by HTML/CSV writers."""

    return {
        "drawing_scope": scope,
        "drawing_type": scope.get("drawing_type", "AMBIGUOUS"),
        "main_device_counts": dict(scope.get("main_device_counts", {})),
        "associated_bus_count": scope.get("associated_bus_count", 0),
        "associated_bus_xml_id": scope.get("associated_bus_xml_id", ""),
        "main_bus_layout": scope.get("main_bus_layout", ""),
        "associated_bus_main_device_counts": dict(
            scope.get("associated_bus_main_device_counts", {})
        ),
        "association_scope_allowed": (
            "YES" if scope.get("association_allowed") else "NO"
        ),
        "association_scope_reason": scope.get("block_reason", ""),
        "association_scope_reasons": list(scope.get("block_reasons", []) or []),
    }
