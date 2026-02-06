"""Эндпоинты для работы с чатами и участниками."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..db import fetch_all, fetch_one
from ..telegram_client import (
    TelegramError,
    get_chat,
    get_chat_member,
    get_chat_member_count,
    pin_chat_message,
    unpin_chat_message,
)

router = APIRouter(prefix="/v1/chats", tags=["chats"])


@router.get("/{chat_id}")
async def get_chat_api(chat_id: str) -> dict[str, Any]:
    """Получить информацию о чате от Telegram API."""
    try:
        result = await get_chat({"chat_id": chat_id})
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"chat": result}


@router.get("/{chat_id}/members/{user_id}")
async def get_chat_member_api(chat_id: str, user_id: int) -> dict[str, Any]:
    """Получить информацию об участнике чата."""
    try:
        result = await get_chat_member({"chat_id": chat_id, "user_id": user_id})
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"member": result}


@router.get("/{chat_id}/members/count")
async def get_chat_member_count_api(chat_id: str) -> dict[str, Any]:
    """Количество участников чата."""
    try:
        result = await get_chat_member_count({"chat_id": chat_id})
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"count": result}


@router.post("/{chat_id}/pin/{message_id}")
async def pin_message_api(chat_id: str, message_id: int) -> dict[str, Any]:
    """Закрепить сообщение в чате."""
    try:
        result = await pin_chat_message({
            "chat_id": chat_id,
            "message_id": message_id,
        })
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/{chat_id}/pin/{message_id}")
async def unpin_message_api(chat_id: str, message_id: int) -> dict[str, Any]:
    """Открепить сообщение в чате."""
    try:
        result = await unpin_chat_message({
            "chat_id": chat_id,
            "message_id": message_id,
        })
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.get("/{chat_id}/stored")
async def get_stored_chat_api(chat_id: str) -> dict[str, Any]:
    """Получить данные о чате из локальной БД (из вебхуков)."""
    row = await fetch_one("SELECT * FROM chats WHERE chat_id = %s", [chat_id])
    if not row:
        raise HTTPException(status_code=404, detail="chat not found in local db")
    return {"chat": row}


@router.get("/{chat_id}/stored-users")
async def list_chat_users_api(chat_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """Список пользователей из БД, которые писали в данном чате."""
    rows = await fetch_all(
        """
        SELECT DISTINCT u.* FROM users u
        JOIN messages m ON m.chat_id = %s
        JOIN webhook_updates wu ON wu.chat_id = %s AND wu.user_id = u.user_id
        ORDER BY u.updated_at DESC
        LIMIT %s OFFSET %s
        """,
        [chat_id, chat_id, limit, offset],
    )
    return {"items": rows, "count": len(rows)}
