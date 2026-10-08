from __future__ import annotations

import sys
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir


def project_root() -> Path:
    """可写项目根目录；打包后为 EXE 所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve()
    # Standalone GFileStudio lives at <project>/g_file_studio/... while the
    # merged DMM v4.2.0 embeds it at <project>/src/g_file_studio/....
    # Resolve both layouts without changing the graphics engines.
    candidate = here.parents[2]
    if candidate.name.lower() == "src":
        return here.parents[3]
    return candidate


def resource_root() -> Path:
    """只读资源根目录；兼容 PyInstaller one-dir / one-file。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return project_root()


def resource_path(relative_path: str | Path) -> Path:
    """返回源码运行或 PyInstaller 打包后的资源绝对路径。"""
    return resource_root() / Path(relative_path)




def app_config_root() -> Path:
    """Return the per-user configuration root without creating it.

    Startup/read paths are side-effect free.  A directory is created only by an
    explicit persistence operation such as Save, Import or manual Central Sync.
    """
    return Path(user_config_dir("GFileStudio", "NARI")) / "Config"


def app_cache_root() -> Path:
    """Return the per-user cache root without creating it."""
    return Path(user_cache_dir("GFileStudio", "NARI"))


def app_data_root() -> Path:
    """Return the per-user persistent-data root without creating it."""
    return Path(user_data_dir("GFileStudio", "NARI"))

def default_workspace() -> Path:
    return project_root() / "workspace"


def ensure_default_workspace() -> Path:
    """Create disposable business/runtime directories only.

    Nothing persistent (configuration, classification markers, symbol caches,
    standards or access-control state) may be stored under this tree. The whole
    workspace can be deleted safely between runs.
    """
    root = default_workspace()
    for name in ("input", "remote_input", "processed", "merged", "adjusted", "work", "output", "runs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def default_template() -> Path:
    return resource_path("resources/templates/SLD-Drawing-Frame-Template.sln.pic.g")


def app_icon_ico() -> Path:
    return resource_path("resources/icons/app.ico")


def app_icon_png() -> Path:
    return resource_path("resources/icons/app.png")
