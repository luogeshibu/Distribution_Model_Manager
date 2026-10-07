from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.channel_status import process_rmu_channel_status_reposition


class ChannelStatusRepositionWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, *, files, run_dir: Path, position: str, inner_margin: int):
        super().__init__()
        self.files = [Path(path) for path in files]
        self.run_dir = Path(run_dir)
        self.position = str(position)
        self.inner_margin = int(inner_margin)

    def run(self):
        try:
            result = process_rmu_channel_status_reposition(
                self.files,
                self.run_dir / "g_output",
                self.run_dir / "channel_status_report",
                position=self.position,
                inner_margin=self.inner_margin,
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
                "found": result.found,
                "moved": result.moved,
                "missing": result.missing,
                "record_count": len(result.records),
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
