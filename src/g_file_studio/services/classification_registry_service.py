from __future__ import annotations

import hashlib
import json
import posixpath
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4


DEFAULT_CONFIG_DIR = "/home/up8000/nari-international/distribution-model-manager/config"
INSTANCE_FILE_NAME = "instance.json"
CLASSIFICATION_FILE_NAME = "symbol_classification.json"
DATABASE_FILE_NAME = "database.json"
FILE_SERVER_FILE_NAME = "file_server.json"
ID_RULES_FILE_NAME = "id_rules.json"
DEFAULT_INSTANCE_PATH = f"{DEFAULT_CONFIG_DIR}/{INSTANCE_FILE_NAME}"
DEFAULT_CLASSIFICATION_PATH = f"{DEFAULT_CONFIG_DIR}/{CLASSIFICATION_FILE_NAME}"
DEFAULT_DATABASE_PATH = f"{DEFAULT_CONFIG_DIR}/{DATABASE_FILE_NAME}"
DEFAULT_FILE_SERVER_PATH = f"{DEFAULT_CONFIG_DIR}/{FILE_SERVER_FILE_NAME}"
DEFAULT_ID_RULES_PATH = f"{DEFAULT_CONFIG_DIR}/{ID_RULES_FILE_NAME}"
# Backward-compatible names; the old admin_lock.json file no longer exists.
ADMIN_LOCK_FILE_NAME = INSTANCE_FILE_NAME
DEFAULT_ADMIN_LOCK_PATH = DEFAULT_INSTANCE_PATH
DEFAULT_CLASSIFICATION_REGISTRY_DIR = DEFAULT_CONFIG_DIR
# Compatibility constant retained for callers/tests from v2.18.169.  Admin ownership
# is now persistent in instance.json and no longer expires by lease timeout.
DEFAULT_ADMIN_LEASE_SECONDS = 180
ADMIN_PASSWORD_ITERATIONS = 310_000
ADMIN_PASSWORD_MIN_LENGTH = 6


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now() -> str:
    return _utc_now_dt().isoformat(timespec="seconds")


@dataclass(frozen=True)
class CentralClassificationSnapshot:
    remote_path: str
    updated_at: str
    marker_count: int
    payload: dict[str, object]


@dataclass(frozen=True)
class AdminLeaseSnapshot:
    """Compatibility view of the central administrator stored in instance.json."""

    remote_path: str
    lease_id: str
    machine_id: str
    machine_name: str
    ip: str
    username: str
    acquired_at: str
    heartbeat_at: str = ""
    expires_at: str = ""
    expired: bool = False
    config_version: int = 0
    admin_epoch: int = 0

    @property
    def owner_text(self) -> str:
        name = self.machine_name or self.machine_id or "未知机器"
        return f"{name} ({self.ip or '未知IP'})"


class AdminLeaseBusyError(RuntimeError):
    def __init__(self, lease: AdminLeaseSnapshot) -> None:
        self.lease = lease
        super().__init__(
            f"中央配置管理员当前为 {lease.owner_text}。"
            "请由该机器先释放管理员权限。"
        )


