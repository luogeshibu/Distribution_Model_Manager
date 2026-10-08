from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from g_file_studio.services.paths import app_data_root
from g_file_studio.services.user_settings_service import UserSettingsService
from g_file_studio.services.symbol_standard_repository import SymbolStandardRepository, relative_path_from_record


def _standard_library_root() -> Path:
    return app_data_root() / "Standards"


def _server_revision_label(timestamp: str) -> str:
    """Return the user-facing revision for the applied server snapshot.

    The persisted timestamp is UTC and deliberately has no filesystem/version
    semantics.  It is only the point-in-time label of the server standard that
    the user explicitly applied.
    """
    raw = str(timestamp or "").strip()
    if not raw:
        return ""
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        value = value.astimezone(timezone.utc)
        return value.strftime("%Y%m%d-%H%M%S")
    except ValueError:
        return re.sub(r"[^0-9]", "", raw)[:14]



@dataclass
class SiteSmartProfile:
    """Server-standard RMU device profile for one site.

    Historical JSON files from v2.18.29-v2.18.32 only contain the two SMART devrefs;
    the NORMAL fields therefore deliberately have defaults so old profiles continue
    to load unchanged. For authoritative profiles, geometry is rebuilt from the
    managed server symbol-definition G files; legacy learned geometry is kept
    only for backward compatibility with profiles that have not yet been migrated.
    """

    profile_name: str
    site_name: str
    smart_lbs_devref: str
    smart_breaker_devref: str
    normal_lbs_devref: str = ""
    normal_breaker_devref: str = ""
    smart_ground_devref: str = ""
    normal_ground_devref: str = ""
    sample_files: list[str] = field(default_factory=list)
    smart_rmu_count: int = 0
    normal_rmu_count: int = 0
    ignored_rmu_count: int = 0
    lbs_observations: int = 0
    breaker_observations: int = 0
    normal_lbs_observations: int = 0
    normal_breaker_observations: int = 0
    ground_observations: int = 0
    normal_ground_observations: int = 0
    lbs_confidence: float = 0.0
    breaker_confidence: float = 0.0
    normal_lbs_confidence: float = 0.0
    normal_breaker_confidence: float = 0.0
    ground_confidence: float = 0.0
    normal_ground_confidence: float = 0.0
    lbs_candidates: dict[str, int] = field(default_factory=dict)
    breaker_candidates: dict[str, int] = field(default_factory=dict)
    normal_lbs_candidates: dict[str, int] = field(default_factory=dict)
    normal_breaker_candidates: dict[str, int] = field(default_factory=dict)
    ground_candidates: dict[str, int] = field(default_factory=dict)
    normal_ground_candidates: dict[str, int] = field(default_factory=dict)
    geometry_templates: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    custom_symbols: list[dict[str, object]] = field(default_factory=list)
    symbol_catalog: dict[str, dict[str, object]] = field(default_factory=dict)
    # Authoritative server-derived icon-definition G files. Files are copied into
    # a version-independent managed library so application upgrades cannot delete
    # the standard. Legacy local records remain readable for migration only.
    managed_standard_files: list[dict[str, object]] = field(default_factory=list)
    standard_fingerprint: str = ""
    # A saved ACTIVE standard may be explicitly locked by the user. Locking is
    # version metadata only: it does not create a new standard version, but all
    # edits/uploads/deletes/restores are rejected until the user unlocks it.
    locked: bool = False
    # Discovery metadata belongs to the inspection workflow, not to the standard version itself.
    # pending = user has been notified once and can review later; ignored = do not ask again.
    discovery_catalog: dict[str, dict[str, object]] = field(default_factory=dict)
    discovery_decisions: dict[str, str] = field(default_factory=dict)
    profile_version: int = 1
    history: list[dict[str, object]] = field(default_factory=list)
    updated_at: str = ""
    # User-facing marker for the server snapshot explicitly applied to this
    # current standard. Internal profile_version/history remain rollback-only.
    server_standard_revision: str = ""

    def normalized(self) -> "SiteSmartProfile":
        managed_files = _normalize_managed_standard_files(self.managed_standard_files)
        normalized_catalog = _normalize_symbol_catalog(self.symbol_catalog)
        # Once managed standard files exist, their metadata and pin geometry are
        # authoritative. Historical scan-derived values may remain for migration,
        # but they can never override a user-uploaded standard file.
        for devref, row in _symbol_catalog_from_managed_standard_files(managed_files).items():
            normalized_catalog[devref] = row
        effective_geometry = _effective_geometry_payload(self.geometry_templates, normalized_catalog)
        for devref, rows in _geometry_templates_from_managed_standard_files(managed_files).items():
            effective_geometry[devref] = rows
        normalized_updated_at = self.updated_at.strip() or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return SiteSmartProfile(
            profile_name=self.profile_name.strip(),
            site_name=self.site_name.strip(),
            smart_lbs_devref=self.smart_lbs_devref.strip(),
            smart_breaker_devref=self.smart_breaker_devref.strip(),
            normal_lbs_devref=self.normal_lbs_devref.strip(),
            normal_breaker_devref=self.normal_breaker_devref.strip(),
            smart_ground_devref=self.smart_ground_devref.strip(),
            normal_ground_devref=self.normal_ground_devref.strip(),
            sample_files=[str(item) for item in self.sample_files if str(item).strip()],
            smart_rmu_count=max(0, int(self.smart_rmu_count)),
            normal_rmu_count=max(0, int(self.normal_rmu_count)),
            ignored_rmu_count=max(0, int(self.ignored_rmu_count)),
            lbs_observations=max(0, int(self.lbs_observations)),
            breaker_observations=max(0, int(self.breaker_observations)),
            normal_lbs_observations=max(0, int(self.normal_lbs_observations)),
            normal_breaker_observations=max(0, int(self.normal_breaker_observations)),
            ground_observations=max(0, int(self.ground_observations)),
            normal_ground_observations=max(0, int(self.normal_ground_observations)),
            lbs_confidence=max(0.0, min(1.0, float(self.lbs_confidence))),
            breaker_confidence=max(0.0, min(1.0, float(self.breaker_confidence))),
            normal_lbs_confidence=max(0.0, min(1.0, float(self.normal_lbs_confidence))),
            normal_breaker_confidence=max(0.0, min(1.0, float(self.normal_breaker_confidence))),
            ground_confidence=max(0.0, min(1.0, float(self.ground_confidence))),
            normal_ground_confidence=max(0.0, min(1.0, float(self.normal_ground_confidence))),
            lbs_candidates={str(k): int(v) for k, v in self.lbs_candidates.items() if str(k).strip() and int(v) > 0},
            breaker_candidates={str(k): int(v) for k, v in self.breaker_candidates.items() if str(k).strip() and int(v) > 0},
            normal_lbs_candidates={str(k): int(v) for k, v in self.normal_lbs_candidates.items() if str(k).strip() and int(v) > 0},
            normal_breaker_candidates={str(k): int(v) for k, v in self.normal_breaker_candidates.items() if str(k).strip() and int(v) > 0},
            ground_candidates={str(k): int(v) for k, v in self.ground_candidates.items() if str(k).strip() and int(v) > 0},
            normal_ground_candidates={str(k): int(v) for k, v in self.normal_ground_candidates.items() if str(k).strip() and int(v) > 0},
            geometry_templates=effective_geometry,
            custom_symbols=_normalize_custom_symbols(self.custom_symbols),
            symbol_catalog=normalized_catalog,
            managed_standard_files=managed_files,
            standard_fingerprint=str(self.standard_fingerprint or "").strip(),
            locked=bool(self.locked),
            discovery_catalog=_normalize_symbol_catalog(self.discovery_catalog),
            discovery_decisions=_normalize_discovery_decisions(self.discovery_decisions),
            profile_version=max(1, int(self.profile_version or 1)),
            history=[dict(item) for item in self.history if isinstance(item, dict)],
            updated_at=normalized_updated_at,
            server_standard_revision=(
                self.server_standard_revision.strip()
                or _server_revision_label(normalized_updated_at)
            ),
        )

    @property
    def server_standard_label(self) -> str:
        """Return the stable label shown by every module using this standard."""
        revision = self.server_standard_revision.strip() or _server_revision_label(self.updated_at)
        return revision or "未标记"

    @property
    def smart_ready(self) -> bool:
        return bool(self.smart_lbs_devref and self.smart_breaker_devref)

    @property
    def normal_ready(self) -> bool:
        return bool(self.normal_lbs_devref and self.normal_breaker_devref)

    @property
    def ground_ready(self) -> bool:
        return bool(self.smart_ground_devref and self.normal_ground_devref)

    @property
    def full_ready(self) -> bool:
        return self.smart_ready and self.normal_ready and self.ground_ready

    @property
    def configured_builtin_role_count(self) -> int:
        return sum(1 for value in (
            self.smart_lbs_devref,
            self.smart_breaker_devref,
            self.smart_ground_devref,
            self.normal_lbs_devref,
            self.normal_breaker_devref,
            self.normal_ground_devref,
        ) if str(value).strip())

    @property
    def authoritative_ready(self) -> bool:
        return bool(self.configured_builtin_role_count or any(
            bool(row.get("enabled", True)) and str(row.get("standard_devref", "")).strip()
            for row in self.custom_symbols
        ))


