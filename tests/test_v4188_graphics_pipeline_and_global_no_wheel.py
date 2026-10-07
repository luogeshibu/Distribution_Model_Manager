from pathlib import Path


def test_global_wheel_filter_covers_combo_and_spin_controls():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert "app.installEventFilter(self)" in source
    assert "event.type() == QEvent.Wheel" in source
    assert "isinstance(probe, (QComboBox, QAbstractSpinBox))" in source
    assert "isinstance(parent, QAbstractScrollArea)" in source
    assert "bar.setValue" in source


def test_graphics_workspace_exposes_one_click_pipeline():
    source = Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")
    assert 'self.graphics_operation_combo.addItem("组合处理（一键）", "GRAPHICS_PIPELINE")' in source
    assert "self._build_graphics_pipeline_panel()" in source
    assert 'self.graphics_pipeline_run_btn = QPushButton("开始组合处理")' in source
    assert '"cleanup": self.pipeline_enable_cleanup.isChecked()' in source
    assert '"channel_status": self.pipeline_enable_channel.isChecked()' in source
    assert '"poke": self.pipeline_enable_poke.isChecked()' in source


def test_pipeline_worker_publishes_only_after_all_selected_steps():
    source = Path("src/dmm/application/graphics_pipeline_worker.py").read_text(encoding="utf-8")
    cleanup = source.index('if stage == "cleanup"')
    channel = source.index('elif stage == "channel_status"')
    poke = source.index('elif stage == "poke"')
    publish = source.index('final_target = final_dir / source.name')
    assert cleanup < channel < poke < publish
    assert 'row["final_status"] = "PASS"' in source
    assert 'except Exception as exc:' in source
    assert 'row["final_status"] = "FAIL"' in source


def test_release_version_is_4188():
    constants = Path("src/dmm/config/constants.py").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.1.112"' in constants
    assert 'version = "4.1.112"' in pyproject
