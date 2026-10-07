from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.rmu_feeder_topology import process_rmu_feeder_topology_analysis


class RmuFeederTopologyWorker(QThread):
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
            result = process_rmu_feeder_topology_analysis(
                self.files,
                self.run_dir / "rmu_feeder_topology_report",
                log=lambda message: self.log.emit(str(message)),
                progress=lambda percent, message="": self.progress.emit(
                    int(percent), str(message)
                ),
            )
            self.completed.emit({
                "run_dir": str(self.run_dir),
                "report_dir": str(self.run_dir / "rmu_feeder_topology_report"),
                "html_report": str(result.html_path),
                "rmu_csv": str(result.rmu_csv_path),
                "port_csv": str(result.port_csv_path),
                "file_count": result.file_count,
                "rmu_count": result.rmu_count,
                "unique_count": result.unique_count,
                "nop_boundary_count": result.nop_boundary_count,
                "conflict_count": result.conflict_count,
                "unresolved_count": result.unresolved_count,
                "source_feeder_count": result.source_feeder_count,
                "source_entry_nop_feeder_count": result.source_entry_nop_feeder_count,
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