JEDDAH_CLASSIFICATION_MARKER_TO_ROLE = {
    "CIRCUIT_BREAKER_SMART": "smart_breaker",
    "LOAD_BREAKER_SWITCH_SMART": "smart_lbs",
    "CIRCUIT_BREAKER_NO_SMART": "normal_breaker",
    "LOAD_BREAKER_SWITCH_NO_SMART": "normal_lbs",
}


def _normalize_jeddah_classification_marker(value: object) -> str:
    """Normalize an operator marker without inferring any business meaning."""
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def resolve_jeddah_classification_marker_roles(
    entries: object,
) -> tuple[dict[str, str], list[str]]:
    """Resolve the four Jeddah RMU target symbols from explicit local markers.

    The marker is authoritative for the *target* symbol only.  Device-role detection
    in a business G remains based on that element's original devref/file name.  No
    filename inference or peer-cabinet learning is used to choose these targets.

    Accepted entry shapes are the portable dictionaries returned by
    ``RemoteSymbolLibraryService.load_classification_marker_entries`` and the compact
    ``(file_name, devref, marker)`` tuples passed by the Jeddah UI/worker settings.
    """
    roles = {
        "smart_lbs": "",
        "smart_breaker": "",
        "smart_ground": "",
        "normal_lbs": "",
        "normal_breaker": "",
        "normal_ground": "",
    }
    candidates: dict[str, set[str]] = {key: set() for key in JEDDAH_CLASSIFICATION_MARKER_TO_ROLE.values()}
    marker_without_devref: set[str] = set()

    raw_entries = entries if isinstance(entries, (list, tuple)) else ()
    for raw in raw_entries:
        file_name = ""
        devref = ""
        marker = ""
        if isinstance(raw, dict):
            file_name = str(raw.get("file_name", raw.get("name", "")) or "").strip()
            devref = str(raw.get("devref", raw.get("standard_devref", "")) or "").strip()
            marker = str(raw.get("classification_marker", raw.get("category_marker", raw.get("marker", ""))) or "").strip()
        elif isinstance(raw, (list, tuple)) and len(raw) >= 3:
            file_name = str(raw[0] or "").strip()
            devref = str(raw[1] or "").strip()
            marker = str(raw[2] or "").strip()
        else:
            continue

        normalized = _normalize_jeddah_classification_marker(marker)
        role_key = JEDDAH_CLASSIFICATION_MARKER_TO_ROLE.get(normalized)
        if not role_key:
            continue
        if not devref:
            marker_without_devref.add(normalized + (f" ({file_name})" if file_name else ""))
            continue
        candidates[role_key].add(devref)

    issues: list[str] = []
    label_by_role = {value: marker for marker, value in JEDDAH_CLASSIFICATION_MARKER_TO_ROLE.items()}
    for role_key, marker in label_by_role.items():
        values = sorted(candidates.get(role_key, set()), key=str.casefold)
        if len(values) == 1:
            roles[role_key] = values[0]
        elif not values:
            issues.append(f"缺少分类标记 {marker}")
        else:
            issues.append(f"分类标记 {marker} 对应多个图元：" + "；".join(values))

    for item in sorted(marker_without_devref, key=str.casefold):
        issues.append(f"分类标记 {item} 对应的服务器图元没有可用 devref")
    return roles, issues


def resolve_jeddah_role_devrefs(profile: SiteSmartProfile | None) -> dict[str, str]:
    """Resolve Jeddah RMU switch roles from the generic standard table.

    v2.18.105 removed the six privileged UI rows and stores authoritative standards
    as generic ``custom_symbols``.  Jeddah batch needs SMART/NORMAL LBS and Circuit
    Breaker categories, so derive those roles from the user-confirmed generic
    metadata. Ground-disconnector fields remain only for old profile compatibility;
    they are not used for replacement. Explicit SMART/NORMAL rows win; an ANY row
    is only used as a fallback for both scopes. Legacy fixed fields remain supported.
    """
    empty = {
        "smart_lbs": "", "smart_breaker": "", "smart_ground": "",
        "normal_lbs": "", "normal_breaker": "", "normal_ground": "",
    }
    if profile is None:
        return empty

    result = dict(empty)
    # Legacy profiles keep working without migration.
    result.update({
        "smart_lbs": str(profile.smart_lbs_devref or "").strip(),
        "smart_breaker": str(profile.smart_breaker_devref or "").strip(),
        "smart_ground": str(profile.smart_ground_devref or "").strip(),
        "normal_lbs": str(profile.normal_lbs_devref or "").strip(),
        "normal_breaker": str(profile.normal_breaker_devref or "").strip(),
        "normal_ground": str(profile.normal_ground_devref or "").strip(),
    })

    file_by_devref = {
        str(row.get("devref", "")).strip().casefold(): str(row.get("original_name", "") or "").strip()
        for row in _normalize_managed_standard_files(profile.managed_standard_files)
        if str(row.get("devref", "")).strip()
    }
    any_fallback: dict[str, str] = {}

    for row in _normalize_custom_symbols(profile.custom_symbols):
        if not bool(row.get("enabled", True)):
            continue
        devref = str(row.get("standard_devref", "") or "").strip()
        if not devref:
            continue
        scope = str(row.get("scope", "ANY") or "ANY").strip().upper()
        tag = str(row.get("element_tag", "") or "").strip()
        source_file = file_by_devref.get(devref.casefold(), str(row.get("source_file", "") or "").strip())
        seed = re.sub(
            r"[^A-Z0-9]+", "_",
            " ".join((
                str(row.get("device_type", "") or ""),
                str(row.get("role", "") or ""),
                tag,
                source_file,
                devref,
            )).upper(),
        ).strip("_")

        kind = ""
        if tag == "ZhaiWaiJieDiDaoZha" or any(token in seed for token in ("GROUND_DISCONNECTOR", "GROUNDDISCONNECTOR", "JIEDIDAOZHA")):
            kind = "ground"
        elif tag == "CBreakerDis":
            if any(token in seed for token in ("LOAD_BREAKER_SWITCH", "LOADBREAKERSWITCH", "RMU_LBS")) or re.search(r"(?:^|_)LBS(?:_|$)", seed):
                kind = "lbs"
            elif "CIRCUIT_BREAKER" in seed or "CIRCUITBREAKER" in seed or re.search(r"(?:^|_)BREAKER(?:_|$)", seed):
                kind = "breaker"
        if not kind:
            continue

        if scope == "SMART":
            result[f"smart_{kind}"] = devref
        elif scope == "NORMAL":
            result[f"normal_{kind}"] = devref
        else:
            any_fallback.setdefault(kind, devref)

    for kind, devref in any_fallback.items():
        result.setdefault(f"smart_{kind}", "")
        result.setdefault(f"normal_{kind}", "")
        if not result[f"smart_{kind}"]:
            result[f"smart_{kind}"] = devref
        if not result[f"normal_{kind}"]:
            result[f"normal_{kind}"] = devref
    return result


def jeddah_role_issues(profile: SiteSmartProfile | None) -> list[str]:
    roles = resolve_jeddah_role_devrefs(profile)
    labels = (
        ("smart_lbs", "SMART LBS"),
        ("smart_breaker", "SMART Circuit Breaker"),
        ("normal_lbs", "NORMAL LBS"),
        ("normal_breaker", "NORMAL Circuit Breaker"),
    )
    return [label for key, label in labels if not str(roles.get(key, "")).strip()]


