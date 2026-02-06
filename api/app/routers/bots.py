"""API endpoints for multi-bot management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import RegisterBotIn
from ..services.bots import BotRegistry

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
