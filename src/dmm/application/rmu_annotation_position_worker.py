from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.rmu_annotation_position import (
    process_rmu_annotation_reposition,
)


class RmuAnnotationPositionWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        files,
        run_dir: Path,
        nop_position: str,
        rmu_name_position: str,
        nop_margin: int,
        rmu_name_margin: int,
    ):
        super().__init__()
        self.files = [Path(path) for path in files]
        self.run_dir = Path(run_dir)
        self.nop_position = str(nop_position)
        self.rmu_name_position = str(rmu_name_position)
        self.nop_margin = int(nop_margin)
        self.rmu_name_margin = int(rmu_name_margin)

    def run(self):
        try:
            result = process_rmu_annotation_reposition(
                self.files,
                self.run_dir / "g_output",
                self.run_dir / "rmu_annotation_position_report",
                nop_position=self.nop_position,
                rmu_name_position=self.rmu_name_position,
                nop_margin=self.nop_margin,
                rmu_name_margin=self.rmu_name_margin,
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
                "rmu_name_found": result.rmu_name_found,
                "rmu_name_moved": result.rmu_name_moved,
                "rmu_name_missing": result.rmu_name_missing,
                "nop_found": result.nop_found,
                "nop_moved": result.nop_moved,
                "nop_unmatched_rmu": result.nop_unmatched_rmu,
                "nop_unmatched_device": result.nop_unmatched_device,
                "record_count": len(result.records),
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
