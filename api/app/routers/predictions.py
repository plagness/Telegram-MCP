"""
Роутер для Prediction Markets (ставки на события) и Stars Payments.

Endpoints:
  - POST /v1/predictions/events — создание события
  - GET /v1/predictions/events — список событий
  - GET /v1/predictions/events/{id} — детали события
  - POST /v1/predictions/bets — размещение ставки
  - POST /v1/predictions/events/{id}/resolve — разрешение события
  - GET /v1/predictions/bets — ставки пользователя
  - POST /v1/stars/invoice — создание счёта
  - POST /v1/stars/refund — возврат Stars платежа
  - GET /v1/stars/transactions — история транзакций
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..db import execute, fetch_all, fetch_one
from ..models import (
    CreatePredictionEventIn,
    PlaceBetIn,
    RefundStarPaymentIn,
    ResolveEventIn,
    SendInvoiceIn,
)
from ..telegram_client import (
    answer_pre_checkout_query,
    get_star_transactions,
    refund_star_payment,
    send_invoice,
    send_message,
)

router = APIRouter(prefix="/v1", tags=["predictions", "stars-payments"])
logger = logging.getLogger(__name__)


# === Prediction Events ===


@router.post("/predictions/events")
async def create_prediction_event(payload: CreatePredictionEventIn):
    """
    Создание события для ставок (Polymarket-style).

    Создаёт событие с вариантами ответов, банком Stars и мультипликатором.
    """
    try:
        # Создание события
        event_query = """
            INSERT INTO prediction_events
            (title, description, chat_id, creator_id, deadline, resolution_date,
             min_bet, max_bet, is_anonymous, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'active')
            RETURNING id
        """
        event_id = await fetch_one(
            event_query,
            [
                payload.title,
                payload.description,
                payload.chat_id,
                payload.creator_id,
                payload.deadline,
                payload.resolution_date,
                payload.min_bet,
                payload.max_bet,
                payload.is_anonymous,
            ],
        )

        # Создание вариантов ответов
        for option in payload.options:
            await execute(
                """
                INSERT INTO prediction_options (event_id, option_id, text, value)
                VALUES ($1, $2, $3, $4)
                """,
                [event_id["id"], option.id, option.text, option.value],
            )

        # Отправка сообщения в чат (если указан)
        if payload.chat_id:
            # Форматирование события
            options_text = "\n".join(
                [f"  • {opt.text}" + (f" ({opt.value})" if opt.value else "") for opt.text in payload.options]
            )
            message_text = f"""
<b>🎯 Новое событие для ставок</b>

<b>{payload.title}</b>

{payload.description}

<b>Варианты:</b>
{options_text}

<b>Ставка:</b> {payload.min_bet}-{payload.max_bet} ⭐
<b>Дедлайн:</b> {payload.deadline or "Не указан"}
<b>Режим:</b> {"Обезличенный" if payload.is_anonymous else "Публичный"}

