from __future__ import annotations

import csv
import html
import os
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


# Makkah fixed cleanup rule confirmed against the supplied field G files.
# The live files use *.zt.icn.g for all three Status icons.  Keep the user's
# historical General_Note *.zt.icg.g spelling as an exact compatibility alias.
FIXED_RMU_NETWORK_STATUS_DEVREFS: dict[str, str] = {
    "#NariPd_Generator.zt.icn.g:NariPd_Generator": "Generator(G)",
    "#NariPd_Temporary_Cable.zt.icn.g:NariPd_Temporary_Cable": "Temporary Cable(L)",
    "#NariPd_General_Note.zt.icn.g:NariPd_General_Note": "General Note(N)",
    "#NariPd_General_Note.zt.icg.g:NariPd_General_Note": "General Note(N)",
}


@dataclass
class GraphicsCleanupFileRecord:
    file_name: str
    generator_removed: int = 0
    temporary_cable_removed: int = 0
    general_note_removed: int = 0
    total_removed: int = 0
    status: str = "NO_MATCH"


@dataclass
class GraphicsCleanupResult:
    output_files: list[Path]
    records: list[GraphicsCleanupFileRecord]
    csv_path: Path
    html_path: Path
    removed: int


def _local_name(tag) -> str:
    return str(tag or "").rsplit("}", 1)[-1]


def _write_tree_atomic(root: ET.Element, output_path: Path) -> None:
    output_path = Path(output_path)
    temp = output_path.with_name(output_path.name + ".tmp_graphics_cleanup")
    tree = ET.ElementTree(root)
    tree.write(temp, encoding="utf-8", xml_declaration=True)
    # Refuse to replace the Workspace safe copy unless the output remains XML.
    ET.parse(temp)
    os.replace(temp, output_path)


def remove_fixed_rmu_network_status_elements(root: ET.Element) -> Counter:
    """Remove the three fixed Makkah RMU-bottom Status icons.

    The operation is deliberately devref-driven and does not use geometry,
    RMU naming, database state, or proximity.  This matches the field request:
    those three graphic resources are obsolete everywhere in the selected
    Makkah ring/SLD G files and should simply be deleted.
    """
    counts: Counter = Counter()
    for parent in root.iter():
        for child in list(parent):
            if _local_name(child.tag).casefold() != "status":
                continue
            devref = str(child.get("devref") or "").strip()
            label = FIXED_RMU_NETWORK_STATUS_DEVREFS.get(devref)
            if not label:
                continue
            parent.remove(child)
            counts[label] += 1
    return counts


def _write_csv(records: list[GraphicsCleanupFileRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(GraphicsCleanupFileRecord.__dataclass_fields__)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    return path


def _write_html(records: list[GraphicsCleanupFileRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in records:
        row_class = "pass" if record.total_removed else "info"
        rows.append(
            "<tr class='%s'><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d</td><td>%s</td></tr>"
            % (
                row_class,
                html.escape(record.file_name),
                record.generator_removed,
                record.temporary_cable_removed,
                record.general_note_removed,
                record.total_removed,
                html.escape(record.status),
            )
        )
    content = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>环网柜网络图元清理报告</title>
<style>
body{{font-family:'Microsoft YaHei','Segoe UI',Arial,sans-serif;margin:24px;background:#f3f7f5;color:#17372e}}
h1{{color:#006b52}} .rule{{background:#eaf8f2;border:1px solid #b8dfd1;padding:12px 14px;margin-bottom:16px;border-radius:8px;line-height:1.7}}
table{{border-collapse:collapse;width:100%;background:white;font-size:12px}}th,td{{border:1px solid #d3e3dc;padding:7px 9px;text-align:left;white-space:nowrap}}th{{background:#006b52;color:white}}.pass{{background:#eaf8f2}}.info{{background:#eaf3ff}}
</style></head><body><h1>环网柜网络图元清理报告</h1>
<div class='rule'>固定删除 Status.devref：NariPd_Generator.zt.icn.g、NariPd_Temporary_Cable.zt.icn.g、NariPd_General_Note.zt.icn.g（兼容 General_Note.zt.icg.g）。原始 G 文件不修改，只写 Workspace 安全副本。</div>
<table><thead><tr><th>G文件</th><th>Generator(G)</th><th>Temporary Cable(L)</th><th>General Note(N)</th><th>删除总数</th><th>状态</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""
    path.write_text(content, encoding="utf-8")
    return path


def process_rmu_network_status_cleanup(
    files: Iterable[Path],
    output_dir: Path,
    report_dir: Path,
    *,
    log=None,
    progress=None,
) -> GraphicsCleanupResult:
    log = log or (lambda _msg: None)
    files = [Path(path) for path in files]
    if not files:
        raise ValueError("没有可处理的 G 文件。")

    output_dir = Path(output_dir)
    report_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    output_files: list[Path] = []
    records: list[GraphicsCleanupFileRecord] = []
    removed_total = 0

    for index, source in enumerate(files, start=1):
        if progress:
            progress(
                int((index - 1) / max(1, len(files)) * 95),
                f"正在清理 {source.name}",
            )
        target = output_dir / source.name
        shutil.copy2(source, target)
        log(f"[安全副本] {source} -> {target}")

        try:
            tree = ET.parse(target)
        except (ET.ParseError, UnicodeError, LookupError) as exc:
            raise ValueError(f"G 文件 XML 解析失败：{source.name}: {exc}") from exc
        root = tree.getroot()
        counts = remove_fixed_rmu_network_status_elements(root)
        _write_tree_atomic(root, target)

        generator = int(counts.get("Generator(G)", 0))
        temporary = int(counts.get("Temporary Cable(L)", 0))
        note = int(counts.get("General Note(N)", 0))
        total = generator + temporary + note
        removed_total += total
        status = "REMOVED" if total else "NO_MATCH"
        records.append(
            GraphicsCleanupFileRecord(
                file_name=target.name,
                generator_removed=generator,
                temporary_cable_removed=temporary,
                general_note_removed=note,
                total_removed=total,
                status=status,
            )
        )
        output_files.append(target)
        log(
            f"[环网柜网络图元清理] {target.name}: "
            f"G={generator}, L={temporary}, N={note}, 合计={total}"
        )

    csv_path = _write_csv(records, report_dir / "rmu_network_cleanup_report.csv")
    html_path = _write_html(records, report_dir / "rmu_network_cleanup_report.html")
    if progress:
        progress(100, "环网柜网络图元清理完成")
    return GraphicsCleanupResult(
        output_files=output_files,
        records=records,
        csv_path=csv_path,
        html_path=html_path,
        removed=removed_total,
    )
