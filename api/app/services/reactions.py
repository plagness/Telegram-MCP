"""Сервис для работы с реакциями."""

from __future__ import annotations

from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one


async def add_reaction(
    message_id: int,
    chat_id: str,
    telegram_message_id: int,
    user_id: str,
    reaction_type: str,
    reaction_emoji: str | None = None,
    reaction_custom_emoji_id: str | None = None,
) -> dict[str, Any]:
    """Добавление реакции на сообщение."""
    sql = """
        INSERT INTO message_reactions (
            message_id, chat_id, telegram_message_id, user_id,
            reaction_type, reaction_emoji, reaction_custom_emoji_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chat_id, telegram_message_id, user_id, reaction_type, reaction_emoji, reaction_custom_emoji_id)
        DO UPDATE SET date = NOW()
        RETURNING *
    """
    return await execute_returning(
        sql,
        [
            message_id,
            chat_id,
            telegram_message_id,
            user_id,
            reaction_type,
            reaction_emoji,
            reaction_custom_emoji_id,
        ],
    )


async def remove_reaction(
    chat_id: str,
    telegram_message_id: int,
    user_id: str,
    reaction_type: str,
    reaction_emoji: str | None = None,
    reaction_custom_emoji_id: str | None = None,
) -> None:
    """Удаление реакции."""
    sql = """
        DELETE FROM message_reactions
        WHERE chat_id = %s AND telegram_message_id = %s AND user_id = %s
          AND reaction_type = %s
          AND (reaction_emoji = %s OR (%s IS NULL AND reaction_emoji IS NULL))
          AND (reaction_custom_emoji_id = %s OR (%s IS NULL AND reaction_custom_emoji_id IS NULL))
    """
    await execute(
        sql,
        [
            chat_id,
            telegram_message_id,
            user_id,
            reaction_type,
            reaction_emoji,
            reaction_emoji,
            reaction_custom_emoji_id,
            reaction_custom_emoji_id,
        ],
    )


async def get_message_reactions(
    chat_id: str,
    telegram_message_id: int,
) -> list[dict[str, Any]]:
    """Получение всех реакций на сообщение."""
    sql = """
        SELECT * FROM message_reactions
        WHERE chat_id = %s AND telegram_message_id = %s
        ORDER BY date DESC
    """
    return await fetch_all(sql, [chat_id, telegram_message_id])


async def list_reactions(
    message_id: int | None = None,
    chat_id: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Список реакций с фильтрацией."""
    where = []
    values: list[Any] = []

    if message_id is not None:
        where.append("message_id = %s")
        values.append(message_id)
    if chat_id:
        where.append("chat_id = %s")
        values.append(chat_id)
    if user_id:
        where.append("user_id = %s")
        values.append(user_id)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM message_reactions {where_sql} ORDER BY date DESC LIMIT %s OFFSET %s"
    values.extend([limit, offset])

    return await fetch_all(sql, values)
