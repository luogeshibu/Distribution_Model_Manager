from pathlib import Path


def test_feeder_resolution_combo_blocks_mouse_wheel():
    src=(Path(__file__).parents[1]/"src/dmm/ui/widgets/feeder_settings.py").read_text(encoding="utf-8")
    assert "class NoWheelComboBox(QComboBox):" in src
    assert "def wheelEvent(self, event):" in src
    assert "self.feeder_resolution_mode = NoWheelComboBox()" in src
