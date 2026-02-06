"""
Роутер для чеклистов и подарков (Bot API 9.1+).

Endpoints:
  - POST /v1/checklists/send — отправка чек-листа
  - PUT /v1/messages/{message_id}/checklist — редактирование чек-листа
  - GET /v1/stars/balance — баланс звёзд бота
  - POST /v1/gifts/premium — подарить премиум за звёзды
  - GET /v1/gifts/user/{user_id} — подарки пользователя
  - GET /v1/gifts/chat/{chat_id} — подарки в чате
  - POST /v1/stories/repost — репост истории
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..models import (
    EditChecklistIn,
    GiftPremiumIn,
    RepostStoryIn,
    SendChecklistIn,
)
from ..services import messages as message_service
from ..services.bots import BotRegistry
from ..telegram_client import (
    edit_message_checklist,
    get_chat_gifts,
    get_my_star_balance,
    get_user_gifts,
    gift_premium_subscription,
    repost_story,
    send_checklist,
)

router = APIRouter(prefix="/v1", tags=["checklists", "stars", "gifts"])
logger = logging.getLogger(__name__)


async def _resolve_bot_context(bot_id: int | None) -> tuple[str, int | None]:
    bot_token = await BotRegistry.get_bot_token(bot_id)
    resolved_bot_id = bot_id
    bot_row = await BotRegistry.get_bot_by_token(bot_token)
    if bot_row and bot_row.get("bot_id") is not None:
        resolved_bot_id = int(bot_row["bot_id"])
    return bot_token, resolved_bot_id


# === Checklists ===


@router.post("/checklists/send")
async def send_checklist_api(payload: SendChecklistIn):
    """
    Отправка чек-листа (Bot API 9.1).

    Чек-лист — интерактивный список задач с галочками (до 30 задач).
    """
    checklist_data = {
        "title": payload.checklist.title,
        "tasks": [task.model_dump() for task in payload.checklist.tasks],
    }

    telegram_payload = {
        "chat_id": payload.chat_id,
        "checklist": checklist_data,
    }

    if payload.business_connection_id is not None:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.message_thread_id is not None:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_to_message_id is not None:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id

    bot_token, resolved_bot_id = await _resolve_bot_context(payload.bot_id)

    try:
        result = await send_checklist(telegram_payload, bot_token=bot_token)

        # Сохранение в БД
        row = await message_service.create_message(
            chat_id=payload.chat_id,
            bot_id=resolved_bot_id,
            direction="outbound",
            text=payload.checklist.title,
            parse_mode=None,
            status="sent",
            request_id=payload.request_id,
            payload=telegram_payload,
            is_live=False,
            reply_to_message_id=payload.reply_to_message_id,
            message_thread_id=payload.message_thread_id,
            message_type="checklist",
        )
        await message_service.update_message(
            row["id"],
            telegram_message_id=result.get("message_id"),
            sent=True,
        )

        return {"ok": True, "result": result, "message": await message_service.get_message(row["id"])}
    except Exception as e:
        logger.error(f"Ошибка send_checklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/messages/{message_id}/checklist")
async def edit_checklist_api(message_id: int, payload: EditChecklistIn):
    """
    Редактирование чек-листа.

    Обновляет список задач в существующем чек-листе.
    """
    # Получаем запись из БД
    msg_record = await message_service.get_message(message_id)
    if not msg_record:
        raise HTTPException(status_code=404, detail="Message not found")

    checklist_data = {
        "title": payload.checklist.title,
        "tasks": [task.model_dump() for task in payload.checklist.tasks],
    }

    telegram_payload = {
        "chat_id": msg_record["chat_id"],
        "message_id": msg_record["telegram_message_id"],
        "checklist": checklist_data,
    }

    if payload.business_connection_id is not None:
        telegram_payload["business_connection_id"] = payload.business_connection_id

    row_bot_id = int(msg_record["bot_id"]) if msg_record.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await _resolve_bot_context(target_bot_id)

    try:
        result = await edit_message_checklist(telegram_payload, bot_token=bot_token)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Ошибка edit_message_checklist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Stars ===


@router.get("/stars/balance")
async def get_star_balance(bot_id: int | None = None):
    """
    Баланс звёзд бота (Bot API 9.1).

    Возвращает количество звёзд на балансе бота.
    """
    try:
        bot_token, _ = await _resolve_bot_context(bot_id)
        result = await get_my_star_balance(bot_token=bot_token)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Ошибка get_my_star_balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Gifts ===


@router.post("/gifts/premium")
async def gift_premium_api(payload: GiftPremiumIn):
    """
    Подарить премиум-подписку за звёзды (Bot API 9.3).

    Списывает звёзды с баланса бота и дарит премиум пользователю.
    """
    telegram_payload = {
        "user_id": payload.user_id,
        "duration_months": payload.duration_months,
        "star_count": payload.star_count,
    }

    try:
        bot_token, _ = await _resolve_bot_context(payload.bot_id)
        result = await gift_premium_subscription(telegram_payload, bot_token=bot_token)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Ошибка gift_premium_subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gifts/user/{user_id}")
async def get_user_gifts_api(user_id: int, bot_id: int | None = None):
    """
    Получить список подарков пользователя (Bot API 9.3).

    Возвращает подарки, отправленные пользователю.
    """
    try:
        bot_token, _ = await _resolve_bot_context(bot_id)
        result = await get_user_gifts({"user_id": user_id}, bot_token=bot_token)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Ошибка get_user_gifts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gifts/chat/{chat_id}")
async def get_chat_gifts_api(chat_id: int | str, bot_id: int | None = None):
    """
    Получить список подарков в чате (Bot API 9.3).

    Возвращает подарки, отправленные в чат.
    """
    try:
        bot_token, _ = await _resolve_bot_context(bot_id)
        result = await get_chat_gifts({"chat_id": chat_id}, bot_token=bot_token)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Ошибка get_chat_gifts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Stories ===


@router.post("/stories/repost")
async def repost_story_api(payload: RepostStoryIn):
    """
    Репост истории в канал (Bot API 9.3).

    Позволяет боту репостить истории из других каналов.
    """
    telegram_payload = {
        "chat_id": payload.chat_id,
        "from_chat_id": payload.from_chat_id,
        "story_id": payload.story_id,
    }

    try:
        bot_token, _ = await _resolve_bot_context(payload.bot_id)
        result = await repost_story(telegram_payload, bot_token=bot_token)
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Ошибка repost_story: {e}")
        raise HTTPException(status_code=500, detail=str(e))
