from pathlib import Path


def _main_window_source():
    return Path("src/dmm/ui/main_window.py").read_text(encoding="utf-8")


def test_progress_group_has_dedicated_object_name():
    src = _main_window_source()
    assert 'self.progress_box.setObjectName("progressBox")' in src


def test_progress_title_overrides_generic_pale_green_background_only():
    src = _main_window_source()
    assert 'QGroupBox#progressBox::title {' in src
    block = src.split('QGroupBox#progressBox::title {', 1)[1].split('}', 1)[0]
    assert 'background: white;' in block
    assert '#F1F6F3' not in block


def test_busy_progress_execution_contract_is_unchanged():
    src = _main_window_source()
    assert 'self.progress_bar.setRange(0, 0)' in src
    assert 'self.progress_bar.setTextVisible(False)' in src
