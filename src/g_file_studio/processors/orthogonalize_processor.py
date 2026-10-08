from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from g_file_studio.engines.orthogonalize_engine import orthogonalize_tree
from g_file_studio.models import InputMode, OrthogonalizeSettings, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs
from g_file_studio.services.remote_symbol_library import DEFAULT_REMOTE_SYMBOL_ROOT, RemoteSymbolLibraryService
from g_file_studio.services.site_profile_service import SiteProfileService, _geometry_templates_from_symbol_catalog


def _cached_server_geometry_templates(
    host: str,
    root: str,
) -> dict[str, list[dict[str, object]]]:
    """Build Pin geometry from the already-synchronized LOCAL server-symbol cache.

    This function is deliberately network-free.  ``RemoteSymbolLibraryService`` only
    reads ``sync_snapshot.json``/``manifest.json`` from AppData here.  A devref is
    accepted only when every cached physical definition for that devref agrees on
    w/h and Pins; conflicting duplicate definitions are ignored instead of guessed.
    """
    host = str(host or "").strip()
    root = str(root or DEFAULT_REMOTE_SYMBOL_ROOT).strip() or DEFAULT_REMOTE_SYMBOL_ROOT
    if not host:
        return {}
    try:
        snapshot = RemoteSymbolLibraryService().load_cached_sync_snapshot(host=host, root=root)
    except Exception:
        return {}

    records: list[dict[str, object]] = []
    raw_rows = snapshot.get("server_file_records", []) if isinstance(snapshot, dict) else []
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            standard = row.get("standard_record", {})
            if isinstance(standard, dict) and str(standard.get("devref", "") or "").strip():
                records.append(dict(standard))
    matched = snapshot.get("matched_records", {}) if isinstance(snapshot, dict) else {}
    if isinstance(matched, dict):
        for standard in matched.values():
            if isinstance(standard, dict) and str(standard.get("devref", "") or "").strip():
                records.append(dict(standard))

    by_devref: dict[str, list[dict[str, object]]] = {}
    for row in records:
        devref = str(row.get("devref", "") or "").strip()
        if devref:
            by_devref.setdefault(devref, []).append(row)

    catalog: dict[str, dict[str, object]] = {}
    for devref, rows in by_devref.items():
        fingerprints: dict[tuple[object, ...], dict[str, object]] = {}
        for row in rows:
            try:
                width = float(row.get("width", 0.0) or 0.0)
                height = float(row.get("height", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            pins_raw = row.get("pins", [])
            pins: list[tuple[float, float]] = []
            if isinstance(pins_raw, list):
                for pin in pins_raw:
                    if not isinstance(pin, (list, tuple)) or len(pin) < 2:
                        continue
                    try:
                        pins.append((float(pin[0]), float(pin[1])))
                    except (TypeError, ValueError):
                        continue
            if width <= 0 or height <= 0 or not pins:
                continue
            fingerprint = (
                round(width, 6),
                round(height, 6),
                tuple((round(x, 6), round(y, 6)) for x, y in pins),
            )
            fingerprints[fingerprint] = row
        if len(fingerprints) != 1:
            continue
        selected = next(iter(fingerprints.values()))
        catalog[devref] = {
            "width": selected.get("width", 0.0),
            "height": selected.get("height", 0.0),
            "pins": selected.get("pins", []),
        }
    return _geometry_templates_from_symbol_catalog(catalog)


def _global_geometry_templates(
    *,
    symbol_library_host: str = "",
    symbol_library_root: str = "",
) -> dict[str, list[dict[str, object]]] | None:
    """Load authoritative Pin geometry, preferring the current local server cache.

    GLOBAL/Profile geometry remains a fallback for old installations.  The explicit
    server-symbol sync cache is merged last because it reflects the operator's
    current ``主程序“图元管理”`` inventory.  No SSH request is made here.
    """
    geometry: dict[str, list[dict[str, object]]] = {}
    try:
        profile = SiteProfileService().get_global_profile(auto_initialize=False)
    except Exception:
        profile = None
    if profile is not None and profile.geometry_templates:
        geometry.update(profile.geometry_templates)
    geometry.update(
        _cached_server_geometry_templates(symbol_library_host, symbol_library_root)
    )
    return geometry or None


def orthogonalize_g_files(
    source_path: Path,
    input_mode: InputMode,
    output_dir: Path,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
    *,
    symbol_library_host: str = "",
    symbol_library_root: str = "",
) -> ProcessingResult:
    """Create orthogonalized copies of one G file or a first-level G directory."""
    files = discover_g_inputs(source_path, input_mode)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    failed: list[str] = []
    total_inspected = 0
    total_changed = 0
    total_segments = 0
    total_aligned_devices = 0
    total_aligned_lines = 0
    total_connection_aligned_lines = 0
    total_repaired_dangling_endpoints = 0
    total_repaired_topology_links = 0
    total_ambiguous_dangling_endpoints = 0
    total_rmu_outgoing_aligned_junctions = 0
    total_rmu_outgoing_extended_lines = 0
    total_rebuilt_lines = 0
    total_skipped = 0
    cached_server_geometry = _cached_server_geometry_templates(
        symbol_library_host, symbol_library_root
    )
    geometry_templates = _global_geometry_templates(
        symbol_library_host=symbol_library_host,
        symbol_library_root=symbol_library_root,
    )
    if geometry_templates:
        if cached_server_geometry:
            log(
                f"[标准几何] 已加载 {len(geometry_templates)} 类标准 Pin，其中 "
                f"{len(cached_server_geometry)} 类来自本机服务器图元缓存（未访问 SSH）。"
            )
        else:
            log(f"[标准几何] 已加载 GLOBAL/Profile 标准 Pin：{len(geometry_templates)} 类图元。")
    else:
        log("[标准几何] 未找到可用标准 Pin，线路终点保留保守外框兼容策略。")

    for index, input_path in enumerate(files, start=1):
        output_path = output_dir / input_path.name
        try:
            if output_path.resolve() == input_path.resolve():
                raise ValueError("正交化输出目录不能与源文件位置相同，避免覆盖原始 G 文件。")
            tree = ET.parse(input_path)
            result = orthogonalize_tree(tree, geometry_templates=geometry_templates)
            total_inspected += result.inspected_lines
            total_changed += result.changed_lines
            total_segments += result.changed_segments
            total_aligned_devices += result.aligned_devices
            total_aligned_lines += result.aligned_lines
            total_connection_aligned_lines += result.connection_aligned_lines
            total_repaired_dangling_endpoints += result.repaired_dangling_endpoints
            total_repaired_topology_links += result.repaired_topology_links
            total_ambiguous_dangling_endpoints += result.ambiguous_dangling_endpoints
            total_rmu_outgoing_aligned_junctions += result.rmu_outgoing_aligned_junctions
            total_rmu_outgoing_extended_lines += result.rmu_outgoing_extended_lines
            total_rebuilt_lines += result.rebuilt_lines
            total_skipped += result.skipped_lines
            if result.changed:
                if hasattr(ET, "indent"):
                    ET.indent(tree, space="    ")
                temp_path = output_path.with_name(output_path.name + ".tmp")
                tree.write(temp_path, encoding="utf-8", xml_declaration=True)
                ET.parse(temp_path)
                os.replace(temp_path, output_path)
            else:
                shutil.copy2(input_path, output_path)
            outputs.append(output_path)
            log(
                f"[OK] {input_path.name}：检查线路 {result.inspected_lines} 条，"
                f"正交化 {result.changed_lines} 条、增加直角段 {result.changed_segments} 个，"
                    f"同类设备对齐 {result.aligned_devices} 个、跟随修正线路 {result.aligned_lines} 条，"
                    f"其中连接点对齐 {result.connection_aligned_lines} 条，"
                    f"悬空端点吸附 {result.repaired_dangling_endpoints} 个、"
                    f"补齐拓扑引用 {result.repaired_topology_links} 处、"
                    f"歧义端点 {result.ambiguous_dangling_endpoints} 个，"
                    f"RMU 出线对齐 {result.rmu_outgoing_aligned_junctions} 处、"
                    f"拉长/校正出线 {result.rmu_outgoing_extended_lines} 条，"
                    f"确认重画线路 {result.rebuilt_lines} 条，"
                f"保守跳过 {result.skipped_lines} 条；输出 {output_path.name}。"
            )
            for detail in result.endpoint_repair_details[:20]:
                log(f"  + 端点修复：{detail}")
            if len(result.endpoint_repair_details) > 20:
                log(f"  + 其余 {len(result.endpoint_repair_details) - 20} 条端点修复详情省略。")
            for detail in result.rmu_outgoing_alignment_details[:20]:
                log(f"  + RMU 出线对齐：{detail}")
            if len(result.rmu_outgoing_alignment_details) > 20:
                log(f"  + 其余 {len(result.rmu_outgoing_alignment_details) - 20} 条 RMU 出线对齐详情省略。")
            for issue in result.issues[:20]:
                log(
                    f"  - 跳过 <{issue.element_type}> id={issue.element_id or '(空)'}："
                    f"{issue.reason}"
                )
            if len(result.issues) > 20:
                log(f"  - 其余 {len(result.issues) - 20} 条跳过原因省略。")
        except Exception as exc:
            failed.append(f"{input_path.name}: {exc}")
            log(f"[ERROR] {input_path.name}：{exc}")
        if progress:
            progress(round(index * 100 / len(files)))

    log(
        f"[线路正交化汇总] 输入 {len(files)} 个，成功 {len(outputs)} 个，失败 {len(failed)} 个；"
        f"检查线路 {total_inspected} 条，正交化 {total_changed} 条，"
        f"增加直角段 {total_segments} 个，同类设备对齐 {total_aligned_devices} 个，"
        f"跟随修正线路 {total_aligned_lines} 条，其中连接点对齐 {total_connection_aligned_lines} 条，"
        f"悬空端点吸附 {total_repaired_dangling_endpoints} 个、"
        f"补齐拓扑引用 {total_repaired_topology_links} 处、"
        f"歧义端点 {total_ambiguous_dangling_endpoints} 个，"
        f"RMU 出线对齐 {total_rmu_outgoing_aligned_junctions} 处、"
        f"拉长/校正出线 {total_rmu_outgoing_extended_lines} 条，"
        f"确认重画线路 {total_rebuilt_lines} 条，保守跳过 {total_skipped} 条。"
    )
    return ProcessingResult(
        success=not failed,
        output_files=outputs,
        warnings=failed,
        statistics={
            "input_mode": input_mode.value,
            "source_path": str(source_path),
            "file_count": len(outputs),
            "failed_file_count": len(failed),
            "inspected_line_count": total_inspected,
            "orthogonalized_line_count": total_changed,
            "added_right_angle_segment_count": total_segments,
            "aligned_device_count": total_aligned_devices,
            "aligned_line_count": total_aligned_lines,
            "connection_aligned_line_count": total_connection_aligned_lines,
            "repaired_dangling_endpoint_count": total_repaired_dangling_endpoints,
            "repaired_topology_link_count": total_repaired_topology_links,
            "ambiguous_dangling_endpoint_count": total_ambiguous_dangling_endpoints,
            "rmu_outgoing_aligned_junction_count": total_rmu_outgoing_aligned_junctions,
            "rmu_outgoing_extended_line_count": total_rmu_outgoing_extended_lines,
            "rebuilt_line_count": total_rebuilt_lines,
            "skipped_line_count": total_skipped,
            "global_standard_geometry_class_count": len(geometry_templates or {}),
            "output_naming": "source_filename",
        },
    )


def process_orthogonalize(
    settings: OrthogonalizeSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    """Run the standalone线路正交化 module from its typed settings object."""
    return orthogonalize_g_files(
        settings.source_path,
        settings.input_mode,
        settings.output_dir,
        log,
        progress,
        symbol_library_host=settings.symbol_library_host,
        symbol_library_root=settings.symbol_library_root,
    )
