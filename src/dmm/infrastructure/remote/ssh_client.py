from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Iterable


class RemoteDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteGFile:
    name: str
    remote_path: str
    size: int
    mtime_epoch: int

    @property
    def mtime_text(self) -> str:
        return datetime.fromtimestamp(self.mtime_epoch).strftime(
            "%Y-%m-%d %H:%M:%S"
        )


class ReadOnlySshClient:
    """
    Strict read-only SSH/SFTP client.

    Deliberately exposes only:
      - test_connection
      - list_g_files
      - stat_file
      - download_file
      - close

    There is intentionally no upload/put/remove/rename/mkdir API.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 10.0,
    ):
        self.host = str(host).strip()
        self.port = int(port)
        self.username = str(username).strip()
        self.password = str(password)
        self.timeout = float(timeout)
        self._ssh = None
        self._sftp = None

    @staticmethod
    def _paramiko():
        try:
            import paramiko
        except ImportError as exc:
            raise RemoteDependencyError(
                "未安装 SSH 依赖 paramiko。请执行："
                "python -m pip install paramiko"
            ) from exc
        return paramiko

    def connect(self):
        if self._ssh is not None:
            return
        if not self.host:
            raise ValueError("SSH IP/主机不能为空。")
        if not self.username:
            raise ValueError("SSH 用户名不能为空。")

        paramiko = self._paramiko()
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            auth_timeout=self.timeout,
            banner_timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        self._ssh = ssh
        self._sftp = ssh.open_sftp()

    def test_connection(self) -> None:
        self.connect()
        # A harmless read-only call verifies the SFTP channel too.
        self._sftp.normalize(".")

    def list_g_files(self, remote_directory: str) -> list[RemoteGFile]:
        self.connect()
        remote_directory = str(remote_directory).strip()
        if not remote_directory:
            raise ValueError("远程 G 文件目录不能为空。")

        rows: list[RemoteGFile] = []
        for attr in self._sftp.listdir_attr(remote_directory):
            name = str(attr.filename)
            # Important: only the real *.g file, excluding .g.h/.g.data/.g.png.
            if not name.lower().endswith(".g"):
                continue
            path = str(PurePosixPath(remote_directory) / name)
            rows.append(
                RemoteGFile(
                    name=name,
                    remote_path=path,
                    size=int(attr.st_size),
                    mtime_epoch=int(attr.st_mtime),
                )
            )
        rows.sort(key=lambda item: item.name.lower())
        return rows

    def stat_file(self, remote_path: str) -> RemoteGFile:
        self.connect()
        attr = self._sftp.stat(remote_path)
        name = PurePosixPath(remote_path).name
        return RemoteGFile(
            name=name,
            remote_path=str(remote_path),
            size=int(attr.st_size),
            mtime_epoch=int(attr.st_mtime),
        )

    def download_file(self, remote_path: str, local_path: str) -> None:
        self.connect()
        # SFTP.get is a read from server to local filesystem only.
        self._sftp.get(str(remote_path), str(local_path))

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
