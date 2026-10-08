from __future__ import annotations

import posixpath
from dataclasses import dataclass

from g_file_studio.services.classification_registry_service import DEFAULT_CONFIG_DIR
from g_file_studio.services.remote_g_source import (
    DEFAULT_SSH_HOST,
    DEFAULT_SSH_PASSWORD,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
)
from g_file_studio.services.user_settings_service import UserSettingsService


@dataclass(frozen=True)
class CentralRepositoryConfig:
    host: str
    port: int
    username: str
    password: str
    config_dir: str

    def validate(self) -> None:
        if not self.host.strip():
            raise ValueError("中央服务器 IP / 主机不能为空。")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("中央服务器端口无效。")
        if not self.username.strip():
            raise ValueError("中央服务器用户名不能为空。")
        if not self.password:
            raise ValueError("中央服务器密码不能为空。")
        directory = normalize_central_config_dir(self.config_dir)
        if directory == "/":
            raise ValueError("中央配置目录不能设置为服务器根目录 /。")

    def connection_args(self) -> dict[str, object]:
        self.validate()
        return {
            "host": self.host.strip(),
            "port": int(self.port),
            "username": self.username.strip(),
            "password": self.password,
        }


def normalize_central_config_dir(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = DEFAULT_CONFIG_DIR
    if not text.startswith("/"):
        raise ValueError("中央配置目录必须是 Linux 绝对路径，例如 /home/up8000/nari-international/distribution-model-manager/config。")
    normalized = posixpath.normpath(text)
    if not normalized.startswith("/"):
        raise ValueError("中央配置目录必须是绝对路径。")
    return normalized


class CentralRepositorySettings:
    """Workstation-local settings for the central configuration repository.

    The central repository connection is intentionally separate from the business
    G-file server connection.  This prevents a downloaded ``file_server.json``
    from accidentally changing where the application looks for the central
    configuration repository itself.
    """

    HOST_KEY = "central_repository/host"
    PORT_KEY = "central_repository/port"
    USERNAME_KEY = "central_repository/username"
    PASSWORD_KEY = "central_repository/password"
    CONFIG_DIR_KEY = "central_repository/config_dir"
    _EXPLICIT_KEYS = (HOST_KEY, PORT_KEY, USERNAME_KEY, PASSWORD_KEY, CONFIG_DIR_KEY)

    def __init__(self, settings: UserSettingsService) -> None:
        self.settings = settings

    def is_explicitly_saved(self) -> bool:
        """Whether this workstation has explicitly confirmed its central repository.

        Fresh workstations intentionally *display* inherited/default values so the
        operator knows what to configure, but privileged operations must never use
        those values silently.  A central repository becomes trusted only after the
        operator explicitly presses "保存中央仓库配置", which persists all five
        central_repository/* keys locally.
        """
        return all(self.settings.has_value(key) for key in self._EXPLICIT_KEYS)

    def require_explicitly_saved(self, *, action: str) -> CentralRepositoryConfig:
        if not self.is_explicitly_saved():
            current = self.load()
            raise ValueError(
                "本机尚未确认中央仓库配置，当前显示值可能只是程序默认值或从业务文件服务器继承的旧值。\n\n"
                f"当前显示中央仓库：{current.host}:{current.port}\n"
                f"中央配置目录：{current.config_dir}\n\n"
                f"为避免跨现场误连、误抢 Admin 或误发布，本次“{action}”已阻止。\n"
                "请先进入【连接与环境 → 中央配置仓库】，按当前现场修改/确认中央服务器 IP、端口、用户名、密码和中央配置目录，"
                "然后点击【保存中央仓库配置】。即使当前现场确实使用页面上的默认地址，也必须先手工保存确认一次。"
            )
        return self.load()

    def load(self) -> CentralRepositoryConfig:
        # Upgrade compatibility: if the new central-repository keys have never
        # been saved, display the workstation's existing SSH values first.  This
        # preserves the old v2.18.222 behavior while still making the repository
        # independent once the operator saves this section.
        host_default = self.settings.get_value("remote_g_source/host", DEFAULT_SSH_HOST).strip() or DEFAULT_SSH_HOST
        port_default = self.settings.get_int("remote_g_source/port", DEFAULT_SSH_PORT)
        username_default = self.settings.get_value("remote_g_source/username", DEFAULT_SSH_USERNAME).strip() or DEFAULT_SSH_USERNAME
        password_default = self.settings.get_value("remote_g_source/password", DEFAULT_SSH_PASSWORD)

        host = self.settings.get_value(self.HOST_KEY, host_default).strip() or host_default
        port = self.settings.get_int(self.PORT_KEY, port_default)
        username = self.settings.get_value(self.USERNAME_KEY, username_default).strip() or username_default
        password = self.settings.get_value(self.PASSWORD_KEY, password_default)
        raw_dir = self.settings.get_value(self.CONFIG_DIR_KEY, DEFAULT_CONFIG_DIR).strip() or DEFAULT_CONFIG_DIR
        try:
            config_dir = normalize_central_config_dir(raw_dir)
        except ValueError:
            config_dir = DEFAULT_CONFIG_DIR
        return CentralRepositoryConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            config_dir=config_dir,
        )

    def save(self, config: CentralRepositoryConfig) -> CentralRepositoryConfig:
        config.validate()
        normalized = CentralRepositoryConfig(
            host=config.host.strip(),
            port=int(config.port),
            username=config.username.strip(),
            password=config.password,
            config_dir=normalize_central_config_dir(config.config_dir),
        )
        self.settings.set_value(self.HOST_KEY, normalized.host)
        self.settings.set_value(self.PORT_KEY, normalized.port)
        self.settings.set_value(self.USERNAME_KEY, normalized.username)
        self.settings.set_value(self.PASSWORD_KEY, normalized.password)
        self.settings.set_value(self.CONFIG_DIR_KEY, normalized.config_dir)
        return normalized
