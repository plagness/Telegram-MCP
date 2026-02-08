"""Генерация и валидация индивидуальных ссылок."""

from __future__ import annotations

import secrets
from typing import Any

from ..config import get_settings
from ..db import execute, execute_returning, fetch_all, fetch_one


def _generate_token(length: int = 16) -> str:
    """Генерация URL-safe токена."""
    return secrets.token_urlsafe(length)


async def create_link(
    *,
    page_id: int,
    user_id: int | None = None,
    chat_id: int | None = None,
    metadata: dict | None = None,
    expires_at: str | None = None,
) -> dict:
    """Создать индивидуальную ссылку на страницу."""
    from psycopg.types.json import Json

    token = _generate_token()
    row = await execute_returning(
        """
        INSERT INTO web_page_links (page_id, token, user_id, chat_id, metadata, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [page_id, token, user_id, chat_id, Json(metadata or {}), expires_at],
    )

    settings = get_settings()
    row["url"] = f"{settings.public_url}/l/{token}"
    return row


async def get_link_by_token(token: str) -> dict[str, Any] | None:
    """Найти ссылку по токену."""
    return await fetch_one(
        """
        SELECT l.*, p.slug, p.page_type, p.is_active as page_active
        FROM web_page_links l
        JOIN web_pages p ON l.page_id = p.id
        WHERE l.token = %s
        """,
        [token],
    )


async def mark_used(link_id: int) -> None:
    """Пометить ссылку как использованную."""
    await execute(
        "UPDATE web_page_links SET used_at = now() WHERE id = %s",
        [link_id],
    )


async def get_page_links(
    page_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Список ссылок для страницы."""
    return await fetch_all(
        "SELECT * FROM web_page_links WHERE page_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s",
        [page_id, limit, offset],
    )
