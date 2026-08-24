#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


class GWriteBackError(RuntimeError):
    pass


class GWriteBackService:
    """Targeted textual G-file write-back.

    Only the opening tag of an explicitly approved (tag + XML id) object is
    modified.  This avoids re-serializing the complete XML document and keeps
    original formatting/order/content unchanged everywhere else.
    """

    def __init__(self, log=None):
        self.log = log or (lambda msg: None)

    def create_backup(self, g_path):
        g_path = Path(g_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = g_path.with_name(f"{g_path.name}.bak_{stamp}")
        shutil.copy2(g_path, backup)
        self.log(f"已创建 G 文件备份：{backup}")
        return backup

    @staticmethod
    def _set_attribute(open_tag: str, key: str, value: str) -> str:
        escaped = str(value).replace("&", "&amp;").replace('"', "&quot;")
        pattern = re.compile(rf'(\s{re.escape(key)}\s*=\s*)(["\'])(.*?)(\2)', re.DOTALL)
        if pattern.search(open_tag):
            return pattern.sub(lambda m: f'{m.group(1)}"{escaped}"', open_tag, count=1)

        # Attribute does not exist: append before '/>' or '>'.
        if open_tag.endswith("/>"):
            return open_tag[:-2] + f' {key}="{escaped}"/>'
        if open_tag.endswith(">"):
            return open_tag[:-1] + f' {key}="{escaped}">'
        raise GWriteBackError(f"无法写入属性 {key}：目标标签格式异常")

    @staticmethod
    def _find_exact_open_tag(text: str, tag: str, xml_id: str):
        """Legacy exact locator retained for compatibility/tests.

        Bulk write-back no longer calls this once per object.  See
        ``_index_target_open_tags`` for the one-pass implementation.
        """
        tag_pattern = re.compile(rf'<{re.escape(tag)}\b[^>]*>', re.DOTALL)
        matches = []
        id_pattern = re.compile(r'\bid\s*=\s*(["\'])(.*?)\1', re.DOTALL)
        for match in tag_pattern.finditer(text):
            id_match = id_pattern.search(match.group(0))
            if id_match and id_match.group(2) == str(xml_id):
                matches.append(match)
        return matches

    @staticmethod
    def _index_target_open_tags(text: str, target_keys):
        """Index all requested (tag, XML id) opening tags in one file scan.

        The previous implementation rescanned the whole G file twice for every
        selected object.  Large RMU drawings can contain thousands of selected
        devices, making write-back effectively O(selected_objects * file_size).
        This index keeps the exact same uniqueness rule while scanning the file
        only once for the requested tag names.
        """
        target_keys = {
            (str(tag), str(xml_id))
            for tag, xml_id in (target_keys or set())
        }
        if not target_keys:
            return {}

        tags = sorted({tag for tag, _ in target_keys}, key=len, reverse=True)
        tag_alternation = "|".join(re.escape(tag) for tag in tags)
        tag_pattern = re.compile(
            rf'<(?P<tag>{tag_alternation})\b[^>]*>',
            re.DOTALL,
        )
        id_pattern = re.compile(r'\bid\s*=\s*(["\'])(.*?)\1', re.DOTALL)

        indexed = {key: [] for key in target_keys}
        for match in tag_pattern.finditer(text):
            opening = match.group(0)
            id_match = id_pattern.search(opening)
            if not id_match:
                continue
            key = (match.group("tag"), id_match.group(2))
            if key in indexed:
                indexed[key].append(match)
        return indexed

    def apply_root_g_attributes(
        self,
        g_path,
        attributes,
        create_backup=True,
    ):
        """Update only the root opening <G ...> tag."""
        g_path = Path(g_path)
        if not g_path.exists():
            raise GWriteBackError(f"G 文件不存在：{g_path}")

        original_bytes = g_path.read_bytes()
        had_bom = original_bytes.startswith(b"\xef\xbb\xbf")
        raw = original_bytes.decode("utf-8-sig")
        match = re.search(r"<G\b[^>]*>", raw, flags=re.DOTALL)
        if match is None:
            raise GWriteBackError("未找到 G 文件根节点 <G ...>。")

        before_tag = match.group(0)
        after_tag = before_tag
        before_attrs = {}
        for key, value in dict(attributes or {}).items():
            attr_re = re.compile(
                rf'\b{re.escape(key)}\s*=\s*(["\'])(.*?)\1',
                re.DOTALL,
            )
            old = attr_re.search(before_tag)
            before_attrs[key] = old.group(2) if old else None
            after_tag = self._set_attribute(after_tag, key, str(value))

        backup = self.create_backup(g_path) if create_backup else None
        updated = raw[:match.start()] + after_tag + raw[match.end():]
        temp_path = g_path.with_name(g_path.name + ".tmp_model_manager")
        try:
            output_bytes = updated.encode("utf-8")
            if had_bom:
                output_bytes = b"\xef\xbb\xbf" + output_bytes
            temp_path.write_bytes(output_bytes)
            temp_path.replace(g_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        return {
            "g_file": str(g_path),
            "backup": str(backup) if backup else "",
            "before": before_attrs,
            "after": {k: str(v) for k, v in dict(attributes or {}).items()},
        }

    def apply_attribute_changes(self, g_path, changes, create_backup=True):
        g_path = Path(g_path)
        if not g_path.exists():
            raise GWriteBackError(f"G 文件不存在：{g_path}")

        original_bytes = g_path.read_bytes()
        had_bom = original_bytes.startswith(b"\xef\xbb\xbf")
        raw = original_bytes.decode("utf-8-sig")

        normalized_changes = []
        for change in changes:
            xml_id = str(change.get("xml_id", "")).strip()
            tag = str(change.get("tag", "")).strip()
            attrs = dict(change.get("attributes", {}))
            normalized_changes.append((tag, xml_id, attrs))

        total = len(normalized_changes)
        target_keys = {(tag, xml_id) for tag, xml_id, _ in normalized_changes}
        self.log(
            f"正在建立 G 文件回写索引：{g_path.name}；"
            f"目标对象数={total}"
        )
        indexed = self._index_target_open_tags(raw, target_keys)

        # Validate every target against the ORIGINAL file before changing
        # anything.  This preserves the original all-or-nothing uniqueness
        # safety rule, but avoids a full-file regex scan per selected object.
        for tag, xml_id, _ in normalized_changes:
            matches = indexed.get((tag, xml_id), [])
            if len(matches) != 1:
                raise GWriteBackError(
                    f"回写目标必须唯一：tag={tag}, XML ID={xml_id}, 匹配数={len(matches)}"
                )

        backup = self.create_backup(g_path) if create_backup else None

        # Keep one mutable opening-tag value per unique target.  If callers
        # provide multiple changes for the same target, apply them in the same
        # sequence as before so the final XML and the per-change audit records
        # remain equivalent to the previous implementation.
        target_state = {}
        for key, matches in indexed.items():
            if len(matches) != 1:
                continue
            match = matches[0]
            target_state[key] = {
                "start": match.start(),
                "end": match.end(),
                "current_tag": match.group(0),
            }

        applied = []
        progress_step = 100 if total >= 500 else 25 if total >= 100 else 10

        for index, (tag, xml_id, attrs) in enumerate(normalized_changes, start=1):
            key = (tag, xml_id)
            state = target_state[key]
            before_tag = state["current_tag"]
            after_tag = before_tag
            before_attrs = {}

            for attr_key, value in attrs.items():
                attr_re = re.compile(
                    rf'\b{re.escape(attr_key)}\s*=\s*(["\'])(.*?)\1',
                    re.DOTALL,
                )
                old = attr_re.search(before_tag)
                before_attrs[attr_key] = old.group(2) if old else None
                after_tag = self._set_attribute(
                    after_tag,
                    attr_key,
                    str(value),
                )

            state["current_tag"] = after_tag
            applied.append({
                "tag": tag,
                "xml_id": xml_id,
                "before": before_attrs,
                "after": {k: str(v) for k, v in attrs.items()},
            })

            if (
                index == 1
                or index == total
                or index % progress_step == 0
            ):
                self.log(
                    f"G 文件回写进度：{index}/{total}；"
                    f"tag={tag}；XML ID={xml_id}"
                )

        # Replace from the end of the file towards the beginning so all
        # original offsets remain valid.  Each unique target is written once.
        replacements = sorted(
            (
                (
                    state["start"],
                    state["end"],
                    state["current_tag"],
                )
                for state in target_state.values()
            ),
            reverse=True,
        )

        updated = raw
        for start, end, replacement in replacements:
            updated = updated[:start] + replacement + updated[end:]

        temp_path = g_path.with_name(g_path.name + ".tmp_model_manager")
        try:
            output_bytes = updated.encode("utf-8")
            if had_bom:
                output_bytes = b"\xef\xbb\xbf" + output_bytes
            temp_path.write_bytes(output_bytes)
            temp_path.replace(g_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        return {
            "g_file": str(g_path),
            "backup": str(backup) if backup else "",
            "applied_count": len(applied),
            "changes": applied,
        }
