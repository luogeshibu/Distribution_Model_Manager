from __future__ import annotations

import csv
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from g_file_studio.engines.transformer_fuse_engine import (
    TransformerFuseBatchResult,
    replace_transformer_oh_with_fuse_pairs,
    write_tree_atomic,
)
from g_file_studio.models import InputMode, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs
from g_file_studio.services.id_rule_service import IdRuleService


@dataclass(frozen=True)
class TransformerFuseSettings:
    source_path: Path
    input_mode: InputMode
    output_dir: Path
    classification_marker_entries: tuple[tuple[str, str, str, str], ...] = ()


def process_transformer_fuse(
    settings: TransformerFuseSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    id_rules = IdRuleService().load_rules()
    for required in ("ZhaiWaiDaoZha", "ConnectLine"):
        rule = id_rules.get(required)
        if rule is None or not rule.enabled or not rule.verified:
            raise ValueError(
                f"柱上变压器熔断器替换需要已确认的 <{required}> ID 规则。"
                "请先在‘ID 检查与修复’中确认后再执行。"
            )

    batch = TransformerFuseBatchResult()
    output_files: list[Path] = []
    warnings: list[str] = []
    total = max(1, len(files))

    if progress:
        progress(0)
    log(
        f"[柱上变压器熔断器替换] 输入 {len(files)} 个 G 文件；"
        "仅处理分类标记 TRANSFORMER_OH 且只有一个 Transformer 端点已连接 ConnectLine/FeedLine 的 TransformerDis；旧图缺失 reciprocal link 时使用精确 Pin 坐标回退。"
    )
    log("[拓扑规则] 原外部线路几何坐标保持不变；其原端点改接新 Fuse 的空闲 Pin，Transformer 通过新增短 ConnectLine 接到 Fuse 另一端。")
    log("[安全规则] Transformer 两个端点均已连接的柱上变压器直接跳过，不做替换。")

    for index, source in enumerate(files, 1):
        output = settings.output_dir / source.name
        shutil.copy2(source, output)
        try:
            tree = ET.parse(output)
            result = replace_transformer_oh_with_fuse_pairs(
                tree,
                source,
                marker_entries=settings.classification_marker_entries,
                id_rules=id_rules,
            )
            write_tree_atomic(tree, output)
            batch.files.append(result)
            output_files.append(output)
            log(
                f"[{index}/{len(files)}] {source.name}: TRANSFORMER_OH={result.matched_transformers}, "
                f"已替换={result.replaced}, 无连接跳过={result.skipped_unconnected}, "
                f"多连接跳过={result.skipped_multi_connected}, 异常连接跳过={result.skipped_invalid_connection}"
            )
            for row in result.rows:
                if row.get("result") == "REPLACED":
                    log(f"  - {row.get('transformer_id')}: {row.get('detail')}")
        except Exception as exc:
            warnings.append(f"{source.name}: {exc}")
            log(f"[{index}/{len(files)}] {source.name}: 处理失败：{exc}")
            output.unlink(missing_ok=True)
        if progress:
            progress(round(index * 100 / total))

    report_path = settings.output_dir / "transformer-fuse-report.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["file", "transformer_id", "result", "detail"],
        )
        writer.writeheader()
        for file_result in batch.files:
            writer.writerows(file_result.rows)
    output_files.append(report_path)

    success = bool(output_files) and not warnings
    return ProcessingResult(
        success=success,
        output_files=output_files,
        warnings=warnings,
        statistics={
            "输入文件": len(files),
            "识别 TRANSFORMER_OH": batch.matched_transformers,
            "已替换": batch.replaced,
            "无连接跳过": batch.skipped_unconnected,
            "多连接跳过": batch.skipped_multi_connected,
            "异常连接跳过": batch.skipped_invalid_connection,
            "报告": str(report_path),
        },
    )
