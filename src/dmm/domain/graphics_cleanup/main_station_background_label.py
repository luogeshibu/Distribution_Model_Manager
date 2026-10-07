from __future__ import annotations

import csv
import html
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from dmm.domain.gfile.master_station_frames import (
    find_master_station_frames,
    parse_master_feeder_label,
    text_has_background,
)
from dmm.domain.gfile.parser import GObject, ParsedG
from dmm.domain.graphics_cleanup.rmu_annotation_position import _new_makkah_parser


MAIN_STATION_BACKGROUND_LABEL_MAX_DISTANCE = 300.0
BACKGROUND_TEXT_TOLERANCE = 3.0
BACKGROUND_PAIR_MAX_GAP = 24.0
BACKGROUND_HORIZONTAL_PADDING = 12.0
BACKGROUND_VERTICAL_PADDING = 4.0
BACKGROUND_LINE_GAP = 0.0
BACKGROUND_GEOMETRY_TAGS = {"poke", "rect", "rectangle", "roundrect", "roundrectangle"}
TARGET_PAREN_RE = re.compile(r"^\s*[\(（]\s*([^()（）]+?)\s*[\)）]\s*$")
COMBINED_LABEL_RE = re.compile(r"^\s*(.*?)\s*([\(（]\s*([^()（）]+?)\s*[\)）])\s*$")


@dataclass
class MainStationBackgroundLabelResult:
    html_path: Path
    csv_path: Path
    output_files: list[Path]
    candidate_count: int
    updated_count: int
    layout_count: int
    ambiguous_count: int
    skipped_count: int


def _txt(value) -> str:
    return str(value or "").strip()


def _esc(value) -> str:
    return html.escape(_txt(value), quote=True)


def _truthy_attr(value: str) -> bool:
    text = _txt(value).casefold()
    return bool(text and text not in {"0", "false", "none", "null", "transparent"})


def _fill_visible(obj: GObject) -> bool:
    """Recognize a visible background carrier without depending on one RGB.

    Field drawings normally use a filled ``poke`` behind the two Text objects,
    but some exports use Rect/RoundRect-like objects.  v4.1.135 deliberately
    recognizes the *background role* from geometry + fill/style rather than a
    single tag or RGB value so the repair can resize whichever filled carrier
    actually owns the two label lines.
    """
    tag = obj.tag.lower()
    attrs = obj.attrs
    if tag in {"text", "line", "feedline", "connectline", "bus", "busdis"}:
        return False
    if obj.box.w <= 0 or obj.box.h <= 0:
        return False

    styled_fill = any(
        _truthy_attr(attrs.get(key, ""))
        for key in ("fm", "RectStyle", "p_RectStyle", "background", "bg")
    )
    fill = _txt(attrs.get("fcc") or attrs.get("fc"))
    visible_fill = bool(
        fill and fill.casefold() not in {"transparent", "none", "#00000000", "0,0,0,0"}
    )
    visible = _txt(attrs.get("isDisplay", "1")) != "0"

    if tag in BACKGROUND_GEOMETRY_TAGS:
        return visible and (styled_fill or visible_fill)

    # Fallback for site-specific filled geometry tags.  Requiring both a fill
    # style and a visible fill keeps ordinary electrical symbols out.
    return visible and styled_fill and visible_fill


def _inside_background(background: GObject, text: GObject) -> bool:
    return background.box.contains_box(text.box, tolerance=BACKGROUND_TEXT_TOLERANCE) or background.box.center_contains(
        text.box, tolerance=BACKGROUND_TEXT_TOLERANCE
    )


def _target_from_text(value: str) -> str:
    match = TARGET_PAREN_RE.fullmatch(_txt(value))
    return _txt(match.group(1)) if match else ""


