from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "src" / "dmm" / "ui" / "main_window.py"
REGISTRY = ROOT / "src" / "dmm" / "ui" / "registry.py"
BULK_WIDGET = ROOT / "src" / "dmm" / "ui" / "widgets" / "bulk_association_settings.py"


def _main():
    return MAIN.read_text(encoding="utf-8")


def test_batch_is_no_longer_a_sidebar_page():
    text = _main()
    nav_line = next(line for line in text.splitlines() if 'for label in ("模型工作区"' in line)
    assert '"批量关联"' not in nav_line
    build_ui = text[text.index("    def _build_ui(self):"):text.index("    # ------------------------------------------------------------\n    # Element management page")]
    assert "self.pages.addWidget(self._build_batch_page())" not in build_ui


def test_bulk_is_a_pseudo_model_inside_model_workspace():
    text = _main()
    workspace = text[text.index("    def _build_workspace_page(self):"):text.index("    def _update_module_stack_height", text.index("    def _build_workspace_page(self):"))]
    assert 'self.module_combo.addItem("一键多模型关联", "BULK")' in workspace
    assert 'create_settings_widget(\n            "BULK"' in workspace
    assert 'QGroupBox("待关联设备（一键多模型校验后确认）")' in workspace
    assert "self.validate_btn.clicked.connect(self._handle_validate_action)" in workspace
    assert "self.apply_btn.clicked.connect(self._handle_apply_action)" in workspace


def test_bulk_reuses_shared_model_workspace_source_and_existing_orchestrator():
    text = _main()
    validate = text[text.index("    def start_batch_validation(self):"):text.index("    def _on_batch_validation_completed", text.index("    def start_batch_validation(self):"))]
    apply = text[text.index("    def apply_batch_association(self):"):text.index("    def _on_batch_association_completed", text.index("    def apply_batch_association(self):"))]
    assert "self._current_input_source()" in validate
    assert "self.input_edit.text().strip()" in validate
    assert "self._selected_remote_files()" in validate
    assert "self._sync_workspace_source_controls_from_batch()" not in validate
    assert "self._sync_workspace_source_controls_from_batch()" not in apply
    assert "BatchValidationWorker(" in validate
    assert "BatchAssociationExecutionWorker(" in apply


def test_bulk_widget_is_registered_and_business_rule_free():
    registry = REGISTRY.read_text(encoding="utf-8")
    widget = BULK_WIDGET.read_text(encoding="utf-8")
    assert '"BULK": BulkAssociationSettingsWidget' in registry
    assert '"RMU", "RMU 环网柜模型"' in widget
    assert '"FEEDER", "馈线模型"' in widget
    assert "def selected_module_ids" in widget
    assert "apply_association" not in widget
    assert "Oracle" not in widget
