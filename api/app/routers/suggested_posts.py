"""Эндпоинты для управления предложенными постами (Bot API 9.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import ApproveSuggestedPostIn, DeclineSuggestedPostIn
from ..telegram_client import (
    TelegramError,
    approve_suggested_post,
    decline_suggested_post,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/suggested-posts", tags=["suggested-posts"])


@router.post("/approve")
async def approve_suggested_post_api(payload: ApproveSuggestedPostIn) -> dict[str, Any]:
    """Одобрить предложенный пост в бизнес-канале (Bot API 9.2)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "business_connection_id": payload.business_connection_id,
        "message_id": payload.message_id,
    }
    if payload.is_scheduled is not None:
        telegram_payload["is_scheduled"] = payload.is_scheduled
    try:
        result = await approve_suggested_post(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/decline")
async def decline_suggested_post_api(payload: DeclineSuggestedPostIn) -> dict[str, Any]:
    """Отклонить предложенный пост в бизнес-канале (Bot API 9.2)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "business_connection_id": payload.business_connection_id,
        "message_id": payload.message_id,
    }
    try:
        result = await decline_suggested_post(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}
