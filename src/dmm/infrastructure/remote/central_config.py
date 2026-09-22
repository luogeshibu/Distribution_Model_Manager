from __future__ import annotations

import json
import posixpath
import shlex
import socket
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath


CENTRAL_CONFIG_FILES = {
    "instance": "instance.json",
    "element_marks": "element_marks.json",
    "database": "database.json",
    "file_server": "file_server.json",
}


class CentralConfigError(RuntimeError):
    """Raised when the shared configuration cannot be read or changed."""


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_machine_id() -> str:
    """Return a stable-enough local identity without exposing user data."""
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"


def local_machine_name() -> str:
    """Return the local host name used for Admin audit and verification."""
    return socket.gethostname().strip() or "unknown-host"


def local_machine_ip(server_host: str = "") -> str:
    """Resolve the local address used to reach the central server.

    The address is recorded for display/audit only.  It is deliberately not
    used as the machine's identity because DHCP or a VPN can change it.
    """
    target = str(server_host or "").strip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.5)
        if target:
            sock.connect((target, 22))
            address = str(sock.getsockname()[0] or "").strip()
            if address:
                return address
    except Exception:
        pass
    finally:
        sock.close()
    try:
        return str(socket.gethostbyname(socket.gethostname()) or "").strip()
    except Exception:
        return ""


def local_machine_info(server_host: str = "") -> tuple[str, str]:
    return local_machine_name(), local_machine_ip(server_host)


