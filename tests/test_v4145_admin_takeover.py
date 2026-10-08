from __future__ import annotations

from dmm.config import settings as settings_module
from dmm.infrastructure.remote.central_config import CentralConfigClient, CentralConfigError


class MemoryCentralClient(CentralConfigClient):
    def __init__(self, instance=None):
        super().__init__({"host": "central", "username": "u"})
        self.instance = dict(instance or {}) if instance is not None else None
        self.writes = []

    def ensure_root(self):
        return None

    def _lock(self):
        return "LOCK"

    def _unlock(self, _path):
        return None

    def read_json(self, name: str, required=False):
        if name == "instance.json":
            if self.instance is None and required:
                raise CentralConfigError("missing")
            return dict(self.instance) if self.instance is not None else None
        return {"ok": True}

    def _write_json(self, name: str, payload: dict):
        if name == "instance.json":
            self.instance = dict(payload)
        self.writes.append((name, dict(payload)))


def test_claim_admin_can_take_over_active_admin_without_publishing_bundle():
    client = MemoryCentralClient(
        {
            "initialized": True,
            "admin_status": "active",
            "admin_machine_id": "A",
            "admin_machine_name": "PC-A",
            "admin_ip": "10.0.0.1",
            "admin_epoch": 7,
            "config_version": 12,
        }
    )

    result = client.claim_admin("B", "PC-B", "10.0.0.2")

    assert result["admin_machine_id"] == "B"
    assert result["admin_epoch"] == 8
    assert result["config_version"] == 12
    assert result["initialized"] is True
    assert [name for name, _payload in client.writes] == ["instance.json"]
    assert result["last_admin"]["machine_id"] == "A"


def test_publish_rejects_stale_epoch_even_on_same_machine():
    client = MemoryCentralClient(
        {
            "initialized": True,
            "admin_status": "active",
            "admin_machine_id": "M",
            "admin_machine_name": "PC-M",
            "admin_epoch": 5,
            "config_version": 2,
        }
    )

    try:
        client.publish({}, "M", "PC-M", "10.0.0.5", expected_admin_epoch=4)
    except CentralConfigError as exc:
        assert "重新抢占" in str(exc)
    else:
        raise AssertionError("stale Admin epoch must be rejected")


def test_release_preserves_previous_admin_audit_and_advances_epoch():
    client = MemoryCentralClient(
        {
            "initialized": True,
            "admin_status": "active",
            "admin_machine_id": "A",
            "admin_machine_name": "PC-A",
            "admin_ip": "10.0.0.1",
            "admin_claimed_at": "2026-09-22T10:00:00+00:00",
            "admin_epoch": 3,
            "config_version": 9,
        }
    )

    version = client.release_admin("A", "PC-A", expected_admin_epoch=3)

    assert version == 9
    assert client.instance["admin_status"] == "unassigned"
    assert client.instance["admin_epoch"] == 4
    assert client.instance["last_admin"]["machine_id"] == "A"
    assert client.instance["last_admin"]["machine_name"] == "PC-A"


def test_takeover_settings_changes_only_admin_state(monkeypatch):
    settings = {
        "machine_id": "B",
        "central_config": {"host": "central", "username": "u", "enabled": True},
        "db": {"host": "local-db"},
        "ssh": {"host": "local-ssh"},
        "element_catalog": {"records": [{"file_name": "x.g", "classification": "RMU"}]},
    }

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def claim_admin(self, machine_id, machine_name, machine_ip):
            assert machine_id == "B"
            return {
                "initialized": True,
                "admin_status": "active",
                "admin_machine_id": machine_id,
                "admin_machine_name": machine_name,
                "admin_ip": machine_ip,
                "admin_epoch": 11,
                "config_version": 21,
            }

    monkeypatch.setattr(settings_module, "CentralConfigClient", FakeClient)
    monkeypatch.setattr(settings_module, "local_machine_info", lambda _host: ("PC-B", "10.0.0.2"))

    epoch = settings_module.takeover_central_admin(settings)

    assert epoch == 11
    assert settings["db"]["host"] == "local-db"
    assert settings["ssh"]["host"] == "local-ssh"
    assert settings["element_catalog"]["records"][0]["classification"] == "RMU"
    assert settings["_central_sync"]["admin_epoch"] == 11


def test_admin_probe_reads_only_instance(monkeypatch):
    calls = []
    settings = {"central_config": {"host": "central", "username": "u", "enabled": True}}

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read_admin_state(self):
            calls.append("instance")
            return {
                "initialized": True,
                "admin_status": "active",
                "admin_machine_id": "A",
                "admin_machine_name": "PC-A",
                "admin_epoch": 2,
                "config_version": 4,
            }

    monkeypatch.setattr(settings_module, "CentralConfigClient", FakeClient)
    state = settings_module.read_central_admin_state(settings)

    assert calls == ["instance"]
    assert state["status"] == "ACTIVE"
    assert state["admin_epoch"] == 2


def test_ui_source_has_no_startup_sync_and_has_admin_polling():
    from pathlib import Path

    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "self.cfg = load_settings(sync_central=False)" in source
    assert "self._central_admin_timer.setInterval(10000)" in source
    assert "def _schedule_central_admin_ownership_check" in source
    assert "def takeover_central_configuration" in source
    assert "抢占 Admin 权限" in source
