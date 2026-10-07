from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.whole_graph_topology import (
    process_whole_graph_topology_analysis,
)


class WholeGraphTopologyWorker(QThread):
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
            report_dir = self.run_dir / "whole_graph_topology_report"
            result = process_whole_graph_topology_analysis(
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
                "device_csv": str(result.device_csv_path),
                "nop_csv": str(result.nop_csv_path),
                "anchor_csv": str(result.anchor_csv_path),
                "rmu_csv": str(result.rmu_csv_path),
                "repair_csv": str(result.repair_csv_path),
                "before_svg": str(result.before_svg_path),
                "after_svg": str(result.after_svg_path),
                "fixed_g": str(result.fixed_g_path) if result.fixed_g_path else "",
                "file_count": result.file_count,
                "device_count": result.device_count,
                "confirmed_count": result.confirmed_count,
                "conflict_count": result.conflict_count,
                "unresolved_count": result.unresolved_count,
                "feeder_count": result.feeder_count,
                "nop_boundary_count": result.nop_boundary_count,
                "pole_nop_count": result.pole_nop_count,
                "rmu_nop_count": result.rmu_nop_count,
                "topology_error_count": result.topology_error_count,
                "no_feeder_error_count": result.no_feeder_error_count,
                "multi_feeder_error_count": result.multi_feeder_error_count,
                "rmu_count": result.rmu_count,
                "rmu_confirmed_count": result.rmu_confirmed_count,
                "rmu_error_count": result.rmu_error_count,
                "repair_candidate_count": result.repair_candidate_count,
                "repair_applied_count": result.repair_applied_count,
                "before_topology_error_count": result.before_topology_error_count,
                "after_topology_error_count": result.after_topology_error_count,
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
