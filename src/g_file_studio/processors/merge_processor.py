from __future__ import annotations

import contextlib
import shutil
from decimal import Decimal
from pathlib import Path

from g_file_studio.engines import merge_engine
from g_file_studio.models import FrameSettings, InputMode, MergeSettings, PersonSettings, ProcessingResult
from g_file_studio.processors.frame_processor import add_drawing_frames
from g_file_studio.processors.poke_processor import PokeProcessingSettings, process_pokes
from g_file_studio.services.database_service import OracleDatabaseService
from g_file_studio.processors.common import (
    CallbackWriter,
    LogCallback,
    ProgressCallback,
    redirect_safe_callback,
    enforce_confirmed_id_rules,
)
from g_file_studio.services.output_naming import (
    default_merge_output_path,
    make_task_timestamp,
)


def merge_feeders(
    settings: MergeSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
    *,
    database_service: OracleDatabaseService | None = None,
) -> ProcessingResult:
    """Merge feeders and optionally run the standard Poke/frame post-processors.

    The post-processing order is deliberately:

        feeder merge -> Poke -> drawing frame

    Poke runs before the drawing-frame template is appended so template Text and
    graphics can never become Poke recognition candidates.  When a frame is
    enabled afterwards, the existing frame processor moves the already-created
    Pokes together with the drawing, preserving their geometry.
    """
    if not settings.input_dir.is_dir():
        raise NotADirectoryError(f"输入目录不存在：{settings.input_dir}")
    settings.output_dir.mkdir(parents=True, exist_ok=True)

    log("正在加载并检查已导入的 G 文件……")
    if progress:
        progress(5)
    infos = merge_engine.discover_files(
        settings.input_dir,
        ordered_file_names=settings.ordered_file_names or None,
        allow_subset=bool(settings.ordered_file_names),
    )
    task_timestamp = make_task_timestamp()
    output_path = (
        settings.output_dir / settings.output_name
        if settings.output_name
        else default_merge_output_path(settings.output_dir, task_timestamp)
    )
    if settings.output_name:
        log(f"使用用户指定输出文件名：{output_path.name}")
    else:
        log(f"未填写输出文件名，自动生成：{output_path.name}")

    # Any post processor gets an isolated staging area.  This guarantees the
    # final workspace file appears only after all requested stages succeed.
    post_stage_dir: Path | None = None
    raw_output_path = output_path
    if settings.add_poke_after_merge or settings.add_frame_after_merge:
        post_stage_dir = settings.output_dir / f".merge-post-stage-{task_timestamp}"
        raw_dir = post_stage_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_output_path = raw_dir / output_path.name
        enabled_parts = []
        if settings.add_poke_after_merge:
            enabled_parts.append("Poke 跳转")
        if settings.add_frame_after_merge:
            enabled_parts.append("图框")
        log(
            "已启用合并后处理：" + " → ".join(enabled_parts) +
            "；先生成隔离的合并中间文件，全部后处理成功后再写入最终输出目录。"
        )

    if settings.add_frame_after_merge:
        if settings.frame_template_file is None or not Path(settings.frame_template_file).is_file():
            raise FileNotFoundError(f"馈线合并图框模板不存在：{settings.frame_template_file}")

    if settings.add_poke_after_merge and database_service is None:
        raise RuntimeError(
            "已勾选“合并完成后自动添加 Poke 跳转”，但未提供 Oracle 数据库服务。"
            "请从 G File Studio 的馈线图合并页面执行该功能。"
        )

    if progress:
        progress(10)
    writer = CallbackWriter(redirect_safe_callback(log))
    poke_result: ProcessingResult | None = None
    frame_added = 0
    poke_processed = 0
    poke_report_csv = ""
    poke_report_html = ""
    current_source = raw_output_path
    try:
        with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
            merge_engine.merge_g_files(
                infos=infos,
                output_path=raw_output_path,
                gap=Decimal(settings.feeder_gap),
                feeder_min_width=Decimal(settings.feeder_min_width),
                merge_main_bus=bool(settings.merge_main_bus),
                main_bus_mode=settings.main_bus_mode,
                main_bus_groups=settings.main_bus_groups,
                left_margin=Decimal(settings.left_margin),
                top_margin=Decimal(settings.top_margin),
                right_margin=Decimal(settings.right_margin),
                bottom_margin=Decimal(settings.bottom_margin),
            )
        writer.flush()
        enforce_confirmed_id_rules(raw_output_path, log)

        # Poke MUST precede frame insertion: only feeder graphics should take
        # part in RMU / AR-LBS-SEC / station Text recognition.
        if settings.add_poke_after_merge:
            assert post_stage_dir is not None
            assert database_service is not None
            if progress:
                progress(72)
            poke_dir = post_stage_dir / "poke"
            poke_dir.mkdir(parents=True, exist_ok=True)
            log(
                "[馈线图合并/自动Poke] 开始复用现有 Poke 跳转处理器："
                "RMU + AR/LBS/SEC + 站点跳转全部启用。"
            )
            poke_settings = PokeProcessingSettings(
                source_path=raw_output_path,
                input_mode=InputMode.SINGLE_FILE,
                output_dir=poke_dir,
                enable_rmu_poke=True,
                enable_classified_device_poke=True,
                enable_station_poke=True,
                rmu_name_positions=tuple(settings.poke_rmu_name_positions or ("top",)),
                rmu_name_exclusions=settings.poke_rmu_name_exclusions,
                rmu_intelligent_markers=settings.poke_rmu_intelligent_markers,
                classification_marker_entries=tuple(settings.poke_classification_marker_entries),
            )
            poke_end = 88 if settings.add_frame_after_merge else 96
            poke_result = process_pokes(
                poke_settings,
                database_service,
                log=log,
                progress=(
                    (lambda value: progress(72 + round(max(0, min(100, int(value))) * (poke_end - 72) / 100)))
                    if progress
                    else None
                ),
            )
            g_outputs = [Path(path) for path in poke_result.output_files if Path(path).suffix.lower() == ".g"]
            if not g_outputs:
                raise RuntimeError("馈线合并完成，但自动 Poke 跳转处理没有生成 G 文件。")
            current_source = next((path for path in g_outputs if path.name == output_path.name), g_outputs[0])
            poke_processed = 1
            poke_report_csv = str(poke_result.statistics.get("csv_report_path", "") or "")
            poke_report_html = str(poke_result.statistics.get("html_report_path", "") or "")

            # Reports belong to this merge run too.  Keep them in the managed
            # merge output directory even though the staging tree is deleted.
            for report_text in (poke_report_csv, poke_report_html):
                if not report_text:
                    continue
                report_path = Path(report_text)
                if report_path.is_file():
                    target = settings.output_dir / report_path.name
                    shutil.copy2(report_path, target)
                    if report_path.suffix.lower() == ".csv":
                        poke_report_csv = str(target)
                    elif report_path.suffix.lower() in {".html", ".htm"}:
                        poke_report_html = str(target)
            log(f"[馈线图合并/自动Poke] Poke 跳转处理完成：{current_source.name}")

        if settings.add_frame_after_merge:
            if progress:
                progress(90 if settings.add_poke_after_merge else 85)
            frame_settings = FrameSettings(
                source_path=current_source,
                input_mode=InputMode.SINGLE_FILE,
                output_dir=settings.output_dir,
                template_file=Path(settings.frame_template_file),
                template_mode=settings.frame_template_mode,
                builtin_template_id=settings.frame_builtin_template_id,
                title="",
                draw=PersonSettings(),
                approve=PersonSettings(),
                issue=PersonSettings(),
                frame_left=settings.frame_left,
                frame_top=settings.frame_top,
                frame_right=settings.frame_right,
                frame_bottom=settings.frame_bottom,
                output_suffix="",
                append_timestamp=False,
                task_timestamp=task_timestamp,
                overwrite=True,
            )
            frame_start = 90 if settings.add_poke_after_merge else 85
            frame_result = add_drawing_frames(
                frame_settings,
                log=log,
                progress=(
                    (lambda value: progress(frame_start + round(max(0, min(100, int(value))) * (100 - frame_start) / 100)))
                    if progress
                    else None
                ),
            )
            if not frame_result.output_files:
                raise RuntimeError("馈线合并完成，但自动图框添加没有生成最终 G 文件。")
            output_path = Path(frame_result.output_files[0])
            frame_added = 1
            log(f"[馈线图合并/自动图框] 已添加图框：{output_path.name}")
        elif settings.add_poke_after_merge:
            # Poke output is staged so it cannot expose a partial final result.
            shutil.copy2(current_source, output_path)
            enforce_confirmed_id_rules(output_path, log)
            if progress:
                progress(100)
        elif progress:
            progress(100)
    finally:
        writer.flush()
        if post_stage_dir is not None and post_stage_dir.exists():
            shutil.rmtree(post_stage_dir, ignore_errors=True)

    poke_stats = poke_result.statistics if poke_result is not None else {}
    return ProcessingResult(
        success=True,
        output_files=[output_path],
        warnings=(list(poke_result.warnings) if poke_result is not None else []),
        statistics={
            "input_count": len(infos),
            "input_order": [info.path.name for info in infos],
            "feeder_gap": settings.feeder_gap,
            "feeder_min_width": settings.feeder_min_width,
            "merge_main_bus": settings.merge_main_bus,
            "main_bus_mode": settings.main_bus_mode,
            "main_bus_groups": settings.main_bus_groups,
            "poke_processed": poke_processed,
            "poke_rmu_added": int(poke_stats.get("rmu_added", 0) or 0),
            "poke_rmu_updated": int(poke_stats.get("rmu_updated", 0) or 0),
            "poke_device_added": int(poke_stats.get("classified_device_added", 0) or 0),
            "poke_device_updated": int(poke_stats.get("classified_device_updated", 0) or 0),
            "poke_station_added": int(poke_stats.get("station_added", 0) or 0),
            "poke_station_updated": int(poke_stats.get("station_updated", 0) or 0),
            "poke_report_csv": poke_report_csv,
            "poke_report_html": poke_report_html,
            "frame_added": frame_added,
            "frame_template": str(settings.frame_template_file or ""),
            "output_file": str(output_path),
        },
    )
