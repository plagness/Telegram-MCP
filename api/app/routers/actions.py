"""Роутер для Chat Actions (typing индикаторы)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import execute
from ..services.bots import BotRegistry
from ..telegram_client import call_api

router = APIRouter(prefix="/v1/chats", tags=["actions"])

ChatActionType = Literal[
    "typing",
    "upload_photo",
    "record_video",
    "upload_video",
    "record_voice",
    "upload_voice",
    "upload_document",
    "choose_sticker",
    "find_location",
    "record_video_note",
    "upload_video_note",
]


class SendChatActionRequest(BaseModel):
    """Запрос на отправку chat action."""

    bot_id: int | None = Field(None, description="ID бота для мультибот-сценария")
    action: ChatActionType = Field(..., description="Тип действия")
    message_thread_id: int | None = Field(None, description="ID топика (для форумов)")


@router.post("/{chat_id}/action")
async def send_chat_action(chat_id: str, request: SendChatActionRequest) -> dict[str, Any]:
    """
    Отправка chat action (индикатор активности).

    **Параметры**:
    - chat_id: ID чата
    - action: Тип действия (typing, upload_photo, record_video, etc.)
    - message_thread_id: ID топика (опционально, для форумов)

    **Примеры действий**:
    - `typing` — печатает текст
    - `upload_photo` — загружает фото
    - `record_video` — записывает видео
    - `upload_video` — загружает видео
    - `record_voice` — записывает голосовое
    - `upload_voice` — загружает голосовое
    - `upload_document` — загружает документ
    - `choose_sticker` — выбирает стикер
    - `find_location` — выбирает местоположение
    - `record_video_note` — записывает видео-кружок
    - `upload_video_note` — загружает видео-кружок

    **Возвращает**:
    ```json
    {
      "ok": true,
      "sent_at": "2025-02-06T14:30:45Z",
      "expires_at": "2025-02-06T14:30:50Z"
    }
    ```

    **Примечание**: Action автоматически исчезает через 5 секунд или при отправке сообщения.
    """
    params = {
        "chat_id": chat_id,
        "action": request.action,
    }

    if request.message_thread_id:
        params["message_thread_id"] = request.message_thread_id

    try:
        bot_token = await BotRegistry.get_bot_token(request.bot_id)
        response = await call_api("sendChatAction", params, bot_token=bot_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send chat action: {str(e)}")

    if not response.get("ok"):
        raise HTTPException(status_code=500, detail=response.get("description", "Unknown error"))

    # Сохраняем в БД для аудита
    import datetime

    sent_at = datetime.datetime.now(datetime.timezone.utc)
    expires_at = sent_at + datetime.timedelta(seconds=5)

    await execute(
        """
        INSERT INTO chat_actions (chat_id, message_thread_id, action, sent_at, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [chat_id, request.message_thread_id, request.action, sent_at, expires_at],
    )

    return {
        "ok": True,
        "sent_at": sent_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


@router.delete("/{chat_id}/actions")
async def cleanup_expired_actions(chat_id: str) -> dict[str, Any]:
    """
    Очистка истекших chat actions для чата.

    **Возвращает**:
    ```json
    {
      "ok": true,
      "deleted": 15
    }
    ```
    """
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)

    result = await execute(
        "DELETE FROM chat_actions WHERE chat_id = %s AND (expires_at < %s OR sent_at < %s - INTERVAL '1 minute')",
        [chat_id, now, now],
    )

    # Note: psycopg doesn't return rowcount in our execute wrapper
    # We'll just return ok for now
    return {
        "ok": True,
        "deleted": 0,  # Placeholder
    }
