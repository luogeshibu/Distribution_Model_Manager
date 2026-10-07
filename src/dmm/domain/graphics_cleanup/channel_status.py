from __future__ import annotations

import csv
import html
import math
import os
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


# This module intentionally mirrors the proven G File Studio v2.18.244
# channel_status positioning algorithm used in the field:
#   * valid RMU frame = direct rect containing BusDis + CBreakerDis + ZhaiWaiJieDiDaoZha
#   * channel_status Status center inside rect is preferred
#   * otherwise allow a 40 px expanded search area
#   * if several candidates exist, choose the one nearest the BusDis center
#   * one Status can only belong to one RMU
#   * move only the Status itself as a rigid body
CHANNEL_STATUS_DEVREF_TOKEN = "channel_status.zt.icn.g:channel_status"
CHANNEL_STATUS_POSITIONS: dict[str, str] = {
    "top_left": "左上角",
    "top_center": "上边中点",
    "top_right": "右上角",
    "middle_left": "左边中点",
    "middle_right": "右边中点",
    "bottom_left": "左下角",
    "bottom_center": "下边中点",
    "bottom_right": "右下角",
}


@dataclass(frozen=True)
class _Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass
class ChannelStatusFileRecord:
    file_name: str
    rmu_rect_count: int = 0
    channel_status_found: int = 0
    channel_status_moved: int = 0
    channel_status_missing: int = 0
    target_position: str = "bottom_left"
    inner_margin: int = 5
    status: str = "NO_MATCH"


@dataclass
class ChannelStatusRepositionResult:
    output_files: list[Path]
    records: list[ChannelStatusFileRecord]
    csv_path: Path
    html_path: Path
    found: int
    moved: int
    missing: int


_PATH_COORD_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")
_X_POSITION_ATTRS = ("x", "x1", "x2", "cx", "mergex")
_Y_POSITION_ATTRS = ("y", "y1", "y2", "cy", "mergey")
_LINE_LIKE_TAGS = {
    "connectline",
    "line",
    "bus",
    "busdis",
    "feedline",
    "flowline",
    "polyline",
    "lwpolyline",
}


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _format_number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"非有限数值：{value}")
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(int(rounded))
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in {"-0", "-0.0"} else text


def _parse_number(value: str) -> float:
    return float(str(value).strip())


def _parse_d_points(value: str) -> list[tuple[float, float]]:
    return [
        (_parse_number(match.group(1)), _parse_number(match.group(2)))
        for match in _PATH_COORD_PATTERN.finditer(value or "")
    ]


def _combine_boxes(boxes) -> _Box | None:
    values = list(boxes)
    if not values:
        return None
    return _Box(
        min(box.left for box in values),
        min(box.top for box in values),
        max(box.right for box in values),
        max(box.bottom for box in values),
    )


