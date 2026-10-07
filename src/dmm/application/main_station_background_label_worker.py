from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.main_station_background_label import (
    process_main_station_background_label_repair,
)


class MainStationBackgroundLabelWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, *, files, run_dir: Path):
        super().__init__()
        self.files = [Path(path) for path in files]
        self.run_dir = Path(run_dir)

    def run(self):
        try:
            output_dir = self.run_dir / "g_output"
            report_dir = self.run_dir / "main_station_background_label_report"
            result = process_main_station_background_label_repair(
                self.files,
                output_dir,
                report_dir,
                log=lambda message: self.log.emit(str(message)),
                progress=lambda percent, message="": self.progress.emit(
                    int(percent), str(message)
                ),
            )
            self.completed.emit({
                "run_dir": str(self.run_dir),
                "g_output_dir": str(output_dir),
                "report_dir": str(report_dir),
                "html_report": str(result.html_path),
                "csv_report": str(result.csv_path),
                "output_files": [str(path) for path in result.output_files],
                "candidate_count": result.candidate_count,
                "updated_count": result.updated_count,
                "layout_count": result.layout_count,
                "ambiguous_count": result.ambiguous_count,
                "skipped_count": result.skipped_count,
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
