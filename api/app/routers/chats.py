"""Endpoints for chats, members and chat management operations."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from ..db import execute, fetch_all, fetch_one
from ..models import SetChatAliasIn
from ..telegram_client import (
    TelegramError,
    ban_chat_member,
    get_chat,
    get_chat_member,
    get_chat_member_count,
    pin_chat_message,
    promote_chat_member,
    restrict_chat_member,
    unban_chat_member,
    unpin_chat_message,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/chats", tags=["chats"])


@router.get("")
async def list_chats_api(
    bot_id: int | None = None,
    chat_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    where: list[str] = []
    values: list[Any] = []
    if bot_id is not None:
        where.append("bot_id = %s")
        values.append(bot_id)
    if chat_type:
        where.append("type = %s")
        values.append(chat_type)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = await fetch_all(
        f"""
        SELECT *
        FROM chats
        {where_sql}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )
    return {"items": rows, "count": len(rows)}


@router.put("/{chat_id}/alias")
async def set_chat_alias_api(chat_id: str, payload: SetChatAliasIn) -> dict[str, Any]:
    row = await execute(
        """
        UPDATE chats
        SET alias = %s,
            updated_at = NOW()
        WHERE chat_id = %s
        """,
        [payload.alias.strip(), chat_id],
    )
    if row is None:
        # execute() doesn't return rowcount; verify existence explicitly.
        exists = await fetch_one("SELECT chat_id FROM chats WHERE chat_id = %s", [chat_id])
        if not exists:
            raise HTTPException(status_code=404, detail="chat not found")

    chat = await fetch_one("SELECT * FROM chats WHERE chat_id = %s", [chat_id])
    return {"chat": chat}


@router.get("/by-alias/{alias}")
async def get_chat_by_alias_api(alias: str) -> dict[str, Any]:
    row = await fetch_one("SELECT * FROM chats WHERE alias = %s", [alias])
    if not row:
        raise HTTPException(status_code=404, detail="chat alias not found")
    return {"chat": row}


@router.get("/{chat_id}/history")
async def get_chat_history_api(
    chat_id: str,
    bot_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["chat_id = %s"]
    values: list[Any] = [chat_id]
    if bot_id is not None:
        where.append("bot_id = %s")
        values.append(bot_id)

    rows = await fetch_all(
        f"""
        SELECT *
        FROM messages
        WHERE {' AND '.join(where)}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )
    return {"items": rows, "count": len(rows)}


@router.get("/{chat_id}/members")
async def list_chat_members_api(
    chat_id: str,
    bot_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["cm.chat_id = %s"]
    values: list[Any] = [chat_id]
    if bot_id is not None:
        where.append("cm.bot_id = %s")
        values.append(bot_id)

    rows = await fetch_all(
        f"""
        SELECT
            cm.*,
            u.username,
            u.first_name,
            u.last_name,
            u.is_premium
        FROM chat_members cm
        LEFT JOIN users u ON u.user_id = cm.user_id
        WHERE {' AND '.join(where)}
        ORDER BY cm.updated_at DESC
        LIMIT %s OFFSET %s
        """,
        [*values, limit, offset],
    )
    return {"items": rows, "count": len(rows)}


@router.get("/{chat_id}")
async def get_chat_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Get chat details from Telegram API."""
    try:
        bot_token, resolved_bot_id = await resolve_bot_context(bot_id)
        result = await get_chat({"chat_id": chat_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await execute(
        """
        INSERT INTO chats (chat_id, type, title, username, description, bot_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (chat_id) DO UPDATE
        SET type = EXCLUDED.type,
            title = EXCLUDED.title,
            username = EXCLUDED.username,
            description = EXCLUDED.description,
            bot_id = COALESCE(EXCLUDED.bot_id, chats.bot_id),
            updated_at = NOW()
        """,
        [
            str(result.get("id") or chat_id),
            result.get("type"),
            result.get("title"),
            result.get("username"),
            result.get("description"),
            resolved_bot_id,
        ],
    )

    return {"chat": result}


@router.get("/{chat_id}/members/{user_id}")
async def get_chat_member_api(chat_id: str, user_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Get member details from Telegram API."""
    try:
        bot_token, resolved_bot_id = await resolve_bot_context(bot_id)
        result = await get_chat_member({"chat_id": chat_id, "user_id": user_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    await execute(
        """
        INSERT INTO chat_members (chat_id, user_id, bot_id, status, last_seen_at, metadata)
        VALUES (%s, %s, %s, %s, NOW(), %s::jsonb)
        ON CONFLICT (chat_id, user_id) DO UPDATE
        SET bot_id = COALESCE(EXCLUDED.bot_id, chat_members.bot_id),
            status = EXCLUDED.status,
            last_seen_at = NOW(),
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        """,
        [chat_id, str(user_id), resolved_bot_id, result.get("status"), json.dumps(result)],
    )

    return {"member": result}


@router.get("/{chat_id}/members/count")
async def get_chat_member_count_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Get number of chat members from Telegram API."""
    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await get_chat_member_count({"chat_id": chat_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"count": result}


@router.post("/{chat_id}/pin/{message_id}")
async def pin_message_api(chat_id: str, message_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Pin a message in chat."""
    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await pin_chat_message(
            {
                "chat_id": chat_id,
                "message_id": message_id,
            },
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/{chat_id}/pin/{message_id}")
async def unpin_message_api(chat_id: str, message_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """Unpin a message in chat."""
    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await unpin_chat_message(
            {
                "chat_id": chat_id,
                "message_id": message_id,
            },
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.get("/{chat_id}/stored")
async def get_stored_chat_api(chat_id: str) -> dict[str, Any]:
    """Get chat data from local DB (captured from webhooks)."""
    row = await fetch_one("SELECT * FROM chats WHERE chat_id = %s", [chat_id])
    if not row:
        raise HTTPException(status_code=404, detail="chat not found in local db")
    return {"chat": row}


@router.get("/{chat_id}/stored-users")
async def list_chat_users_api(chat_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    """List users from DB that were seen in this chat."""
    rows = await fetch_all(
        """
        SELECT DISTINCT u.*
        FROM users u
        JOIN webhook_updates wu ON wu.chat_id = %s AND wu.user_id = u.user_id
        ORDER BY u.updated_at DESC
        LIMIT %s OFFSET %s
        """,
        [chat_id, limit, offset],
    )
    return {"items": rows, "count": len(rows)}


# === Chat management ===


@router.post("/{chat_id}/members/{user_id}/ban")
async def ban_member_api(
    chat_id: str,
    user_id: int,
    until_date: int | None = None,
    revoke_messages: bool = False,
    bot_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "revoke_messages": revoke_messages,
    }
    if until_date:
        payload["until_date"] = until_date

    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await ban_chat_member(payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/{chat_id}/members/{user_id}/unban")
async def unban_member_api(
    chat_id: str,
    user_id: int,
    only_if_banned: bool = True,
    bot_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "only_if_banned": only_if_banned,
    }

    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await unban_chat_member(payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/{chat_id}/members/{user_id}/restrict")
async def restrict_member_api(
    chat_id: str,
    user_id: int,
    permissions: dict[str, bool],
    until_date: int | None = None,
    bot_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "user_id": user_id,
        "permissions": permissions,
    }
    if until_date:
        payload["until_date"] = until_date

    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await restrict_chat_member(payload, bot_token=bot_token)
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
    bot_id: int | None = None,
) -> dict[str, Any]:
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
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await promote_chat_member(payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}