def infer_builtin_standard_role(record: dict[str, object]) -> tuple[str, str]:
    """Infer SMART/NORMAL + device role from one uploaded icon definition.

    The result is only a guardrail for row-specific manual upload.  The user-selected
    row remains authoritative when a vendor filename is ambiguous.  We deliberately
    recognize only strong names so arbitrary site-specific icon names are not guessed.
    """
    tag = str(record.get("element_tag", "")).strip()
    source = " ".join(
        str(record.get(key, "") or "")
        for key in ("original_name", "element_id", "devref")
    ).upper()
    tokenized = re.sub(r"[^A-Z0-9]+", "_", source).strip("_")

    scope = ""
    if re.search(r"(?:^|_)(?:NON|NO)_?SMART(?:_|$)", tokenized) or re.search(r"(?:^|_)NORMAL(?:_|$)", tokenized):
        scope = "NORMAL"
    elif re.search(r"(?:^|_)SMART(?:_|$)", tokenized):
        scope = "SMART"

    if tag == "ZhaiWaiJieDiDaoZha":
        return scope, "GROUND"
    if tag != "CBreakerDis":
        return scope, ""

    role = ""
    if "LOAD_BREAKER_SWITCH" in tokenized or re.search(r"(?:^|_)LBS(?:_|$)", tokenized):
        role = "LBS"
    elif "CIRCUIT_BREAKER" in tokenized or re.search(r"(?:^|_)BREAKER(?:_|$)", tokenized):
        role = "BREAKER"
    return scope, role


