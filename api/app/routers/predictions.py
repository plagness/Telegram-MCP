"""
Роутер для Prediction Markets (предсказания) и Stars Payments.

Тонкий роутер: валидация → сервис → ответ.
Вся бизнес-логика вынесена в services/predictions.py.

Endpoints:
  - POST /v1/predictions/events — создание события
  - GET /v1/predictions/events — список событий
  - GET /v1/predictions/events/{id} — детали события
  - POST /v1/predictions/bets — размещение ставки
  - POST /v1/predictions/events/{id}/resolve — разрешение события
  - POST /v1/predictions/events/{id}/auto-resolve — авто-разрешение (LLM)
  - GET /v1/predictions/bets — ставки пользователя
  - GET /v1/predictions/currencies — доступные валюты
  - POST /v1/stars/invoice — создание счёта
  - POST /v1/stars/refund — возврат Stars платежа
  - GET /v1/stars/transactions — история транзакций
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..models import (
    CreatePredictionEventIn,
    PlaceBetIn,
    RefundStarPaymentIn,
    ResolveEventIn,
    SendInvoiceIn,
)
from ..services import predictions as pred_service

router = APIRouter(prefix="/v1", tags=["predictions", "stars-payments"])
logger = logging.getLogger(__name__)


# === Prediction Events ===


@router.post("/predictions/events")
async def create_prediction_event(payload: CreatePredictionEventIn):
    """Создание события для предсказаний (Polymarket-style)."""
    try:
        return await pred_service.create_event(
            title=payload.title,
            description=payload.description,
            chat_id=payload.chat_id,
            creator_id=payload.creator_id,
            deadline=payload.deadline,
            resolution_date=payload.resolution_date,
            min_bet=payload.min_bet,
            max_bet=payload.max_bet,
            is_anonymous=payload.is_anonymous,
            bot_id=payload.bot_id,
            currency=payload.currency or "XTR",
            options=payload.options,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Ошибка создания события: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/events")
async def list_prediction_events(
    status: str | None = Query(None, description="Фильтр по статусу"),
    chat_id: int | None = Query(None, description="Фильтр по чату"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список событий для предсказаний."""
    return await pred_service.list_events(
        status=status, chat_id=chat_id, limit=limit, offset=offset
    )


@router.get("/predictions/events/{event_id}")
async def get_prediction_event(event_id: int):
    """Детали события с полной информацией о ставках."""
    event = await pred_service.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"ok": True, "event": event}


@router.post("/predictions/bets")
async def place_bet(payload: PlaceBetIn):
    """Размещение предсказания на событие."""
    try:
        return await pred_service.place_bet(
            event_id=payload.event_id,
            option_id=payload.option_id,
            user_id=payload.user_id,
            amount=payload.amount,
            source=payload.source,
            bot_id=getattr(payload, "bot_id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Ошибка размещения ставки: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predictions/events/{event_id}/resolve")
async def resolve_prediction_event(event_id: int, payload: ResolveEventIn):
    """Разрешение события и выплата выигрышей."""
    try:
        return await pred_service.resolve_event(
            event_id,
            winning_option_ids=payload.winning_option_ids,
            resolution_source=payload.resolution_source,
            resolution_data=payload.resolution_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Ошибка разрешения события: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predictions/events/{event_id}/auto-resolve")
async def auto_resolve_prediction_event(event_id: int):
    """Автоматическое разрешение события через LLM-MCP."""
    try:
        return await pred_service.auto_resolve_event(event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError:
        raise HTTPException(status_code=504, detail="LLM job timeout")
    except Exception as e:
        logger.error("Auto-resolve error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/bets")
async def list_user_bets(
    user_id: int = Query(...),
    event_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Ставки пользователя."""
    return await pred_service.list_user_bets(
        user_id=user_id, event_id=event_id, status=status, limit=limit
    )


@router.get("/predictions/currencies")
async def list_currencies():
    """Список доступных валют для предсказаний."""
    return await pred_service.list_currencies()


# === Stars Payments ===


@router.post("/stars/invoice")
async def create_star_invoice(payload: SendInvoiceIn):
    """Создание счёта на оплату Stars."""
    try:
        return await pred_service.create_invoice(
            chat_id=payload.chat_id,
            title=payload.title,
            description=payload.description,
            payload=payload.payload,
            currency=payload.currency,
            prices=[p.model_dump() for p in payload.prices],
            message_thread_id=payload.message_thread_id,
            reply_to_message_id=payload.reply_to_message_id,
            bot_id=payload.bot_id,
        )
    except Exception as e:
        logger.error("Ошибка создания счёта: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stars/refund")
async def refund_star_payment_api(payload: RefundStarPaymentIn):
    """Возврат Stars платежа."""
    try:
        return await pred_service.refund_payment(
            user_id=payload.user_id,
            telegram_payment_charge_id=payload.telegram_payment_charge_id,
            bot_id=payload.bot_id,
        )
    except Exception as e:
        logger.error("Ошибка возврата платежа: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stars/transactions")
async def get_star_transactions_api(
    user_id: int | None = Query(None),
    bot_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """История транзакций Stars."""
    try:
        return await pred_service.list_star_transactions(
            user_id=user_id, bot_id=bot_id, limit=limit, offset=offset
        )
    except Exception as e:
        logger.error("Ошибка получения транзакций: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