def _split_combined(value: str) -> tuple[str, str, str]:
    """Return ``(prefix, target, suffix)`` for ``ABC (1234)``."""
    match = COMBINED_LABEL_RE.fullmatch(_txt(value))
    if not match:
        return "", "", ""
    prefix = _txt(match.group(1))
    target = _txt(match.group(3))
    suffix = _txt(match.group(2))
    if not prefix or not target or not parse_master_feeder_label(prefix):
        return "", "", ""
    return prefix, target, suffix


def find_background_jump_label_groups(parsed: ParsedG) -> list[dict]:
    """Find colored jump-label groups like ``MNA4-12`` + ``(33359)``.

    These are Poke/RMU jump labels, not feeder-title evidence.  The function is
    intentionally independent of main-station matching so the whole-graph
    analyzer can exclude them *before* it decides feeder anchors.
    """
    texts = [obj for obj in parsed.objects if obj.tag.lower() == "text" and _txt(obj.xml_id)]
    backgrounds = [obj for obj in parsed.objects if _fill_visible(obj) and obj.box.w > 0 and obj.box.h > 0]
    groups: list[dict] = []
    consumed: set[str] = set()

    for bg in backgrounds:
        contained = [text for text in texts if _inside_background(bg, text)]
        if not contained:
            continue

        # Combined single-Text form: ``MNA4-12 (33359)``.
        for text in contained:
            prefix, target, suffix = _split_combined(text.attrs.get("ts", ""))
            if not prefix:
                continue
            text_id = _txt(text.xml_id)
            if text_id in consumed:
                continue
            consumed.add(text_id)
            groups.append({
                "background_xml_id": _txt(bg.xml_id),
                "background_tag": bg.tag,
                "label_text_xml_id": text_id,
                "label_text": prefix,
                "target_text_xml_id": text_id,
                "target_text": suffix,
                "target_rmu_name": target,
                "combined_text": True,
                "group_status": "BACKGROUND_JUMP_LABEL",
            })

        target_texts = [(text, _target_from_text(text.attrs.get("ts", ""))) for text in contained]
        target_texts = [(text, target) for text, target in target_texts if target]
        label_texts = []
        for text in contained:
            text_id = _txt(text.xml_id)
            if text_id in consumed or _target_from_text(text.attrs.get("ts", "")):
                continue
            raw = _txt(text.attrs.get("ts"))
            if parse_master_feeder_label(raw):
                label_texts.append(text)

        # Separate two-Text form.  Require exactly one feeder-like label and one
        # parenthesized target in the same colored background.  This avoids
        # treating arbitrary colored annotations as jump labels.
        if len(label_texts) == 1 and len(target_texts) == 1:
            label = label_texts[0]
            target_obj, target = target_texts[0]
            if float(label.box.edge_distance(target_obj.box)) <= BACKGROUND_PAIR_MAX_GAP:
                label_id = _txt(label.xml_id)
                target_id = _txt(target_obj.xml_id)
                if label_id not in consumed and target_id not in consumed:
                    consumed.update({label_id, target_id})
                    groups.append({
                        "background_xml_id": _txt(bg.xml_id),
                        "background_tag": bg.tag,
                        "label_text_xml_id": label_id,
                        "label_text": _txt(label.attrs.get("ts")),
                        "target_text_xml_id": target_id,
                        "target_text": _txt(target_obj.attrs.get("ts")),
                        "target_rmu_name": target,
                        "combined_text": False,
                        "group_status": "BACKGROUND_JUMP_LABEL",
                    })

    # Text objects can carry an explicit background flag without a separate
    # Poke/rect.  Support the combined form and a tightly adjacent parenthesized
    # Text as a fallback.
    by_id = {_txt(obj.xml_id): obj for obj in texts}
    for label in texts:
        label_id = _txt(label.xml_id)
        if label_id in consumed or not text_has_background(label):
            continue
        prefix, target, suffix = _split_combined(label.attrs.get("ts", ""))
        if prefix:
            consumed.add(label_id)
            groups.append({
                "background_xml_id": "",
                "background_tag": "TextBackground",
                "label_text_xml_id": label_id,
                "label_text": prefix,
                "target_text_xml_id": label_id,
                "target_text": suffix,
                "target_rmu_name": target,
                "combined_text": True,
                "group_status": "BACKGROUND_JUMP_LABEL",
            })
            continue
        raw = _txt(label.attrs.get("ts"))
        if not parse_master_feeder_label(raw):
            continue
        candidates = []
        for target_obj in texts:
            target_id = _txt(target_obj.xml_id)
            if target_id == label_id or target_id in consumed:
                continue
            target = _target_from_text(target_obj.attrs.get("ts", ""))
            if not target:
                continue
            distance = float(label.box.edge_distance(target_obj.box))
            if distance <= BACKGROUND_PAIR_MAX_GAP:
                candidates.append((distance, int(target_obj.xml_index), target_obj, target))
        if len(candidates) == 1:
            _, _, target_obj, target = candidates[0]
            target_id = _txt(target_obj.xml_id)
            consumed.update({label_id, target_id})
            groups.append({
                "background_xml_id": "",
                "background_tag": "TextBackground",
                "label_text_xml_id": label_id,
                "label_text": raw,
                "target_text_xml_id": target_id,
                "target_text": _txt(target_obj.attrs.get("ts")),
                "target_rmu_name": target,
                "combined_text": False,
                "group_status": "BACKGROUND_JUMP_LABEL",
            })

    groups.sort(key=lambda row: (
        row.get("background_xml_id", ""),
        row.get("label_text_xml_id", ""),
        row.get("target_text_xml_id", ""),
    ))
    return groups


