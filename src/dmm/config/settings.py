from __future__ import annotations

import copy
import json

from dmm.config.defaults import DEFAULT_MASTER_STATION_RULES, DEFAULT_SETTINGS
from dmm.infrastructure.filesystem.workspace import (
    CONFIG_PATH,
    ensure_workspace,
    load_user_element_catalog,
    load_user_settings_cache,
    save_user_element_catalog,
    save_user_settings_cache,
)
from dmm.infrastructure.remote.central_config import (
    CentralConfigClient,
    CentralConfigError,
    local_machine_info,
    make_machine_id,
)


_LOCAL_ONLY_MESSAGE = (
    "当前仅使用本机缓存；软件启动不会访问中央配置。"
    "只有手动点击【连接并同步中央配置】才会读取并覆盖本机共享配置缓存。"
)


def _central_bootstrap(settings: dict) -> dict:
    """Resolve the central-config connection without performing network I/O."""
    central = dict(settings.get("central_config", {}) or {})
    ssh = dict(settings.get("ssh", {}) or {})
    for key in ("host", "port", "username", "password"):
        if not str(central.get(key, "") or "").strip() and ssh.get(key) is not None:
            central[key] = ssh[key]
    central.setdefault(
        "remote_directory",
        "/home/up8000/nari-international/distribution-model-manager/config",
    )
    central.setdefault("enabled", True)
    return central


def _set_central_status(
    settings: dict, status: str, message: str = "", **metadata
):
    settings["_central_sync"] = {
        "status": str(status),
        "message": str(message),
        **metadata,
    }


def _merge_local_payload(settings: dict, saved: dict) -> None:
    """Merge a local cache without ever contacting a remote service."""
    if not isinstance(saved, dict):
        return
    for key, value in saved.items():
        # Sync state is runtime information.  Never restore a stale ACTIVE
        # state on next launch because that would make the UI look connected
        # without actually reading the central repository.
        if key == "_central_sync":
            continue
        if key in {"db", "ssh", "central_config", "rmu_name_positions"} and isinstance(value, dict):
            current = settings.setdefault(key, {})
            if isinstance(current, dict):
                current.update(value)
            else:
                settings[key] = copy.deepcopy(value)
        else:
            settings[key] = copy.deepcopy(value)


def _enforce_fixed_master_station_rules(settings: dict) -> None:
    """Force fixed Jeddah master-station table/domain mappings.

    Older releases allowed these values to be edited and cached locally.  Keep
    the association module untouched and sanitize configuration centrally so
    stale user/workspace values can no longer alter runtime behavior.
    """
    settings["master_station_rules"] = copy.deepcopy(DEFAULT_MASTER_STATION_RULES)


def _persistent_payload(settings: dict) -> dict:
    """Return local settings only; runtime central-sync state is not persisted."""
    payload = copy.deepcopy(settings)
    payload.pop("_central_sync", None)
    return payload


def _merge_central_bundle(settings: dict, bundle: dict) -> dict:
    """Replace the locally cached shared settings with an explicit central pull."""
    instance = dict(bundle.get("instance", {}) or {})
    database = dict(bundle.get("database", {}) or {})
    file_server = dict(bundle.get("file_server", {}) or {})
    element_marks = dict(bundle.get("element_marks", {}) or {})

    # Manual central sync is authoritative for the shared configuration.
    # Rebuild from application defaults first so removed/omitted local values
    # do not survive a central pull by accident.
    db_settings = database.get("settings")
    if isinstance(db_settings, dict):
        settings["db"] = copy.deepcopy(DEFAULT_SETTINGS["db"])
        settings["db"].update(db_settings)

    server_settings = file_server.get("settings")
    if isinstance(server_settings, dict):
        settings["ssh"] = copy.deepcopy(DEFAULT_SETTINGS["ssh"])
        settings["ssh"].update(server_settings)

    records = element_marks.get("records")
    if isinstance(records, list):
        settings["element_catalog"] = {
            "remote_directory": str(
                settings.get("ssh", {}).get("element_directory", "") or ""
            ),
            "records": copy.deepcopy(records),
        }

    settings["_central_sync"] = {
        "status": "ACTIVE" if instance.get("admin_status") == "active" else "UNASSIGNED",
        "message": "中央配置已手动同步，并已覆盖本机共享配置缓存",
        "admin_status": instance.get("admin_status", ""),
        "admin_machine_id": instance.get("admin_machine_id"),
        "admin_machine_name": instance.get("admin_machine_name"),
        "admin_ip": instance.get("admin_ip"),
        "admin_claimed_at": instance.get("admin_claimed_at"),
        "admin_epoch": int(instance.get("admin_epoch", 0) or 0),
        "last_admin": instance.get("last_admin"),
        "config_version": instance.get("config_version", 0),
        "updated_at": instance.get("updated_at"),
    }
    return settings


