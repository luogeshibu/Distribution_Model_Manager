from pathlib import Path


MAIN_WINDOW = Path(__file__).resolve().parents[1] / "src" / "dmm" / "ui" / "main_window.py"


def _text():
    return MAIN_WINDOW.read_text(encoding="utf-8")


def test_batch_page_warns_about_single_line_only_modules():
    text = _text()
    block = text[
        text.index("    def _build_batch_page(self):"):
        text.index("    def _prepare_batch_page(self):")
    ]
    assert "self.batch_single_line_notice = QLabel()" in block
    assert "配网主站设备、馈线模型只允许在单线图中执行关联" in text
    assert "合成图或环网图" in text
    assert "批量校验阶段自动阻断" in text


def test_batch_single_line_notice_tracks_selected_restricted_modules():
    text = _text()
    block = text[
        text.index("    def _update_batch_single_line_notice(self):"):
        text.index("    def _on_batch_module_selection_changed", text.index("    def _update_batch_single_line_notice(self):"))
    ]
    assert '("MASTER_STATION", "FEEDER")' in block
    assert "当前已选择" in block
    selection = text[
        text.index("    def _on_batch_module_selection_changed"):
        text.index("    def _collect_batch_settings", text.index("    def _on_batch_module_selection_changed"))
    ]
    assert "self._update_batch_single_line_notice()" in selection


def test_batch_apply_confirmation_repeats_single_line_safety_boundary():
    text = _text()
    block = text[
        text.index("    def apply_batch_association(self):"):
        text.index("    def _on_batch_association_completed", text.index("    def apply_batch_association(self):"))
    ]
    assert "配网主站设备、馈线模型只允许单线图" in block
    assert "非单线图对象会在校验阶段阻断" in block
