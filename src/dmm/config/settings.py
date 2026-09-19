from __future__ import annotations

import copy
import json

from dmm.config.defaults import (
    DEFAULT_NAME_POSITIONS,
    DEFAULT_RMU_NAME_POSITIONS,
    DEFAULT_SETTINGS,
)
from dmm.infrastructure.filesystem.workspace import (
    CONFIG_PATH,
    ensure_workspace,
    load_user_element_catalog,
    save_user_element_catalog,
)


def load_settings() -> dict:
    settings = copy.deepcopy(DEFAULT_SETTINGS)

    if not CONFIG_PATH.exists():
        return settings

    try:
        saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return settings

    for key, value in saved.items():
        if key == "db" and isinstance(value, dict):
            settings["db"].update(value)
        elif key == "ssh" and isinstance(value, dict):
            settings["ssh"].update(value)
        elif key == "rmu_name_positions" and isinstance(value, dict):
            settings["rmu_name_positions"].update(value)
        elif key == "feeder_rmu_name_positions" and isinstance(value, dict):
            settings["feeder_rmu_name_positions"].update(value)
        else:
            settings[key] = value

    # Migrate the previous Jeddah/top-only default to the Makkah/right-side
    # default once. An explicit custom RMU direction is preserved.
    if (
        not bool(settings.get("rmu_name_positions_custom", False))
        and settings.get("rmu_name_positions") == DEFAULT_NAME_POSITIONS
    ):
        settings["rmu_name_positions"] = dict(DEFAULT_RMU_NAME_POSITIONS)

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

    return settings


def save_settings(settings: dict) -> None:
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
