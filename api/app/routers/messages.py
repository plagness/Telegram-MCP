"""Эндпоинты для работы с сообщениями: отправка, редактирование, удаление."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import (
    EditMessageIn,
    SendMessageIn,
    ForwardMessageIn,
    CopyMessageIn,
    PinMessageIn,
    DeleteMessagesIn,
    ForwardMessagesIn,
    CopyMessagesIn,
    EditMessageCaptionIn,
    EditMessageReplyMarkupIn,
    EditMessageMediaIn,
    SendMessageDraftIn,
    EditLiveLocationIn,
    StopLiveLocationIn,
)
from ..services import messages as message_service
from ..services import templates as template_service
from ..telegram_client import (
    TelegramError,
    send_message,
    edit_message_text,
    delete_message,
    forward_message,
    copy_message,
    pin_chat_message,
    unpin_chat_message,
    delete_messages,
    forward_messages,
    copy_messages,
    edit_message_caption,
    edit_message_reply_markup,
    edit_message_media,
    send_message_draft,
    edit_message_live_location,
    stop_message_live_location,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/messages", tags=["messages"])


@router.post("/send")
async def send_message_api(payload: SendMessageIn) -> dict[str, Any]:
    if not payload.text and not payload.template:
        raise HTTPException(status_code=400, detail="text or template required")

    text = payload.text
    parse_mode = payload.parse_mode
    if payload.template:
        try:
            rendered = await template_service.render_template(payload.template, payload.variables)
        except KeyError:
            raise HTTPException(status_code=404, detail="template not found")
        text = rendered["text"]
        parse_mode = parse_mode or rendered.get("parse_mode")

    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "text": text,
    }
    if parse_mode:
        telegram_payload["parse_mode"] = parse_mode
    if payload.disable_web_page_preview is not None:
        telegram_payload["disable_web_page_preview"] = payload.disable_web_page_preview
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup is not None:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.link_preview_options is not None:
        telegram_payload["link_preview_options"] = payload.link_preview_options
    if payload.reply_parameters is not None:
        telegram_payload["reply_parameters"] = payload.reply_parameters
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=text,
        parse_mode=parse_mode,
        status="queued" if not payload.dry_run else "dry_run",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=payload.live,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
    )
    if payload.dry_run:
        return {"message": row, "dry_run": True}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_message(telegram_payload, bot_token=bot_token)
        await message_service.update_message(
            row["id"],
            status="sent",
            telegram_message_id=result.get("message_id"),
            sent=True,
        )
        await message_service.add_event(row["id"], "send_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "send_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/{message_id}/edit")
async def edit_message_api(message_id: int, payload: EditMessageIn) -> dict[str, Any]:
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    text = payload.text
    parse_mode = payload.parse_mode or row.get("parse_mode")
    if payload.template:
        if payload.direct_messages_topic_id is not None:
            telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
        if payload.suggested_post_parameters is not None:
            telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
        try:
            rendered = await template_service.render_template(payload.template, payload.variables)
        except KeyError:
            raise HTTPException(status_code=404, detail="template not found")
        text = rendered["text"]
        parse_mode = parse_mode or rendered.get("parse_mode")

    if not text:
        raise HTTPException(status_code=400, detail="text or template required")

    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await resolve_bot_context(target_bot_id)

    telegram_payload = {
        "chat_id": row.get("chat_id"),
        "message_id": row.get("telegram_message_id"),
        "text": text,
    }
    if parse_mode:
        telegram_payload["parse_mode"] = parse_mode

    try:
        await message_service.add_event(row["id"], "edit_attempt", telegram_payload)
        result = await edit_message_text(telegram_payload, bot_token=bot_token)
        await message_service.update_message(
            row["id"],
            status="edited",
            text=text,
            parse_mode=parse_mode,
            edited=True,
        )
        await message_service.add_event(row["id"], "edit_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "edit_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/{message_id}/delete")
async def delete_message_api(message_id: int) -> dict[str, Any]:
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    telegram_payload = {
        "chat_id": row.get("chat_id"),
        "message_id": row.get("telegram_message_id"),
    }
    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    bot_token, _ = await resolve_bot_context(row_bot_id)
    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        await message_service.add_event(row["id"], "delete_attempt", telegram_payload)
        result = await delete_message(telegram_payload, bot_token=bot_token)
        await message_service.update_message(row["id"], status="deleted", deleted=True)
        await message_service.add_event(row["id"], "delete_success", {"result": result})
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "delete_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated}


@router.get("/{message_id}")
async def get_message_api(message_id: int) -> dict[str, Any]:
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    return {"message": row}


@router.get("")
async def list_messages_api(
    chat_id: str | None = None,
    bot_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    rows = await message_service.list_messages(
        chat_id=chat_id,
        bot_id=bot_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"items": rows, "count": len(rows)}


@router.post("/forward")
async def forward_message_api(payload: ForwardMessageIn) -> dict[str, Any]:
    """Пересылка сообщения из одного чата в другой."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "from_chat_id": payload.from_chat_id,
        "message_id": payload.message_id,
    }
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await forward_message(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=None,
        parse_mode=None,
        status="sent",
        request_id=None,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=None,
        message_thread_id=None,
        message_type="forward",
    )
    await message_service.update_message(
        row["id"],
        telegram_message_id=result.get("message_id"),
        sent=True,
    )
    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/copy")
