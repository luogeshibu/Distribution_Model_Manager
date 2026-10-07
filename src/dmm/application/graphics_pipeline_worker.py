from __future__ import annotations

import csv
import html
import re
import shutil
import traceback
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dmm.domain.graphics_cleanup.engine import process_rmu_network_status_cleanup
from dmm.domain.graphics_cleanup.channel_status import process_rmu_channel_status_reposition
from dmm.domain.poke.engine import process_poke_files
from dmm.infrastructure.database.oracle import OracleClient


class GraphicsPipelineWorker(QThread):
    """Run selected graphics operations as one safe per-file pipeline.

    Every source file gets its own temporary chain.  A final G file is copied
    into ``g_output`` only after every selected step for that file succeeds.
    A failure therefore never publishes a partially processed final file and
    does not stop the remaining source files from being processed.
    """

    log = Signal(str)
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        *,
        files,
        run_dir: Path,
        steps: dict,
        channel_position: str,
        channel_margin: int,
        db_config: dict | None,
        poke_settings: dict | None,
        poke_enable_main_feeder: bool,
        poke_enable_smart_rmu: bool,
    ):
        super().__init__()
        self.files = [Path(path) for path in files]
        self.run_dir = Path(run_dir)
        self.steps = {
            "cleanup": bool(steps.get("cleanup")),
            "channel_status": bool(steps.get("channel_status")),
            "poke": bool(steps.get("poke")),
        }
        self.channel_position = str(channel_position)
        self.channel_margin = int(channel_margin)
        self.db_config = dict(db_config or {})
        self.poke_settings = dict(poke_settings or {})
        self.poke_enable_main_feeder = bool(poke_enable_main_feeder)
        self.poke_enable_smart_rmu = bool(poke_enable_smart_rmu)

    @staticmethod
    def _safe_name(value: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "file"))
        return value[:120] or "file"

    def _emit_stage_progress(self, file_index: int, file_count: int, stage_index: int, stage_count: int, local_percent: int, message: str):
        file_fraction = (stage_index + max(0, min(100, int(local_percent))) / 100.0) / max(1, stage_count)
        overall = int(((file_index + file_fraction) / max(1, file_count)) * 96)
        self.progress.emit(max(1, min(96, overall)), str(message or ""))

    @staticmethod
    def _write_summary(records: list[dict], report_dir: Path) -> tuple[Path, Path]:
        report_dir.mkdir(parents=True, exist_ok=True)
        fields = [
            "file_name",
            "cleanup_status",
            "cleanup_removed",
            "channel_status",
            "channel_found",
            "channel_moved",
            "poke_status",
            "poke_added",
            "poke_updated",
            "poke_unchanged",
            "poke_skipped",
            "final_status",
            "error",
        ]
        csv_path = report_dir / "graphics_pipeline_report.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in records:
                writer.writerow({key: row.get(key, "") for key in fields})

        rows = []
        for row in records:
            cls = "pass" if row.get("final_status") == "PASS" else "fail"
            cells = "".join(
                f"<td>{html.escape(str(row.get(key, '') or ''))}</td>" for key in fields
            )
            rows.append(f"<tr class='{cls}'>{cells}</tr>")
        labels = [
            "G文件", "网络图元清理", "删除数量", "channel_status", "找到状态点", "移动数量",
            "Poke", "Poke新增", "Poke更新", "Poke不变", "Poke跳过", "最终状态", "错误",
        ]
        html_path = report_dir / "graphics_pipeline_report.html"
        html_path.write_text(
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<title>图形组合处理报告</title><style>"
            "body{font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;margin:24px;background:#f3f7f5;color:#17372e}"
            "h1{color:#006b52}.rule{background:#eaf8f2;border:1px solid #b8dfd1;padding:12px 14px;margin-bottom:16px;border-radius:8px;line-height:1.7}"
            "table{border-collapse:collapse;width:100%;background:#fff;font-size:12px}th,td{border:1px solid #d3e3dc;padding:7px 9px;text-align:left;white-space:nowrap}"
            "th{background:#006b52;color:white}.pass{background:#eaf8f2}.fail{background:#fff0f0}</style></head><body>"
            "<h1>图形组合处理报告</h1><div class='rule'>同一 G 文件按勾选顺序串行处理；只有全部选中步骤成功后才发布到最终 g_output。单文件失败不会阻断其它文件。</div>"
            "<table><thead><tr>" + "".join(f"<th>{html.escape(label)}</th>" for label in labels) +
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></body></html>",
            encoding="utf-8",
        )
        return csv_path, html_path

    def run(self):
        db = None
        try:
            selected_steps = [
                key for key in ("cleanup", "channel_status", "poke") if self.steps.get(key)
            ]
            if not selected_steps:
                raise ValueError("组合处理至少选择一个处理步骤。")
            if not self.files:
                raise ValueError("没有可处理的 G 文件。")
            if self.steps.get("poke") and not (
                self.poke_enable_main_feeder or self.poke_enable_smart_rmu
            ):
                raise ValueError("组合处理启用 Poke 时，请至少选择一种 Poke 跳转类型。")

            if self.steps.get("poke"):
                self.progress.emit(1, "正在连接 Oracle 数据库……")
                db = OracleClient(self.db_config)
                self.log.emit(db.test_connection())
                self.log.emit("[组合处理] Oracle 数据库连接正常。")

            final_dir = self.run_dir / "g_output"
            report_dir = self.run_dir / "graphics_pipeline_report"
            detail_root = report_dir / "detail"
            work_root = self.run_dir / "_graphics_pipeline_work"
            final_dir.mkdir(parents=True, exist_ok=True)
            detail_root.mkdir(parents=True, exist_ok=True)
            work_root.mkdir(parents=True, exist_ok=True)

            records: list[dict] = []
            published: list[str] = []
            totals = {
                "cleanup_removed": 0,
                "channel_found": 0,
                "channel_moved": 0,
                "poke_added": 0,
                "poke_updated": 0,
                "poke_unchanged": 0,
                "poke_skipped": 0,
                "passed": 0,
                "failed": 0,
            }

            file_count = len(self.files)
            stage_count = len(selected_steps)
            for file_index, source in enumerate(self.files):
                row = {
                    "file_name": source.name,
                    "cleanup_status": "SKIPPED",
                    "cleanup_removed": 0,
                    "channel_status": "SKIPPED",
                    "channel_found": 0,
                    "channel_moved": 0,
                    "poke_status": "SKIPPED",
                    "poke_added": 0,
                    "poke_updated": 0,
                    "poke_unchanged": 0,
                    "poke_skipped": 0,
                    "final_status": "FAIL",
                    "error": "",
                }
                current = Path(source)
                file_work = work_root / f"{file_index + 1:04d}_{self._safe_name(source.stem)}"
                file_detail = detail_root / f"{file_index + 1:04d}_{self._safe_name(source.stem)}"
                file_work.mkdir(parents=True, exist_ok=True)
                file_detail.mkdir(parents=True, exist_ok=True)

                try:
                    for stage_index, stage in enumerate(selected_steps):
                        stage_output = file_work / f"{stage_index + 1:02d}_{stage}"
                        stage_report = file_detail / f"{stage_index + 1:02d}_{stage}"
                        mapper = lambda percent, message="", fi=file_index, si=stage_index: self._emit_stage_progress(
                            fi, file_count, si, stage_count, percent, message
                        )

                        if stage == "cleanup":
                            self.log.emit(f"[组合处理] {source.name} -> ① 环网柜网络图元清理")
                            result = process_rmu_network_status_cleanup(
                                [current], stage_output, stage_report,
                                log=lambda message: self.log.emit(str(message)),
                                progress=mapper,
                            )
                            current = result.output_files[0]
                            row["cleanup_status"] = "PASS"
                            row["cleanup_removed"] = int(result.removed)
                            totals["cleanup_removed"] += int(result.removed)

                        elif stage == "channel_status":
                            self.log.emit(f"[组合处理] {source.name} -> ② channel_status 移动")
                            result = process_rmu_channel_status_reposition(
                                [current], stage_output, stage_report,
                                position=self.channel_position,
                                inner_margin=self.channel_margin,
                                log=lambda message: self.log.emit(str(message)),
                                progress=mapper,
                            )
                            current = result.output_files[0]
                            row["channel_status"] = "PASS"
                            row["channel_found"] = int(result.found)
                            row["channel_moved"] = int(result.moved)
                            totals["channel_found"] += int(result.found)
                            totals["channel_moved"] += int(result.moved)

                        elif stage == "poke":
                            self.log.emit(f"[组合处理] {source.name} -> ③ Poke 跳转处理")
                            result = process_poke_files(
                                db, [current], self.poke_settings, stage_output, stage_report,
                                enable_main_feeder=self.poke_enable_main_feeder,
                                enable_smart_rmu=self.poke_enable_smart_rmu,
                                log=lambda message: self.log.emit(str(message)),
                                progress=mapper,
                            )
                            current = result.output_files[0]
                            row["poke_status"] = "PASS"
                            row["poke_added"] = int(result.added)
                            row["poke_updated"] = int(result.updated)
                            row["poke_unchanged"] = int(result.unchanged)
                            row["poke_skipped"] = int(result.skipped)
                            totals["poke_added"] += int(result.added)
                            totals["poke_updated"] += int(result.updated)
                            totals["poke_unchanged"] += int(result.unchanged)
                            totals["poke_skipped"] += int(result.skipped)

                    final_target = final_dir / source.name
                    temp_target = final_target.with_name(final_target.name + ".tmp_pipeline")
                    shutil.copy2(current, temp_target)
                    temp_target.replace(final_target)
                    row["final_status"] = "PASS"
                    totals["passed"] += 1
                    published.append(str(final_target))
                    self.log.emit(f"[组合处理完成] {source.name} -> {final_target}")
                except Exception as exc:
                    row["error"] = str(exc)
                    row["final_status"] = "FAIL"
                    totals["failed"] += 1
                    self.log.emit(f"[组合处理失败] {source.name}: {exc}")
                records.append(row)

            csv_path, html_path = self._write_summary(records, report_dir)
            shutil.rmtree(work_root, ignore_errors=True)
            self.progress.emit(100, "图形组合处理完成")
            self.completed.emit({
                "run_dir": str(self.run_dir),
                "g_output_dir": str(final_dir),
                "html_report": str(html_path),
                "csv_report": str(csv_path),
                "output_files": published,
                "record_count": len(records),
                **totals,
            })
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if db:
                db.close()
