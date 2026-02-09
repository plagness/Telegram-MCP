"""Endpoints for chats, members and chat management operations."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from ..db import execute, fetch_all, fetch_one
from ..models import (
    SetChatAliasIn,
    SetChatTitleIn,
    SetChatDescriptionIn,
    CreateChatInviteLinkIn,
    EditChatInviteLinkIn,
    RevokeChatInviteLinkIn,
    CreateSubscriptionInviteLinkIn,
    EditChatSubscriptionInviteLinkIn,
)
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
    set_chat_title,
    set_chat_description,
    delete_chat_photo,
    leave_chat,
    unpin_all_chat_messages,
    create_chat_invite_link,
    edit_chat_invite_link,
    revoke_chat_invite_link,
    export_chat_invite_link,
    create_chat_subscription_invite_link,
    edit_chat_subscription_invite_link,
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


# === Batch 7: Chat Administration ===


@router.put("/{chat_id}/title")
async def set_chat_title_api(chat_id: str, payload: SetChatTitleIn) -> dict[str, Any]:
    """Установить название чата."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    try:
        result = await set_chat_title({"chat_id": chat_id, "title": payload.title}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.put("/{chat_id}/description")
async def set_chat_description_api(chat_id: str, payload: SetChatDescriptionIn) -> dict[str, Any]:
    """Установить описание чата."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {"chat_id": chat_id}
    if payload.description is not None:
        telegram_payload["description"] = payload.description
    try:
        result = await set_chat_description(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/{chat_id}/photo")
async def delete_chat_photo_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Удалить фото чата."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await delete_chat_photo({"chat_id": chat_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/leave")
async def leave_chat_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Выйти из чата."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await leave_chat({"chat_id": chat_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/unpin-all")
async def unpin_all_chat_messages_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Открепить все сообщения в чате."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await unpin_all_chat_messages({"chat_id": chat_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/invite-links")
async def create_chat_invite_link_api(chat_id: str, payload: CreateChatInviteLinkIn) -> dict[str, Any]:
    """Создать пригласительную ссылку."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {"chat_id": chat_id}
    if payload.name:
        telegram_payload["name"] = payload.name
    if payload.expire_date is not None:
        telegram_payload["expire_date"] = payload.expire_date
    if payload.member_limit is not None:
        telegram_payload["member_limit"] = payload.member_limit
    if payload.creates_join_request:
        telegram_payload["creates_join_request"] = payload.creates_join_request
    try:
        result = await create_chat_invite_link(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.put("/{chat_id}/invite-links")
async def edit_chat_invite_link_api(chat_id: str, payload: EditChatInviteLinkIn) -> dict[str, Any]:
    """Редактировать пригласительную ссылку."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": chat_id,
        "invite_link": payload.invite_link,
    }
    if payload.name is not None:
        telegram_payload["name"] = payload.name
    if payload.expire_date is not None:
        telegram_payload["expire_date"] = payload.expire_date
    if payload.member_limit is not None:
        telegram_payload["member_limit"] = payload.member_limit
    if payload.creates_join_request is not None:
        telegram_payload["creates_join_request"] = payload.creates_join_request
    try:
        result = await edit_chat_invite_link(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.delete("/{chat_id}/invite-links")
async def revoke_chat_invite_link_api(chat_id: str, payload: RevokeChatInviteLinkIn) -> dict[str, Any]:
    """Отозвать пригласительную ссылку."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    try:
        result = await revoke_chat_invite_link(
            {"chat_id": chat_id, "invite_link": payload.invite_link},
            bot_token=bot_token,
        )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/export-invite-link")
async def export_chat_invite_link_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Экспорт основной пригласительной ссылки."""
    bot_token, _ = await resolve_bot_context(bot_id)
    try:
        result = await export_chat_invite_link({"chat_id": chat_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{chat_id}/subscription-links")
async def create_subscription_invite_link_api(chat_id: str, payload: CreateSubscriptionInviteLinkIn) -> dict[str, Any]:
    """Создать подписочную пригласительную ссылку (Bot API 7.9)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": chat_id,
        "subscription_period": payload.subscription_period,
        "subscription_price": payload.subscription_price,
    }
    if payload.name:
        telegram_payload["name"] = payload.name
    try:
        result = await create_chat_subscription_invite_link(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.put("/{chat_id}/subscription-links")
async def edit_subscription_invite_link_api(chat_id: str, payload: EditChatSubscriptionInviteLinkIn) -> dict[str, Any]:
    """Редактировать подписочную пригласительную ссылку (Bot API 7.9)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": chat_id,
        "invite_link": payload.invite_link,
    }
    if payload.name is not None:
        telegram_payload["name"] = payload.name
    try:
        result = await edit_chat_subscription_invite_link(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}
