from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from g_file_studio.engines.connection_engine import repair_tree_connections
from g_file_studio.models import (
    BasicOutputConflictAction,
    ConnectionRepairSettings,
    ProcessingResult,
)
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs



def _output_path_for(input_path: Path, settings: ConnectionRepairSettings) -> Path:
    # 一对一处理统一保持源 G 文件名。
    return settings.output_dir / input_path.name


def process_connection_points(
    settings: ConnectionRepairSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    """Align verified device ports and repair node_area/link connection references."""
    files = discover_g_inputs(settings.source_path, settings.input_mode)
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    failed: list[str] = []
    total_aligned_devices = 0
    total_adjusted_lines = 0
    total_relations = 0
    total_added = 0
    total_updated = 0
    total_removed = 0
    total_changed_elements = 0
    total_changed_attributes = 0

    log(
        f"[连接点修复] 输入 {len(files)} 个 G 文件。采用保守增量模式：保留全部原连接，"
        "仅吸附已验证的半像素设备 X，不修改连接线坐标，只修复 node_area/link 中缺失的引用。"
        "不修改设备 Y、ID、文字、颜色、图标、Merge 或其他业务属性。"
    )

    for index, input_path in enumerate(files, start=1):
        output_path = _output_path_for(input_path, settings)
        try:
            tree = ET.parse(input_path)
            repair = repair_tree_connections(tree, input_path)
            total_aligned_devices += repair.aligned_device_count
            total_adjusted_lines += repair.adjusted_line_endpoint_count
            total_relations += repair.inferred_relation_count
            total_added += repair.added_reference_count
            total_updated += repair.updated_reference_count
            total_removed += repair.removed_reference_count
            total_changed_elements += repair.changed_element_count
            total_changed_attributes += repair.changed_attribute_count

            tmp_path = output_path.with_name(output_path.name + ".tmp")
            tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
            ET.parse(tmp_path)
            os.replace(tmp_path, output_path)
            outputs.append(output_path)

            log(
                f"✓ {input_path.name}：连接线 {repair.line_count} 个、母线 {repair.conductor_count} 个、"
                f"可连接设备 {repair.device_count} 个；水平对齐设备 {repair.aligned_device_count} 个、"
                f"连接线坐标修改 {repair.adjusted_line_endpoint_count} 个；"
                f"推断连接关系 {repair.inferred_relation_count} 条，新增引用 "
                f"{repair.added_reference_count} 处、修正引用 {repair.updated_reference_count} 处、"
                f"删除错误引用 {repair.removed_reference_count} 处，"
                f"实际变更图元 {repair.changed_element_count} 个、属性 {repair.changed_attribute_count} 个；"
                f"输出 {output_path.name}。"
            )
            if repair.changed_element_ids:
                log("  - 变更图元 ID：" + ", ".join(repair.changed_element_ids))
            else:
                log("  - 当前文件连接关系完整，无需修改。")
            for warning in repair.warnings:
                log(f"[连接点修复告警] {input_path.name}：{warning}")
        except Exception as exc:
            failed.append(f"{input_path.name}: {exc}")
            log(f"[连接点修复失败] {input_path.name}：{exc}")

        if progress:
            progress(round(index * 100 / len(files)))

    log(
        f"[连接点修复汇总] 输入 {len(files)} 个，成功 {len(outputs)} 个，失败 {len(failed)} 个；"
        f"水平对齐设备 {total_aligned_devices} 个、连接线坐标修改 {total_adjusted_lines} 个；"
        f"推断连接关系 {total_relations} 条，新增引用 {total_added} 处，修正引用 {total_updated} 处，"
        f"删除错误引用 {total_removed} 处，"
        f"变更图元 {total_changed_elements} 个、属性 {total_changed_attributes} 个。"
    )

    return ProcessingResult(
        success=not failed,
        output_files=outputs,
        warnings=failed,
        statistics={
            "input_mode": settings.input_mode.value,
            "source_path": str(settings.source_path),
            "file_count": len(outputs),
            "failed_file_count": len(failed),
            "aligned_connection_device_count": total_aligned_devices,
            "adjusted_connection_line_count": total_adjusted_lines,
            "inferred_connection_count": total_relations,
            "added_connection_reference_count": total_added,
            "updated_connection_reference_count": total_updated,
            "removed_connection_reference_count": total_removed,
            "changed_connection_element_count": total_changed_elements,
            "changed_connection_attribute_count": total_changed_attributes,
        },
    )
