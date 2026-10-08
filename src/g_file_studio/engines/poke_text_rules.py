from __future__ import annotations

import re
import xml.etree.ElementTree as ET


def text_instance_key(element: ET.Element) -> str:
    """Return a stable-in-file ownership key for one concrete Text element.

    G drawings normally provide an XML id for every Text.  Use that id when
    available so ownership also survives a save/reload cycle.  Object identity
    is only a same-run fallback for malformed/legacy Text without an id.
    """
    text_id = (element.get("id") or "").strip()
    if text_id:
        return f"id:{text_id}"
    return f"object:{id(element)}"


def text_id_key(text_id: object) -> str:
    value = str(text_id or "").strip()
    return f"id:{value}" if value else ""


def metadata_text_keys(root: ET.Element, *attribute_names: str) -> set[str]:
    """Collect persisted Text ownership keys from GFS-generated Pokes."""
    result: set[str] = set()
    names = tuple(name for name in attribute_names if name)
    if not names:
        return result
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].casefold() != "poke":
            continue
        for name in names:
            key = text_id_key(element.get(name) or "")
            if key:
                result.add(key)
    return result


def is_red_text(element: ET.Element) -> bool:
    """Return whether the visible Text line/font color is red.

    Device-name recognition uses lc/lcc.  Fill/background attributes are not
    treated as the font/line color because a valid device name can sit on a
    separately colored background.
    """
    lcc = (element.get("lcc") or "").strip().lower()
    lc = re.sub(r"\s+", "", (element.get("lc") or "").strip()).lower()
    return lcc in {"#ff0000", "#f00"} or lc == "255,0,0"
