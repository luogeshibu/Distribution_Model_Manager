from __future__ import annotations

"""Faithful, self-contained SVG preview renderer for NARI ``*.g`` drawings.

The renderer intentionally uses only information already present in the G XML.
It does not infer feeder ownership, NOP semantics, database data, or topology
membership.  Geometry, object order, labels, line styles, RMU frames, status
icons, switch symbols, NOP image placeholders, and title-frame objects are all
rendered from the source G object attributes.

External ``*.icn.g`` symbol libraries are not embedded in a business G file, so
for those GIcon objects we draw a deterministic vector surrogate based on the
object tag/devref while preserving the exact source x/y/w/h/rotate placement.
Every rendered object also receives an SVG ``<title>`` containing its original
G metadata so operators can inspect the source object on hover.
"""

import html
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


LINE_TAGS = {"ConnectLine", "FeedLine", "Bus", "ACLine", "BusDis", "line"}
TEXT_TAGS = {"Text", "DText"}
META_TAGS = {"G", "Layer", "Color", "Font", "Theme", "Item"}
ICON_TAGS = {
    "CBreakerDis",
    "ZhaiWaiJieDiDaoZha",
    "Status",
    "pwbh",
    "CBreaker",
    "GroundDisconnector",
    "Disconnector",
    "Protect",
    "Transformer2",
    "PT",
    "Capacitor",
}


def _local_name(tag: str) -> str:
    return str(tag).split("}", 1)[-1]


def _txt(value: object) -> str:
    return "" if value is None else str(value).strip()


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _points(element: ET.Element) -> list[tuple[float, float]]:
    raw = _txt(element.get("d"))
    if not raw:
        return []
    values: list[float] = []
    for token in re.split(r"[\s,]+", raw):
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError:
            return []
    if len(values) < 4 or len(values) % 2:
        return []
    return list(zip(values[0::2], values[1::2]))


def _parse_rgb(raw: str) -> tuple[int, int, int] | None:
    raw = _txt(raw)
    if not raw:
        return None
    if raw.startswith("#"):
        value = raw[1:]
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        if len(value) == 6:
            try:
                return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return None
    parts = [part.strip() for part in raw.split(",")]
    if len(parts) >= 3:
        try:
            return tuple(max(0, min(255, int(float(part)))) for part in parts[:3])  # type: ignore[return-value]
        except ValueError:
            return None
    return None


def _hex(rgb: tuple[int, int, int] | None, default: str) -> str:
    if rgb is None:
        return default
    return "#" + "".join(f"{item:02x}" for item in rgb)


def _raw_color(element: ET.Element, *, fill: bool = False, default: str = "#222222") -> str:
    candidates = ("fcc", "fc") if fill else ("lcc", "lc")
    for key in candidates:
        rgb = _parse_rgb(_txt(element.get(key)))
        if rgb is not None:
            return _hex(rgb, default)
    return default


def _light_theme_color(element: ET.Element, tag: str, *, fill: bool = False) -> str:
    """Map native dark-canvas colors to a readable light report canvas.

    Production G drawings frequently store labels/RMU frames as pure white for
    a black runtime canvas.  The report intentionally uses a white canvas to
    match the operator's light GFileStudio screenshots, so only near-white and
    near-yellow colors are remapped for legibility.  Other source colors are
    preserved exactly.
    """
    raw = _raw_color(element, fill=fill, default="#222222")
    rgb = _parse_rgb(raw)
    if rgb is None:
        return raw
    r, g, b = rgb

    # Built-in title/info frame explicitly uses white text over green fill.
    if tag in TEXT_TAGS and any(key.startswith("gfs_frame_") for key in element.attrib):
        return raw

    if r >= 238 and g >= 238 and b >= 238:
        if tag in TEXT_TAGS:
            return "#1f2937"
        return "#60656b"
    if r >= 220 and g >= 220 and b <= 170:
        return "#8a6d00"
    return raw