def _geometry_templates_from_symbol_catalog(
    catalog: dict[str, dict[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Build authoritative rotation-specific electrical-anchor geometry from raw icon metadata.

    ``symbol_catalog`` rows populated from a real ``*.icn.g`` definition include
    width/height and the raw ``pin(cx, cy)`` coordinates.  Those pin coordinates are
    more authoritative than geometry inferred from an already-placed main G symbol.
    In particular, when the user changes a standard devref (for example
    ``Circuit_Breaker_NON-SMART`` -> ``Circuit_Breaker_NO-SMART``), Jeddah batch must
    update x/y/w/h so the NEW symbol pins stay on the existing ConnectLine endpoints.
    """
    if not isinstance(catalog, dict):
        return {}
    # Import here to keep the persistence service lightweight and avoid changing the
    # module import graph for users that only read profile JSON.
    from g_file_studio.engines.icon_upgrade_engine import rotated

    result: dict[str, list[dict[str, object]]] = {}
    for devref, raw in catalog.items():
        if not isinstance(raw, dict):
            continue
        key = str(devref).strip()
        if not key:
            continue
        try:
            width = float(raw.get("width", 0.0) or 0.0)
            height = float(raw.get("height", 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        raw_pins = raw.get("pins", [])
        pins: list[tuple[float, float]] = []
        if isinstance(raw_pins, list):
            for pin in raw_pins:
                if not isinstance(pin, (list, tuple)) or len(pin) < 2:
                    continue
                try:
                    pins.append((float(pin[0]), float(pin[1])))
                except (TypeError, ValueError):
                    continue
        if width <= 0 or height <= 0 or not pins:
            continue
        rows: list[dict[str, object]] = []
        for rotation in (0, 90, 180, 270):
            rows.append({
                "rotation": rotation,
                "width": width,
                "height": height,
                "anchor_offsets": [
                    [float(x), float(y)]
                    for x, y in (rotated(pin, width, height, rotation) for pin in pins)
                ],
            })
        result[key] = rows
    return result


def _effective_geometry_payload(
    geometry_templates: object,
    symbol_catalog: object,
) -> dict[str, list[dict[str, object]]]:
    """Return profile geometry with raw icon-definition pin geometry taking precedence."""
    geometry = _normalize_geometry_payload(geometry_templates)
    catalog = _normalize_symbol_catalog(symbol_catalog)
    # If a catalog row has real pin(cx,cy) data it came from a symbol-definition G,
    # so replace any stale/inferred rows for that devref rather than mixing two
    # incompatible generations and letting the fitter choose arbitrarily.
    for devref, rows in _geometry_templates_from_symbol_catalog(catalog).items():
        geometry[devref] = rows
    return geometry

def _normalize_geometry_payload(value: object) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    if not isinstance(value, dict):
        return result
    for devref, rows in value.items():
        if not isinstance(devref, str) or not devref.strip() or not isinstance(rows, list):
            continue
        clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
        if clean_rows:
            result[devref.strip()] = clean_rows
    return result



def _normalize_custom_symbols(value: object) -> list[dict[str, object]]:
    """Normalize user-defined symbol-standard rows.

    Rows are stored as JSON-compatible dictionaries so old profiles remain readable
    and future releases can add fields without a hard migration.
    """
    result: list[dict[str, object]] = []
    if not isinstance(value, list):
        return result
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            continue
        uid = str(raw.get("uid", "")).strip() or f"custom-{index + 1}"
        if uid in seen:
            uid = f"{uid}-{index + 1}"
        seen.add(uid)
        scope = str(raw.get("scope", "ANY")).strip().upper() or "ANY"
        if scope not in {"ANY", "SMART", "NORMAL"}:
            scope = "ANY"
        role = str(raw.get("role", "")).strip()
        element_tag = str(raw.get("element_tag", "")).strip()
        standard_devref = str(raw.get("standard_devref", "")).strip()
        match_attr = str(raw.get("match_attr", "devref")).strip() or "devref"
        if match_attr not in {"XML元素", "devref", "p_NameString", "key_name"}:
            match_attr = "devref"
        observed_devref = str(raw.get("observed_devref", "")).strip()
        match_value = str(raw.get("match_value", "")).strip() or observed_devref or standard_devref
        if not role and not element_tag and not standard_devref:
            continue
        symbol_usage = str(raw.get("symbol_usage", "")).strip()
        if symbol_usage not in {"设备", "设备组成图元", "状态图元", "标签/辅助图元", "测量/信号", "Poke/跳转", "其他"}:
            source_hint = str(raw.get("source_file", "") or "").lower()
            role_hint = f"{role} {element_tag}".upper()
            if ".zt.icn.g" in source_hint or "STATUS" in role_hint or "状态" in role_hint:
                symbol_usage = "状态图元"
            elif "POKE" in role_hint:
                symbol_usage = "Poke/跳转"
            elif any(token in role_hint for token in ("MEASURE", "ANALOG", "SIGNAL", "测量", "信号")):
                symbol_usage = "测量/信号"
            else:
                symbol_usage = "设备"
        device_type = str(raw.get("device_type", "")).strip() or role
        device_subtype = str(raw.get("device_subtype", "")).strip()
        device_level = str(raw.get("device_level", "")).strip()
        if device_level not in {"独立设备", "组合设备", "设备内部部件", "辅助关联", "不计入设备"}:
            if symbol_usage == "设备":
                device_level = "独立设备"
            elif symbol_usage == "设备组成图元":
                device_level = "设备内部部件"
            elif symbol_usage in {"状态图元", "标签/辅助图元", "测量/信号", "Poke/跳转"}:
                device_level = "辅助关联"
            else:
                device_level = "不计入设备"
        result.append({
            "uid": uid,
            "scope": scope,
            "role": role,
            "device_type": device_type,
            "device_subtype": device_subtype,
            "device_level": device_level,
            "symbol_usage": symbol_usage,
            "element_tag": element_tag,
            "standard_devref": standard_devref,
            "match_attr": match_attr,
            "match_value": match_value,
            "enabled": bool(raw.get("enabled", True)),
            "source_file": str(raw.get("source_file", "")).strip(),
            "classification_marker": str(raw.get("classification_marker", raw.get("category_marker", "")) or "").strip(),
            "category_marker": str(raw.get("classification_marker", raw.get("category_marker", "")) or "").strip(),
            # Optional business-G discovery evidence. These fields are informational
            # only and never override the authoritative uploaded standard file.
            "observed_devref": observed_devref,
            "observed_symbol_file": str(raw.get("observed_symbol_file", "")).strip(),
            "observed_count": max(0, int(raw.get("observed_count", 0) or 0)),
            "observed_files": [str(item) for item in raw.get("observed_files", []) if str(item).strip()] if isinstance(raw.get("observed_files", []), list) else [],
            "observed_examples": [dict(item) for item in raw.get("observed_examples", []) if isinstance(item, dict)] if isinstance(raw.get("observed_examples", []), list) else [],
        })
    return result


def _normalize_symbol_catalog(value: object) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    if not isinstance(value, dict):
        return result
    for devref, raw in value.items():
        key = str(devref).strip()
        if not key or not isinstance(raw, dict):
            continue
        row = dict(raw)
        row["devref"] = key
        row["element_tag"] = str(row.get("element_tag", "")).strip()
        row["element_id"] = str(row.get("element_id", "")).strip()
        row["source_file"] = str(row.get("source_file", "")).strip()
        row["classification_marker"] = str(row.get("classification_marker", row.get("category_marker", "")) or "").strip()
        row["category_marker"] = row["classification_marker"]
        row["p_NameString"] = str(row.get("p_NameString", "")).strip()
        row["key_name"] = str(row.get("key_name", "")).strip()
        try:
            row["count"] = max(0, int(row.get("count", 0) or 0))
        except (TypeError, ValueError):
            row["count"] = 0
        for name in ("width", "height"):
            try:
                row[name] = float(row.get(name, 0.0) or 0.0)
            except (TypeError, ValueError):
                row[name] = 0.0
        align = row.get("align_center", [])
        if isinstance(align, (list, tuple)) and len(align) >= 2:
            try:
                row["align_center"] = [float(align[0]), float(align[1])]
            except (TypeError, ValueError):
                row["align_center"] = []
        else:
            row["align_center"] = []
        pins: list[list[float]] = []
        raw_pins = row.get("pins", [])
        if isinstance(raw_pins, list):
            for pin in raw_pins:
                if isinstance(pin, (list, tuple)) and len(pin) >= 2:
                    try:
                        pins.append([float(pin[0]), float(pin[1])])
                    except (TypeError, ValueError):
                        continue
        row["pins"] = pins
        row["pin_ids"] = [str(item) for item in row.get("pin_ids", [])] if isinstance(row.get("pin_ids", []), list) else []
        rotations: list[int] = []
        raw_rotations = row.get("rotations", [])
        if isinstance(raw_rotations, list):
            for item in raw_rotations:
                try:
                    rotations.append(int(item) % 360)
                except (TypeError, ValueError):
                    continue
        row["rotations"] = sorted(set(rotations))
        result[key] = row
    return result


def _normalize_managed_standard_files(value: object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    # Server-cache consumers intentionally use immutable tuples while saved
    # Profile data uses lists. Treat both as the same record sequence.
    if not isinstance(value, (list, tuple)):
        return result
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        devref = str(row.get("devref", "")).strip()
        sha256 = str(row.get("sha256", "")).strip().lower()
        if not devref or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            continue
        key = (devref.casefold(), sha256)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "devref": devref,
            "sha256": sha256,
            "original_name": str(row.get("original_name", "")).strip(),
            "original_source": str(row.get("original_source", "")).strip(),
            "managed_path": str(row.get("managed_path", "")).strip(),
            "relative_path": relative_path_from_record(row),
            "element_tag": str(row.get("element_tag", "")).strip(),
            "element_id": str(row.get("element_id", "")).strip(),
            "width": float(row.get("width", 0.0) or 0.0),
            "height": float(row.get("height", 0.0) or 0.0),
            "align_center": list(row.get("align_center", [])) if isinstance(row.get("align_center", []), list) else [],
            "pins": list(row.get("pins", [])) if isinstance(row.get("pins", []), list) else [],
            "pin_ids": [str(item) for item in row.get("pin_ids", [])] if isinstance(row.get("pin_ids", []), list) else [],
            "pin_indices": [str(item) for item in row.get("pin_indices", [])] if isinstance(row.get("pin_indices", []), list) else [],
            "standard_source": str(row.get("standard_source", "server") or "server").strip().lower(),
            "remote_host": str(row.get("remote_host", "")).strip(),
            "remote_root": str(row.get("remote_root", "")).strip(),
            "remote_path": str(row.get("remote_path", "")).strip(),
            "remote_size": int(row.get("remote_size", 0) or 0),
            "remote_mtime": int(row.get("remote_mtime", 0) or 0),
            "cache_path": str(row.get("cache_path", "")).strip(),
            "synced_at": str(row.get("synced_at", "")).strip(),
            "classification_marker": str(row.get("classification_marker", row.get("category_marker", "")) or "").strip(),
            "category_marker": str(row.get("classification_marker", row.get("category_marker", "")) or "").strip(),
        })
    result.sort(key=lambda row: (str(row.get("devref", "")).casefold(), str(row.get("sha256", ""))))
    return result


def _symbol_catalog_from_managed_standard_files(records: object) -> dict[str, dict[str, object]]:
    """Build deterministic catalog rows only from uploaded standard icon files."""
    catalog: dict[str, dict[str, object]] = {}
    for row in _normalize_managed_standard_files(records):
        devref = str(row.get("devref", "")).strip()
        if not devref:
            continue
        catalog[devref] = {
            "devref": devref,
            "element_tag": str(row.get("element_tag", "")).strip(),
            "element_id": str(row.get("element_id", "")).strip(),
            "source_file": str(row.get("original_name", "")).strip(),
            "width": float(row.get("width", 0.0) or 0.0),
            "height": float(row.get("height", 0.0) or 0.0),
            "align_center": list(row.get("align_center", [])),
            "pins": list(row.get("pins", [])),
            "pin_ids": list(row.get("pin_ids", [])),
            "pin_indices": list(row.get("pin_indices", [])),
            "rotations": [0, 90, 180, 270],
            "p_NameString": "",
            "key_name": "",
            "count": 1,
            "sha256": str(row.get("sha256", "")).strip(),
            "managed_path": str(row.get("managed_path", "")).strip(),
            "relative_path": relative_path_from_record(row),
            "standard_source": str(row.get("standard_source", "server") or "server").strip().lower(),
            "remote_host": str(row.get("remote_host", "")).strip(),
            "remote_root": str(row.get("remote_root", "")).strip(),
            "remote_path": str(row.get("remote_path", "")).strip(),
            "remote_size": int(row.get("remote_size", 0) or 0),
            "remote_mtime": int(row.get("remote_mtime", 0) or 0),
            "cache_path": str(row.get("cache_path", "")).strip(),
            "synced_at": str(row.get("synced_at", "")).strip(),
            "classification_marker": str(row.get("classification_marker", row.get("category_marker", "")) or "").strip(),
            "category_marker": str(row.get("classification_marker", row.get("category_marker", "")) or "").strip(),
        }
    return catalog


def _geometry_templates_from_managed_standard_files(records: object) -> dict[str, list[dict[str, object]]]:
    return _geometry_templates_from_symbol_catalog(_symbol_catalog_from_managed_standard_files(records))


def authoritative_standard_catalog(profile: SiteSmartProfile) -> dict[str, dict[str, object]]:
    """Return only the managed server-synchronized standards; never business-scan data."""
    return _symbol_catalog_from_managed_standard_files(profile.managed_standard_files)


def authoritative_geometry_templates(profile: SiteSmartProfile) -> dict[str, list[dict[str, object]]]:
    """Build exact geometry solely from the synchronized server icon definitions."""
    return _geometry_templates_from_managed_standard_files(profile.managed_standard_files)


def standard_catalog_from_server_records(records: object) -> dict[str, dict[str, object]]:
    """Build an authoritative catalog directly from the local server-symbol cache.

    The public Server Symbol Sync Management flow no longer persists the retired
    Profile repository. Site processors that only need the already-synchronized
    server definitions must therefore consume the cache records directly instead
    of requiring a legacy ``global_selection`` pointer.
    """
    return _symbol_catalog_from_managed_standard_files(records)


def geometry_templates_from_server_records(records: object) -> dict[str, list[dict[str, object]]]:
    """Build exact geometry directly from synchronized server-symbol records."""
    return _geometry_templates_from_managed_standard_files(records)


def _standard_files_fingerprint(records: object) -> str:
    rows = _normalize_managed_standard_files(records)
    payload = [
        {
            "devref": row["devref"],
            "sha256": row["sha256"],
            "element_tag": row["element_tag"],
            "element_id": row["element_id"],
            "width": row["width"],
            "height": row["height"],
            "align_center": row["align_center"],
            "pins": row["pins"],
            "pin_ids": row.get("pin_ids", []),
            "pin_indices": row.get("pin_indices", []),
        }
        for row in rows
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest() if payload else ""


def _profile_standard_fingerprint(profile) -> str:
    files = _normalize_managed_standard_files(getattr(profile, "managed_standard_files", []))
    if not files:
        return ""
    payload = {
        "roles": {
            "smart_lbs": str(getattr(profile, "smart_lbs_devref", "")),
            "smart_breaker": str(getattr(profile, "smart_breaker_devref", "")),
            "smart_ground": str(getattr(profile, "smart_ground_devref", "")),
            "normal_lbs": str(getattr(profile, "normal_lbs_devref", "")),
            "normal_breaker": str(getattr(profile, "normal_breaker_devref", "")),
            "normal_ground": str(getattr(profile, "normal_ground_devref", "")),
        },
        "files": [
            {
                "devref": row["devref"],
                "sha256": row["sha256"],
                "element_tag": row["element_tag"],
                "element_id": row["element_id"],
                "width": row["width"],
                "height": row["height"],
                "align_center": row["align_center"],
                "pins": row["pins"],
                "pin_ids": row.get("pin_ids", []),
                "pin_indices": row.get("pin_indices", []),
            }
            for row in files
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _normalize_discovery_decisions(value: object) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(value, dict):
        return result
    for devref, status in value.items():
        key = str(devref).strip()
        state = str(status).strip().lower()
        if key and state in {"pending", "ignored"}:
            result[key] = state
    return result


class SiteProfileService:
    """Persist user-confirmed site RMU device profiles outside project source files."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            settings = UserSettingsService()
            path = settings.ini_path.parent / "site_smart_profiles.json"
        self.path = Path(path)
        self._profiles_cache: dict[str, SiteSmartProfile] | None = None
        self._profiles_cache_mtime_ns: int | None = None
        # v2.18.119: Git-style immutable symbol repository.  The repository is
        # local-only; it never writes to the remote server.
        self.repository = SymbolStandardRepository(_standard_library_root().parent / "SymbolRepository")

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_name(value: str) -> str:
        text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip()).strip("._")
        return text or "standard"

    def prepare_standard_file_records(self, files: list[Path]) -> list[dict[str, object]]:
        """Validate server-downloaded authoritative symbol G files.

        Business SLD G files and manually uploaded files are not accepted by the
        current UI. Every selected file must be a
        parseable icon-definition G containing a body with w/h/AlignCenter.
        Multiple historical versions are supported through Profile versions, but
        one ACTIVE standard cannot contain two different files for the same devref.
        """
        from g_file_studio.engines.icon_upgrade_engine import parse_icon_definition

        rows: list[dict[str, object]] = []
        failures: list[str] = []
        by_devref: dict[str, str] = {}
        for raw_path in files:
            path = Path(raw_path)
            try:
                definition = parse_icon_definition(path)
            except Exception as exc:
                failures.append(f"{path.name}: 不是有效的标准图元 G（{exc}）")
                continue
            devref = f"#{definition.file_name}:{definition.element_id}"
            sha256 = self._file_sha256(path)
            previous = by_devref.get(devref.casefold())
            if previous and previous != sha256:
                failures.append(
                    f"{path.name}: 同一个图元 {devref} 在本次 ACTIVE 标准中出现多个不同文件版本；"
                    "请只保留一个，其他版本通过 Profile 历史版本保存。"
                )
                continue
            by_devref[devref.casefold()] = sha256
            rows.append({
                "devref": devref,
                "sha256": sha256,
                "original_name": path.name,
                "original_source": str(path.resolve(strict=False)),
                "managed_path": "",
                "element_tag": definition.element_tag,
                "element_id": definition.element_id,
                "width": float(definition.width),
                "height": float(definition.height),
                "align_center": [float(definition.align_center[0]), float(definition.align_center[1])],
                "pins": [[float(x), float(y)] for x, y in definition.pins],
                "pin_ids": [str(item) for item in definition.pin_ids],
                "pin_indices": [str(item) for item in definition.pin_indices],
            "standard_source": "server",
            })
        if failures:
            raise ValueError(
                "标准图元必须由有效的图元定义 G 文件提供，业务单线图不能作为标准。\n"
                + "\n".join(failures[:10])
            )
        if not rows:
            raise ValueError("未找到有效的标准图元 G 文件。")
        return _normalize_managed_standard_files(rows)

    def _materialize_standard_files(self, profile: SiteSmartProfile) -> SiteSmartProfile:
        records = _normalize_managed_standard_files(profile.managed_standard_files)
        if not records:
            profile.standard_fingerprint = ""
            return profile
        target_root = (
            _standard_library_root()
            / self._safe_name(profile.profile_name)
            / f"V{int(profile.profile_version)}"
        )
        target_root.mkdir(parents=True, exist_ok=True)
        materialized: list[dict[str, object]] = []
        for row in records:
            source_text = str(row.get("managed_path") or row.get("original_source") or "").strip()
            source = Path(source_text) if source_text else None
            name = self._safe_name(str(row.get("original_name") or Path(source_text).name or "symbol.g"))
            target = target_root / f"{str(row['sha256'])[:12]}_{name}"
            if source is not None and source.is_file():
                if not target.is_file() or self._file_sha256(target) != str(row["sha256"]):
                    shutil.copy2(source, target)
            if not target.is_file():
                # Existing profiles may already point to an earlier managed copy.
                existing = Path(str(row.get("managed_path") or ""))
                if existing.is_file() and self._file_sha256(existing) == str(row["sha256"]):
                    target = existing
                else:
                    raise ValueError(f"标准图元文件不存在，无法保存：{row.get('original_name') or row.get('devref')}")
            if self._file_sha256(target) != str(row["sha256"]):
                raise ValueError(f"标准图元文件内容已变化，拒绝保存：{target.name}")
            item = dict(row)
            item["managed_path"] = str(target.resolve(strict=False))
            item["relative_path"] = relative_path_from_record(item)
            materialized.append(item)
        profile.managed_standard_files = _normalize_managed_standard_files(materialized)
        profile.standard_fingerprint = _profile_standard_fingerprint(profile)
        return profile

    def _freeze_repository_version(self, profile: SiteSmartProfile) -> SiteSmartProfile:
        """Commit every standard G as an immutable local blob + version manifest.

        A formal version is not allowed to exist unless all referenced symbol bytes
        have been frozen and SHA256-verified locally.  This is independent of the
        read-only server and makes historical versions recoverable offline.
        """
        self.repository.commit_profile(profile)
        profile.managed_standard_files = _normalize_managed_standard_files(
            self.repository.hydrate_records(profile)
        )
        profile.standard_fingerprint = _profile_standard_fingerprint(profile)
        return profile

    def verify_version_repository(self, profile_name: str, version: int):
        profile = self.get_profile_version(profile_name, version)
        if profile is None:
            raise ValueError(f"Profile {profile_name} 不存在 V{version}。")
        return self.repository.verify_profile(profile, parse_metadata=True)

    def version_repository_details(self, profile_name: str, version: int) -> dict[str, object]:
        profile = self.get_profile_version(profile_name, version)
        if profile is None:
            raise ValueError(f"Profile {profile_name} 不存在 V{version}。")
        return self.repository.version_details(profile)

    def export_version_element(
        self, profile_name: str, version: int, destination: str | Path, *, zip_output: bool = False
    ) -> Path:
        profile = self.get_profile_version(profile_name, version)
        if profile is None:
            raise ValueError(f"Profile {profile_name} 不存在 V{version}。")
        # Export is reconstructed solely from immutable local objects.  Never use
        # the current server file with the same name as a historical substitute.
        return self.repository.export_profile(profile, destination, zip_output=zip_output)

    def validate_authoritative_standard(self, profile: SiteSmartProfile | None) -> tuple[bool, list[str]]:
        if profile is None:
            return False, ["尚未选择 ACTIVE 图元标准。"]
        issues: list[str] = []
        records = _normalize_managed_standard_files(self.repository.hydrate_records(profile))
        profile.managed_standard_files = records
        by_devref: dict[str, list[dict[str, object]]] = {}
        for row in records:
            by_devref.setdefault(str(row.get("devref", "")).casefold(), []).append(row)
        roles = [
            ("SMART / LBS", profile.smart_lbs_devref),
            ("SMART / Circuit Breaker", profile.smart_breaker_devref),
            ("SMART / 接地刀闸", profile.smart_ground_devref),
            ("NORMAL / LBS", profile.normal_lbs_devref),
            ("NORMAL / Circuit Breaker", profile.normal_breaker_devref),
            ("NORMAL / 接地刀闸", profile.normal_ground_devref),
        ]
        configured = 0
        for label, devref in roles:
            devref = str(devref or "").strip()
            if not devref:
                continue
            configured += 1
            matches = by_devref.get(devref.casefold(), [])
            if len(matches) != 1:
                issues.append(f"{label}: 必须且只能绑定 1 个服务器标准图元 G，当前 {len(matches)} 个。")
                continue
            row = matches[0]
            # The user-selected device role is authoritative. element_tag / file-name
            # inference is retained only as parsed metadata and never blocks binding.
            if not list(row.get("pins", [])):
                issues.append(f"{label}: 服务器标准图元没有可用 pin 定义，不能作为 RMU 电气设备标准。")
            managed = Path(str(row.get("managed_path") or ""))
            if not managed.is_file():
                issues.append(f"{label}: 持久化标准文件不存在：{managed}")
                continue
            try:
                current_hash = self._file_sha256(managed)
            except OSError:
                issues.append(f"{label}: 无法读取标准文件：{managed}")
                continue
            if current_hash != str(row.get("sha256", "")):
                issues.append(f"{label}: 标准文件 SHA256 已变化，必须重新上传确认。")
        for entry in profile.custom_symbols:
            if not bool(entry.get("enabled", True)):
                continue
            devref = str(entry.get("standard_devref", "")).strip()
            role = str(entry.get("role", "图元")).strip() or "图元"
            if not devref:
                issues.append(f"图元 {role}: 未指定标准图元 G。")
                continue
            configured += 1
            matches = by_devref.get(devref.casefold(), [])
            if len(matches) != 1:
                issues.append(f"图元 {role}: 必须且只能绑定 1 个服务器标准图元 G，当前 {len(matches)} 个。")
                continue
            row = matches[0]
            managed = Path(str(row.get("managed_path") or ""))
            if not managed.is_file():
                issues.append(f"图元 {role}: 持久化标准文件不存在：{managed}")
                continue
            try:
                current_hash = self._file_sha256(managed)
            except OSError:
                issues.append(f"图元 {role}: 无法读取标准文件：{managed}")
                continue
            if current_hash != str(row.get("sha256", "")):
                issues.append(f"图元 {role}: 标准文件 SHA256 已变化，必须重新上传确认。")

        if configured == 0:
            issues.append("当前标准尚未配置任何要检查的图元。")
        expected_fingerprint = _profile_standard_fingerprint(profile)
        if records and profile.standard_fingerprint and expected_fingerprint != profile.standard_fingerprint:
            issues.append("标准图元库指纹与 Profile 记录不一致。")
        return not issues, issues

    def _read_payload(self) -> dict[str, object]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def load_profiles(self) -> dict[str, SiteSmartProfile]:
        try:
            mtime_ns = self.path.stat().st_mtime_ns if self.path.is_file() else None
        except OSError:
            mtime_ns = None
        if self._profiles_cache is not None and mtime_ns == self._profiles_cache_mtime_ns:
            # Callers historically mutate the returned profile before an explicit
            # write.  Keep the same shallow-copy behavior while avoiding repeated
            # JSON parsing and normalization during one page refresh.
            return dict(self._profiles_cache)
        payload = self._read_payload()
        raw_profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
        profiles: dict[str, SiteSmartProfile] = {}
        if not isinstance(raw_profiles, dict):
            self._profiles_cache = profiles
            self._profiles_cache_mtime_ns = mtime_ns
            return profiles
        for _key, raw in raw_profiles.items():
            if not isinstance(raw, dict):
                continue
            try:
                profile = SiteSmartProfile(**raw).normalized()
            except (TypeError, ValueError):
                continue
            if profile.profile_name:
                profiles[profile.profile_name] = profile
        self._profiles_cache = profiles
        self._profiles_cache_mtime_ns = mtime_ns
        return profiles

    def _write(
        self,
        profiles: dict[str, SiteSmartProfile],
        *,
        global_selection: dict[str, object] | None = None,
    ) -> None:
        existing = self._read_payload()
        if global_selection is None:
            raw_selection = existing.get("global_selection", {})
            global_selection = dict(raw_selection) if isinstance(raw_selection, dict) else {}
        payload = {
            "version": 9,
            "global_selection": global_selection,
            "profiles": {
                name: asdict(profile.normalized())
                for name, profile in sorted(profiles.items(), key=lambda row: row[0].casefold())
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        # The next read must rebuild from the just-written JSON.  Do not keep
        # mutable profile objects alive across an explicit persistence boundary.
        self._profiles_cache = None
        self._profiles_cache_mtime_ns = None

    def get_global_profile_selection(self, *, auto_initialize: bool = True) -> tuple[str, int | None]:
        """Return the user-selected global execution standard.

        The selection is independent from the newest/editable Profile head. Creating
        V(N+1) therefore never silently switches downstream modules away from the
        version the user explicitly selected.  Existing installations with no saved
        selection are initialized once to the most recently saved current version.
        """
        payload = self._read_payload()
        raw = payload.get("global_selection", {}) if isinstance(payload, dict) else {}
        name = str(raw.get("profile_name", "") or "").strip() if isinstance(raw, dict) else ""
        try:
            version = int(raw.get("version")) if isinstance(raw, dict) and raw.get("version") is not None else None
        except (TypeError, ValueError):
            version = None
        if name and version is not None and self.get_profile_version(name, version) is not None:
            return name, version
        if not auto_initialize:
            return "", None
        profiles = self.load_profiles()
        if not profiles:
            return "", None
        name, profile = max(
            profiles.items(),
            key=lambda row: (str(getattr(row[1], "updated_at", "") or ""), row[0].casefold()),
        )
        version = int(profile.profile_version)
        self.set_global_profile_version(name, version, validate=False)
        return name, version

    def get_global_profile(self, *, auto_initialize: bool = True) -> SiteSmartProfile | None:
        name, version = self.get_global_profile_selection(auto_initialize=auto_initialize)
        if not name or version is None:
            return None
        return self.get_profile_version(name, version)

    def get_current_server_standard(self, *, auto_initialize: bool = False) -> SiteSmartProfile | None:
        """Return the one server standard explicitly applied by the user.

        Profile versions remain an internal persistence and rollback mechanism,
        but callers in the public workflow must use this method instead of
        selecting a version independently.  A server read/cache operation does
        not move this pointer; only the explicit manual-update action does.
        """
        return self.get_global_profile(auto_initialize=auto_initialize)

    def set_global_profile_version(self, profile_name: str, version: int, *, validate: bool = True) -> SiteSmartProfile:
        name = str(profile_name or "").strip()
        target = self.get_profile_version(name, int(version))
        if target is None:
            raise ValueError(f"Profile {name or '<空>'} 不存在 V{version}。")
        if validate:
            ready, issues = self.validate_authoritative_standard(target)
            if not ready:
                raise ValueError("该版本不能设为全局执行标准：" + "；".join(issues[:5]))
        self._write(
            self.load_profiles(),
            global_selection={
                "profile_name": name,
                "version": int(target.profile_version),
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        )
        return target

    @staticmethod
    def _device_signature(profile: SiteSmartProfile) -> tuple[str, ...]:
        # Geometry is part of the symbol standard too.  A vendor may replace the
        # icon body/port offsets while keeping the same devref name.
        geometry_json = json.dumps(
            _normalize_geometry_payload(profile.geometry_templates),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        custom_json = json.dumps(
            _normalize_custom_symbols(profile.custom_symbols),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return (
            profile.smart_lbs_devref,
            profile.smart_breaker_devref,
            profile.normal_lbs_devref,
            profile.normal_breaker_devref,
            profile.smart_ground_devref,
            profile.normal_ground_devref,
            geometry_json,
            custom_json,
            _standard_files_fingerprint(profile.managed_standard_files),
        )

    @staticmethod
    def _history_snapshot(profile: SiteSmartProfile) -> dict[str, object]:
        """Store a complete immutable version snapshot.

        v2.18.34 keeps candidate/confidence/geometry information in history so a
        profile can be audited and safely restored even when the vendor changes an
        icon without changing its devref string (for example only width/height or
        electrical anchor offsets change).
        """
        payload = asdict(profile.normalized())
        payload.pop("history", None)
        payload.pop("discovery_catalog", None)
        payload.pop("discovery_decisions", None)
        payload["version"] = profile.profile_version
        payload["profile_version"] = profile.profile_version
        payload["geometry_templates"] = _normalize_geometry_payload(profile.geometry_templates)
        payload["custom_symbols"] = _normalize_custom_symbols(profile.custom_symbols)
        payload["symbol_catalog"] = _normalize_symbol_catalog(profile.symbol_catalog)
        return payload

    @staticmethod
    def _profile_from_snapshot(current: SiteSmartProfile, snapshot: dict[str, object]) -> SiteSmartProfile:
        """Rebuild a historical version with backward compatibility for old snapshots."""
        raw = dict(snapshot)
        version = raw.pop("version", raw.get("profile_version", 1))
        raw.pop("history", None)
        values = {
            "profile_name": str(raw.get("profile_name", current.profile_name)),
            "site_name": str(raw.get("site_name", current.site_name)),
            "smart_lbs_devref": str(raw.get("smart_lbs_devref", "")),
            "smart_breaker_devref": str(raw.get("smart_breaker_devref", "")),
            "normal_lbs_devref": str(raw.get("normal_lbs_devref", "")),
            "normal_breaker_devref": str(raw.get("normal_breaker_devref", "")),
            "smart_ground_devref": str(raw.get("smart_ground_devref", "")),
            "normal_ground_devref": str(raw.get("normal_ground_devref", "")),
            "sample_files": list(raw.get("sample_files", [])) if isinstance(raw.get("sample_files", []), list) else [],
            "smart_rmu_count": int(raw.get("smart_rmu_count", 0) or 0),
            "normal_rmu_count": int(raw.get("normal_rmu_count", 0) or 0),
            "ignored_rmu_count": int(raw.get("ignored_rmu_count", 0) or 0),
            "lbs_observations": int(raw.get("lbs_observations", 0) or 0),
            "breaker_observations": int(raw.get("breaker_observations", 0) or 0),
            "normal_lbs_observations": int(raw.get("normal_lbs_observations", 0) or 0),
            "normal_breaker_observations": int(raw.get("normal_breaker_observations", 0) or 0),
            "ground_observations": int(raw.get("ground_observations", 0) or 0),
            "normal_ground_observations": int(raw.get("normal_ground_observations", 0) or 0),
            "lbs_confidence": float(raw.get("lbs_confidence", 0.0) or 0.0),
            "breaker_confidence": float(raw.get("breaker_confidence", 0.0) or 0.0),
            "normal_lbs_confidence": float(raw.get("normal_lbs_confidence", 0.0) or 0.0),
            "normal_breaker_confidence": float(raw.get("normal_breaker_confidence", 0.0) or 0.0),
            "ground_confidence": float(raw.get("ground_confidence", 0.0) or 0.0),
            "normal_ground_confidence": float(raw.get("normal_ground_confidence", 0.0) or 0.0),
            "lbs_candidates": dict(raw.get("lbs_candidates", {})) if isinstance(raw.get("lbs_candidates", {}), dict) else {},
            "breaker_candidates": dict(raw.get("breaker_candidates", {})) if isinstance(raw.get("breaker_candidates", {}), dict) else {},
            "normal_lbs_candidates": dict(raw.get("normal_lbs_candidates", {})) if isinstance(raw.get("normal_lbs_candidates", {}), dict) else {},
            "normal_breaker_candidates": dict(raw.get("normal_breaker_candidates", {})) if isinstance(raw.get("normal_breaker_candidates", {}), dict) else {},
            "ground_candidates": dict(raw.get("ground_candidates", {})) if isinstance(raw.get("ground_candidates", {}), dict) else {},
            "normal_ground_candidates": dict(raw.get("normal_ground_candidates", {})) if isinstance(raw.get("normal_ground_candidates", {}), dict) else {},
            "geometry_templates": _normalize_geometry_payload(raw.get("geometry_templates", {})),
            "custom_symbols": _normalize_custom_symbols(raw.get("custom_symbols", [])),
            "symbol_catalog": _normalize_symbol_catalog(raw.get("symbol_catalog", {})),
            "managed_standard_files": _normalize_managed_standard_files(raw.get("managed_standard_files", [])),
            "standard_fingerprint": str(raw.get("standard_fingerprint", "")),
            "locked": bool(raw.get("locked", False)),
            "discovery_catalog": _normalize_symbol_catalog(current.discovery_catalog),
            "discovery_decisions": _normalize_discovery_decisions(current.discovery_decisions),
            "profile_version": int(version or 1),
            "history": [],
            "updated_at": str(raw.get("updated_at", "")),
            "server_standard_revision": str(raw.get("server_standard_revision", "")),
        }
        return SiteSmartProfile(**values).normalized()

    def load_profile_versions(self, profile_name: str) -> list[SiteSmartProfile]:
        """Return archived versions followed by the current ACTIVE version."""
        current = self.load_profiles().get(str(profile_name).strip())
        if current is None:
            return []
        versions: list[SiteSmartProfile] = []
        for snapshot in current.history:
            try:
                versions.append(self._profile_from_snapshot(current, snapshot))
            except (TypeError, ValueError):
                continue
        versions.append(current)
        by_version: dict[int, SiteSmartProfile] = {}
        for item in versions:
            item.managed_standard_files = _normalize_managed_standard_files(self.repository.hydrate_records(item))
            by_version[item.profile_version] = item
        return [by_version[key] for key in sorted(by_version)]

    def get_profile_version(self, profile_name: str, version: int | None = None) -> SiteSmartProfile | None:
        current = self.load_profiles().get(str(profile_name).strip())
        if current is None:
            return None
        if version is None or int(version) == current.profile_version:
            current.managed_standard_files = _normalize_managed_standard_files(self.repository.hydrate_records(current))
            return current
        for item in self.load_profile_versions(profile_name):
            if item.profile_version == int(version):
                return item
        return None

    def restore_version(self, profile_name: str, version: int) -> SiteSmartProfile:
        """Restore an archived standard as a new ACTIVE version, preserving chronology."""
        name = str(profile_name).strip()
        current = self.load_profiles().get(name)
        if current is None:
            raise ValueError("Profile 不存在。")
        if current.locked:
            raise ValueError(f"当前 ACTIVE V{current.profile_version} 已锁定。请先解锁当前版本再恢复历史版本。")
        target = self.get_profile_version(name, version)
        if target is None:
            raise ValueError(f"Profile {name} 不存在 V{version}。")
        if target.profile_version == current.profile_version:
            return current
        target.profile_name = current.profile_name
        target.site_name = current.site_name
        target.history = list(current.history)
        # upsert sees a changed device/geometry signature and creates V(current+1).
        return self.upsert(target)

    def upsert(self, profile: SiteSmartProfile) -> SiteSmartProfile:
        profile = profile.normalized()
        if not profile.profile_name:
            raise ValueError("Profile Name 不能为空。")
        if not profile.site_name:
            raise ValueError("Site Name 不能为空。")
        if not profile.authoritative_ready:
            raise ValueError("请至少配置 1 个设备角色的标准图元 G。")

        profiles = self.load_profiles()
        old = profiles.get(profile.profile_name)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if old is not None:
            changed = self._device_signature(old) != self._device_signature(profile)
            if old.locked and (changed or old.site_name != profile.site_name):
                raise ValueError(
                    f"当前 ACTIVE V{old.profile_version} 已锁定，不能修改、上传或保存标准内容。请先解锁当前版本。"
                )
            # Saving an unchanged locked object is harmless, but never lets caller
            # silently clear the persisted lock bit. Unlock must go through set_locked().
            if old.locked:
                profile.locked = True
            profile.history = list(old.history)
            # Standard edits must not wipe the inspection discovery queue.
            if not profile.discovery_catalog:
                profile.discovery_catalog = dict(old.discovery_catalog)
            if not profile.discovery_decisions:
                profile.discovery_decisions = dict(old.discovery_decisions)
            if changed:
                # Freeze the old ACTIVE before it becomes historical.
                old = self._freeze_repository_version(old)
                profile.history.append(self._history_snapshot(old))
                profile.profile_version = old.profile_version + 1
            else:
                profile.profile_version = old.profile_version
            # v2.18.119: history is Git-like and intentionally unbounded; an old
            # standard version must remain recoverable regardless of age.
        else:
            profile.profile_version = max(1, profile.profile_version)
            profile.history = list(profile.history)
        profile.updated_at = now
        profile.server_standard_revision = _server_revision_label(now)
        profile = self._materialize_standard_files(profile)
        profile = self._freeze_repository_version(profile)
        profile = profile.normalized()
        profiles[profile.profile_name] = profile
        self._write(profiles)
        return profile


    def save_as_next_version(self, profile: SiteSmartProfile) -> SiteSmartProfile:
        """Persist an explicit fresh-rescan draft as V(N+1), even from a locked ACTIVE.

        The caller has already built a local draft from read-only business-G/server
        inputs.  This method never edits the saved current snapshot in place: it
        archives the current ACTIVE exactly as-is, writes the draft as a new unlocked
        ACTIVE version, and deliberately leaves the separately persisted GLOBAL
        execution pointer unchanged.
        """
        profile = profile.normalized()
        if not profile.profile_name:
            raise ValueError("Profile Name 不能为空。")
        if not profile.site_name:
            raise ValueError("Site Name 不能为空。")
        if not profile.authoritative_ready:
            raise ValueError("请至少配置 1 个设备角色的标准图元 G。")

        profiles = self.load_profiles()
        current = profiles.get(profile.profile_name)
        if current is None:
            # No history exists yet; normal upsert is the correct first-version path.
            return self.upsert(profile)

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        current = self._freeze_repository_version(current)
        profile.profile_name = current.profile_name
        profile.site_name = profile.site_name or current.site_name
        profile.history = list(current.history)
        profile.history.append(self._history_snapshot(current))
        profile.profile_version = int(current.profile_version) + 1
        profile.locked = False
        profile.updated_at = now
        profile.server_standard_revision = _server_revision_label(now)
        profile = self._materialize_standard_files(profile)
        profile = self._freeze_repository_version(profile)
        profile = profile.normalized()
        profiles[profile.profile_name] = profile
        self._write(profiles)
        return profile

    def create_next_version_from_server_records(
        self, profile_name: str, replacement_records: list[dict[str, object]]
    ) -> SiteSmartProfile:
        """Create V(N+1) from a locked/unlocked ACTIVE profile using server-cached symbols.

        This is the explicit safe path for a locked standard: the current locked
        ACTIVE version is first archived exactly as-is, then matching symbol files
        are replaced by basename in a new unlocked ACTIVE version. The remote server
        is never modified.
        """
        name = str(profile_name).strip()
        profiles = self.load_profiles()
        current = profiles.get(name)
        if current is None:
            raise ValueError("Profile 不存在。")
        replacements = _normalize_managed_standard_files(replacement_records)
        if not replacements:
            raise ValueError("没有可用于创建新版本的服务器标准图元。")
        replacement_by_name = {
            Path(str(row.get("original_name", "")).strip()).name.casefold(): dict(row)
            for row in replacements
            if Path(str(row.get("original_name", "")).strip()).name
        }
        if not replacement_by_name:
            raise ValueError("服务器标准图元缺少有效文件名。")

        current_records = [dict(row) for row in current.managed_standard_files]
        current_by_devref = {str(row.get("devref", "")).strip().casefold(): dict(row) for row in current_records}
        material_records: list[dict[str, object]] = []
        changed = False
        used_names: set[str] = set()
        old_to_new_devref: dict[str, str] = {}
        for row in current_records:
            key = Path(str(row.get("original_name", "")).strip()).name.casefold()
            replacement = replacement_by_name.get(key)
            if replacement is None:
                material_records.append(row)
                continue
            used_names.add(key)
            material_records.append(dict(replacement))
            old_devref = str(row.get("devref", "")).strip()
            new_devref = str(replacement.get("devref", "")).strip()
            if old_devref and new_devref:
                old_to_new_devref[old_devref.casefold()] = new_devref
            if str(row.get("sha256", "")).strip().lower() != str(replacement.get("sha256", "")).strip().lower():
                changed = True

        # A server-backed candidate may have been discovered after the old version
        # was saved. Add it only when an existing generic row explicitly references
        # that observed symbol filename.
        custom_symbols = [dict(row) for row in current.custom_symbols]
        referenced_names = {
            Path(str(row.get("observed_symbol_file", "")).strip()).name.casefold()
            for row in custom_symbols
            if Path(str(row.get("observed_symbol_file", "")).strip()).name
        }
        for key, replacement in replacement_by_name.items():
            if key not in used_names and key in referenced_names:
                material_records.append(dict(replacement))
                used_names.add(key)
                changed = True

        # Rebind generic rows to the replacement devref using observed filename first,
        # then the old standard devref for migrated legacy rows.
        for entry in custom_symbols:
            observed_name = Path(str(entry.get("observed_symbol_file", "")).strip()).name.casefold()
            replacement = replacement_by_name.get(observed_name) if observed_name else None
            if replacement is None:
                old_devref = str(entry.get("standard_devref", "")).strip()
                old_record = current_by_devref.get(old_devref.casefold()) if old_devref else None
                old_name = Path(str(old_record.get("original_name", "")).strip()).name.casefold() if old_record else ""
                replacement = replacement_by_name.get(old_name) if old_name else None
            if replacement is not None:
                new_devref = str(replacement.get("devref", "")).strip()
                if new_devref and new_devref != str(entry.get("standard_devref", "")).strip():
                    changed = True
                if new_devref:
                    entry["standard_devref"] = new_devref
                    entry["source_file"] = str(replacement.get("original_name", "")).strip()

        if not changed:
            raise ValueError("服务器图元与当前 ACTIVE 标准内容一致，无需创建新版本。")

        import copy
        next_profile = copy.deepcopy(current)
        current = self._freeze_repository_version(current)
        next_profile.history = list(current.history) + [self._history_snapshot(current)]
        next_profile.profile_version = current.profile_version + 1
        next_profile.locked = False
        next_profile.managed_standard_files = _normalize_managed_standard_files(material_records)
        next_profile.custom_symbols = _normalize_custom_symbols(custom_symbols)
        next_profile.symbol_catalog = _symbol_catalog_from_managed_standard_files(next_profile.managed_standard_files)
        next_profile.geometry_templates = {}

        def replace_role(value: str) -> str:
            text = str(value or "").strip()
            return old_to_new_devref.get(text.casefold(), text) if text else ""

        next_profile.smart_lbs_devref = replace_role(next_profile.smart_lbs_devref)
        next_profile.smart_breaker_devref = replace_role(next_profile.smart_breaker_devref)
        next_profile.normal_lbs_devref = replace_role(next_profile.normal_lbs_devref)
        next_profile.normal_breaker_devref = replace_role(next_profile.normal_breaker_devref)
        next_profile.smart_ground_devref = replace_role(next_profile.smart_ground_devref)
        next_profile.normal_ground_devref = replace_role(next_profile.normal_ground_devref)
        next_profile.sample_files = [
            str(row.get("original_name", "")).strip()
            for row in next_profile.managed_standard_files
            if str(row.get("original_name", "")).strip()
        ]
        next_profile.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        next_profile.server_standard_revision = _server_revision_label(next_profile.updated_at)
        next_profile = self._materialize_standard_files(next_profile.normalized())
        next_profile = self._freeze_repository_version(next_profile).normalized()
        profiles[name] = next_profile
        self._write(profiles)
        return next_profile

    def set_locked(self, profile_name: str, locked: bool) -> SiteSmartProfile:
        """Lock/unlock the current ACTIVE version without creating a new version."""
        name = str(profile_name).strip()
        profiles = self.load_profiles()
        profile = profiles.get(name)
        if profile is None:
            raise ValueError("Profile 不存在。")
        profile.locked = bool(locked)
        profiles[name] = profile.normalized()
        self._write(profiles)
        return profiles[name]



    def update_discovery_metadata(
        self,
        profile_name: str,
        *,
        catalog: dict[str, dict[str, object]] | None = None,
        decisions: dict[str, str] | None = None,
    ) -> SiteSmartProfile | None:
        """Persist inspection discovery metadata without creating a new standard version."""
        name = str(profile_name).strip()
        profiles = self.load_profiles()
        profile = profiles.get(name)
        if profile is None:
            return None
        if catalog is not None:
            merged = dict(profile.discovery_catalog)
            for devref, row in _normalize_symbol_catalog(catalog).items():
                current = dict(merged.get(devref, {}))
                current.update(row)
                merged[devref] = current
            profile.discovery_catalog = _normalize_symbol_catalog(merged)
        if decisions is not None:
            profile.discovery_decisions = _normalize_discovery_decisions(decisions)
        # Discovery acknowledgement is UI metadata; it must not change the standard's last-saved timestamp.
        profiles[name] = profile.normalized()
        self._write(profiles)
        return profiles[name]

    def delete_archived_version(self, profile_name: str, version: int) -> SiteSmartProfile:
        """Delete exactly one ARCHIVED version while preserving every other version.

        ACTIVE and GLOBAL versions are protected. The selected historical snapshot
        is removed from reachable Profile history and its Manifest is moved to the
        repository deletion archive. Content-addressed objects are never garbage
        collected automatically.
        """
        name = str(profile_name or "").strip()
        target_version = int(version)
        profiles = self.load_profiles()
        current = profiles.get(name)
        if current is None:
            raise ValueError("Profile 不存在。")
        if target_version == int(current.profile_version):
            raise ValueError("当前 ACTIVE 版本不能作为历史版本删除。请先创建/恢复新的 ACTIVE 版本。")
        global_name, global_version = self.get_global_profile_selection(auto_initialize=False)
        if name == global_name and global_version == target_version:
            raise ValueError("当前 GLOBAL 全局执行版本不能删除。请先将其他版本设为全局版本。")

        original_history = list(current.history)
        kept: list[dict[str, object]] = []
        found = False
        for snapshot in original_history:
            if not isinstance(snapshot, dict):
                kept.append(snapshot)
                continue
            raw_version = snapshot.get("version", snapshot.get("profile_version", 0))
            try:
                snapshot_version = int(raw_version or 0)
            except (TypeError, ValueError):
                snapshot_version = 0
            if snapshot_version == target_version:
                found = True
                continue
            kept.append(snapshot)
        if not found:
            raise ValueError(f"Profile {name} 不存在 ARCHIVED V{target_version}。")

        current.history = kept
        profiles[name] = current.normalized()
        self._write(profiles)
        try:
            self.repository.archive_deleted_manifest(name, target_version)
        except Exception as exc:
            current.history = original_history
            profiles[name] = current.normalized()
            self._write(profiles)
            raise ValueError(f"删除历史版本失败，已自动回滚：{exc}") from exc
        return profiles[name]

    def remove(self, profile_name: str) -> None:
        name = str(profile_name).strip()
        profiles = self.load_profiles()
        profile = profiles.get(name)
        if profile is not None and profile.locked:
            raise ValueError(f"当前 ACTIVE V{profile.profile_version} 已锁定。请先解锁后再删除标准。")
        if name in profiles:
            del profiles[name]
            self._write(profiles)
