
from pathlib import Path

def test_ssh_status_is_below_ssh_buttons():
    main = (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")

    button_pos = main.index('QPushButton("测试 SSH 连接")')
    status_pos = main.index("self.ssh_connection_status = QLabel")
    readonly_pos = main.index("self.ssh_readonly_notice = QLabel")

    assert button_pos < status_pos < readonly_pos
    assert "def _set_ssh_connection_status" in main

def test_connection_messages_use_local_status_label():
    main = (
        Path(__file__).parents[1]
        / "src/dmm/ui/main_window.py"
    ).read_text(encoding="utf-8")

    assert "正在测试 SSH/SFTP 只读连接" in main
    assert "SSH/SFTP 连接正常；远程文件源为只读。" in main
    assert "读取远程 G 文件列表失败" in main
