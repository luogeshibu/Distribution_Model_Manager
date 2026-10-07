from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.feeder_avoidance import process_feeder_avoidance


class FeederAvoidanceWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        files,
        run_dir: Path,
        text_clearance: int,
        feeder_spacing: int,
        corridor_tolerance: int,
        max_right_shift: int,
        process_right: bool,
        process_left: bool,
    ):
        super().__init__()
        self.files = [Path(path) for path in files]
        self.run_dir = Path(run_dir)
        self.text_clearance = int(text_clearance)
        self.feeder_spacing = int(feeder_spacing)
        self.corridor_tolerance = int(corridor_tolerance)
        self.max_right_shift = int(max_right_shift)
        self.process_right = bool(process_right)
        self.process_left = bool(process_left)

    def run(self):
        try:
            result = process_feeder_avoidance(
                self.files,
                self.run_dir / "g_output",
                self.run_dir / "feeder_avoidance_report",
                text_clearance=self.text_clearance,
                feeder_spacing=self.feeder_spacing,
                corridor_tolerance=self.corridor_tolerance,
                max_right_shift=self.max_right_shift,
                process_right=self.process_right,
                process_left=self.process_left,
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
                "colliding_feedline_count": result.colliding_feedline_count,
                "moved_feedline_count": result.moved_feedline_count,
                "moved_segment_count": result.moved_segment_count,
                "staggered_segment_count": result.staggered_segment_count,
                "unresolved_collision_count": result.unresolved_collision_count,
                "skipped_side_count": result.skipped_side_count,
                "record_count": len(result.records),
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