def _stroke_width(element: ET.Element, default: float = 1.0) -> float:
    return max(0.8, min(8.0, _num(element.get("lw"), default)))


def _dasharray(element: ET.Element) -> str:
    ls = _txt(element.get("ls"))
    if ls == "2":
        return "12 8"
    if ls in {"3", "4"}:
        return "4 6"
    return ""


def _rotation(element: ET.Element) -> float:
    value = _num(element.get("rotate"), 0.0)
    if abs(value) < 1e-9:
        tfr = _txt(element.get("tfr"))
        match = re.search(r"rotate\(([-+0-9.eE]+)\)", tfr)
        if match:
            value = _num(match.group(1), 0.0)
    return value % 360.0


def _box(element: ET.Element) -> tuple[float, float, float, float]:
    x = _num(element.get("x"), 0.0)
    y = _num(element.get("y"), 0.0)
    w = max(0.0, _num(element.get("w") or element.get("width"), 0.0))
    h = max(0.0, _num(element.get("h") or element.get("height"), 0.0))
    return x, y, w, h


def _visible(element: ET.Element) -> bool:
    if _txt(element.get("isDisplay")) == "0":
        return False
    if _num(element.get("opacity"), 1.0) <= 0.0:
        return False
    return True


def _title(element: ET.Element, tag: str) -> str:
    parts = [tag]
    for key in (
        "id",
        "ts",
        "p_NameString",
        "gfs_rmu_name",
        "key_name",
        "devref",
        "ahref",
        "link",
        "node_area",
    ):
        value = _txt(element.get(key))
        if not value:
            continue
        if len(value) > 260:
            value = value[:257] + "..."
        parts.append(f"{key}={value}")
    return html.escape(" | ".join(parts))


def _group_transform(element: ET.Element) -> str:
    x, y, w, h = _box(element)
    angle = _rotation(element)
    if abs(angle) <= 1e-9:
        return ""
    cx = x + w / 2.0
    cy = y + h / 2.0
    return f" transform='rotate({angle:.3f} {cx:.3f} {cy:.3f})'"


def _svg_polyline(element: ET.Element, tag: str, *, highlight: str = "") -> str:
    pts = _points(element)
    if len(pts) < 2:
        return ""
    coords = " ".join(f"{x:.3f},{y:.3f}" for x, y in pts)
    color = _light_theme_color(element, tag)
    width = _stroke_width(element, 1.0)
    dash = _dasharray(element)
    dash_attr = f" stroke-dasharray='{dash}'" if dash else ""
    title = _title(element, tag)
    underlay = ""
    if highlight:
        underlay = (
            f"<polyline points='{coords}' fill='none' stroke='{highlight}' stroke-width='{max(7.0, width + 6.0):.2f}' "
            "stroke-linecap='round' stroke-linejoin='round' opacity='.45' vector-effect='non-scaling-stroke'/>"
        )
    return (
        f"<g>{underlay}<polyline points='{coords}' fill='none' stroke='{color}' stroke-width='{width:.2f}'{dash_attr} "
        "stroke-linecap='round' stroke-linejoin='round' vector-effect='non-scaling-stroke'>"
        f"<title>{title}</title></polyline></g>"
    )