def _node_box(node: ET.Element) -> _Box | None:
    tag = _local_name(node.tag).lower()
    numeric: dict[str, float] = {}
    for name in (
        "x", "y", "x1", "y1", "x2", "y2", "cx", "cy",
        "mergex", "mergey", "w", "h", "width", "height", "rx", "ry",
    ):
        raw = node.get(name)
        if raw not in (None, ""):
            try:
                numeric[name] = _parse_number(raw)
            except (TypeError, ValueError):
                return None

    if tag in _LINE_LIKE_TAGS:
        d_points = _parse_d_points(node.get("d", ""))
        if d_points:
            xs = [x for x, _ in d_points]
            ys = [y for _, y in d_points]
            return _Box(min(xs), min(ys), max(xs), max(ys))
        if all(name in numeric for name in ("x1", "y1", "x2", "y2")):
            return _Box(
                min(numeric["x1"], numeric["x2"]),
                min(numeric["y1"], numeric["y2"]),
                max(numeric["x1"], numeric["x2"]),
                max(numeric["y1"], numeric["y2"]),
            )
        if "x" in numeric and "y" in numeric:
            return _Box(numeric["x"], numeric["y"], numeric["x"], numeric["y"])
        return None

    xs: list[float] = []
    ys: list[float] = []
    for name in ("x", "x1", "x2", "cx", "mergex"):
        if name in numeric:
            xs.append(numeric[name])
    for name in ("y", "y1", "y2", "cy", "mergey"):
        if name in numeric:
            ys.append(numeric[name])

    width = numeric.get("w", numeric.get("width"))
    height = numeric.get("h", numeric.get("height"))
    if "x" in numeric and width is not None:
        xs.append(numeric["x"] + width)
    if "y" in numeric and height is not None:
        ys.append(numeric["y"] + height)
    if "mergex" in numeric and width is not None:
        xs.append(numeric["mergex"] + width)
    if "mergey" in numeric and height is not None:
        ys.append(numeric["mergey"] + height)
    if "cx" in numeric and "rx" in numeric:
        xs.extend((numeric["cx"] - numeric["rx"], numeric["cx"] + numeric["rx"]))
    if "cy" in numeric and "ry" in numeric:
        ys.extend((numeric["cy"] - numeric["ry"], numeric["cy"] + numeric["ry"]))
    for x, y in _parse_d_points(node.get("d", "")):
        xs.append(x)
        ys.append(y)
    if not xs or not ys:
        return None
    return _Box(min(xs), min(ys), max(xs), max(ys))


def _subtree_box(element: ET.Element) -> _Box | None:
    return _combine_boxes(
        box for node in element.iter() if (box := _node_box(node)) is not None
    )


def _fully_inside(inner: _Box, outer: _Box, tolerance: float = 0.5) -> bool:
    return (
        inner.left >= outer.left - tolerance
        and inner.top >= outer.top - tolerance
        and inner.right <= outer.right + tolerance
        and inner.bottom <= outer.bottom + tolerance
    )


def _area(box: _Box | None) -> float:
    if box is None:
        return 0.0
    return max(0.0, box.width) * max(0.0, box.height)


def _direct_rects(layer: ET.Element) -> list[ET.Element]:
    return [element for element in list(layer) if _local_name(element.tag) == "rect"]


def _elements_inside_rect(layer: ET.Element, rect: ET.Element) -> list[ET.Element]:
    rect_box = _subtree_box(rect)
    if rect_box is None:
        return []
    result: list[ET.Element] = []
    for element in list(layer):
        if element is rect or _local_name(element.tag) == "Merge":
            continue
        box = _subtree_box(element)
        if box is not None and _fully_inside(box, rect_box, tolerance=0.5):
            result.append(element)
    return result


def _center_inside_box(element: ET.Element, box: _Box, tolerance: float = 0.5) -> bool:
    candidate = _subtree_box(element)
    if candidate is None:
        return False
    return (
        box.left - tolerance <= candidate.center_x <= box.right + tolerance
        and box.top - tolerance <= candidate.center_y <= box.bottom + tolerance
    )


def _valid_rmu_rects(layer: ET.Element) -> list[ET.Element]:
    # Exact field rule copied from G File Studio: the rect must be large enough
    # and contain the three RMU structural element classes by center point.
    direct = list(layer)
    buses = [e for e in direct if _local_name(e.tag) == "BusDis"]
    breakers = [e for e in direct if _local_name(e.tag) == "CBreakerDis"]
    grounds = [e for e in direct if _local_name(e.tag) == "ZhaiWaiJieDiDaoZha"]
    result: list[ET.Element] = []
    for rect in _direct_rects(layer):
        rect_box = _subtree_box(rect)
        if rect_box is None or rect_box.width < 100 or rect_box.height < 100:
            continue
        if not any(_center_inside_box(e, rect_box) for e in buses):
            continue
        if not any(_center_inside_box(e, rect_box) for e in breakers):
            continue
        if not any(_center_inside_box(e, rect_box) for e in grounds):
            continue
        result.append(rect)
    return result


