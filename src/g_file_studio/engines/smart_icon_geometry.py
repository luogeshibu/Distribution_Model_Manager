from __future__ import annotations

import itertools
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from g_file_studio.engines.id_engine import local_name
from g_file_studio.engines.icon_upgrade_engine import rotated


@dataclass(frozen=True)
class SmartIconGeometryTemplate:
    devref: str
    rotation: int
    width: float
    height: float
    anchor_offsets: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class SmartIconApplyResult:
    devref_changed: bool
    geometry_changed: bool
    template_used: bool
    fit_residual: float | None = None


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _rotation(element: ET.Element) -> int:
    raw = (element.get("rotate") or "").strip()
    if raw:
        try:
            return int(round(float(raw))) % 360
        except ValueError:
            pass
    tfr = element.get("tfr") or ""
    match = re.search(r"rotate\(\s*([-+]?\d+(?:\.\d+)?)", tfr)
    if match:
        try:
            return int(round(float(match.group(1)))) % 360
        except ValueError:
            pass
    return 0


def _points_from_d(element: ET.Element) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for token in (element.get("d") or "").replace(";", " ").split():
        if "," not in token:
            continue
        left, right = token.split(",", 1)
        try:
            points.append((float(left), float(right)))
        except ValueError:
            continue
    return points


def _point_to_box_distance(
    point: tuple[float, float],
    box: tuple[float, float, float, float],
) -> float:
    x, y = point
    left, top, right, bottom = box
    dx = max(left - x, 0.0, x - right)
    dy = max(top - y, 0.0, y - bottom)
    return math.hypot(dx, dy)


def _connected_ids(element: ET.Element) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for item in (element.get("node_area") or "").split(";"):
        parts = [part.strip() for part in item.split(",")]
        if len(parts) < 3 or not parts[2] or parts[2] in seen:
            continue
        seen.add(parts[2])
        ids.append(parts[2])
    return ids


def connected_anchor_points(
    element: ET.Element,
    element_by_id: dict[str, ET.Element],
) -> tuple[tuple[float, float], ...]:
    """Return the actual line-end coordinates attached to a device.

    ``node_area`` supplies the connected element IDs.  For each connected line, the
    endpoint nearest the current device box is treated as the electrical anchor.
    This keeps the calculation independent of the icon's visual center and works for
    both vertical and horizontal/rotated devices.
    """

    x = _number(element.get("x"))
    y = _number(element.get("y"))
    width = _number(element.get("w"))
    height = _number(element.get("h"))
    if width <= 0 or height <= 0:
        return ()
    box = (x, y, x + width, y + height)
    anchors: list[tuple[float, float]] = []
    for element_id in _connected_ids(element):
        linked = element_by_id.get(element_id)
        if linked is None or local_name(linked.tag) != "ConnectLine":
            continue
        points = _points_from_d(linked)
        if not points:
            continue
        point = min(points, key=lambda value: (_point_to_box_distance(value, box), value[0], value[1]))
        if point not in anchors:
            anchors.append(point)
    return tuple(anchors)


