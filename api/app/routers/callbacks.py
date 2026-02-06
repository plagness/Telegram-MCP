"""Эндпоинты для работы с callback queries (нажатия inline-кнопок)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..db import execute, execute_returning, fetch_all, fetch_one
from ..models import AnswerCallbackIn
from ..services.bots import BotRegistry
from ..telegram_client import TelegramError, answer_callback_query

router = APIRouter(prefix="/v1/callbacks", tags=["callbacks"])


@router.post("/answer")
async def answer_callback_api(payload: AnswerCallbackIn) -> dict[str, Any]:
    """Ответ на callback_query от пользователя."""
    telegram_payload: dict[str, Any] = {
        "callback_query_id": payload.callback_query_id,
    }
    if payload.text:
        telegram_payload["text"] = payload.text
    if payload.show_alert:
        telegram_payload["show_alert"] = payload.show_alert
    if payload.url:
        telegram_payload["url"] = payload.url
    if payload.cache_time is not None:
        telegram_payload["cache_time"] = payload.cache_time

    try:
        bot_token = await BotRegistry.get_bot_token(payload.bot_id)
        result = await answer_callback_query(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Отмечаем callback как отвеченный в БД
    await execute(
        """
        UPDATE callback_queries
        SET answered = TRUE,
            answer_text = %s,
            answer_show_alert = %s,
            answered_at = NOW()
        WHERE callback_query_id = %s
        """,
        [payload.text, payload.show_alert, payload.callback_query_id],
    )

    return {"ok": True, "result": result}


@router.get("")
async def list_callbacks_api(
    chat_id: str | None = None,
    user_id: str | None = None,
    answered: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Список полученных callback queries."""
    where = []
    values: list[Any] = []
    if chat_id:
        where.append("chat_id = %s")
        values.append(chat_id)
    if user_id:
        where.append("user_id = %s")
        values.append(user_id)
    if answered is not None:
        where.append("answered = %s")
        values.append(answered)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM callback_queries {where_sql} ORDER BY received_at DESC LIMIT %s OFFSET %s"
    values.extend([limit, offset])
    rows = await fetch_all(sql, values)
    return {"items": rows, "count": len(rows)}


@router.get("/{callback_id}")
async def get_callback_api(callback_id: int) -> dict[str, Any]:
    """Получить callback query по внутреннему ID."""
    row = await fetch_one("SELECT * FROM callback_queries WHERE id = %s", [callback_id])
    if not row:
        raise HTTPException(status_code=404, detail="callback query not found")
    return {"callback_query": row}
