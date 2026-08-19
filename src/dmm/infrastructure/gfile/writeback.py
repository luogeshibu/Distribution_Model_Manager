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
        # Match only an opening tag and then verify its id attribute exactly.
        tag_pattern = re.compile(rf'<{re.escape(tag)}\b[^>]*>', re.DOTALL)
        matches = []
        id_pattern = re.compile(r'\bid\s*=\s*(["\'])(.*?)\1', re.DOTALL)
        for match in tag_pattern.finditer(text):
            id_match = id_pattern.search(match.group(0))
            if id_match and id_match.group(2) == str(xml_id):
                matches.append(match)
        return matches

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

        # Validate every target against the ORIGINAL file before changing anything.
        validated = []
        for change in changes:
            xml_id = str(change.get("xml_id", "")).strip()
            tag = str(change.get("tag", "")).strip()
            attrs = dict(change.get("attributes", {}))
            matches = self._find_exact_open_tag(raw, tag, xml_id)
            if len(matches) != 1:
                raise GWriteBackError(
                    f"回写目标必须唯一：tag={tag}, XML ID={xml_id}, 匹配数={len(matches)}"
                )
            validated.append((tag, xml_id, attrs))

        backup = self.create_backup(g_path) if create_backup else None
        updated = raw
        applied = []

        # Locate again after each replacement because offsets may move.
        for tag, xml_id, attrs in validated:
            matches = self._find_exact_open_tag(updated, tag, xml_id)
            if len(matches) != 1:
                raise GWriteBackError(
                    f"回写过程中目标失去唯一性：tag={tag}, XML ID={xml_id}"
                )
            match = matches[0]
            before_tag = match.group(0)
            after_tag = before_tag
            before_attrs = {}

            for key, value in attrs.items():
                attr_re = re.compile(rf'\b{re.escape(key)}\s*=\s*(["\'])(.*?)\1', re.DOTALL)
                old = attr_re.search(before_tag)
                before_attrs[key] = old.group(2) if old else None
                after_tag = self._set_attribute(after_tag, key, str(value))

            updated = updated[:match.start()] + after_tag + updated[match.end():]
            applied.append({
                "tag": tag,
                "xml_id": xml_id,
                "before": before_attrs,
                "after": {k: str(v) for k, v in attrs.items()},
            })

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