def build_geometry_templates(
    elements: list[ET.Element],
    target_devrefs: set[str] | frozenset[str],
) -> dict[tuple[str, int], list[SmartIconGeometryTemplate]]:
    """Learn target RMU symbol geometry from already-correct icons in the same G file.

    The geometry bank supports both switching devices (``CBreakerDis``) and the
    RMU grounding-switch element ``ZhaiWaiJieDiDaoZha``.  The latter is important
    because a vendor may update its icon size/port offsets while keeping the same
    electrical role.
    """

    by_id = {element.get("id"): element for element in elements if element.get("id")}
    templates: dict[tuple[str, int], list[SmartIconGeometryTemplate]] = {}
    seen: set[tuple[str, int, float, float, tuple[tuple[float, float], ...]]] = set()
    for element in elements:
        # v2.18.44: geometry templates are no longer limited to the three built-in
        # RMU roles. Any placed GIcon-like element with a devref and real electrical
        # anchors may participate in a user-defined symbol standard.
        devref = (element.get("devref") or "").strip()
        if devref not in target_devrefs:
            continue
        width = _number(element.get("w"))
        height = _number(element.get("h"))
        if width <= 0 or height <= 0:
            continue
        anchors = connected_anchor_points(element, by_id)
        if not anchors:
            continue
        x = _number(element.get("x"))
        y = _number(element.get("y"))
        observed_offsets = tuple((px - x, py - y) for px, py in anchors)
        observed_rotation = _rotation(element)

        # A correct target symbol may exist only in one orientation in the current
        # drawing (the real Jeddah 30815 case has NO-SMART CB samples at 270° while
        # the wrong legacy Q1 that needs correction is at 0°).  Recover the raw
        # rotation-0 pin offsets from the observed instance, then synthesize all four
        # orthogonal orientations.  This lets one confirmed target instance safely
        # correct another orientation without moving any ConnectLine endpoint.
        raw_offsets = tuple(
            rotated(offset, width, height, (-observed_rotation) % 360)
            for offset in observed_offsets
        )
        for rotation in (0, 90, 180, 270):
            offsets = tuple(rotated(offset, width, height, rotation) for offset in raw_offsets)
            signature = (devref, rotation, width, height, offsets)
            if signature in seen:
                continue
            seen.add(signature)
            templates.setdefault((devref, rotation), []).append(
                SmartIconGeometryTemplate(
                    devref=devref,
                    rotation=rotation,
                    width=width,
                    height=height,
                    anchor_offsets=offsets,
                )
            )
    return templates


def _fit_template(
    template: SmartIconGeometryTemplate,
    anchors: tuple[tuple[float, float], ...],
) -> tuple[float, float, float] | None:
    if not anchors or len(anchors) != len(template.anchor_offsets):
        return None
    # RMU switching devices normally have two electrical anchors.  Keep the helper
    # conservative for unexpected icons with many ports to avoid factorial growth.
    if len(anchors) > 5:
        return None

    best: tuple[float, float, float] | None = None
    for offsets in itertools.permutations(template.anchor_offsets):
        tx = sum(point[0] - offset[0] for point, offset in zip(anchors, offsets)) / len(anchors)
        ty = sum(point[1] - offset[1] for point, offset in zip(anchors, offsets)) / len(anchors)
        residual = math.sqrt(
            sum(
                ((tx + offset[0] - point[0]) ** 2 + (ty + offset[1] - point[1]) ** 2)
                for point, offset in zip(anchors, offsets)
            )
            / len(anchors)
        )
        candidate = (residual, tx, ty)
        if best is None or candidate < best:
            best = candidate
    return best


def apply_devref_preserving_anchors(
    element: ET.Element,
    new_devref: str,
    *,
    elements: list[ET.Element],
    templates: dict[tuple[str, int], list[SmartIconGeometryTemplate]] | None = None,
    max_fit_residual: float = 0.75,
    require_template_for_connected_devref_change: bool = False,
) -> SmartIconApplyResult:
    """Replace a SMART icon while keeping its electrical connection points fixed.

    If the file contains an already-correct target icon with the same rotation, its
    width/height and local port offsets are learned and used to recompute ``x/y``.
    Therefore the connected ``ConnectLine`` endpoints stay at exactly the same
    absolute coordinates even when the target icon has different internal geometry.

    When no safe geometry template can be learned, the default behavior remains
    backward-compatible: only ``devref`` is changed and geometry stays untouched.
    Callers that set ``require_template_for_connected_devref_change=True`` instead
    keep both devref and geometry unchanged for connected electrical symbols.
    """

    old_devref = (element.get("devref") or "").strip()

    by_id = {item.get("id"): item for item in elements if item.get("id")}
    anchors = connected_anchor_points(element, by_id)
    template_bank = templates or build_geometry_templates(elements, {new_devref})
    candidates = template_bank.get((new_devref, _rotation(element)), [])

    chosen: tuple[float, float, float, SmartIconGeometryTemplate] | None = None
    for template in candidates:
        fit = _fit_template(template, anchors)
        if fit is None:
            continue
        residual, tx, ty = fit
        candidate = (residual, tx, ty, template)
        if chosen is None or candidate[:3] < chosen[:3]:
            chosen = candidate

    geometry_changed = False
    template_used = False
    residual_value: float | None = None
    if chosen is not None and chosen[0] <= max_fit_residual:
        residual_value, new_x, new_y, template = chosen
        desired = {
            "x": _format_number(new_x),
            "y": _format_number(new_y),
            "w": _format_number(template.width),
            "h": _format_number(template.height),
        }
        for key, value in desired.items():
            if (element.get(key) or "") != value:
                element.set(key, value)
                geometry_changed = True
        template_used = True

    devref_changed = old_devref != new_devref
    # The generic Symbol Standard Correction action uses strict mode for connected
    # electrical symbols: changing devref without a fitting target geometry template
    # can visually detach the new icon from its fixed ConnectLine anchors.  Existing
    # callers (including Jeddah batch) keep the historical fallback by default.
    if (
        devref_changed
        and require_template_for_connected_devref_change
        and anchors
        and not template_used
    ):
        devref_changed = False
    if devref_changed:
        element.set("devref", new_devref)
    return SmartIconApplyResult(devref_changed, geometry_changed, template_used, residual_value)


