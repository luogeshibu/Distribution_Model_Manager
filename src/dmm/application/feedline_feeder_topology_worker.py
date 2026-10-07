from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.feedline_feeder_topology import (
    process_feedline_feeder_topology_analysis,
)


class FeedlineFeederTopologyWorker(QThread):
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
            report_dir = self.run_dir / "feedline_feeder_topology_report"
            result = process_feedline_feeder_topology_analysis(
                self.files,
                report_dir,
                log=lambda message: self.log.emit(str(message)),
                progress=lambda percent, message="": self.progress.emit(
                    int(percent), str(message)
                ),
            )
            self.completed.emit({
                "run_dir": str(self.run_dir),
                "report_dir": str(report_dir),
                "html_report": str(result.html_path),
                "feedline_csv": str(result.feedline_csv_path),
                "nop_csv": str(result.nop_csv_path),
                "file_count": result.file_count,
                "feedline_count": result.feedline_count,
                "confirmed_count": result.confirmed_count,
                "conflict_count": result.conflict_count,
                "unresolved_count": result.unresolved_count,
                "source_feeder_count": result.source_feeder_count,
                "nop_boundary_count": result.nop_boundary_count,
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
