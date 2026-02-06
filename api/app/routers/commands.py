"""Эндпоинты для управления командами бота (BotCommandScope)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import CommandSetIn, CommandSyncIn
from ..services import commands as command_service

router = APIRouter(prefix="/v1/commands", tags=["commands"])


@router.post("")
async def upsert_commands_api(payload: CommandSetIn) -> dict[str, Any]:
    row = await command_service.upsert_command_set(
        bot_id=payload.bot_id,
        scope_type=payload.scope_type,
        chat_id=payload.chat_id,
        user_id=payload.user_id,
        language_code=payload.language_code,
        commands=[c.model_dump() for c in payload.commands],
    )
    return {"command_set": row}


@router.get("")
async def list_commands_api() -> dict[str, Any]:
    rows = await command_service.list_command_sets()
    return {"items": rows, "count": len(rows)}


@router.post("/sync")
async def sync_commands_api(payload: CommandSyncIn) -> dict[str, Any]:
    if not payload.command_set_id:
        raise HTTPException(status_code=400, detail="command_set_id required")
    try:
        result = await command_service.sync_command_set(payload.command_set_id, bot_id=payload.bot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="command set not found")
    return result
