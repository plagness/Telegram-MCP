"""
HTTP-клиент к Telegram Bot API.

Единый httpx.AsyncClient с connection pool, retry при 429 и multipart-upload.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, BinaryIO

import httpx

from .config import get_settings

_settings = get_settings()
logger = logging.getLogger(__name__)

# --- Singleton HTTP-клиент ---

_client: httpx.AsyncClient | None = None

_MAX_RETRIES = 3
_TIMEOUT = 30.0


async def get_client() -> httpx.AsyncClient:
    """Возвращает переиспользуемый AsyncClient (ленивая инициализация)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


async def close_client() -> None:
    """Закрытие клиента при остановке приложения."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


class TelegramError(RuntimeError):
    """Ошибка от Telegram Bot API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# --- Внутренние вызовы ---


def _build_url(method: str) -> str:
    base = _settings.telegram_api_base.rstrip("/")
    return f"{base}/bot{_settings.telegram_bot_token}/{method}"


async def _call(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    """JSON-запрос к Telegram Bot API с retry при 429."""
    url = _build_url(method)
    client = await get_client()

    for attempt in range(1, _MAX_RETRIES + 1):
        resp = await client.post(url, json=payload)

        if resp.status_code == 429:
            # Telegram rate limit — ждём Retry-After
            data = resp.json()
            retry_after = data.get("parameters", {}).get("retry_after", 1)
            logger.warning(
                "Telegram 429 (retry_after=%s) attempt %d/%d for %s",
                retry_after, attempt, _MAX_RETRIES, method,
            )
            await asyncio.sleep(retry_after)
            continue

        if resp.status_code >= 500 and attempt < _MAX_RETRIES:
            # Telegram 5xx — экспоненциальный backoff
            delay = 2 ** (attempt - 1)
            logger.warning(
                "Telegram %d, retry in %ds (attempt %d/%d) for %s",
                resp.status_code, delay, attempt, _MAX_RETRIES, method,
            )
            await asyncio.sleep(delay)
            continue

        break

    data = resp.json()
    if not data.get("ok"):
        raise TelegramError(
            data.get("description") or f"telegram api error ({resp.status_code})",
            status_code=resp.status_code,
        )
    return data.get("result") or {}


async def call_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Публичный API для вызова Telegram Bot API методов.

    Возвращает полный ответ с "ok" и "result" (в отличие от _call, который возвращает только result).
    """
    url = _build_url(method)
    client = await get_client()

    for attempt in range(1, _MAX_RETRIES + 1):
        resp = await client.post(url, json=payload)

        if resp.status_code == 429:
            data = resp.json()
            retry_after = data.get("parameters", {}).get("retry_after", 1)
            logger.warning(
                "Telegram 429 (retry_after=%s) attempt %d/%d for %s",
                retry_after, attempt, _MAX_RETRIES, method,
            )
            await asyncio.sleep(retry_after)
            continue

        if resp.status_code >= 500 and attempt < _MAX_RETRIES:
            delay = 2 ** (attempt - 1)
            logger.warning(
                "Telegram %d, retry in %ds (attempt %d/%d) for %s",
                resp.status_code, delay, attempt, _MAX_RETRIES, method,
            )
            await asyncio.sleep(delay)
            continue

        break

    # Возвращаем полный ответ (включая "ok" и "result")
    return resp.json()


async def _call_multipart(
    method: str,
    data: dict[str, Any],
    files: dict[str, tuple[str, BinaryIO | bytes, str]],
) -> dict[str, Any]:
    """
    Multipart/form-data запрос к Telegram Bot API.

    files: {"photo": ("chart.png", file_bytes, "image/png")}
    """
    url = _build_url(method)
    client = await get_client()

    for attempt in range(1, _MAX_RETRIES + 1):
        resp = await client.post(url, data=data, files=files)

        if resp.status_code == 429:
            retry_data = resp.json()
            retry_after = retry_data.get("parameters", {}).get("retry_after", 1)
            logger.warning(
                "Telegram 429 (retry_after=%s) attempt %d/%d for %s (multipart)",
                retry_after, attempt, _MAX_RETRIES, method,
            )
            await asyncio.sleep(retry_after)
            continue

        if resp.status_code >= 500 and attempt < _MAX_RETRIES:
            delay = 2 ** (attempt - 1)
            logger.warning(
                "Telegram %d, retry in %ds (attempt %d/%d) for %s (multipart)",
                resp.status_code, delay, attempt, _MAX_RETRIES, method,
            )
            await asyncio.sleep(delay)
            continue

        break

    resp_data = resp.json()
    if not resp_data.get("ok"):
        raise TelegramError(
            resp_data.get("description") or f"telegram api error ({resp.status_code})",
            status_code=resp.status_code,
        )
    return resp_data.get("result") or {}


# === Сообщения ===


async def send_message(payload: dict[str, Any]) -> dict[str, Any]:
    """sendMessage — отправка текстового сообщения."""
    return await _call("sendMessage", payload)


async def edit_message_text(payload: dict[str, Any]) -> dict[str, Any]:
    """editMessageText — редактирование текста сообщения."""
    return await _call("editMessageText", payload)


async def delete_message(payload: dict[str, Any]) -> dict[str, Any]:
    """deleteMessage — удаление сообщения."""
    return await _call("deleteMessage", payload)


async def forward_message(payload: dict[str, Any]) -> dict[str, Any]:
    """forwardMessage — пересылка сообщения."""
    return await _call("forwardMessage", payload)


async def copy_message(payload: dict[str, Any]) -> dict[str, Any]:
    """copyMessage — копирование сообщения."""
    return await _call("copyMessage", payload)


async def pin_chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    """pinChatMessage — закрепление сообщения в чате."""
    return await _call("pinChatMessage", payload)


async def unpin_chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    """unpinChatMessage — открепление сообщения в чате."""
    return await _call("unpinChatMessage", payload)


# === Медиа ===


async def send_photo(
    data: dict[str, Any],
    photo_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """
    sendPhoto — отправка фото.

    Если photo_file задан — загрузка файла (multipart).
    Если data содержит 'photo' как строку — URL или file_id (JSON).
    """
    if photo_file:
        return await _call_multipart("sendPhoto", data, {"photo": photo_file})
    return await _call("sendPhoto", data)


async def send_document(
    data: dict[str, Any],
    document_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """sendDocument — отправка документа/файла."""
    if document_file:
        return await _call_multipart("sendDocument", data, {"document": document_file})
    return await _call("sendDocument", data)


async def send_video(
    data: dict[str, Any],
    video_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """sendVideo — отправка видео."""
    if video_file:
        return await _call_multipart("sendVideo", data, {"video": video_file})
    return await _call("sendVideo", data)


async def send_animation(
    data: dict[str, Any],
    animation_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """sendAnimation — отправка GIF."""
    if animation_file:
        return await _call_multipart("sendAnimation", data, {"animation": animation_file})
    return await _call("sendAnimation", data)


async def send_voice(
    data: dict[str, Any],
    voice_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """sendVoice — отправка голосового сообщения."""
    if voice_file:
        return await _call_multipart("sendVoice", data, {"voice": voice_file})
    return await _call("sendVoice", data)


async def send_audio(
    data: dict[str, Any],
    audio_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """sendAudio — отправка аудио."""
    if audio_file:
        return await _call_multipart("sendAudio", data, {"audio": audio_file})
    return await _call("sendAudio", data)


async def send_sticker(
    data: dict[str, Any],
    sticker_file: tuple[str, BinaryIO | bytes, str] | None = None,
) -> dict[str, Any]:
    """sendSticker — отправка стикера."""
    if sticker_file:
        return await _call_multipart("sendSticker", data, {"sticker": sticker_file})
    return await _call("sendSticker", data)


async def send_media_group(payload: dict[str, Any]) -> dict[str, Any]:
    """sendMediaGroup — отправка альбома (медиагруппы)."""
    return await _call("sendMediaGroup", payload)


# === Callback Query ===


async def answer_callback_query(payload: dict[str, Any]) -> dict[str, Any]:
    """answerCallbackQuery — ответ на нажатие inline-кнопки."""
    return await _call("answerCallbackQuery", payload)


# === Чаты и участники ===


async def get_chat(payload: dict[str, Any]) -> dict[str, Any]:
    """getChat — информация о чате."""
    return await _call("getChat", payload)


async def get_chat_member(payload: dict[str, Any]) -> dict[str, Any]:
    """getChatMember — информация об участнике чата."""
    return await _call("getChatMember", payload)


async def get_chat_member_count(payload: dict[str, Any]) -> dict[str, Any]:
    """getChatMemberCount — число участников чата."""
    return await _call("getChatMemberCount", payload)


# === Команды бота ===


async def set_my_commands(payload: dict[str, Any]) -> dict[str, Any]:
    """setMyCommands — установка списка команд по скоупу."""
    return await _call("setMyCommands", payload)


async def delete_my_commands(payload: dict[str, Any]) -> dict[str, Any]:
    """deleteMyCommands — удаление списка команд."""
    return await _call("deleteMyCommands", payload)


async def get_my_commands(payload: dict[str, Any]) -> dict[str, Any]:
    """getMyCommands — получение текущих команд."""
    return await _call("getMyCommands", payload)


# === Вебхуки ===


async def set_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """setWebhook — настройка вебхука."""
    return await _call("setWebhook", payload)


async def delete_webhook(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """deleteWebhook — удаление вебхука."""
    return await _call("deleteWebhook", payload or {})


async def get_webhook_info() -> dict[str, Any]:
    """getWebhookInfo — текущая конфигурация вебхука."""
    return await _call("getWebhookInfo", {})


# === Прочее ===


async def get_me() -> dict[str, Any]:
    """getMe — информация о боте."""
    return await _call("getMe", {})


async def pin_chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    """pinChatMessage — закрепить сообщение."""
    return await _call("pinChatMessage", payload)


async def unpin_chat_message(payload: dict[str, Any]) -> dict[str, Any]:
    """unpinChatMessage — открепить сообщение."""
    return await _call("unpinChatMessage", payload)


# === Опросы ===


async def send_poll(payload: dict[str, Any]) -> dict[str, Any]:
    """sendPoll — создание опроса или викторины."""
    return await _call("sendPoll", payload)


async def stop_poll(payload: dict[str, Any]) -> dict[str, Any]:
    """stopPoll — остановка опроса с показом результатов."""
    return await _call("stopPoll", payload)


# === Реакции ===


async def set_message_reaction(payload: dict[str, Any]) -> dict[str, Any]:
    """setMessageReaction — установка реакции на сообщение."""
    return await _call("setMessageReaction", payload)


# === Chat Management ===


async def ban_chat_member(payload: dict[str, Any]) -> dict[str, Any]:
    """banChatMember — блокировка участника чата."""
    return await _call("banChatMember", payload)


async def unban_chat_member(payload: dict[str, Any]) -> dict[str, Any]:
    """unbanChatMember — разблокировка участника чата."""
    return await _call("unbanChatMember", payload)


async def restrict_chat_member(payload: dict[str, Any]) -> dict[str, Any]:
    """restrictChatMember — ограничение прав участника."""
    return await _call("restrictChatMember", payload)


async def promote_chat_member(payload: dict[str, Any]) -> dict[str, Any]:
    """promoteChatMember — повышение участника до админа."""
    return await _call("promoteChatMember", payload)


async def set_chat_administrator_custom_title(payload: dict[str, Any]) -> dict[str, Any]:
    """setChatAdministratorCustomTitle — установка кастомного титула админа."""
    return await _call("setChatAdministratorCustomTitle", payload)


# === Checklists (Bot API 9.1) ===


async def send_checklist(payload: dict[str, Any]) -> dict[str, Any]:
    """sendChecklist — отправка чек-листа (Bot API 9.1)."""
    return await _call("sendChecklist", payload)


async def edit_message_checklist(payload: dict[str, Any]) -> dict[str, Any]:
    """editMessageChecklist — редактирование чек-листа."""
    return await _call("editMessageChecklist", payload)


# === Stars & Gifts (Bot API 9.1+) ===


async def get_my_star_balance() -> dict[str, Any]:
    """getMyStarBalance — баланс звёзд бота (Bot API 9.1)."""
    return await _call("getMyStarBalance", {})


async def get_user_gifts(payload: dict[str, Any]) -> dict[str, Any]:
    """getUserGifts — подарки пользователя (Bot API 9.3)."""
    return await _call("getUserGifts", payload)


async def get_chat_gifts(payload: dict[str, Any]) -> dict[str, Any]:
    """getChatGifts — подарки в чате (Bot API 9.3)."""
    return await _call("getChatGifts", payload)


async def gift_premium_subscription(payload: dict[str, Any]) -> dict[str, Any]:
    """giftPremiumSubscription — подарить премиум за звёзды (Bot API 9.3)."""
    return await _call("giftPremiumSubscription", payload)


# === Stories (Bot API 9.3) ===


async def repost_story(payload: dict[str, Any]) -> dict[str, Any]:
    """repostStory — репост истории в канал (Bot API 9.3)."""
    return await _call("repostStory", payload)
