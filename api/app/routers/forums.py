"""Эндпоинты для работы с форум-топиками (Bot API 7.0+)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import CreateForumTopicIn, EditForumTopicIn, ForumTopicActionIn
from ..telegram_client import (
    TelegramError,
    create_forum_topic,
    edit_forum_topic,
    close_forum_topic,
    reopen_forum_topic,
    delete_forum_topic,
    unpin_all_forum_topic_messages,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/forums", tags=["forums"])


@router.post("/create")
async def create_forum_topic_api(payload: CreateForumTopicIn) -> dict[str, Any]:
    """Создание топика в форум-группе."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "name": payload.name,
    }
    if payload.icon_color is not None:
        telegram_payload["icon_color"] = payload.icon_color
    if payload.icon_custom_emoji_id:
        telegram_payload["icon_custom_emoji_id"] = payload.icon_custom_emoji_id

    try:
        result = await create_forum_topic(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/edit")
async def edit_forum_topic_api(payload: EditForumTopicIn) -> dict[str, Any]:
    """Редактирование топика (имя / иконка)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "message_thread_id": payload.message_thread_id,
    }
    if payload.name is not None:
        telegram_payload["name"] = payload.name
    if payload.icon_custom_emoji_id is not None:
        telegram_payload["icon_custom_emoji_id"] = payload.icon_custom_emoji_id

    try:
        result = await edit_forum_topic(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/{thread_id}/close")
async def close_forum_topic_api(chat_id: str, thread_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Закрытие топика."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await close_forum_topic(
            {"chat_id": chat_id, "message_thread_id": thread_id},
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/{thread_id}/reopen")
async def reopen_forum_topic_api(chat_id: str, thread_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Повторное открытие топика."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await reopen_forum_topic(
            {"chat_id": chat_id, "message_thread_id": thread_id},
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/{chat_id}/{thread_id}")
async def delete_forum_topic_api(chat_id: str, thread_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Удаление топика."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await delete_forum_topic(
            {"chat_id": chat_id, "message_thread_id": thread_id},
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/{thread_id}/unpin-all")
async def unpin_all_forum_topic_messages_api(chat_id: str, thread_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Открепление всех сообщений в топике."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await unpin_all_forum_topic_messages(
            {"chat_id": chat_id, "message_thread_id": thread_id},
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}
