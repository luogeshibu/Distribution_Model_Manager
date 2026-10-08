from __future__ import annotations

import csv
import html
import os
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from g_file_studio.engines.feeder_title_engine import move_feeder_titles_above_buses
from g_file_studio.engines.rmu_group_engine import enhance_rmu_tree, remove_all_graphic_merges
from g_file_studio.engines.rmu_identification_engine import identify_rmus, parse_name_exclusions
from g_file_studio.engines.small_element_engine import delete_issues_to_output, scan_file, write_reports
from g_file_studio.engines.smart_profile_engine import apply_smart_profile_to_tree
from g_file_studio.jeddah.style_engine import (
    apply_jeddah_busdis_blue,
    apply_jeddah_rmu_name_standard_to_tree,
    ensure_jeddah_normal_rmu_frames_white,
    ensure_jeddah_smart_rmu_devices,
    ensure_jeddah_smart_rmu_frames_red,
    remove_duplicate_smart_labels_in_rmus,
    remove_jeddah_adjacent_measurement_texts,
    remove_jeddah_channel_status_points,
    remove_jeddah_ht_texts,
    replace_jeddah_smr_with_smart,
)
from g_file_studio.models import (
    BasicOutputConflictAction,
    FrameSettings,
    IdAction,
    IdSettings,
    InputMode,
    MarginSettings,
    PersonSettings,
    ProcessingResult,
    TemplateMode,
)
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs
from g_file_studio.processors.frame_processor import add_drawing_frames
from g_file_studio.processors.id_processor import process_ids
from g_file_studio.processors.margin_processor import adjust_graph_margins
from g_file_studio.services.output_naming import make_task_timestamp
from g_file_studio.services.site_profile_service import (
    SiteProfileService,
    authoritative_standard_catalog,
    authoritative_geometry_templates,
    geometry_templates_from_server_records,
    resolve_jeddah_classification_marker_roles,
    resolve_jeddah_role_devrefs,
    standard_catalog_from_server_records,
)
from g_file_studio.services.report_i18n import report_is_english


JEDDAH_RED = "#FF0000"


@dataclass(frozen=True)
class JeddahBatchSettings:
    """Parameters owned only by the Jeddah feeder batch module.

    Existing module settings and business implementations are intentionally not
    changed.  This object only tells the orchestrator which input to process and
    which Jeddah-specific parameters to apply. RMU cabinet-name direction is no
    longer user-configured here; the Jeddah flow uses the shared fixed top-of-frame resolver.
    """

    source_path: Path
    input_mode: InputMode
    output_dir: Path
    small_element_threshold: int = 10
    rmu_name_exclusions: str = ""
    margin_left: int = 500
    margin_top: int = 500
    margin_right: int = 500
    margin_bottom: int = 500
    frame_template_file: Path | None = None
    frame_template_mode: TemplateMode = TemplateMode.BUILTIN
    frame_builtin_template_id: str = "default_sld_frame"
    rmu_profile_name: str = ""
    rmu_profile_version: int | None = None
    classification_marker_entries: tuple[tuple[str, str, str], ...] = ()
    # Public v2.18.248 path: exact definitions already synchronized to local AppData.
    # Kept separate from the retired SiteProfile repository/global-selection pointer.
    server_standard_records: tuple[dict[str, object], ...] = ()

@dataclass
class _FileSummary:
    file_name: str
    graphic_merges_removed: int = 0
    rmu_rects_lowered: int = 0
    abnormal_removed: int = 0
    abnormal_with_keyid: int = 0
    rmu_names_found: int = 0
    rmu_name_text_matched: int = 0
    rmu_name_white_changed: int = 0
    normal_rmu_frame_white_changed: int = 0
    smr_to_smart_replaced: int = 0
    smr_existing_smart_cleanup: int = 0
    smr_text_removed: int = 0
    smart_device_precheck_changed: int = 0
    cbreaker_smart_devref_changed: int = 0
    smart_device_postcheck_changed: int = 0
    profile_smart_lbs_changed: int = 0
    profile_smart_breaker_changed: int = 0
    profile_smart_ground_changed: int = 0
    profile_normal_lbs_changed: int = 0
    profile_normal_breaker_changed: int = 0
    profile_normal_ground_changed: int = 0
    profile_geometry_adjusted: int = 0
    redundant_connection_lines_removed: int = 0
    connection_lines_straightened: int = 0
    connection_devices_realigned: int = 0
    connection_endpoints_connected: int = 0
    connection_topology_links_repaired: int = 0
    busdis_blue_changed: int = 0
    ht_text_removed: int = 0
    channel_status_removed: int = 0
    duplicate_smart_removed: int = 0
    adjacent_measurement_pairs_removed: int = 0
    adjacent_measurement_texts_removed: int = 0
    margin_adjusted: int = 0
    frame_added: int = 0
    final_output: str = ""
    result: str = "PASS"
    notes: str = ""


def _scale_progress(progress: ProgressCallback | None, start: int, end: int):
    if progress is None:
        return None

    span = max(0, end - start)

    def emit(value: int) -> None:
        value = max(0, min(100, int(value)))
        progress(start + round(span * value / 100))

    return emit



