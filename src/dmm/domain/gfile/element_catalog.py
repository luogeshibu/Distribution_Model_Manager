from __future__ import annotations

import re
import hashlib
import xml.etree.ElementTree as ET
from pathlib import PurePosixPath


def normalize_element_key(value: str) -> str:
    """Normalize a devref/file key without changing its semantic name."""
    text = str(value or "").strip().replace("\\", "/")
    text = text.lstrip("#")
    return re.sub(r"/+", "/", text).casefold()


def element_key_candidates(devref: str) -> tuple[str, ...]:
    """Return exact keys that can identify one element definition.

    Drawing instances commonly use ``#file.g:ROOT_ID`` while the element
    catalog may store a relative file path, just the file name, or the root
    element id.  Matching remains exact against these normalized candidates;
    no fuzzy substring match is used.
    """
    raw = normalize_element_key(devref)
    if not raw:
        return ()
    candidates = [raw]
    file_part, separator, root_id = raw.rpartition(":")
    if separator and file_part and root_id:
        candidates.extend((file_part, PurePosixPath(file_part).name, root_id))
    else:
        candidates.append(PurePosixPath(raw).name)
    return tuple(dict.fromkeys(item for item in candidates if item))


def _record_keys(record: dict) -> tuple[str, ...]:
    values = [
        record.get("element_key"),
        record.get("file_key"),
        record.get("file_name"),
        record.get("root_id"),
    ]
    keys = []
    for value in values:
        normalized = normalize_element_key(value)
        if normalized:
            keys.append(normalized)
            # Remote element files may be grouped in folders while devref
            # usually carries only the file name.  Keep both exact forms.
            basename = PurePosixPath(normalized).name
            if basename:
                keys.append(basename)
    return tuple(dict.fromkeys(keys))


def resolve_element_record(devref: str, catalog) -> dict | None:
    """Resolve a devref through the user-maintained element catalog."""
    if not isinstance(catalog, dict):
        return None
    records = catalog.get("records", [])
    if not isinstance(records, list):
        return None
    candidates = set(element_key_candidates(devref))
    if not candidates:
        return None
    for record in records:
        if not isinstance(record, dict):
            continue
        if candidates.intersection(_record_keys(record)):
            return dict(record)
    return None


def normalized_classification(record: dict | None) -> str:
    if not isinstance(record, dict):
        return ""
    value = record.get("classification") or record.get("category") or ""
    return re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")


def classification_is(record: dict | None, *keywords: str) -> bool:
    classification = normalized_classification(record)
    if not classification:
        return False
    return any(
        re.search(rf"(?:^|_){re.escape(str(keyword).upper())}(?:_|$)", classification)
        for keyword in keywords
    )


def name_format_penalty(text: str, preference: str) -> int:
    """Return 0 for a name that satisfies the configured format."""
    value = re.sub(r"\s+", " ", str(text or "").strip())
    choice = str(preference or "").strip().upper()
    aliases = {
        "自动": "AUTO",
        "不限": "AUTO",
        "数字": "NUMERIC",
        "纯数字": "NUMERIC",
        "字母数字": "ALPHANUMERIC",
        "字母数字空格": "ALPHANUMERIC_SPACE",
    }
    choice = aliases.get(choice, choice)
    if not choice or choice == "AUTO":
        return 0
    if choice == "NUMERIC":
        matched = bool(re.fullmatch(r"\d+", value))
    elif choice == "ALPHANUMERIC":
        matched = bool(re.fullmatch(r"[A-Za-z0-9_.\-/]+", value))
    elif choice == "ALPHANUMERIC_SPACE":
        matched = bool(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*(?:\s+[A-Za-z0-9][A-Za-z0-9_.\-/]*)*", value)
        ) and not bool(re.fullmatch(r"\d+", value))
    elif choice.startswith("REGEX:"):
        try:
            matched = bool(re.fullmatch(choice[6:], value))
        except re.error:
            matched = True
    else:
        # Unknown/custom values remain informational rather than becoming a
        # hidden hard filter.
        matched = True
    return 0 if matched else 1


