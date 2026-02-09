"""API для управления веб-страницами (внутренний, через tgapi proxy)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import links as links_svc
from ..services import pages as pages_svc

router = APIRouter(prefix="/api/v1/pages", tags=["pages"])
logger = logging.getLogger(__name__)


class CreatePageIn(BaseModel):
    slug: str = Field(..., max_length=100)
    title: str = Field(..., max_length=200)
    page_type: str = Field("page", pattern="^(page|survey|prediction|dashboard|leaderboard|calendar)$")
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


@router.post("")
async def create_page(payload: CreatePageIn):
    """Создать веб-страницу."""
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