def background_jump_label_text_ids(parsed: ParsedG) -> set[str]:
    ids: set[str] = set()
    for row in find_background_jump_label_groups(parsed):
        ids.add(_txt(row.get("label_text_xml_id")))
        ids.add(_txt(row.get("target_text_xml_id")))
    return {value for value in ids if value}


def analyze_main_station_background_labels(parsed: ParsedG) -> list[dict]:
    groups = find_background_jump_label_groups(parsed)
    excluded_ids = background_jump_label_text_ids(parsed)
    frames = find_master_station_frames(parsed, excluded_text_ids=excluded_ids)
    by_id = {_txt(obj.xml_id): obj for obj in parsed.objects if _txt(obj.xml_id)}

    sources = []
    for frame in frames:
        if len(frame.breakers) != 1 or not frame.breaker or not _txt(frame.feeder_label):
            continue
        breaker = frame.breaker
        sources.append({
            "breaker": breaker,
            "breaker_xml_id": _txt(breaker.xml_id),
            "feeder_label": _txt(frame.feeder_label),
            "frame_xml_id": _txt(frame.frame.xml_id),
        })

    rows = []
    for group in groups:
        bg = by_id.get(_txt(group.get("background_xml_id")))
        label = by_id.get(_txt(group.get("label_text_xml_id")))
        reference_box = bg.box if bg is not None else (label.box if label is not None else None)
        candidates = []
        if reference_box is not None:
            for source in sources:
                distance = float(reference_box.edge_distance(source["breaker"].box))
                if distance <= MAIN_STATION_BACKGROUND_LABEL_MAX_DISTANCE:
                    candidates.append((distance, int(source["breaker"].xml_index), source))
        candidates.sort(key=lambda item: (item[0], item[1]))

        row = dict(group)
        row.update({
            "source_breaker_xml_id": "",
            "source_frame_xml_id": "",
            "source_feeder_label": "",
            "source_distance": "",
            "new_label_text": "",
            "status": "SKIP_NO_MAIN_STATION_WITHIN_300",
            "reason": "300G 内没有唯一可确认的主网 CBreaker。",
        })
        if len(candidates) == 1:
            distance, _order, source = candidates[0]
            new_label = source["feeder_label"]
            if bool(group.get("combined_text")):
                new_label = f"{new_label} {group['target_text']}"
            row.update({
                "source_breaker_xml_id": source["breaker_xml_id"],
                "source_frame_xml_id": source["frame_xml_id"],
                "source_feeder_label": source["feeder_label"],
                "source_distance": round(distance, 3),
                "new_label_text": new_label,
                "status": "READY" if _txt(group.get("label_text")) != source["feeder_label"] else "UNCHANGED",
                "reason": "背景跳转标签在唯一主网 CBreaker 的 300G 范围内；保留括号目标，仅修正主网名称。",
            })
        elif len(candidates) > 1:
            row.update({
                "source_distance": " | ".join(str(round(item[0], 3)) for item in candidates),
                "status": "AMBIGUOUS_MAIN_STATION",
                "reason": "300G 内存在多个主网 CBreaker，禁止自动猜测。",
            })
        rows.append(row)
    return rows




