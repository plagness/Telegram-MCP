from __future__ import annotations

from typing import Any, Iterable

from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

from .config import get_settings

_settings = get_settings()

pool = AsyncConnectionPool(
    conninfo=_settings.db_dsn,
    min_size=1,
    max_size=5,
    open=False,
)


async def init_pool() -> None:
    if not pool.opened:
        await pool.open()


async def close_pool() -> None:
    if pool.opened:
        await pool.close()


async def fetch_one(query: str, params: Iterable[Any] | None = None) -> dict | None:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or [])
            return await cur.fetchone()


async def fetch_all(query: str, params: Iterable[Any] | None = None) -> list[dict]:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or [])
            rows = await cur.fetchall()
            return list(rows)


async def execute(query: str, params: Iterable[Any] | None = None) -> None:
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or [])
            await conn.commit()


async def execute_returning(query: str, params: Iterable[Any] | None = None) -> dict | None:
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or [])
            row = await cur.fetchone()
            await conn.commit()
            return row
