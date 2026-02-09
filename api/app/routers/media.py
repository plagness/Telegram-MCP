"""Эндпоинты для отправки медиа: фото, документы, видео."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from ..models import (
    SendPhotoIn,
    SendDocumentIn,
    SendVideoIn,
    SendAnimationIn,
    SendAudioIn,
    SendVoiceIn,
    SendStickerIn,
    SendMediaGroupIn,
    GetFileIn,
    SendLocationIn,
    SendVenueIn,
    SendContactIn,
    SendDiceIn,
    SendVideoNoteIn,
    SendPaidMediaIn,
)
from ..services import messages as message_service
from ..telegram_client import (
    TelegramError,
    send_photo,
    send_document,
    send_video,
    send_animation,
    send_audio,
    send_voice,
    send_sticker,
    send_media_group,
    get_file,
    send_location,
    send_venue,
    send_contact,
    send_dice,
    send_video_note,
    send_paid_media,
)
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/media", tags=["media"])


@router.post("/send-photo")
async def send_photo_json(payload: SendPhotoIn) -> dict[str, Any]:
    """Отправка фото по URL или file_id (JSON body)."""
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "photo": payload.photo,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.show_caption_above_media is not None:
        telegram_payload["show_caption_above_media"] = payload.show_caption_above_media
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
        text=payload.caption,
        parse_mode=payload.parse_mode,
        status="queued" if not payload.dry_run else "dry_run",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="photo",
    )
    if payload.dry_run:
        return {"message": row, "dry_run": True}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_photo(telegram_payload, bot_token=bot_token)
        await message_service.update_message(
            row["id"],
            status="sent",
            telegram_message_id=result.get("message_id"),
            sent=True,
            media_file_id=_extract_file_id(result, "photo"),
        )
        await message_service.add_event(row["id"], "send_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "send_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/upload-photo")
async def upload_photo(
    bot_id: int | None = Form(None),
    chat_id: str = Form(...),
    caption: str | None = Form(None),
    parse_mode: str | None = Form(None),
    reply_to_message_id: int | None = Form(None),
    message_thread_id: int | None = Form(None),
    request_id: str | None = Form(None),
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Загрузка фото файлом (multipart/form-data)."""
    bot_token, resolved_bot_id = await resolve_bot_context(bot_id)
    form_data: dict[str, Any] = {"chat_id": chat_id}
    if caption:
        form_data["caption"] = caption
    if parse_mode:
        form_data["parse_mode"] = parse_mode
    if reply_to_message_id:
        form_data["reply_to_message_id"] = str(reply_to_message_id)
    if message_thread_id:
        form_data["message_thread_id"] = str(message_thread_id)

    row = await message_service.create_message(
        chat_id=chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=caption,
        parse_mode=parse_mode,
        status="queued" if not dry_run else "dry_run",
        request_id=request_id,
        payload={"chat_id": chat_id, "caption": caption, "file": file.filename},
        is_live=False,
        reply_to_message_id=reply_to_message_id,
        message_thread_id=message_thread_id,
        message_type="photo",
    )
    if dry_run:
        return {"message": row, "dry_run": True}

    file_bytes = await file.read()
    content_type = file.content_type or "image/jpeg"
    photo_file = (file.filename or "photo.jpg", file_bytes, content_type)

    try:
        await message_service.add_event(row["id"], "send_attempt", form_data)
        result = await send_photo(form_data, photo_file=photo_file, bot_token=bot_token)
        await message_service.update_message(
            row["id"],
            status="sent",
            telegram_message_id=result.get("message_id"),
            sent=True,
            media_file_id=_extract_file_id(result, "photo"),
        )
        await message_service.add_event(row["id"], "send_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "send_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/send-document")
async def send_document_json(payload: SendDocumentIn) -> dict[str, Any]:
    """Отправка документа по URL или file_id."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "document": payload.document,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=payload.caption,
        parse_mode=payload.parse_mode,
        status="queued" if not payload.dry_run else "dry_run",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="document",
    )
    if payload.dry_run:
        return {"message": row, "dry_run": True}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_document(telegram_payload, bot_token=bot_token)
        await message_service.update_message(
            row["id"],
            status="sent",
            telegram_message_id=result.get("message_id"),
            sent=True,
            media_file_id=_extract_file_id(result, "document"),
        )
        await message_service.add_event(row["id"], "send_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "send_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/send-video")
async def send_video_json(payload: SendVideoIn) -> dict[str, Any]:
    """Отправка видео по URL или file_id."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "video": payload.video,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.show_caption_above_media is not None:
        telegram_payload["show_caption_above_media"] = payload.show_caption_above_media
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=payload.caption,
        parse_mode=payload.parse_mode,
        status="queued" if not payload.dry_run else "dry_run",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="video",
    )
    if payload.dry_run:
        return {"message": row, "dry_run": True}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_video(telegram_payload, bot_token=bot_token)
        await message_service.update_message(
            row["id"],
            status="sent",
            telegram_message_id=result.get("message_id"),
            sent=True,
            media_file_id=_extract_file_id(result, "video"),
        )
        await message_service.add_event(row["id"], "send_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "send_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


def _extract_file_id(result: dict[str, Any], media_type: str) -> str | None:
    """Извлечение file_id из ответа Telegram."""
    if media_type == "photo":
        # Telegram возвращает массив PhotoSize, берём самый большой
        photos = result.get("photo", [])
        if photos:
            return photos[-1].get("file_id")
    elif media_type in ("document", "video", "animation", "voice", "sticker"):
        media = result.get(media_type, {})
        if isinstance(media, dict):
            return media.get("file_id")
    return None


@router.post("/send-media-group")
async def send_media_group_api(payload: SendMediaGroupIn) -> dict[str, Any]:
    """
    Отправка медиа-группы (альбома из 2-10 фото/видео).

    **Параметры**:
    - chat_id: ID чата
    - media: Список из 2-10 элементов (InputMedia)
    - reply_to_message_id: ID сообщения для ответа (опционально)
    - message_thread_id: ID топика/форума (опционально)

    **Примечание**: Только первый элемент может иметь caption.

    **Возвращает**:
    ```json
    {
      "ok": true,
      "messages": [...],
      "media_group_id": "123456789"
    }
    ```
    """
    # Формируем payload для Telegram
    media_array = [item.model_dump(exclude_none=True) for item in payload.media]

    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "media": media_array,
    }
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)

    # Dry run
    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    # Отправляем через Telegram API
    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_media_group(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Сохраняем в БД (создаём записи для каждого сообщения в группе)
    messages = result if isinstance(result, list) else [result]
    media_group_id = messages[0].get("media_group_id") if messages else None

    saved_messages = []
    for msg in messages:
        telegram_message_id = msg.get("message_id")
        text_content = msg.get("caption", "")

        # Определяем тип медиа
        message_type = "photo"
        if "video" in msg:
            message_type = "video"
        elif "document" in msg:
            message_type = "document"

        row = await message_service.create_message(
            chat_id=payload.chat_id,
            bot_id=resolved_bot_id,
            direction="outbound",
            text=text_content,
            parse_mode=None,  # parse_mode обязательный параметр
            status="sent",
            request_id=payload.request_id,
            payload=telegram_payload,
            is_live=False,
            reply_to_message_id=payload.reply_to_message_id,
            message_thread_id=payload.message_thread_id,
            message_type=message_type,
        )

        await message_service.update_message(
            row["id"],
            telegram_message_id=telegram_message_id,
            sent=True,
        )
        saved_messages.append(await message_service.get_message(row["id"]))

    return {
        "ok": True,
        "messages": saved_messages,
        "media_group_id": media_group_id,
    }


@router.post("/send-animation")
async def send_animation_api(payload: SendAnimationIn) -> dict[str, Any]:
    """Отправка анимации/GIF по URL или file_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "animation": payload.animation,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.show_caption_above_media is not None:
        telegram_payload["show_caption_above_media"] = payload.show_caption_above_media
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_animation(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-audio")
async def send_audio_api(payload: SendAudioIn) -> dict[str, Any]:
    """Отправка аудио по URL или file_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "audio": payload.audio,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.duration:
        telegram_payload["duration"] = payload.duration
    if payload.performer:
        telegram_payload["performer"] = payload.performer
    if payload.title:
        telegram_payload["title"] = payload.title
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_audio(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-voice")
async def send_voice_api(payload: SendVoiceIn) -> dict[str, Any]:
    """Отправка голосового сообщения по URL или file_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "voice": payload.voice,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.duration:
        telegram_payload["duration"] = payload.duration
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_voice(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-sticker")
async def send_sticker_api(payload: SendStickerIn) -> dict[str, Any]:
    """Отправка стикера по file_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "sticker": payload.sticker,
    }
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_sticker(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


# === Batch 1: getFile ===


@router.post("/get-file")
async def get_file_api(payload: GetFileIn) -> dict[str, Any]:
    """Получить file_path для скачивания файла по file_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    try:
        result = await get_file({"file_id": payload.file_id}, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "result": result}


# === Batch 3: Базовые send-методы ===


@router.post("/send-location")
async def send_location_api(payload: SendLocationIn) -> dict[str, Any]:
    """Отправка геолокации (+ live location при задании live_period)."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    }
    if payload.horizontal_accuracy is not None:
        telegram_payload["horizontal_accuracy"] = payload.horizontal_accuracy
    if payload.live_period is not None:
        telegram_payload["live_period"] = payload.live_period
    if payload.heading is not None:
        telegram_payload["heading"] = payload.heading
    if payload.proximity_alert_radius is not None:
        telegram_payload["proximity_alert_radius"] = payload.proximity_alert_radius
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_location(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=f"📍 {payload.latitude}, {payload.longitude}",
        parse_mode=None,
        status="sent",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=bool(payload.live_period),
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="location",
    )
    await message_service.update_message(
        row["id"], telegram_message_id=result.get("message_id"), sent=True,
    )
    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/send-venue")
async def send_venue_api(payload: SendVenueIn) -> dict[str, Any]:
    """Отправка места (venue) с адресом и координатами."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "title": payload.title,
        "address": payload.address,
    }
    if payload.foursquare_id:
        telegram_payload["foursquare_id"] = payload.foursquare_id
    if payload.foursquare_type:
        telegram_payload["foursquare_type"] = payload.foursquare_type
    if payload.google_place_id:
        telegram_payload["google_place_id"] = payload.google_place_id
    if payload.google_place_type:
        telegram_payload["google_place_type"] = payload.google_place_type
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_venue(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=f"📍 {payload.title} — {payload.address}",
        parse_mode=None,
        status="sent",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="venue",
    )
    await message_service.update_message(
        row["id"], telegram_message_id=result.get("message_id"), sent=True,
    )
    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/send-contact")
async def send_contact_api(payload: SendContactIn) -> dict[str, Any]:
    """Отправка контакта (телефон + имя)."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "phone_number": payload.phone_number,
        "first_name": payload.first_name,
    }
    if payload.last_name:
        telegram_payload["last_name"] = payload.last_name
    if payload.vcard:
        telegram_payload["vcard"] = payload.vcard
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_contact(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=f"{payload.first_name} {payload.phone_number}",
        parse_mode=None,
        status="sent",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="contact",
    )
    await message_service.update_message(
        row["id"], telegram_message_id=result.get("message_id"), sent=True,
    )
    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/send-dice")
async def send_dice_api(payload: SendDiceIn) -> dict[str, Any]:
    """Отправка анимированного эмодзи (🎲🎯🏀⚽🎳🎰)."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {"chat_id": payload.chat_id}
    if payload.emoji:
        telegram_payload["emoji"] = payload.emoji
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_dice(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-video-note")
async def send_video_note_api(payload: SendVideoNoteIn) -> dict[str, Any]:
    """Отправка видео-кружка (video note) по URL или file_id."""
    bot_token, _ = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "video_note": payload.video_note,
    }
    if payload.duration:
        telegram_payload["duration"] = payload.duration
    if payload.length:
        telegram_payload["length"] = payload.length
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.message_effect_id:
        telegram_payload["message_effect_id"] = payload.message_effect_id
    if payload.business_connection_id:
        telegram_payload["business_connection_id"] = payload.business_connection_id
    if payload.allow_paid_broadcast is not None:
        telegram_payload["allow_paid_broadcast"] = payload.allow_paid_broadcast

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_video_note(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


# === Batch 8: sendPaidMedia ===


@router.post("/send-paid-media")
async def send_paid_media_api(payload: SendPaidMediaIn) -> dict[str, Any]:
    """Отправка платного медиа-контента (Bot API 7.6)."""
    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "star_count": payload.star_count,
        "media": payload.media,
    }
    if payload.caption:
        telegram_payload["caption"] = payload.caption
    if payload.parse_mode:
        telegram_payload["parse_mode"] = payload.parse_mode
    if payload.show_caption_above_media is not None:
        telegram_payload["show_caption_above_media"] = payload.show_caption_above_media
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    if payload.direct_messages_topic_id is not None:
        telegram_payload["direct_messages_topic_id"] = payload.direct_messages_topic_id
    if payload.suggested_post_parameters is not None:
        telegram_payload["suggested_post_parameters"] = payload.suggested_post_parameters
    try:
        result = await send_paid_media(telegram_payload, bot_token=bot_token)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    row = await message_service.create_message(
        chat_id=payload.chat_id,
        bot_id=resolved_bot_id,
        direction="outbound",
        text=payload.caption,
        parse_mode=payload.parse_mode,
        status="sent",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="paid_media",
    )
    await message_service.update_message(
        row["id"], telegram_message_id=result.get("message_id"), sent=True,
    )
    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}