def _num(value, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float(default)


def _fmt_num(value: float) -> str:
    rounded = round(float(value), 3)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return (f"{rounded:.3f}").rstrip("0").rstrip(".")


def _text_units(value: str) -> float:
    """Cheap, deterministic text-width proxy for G-file labels.

    We intentionally avoid platform font APIs because the tool must render the
    same way on packaged Windows builds.  Existing Text.w remains the primary
    calibration; these units are only used to scale it after the feeder label
    becomes longer/shorter and to provide a conservative font-size floor.
    """
    total = 0.0
    for ch in _txt(value):
        if ch.isspace():
            total += 0.45
        elif ch in "-_.:/()（）":
            total += 0.58
        elif ord(ch) > 127:
            total += 1.0
        elif ch in "MW@#%&":
            total += 1.05
        elif ch in "I1il":
            total += 0.55
        else:
            total += 0.86
    return max(total, 1.0)


def _estimated_text_width(element: ET.Element, old_text: str, new_text: str) -> float:
    current_w = max(1.0, _num(element.get("w"), 1.0))
    old_units = _text_units(old_text)
    new_units = _text_units(new_text)
    scaled = current_w * (new_units / old_units) if old_units > 0 else current_w
    font_size = max(1.0, _num(element.get("p_FontWidth") or element.get("fs") or element.get("p_FontHeight"), 12.0))
    font_floor = font_size * 0.68 * new_units
    # Never shrink the Text box here.  We only enlarge when the replacement
    # needs more room; this avoids breaking existing hand-tuned site layouts.
    return max(current_w, scaled, font_floor)


def _layout_background_label_group(
    root: ET.Element,
    row: dict,
    *,
    old_label_text: str,
) -> dict:
    """Resize the filled carrier and vertically stack/center its label lines.

    The background keeps its original centre so the incoming jump line remains
    visually anchored.  For the common two-Text form the feeder name is the
    first line and ``(RMU)`` is the second line; both are horizontally centered
    and the pair is vertically centered as one block.
    """
    background = _find_xml_element(root, row.get("background_xml_id", ""))
    label = _find_xml_element(root, row.get("label_text_xml_id", ""))
    target = _find_xml_element(root, row.get("target_text_xml_id", ""))
    result = {
        "layout_status": "SKIP_NO_LAYOUT_TARGET",
        "old_background_geometry": "",
        "new_background_geometry": "",
        "label_geometry": "",
        "target_geometry": "",
    }
    if label is None:
        return result

    new_label_text = _txt(label.get("ts"))
    label_w = _estimated_text_width(label, old_label_text or new_label_text, new_label_text)
    label_h = max(1.0, _num(label.get("h"), _num(label.get("p_FontHeight"), 20.0)))
    label.set("w", _fmt_num(label_w))

    combined = bool(row.get("combined_text")) or target is label
    if combined:
        target = None

    target_w = target_h = 0.0
    if target is not None:
        target_text = _txt(target.get("ts"))
        target_w = _estimated_text_width(target, target_text, target_text)
        target_h = max(1.0, _num(target.get("h"), _num(target.get("p_FontHeight"), 20.0)))
        target.set("w", _fmt_num(target_w))

    # TextBackground form has no separate geometry object.  Expanding Text.w is
    # still useful, but there is no carrier to resize/recenter.
    if background is None:
        result["layout_status"] = "TEXT_WIDTH_ONLY"
        result["label_geometry"] = f"x={label.get('x','')},y={label.get('y','')},w={label.get('w','')},h={label.get('h','')}"
        if target is not None:
            result["target_geometry"] = f"x={target.get('x','')},y={target.get('y','')},w={target.get('w','')},h={target.get('h','')}"
        return result

    bg_x = _num(background.get("x"))
    bg_y = _num(background.get("y"))
    bg_w = max(1.0, _num(background.get("w"), 1.0))
    bg_h = max(1.0, _num(background.get("h"), 1.0))
    result["old_background_geometry"] = f"x={_fmt_num(bg_x)},y={_fmt_num(bg_y)},w={_fmt_num(bg_w)},h={_fmt_num(bg_h)}"
    center_x = bg_x + bg_w / 2.0
    center_y = bg_y + bg_h / 2.0

    max_text_w = max(label_w, target_w if target is not None else 0.0)
    content_h = label_h if target is None else label_h + BACKGROUND_LINE_GAP + target_h
    new_bg_w = max(bg_w, max_text_w + 2.0 * BACKGROUND_HORIZONTAL_PADDING)
    new_bg_h = max(bg_h, content_h + 2.0 * BACKGROUND_VERTICAL_PADDING)
    new_bg_x = center_x - new_bg_w / 2.0
    new_bg_y = center_y - new_bg_h / 2.0

    background.set("x", _fmt_num(new_bg_x))
    background.set("y", _fmt_num(new_bg_y))
    background.set("w", _fmt_num(new_bg_w))
    background.set("h", _fmt_num(new_bg_h))

    if target is None:
        label_x = new_bg_x + (new_bg_w - label_w) / 2.0
        label_y = new_bg_y + (new_bg_h - label_h) / 2.0
        label.set("x", _fmt_num(label_x))
        label.set("y", _fmt_num(label_y))
    else:
        content_top = new_bg_y + (new_bg_h - content_h) / 2.0
        label_x = new_bg_x + (new_bg_w - label_w) / 2.0
        target_x = new_bg_x + (new_bg_w - target_w) / 2.0
        label.set("x", _fmt_num(label_x))
        label.set("y", _fmt_num(content_top))
        target.set("x", _fmt_num(target_x))
        target.set("y", _fmt_num(content_top + label_h + BACKGROUND_LINE_GAP))

    result["layout_status"] = "BACKGROUND_RESIZED_AND_CENTERED"
    result["new_background_geometry"] = (
        f"x={background.get('x','')},y={background.get('y','')},w={background.get('w','')},h={background.get('h','')}"
    )
    result["label_geometry"] = f"x={label.get('x','')},y={label.get('y','')},w={label.get('w','')},h={label.get('h','')}"
    if target is not None:
        result["target_geometry"] = f"x={target.get('x','')},y={target.get('y','')},w={target.get('w','')},h={target.get('h','')}"
    return result


def _find_xml_element(root: ET.Element, xml_id: str) -> ET.Element | None:
    wanted = _txt(xml_id)
    for element in root.iter():
        if _txt(element.get("id")) == wanted:
            return element
    return None


def _output_name(path: Path) -> str:
    name = path.name
    suffix = ".sln.pic.g"
    if name.lower().endswith(suffix):
        return name[:-len(suffix)] + ".main-station-label-fixed" + suffix
    if name.lower().endswith(".g"):
        return name[:-2] + ".main-station-label-fixed.g"
    return name + ".main-station-label-fixed.g"


def _write_csv(path: Path, rows: list[dict]):
    fields = [
        "file_name", "background_xml_id", "background_tag", "label_text_xml_id",
        "old_label_text", "target_text_xml_id", "target_text", "target_rmu_name",
        "source_breaker_xml_id", "source_frame_xml_id", "source_feeder_label",
        "source_distance", "new_label_text", "layout_status",
        "old_background_geometry", "new_background_geometry",
        "label_geometry", "target_geometry", "status", "reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows([{field: row.get(field, "") for field in fields} for row in rows])


def _write_html(path: Path, rows: list[dict], output_files: list[Path]):
    body = []
    for row in rows:
        cls = "ok" if row.get("status") in {"UPDATED", "UNCHANGED"} else ("warn" if row.get("status") == "AMBIGUOUS_MAIN_STATION" else "")
        body.append(
            f"<tr class='{cls}'><td>{_esc(row.get('file_name'))}</td>"
            f"<td>{_esc(row.get('background_xml_id'))}</td>"
            f"<td>{_esc(row.get('label_text_xml_id'))}</td>"
            f"<td>{_esc(row.get('old_label_text'))}</td>"
            f"<td>{_esc(row.get('target_text'))}</td>"
            f"<td>{_esc(row.get('target_rmu_name'))}</td>"
            f"<td>{_esc(row.get('source_breaker_xml_id'))}</td>"
            f"<td>{_esc(row.get('source_feeder_label'))}</td>"
            f"<td>{_esc(row.get('source_distance'))}</td>"
            f"<td>{_esc(row.get('new_label_text'))}</td>"
            f"<td>{_esc(row.get('layout_status'))}</td>"
            f"<td>{_esc(row.get('old_background_geometry'))}</td>"
            f"<td>{_esc(row.get('new_background_geometry'))}</td>"
            f"<td>{_esc(row.get('label_geometry'))}</td>"
            f"<td>{_esc(row.get('target_geometry'))}</td>"
            f"<td>{_esc(row.get('status'))}</td><td>{_esc(row.get('reason'))}</td></tr>"
        )
    outputs = "<br>".join(_esc(str(item)) for item in output_files) or "无"
    html_text = f"""<!doctype html><html><head><meta charset='utf-8'><title>主网入口背景标签修正报告</title>
<style>
body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#16332c;background:#f7faf8}}
article{{background:#fff;border:1px solid #dbe8e2;border-radius:12px;padding:20px}}
.note{{padding:12px 14px;border-left:4px solid #0b7b60;background:#edf8f4;margin-bottom:18px;line-height:1.7}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #d9e5df;padding:7px 8px;text-align:left;white-space:nowrap}}th{{background:#eaf5f0;color:#174f42;position:sticky;top:0}}
.ok td{{background:#effaf6}}.warn td{{background:#fff8e8}}
</style></head><body><article><h1>主网入口背景标签修正报告</h1>
<div class='note'>规则：只处理主网 CBreaker 300G 范围内、具有可见背景色且包含“主网样式文字 + (目标环网柜名称)”的跳转标签。括号内容绝不修改；只把括号外主网文字修正为该 CBreaker 已识别的馈线名称。多个主网候选时不自动修改。修正后会按文字实际长度自动扩展背景 Poke/Rect/其它可见填充对象，并把“主网名称”和“(目标RMU)”上下两行作为一个整体居中排版；原始 G 文件不覆盖，只生成安全副本。此类背景跳转标签同时会被“整图馈线拓扑分析”排除，绝不作为馈线锚点。</div>
<p><b>输出 G：</b><br>{outputs}</p>
<div style='overflow:auto'><table><thead><tr><th>文件</th><th>背景XML</th><th>标签Text XML</th><th>原标签</th><th>目标Text</th><th>目标RMU</th><th>主网CBreaker</th><th>主网馈线</th><th>距离</th><th>修正后</th><th>排版处理</th><th>原背景几何</th><th>新背景几何</th><th>主网文字几何</th><th>RMU文字几何</th><th>状态</th><th>说明</th></tr></thead><tbody>{''.join(body) if body else '<tr><td colspan="17">未发现符合规则的背景跳转标签。</td></tr>'}</tbody></table></div>
</article></body></html>"""
    path.write_text(html_text, encoding="utf-8")


def process_main_station_background_label_repair(
    files: Iterable[Path],
    output_dir: Path,
    report_dir: Path,
    *,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> MainStationBackgroundLabelResult:
    files = [Path(path) for path in files]
    output_dir = Path(output_dir)
    report_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    log = log or (lambda _message: None)
    progress = progress or (lambda _percent, _message="": None)

    all_rows: list[dict] = []
    outputs: list[Path] = []
    updated_count = 0
    layout_count = 0
    ambiguous_count = 0
    skipped_count = 0

    total = max(1, len(files))
    for index, source in enumerate(files, start=1):
        progress(int((index - 1) * 85 / total), f"正在分析背景跳转标签：{source.name}")
        parser = _new_makkah_parser()
        parsed = parser.parse(source)
        rows = analyze_main_station_background_labels(parsed)
        tree = ET.parse(source)
        root = tree.getroot()
        changed = False

        for row in rows:
            row = dict(row)
            row["file_name"] = source.name
            row["old_label_text"] = row.get("label_text", "")
            status = row.get("status")
            if status == "READY":
                element = _find_xml_element(root, row.get("label_text_xml_id", ""))
                if element is None:
                    row["status"] = "SKIP_TEXT_XML_NOT_FOUND"
                    row["reason"] = "候选 Text 在 XML 中不存在，未修改。"
                    skipped_count += 1
                else:
                    row["_layout_old_text"] = _txt(element.get("ts"))
                    element.set("ts", _txt(row.get("new_label_text")))
                    row["status"] = "UPDATED"
                    changed = True
                    updated_count += 1
            elif status == "AMBIGUOUS_MAIN_STATION":
                ambiguous_count += 1
            elif status == "UNCHANGED":
                existing = _find_xml_element(root, row.get("label_text_xml_id", ""))
                if existing is not None:
                    row["_layout_old_text"] = _txt(existing.get("ts"))
            else:
                skipped_count += 1

            # v4.1.135: layout is an independent safe repair.  Even an already
            # corrected label (UNCHANGED) may still carry the old narrow Poke
            # geometry, so resize/recenter whenever the candidate is uniquely
            # associated with a main station.
            if row.get("status") in {"UPDATED", "UNCHANGED"}:
                layout = _layout_background_label_group(
                    root, row, old_label_text=_txt(row.get("_layout_old_text") or row.get("old_label_text"))
                )
                row.update(layout)
                if layout.get("layout_status") in {"BACKGROUND_RESIZED_AND_CENTERED", "TEXT_WIDTH_ONLY"}:
                    changed = True
                    layout_count += 1
            all_rows.append(row)

        output_path = output_dir / _output_name(source)
        if changed:
            tree.write(output_path, encoding="utf-8", xml_declaration=True)
        else:
            shutil.copy2(source, output_path)
        outputs.append(output_path)
        log(
            f"[{source.name}] 背景跳转标签={len(rows)}，文字已修正={sum(1 for row in all_rows if row.get('file_name') == source.name and row.get('status') == 'UPDATED')}，背景排版={sum(1 for row in all_rows if row.get('file_name') == source.name and row.get('layout_status') in {'BACKGROUND_RESIZED_AND_CENTERED', 'TEXT_WIDTH_ONLY'})}，输出={output_path.name}"
        )

    csv_path = report_dir / "main_station_background_label_repairs.csv"
    html_path = report_dir / "main_station_background_label_report.html"
    _write_csv(csv_path, all_rows)
    _write_html(html_path, all_rows, outputs)
    progress(100, "主网入口背景标签修正完成")
    return MainStationBackgroundLabelResult(
        html_path=html_path,
        csv_path=csv_path,
        output_files=outputs,
        candidate_count=len(all_rows),
        updated_count=updated_count,
        layout_count=layout_count,
        ambiguous_count=ambiguous_count,
        skipped_count=skipped_count,
    )
