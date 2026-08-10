from pathlib import Path

from dmm.infrastructure.filesystem.workspace import (
    APP_ROOT,
    WORKSPACE_ROOT,
)


def test_source_workspace_is_project_level():
    # During source-mode pytest:
    # <project>/src/dmm/infrastructure/filesystem/workspace.py
    expected_project_root = Path(__file__).resolve().parents[1]

    assert APP_ROOT == expected_project_root
    assert WORKSPACE_ROOT == expected_project_root / "workspace"
    assert "src" not in WORKSPACE_ROOT.parts[-2:]
