from __future__ import annotations

import hashlib
import json
import re
import stat as stat_module
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from g_file_studio.services.remote_g_source import ReadOnlySshClient, RemoteGFile
from g_file_studio.services.paths import app_cache_root
from g_file_studio.services.site_profile_service import SiteProfileService


DEFAULT_REMOTE_SYMBOL_ROOT = "/home/up8000/data/graph/element"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_component(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
    return text or "default"


def _is_g_definition_name(name: str) -> bool:
    """Return True only for a file whose final extension is exactly ``.g``."""
    return PurePosixPath(str(name or "").strip()).suffix == ".g"


def _relative_remote_path(root: str, remote_path: str) -> str:
    """Return a stable POSIX path relative to the configured server root."""
    try:
        return str(PurePosixPath(remote_path).relative_to(PurePosixPath(root)))
    except Exception:
        return PurePosixPath(remote_path).name


def _classification_marker(record: dict[str, object] | None) -> str:
    """Return the operator-owned category marker from a cached server record."""
    if not isinstance(record, dict):
        return ""
    # ``category_marker`` is accepted as a compatibility alias for callers that
    # use the shorter English field name; the persisted/public name is the one
    # matching the UI label: ``classification_marker``.
    return str(
        record.get("classification_marker", record.get("category_marker", "")) or ""
    ).strip()


def _copy_classification_marker(target: dict[str, object], source: dict[str, object] | None) -> None:
    marker = _classification_marker(source)
    if marker:
        _set_classification_marker(target, marker)


def _set_classification_marker(target: dict[str, object], marker: str) -> None:
    value = str(marker or "").strip()
    standard = target.get("standard_record")
    if value:
        target["classification_marker"] = value
        target["category_marker"] = value
        if isinstance(standard, dict):
            standard["classification_marker"] = value
            standard["category_marker"] = value
    else:
        target.pop("classification_marker", None)
        target.pop("category_marker", None)
        if isinstance(standard, dict):
            standard.pop("classification_marker", None)
            standard.pop("category_marker", None)


def _marker_entry(record: dict[str, object], *, root: str = "") -> dict[str, str]:
    standard = record.get("standard_record")
    standard = standard if isinstance(standard, dict) else {}
    remote_path = str(record.get("remote_path", standard.get("remote_path", "")) or "").strip()
    relative_path = str(
        record.get("relative_path", standard.get("relative_path", "")) or ""
    ).strip()
    if not relative_path and root and remote_path:
        relative_path = _relative_remote_path(root, remote_path)
    name = Path(str(record.get("name", standard.get("original_name", "")) or "")).name
    devref = str(record.get("devref", standard.get("devref", "")) or "").strip()
    element_id = str(record.get("element_id", standard.get("element_id", "")) or "").strip()
    return {
        "relative_path": relative_path,
        "file_name": name,
        "devref": devref,
        "element_id": element_id,
        "classification_marker": _classification_marker(record),
    }


def _normalize_marker_entry(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    relative_path = str(raw.get("relative_path", raw.get("path", "")) or "").strip()
    file_name = Path(str(raw.get("file_name", raw.get("name", "")) or "")).name
    devref = str(raw.get("devref", "") or "").strip()
    element_id = str(raw.get("element_id", raw.get("id", "")) or "").strip()
    marker = str(
        raw.get("classification_marker", raw.get("category_marker", raw.get("marker", "")))
        or ""
    ).strip()
    if not relative_path and not file_name and not devref:
        return {}
    return {
        "relative_path": relative_path,
        "file_name": file_name,
        "devref": devref,
        "element_id": element_id,
        "classification_marker": marker,
    }


def _marker_entry_key(entry: dict[str, str]) -> str:
    relative = str(entry.get("relative_path", "")).strip().casefold()
    if relative:
        return f"path:{relative}"
    devref = str(entry.get("devref", "")).strip().casefold()
    name = str(entry.get("file_name", "")).strip().casefold()
    return f"identity:{name}|{devref}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _list_g_files_recursive(client: ReadOnlySshClient, root: str, *, max_files: int = 20000) -> list[RemoteGFile]:
    """Recursively enumerate remote ``*.g`` files without changing the server.

    ``remote_g_source.py`` is part of the protected v2.17.60 business baseline, so
    the symbol-library feature deliberately keeps recursive traversal here instead
    of extending that protected service. Existing/fake clients that expose their
    own recursive helper are supported; otherwise the already-connected SFTP
    channel is used only for ``listdir_attr`` metadata reads. Symlinks are never
    followed.
    """
    recursive = getattr(client, "list_g_files_recursive", None)
    if callable(recursive):
        return [
            item for item in recursive(root, max_files=max_files)
            if isinstance(item, RemoteGFile) and _is_g_definition_name(item.name)
        ][:max_files]

    client.connect()
    sftp = getattr(client, "_sftp", None)
    if sftp is None:
        raise RuntimeError("SSH/SFTP 连接未建立，无法读取服务器图元库。")
    root_text = str(root).strip()
    if not root_text:
        raise ValueError("服务器图元库根目录不能为空。")
    rows: list[RemoteGFile] = []
    pending = [str(PurePosixPath(root_text))]
    while pending:
        current = pending.pop()
        for attr in sftp.listdir_attr(current):
            name = str(attr.filename)
            remote_path = str(PurePosixPath(current) / name)
            mode = int(getattr(attr, "st_mode", 0) or 0)
            if stat_module.S_ISLNK(mode):
                continue
            if stat_module.S_ISDIR(mode):
                pending.append(remote_path)
                continue
            if not _is_g_definition_name(name):
                continue
            rows.append(RemoteGFile(
                name=name,
                remote_path=remote_path,
                size=int(attr.st_size),
                mtime_epoch=int(attr.st_mtime),
            ))
            if len(rows) > int(max_files):
                raise ValueError(f"服务器图元库中的 .g 文件超过安全上限 {max_files}，请缩小根目录。")
    rows.sort(key=lambda item: (item.name.casefold(), item.remote_path.casefold()))
    return rows


@dataclass
class RemoteSymbolLibrarySyncResult:
    host: str
    root: str
    scanned_remote_files: int = 0
    requested_names: list[str] = field(default_factory=list)
    matched_records: dict[str, dict[str, object]] = field(default_factory=dict)
    # One entry per physical remote .g file.  ``matched_records`` intentionally
    # remains basename-keyed for standard binding; this inventory is what the UI
    # uses when it must show duplicate paths, conflicts, and parse failures too.
    server_file_records: list[dict[str, object]] = field(default_factory=list)
    unmatched_names: list[str] = field(default_factory=list)
    conflicts: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)
    downloaded: int = 0
    reused: int = 0
    added_names: list[str] = field(default_factory=list)
    unchanged_names: list[str] = field(default_factory=list)
    changed_names: list[str] = field(default_factory=list)
    # Metadata-only server updates are reported to the operator but do not
    # invalidate the local parsed symbol or its filename-based classification.
    updated_files: list[dict[str, object]] = field(default_factory=list)
    checked_at: str = ""
    cache_root: str = ""

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


class RemoteSymbolLibraryService:
    """Read-only remote symbol-library index + incremental local cache.

    The remote server is never modified. The service recursively lists ``*.g``
    metadata, downloads either requested definitions or the complete catalog,
    parses them locally, and remembers size/mtime/hash metadata in an atomic
    manifest. Duplicate basenames are accepted only when their downloaded content
    hashes are identical.
    """

    def __init__(self, cache_root: str | Path | None = None) -> None:
        base = Path(cache_root) if cache_root is not None else app_cache_root() / "SymbolLibrary"
        self.cache_root = base
        self.standard_service = SiteProfileService()

    @staticmethod
    def _root_token(host: str, root: str) -> str:
        digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]
        return f"{_safe_component(host)}_{digest}"

    def _existing_library_dir(self, host: str, root: str) -> Path:
        """Find an already-saved local cache without creating anything.

        The current deterministic token is checked first.  For compatibility with
        caches written by older GFileStudio builds, existing child directories are
        then inspected by the host/root metadata stored in sync_snapshot.json or
        manifest.json.  This is LOCAL AppData discovery only.
        """
        exact = self.cache_root / self._root_token(host, root)
        if exact.is_dir():
            return exact

        if not self.cache_root.is_dir():
            return exact

        wanted_host = str(host).strip().casefold()
        wanted_root = str(root).strip().rstrip("/").casefold()
        matches: list[tuple[float, Path]] = []

        try:
            children = list(self.cache_root.iterdir())
        except OSError:
            return exact

        for child in children:
            if not child.is_dir():
                continue
            metadata_paths = (child / "sync_snapshot.json", child / "manifest.json")
            matched = False
            newest = 0.0
            for meta in metadata_paths:
                if not meta.is_file():
                    continue
                try:
                    payload = json.loads(meta.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                cached_host = str(payload.get("host", "") or "").strip().casefold()
                cached_root = str(payload.get("root", "") or "").strip().rstrip("/").casefold()
                if cached_host == wanted_host and cached_root == wanted_root:
                    matched = True
                    try:
                        newest = max(newest, meta.stat().st_mtime)
                    except OSError:
                        pass
            if matched:
                matches.append((newest, child))

        if not matches:
            return exact
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def _library_dir(self, host: str, root: str, *, create: bool = False) -> Path:
        target = self.cache_root / self._root_token(host, root)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    def library_dir(self, host: str, root: str = DEFAULT_REMOTE_SYMBOL_ROOT) -> Path:
        """Return the cache directory path without creating it."""
        return self._library_dir(host, root, create=False)

    def _manifest_path(self, host: str, root: str, *, existing: bool = False) -> Path:
        base = self._existing_library_dir(host, root) if existing else self._library_dir(host, root)
        return base / "manifest.json"

    def _sync_snapshot_path(self, host: str, root: str, *, existing: bool = False) -> Path:
        """Return the last complete physical-server-file inventory snapshot."""
        base = self._existing_library_dir(host, root) if existing else self._library_dir(host, root)
        return base / "sync_snapshot.json"

    def _marker_overrides_path(self, host: str, root: str, *, existing: bool = False) -> Path:
        base = self._existing_library_dir(host, root) if existing else self._library_dir(host, root)
        return base / "classification_markers.json"

    def _load_manifest(self, host: str, root: str) -> dict[str, dict[str, object]]:
        path = self._manifest_path(host, root, existing=True)
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        records = payload.get("records", {}) if isinstance(payload, dict) else {}
        return {str(key): dict(value) for key, value in records.items() if isinstance(value, dict)} if isinstance(records, dict) else {}

    def _write_manifest(self, host: str, root: str, records: dict[str, dict[str, object]]) -> None:
        path = self._manifest_path(host, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "host": str(host),
            "root": str(root),
            "updated_at": _utc_now(),
            "records": records,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _write_sync_snapshot(
        self,
        host: str,
        root: str,
        result: RemoteSymbolLibrarySyncResult,
    ) -> None:
        """Persist the complete sync result, including unparseable files.

        ``matched_records`` is intentionally a parseable/standard catalog and can
        therefore be smaller than the physical server inventory.  The UI must be
        able to restore the latter after an application restart, so it is stored
        separately from the metadata manifest.
        """
        payload = result.to_payload()
        payload.update({
            "schema": 1,
            "kind": "GFileStudio remote symbol-library sync snapshot",
            "host": str(host),
            "root": str(root),
            "inventory_complete": True,
            "saved_at": _utc_now(),
        })
        path = self._sync_snapshot_path(host, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def save_cached_sync_snapshot_payload(
        self,
        *,
        host: str,
        root: str,
        payload: dict[str, object],
    ) -> Path:
        """Persist the currently visible local catalog snapshot without network I/O.

        This is used by the explicit "保存到本地" workflow.  It never contacts SSH;
        it only makes the current in-memory/local catalog restartable.
        """
        rows = payload.get("server_file_records", [])
        if not isinstance(rows, list):
            rows = []
        matched = payload.get("matched_records", {})
        if not isinstance(matched, dict):
            matched = {}

        normalized = dict(payload)
        normalized.update({
            "schema": 1,
            "kind": "GFileStudio remote symbol-library sync snapshot",
            "host": str(host),
            "root": str(root),
            "server_file_records": [
                dict(row) for row in rows
                if isinstance(row, dict) and _is_g_definition_name(str(row.get("name", "")))
            ],
            "matched_records": {
                str(name): dict(record)
                for name, record in matched.items()
                if isinstance(record, dict) and _is_g_definition_name(str(name))
            },
            "inventory_complete": bool(payload.get("inventory_complete", True)),
            "saved_at": _utc_now(),
            "cached_restore": True,
        })
        normalized["scanned_remote_files"] = len(normalized["server_file_records"])

        path = self._sync_snapshot_path(host, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load_cached_sync_snapshot(self, *, host: str, root: str) -> dict[str, object]:
        """Load the last complete server inventory without contacting SSH.

        Older caches may not have a snapshot yet.  In that case, synthesize a
        best-effort READY inventory from the metadata manifest; the next explicit
        sync will replace it with the authoritative complete inventory, including
        conflict and parse-error rows.
        """
        path = self._sync_snapshot_path(host, root, existing=True)
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict) and isinstance(payload.get("server_file_records"), list):
                restored = dict(payload)
                restored_records = [
                    dict(row)
                    for row in restored.get("server_file_records", [])
                    if isinstance(row, dict)
                    and _is_g_definition_name(str(row.get("name", "")))
                ]
                # Classification is local operator metadata and is persisted in
                # a separate override file.  Re-apply it when restoring the
                # snapshot; otherwise a restart would show the raw snapshot and
                # make saved markers appear to have disappeared.
                overrides = self._load_marker_overrides(host, root)
                for row in restored_records:
                    # classification_markers.json is the authoritative local marker
                    # layer. Clear any marker embedded in an older snapshot first so
                    # a central admin sync can also remove classifications.
                    _set_classification_marker(row, "")
                    remote_path = str(row.get("remote_path", "")).strip()
                    if not remote_path:
                        continue
                    self._apply_marker_override(
                        row,
                        remote_path=remote_path,
                        root=root,
                        overrides=overrides,
                    )
                restored["server_file_records"] = restored_records
                restored["scanned_remote_files"] = len(restored_records)
                matched = restored.get("matched_records", {})
                if isinstance(matched, dict):
                    restored_matched: dict[str, dict[str, object]] = {}
                    for name, record in matched.items():
                        if not isinstance(record, dict) or not _is_g_definition_name(str(name)):
                            continue
                        standard = dict(record)
                        _set_classification_marker(standard, "")
                        candidates = [
                            row for row in restored_records
                            if str(row.get("name", "")).casefold() == str(name).casefold()
                            and str(row.get("remote_path", "")).strip()
                        ]
                        # v2.18.249: old AppData snapshots can have a perfectly
                        # valid physical READY row (including sha256) while the
                        # nested/matched standard record predates the hash field.
                        # Jeddah's local-cache catalog requires that hash, so enrich
                        # the matched record from the physical inventory instead of
                        # falsely reporting every classified target as missing.
                        if len(candidates) == 1:
                            physical = candidates[0]
                            nested = physical.get("standard_record", {})
                            nested = nested if isinstance(nested, dict) else {}
                            backfill = {
                                "sha256": physical.get("sha256", nested.get("sha256", "")),
                                "original_name": physical.get("name", nested.get("original_name", name)),
                                "cache_path": physical.get("cache_path", nested.get("cache_path", "")),
                                "remote_host": physical.get("remote_host", nested.get("remote_host", host)),
                                "remote_root": physical.get("remote_root", nested.get("remote_root", root)),
                                "remote_path": physical.get("remote_path", nested.get("remote_path", "")),
                                "relative_path": physical.get("relative_path", nested.get("relative_path", "")),
                                "remote_size": physical.get("size", nested.get("remote_size", 0)),
                                "remote_mtime": physical.get("mtime_epoch", nested.get("remote_mtime", 0)),
                            }
                            for field, value in backfill.items():
                                if not str(standard.get(field, "") or "").strip() and value not in (None, ""):
                                    standard[field] = value
                        remote_path = str(standard.get("remote_path", "")).strip()
                        if not remote_path and len(candidates) == 1:
                            remote_path = str(candidates[0].get("remote_path", "")).strip()
                        if remote_path:
                            self._apply_marker_override(
                                standard,
                                remote_path=remote_path,
                                root=root,
                                overrides=overrides,
                            )
                        restored_matched[str(name)] = standard
                    restored["matched_records"] = restored_matched
                return restored

        records = self._load_manifest(host, root)
        inventory: list[dict[str, object]] = []
        matched: dict[str, dict[str, object]] = {}
        for remote_path, record in records.items():
            standard = record.get("standard_record", {})
            standard = dict(standard) if isinstance(standard, dict) else {}
            name = str(record.get("name", standard.get("original_name", ""))).strip()
            if not name or not _is_g_definition_name(name):
                continue
            standard.setdefault("sha256", str(record.get("sha256", "") or "").strip().lower())
            standard.setdefault("remote_path", remote_path)
            standard.setdefault("relative_path", _relative_remote_path(root, remote_path))
            standard.setdefault("original_name", name)
            inventory.append({
                "name": name,
                "remote_path": str(remote_path),
                "relative_path": _relative_remote_path(root, remote_path),
                "remote_host": str(host),
                "remote_root": str(root),
                "size": int(record.get("size", 0) or 0),
                "mtime_epoch": int(record.get("mtime_epoch", 0) or 0),
                "sha256": str(record.get("sha256", "")),
                "cache_path": str(record.get("cache_path", "")),
                "standard_record": standard,
                "classification_marker": _classification_marker(record),
                "category_marker": _classification_marker(record),
                "sync_status": "READY",
            })
            devref = str(standard.get("devref", "")).strip()
            if devref:
                matched[name] = standard
        return {
            "schema": 1,
            "kind": "GFileStudio remote symbol-library sync snapshot",
            "host": str(host),
            "root": str(root),
            "scanned_remote_files": len(inventory),
            "matched_records": matched,
            "server_file_records": inventory,
            "checked_at": "",
            "downloaded": 0,
            "reused": len(inventory),
            "added_names": [],
            "changed_names": [],
            "unchanged_names": [],
            "unmatched_names": [],
            "conflicts": {},
            "errors": {},
            "inventory_complete": False,
            "cached_restore": True,
        }

    def cached_sync_age_seconds(self, *, host: str, root: str) -> float | None:
        """Return the age of the last completed sync without loading its rows.

        Startup only needs this timestamp to decide whether the daily background
        refresh is due.  The full cached inventory remains untouched until the
        operator explicitly opens a sync result or a background refresh completes.
        """
        path = self._sync_snapshot_path(host, root)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw = str(payload.get("checked_at", "") or payload.get("saved_at", "")).strip()
            if not raw:
                return None
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds())
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _load_marker_overrides(self, host: str, root: str) -> list[dict[str, str]]:
        path = self._marker_overrides_path(host, root, existing=True)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        raw_entries = payload.get("markers", []) if isinstance(payload, dict) else []
        if not isinstance(raw_entries, list):
            return []
        entries: dict[str, dict[str, str]] = {}
        for raw in raw_entries:
            entry = _normalize_marker_entry(raw)
            if not entry:
                continue
            entries[_marker_entry_key(entry)] = entry
        return list(entries.values())

    def _write_marker_overrides(
        self,
        host: str,
        root: str,
        entries: list[dict[str, str]],
    ) -> None:
        path = self._marker_overrides_path(host, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 2,
            "kind": "GFileStudio symbol classification markers",
            "updated_at": _utc_now(),
            "source": {"host": str(host), "root": str(root)},
            "markers": sorted(
                [dict(item) for item in entries if str(item.get("classification_marker", "")).strip()],
                key=lambda item: (
                    str(item.get("relative_path", "")).casefold(),
                    str(item.get("file_name", "")).casefold(),
                    str(item.get("devref", "")).casefold(),
                    str(item.get("element_id", "")).casefold(),
                ),
            ),
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _find_marker_override(
        record: dict[str, object],
        remote_path: str,
        root: str,
        overrides: list[dict[str, str]],
    ) -> dict[str, str] | None:
        current = _marker_entry(
            {
                **record,
                "remote_path": remote_path,
                "relative_path": _relative_remote_path(root, remote_path),
            },
            root=root,
        )
        relative = current["relative_path"].casefold()
        exact = [item for item in overrides if item.get("relative_path", "").casefold() == relative and relative]
        if len(exact) == 1:
            return exact[0]

        file_name = current["file_name"].casefold()
        by_name = [item for item in overrides if item.get("file_name", "").casefold() == file_name and file_name]
        if len(by_name) == 1:
            return by_name[0]

        devref = current["devref"].casefold()
        by_devref = [item for item in overrides if item.get("devref", "").casefold() == devref and devref]
        if len(by_devref) == 1:
            return by_devref[0]
        return None

    def _apply_marker_override(
        self,
        record: dict[str, object],
        *,
        remote_path: str,
        root: str,
        overrides: list[dict[str, str]],
    ) -> dict[str, object]:
        override = self._find_marker_override(record, remote_path, root, overrides)
        if override is None:
            return record
        _set_classification_marker(record, override.get("classification_marker", ""))
        return record

    def update_classification_marker(
        self,
        *,
        host: str,
        root: str,
        remote_path: str,
        marker: str,
    ) -> bool:
        """Persist one local category marker without contacting or changing SSH.

        The server is read-only.  Markers belong to the local server-catalog
        manifest and are keyed by the physical relative file path, so duplicate
        basenames remain distinguishable and later programs can reuse the same
        classification.
        """
        remote_key = str(remote_path or "").strip()
        if not remote_key:
            return False
        records = self._load_manifest(host, root)
        record = records.get(remote_key)
        if not isinstance(record, dict):
            # A marker may be entered immediately after restoring an older
            # snapshot, before that path exists in the current manifest.  Keep
            # the marker as a path-based override instead of silently dropping
            # the user's edit.
            record = {
                "name": Path(remote_key).name,
                "remote_path": remote_key,
                "relative_path": _relative_remote_path(root, remote_key),
            }
        value = str(marker or "").strip()
        if value:
            record["classification_marker"] = value
            record["category_marker"] = value
        else:
            record.pop("classification_marker", None)
            record.pop("category_marker", None)
        standard = record.get("standard_record")
        if isinstance(standard, dict):
            if value:
                standard["classification_marker"] = value
                standard["category_marker"] = value
            else:
                standard.pop("classification_marker", None)
                standard.pop("category_marker", None)
        records[remote_key] = record
        self._write_manifest(host, root, records)
        overrides = self._load_marker_overrides(host, root)
        entry = _marker_entry(record, root=root)
        entry["classification_marker"] = value
        key = _marker_entry_key(entry)
        overrides = [item for item in overrides if _marker_entry_key(item) != key]
        if value:
            overrides.append(entry)
        self._write_marker_overrides(host, root, overrides)

        # Keep the restart snapshot aligned as well.  The override file remains
        # authoritative, but updating the snapshot makes the saved value visible
        # even before the next server synchronization.
        snapshot_path = self._sync_snapshot_path(host, root)
        if snapshot_path.is_file():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except Exception:
                snapshot = {}
            if isinstance(snapshot, dict):
                rows = snapshot.get("server_file_records", [])
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict) or str(row.get("remote_path", "")).strip() != remote_key:
                            continue
                        _set_classification_marker(row, value)
                matched = snapshot.get("matched_records", {})
                if isinstance(matched, dict):
                    for standard in matched.values():
                        if not isinstance(standard, dict):
                            continue
                        if str(standard.get("remote_path", "")).strip() == remote_key:
                            _set_classification_marker(standard, value)
                tmp = snapshot_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(snapshot_path)
        return True

    def update_classification_markers_batch(
        self,
        *,
        host: str,
        root: str,
        updates: dict[str, str],
    ) -> int:
        """Persist multiple local classification edits with one set of JSON writes.

        This is intentionally local-only.  It never opens SSH.  The previous single-
        marker API rewrote three JSON files for each edited table cell; callers that
        debounce edits should use this method so the manifest, marker layer and
        restart snapshot are each loaded/written at most once per flush.
        """
        normalized = {
            str(remote_path or "").strip(): str(marker or "").strip()
            for remote_path, marker in dict(updates or {}).items()
            if str(remote_path or "").strip()
        }
        if not normalized:
            return 0

        records = self._load_manifest(host, root)
        overrides = self._load_marker_overrides(host, root)
        override_map = {_marker_entry_key(item): dict(item) for item in overrides}

        snapshot_path = self._sync_snapshot_path(host, root, existing=True)
        snapshot: dict[str, object] = {}
        snapshot_rows: list[dict[str, object]] = []
        snapshot_matched: dict[str, dict[str, object]] = {}
        if snapshot_path.is_file():
            try:
                loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
            except Exception:
                loaded = {}
            if isinstance(loaded, dict):
                snapshot = loaded
                raw_rows = snapshot.get("server_file_records", [])
                if isinstance(raw_rows, list):
                    snapshot_rows = [row for row in raw_rows if isinstance(row, dict)]
                raw_matched = snapshot.get("matched_records", {})
                if isinstance(raw_matched, dict):
                    snapshot_matched = {
                        str(name): record
                        for name, record in raw_matched.items()
                        if isinstance(record, dict)
                    }

        rows_by_path = {
            str(row.get("remote_path", "")).strip(): row
            for row in snapshot_rows
            if str(row.get("remote_path", "")).strip()
        }

        for remote_key, value in normalized.items():
            record = records.get(remote_key)
            if not isinstance(record, dict):
                cached_row = rows_by_path.get(remote_key)
                if isinstance(cached_row, dict):
                    standard = cached_row.get("standard_record", {})
                    record = {
                        "name": str(cached_row.get("name", Path(remote_key).name) or Path(remote_key).name),
                        "remote_path": remote_key,
                        "relative_path": str(cached_row.get("relative_path", _relative_remote_path(root, remote_key)) or _relative_remote_path(root, remote_key)),
                        "size": int(cached_row.get("size", 0) or 0),
                        "mtime_epoch": int(cached_row.get("mtime_epoch", 0) or 0),
                        "sha256": str(cached_row.get("sha256", "") or ""),
                        "cache_path": str(cached_row.get("cache_path", "") or ""),
                        "standard_record": dict(standard) if isinstance(standard, dict) else {},
                    }
                else:
                    record = {
                        "name": Path(remote_key).name,
                        "remote_path": remote_key,
                        "relative_path": _relative_remote_path(root, remote_key),
                    }
            _set_classification_marker(record, value)
            records[remote_key] = record

            entry = _marker_entry(record, root=root)
            entry["classification_marker"] = value
            key = _marker_entry_key(entry)
            override_map.pop(key, None)
            if value:
                override_map[key] = entry

            cached_row = rows_by_path.get(remote_key)
            if isinstance(cached_row, dict):
                _set_classification_marker(cached_row, value)
            for standard in snapshot_matched.values():
                if str(standard.get("remote_path", "")).strip() == remote_key:
                    _set_classification_marker(standard, value)

        self._write_manifest(host, root, records)
        self._write_marker_overrides(host, root, list(override_map.values()))

        if snapshot:
            snapshot["server_file_records"] = snapshot_rows
            snapshot["matched_records"] = snapshot_matched
            tmp = snapshot_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(snapshot_path)
        return len(normalized)

    def load_classification_markers(self, *, host: str, root: str) -> dict[str, str]:
        """Return the effective local classification layer keyed by remote path.

        ``classification_markers.json`` is the authoritative operator cache.
        ``manifest.json`` is only a catalog/metadata cache and may be absent, stale,
        or rebuilt independently.  Merge both sources so a restart never loses
        markers simply because the manifest does not currently carry them.
        """
        records = self._load_manifest(host, root)
        result: dict[str, str] = {
            str(path): _classification_marker(record)
            for path, record in records.items()
            if _classification_marker(record)
        }

        overrides = self._load_marker_overrides(host, root)
        if not overrides:
            return result

        # First resolve each override against the current physical manifest.
        for entry in overrides:
            marker = str(entry.get("classification_marker", "") or "").strip()
            if not marker:
                continue

            target_path = ""
            relative = str(entry.get("relative_path", "") or "").strip().casefold()
            if relative:
                exact = [
                    str(remote_path)
                    for remote_path, record in records.items()
                    if _marker_entry(record, root=root)["relative_path"].casefold() == relative
                ]
                if len(exact) == 1:
                    target_path = exact[0]

            if not target_path:
                file_name = str(entry.get("file_name", "") or "").strip().casefold()
                if file_name:
                    by_name = [
                        str(remote_path)
                        for remote_path, record in records.items()
                        if _marker_entry(record, root=root)["file_name"].casefold() == file_name
                    ]
                    if len(by_name) == 1:
                        target_path = by_name[0]

            if not target_path:
                devref = str(entry.get("devref", "") or "").strip().casefold()
                if devref:
                    by_devref = [
                        str(remote_path)
                        for remote_path, record in records.items()
                        if _marker_entry(record, root=root)["devref"].casefold() == devref
                    ]
                    if len(by_devref) == 1:
                        target_path = by_devref[0]

            # If the manifest is missing/stale, an override with a relative path
            # can still be mapped deterministically to the configured remote root.
            if not target_path:
                raw_relative = str(entry.get("relative_path", "") or "").strip().lstrip("/")
                if raw_relative:
                    target_path = f"{str(root).rstrip('/')}/{raw_relative}"

            if target_path:
                result[target_path] = marker

        return result

    def load_classification_marker_entries(
        self,
        *,
        host: str,
        root: str,
    ) -> list[dict[str, str]]:
        """Return portable marker records for downstream analysis/programs.

        Unlike ``load_classification_markers()``, this also returns markers that
        were imported before their matching server file was synchronized.
        """
        entries: dict[str, dict[str, str]] = {}
        for record in self._load_manifest(host, root).values():
            entry = _marker_entry(record, root=root)
            if entry["classification_marker"]:
                entries[_marker_entry_key(entry)] = entry
        for entry in self._load_marker_overrides(host, root):
            if not entry["classification_marker"]:
                continue
            key = _marker_entry_key(entry)
            # Older local marker caches (schema 1) did not store element_id. Keep
            # the authoritative marker from the override but enrich its portable
            # identity metadata from the manifest so the next JSON export/publish
            # immediately contains element_id without forcing the operator to
            # reclassify all existing rows.
            existing = entries.get(key, {})
            merged = dict(existing)
            for field in ("relative_path", "file_name", "devref", "element_id"):
                value = str(entry.get(field, "") or "").strip()
                if value:
                    merged[field] = value
            merged["classification_marker"] = entry["classification_marker"]
            entries[key] = merged
        return sorted(
            entries.values(),
            key=lambda item: (
                item.get("relative_path", "").casefold(),
                item.get("file_name", "").casefold(),
                item.get("devref", "").casefold(),
            ),
        )

    def build_classification_marker_payload(
        self,
        *,
        host: str,
        root: str,
    ) -> dict[str, object]:
        """Build the portable marker payload without writing a local file."""
        markers = self.load_classification_marker_entries(host=host, root=root)
        return {
            "schema": 2,
            "kind": "GFileStudio symbol classification markers",
            "exported_at": _utc_now(),
            "source": {"host": str(host), "root": str(root)},
            "markers": markers,
        }

    def export_classification_markers(
        self,
        *,
        host: str,
        root: str,
        target_path: str | Path,
    ) -> dict[str, object]:
        """Export local classification markers as a portable JSON configuration."""
        payload = self.build_classification_marker_payload(host=host, root=root)
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": str(path), "count": len(payload.get("markers", []))}

    def import_classification_marker_payload(
        self,
        *,
        host: str,
        root: str,
        payload: object,
    ) -> dict[str, object]:
        """Apply a marker JSON object directly to the local cache."""
        raw_entries = payload.get("markers", []) if isinstance(payload, dict) else []
        if not isinstance(raw_entries, list):
            raise ValueError("分类标记 JSON 缺少 markers 数组。")
        imported: list[dict[str, str]] = []
        for raw in raw_entries:
            entry = _normalize_marker_entry(raw)
            if entry:
                imported.append(entry)
        if not imported:
            raise ValueError("分类标记 JSON 中没有可载入的标记。")

        overrides = self._load_marker_overrides(host, root)
        merged = {_marker_entry_key(item): item for item in overrides}
        for entry in imported:
            key = _marker_entry_key(entry)
            if entry["classification_marker"]:
                merged[key] = entry
            else:
                merged.pop(key, None)

        records = self._load_manifest(host, root)
        matched = 0
        unmatched = 0
        for entry in imported:
            target_path = ""
            exact = [
                remote_path for remote_path, record in records.items()
                if _marker_entry(record, root=root)["relative_path"].casefold()
                == entry["relative_path"].casefold()
                and entry["relative_path"]
            ]
            if len(exact) == 1:
                target_path = exact[0]
            else:
                by_name = [
                    remote_path for remote_path, record in records.items()
                    if _marker_entry(record, root=root)["file_name"].casefold()
                    == entry["file_name"].casefold()
                    and entry["file_name"]
                ]
                if len(by_name) == 1:
                    target_path = by_name[0]
                else:
                    by_devref = [
                        remote_path for remote_path, record in records.items()
                        if _marker_entry(record, root=root)["devref"].casefold()
                        == entry["devref"].casefold()
                        and entry["devref"]
                    ]
                    if len(by_devref) == 1:
                        target_path = by_devref[0]
            if target_path:
                _set_classification_marker(records[target_path], entry["classification_marker"])
                matched += 1
            else:
                unmatched += 1

        self._write_manifest(host, root, records)
        self._write_marker_overrides(host, root, list(merged.values()))
        return {
            "imported": len(imported),
            "matched": matched,
            "pending": unmatched,
        }

    def replace_classification_marker_payload(
        self,
        *,
        host: str,
        root: str,
        payload: object,
    ) -> dict[str, object]:
        """Replace the local classification layer from one authoritative payload.

        This is used only for the central ``symbol_classification.json`` workflow. Entries absent
        from the central file are deliberately removed locally so all workstations
        converge on exactly the same administrator-approved classification set.
        """
        raw_entries = payload.get("markers", []) if isinstance(payload, dict) else []
        if not isinstance(raw_entries, list):
            raise ValueError("中央分类配置缺少 markers 数组。")
        imported: list[dict[str, str]] = []
        for raw in raw_entries:
            entry = _normalize_marker_entry(raw)
            if entry and entry["classification_marker"]:
                imported.append(entry)

        records = self._load_manifest(host, root)
        for record in records.values():
            _set_classification_marker(record, "")

        matched = 0
        unmatched = 0
        for entry in imported:
            target_path = ""
            exact = [
                remote_path for remote_path, record in records.items()
                if _marker_entry(record, root=root)["relative_path"].casefold()
                == entry["relative_path"].casefold()
                and entry["relative_path"]
            ]
            if len(exact) == 1:
                target_path = exact[0]
            else:
                by_name = [
                    remote_path for remote_path, record in records.items()
                    if _marker_entry(record, root=root)["file_name"].casefold()
                    == entry["file_name"].casefold()
                    and entry["file_name"]
                ]
                if len(by_name) == 1:
                    target_path = by_name[0]
                else:
                    by_devref = [
                        remote_path for remote_path, record in records.items()
                        if _marker_entry(record, root=root)["devref"].casefold()
                        == entry["devref"].casefold()
                        and entry["devref"]
                    ]
                    if len(by_devref) == 1:
                        target_path = by_devref[0]
            if target_path:
                _set_classification_marker(records[target_path], entry["classification_marker"])
                matched += 1
            else:
                unmatched += 1

        self._write_manifest(host, root, records)
        # Store the exact central set, not a merge. This makes deletions propagate.
        self._write_marker_overrides(host, root, imported)
        return {
            "imported": len(imported),
            "matched": matched,
            "pending": unmatched,
        }

    def import_classification_markers(
        self,
        *,
        host: str,
        root: str,
        source_path: str | Path,
    ) -> dict[str, object]:
        """Replace local markers with the imported portable JSON.

        Manual import is authoritative just like an explicit central pull: entries
        absent from the imported JSON are removed locally.  This keeps the local
        cache deterministic and matches the UI contract that every manual pull/import
        directly overwrites, rather than silently merging with, the previous cache.
        """
        path = Path(source_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = self.replace_classification_marker_payload(host=host, root=root, payload=payload)
        result["path"] = str(path)
        return result

    @staticmethod
    def _record_unchanged(cached: dict[str, object], remote: RemoteGFile) -> bool:
        local = Path(str(cached.get("cache_path", "")))
        return (
            local.is_file()
            and RemoteSymbolLibraryService._cached_name(cached) == remote.name.casefold()
            and bool(str(cached.get("sha256", "")).strip())
        )

    @staticmethod
    def _cached_name(cached: dict[str, object]) -> str:
        standard = cached.get("standard_record", {})
        if isinstance(standard, dict):
            name = Path(str(standard.get("original_name", "")).strip()).name
            if name:
                return name.casefold()
        name = Path(str(cached.get("name", "")).strip()).name
        if name:
            return name.casefold()
        return Path(str(cached.get("cache_path", "")).strip()).name.casefold()

    @classmethod
    def _find_unchanged_same_name(
        cls,
        previous_manifest: dict[str, dict[str, object]],
        remote: RemoteGFile,
    ) -> dict[str, object]:
        """Reuse a cached file when its basename and remote metadata still match.

        The remote directory layout is not part of the marker identity. A file
        moved between subdirectories, or changed on the server, is still reused
        when its basename remains the same. The operator's classification follows
        the filename; remote content changes are intentionally not relevant here.
        Ambiguous duplicate basenames are reused only when all candidates are the
        same cached bytes.
        """
        candidates = [
            row for row in previous_manifest.values()
            if cls._cached_name(row) == remote.name.casefold()
            and Path(str(row.get("cache_path", ""))).is_file()
            and bool(str(row.get("sha256", "")).strip())
        ]
        if len(candidates) == 1:
            return dict(candidates[0])
        hashes = {str(row.get("sha256", "")).strip().lower() for row in candidates}
        if candidates and len(hashes) == 1:
            return dict(candidates[0])
        return {}

    @staticmethod
    def _relative_parent(root: str, remote_path: str) -> Path:
        try:
            rel = PurePosixPath(remote_path).relative_to(PurePosixPath(root))
            parts = [part for part in rel.parent.parts if part not in {"", ".", ".."}]
            return Path(*[_safe_component(part) for part in parts]) if parts else Path()
        except Exception:
            return Path("external")

    def _download_and_parse(
        self,
        *,
        client: ReadOnlySshClient,
        remote: RemoteGFile,
        host: str,
        root: str,
        library_dir: Path,
        log: Callable[[str], None],
        previous_record: dict[str, object] | None = None,
    ) -> dict[str, object]:
        relative_parent = self._relative_parent(root, remote.remote_path)
        target_dir = library_dir / "files" / relative_parent
        target_dir.mkdir(parents=True, exist_ok=True)
        # Preserve the authoritative basename exactly: parse_icon_definition() uses
        # Path.name to construct the devref file component. Relative directories
        # already keep duplicate basenames isolated.
        target = target_dir / remote.name
        temp = target.with_name(target.name + ".downloading")
        temp.unlink(missing_ok=True)

        before = client.stat_file(remote.remote_path)
        log(f"[服务器图元库] 下载 {before.remote_path} -> {target}")
        client.download_file(before.remote_path, str(temp))
        after = client.stat_file(remote.remote_path)
        if before.size != after.size or before.mtime_epoch != after.mtime_epoch:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"服务器图元下载期间发生变化：{remote.remote_path}，请重试。")
        if not temp.is_file() or temp.stat().st_size != after.size:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"服务器图元下载不完整：{remote.remote_path}")
        temp.replace(target)

        standard = dict(self.standard_service.prepare_standard_file_records([target])[0])
        digest = _sha256(target)
        standard.update({
            "sha256": digest,
            "standard_source": "server",
            "remote_host": str(host),
            "remote_root": str(root),
            "remote_path": str(after.remote_path),
            "relative_path": _relative_remote_path(root, after.remote_path),
            "remote_size": int(after.size),
            "remote_mtime": int(after.mtime_epoch),
            "cache_path": str(target.resolve(strict=False)),
            "original_name": str(after.name),
            "original_source": str(target.resolve(strict=False)),
            "synced_at": _utc_now(),
        })
        result = {
            "name": str(after.name),
            "remote_path": str(after.remote_path),
            "size": int(after.size),
            "mtime_epoch": int(after.mtime_epoch),
            "sha256": digest,
            "cache_path": str(target.resolve(strict=False)),
            "standard_record": standard,
            "synced_at": _utc_now(),
        }
        # Classification is operator metadata, not server content. Keep it when
        # the same file is refreshed or moved, even though its bytes are parsed
        # again.
        _copy_classification_marker(result, previous_record)
        return result

    def sync_expected(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        root: str = DEFAULT_REMOTE_SYMBOL_ROOT,
        expected_names: Iterable[str] | None,
        log: Callable[[str], None] | None = None,
        progress: Callable[[int], None] | None = None,
    ) -> RemoteSymbolLibrarySyncResult:
        log = log or (lambda _msg: None)
        # ``None`` means the complete server catalog.  An explicit empty iterable
        # retains the historical no-op behavior used by callers that only want to
        # resolve a known set of filenames.
        sync_all = expected_names is None
        expected = (
            []
            if sync_all
            else sorted(
                {Path(str(name).strip()).name for name in expected_names if Path(str(name).strip()).name},
                key=str.casefold,
            )
        )
        root = str(root or DEFAULT_REMOTE_SYMBOL_ROOT).strip() or DEFAULT_REMOTE_SYMBOL_ROOT
        result = RemoteSymbolLibrarySyncResult(
            host=str(host).strip(),
            root=root,
            requested_names=expected,
            checked_at=_utc_now(),
            cache_root=str(self._library_dir(host, root, create=True)),
        )
        if progress:
            progress(0)
        if not expected and not sync_all:
            if progress:
                progress(100)
            return result

        library_dir = self._library_dir(host, root, create=True)
        manifest = self._load_manifest(host, root)
        previous_manifest = {path: dict(row) for path, row in manifest.items()}
        marker_overrides = self._load_marker_overrides(host, root)
        with ReadOnlySshClient(host, int(port), username, password) as client:
            remote_files = _list_g_files_recursive(client, root)
            result.scanned_remote_files = len(remote_files)
            if sync_all:
                # Keep one logical work item per basename while the manifest still
                # retains every relative remote path.  Duplicate basenames are
                # resolved below and are reported as conflicts when their bytes
                # differ, so no path is silently discarded.
                expected = sorted({item.name for item in remote_files}, key=str.casefold)
                result.requested_names = list(expected)
            if progress:
                progress(15)
            by_name: dict[str, list[RemoteGFile]] = {}
            remote_paths = {item.remote_path for item in remote_files}
            for item in remote_files:
                by_name.setdefault(item.name.casefold(), []).append(item)

            # Prune records that disappeared from the configured root.
            manifest = {path: row for path, row in manifest.items() if path in remote_paths}
            total = max(1, len(expected))
            for index, expected_name in enumerate(expected, 1):
                matches = sorted(by_name.get(expected_name.casefold(), []), key=lambda item: item.remote_path.casefold())
                if not matches:
                    result.unmatched_names.append(expected_name)
                    if progress:
                        progress(15 + round(index * 80 / total))
                    continue

                candidate_records: list[dict[str, object]] = []
                candidate_errors: list[str] = []
                for remote in matches:
                    cached = manifest.get(remote.remote_path, {})
                    if not cached:
                        cached = self._find_unchanged_same_name(previous_manifest, remote)
                    metadata_updated = bool(
                        cached
                        and (
                            int(cached.get("size", -1) or -1) != int(remote.size)
                            or int(cached.get("mtime_epoch", -1) or -1) != int(remote.mtime_epoch)
                        )
                    )
                    try:
                        if self._record_unchanged(cached, remote):
                            record = dict(cached)
                            result.reused += 1
                            result.unchanged_names.append(expected_name)
                            standard = dict(record.get("standard_record", {})) if isinstance(record.get("standard_record"), dict) else {}
                            # Old manifests without parsed metadata are refreshed once.
                            if not standard:
                                record = self._download_and_parse(
                                    client=client, remote=remote, host=host, root=root, library_dir=library_dir,
                                    log=log, previous_record=cached
                                )
                                result.downloaded += 1
                            else:
                                # Refresh volatile provenance fields while preserving parsed geometry.
                                standard.update({
                                    # Backfill hash into legacy parsed records. The
                                    # outer manifest has always carried the content
                                    # hash even when an old nested standard did not.
                                    "sha256": str(record.get("sha256", "") or "").strip().lower(),
                                    "standard_source": "server",
                                    "remote_host": str(host),
                                    "remote_root": root,
                                    "remote_path": remote.remote_path,
                                    "relative_path": _relative_remote_path(root, remote.remote_path),
                                    "remote_size": int(remote.size),
                                    "remote_mtime": int(remote.mtime_epoch),
                                    "cache_path": str(record.get("cache_path", "")),
                                    "original_name": remote.name,
                                    "original_source": str(record.get("cache_path", "")),
                                    "synced_at": str(record.get("synced_at", "")) or _utc_now(),
                                })
                                record["standard_record"] = standard
                                _copy_classification_marker(record, cached)
                        else:
                            old_hash = str(cached.get("sha256", "")).strip().lower()
                            record = self._download_and_parse(
                                client=client, remote=remote, host=host, root=root, library_dir=library_dir,
                                log=log, previous_record=cached
                            )
                            result.downloaded += 1
                            new_hash = str(record.get("sha256", "")).strip().lower()
                            # mtime/size is only a cache invalidation hint. A standard is
                            # considered changed only when its content hash changed.
                            if old_hash and new_hash and old_hash != new_hash:
                                result.changed_names.append(expected_name)
                            elif not old_hash:
                                result.added_names.append(expected_name)
                        record.update({
                            "name": remote.name,
                            "remote_path": remote.remote_path,
                            "size": int(remote.size),
                            "mtime_epoch": int(remote.mtime_epoch),
                        })
                        record = self._apply_marker_override(
                            record,
                            remote_path=remote.remote_path,
                            root=root,
                            overrides=marker_overrides,
                        )
                        manifest[remote.remote_path] = record
                        candidate_records.append(record)
                        result.server_file_records.append({
                            "name": str(record.get("name", remote.name)),
                            "remote_path": str(remote.remote_path),
                            "relative_path": _relative_remote_path(root, remote.remote_path),
                            "remote_host": str(host),
                            "remote_root": str(root),
                            "size": int(record.get("size", remote.size) or remote.size),
                            "mtime_epoch": int(record.get("mtime_epoch", remote.mtime_epoch) or remote.mtime_epoch),
                            "sha256": str(record.get("sha256", "")),
                            "cache_path": str(record.get("cache_path", "")),
                            "standard_record": dict(record.get("standard_record", {})) if isinstance(record.get("standard_record"), dict) else {},
                            "classification_marker": _classification_marker(record),
                            "category_marker": _classification_marker(record),
                            "sync_status": "READY",
                            "server_updated": metadata_updated,
                        })
                        if metadata_updated:
                            result.updated_files.append({
                                "name": str(remote.name),
                                "remote_path": str(remote.remote_path),
                                "relative_path": _relative_remote_path(root, remote.remote_path),
                                "mtime_epoch": int(remote.mtime_epoch),
                                "previous_mtime_epoch": int(cached.get("mtime_epoch", 0) or 0),
                            })
                    except Exception as exc:
                        message = f"{remote.remote_path}: {exc}"
                        candidate_errors.append(message)
                        result.server_file_records.append({
                            "name": str(remote.name),
                            "remote_path": str(remote.remote_path),
                            "relative_path": _relative_remote_path(root, remote.remote_path),
                            "remote_host": str(host),
                            "remote_root": str(root),
                            "size": int(remote.size),
                            "mtime_epoch": int(remote.mtime_epoch),
                            "sha256": "",
                            "cache_path": "",
                            "standard_record": {},
                            "classification_marker": _classification_marker(cached),
                            "category_marker": _classification_marker(cached),
                            "sync_status": "ERROR",
                            "server_updated": metadata_updated,
                            "error": str(exc),
                        })
                        log(f"[服务器图元库] 解析失败：{message}")

                if candidate_errors:
                    # Do not guess when one of several same-name definitions could
                    # not be verified. The operator can inspect/fallback manually.
                    result.errors[expected_name] = candidate_errors
                    for item in result.server_file_records:
                        if str(item.get("name", "")).casefold() == expected_name.casefold():
                            item["sync_status"] = "ERROR"
                else:
                    hashes = {str(item.get("sha256", "")).strip().lower() for item in candidate_records if str(item.get("sha256", "")).strip()}
                    if len(hashes) > 1:
                        result.conflicts[expected_name] = [
                            {
                                "remote_path": str(item.get("remote_path", "")),
                                "sha256": str(item.get("sha256", "")),
                                "size": int(item.get("size", 0) or 0),
                                "mtime_epoch": int(item.get("mtime_epoch", 0) or 0),
                            }
                            for item in candidate_records
                        ]
                        conflict_paths = {
                            str(item.get("remote_path", ""))
                            for item in candidate_records
                        }
                        for item in result.server_file_records:
                            if str(item.get("remote_path", "")) in conflict_paths:
                                item["sync_status"] = "CONFLICT"
                    elif candidate_records:
                        chosen = candidate_records[0]
                        standard_record = dict(chosen.get("standard_record", {}))
                        if standard_record:
                            result.matched_records[expected_name] = standard_record

                if progress:
                    progress(15 + round(index * 80 / total))

        # Standard version changes are content-based. size/mtime only decide whether
        # a cached file must be re-fetched; touching a file without changing bytes
        # must not manufacture a new locked Profile version.
        result.changed_names = sorted({name for name in result.changed_names if name}, key=str.casefold)
        result.added_names = sorted({name for name in result.added_names if name}, key=str.casefold)
        result.unchanged_names = sorted({name for name in result.unchanged_names if name}, key=str.casefold)
        result.updated_files = sorted(
            result.updated_files,
            key=lambda item: (
                str(item.get("relative_path", "")).casefold(),
                str(item.get("name", "")).casefold(),
            ),
        )
        self._write_manifest(host, root, manifest)
        # Keep the physical-file inventory separately from the parseable catalog.
        # This is what lets the next application start restore 198 server files
        # even when only 187 of them can enter the parsed standard catalog.
        self._write_sync_snapshot(host, root, result)
        if progress:
            progress(100)
        return result

    def sync_all(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        root: str = DEFAULT_REMOTE_SYMBOL_ROOT,
        log: Callable[[str], None] | None = None,
        progress: Callable[[int], None] | None = None,
    ) -> RemoteSymbolLibrarySyncResult:
        """Read and incrementally cache every icon-definition G below ``root``.

        The server remains strictly read-only. PNG previews and non-G files are
        ignored by the recursive indexer; every parseable ``.g`` is downloaded on
        first use and then reused by filename, even when its remote content,
        size, or modification time changes.
        """
        return self.sync_expected(
            host=host,
            port=port,
            username=username,
            password=password,
            root=root,
            expected_names=None,
            log=log,
            progress=progress,
        )
