from __future__ import annotations

import json
from pathlib import Path

from dmm.config import settings as settings_module
from dmm.config.defaults import DEFAULT_SETTINGS


def _isolate_local_cache(monkeypatch, tmp_path, *, user_cache=None, element_cache=None):
    workspace_config = tmp_path / "workspace" / "config.json"
    monkeypatch.setattr(settings_module, "CONFIG_PATH", workspace_config)
    monkeypatch.setattr(
        settings_module,
        "load_user_settings_cache",
        lambda: user_cache,
    )
    monkeypatch.setattr(
        settings_module,
        "load_user_element_catalog",
        lambda: element_cache,
    )
    monkeypatch.setattr(settings_module, "save_user_element_catalog", lambda _value: None)
    monkeypatch.setattr(settings_module, "save_user_settings_cache", lambda _value: None)
    return workspace_config


def test_startup_load_is_local_only_and_never_connects_central(monkeypatch, tmp_path):
    _isolate_local_cache(
        monkeypatch,
        tmp_path,
        user_cache={
            "db": {"host": "10.1.1.5"},
            "ssh": {"host": "10.2.2.6"},
            "element_catalog": {
                "remote_directory": "/local/elements",
                "records": [{"file_name": "A.g", "classification": "RMU"}],
            },
        },
    )

    class ForbiddenCentralClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("startup must not create a central client")

    monkeypatch.setattr(settings_module, "CentralConfigClient", ForbiddenCentralClient)

    loaded = settings_module.load_settings()

    assert loaded["db"]["host"] == "10.1.1.5"
    assert loaded["ssh"]["host"] == "10.2.2.6"
    assert loaded["element_catalog"]["records"][0]["classification"] == "RMU"
    assert loaded["_central_sync"]["status"] == "LOCAL_ONLY"


def test_user_cache_overrides_legacy_workspace_cache(monkeypatch, tmp_path):
    workspace_config = _isolate_local_cache(
        monkeypatch,
        tmp_path,
        user_cache={
            "db": {"host": "user-cache-db"},
            "ssh": {"host": "user-cache-ssh"},
        },
    )
    workspace_config.parent.mkdir(parents=True, exist_ok=True)
    workspace_config.write_text(
        json.dumps(
            {
                "db": {"host": "legacy-workspace-db"},
                "ssh": {"host": "legacy-workspace-ssh"},
            }
        ),
        encoding="utf-8",
    )

    loaded = settings_module.load_settings()

    assert loaded["db"]["host"] == "user-cache-db"
    assert loaded["ssh"]["host"] == "user-cache-ssh"


def test_manual_central_sync_replaces_shared_local_cache(monkeypatch):
    settings = {
        "db": {**DEFAULT_SETTINGS["db"], "host": "local-db", "user": "local-user"},
        "ssh": {**DEFAULT_SETTINGS["ssh"], "host": "local-ssh"},
        "central_config": dict(DEFAULT_SETTINGS["central_config"]),
        "element_catalog": {
            "remote_directory": "/local/elements",
            "records": [{"file_name": "old.g", "classification": "OLD"}],
        },
    }

    bundle = {
        "instance": {
            "initialized": True,
            "admin_status": "active",
            "admin_machine_id": "admin-1",
            "admin_machine_name": "PC-A",
            "config_version": 7,
        },
        "database": {
            "settings": {
                "host": "central-db",
                "user": "central-user",
                "password": "central-password",
                "port": 1522,
                "service_name": "central-service",
            }
        },
        "file_server": {
            "settings": {
                "host": "central-ssh",
                "port": 2222,
                "username": "central-user",
                "password": "central-ssh-password",
                "remote_directory": "/central/g",
                "element_directory": "/central/elements",
            }
        },
        "element_marks": {
            "records": [{"file_name": "new.g", "classification": "LBS"}]
        },
    }

    class FakeCentralClient:
        def __init__(self, _config):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read_bundle(self):
            return bundle

    monkeypatch.setattr(settings_module, "CentralConfigClient", FakeCentralClient)

    settings_module.sync_central_settings(settings, raise_on_error=True)

    assert settings["db"]["host"] == "central-db"
    assert settings["db"]["user"] == "central-user"
    assert settings["ssh"]["host"] == "central-ssh"
    assert settings["ssh"]["remote_directory"] == "/central/g"
    assert settings["element_catalog"]["remote_directory"] == "/central/elements"
    assert settings["element_catalog"]["records"] == [
        {"file_name": "new.g", "classification": "LBS"}
    ]
    assert settings["_central_sync"]["status"] == "ACTIVE"


def test_save_settings_writes_full_user_cache_without_runtime_sync_state(monkeypatch, tmp_path):
    config_path = tmp_path / "workspace" / "config.json"
    monkeypatch.setattr(settings_module, "CONFIG_PATH", config_path)
    monkeypatch.setattr(settings_module, "ensure_workspace", lambda: config_path.parent.mkdir(parents=True, exist_ok=True))
    captured = {}
    monkeypatch.setattr(settings_module, "save_user_settings_cache", lambda payload: captured.update(payload))
    monkeypatch.setattr(settings_module, "save_user_element_catalog", lambda _value: None)

    settings = {
        "db": {"host": "db-local"},
        "ssh": {"host": "ssh-local"},
        "element_catalog": {"records": [{"file_name": "x.g"}]},
        "_central_sync": {"status": "ACTIVE"},
    }
    settings_module.save_settings(settings)

    assert captured["db"]["host"] == "db-local"
    assert captured["ssh"]["host"] == "ssh-local"
    assert captured["element_catalog"]["records"][0]["file_name"] == "x.g"
    assert "_central_sync" not in captured

    disk = json.loads(config_path.read_text(encoding="utf-8"))
    assert "_central_sync" not in disk


def test_ui_source_separates_local_save_from_manual_central_io():
    main_source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    element_source = Path("src/dmm/ui/widgets/element_management_page.py").read_text(encoding="utf-8")

    assert "self.cfg = load_settings(sync_central=False)" in main_source
    assert "self.cfg = load_settings(sync_central=True)" not in main_source
    assert "def _publish_central_if_admin" not in main_source
    assert "def save_catalog(self, sync_central=False):" in element_source
    assert "中央配置已手动同步，并已覆盖本机" in main_source