def sync_central_settings(settings: dict, *, raise_on_error=False) -> dict:
    """Explicitly load the central bundle and replace the local shared cache.

    This function performs network I/O and is intended only for an explicit
    user action such as clicking ``连接并同步中央配置``.  Application startup
    never calls it in v4.1.45.
    """
    central = _central_bootstrap(settings)
    settings["central_config"] = central
    if not bool(central.get("enabled", True)):
        _set_central_status(settings, "DISABLED", "中央配置同步已关闭")
        return settings

    try:
        with CentralConfigClient(central) as client:
            bundle = client.read_bundle()
        if not bundle:
            _set_central_status(
                settings,
                "UNINITIALIZED",
                "中央配置尚未初始化，请先在一台机器上完成 Admin 初始化",
            )
        elif not bool(bundle.get("instance", {}).get("initialized")):
            instance = dict(bundle.get("instance", {}) or {})
            files_empty = bool(instance.get("central_files_empty"))
            admin_active = str(instance.get("admin_status") or "").lower() == "active"
            _set_central_status(
                settings,
                "ACTIVE" if admin_active else "UNINITIALIZED",
                (
                    "Admin 已认领；中央共享配置尚未发布。"
                    if admin_active
                    else (
                        "中央同步文件为空；请先抢占 Admin 后重新发布。"
                        if files_empty and instance.get("admin_machine_id")
                        else "中央配置尚未初始化；请先抢占 Admin，再发布当前本机配置。"
                    )
                ),
                initialized=False,
                admin_status=instance.get("admin_status", ""),
                admin_machine_id=instance.get("admin_machine_id"),
                admin_machine_name=instance.get("admin_machine_name"),
                admin_ip=instance.get("admin_ip"),
                admin_epoch=int(instance.get("admin_epoch", 0) or 0),
                config_version=instance.get("config_version", 0),
            )
        else:
            _merge_central_bundle(settings, bundle)
    except Exception as exc:
        _set_central_status(settings, "OFFLINE", f"中央配置暂时不可用：{exc}")
        if raise_on_error:
            raise
    return settings


def publish_central_settings(settings: dict) -> int:
    """Publish current local settings when this machine is the Admin."""
    central = _central_bootstrap(settings)
    machine_id = str(settings.get("machine_id") or "").strip()
    if not machine_id:
        machine_id = make_machine_id()
        settings["machine_id"] = machine_id
    machine_name, machine_ip = local_machine_info(central.get("host", ""))
    expected_epoch = int(
        (settings.get("_central_sync", {}) or {}).get("admin_epoch", 0) or 0
    ) or None
    with CentralConfigClient(central) as client:
        version = client.publish(
            settings, machine_id, machine_name, machine_ip, expected_epoch
        )
    _set_central_status(
        settings,
        "ACTIVE",
        f"中央配置已手动发布，版本 {version}",
    )
    settings["_central_sync"].update(
        {
            "admin_status": "active",
            "admin_machine_id": machine_id,
            "admin_machine_name": machine_name,
            "admin_ip": machine_ip,
            "admin_epoch": int(expected_epoch or 0),
            "config_version": version,
        }
    )
    return version


