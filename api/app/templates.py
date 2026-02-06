from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import get_settings

_settings = get_settings()

_env = Environment(
    loader=FileSystemLoader(_settings.templates_dir),
    autoescape=select_autoescape(enabled_extensions=("html", "j2")),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_from_string(template_body: str, variables: dict[str, Any]) -> str:
    template = _env.from_string(template_body)
    return template.render(**(variables or {}))


def render_from_file(template_name: str, variables: dict[str, Any]) -> str:
    template = _env.get_template(template_name)
    return template.render(**(variables or {}))


def list_template_files() -> list[str]:
    root = Path(_settings.templates_dir)
    if not root.exists():
        return []
    return sorted([p.name for p in root.glob("*.j2")])


def read_template_file(template_name: str) -> str:
    root = Path(_settings.templates_dir)
    path = root / template_name
    return path.read_text(encoding="utf-8")