def _rmu_rects_by_busdis(layer: ET.Element) -> list[tuple[ET.Element, ET.Element]]:
    valid_ids = {
        (rect.get("id") or "").strip()
        for rect in _valid_rmu_rects(layer)
        if (rect.get("id") or "").strip()
    }
    matches: list[tuple[ET.Element, ET.Element]] = []
    for rect in _direct_rects(layer):
        if (rect.get("id") or "").strip() not in valid_ids:
            continue
        candidates = [
            element
            for element in _elements_inside_rect(layer, rect)
            if _local_name(element.tag) == "BusDis"
        ]
        if candidates:
            candidates.sort(key=lambda element: (_area(_subtree_box(element)), element.get("id") or ""))
            matches.append((rect, candidates[0]))
    return matches


def _is_channel_status(element: ET.Element) -> bool:
    if _local_name(element.tag) != "Status":
        return False
    devref = (element.get("devref") or "").strip().lower().replace("\\", "/")
    return CHANNEL_STATUS_DEVREF_TOKEN in devref


def _point_inside_box(x: float, y: float, box: _Box, tolerance: float = 0.5) -> bool:
    return (
        box.left - tolerance <= x <= box.right + tolerance
        and box.top - tolerance <= y <= box.bottom + tolerance
    )


def _find_channel_status_for_rect(
    layer: ET.Element,
    rect: ET.Element,
    bus: ET.Element,
    claimed: set[int],
) -> ET.Element | None:
    rect_box = _subtree_box(rect)
    bus_box = _subtree_box(bus)
    if rect_box is None:
        return None
    reference_x = bus_box.center_x if bus_box is not None else rect_box.center_x
    reference_y = bus_box.center_y if bus_box is not None else rect_box.center_y
    candidates: list[tuple[int, float, str, ET.Element]] = []
    for element in list(layer):
        if id(element) in claimed or not _is_channel_status(element):
            continue
        box = _subtree_box(element)
        if box is None:
            continue
        inside = _point_inside_box(box.center_x, box.center_y, rect_box)
        near = (
            rect_box.left - 40.0 <= box.center_x <= rect_box.right + 40.0
            and rect_box.top - 40.0 <= box.center_y <= rect_box.bottom + 40.0
        )
        if not inside and not near:
            continue
        distance = math.hypot(box.center_x - reference_x, box.center_y - reference_y)
        candidates.append((0 if inside else 1, distance, element.get("id") or "", element))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return candidates[0][3]


def _channel_status_target(
    rect_box: _Box,
    status_box: _Box,
    position: str,
    margin: float,
) -> tuple[float, float]:
    if position not in CHANNEL_STATUS_POSITIONS:
        raise ValueError(f"不支持的 channel_status 框内位置：{position!r}。")
    if status_box.width > rect_box.width + 1e-6 or status_box.height > rect_box.height + 1e-6:
        raise ValueError("channel_status 状态点尺寸大于环网柜外框，无法放入框内。")

    x_margin = min(max(0.0, margin), max(0.0, rect_box.width - status_box.width))
    y_margin = min(max(0.0, margin), max(0.0, rect_box.height - status_box.height))

    if position.endswith("left"):
        left = rect_box.left + x_margin
    elif position.endswith("right"):
        left = rect_box.right - status_box.width - x_margin
    else:
        left = rect_box.center_x - status_box.width / 2.0

    if position.startswith("top"):
        top = rect_box.top + y_margin
    elif position.startswith("bottom"):
        top = rect_box.bottom - status_box.height - y_margin
    else:
        top = rect_box.center_y - status_box.height / 2.0
    return left, top


def _translate_number(value: str, delta: float) -> str:
    try:
        return _format_number(float(value) + delta)
    except (TypeError, ValueError):
        return value


def _translate_path_xy(value: str, delta_x: float, delta_y: float) -> str:
    return _PATH_COORD_PATTERN.sub(
        lambda match: (
            f"{_translate_number(match.group(1), delta_x)},"
            f"{_translate_number(match.group(2), delta_y)}"
        ),
        value,
    )


