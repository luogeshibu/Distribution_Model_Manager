from pathlib import Path


def test_progress_box_is_embedded_with_console_not_main_layout():
    src = Path('src/dmm/ui/main_window.py').read_text(encoding='utf-8')
    assert 'self.progress_box = QGroupBox("任务进度")' in src
    assert 'log_layout.addWidget(self.progress_box)' in src
    assert '\n        layout.addWidget(progress_box)\n' not in src
    assert '\n        layout.addWidget(self.progress_box)\n' not in src


def test_busy_progress_behavior_remains_unchanged():
    src = Path('src/dmm/ui/main_window.py').read_text(encoding='utf-8')
    assert 'self.progress_bar.setRange(0, 0)' in src
    assert 'self.progress_bar.setTextVisible(False)' in src
    assert 'AssociationExecutionWorker' in src
