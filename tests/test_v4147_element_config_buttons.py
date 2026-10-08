from pathlib import Path


def test_element_management_exposes_three_explicit_config_actions():
    source = Path("src/dmm/ui/widgets/element_management_page.py").read_text(encoding="utf-8")

    assert 'QPushButton("保存到本地缓存")' in source
    assert 'QPushButton("保存并同步到中央仓库")' in source
    assert 'QPushButton("同步中央配置仓库配置")' in source
    assert "def save_local_cache" in source
    assert "def publish_catalog_to_central" in source
    assert "def request_central_sync" in source


def test_central_pull_button_is_not_admin_only_and_routes_to_main_sync():
    element_source = Path("src/dmm/ui/widgets/element_management_page.py").read_text(encoding="utf-8")
    main_source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")

    # v4.1.49+: only central publish is Admin-only; local edit/save/refresh/import are available to all clients.
    assert 'self.publish_button.setEnabled(self._admin_mode)' in element_source
    assert 'widget.setEnabled(True)' in element_source
    assert "centralSyncRequested = Signal()" in element_source
    assert "self.centralSyncRequested.emit()" in element_source
    assert "page.centralSyncRequested.connect(self.sync_central_configuration)" in main_source
    assert "sync_central_settings(self.cfg, raise_on_error=True)" in main_source


def test_publish_is_admin_only_and_saves_local_cache_first():
    source = Path("src/dmm/ui/widgets/element_management_page.py").read_text(encoding="utf-8")

    publish_start = source.index("def publish_catalog_to_central")
    publish_block = source[publish_start: publish_start + 1500]
    assert '_require_admin_mode("保存并同步到中央仓库")' in publish_block
    assert "self.save_local_cache(show_status=False)" in publish_block
    assert "publish_central_settings(self.config)" in publish_block


def test_local_save_persists_element_server_and_catalog_without_central_io():
    source = Path("src/dmm/ui/widgets/element_management_page.py").read_text(encoding="utf-8")

    start = source.index("def save_local_cache")
    block = source[start: start + 1800]
    assert "self._current_element_ssh_config()" in block
    assert 'self.config["ssh"] = ssh_config' in block
    assert 'self.config["element_catalog"]' in block
    assert "save_settings(self.config)" in block
    assert "publish_central_settings" not in block
