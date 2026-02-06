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
    ban_chat_member,
    unban_chat_member,
    restrict_chat_member,
    promote_chat_member,
    set_chat_administrator_custom_title,
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


# === Chat Management ===


@router.post("/{chat_id}/members/{user_id}/ban")
async def ban_member_api(
    chat_id: str,
    user_id: int,
    until_date: int | None = None,
    revoke_messages: bool = False,
) -> dict[str, Any]:
    """
    Забанить участника чата.

    Args:
        chat_id: ID чата
        user_id: ID пользователя
        until_date: Unix timestamp до когда бан (None = навсегда)
        revoke_messages: Удалить все сообщения пользователя
    """
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "revoke_messages": revoke_messages,
    }
    if until_date:
        payload["until_date"] = until_date

    try:
        result = await ban_chat_member(payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/{chat_id}/members/{user_id}/unban")
async def unban_member_api(
    chat_id: str,
    user_id: int,
    only_if_banned: bool = True,
) -> dict[str, Any]:
    """
    Разбанить участника чата.

    Args:
        chat_id: ID чата
        user_id: ID пользователя
        only_if_banned: Разбанить только если забанен
    """
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "only_if_banned": only_if_banned,
    }

    try:
        result = await unban_chat_member(payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/{chat_id}/members/{user_id}/restrict")
async def restrict_member_api(
    chat_id: str,
    user_id: int,
    permissions: dict[str, bool],
    until_date: int | None = None,
) -> dict[str, Any]:
    """
    Ограничить права участника.

    Args:
        chat_id: ID чата
        user_id: ID пользователя
        permissions: Права (can_send_messages, can_send_media_messages, etc.)
        until_date: Unix timestamp до когда ограничение
    """
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "permissions": permissions,
    }
    if until_date:
        payload["until_date"] = until_date

    try:
        result = await restrict_chat_member(payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/{chat_id}/members/{user_id}/promote")
async def promote_member_api(
    chat_id: str,
    user_id: int,
    is_anonymous: bool = False,
    can_manage_chat: bool = False,
    can_post_messages: bool = False,
    can_edit_messages: bool = False,
    can_delete_messages: bool = False,
    can_manage_video_chats: bool = False,
    can_restrict_members: bool = False,
    can_promote_members: bool = False,
    can_change_info: bool = False,
    can_invite_users: bool = False,
    can_pin_messages: bool = False,
) -> dict[str, Any]:
    """
    Повысить участника до админа с заданными правами.

    Args:
        chat_id: ID чата
        user_id: ID пользователя
        is_anonymous: Анонимный админ
        can_*: Различные права админа
    """
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "is_anonymous": is_anonymous,
        "can_manage_chat": can_manage_chat,
        "can_post_messages": can_post_messages,
        "can_edit_messages": can_edit_messages,
        "can_delete_messages": can_delete_messages,
        "can_manage_video_chats": can_manage_video_chats,
        "can_restrict_members": can_restrict_members,
        "can_promote_members": can_promote_members,
        "can_change_info": can_change_info,
        "can_invite_users": can_invite_users,
        "can_pin_messages": can_pin_messages,
    }

    try:
        result = await promote_chat_member(payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}
