"""Подключение к PostgreSQL для web-ui.

Использует ту же БД что и tgapi (shared schema).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from psycopg_pool import AsyncConnectionPool

from .config import get_settings

logger = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None


async def init_pool() -> None:
    """Инициализация пула соединений."""
    global _pool
    settings = get_settings()
    _pool = AsyncConnectionPool(
        conninfo=settings.db_dsn,
        min_size=2,
        max_size=10,
        kwargs={"autocommit": True},
    )
    await _pool.open()
    logger.info("DB pool opened: %s", settings.db_dsn.split("@")[-1])


async def close_pool() -> None:
    """Закрытие пула."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn():
    """Получить соединение из пула."""
    if not _pool:
        raise RuntimeError("DB pool not initialized")
    async with _pool.connection() as conn:
        yield conn


async def fetch_one(query: str, params: list | None = None) -> dict[str, Any] | None:
    """Выполнить запрос и вернуть одну строку как dict."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or [])
            row = await cur.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))


async def fetch_all(query: str, params: list | None = None) -> list[dict[str, Any]]:
    """Выполнить запрос и вернуть все строки как list[dict]."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or [])
            rows = await cur.fetchall()
            if not rows:
                return []
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in rows]


async def execute(query: str, params: list | None = None) -> None:
    """Выполнить запрос без возврата данных."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or [])


async def execute_returning(query: str, params: list | None = None) -> dict[str, Any]:
    """Выполнить INSERT/UPDATE RETURNING и вернуть строку."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or [])
            row = await cur.fetchone()
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))
