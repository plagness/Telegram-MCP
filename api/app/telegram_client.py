"""
HTTP client for Telegram Bot API.

Features:
- Single shared httpx.AsyncClient
- Retry policy for 429/5xx
- Optional per-call bot token override
- Contextual bot token override (for webhook workers)
- Non-blocking activity logging into api_activity_log
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, BinaryIO

import httpx

from .config import get_settings
from .services.activity import log_activity_background
from .services.bots import BotRegistry

_settings = get_settings()
logger = logging.getLogger(__name__)

# --- Singleton HTTP client ---

_client: httpx.AsyncClient | None = None

_MAX_RETRIES = 3
_TIMEOUT = 30.0

# Context-local override (used by webhook routes bound to a specific bot).
_current_bot_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "telegram_bot_token_override",
    default=None,
)


async def get_client() -> httpx.AsyncClient:
    """Return a reused AsyncClient instance (lazy initialization)."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


async def close_client() -> None:
    """Close HTTP client on app shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None


@asynccontextmanager
async def using_bot_token(bot_token: str | None):
    """Temporarily set default bot token for all Telegram calls in this task."""
    if not bot_token:
        yield
        return

    token = _current_bot_token.set(bot_token)
    try:
        yield
    finally:
        _current_bot_token.reset(token)


class TelegramError(RuntimeError):
    """Telegram Bot API error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _token_hint(token: str | None) -> str:
    if not token:
        return "unknown"
    suffix = token[-6:] if len(token) >= 6 else token
    return f"*{suffix}"


async def _resolve_bot_token(bot_token: str | None = None) -> str:
    if bot_token:
        return bot_token

    contextual = _current_bot_token.get()
    if contextual:
        return contextual

    return await BotRegistry.get_bot_token()


def _build_url(method: str, bot_token: str) -> str:
    base = _settings.telegram_api_base.rstrip("/")
    return f"{base}/bot{bot_token}/{method}"


def _extract_actor(payload: dict[str, Any] | None = None, data: dict[str, Any] | None = None) -> tuple[str | int | None, str | int | None]:
    source = payload or data or {}
    return source.get("chat_id"), source.get("user_id")


def _build_activity_metadata(
    *,
    method: str,
    attempts: int,
    http_status: int | None,
    multipart: bool,
    payload: dict[str, Any] | None,
    data: dict[str, Any] | None,
) -> dict[str, Any]:
    source = payload or data or {}
    return {
        "method": method,
        "attempts": attempts,
        "http_status": http_status,
        "multipart": multipart,
        "payload_keys": sorted(source.keys()),
    }


