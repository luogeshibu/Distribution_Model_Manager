from __future__ import annotations

from pathlib import Path

from g_file_studio.engines.margin_engine import adjust_one_file
from g_file_studio.models import MarginSettings, ProcessingResult
from g_file_studio.processors.common import LogCallback, ProgressCallback, discover_g_inputs, enforce_confirmed_id_rules


def adjust_graph_margins(
    settings: MarginSettings,
    log: LogCallback = print,
    progress: ProgressCallback | None = None,
    *,
    enforce_id_rules: bool = True,
) -> ProcessingResult:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    files = discover_g_inputs(settings.source_path, settings.input_mode)

    outputs: list[Path] = []
    files_with_frame: list[str] = []
    files_without_frame: list[str] = []
    for index, input_path in enumerate(files, 1):
        output_path = settings.output_dir / input_path.name
        try:
            same_as_input = output_path.resolve() == input_path.resolve()
        except OSError:
            same_as_input = output_path.absolute() == input_path.absolute()
        if same_as_input:
            raise ValueError(
                "图形边距调整保持源文件名不变，禁止覆盖原始 G 文件。请更换输出目录。"
            )
        if output_path.exists() and not settings.overwrite:
            raise FileExistsError(f"输出文件已存在且不允许覆盖：{output_path}")

        result = adjust_one_file(
            input_path,
            output_path,
            left_margin=settings.left_margin,
            top_margin=settings.top_margin,
            right_margin=settings.right_margin,
            bottom_margin=settings.bottom_margin,
            preserve_existing_frame=settings.preserve_existing_frame,
            force_remove_existing_frame=settings.force_remove_existing_frame,
        )
        if enforce_id_rules:
            enforce_confirmed_id_rules(output_path, log)
        outputs.append(output_path)
        removed_frame_count = int(getattr(result, "removed_existing_frame_count", 0) or 0)
        removed_frame_modes = tuple(getattr(result, "removed_existing_frame_modes", ()) or ())
        if removed_frame_count:
            files_with_frame.append(output_path.name)
            mode_text = ", ".join(removed_frame_modes) or "detected"
            frame_text = (
                f"；已按任务选择强制移除旧图框 {removed_frame_count} 个组件"
                f"（{mode_text}），后续由当前选择模板重新添加"
            )
        elif result.had_existing_frame:
            files_with_frame.append(output_path.name)
            frame_mode = (
                "身份标记" if result.frame_detection_mode == "marker"
                else "旧版内置模板指纹"
            )
            frame_text = (
                f"；已识别内置图框（{frame_mode}），保持边距 "
                f"左={result.frame_left_margin:g}、上={result.frame_top_margin:g}、"
                f"右={result.frame_right_margin:g}、下={result.frame_bottom_margin:g}"
            )
        else:
            files_without_frame.append(output_path.name)
            frame_text = "；未检测到完整外框"

        log(
            f"✓ {input_path.name}：画布 "
            f"{result.old_canvas_width}×{result.old_canvas_height} → "
            f"{result.new_canvas_width}×{result.new_canvas_height}；"
            f"主体边距 左={result.body_left_margin:g}、上={result.body_top_margin:g}、"
            f"右={result.body_right_margin:g}、下={result.body_bottom_margin:g}"
            f"{frame_text}"
        )
        if progress:
            progress(round(index * 100 / len(files)))

    return ProcessingResult(
        success=True,
        output_files=outputs,
        statistics={
            "input_mode": settings.input_mode.value,
            "source_path": str(settings.source_path),
            "file_count": len(outputs),
            "files_with_existing_frame": files_with_frame,
            "files_without_existing_frame": files_without_frame,
            "existing_frame_count": len(files_with_frame),
            "left_margin": settings.left_margin,
            "top_margin": settings.top_margin,
            "right_margin": settings.right_margin,
            "bottom_margin": settings.bottom_margin,
            "output_naming": "source_filename",
            "overwrite_existing": settings.overwrite,
        },
    )