def _remove_all_graphic_merges_first(
    files: list[Path],
    output_dir: Path,
    *,
    name_exclusions: str = "",
    summaries: dict[str, _FileSummary],
    log: LogCallback,
    progress: ProgressCallback | None,
) -> tuple[int, int]:
    """Run the existing Basic Processing graphic-group cleanup as the first Jeddah step.

    No merge-cleanup algorithm is duplicated here.  The Jeddah orchestrator only parses
    each input, obtains the shared strict RMU rectangle IDs, calls
    ``remove_all_graphic_merges(..., lower_rmu_rects=True, rmu_rect_ids=...)``,
    validates the serialized XML, and passes the result to the following stages.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    total_removed = 0
    total_lowered = 0
    count = max(1, len(files))

    for index, source in enumerate(files, 1):
        tree = ET.parse(source)
        identification = identify_rmus(
            tree,
            source,
            smart_in_type=True,
            excluded_name_values=parse_name_exclusions(name_exclusions),
        )
        validated_rmu_rect_ids = {
            item.rect_id for item in identification.items if item.rect_id
        }
        cleanup = remove_all_graphic_merges(
            tree,
            source,
            lower_rmu_rects=True,
            rmu_rect_ids=validated_rmu_rect_ids,
        )
        output = output_dir / source.name
        # Intermediate batch files stay compact. The next stage immediately parses
        # them, so pretty-indenting and reparsing the just-written XML would duplicate
        # full-tree CPU/disk work for every feeder without changing business output.
        tmp = output.with_name(output.name + ".tmp")
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        os.replace(tmp, output)

        row = summaries[source.name]
        row.graphic_merges_removed = cleanup.removed_merge_count
        row.rmu_rects_lowered = cleanup.lowered_rect_count
        total_removed += cleanup.removed_merge_count
        total_lowered += cleanup.lowered_rect_count
        log(
            f"[吉达批处理/图形组合清理] {source.name}：原 Merge {cleanup.previous_merge_count} 个，"
            f"删除 {cleanup.removed_merge_count} 个，剩余 {cleanup.remaining_merge_count} 个；"
            f"识别 RMU 外框 {cleanup.rmu_rect_count} 个，置底 {cleanup.lowered_rect_count} 个。"
        )
        if progress:
            progress(round(index * 100 / count))

    return total_removed, total_lowered

def _copy_or_delete_small_elements(
    files: list[Path],
    output_dir: Path,
    *,
    threshold: int,
    summaries: dict[str, _FileSummary],
    log: LogCallback,
    progress: ProgressCallback | None,
) -> tuple[int, int, list]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_issues = []
    total_removed = 0
    total_keyid = 0
    count = max(1, len(files))

    for index, source in enumerate(files, 1):
        issues = scan_file(source, threshold)
        all_issues.extend(issues)
        total_removed += len(issues)
        keyed = sum(1 for item in issues if item.keyid)
        total_keyid += keyed
        row = summaries[source.name]
        row.abnormal_removed = len(issues)
        row.abnormal_with_keyid = keyed
        if issues:
            delete_issues_to_output(issues, output_dir)
        else:
            shutil.copy2(source, output_dir / source.name)
        log(
            f"[吉达批处理/异常小元素] {source.name}：发现并删除 {len(issues)} 个，"
            f"其中带 keyid {keyed} 个。"
        )
        if progress:
            progress(round(index * 100 / count))
    return total_removed, total_keyid, all_issues


def _write_batch_report(
    output_dir: Path,
    summaries: list[_FileSummary],
    *,
    threshold: int,
    graphic_merges_removed: int,
    rmu_rects_lowered: int,
    smart_changed: int,
    normal_frame_white_changed: int,
    smr_changed: int,
    smr_to_smart_replaced: int,
    smr_existing_smart_cleanup: int,
    smr_text_removed: int,
    smart_device_precheck_changed: int,
    cbreaker_smart_devref_changed: int,
    smart_device_postcheck_changed: int,
    redundant_connection_lines_removed: int,
    connection_lines_straightened: int,
    connection_devices_realigned: int,
    connection_endpoints_connected: int,
    connection_topology_links_repaired: int,
    busdis_blue_changed: int,
    bus_frames_removed: int,
    bus_titles_moved: int,
    feeder_titles_moved: int,
    ht_text_removed: int,
    channel_status_removed: int,
    duplicate_smart_removed: int,
    adjacent_measurement_pairs_removed: int,
    adjacent_measurement_texts_removed: int,
    ids_repaired: int,
    total_rmu_names_white: int,
    margin_adjusted: int,
    frames_added: int,
    margin_text: str,
    frame_template_name: str,
    server_standard_revision: str,
    warnings: list[str],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "jeddah-batch-report.csv"
    html_path = output_dir / "jeddah-batch-report.html"
    english = report_is_english()

    headers_en = [
        "File",
        "GraphicMergesRemoved",
        "RMURectsLowered",
        "AbnormalRemoved",
        "AbnormalWithKeyID",
        "RMUNamesFound",
        "RMUNameTextMatched",
        "RMUNameWhiteChanged",
        "NORMALRMUFrameWhiteChanged",
        "SMRToSMARTReplaced",
        "ExistingSMARTCleanupOnly",
        "SMRTextRemoved",
        "ExistingSMARTDeviceDevrefCorrected",
        "SMRConversionDeviceDevrefChanged",
        "PostSMRSMARTDeviceDevrefCorrected",
        "ProfileSMARTLBSChanged",
        "ProfileSMARTBreakerChanged",
        "ProfileSMARTGroundChanged",
        "ProfileNORMALLBSChanged",
        "ProfileNORMALBreakerChanged",
        "ProfileNORMALGroundChanged",
        "ProfileGeometryAdjusted",
        "RedundantConnectionLinesRemoved",
        "ConnectionLinesStraightened",
        "ConnectionDevicesRealigned",
        "ConnectionEndpointsConnected",
        "ConnectionTopologyLinksRepaired",
        "BusDisBlueChanged",
        "HTTextRemoved",
        "RMUChannelStatusRemoved",
        "DuplicateSMARTRemoved",
        "AdjacentMeasurementPairsRemoved",
        "AdjacentMeasurementTextsRemoved",
        "MarginAdjusted",
        "FrameAdded",
        "FinalOutput",
        "Result",
        "Notes",
    ]
    headers_zh = [
        "文件",
        "图形组合Merge删除",
        "RMU外框置底",
        "异常元素删除",
        "异常元素含KeyID",
        "识别RMU名称",
        "匹配RMU名称文字",
        "RMU名称改白",
        "非智能RMU外框刷白",
        "SMR替换SMART",
        "已有SMART仅清理SMR",
        "删除SMR文字",
        "已有SMART柜图元校正",
        "SMR转换阶段图元切换",
        "SMR转换后SMART图元复检校正",
        "Profile校正SMART LBS",
        "Profile校正SMART断路器",
        "Profile SMART接地刀闸不替换",
        "Profile校正普通LBS",
        "Profile校正普通断路器",
        "Profile普通接地刀闸不替换",
        "Profile几何原位调整",
        "重复贯穿连接线删除",
        "设备连接线正交修复",
        "正交修复设备对齐",
        "双Pin连接端点吸附",
        "设备拓扑引用补齐",
        "配网母线BusDis刷蓝",
        "删除H.T文字",
        "删除RMU红色状态点",
        "删除重复SMART文字",
        "删除相邻测量字符对",
        "删除相邻测量文字",
        "图形边距调整",
        "图框添加",
        "最终输出",
        "结果",
        "备注",
    ]
    headers = headers_en if english else headers_zh

    def values(row: _FileSummary) -> list[object]:
        return [
            row.file_name,
            row.graphic_merges_removed,
            row.rmu_rects_lowered,
            row.abnormal_removed,
            row.abnormal_with_keyid,
            row.rmu_names_found,
            row.rmu_name_text_matched,
            row.rmu_name_white_changed,
            row.normal_rmu_frame_white_changed,
            row.smr_to_smart_replaced,
            row.smr_existing_smart_cleanup,
            row.smr_text_removed,
            row.smart_device_precheck_changed,
            row.cbreaker_smart_devref_changed,
            row.smart_device_postcheck_changed,
            row.profile_smart_lbs_changed,
            row.profile_smart_breaker_changed,
            row.profile_smart_ground_changed,
            row.profile_normal_lbs_changed,
            row.profile_normal_breaker_changed,
            row.profile_normal_ground_changed,
            row.profile_geometry_adjusted,
            row.redundant_connection_lines_removed,
            row.connection_lines_straightened,
            row.connection_devices_realigned,
            row.connection_endpoints_connected,
            row.connection_topology_links_repaired,
            row.busdis_blue_changed,
            row.ht_text_removed,
            row.channel_status_removed,
            row.duplicate_smart_removed,
            row.adjacent_measurement_pairs_removed,
            row.adjacent_measurement_texts_removed,
            row.margin_adjusted,
            row.frame_added,
            row.final_output,
            row.result,
            row.notes,
        ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for row in summaries:
            writer.writerow(values(row))

    total_files = len(summaries)
    passed = sum(1 for row in summaries if row.result == "PASS")
    failed = total_files - passed
    abnormal_removed = sum(row.abnormal_removed for row in summaries)
    keyid_removed = sum(row.abnormal_with_keyid for row in summaries)

    if english:
        title = "Jeddah Graphics Batch Processing Report"
        summary = (
            f"Files: {total_files}; PASS: {passed}; Failed/Warning: {failed}; "
            f"Server standard revision: {html.escape(server_standard_revision or '-')} UTC; "
            f"Graphic Merge elements removed first: {graphic_merges_removed}; RMU frames sent to back: {rmu_rects_lowered}; "
            f"Abnormal elements removed: {abnormal_removed} (with keyid: {keyid_removed}); "
            f"SMART frames changed to red: {smart_changed}; NORMAL RMU frames changed to white: {normal_frame_white_changed}; "
            f"SMR frames changed to red: {smr_changed}; "
            f"SMR labels replaced with SMART: {smr_to_smart_replaced}; "
            f"SMR cabinets already containing SMART (SMR removed only): {smr_existing_smart_cleanup}; "
            f"SMR texts removed: {smr_text_removed}; existing-SMART device devrefs corrected: {smart_device_precheck_changed}; "
            f"SMR-conversion device devrefs changed: {cbreaker_smart_devref_changed}; post-SMR SMART device devrefs corrected: {smart_device_postcheck_changed}; "
            f"standalone connection/topology normalization: not executed (all counters 0); "
            f"distribution BusDis changed to blue: {busdis_blue_changed}; "
            f"RMU name texts changed to white: {total_rmu_names_white}; "
            f"Bus frames removed: {bus_frames_removed}; corresponding titles moved: {bus_titles_moved}; "
            f"feeder titles moved above bus: {feeder_titles_moved}; "
            f"H.T texts removed: {ht_text_removed}; RMU channel_status red points removed: {channel_status_removed}; "
            f"duplicate SMART texts removed: {duplicate_smart_removed}; "
            f"adjacent 2000.00 + UPDATED_MEASURMENT pairs removed: {adjacent_measurement_pairs_removed} "
            f"({adjacent_measurement_texts_removed} Text elements); IDs repaired: {ids_repaired}; drawing margins adjusted: {margin_adjusted}; "
            f"drawing frames added: {frames_added}; margins: {html.escape(margin_text)}; "
            f"frame template: {html.escape(frame_template_name)}; "
            f"small-element threshold: w &lt; {threshold} and h &lt; {threshold}."
        )
        warning_title = "Batch Warnings"
        no_warnings = "None"
    else:
        title = "吉达图形批处理报告"
        summary = (
            f"文件：{total_files}；通过：{passed}；失败/告警：{failed}；"
            f"服务器标准版本：{html.escape(server_standard_revision or '-')} UTC；"
            f"第一步删除图形组合 Merge：{graphic_merges_removed}；RMU 外框置底：{rmu_rects_lowered}；"
            f"删除异常小尺寸图元：{abnormal_removed}（其中带 keyid：{keyid_removed}）；"
            f"SMART 外框刷红：{smart_changed}；非智能 RMU 外框刷白：{normal_frame_white_changed}；SMR 外框刷红：{smr_changed}；"
            f"SMR 替换 SMART：{smr_to_smart_replaced}；已有 SMART 仅清理 SMR：{smr_existing_smart_cleanup}；"
            f"删除 SMR 文字：{smr_text_removed}；已有 SMART 柜图元校正：{smart_device_precheck_changed}；"
            f"SMR 转换阶段图元切换：{cbreaker_smart_devref_changed}；SMR 转换后 SMART 图元复检校正：{smart_device_postcheck_changed}；"
            f"独立线路/拓扑/连接规范化：未执行（重复贯穿线、双 Pin 吸附、拓扑引用、正交修复、设备对齐均为 0）；"
            f"配网母线 BusDis 刷蓝：{busdis_blue_changed}；"
            f"RMU 名称文字改白：{total_rmu_names_white}；"
            f"删除带 Bus 外框：{bus_frames_removed}；对应标题上移：{bus_titles_moved}；"
            f"馈线名称移到母线上方：{feeder_titles_moved}；"
            f"删除 H.T 文字：{ht_text_removed}；删除 RMU 红色状态点：{channel_status_removed}；"
            f"删除重复 SMART 文字：{duplicate_smart_removed}；"
            f"删除相邻 2000.00 + UPDATED_MEASURMENT 字符对：{adjacent_measurement_pairs_removed} 对（{adjacent_measurement_texts_removed} 个 Text）；"
            f"修复 ID：{ids_repaired}；图形边距调整：{margin_adjusted}；"
            f"图框添加：{frames_added}；边距：{html.escape(margin_text)}；"
            f"图框模板：{html.escape(frame_template_name)}；"
            f"异常元素阈值：w &lt; {threshold} 且 h &lt; {threshold}。"
        )
        warning_title = "批处理告警"
        no_warnings = "无"

    body = []
    for row in summaries:
        css = "pass" if row.result == "PASS" else "warn"
        body.append(
            f"<tr class='{css}'>"
            + "".join(f"<td>{html.escape(str(value))}</td>" for value in values(row))
            + "</tr>"
        )
    warning_html = (
        "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in warnings) + "</ul>"
        if warnings
        else f"<p>{no_warnings}</p>"
    )
    html_path.write_text(
        f"<!doctype html><html lang='{'en' if english else 'zh-CN'}'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>"
        "body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:24px;color:#1f2937}"
        ".summary{padding:12px;background:#f3f7f5;border-left:4px solid #12815f;margin:12px 0 18px}"
        "table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d1d5db;padding:7px 8px;text-align:left}"
        "th{background:#e8f3ef}.pass td{background:#edf9f2}.warn td{background:#fff7d6}"
        "</style></head><body>"
        f"<h2>{html.escape(title)}</h2><div class='summary'>{summary}</div>"
        "<table><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead>"
        "<tbody>" + "".join(body) + "</tbody></table>"
        f"<h3>{html.escape(warning_title)}</h3>{warning_html}</body></html>",
        encoding="utf-8",
    )
    return csv_path, html_path


def process_jeddah_batch(
    settings: JeddahBatchSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
) -> ProcessingResult:
    """Run the Jeddah-only fixed feeder cleanup workflow.

    This function is an orchestrator. It reuses the existing small-element, RMU-enhancement,
    feeder-title, ID, margin-adjustment and drawing-frame implementations without modifying
    them. Jeddah-only styling remains isolated in this module.
    """

    if settings.small_element_threshold <= 0:
        raise ValueError("异常小尺寸阈值必须大于 0。")
    # Jeddah RMU detection and name matching both use the shared fixed resolver:
    # valid frame + BusDis/CBreakerDis/ZhaiWaiJieDiDaoZha + nearest top Text.
    if min(settings.margin_left, settings.margin_top, settings.margin_right, settings.margin_bottom) < 0:
        raise ValueError("吉达批处理的图形边距不能小于 0。")
    if settings.frame_template_file is None or not Path(settings.frame_template_file).is_file():
        raise FileNotFoundError(f"吉达批处理图框模板不存在：{settings.frame_template_file}")

    files = discover_g_inputs(settings.source_path, settings.input_mode)
    if not files:
        raise ValueError("没有找到可处理的 G 文件。")

    overall_started = time.perf_counter()
    stage_timings: dict[str, float] = {}

    output_root = Path(settings.output_dir)
    stage_root = output_root / "_stages"
    stage_ungroup = stage_root / "01_graphic_merge_cleanup"
    stage_small = stage_root / "02_small_elements"
    stage_white = stage_root / "03_rmu_name_white"
    stage_visual = stage_root / "04_jeddah_visual"
    stage_id = stage_root / "05_id"
    stage_margin = stage_root / "06_margin"
    final_dir = output_root / "final"
    report_dir = output_root / "reports"
    for path in (stage_ungroup, stage_small, stage_visual, stage_id, stage_margin, final_dir, report_dir):
        path.mkdir(parents=True, exist_ok=True)

    summaries = {path.name: _FileSummary(path.name) for path in files}
    warnings: list[str] = []
    timestamp = make_task_timestamp()

    log(f"[吉达批处理] 开始处理 {len(files)} 个单馈线 G 文件。")
    log(
        "[吉达批处理] 固定流程：彻底取消图形组合（删除全部 <Merge>，RMU 外框置底） → 删除异常小尺寸元素 → RMU 名称改白 → "
        "SMART/SMR 外框刷红 + SMR 强制转换为 SMART + 无 SMART 的 RMU 外框强制白色 + 按原图元名称识别 Circuit_Breaker/Load_Breaker_Switch，并严格按四个本地分类标记统一 SMART/NO-SMART 目标 + SMR 转换后再次检查 SMART 图元 + "
        "GLOBAL 图元标准化 + 重复贯穿连接线清理 + 单连接点设备连接线正交修复 + "
        "删除带 Bus 外框并上移标题 + "
        "馈线名称上移 + 删除 H.T 文字 + 删除 RMU channel_status 红色状态点 + 清理 RMU 内重复 SMART + "
        "删除相邻 2000.00 / UPDATED_MEASURMENT 字符对 → ID 检查与修复 → 图形边距调整 → 图框添加。"
    )
    log("[吉达批处理] RMU 柜名识别：严格检查框内三类组成，并只从外框上方按一对一规则匹配。")
    log(f"[吉达批处理] RMU 名称排除字符串：{settings.rmu_name_exclusions or '(无)'}")

    # Stage 1: reuse Basic Processing > Graphic Group Processing unchanged.
    # This MUST run before abnormal-small-element deletion so grouped RMU contents are
    # released first and RMU rects are sent behind devices exactly as in Basic Processing.
    stage_started = time.perf_counter()
    ungroup_progress = _scale_progress(progress, 0, 10)
    graphic_merges_removed, rmu_rects_lowered = _remove_all_graphic_merges_first(
        files,
        stage_ungroup,
        name_exclusions=settings.rmu_name_exclusions,
        summaries=summaries,
        log=log,
        progress=ungroup_progress,
    )
    stage_timings["graphic_merge_cleanup_seconds"] = time.perf_counter() - stage_started
    log(
        f"[吉达批处理] 图形组合清理阶段完成：删除 Merge {graphic_merges_removed} 个，"
        f"RMU 外框置底 {rmu_rects_lowered} 个；耗时 {stage_timings['graphic_merge_cleanup_seconds']:.1f}s。"
    )

    # Stage 2: use the existing small-element scan/delete engine unchanged.
    stage_started = time.perf_counter()
    ungrouped_files = discover_g_inputs(stage_ungroup, InputMode.DIRECTORY)
    small_progress = _scale_progress(progress, 10, 26)
    total_removed, total_keyid, all_issues = _copy_or_delete_small_elements(
        ungrouped_files,
        stage_small,
        threshold=settings.small_element_threshold,
        summaries=summaries,
        log=log,
        progress=small_progress,
    )
    processed_keys = {
        (str(item.file_path), item.element_type, item.ordinal, item.xml_id)
        for item in all_issues
    }
    small_report_dir = report_dir / "small-elements"
    small_csv, small_html = write_reports(
        small_report_dir,
        all_issues,
        settings.small_element_threshold,
        timestamp,
        report_kind="process",
        processed_keys=processed_keys,
    )
    stage_timings["small_element_seconds"] = time.perf_counter() - stage_started
    log(
        f"[吉达批处理] 异常元素阶段完成：删除 {total_removed} 个，其中带 keyid {total_keyid} 个；"
        f"耗时 {stage_timings['small_element_seconds']:.1f}s。"
    )

    # Stage 3/4 performance path: keep the existing Jeddah name-standard and visual
    # business rules, but execute both against the same parsed XML tree.  The old
    # implementation wrote a full intermediate G file after the name-only pass,
    # then immediately parsed that file again for visual processing.  For hundreds
    # of feeder files that extra round-trip dominates disk/CPU time without adding
    # any business value.  Standalone RMU-name processing remains unchanged.
    white_total = 0
    white_matched = 0
    white_named = 0

    # Stage 4: reuse the exact existing RMU-enhancement and feeder-title engines.
    # This Jeddah module only orchestrates them; their algorithms remain untouched.
    smart_matched = 0
    smart_changed = 0
    normal_frame_white_changed = 0
    normal_frame_scanned_rmus = 0
    smr_texts = 0
    smr_matched = 0
    smr_changed = 0
    smr_to_smart_replaced = 0
    smr_existing_smart_cleanup = 0
    smr_text_removed = 0
    smart_device_precheck_changed = 0
    cbreaker_smart_devref_changed = 0
    smart_device_postcheck_changed = 0
    profile_smart_lbs_changed = 0
    profile_smart_breaker_changed = 0
    profile_smart_ground_changed = 0
    profile_normal_lbs_changed = 0
    profile_normal_breaker_changed = 0
    profile_normal_ground_changed = 0
    profile_geometry_adjusted = 0
    redundant_connection_lines_removed = 0
    connection_lines_straightened = 0
    connection_devices_realigned = 0
    connection_endpoints_connected = 0
    connection_topology_links_repaired = 0
    busdis_blue_changed = 0
    smr_to_smart_frame_red_changed = 0
    bus_frames_removed = 0
    bus_titles_moved = 0
    feeder_titles_moved = 0
    ht_text_removed = 0
    channel_status_removed = 0
    channel_status_matched = 0
    channel_status_scanned_rmus = 0
    duplicate_smart_removed = 0
    duplicate_smart_rmus = 0
    duplicate_smart_scanned_rmus = 0
    adjacent_measurement_pairs_removed = 0
    adjacent_measurement_texts_removed = 0
    visual_failures: list[str] = []
    active_rmu_profile = None
    active_rmu_roles: dict[str, str] = {}
    profile_geometry_templates: dict[str, list[dict[str, object]]] = {}
    profile_standard_devrefs: set[str] = set()
    active_standard_label = ""

    if settings.server_standard_records:
        # Normal/public workflow. The synchronized server cache is already the
        # authoritative standard catalog; no hidden Profile/global-selection state
        # is required and no SSH call is made during batch execution.
        active_rmu_roles, marker_issues = resolve_jeddah_classification_marker_roles(
            settings.classification_marker_entries
        )
        warnings.extend(f"吉达图元分类标记：{item}" for item in marker_issues)
        profile_geometry_templates = geometry_templates_from_server_records(
            list(settings.server_standard_records)
        )
        profile_standard_devrefs = set(
            standard_catalog_from_server_records(list(settings.server_standard_records))
        )
        standard_keys = {value.casefold() for value in profile_standard_devrefs}
        for role_key in ("smart_lbs", "smart_breaker", "normal_lbs", "normal_breaker"):
            target = str(active_rmu_roles.get(role_key, "") or "").strip()
            if target and target.casefold() not in standard_keys:
                warnings.append(
                    f"吉达图元分类标记 {role_key} 指向 {target}，但该图元不在本机已同步服务器图元缓存中。"
                )
                active_rmu_roles[role_key] = ""
        active_standard_label = "LOCAL_SYNC_CACHE"
        log(
            f"[吉达批处理/图元标准] 使用本机已同步服务器图元缓存：{len(profile_standard_devrefs)} 个标准图元；"
            "目标图元只使用本地已保存四个分类标记；运行阶段不访问 SSH；设备类型以原图元 devref/文件名中的 "
            "Circuit_Breaker 或 Load_Breaker_Switch 为准，Y/Q 名称不覆盖；"
            "柜内 SMART 文字只决定 SMART/NO-SMART 目标；ZhaiWaiJieDiDaoZha 接地刀闸不替换。"
        )
    elif settings.rmu_profile_name.strip():
        # Backward-compatible API path for older callers/tests that still pass a
        # persisted SiteProfile explicitly. The UI no longer depends on this path.
        active_rmu_profile = SiteProfileService().get_profile_version(
            settings.rmu_profile_name.strip(), settings.rmu_profile_version
        )
        if active_rmu_profile is None:
            warnings.append(
                f"吉达批处理所选全局图元标准不存在：{settings.rmu_profile_name} "
                f"V{settings.rmu_profile_version or '-'}"
            )
        else:
            if settings.classification_marker_entries:
                active_rmu_roles, marker_issues = resolve_jeddah_classification_marker_roles(
                    settings.classification_marker_entries
                )
                warnings.extend(f"吉达图元分类标记：{item}" for item in marker_issues)
            else:
                active_rmu_roles = resolve_jeddah_role_devrefs(active_rmu_profile)
            profile_geometry_templates = (
                authoritative_geometry_templates(active_rmu_profile)
                if active_rmu_profile.managed_standard_files
                else active_rmu_profile.geometry_templates
            )
            profile_standard_devrefs = set(
                authoritative_standard_catalog(active_rmu_profile)
                if active_rmu_profile.managed_standard_files
                else profile_geometry_templates
            )
            if settings.classification_marker_entries:
                standard_keys = {value.casefold() for value in profile_standard_devrefs}
                for role_key in ("smart_lbs", "smart_breaker", "normal_lbs", "normal_breaker"):
                    target = str(active_rmu_roles.get(role_key, "") or "").strip()
                    if target and target.casefold() not in standard_keys:
                        warnings.append(
                            f"吉达图元分类标记 {role_key} 指向 {target}，但该图元不在当前已应用服务器标准中。"
                        )
                        active_rmu_roles[role_key] = ""
            active_standard_label = active_rmu_profile.server_standard_label
            log(
                f"[吉达批处理/图元标准] 使用兼容 Profile：{active_rmu_profile.site_name} / "
                f"{active_rmu_profile.profile_name} / 服务器版本 {active_rmu_profile.server_standard_label} UTC；"
                "目标图元优先使用本地已保存四个分类标记。"
            )
    stage_started = time.perf_counter()
    stage3_files = discover_g_inputs(stage_small, InputMode.DIRECTORY)
    parsed_name_exclusions = parse_name_exclusions(settings.rmu_name_exclusions)
    for index, source in enumerate(stage3_files, 1):
        try:
            tree = ET.parse(source)
            # One authoritative pre-conversion RMU identification is shared by the
            # name standardization, SMART audit, validated-frame set and SMR lookup.
            # This preserves the exact existing recognition algorithm while avoiding
            # repeated full-drawing scans for the same unchanged tree state.
            identification = identify_rmus(
                tree,
                source,
                name_positions=("top",),
                name_resolution_mode="selected_direction",
                smart_in_type=True,
                excluded_name_values=parsed_name_exclusions,
            )
            name_standard = apply_jeddah_rmu_name_standard_to_tree(
                tree,
                source,
                name_exclusions=settings.rmu_name_exclusions,
                font_size=50,
                top_gap=10,
                identification=identification,
            )
            row = summaries[source.name]
            row.rmu_names_found = name_standard.named_rmu_count
            row.rmu_name_text_matched = name_standard.matched_name_text_count
            row.rmu_name_white_changed = name_standard.changed_name_text_count
            white_total += name_standard.changed_name_text_count
            white_matched += name_standard.matched_name_text_count
            white_named += name_standard.named_rmu_count
            warnings.extend(name_standard.warnings)
            log(
                f"[吉达批处理/RMU名称白色] {source.name}：识别柜名 {name_standard.named_rmu_count} 个，"
                f"匹配名称 Text {name_standard.matched_name_text_count} 个，改为白色 {name_standard.changed_name_text_count} 个。"
            )
            validated_rmu_rect_ids = {
                item.rect_id for item in identification.items if item.rect_id
            }
            # Function 1 (Jeddah): every RMU that already contains SMART must use
            # the SMART LBS/Circuit-Breaker devrefs. This is independent from SMR conversion.
            smart_device_precheck = ensure_jeddah_smart_rmu_devices(
                tree, source, identification=identification
            )
            enhancement = enhance_rmu_tree(
                tree,
                source,
                change_smart_frame_color=False,
                smart_frame_color=JEDDAH_RED,
                change_smr_frame_color=True,
                smr_frame_color=JEDDAH_RED,
                reposition_channel_status=False,
                remove_bus_frame_and_reposition_title=True,
                validated_rmu_rect_ids=validated_rmu_rect_ids,
            )
            smr_replacement = replace_jeddah_smr_with_smart(
                tree, source, identification=identification
            )
            # SMR conversion can change the cabinet marker state. Recompute exactly
            # once after that mutation and share the result across every subsequent
            # read-only RMU ownership/audit pass in this file.
            post_identification = identify_rmus(
                tree,
                source,
                name_positions=("top", "bottom", "left", "right"),
                smart_in_type=True,
            )
            # Function 2 (Jeddah): after SMR handling, check SMART RMUs again so
            # a newly-created SMART cabinet cannot retain NON-SMART device devrefs.
            smart_device_postcheck = ensure_jeddah_smart_rmu_devices(
                tree, source, identification=post_identification
            )
            # Final RMU symbol standardization uses the user-confirmed ACTIVE Site
            # RMU Device Profile.  In Jeddah, SMR has already been mandatory-
            # converted to SMART.  A visible SMART marker (or an unconverted SMR
            # marker as a safety fallback) selects the confirmed SMART targets;
            # only CBreakerDis is eligible.  Ground disconnectors are deliberately
            # excluded and retain their original symbol and geometry.
            profile_consistency = None
            required_rmu_targets_ready = all(
                str(active_rmu_roles.get(key, "") or "").strip()
                for key in ("smart_lbs", "smart_breaker", "normal_lbs", "normal_breaker")
            )
            if required_rmu_targets_ready and profile_standard_devrefs:
                profile_consistency = apply_smart_profile_to_tree(
                    tree,
                    source,
                    identification=post_identification,
                    smart_lbs_devref=active_rmu_roles["smart_lbs"],
                    smart_breaker_devref=active_rmu_roles["smart_breaker"],
                    normal_lbs_devref=active_rmu_roles["normal_lbs"],
                    normal_breaker_devref=active_rmu_roles["normal_breaker"],
                    # Ground-disconnector role bindings are legacy metadata only;
                    # this pass intentionally never replaces ZhaiWaiJieDiDaoZha.
                    smart_ground_devref="",
                    normal_ground_devref="",
                    profile_geometry_templates=profile_geometry_templates,
                    authoritative_standard_devrefs=profile_standard_devrefs,
                    allow_source_geometry_fallback=False,
                    jeddah_variant_only=True,
                    jeddah_strict_marker_targets=bool(settings.classification_marker_entries),
                )
            elif settings.classification_marker_entries:
                warnings.append(
                    f"{source.name}: 吉达四个 SMART/NO-SMART 分类目标不完整，本文件仅执行其他吉达步骤，未替换 LBS/Circuit Breaker 图元。"
                )
            connection_cleanup = None
            busdis_blue = apply_jeddah_busdis_blue(tree, source)
            feeder_titles = move_feeder_titles_above_buses(tree, source)
            ht_cleanup = remove_jeddah_ht_texts(tree, source)
            channel_status_cleanup = remove_jeddah_channel_status_points(
                tree, source, identification=post_identification
            )
            duplicate_smart_cleanup = remove_duplicate_smart_labels_in_rmus(
                tree, source, identification=post_identification
            )
            measurement_cleanup = remove_jeddah_adjacent_measurement_texts(tree, source)
            # Final Jeddah RMU frame-color consistency.  SMR conversion has already
            # completed, so a recognized cabinet with no in-frame SMART Text is
            # definitively NORMAL for this batch and must be white.  SMART cabinets
            # are then forced red with the exact same center-inside ownership rule.
            normal_frame_audit = ensure_jeddah_normal_rmu_frames_white(
                tree, source, identification=post_identification
            )
            smart_frame_audit = ensure_jeddah_smart_rmu_frames_red(
                tree, source, identification=post_identification
            )

            output = stage_visual / source.name
            # Stage 5 immediately reparses this output for ID normalization. Keep the
            # intermediate XML compact and atomic; skip redundant pretty-print + self-parse.
            tmp = output.with_name(output.name + ".tmp")
            tree.write(tmp, encoding="utf-8", xml_declaration=True)
            os.replace(tmp, output)

            smart_matched += smart_frame_audit.smart_rmu_count
            smart_changed += smart_frame_audit.frame_red_changed_count
            normal_frame_white_changed += normal_frame_audit.frame_white_changed_count
            normal_frame_scanned_rmus += normal_frame_audit.normal_rmu_count
            summaries[source.name].normal_rmu_frame_white_changed = normal_frame_audit.frame_white_changed_count
            smr_texts += enhancement.smr_text_count
            smr_matched += enhancement.smr_matched_rect_count
            smr_changed += enhancement.smr_frame_color_changed
            smr_to_smart_replaced += smr_replacement.replaced_count
            smr_existing_smart_cleanup += smr_replacement.existing_smart_cleanup_count
            smr_text_removed += smr_replacement.smr_text_removed_count
            smart_device_precheck_changed += smart_device_precheck.cbreaker_smart_devref_changed_count
            cbreaker_smart_devref_changed += smr_replacement.cbreaker_smart_devref_changed_count
            smart_device_postcheck_changed += smart_device_postcheck.cbreaker_smart_devref_changed_count
            smr_to_smart_frame_red_changed += smr_replacement.frame_red_changed_count
            summaries[source.name].smr_to_smart_replaced = smr_replacement.replaced_count
            summaries[source.name].smr_existing_smart_cleanup = smr_replacement.existing_smart_cleanup_count
            summaries[source.name].smr_text_removed = smr_replacement.smr_text_removed_count
            summaries[source.name].smart_device_precheck_changed = smart_device_precheck.cbreaker_smart_devref_changed_count
            summaries[source.name].cbreaker_smart_devref_changed = smr_replacement.cbreaker_smart_devref_changed_count
            summaries[source.name].smart_device_postcheck_changed = smart_device_postcheck.cbreaker_smart_devref_changed_count
            if profile_consistency is not None:
                profile_smart_lbs_changed += profile_consistency.lbs_changed_count
                profile_smart_breaker_changed += profile_consistency.breaker_changed_count
                profile_smart_ground_changed += profile_consistency.ground_changed_count
                profile_normal_lbs_changed += profile_consistency.normal_lbs_changed_count
                profile_normal_breaker_changed += profile_consistency.normal_breaker_changed_count
                profile_normal_ground_changed += profile_consistency.normal_ground_changed_count
                profile_geometry_adjusted += profile_consistency.geometry_adjusted_count
                row = summaries[source.name]
                row.profile_smart_lbs_changed = profile_consistency.lbs_changed_count
                row.profile_smart_breaker_changed = profile_consistency.breaker_changed_count
                row.profile_smart_ground_changed = profile_consistency.ground_changed_count
                row.profile_normal_lbs_changed = profile_consistency.normal_lbs_changed_count
                row.profile_normal_breaker_changed = profile_consistency.normal_breaker_changed_count
                row.profile_normal_ground_changed = profile_consistency.normal_ground_changed_count
                row.profile_geometry_adjusted = profile_consistency.geometry_adjusted_count
                for warning in profile_consistency.warnings:
                    warnings.append(f"{source.name}: {warning}")
            if connection_cleanup is not None:
                redundant_connection_lines_removed += connection_cleanup.removed_redundant_lines
                connection_lines_straightened += connection_cleanup.straightened_lines
                connection_devices_realigned += connection_cleanup.moved_devices
                row = summaries[source.name]
                row.redundant_connection_lines_removed = connection_cleanup.removed_redundant_lines
                row.connection_lines_straightened = connection_cleanup.straightened_lines
                row.connection_devices_realigned = connection_cleanup.moved_devices
            bus_frames_removed += enhancement.bus_rect_removed
            bus_titles_moved += enhancement.bus_title_moved
            busdis_blue_changed += busdis_blue.changed_count
            summaries[source.name].busdis_blue_changed = busdis_blue.changed_count
            feeder_titles_moved += feeder_titles.moved_count
            ht_text_removed += ht_cleanup.removed_count
            summaries[source.name].ht_text_removed = ht_cleanup.removed_count
            channel_status_removed += channel_status_cleanup.removed_status_count
            channel_status_matched += channel_status_cleanup.matched_status_count
            channel_status_scanned_rmus += channel_status_cleanup.scanned_rmu_count
            summaries[source.name].channel_status_removed = channel_status_cleanup.removed_status_count
            duplicate_smart_removed += duplicate_smart_cleanup.smart_text_removed_count
            duplicate_smart_rmus += duplicate_smart_cleanup.duplicate_rmu_count
            duplicate_smart_scanned_rmus += duplicate_smart_cleanup.scanned_rmu_count
            summaries[source.name].duplicate_smart_removed = duplicate_smart_cleanup.smart_text_removed_count
            adjacent_measurement_pairs_removed += measurement_cleanup.adjacent_pair_count
            adjacent_measurement_texts_removed += measurement_cleanup.removed_text_count
            summaries[source.name].adjacent_measurement_pairs_removed = measurement_cleanup.adjacent_pair_count
            summaries[source.name].adjacent_measurement_texts_removed = measurement_cleanup.removed_text_count
            for warning in enhancement.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in smart_device_precheck.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in smr_replacement.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in smart_device_postcheck.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in normal_frame_audit.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in smart_frame_audit.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in feeder_titles.warnings:
                warnings.append(f"{source.name}: {warning}")
            for warning in duplicate_smart_cleanup.warnings:
                warnings.append(f"{source.name}: {warning}")
            profile_text = ""
            if profile_consistency is not None:
                profile_text = (
                    f"图元标准变体校验：SMART LBS {profile_consistency.lbs_changed_count}、SMART Q {profile_consistency.breaker_changed_count}、SMART 接地刀闸不替换；"
                    f"NORMAL LBS {profile_consistency.normal_lbs_changed_count}、NORMAL Q {profile_consistency.normal_breaker_changed_count}、NORMAL 接地刀闸不替换；"
                    f"服务器缺失图元 {profile_consistency.missing_standard_count}（仅告警）；"
                    f"几何原位升级 {profile_consistency.geometry_adjusted_count}；"
                )
            connection_text = ""
            if connection_cleanup is not None:
                connection_text = (
                    f"连接规范化：重复贯穿线删除 {connection_cleanup.removed_redundant_lines}、"
                    f"双 Pin 端点吸附 {connection_cleanup.connected_endpoints}、拓扑引用补齐 {connection_cleanup.repaired_topology_links}、"
                    f"单 Pin 正交修复 {connection_cleanup.straightened_lines}、设备同步对齐 {connection_cleanup.moved_devices}；"
                )
            log(
                f"[吉达批处理/图面处理] {source.name}：SMART 匹配 {enhancement.smart_rmu_rect_count}、最终刷红 {smart_frame_audit.frame_red_changed_count}；"
                f"无 SMART 的 NORMAL RMU {normal_frame_audit.normal_rmu_count} 个、外框刷白 {normal_frame_audit.frame_white_changed_count}；"
                f"SMR Text {enhancement.smr_text_count}、匹配 {enhancement.smr_matched_rect_count}、刷红 {enhancement.smr_frame_color_changed}；"
                f"已有 SMART 柜图元预检查：SMART 柜 {smart_device_precheck.smart_rmu_count}、校正 devref {smart_device_precheck.cbreaker_smart_devref_changed_count}；"
                f"SMR→SMART 新生成 {smr_replacement.replaced_count}；已有 SMART 清理 SMR {smr_replacement.existing_smart_cleanup_count}；"
                f"删除 SMR Text {smr_replacement.smr_text_removed_count}；SMR 转换阶段切 SMART 图元 {smr_replacement.cbreaker_smart_devref_changed_count}；"
                f"SMR 后复检：SMART 柜 {smart_device_postcheck.smart_rmu_count}、校正 devref {smart_device_postcheck.cbreaker_smart_devref_changed_count}；"
                f"{profile_text}"
                f"{connection_text}"
                f"删除带 Bus 外框 {enhancement.bus_rect_removed}、对应标题上移 {enhancement.bus_title_moved}；"
                f"配网 BusDis 刷蓝 {busdis_blue.changed_count}/{busdis_blue.eligible_count}（无关联 keyid 兜底 {busdis_blue.keyid_fallback_count}）；"
                f"馈线名称上移 {feeder_titles.moved_count}；删除 H.T 文字 {ht_cleanup.removed_count}；"
                f"删除 RMU 红色状态点 {channel_status_cleanup.removed_status_count}/{channel_status_cleanup.matched_status_count} 个；"
                f"扫描 RMU {duplicate_smart_cleanup.scanned_rmu_count} 个、重复 SMART 柜 {duplicate_smart_cleanup.duplicate_rmu_count} 个、删除重复 SMART {duplicate_smart_cleanup.smart_text_removed_count} 个；"
                f"删除相邻 2000.00 + UPDATED_MEASURMENT {measurement_cleanup.adjacent_pair_count} 对（{measurement_cleanup.removed_text_count} 个 Text）。"
            )
        except Exception as exc:
            message = f"{source.name}: {exc}"
            visual_failures.append(message)
            warnings.append(message)
            summaries[source.name].result = "WARNING/FAILED"
            summaries[source.name].notes = str(exc)
            log(f"[吉达批处理/图面处理失败] {message}")
        if progress:
            progress(26 + round(index * 36 / max(1, len(stage3_files))))

    stage_timings["jeddah_visual_seconds"] = time.perf_counter() - stage_started
    log(
        f"[吉达批处理] RMU 名称 + 吉达图面处理阶段完成：{len(stage3_files)} 个 G 文件；"
        f"耗时 {stage_timings['jeddah_visual_seconds']:.1f}s。"
    )

    if not list(stage_visual.glob("*.g")):
        raise RuntimeError("吉达图面处理阶段没有生成可继续执行 ID 检查的 G 文件。")

    # Stage 5: ID check & repair uses the existing ID processor/global ID rules unchanged.
    stage_started = time.perf_counter()
    id_settings = IdSettings(
        source_path=stage_visual,
        input_mode=InputMode.DIRECTORY,
        output_dir=stage_id,
        action=IdAction.REPAIR,
        output_conflict_action=BasicOutputConflictAction.OVERWRITE,
        task_timestamp=timestamp,
    )
    id_result = process_ids(
        id_settings,
        log=log,
        progress=_scale_progress(progress, 62, 75),
    )
    warnings.extend(id_result.warnings)
    id_new_type_count = int(id_result.statistics.get("new_id_type_count", 0) or 0)
    if id_new_type_count:
        warnings.append(
            f"ID 检查发现 {id_new_type_count} 个元素类型尚未配置已确认模板；这些类型未擅自生成或改写 ID，请在 ID 检查与修复模块确认规则。"
        )
    ids_repaired = int(id_result.statistics.get("repaired_id_count", 0) or 0)
    stage_timings["id_repair_seconds"] = time.perf_counter() - stage_started
    log(f"[吉达批处理/ID] 阶段耗时 {stage_timings['id_repair_seconds']:.1f}s。")

    # Stage 6: reuse Drawing Margin Adjustment, but Jeddah is an explicit
    # replacement workflow: any detected pre-existing frame is removed first so
    # it cannot block body-margin calculation.  Stage 7 adds the selected frame.
    stage_started = time.perf_counter()
    margin_settings = MarginSettings(
        source_path=stage_id,
        input_mode=InputMode.DIRECTORY,
        output_dir=stage_margin,
        left_margin=settings.margin_left,
        top_margin=settings.margin_top,
        right_margin=settings.margin_right,
        bottom_margin=settings.margin_bottom,
        preserve_existing_frame=True,
        force_remove_existing_frame=True,
        output_suffix="",
        append_timestamp=False,
        task_timestamp=timestamp,
        overwrite=True,
    )
    margin_result = adjust_graph_margins(
        margin_settings,
        log=log,
        progress=_scale_progress(progress, 75, 88),
        # Stage 5 has just normalized every configured ID. Margin adjustment only
        # moves/removes geometry and creates no new XML IDs, so a second full-file
        # ID parse/normalization here is redundant. Frame addition still performs
        # the normal ID enforcement after it adds template elements.
        enforce_id_rules=False,
    )
    warnings.extend(margin_result.warnings)
    margin_names = {Path(path).name for path in margin_result.output_files}
    for name in margin_names:
        if name in summaries:
            summaries[name].margin_adjusted = 1
    stage_timings["margin_seconds"] = time.perf_counter() - stage_started
    log(
        f"[吉达批处理/图形边距] 完成 {len(margin_result.output_files)} 个 G 文件；"
        f"左={settings.margin_left}、上={settings.margin_top}、右={settings.margin_right}、下={settings.margin_bottom}；"
        f"耗时 {stage_timings['margin_seconds']:.1f}s。"
    )

    # Stage 7: Drawing Frame treats the current template selection as authoritative
    # and replaces any frame that may still be present instead of appending it.
    stage_started = time.perf_counter()
    frame_settings = FrameSettings(
        source_path=stage_margin,
        input_mode=InputMode.DIRECTORY,
        output_dir=final_dir,
        template_file=Path(settings.frame_template_file),
        template_mode=settings.frame_template_mode,
        builtin_template_id=settings.frame_builtin_template_id,
        title="",
        draw=PersonSettings(),
        approve=PersonSettings(),
        issue=PersonSettings(),
        frame_left=50,
        frame_top=50,
        frame_right=50,
        frame_bottom=50,
        output_suffix="",
        append_timestamp=False,
        task_timestamp=timestamp,
        overwrite=True,
    )
    frame_result = add_drawing_frames(
        frame_settings,
        log=log,
        progress=_scale_progress(progress, 88, 98),
    )
    warnings.extend(frame_result.warnings)
    frame_names = {Path(path).name for path in frame_result.output_files}
    for name in frame_names:
        if name in summaries:
            summaries[name].frame_added = 1
    stage_timings["frame_seconds"] = time.perf_counter() - stage_started
    log(
        f"[吉达批处理/图框添加] 完成 {len(frame_result.output_files)} 个 G 文件；"
        f"模板={Path(settings.frame_template_file).name}；耗时 {stage_timings['frame_seconds']:.1f}s。"
    )

    final_g_files = sorted(final_dir.glob("*.g"), key=lambda path: path.name.casefold())
    final_names = {path.name for path in final_g_files}
    warning_by_name: dict[str, list[str]] = {}
    for warning in warnings:
        prefix = str(warning).split(":", 1)[0].strip()
        warning_by_name.setdefault(prefix, []).append(str(warning))
    for row in summaries.values():
        if row.file_name in final_names:
            row.final_output = str(final_dir / row.file_name)
        else:
            row.result = "WARNING/FAILED"
        per_file = warning_by_name.get(row.file_name, [])
        if per_file:
            row.result = "WARNING/FAILED"
            row.notes = " | ".join(per_file)

    margin_text = (
        f"L={settings.margin_left}, T={settings.margin_top}, "
        f"R={settings.margin_right}, B={settings.margin_bottom}"
    )
    batch_csv, batch_html = _write_batch_report(
        report_dir,
        list(summaries.values()),
        threshold=settings.small_element_threshold,
        graphic_merges_removed=graphic_merges_removed,
        rmu_rects_lowered=rmu_rects_lowered,
        smart_changed=smart_changed,
        normal_frame_white_changed=normal_frame_white_changed,
        smr_changed=smr_changed,
        smr_to_smart_replaced=smr_to_smart_replaced,
        smr_existing_smart_cleanup=smr_existing_smart_cleanup,
        smr_text_removed=smr_text_removed,
        smart_device_precheck_changed=smart_device_precheck_changed,
        cbreaker_smart_devref_changed=cbreaker_smart_devref_changed,
        smart_device_postcheck_changed=smart_device_postcheck_changed,
        redundant_connection_lines_removed=redundant_connection_lines_removed,
        connection_lines_straightened=connection_lines_straightened,
        connection_devices_realigned=connection_devices_realigned,
        connection_endpoints_connected=connection_endpoints_connected,
        connection_topology_links_repaired=connection_topology_links_repaired,
        busdis_blue_changed=busdis_blue_changed,
        bus_frames_removed=bus_frames_removed,
        bus_titles_moved=bus_titles_moved,
        feeder_titles_moved=feeder_titles_moved,
        ht_text_removed=ht_text_removed,
        channel_status_removed=channel_status_removed,
        duplicate_smart_removed=duplicate_smart_removed,
        adjacent_measurement_pairs_removed=adjacent_measurement_pairs_removed,
        adjacent_measurement_texts_removed=adjacent_measurement_texts_removed,
        ids_repaired=ids_repaired,
        total_rmu_names_white=white_total,
        margin_adjusted=len(margin_result.output_files),
        frames_added=len(frame_result.output_files),
        margin_text=margin_text,
        frame_template_name=Path(settings.frame_template_file).name,
        server_standard_revision=active_standard_label,
        warnings=warnings,
    )

    stage_timings["total_seconds"] = time.perf_counter() - overall_started
    if progress:
        progress(100)
    log(
        f"[吉达批处理] 完成：最终 G 文件 {len(final_g_files)}/{len(files)} 个；"
        f"服务器标准来源 {active_standard_label or '-'}；"
        f"删除 Merge {graphic_merges_removed}；RMU 外框置底 {rmu_rects_lowered}；"
        f"异常元素删除 {total_removed}；SMART 外框刷红 {smart_changed}；非智能 RMU 外框刷白 {normal_frame_white_changed}；SMR 外框刷红 {smr_changed}；"
        f"SMR 新生成 SMART {smr_to_smart_replaced}；已有 SMART 仅删 SMR {smr_existing_smart_cleanup}；"
        f"删除 SMR Text {smr_text_removed}；已有 SMART 柜图元校正 {smart_device_precheck_changed}；"
        f"SMR 转换阶段图元切换 {cbreaker_smart_devref_changed}；SMR 后复检图元校正 {smart_device_postcheck_changed}；"
        f"Profile 图元变体校验：SMART LBS {profile_smart_lbs_changed}、SMART Q {profile_smart_breaker_changed}、SMART 接地不替换、"
        f"NORMAL LBS {profile_normal_lbs_changed}、NORMAL Q {profile_normal_breaker_changed}、NORMAL 接地不替换、几何原位调整 {profile_geometry_adjusted}；"
        f"独立线路/拓扑/连接规范化：未执行（重复贯穿线、双 Pin 吸附、拓扑引用、正交修复、设备对齐均为 0）；"
        f"配网母线 BusDis 刷蓝 {busdis_blue_changed}；"
        f"RMU 名称改白 {white_total}；带 Bus 外框删除 {bus_frames_removed}；"
        f"对应标题上移 {bus_titles_moved}；馈线名称上移 {feeder_titles_moved}；"
        f"删除 H.T 文字 {ht_text_removed}；"
        f"删除 RMU 红色状态点 {channel_status_removed}/{channel_status_matched} 个（扫描 BusDis RMU {channel_status_scanned_rmus} 个）；"
        f"扫描 RMU {duplicate_smart_scanned_rmus} 个、重复 SMART 柜 {duplicate_smart_rmus} 个、删除重复 SMART {duplicate_smart_removed} 个；"
        f"删除相邻测量字符对 {adjacent_measurement_pairs_removed} 对（{adjacent_measurement_texts_removed} 个 Text）；ID 修复 {ids_repaired}；"
        f"边距调整 {len(margin_result.output_files)}；图框添加 {len(frame_result.output_files)}。"
    )
    log(
        f"[吉达批处理/性能] 总耗时 {stage_timings['total_seconds']:.1f}s；"
        f"组合清理 {stage_timings.get('graphic_merge_cleanup_seconds', 0):.1f}s；"
        f"异常元素 {stage_timings.get('small_element_seconds', 0):.1f}s；"
        f"RMU/图面 {stage_timings.get('jeddah_visual_seconds', 0):.1f}s；"
        f"ID {stage_timings.get('id_repair_seconds', 0):.1f}s；"
        f"边距 {stage_timings.get('margin_seconds', 0):.1f}s；"
        f"图框 {stage_timings.get('frame_seconds', 0):.1f}s。"
    )
    log(f"[吉达批处理] 最终输出目录：{final_dir}")
    log(f"[吉达批处理] 汇总报告：{batch_html}")

    output_files = [*final_g_files, batch_csv, batch_html, small_csv, small_html]
    id_csv = stage_id / "id-repair-report.csv"
    id_html = stage_id / "id-repair-report.html"
    for report in (id_csv, id_html):
        if report.exists() and report not in output_files:
            output_files.append(report)

    return ProcessingResult(
        success=(
            len(final_g_files) == len(files)
            and len(margin_result.output_files) == len(files)
            and len(frame_result.output_files) == len(files)
            and not visual_failures
            and not id_result.warnings
            and id_new_type_count == 0
        ),
        output_files=output_files,
        warnings=warnings,
        statistics={
            "site_profile": "JEDDAH",
            "input_file_count": len(files),
            "final_file_count": len(final_g_files),
            "graphic_merge_removed_count": graphic_merges_removed,
            "graphic_merge_rmu_rect_lowered_count": rmu_rects_lowered,
            "small_element_removed_count": total_removed,
            "small_element_keyid_count": total_keyid,
            "rmu_named_count": white_named,
            "rmu_name_text_matched_count": white_matched,
            "rmu_name_white_changed_count": white_total,
            "smart_rmu_matched_count": smart_matched,
            "smart_rmu_frame_red_changed_count": smart_changed,
            "normal_rmu_count": normal_frame_scanned_rmus,
            "normal_rmu_frame_white_changed_count": normal_frame_white_changed,
            "smr_text_count": smr_texts,
            "smr_matched_rmu_count": smr_matched,
            "smr_rmu_frame_red_changed_count": smr_changed,
            "smr_to_smart_replaced_count": smr_to_smart_replaced,
            "smr_existing_smart_cleanup_count": smr_existing_smart_cleanup,
            "smr_text_removed_count": smr_text_removed,
            "smart_device_precheck_changed_count": smart_device_precheck_changed,
            "smr_conversion_device_devref_changed_count": cbreaker_smart_devref_changed,
            "smart_device_postcheck_changed_count": smart_device_postcheck_changed,
            "rmu_profile_name": active_rmu_profile.profile_name if active_rmu_profile else "",
            "rmu_profile_version": active_rmu_profile.profile_version if active_rmu_profile else 0,
            "rmu_server_standard_revision": active_standard_label,
            "profile_smart_lbs_changed_count": profile_smart_lbs_changed,
            "profile_smart_breaker_changed_count": profile_smart_breaker_changed,
            "profile_smart_ground_changed_count": profile_smart_ground_changed,
            "profile_normal_lbs_changed_count": profile_normal_lbs_changed,
            "profile_normal_breaker_changed_count": profile_normal_breaker_changed,
            "profile_normal_ground_changed_count": profile_normal_ground_changed,
            "profile_geometry_adjusted_count": profile_geometry_adjusted,
            "redundant_connection_line_removed_count": redundant_connection_lines_removed,
            "connection_line_straightened_count": connection_lines_straightened,
            "connection_device_realigned_count": connection_devices_realigned,
            "connection_endpoint_connected_count": connection_endpoints_connected,
            "connection_topology_link_repaired_count": connection_topology_links_repaired,
            "busdis_blue_changed_count": busdis_blue_changed,
            "smr_to_smart_frame_red_changed_count": smr_to_smart_frame_red_changed,
            "bus_rmu_frame_removed_count": bus_frames_removed,
            "bus_rmu_title_moved_count": bus_titles_moved,
            "feeder_title_moved_count": feeder_titles_moved,
            "ht_text_removed_count": ht_text_removed,
            "channel_status_scanned_rmu_count": channel_status_scanned_rmus,
            "channel_status_matched_count": channel_status_matched,
            "channel_status_removed_count": channel_status_removed,
            "duplicate_smart_scanned_rmu_count": duplicate_smart_scanned_rmus,
            "duplicate_smart_rmu_count": duplicate_smart_rmus,
            "duplicate_smart_removed_count": duplicate_smart_removed,
            "adjacent_measurement_pair_removed_count": adjacent_measurement_pairs_removed,
            "adjacent_measurement_text_removed_count": adjacent_measurement_texts_removed,
            "id_repaired_count": ids_repaired,
            "id_unconfigured_type_count": id_new_type_count,
            "margin_adjusted_file_count": len(margin_result.output_files),
            "margin_left": settings.margin_left,
            "margin_top": settings.margin_top,
            "margin_right": settings.margin_right,
            "margin_bottom": settings.margin_bottom,
            "drawing_frame_added_file_count": len(frame_result.output_files),
            "drawing_frame_template": str(settings.frame_template_file),
            **stage_timings,
            "final_output_dir": str(final_dir),
            "batch_report_html": str(batch_html),
            "batch_report_csv": str(batch_csv),
        },
    )
