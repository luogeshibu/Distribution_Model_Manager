from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.engine import process_rmu_network_status_cleanup


class GraphicsCleanupWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, *, files, run_dir: Path, target_element_files=None):
        super().__init__()
        self.files = [Path(path) for path in files]
        self.run_dir = Path(run_dir)
        self.target_element_files = list(target_element_files or [])

    def run(self):
        try:
            result = process_rmu_network_status_cleanup(
                self.files,
                self.run_dir / "g_output",
                self.run_dir / "graphics_cleanup_report",
                target_element_files=self.target_element_files,
                log=lambda message: self.log.emit(str(message)),
                progress=lambda percent, message="": self.progress.emit(
                    int(percent), str(message)
                ),
            )
            self.completed.emit({
                "run_dir": str(self.run_dir),
                "g_output_dir": str(self.run_dir / "g_output"),
                "html_report": str(result.html_path),
                "csv_report": str(result.csv_path),
                "output_files": [str(path) for path in result.output_files],
                "removed": result.removed,
                "record_count": len(result.records),
                "target_element_files": list(result.target_element_files),
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
