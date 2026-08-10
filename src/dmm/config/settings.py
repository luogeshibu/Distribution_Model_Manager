from __future__ import annotations

import copy
import json

from dmm.config.defaults import DEFAULT_SETTINGS
from dmm.infrastructure.filesystem.workspace import CONFIG_PATH, ensure_workspace


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
        elif key == "rmu_name_positions" and isinstance(value, dict):
            settings["rmu_name_positions"].update(value)
        else:
            settings[key] = value

    # The project has a fixed default Oracle password.
    # If an older workspace config saved an empty password, fall back to default.
    if not str(settings.get("db", {}).get("password", "")).strip():
        settings["db"]["password"] = DEFAULT_SETTINGS["db"]["password"]

    return settings


def save_settings(settings: dict) -> None:
    ensure_workspace()
    CONFIG_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
