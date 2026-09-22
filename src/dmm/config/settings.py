from __future__ import annotations

import copy
import json

from dmm.config.defaults import DEFAULT_SETTINGS
from dmm.infrastructure.filesystem.workspace import (
    CONFIG_PATH,
    ensure_workspace,
    load_user_element_catalog,
    save_user_element_catalog,
)
from dmm.infrastructure.remote.central_config import (
    CentralConfigClient,
    CentralConfigError,
    local_machine_info,
    make_machine_id,
)


def _central_bootstrap(settings: dict) -> dict:
    """Resolve the central-config connection without requiring local setup."""
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


def _merge_central_bundle(settings: dict, bundle: dict) -> dict:
    instance = dict(bundle.get("instance", {}) or {})
    database = dict(bundle.get("database", {}) or {})
    file_server = dict(bundle.get("file_server", {}) or {})
    element_marks = dict(bundle.get("element_marks", {}) or {})

    db_settings = database.get("settings")
    if isinstance(db_settings, dict):
        settings["db"].update(db_settings)

    server_settings = file_server.get("settings")
    if isinstance(server_settings, dict):
        settings["ssh"].update(server_settings)

    records = element_marks.get("records")
    if isinstance(records, list):
        existing_catalog = dict(settings.get("element_catalog", {}) or {})
        settings["element_catalog"] = {
            "remote_directory": existing_catalog.get(
                "remote_directory",
                settings["ssh"].get("element_directory", ""),
            ),
            "records": records,
        }

    settings["_central_sync"] = {
        "status": "ACTIVE" if instance.get("admin_status") == "active" else "UNASSIGNED",
        "message": "中央配置已同步",
        "admin_status": instance.get("admin_status", ""),
        "admin_machine_id": instance.get("admin_machine_id"),
        "admin_machine_name": instance.get("admin_machine_name"),
        "admin_ip": instance.get("admin_ip"),
        "admin_claimed_at": instance.get("admin_claimed_at"),
        "last_admin": instance.get("last_admin"),
        "config_version": instance.get("config_version", 0),
        "updated_at": instance.get("updated_at"),
    }
    return settings


def sync_central_settings(settings: dict, *, raise_on_error=False) -> dict:
    """Load the central bundle into settings, retaining local values offline."""
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
            _set_central_status(
                settings,
                "UNINITIALIZED",
                "中央同步文件为空；请由当前 Admin 重新初始化。"
                if files_empty and instance.get("admin_machine_id")
                else "中央配置尚未初始化，请由 Admin 完成首次初始化",
                admin_status=instance.get("admin_status", ""),
                admin_machine_id=instance.get("admin_machine_id"),
                admin_machine_name=instance.get("admin_machine_name"),
                admin_ip=instance.get("admin_ip"),
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
    with CentralConfigClient(central) as client:
        version = client.publish(settings, machine_id, machine_name, machine_ip)
    _set_central_status(
        settings,
        "ACTIVE",
        f"中央配置已发布，版本 {version}",
    )
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
    with CentralConfigClient(central) as client:
        version = client.release_admin(machine_id, machine_name)
    _set_central_status(settings, "UNASSIGNED", f"Admin 权限已释放，版本 {version}")
    settings["_central_sync"].update(
        {
            "admin_status": "unassigned",
            "admin_machine_id": None,
            "admin_machine_name": None,
            "admin_ip": None,
            "config_version": version,
        }
    )
    return version


def load_settings(*, sync_central=False) -> dict:
    settings = copy.deepcopy(DEFAULT_SETTINGS)

    saved = {}
    if CONFIG_PATH.exists():
        try:
            candidate = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(candidate, dict):
                saved = candidate
        except Exception:
            saved = {}

    for key, value in saved.items():
        if key == "db" and isinstance(value, dict):
            settings["db"].update(value)
        elif key == "ssh" and isinstance(value, dict):
            settings["ssh"].update(value)
        elif key == "rmu_name_positions" and isinstance(value, dict):
            settings["rmu_name_positions"].update(value)
        else:
            settings[key] = value

    # Element classifications are user preferences, not application files.
    # Prefer the user-level cache so replacing/deleting the program directory
    # does not erase the last saved catalog.  Migrate an older workspace-only
    # catalog the first time it is found.
    saved_catalog = settings.get("element_catalog")
    user_catalog = load_user_element_catalog()
    if isinstance(user_catalog, dict) and isinstance(
        user_catalog.get("records"), list
    ):
        settings["element_catalog"] = user_catalog
    elif isinstance(saved_catalog, dict) and isinstance(
        saved_catalog.get("records"), list
    ) and saved_catalog.get("records"):
        try:
            save_user_element_catalog(saved_catalog)
        except OSError:
            pass

    # The project has a fixed default Oracle password.
    # If an older workspace config saved an empty password, fall back to default.
    if not str(settings.get("db", {}).get("password", "")).strip():
        settings["db"]["password"] = DEFAULT_SETTINGS["db"]["password"]

    if not str(settings.get("machine_id") or "").strip():
        settings["machine_id"] = make_machine_id()

    # v3.0.23 data-rule migration:
    # BusDis / dms_bs_device uses Table ID 13506 and Domain 1.
    # Older versions stored Domain 0 in workspace/config.json.  Migrate that
    # legacy value automatically so an upgrade does not silently keep using
    # the incorrect KeyID rule.
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

    if sync_central:
        sync_central_settings(settings)

    return settings


def save_settings(settings: dict, *, publish_central=False) -> None:
    ensure_workspace()
    CONFIG_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    catalog = settings.get("element_catalog")
    if isinstance(catalog, dict) and isinstance(catalog.get("records"), list):
        try:
            save_user_element_catalog(catalog)
        except OSError:
            # The workspace copy remains available if the user profile is
            # temporarily read-only or unavailable.
            pass

    if publish_central:
        publish_central_settings(settings)
