from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from g_file_studio.services.paths import default_workspace

RETENTION_DAYS = 30

MODULE_LABELS = {
    "small-elements": "异常小尺寸图元检测",
    "id": "ID 检查与修复",
    "rmu": "环网柜处理",
    "basic": "基础处理",
    "merge": "馈线图合并",
    "margin": "图形边距调整",
    "frame": "图框添加",
    "whole-graph-topology": "整图拓扑连接检查/修复",
    "transformer-fuse": "柱上变压器熔断器替换",
    "rmu-efi": "环网柜 EFI 保护图元添加",
}


def runs_root() -> Path:
    root = default_workspace() / "runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def module_runs_root(module_key: str) -> Path:
    root = runs_root() / module_key
    root.mkdir(parents=True, exist_ok=True)
    return root


def _meta_path(run_dir: Path) -> Path:
    return Path(run_dir) / "run.json"


def cleanup_expired_runs(days: int = RETENTION_DAYS) -> int:
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    root = runs_root()
    for module_dir in root.iterdir():
        if not module_dir.is_dir():
            continue
        for run_dir in module_dir.iterdir():
            if not run_dir.is_dir():
                continue
            try:
                mtime = datetime.fromtimestamp(run_dir.stat().st_mtime)
            except OSError:
                continue
            if mtime < cutoff:
                shutil.rmtree(run_dir, ignore_errors=True)
                removed += 1
    return removed


def create_run_directory(module_key: str, action: str) -> Path:
    cleanup_expired_runs()
    root = module_runs_root(module_key)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_action = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in action).strip("-") or "run"
    candidate = root / f"{stamp}_{safe_action}"
    index = 1
    while candidate.exists():
        candidate = root / f"{stamp}_{safe_action}_{index:02d}"
        index += 1
    candidate.mkdir(parents=True, exist_ok=False)
    now = datetime.now().isoformat(timespec="seconds")
    _meta_path(candidate).write_text(
        json.dumps({
            "module_key": module_key,
            "module": MODULE_LABELS.get(module_key, module_key),
            "action": action,
            "created_at": now,
            "status": "RUNNING",
            "path": str(candidate),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return candidate


def update_run_status(run_dir: Path | str, status: str, *, note: str = "") -> None:
    run_dir = Path(run_dir)
    path = _meta_path(run_dir)
    data: dict[str, object] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data.update({
        "status": status,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "path": str(run_dir),
    })
    if note:
        data["note"] = note
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_runs() -> list[dict[str, str]]:
    cleanup_expired_runs()
    rows: list[dict[str, str]] = []
    for module_dir in runs_root().iterdir():
        if not module_dir.is_dir():
            continue
        for run_dir in module_dir.iterdir():
            if not run_dir.is_dir():
                continue
            data: dict[str, object] = {}
            meta = _meta_path(run_dir)
            if meta.exists():
                try:
                    data = json.loads(meta.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            rows.append({
                "module": str(data.get("module") or MODULE_LABELS.get(module_dir.name, module_dir.name)),
                "action": str(data.get("action") or ""),
                "created_at": str(data.get("created_at") or ""),
                "status": str(data.get("status") or "UNKNOWN"),
                "path": str(run_dir),
            })
    rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    return rows


def configure_managed_output(path_row, module_key: str) -> Path:
    root = module_runs_root(module_key)
    path_row.set_path(root)
    path_row.edit.setReadOnly(True)
    path_row.edit.setClearButtonEnabled(False)
    path_row.button.setVisible(False)
    text = (
        "输出由 G File Studio 统一写入 workspace 运行记录目录，用户不能修改。"
        "每次执行都会创建独立运行目录；需要长期保存的结果请自行复制。运行记录仅保留 30 天。"
    )
    path_row.set_tooltip(text)
    return root


def begin_managed_run(path_row, module_key: str, action: str) -> Path:
    run_dir = create_run_directory(module_key, action)
    path_row.set_path(run_dir)
    return run_dir
