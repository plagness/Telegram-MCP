"""Эндпоинты для работы с опросами."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..models import SendPollIn
from ..services import messages as message_service
from ..services import polls as poll_service
from ..telegram_client import TelegramError, send_poll, stop_poll
from ..utils import resolve_bot_context

router = APIRouter(prefix="/v1/polls", tags=["polls"])


@router.post("/send")
async def send_poll_api(payload: SendPollIn) -> dict[str, Any]:
    """Создание опроса или викторины."""
    # Подготовка payload для Telegram
    telegram_payload: dict[str, Any] = {
        "chat_id": payload.chat_id,
        "question": payload.question,
        "options": [opt if isinstance(opt, str) else opt.text for opt in payload.options],
        "is_anonymous": payload.is_anonymous,
        "type": payload.type,
        "allows_multiple_answers": payload.allows_multiple_answers,
    }

    if payload.correct_option_id is not None:
        telegram_payload["correct_option_id"] = payload.correct_option_id
    if payload.explanation:
        telegram_payload["explanation"] = payload.explanation
    if payload.explanation_parse_mode:
        telegram_payload["explanation_parse_mode"] = payload.explanation_parse_mode
    if payload.explanation_entities:
        telegram_payload["explanation_entities"] = payload.explanation_entities
    if payload.open_period is not None:
        telegram_payload["open_period"] = payload.open_period
    if payload.close_date:
        telegram_payload["close_date"] = payload.close_date
    if payload.is_closed:
        telegram_payload["is_closed"] = payload.is_closed
    if payload.disable_notification:
        telegram_payload["disable_notification"] = payload.disable_notification
    if payload.protect_content:
        telegram_payload["protect_content"] = payload.protect_content
    if payload.message_thread_id:
        telegram_payload["message_thread_id"] = payload.message_thread_id
    if payload.reply_to_message_id:
        telegram_payload["reply_to_message_id"] = payload.reply_to_message_id
    if payload.reply_markup:
        telegram_payload["reply_markup"] = payload.reply_markup

    bot_token, resolved_bot_id = await resolve_bot_context(payload.bot_id)

    # Создание записи в messages
    row = await message_service.create_message(
        chat_id=str(payload.chat_id),
        bot_id=resolved_bot_id,
        direction="outbound",
        text=payload.question,
        parse_mode=None,
        status="queued" if not payload.dry_run else "dry_run",
        request_id=payload.request_id,
        payload=telegram_payload,
        is_live=False,
        reply_to_message_id=payload.reply_to_message_id,
        message_thread_id=payload.message_thread_id,
        message_type="poll",
    )

    if payload.dry_run:
        return {"message": row, "dry_run": True}

    # Отправка опроса в Telegram
    try:
        await message_service.add_event(row["id"], "send_attempt", telegram_payload)
        result = await send_poll(telegram_payload, bot_token=bot_token)

        poll_data = result.get("poll", {})
        poll_id = poll_data.get("id")
        telegram_message_id = result.get("message_id")

        # Обновление messages
        await message_service.update_message(
            row["id"],
            status="sent",
            telegram_message_id=telegram_message_id,
            sent=True,
        )

        # Создание записи в polls
        if poll_id:
            await poll_service.create_poll(
                poll_id=poll_id,
                message_id=row["id"],
                chat_id=str(payload.chat_id),
                telegram_message_id=telegram_message_id,
                bot_id=resolved_bot_id,
                question=payload.question,
                options=[{"text": opt if isinstance(opt, str) else opt.text} for opt in payload.options],
                poll_type=payload.type,
                is_anonymous=payload.is_anonymous,
                allows_multiple_answers=payload.allows_multiple_answers,
                correct_option_id=payload.correct_option_id,
                explanation=payload.explanation,
                explanation_entities=payload.explanation_entities,
                open_period=payload.open_period,
                close_date=payload.close_date,
            )

        await message_service.add_event(row["id"], "send_success", result)
    except TelegramError as exc:
        await message_service.update_message(row["id"], status="error", error=str(exc))
        await message_service.add_event(row["id"], "send_error", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))

    updated = await message_service.get_message(row["id"])
    return {"message": updated, "result": result}


@router.post("/{chat_id}/{message_id}/stop")
async def stop_poll_api(chat_id: str, message_id: int, bot_id: int | None = None) -> dict[str, Any]:
    """
    Остановка опроса с показом результатов.

    message_id — telegram_message_id (не внутренний).
    """
    telegram_payload = {
        "chat_id": chat_id,
        "message_id": message_id,
    }

    try:
        bot_token, _ = await resolve_bot_context(bot_id)
        result = await stop_poll(telegram_payload, bot_token=bot_token)

        # Обновление опроса в БД
        poll_data = result
        poll_id = poll_data.get("id")
        if poll_id:
            await poll_service.update_poll(
                poll_id=poll_id,
                is_closed=True,
                total_voter_count=poll_data.get("total_voter_count", 0),
                results={"options": poll_data.get("options", [])},
            )
    except TelegramError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"ok": True, "poll": result}


@router.get("")
async def list_polls_api(
    chat_id: str | None = None,
    bot_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Список опросов."""
    rows = await poll_service.list_polls(chat_id=chat_id, bot_id=bot_id, limit=limit, offset=offset)
    return {"items": rows, "count": len(rows)}


@router.get("/{poll_id}")
async def get_poll_api(poll_id: str) -> dict[str, Any]:
    """Получение опроса по poll_id."""
    row = await poll_service.get_poll(poll_id)
    if not row:
        raise HTTPException(status_code=404, detail="poll not found")
    return {"poll": row}


@router.get("/{poll_id}/answers")
async def get_poll_answers_api(poll_id: str) -> dict[str, Any]:
    """Получение всех ответов на опрос."""
    answers = await poll_service.get_poll_answers(poll_id)
    return {"items": answers, "count": len(answers)}
