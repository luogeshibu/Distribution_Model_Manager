from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v420_version_and_graphics_nav_present():
    constants = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
    main = (ROOT / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.2.21"' in constants
    assert '"图形工作区"' in main
    assert 'GraphicsWorkspaceWidget(self.cfg, self)' in main


def test_all_latest_gfilestudio_site_modules_are_embedded():
    graphics = (ROOT / "src/dmm/ui/graphics_workspace.py").read_text(encoding="utf-8")
    expected = [
        "small_element_page:SmallElementPage",
        "id_page:IdPage",
        "rmu_page:RmuPage",
        "poke_page:PokePage",
        "basic_page:BasicPage",
        "merge_page:MergePage",
        "margin_page:MarginPage",
        "frame_page:FramePage",
        "orthogonalize_page:OrthogonalizePage",
        "jeddah_batch_page:JeddahBatchPage",
        "transformer_fuse_page:TransformerFusePage",
        "rmu_efi_page:RmuEfiPage",
    ]
    for item in expected:
        assert item in graphics


def test_packaging_includes_embedded_graphics_and_templates():
    build = (ROOT / "build_exe.ps1").read_text(encoding="utf-8")
    assert '--collect-all "g_file_studio"' in build
    assert '--add-data "resources;resources"' in build
    assert (ROOT / "resources/templates/transform_fuse_mode.sln.pic.g").is_file()
    assert (ROOT / "resources/templates/SLD-Drawing-Frame-Template.sln.pic.g").is_file()


def test_jeddah_model_baseline_modules_remain_present():
    for name in ("rmu.py", "feeder.py", "pole_switch.py", "transformer.py", "fuse.py", "master_station.py"):
        assert (ROOT / "src/dmm/application/modules" / name).is_file()


def test_v422_graphics_workspace_uses_main_element_management_only():
    graphics = (ROOT / "src/dmm/ui/graphics_workspace.py").read_text(encoding="utf-8")
    assert "服务器图元同步管理" not in graphics
    assert "site_profile_page:SiteProfilePage" not in graphics
    assert 'requestMainPage.emit(2)' in graphics
    assert 'requestMainPage.emit(3)' in graphics
    assert "_bridge_element_catalog" in graphics
    assert "replace_classification_marker_payload" in graphics


def test_v423_graphics_uses_single_dmm_central_repository_and_admin_identity():
    graphics = (ROOT / "src/dmm/ui/graphics_workspace.py").read_text(encoding="utf-8")
    main = (ROOT / "src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    registry = (ROOT / "src/g_file_studio/services/classification_registry_service.py").read_text(encoding="utf-8")
    assert '"central_repository/config_dir"' in graphics
    assert '/home/up8000/nari-international/distribution-model-manager/config' in graphics
    assert '/home/up8000/nari-international/gfilestudio/config' not in graphics
    assert '"access_control/machine_id": cfg.get("machine_id", "")' in graphics
    assert 'def set_admin_mode(self, is_admin: bool, admin_epoch: int | None = None)' in graphics
    assert 'graphics_page.set_admin_mode(' in main
    assert 'DEFAULT_CONFIG_DIR = "/home/up8000/nari-international/distribution-model-manager/config"' in registry


def test_v423_element_marks_remain_single_authoritative_classification_source():
    graphics = (ROOT / "src/dmm/ui/graphics_workspace.py").read_text(encoding="utf-8")
    central = (ROOT / "src/dmm/infrastructure/remote/central_config.py").read_text(encoding="utf-8")
    assert 'replace_classification_marker_payload' in graphics
    assert '"element_marks": "element_marks.json"' in central
    assert 'site_profile_page:SiteProfilePage' not in graphics