def _translate_element_xy(element: ET.Element, delta_x: float, delta_y: float) -> bool:
    if abs(delta_x) <= 1e-9 and abs(delta_y) <= 1e-9:
        return False
    changed = False
    for node in element.iter():
        for attr in _X_POSITION_ATTRS:
            if attr in node.attrib:
                old = node.get(attr, "")
                new = _translate_number(old, delta_x)
                if new != old:
                    node.set(attr, new)
                    changed = True
        for attr in _Y_POSITION_ATTRS:
            if attr in node.attrib:
                old = node.get(attr, "")
                new = _translate_number(old, delta_y)
                if new != old:
                    node.set(attr, new)
                    changed = True
        if "d" in node.attrib:
            old = node.get("d", "")
            new = _translate_path_xy(old, delta_x, delta_y)
            if new != old:
                node.set("d", new)
                changed = True
    return changed


def reposition_channel_statuses(
    layer: ET.Element,
    *,
    position: str = "bottom_left",
    inner_margin: float = 5.0,
) -> tuple[int, int, int, int]:
    """Return (valid_rmu_rects, found, moved, missing)."""
    position_value = str(getattr(position, "value", position))
    if position_value not in CHANNEL_STATUS_POSITIONS:
        raise ValueError(f"不支持的 channel_status 框内位置：{position_value!r}。")
    if inner_margin < 0:
        raise ValueError("channel_status 框内边距不能小于 0。")

    pairs = _rmu_rects_by_busdis(layer)
    claimed: set[int] = set()
    found = 0
    moved = 0
    missing = 0

    for rect, bus in pairs:
        status = _find_channel_status_for_rect(layer, rect, bus, claimed)
        if status is None:
            missing += 1
            continue
        claimed.add(id(status))
        found += 1
        rect_box = _subtree_box(rect)
        status_box = _subtree_box(status)
        if rect_box is None or status_box is None:
            missing += 1
            continue
        target_left, target_top = _channel_status_target(
            rect_box,
            status_box,
            position_value,
            float(inner_margin),
        )
        if _translate_element_xy(
            status,
            target_left - status_box.left,
            target_top - status_box.top,
        ):
            moved += 1
    return len(pairs), found, moved, missing


def _find_layer(root: ET.Element) -> ET.Element:
    direct_layers = [child for child in list(root) if _local_name(child.tag) == "Layer"]
    if len(direct_layers) == 1:
        return direct_layers[0]
    for element in root.iter():
        if _local_name(element.tag) == "Layer":
            return element
    raise ValueError("G 文件缺少 <Layer>。")


def _write_tree_atomic(root: ET.Element, output_path: Path) -> None:
    output_path = Path(output_path)
    temp = output_path.with_name(output_path.name + ".tmp_channel_status")
    ET.ElementTree(root).write(temp, encoding="utf-8", xml_declaration=True)
    ET.parse(temp)
    os.replace(temp, output_path)


