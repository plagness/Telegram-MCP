"""Сервис данных чата для Integrat-плагина telegram-chat-data.

Предоставляет агрегированные данные:
- Метаданные чата (info)
- Участники (members)
- Сообщения с фильтрацией (messages)
- Реакции (reactions)
- Системные события (events)
- Статистика (stats)

payload_json не отдаётся наружу — только парсенные поля.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from ..db import fetch_all, fetch_one

logger = logging.getLogger(__name__)


async def get_chat_info(chat_id: str) -> dict[str, Any] | None:
    """Метаданные чата с подсчётом известных участников и админов."""
    chat = await fetch_one(
        """
        SELECT c.chat_id, c.type, c.title, c.username, c.description,
               c.member_count, c.photo_file_id, c.is_forum, c.invite_link,
               c.hub_description, c.hub_links,
               c.created_at, c.updated_at,
               a.local_path AS avatar_local_path
        FROM chats c
        LEFT JOIN avatars a ON a.entity_type = 'chat' AND a.entity_id = c.chat_id
        WHERE c.chat_id = %s
        """,
        [str(chat_id)],
    )
    if not chat:
        return None

    counts = await fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE status NOT IN ('left', 'kicked')) AS known_members_count,
            COUNT(*) FILTER (WHERE status IN ('administrator', 'creator')) AS admins_count
        FROM chat_members
        WHERE chat_id = %s
        """,
        [str(chat_id)],
    )

    messages_count = await fetch_one(
        "SELECT COUNT(*) AS total FROM messages WHERE chat_id = %s AND direction = 'inbound'",
        [str(chat_id)],
    )

    return {
        **dict(chat),
        "avatar_url": chat.get("avatar_local_path") or None,
        "known_members_count": counts["known_members_count"] if counts else 0,
        "admins_count": counts["admins_count"] if counts else 0,
        "messages_count": messages_count["total"] if messages_count else 0,
    }


async def get_chat_members(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Участники чата с профилями и аватарками."""
    where = ["cm.chat_id = %s"]
    values: list[Any] = [str(chat_id)]

    if status:
        where.append("cm.status = %s")
        values.append(status)
    else:
        where.append("cm.status NOT IN ('left', 'kicked')")

    if search:
        where.append("(u.username ILIKE %s OR u.first_name ILIKE %s OR u.last_name ILIKE %s)")
        pattern = f"%{search}%"
        values.extend([pattern, pattern, pattern])

    where_sql = " AND ".join(where)

    total_row = await fetch_one(
        f"SELECT COUNT(*) AS total FROM chat_members cm LEFT JOIN users u ON u.user_id = cm.user_id WHERE {where_sql}",
        values,
    )

    rows = await fetch_all(
        f"""
        SELECT cm.user_id, cm.status, cm.last_seen_at, cm.metadata,
               u.username, u.first_name, u.last_name, u.is_premium,
               u.language_code,
               a.local_path AS avatar_local_path
        FROM chat_members cm
        LEFT JOIN users u ON u.user_id = cm.user_id
        LEFT JOIN avatars a ON a.entity_type = 'user' AND a.entity_id = cm.user_id
        WHERE {where_sql}
        ORDER BY cm.last_seen_at DESC NULLS LAST
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )

    items = []
    for r in rows:
        item = dict(r)
        item["avatar_url"] = item.pop("avatar_local_path", None)
        items.append(item)

    return {
        "items": items,
        "total": total_row["total"] if total_row else 0,
        "limit": limit,
        "offset": offset,
    }


