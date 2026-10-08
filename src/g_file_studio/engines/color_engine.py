from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.engines.id_engine import local_name

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LINE_STYLES = {"keep", "solid", "dashed"}


class ColorProcessingError(ValueError):
    """线路与母线样式配置或处理错误。"""


@dataclass(frozen=True)
class ColorRule:
    element_tag: str
    display_name: str
    color: str
    line_style: str = "keep"
    change_color: bool = True


@dataclass
class ColorChangeResult:
    file_path: Path
    changed_by_tag: dict[str, int] = field(default_factory=dict)
    color_changed_by_tag: dict[str, int] = field(default_factory=dict)
    style_changed_by_tag: dict[str, int] = field(default_factory=dict)
    dynamic_color_by_tag: dict[str, int] = field(default_factory=dict)

    @property
    def total_changed(self) -> int:
        return sum(self.changed_by_tag.values())

    @property
    def total_dynamic_color(self) -> int:
        return sum(self.dynamic_color_by_tag.values())

    @property
    def total_style_changed(self) -> int:
        return sum(self.style_changed_by_tag.values())


def normalize_hex_color(value: str) -> str:
    color = value.strip()
    if not color.startswith("#") and len(color) == 6:
        color = "#" + color
    if not _COLOR_RE.fullmatch(color):
        raise ColorProcessingError(f"颜色必须是 #RRGGBB 格式：{value!r}")
    return color.upper()


def normalize_line_style(value: str) -> str:
    style = (value or "keep").strip().lower()
    aliases = {"1": "solid", "2": "dashed", "实线": "solid", "虚线": "dashed", "保持原样": "keep"}
    style = aliases.get(style, style)
    if style not in _LINE_STYLES:
        raise ColorProcessingError(f"不支持的线型：{value!r}")
    return style


def line_style_to_ls(value: str) -> str | None:
    style = normalize_line_style(value)
    if style == "solid":
        return "1"
    if style == "dashed":
        return "2"
    return None


def color_to_rgb_text(value: str) -> str:
    color = normalize_hex_color(value)
    return ",".join(str(int(color[index : index + 2], 16)) for index in (1, 3, 5))


def apply_line_colors(
    tree: ET.ElementTree,
    file_path: Path,
    rules: list[ColorRule],
) -> ColorChangeResult:
    """修改 G 根节点直属 Layer 的线路/母线显示样式。

    - 颜色：仅在 rule.change_color=True 时修改 lc/lcc；
    - 线型：solid -> ls=1，dashed -> ls=2，keep -> 不修改 ls；
    - 不修改 lw、填充色、坐标、ID 或引用。

    函数名保留为 apply_line_colors 以兼容既有调用。
    """
    normalized_rules: dict[str, tuple[ColorRule, str, str | None]] = {}
    for rule in rules:
        color = normalize_hex_color(rule.color)
        ls_value = line_style_to_ls(rule.line_style)
        if not rule.change_color and ls_value is None:
            continue
        normalized_rules[rule.element_tag] = (rule, color, ls_value)

    result = ColorChangeResult(file_path=file_path)
    if not normalized_rules:
        return result

    root = tree.getroot()
    layers = [child for child in list(root) if local_name(child.tag) == "Layer"]
    if not layers:
        raise ColorProcessingError(f"文件 {file_path.name} 的 G 根节点下没有直属 Layer。")

    for layer in layers:
        for element in list(layer):
            tag = local_name(element.tag)
            item = normalized_rules.get(tag)
            if item is None:
                continue
            rule, color, ls_value = item
            touched = False
            if rule.change_color:
                element.set("lcc", color)
                element.set("lc", color_to_rgb_text(color))
                result.color_changed_by_tag[tag] = result.color_changed_by_tag.get(tag, 0) + 1
                touched = True
                dy_flag = (element.get("p_DyColorFlag") or "0").strip()
                if dy_flag not in {"", "0"}:
                    result.dynamic_color_by_tag[tag] = result.dynamic_color_by_tag.get(tag, 0) + 1
            if ls_value is not None:
                element.set("ls", ls_value)
                result.style_changed_by_tag[tag] = result.style_changed_by_tag.get(tag, 0) + 1
                touched = True
            if touched:
                result.changed_by_tag[tag] = result.changed_by_tag.get(tag, 0) + 1

    return result
