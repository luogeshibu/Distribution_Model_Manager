from __future__ import annotations

import hashlib
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


DEFAULT_SSH_HOST = "172.16.21.27"
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USERNAME = "up8000"
DEFAULT_SSH_PASSWORD = "up8000"
DEFAULT_SSH_REMOTE_DIRECTORY = "/home/up8000/data/graph/display/sln"


class RemoteDependencyError(RuntimeError):
    pass


class RemoteFileChangedDuringDownload(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteGFile:
    name: str
    remote_path: str
    size: int
    mtime_epoch: int

    @property
    def mtime_text(self) -> str:
        return datetime.fromtimestamp(self.mtime_epoch).strftime("%Y-%m-%d %H:%M:%S")


class ReadOnlySshClient:
    """严格只读的 SSH/SFTP 客户端。

    只暴露连接测试、列目录、读取属性和下载。刻意不提供 put/remove/rename/mkdir。
    """

    def __init__(self, host: str, port: int, username: str, password: str, timeout: float = 10.0):
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
                "未安装 SSH 依赖 paramiko。请执行：python -m pip install paramiko"
            ) from exc
        return paramiko

    def connect(self) -> None:
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
        self._sftp.normalize(".")

    def list_g_files(self, remote_directory: str) -> list[RemoteGFile]:
        self.connect()
        remote_directory = str(remote_directory).strip()
        if not remote_directory:
            raise ValueError("远程 G 文件目录不能为空。")
        rows: list[RemoteGFile] = []
        for attr in self._sftp.listdir_attr(remote_directory):
            name = str(attr.filename)
            if not name.lower().endswith(".g"):
                continue
            rows.append(
                RemoteGFile(
                    name=name,
                    remote_path=str(PurePosixPath(remote_directory) / name),
                    size=int(attr.st_size),
                    mtime_epoch=int(attr.st_mtime),
                )
            )
        rows.sort(key=lambda item: item.name.casefold())
        return rows

    def stat_file(self, remote_path: str) -> RemoteGFile:
        self.connect()
        attr = self._sftp.stat(remote_path)
        return RemoteGFile(
            name=PurePosixPath(remote_path).name,
            remote_path=str(remote_path),
            size=int(attr.st_size),
            mtime_epoch=int(attr.st_mtime),
        )

    def download_file(self, remote_path: str, local_path: str) -> None:
        self.connect()
        self._sftp.get(str(remote_path), str(local_path))

    def close(self) -> None:
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


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_stable_files(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    selected_files: Iterable[RemoteGFile],
    target_dir: Path,
    log: Callable[[str], None] | None = None,
    max_attempts: int = 3,
    clear_target: bool = True,
    progress: Callable[[int], None] | None = None,
) -> list[Path]:
    """把当前所选远程 G 文件下载为稳定的本地只读快照。"""
    selected = list(selected_files)
    if not selected:
        raise ValueError("没有选择任何远程 G 文件。")
    log = log or (lambda _msg: None)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 模块运行缓存每次以“本次选择”为准，避免旧缓存混入处理范围。
    # 用户主动“下载到本地”时 clear_target=False，绝不删除目标目录里的其他 G 文件。
    if clear_target:
        for old in target_dir.glob("*.g"):
            old.unlink(missing_ok=True)
        for old in target_dir.glob("*.downloading"):
            old.unlink(missing_ok=True)

    result: list[Path] = []
    if progress:
        progress(0)
    with ReadOnlySshClient(host, port, username, password) as client:
        for index, listed in enumerate(selected, 1):
            local_path = target_dir / listed.name
            stable = None
            for attempt in range(1, max_attempts + 1):
                before = client.stat_file(listed.remote_path)
                temp_path = local_path.with_name(local_path.name + ".downloading")
                temp_path.unlink(missing_ok=True)
                log(
                    f"[SSH {index}/{len(selected)}] 下载 {before.name} | "
                    f"{human_size(before.size)} | {before.mtime_text} | attempt={attempt}"
                )
                client.download_file(before.remote_path, str(temp_path))
                after = client.stat_file(before.remote_path)
                if (
                    before.size == after.size
                    and before.mtime_epoch == after.mtime_epoch
                    and temp_path.exists()
                    and temp_path.stat().st_size == after.size
                ):
                    temp_path.replace(local_path)
                    stable = after
                    break
                temp_path.unlink(missing_ok=True)
                if attempt < max_attempts:
                    time.sleep(0.4)
            if stable is None:
                raise RemoteFileChangedDuringDownload(
                    f"无法取得稳定的服务器文件版本：{listed.remote_path}。请稍后重试。"
                )
            log(f"  完成：{local_path.name} | SHA256={_sha256(local_path)}")
            result.append(local_path)
            if progress:
                progress(round(index * 100 / len(selected)))
    return result


def copy_downloaded_files(files: Iterable[Path], destination: Path) -> list[Path]:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for source in files:
        target = destination / Path(source).name
        shutil.copy2(source, target)
        outputs.append(target)
    return outputs
