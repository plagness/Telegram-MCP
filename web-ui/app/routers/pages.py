"""API для управления веб-страницами (внутренний, через tgapi proxy)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..handlers.registry import get_handler, list_types as handler_list_types
from ..services import links as links_svc
from ..services import pages as pages_svc
from ..services.access import (
    get_accessible_pages,
    get_page_access_summary,
    grant_access,
    revoke_access,
)

router = APIRouter(prefix="/api/v1/pages", tags=["pages"])
logger = logging.getLogger(__name__)


class CreatePageIn(BaseModel):
    slug: str = Field(..., max_length=100)
    title: str = Field(..., max_length=200)
    page_type: str = Field("page", max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)
    template: str | None = None
    creator_id: int | None = None
    bot_id: int | None = None
    event_id: int | None = None
    expires_at: str | None = None


class CreateLinkIn(BaseModel):
    user_id: int | None = None
    chat_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    expires_at: str | None = None


class AccessGrantIn(BaseModel):
    grant_type: str = Field(..., pattern="^(user|role|chat)$")
    value: int | str


class AccessRulesIn(BaseModel):
    access_rules: dict[str, Any]


class ValidatePageIn(BaseModel):
    slug: str = Field(..., max_length=100)
    title: str = Field(..., max_length=200)
    page_type: str = Field("page", max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)


# ── Page Types (из handler registry) ─────────────────────────────────────


@router.get("/types")
async def get_page_types():
    """Список зарегистрированных page_types и их возможностей."""
    return {"ok": True, "types": handler_list_types()}


@router.get("/types/{page_type}/schema")
async def get_page_type_schema(page_type: str):
    """JSON Schema конфига для page_type."""
    handler = get_handler(page_type)
    if not handler:
        raise HTTPException(status_code=404, detail=f"Unknown page_type: {page_type}")
    return {"ok": True, "page_type": page_type, "schema": handler.get_config_schema()}


# ── CRUD страниц ─────────────────────────────────────────────────────────


@router.post("")
async def create_page(payload: CreatePageIn):
    """Создать веб-страницу."""
    handler = get_handler(payload.page_type)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown page_type: {payload.page_type}",
        )

    try:
        page = await pages_svc.create_page(
            slug=payload.slug,
            title=payload.title,
            page_type=payload.page_type,
            config=payload.config,
            template=payload.template,
            creator_id=payload.creator_id,
            bot_id=payload.bot_id,
            event_id=payload.event_id,
            expires_at=payload.expires_at,
        )
        return {"ok": True, "page": page}
    except Exception as e:
        logger.error("Ошибка создания страницы: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_pages(
    page_type: str | None = Query(None),
    bot_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список страниц."""
    pages = await pages_svc.list_pages(
        page_type=page_type, bot_id=bot_id, limit=limit, offset=offset
    )
    return {"ok": True, "pages": pages}


@router.get("/user/{user_id}/accessible")
async def get_user_accessible_pages(user_id: int):
    """Страницы, доступные пользователю."""
    pages = await get_accessible_pages(user_id)
    return {
        "ok": True,
        "user_id": user_id,
        "total": len(pages),
        "pages": [
            {
                "slug": p["slug"],
                "title": p["title"],
                "page_type": p["page_type"],
                "is_active": p.get("is_active", True),
            }
            for p in pages
        ],
    }


@router.post("/validate")
async def validate_page(payload: ValidatePageIn):
    """Валидировать конфиг страницы БЕЗ создания.

    Проверяет: page_type зарегистрирован, slug свободен, config валиден.
    """
    errors: list[str] = []

    handler = get_handler(payload.page_type)
    if not handler:
        errors.append(f"Unknown page_type: {payload.page_type}")

    existing = await pages_svc.get_page(payload.slug)
    if existing:
        errors.append(f"Slug '{payload.slug}' already exists")

    if not payload.slug or len(payload.slug) < 2:
        errors.append("Slug must be at least 2 characters")

    if not payload.title or len(payload.title) < 1:
        errors.append("Title is required")

    return {
        "ok": len(errors) == 0,
        "valid": len(errors) == 0,
        "errors": errors,
    }


@router.get("/{slug}")
async def get_page(slug: str):
    """Получить конфигурацию страницы."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"ok": True, "page": page}


@router.delete("/{slug}")
async def delete_page(slug: str):
    """Удалить страницу (деактивация)."""
    deleted = await pages_svc.delete_page(slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"ok": True}


# ── Access Management ─────────────────────────────────────────────────────


@router.get("/{slug}/access")
async def get_page_access(slug: str):
    """Текущие правила доступа + resolved summary."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    summary = await get_page_access_summary(page)
    return {"ok": True, "access": summary}


@router.put("/{slug}/access")
async def update_page_access(slug: str, payload: AccessRulesIn):
    """Обновить access_rules целиком."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    config = dict(page.get("config") or {})
    config["access_rules"] = payload.access_rules
    ok = await pages_svc.update_page_config(slug, config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update access rules")
    return {"ok": True}


@router.post("/{slug}/access/grant")
async def grant_page_access(slug: str, payload: AccessGrantIn):
    """Добавить правило доступа (user/role/chat)."""
    ok = await grant_access(slug, payload.grant_type, payload.value)
    if not ok:
        raise HTTPException(status_code=404, detail="Page not found or invalid grant_type")
    return {"ok": True}


@router.post("/{slug}/access/revoke")
async def revoke_page_access(slug: str, payload: AccessGrantIn):
    """Убрать правило доступа (user/role/chat)."""
    ok = await revoke_access(slug, payload.grant_type, payload.value)
    if not ok:
        raise HTTPException(status_code=404, detail="Page not found or invalid grant_type")
    return {"ok": True}


# ── Links & Submissions ──────────────────────────────────────────────────


@router.post("/{slug}/links")
async def create_link(slug: str, payload: CreateLinkIn):
    """Создать индивидуальную ссылку на страницу."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    link = await links_svc.create_link(
        page_id=page["id"],
        user_id=payload.user_id,
        chat_id=payload.chat_id,
        metadata=payload.metadata,
        expires_at=payload.expires_at,
    )
    return {"ok": True, "link": link}


@router.post("/backfill-emojis")
async def backfill_emojis():
    """Сгенерировать эмодзи для всех страниц без config.emojis."""
    from ..db import fetch_all
    from ..services.emoji_gen import generate_page_emojis

    rows = await fetch_all(
        "SELECT slug, title, page_type FROM web_pages "
        "WHERE is_active = TRUE "
        "ORDER BY created_at DESC",
        [],
    )
    results = {"total": len(rows), "updated": 0, "failed": 0}
    for row in rows:
        emojis = await generate_page_emojis(row["title"], row["page_type"])
        if emojis:
            await pages_svc.update_page_config(row["slug"], {"emojis": emojis})
            results["updated"] += 1
        else:
            results["failed"] += 1
        # Пауза между вызовами LLM
        import asyncio
        await asyncio.sleep(2)
    return {"ok": True, **results}


@router.get("/{slug}/submissions")
async def get_submissions(
    slug: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Ответы на форму страницы."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    from ..db import fetch_all
    submissions = await fetch_all(
        """
        SELECT s.*, l.token as link_token
        FROM web_form_submissions s
        LEFT JOIN web_page_links l ON s.link_id = l.id
        WHERE s.page_id = %s
        ORDER BY s.created_at DESC
        LIMIT %s OFFSET %s
        """,
        [page["id"], limit, offset],
    )
    return {"ok": True, "submissions": submissions}
