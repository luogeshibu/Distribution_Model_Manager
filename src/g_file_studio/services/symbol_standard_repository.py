from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

from g_file_studio.services.paths import app_data_root


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_component(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
    return text or "default"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(value: str, *, fallback_name: str = "symbol.g") -> str:
    """Return a traversal-safe POSIX relative path.

    Server-backed standards keep the path relative to `/element`.  Older/manual
    records that never had remote provenance are placed under `_manual/` so an
    exported historical version is still complete and deterministic.
    """
    raw = str(value or "").replace("\\", "/").strip()
    parts: list[str] = []
    for part in PurePosixPath(raw).parts:
        if part in {"", ".", "/"}:
            continue
        if part == "..":
            continue
        parts.append(part)
    if parts:
        return str(PurePosixPath(*parts))
    return str(PurePosixPath("_manual") / Path(fallback_name or "symbol.g").name)


def relative_path_from_record(record: dict[str, object]) -> str:
    # Remote provenance is authoritative for the element tree.  A record may have
    # first been parsed as a local cache file (temporarily `_manual/...`) and only
    # then decorated with remote_root/remote_path, so prefer remote provenance.
    remote_root = str(record.get("remote_root", "")).strip()
    remote_path = str(record.get("remote_path", "")).strip()
    if remote_root and remote_path:
        try:
            rel = PurePosixPath(remote_path).relative_to(PurePosixPath(remote_root))
            return _safe_relative_path(str(rel), fallback_name=str(record.get("original_name", "symbol.g")))
        except Exception:
            pass
    existing = str(record.get("relative_path", "")).strip()
    if existing:
        return _safe_relative_path(existing, fallback_name=str(record.get("original_name", "symbol.g")))
    return _safe_relative_path("", fallback_name=str(record.get("original_name", "symbol.g")))


@dataclass
class RepositoryIntegrityResult:
    ok: bool
    profile_name: str
    version: int
    total: int = 0
    verified: int = 0
    missing: list[str] = field(default_factory=list)
    hash_mismatch: list[str] = field(default_factory=list)
    metadata_mismatch: list[str] = field(default_factory=list)
    manifest_path: str = ""
    repository_fingerprint: str = ""


class SymbolStandardRepository:
    """Immutable, Git-style local repository for authoritative symbol G revisions.

    * `objects/<sha-prefix>/<sha>.g` contains immutable content-addressed blobs.
    * `manifests/<profile>/Vn.json` is the immutable version tree/commit manifest.
    * exports are reconstructed solely from the local blobs and never consult the
      remote server, so a historical version survives upstream overwrite/deletion.
    """

    MANIFEST_VERSION = 1

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else app_data_root() / "SymbolRepository"
        self.objects_root = self.root / "objects"
        self.manifests_root = self.root / "manifests"
        self.deleted_manifests_root = self.root / "deleted_manifests"
        self.exports_root = self.root / "exports"
        # Read-only construction must not manufacture a repository tree.  Writer
        # methods create only the directories they actually need.

    def object_path(self, sha256: str) -> Path:
        digest = str(sha256 or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"无效的 SHA256：{sha256}")
        return self.objects_root / digest[:2] / f"{digest}.g"

    def manifest_path(self, profile_name: str, version: int) -> Path:
        return self.manifests_root / _safe_component(profile_name) / f"V{int(version)}.json"

    @staticmethod
    def _entry_payload(record: dict[str, object]) -> dict[str, object]:
        return {
            "devref": str(record.get("devref", "")).strip(),
            "sha256": str(record.get("sha256", "")).strip().lower(),
            "relative_path": relative_path_from_record(record),
            "original_name": str(record.get("original_name", "")).strip(),
            "element_tag": str(record.get("element_tag", "")).strip(),
            "element_id": str(record.get("element_id", "")).strip(),
            "width": float(record.get("width", 0.0) or 0.0),
            "height": float(record.get("height", 0.0) or 0.0),
            "align_center": list(record.get("align_center", [])) if isinstance(record.get("align_center", []), list) else [],
            "pins": list(record.get("pins", [])) if isinstance(record.get("pins", []), list) else [],
            "pin_ids": [str(item) for item in record.get("pin_ids", [])] if isinstance(record.get("pin_ids", []), list) else [],
            "pin_indices": [str(item) for item in record.get("pin_indices", [])] if isinstance(record.get("pin_indices", []), list) else [],
            "standard_source": str(record.get("standard_source", "manual") or "manual").strip().lower(),
            "remote_host": str(record.get("remote_host", "")).strip(),
            "remote_root": str(record.get("remote_root", "")).strip(),
            "remote_path": str(record.get("remote_path", "")).strip(),
            "remote_size": int(record.get("remote_size", 0) or 0),
            "remote_mtime": int(record.get("remote_mtime", 0) or 0),
            "synced_at": str(record.get("synced_at", "")).strip(),
        }

    @staticmethod
    def _fingerprint(entries: Iterable[dict[str, object]]) -> str:
        rows = sorted(
            [dict(row) for row in entries],
            key=lambda row: (
                str(row.get("relative_path", "")).casefold(),
                str(row.get("devref", "")).casefold(),
                str(row.get("sha256", "")),
            ),
        )
        raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest() if rows else ""

    def _source_for_record(self, record: dict[str, object]) -> Path | None:
        expected = str(record.get("sha256", "")).strip().lower()
        candidates = [
            str(record.get("managed_path", "")).strip(),
            str(record.get("original_source", "")).strip(),
            str(record.get("cache_path", "")).strip(),
        ]
        for text in candidates:
            if not text:
                continue
            path = Path(text)
            try:
                if path.is_file() and _sha256(path) == expected:
                    return path
            except OSError:
                continue
        try:
            blob = self.object_path(expected)
        except ValueError:
            return None
        if blob.is_file():
            try:
                if _sha256(blob) == expected:
                    return blob
            except OSError:
                return None
        return None

    def store_blob(self, source: Path, sha256: str) -> Path:
        expected = str(sha256 or "").strip().lower()
        if _sha256(source) != expected:
            raise ValueError(f"图元文件 SHA256 与记录不一致：{source.name}")
        target = self.object_path(expected)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            if _sha256(target) != expected:
                raise ValueError(f"本地图元对象仓库损坏：{target}")
            return target
        temp = target.with_suffix(".g.tmp")
        temp.unlink(missing_ok=True)
        shutil.copy2(source, temp)
        if _sha256(temp) != expected:
            temp.unlink(missing_ok=True)
            raise ValueError(f"冻结图元对象校验失败：{source.name}")
        temp.replace(target)
        return target

    def commit_profile(self, profile) -> dict[str, object]:
        """Freeze every referenced symbol blob before a formal profile save.

        This method is intentionally server-independent.  A formal version cannot
        be committed unless every standard file can be materialized as an immutable
        local object with the exact recorded SHA256.
        """
        entries: list[dict[str, object]] = []
        for raw in list(getattr(profile, "managed_standard_files", []) or []):
            record = dict(raw)
            source = self._source_for_record(record)
            if source is None:
                raise ValueError(
                    "无法冻结标准版本：缺少图元文件 "
                    f"{record.get('original_name') or record.get('devref')} / SHA256 {record.get('sha256')}。"
                )
            blob = self.store_blob(source, str(record.get("sha256", "")))
            entry = self._entry_payload(record)
            entry["object_path"] = str(blob.relative_to(self.root).as_posix())
            entries.append(entry)

        # Relative paths must be unique inside one exported element tree.  Same
        # basename in different server subdirectories is fine; same relative path
        # with different content is an ambiguous standard and is rejected.
        path_hashes: dict[str, str] = {}
        for entry in entries:
            rel = str(entry["relative_path"])
            digest = str(entry["sha256"])
            previous = path_hashes.get(rel.casefold())
            if previous and previous != digest:
                raise ValueError(f"同一版本存在相同 element 相对路径但内容不同：{rel}")
            path_hashes[rel.casefold()] = digest

        ordered_entries = sorted(entries, key=lambda row: (str(row["relative_path"]).casefold(), str(row["devref"]).casefold()))
        standard_metadata = {
            "smart_lbs_devref": str(getattr(profile, "smart_lbs_devref", "")),
            "smart_breaker_devref": str(getattr(profile, "smart_breaker_devref", "")),
            "smart_ground_devref": str(getattr(profile, "smart_ground_devref", "")),
            "normal_lbs_devref": str(getattr(profile, "normal_lbs_devref", "")),
            "normal_breaker_devref": str(getattr(profile, "normal_breaker_devref", "")),
            "normal_ground_devref": str(getattr(profile, "normal_ground_devref", "")),
            "custom_symbols": list(getattr(profile, "custom_symbols", []) or []),
        }
        fingerprint_payload = {"entries": ordered_entries, "standard_metadata": standard_metadata}
        fingerprint_raw = json.dumps(
            fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        repository_fingerprint = hashlib.sha256(fingerprint_raw).hexdigest()
        manifest = {
            "manifest_version": self.MANIFEST_VERSION,
            "profile_name": str(getattr(profile, "profile_name", "")),
            "site_name": str(getattr(profile, "site_name", "")),
            "profile_version": int(getattr(profile, "profile_version", 1)),
            "standard_fingerprint": str(getattr(profile, "standard_fingerprint", "")),
            "repository_fingerprint": repository_fingerprint,
            "created_at": _utc_now(),
            "entry_count": len(entries),
            "standard_metadata": standard_metadata,
            "entries": ordered_entries,
        }
        target = self.manifest_path(manifest["profile_name"], manifest["profile_version"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            try:
                old = json.loads(target.read_text(encoding="utf-8"))
            except Exception as exc:
                raise ValueError(f"历史版本 Manifest 无法读取：{target}（{exc}）") from exc
            old_fp = str(old.get("repository_fingerprint", "")) if isinstance(old, dict) else ""
            if old_fp and old_fp != repository_fingerprint:
                raise ValueError(
                    f"历史版本 V{manifest['profile_version']} 已存在且内容不同。历史版本不可变，拒绝覆盖。"
                )
            return old if isinstance(old, dict) else manifest
        temp = target.with_suffix(".json.tmp")
        temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        return manifest

    def load_manifest(self, profile_name: str, version: int) -> dict[str, object] | None:
        path = self.manifest_path(profile_name, version)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def ensure_profile(self, profile) -> dict[str, object]:
        existing = self.load_manifest(str(profile.profile_name), int(profile.profile_version))
        if existing is not None:
            return existing
        return self.commit_profile(profile)

    def hydrate_records(self, profile) -> list[dict[str, object]]:
        """Resolve version records to immutable object paths when possible."""
        manifest = self.load_manifest(str(profile.profile_name), int(profile.profile_version))
        if manifest is None:
            try:
                manifest = self.commit_profile(profile)
            except ValueError:
                # Callers may still want to display the legacy version; validation
                # will report the missing frozen object instead of silently using a
                # current server file.
                return [dict(row) for row in list(profile.managed_standard_files or [])]
        by_key: dict[tuple[str, str], dict[str, object]] = {}
        for raw in manifest.get("entries", []) if isinstance(manifest.get("entries", []), list) else []:
            if isinstance(raw, dict):
                by_key[(str(raw.get("devref", "")).casefold(), str(raw.get("sha256", "")).lower())] = raw
        hydrated: list[dict[str, object]] = []
        for raw in list(profile.managed_standard_files or []):
            row = dict(raw)
            key = (str(row.get("devref", "")).casefold(), str(row.get("sha256", "")).lower())
            entry = by_key.get(key)
            if entry:
                row["relative_path"] = str(entry.get("relative_path", ""))
                try:
                    blob = self.object_path(str(entry.get("sha256", "")))
                    # A normal version switch is only a local checkout/display step.
                    # Formal commits already verified the full content hash. Explicit
                    # integrity validation and executable standard validation re-hash
                    # before use, so avoid re-reading every blob just to redraw the UI.
                    if blob.is_file():
                        row["managed_path"] = str(blob.resolve(strict=False))
                except (OSError, ValueError):
                    pass
            hydrated.append(row)
        return hydrated

    def verify_profile(self, profile, *, parse_metadata: bool = True) -> RepositoryIntegrityResult:
        manifest_path = self.manifest_path(str(profile.profile_name), int(profile.profile_version))
        try:
            manifest = self.ensure_profile(profile)
        except ValueError as exc:
            return RepositoryIntegrityResult(
                ok=False,
                profile_name=str(profile.profile_name),
                version=int(profile.profile_version),
                missing=[str(exc)],
                manifest_path=str(manifest_path),
            )
        entries = manifest.get("entries", []) if isinstance(manifest.get("entries", []), list) else []
        result = RepositoryIntegrityResult(
            ok=True,
            profile_name=str(profile.profile_name),
            version=int(profile.profile_version),
            total=len(entries),
            manifest_path=str(manifest_path),
            repository_fingerprint=str(manifest.get("repository_fingerprint", "")),
        )
        if parse_metadata:
            from g_file_studio.engines.icon_upgrade_engine import parse_icon_definition
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            rel = str(raw.get("relative_path", ""))
            digest = str(raw.get("sha256", "")).lower()
            try:
                blob = self.object_path(digest)
            except ValueError:
                result.hash_mismatch.append(rel or digest)
                continue
            if not blob.is_file():
                result.missing.append(rel or digest)
                continue
            try:
                if _sha256(blob) != digest:
                    result.hash_mismatch.append(rel or digest)
                    continue
            except OSError:
                result.missing.append(rel or digest)
                continue
            if parse_metadata:
                try:
                    definition = parse_icon_definition(blob)
                    actual = {
                        "width": float(definition.width),
                        "height": float(definition.height),
                        "align_center": [float(definition.align_center[0]), float(definition.align_center[1])],
                        "pins": [[float(x), float(y)] for x, y in definition.pins],
                        "element_tag": str(definition.element_tag),
                        "element_id": str(definition.element_id),
                    }
                    expected = {
                        "width": float(raw.get("width", 0.0) or 0.0),
                        "height": float(raw.get("height", 0.0) or 0.0),
                        "align_center": list(raw.get("align_center", [])),
                        "pins": list(raw.get("pins", [])),
                        "element_tag": str(raw.get("element_tag", "")),
                        "element_id": str(raw.get("element_id", "")),
                    }
                    if actual != expected:
                        result.metadata_mismatch.append(rel or digest)
                        continue
                except Exception:
                    result.metadata_mismatch.append(rel or digest)
                    continue
            result.verified += 1
        result.ok = not (result.missing or result.hash_mismatch or result.metadata_mismatch) and result.verified == result.total
        return result

    def export_profile(self, profile, destination: str | Path, *, zip_output: bool = False) -> Path:
        """Rebuild `element/...` from frozen local objects only."""
        integrity = self.verify_profile(profile, parse_metadata=True)
        if not integrity.ok:
            problems = integrity.missing + integrity.hash_mismatch + integrity.metadata_mismatch
            raise ValueError(
                f"V{profile.profile_version} 本地版本库完整性校验失败，禁止导出。"
                + ("\n" + "\n".join(problems[:10]) if problems else "")
            )
        manifest = self.load_manifest(str(profile.profile_name), int(profile.profile_version)) or {}
        destination = Path(destination)
        if zip_output:
            zip_path = destination if destination.suffix.lower() == ".zip" else destination.with_suffix(".zip")
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            temp_root = self.exports_root / f"{_safe_component(profile.profile_name)}_V{int(profile.profile_version)}_tmp"
            if temp_root.exists():
                shutil.rmtree(temp_root)
            element_root = temp_root / "element"
            self._rebuild_element_tree(manifest, element_root)
            temp_zip = zip_path.with_suffix(zip_path.suffix + ".tmp")
            temp_zip.unlink(missing_ok=True)
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(element_root.rglob("*")):
                    if path.is_file():
                        archive.write(path, arcname=str(Path("element") / path.relative_to(element_root)))
            temp_zip.replace(zip_path)
            shutil.rmtree(temp_root, ignore_errors=True)
            return zip_path
        element_root = destination if destination.name.casefold() == "element" else destination / "element"
        if element_root.exists():
            # Export must be deterministic and must not merge with stale files from
            # another version. The caller chooses/approves the destination first.
            if any(element_root.iterdir()):
                raise ValueError(f"导出目录非空：{element_root}。请选择空目录。")
        element_root.mkdir(parents=True, exist_ok=True)
        self._rebuild_element_tree(manifest, element_root)
        return element_root

    def _rebuild_element_tree(self, manifest: dict[str, object], element_root: Path) -> None:
        entries = manifest.get("entries", []) if isinstance(manifest.get("entries", []), list) else []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            digest = str(raw.get("sha256", "")).lower()
            rel = _safe_relative_path(str(raw.get("relative_path", "")), fallback_name=str(raw.get("original_name", "symbol.g")))
            source = self.object_path(digest)
            target = element_root / Path(*PurePosixPath(rel).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def archive_deleted_manifest(self, profile_name: str, version: int) -> Path | None:
        """Remove one user-deleted historical version from the reachable manifest set.

        The manifest is moved into a local deletion archive instead of being
        overwritten. Immutable SHA256 objects are deliberately retained because
        another version may reference the same content. No remote/server file is
        accessed or changed.
        """
        source = self.manifest_path(profile_name, version)
        if not source.is_file():
            return None
        target_dir = self.deleted_manifests_root / _safe_component(profile_name)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = target_dir / f"V{int(version)}.{stamp}.json"
        counter = 1
        while target.exists():
            target = target_dir / f"V{int(version)}.{stamp}.{counter}.json"
            counter += 1
        source.replace(target)
        return target

    def version_details(self, profile) -> dict[str, object]:
        manifest = self.ensure_profile(profile)
        entries = manifest.get("entries", []) if isinstance(manifest.get("entries", []), list) else []
        server_backed = sum(1 for row in entries if isinstance(row, dict) and str(row.get("standard_source", "")) == "server")
        manual = len(entries) - server_backed
        revisions: dict[str, set[str]] = {}
        profile_manifest_dir = self.manifests_root / _safe_component(str(profile.profile_name))
        for path in profile_manifest_dir.glob("V*.json") if profile_manifest_dir.is_dir() else []:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            for raw in payload.get("entries", []) if isinstance(payload, dict) and isinstance(payload.get("entries", []), list) else []:
                if not isinstance(raw, dict):
                    continue
                revisions.setdefault(str(raw.get("relative_path", "")), set()).add(str(raw.get("sha256", "")))
        changed_paths = sum(1 for hashes in revisions.values() if len({item for item in hashes if item}) > 1)
        return {
            "profile_name": str(profile.profile_name),
            "site_name": str(profile.site_name),
            "version": int(profile.profile_version),
            "entry_count": len(entries),
            "server_backed": server_backed,
            "manual": manual,
            "repository_fingerprint": str(manifest.get("repository_fingerprint", "")),
            "manifest_path": str(self.manifest_path(str(profile.profile_name), int(profile.profile_version))),
            "repository_root": str(self.root),
            "paths_with_history": changed_paths,
        }
