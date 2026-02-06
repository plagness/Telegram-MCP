"""Сервис для работы с сообщениями: CRUD, аудит-события."""

from __future__ import annotations

import json
from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one


async def create_message(
    *,
    chat_id: int | str,
    direction: str,
    text: str | None,
    parse_mode: str | None,
    status: str,
    request_id: str | None,
    payload: dict[str, Any],
    is_live: bool,
    reply_to_message_id: int | None,
    message_thread_id: int | None,
    message_type: str = "text",
) -> dict:
    row = await execute_returning(
        """
        INSERT INTO messages (
            external_id,
            chat_id,
            direction,
            text,
            parse_mode,
            status,
            payload_json,
            is_live,
            reply_to_message_id,
            message_thread_id,
            message_type
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
        RETURNING *
        """,
        [
            request_id,
            str(chat_id),
            direction,
            text,
            parse_mode,
            status,
            json.dumps(payload or {}),
            is_live,
            reply_to_message_id,
            message_thread_id,
            message_type,
        ],
    )
    return row or {}


async def update_message(
    message_id: int,
    *,
    status: str | None = None,
    telegram_message_id: int | None = None,
    error: str | None = None,
    text: str | None = None,
    parse_mode: str | None = None,
    media_file_id: str | None = None,
    sent: bool = False,
    edited: bool = False,
    deleted: bool = False,
) -> None:
    sets = []
    values: list[Any] = []
    if status is not None:
        sets.append("status = %s")
        values.append(status)
    if telegram_message_id is not None:
        sets.append("telegram_message_id = %s")
        values.append(telegram_message_id)
    if error is not None:
        sets.append("error = %s")
        values.append(error)
    if text is not None:
        sets.append("text = %s")
        values.append(text)
    if parse_mode is not None:
        sets.append("parse_mode = %s")
        values.append(parse_mode)
    if media_file_id is not None:
        sets.append("media_file_id = %s")
        values.append(media_file_id)
    if sent:
        sets.append("sent_at = NOW()")
    if edited:
        sets.append("edited_at = NOW()")
    if deleted:
        sets.append("deleted_at = NOW()")
    sets.append("updated_at = NOW()")
    if not sets:
        return
    values.append(message_id)
    await execute(
        f"UPDATE messages SET {', '.join(sets)} WHERE id = %s",
        values,
    )


async def add_event(message_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
    await execute(
        """
        INSERT INTO message_events (message_id, event_type, payload_json)
        VALUES (%s, %s, %s::jsonb)
        """,
        [message_id, event_type, json.dumps(payload or {})],
    )


async def get_message(message_id: int) -> dict | None:
    return await fetch_one("SELECT * FROM messages WHERE id = %s", [message_id])


async def list_messages(
    *,
    chat_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    where = []
    values: list[Any] = []
    if chat_id:
        where.append("chat_id = %s")
        values.append(str(chat_id))
    if status:
        where.append("status = %s")
        values.append(status)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM messages {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s"
    values.extend([limit, offset])
    return await fetch_all(sql, values)