def serialize_geometry_templates(
    templates: dict[tuple[str, int], list[SmartIconGeometryTemplate]],
) -> dict[str, list[dict[str, object]]]:
    """Serialize learned icon geometry so a Site Profile can reuse sample geometry.

    Keys are kept by devref rather than by site name.  This lets a user re-learn a
    profile when a vendor changes symbols without adding any site-specific code.
    """
    payload: dict[str, list[dict[str, object]]] = {}
    for (devref, rotation), rows in templates.items():
        for row in rows:
            payload.setdefault(devref, []).append(
                {
                    "rotation": int(rotation) % 360,
                    "width": float(row.width),
                    "height": float(row.height),
                    "anchor_offsets": [[float(x), float(y)] for x, y in row.anchor_offsets],
                }
            )
    return payload


def deserialize_geometry_templates(
    payload: dict[str, list[dict[str, object]]] | None,
) -> dict[tuple[str, int], list[SmartIconGeometryTemplate]]:
    """Restore profile geometry templates, ignoring malformed historical entries."""
    templates: dict[tuple[str, int], list[SmartIconGeometryTemplate]] = {}
    if not isinstance(payload, dict):
        return templates
    seen: set[tuple[str, int, float, float, tuple[tuple[float, float], ...]]] = set()
    for devref, rows in payload.items():
        if not isinstance(devref, str) or not devref.strip() or not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            try:
                rotation = int(raw.get("rotation", 0)) % 360
                width = float(raw.get("width", 0.0))
                height = float(raw.get("height", 0.0))
                raw_offsets = raw.get("anchor_offsets", [])
                offsets = tuple((float(pair[0]), float(pair[1])) for pair in raw_offsets if isinstance(pair, (list, tuple)) and len(pair) >= 2)
            except (TypeError, ValueError, IndexError):
                continue
            if width <= 0 or height <= 0 or not offsets:
                continue
            signature = (devref.strip(), rotation, width, height, offsets)
            if signature in seen:
                continue
            seen.add(signature)
            templates.setdefault((devref.strip(), rotation), []).append(
                SmartIconGeometryTemplate(
                    devref=devref.strip(),
                    rotation=rotation,
                    width=width,
                    height=height,
                    anchor_offsets=offsets,
                )
            )
    return templates


def merge_geometry_templates(
    *banks: dict[tuple[str, int], list[SmartIconGeometryTemplate]],
) -> dict[tuple[str, int], list[SmartIconGeometryTemplate]]:
    """Merge same-file and profile geometry templates without duplicate signatures."""
    merged: dict[tuple[str, int], list[SmartIconGeometryTemplate]] = {}
    seen: set[tuple[str, int, float, float, tuple[tuple[float, float], ...]]] = set()
    for bank in banks:
        for key, rows in (bank or {}).items():
            for row in rows:
                signature = (row.devref, row.rotation, row.width, row.height, row.anchor_offsets)
                if signature in seen:
                    continue
                seen.add(signature)
                merged.setdefault(key, []).append(row)
    return merged
