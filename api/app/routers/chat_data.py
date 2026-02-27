"""Chat Data API — готовые наборы данных из чатов для Integrat/Datesale.

6 endpoints, prefix /v1/chat-data/{chat_id}/:
- info     — метаданные чата
- members  — участники с профилями
- messages — сообщения с фильтрацией
- reactions — реакции с агрегацией
- events   — системные события
- stats    — агрегированная статистика
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.chat_data import (
    get_chat_events,
    get_chat_info,
    get_chat_members,
    get_chat_messages,
    get_chat_reactions,
    get_chat_stats,
)

router = APIRouter(prefix="/v1/chat-data", tags=["chat-data"])


@router.get("/{chat_id}/info")
async def chat_data_info(chat_id: str) -> dict[str, Any]:
    """Метаданные чата: название, описание, member_count, avatar_url, counters."""
    info = await get_chat_info(chat_id)
    if not info:
        raise HTTPException(status_code=404, detail="chat not found")
    return info


@router.get("/{chat_id}/members")
async def chat_data_members(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    """Участники чата с профилями, статусами, аватарками."""
    return await get_chat_members(
        chat_id, limit=limit, offset=offset, status=status, search=search,
    )


@router.get("/{chat_id}/messages")
async def chat_data_messages(
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
    return await get_chat_messages(
        chat_id,
        limit=limit, offset=offset,
        date_from=date_from, date_to=date_to,
        user_id=user_id, media_type=media_type, search=search,
    )


@router.get("/{chat_id}/reactions")
async def chat_data_reactions(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    telegram_message_id: int | None = None,
    user_id: str | None = None,
    aggregate: bool = True,
) -> dict[str, Any]:
    """Реакции чата с агрегацией по типу."""
    return await get_chat_reactions(
        chat_id,
        limit=limit, offset=offset,
        telegram_message_id=telegram_message_id,
        user_id=user_id, aggregate=aggregate,
    )


@router.get("/{chat_id}/events")
async def chat_data_events(
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Лог системных событий (join, leave, pin, photo, title_change)."""
    return await get_chat_events(
        chat_id,
        limit=limit, offset=offset,
        event_type=event_type,
        date_from=date_from, date_to=date_to,
        user_id=user_id,
    )


@router.get("/{chat_id}/stats")
async def chat_data_stats(
    chat_id: str,
    period: str = "30d",
) -> dict[str, Any]:
    """Агрегированная статистика: активность, топ авторы, тренды, медиа."""
    if period not in ("7d", "30d", "90d", "all"):
        raise HTTPException(status_code=400, detail="period must be 7d, 30d, 90d or all")
    return await get_chat_stats(chat_id, period=period)