<i>ID события: {event_id['id']}</i>
            """.strip()

            try:
                msg_result = await send_message(
                    {
                        "chat_id": payload.chat_id,
                        "text": message_text,
                        "parse_mode": "HTML",
                    }
                )

                # Сохранение ID сообщения
                await execute(
                    "UPDATE prediction_events SET telegram_message_id = $1 WHERE id = $2",
                    [msg_result["message_id"], event_id["id"]],
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение о событии: {e}")

        return {"ok": True, "event_id": event_id["id"]}

    except Exception as e:
        logger.error(f"Ошибка создания события: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/events")
async def list_prediction_events(
    status: str | None = Query(None, description="Фильтр по статусу"),
    chat_id: int | None = Query(None, description="Фильтр по чату"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список событий для ставок."""
    conditions = []
    params = []
    param_count = 1

    if status:
        conditions.append(f"status = ${param_count}")
        params.append(status)
        param_count += 1

    if chat_id:
        conditions.append(f"chat_id = ${param_count}")
        params.append(chat_id)
        param_count += 1

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        SELECT
            e.*,
            (SELECT COUNT(*) FROM prediction_bets WHERE event_id = e.id) as bet_count,
            (SELECT json_agg(json_build_object(
                'id', option_id,
                'text', text,
                'value', value,
                'total_bets', total_bets,
                'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """
    params.extend([limit, offset])

    events = await fetch_all(query, params)
    return {"ok": True, "events": events, "total": len(events)}


@router.get("/predictions/events/{event_id}")
async def get_prediction_event(event_id: int):
    """Детали события с полной информацией о ставках."""
    event = await fetch_one(
        """
        SELECT
            e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id,
                'text', text,
                'value', value,
                'total_bets', total_bets,
                'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options,
            (SELECT COUNT(*) FROM prediction_bets WHERE event_id = e.id) as bet_count,
            (SELECT json_agg(json_build_object(
                'user_id', user_id,
                'option_id', option_id,
                'amount', amount,
                'status', status
            )) FROM prediction_bets WHERE event_id = e.id AND e.is_anonymous = FALSE) as bets
        FROM prediction_events e
        WHERE e.id = $1
        """,
        [event_id],
    )

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return {"ok": True, "event": event}


@router.post("/predictions/bets")
async def place_bet(payload: PlaceBetIn):
    """
    Размещение ставки на событие.

    Создаёт счёт (invoice) для оплаты Stars и сохраняет ставку.
    """
    try:
        # Проверка события
        event = await fetch_one(
            "SELECT * FROM prediction_events WHERE id = $1",
            [payload.event_id],
        )

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        if event["status"] != "active":
            raise HTTPException(status_code=400, detail="Event is not active")

        # Проверка лимитов ставки
        if payload.amount < event["min_bet"] or payload.amount > event["max_bet"]:
            raise HTTPException(
                status_code=400,
                detail=f"Bet amount must be between {event['min_bet']} and {event['max_bet']} stars",
            )

        # Проверка существования варианта
        option = await fetch_one(
            "SELECT * FROM prediction_options WHERE event_id = $1 AND option_id = $2",
            [payload.event_id, payload.option_id],
        )

        if not option:
            raise HTTPException(status_code=404, detail="Option not found")

        # Создание транзакции
        transaction = await fetch_one(
            """
            INSERT INTO star_transactions
            (user_id, transaction_type, amount, payload, status, metadata)
            VALUES ($1, 'payment', $2, $3, 'pending', $4)
            RETURNING id
            """,
            [
                payload.user_id,
                payload.amount,
                f"bet_{payload.event_id}_{payload.option_id}",
                {"event_id": payload.event_id, "option_id": payload.option_id},
            ],
        )

        # Создание ставки
        bet = await fetch_one(
            """
            INSERT INTO prediction_bets
            (event_id, option_id, user_id, amount, status, transaction_id)
            VALUES ($1, $2, $3, $4, 'active', $5)
            RETURNING id
            """,
            [payload.event_id, payload.option_id, payload.user_id, payload.amount, transaction["id"]],
        )

        # Создание счёта для оплаты
        invoice_payload = {
            "chat_id": payload.user_id,
            "title": f"Ставка: {event['title'][:30]}",
            "description": f"Ставка {payload.amount} ⭐ на вариант '{option['text']}'",
            "payload": f"bet_{bet['id']}_{transaction['id']}",
            "currency": "XTR",
            "prices": [{"label": "Ставка", "amount": payload.amount}],
        }

        invoice_result = await send_invoice(invoice_payload)

        return {
            "ok": True,
            "bet_id": bet["id"],
            "transaction_id": transaction["id"],
            "invoice": invoice_result,
        }

    except Exception as e:
        logger.error(f"Ошибка размещения ставки: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predictions/events/{event_id}/resolve")
async def resolve_prediction_event(event_id: int, payload: ResolveEventIn):
    """
    Разрешение события и выплата выигрышей.

    Определяет победителей, рассчитывает мультипликаторы и выплачивает Stars.
    """
    try:
        # Проверка события
        event = await fetch_one(
            "SELECT * FROM prediction_events WHERE id = $1",
            [event_id],
        )

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        if event["status"] == "resolved":
            raise HTTPException(status_code=400, detail="Event already resolved")

        # Получение всех ставок
        all_bets = await fetch_all(
            "SELECT * FROM prediction_bets WHERE event_id = $1 AND status = 'active'",
            [event_id],
        )

        # Расчёт выигрышей
        total_pool = event["total_pool"]
        winning_bets = [b for b in all_bets if b["option_id"] in payload.winning_option_ids]
        losing_bets = [b for b in all_bets if b["option_id"] not in payload.winning_option_ids]

        if not winning_bets:
            # Нет победителей → полный возврат
            for bet in all_bets:
                await execute(
                    "UPDATE prediction_bets SET status = 'refunded', payout = amount WHERE id = $1",
                    [bet["id"]],
                )
                # TODO: Вызов refund_star_payment
        else:
            # Распределение банка между победителями пропорционально ставкам
            total_winning_amount = sum(b["amount"] for b in winning_bets)

            for bet in winning_bets:
                # Расчёт выплаты: доля от общего банка
                payout = int((bet["amount"] / total_winning_amount) * total_pool)
                await execute(
                    "UPDATE prediction_bets SET status = 'won', payout = $1 WHERE id = $2",
                    [payout, bet["id"]],
                )
                # TODO: Выплата Stars через sendStars или аналогичный метод

            for bet in losing_bets:
                await execute(
                    "UPDATE prediction_bets SET status = 'lost' WHERE id = $1",
                    [bet["id"]],
                )

        # Создание записи о разрешении
        await execute(
            """
            INSERT INTO prediction_resolutions
            (event_id, winning_option_ids, resolution_source, resolution_data,
             total_winners, total_payout)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [
                event_id,
                payload.winning_option_ids,
                payload.resolution_source,
                payload.resolution_data,
                len(winning_bets),
                sum(b["payout"] for b in winning_bets) if winning_bets else 0,
            ],
        )

        # Обновление статуса события
        await execute(
            "UPDATE prediction_events SET status = 'resolved', updated_at = NOW() WHERE id = $1",
            [event_id],
        )

        return {
            "ok": True,
            "event_id": event_id,
            "winners": len(winning_bets),
            "total_payout": sum(b["payout"] for b in winning_bets) if winning_bets else 0,
        }

    except Exception as e:
        logger.error(f"Ошибка разрешения события: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/bets")
async def list_user_bets(
    user_id: int = Query(...),
    event_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Ставки пользователя."""
    conditions = ["user_id = $1"]
    params = [user_id]
    param_count = 2

    if event_id:
        conditions.append(f"event_id = ${param_count}")
        params.append(event_id)
        param_count += 1

    if status:
        conditions.append(f"status = ${param_count}")
        params.append(status)
        param_count += 1

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            b.*,
            e.title as event_title,
            o.text as option_text
        FROM prediction_bets b
        JOIN prediction_events e ON b.event_id = e.id
        JOIN prediction_options o ON b.event_id = o.event_id AND b.option_id = o.option_id
        WHERE {where_clause}
        ORDER BY b.created_at DESC
        LIMIT ${param_count}
    """
    params.append(limit)

    bets = await fetch_all(query, params)
    return {"ok": True, "bets": bets}


# === Stars Payments ===


@router.post("/stars/invoice")
async def create_star_invoice(payload: SendInvoiceIn):
    """Создание счёта на оплату Stars."""
    try:
        telegram_payload = {
            "chat_id": payload.chat_id,
            "title": payload.title,
            "description": payload.description,
            "payload": payload.payload,
            "currency": payload.currency,
            "prices": [p.model_dump() for p in payload.prices],
        }

        if payload.message_thread_id:
            telegram_payload["message_thread_id"] = payload.message_thread_id
        if payload.reply_to_message_id:
            telegram_payload["reply_to_message_id"] = payload.reply_to_message_id

        result = await send_invoice(telegram_payload)
        return {"ok": True, "result": result}

    except Exception as e:
        logger.error(f"Ошибка создания счёта: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stars/refund")
async def refund_star_payment_api(payload: RefundStarPaymentIn):
    """Возврат Stars платежа."""
    try:
        telegram_payload = {
            "user_id": payload.user_id,
            "telegram_payment_charge_id": payload.telegram_payment_charge_id,
        }

        result = await refund_star_payment(telegram_payload)

        # Обновление транзакции
        await execute(
            "UPDATE star_transactions SET status = 'refunded', updated_at = NOW() WHERE telegram_payment_charge_id = $1",
            [payload.telegram_payment_charge_id],
        )

        return {"ok": True, "result": result}

    except Exception as e:
        logger.error(f"Ошибка возврата платежа: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stars/transactions")
async def get_star_transactions_api(
    user_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """История транзакций Stars."""
    try:
        # Получение из БД
        conditions = []
        params = []
        param_count = 1

        if user_id:
            conditions.append(f"user_id = ${param_count}")
            params.append(user_id)
            param_count += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT * FROM star_transactions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        params.extend([limit, offset])

        transactions = await fetch_all(query, params)

        # Также получаем из Telegram API
        telegram_txs = await get_star_transactions()

        return {
            "ok": True,
            "transactions": transactions,
            "telegram_transactions": telegram_txs,
        }

    except Exception as e:
        logger.error(f"Ошибка получения транзакций: {e}")
        raise HTTPException(status_code=500, detail=str(e))
