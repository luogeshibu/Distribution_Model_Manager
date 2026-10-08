from __future__ import annotations

import os
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from g_file_studio.engines.id_engine import direct_layer_elements, local_name
from g_file_studio.engines.rmu_identification_engine import identify_rmus, parse_name_exclusions


@dataclass
class RmuNameColorResult:
    """Result of changing already-recognized RMU name Text styling."""

    file_path: Path
    identified_rmu_count: int = 0
    named_rmu_count: int = 0
    matched_name_text_count: int = 0
    changed_name_text_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Box:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


def _float(element: ET.Element, name: str, default: float = 0.0) -> float:
    try:
        return float(element.get(name, default))
    except (TypeError, ValueError):
        return default


def _box(element: ET.Element) -> _Box | None:
    width = _float(element, "w")
    height = _float(element, "h")
    if width <= 0 or height <= 0:
        return None
    left = _float(element, "x")
    top = _float(element, "y")
    return _Box(left, top, left + width, top + height)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _direction_score(text_box: _Box, rect_box: _Box, position: str, *, relaxed: bool) -> float | None:
    """Return a deterministic geometry score without changing RMU recognition logic."""

    max_distance = 160.0 if relaxed else 120.0
    edge_tolerance = 80.0 if relaxed else 20.0

    if position == "top":
        gap = rect_box.top - text_box.bottom
        if (
            -edge_tolerance <= gap <= max_distance
            and text_box.center_y < rect_box.top
            and rect_box.left - edge_tolerance <= text_box.center_x <= rect_box.right + edge_tolerance
        ):
            return max(0.0, gap) + abs(text_box.center_x - rect_box.center_x) * 0.08
    elif position == "bottom":
        gap = text_box.top - rect_box.bottom
        if (
            -edge_tolerance <= gap <= max_distance
            and text_box.center_y > rect_box.bottom
            and rect_box.left - edge_tolerance <= text_box.center_x <= rect_box.right + edge_tolerance
        ):
            return max(0.0, gap) + abs(text_box.center_x - rect_box.center_x) * 0.08
    elif position == "left":
        gap = rect_box.left - text_box.right
        if (
            -edge_tolerance <= gap <= max_distance
            and text_box.center_x < rect_box.left
            and rect_box.top - edge_tolerance <= text_box.center_y <= rect_box.bottom + edge_tolerance
        ):
            return max(0.0, gap) + abs(text_box.center_y - rect_box.center_y) * 0.08
    elif position == "right":
        gap = text_box.left - rect_box.right
        if (
            -edge_tolerance <= gap <= max_distance
            and text_box.center_x > rect_box.right
            and rect_box.top - edge_tolerance <= text_box.center_y <= rect_box.bottom + edge_tolerance
        ):
            return max(0.0, gap) + abs(text_box.center_y - rect_box.center_y) * 0.08
    return None


def _find_exact_name_text(
    texts: list[ET.Element],
    *,
    name: str,
    rect_box: _Box,
    preferred_position: str,
    allowed_positions: tuple[str, ...],
    used_text_keys: set[str],
) -> ET.Element | None:
    target = _normalize(name)
    if not target:
        return None

    if preferred_position in {"top", "bottom", "left", "right"}:
        positions = (preferred_position,)
    else:
        positions = allowed_positions

    candidates: list[tuple[float, str, ET.Element]] = []
    for text in texts:
        if _normalize(text.get("ts") or "") != target:
            continue
        # Match the same concrete Text-object ownership rule as identification;
        # equal rendered values and duplicate/missing XML ids remain independent.
        text_key = f"__text_object_{id(text)}"
        if text_key in used_text_keys:
            continue
        text_box = _box(text)
        if text_box is None:
            continue

        best: float | None = None
        for relaxed in (False, True):
            for order, position in enumerate(positions):
                score = _direction_score(text_box, rect_box, position, relaxed=relaxed)
                if score is None:
                    continue
                score += order * 0.0001 + (1000.0 if relaxed else 0.0)
                if best is None or score < best:
                    best = score
            if best is not None and not relaxed:
                break
        if best is not None:
            candidates.append((best, text_key, text))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    _score, text_key, chosen = candidates[0]
    used_text_keys.add(text_key)
    return chosen


def _set_text_white(element: ET.Element) -> bool:
    desired = {
        "lc": "255,255,255",
        "lcc": "#ffffff",
        "fc": "255,255,255",
        "fcc": "#ffffff",
    }
    changed = False
    for key, value in desired.items():
        if (element.get(key) or "").lower() != value.lower():
            element.set(key, value)
            changed = True
    return changed


def apply_rmu_name_white_to_tree(
    tree: ET.ElementTree,
    file_path: Path,
    *,
    name_positions: tuple[str, ...],
    name_exclusions: str = "",
    name_resolution_mode: str = "selected_direction",
) -> RmuNameColorResult:
    """Set only the Text selected as an RMU name to white in the supplied tree.

    Cabinet/name/type recognition remains delegated to the existing identify_rmus()
    implementation.  This function is a presentation-only action over that result.
    """

    file_path = Path(file_path)
    identification = identify_rmus(
        tree,
        file_path,
        name_positions=name_positions,
        smart_in_type=True,
        excluded_name_values=parse_name_exclusions(name_exclusions),
        name_resolution_mode=name_resolution_mode,
    )
    result = RmuNameColorResult(
        file_path=file_path,
        identified_rmu_count=identification.cabinet_count,
        named_rmu_count=identification.named_count,
    )

    elements = direct_layer_elements(tree.getroot())
    texts = [element for element in elements if local_name(element.tag) == "Text"]
    used_text_keys: set[str] = set()
    # The shared RMU recognizer accepts names only above the validated frame.
    effective_positions = ("top",)

    for item in identification.items:
        if not item.name:
            continue
        rect_box = _Box(
            item.rect_x,
            item.rect_y,
            item.rect_x + item.rect_w,
            item.rect_y + item.rect_h,
        )
        text = _find_exact_name_text(
            texts,
            name=item.name,
            rect_box=rect_box,
            preferred_position=item.name_position,
            allowed_positions=effective_positions,
            used_text_keys=used_text_keys,
        )
        if text is None:
            result.warnings.append(
                f"{file_path.name}: RMU {item.name} 已识别，但未定位到可安全改色的同名 Text。"
            )
            continue
        result.matched_name_text_count += 1
        if _set_text_white(text):
            result.changed_name_text_count += 1

    return result


def apply_rmu_name_white(
    source_path: Path,
    output_path: Path,
    *,
    name_positions: tuple[str, ...],
    name_exclusions: str = "",
    name_resolution_mode: str = "selected_direction",
) -> RmuNameColorResult:
    """File wrapper for apply_rmu_name_white_to_tree()."""

    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tree = ET.parse(source_path)
    result = apply_rmu_name_white_to_tree(
        tree,
        source_path,
        name_positions=name_positions,
        name_exclusions=name_exclusions,
        name_resolution_mode=name_resolution_mode,
    )

    if result.changed_name_text_count:
        if hasattr(ET, "indent"):
            ET.indent(tree, space="    ")
        tmp = output_path.with_name(output_path.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        ET.parse(tmp)
        os.replace(tmp, output_path)
    else:
        shutil.copy2(source_path, output_path)
    return result