def _record_activity_async(
    *,
    method: str,
    bot_token: str | None,
    status: str,
    duration_ms: int,
    payload: dict[str, Any] | None,
    data: dict[str, Any] | None,
    error: str | None,
    attempts: int,
    http_status: int | None,
    multipart: bool,
) -> None:
    async def _worker() -> None:
        bot_id: int | None = None
        bot_username: str | None = None
        if bot_token:
            try:
                bot_row = await BotRegistry.get_bot_by_token(bot_token)
                if bot_row:
                    raw_bot_id = bot_row.get("bot_id")
                    if raw_bot_id is not None:
                        bot_id = int(raw_bot_id)
                    bot_username = bot_row.get("username")
            except Exception:
                pass

        chat_id, user_id = _extract_actor(payload=payload, data=data)
        metadata = _build_activity_metadata(
            method=method,
            attempts=attempts,
            http_status=http_status,
            multipart=multipart,
            payload=payload,
            data=data,
        )
        log_activity_background(
            bot_id=bot_id,
            bot_username=bot_username,
            action=method,
            chat_id=chat_id,
            user_id=user_id,
            status=status,
            error=error,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    try:
        asyncio.create_task(_worker())
    except RuntimeError:
        # No running event loop (for example during process teardown).
        pass


async def _post_with_retry(
    *,
    url: str,
    method: str,
    json_payload: dict[str, Any] | None = None,
    data_payload: dict[str, Any] | None = None,
    files: dict[str, tuple[str, BinaryIO | bytes, str]] | None = None,
) -> tuple[httpx.Response, int]:
    client = await get_client()

    for attempt in range(1, _MAX_RETRIES + 1):
        if files is not None:
            resp = await client.post(url, data=data_payload or {}, files=files)
        else:
            resp = await client.post(url, json=json_payload or {})

        if resp.status_code == 429 and attempt < _MAX_RETRIES:
            retry_after = 1
            try:
                retry_data = resp.json()
                retry_after = int(retry_data.get("parameters", {}).get("retry_after", 1))
            except Exception:
                retry_after = 1
            logger.warning(
                "Telegram 429 (retry_after=%s) attempt %d/%d for %s",
                retry_after,
                attempt,
                _MAX_RETRIES,
                method,
            )
            await asyncio.sleep(max(1, retry_after))
            continue

        if resp.status_code >= 500 and attempt < _MAX_RETRIES:
            delay = 2 ** (attempt - 1)
            logger.warning(
                "Telegram %d, retry in %ds (attempt %d/%d) for %s",
                resp.status_code,
                delay,
                attempt,
                _MAX_RETRIES,
                method,
            )
            await asyncio.sleep(delay)
            continue

        return resp, attempt

    # Defensive fallback; loop always returns.
    raise RuntimeError("retry loop ended unexpectedly")


async def _execute_telegram_request(
    method: str,
    *,
    payload: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    files: dict[str, tuple[str, BinaryIO | bytes, str]] | None = None,
    bot_token: str | None = None,
    strict: bool,
    return_full: bool,
) -> dict[str, Any]:
    resolved_token: str | None = None
    attempts = 1
    http_status: int | None = None
    error_text: str | None = None
    status = "error"
    started = time.perf_counter()

    try:
        resolved_token = await _resolve_bot_token(bot_token)
        url = _build_url(method, resolved_token)

        chat_id, _ = _extract_actor(payload=payload, data=data)
        logger.info(
            "telegram.call method=%s chat_id=%s bot=%s",
            method,
            chat_id,
            _token_hint(resolved_token),
        )

        response, attempts = await _post_with_retry(
            url=url,
            method=method,
            json_payload=payload,
            data_payload=data,
            files=files,
        )
        http_status = response.status_code

        try:
            response_data = response.json()
        except Exception as exc:
            raise TelegramError(f"invalid Telegram JSON response: {exc}", status_code=response.status_code) from exc

        is_ok = bool(response_data.get("ok"))
        if not is_ok:
            error_text = response_data.get("description") or f"telegram api error ({response.status_code})"
            if strict:
                raise TelegramError(error_text, status_code=response.status_code)
            status = "error"
            return response_data

        status = "success"
        if return_full:
            return response_data
        return response_data.get("result") or {}
    except TelegramError as exc:
        error_text = error_text or str(exc)
        status = "error"
        raise
    except Exception as exc:
        error_text = error_text or str(exc)
        status = "error"
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _record_activity_async(
            method=method,
            bot_token=resolved_token,
            status=status,
            duration_ms=duration_ms,
            payload=payload,
            data=data,
            error=error_text,
            attempts=attempts,
            http_status=http_status,
            multipart=files is not None,
        )
        logger.info(
            "telegram.result method=%s status=%s ms=%s bot=%s http=%s",
            method,
            status,
            duration_ms,
            _token_hint(resolved_token),
            http_status,
        )


# --- Internal wrappers ---


async def _call(method: str, payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """Strict JSON call to Telegram Bot API (raises TelegramError on !ok)."""
    return await _execute_telegram_request(
        method,
        payload=payload,
        bot_token=bot_token,
        strict=True,
        return_full=False,
    )


async def call_api(method: str, payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """Low-level call that returns raw Telegram payload, including `ok`."""
    return await _execute_telegram_request(
        method,
        payload=payload,
        bot_token=bot_token,
        strict=False,
        return_full=True,
    )


async def _call_multipart(
    method: str,
    data: dict[str, Any],
    files: dict[str, tuple[str, BinaryIO | bytes, str]],
    bot_token: str | None = None,
) -> dict[str, Any]:
    """Strict multipart/form-data call to Telegram Bot API."""
    return await _execute_telegram_request(
        method,
        data=data,
        files=files,
        bot_token=bot_token,
        strict=True,
        return_full=False,
    )


# === Messages ===


async def send_message(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendMessage."""
    return await _call("sendMessage", payload, bot_token=bot_token)


async def edit_message_text(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editMessageText."""
    return await _call("editMessageText", payload, bot_token=bot_token)


async def delete_message(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """deleteMessage."""
    return await _call("deleteMessage", payload, bot_token=bot_token)


async def forward_message(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """forwardMessage."""
    return await _call("forwardMessage", payload, bot_token=bot_token)


async def copy_message(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """copyMessage."""
    return await _call("copyMessage", payload, bot_token=bot_token)


async def pin_chat_message(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """pinChatMessage."""
    return await _call("pinChatMessage", payload, bot_token=bot_token)


async def unpin_chat_message(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """unpinChatMessage."""
    return await _call("unpinChatMessage", payload, bot_token=bot_token)


# === Media ===


async def send_photo(
    data: dict[str, Any],
    photo_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendPhoto."""
    if photo_file:
        return await _call_multipart("sendPhoto", data, {"photo": photo_file}, bot_token=bot_token)
    return await _call("sendPhoto", data, bot_token=bot_token)


async def send_document(
    data: dict[str, Any],
    document_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendDocument."""
    if document_file:
        return await _call_multipart("sendDocument", data, {"document": document_file}, bot_token=bot_token)
    return await _call("sendDocument", data, bot_token=bot_token)


async def send_video(
    data: dict[str, Any],
    video_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendVideo."""
    if video_file:
        return await _call_multipart("sendVideo", data, {"video": video_file}, bot_token=bot_token)
    return await _call("sendVideo", data, bot_token=bot_token)


async def send_animation(
    data: dict[str, Any],
    animation_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendAnimation."""
    if animation_file:
        return await _call_multipart("sendAnimation", data, {"animation": animation_file}, bot_token=bot_token)
    return await _call("sendAnimation", data, bot_token=bot_token)


async def send_voice(
    data: dict[str, Any],
    voice_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendVoice."""
    if voice_file:
        return await _call_multipart("sendVoice", data, {"voice": voice_file}, bot_token=bot_token)
    return await _call("sendVoice", data, bot_token=bot_token)


async def send_audio(
    data: dict[str, Any],
    audio_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendAudio."""
    if audio_file:
        return await _call_multipart("sendAudio", data, {"audio": audio_file}, bot_token=bot_token)
    return await _call("sendAudio", data, bot_token=bot_token)


async def send_sticker(
    data: dict[str, Any],
    sticker_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendSticker."""
    if sticker_file:
        return await _call_multipart("sendSticker", data, {"sticker": sticker_file}, bot_token=bot_token)
    return await _call("sendSticker", data, bot_token=bot_token)


async def send_media_group(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendMediaGroup."""
    return await _call("sendMediaGroup", payload, bot_token=bot_token)


# === Callback Query ===


async def answer_callback_query(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """answerCallbackQuery."""
    return await _call("answerCallbackQuery", payload, bot_token=bot_token)


# === Chats and members ===


async def get_chat(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getChat."""
    return await _call("getChat", payload, bot_token=bot_token)


async def get_chat_member(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getChatMember."""
    return await _call("getChatMember", payload, bot_token=bot_token)


async def get_chat_member_count(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getChatMemberCount."""
    return await _call("getChatMemberCount", payload, bot_token=bot_token)


# === Bot commands ===


async def set_my_commands(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setMyCommands."""
    return await _call("setMyCommands", payload, bot_token=bot_token)


async def delete_my_commands(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """deleteMyCommands."""
    return await _call("deleteMyCommands", payload, bot_token=bot_token)


async def get_my_commands(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getMyCommands."""
    return await _call("getMyCommands", payload, bot_token=bot_token)


# === Webhooks ===


async def set_webhook(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setWebhook."""
    return await _call("setWebhook", payload, bot_token=bot_token)


async def delete_webhook(payload: dict[str, Any] | None = None, bot_token: str | None = None) -> dict[str, Any]:
    """deleteWebhook."""
    return await _call("deleteWebhook", payload or {}, bot_token=bot_token)


async def get_webhook_info(bot_token: str | None = None) -> dict[str, Any]:
    """getWebhookInfo."""
    return await _call("getWebhookInfo", {}, bot_token=bot_token)


# === Misc ===


async def get_me(bot_token: str | None = None) -> dict[str, Any]:
    """getMe."""
    return await _call("getMe", {}, bot_token=bot_token)


# === Polls ===


async def send_poll(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendPoll."""
    return await _call("sendPoll", payload, bot_token=bot_token)


async def stop_poll(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """stopPoll."""
    return await _call("stopPoll", payload, bot_token=bot_token)


# === Reactions ===


async def set_message_reaction(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setMessageReaction."""
    return await _call("setMessageReaction", payload, bot_token=bot_token)


# === Chat management ===


async def ban_chat_member(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """banChatMember."""
    return await _call("banChatMember", payload, bot_token=bot_token)


async def unban_chat_member(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """unbanChatMember."""
    return await _call("unbanChatMember", payload, bot_token=bot_token)


async def restrict_chat_member(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """restrictChatMember."""
    return await _call("restrictChatMember", payload, bot_token=bot_token)


async def promote_chat_member(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """promoteChatMember."""
    return await _call("promoteChatMember", payload, bot_token=bot_token)


async def set_chat_administrator_custom_title(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setChatAdministratorCustomTitle."""
    return await _call("setChatAdministratorCustomTitle", payload, bot_token=bot_token)


# === Checklists (Bot API 9.1) ===


async def send_checklist(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendChecklist."""
    return await _call("sendChecklist", payload, bot_token=bot_token)


async def edit_message_checklist(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editMessageChecklist."""
    return await _call("editMessageChecklist", payload, bot_token=bot_token)


# === Stars & Gifts (Bot API 9.1+) ===


async def get_my_star_balance(bot_token: str | None = None) -> dict[str, Any]:
    """getMyStarBalance."""
    return await _call("getMyStarBalance", {}, bot_token=bot_token)


async def get_user_gifts(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getUserGifts."""
    return await _call("getUserGifts", payload, bot_token=bot_token)


async def get_chat_gifts(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getChatGifts."""
    return await _call("getChatGifts", payload, bot_token=bot_token)


async def gift_premium_subscription(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """giftPremiumSubscription."""
    return await _call("giftPremiumSubscription", payload, bot_token=bot_token)


# === Stories (Bot API 9.3) ===


async def repost_story(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """repostStory."""
    return await _call("repostStory", payload, bot_token=bot_token)


# === Stars payments ===


async def send_invoice(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendInvoice."""
    return await _call("sendInvoice", payload, bot_token=bot_token)


async def create_invoice_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """createInvoiceLink."""
    return await _call("createInvoiceLink", payload, bot_token=bot_token)


async def answer_pre_checkout_query(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """answerPreCheckoutQuery."""
    return await _call("answerPreCheckoutQuery", payload, bot_token=bot_token)


async def refund_star_payment(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """refundStarPayment."""
    return await _call("refundStarPayment", payload, bot_token=bot_token)


async def get_star_transactions(payload: dict[str, Any] | None = None, bot_token: str | None = None) -> dict[str, Any]:
    """getStarTransactions."""
    return await _call("getStarTransactions", payload or {}, bot_token=bot_token)


# === Batch 1: Bulk Operations + Core Edits (Bot API 7.0+) ===


async def delete_messages(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """deleteMessages — массовое удаление (до 100 сообщений)."""
    return await _call("deleteMessages", payload, bot_token=bot_token)


async def forward_messages(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """forwardMessages — массовая пересылка."""
    return await _call("forwardMessages", payload, bot_token=bot_token)


async def copy_messages(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """copyMessages — массовое копирование."""
    return await _call("copyMessages", payload, bot_token=bot_token)


async def edit_message_caption(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editMessageCaption — редактирование подписи к медиа."""
    return await _call("editMessageCaption", payload, bot_token=bot_token)


async def edit_message_reply_markup(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editMessageReplyMarkup — изменение inline-клавиатуры."""
    return await _call("editMessageReplyMarkup", payload, bot_token=bot_token)


async def edit_message_media(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editMessageMedia — замена медиа в сообщении (Bot API 7.11)."""
    return await _call("editMessageMedia", payload, bot_token=bot_token)


async def get_file(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getFile — получение file_path для скачивания."""
    return await _call("getFile", payload, bot_token=bot_token)


# === Batch 2: sendMessageDraft (Bot API 9.3) ===


async def send_message_draft(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendMessageDraft — стриминг частичного сообщения."""
    return await _call("sendMessageDraft", payload, bot_token=bot_token)


# === Batch 3: Базовые send-методы ===


async def send_location(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendLocation — отправка геолокации."""
    return await _call("sendLocation", payload, bot_token=bot_token)


async def send_venue(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendVenue — отправка места."""
    return await _call("sendVenue", payload, bot_token=bot_token)


async def send_contact(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendContact — отправка контакта."""
    return await _call("sendContact", payload, bot_token=bot_token)


async def send_dice(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendDice — анимированные эмодзи."""
    return await _call("sendDice", payload, bot_token=bot_token)


async def send_video_note(
    data: dict[str, Any],
    video_note_file: tuple[str, BinaryIO | bytes, str] | None = None,
    bot_token: str | None = None,
) -> dict[str, Any]:
    """sendVideoNote — видео-кружок."""
    if video_note_file:
        return await _call_multipart("sendVideoNote", data, {"video_note": video_note_file}, bot_token=bot_token)
    return await _call("sendVideoNote", data, bot_token=bot_token)


# === Batch 4: Live Location ===


async def edit_message_live_location(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editMessageLiveLocation — обновление живой геолокации."""
    return await _call("editMessageLiveLocation", payload, bot_token=bot_token)


async def stop_message_live_location(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """stopMessageLiveLocation — остановка живой геолокации."""
    return await _call("stopMessageLiveLocation", payload, bot_token=bot_token)


# === Batch 6: Forum Topics ===


async def create_forum_topic(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """createForumTopic — создание топика в форум-группе."""
    return await _call("createForumTopic", payload, bot_token=bot_token)


async def edit_forum_topic(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editForumTopic — редактирование топика."""
    return await _call("editForumTopic", payload, bot_token=bot_token)


async def close_forum_topic(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """closeForumTopic — закрытие топика."""
    return await _call("closeForumTopic", payload, bot_token=bot_token)


async def reopen_forum_topic(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """reopenForumTopic — повторное открытие топика."""
    return await _call("reopenForumTopic", payload, bot_token=bot_token)


async def delete_forum_topic(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """deleteForumTopic — удаление топика."""
    return await _call("deleteForumTopic", payload, bot_token=bot_token)


async def unpin_all_forum_topic_messages(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """unpinAllForumTopicMessages — открепление всех сообщений в топике."""
    return await _call("unpinAllForumTopicMessages", payload, bot_token=bot_token)


# === Batch 7: Chat Administration ===


async def set_chat_title(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setChatTitle — установить название чата."""
    return await _call("setChatTitle", payload, bot_token=bot_token)


async def set_chat_description(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setChatDescription — установить описание чата."""
    return await _call("setChatDescription", payload, bot_token=bot_token)


async def delete_chat_photo(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """deleteChatPhoto — удалить фото чата."""
    return await _call("deleteChatPhoto", payload, bot_token=bot_token)


async def leave_chat(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """leaveChat — выход из чата."""
    return await _call("leaveChat", payload, bot_token=bot_token)


async def unpin_all_chat_messages(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """unpinAllChatMessages — открепить все сообщения."""
    return await _call("unpinAllChatMessages", payload, bot_token=bot_token)


async def create_chat_invite_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """createChatInviteLink — создать пригласительную ссылку."""
    return await _call("createChatInviteLink", payload, bot_token=bot_token)


async def edit_chat_invite_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editChatInviteLink — редактировать пригласительную ссылку."""
    return await _call("editChatInviteLink", payload, bot_token=bot_token)


async def revoke_chat_invite_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """revokeChatInviteLink — отозвать пригласительную ссылку."""
    return await _call("revokeChatInviteLink", payload, bot_token=bot_token)


async def export_chat_invite_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """exportChatInviteLink — экспорт основной ссылки."""
    return await _call("exportChatInviteLink", payload, bot_token=bot_token)


async def create_chat_subscription_invite_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """createChatSubscriptionInviteLink — подписочная ссылка (Bot API 7.9)."""
    return await _call("createChatSubscriptionInviteLink", payload, bot_token=bot_token)


async def edit_chat_subscription_invite_link(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editChatSubscriptionInviteLink — редактирование подписочной ссылки (Bot API 7.9)."""
    return await _call("editChatSubscriptionInviteLink", payload, bot_token=bot_token)


# === Batch 8: Gifts + Paid Media ===


async def send_gift(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendGift — отправка подарка (Bot API 8.0)."""
    return await _call("sendGift", payload, bot_token=bot_token)


async def get_available_gifts(bot_token: str | None = None) -> dict[str, Any]:
    """getAvailableGifts — список доступных подарков."""
    return await _call("getAvailableGifts", {}, bot_token=bot_token)


async def send_paid_media(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """sendPaidMedia — отправка платного медиа (Bot API 7.6)."""
    return await _call("sendPaidMedia", payload, bot_token=bot_token)


# === Batch 9: Stories ===


async def post_story(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """postStory — публикация истории (Bot API 9.0)."""
    return await _call("postStory", payload, bot_token=bot_token)


async def edit_story(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editStory — редактирование истории."""
    return await _call("editStory", payload, bot_token=bot_token)


async def delete_story(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """deleteStory — удаление истории."""
    return await _call("deleteStory", payload, bot_token=bot_token)


# === Batch 10: Bot Profile + Subscriptions ===


async def set_my_profile_photo(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """setMyProfilePhoto — установить фото профиля бота (Bot API 9.4)."""
    return await _call("setMyProfilePhoto", payload, bot_token=bot_token)


async def remove_my_profile_photo(payload: dict[str, Any] | None = None, bot_token: str | None = None) -> dict[str, Any]:
    """removeMyProfilePhoto — удалить фото профиля бота (Bot API 9.4)."""
    return await _call("removeMyProfilePhoto", payload or {}, bot_token=bot_token)


async def get_user_profile_audios(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """getUserProfileAudios — аудио профиля пользователя (Bot API 9.4)."""
    return await _call("getUserProfileAudios", payload, bot_token=bot_token)


async def approve_suggested_post(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """approveSuggestedPost — одобрить предложенный пост (Bot API 9.2)."""
    return await _call("approveSuggestedPost", payload, bot_token=bot_token)


async def decline_suggested_post(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """declineSuggestedPost — отклонить предложенный пост (Bot API 9.2)."""
    return await _call("declineSuggestedPost", payload, bot_token=bot_token)


async def edit_user_star_subscription(payload: dict[str, Any], bot_token: str | None = None) -> dict[str, Any]:
    """editUserStarSubscription — редактирование Star-подписки (Bot API 8.0)."""
    return await _call("editUserStarSubscription", payload, bot_token=bot_token)
