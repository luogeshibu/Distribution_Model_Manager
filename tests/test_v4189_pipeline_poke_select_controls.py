from pathlib import Path


def test_pipeline_poke_group_has_select_all_and_clear_all_controls():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.pipeline_poke_select_all_btn = QPushButton("全选")' in source
    assert 'self.pipeline_poke_clear_all_btn = QPushButton("全部取消")' in source
    assert 'self.pipeline_poke_main_feeder, self.pipeline_poke_smart_rmu' in source
    assert 'getattr(self, "pipeline_poke_select_all_btn", None)' in source
    assert 'getattr(self, "pipeline_poke_clear_all_btn", None)' in source


def test_release_version_is_4189():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.112"' in constants
    assert 'version = "4.1.112"' in pyproject