class ClassificationRegistryService:
    """SSH/SFTP-backed central configuration repository.

    By default central files live under ``/home/up8000/nari-international/distribution-model-manager/config``;
    the workstation may explicitly configure another absolute Linux directory.
    ``instance.json`` is the single source of truth for the active administrator and
    global config version.  Workstations may keep independent local settings; only
    the current administrator can publish/overwrite the central files.
    """

    def __init__(
        self,
        remote_path: str | None = None,
        *,
        instance_path: str | None = None,
        config_dir: str | None = None,
    ) -> None:
        raw_base = config_dir
        if raw_base is None and remote_path:
            raw_base = posixpath.dirname(str(remote_path))
        if raw_base is None and instance_path:
            raw_base = posixpath.dirname(str(instance_path))
        base = posixpath.normpath(str(raw_base or DEFAULT_CONFIG_DIR).strip() or DEFAULT_CONFIG_DIR)
        if not base.startswith("/") or base == "/":
            raise ValueError("中央配置目录必须是 Linux 绝对路径，且不能是服务器根目录 /。")
        path = str(remote_path or posixpath.join(base, CLASSIFICATION_FILE_NAME)).strip()
        if not path.startswith("/") or not path.endswith("/" + CLASSIFICATION_FILE_NAME):
            raise ValueError("中央分类配置路径必须是绝对路径并以 /symbol_classification.json 结尾。")
        instance = str(instance_path or posixpath.join(base, INSTANCE_FILE_NAME)).strip()
        if not instance.startswith("/") or not instance.endswith("/" + INSTANCE_FILE_NAME):
            raise ValueError("中央实例配置路径必须是绝对路径并以 /instance.json 结尾。")
        self.config_dir = base
        self.remote_path = path
        self.instance_path = instance
        self.database_path = posixpath.join(base, DATABASE_FILE_NAME)
        self.file_server_path = posixpath.join(base, FILE_SERVER_FILE_NAME)
        self.id_rules_path = posixpath.join(base, ID_RULES_FILE_NAME)

    @staticmethod
    def _paramiko():
        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError("未安装 SSH 依赖 paramiko。请执行：python -m pip install paramiko") from exc
        return paramiko

    @staticmethod
    def _connect(*, host: str, port: int, username: str, password: str, timeout: float = 10.0):
        if not str(host).strip():
            raise ValueError("SSH IP/主机不能为空。")
        if not str(username).strip():
            raise ValueError("SSH 用户名不能为空。")
        paramiko = ClassificationRegistryService._paramiko()
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=str(host).strip(),
            port=int(port),
            username=str(username).strip(),
            password=str(password),
            timeout=timeout,
            auth_timeout=timeout,
            banner_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return ssh, ssh.open_sftp()

    @staticmethod
    def _mkdir_p(sftp, directory: str) -> None:
        directory = posixpath.normpath(str(directory))
        current = "/" if directory.startswith("/") else ""
        for part in [item for item in directory.split("/") if item]:
            current = posixpath.join(current, part) if current else part
            try:
                attrs = sftp.stat(current)
                if not stat.S_ISDIR(int(attrs.st_mode)):
                    raise ValueError(f"中央配置路径不是目录：{current}")
            except OSError as exc:
                missing = ClassificationRegistryService._is_missing(exc)
                if not missing:
                    raise
                sftp.mkdir(current)
        try:
            sftp.chmod(directory, 0o700)
        except Exception:
            pass

    @staticmethod
    def _connection_ip(ssh) -> str:
        try:
            transport = ssh.get_transport()
            sock = getattr(transport, "sock", None) if transport is not None else None
            if sock is not None:
                value = sock.getsockname()
                if isinstance(value, tuple) and value:
                    return str(value[0])
        except Exception:
            pass
        return ""

    @staticmethod
    def _is_missing(exc: BaseException) -> bool:
        return (
            isinstance(exc, FileNotFoundError)
            or getattr(exc, "errno", None) == 2
            or "No such file" in str(exc)
            or "not found" in str(exc).lower()
        )

    @staticmethod
    def _read_json(sftp, path: str) -> dict[str, object]:
        with sftp.open(path, "rb") as handle:
            raw = handle.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path} 不是有效 UTF-8 JSON：{exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path} 必须是 JSON 对象。")
        return payload

    @staticmethod
    def _atomic_replace_bytes(sftp, target_path: str, encoded: bytes) -> None:
        temp_path = f"{target_path}.tmp-{uuid4().hex}"
        try:
            with sftp.open(temp_path, "wb") as handle:
                handle.write(encoded)
                handle.flush()
            with sftp.open(temp_path, "rb") as handle:
                verify = handle.read()
            if verify != encoded:
                raise IOError(f"上传后校验失败，{posixpath.basename(target_path)} 未更新。")

            posix_rename = getattr(sftp, "posix_rename", None)
            renamed = False
            if callable(posix_rename):
                try:
                    posix_rename(temp_path, target_path)
                    renamed = True
                except OSError:
                    renamed = False
            if not renamed:
                try:
                    sftp.rename(temp_path, target_path)
                except OSError:
                    try:
                        sftp.remove(target_path)
                    except OSError:
                        pass
                    sftp.rename(temp_path, target_path)
            try:
                sftp.chmod(target_path, 0o600)
            except Exception:
                pass
        finally:
            try:
                sftp.remove(temp_path)
            except OSError:
                pass

    @staticmethod
    def _files_map() -> dict[str, str]:
        return {
            "instance": INSTANCE_FILE_NAME,
            "symbol_classification": CLASSIFICATION_FILE_NAME,
            "database": DATABASE_FILE_NAME,
            "file_server": FILE_SERVER_FILE_NAME,
            "id_rules": ID_RULES_FILE_NAME,
        }

    @classmethod
    def _default_instance(cls) -> dict[str, object]:
        return {
            "schema_version": 1,
            "initialized": False,
            "admin_status": "released",
            "admin_machine_id": "",
            "admin_machine_name": "",
            "admin_ip": "",
            "admin_claimed_at": "",
            "admin_epoch": 0,
            "last_admin": {},
            "admin_auth": {
                "initialized": False,
                "algorithm": "pbkdf2_sha256",
                "salt": "",
                "password_hash": "",
                "iterations": ADMIN_PASSWORD_ITERATIONS,
                "updated_at": "",
            },
            "config_version": 0,
            "updated_at": _utc_now(),
            "files": cls._files_map(),
        }

    @staticmethod
    def _normalize_admin_auth(payload: object) -> dict[str, object]:
        raw = dict(payload) if isinstance(payload, dict) else {}
        return {
            "initialized": bool(raw.get("initialized", False)),
            "algorithm": "pbkdf2_sha256",
            "salt": str(raw.get("salt", "") or "").strip(),
            "password_hash": str(raw.get("password_hash", "") or "").strip(),
            "iterations": max(100_000, int(raw.get("iterations", ADMIN_PASSWORD_ITERATIONS) or ADMIN_PASSWORD_ITERATIONS)),
            "updated_at": str(raw.get("updated_at", "") or "").strip(),
        }

    @staticmethod
    def _derive_admin_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, int(iterations), dklen=32)

    @classmethod
    def _verify_admin_password_payload(cls, instance: dict[str, object], password: str) -> bool:
        auth = cls._normalize_admin_auth(instance.get("admin_auth", {}))
        if not auth["initialized"] or not auth["salt"] or not auth["password_hash"]:
            return False
        try:
            salt = bytes.fromhex(str(auth["salt"]))
            expected = bytes.fromhex(str(auth["password_hash"]))
            actual = cls._derive_admin_password(password, salt, int(auth["iterations"]))
        except (TypeError, ValueError):
            return False
        return secrets.compare_digest(actual, expected)

    @staticmethod
    def _validate_admin_password(password: str) -> None:
        value = str(password or "")
        if len(value) < ADMIN_PASSWORD_MIN_LENGTH or not value.strip():
            raise ValueError(f"管理员密码至少需要 {ADMIN_PASSWORD_MIN_LENGTH} 个字符。")

    @classmethod
    def _set_admin_password_payload(cls, instance: dict[str, object], password: str) -> dict[str, object]:
        cls._validate_admin_password(password)
        salt = secrets.token_bytes(32)
        iterations = ADMIN_PASSWORD_ITERATIONS
        digest = cls._derive_admin_password(password, salt, iterations)
        instance["admin_auth"] = {
            "initialized": True,
            "algorithm": "pbkdf2_sha256",
            "salt": salt.hex(),
            "password_hash": digest.hex(),
            "iterations": iterations,
            "updated_at": _utc_now(),
        }
        return instance

    @classmethod
    def _normalize_instance(cls, payload: object) -> dict[str, object]:
        source = dict(payload) if isinstance(payload, dict) else {}
        result = cls._default_instance()
        result.update({
            "schema_version": 1,
            "initialized": bool(source.get("initialized", False)),
            "admin_status": str(source.get("admin_status", "released") or "released").strip().lower(),
            "admin_machine_id": str(source.get("admin_machine_id", "") or "").strip(),
            "admin_machine_name": str(source.get("admin_machine_name", "") or "").strip(),
            "admin_ip": str(source.get("admin_ip", "") or "").strip(),
            "admin_claimed_at": str(source.get("admin_claimed_at", "") or "").strip(),
            "admin_epoch": max(0, int(source.get("admin_epoch", 0) or 0)),
            "last_admin": dict(source.get("last_admin", {})) if isinstance(source.get("last_admin", {}), dict) else {},
            "admin_auth": cls._normalize_admin_auth(source.get("admin_auth", {})),
            "config_version": max(0, int(source.get("config_version", 0) or 0)),
            "updated_at": str(source.get("updated_at", "") or "").strip() or _utc_now(),
            "files": cls._files_map(),
        })
        if result["admin_status"] != "active":
            result["admin_status"] = "released"
            result["admin_machine_id"] = ""
            result["admin_machine_name"] = ""
            result["admin_ip"] = ""
            result["admin_claimed_at"] = ""
        return result

    @classmethod
    def _instance_to_snapshot(cls, payload: dict[str, object], *, remote_path: str) -> AdminLeaseSnapshot | None:
        item = cls._normalize_instance(payload)
        if item.get("admin_status") != "active" or not str(item.get("admin_machine_id", "")).strip():
            return None
        machine_id = str(item.get("admin_machine_id", "")).strip()
        return AdminLeaseSnapshot(
            remote_path=remote_path,
            lease_id=machine_id,
            machine_id=machine_id,
            machine_name=str(item.get("admin_machine_name", "")).strip(),
            ip=str(item.get("admin_ip", "")).strip(),
            username="",
            acquired_at=str(item.get("admin_claimed_at", "")).strip(),
            heartbeat_at=str(item.get("updated_at", "")).strip(),
            expires_at="",
            expired=False,
            config_version=int(item.get("config_version", 0) or 0),
            admin_epoch=int(item.get("admin_epoch", 0) or 0),
        )

    def fetch_instance(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 6.0,
    ) -> dict[str, object]:
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password, timeout=timeout)
            try:
                return self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    return self._default_instance()
                raise
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def test_repository(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 6.0,
    ) -> dict[str, object]:
        """Read-only connectivity/path check for the configured central repository."""
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(
                host=host, port=port, username=username, password=password, timeout=timeout
            )
            try:
                attrs = sftp.stat(self.config_dir)
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError(
                        f"中央配置目录不存在：{self.config_dir}"
                    ) from exc
                raise
            if not stat.S_ISDIR(int(attrs.st_mode)):
                raise NotADirectoryError(f"中央配置路径不是目录：{self.config_dir}")
            names = set(str(name) for name in sftp.listdir(self.config_dir))
            expected = [
                INSTANCE_FILE_NAME,
                DATABASE_FILE_NAME,
                FILE_SERVER_FILE_NAME,
                ID_RULES_FILE_NAME,
                CLASSIFICATION_FILE_NAME,
            ]
            present = [name for name in expected if name in names]
            missing = [name for name in expected if name not in names]
            return {
                "config_dir": self.config_dir,
                "present": present,
                "missing": missing,
                "server_ip": self._connection_ip(ssh),
            }
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def fetch_admin_lease(self, **kwargs) -> AdminLeaseSnapshot | None:
        payload = self.fetch_instance(**kwargs)
        return self._instance_to_snapshot(payload, remote_path=self.instance_path)

    def force_set_admin_password(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        new_admin_password: str,
        machine_id: str = "",
        machine_name: str = "",
        take_over: bool = False,
    ) -> AdminLeaseSnapshot | None:
        """Reset the central administrator password through the configured SSH account.

        SSH write access is the recovery authority.  No old admin password is
        required.  When ``take_over`` is true, the resetting workstation also
        becomes the active central-config administrator.
        """
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if not self._is_missing(exc):
                    raise
                instance = self._default_instance()
            self._set_admin_password_payload(instance, new_admin_password)
            now = _utc_now()
            instance["initialized"] = True
            if take_over:
                machine_id = str(machine_id or "").strip()
                if not machine_id:
                    raise ValueError("本机唯一标识为空，无法接管管理员权限。")
                instance.update({
                    "admin_status": "active",
                    "admin_machine_id": machine_id,
                    "admin_machine_name": str(machine_name or "").strip() or "Unknown",
                    "admin_ip": self._connection_ip(ssh),
                    "admin_claimed_at": now,
                })
            instance["updated_at"] = now
            instance["files"] = self._files_map()
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            return self._instance_to_snapshot(instance, remote_path=self.instance_path)
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def takeover_admin(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        machine_name: str,
        timeout: float = 6.0,
    ) -> AdminLeaseSnapshot:
        """Explicitly take over Admin ownership without syncing business config.

        This follows the Distribution Model Manager central-repository contract:
        any workstation with the configured SSH write access may explicitly claim
        Admin.  The operation changes only ``instance.json`` ownership metadata;
        database, file-server, ID-rule and symbol-classification files are untouched.
        """
        machine_id = str(machine_id or "").strip()
        machine_name = str(machine_name or "").strip() or "Unknown"
        if not machine_id:
            raise ValueError("本机唯一标识为空，无法抢占管理员权限。")

        ssh = sftp = None
        try:
            ssh, sftp = self._connect(
                host=host, port=port, username=username, password=password, timeout=timeout
            )
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if not self._is_missing(exc):
                    raise
                instance = self._default_instance()

            now = _utc_now()
            current = self._instance_to_snapshot(instance, remote_path=self.instance_path)
            previous_owner: dict[str, object] = {}
            if current is not None:
                previous_owner = {
                    "machine_id": current.machine_id,
                    "machine_name": current.machine_name,
                    "ip": current.ip,
                    "claimed_at": current.acquired_at,
                    "released_at": now,
                }
            epoch = int(instance.get("admin_epoch", 0) or 0) + 1
            instance.update({
                "initialized": bool(instance.get("initialized", False)),
                "admin_status": "active",
                "admin_machine_id": machine_id,
                "admin_machine_name": machine_name,
                "admin_ip": self._connection_ip(ssh),
                "admin_claimed_at": now,
                "admin_epoch": epoch,
                "updated_at": now,
                "files": self._files_map(),
            })
            if previous_owner.get("machine_id"):
                instance["last_admin"] = previous_owner
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            final = self._instance_to_snapshot(instance, remote_path=self.instance_path)
            if final is None:
                raise RuntimeError("中央管理员状态写入失败。")
            return final
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def acquire_admin_lease(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        machine_name: str,
        admin_password: str = "",
        force_takeover: bool = False,
        lease_seconds: int = DEFAULT_ADMIN_LEASE_SECONDS,
        allow_same_machine_takeover: bool = True,
    ) -> AdminLeaseSnapshot:
        del lease_seconds
        machine_id = str(machine_id or "").strip()
        machine_name = str(machine_name or "").strip() or "Unknown"
        if not machine_id:
            raise ValueError("本机唯一标识为空，无法申请管理员权限。")

        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if not self._is_missing(exc):
                    raise
                instance = self._default_instance()

            auth = self._normalize_admin_auth(instance.get("admin_auth", {}))
            if not auth["initialized"]:
                raise RuntimeError("中央管理员密码尚未设置，请先使用“强制设置管理员密码”。")
            if not self._verify_admin_password_payload(instance, admin_password):
                raise PermissionError("管理员密码不正确。")

            current = self._instance_to_snapshot(instance, remote_path=self.instance_path)
            if current is not None and current.machine_id != machine_id and not force_takeover:
                raise AdminLeaseBusyError(current)
            if current is not None and not allow_same_machine_takeover:
                raise AdminLeaseBusyError(current)

            now = _utc_now()
            instance.update({
                "initialized": True,
                "admin_status": "active",
                "admin_machine_id": machine_id,
                "admin_machine_name": machine_name,
                "admin_ip": self._connection_ip(ssh),
                "admin_claimed_at": (
                    str(instance.get("admin_claimed_at", "") or "").strip()
                    if current is not None and current.machine_id == machine_id
                    else now
                ),
                "updated_at": now,
                "files": self._files_map(),
            })
            encoded = (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            self._atomic_replace_bytes(sftp, self.instance_path, encoded)
            final = self._instance_to_snapshot(instance, remote_path=self.instance_path)
            if final is None:
                raise RuntimeError("中央管理员状态写入失败。")
            return final
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def renew_admin_lease(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        lease_id: str,
        lease_seconds: int = DEFAULT_ADMIN_LEASE_SECONDS,
        expected_admin_epoch: int | None = None,
    ) -> AdminLeaseSnapshot:
        del lease_seconds
        current = self.fetch_admin_lease(
            host=host, port=port, username=username, password=password, timeout=6.0
        )
        if current is None:
            raise RuntimeError("中央配置当前没有管理员。")
        if current.machine_id != str(machine_id).strip() or current.lease_id != str(lease_id).strip():
            raise AdminLeaseBusyError(current)
        if expected_admin_epoch is not None and current.admin_epoch != int(expected_admin_epoch):
            raise AdminLeaseBusyError(current)
        return current

    def release_admin_lease(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        lease_id: str,
        timeout: float = 6.0,
        expected_admin_epoch: int | None = None,
    ) -> bool:
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password, timeout=timeout)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    return True
                raise
            current = self._instance_to_snapshot(instance, remote_path=self.instance_path)
            if current is None:
                return True
            if current.machine_id != str(machine_id).strip() or current.lease_id != str(lease_id).strip():
                return False
            if expected_admin_epoch is not None and current.admin_epoch != int(expected_admin_epoch):
                return False
            previous_owner = {
                "machine_id": current.machine_id,
                "machine_name": current.machine_name,
                "ip": current.ip,
                "claimed_at": current.acquired_at,
                "released_at": _utc_now(),
            }
            instance.update({
                "admin_status": "released",
                "admin_machine_id": "",
                "admin_machine_name": "",
                "admin_ip": "",
                "admin_claimed_at": "",
                "admin_epoch": int(instance.get("admin_epoch", 0) or 0) + 1,
                "last_admin": previous_owner,
                "updated_at": _utc_now(),
                "files": self._files_map(),
            })
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            return True
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    @staticmethod
    def _validate_payload(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("中央分类配置必须是 JSON 对象。")
        raw_markers = payload.get("markers")
        if not isinstance(raw_markers, list):
            raise ValueError("中央分类配置缺少 markers 数组。")
        markers: list[dict[str, str]] = []
        for raw in raw_markers:
            if not isinstance(raw, dict):
                continue
            marker = str(raw.get("classification_marker", raw.get("category_marker", "")) or "").strip()
            if not marker:
                continue
            row = {
                "relative_path": str(raw.get("relative_path", raw.get("path", "")) or "").strip(),
                "file_name": str(raw.get("file_name", raw.get("name", "")) or "").strip(),
                "devref": str(raw.get("devref", "") or "").strip(),
                "element_id": str(raw.get("element_id", raw.get("id", "")) or "").strip(),
                "classification_marker": marker,
            }
            if not any(row[key] for key in ("relative_path", "file_name", "devref")):
                continue
            markers.append(row)
        # v2.18.199: central/user-facing classification JSON contains portable
        # file identity + body element_id + classification. Legacy XML element-tag
        # fields (element_tag/xml_tag/target_xml) are deliberately not propagated.
        cleaned = {
            "schema": 2,
            "kind": "GFileStudio central symbol classification markers",
            "updated_at": str(payload.get("updated_at", payload.get("exported_at", "")) or "").strip() or _utc_now(),
            "owner": "GFileStudio",
            "markers": markers,
        }
        return cleaned

    def fetch(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        log: Callable[[str], None] | None = None,
    ) -> CentralClassificationSnapshot:
        log = log or (lambda _msg: None)
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            log(f"读取中央分类配置：{self.remote_path}")
            try:
                payload = self._read_json(sftp, self.remote_path)
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError(
                        f"中央图元分类配置尚未创建：{self.remote_path}。请由管理员首次上传。"
                    ) from exc
                raise
            cleaned = self._validate_payload(payload)
            return CentralClassificationSnapshot(
                remote_path=self.remote_path,
                updated_at=str(cleaned.get("updated_at", "")),
                marker_count=len(cleaned.get("markers", [])),
                payload=cleaned,
            )
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def _assert_admin(
        self,
        instance: dict[str, object],
        *,
        machine_id: str,
        expected_admin_epoch: int | None = None,
    ) -> None:
        current = self._instance_to_snapshot(instance, remote_path=self.instance_path)
        if current is None:
            raise RuntimeError("中央配置当前没有管理员，请先申请管理员权限。")
        if current.machine_id != str(machine_id or "").strip():
            raise AdminLeaseBusyError(current)
        if expected_admin_epoch is not None and current.admin_epoch != int(expected_admin_epoch):
            raise RuntimeError(
                "Admin 权限已被重新抢占，本次发布已阻止。请重新抢占 Admin 后再操作。"
            )

    @classmethod
    def _bump_instance(cls, instance: dict[str, object]) -> dict[str, object]:
        next_instance = cls._normalize_instance(instance)
        next_instance["initialized"] = True
        next_instance["config_version"] = int(next_instance.get("config_version", 0) or 0) + 1
        next_instance["updated_at"] = _utc_now()
        next_instance["files"] = cls._files_map()
        return next_instance

    def publish(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        payload: dict[str, object],
        publisher_machine: str = "",
        publisher_ip: str = "",
        machine_id: str = "",
        lease_id: str = "",
        expected_admin_epoch: int | None = None,
        log: Callable[[str], None] | None = None,
    ) -> CentralClassificationSnapshot:
        del lease_id
        log = log or (lambda _msg: None)
        cleaned = self._validate_payload(payload)
        cleaned["updated_at"] = _utc_now()
        cleaned["published_by"] = {
            "application": "GFileStudio",
            "machine_name": str(publisher_machine or "").strip(),
            "ip": str(publisher_ip or "").strip(),
        }
        encoded = (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    instance = self._default_instance()
                else:
                    raise
            self._assert_admin(
                instance, machine_id=machine_id, expected_admin_epoch=expected_admin_epoch
            )
            log(f"更新中央图元分类配置：{self.remote_path}")
            self._atomic_replace_bytes(sftp, self.remote_path, encoded)
            instance = self._bump_instance(instance)
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            final_payload = self._validate_payload(self._read_json(sftp, self.remote_path))
            return CentralClassificationSnapshot(
                remote_path=self.remote_path,
                updated_at=str(final_payload.get("updated_at", "")),
                marker_count=len(final_payload.get("markers", [])),
                payload=final_payload,
            )
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    @staticmethod
    def _validate_id_rules_config(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("id_rules.json 必须是 JSON 对象。")
        raw_rules = payload.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError("id_rules.json 缺少 rules 数组。")

        rules: list[dict[str, object]] = []
        for raw in raw_rules:
            if not isinstance(raw, dict):
                continue
            tag = str(raw.get("tag", "") or "").strip()
            prefix = str(raw.get("prefix", "") or "").strip()
            try:
                total_length = int(raw.get("total_length", 0) or 0)
            except (TypeError, ValueError):
                continue
            if not tag or not prefix.isdigit() or total_length <= len(prefix):
                continue
            sequence_width = total_length - len(prefix)
            valid_example = f"{prefix}{1:0{sequence_width}d}"
            rules.append({
                "tag": tag,
                "prefix": prefix,
                "total_length": total_length,
                "valid_example": valid_example,
                "enabled": bool(raw.get("enabled", True)),
                "verified": bool(raw.get("verified", True)),
                "note": str(raw.get("note", "") or ""),
            })

        if not rules:
            raise ValueError("id_rules.json 没有有效 ID 规则。")

        deleted_tags = sorted({
            str(tag).strip()
            for tag in payload.get("deleted_tags", [])
            if str(tag).strip()
        })
        result: dict[str, object] = {
            "version": max(7, int(payload.get("version", 7) or 7)),
            "allocation": "per_type_full_id_increment",
            "match": "prefix_and_total_length",
            "deleted_tags": deleted_tags,
            "rules": rules,
            "updated_at": str(payload.get("updated_at", "") or "").strip() or _utc_now(),
        }
        snapshot = payload.get("server_snapshot")
        if isinstance(snapshot, dict) and snapshot:
            result["server_snapshot"] = dict(snapshot)
        published_by = payload.get("published_by")
        if isinstance(published_by, dict) and published_by:
            result["published_by"] = dict(published_by)
        return result

    def fetch_id_rules(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        log: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        log = log or (lambda _msg: None)
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            log(f"读取中央 ID 规则：{self.id_rules_path}")
            try:
                rules = self._validate_id_rules_config(self._read_json(sftp, self.id_rules_path))
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError(
                        f"中央 ID 规则尚未创建：{self.id_rules_path}。请由管理员首次发布。"
                    ) from exc
                raise
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    instance = self._default_instance()
                else:
                    raise
            return {
                "instance": instance,
                "id_rules": rules,
                "remote_path": self.id_rules_path,
            }
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def publish_id_rules(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        machine_name: str = "",
        expected_admin_epoch: int | None = None,
        payload: dict[str, object],
        log: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        log = log or (lambda _msg: None)
        cleaned = self._validate_id_rules_config(payload)
        cleaned["updated_at"] = _utc_now()

        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    instance = self._default_instance()
                else:
                    raise
            self._assert_admin(
                instance, machine_id=machine_id, expected_admin_epoch=expected_admin_epoch
            )
            cleaned["published_by"] = {
                "application": "GFileStudio",
                "machine_name": str(machine_name or "").strip(),
                "ip": self._connection_ip(ssh),
            }
            log(f"更新中央 ID 规则：{self.id_rules_path}")
            self._atomic_replace_bytes(
                sftp,
                self.id_rules_path,
                (json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            instance = self._bump_instance(instance)
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            final_rules = self._validate_id_rules_config(self._read_json(sftp, self.id_rules_path))
            return {
                "instance": instance,
                "id_rules": final_rules,
                "remote_path": self.id_rules_path,
            }
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    @staticmethod
    def _validate_database_config(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("database.json 必须是 JSON 对象。")
        result = {
            "schema_version": 1,
            "username": str(payload.get("username", "") or "").strip(),
            "password": str(payload.get("password", "") or ""),
            "host": str(payload.get("host", "") or "").strip(),
            "port": int(payload.get("port", 1521) or 1521),
            "service_name": str(payload.get("service_name", "") or "").strip(),
            "updated_at": str(payload.get("updated_at", "") or "").strip() or _utc_now(),
        }
        if not result["username"] or not result["password"] or not result["host"] or not result["service_name"]:
            raise ValueError("database.json 缺少用户名、密码、服务器地址或 Service Name。")
        if not 1 <= int(result["port"]) <= 65535:
            raise ValueError("database.json 数据库端口无效。")
        return result

    @staticmethod
    def _validate_file_server_config(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise ValueError("file_server.json 必须是 JSON 对象。")
        result = {
            "schema_version": 1,
            "host": str(payload.get("host", "") or "").strip(),
            "port": int(payload.get("port", 22) or 22),
            "username": str(payload.get("username", "") or "").strip(),
            "password": str(payload.get("password", "") or ""),
            "business_g_directory": str(payload.get("business_g_directory", "") or "").strip(),
            "symbol_library_root": str(payload.get("symbol_library_root", "") or "").strip(),
            "updated_at": str(payload.get("updated_at", "") or "").strip() or _utc_now(),
        }
        if not result["host"] or not result["username"] or not result["password"]:
            raise ValueError("file_server.json 缺少 SSH 主机、用户名或密码。")
        if not result["business_g_directory"] or not result["symbol_library_root"]:
            raise ValueError("file_server.json 缺少业务 G 或标准图元目录。")
        if not 1 <= int(result["port"]) <= 65535:
            raise ValueError("file_server.json SSH 端口无效。")
        return result

    def fetch_database_config(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> dict[str, object]:
        """Read and validate only database.json plus instance.json (read-only)."""
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            try:
                database = self._validate_database_config(self._read_json(sftp, self.database_path))
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError("中央 database.json 尚未创建，请由管理员首次发布数据库配置。") from exc
                raise
            instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            return {"instance": instance, "database": database}
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def fetch_file_server_config(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> dict[str, object]:
        """Read and validate only file_server.json plus instance.json (read-only)."""
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            try:
                file_server = self._validate_file_server_config(self._read_json(sftp, self.file_server_path))
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError("中央 file_server.json 尚未创建，请由管理员首次发布文件服务器配置。") from exc
                raise
            instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            return {"instance": instance, "file_server": file_server}
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def fetch_connection_configs(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> dict[str, object]:
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            try:
                database = self._validate_database_config(self._read_json(sftp, self.database_path))
                file_server = self._validate_file_server_config(self._read_json(sftp, self.file_server_path))
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError("中央数据库或文件服务器配置尚未创建，请由管理员首次发布。") from exc
                raise
            instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            return {
                "instance": instance,
                "database": database,
                "file_server": file_server,
            }
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def fetch_all_configs(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        log: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        """Download every operator-managed central configuration in one SSH session.

        The method is intentionally read-only.  All files are read and validated before
        the caller changes any workstation-local cache, so a missing/corrupt central
        file aborts the bulk sync before local settings are touched.
        """
        log = log or (lambda _msg: None)
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            log(f"读取中央全量配置目录：{self.config_dir}")
            try:
                log(f"读取：{self.database_path}")
                database = self._validate_database_config(
                    self._read_json(sftp, self.database_path)
                )
                log(f"读取：{self.file_server_path}")
                file_server = self._validate_file_server_config(
                    self._read_json(sftp, self.file_server_path)
                )
                log(f"读取：{self.id_rules_path}")
                id_rules = self._validate_id_rules_config(
                    self._read_json(sftp, self.id_rules_path)
                )
                log(f"读取：{self.remote_path}")
                classification = self._validate_payload(
                    self._read_json(sftp, self.remote_path)
                )
                log(f"读取：{self.instance_path}")
                instance = self._normalize_instance(
                    self._read_json(sftp, self.instance_path)
                )
            except OSError as exc:
                if self._is_missing(exc):
                    raise FileNotFoundError(
                        "中央全量配置不完整：database.json、file_server.json、"
                        "id_rules.json、symbol_classification.json 和 instance.json "
                        "必须全部存在。请由管理员先补齐中央配置。"
                    ) from exc
                raise
            log("中央全量配置读取并校验完成。")
            return {
                "instance": instance,
                "database": database,
                "file_server": file_server,
                "id_rules": id_rules,
                "classification": {
                    "remote_path": self.remote_path,
                    "updated_at": str(classification.get("updated_at", "") or ""),
                    "marker_count": len(classification.get("markers", [])),
                    "payload": classification,
                },
            }
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def _publish_single_connection_file(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        expected_admin_epoch: int | None,
        file_name: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    instance = self._default_instance()
                else:
                    raise
            self._assert_admin(
                instance, machine_id=machine_id, expected_admin_epoch=expected_admin_epoch
            )
            path = self.database_path if file_name == DATABASE_FILE_NAME else self.file_server_path
            self._atomic_replace_bytes(
                sftp,
                path,
                (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            instance = self._bump_instance(instance)
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            return {"instance": instance, file_name.removesuffix(".json"): payload, "remote_path": path}
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()

    def publish_database_config(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        expected_admin_epoch: int | None = None,
        database: dict[str, object],
    ) -> dict[str, object]:
        clean = self._validate_database_config(database)
        clean["updated_at"] = _utc_now()
        return self._publish_single_connection_file(
            host=host, port=port, username=username, password=password,
            machine_id=machine_id, expected_admin_epoch=expected_admin_epoch,
            file_name=DATABASE_FILE_NAME, payload=clean,
        )

    def publish_file_server_config(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        expected_admin_epoch: int | None = None,
        file_server: dict[str, object],
    ) -> dict[str, object]:
        clean = self._validate_file_server_config(file_server)
        clean["updated_at"] = _utc_now()
        return self._publish_single_connection_file(
            host=host, port=port, username=username, password=password,
            machine_id=machine_id, expected_admin_epoch=expected_admin_epoch,
            file_name=FILE_SERVER_FILE_NAME, payload=clean,
        )

    def publish_connection_configs(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        machine_id: str,
        expected_admin_epoch: int | None = None,
        database: dict[str, object],
        file_server: dict[str, object],
    ) -> dict[str, object]:
        database_clean = self._validate_database_config(database)
        file_server_clean = self._validate_file_server_config(file_server)
        now = _utc_now()
        database_clean["updated_at"] = now
        file_server_clean["updated_at"] = now

        ssh = sftp = None
        try:
            ssh, sftp = self._connect(host=host, port=port, username=username, password=password)
            self._mkdir_p(sftp, self.config_dir)
            try:
                instance = self._normalize_instance(self._read_json(sftp, self.instance_path))
            except OSError as exc:
                if self._is_missing(exc):
                    instance = self._default_instance()
                else:
                    raise
            self._assert_admin(
                instance, machine_id=machine_id, expected_admin_epoch=expected_admin_epoch
            )
            self._atomic_replace_bytes(
                sftp,
                self.database_path,
                (json.dumps(database_clean, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            self._atomic_replace_bytes(
                sftp,
                self.file_server_path,
                (json.dumps(file_server_clean, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            instance = self._bump_instance(instance)
            self._atomic_replace_bytes(
                sftp,
                self.instance_path,
                (json.dumps(instance, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            )
            return {
                "instance": instance,
                "database": database_clean,
                "file_server": file_server_clean,
            }
        finally:
            try:
                if sftp is not None:
                    sftp.close()
            finally:
                if ssh is not None:
                    ssh.close()
