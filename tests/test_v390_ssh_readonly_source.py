
from pathlib import Path
from types import SimpleNamespace

from dmm.infrastructure.remote.ssh_client import (
    ReadOnlySshClient,
    RemoteGFile,
)
from dmm.infrastructure.remote import snapshot_service as snapshot_module
from dmm.infrastructure.remote.snapshot_service import RemoteSnapshotService


def test_read_only_ssh_client_exposes_no_server_write_methods():
    forbidden = {
        "put",
        "upload",
        "upload_file",
        "remove",
        "delete",
        "rename",
        "mkdir",
        "rmdir",
        "write",
    }
    assert forbidden.isdisjoint(set(dir(ReadOnlySshClient)))


def test_remote_listing_accepts_only_real_dot_g_files():
    client = ReadOnlySshClient("host", 22, "user", "password")
    client._ssh = object()

    class FakeSftp:
        def listdir_attr(self, path):
            return [
                SimpleNamespace(
                    filename="A.sln.pic.g",
                    st_size=100,
                    st_mtime=10,
                ),
                SimpleNamespace(
                    filename="A.sln.pic.g.h",
                    st_size=20,
                    st_mtime=10,
                ),
                SimpleNamespace(
                    filename="A.sln.pic.g.data",
                    st_size=30,
                    st_mtime=10,
                ),
                SimpleNamespace(
                    filename="A.sln.pic.g.png",
                    st_size=40,
                    st_mtime=10,
                ),
            ]

    client._sftp = FakeSftp()
    rows = client.list_g_files("/remote")
    assert [row.name for row in rows] == ["A.sln.pic.g"]


def test_every_validation_snapshot_downloads_and_retries_if_server_changes(
    tmp_path,
    monkeypatch,
):
    remote = RemoteGFile(
        name="A.sln.pic.g",
        remote_path="/remote/A.sln.pic.g",
        size=3,
        mtime_epoch=100,
    )

    created_clients = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.stat_calls = 0
            self.download_calls = 0
            created_clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stat_file(self, path):
            self.stat_calls += 1
            # First download attempt changes from version 100 -> 101.
            # Second attempt is stable on version 101.
            if self.stat_calls == 1:
                return RemoteGFile("A.sln.pic.g", path, 3, 100)
            return RemoteGFile("A.sln.pic.g", path, 3, 101)

        def download_file(self, remote_path, local_path):
            self.download_calls += 1
            Path(local_path).write_bytes(b"new")

    monkeypatch.setattr(
        snapshot_module,
        "ReadOnlySshClient",
        FakeClient,
    )

    service = RemoteSnapshotService(
        host="172.16.21.27",
        port=22,
        username="up8000",
        password="up8000",
        remote_directory="/remote",
        retry_delay=0,
    )
    paths, info = service.download_latest(
        [remote],
        tmp_path,
    )

    assert len(paths) == 1
    assert paths[0].read_bytes() == b"new"
    assert created_clients[0].download_calls == 2
    assert info["read_only"] is True
    assert info["download_policy"] == "ALWAYS_LATEST_ON_VALIDATION"
    assert info["association_policy"] == "USE_VALIDATION_SNAPSHOT_ONLY"
    assert info["files"][0]["remote_mtime_epoch"] == 101
    assert len(info["files"][0]["sha256"]) == 64


def test_main_window_ssh_association_uses_validation_snapshot_only():
    source = (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")

    assert "SSH 文件服务器（只读）" in source
    assert "RemoteSnapshotService" in source
    assert "self.current_snapshot_files" in source
    assert "不会再次从服务器下载" in source
    assert "模型校验已锁定 remote_input 快照" in source


def test_default_ssh_connection_points_to_field_server():
    defaults = (
        Path(__file__).parents[1]
        / "src/dmm/config/defaults.py"
    ).read_text(encoding="utf-8")

    assert '"host": "172.16.21.27"' in defaults
    assert '"username": "up8000"' in defaults
    assert '"/home/up8000/data/graph/display/sln"' in defaults


def test_batch_final_sweep_redownloads_file_that_changed_while_others_download(
    tmp_path,
    monkeypatch,
):
    a = RemoteGFile("A.g", "/remote/A.g", 1, 100)
    b = RemoteGFile("B.g", "/remote/B.g", 1, 100)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.download_counts = {"A.g": 0, "B.g": 0}
            self.stat_counts = {"A.g": 0, "B.g": 0}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stat_file(self, path):
            name = Path(path).name
            self.stat_counts[name] += 1

            # A is stable during its own initial download (mtime=100),
            # then changes to 200 by the time the final batch sweep runs.
            if name == "A.g":
                if self.stat_counts[name] <= 2:
                    mtime = 100
                else:
                    mtime = 200
            else:
                mtime = 100
            return RemoteGFile(name, path, 1, mtime)

        def download_file(self, remote_path, local_path):
            name = Path(remote_path).name
            self.download_counts[name] += 1
            Path(local_path).write_bytes(b"x")

    fake = FakeClient()
    monkeypatch.setattr(
        snapshot_module,
        "ReadOnlySshClient",
        lambda *args, **kwargs: fake,
    )

    service = RemoteSnapshotService(
        host="host",
        port=22,
        username="user",
        password="pwd",
        remote_directory="/remote",
        retry_delay=0,
    )
    _paths, info = service.download_latest([a, b], tmp_path)

    assert fake.download_counts["A.g"] == 2
    assert fake.download_counts["B.g"] == 1
    saved_a = next(
        item for item in info["files"] if item["name"] == "A.g"
    )
    assert saved_a["remote_mtime_epoch"] == 200
    assert (
        info["batch_consistency_policy"]
        == "FINAL_STAT_SWEEP_AND_REDOWNLOAD"
    )
