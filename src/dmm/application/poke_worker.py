from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.poke.engine import process_poke_files
from dmm.infrastructure.database.oracle import OracleClient


class PokeProcessingWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        db_config: dict,
        files,
        settings: dict,
        run_dir: Path,
        enable_main_feeder: bool,
        enable_smart_rmu: bool,
    ):
        super().__init__()
        self.db_config = dict(db_config)
        self.files = [Path(path) for path in files]
        self.settings = dict(settings)
        self.run_dir = Path(run_dir)
        self.enable_main_feeder = bool(enable_main_feeder)
        self.enable_smart_rmu = bool(enable_smart_rmu)

    def run(self):
        db = None
        try:
            self.progress.emit(1, "正在连接 Oracle 数据库……")
            db = OracleClient(self.db_config)
            self.log.emit(db.test_connection())
            self.progress.emit(5, "Oracle 数据库连接正常")

            result = process_poke_files(
                db,
                self.files,
                self.settings,
                self.run_dir / "g_output",
                self.run_dir / "poke_report",
                enable_main_feeder=self.enable_main_feeder,
                enable_smart_rmu=self.enable_smart_rmu,
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
                "added": result.added,
                "updated": result.updated,
                "unchanged": result.unchanged,
                "skipped": result.skipped,
                "record_count": len(result.records),
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if db:
                db.close()
