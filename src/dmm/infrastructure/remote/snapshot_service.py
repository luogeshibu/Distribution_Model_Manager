from __future__ import annotations

import hashlib
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from .ssh_client import ReadOnlySshClient, RemoteGFile


class RemoteFileChangedDuringDownload(RuntimeError):
    pass


class RemoteSnapshotService:
    """
    Download the latest stable server version into the current run directory.

    Freshness rule:
      Every new model validation calls this service and downloads again.
      No previous local snapshot is reused.

    Stability rule:
      stat-before -> download -> stat-after.
      Size and mtime must match. Otherwise discard and retry.

    Association rule:
      This service is NOT called by association. Association uses the exact
      local remote_input snapshot created by the corresponding validation.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        remote_directory: str,
        max_attempts: int = 3,
        retry_delay: float = 0.6,
    ):
        self.host = str(host).strip()
        self.port = int(port)
        self.username = str(username).strip()
        self.password = str(password)
        self.remote_directory = str(remote_directory).strip()
        self.max_attempts = int(max_attempts)
        self.retry_delay = float(retry_delay)

    @staticmethod
    def sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def download_latest(
        self,
        selected_files: Iterable[RemoteGFile],
        run_dir: Path,
        log: Callable[[str], None] | None = None,
    ) -> tuple[list[Path], dict]:
        log = log or (lambda _msg: None)
        selected = list(selected_files)
        if not selected:
            raise ValueError("没有选择任何远程 G 文件。")

        target_dir = Path(run_dir) / "remote_input"
        target_dir.mkdir(parents=True, exist_ok=True)

        def download_one(client, listed, display_index):
            remote_path = listed.remote_path
            local_path = target_dir / listed.name

            stable = None
            for attempt in range(1, self.max_attempts + 1):
                before = client.stat_file(remote_path)
                log(
                    f"[{display_index}/{len(selected)}] 获取最新文件："
                    f"{before.name} | size={before.size} | "
                    f"mtime={before.mtime_text} | attempt={attempt}"
                )

                temp_path = local_path.with_suffix(
                    local_path.suffix + ".downloading"
                )
                temp_path.unlink(missing_ok=True)
                client.download_file(remote_path, str(temp_path))
                after = client.stat_file(remote_path)

                if (
                    before.size == after.size
                    and before.mtime_epoch == after.mtime_epoch
                    and temp_path.stat().st_size == after.size
                ):
                    temp_path.replace(local_path)
                    stable = after
                    break

                temp_path.unlink(missing_ok=True)
                log(
                    f"  远程文件在下载过程中发生变化：{before.name}；"
                    f"before(size={before.size},mtime={before.mtime_text})；"
                    f"after(size={after.size},mtime={after.mtime_text})。"
                )
                if attempt < self.max_attempts:
                    log("  正在重新获取服务器最新稳定版本……")
                    time.sleep(self.retry_delay)

            if stable is None:
                raise RemoteFileChangedDuringDownload(
                    f"无法取得稳定的服务器文件版本：{remote_path}。"
                    f"文件在连续 {self.max_attempts} 次下载期间均发生变化，"
                    "请稍后重新执行模型校验。"
                )

            sha256 = self.sha256_file(local_path)
            info = {
                "name": stable.name,
                "remote_path": stable.remote_path,
                "remote_size": stable.size,
                "remote_mtime_epoch": stable.mtime_epoch,
                "remote_mtime": stable.mtime_text,
                "download_time": datetime.now().isoformat(
                    timespec="seconds"
                ),
                "local_snapshot_path": str(local_path),
                "sha256": sha256,
            }
            log(
                f"  远程快照下载完成：{stable.name}"
                f" | SHA256={sha256}"
            )
            return local_path, info

        metadata_by_path: dict[str, dict] = {}
        local_by_path: dict[str, Path] = {}

        with ReadOnlySshClient(
            self.host,
            self.port,
            self.username,
            self.password,
        ) as client:
            log(
                f"SSH只读文件源：{self.host}:{self.port}"
                f" | {self.remote_directory}"
            )
            log(
                "每次模型校验均重新从服务器获取当前最新 G 文件；"
                "不会使用历史下载缓存。"
            )

            # Initial fresh download of every selected file.
            for index, listed in enumerate(selected, start=1):
                local_path, info = download_one(
                    client,
                    listed,
                    index,
                )
                local_by_path[listed.remote_path] = local_path
                metadata_by_path[listed.remote_path] = info

            # Important for multi-file runs:
            # File A can change on the server while file B is downloading.
            # Before validation begins, sweep ALL selected remote files again.
            # Any changed file is re-downloaded, and the entire set is checked
            # again. This prevents an old A snapshot from being validated just
            # because A itself was stable earlier in the batch.
            for batch_round in range(1, self.max_attempts + 1):
                changed = []
                for listed in selected:
                    latest = client.stat_file(listed.remote_path)
                    saved = metadata_by_path[listed.remote_path]
                    if (
                        int(saved["remote_size"]) != latest.size
                        or int(saved["remote_mtime_epoch"])
                        != latest.mtime_epoch
                    ):
                        changed.append((listed, latest))

                if not changed:
                    log(
                        "服务器最终一致性检查通过："
                        "所有已选 G 文件在模型校验开始前均为最新稳定版本。"
                    )
                    break

                log(
                    f"服务器最终一致性检查发现 {len(changed)} 个文件"
                    "在批量下载期间再次更新，正在重新获取最新版本。"
                )
                if batch_round >= self.max_attempts:
                    names = ", ".join(
                        item.name for item, _latest in changed
                    )
                    raise RemoteFileChangedDuringDownload(
                        "无法在模型校验开始前取得一组稳定的最新服务器文件："
                        f"{names}。请稍后重新执行。"
                    )

                for listed, _latest in changed:
                    display_index = selected.index(listed) + 1
                    local_path, info = download_one(
                        client,
                        listed,
                        display_index,
                    )
                    local_by_path[listed.remote_path] = local_path
                    metadata_by_path[listed.remote_path] = info

        snapshot_files = [
            local_by_path[item.remote_path]
            for item in selected
        ]
        metadata = [
            metadata_by_path[item.remote_path]
            for item in selected
        ]

        source_info = {
            "source_type": "SSH",
            "read_only": True,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "remote_directory": self.remote_directory,
            "download_policy": "ALWAYS_LATEST_ON_VALIDATION",
            "batch_consistency_policy": "FINAL_STAT_SWEEP_AND_REDOWNLOAD",
            "association_policy": "USE_VALIDATION_SNAPSHOT_ONLY",
            "files": metadata,
        }
        return snapshot_files, source_info