def color_preference_penalty(color: str, preference) -> int:
    """Return 0 when a Text color satisfies the configured color filter."""
    raw = re.sub(r"\s+", "", str(color or "")).upper()
    if isinstance(preference, (list, tuple, set)):
        choices = [re.sub(r"\s+", "", str(item or "")).upper() for item in preference]
    else:
        choices = [re.sub(r"\s+", "", str(preference or "")).upper()]
    aliases = {
        "自动": "AUTO",
        "不限": "AUTO",
        "无偏好": "AUTO",
        "白色": "WHITE",
        "绿色": "GREEN",
        "黄色": "YELLOW",
        "橙色": "ORANGE",
        "红色": "RED",
        "蓝色": "BLUE",
    }
    choices = [aliases.get(choice, choice) for choice in choices]
    choices = [choice for choice in choices if choice and choice not in {"AUTO", "NONE"}]
    if not choices:
        return 0
    color_aliases = {
        "0,255,0": "GREEN",
        "0,255,0,255": "GREEN",
        "#00FF00": "GREEN",
        "#00FF00FF": "GREEN",
        "255,255,255": "WHITE",
        "#FFFFFF": "WHITE",
        "#FFFFFFFF": "WHITE",
        "255,255,0": "YELLOW",
        "255,170,0": "ORANGE",
        "255,0,0": "RED",
        "0,0,255": "BLUE",
    }
    # G-file Text defaults to white when no explicit color is present.
    actual = color_aliases.get(raw, raw or "WHITE")
    if "OTHER" in choices:
        non_white = bool(raw) and actual not in {"WHITE", "#FFFFFF", "#FFFFFFFF"}
        if non_white:
            return 0
    expected = {color_aliases.get(choice, choice) for choice in choices}
    return 0 if actual in expected else 1


def _xml_local_name(tag: str) -> str:
    """Return an XML tag without a namespace prefix."""
    value = str(tag or "")
    if "}" in value:
        value = value.rsplit("}", 1)[-1]
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    return value


def parse_element_definition(
    content: bytes | str,
    file_name: str = "",
) -> dict:
    """Extract the stable metadata used by the element management page.

    Element definition files are XML-shaped ``.g`` files.  The repository
    contains GBK and UTF-8 files, so the parser first lets ElementTree inspect
    the original bytes and only falls back to common text encodings when the
    source was supplied as a string.
    """
    raw_content = content.encode("utf-8") if isinstance(content, str) else content
    root = None
    parse_error = None
    if isinstance(raw_content, bytes):
        try:
            root = ET.fromstring(raw_content)
        except (ET.ParseError, ValueError, LookupError, UnicodeDecodeError) as exc:
            parse_error = exc
            # Some legacy element files declare a multibyte encoding that
            # ElementTree cannot decode directly.  Decode it explicitly and
            # remove the XML declaration before parsing the Unicode string.
            for encoding in ("utf-8", "gb18030", "gbk", "big5", "cp1252"):
                try:
                    text = raw_content.decode(encoding)
                except UnicodeDecodeError:
                    continue
                text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)
                try:
                    root = ET.fromstring(text)
                    break
                except (ET.ParseError, ValueError, LookupError) as exc:
                    parse_error = exc
    else:
        root = ET.fromstring(str(content or ""))
    if root is None:
        raise parse_error or ValueError("图元 XML 内容为空或格式无效。")

    children = list(root)
    main = next(
        (
            child
            for child in children
            if _xml_local_name(child.tag).casefold() not in {"comment", "layer"}
        ),
        root,
    )
    attrs = dict(main.attrib)
    target_xml = _xml_local_name(main.tag)
    root_id = str(attrs.get("id", "")).strip()
    file_name = str(file_name or "").replace("\\", "/").strip()
    file_base = PurePosixPath(file_name).name
    element_key = f"{file_base}:{root_id}" if root_id else file_base

    pins = []
    for node in main.iter():
        if _xml_local_name(node.tag).casefold() != "pin":
            continue
        pin_attrs = node.attrib
        index = str(pin_attrs.get("index", "")).strip()
        cx = str(pin_attrs.get("cx", "")).strip()
        cy = str(pin_attrs.get("cy", "")).strip()
        if index or cx or cy:
            pins.append(f"{index}:({cx},{cy})")

    return {
        "element_key": element_key,
        "file_key": file_name,
        "file_name": file_base,
        "target_xml": target_xml,
        "root_id": root_id,
        "width": str(attrs.get("w", "")).strip(),
        "height": str(attrs.get("h", "")).strip(),
        "align_center": str(attrs.get("AlignCenter", "")).strip(),
        "pins": "; ".join(pins),
        "definition_hash": hashlib.sha256(raw_content or b"").hexdigest(),
        "classification": "",
        "device_alias": "",
        "device_code": "",
        "remark": "",
        "status": "已读取",
    }
