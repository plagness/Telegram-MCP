"""Эндпоинты для работы с историями (Bot API 9.0+)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import PostStoryIn, EditStoryIn
from ..telegram_client import (
    TelegramError,
    post_story,
    edit_story,
    delete_story,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/stories", tags=["stories"])
logger = logging.getLogger(__name__)


@router.post("/post")
async def post_story_api(payload: PostStoryIn) -> dict[str, Any]:
    """Публикация истории в канал (Bot API 9.0)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "content": payload.content,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.areas:
        telegram_payload["areas"] = payload.areas
    if payload.post_to_chat_page is not None:
        telegram_payload["post_to_chat_page"] = payload.post_to_chat_page
    if payload.protect_content is not None:
        telegram_payload["protect_content"] = payload.protect_content

    try:
        result = await post_story(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.put("/{chat_id}/{story_id}")
async def edit_story_api(chat_id: str, story_id: int, payload: EditStoryIn) -> dict[str, Any]:
    """Редактирование истории."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": chat_id,
        "story_id": story_id,
    }
    if payload.content is not None:
        telegram_payload["content"] = payload.content
    if payload.caption is not None:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.areas is not None:
        telegram_payload["areas"] = payload.areas

    try:
        result = await edit_story(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/{chat_id}/{story_id}")
async def delete_story_api(chat_id: str, story_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Удаление истории."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await delete_story(
            {"chat_id": chat_id, "story_id": story_id},
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}