def read_central_admin_state(settings: dict) -> dict:
    """Read only instance.json; never pull shared business configuration."""
    central = _central_bootstrap(settings)
    if not bool(central.get("enabled", True)):
        return {"status": "DISABLED", "message": "中央配置同步已关闭"}
    with CentralConfigClient(central) as client:
        instance = client.read_admin_state()
    if not instance:
        return {
            "status": "UNINITIALIZED",
            "message": "中央配置尚未初始化。",
            "initialized": False,
            "admin_status": "unassigned",
            "admin_epoch": 0,
        }
    admin_active = str(instance.get("admin_status") or "").lower() == "active"
    return {
        "status": "ACTIVE" if admin_active else (
            "UNASSIGNED" if bool(instance.get("initialized")) else "UNINITIALIZED"
        ),
        "message": "仅检查 Admin 所有权；未同步数据库、服务器或图元配置。",
        "initialized": bool(instance.get("initialized")),
        "admin_status": instance.get("admin_status", ""),
        "admin_machine_id": instance.get("admin_machine_id"),
        "admin_machine_name": instance.get("admin_machine_name"),
        "admin_ip": instance.get("admin_ip"),
        "admin_claimed_at": instance.get("admin_claimed_at"),
        "admin_epoch": int(instance.get("admin_epoch", 0) or 0),
        "config_version": int(instance.get("config_version", 0) or 0),
        "updated_at": instance.get("updated_at"),
        "last_admin": instance.get("last_admin"),
    }


def takeover_central_admin(settings: dict) -> int:
    """Atomically take over Admin ownership without syncing/publishing config."""
    central = _central_bootstrap(settings)
    settings["central_config"] = central
    machine_id = str(settings.get("machine_id") or "").strip()
    if not machine_id:
        machine_id = make_machine_id()
        settings["machine_id"] = machine_id
    machine_name, machine_ip = local_machine_info(central.get("host", ""))
    with CentralConfigClient(central) as client:
        instance = client.claim_admin(machine_id, machine_name, machine_ip)
    epoch = int(instance.get("admin_epoch", 0) or 0)
    _set_central_status(
        settings,
        "ACTIVE",
        "当前机器已抢占 Admin；未自动同步或发布任何共享配置。",
        initialized=bool(instance.get("initialized")),
        admin_status="active",
        admin_machine_id=machine_id,
        admin_machine_name=machine_name,
        admin_ip=machine_ip,
        admin_claimed_at=instance.get("admin_claimed_at"),
        admin_epoch=epoch,
        config_version=int(instance.get("config_version", 0) or 0),
        updated_at=instance.get("updated_at"),
        last_admin=instance.get("last_admin"),
    )
    return epoch


def initialize_central_settings(settings: dict) -> int:
    """Claim Admin and create central config files for the first time."""
    central = _central_bootstrap(settings)
    machine_id = str(settings.get("machine_id") or "").strip()
    if not machine_id:
        machine_id = make_machine_id()
        settings["machine_id"] = machine_id
    machine_name, machine_ip = local_machine_info(central.get("host", ""))
    with CentralConfigClient(central) as client:
        version = client.initialize(settings, machine_id, machine_name, machine_ip)
    _set_central_status(settings, "ACTIVE", f"已完成 Admin 初始化，版本 {version}")
    settings["_central_sync"].update(
        {
            "admin_status": "active",
            "admin_machine_id": machine_id,
            "admin_machine_name": machine_name,
            "admin_ip": machine_ip,
            "config_version": version,
        }
    )
    return version


def release_central_admin(settings: dict) -> int:
    """Release only the current machine's Admin role."""
    central = _central_bootstrap(settings)
    machine_id = str(settings.get("machine_id") or "").strip()
    if not machine_id:
        raise CentralConfigError("当前机器没有有效的机器标识。")
    machine_name, _machine_ip = local_machine_info(central.get("host", ""))
    expected_epoch = int(
        (settings.get("_central_sync", {}) or {}).get("admin_epoch", 0) or 0
    ) or None
    with CentralConfigClient(central) as client:
        version = client.release_admin(machine_id, machine_name, expected_epoch)
    _set_central_status(settings, "UNASSIGNED", f"Admin 权限已释放，版本 {version}")
    settings["_central_sync"].update(
        {
            "admin_status": "unassigned",
            "admin_machine_id": None,
            "admin_machine_name": None,
            "admin_ip": None,
            "admin_epoch": int(expected_epoch or 0) + 1,
            "config_version": version,
        }
    )
    return version


