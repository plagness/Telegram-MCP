"""Эндпоинты статистики: активные пользователи, чаты, объём сообщений."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..db import fetch_all, fetch_one

router = APIRouter(prefix="/v1/stats", tags=["stats"])

_PERIOD_MAP = {
    "1d": "1 day",
    "7d": "7 days",
    "30d": "30 days",
    "all": "100 years",
}


def _interval(period: str) -> str:
    return _PERIOD_MAP.get(period, "7 days")


@router.get("/overview")
async def stats_overview(bot_id: int | None = Query(None)) -> dict[str, Any]:
    """Общая статистика: количество чатов, юзеров, сообщений."""
    chats_row = await fetch_one("SELECT COUNT(*) AS cnt FROM chats")
    users_row = await fetch_one("SELECT COUNT(*) AS cnt FROM users WHERE is_bot = FALSE")
    msgs_row = await fetch_one("SELECT COUNT(*) AS cnt FROM messages")
    inbound_row = await fetch_one("SELECT COUNT(*) AS cnt FROM messages WHERE direction = 'inbound'")
    outbound_row = await fetch_one("SELECT COUNT(*) AS cnt FROM messages WHERE direction = 'outbound'")
    updates_row = await fetch_one("SELECT COUNT(*) AS cnt FROM webhook_updates")

    return {
        "chats": chats_row["cnt"] if chats_row else 0,
        "users": users_row["cnt"] if users_row else 0,
        "messages_total": msgs_row["cnt"] if msgs_row else 0,
        "messages_inbound": inbound_row["cnt"] if inbound_row else 0,
        "messages_outbound": outbound_row["cnt"] if outbound_row else 0,
        "webhook_updates": updates_row["cnt"] if updates_row else 0,
    }


@router.get("/active-users")
async def most_active_users(
    chat_id: str | None = Query(None),
    period: str = Query("7d", regex="^(1d|7d|30d|all)$"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Самые активные пользователи по количеству сообщений."""
    interval = _interval(period)

    if chat_id:
        rows = await fetch_all(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   COUNT(*) AS message_count
            FROM messages m
            JOIN users u ON u.user_id = (m.payload_json->'from'->>'id')
            WHERE m.chat_id = %s
              AND m.direction = 'inbound'
              AND m.created_at > NOW() - %s::interval
            GROUP BY u.user_id, u.username, u.first_name, u.last_name
            ORDER BY message_count DESC
            LIMIT %s
            """,
            [chat_id, interval, limit],
        )
    else:
        rows = await fetch_all(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   u.message_count
            FROM users u
            WHERE u.is_bot = FALSE
              AND u.message_count > 0
            ORDER BY u.message_count DESC
            LIMIT %s
            """,
            [limit],
        )

    return {"users": rows, "count": len(rows), "period": period, "chat_id": chat_id}


@router.get("/active-chats")
async def most_active_chats(
    period: str = Query("7d", regex="^(1d|7d|30d|all)$"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Самые активные чаты по количеству входящих сообщений."""
    interval = _interval(period)

    rows = await fetch_all(
        """
        SELECT m.chat_id, c.title, c.type, c.username,
               COUNT(*) AS message_count
        FROM messages m
        LEFT JOIN chats c ON c.chat_id = m.chat_id
        WHERE m.direction = 'inbound'
          AND m.created_at > NOW() - %s::interval
        GROUP BY m.chat_id, c.title, c.type, c.username
        ORDER BY message_count DESC
        LIMIT %s
        """,
        [interval, limit],
    )

    return {"chats": rows, "count": len(rows), "period": period}


@router.get("/message-volume")
async def message_volume(
    chat_id: str | None = Query(None),
    period: str = Query("7d", regex="^(1d|7d|30d)$"),
    granularity: str = Query("1h", regex="^(1h|1d)$"),
) -> dict[str, Any]:
    """Объём сообщений по времени (для графиков/дашбордов)."""
    interval = _interval(period)
    trunc = "hour" if granularity == "1h" else "day"

    params: list[Any] = [interval]
    where_chat = ""
    if chat_id:
        where_chat = "AND m.chat_id = %s"
        params.append(chat_id)
    params.append(100 if granularity == "1h" else 31)

    rows = await fetch_all(
        f"""
        SELECT date_trunc('{trunc}', m.created_at) AS bucket,
               COUNT(*) FILTER (WHERE m.direction = 'inbound') AS inbound,
               COUNT(*) FILTER (WHERE m.direction = 'outbound') AS outbound,
               COUNT(*) AS total
        FROM messages m
        WHERE m.created_at > NOW() - %s::interval
          {where_chat}
        GROUP BY bucket
        ORDER BY bucket ASC
        LIMIT %s
        """,
        params,
    )

    return {"buckets": rows, "count": len(rows), "period": period, "granularity": granularity}


@router.get("/update-types")
async def update_type_distribution(
    period: str = Query("7d", regex="^(1d|7d|30d|all)$"),
) -> dict[str, Any]:
    """Распределение типов входящих обновлений."""
    interval = _interval(period)

    rows = await fetch_all(
        """
        SELECT update_type, COUNT(*) AS cnt
        FROM webhook_updates
        WHERE received_at > NOW() - %s::interval
        GROUP BY update_type
        ORDER BY cnt DESC
        """,
        [interval],
    )

    return {"types": rows, "count": len(rows), "period": period}
