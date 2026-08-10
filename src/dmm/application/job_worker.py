
from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.infrastructure.database.oracle import OracleClient
from dmm.infrastructure.reporting.writer import export_csv_bundle, export_html_bundle
from dmm.config.settings import save_settings

class JobWorker(QThread):
    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(str, dict, object, object, object)
    failed = Signal(str)

    def __init__(self, cfg, module, operation, settings, files, run_dir):
        super().__init__()
        self.cfg = cfg
        self.module = module
        self.operation = operation
        self.settings = settings
        self.files = files
        self.run_dir = Path(run_dir)

    def run(self):
        db = None
        try:
            self.progress.emit(1, "正在连接 Oracle 数据库……")
            self.log.emit("Oracle 预检查：正在验证数据库连接……")
            db = OracleClient(self.cfg["db"])
            self.log.emit(db.test_connection())
            self.log.emit("Oracle 预检查：通过")
            self.progress.emit(5, "Oracle 数据库预检查通过")

            if not self.module.supports(self.operation):
                raise RuntimeError(
                    f"{self.module.display_name} 当前不支持此操作：{self.operation}"
                )

            preview_data = None

            if self.operation == "VALIDATE":
                reports, summary, rules = self.module.validate(
                    db,
                    self.files,
                    self.settings,
                    lambda msg: self.log.emit(str(msg)),
                    lambda percent, message="": self.progress.emit(int(percent), str(message)),
                )

            elif self.operation == "PREVIEW_ASSOCIATION":
                preview_data = self.module.preview_association(
                    db,
                    self.files,
                    self.settings,
                    lambda msg: self.log.emit(str(msg)),
                    lambda percent, message="": self.progress.emit(int(percent), str(message)),
                )
                reports = preview_data.get("reports", [])
                summary = preview_data.get("summary", {})
                rules = preview_data.get("rules", {})

            else:
                raise RuntimeError("模型关联回写必须基于已经确认的关联预览执行。")

            report_context = {
                "VALIDATE": ("validation", "validation_report"),
                "PREVIEW_ASSOCIATION": ("preview", "association_preview_report"),
            }.get(self.operation, ("result", "report"))

            self.progress.emit(96, "正在生成 HTML / CSV 报告……")
            report_dir = self.run_dir / report_context[1]
            report_dir.mkdir(parents=True, exist_ok=True)

            html_path = report_dir / "report.html"
            csv_base = report_dir / "report.csv"
            export_html_bundle(reports, html_path, rules)
            csv_paths = export_csv_bundle(reports, csv_base)

            artifacts = {
                "task_type": report_context[0],
                "operation": self.operation,
                "run_dir": str(self.run_dir),
                "report_dir": str(report_dir),
                "html": str(html_path),
                "rmu_csv": str(csv_paths[0]) if len(csv_paths) > 0 else "",
                "device_csv": str(csv_paths[1]) if len(csv_paths) > 1 else "",
                "g_output_dir": str(self.run_dir / "g_output"),
            }

            self.cfg["last_run_dir"] = str(self.run_dir)
            save_settings(self.cfg)

            self.progress.emit(100, "任务处理完成")
            self.completed.emit(str(self.run_dir), summary, rules, preview_data, artifacts)

        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if db:
                db.close()


