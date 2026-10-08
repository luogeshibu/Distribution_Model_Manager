from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from g_file_studio.services.paths import resource_root


@dataclass(frozen=True)
class BuiltinTemplate:
    template_id: str
    name: str
    version: str
    file_name: str
    editable_content: bool
    description: str
    path: Path


class TemplateServiceError(RuntimeError):
    pass


def template_resource_dir() -> Path:
    return resource_root() / "resources" / "templates"


def template_manifest_path() -> Path:
    return template_resource_dir() / "templates.json"


def load_builtin_templates() -> tuple[str, list[BuiltinTemplate]]:
    manifest = template_manifest_path()
    if not manifest.is_file():
        raise TemplateServiceError(f"找不到内置模板清单：{manifest}")

    try:
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TemplateServiceError(f"内置模板清单读取失败：{exc}") from exc

    default_id = str(data.get("default_template_id", "")).strip()
    raw_templates = data.get("templates", [])
    if not isinstance(raw_templates, list) or not raw_templates:
        raise TemplateServiceError("内置模板清单中没有 templates。")

    result: list[BuiltinTemplate] = []
    for index, item in enumerate(raw_templates, 1):
        if not isinstance(item, dict):
            raise TemplateServiceError(f"templates[{index}] 必须是对象。")
        template_id = str(item.get("id", "")).strip()
        file_name = str(item.get("file", "")).strip()
        if not template_id or not file_name:
            raise TemplateServiceError(f"templates[{index}] 缺少 id 或 file。")
        path = template_resource_dir() / file_name
        if not path.is_file():
            raise TemplateServiceError(f"内置模板文件不存在：{path}")
        result.append(
            BuiltinTemplate(
                template_id=template_id,
                name=str(item.get("name", template_id)),
                version=str(item.get("version", "1.0.0")),
                file_name=file_name,
                editable_content=bool(item.get("editable_content", True)),
                description=str(item.get("description", "")),
                path=path,
            )
        )

    if not default_id:
        default_id = result[0].template_id
    if default_id not in {item.template_id for item in result}:
        raise TemplateServiceError(f"默认内置模板 ID 不存在：{default_id}")
    return default_id, result


def get_builtin_template(template_id: str | None = None) -> BuiltinTemplate:
    default_id, templates = load_builtin_templates()
    selected = template_id or default_id
    for item in templates:
        if item.template_id == selected:
            return item
    raise TemplateServiceError(f"找不到内置模板：{selected}")


def export_builtin_template(template_id: str, destination: Path) -> Path:
    template = get_builtin_template(template_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template.path, destination)
    return destination
