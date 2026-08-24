from __future__ import annotations

import json
from pathlib import Path

from dmm.config import settings as settings_module
from dmm.config.defaults import DEFAULT_SETTINGS


def test_load_settings_deep_merges_partial_ssh_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "ssh": {
                    "host": "10.20.30.40",
                    "username": "custom_user",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "CONFIG_PATH", config_path)

    loaded = settings_module.load_settings()

    assert loaded["ssh"]["host"] == "10.20.30.40"
    assert loaded["ssh"]["username"] == "custom_user"
    assert loaded["ssh"]["port"] == DEFAULT_SETTINGS["ssh"]["port"]
    assert loaded["ssh"]["password"] == DEFAULT_SETTINGS["ssh"]["password"]
    assert (
        loaded["ssh"]["remote_directory"]
        == DEFAULT_SETTINGS["ssh"]["remote_directory"]
    )


def test_main_window_contains_explicit_ssh_save_action():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")

    assert 'QPushButton("保存 SSH 配置")' in source
    assert "save_ssh_btn.clicked.connect(self.save_ssh_settings)" in source
    assert "def save_ssh_settings(self):" in source
    assert 'self.cfg["ssh"] = cfg' in source
    assert 'self.cfg["input_source"] = "SSH"' in source
    assert "下次启动将自动恢复最后一次保存的输入" in source
