from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSFORMER = (ROOT / "src/dmm/ui/widgets/transformer_settings.py").read_text(encoding="utf-8")
POLE_SWITCH = (ROOT / "src/dmm/ui/widgets/pole_switch_settings.py").read_text(encoding="utf-8")
SETTINGS = (ROOT / "src/dmm/config/settings.py").read_text(encoding="utf-8")
WORKSPACE = (ROOT / "src/dmm/infrastructure/filesystem/workspace.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "src/dmm/config/constants.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_transformer_has_explicit_local_user_cache_save():
    assert 'QPushButton("保存到本地用户缓存")' in TRANSFORMER
    assert 'clicked.connect(self._save_local_cache)' in TRANSFORMER
    assert 'self.config["transformer_element_files"] = files' in TRANSFORMER
    assert 'save_settings(self.config)' in TRANSFORMER
    assert '已保存到本地用户缓存：柱上变压器图元' in TRANSFORMER


def test_pole_switch_has_same_local_user_cache_save():
    assert 'QPushButton("保存到本地用户缓存")' in POLE_SWITCH
    assert 'clicked.connect(self._save_local_cache)' in POLE_SWITCH
    assert 'self.config["pole_switch_element_files"] = files' in POLE_SWITCH
    assert 'save_settings(self.config)' in POLE_SWITCH
    assert '已保存到本地用户缓存：柱上开关图元' in POLE_SWITCH


def test_save_settings_writes_per_user_cache_outside_app_folder():
    assert 'save_user_settings_cache(payload)' in SETTINGS
    assert 'USER_SETTINGS_CACHE_PATH = user_data_root() / "settings.json"' in WORKSPACE
    assert 'Path(base) / "DistributionModelManager"' in WORKSPACE


def test_v4199_version():
    assert 'APP_VERSION = "4.1.112"' in CONSTANTS
    assert 'version = "4.1.112"' in PYPROJECT