async def copy_message_api(payload: CopyMessageIn) -> dict[str, Any]:
    """Копирование сообщения (без пометки 'Переслано')."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "from_chat_id": payload.from_chat_id,
        "message_id": payload.message_id,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await copy_message(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/{message_id}/pin")
async def pin_message_api(message_id: int, payload: PinMessageIn) -> dict[str, Any]:
    """
    Закрепление сообщения в чате (pinChatMessage).

    **Параметры**:
    - message_id: ID сообщения из БД
    - disable_notification: Не отправлять уведомление (по умолчанию True)

    **Примечание**: Для тихого закрепления (без пуша в чат) используйте disable_notification=True.
    """
    # Получаем chat_id и telegram_message_id из БД
    msg_record = await message_service.get_message(message_id)
    if not msg_record:
        raise HTTPException(status_code=404, detail="Message not found")

    telegram_payload: dict[str, Any] = {
        "chat_id": msg_record["chat_id"],
        "message_id": msg_record["telegram_message_id"],
        "disable_notification": payload.disable_notification,
    }
    row_bot_id = int(msg_record["bot_id"]) if msg_record.get("bot_id") is not None else None
    bot_token, _ = await resolve_bot_context(row_bot_id)

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await pin_chat_message(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.delete("/{message_id}/pin")
async def unpin_message_api(message_id: int) -> dict[str, Any]:
    """
    Открепление сообщения в чате (unpinChatMessage).

    **Параметры**:
    - message_id: ID сообщения из БД
    """
    # Получаем chat_id и telegram_message_id из БД
    msg_record = await message_service.get_message(message_id)
    if not msg_record:
        raise HTTPException(status_code=404, detail="Message not found")

    telegram_payload: dict[str, Any] = {
        "chat_id": msg_record["chat_id"],
        "message_id": msg_record["telegram_message_id"],
    }
    row_bot_id = int(msg_record["bot_id"]) if msg_record.get("bot_id") is not None else None
    bot_token, _ = await resolve_bot_context(row_bot_id)

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await unpin_chat_message(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


# === Batch 1: Bulk Operations (Bot API 7.0) ===


@router.post("/delete-batch")
async def delete_messages_api(payload: DeleteMessagesIn) -> dict[str, Any]:
    """Массовое удаление до 100 сообщений по Telegram message_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload = {
        "chat_id": payload.chat_id,
        "message_ids": payload.message_ids,
    }
    try:
        result = await delete_messages(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/forward-batch")
async def forward_messages_api(payload: ForwardMessagesIn) -> dict[str, Any]:
    """Массовая пересылка до 100 сообщений."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload = {
        "chat_id": payload.chat_id,
        "from_chat_id": payload.from_chat_id,
        "message_ids": payload.message_ids,
    }
    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await forward_messages(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/copy-batch")
async def copy_messages_api(payload: CopyMessagesIn) -> dict[str, Any]:
    """Массовое копирование до 100 сообщений."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload = {
        "chat_id": payload.chat_id,
        "from_chat_id": payload.from_chat_id,
        "message_ids": payload.message_ids,
    }
    try:
        result = await copy_messages(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


# === Batch 1: Core Edits ===


@router.post("/{message_id}/edit-caption")
async def edit_caption_api(message_id: int, payload: EditMessageCaptionIn) -> dict[str, Any]:
    """Редактирование подписи к медиа-сообщению."""
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await resolve_bot_context(target_bot_id)

    telegram_payload: dict[str, Any] = {
        "chat_id": row["chat_id"],
        "message_id": row["telegram_message_id"],
    }
    if payload.caption is not None:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.show_caption_above_media is not None:
        telegram_payload["show_caption_above_media"] = payload.show_caption_above_media

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await edit_message_caption(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{message_id}/edit-markup")
async def edit_reply_markup_api(message_id: int, payload: EditMessageReplyMarkupIn) -> dict[str, Any]:
    """Изменение inline-клавиатуры существующего сообщения."""
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await resolve_bot_context(target_bot_id)

    telegram_payload: dict[str, Any] = {
        "chat_id": row["chat_id"],
        "message_id": row["telegram_message_id"],
    }
    if payload.reply_markup is not None:
        telegram_payload["reply_markup"] = payload.reply_markup

    try:
        result = await edit_message_reply_markup(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{message_id}/edit-media")
async def edit_media_api(message_id: int, payload: EditMessageMediaIn) -> dict[str, Any]:
    """Замена медиа в существующем сообщении (Bot API 7.11)."""
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await resolve_bot_context(target_bot_id)

    telegram_payload: dict[str, Any] = {
        "chat_id": row["chat_id"],
        "message_id": row["telegram_message_id"],
        "media": payload.media,
    }
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await edit_message_media(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


# === Batch 2: sendMessageDraft (Bot API 9.3) ===


@router.post("/draft")
async def send_message_draft_api(payload: SendMessageDraftIn) -> dict[str, Any]:
    """Стриминг частичного сообщения (Bot API 9.3). Эфемерный, без записи в БД."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {"chat_id": payload.chat_id}
    if payload.text is not None:
        telegram_payload["text"] = payload.text
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id

    try:
        result = await send_message_draft(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


# === Batch 4: Live Location ===


@router.post("/{message_id}/edit-live-location")
async def edit_live_location_api(message_id: int, payload: EditLiveLocationIn) -> dict[str, Any]:
    """Обновление живой геолокации."""
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await resolve_bot_context(target_bot_id)

    telegram_payload: dict[str, Any] = {
        "chat_id": row["chat_id"],
        "message_id": row["telegram_message_id"],
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    }
    if payload.live_period is not None:
        telegram_payload["live_period"] = payload.live_period
    if payload.horizontal_accuracy is not None:
        telegram_payload["horizontal_accuracy"] = payload.horizontal_accuracy
    if payload.heading is not None:
        telegram_payload["heading"] = payload.heading
    if payload.proximity_alert_radius is not None:
        telegram_payload["proximity_alert_radius"] = payload.proximity_alert_radius
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await edit_message_live_location(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


@router.post("/{message_id}/stop-live-location")
async def stop_live_location_api(message_id: int, payload: StopLiveLocationIn) -> dict[str, Any]:
    """Остановка живой геолокации."""
    row = await message_service.get_message(message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    if not row.get("telegram_message_id"):
        raise HTTPException(status_code=409, detail="telegram message_id missing")

    row_bot_id = int(row["bot_id"]) if row.get("bot_id") is not None else None
    target_bot_id = payload.bot_id if payload.bot_id is not None else row_bot_id
    bot_token, _ = await resolve_bot_context(target_bot_id)

    telegram_payload: dict[str, Any] = {
        "chat_id": row["chat_id"],
        "message_id": row["telegram_message_id"],
    }
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup

    try:
        result = await stop_message_live_location(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}