async def get_chat_messages(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    date_from: str | None = None,
    date_to: str | None = None,
    user_id: str | None = None,
    media_type: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Сообщения чата с фильтрацией. Без payload_json."""
    where = ["m.chat_id = %s", "m.direction = 'inbound'"]
    values: list[Any] = [str(chat_id)]

    if date_from:
        where.append("m.created_at >= %s")
        values.append(date_from)
    if date_to:
        where.append("m.created_at <= %s")
        values.append(date_to)
    if user_id:
        where.append("""
            EXISTS (
                SELECT 1 FROM webhook_updates wu
                WHERE wu.chat_id = m.chat_id
                  AND wu.message_id = m.telegram_message_id
                  AND wu.user_id = %s
            )
        """)
        values.append(str(user_id))
    if media_type:
        where.append("m.media_type = %s")
        values.append(media_type)
    if search:
        where.append("(m.text ILIKE %s OR m.caption ILIKE %s)")
        pattern = f"%{search}%"
        values.extend([pattern, pattern])

    where_sql = " AND ".join(where)

    total_row = await fetch_one(
        f"SELECT COUNT(*) AS total FROM messages m WHERE {where_sql}",
        values,
    )

    rows = await fetch_all(
        f"""
        SELECT m.id, m.telegram_message_id, m.text, m.media_type, m.caption,
               m.has_media, m.forward_origin, m.entities, m.is_topic_message,
               m.sender_chat_id, m.status, m.created_at,
               wu.user_id,
               u.first_name, u.last_name, u.username
        FROM messages m
        LEFT JOIN LATERAL (
            SELECT wu.user_id FROM webhook_updates wu
            WHERE wu.chat_id = m.chat_id
              AND wu.message_id = m.telegram_message_id
            LIMIT 1
        ) wu ON TRUE
        LEFT JOIN users u ON u.user_id = wu.user_id
        WHERE {where_sql}
        ORDER BY m.created_at DESC
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )

    return {
        "items": [dict(r) for r in rows],
        "total": total_row["total"] if total_row else 0,
        "limit": limit,
        "offset": offset,
    }