def load_settings(*, sync_central=False) -> dict:
    """Load settings from local defaults/cache only unless explicitly synced.

    Startup uses ``sync_central=False``.  Missing local cache therefore falls
    back to the bundled defaults rather than contacting Oracle/SSH/central
    services.  ``sync_central=True`` remains available only for explicit code
    paths/tests; the main window never uses it during application launch.
    """
    settings = copy.deepcopy(DEFAULT_SETTINGS)

    # Legacy workspace config is read first so existing installations migrate
    # seamlessly.  The per-user cache is authoritative when both exist and
    # survives replacement of the application directory.
    workspace_saved = {}
    if CONFIG_PATH.exists():
        try:
            candidate = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                workspace_saved = candidate
        except Exception:
            workspace_saved = {}
    _merge_local_payload(settings, workspace_saved)

    user_saved = load_user_settings_cache()
    if isinstance(user_saved, dict):
        _merge_local_payload(settings, user_saved)


    # v4.1.85: master-station table/domain mappings are fixed engineering rules.
    # Ignore stale editable values saved by older versions.
    _enforce_fixed_master_station_rules(settings)

    # Backward compatibility with the older dedicated element-mark cache.
    # A complete user settings cache wins; otherwise migrate the old catalog.
    saved_catalog = settings.get("element_catalog")
    user_catalog = load_user_element_catalog()
    user_cache_has_catalog = isinstance(user_saved, dict) and isinstance(
        user_saved.get("element_catalog"), dict
    )
    if (
        not user_cache_has_catalog
        and isinstance(user_catalog, dict)
        and isinstance(user_catalog.get("records"), list)
    ):
        settings["element_catalog"] = user_catalog
    elif isinstance(saved_catalog, dict) and isinstance(
        saved_catalog.get("records"), list
    ) and saved_catalog.get("records"):
        try:
            save_user_element_catalog(saved_catalog)
        except OSError:
            pass

    # The project has a fixed default Oracle password.  If an older local
    # cache saved an empty password, fall back to the bundled local default.
    if not str(settings.get("db", {}).get("password", "")).strip():
        settings["db"]["password"] = DEFAULT_SETTINGS["db"]["password"]

    if not str(settings.get("machine_id") or "").strip():
        settings["machine_id"] = make_machine_id()

    # v3.0.23 data-rule migration:
    # BusDis / dms_bs_device uses Table ID 13506 and Domain 1.
    device_rules = settings.get("device_rules")
    if isinstance(device_rules, dict):
        bus_rule = device_rules.get("BusDis")
        if isinstance(bus_rule, dict):
            try:
                table_id = int(bus_rule.get("table_id", 13506))
                domain = int(bus_rule.get("domain", 1))
            except (TypeError, ValueError):
                table_id = 13506
                domain = 1

            if table_id == 13506 and domain == 0:
                bus_rule["domain"] = 1

    # Never present a stale remote state on launch.  No connection is made.
    _set_central_status(settings, "LOCAL_ONLY", _LOCAL_ONLY_MESSAGE)

    # Persist/migrate the effective local values (including machine_id) to the
    # per-user cache.  This is local file I/O only.
    try:
        save_user_settings_cache(_persistent_payload(settings))
    except OSError:
        pass

    if sync_central:
        sync_central_settings(settings)

    return settings


def save_settings(settings: dict, *, publish_central=False) -> None:
    """Save locally; remote publish happens only when explicitly requested."""
    payload = _persistent_payload(settings)

    # The per-user cache is the primary persistent copy because it survives a
    # replacement of the application folder.  Keep workspace/config.json as a
    # compatible secondary copy for existing deployments and diagnostics.
    user_cache_saved = False
    try:
        save_user_settings_cache(payload)
        user_cache_saved = True
    except OSError:
        pass

    try:
        ensure_workspace()
        CONFIG_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        if not user_cache_saved:
            raise

    catalog = settings.get("element_catalog")
    if isinstance(catalog, dict) and isinstance(catalog.get("records"), list):
        try:
            save_user_element_catalog(catalog)
        except OSError:
            pass

    # Kept for API compatibility.  No normal save path passes True in v4.1.45;
    # an explicit caller still counts as a manual publish request.
    if publish_central:
        publish_central_settings(settings)
