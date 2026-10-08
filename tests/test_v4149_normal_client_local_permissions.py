from pathlib import Path


def test_normal_client_can_edit_and_save_local_shared_settings():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "edit.setReadOnly(False)" in source
    assert "self.db_save_button.setEnabled(True)" in source
    assert "self.ssh_save_button.setEnabled(True)" in source
    assert "普通客户端只能同步中央配置" not in source


def test_element_page_only_central_publish_is_admin_gated():
    source = Path("src/dmm/ui/widgets/element_management_page.py").read_text(encoding="utf-8")
    assert "self.publish_button.setEnabled(self._admin_mode)" in source
    assert '_require_admin_mode("保存并同步到中央仓库")' in source
    assert '_require_admin_mode("保存到本地缓存")' not in source
    assert '_require_admin_mode("刷新图元列表")' not in source
    assert '_require_admin_mode("保存图元服务器配置")' not in source
    assert '_require_admin_mode("导入图元共享配置")' not in source


def test_admin_loss_message_preserves_local_edit_rights():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "本机配置仍可修改保存和同步，但不能发布到中央仓库" in source