class CentralConfigClient:
    """Read and publish the shared NARI configuration over SFTP.

    The existing read-only G-file client intentionally remains read-only. This
    separate client is used only for the explicitly approved central config
    directory and writes through temporary files followed by atomic rename.
    """

    def __init__(self, config: dict):
        self.config = dict(config or {})
        self.host = str(self.config.get("host", "")).strip()
        self.port = int(self.config.get("port", 22) or 22)
        self.username = str(self.config.get("username", "")).strip()
        self.password = str(self.config.get("password", ""))
        self.root = str(
            self.config.get(
                "remote_directory",
                "/home/up8000/nari-international/distribution-model-manager/config",
            )
        ).rstrip("/")
        self._ssh = None
        self._sftp = None

    @staticmethod
    def _paramiko():
        try:
            import paramiko
        except ImportError as exc:
            raise CentralConfigError(
                "未安装中央配置同步所需的 SSH 依赖 paramiko。"
            ) from exc
        return paramiko

    def connect(self):
        if self._ssh is not None:
            return
        if not self.host or not self.username:
            raise CentralConfigError("中央配置服务器地址或用户名为空。")
        paramiko = self._paramiko()
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,
                auth_timeout=10,
                banner_timeout=10,
                look_for_keys=False,
                allow_agent=False,
            )
            self._ssh = ssh
            self._sftp = ssh.open_sftp()
        except Exception as exc:
            ssh.close()
            raise CentralConfigError(f"连接中央配置服务器失败：{exc}") from exc

    def close(self):
        sftp, ssh = self._sftp, self._ssh
        self._sftp = None
        self._ssh = None
        try:
            if sftp is not None:
                sftp.close()
        finally:
            if ssh is not None:
                ssh.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _path(self, name: str) -> str:
        if name not in CENTRAL_CONFIG_FILES.values():
            raise CentralConfigError(f"不允许访问中央配置文件：{name}")
        return posixpath.join(self.root, name)

    def ensure_root(self):
        """Create only missing central directories during first initialization."""
        self.connect()
        command = f"mkdir -p -- {shlex.quote(self.root)}"
        _stdin, stdout, stderr = self._ssh.exec_command(command)
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            detail = stderr.read().decode("utf-8", errors="replace").strip()
            raise CentralConfigError(
                f"创建中央配置目录失败：{detail or 'unknown error'}"
            )

    def read_json(self, name: str, required=False) -> dict | None:
        self.connect()
        try:
            with self._sftp.open(self._path(name), "r") as handle:
                raw = handle.read()
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if not str(raw).strip():
                    return None
                payload = json.loads(raw)
        except FileNotFoundError:
            if required:
                raise CentralConfigError(f"中央配置文件不存在：{name}")
            return None
        except Exception as exc:
            raise CentralConfigError(f"读取中央配置文件失败（{name}）：{exc}") from exc
        if not isinstance(payload, dict):
            raise CentralConfigError(f"中央配置文件格式错误：{name}")
        return payload

    def _write_json(self, name: str, payload: dict):
        self.connect()
        path = self._path(name)
        temp = f"{path}.{uuid.uuid4().hex}.tmp"
        data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        try:
            with self._sftp.file(temp, "wb") as handle:
                handle.write(data)
                handle.flush()
            self._sftp.chmod(temp, 0o600)
            # The OpenSSH SFTP server used by the site rejects rename when
            # the destination already exists.  Both files are on the same
            # filesystem, so a server-local mv keeps replacement atomic and
            # works for both first creation and later updates.
            _stdin, stdout, stderr = self._ssh.exec_command(
                f"mv -f -- {shlex.quote(temp)} {shlex.quote(path)}"
            )
            exit_code = stdout.channel.recv_exit_status()
            if exit_code != 0:
                detail = stderr.read().decode("utf-8", errors="replace").strip()
                raise OSError(detail or "server-side replacement failed")
            self._sftp.chmod(path, 0o600)
        except Exception as exc:
            try:
                self._sftp.remove(temp)
            except Exception:
                pass
            raise CentralConfigError(f"写入中央配置文件失败（{name}）：{exc}") from exc

    def _lock(self):
        self.connect()
        path = posixpath.join(self.root, ".config.lock")
        for attempt in range(2):
            try:
                # Use RHEL's native mkdir through the SSH channel. mkdir is
                # atomic and returns non-zero when another client owns it.
                _stdin, _stdout, stderr = self._ssh.exec_command(
                    f"mkdir {shlex.quote(path)}"
                )
                exit_code = _stdout.channel.recv_exit_status()
                if exit_code == 0:
                    return path
                detail = stderr.read().decode("utf-8", errors="replace").strip()
                raise OSError(detail or "lock directory already exists")
            except Exception as exc:
                # A crashed process may leave the lock behind. Reclaim only
                # a lock older than 30 minutes; a live update is never touched.
                try:
                    attrs = self._sftp.stat(path)
                    age = time.time() - float(attrs.st_mtime or 0)
                    if attempt == 0 and age > 1800:
                        if stat.S_ISDIR(int(attrs.st_mode or 0)):
                            self._sftp.rmdir(path)
                        else:
                            self._sftp.remove(path)
                        continue
                except Exception:
                    pass
                raise CentralConfigError(
                    "中央配置正在被另一台机器初始化或更新，请稍后重试。"
                ) from exc

    def _unlock(self, path):
        try:
            _stdin, _stdout, _stderr = self._ssh.exec_command(
                f"rmdir {shlex.quote(path)}"
            )
            _stdout.channel.recv_exit_status()
        except Exception:
            pass

    def read_bundle(self) -> dict | None:
        instance = self.read_json(CENTRAL_CONFIG_FILES["instance"])
        if not instance:
            return None
        if not bool(instance.get("initialized")):
            return {"instance": instance}
        element_marks = self.read_json(CENTRAL_CONFIG_FILES["element_marks"])
        database = self.read_json(CENTRAL_CONFIG_FILES["database"])
        file_server = self.read_json(CENTRAL_CONFIG_FILES["file_server"])
        if any(
            value is None or not isinstance(value, dict) or not value
            for value in (element_marks, database, file_server)
        ):
            incomplete_instance = dict(instance)
            incomplete_instance["initialized"] = False
            incomplete_instance["central_files_empty"] = True
            return {"instance": incomplete_instance}
        return {
            "instance": instance,
            "element_marks": element_marks,
            "database": database,
            "file_server": file_server,
        }

    @staticmethod
    def _database_payload(settings: dict) -> dict:
        return {
            "schema_version": 1,
            "configured": bool(settings.get("db")),
            "settings": dict(settings.get("db", {}) or {}),
        }

    @staticmethod
    def _file_server_payload(settings: dict) -> dict:
        return {
            "schema_version": 1,
            "configured": bool(settings.get("ssh")),
            "settings": dict(settings.get("ssh", {}) or {}),
        }

    @staticmethod
    def _element_marks_payload(settings: dict) -> dict:
        catalog = dict(settings.get("element_catalog", {}) or {})
        records = catalog.get("records", [])
        return {
            "schema": "element-marks",
            "schema_version": 1,
            "records": list(records) if isinstance(records, list) else [],
        }

    def _write_bundle(
        self,
        settings: dict,
        machine_id: str,
        machine_name: str,
        machine_ip: str,
        previous=None,
    ):
        previous = dict(previous or {})
        old_version = int(previous.get("config_version", 0) or 0)
        version = old_version + 1
        claimed_at = str(previous.get("admin_claimed_at") or "").strip()
        if not claimed_at or str(previous.get("admin_machine_id") or "") != str(
            machine_id
        ):
            claimed_at = utc_now_text()
        self._write_json(
            CENTRAL_CONFIG_FILES["element_marks"],
            self._element_marks_payload(settings),
        )
        self._write_json(
            CENTRAL_CONFIG_FILES["database"], self._database_payload(settings)
        )
        self._write_json(
            CENTRAL_CONFIG_FILES["file_server"],
            self._file_server_payload(settings),
        )
        self._write_json(
            CENTRAL_CONFIG_FILES["instance"],
            {
                "schema_version": 1,
                "initialized": True,
                "admin_status": "active",
                "admin_machine_id": machine_id,
                "admin_machine_name": machine_name,
                "admin_ip": machine_ip,
                "admin_claimed_at": claimed_at,
                "config_version": version,
                "updated_at": utc_now_text(),
                "files": dict(CENTRAL_CONFIG_FILES),
            },
        )
        return version

    def initialize(
        self, settings: dict, machine_id: str, machine_name: str, machine_ip: str
    ) -> int:
        # The application, not deployment preparation, owns first-run setup.
        # Existing directories are reused by mkdir -p and are never replaced.
        self.ensure_root()
        lock = self._lock()
        try:
            current = self.read_json(CENTRAL_CONFIG_FILES["instance"])
            if current and bool(current.get("initialized")):
                sync_files = {
                    name: self.read_json(filename)
                    for name, filename in CENTRAL_CONFIG_FILES.items()
                    if name != "instance"
                }
                files_empty = any(
                    value is None
                    or not isinstance(value, dict)
                    or not value
                    for value in sync_files.values()
                )
                current_admin_id = str(current.get("admin_machine_id") or "")
                current_admin_name = str(current.get("admin_machine_name") or "")
                is_recorded_admin = (
                    current_admin_id == str(machine_id)
                    and (
                        not current_admin_name
                        or current_admin_name == str(machine_name)
                    )
                )
                if current.get("admin_status") != "unassigned" and not (
                    files_empty and is_recorded_admin
                ):
                    raise CentralConfigError(
                        "中央配置已经存在 Admin；只有当前 Admin 在同步文件为空时才能重新初始化。"
                    )
            return self._write_bundle(
                settings, machine_id, machine_name, machine_ip, current
            )
        finally:
            self._unlock(lock)

    def publish(
        self, settings: dict, machine_id: str, machine_name: str, machine_ip: str
    ) -> int:
        lock = self._lock()
        try:
            current = self.read_json(CENTRAL_CONFIG_FILES["instance"])
            if not current or not bool(current.get("initialized")):
                raise CentralConfigError("中央配置尚未初始化，请先完成 Admin 初始化。")
            current_admin_id = str(current.get("admin_machine_id") or "")
            current_admin_name = str(current.get("admin_machine_name") or "")
            if current_admin_id != str(machine_id) or (
                current_admin_name and current_admin_name != str(machine_name)
            ):
                raise CentralConfigError("当前机器不是 Admin，不能发布中央配置。")
            return self._write_bundle(
                settings, machine_id, machine_name, machine_ip, current
            )
        finally:
            self._unlock(lock)

    def release_admin(self, machine_id: str, machine_name: str) -> int:
        lock = self._lock()
        try:
            current = self.read_json(CENTRAL_CONFIG_FILES["instance"], required=True)
            current_admin_id = str(current.get("admin_machine_id") or "")
            current_admin_name = str(current.get("admin_machine_name") or "")
            if current_admin_id != str(machine_id) or (
                current_admin_name and current_admin_name != str(machine_name)
            ):
                raise CentralConfigError("当前机器不是 Admin，不能释放 Admin 权限。")
            version = int(current.get("config_version", 0) or 0) + 1
            released_at = utc_now_text()
            current.update(
                {
                    "admin_status": "unassigned",
                    "admin_machine_id": None,
                    "admin_machine_name": None,
                    "admin_ip": None,
                    "admin_released_at": released_at,
                    "last_admin": {
                        "machine_id": current.get("admin_machine_id"),
                        "machine_name": current.get("admin_machine_name"),
                        "ip": current.get("admin_ip"),
                        "claimed_at": current.get("admin_claimed_at"),
                        "released_at": released_at,
                    },
                    "config_version": version,
                    "updated_at": released_at,
                }
            )
            self._write_json(CENTRAL_CONFIG_FILES["instance"], current)
            return version
        finally:
            self._unlock(lock)
