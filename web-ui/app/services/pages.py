"""CRUD для веб-страниц (web_pages)."""

from __future__ import annotations

import secrets
from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one


async def create_page(
    *,
    slug: str,
    title: str,
    page_type: str = "page",
    config: dict | None = None,
    template: str | None = None,
    creator_id: int | None = None,
    bot_id: int | None = None,
    event_id: int | None = None,
    expires_at: str | None = None,
) -> dict:
    """Создать новую страницу."""
    from psycopg.types.json import Json

    return await execute_returning(
        """
        INSERT INTO web_pages (slug, page_type, title, config, template,
                               creator_id, bot_id, event_id, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [slug, page_type, title, Json(config or {}), template,
         creator_id, bot_id, event_id, expires_at],
    )


async def get_page(slug: str) -> dict[str, Any] | None:
    """Получить страницу по slug."""
    return await fetch_one(
        "SELECT * FROM web_pages WHERE slug = %s AND is_active = TRUE", [slug]
    )


async def list_pages(
    *,
    page_type: str | None = None,
    bot_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Список страниц с фильтрацией."""
    conditions = ["is_active = TRUE"]
    params: list[Any] = []

    if page_type:
        conditions.append("page_type = %s")
        params.append(page_type)
    if bot_id is not None:
        conditions.append("bot_id = %s")
        params.append(bot_id)

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    return await fetch_all(
        f"SELECT * FROM web_pages WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params,
    )


async def delete_page(slug: str) -> bool:
    """Деактивировать страницу (soft delete)."""
    page = await get_page(slug)
    if not page:
        return False
    await execute(
        "UPDATE web_pages SET is_active = FALSE, updated_at = now() WHERE slug = %s",
        [slug],
    )
    return True
