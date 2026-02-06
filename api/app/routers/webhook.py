"""Webhook endpoints, updates listing and webhook management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..models import SetWebhookIn
from ..services import updates as update_service
from ..services.bots import BotRegistry
from ..telegram_client import (
    TelegramError,
    delete_webhook,
    get_me,
    get_webhook_info,
    set_webhook,
    using_bot_token,
)

router = APIRouter(tags=["webhook"])


async def _resolve_bot_context(bot_id: int | None) -> tuple[str, int | None]:
    bot_token = await BotRegistry.get_bot_token(bot_id)
    resolved_bot_id = bot_id
    bot_row = await BotRegistry.get_bot_by_token(bot_token)
    if bot_row and bot_row.get("bot_id") is not None:
        resolved_bot_id = int(bot_row["bot_id"])
    return bot_token, resolved_bot_id


@router.post("/telegram/webhook")
async def telegram_webhook(update: dict[str, Any]) -> JSONResponse:
    """Receive Telegram updates for default bot."""
    bot_token, resolved_bot_id = await _resolve_bot_context(None)
    async with using_bot_token(bot_token):
        result = await update_service.ingest_update(update, bot_id=resolved_bot_id)
    return JSONResponse(content=result)


@router.post("/telegram/webhook/{bot_id}")
async def telegram_webhook_by_bot(bot_id: int, update: dict[str, Any]) -> JSONResponse:
    """Receive Telegram updates bound to a specific bot."""
    bot_token, resolved_bot_id = await _resolve_bot_context(bot_id)
    async with using_bot_token(bot_token):
        result = await update_service.ingest_update(update, bot_id=resolved_bot_id)
    return JSONResponse(content=result)


@router.get("/v1/updates")
async def list_updates_api(
    limit: int = 100,
    offset: int = 0,
    update_type: str | None = None,
    bot_id: int | None = None,
) -> dict[str, Any]:
    """List stored inbound updates with optional filters."""
    rows = await update_service.list_updates(limit=limit, offset=offset, update_type=update_type, bot_id=bot_id)
    return {"items": rows, "count": len(rows)}


@router.post("/v1/webhook/set")
async def set_webhook_api(payload: SetWebhookIn) -> dict[str, Any]:
    """Configure Telegram webhook."""
    telegram_payload: dict[str, Any] = {"url": payload.url}
    if payload.secret_token:
        telegram_payload["secret_token"] = payload.secret_token
    if payload.max_connections is not None:
        telegram_payload["max_connections"] = payload.max_connections
    if payload.allowed_updates:
        telegram_payload["allowed_updates"] = payload.allowed_updates

    try:
        bot_token, _ = await _resolve_bot_context(payload.bot_id)
        result = await set_webhook(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/v1/webhook")
async def delete_webhook_api(bot_id: int | None = None) -> dict[str, Any]:
    """Delete Telegram webhook."""
    try:
        bot_token, _ = await _resolve_bot_context(bot_id)
        result = await delete_webhook(bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.get("/v1/webhook/info")
async def get_webhook_info_api(bot_id: int | None = None) -> dict[str, Any]:
    """Get current Telegram webhook config."""
    try:
        bot_token, _ = await _resolve_bot_context(bot_id)
        result = await get_webhook_info(bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"webhook_info": result}


@router.get("/v1/bot/me")
async def get_bot_info_api(bot_id: int | None = None) -> dict[str, Any]:
    """Get bot info via getMe."""
    try:
        bot_token, _ = await _resolve_bot_context(bot_id)
        result = await get_me(bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"bot": result}
