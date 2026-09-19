from __future__ import annotations

import shutil
import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

from dmm.config.constants import WORKSPACE_RETENTION_DAYS


def application_root() -> Path:
    """
    Return the application-owned root directory.

    Development/source mode:
        <project root>/

        Example:
        D:/Workspace/Python/Distribution_Model_Manager/

    Packaged EXE mode:
        <directory containing the EXE>/

    Runtime output must never be created inside src/dmm/.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # This file is:
    # <project>/src/dmm/infrastructure/filesystem/workspace.py
    #
    # parents[0] = filesystem
    # parents[1] = infrastructure
    # parents[2] = dmm
    # parents[3] = src
    # parents[4] = project root
    return Path(__file__).resolve().parents[4]


APP_ROOT = application_root()
WORKSPACE_ROOT = APP_ROOT / "workspace"
CONFIG_PATH = WORKSPACE_ROOT / "config.json"
RUNS_ROOT = WORKSPACE_ROOT / "runs"
LOGS_ROOT = WORKSPACE_ROOT / "logs"


def user_data_root() -> Path:
    """Return a per-Windows-user location that survives app replacement."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or (
            Path.home() / "AppData" / "Roaming"
        )
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or (
            Path.home() / ".config"
        )
    return Path(base) / "DistributionModelManager"


USER_ELEMENT_CATALOG_PATH = user_data_root() / "element_catalog.json"


def ensure_user_data():
    USER_ELEMENT_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_user_element_catalog() -> dict | None:
    """Load user-level element marks, independent of the app directory."""
    try:
        payload = json.loads(
            USER_ELEMENT_CATALOG_PATH.read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def save_user_element_catalog(catalog: dict) -> None:
    """Persist only element marks outside the replaceable app directory."""
    if not isinstance(catalog, dict):
        return
    ensure_user_data()
    USER_ELEMENT_CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ensure_workspace():
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)


def cleanup_workspace(retention_days=WORKSPACE_RETENTION_DAYS):
    ensure_workspace()
    cutoff = datetime.now() - timedelta(days=retention_days)

    for item in RUNS_ROOT.iterdir():
        if item.is_dir():
            try:
                if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                    shutil.rmtree(item, ignore_errors=True)
            except Exception:
                pass

    for item in LOGS_ROOT.glob("*.log"):
        try:
            if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                item.unlink(missing_ok=True)
        except Exception:
            pass


def create_run_directory():
    ensure_workspace()
    cleanup_workspace()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUNS_ROOT / stamp

    if run_dir.exists():
        index = 2
        while (RUNS_ROOT / f"{stamp}_{index}").exists():
            index += 1
        run_dir = RUNS_ROOT / f"{stamp}_{index}"

    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "g_output").mkdir(parents=True, exist_ok=True)
    (run_dir / "report").mkdir(parents=True, exist_ok=True)
    return run_dir


def database_log_path():
    ensure_workspace()
    return LOGS_ROOT / f"database_{datetime.now():%Y%m%d}.log"


def append_database_log(message):
    ensure_workspace()
    cleanup_workspace()

    with database_log_path().open("a", encoding="utf-8") as file:
        file.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