async def get_chat_reactions(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    telegram_message_id: int | None = None,
    user_id: str | None = None,
    aggregate: bool = True,
) -> dict[str, Any]:
    """Реакции чата с опциональной агрегацией."""
    where = ["mr.chat_id = %s"]
    values: list[Any] = [str(chat_id)]

    if telegram_message_id:
        where.append("mr.telegram_message_id = %s")
        values.append(telegram_message_id)
    if user_id:
        where.append("mr.user_id = %s")
        values.append(str(user_id))

    where_sql = " AND ".join(where)

    rows = await fetch_all(
        f"""
        SELECT mr.message_id, mr.telegram_message_id, mr.user_id,
               mr.reaction_type, mr.reaction_emoji, mr.reaction_custom_emoji_id,
               mr.date
        FROM message_reactions mr
        WHERE {where_sql}
        ORDER BY mr.date DESC
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )

    result: dict[str, Any] = {
        "items": [dict(r) for r in rows],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }

    if aggregate:
        agg_rows = await fetch_all(
            f"""
            SELECT COALESCE(reaction_emoji, reaction_type) AS reaction,
                   COUNT(*) AS count
            FROM message_reactions mr
            WHERE {where_sql}
            GROUP BY COALESCE(reaction_emoji, reaction_type)
            ORDER BY count DESC
            """,
            values,
        )
        result["aggregated"] = {r["reaction"]: r["count"] for r in agg_rows}

    return result


async def get_chat_events(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Лог системных событий чата."""
    where = ["ce.chat_id = %s"]
    values: list[Any] = [str(chat_id)]

    if event_type:
        where.append("ce.event_type = %s")
        values.append(event_type)
    if date_from:
        where.append("ce.created_at >= %s")
        values.append(date_from)
    if date_to:
        where.append("ce.created_at <= %s")
        values.append(date_to)
    if user_id:
        where.append("(ce.actor_user_id = %s OR ce.target_user_id = %s)")
        values.extend([str(user_id), str(user_id)])

    where_sql = " AND ".join(where)

    total_row = await fetch_one(
        f"SELECT COUNT(*) AS total FROM chat_events ce WHERE {where_sql}",
        values,
    )

    rows = await fetch_all(
        f"""
        SELECT ce.id, ce.event_type, ce.actor_user_id, ce.target_user_id,
               ce.telegram_message_id, ce.event_data, ce.created_at,
               ua.username AS actor_username,
               ua.first_name AS actor_name,
               ut.username AS target_username,
               ut.first_name AS target_name
        FROM chat_events ce
        LEFT JOIN users ua ON ua.user_id = ce.actor_user_id
        LEFT JOIN users ut ON ut.user_id = ce.target_user_id
        WHERE {where_sql}
        ORDER BY ce.created_at DESC
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )

    return {
        "items": [dict(r) for r in rows],
        "total": total_row["total"] if total_row else 0,
        "limit": limit,
        "offset": offset,
    }


def _parse_period(period: str) -> datetime:
    """Конвертировать строку периода в datetime начала."""
    now = datetime.utcnow()
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    if period == "90d":
        return now - timedelta(days=90)
    return datetime(2020, 1, 1)  # "all"


async def get_chat_stats(chat_id: str, period: str = "30d") -> dict[str, Any]:
    """Агрегированная статистика чата за период."""
    since = _parse_period(period)
    cid = str(chat_id)

    # Общее количество сообщений
    msg_total = await fetch_one(
        "SELECT COUNT(*) AS total FROM messages WHERE chat_id = %s AND direction = 'inbound' AND created_at >= %s",
        [cid, since],
    )

    # Сообщений по дням
    msg_per_day = await fetch_all(
        """
        SELECT DATE(created_at) AS date, COUNT(*) AS count
        FROM messages
        WHERE chat_id = %s AND direction = 'inbound' AND created_at >= %s
        GROUP BY DATE(created_at)
        ORDER BY date
        """,
        [cid, since],
    )

    # Активные пользователи (из webhook_updates)
    active_users = await fetch_one(
        """
        SELECT COUNT(DISTINCT user_id) AS count
        FROM webhook_updates
        WHERE chat_id = %s AND received_at >= %s AND user_id IS NOT NULL
        """,
        [cid, since],
    )

    # Топ авторы
    top_authors = await fetch_all(
        """
        SELECT wu.user_id, u.username, u.first_name,
               COUNT(*) AS count
        FROM webhook_updates wu
        LEFT JOIN users u ON u.user_id = wu.user_id
        WHERE wu.chat_id = %s AND wu.received_at >= %s
          AND wu.update_type IN ('message', 'channel_post') AND wu.user_id IS NOT NULL
        GROUP BY wu.user_id, u.username, u.first_name
        ORDER BY count DESC
        LIMIT 10
        """,
        [cid, since],
    )

    # Распределение медиа
    media_dist = await fetch_all(
        """
        SELECT media_type, COUNT(*) AS count
        FROM messages
        WHERE chat_id = %s AND created_at >= %s AND media_type IS NOT NULL
        GROUP BY media_type
        ORDER BY count DESC
        """,
        [cid, since],
    )

    # Реакции
    reactions_total = await fetch_one(
        "SELECT COUNT(*) AS total FROM message_reactions WHERE chat_id = %s AND date >= %s",
        [cid, since],
    )

    top_reactions = await fetch_all(
        """
        SELECT COALESCE(reaction_emoji, reaction_type) AS reaction, COUNT(*) AS count
        FROM message_reactions
        WHERE chat_id = %s AND date >= %s
        GROUP BY COALESCE(reaction_emoji, reaction_type)
        ORDER BY count DESC
        LIMIT 10
        """,
        [cid, since],
    )

    # Сводка событий
    events_summary = await fetch_all(
        """
        SELECT event_type, COUNT(*) AS count
        FROM chat_events
        WHERE chat_id = %s AND created_at >= %s
        GROUP BY event_type
        ORDER BY count DESC
        """,
        [cid, since],
    )

    # Пиковые часы
    peak_hours = await fetch_all(
        """
        SELECT EXTRACT(HOUR FROM created_at)::int AS hour, COUNT(*) AS count
        FROM messages
        WHERE chat_id = %s AND direction = 'inbound' AND created_at >= %s
        GROUP BY hour
        ORDER BY hour
        """,
        [cid, since],
    )

    # Среднее сообщений в день
    total_msgs = msg_total["total"] if msg_total else 0
    day_count = len(msg_per_day) if msg_per_day else 1
    avg_per_day = round(total_msgs / max(day_count, 1), 1)

    # Форматируем top_authors: name = first_name || username || user_id
    authors_list = []
    for r in top_authors:
        d = dict(r)
        d["name"] = d.get("first_name") or d.get("username") or str(d.get("user_id", "?"))
        authors_list.append(d)

    return {
        "chat_id": cid,
        "period": period,
        "messages_total": total_msgs,
        "messages_per_day": avg_per_day,
        "active_users": active_users["count"] if active_users else 0,
        "top_authors": authors_list,
        "media_distribution": [
            {"label": r["media_type"], "value": r["count"]} for r in media_dist
        ],
        "reactions_total": reactions_total["total"] if reactions_total else 0,
        "top_reactions": [
            {"emoji": r["reaction"], "label": r["reaction"], "count": r["count"]}
            for r in top_reactions
        ],
        "events_summary": {r["event_type"]: r["count"] for r in events_summary},
        "peak_hours": [dict(r) for r in peak_hours],
    }
