"""API endpoints for multi-bot management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import RegisterBotIn, SetMyProfilePhotoIn, EditUserStarSubscriptionIn
from ..services.bots import BotRegistry
from ..telegram_client import (
    TelegramError,
    set_my_profile_photo,
    remove_my_profile_photo,
    get_user_profile_audios,
    edit_user_star_subscription,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/bots", tags=["bots"])


@router.get("")
async def list_bots_api(include_inactive: bool = False) -> dict[str, Any]:
    items = await BotRegistry.list_bots(include_inactive=include_inactive, include_token=False)
    return {"items": items, "count": len(items)}


@router.post("")
async def register_bot_api(payload: RegisterBotIn) -> dict[str, Any]:
    try:
        bot = await BotRegistry.register_bot(payload.token, set_default=payload.is_default)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"bot": bot}


@router.get("/default")
async def get_default_bot_api() -> dict[str, Any]:
    bot = await BotRegistry.get_default_bot()
    if not bot:
        raise HTTPException(status_code=404, detail="default bot is not configured")
    return {"bot": bot}


@router.put("/{bot_id}/default")
async def set_default_bot_api(bot_id: int) -> dict[str, Any]:
    try:
        bot = await BotRegistry.set_default(bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="bot not found")
    return {"bot": bot}


@router.get("/{bot_id}")
async def get_bot_api(bot_id: int) -> dict[str, Any]:
    bot = await BotRegistry.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="bot not found")
    return {"bot": bot}


@router.delete("/{bot_id}")
async def deactivate_bot_api(bot_id: int) -> dict[str, Any]:
    bot = await BotRegistry.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="bot not found")

    await BotRegistry.deactivate_bot(bot_id)
    return {"ok": True, "bot_id": bot_id, "status": "deactivated"}


# === Batch 10: Bot Profile + Subscriptions ===


@router.post("/profile-photo")
async def set_my_profile_photo_api(payload: SetMyProfilePhotoIn) -> dict[str, Any]:
    """Установить фото профиля бота (Bot API 9.4)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {"photo": payload.photo}
    if payload.is_public is not None:
        telegram_payload["is_public"] = payload.is_public
    try:
        result = await set_my_profile_photo(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/profile-photo")
async def remove_my_profile_photo_api(bot_id: int | None = None) -> dict[str, Any]:
    """Удалить фото профиля бота (Bot API 9.4)."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await remove_my_profile_photo(bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.get("/users/{user_id}/profile-audios")
async def get_user_profile_audios_api(
    user_id: int,
    bot_id: int | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Получить аудио профиля пользователя (Bot API 9.4)."""
    bot_token, _ = await resolve_bot_context(bot_id)
    telegram_payload: dict[str, Any] = {"user_id": user_id}
    if offset is not None:
        telegram_payload["offset"] = offset
    if limit is not None:
        telegram_payload["limit"] = limit
    try:
        result = await get_user_profile_audios(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/star-subscription/edit")
async def edit_user_star_subscription_api(payload: EditUserStarSubscriptionIn) -> dict[str, Any]:
    """Редактирование Star-подписки пользователя (Bot API 8.0)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload = {
        "user_id": payload.user_id,
        "telegram_payment_charge_id": payload.telegram_payment_charge_id,
        "is_canceled": payload.is_canceled,
    }
    try:
        result = await edit_user_star_subscription(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}
