from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from g_file_studio.engines.rmu_efi_engine import (
    RmuEfiBatchResult,
    add_rmu_efi_normal_icons,
    write_tree_atomic,
)
from g_file_studio.models import InputMode, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs
from g_file_studio.services.id_rule_service import IdRuleService


@dataclass(frozen=True)
class RmuEfiSettings:
    source_path: Path
    input_mode: InputMode
    output_dir: Path
    normal_earth_gap_px: int = 5
    frame_margin_px: int = 10


def process_rmu_efi(
    settings: RmuEfiSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    rule = IdRuleService().load_rules().get("pwbh")
    if rule is None or not rule.enabled or not rule.verified:
        raise ValueError(
            "环网柜 EFI 保护图元添加需要已确认的 <pwbh> ID 规则。"
            "请先到‘ID 检查与修复’完成确认。"
        )

    batch = RmuEfiBatchResult()
    output_files: list[Path] = []
    warnings: list[str] = []
    log(f"[环网柜 EFI 保护图元添加] 输入 {len(files)} 个 G 文件。")
    log(
        "[EFI 参数] 已有 NariPd_Normal 不重复添加；只支持左侧/上侧两种布局；"
        f"Normal-Earth 图形间距={settings.normal_earth_gap_px} G坐标单位；"
        f"EFI-环网柜框距离={settings.frame_margin_px} G坐标单位。"
    )

    total = max(1, len(files))
    for index, source in enumerate(files, start=1):
        try:
            tree = ET.parse(source)
            result = add_rmu_efi_normal_icons(
                tree,
                file_name=source.name,
                pwbh_id_rule=rule,
                normal_earth_gap_px=settings.normal_earth_gap_px,
                frame_margin_px=settings.frame_margin_px,
            )
            target = settings.output_dir / source.name
            batch.files.append(result)
            if result.added:
                write_tree_atomic(tree, target)
                output_files.append(target)
                log(
                    f"[{source.name}] 已修改并输出 G：环网柜 {result.detected_rmus}，"
                    f"已存在 {result.already_present}，新增 {result.added}，"
                    f"无 Earth 跳过 {result.skipped_no_earth}，"
                    f"非两种确认布局跳过 {result.skipped_unsupported_side}，"
                    f"空间不足跳过 {result.skipped_insufficient_space}。"
                )
            else:
                if result.detected_rmus > 0 and result.already_present == result.detected_rmus:
                    reason = "所有识别到的环网柜都已经存在 EFI Normal"
                elif result.detected_rmus == 0:
                    reason = "未识别到环网柜"
                else:
                    reason = "没有成功新增 EFI Normal；具体跳过原因见报告"
                log(
                    f"[{source.name}] 未修改，不输出 G 文件：{reason}。"
                    f"识别 {result.detected_rmus}，已存在 {result.already_present}，新增 0，"
                    f"无 Earth 跳过 {result.skipped_no_earth}，"
                    f"非两种确认布局跳过 {result.skipped_unsupported_side}，"
                    f"空间不足跳过 {result.skipped_insufficient_space}。"
                )
        except Exception as exc:
            warnings.append(f"{source.name}: {type(exc).__name__}: {exc}")
            log(f"[{source.name}] 失败：{type(exc).__name__}: {exc}")
        if progress is not None:
            progress(int(index * 100 / total))

    report_path = settings.output_dir / "rmu-efi-report.csv"
    fieldnames = ["file", "rmu", "frame_id", "result", "detail"]
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for file_result in batch.files:
            writer.writerow({
                "file": file_result.file_name,
                "rmu": "",
                "frame_id": "",
                "result": "FILE_MODIFIED_OUTPUT" if file_result.added else "FILE_UNCHANGED_NO_G_OUTPUT",
                "detail": (
                    f"识别环网柜={file_result.detected_rmus}；已存在 Normal={file_result.already_present}；"
                    f"新增={file_result.added}；无 Earth 跳过={file_result.skipped_no_earth}；"
                    f"非确认布局跳过={file_result.skipped_unsupported_side}；"
                    f"空间不足跳过={file_result.skipped_insufficient_space}；"
                    + ("已生成修改后的 G 文件" if file_result.added else "原 G 未发生修改，因此不复制到输出目录")
                ),
            })
            for row in file_result.rows:
                writer.writerow({name: row.get(name, "") for name in fieldnames})
    output_files.append(report_path)

    return ProcessingResult(
        success=bool(output_files) and not warnings,
        output_files=output_files,
        warnings=warnings,
        statistics={
            "输入文件": len(files),
            "实际修改并输出 G 文件": sum(1 for item in batch.files if item.added > 0),
            "未修改且未输出 G 文件": sum(1 for item in batch.files if item.added == 0),
            "识别环网柜": batch.detected_rmus,
            "已存在 Normal": batch.already_present,
            "新增 EFI Normal": batch.added,
            "无 Earth 跳过": batch.skipped_no_earth,
            "非确认布局跳过": batch.skipped_unsupported_side,
            "空间不足跳过": batch.skipped_insufficient_space,
            "报告": str(report_path),
        },
    )
