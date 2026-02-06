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
)

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

    row = await message_service.create_message(
        chat_id=payload.chat_id,
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

    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_photo(telegram_payload)
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
        result = await send_photo(form_data, photo_file=photo_file)
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

    row = await message_service.create_message(
        chat_id=payload.chat_id,
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

    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_document(telegram_payload)
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

    row = await message_service.create_message(
        chat_id=payload.chat_id,
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

    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_video(telegram_payload)
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

    # Dry run
    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    # Отправляем через Telegram API
    try:
        result = await send_media_group(telegram_payload)
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

        # TODO: Обновить telegram_message_id через update_message
        saved_messages.append(row)

    return {
        "ok": True,
        "messages": saved_messages,
        "media_group_id": media_group_id,
    }


@router.post("/send-animation")
async def send_animation_api(payload: SendAnimationIn) -> dict[str, Any]:
    """Отправка анимации/GIF по URL или file_id."""
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

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    try:
        result = await send_animation(telegram_payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-audio")
async def send_audio_api(payload: SendAudioIn) -> dict[str, Any]:
    """Отправка аудио по URL или file_id."""
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

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    try:
        result = await send_audio(telegram_payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-voice")
async def send_voice_api(payload: SendVoiceIn) -> dict[str, Any]:
    """Отправка голосового сообщения по URL или file_id."""
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

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    try:
        result = await send_voice(telegram_payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}


@router.post("/send-sticker")
async def send_sticker_api(payload: SendStickerIn) -> dict[str, Any]:
    """Отправка стикера по file_id."""
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "sticker": payload.sticker,
    }
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id

    if payload.dry_run:
        return {"ok": True, "dry_run": True, "payload": telegram_payload}

    try:
        result = await send_sticker(telegram_payload)
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "result": result}
