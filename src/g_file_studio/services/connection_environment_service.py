from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from uuid import uuid4

from g_file_studio.services.database_service import OracleDatabaseService
from g_file_studio.services.remote_g_source import (
    DEFAULT_SSH_HOST,
    DEFAULT_SSH_PASSWORD,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_REMOTE_DIRECTORY,
    DEFAULT_SSH_USERNAME,
)
from g_file_studio.services.remote_symbol_library import DEFAULT_REMOTE_SYMBOL_ROOT
from g_file_studio.services.user_settings_service import UserSettingsService


@dataclass
class ConnectionEnvironmentProfile:
    """Named site/environment profile backed by the existing shared connection keys.

    Business modules continue consuming the long-lived ``remote_g_source/*`` and
    ``database/oracle_*`` keys.  Activating a profile simply projects that profile
    into those shared keys, so no business module needs private credentials or a
    separate connection implementation.
    """

    uid: str
    name: str
    ssh_host: str
    ssh_port: int
    ssh_username: str
    ssh_password: str
    business_g_directory: str
    symbol_library_root: str
    oracle_username: str
    oracle_host: str
    oracle_port: int
    oracle_service: str
    oracle_password_dpapi: str = ""


class ConnectionEnvironmentService:
    PROFILES_KEY = "connection_environment/profiles_json"
    ACTIVE_KEY = "connection_environment/active_uid"
    ACTIVE_NAME_KEY = "connection_environment/active_name"

    def __init__(self, settings: UserSettingsService) -> None:
        self.settings = settings
        self.database_service = OracleDatabaseService(settings)
        self._ensure_profile_exists()

    def _read_profiles(self) -> list[ConnectionEnvironmentProfile]:
        raw = self.settings.get_value(self.PROFILES_KEY).strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except Exception:
            return []
        result: list[ConnectionEnvironmentProfile] = []
        if not isinstance(payload, list):
            return result
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                result.append(ConnectionEnvironmentProfile(
                    uid=str(item.get("uid", "") or uuid4().hex),
                    name=str(item.get("name", "") or "Site Environment"),
                    ssh_host=str(item.get("ssh_host", DEFAULT_SSH_HOST) or DEFAULT_SSH_HOST),
                    ssh_port=int(item.get("ssh_port", DEFAULT_SSH_PORT) or DEFAULT_SSH_PORT),
                    ssh_username=str(item.get("ssh_username", DEFAULT_SSH_USERNAME) or DEFAULT_SSH_USERNAME),
                    ssh_password=str(item.get("ssh_password", DEFAULT_SSH_PASSWORD)),
                    business_g_directory=str(item.get("business_g_directory", DEFAULT_SSH_REMOTE_DIRECTORY) or DEFAULT_SSH_REMOTE_DIRECTORY),
                    symbol_library_root=str(item.get("symbol_library_root", DEFAULT_REMOTE_SYMBOL_ROOT) or DEFAULT_REMOTE_SYMBOL_ROOT),
                    oracle_username=str(item.get("oracle_username", "d5000") or "d5000"),
                    oracle_host=str(item.get("oracle_host", "172.16.21.45") or "172.16.21.45"),
                    oracle_port=int(item.get("oracle_port", 1521) or 1521),
                    oracle_service=str(item.get("oracle_service", "jedup8000") or "jedup8000"),
                    oracle_password_dpapi=str(item.get("oracle_password_dpapi", "") or ""),
                ))
            except (TypeError, ValueError):
                continue
        return result

    def _write_profiles(self, profiles: list[ConnectionEnvironmentProfile]) -> None:
        self.settings.set_value(
            self.PROFILES_KEY,
            json.dumps([asdict(profile) for profile in profiles], ensure_ascii=False, separators=(",", ":")),
        )

    def _snapshot_shared(self, *, uid: str, name: str) -> ConnectionEnvironmentProfile:
        db = self.database_service.load_config()
        return ConnectionEnvironmentProfile(
            uid=uid,
            name=name.strip() or "Jeddah Site / Production",
            ssh_host=self.settings.get_value("remote_g_source/host", DEFAULT_SSH_HOST).strip() or DEFAULT_SSH_HOST,
            ssh_port=self.settings.get_int("remote_g_source/port", DEFAULT_SSH_PORT),
            ssh_username=self.settings.get_value("remote_g_source/username", DEFAULT_SSH_USERNAME).strip() or DEFAULT_SSH_USERNAME,
            ssh_password=self.settings.get_value("remote_g_source/password", DEFAULT_SSH_PASSWORD),
            business_g_directory=self.settings.get_value(
                "remote_g_source/remote_directory", DEFAULT_SSH_REMOTE_DIRECTORY
            ).strip() or DEFAULT_SSH_REMOTE_DIRECTORY,
            symbol_library_root=self.settings.get_value(
                "site_profile/remote_symbol_library_root", DEFAULT_REMOTE_SYMBOL_ROOT
            ).strip() or DEFAULT_REMOTE_SYMBOL_ROOT,
            oracle_username=db.username,
            oracle_host=db.host,
            oracle_port=db.port,
            oracle_service=db.service_name,
            oracle_password_dpapi=self.settings.get_value("database/oracle_password_dpapi").strip(),
        )

    def _ensure_profile_exists(self) -> None:
        profiles = self._read_profiles()
        if profiles:
            active_uid = self.settings.get_value(self.ACTIVE_KEY).strip()
            if not any(profile.uid == active_uid for profile in profiles):
                self.settings.set_value(self.ACTIVE_KEY, profiles[0].uid)
                self.settings.set_value(self.ACTIVE_NAME_KEY, profiles[0].name)
            return
        profile = self._snapshot_shared(uid=uuid4().hex, name="Jeddah Site / Production")
        self._write_profiles([profile])
        self.settings.set_value(self.ACTIVE_KEY, profile.uid)
        self.settings.set_value(self.ACTIVE_NAME_KEY, profile.name)

    def profiles(self) -> list[ConnectionEnvironmentProfile]:
        self._ensure_profile_exists()
        return self._read_profiles()

    def active_uid(self) -> str:
        self._ensure_profile_exists()
        return self.settings.get_value(self.ACTIVE_KEY).strip()

    def active(self) -> ConnectionEnvironmentProfile:
        profiles = self.profiles()
        active_uid = self.active_uid()
        return next((profile for profile in profiles if profile.uid == active_uid), profiles[0])

    def activate(self, uid: str) -> ConnectionEnvironmentProfile:
        profiles = self.profiles()
        profile = next((item for item in profiles if item.uid == uid), None)
        if profile is None:
            raise KeyError(f"连接环境不存在：{uid}")
        # Project the selected environment into the established shared keys.
        self.settings.set_value("remote_g_source/host", profile.ssh_host)
        self.settings.set_value("remote_g_source/port", int(profile.ssh_port))
        self.settings.set_value("remote_g_source/username", profile.ssh_username)
        self.settings.set_value("remote_g_source/password", profile.ssh_password)
        self.settings.set_value("remote_g_source/remote_directory", profile.business_g_directory)
        self.settings.set_value("site_profile/remote_symbol_library_root", profile.symbol_library_root)
        self.settings.set_value("database/oracle_username", profile.oracle_username)
        self.settings.set_value("database/oracle_host", profile.oracle_host)
        self.settings.set_value("database/oracle_port", int(profile.oracle_port))
        self.settings.set_value("database/oracle_service", profile.oracle_service)
        self.settings.set_value("database/oracle_config_saved", "true")
        if profile.oracle_password_dpapi:
            self.settings.set_value("database/oracle_password_dpapi", profile.oracle_password_dpapi)
        else:
            self.settings.clear("database/oracle_password_dpapi")
        self.settings.set_value(self.ACTIVE_KEY, profile.uid)
        self.settings.set_value(self.ACTIVE_NAME_KEY, profile.name)
        return profile

    def save_active_from_shared(self, *, name: str | None = None) -> ConnectionEnvironmentProfile:
        profiles = self.profiles()
        active = self.active()
        updated = self._snapshot_shared(uid=active.uid, name=name if name is not None else active.name)
        for index, profile in enumerate(profiles):
            if profile.uid == active.uid:
                profiles[index] = updated
                break
        self._write_profiles(profiles)
        self.settings.set_value(self.ACTIVE_NAME_KEY, updated.name)
        return updated

    def create_copy(self, name: str) -> ConnectionEnvironmentProfile:
        source = self.save_active_from_shared()
        clone = ConnectionEnvironmentProfile(**{**asdict(source), "uid": uuid4().hex, "name": name.strip() or "New Environment"})
        profiles = self.profiles()
        profiles.append(clone)
        self._write_profiles(profiles)
        return self.activate(clone.uid)

    def delete(self, uid: str) -> ConnectionEnvironmentProfile:
        profiles = self.profiles()
        if len(profiles) <= 1:
            raise ValueError("至少需要保留一个连接环境。")
        profiles = [item for item in profiles if item.uid != uid]
        if not profiles:
            raise ValueError("至少需要保留一个连接环境。")
        self._write_profiles(profiles)
        return self.activate(profiles[0].uid)
