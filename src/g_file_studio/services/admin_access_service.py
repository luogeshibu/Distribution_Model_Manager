from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from g_file_studio.services.user_settings_service import UserSettingsService


@dataclass(frozen=True)
class AdminCredentialState:
    initialized: bool
    initialized_at: str = ""


class AdminAccessService:
    """Local administrator credential verifier for protected catalog editing.

    The desktop app always starts in ordinary/read-only mode.  Only a salted
    PBKDF2-SHA256 verifier is persisted; the plaintext administrator password is
    never written to disk.
    """

    _SALT_KEY = "access_control/admin_password_salt"
    _HASH_KEY = "access_control/admin_password_hash"
    _ITERATIONS_KEY = "access_control/admin_password_iterations"
    _INITIALIZED_AT_KEY = "access_control/admin_initialized_at"
    DEFAULT_ITERATIONS = 310_000
    MIN_PASSWORD_LENGTH = 6

    def __init__(self, settings: UserSettingsService) -> None:
        self.settings = settings

    def state(self) -> AdminCredentialState:
        return AdminCredentialState(
            initialized=self.is_initialized(),
            initialized_at=self.settings.get_value(self._INITIALIZED_AT_KEY, "").strip(),
        )

    def is_initialized(self) -> bool:
        salt = self.settings.get_value(self._SALT_KEY, "").strip()
        digest = self.settings.get_value(self._HASH_KEY, "").strip()
        iterations = self.settings.get_int(self._ITERATIONS_KEY, 0)
        if not salt or not digest or iterations <= 0:
            return False
        try:
            bytes.fromhex(salt)
            bytes.fromhex(digest)
        except ValueError:
            return False
        return True

    @classmethod
    def validate_new_password(cls, password: str) -> None:
        value = str(password or "")
        if len(value) < cls.MIN_PASSWORD_LENGTH:
            raise ValueError(f"管理员密码至少需要 {cls.MIN_PASSWORD_LENGTH} 个字符。")
        if not value.strip():
            raise ValueError("管理员密码不能为空。")

    @staticmethod
    def _derive(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            str(password).encode("utf-8"),
            salt,
            int(iterations),
            dklen=32,
        )

    def set_password(self, password: str) -> None:
        self.validate_new_password(password)
        salt = secrets.token_bytes(32)
        iterations = self.DEFAULT_ITERATIONS
        digest = self._derive(password, salt, iterations)
        self.settings.set_value(self._SALT_KEY, salt.hex())
        self.settings.set_value(self._HASH_KEY, digest.hex())
        self.settings.set_value(self._ITERATIONS_KEY, iterations)
        self.settings.set_value(
            self._INITIALIZED_AT_KEY,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    def verify_password(self, password: str) -> bool:
        if not self.is_initialized():
            return False
        try:
            salt = bytes.fromhex(self.settings.get_value(self._SALT_KEY, "").strip())
            expected = bytes.fromhex(self.settings.get_value(self._HASH_KEY, "").strip())
            iterations = self.settings.get_int(self._ITERATIONS_KEY, self.DEFAULT_ITERATIONS)
            actual = self._derive(password, salt, iterations)
        except (TypeError, ValueError):
            return False
        return secrets.compare_digest(actual, expected)
