"""Эндпоинты для приёма вебхуков, просмотра обновлений и управления вебхуком."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..models import SetWebhookIn
from ..services import updates as update_service
from ..telegram_client import (
    TelegramError,
    set_webhook,
    delete_webhook,
    get_webhook_info,
    get_me,
)

router = APIRouter(tags=["webhook"])


@router.post("/telegram/webhook")
async def telegram_webhook(update: dict[str, Any]) -> JSONResponse:
    """Приём обновлений от Telegram (webhook target)."""
    result = await update_service.ingest_update(update)
    return JSONResponse(content=result)


@router.get("/v1/updates")
async def list_updates_api(
    limit: int = 100,
    offset: int = 0,
    update_type: str | None = None,
) -> dict[str, Any]:
    """Список полученных обновлений с фильтрацией по типу."""
    rows = await update_service.list_updates(limit=limit, offset=offset, update_type=update_type)
    return {"items": rows, "count": len(rows)}


@router.post("/v1/webhook/set")
async def set_webhook_api(payload: SetWebhookIn) -> dict[str, Any]:
    """Настроить вебхук у Telegram."""
    telegram_payload: dict[str, Any] = {"url": payload.url}
    if payload.secret_token:
        telegram_payload["secret_token"] = payload.secret_token
    if payload.max_connections is not None:
        telegram_payload["max_connections"] = payload.max_connections
    if payload.allowed_updates:
        telegram_payload["allowed_updates"] = payload.allowed_updates

    try:
        result = await set_webhook(telegram_payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/v1/webhook")
async def delete_webhook_api() -> dict[str, Any]:
    """Удалить вебхук у Telegram."""
    try:
        result = await delete_webhook()
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.get("/v1/webhook/info")
async def get_webhook_info_api() -> dict[str, Any]:
    """Текущая конфигурация вебхука."""
    try:
        result = await get_webhook_info()
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"webhook_info": result}


@router.get("/v1/bot/me")
async def get_bot_info_api() -> dict[str, Any]:
    """Информация о боте (getMe)."""
    try:
        result = await get_me()
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"bot": result}
