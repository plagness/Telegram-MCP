"""Сервис для обработки входящих вебхук-обновлений от Telegram."""

from __future__ import annotations

import json
from typing import Any

from ..db import execute, execute_returning, fetch_all


def _detect_update_type(update: dict[str, Any]) -> str:
    for key in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
        "message_reaction",
        "message_reaction_count",
        "poll",
        "poll_answer",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "purchased_paid_media",
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
    ):
        if key in update:
            return key
    return "unknown"


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        if key in update:
            return update[key]
    return None


async def _upsert_user(user: dict[str, Any]) -> None:
    await execute(
        """
        INSERT INTO users (user_id, is_bot, first_name, last_name, username, language_code)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET is_bot = EXCLUDED.is_bot,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            username = EXCLUDED.username,
            language_code = EXCLUDED.language_code,
            updated_at = NOW()
        """,
        [
            str(user.get("id")),
            bool(user.get("is_bot")),
            user.get("first_name"),
            user.get("last_name"),
            user.get("username"),
            user.get("language_code"),
        ],
    )


async def _upsert_chat(chat: dict[str, Any]) -> None:
    await execute(
        """
        INSERT INTO chats (chat_id, type, title, username)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (chat_id) DO UPDATE
        SET type = EXCLUDED.type,
            title = EXCLUDED.title,
            username = EXCLUDED.username,
            updated_at = NOW()
        """,
        [
            str(chat.get("id")),
            chat.get("type"),
            chat.get("title"),
            chat.get("username"),
        ],
    )


async def _insert_inbound_message(message: dict[str, Any], update_type: str) -> None:
    await execute(
        """
        INSERT INTO messages (
            chat_id,
            telegram_message_id,
            direction,
            text,
            parse_mode,
            status,
            payload_json
        )
        VALUES (%s, %s, 'inbound', %s, NULL, %s, %s::jsonb)
        ON CONFLICT (chat_id, telegram_message_id) DO NOTHING
        """,
        [
            str(message.get("chat", {}).get("id")),
            message.get("message_id"),
            message.get("text"),
            update_type,
            json.dumps(message),
        ],
    )


async def _insert_callback_query(callback_query: dict[str, Any]) -> None:
    """Сохранение callback_query в БД."""
    cq_id = str(callback_query.get("id"))
    cq_from = callback_query.get("from", {})
    message = callback_query.get("message", {})
    chat = message.get("chat", {})

    # Upsert пользователя
    if cq_from:
        await _upsert_user(cq_from)

    await execute(
        """
        INSERT INTO callback_queries (
            callback_query_id, chat_id, user_id, message_id,
            inline_message_id, data, payload_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (callback_query_id) DO NOTHING
        """,
        [
            cq_id,
            str(chat.get("id")) if chat else None,
            str(cq_from.get("id")) if cq_from else None,
            message.get("message_id"),
            callback_query.get("inline_message_id"),
            callback_query.get("data"),
            json.dumps(callback_query),
        ],
    )


async def ingest_update(update: dict[str, Any]) -> dict[str, Any]:
    update_id = update.get("update_id")
    update_type = _detect_update_type(update)
    message = _extract_message(update)

    if message:
        chat = message.get("chat") or {}
        await _upsert_chat(chat)
        if message.get("from"):
            await _upsert_user(message.get("from") or {})
        await _insert_inbound_message(message, update_type)

    # Обработка callback_query
    if update_type == "callback_query":
        callback_query = update.get("callback_query", {})
        await _insert_callback_query(callback_query)

    await execute_returning(
        """
        INSERT INTO webhook_updates (update_id, update_type, chat_id, user_id, message_id, payload_json)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (update_id) DO UPDATE
        SET update_type = EXCLUDED.update_type,
            chat_id = EXCLUDED.chat_id,
            user_id = EXCLUDED.user_id,
            message_id = EXCLUDED.message_id,
            payload_json = EXCLUDED.payload_json,
            received_at = NOW()
        RETURNING id
        """,
        [
            update_id,
            update_type,
            str(message.get("chat", {}).get("id")) if message else None,
            str(message.get("from", {}).get("id")) if message and message.get("from") else None,
            message.get("message_id") if message else None,
            json.dumps(update),
        ],
    )

    return {"ok": True, "update_type": update_type}


async def list_updates(
    limit: int = 100,
    offset: int = 0,
    update_type: str | None = None,
) -> list[dict]:
    if update_type:
        return await fetch_all(
            "SELECT * FROM webhook_updates WHERE update_type = %s ORDER BY received_at DESC LIMIT %s OFFSET %s",
            [update_type, limit, offset],
        )
    return await fetch_all(
        "SELECT * FROM webhook_updates ORDER BY received_at DESC LIMIT %s OFFSET %s",
        [limit, offset],
    )