def _svg_rect(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    if w <= 0 or h <= 0:
        return ""
    stroke = _light_theme_color(element, tag)
    fill = "none"
    if _txt(element.get("fm")) == "1":
        fill = _light_theme_color(element, tag, fill=True)
    width = _stroke_width(element, 1.0)
    dash = _dasharray(element)
    dash_attr = f" stroke-dasharray='{dash}'" if dash else ""
    return (
        f"<rect x='{x:.3f}' y='{y:.3f}' width='{w:.3f}' height='{h:.3f}' fill='{fill}' stroke='{stroke}' "
        f"stroke-width='{width:.2f}'{dash_attr} vector-effect='non-scaling-stroke'{_group_transform(element)}>"
        f"<title>{_title(element, tag)}</title></rect>"
    )


def _svg_text(element: ET.Element, tag: str) -> str:
    text = _txt(element.get("ts"))
    if not text:
        return ""
    x, y, w, h = _box(element)
    fs = max(6.0, _num(element.get("fs") or element.get("p_FontHeight"), h if h > 0 else 20.0))
    color = _light_theme_color(element, tag)
    font = html.escape(_txt(element.get("ff")) or "Arial", quote=True)
    weight = "700" if _txt(element.get("bold")).lower() == "true" or _txt(element.get("p_BoldFontFlag")) == "1" else "400"
    style = "italic" if _txt(element.get("italic")).lower() == "true" or _txt(element.get("p_ItalicFontFlag")) == "1" else "normal"
    # G text x/y is top-left; SVG y is baseline.  0.88*font-size visually
    # matches GFileStudio's Arial text placement closely for the field files.
    baseline = y + fs * 0.88
    angle = _rotation(element)
    transform = ""
    if abs(angle) > 1e-9:
        cx, cy = x + w / 2.0, y + h / 2.0
        transform = f" transform='rotate({angle:.3f} {cx:.3f} {cy:.3f})'"
    opacity = max(0.0, min(1.0, _num(element.get("opacity"), 1.0)))
    return (
        f"<text x='{x:.3f}' y='{baseline:.3f}' font-family='{font}, Segoe UI, Microsoft YaHei, sans-serif' "
        f"font-size='{fs:.3f}' font-weight='{weight}' font-style='{style}' fill='{color}' opacity='{opacity:.3f}'{transform}>"
        f"<title>{_title(element, tag)}</title>{html.escape(text)}</text>"
    )


def _g_wrap(element: ET.Element, tag: str, body: str) -> str:
    if not body:
        return ""
    return f"<g{_group_transform(element)}><title>{_title(element, tag)}</title>{body}</g>"


def _icon_status(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    r = max(5.0, min(w, h) * 0.42)
    devref = _txt(element.get("devref"))
    if "Generator" in devref:
        return _g_wrap(element, tag, f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{r:.3f}' fill='#8a8a8a'/><text x='{cx:.3f}' y='{cy+r*.35:.3f}' text-anchor='middle' font-size='{r*1.05:.3f}' font-family='Arial' fill='#333'>G</text>")
    if "General_Note" in devref:
        return _g_wrap(element, tag, f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{r:.3f}' fill='#8a8a8a'/><text x='{cx:.3f}' y='{cy+r*.35:.3f}' text-anchor='middle' font-size='{r*1.05:.3f}' font-family='Arial' fill='#333'>i</text>")
    # Temporary cable target icon.
    return _g_wrap(
        element,
        tag,
        f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{r:.3f}' fill='none' stroke='#8a8a8a' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{r*.68:.3f}' fill='none' stroke='#8a8a8a' stroke-width='1.0' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{r*.35:.3f}' fill='none' stroke='#8a8a8a' stroke-width='1.0' vector-effect='non-scaling-stroke'/>",
    )


def _icon_pwbh(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    devref = _txt(element.get("devref"))
    color = "#8a8a8a"
    if "Earth" not in devref:
        fs = max(10.0, min(w, h) * 0.62)
        return _g_wrap(element, tag, f"<text x='{cx:.3f}' y='{cy+fs*.32:.3f}' text-anchor='middle' font-size='{fs:.3f}' font-family='Arial' fill='{color}'>!</text>")
    s = max(3.0, min(w, h) * 0.42)
    body = (
        f"<line x1='{cx:.3f}' y1='{cy-s*.75:.3f}' x2='{cx:.3f}' y2='{cy+s*.05:.3f}' stroke='{color}' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s*.62:.3f}' y1='{cy+s*.08:.3f}' x2='{cx+s*.62:.3f}' y2='{cy+s*.08:.3f}' stroke='{color}' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s*.42:.3f}' y1='{cy+s*.30:.3f}' x2='{cx+s*.42:.3f}' y2='{cy+s*.30:.3f}' stroke='{color}' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s*.22:.3f}' y1='{cy+s*.50:.3f}' x2='{cx+s*.22:.3f}' y2='{cy+s*.50:.3f}' stroke='{color}' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
    )
    return _g_wrap(element, tag, body)


def _icon_breaker_dis(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    s = max(7.0, min(w, h) * 0.42)
    devref = _txt(element.get("devref"))
    if "Circuit_Breaker" in devref:
        body = (
            f"<line x1='{cx-s:.3f}' y1='{cy:.3f}' x2='{cx-s*.42:.3f}' y2='{cy:.3f}' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
            f"<rect x='{cx-s*.42:.3f}' y='{cy-s*.32:.3f}' width='{s*.84:.3f}' height='{s*.64:.3f}' fill='white' stroke='{color}' stroke-width='1.5' vector-effect='non-scaling-stroke'/>"
            f"<line x1='{cx+s*.42:.3f}' y1='{cy:.3f}' x2='{cx+s:.3f}' y2='{cy:.3f}' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
        )
    else:
        body = (
            f"<line x1='{cx-s:.3f}' y1='{cy:.3f}' x2='{cx-s*.55:.3f}' y2='{cy:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
            f"<circle cx='{cx-s*.42:.3f}' cy='{cy:.3f}' r='{max(1.8,s*.11):.3f}' fill='{color}'/>"
            f"<circle cx='{cx+s*.42:.3f}' cy='{cy:.3f}' r='{max(1.8,s*.11):.3f}' fill='{color}'/>"
            f"<line x1='{cx-s*.28:.3f}' y1='{cy-s*.06:.3f}' x2='{cx+s*.20:.3f}' y2='{cy-s*.36:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
            f"<line x1='{cx+s*.55:.3f}' y1='{cy:.3f}' x2='{cx+s:.3f}' y2='{cy:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
        )
    return _g_wrap(element, tag, body)


def _icon_ground_external(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    s = max(6.0, min(w, h) * 0.42)
    body = (
        f"<line x1='{cx-s*.8:.3f}' y1='{cy:.3f}' x2='{cx-s*.15:.3f}' y2='{cy:.3f}' stroke='{color}' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{max(1.6,s*.10):.3f}' fill='{color}'/>"
        f"<line x1='{cx:.3f}' y1='{cy+s*.12:.3f}' x2='{cx:.3f}' y2='{cy+s*.62:.3f}' stroke='{color}' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s*.45:.3f}' y1='{cy+s*.68:.3f}' x2='{cx+s*.45:.3f}' y2='{cy+s*.68:.3f}' stroke='{color}' stroke-width='1.0' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s*.30:.3f}' y1='{cy+s*.84:.3f}' x2='{cx+s*.30:.3f}' y2='{cy+s*.84:.3f}' stroke='{color}' stroke-width='1.0' vector-effect='non-scaling-stroke'/>"
    )
    return _g_wrap(element, tag, body)


def _icon_main_breaker(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    s = max(8.0, min(w, h) * 0.38)
    body = (
        f"<line x1='{cx:.3f}' y1='{cy-s:.3f}' x2='{cx:.3f}' y2='{cy-s*.48:.3f}' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
        f"<rect x='{cx-s*.42:.3f}' y='{cy-s*.48:.3f}' width='{s*.84:.3f}' height='{s*.96:.3f}' fill='white' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx:.3f}' y1='{cy+s*.48:.3f}' x2='{cx:.3f}' y2='{cy+s:.3f}' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
    )
    return _g_wrap(element, tag, body)


def _icon_disconnector(element: ET.Element, tag: str, *, ground: bool = False) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    s = max(8.0, min(w, h) * 0.40)
    body = (
        f"<line x1='{cx:.3f}' y1='{cy-s:.3f}' x2='{cx:.3f}' y2='{cy-s*.52:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy-s*.38:.3f}' r='{max(1.7,s*.10):.3f}' fill='{color}'/>"
        f"<circle cx='{cx:.3f}' cy='{cy+s*.38:.3f}' r='{max(1.7,s*.10):.3f}' fill='{color}'/>"
        f"<line x1='{cx+s*.03:.3f}' y1='{cy-s*.23:.3f}' x2='{cx+s*.34:.3f}' y2='{cy+s*.18:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx:.3f}' y1='{cy+s*.52:.3f}' x2='{cx:.3f}' y2='{cy+s:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
    )
    if ground:
        gx = cx + s * 0.72
        body += (
            f"<line x1='{cx+s*.22:.3f}' y1='{cy:.3f}' x2='{gx:.3f}' y2='{cy:.3f}' stroke='{color}' stroke-width='1.1' vector-effect='non-scaling-stroke'/>"
            f"<line x1='{gx:.3f}' y1='{cy:.3f}' x2='{gx:.3f}' y2='{cy+s*.35:.3f}' stroke='{color}' stroke-width='1.1' vector-effect='non-scaling-stroke'/>"
            f"<line x1='{gx-s*.30:.3f}' y1='{cy+s*.40:.3f}' x2='{gx+s*.30:.3f}' y2='{cy+s*.40:.3f}' stroke='{color}' stroke-width='1.0' vector-effect='non-scaling-stroke'/>"
        )
    return _g_wrap(element, tag, body)


def _icon_protect(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    s = max(8.0, min(w, h) * 0.42)
    body = (
        f"<rect x='{cx-s:.3f}' y='{cy-s:.3f}' width='{2*s:.3f}' height='{2*s:.3f}' fill='white' stroke='#8a8a8a' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
        f"<text x='{cx:.3f}' y='{cy+s*.42:.3f}' text-anchor='middle' font-size='{s*1.28:.3f}' font-family='Arial' fill='#8a8a8a'>R</text>"
    )
    return _g_wrap(element, tag, body)


def _icon_transformer(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    r = max(12.0, min(w, h) * 0.23)
    body = (
        f"<line x1='{cx:.3f}' y1='{y:.3f}' x2='{cx:.3f}' y2='{cy-r*1.7:.3f}' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy-r*.55:.3f}' r='{r:.3f}' fill='none' stroke='{color}' stroke-width='1.5' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy+r*.55:.3f}' r='{r:.3f}' fill='none' stroke='{color}' stroke-width='1.5' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx:.3f}' y1='{cy+r*1.7:.3f}' x2='{cx:.3f}' y2='{y+h:.3f}' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>"
    )
    return _g_wrap(element, tag, body)


def _icon_pt(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    r = max(12.0, min(w, h) * 0.28)
    body = (
        f"<line x1='{cx:.3f}' y1='{y:.3f}' x2='{cx:.3f}' y2='{cy-r:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
        f"<circle cx='{cx:.3f}' cy='{cy:.3f}' r='{r:.3f}' fill='white' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
        f"<text x='{cx:.3f}' y='{cy+r*.25:.3f}' text-anchor='middle' font-size='{r*.70:.3f}' font-family='Arial' fill='{color}'>PT</text>"
    )
    return _g_wrap(element, tag, body)


def _icon_capacitor(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    cx, cy = x + w / 2.0, y + h / 2.0
    color = _light_theme_color(element, tag)
    s = max(12.0, min(w, h) * 0.28)
    body = (
        f"<line x1='{cx:.3f}' y1='{y:.3f}' x2='{cx:.3f}' y2='{cy-s*.35:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s:.3f}' y1='{cy-s*.30:.3f}' x2='{cx+s:.3f}' y2='{cy-s*.30:.3f}' stroke='{color}' stroke-width='1.5' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx-s:.3f}' y1='{cy+s*.30:.3f}' x2='{cx+s:.3f}' y2='{cy+s*.30:.3f}' stroke='{color}' stroke-width='1.5' vector-effect='non-scaling-stroke'/>"
        f"<line x1='{cx:.3f}' y1='{cy+s*.35:.3f}' x2='{cx:.3f}' y2='{y+h:.3f}' stroke='{color}' stroke-width='1.4' vector-effect='non-scaling-stroke'/>"
    )
    return _g_wrap(element, tag, body)


def _svg_icon(element: ET.Element, tag: str) -> str:
    if tag == "Status":
        return _icon_status(element, tag)
    if tag == "pwbh":
        return _icon_pwbh(element, tag)
    if tag == "CBreakerDis":
        return _icon_breaker_dis(element, tag)
    if tag == "ZhaiWaiJieDiDaoZha":
        return _icon_ground_external(element, tag)
    if tag == "CBreaker":
        return _icon_main_breaker(element, tag)
    if tag == "Disconnector":
        return _icon_disconnector(element, tag, ground=False)
    if tag == "GroundDisconnector":
        return _icon_disconnector(element, tag, ground=True)
    if tag == "Protect":
        return _icon_protect(element, tag)
    if tag == "Transformer2":
        return _icon_transformer(element, tag)
    if tag == "PT":
        return _icon_pt(element, tag)
    if tag == "Capacitor":
        return _icon_capacitor(element, tag)
    return ""


def _svg_poke(element: ET.Element, tag: str) -> str:
    # fm=0/ls=0 RMU pokes are invisible click hotspots in GFileStudio.  They are
    # preserved as SVG metadata only and must not be drawn as fake rectangles.
    if _txt(element.get("fm")) != "1" and _txt(element.get("ls")) in {"", "0"}:
        return ""
    x, y, w, h = _box(element)
    if w <= 0 or h <= 0:
        return ""
    fill = _light_theme_color(element, tag, fill=True)
    stroke = _light_theme_color(element, tag)
    return (
        f"<rect x='{x:.3f}' y='{y:.3f}' width='{w:.3f}' height='{h:.3f}' rx='1.5' fill='{fill}' stroke='{stroke}' "
        f"stroke-width='{_stroke_width(element):.2f}' vector-effect='non-scaling-stroke'{_group_transform(element)}>"
        f"<title>{_title(element, tag)}</title></rect>"
    )


def _svg_image(element: ET.Element, tag: str) -> str:
    x, y, w, h = _box(element)
    if w <= 0 or h <= 0:
        return ""
    href = _txt(element.get("ahref"))
    if href.lower().endswith("nop.png"):
        cx, cy = x + w / 2.0, y + h / 2.0
        body = (
            f"<ellipse cx='{cx:.3f}' cy='{cy:.3f}' rx='{w*.48:.3f}' ry='{h*.46:.3f}' fill='#ff1010' stroke='#ff1010' stroke-width='1.2' vector-effect='non-scaling-stroke'/>"
            f"<text x='{cx:.3f}' y='{cy+h*.13:.3f}' text-anchor='middle' font-size='{max(9.0,h*.34):.3f}' font-family='Arial' fill='white'>N.O.P</text>"
        )
        return _g_wrap(element, tag, body)
    # Unknown external bitmap: preserve its exact footprint and reference name.
    label = html.escape(Path(href).name if href else "image")
    return _g_wrap(
        element,
        tag,
        f"<rect x='{x:.3f}' y='{y:.3f}' width='{w:.3f}' height='{h:.3f}' fill='none' stroke='#9ca3af' stroke-width='1' vector-effect='non-scaling-stroke'/>"
        f"<text x='{x+w/2:.3f}' y='{y+h/2:.3f}' text-anchor='middle' font-size='{max(8.0,min(w,h)*.20):.3f}' font-family='Arial' fill='#6b7280'>{label}</text>",
    )


def _element_bounds(element: ET.Element, tag: str) -> tuple[float, float, float, float] | None:
    if tag in LINE_TAGS:
        pts = _points(element)
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return min(xs), min(ys), max(xs), max(ys)
    x, y, w, h = _box(element)
    if w > 0 or h > 0:
        return x, y, x + w, y + h
    return None


def _canvas_bounds(root: ET.Element) -> tuple[float, float, float, float]:
    x = _num(root.get("x"), 0.0)
    y = _num(root.get("y"), 0.0)
    w = _num(root.get("width") or root.get("w"), 0.0)
    h = _num(root.get("height") or root.get("h"), 0.0)
    if w > 0 and h > 0:
        return x, y, x + w, y + h

    boxes: list[tuple[float, float, float, float]] = []
    for element in root.iter():
        tag = _local_name(element.tag)
        if tag in META_TAGS or not _visible(element):
            continue
        box = _element_bounds(element, tag)
        if box:
            boxes.append(box)
    if not boxes:
        return 0.0, 0.0, 1000.0, 800.0
    min_x = min(box[0] for box in boxes)
    min_y = min(box[1] for box in boxes)
    max_x = max(box[2] for box in boxes)
    max_y = max(box[3] for box in boxes)
    margin = 50.0
    return min_x - margin, min_y - margin, max_x + margin, max_y + margin


def _issue_point(row: Mapping[str, object], prefix: str) -> tuple[float, float] | None:
    try:
        return float(row[f"{prefix}_x_before"]), float(row[f"{prefix}_y_before"])
    except (KeyError, TypeError, ValueError):
        return None


def _issue_overlay(
    issue_rows: Sequence[Mapping[str, object]],
    *,
    after: bool,
    canvas_width: float,
) -> str:
    marker = max(36.0, min(96.0, canvas_width * 0.00092))
    font_size = max(28.0, marker * 0.52)
    out: list[str] = ["<g id='topology-issue-overlay'>"]
    for index, row in enumerate(issue_rows, start=1):
        p1 = _issue_point(row, "left")
        p2 = _issue_point(row, "right")
        if p1 is None or p2 is None:
            continue
        x1, y1 = p1
        x2, y2 = p2
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        status = _txt(row.get("status"))
        auto = status == "AUTO_FIXED"
        if after and auto:
            color, label = "#059669", f"#{index} 已修复"
        elif auto:
            color, label = "#ef4444", f"#{index} 断点"
        else:
            color, label = "#f59e0b", f"#{index} 待确认"
        distance = math.hypot(x1 - x2, y1 - y2)
        title = html.escape(
            f"{label}: {row.get('left_tag','')} {row.get('left_xml_id','')} ↔ "
            f"{row.get('right_tag','')} {row.get('right_xml_id','')}; distance={row.get('distance_before','')}G"
        )
        out.append(f"<g id='issue-{index}'><title>{title}</title>")
        if distance > 0.01:
            out.append(
                f"<line x1='{x1:.3f}' y1='{y1:.3f}' x2='{x2:.3f}' y2='{y2:.3f}' stroke='{color}' stroke-width='4.5' "
                "stroke-dasharray='12 8' opacity='.92' vector-effect='non-scaling-stroke'/>")
        out.append(
            f"<circle cx='{mx:.3f}' cy='{my:.3f}' r='{marker:.3f}' fill='{color}' fill-opacity='.08' stroke='{color}' stroke-width='5' vector-effect='non-scaling-stroke'/>")
        cross = marker * 0.48
        out.append(
            f"<line x1='{mx-cross:.3f}' y1='{my-cross:.3f}' x2='{mx+cross:.3f}' y2='{my+cross:.3f}' stroke='{color}' stroke-width='5' vector-effect='non-scaling-stroke'/>")
        out.append(
            f"<line x1='{mx-cross:.3f}' y1='{my+cross:.3f}' x2='{mx+cross:.3f}' y2='{my-cross:.3f}' stroke='{color}' stroke-width='5' vector-effect='non-scaling-stroke'/>")
        out.append(
            f"<text x='{mx+marker*.72:.3f}' y='{my-marker*.60:.3f}' font-size='{font_size:.3f}' font-family='Segoe UI,Microsoft YaHei,Arial' "
            f"font-weight='700' fill='{color}' paint-order='stroke' stroke='white' stroke-width='8' stroke-linejoin='round'>{html.escape(label)}</text>")
        out.append("</g>")
    out.append("</g>")
    return "".join(out)


@dataclass(frozen=True)
class GRenderStats:
    total_source_objects: int
    visible_source_objects: int
    rendered_objects: int
    skipped_invisible_objects: int
    skipped_metadata_objects: int
    rendered_by_tag: dict[str, int]
    canvas_width: float
    canvas_height: float


def render_g_root_to_svg(
    root: ET.Element,
    path: Path,
    *,
    issue_rows: Sequence[Mapping[str, object]] = (),
    after: bool = False,
) -> GRenderStats:
    min_x, min_y, max_x, max_y = _canvas_bounds(root)
    width = max(100.0, max_x - min_x)
    height = max(100.0, max_y - min_y)

    repaired_ids: set[str] = set()
    problem_ids: set[str] = set()
    for row in issue_rows:
        left_id = _txt(row.get("left_xml_id"))
        right_id = _txt(row.get("right_xml_id"))
        moved_id = _txt(row.get("moved_xml_id"))
        if left_id:
            problem_ids.add(left_id)
        if right_id:
            problem_ids.add(right_id)
        if moved_id:
            repaired_ids.add(moved_id)

    body: list[str] = [
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{min_x:.3f} {min_y:.3f} {width:.3f} {height:.3f}' role='img' preserveAspectRatio='xMinYMin meet'>",
        f"<rect x='{min_x:.3f}' y='{min_y:.3f}' width='{width:.3f}' height='{height:.3f}' fill='#ffffff'/>",
    ]

    total = 0
    visible = 0
    skipped_invisible = 0
    skipped_metadata = 0
    rendered = 0
    by_tag: Counter[str] = Counter()

    for element in root.iter():
        tag = _local_name(element.tag)
        if element is root or tag in META_TAGS:
            if element is not root:
                skipped_metadata += 1
            continue
        total += 1
        if not _visible(element):
            skipped_invisible += 1
            continue
        visible += 1

        snippet = ""
        if tag in LINE_TAGS:
            element_id = _txt(element.get("id"))
            highlight = ""
            if after and element_id in repaired_ids:
                highlight = "#059669"
            elif not after and element_id in problem_ids:
                highlight = "#ef4444"
            snippet = _svg_polyline(element, tag, highlight=highlight)
        elif tag == "rect":
            snippet = _svg_rect(element, tag)
        elif tag in TEXT_TAGS:
            snippet = _svg_text(element, tag)
        elif tag in ICON_TAGS:
            snippet = _svg_icon(element, tag)
        elif tag == "poke":
            snippet = _svg_poke(element, tag)
        elif tag == "image":
            snippet = _svg_image(element, tag)
        else:
            # Unknown visible G object: preserve its exact footprint rather than
            # silently dropping it.  This makes omissions obvious in the report.
            x, y, w, h = _box(element)
            if w > 0 and h > 0:
                snippet = (
                    f"<g{_group_transform(element)}><title>{_title(element, tag)}</title>"
                    f"<rect x='{x:.3f}' y='{y:.3f}' width='{w:.3f}' height='{h:.3f}' fill='none' stroke='#94a3b8' stroke-width='1' stroke-dasharray='3 4' vector-effect='non-scaling-stroke'/>"
                    f"</g>"
                )

        if snippet:
            body.append(snippet)
            rendered += 1
            by_tag[tag] += 1

    body.append(_issue_overlay(issue_rows, after=after, canvas_width=width))
    body.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(body), encoding="utf-8")

    return GRenderStats(
        total_source_objects=total,
        visible_source_objects=visible,
        rendered_objects=rendered,
        skipped_invisible_objects=skipped_invisible,
        skipped_metadata_objects=skipped_metadata,
        rendered_by_tag=dict(sorted(by_tag.items())),
        canvas_width=width,
        canvas_height=height,
    )
