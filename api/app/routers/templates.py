"""Эндпоинты для управления шаблонами Jinja2."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import TemplateCreateIn, TemplateRenderIn
from ..services import templates as template_service

router = APIRouter(prefix="/v1/templates", tags=["templates"])


@router.post("")
async def create_template_api(payload: TemplateCreateIn) -> dict[str, Any]:
    row = await template_service.upsert_template(
        name=payload.name,
        body=payload.body,
        parse_mode=payload.parse_mode,
        description=payload.description,
    )
    return {"template": row}


@router.get("")
async def list_templates_api() -> dict[str, Any]:
    rows = await template_service.list_templates()
    return {"items": rows, "count": len(rows)}


@router.get("/{name}")
async def get_template_api(name: str) -> dict[str, Any]:
    row = await template_service.get_template(name)
    if not row:
        raise HTTPException(status_code=404, detail="template not found")
    return {"template": row}


@router.post("/{name}/render")
async def render_template_api(name: str, payload: TemplateRenderIn) -> dict[str, Any]:
    try:
        rendered = await template_service.render_template(name, payload.variables or {})
    except KeyError:
        raise HTTPException(status_code=404, detail="template not found")
    return rendered


@router.post("/seed")
async def seed_templates_api() -> dict[str, Any]:
    rows = await template_service.seed_templates_from_files()
    return {"items": rows, "count": len(rows)}