def _write_csv(records: list[ChannelStatusFileRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(ChannelStatusFileRecord.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    return path


def _write_html(records: list[ChannelStatusFileRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for record in records:
        row_class = "pass" if record.channel_status_found else "info"
        rows.append(
            "<tr class='%s'><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%s</td><td>%d</td><td>%s</td></tr>"
            % (
                row_class,
                html.escape(record.file_name),
                record.rmu_rect_count,
                record.channel_status_found,
                record.channel_status_moved,
                record.channel_status_missing,
                html.escape(CHANNEL_STATUS_POSITIONS.get(record.target_position, record.target_position)),
                record.inner_margin,
                html.escape(record.status),
            )
        )
    content = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>环网柜 channel_status 移动报告</title>
<style>
body{{font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;margin:24px;background:#f3f7f5;color:#17372e}}
h1{{color:#006b52}} .rule{{background:#eaf8f2;border:1px solid #b8dfd1;padding:12px 14px;margin-bottom:16px;border-radius:8px;line-height:1.7}}
table{{border-collapse:collapse;width:100%;background:white;font-size:12px}}th,td{{border:1px solid #d3e3dc;padding:7px 9px;text-align:left;white-space:nowrap}}th{{background:#006b52;color:white}}.pass{{background:#eaf8f2}}.info{{background:#eaf3ff}}
</style></head><body><h1>环网柜 channel_status 移动报告</h1>
<div class='rule'>处理逻辑复用 G File Studio v2.18.244：只处理有效 RMU 外框附近 devref 包含 channel_status.zt.icn.g:channel_status 的 Status 图元；每个 Status 只归属一个 RMU；只平移该 Status 本身，不移动环网柜、母线、设备、标题或连接线。原始 G 文件不修改，只写 Workspace 安全副本。</div>
<table><thead><tr><th>G文件</th><th>有效RMU</th><th>找到状态点</th><th>实际移动</th><th>未找到</th><th>目标位置</th><th>距边(px)</th><th>状态</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    path.write_text(content, encoding="utf-8")
    return path


def process_rmu_channel_status_reposition(
    files: Iterable[Path],
    output_dir: Path,
    report_dir: Path,
    *,
    position: str = "bottom_left",
    inner_margin: int = 5,
    log=None,
    progress=None,
) -> ChannelStatusRepositionResult:
    position = str(position)
    if position not in CHANNEL_STATUS_POSITIONS:
        raise ValueError(f"不支持的 channel_status 位置：{position!r}")
    if int(inner_margin) < 0:
        raise ValueError("channel_status 距边像素不能小于 0。")

    log = log or (lambda _msg: None)
    files = [Path(path) for path in files]
    if not files:
        raise ValueError("没有可处理的 G 文件。")

    output_dir = Path(output_dir)
    report_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    output_files: list[Path] = []
    records: list[ChannelStatusFileRecord] = []
    total_found = 0
    total_moved = 0
    total_missing = 0

    for index, source in enumerate(files, start=1):
        if progress:
            progress(
                int((index - 1) / max(1, len(files)) * 95),
                f"正在移动 channel_status：{source.name}",
            )
        target = output_dir / source.name
        shutil.copy2(source, target)
        log(f"[安全副本] {source} -> {target}")

        try:
            tree = ET.parse(target)
        except (ET.ParseError, UnicodeError, LookupError) as exc:
            raise ValueError(f"G 文件 XML 解析失败：{source.name}: {exc}") from exc
        root = tree.getroot()
        layer = _find_layer(root)
        rmu_count, found, moved, missing = reposition_channel_statuses(
            layer,
            position=position,
            inner_margin=float(inner_margin),
        )
        _write_tree_atomic(root, target)

        total_found += found
        total_moved += moved
        total_missing += missing
        status = "MOVED" if moved else ("ALREADY_AT_TARGET" if found else "NO_MATCH")
        records.append(
            ChannelStatusFileRecord(
                file_name=target.name,
                rmu_rect_count=rmu_count,
                channel_status_found=found,
                channel_status_moved=moved,
                channel_status_missing=missing,
                target_position=position,
                inner_margin=int(inner_margin),
                status=status,
            )
        )
        output_files.append(target)
        log(
            f"[channel_status] {target.name}: 有效RMU={rmu_count}, 找到={found}, "
            f"移动={moved}, 未找到={missing}, 位置={CHANNEL_STATUS_POSITIONS[position]}, "
            f"距边={int(inner_margin)}px"
        )

    csv_path = _write_csv(records, report_dir / "rmu_channel_status_reposition_report.csv")
    html_path = _write_html(records, report_dir / "rmu_channel_status_reposition_report.html")
    if progress:
        progress(100, "环网柜 channel_status 移动完成")
    return ChannelStatusRepositionResult(
        output_files=output_files,
        records=records,
        csv_path=csv_path,
        html_path=html_path,
        found=total_found,
        moved=total_moved,
        missing=total_missing,
    )
