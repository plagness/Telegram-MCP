"""Сервис для работы с опросами."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from ..db import execute, execute_returning, fetch_all, fetch_one


async def create_poll(
    poll_id: str,
    message_id: int | None,
    chat_id: str,
    telegram_message_id: int | None,
    bot_id: int | None,
    question: str,
    options: list[dict[str, Any]],
    poll_type: str,
    is_anonymous: bool,
    allows_multiple_answers: bool,
    correct_option_id: int | None = None,
    explanation: str | None = None,
    explanation_entities: list[dict[str, Any]] | None = None,
    open_period: int | None = None,
    close_date: int | None = None,
) -> dict[str, Any]:
    """Создание опроса в БД."""
    sql = """
        INSERT INTO polls (
            poll_id, message_id, chat_id, telegram_message_id,
            bot_id,
            question, options, type, is_anonymous, allows_multiple_answers,
            correct_option_id, explanation, explanation_entities,
            open_period, close_date
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
    """
    return await execute_returning(
        sql,
        [
            poll_id,
            message_id,
            chat_id,
            telegram_message_id,
            bot_id,
            question,
            Json(options),
            poll_type,
            is_anonymous,
            allows_multiple_answers,
            correct_option_id,
            explanation,
            Json(explanation_entities) if explanation_entities else None,
            open_period,
            close_date,
        ],
    )


async def get_poll(poll_id: str) -> dict[str, Any] | None:
    """Получение опроса по poll_id."""
    return await fetch_one("SELECT * FROM polls WHERE poll_id = %s", [poll_id])


async def update_poll(
    poll_id: str,
    is_closed: bool | None = None,
    total_voter_count: int | None = None,
    results: dict[str, Any] | None = None,
) -> None:
    """Обновление опроса (результаты, закрытие)."""
    updates = []
    values = []

    if is_closed is not None:
        updates.append("is_closed = %s")
        values.append(is_closed)
    if total_voter_count is not None:
        updates.append("total_voter_count = %s")
        values.append(total_voter_count)
    if results is not None:
        updates.append("results = %s")
        values.append(Json(results))

    if not updates:
        return

    updates.append("updated_at = NOW()")
    values.append(poll_id)

    sql = f"UPDATE polls SET {', '.join(updates)} WHERE poll_id = %s"
    await execute(sql, values)


async def list_polls(
    chat_id: str | None = None,
    bot_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Список опросов с фильтрацией."""
    where = []
    values: list[Any] = []

    if chat_id:
        where.append("chat_id = %s")
        values.append(chat_id)
    if bot_id is not None:
        where.append("bot_id = %s")
        values.append(bot_id)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM polls {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s"
    values.extend([limit, offset])

    return await fetch_all(sql, values)


async def add_poll_answer(
    poll_id: str,
    user_id: str,
    option_ids: list[int],
) -> dict[str, Any]:
    """Сохранение ответа пользователя на опрос."""
    sql = """
        INSERT INTO poll_answers (poll_id, user_id, option_ids)
        VALUES (%s, %s, %s)
        RETURNING *
    """
    return await execute_returning(sql, [poll_id, user_id, Json(option_ids)])


async def get_poll_answers(poll_id: str) -> list[dict[str, Any]]:
    """Получение всех ответов на опрос."""
    return await fetch_all("SELECT * FROM poll_answers WHERE poll_id = %s", [poll_id])
