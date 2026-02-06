"""Эндпоинты для отправки медиа: фото, документы, видео."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form

from ..models import SendPhotoIn, SendDocumentIn, SendVideoIn
from ..services import messages as message_service
from ..telegram_client import TelegramError, send_photo, send_document, send_video

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
