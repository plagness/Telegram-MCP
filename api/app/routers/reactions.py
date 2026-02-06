"""Эндпоинты для работы с реакциями."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import SetMessageReactionIn
from ..services import reactions as reaction_service
from ..telegram_client import TelegramError, set_message_reaction

router = APIRouter(prefix="/v1/reactions", tags=["reactions"])


@router.post("/set")
async def set_reaction_api(payload: SetMessageReactionIn) -> dict[str, Any]:
    """Установка реакции на сообщение."""
    # Подготовка payload для Telegram
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "message_id": payload.message_id,
        "is_big": payload.is_big,
    }

    if payload.reaction:
        telegram_payload["reaction"] = [r.model_dump() for r in payload.reaction]

    try:
        result = await set_message_reaction(telegram_payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.get("")
async def list_reactions_api(
    message_id: int | None = None,
    chat_id: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Список реакций с фильтрацией."""
    rows = await reaction_service.list_reactions(
        message_id=message_id,
        chat_id=chat_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return {"items": rows, "count": len(rows)}


@router.get("/{chat_id}/{message_id}")
async def get_message_reactions_api(chat_id: str, message_id: int) -> dict[str, Any]:
    """
    Получение всех реакций на конкретное сообщение.

    message_id — telegram_message_id (не внутренний).
    """
    rows = await reaction_service.get_message_reactions(chat_id, message_id)
    return {"items": rows, "count": len(rows)}
