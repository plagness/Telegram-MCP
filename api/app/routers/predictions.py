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

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

import httpx
from ..config import get_settings
from ..db import execute, execute_returning, fetch_all, fetch_one
from ..models import (
    CreatePredictionEventIn,
    PlaceBetIn,
    RefundStarPaymentIn,
    ResolveEventIn,
    SendInvoiceIn,
)
from ..services import balance
from ..services.bots import BotRegistry
from ..telegram_client import (
    answer_pre_checkout_query,
    get_star_transactions,
    refund_star_payment,
    send_invoice,
    send_message,
)

settings = get_settings()

router = APIRouter(prefix="/v1", tags=["predictions", "stars-payments"])
logger = logging.getLogger(__name__)


async def _resolve_bot_context(bot_id: int | None) -> tuple[str, int | None]:
    bot_token = await BotRegistry.get_bot_token(bot_id)
    resolved_bot_id = bot_id
    bot_row = await BotRegistry.get_bot_by_token(bot_token)
    if bot_row and bot_row.get("bot_id") is not None:
        resolved_bot_id = int(bot_row["bot_id"])
    return bot_token, resolved_bot_id


# === Prediction Events ===


@router.post("/predictions/events")
async def create_prediction_event(payload: CreatePredictionEventIn):
    """
    Создание события для ставок (Polymarket-style).

    Создаёт событие с вариантами ответов, банком Stars и мультипликатором.
    """
    try:
        bot_token, resolved_bot_id = await _resolve_bot_context(payload.bot_id)

        # Создание события
        event_query = """
            INSERT INTO prediction_events
            (title, description, chat_id, creator_id, deadline, resolution_date,
             min_bet, max_bet, is_anonymous, status, bot_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
            RETURNING id
        """
        params = [
            payload.title,
            payload.description,
            payload.chat_id,
            payload.creator_id,
            payload.deadline,
            payload.resolution_date,
            payload.min_bet,
            payload.max_bet,
            payload.is_anonymous,
            resolved_bot_id,
        ]
        event_id = await execute_returning(event_query, params)

        # Создание вариантов ответов
        for option in payload.options:
            await execute(
                """
                INSERT INTO prediction_options (event_id, option_id, text, value)
                VALUES (%s, %s, %s, %s)
                """,
                [event_id["id"], option.id, option.text, option.value],
            )

        # Форматирование события
        def escape_html(text: str) -> str:
            """Экранирование HTML символов."""
            return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        options_text = "\n".join(
            [f"  • {opt.text}" + (f" <code>({escape_html(opt.value)})</code>" if opt.value else "") for opt in payload.options]
        )

        # 1. Анонс в публичный чат (если указан) — без кнопок, без личной информации
        if payload.chat_id:
            # Форматирование опций с местом для статистики
            options_lines = []
            for opt in payload.options:
                value_str = f" <code>({escape_html(opt.value)})</code>" if opt.value else ""
                options_lines.append(
                    f"  • {opt.text}{value_str}\n    0 ставок, 0 ⭐"
                )

            formatted_options = "\n\n".join(options_lines)

            public_message_text = f"""
<b>🎯 Новое событие для ставок</b>

<b>{payload.title}</b>

{payload.description}

<b>Варианты:</b>
{formatted_options}

<b>Общий банк:</b> 0 ⭐
<b>Ставка:</b> {payload.min_bet}-{payload.max_bet} ⭐
<b>Дедлайн:</b> {payload.deadline or "Не указан"}
<b>Статус:</b> active
            """.strip()

            # Inline кнопка для ставки
            public_inline_keyboard = [[
                {
                    "text": "💰 Поставить",
                    "callback_data": f"bet_event_{event_id['id']}"
                }
            ]]

            try:
                send_payload = {
                    "chat_id": payload.chat_id,
                    "text": public_message_text,
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "inline_keyboard": public_inline_keyboard
                    }
                }
                msg_result = await send_message(send_payload, bot_token=bot_token)

                # Сохранение ID сообщения
                await execute(
                    "UPDATE prediction_events SET telegram_message_id = %s WHERE id = %s",
                    [msg_result["message_id"], event_id["id"]],
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить анонс события в чат: {e}")

        # 2. Интерактивное сообщение создателю в личку — с кнопками для ставок
        if payload.creator_id:
            # Формируем кнопки для каждого варианта
            inline_keyboard = []
            for opt in payload.options:
                inline_keyboard.append([
                    {
                        "text": f"💰 {opt.text}",
                        "callback_data": f"bet_{event_id['id']}_{opt.id}"
                    }
                ])

            # Кнопка для просмотра статистики
            inline_keyboard.append([
                {
                    "text": "📊 Статистика события",
                    "callback_data": f"stats_{event_id['id']}"
                }
            ])

            private_message_text = f"""
<b>✅ Событие создано!</b>

<b>{payload.title}</b>

{payload.description}

<b>Варианты:</b>
{options_text}

<b>Ставка:</b> {payload.min_bet}-{payload.max_bet} ⭐

<i>Выберите вариант для ставки:</i>
            """.strip()

            try:
                await send_message(
                    {
                        "chat_id": payload.creator_id,
                        "text": private_message_text,
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": inline_keyboard
                        }
                    },
                    bot_token=bot_token,
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить личное сообщение создателю: {e}")

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

    if status:
        conditions.append("status = %s")
        params.append(status)

    if chat_id:
        conditions.append("chat_id = %s")
        params.append(chat_id)

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
        LIMIT %s OFFSET %s
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
        WHERE e.id = %s
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
            "SELECT * FROM prediction_events WHERE id = %s",
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
            "SELECT * FROM prediction_options WHERE event_id = %s AND option_id = %s",
            [payload.event_id, payload.option_id],
        )

        if not option:
            raise HTTPException(status_code=404, detail="Option not found")

        # Создание транзакции
        transaction = await execute_returning(
            """
            INSERT INTO star_transactions
            (user_id, transaction_type, amount, payload, status, metadata)
            VALUES (%s, 'payment', %s, %s, 'pending', %s)
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
        bet = await execute_returning(
            """
            INSERT INTO prediction_bets
            (event_id, option_id, user_id, amount, status, transaction_id)
            VALUES (%s, %s, %s, %s, 'active', %s)
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

        event_bot_id = int(event["bot_id"]) if event.get("bot_id") is not None else None
        event_bot_token, _ = await _resolve_bot_context(event_bot_id)
        invoice_result = await send_invoice(invoice_payload, bot_token=event_bot_token)

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
            "SELECT * FROM prediction_events WHERE id = %s",
            [event_id],
        )

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        if event["status"] == "resolved":
            raise HTTPException(status_code=400, detail="Event already resolved")

        event_bot_id = int(event["bot_id"]) if event.get("bot_id") is not None else None
        event_bot_token, _ = await _resolve_bot_context(event_bot_id)

        # Получение всех ставок
        all_bets = await fetch_all(
            "SELECT * FROM prediction_bets WHERE event_id = %s AND status = 'active'",
            [event_id],
        )

        # Расчёт выигрышей
        total_pool = event["total_pool"]
        winning_bets = [b for b in all_bets if b["option_id"] in payload.winning_option_ids]
        losing_bets = [b for b in all_bets if b["option_id"] not in payload.winning_option_ids]

        payouts_summary = []

        if not winning_bets:
            # Нет победителей → полный возврат всем
            for bet in all_bets:
                await execute(
                    "UPDATE prediction_bets SET status = 'refunded', payout = amount WHERE id = %s",
                    [bet["id"]],
                )
                # Вернуть средства на баланс
                await balance.add_to_balance(
                    user_id=bet["user_id"],
                    amount=bet["amount"],
                    transaction_type="refund",
                    reference_type="prediction_bet",
                    reference_id=bet["id"],
                    description=f"Возврат ставки (событие без победителей): '{event['title']}'"
                )
                payouts_summary.append({
                    "user_id": bet["user_id"],
                    "amount": bet["amount"],
                    "type": "refund"
                })
        else:
            # Распределение банка между победителями пропорционально ставкам
            total_winning_amount = sum(b["amount"] for b in winning_bets)

            for bet in winning_bets:
                # Расчёт выплаты: доля от общего банка
                payout = int((bet["amount"] / total_winning_amount) * total_pool)
                await execute(
                    "UPDATE prediction_bets SET status = 'won', payout = %s WHERE id = %s",
                    [payout, bet["id"]],
                )

                # Зачислить выигрыш на баланс
                await balance.add_to_balance(
                    user_id=bet["user_id"],
                    amount=payout,
                    transaction_type="win",
                    reference_type="prediction_bet",
                    reference_id=bet["id"],
                    description=f"Выигрыш в событии '{event['title']}'"
                )

                profit = payout - bet["amount"]
                payouts_summary.append({
                    "user_id": bet["user_id"],
                    "bet_amount": bet["amount"],
                    "payout": payout,
                    "profit": profit,
                    "type": "win"
                })

            for bet in losing_bets:
                await execute(
                    "UPDATE prediction_bets SET status = 'lost' WHERE id = %s",
                    [bet["id"]],
                )

                # Записать проигрыш для статистики
                await balance.record_loss(bet["user_id"], bet["amount"])

                payouts_summary.append({
                    "user_id": bet["user_id"],
                    "bet_amount": bet["amount"],
                    "type": "loss"
                })

        # Отправить уведомления всем участникам
        for item in payouts_summary:
            user_id = item["user_id"]

            if item["type"] == "win":
                notification_text = f"""
🎉 <b>Поздравляем! Вы выиграли!</b>

<b>Событие:</b> {event['title']}

<b>Ваша ставка:</b> {item['bet_amount']} ⭐
<b>Выплата:</b> {item['payout']} ⭐
<b>Чистая прибыль:</b> +{item['profit']} ⭐

<i>Выигрыш зачислен на ваш баланс.</i>
                """.strip()
            elif item["type"] == "loss":
                notification_text = f"""
😔 <b>К сожалению, вы проиграли</b>

<b>Событие:</b> {event['title']}

<b>Ваша ставка:</b> {item['bet_amount']} ⭐

<i>Попробуйте в следующий раз!</i>
                """.strip()
            else:  # refund
                notification_text = f"""
↩️ <b>Ставка возвращена</b>

<b>Событие:</b> {event['title']}

<b>Возвращено:</b> {item['amount']} ⭐

<i>Событие завершилось без победителей, ставка полностью возвращена.</i>
                """.strip()

            try:
                await send_message({
                    "chat_id": user_id,
                    "text": notification_text,
                    "parse_mode": "HTML"
                }, bot_token=event_bot_token)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

        # Создание записи о разрешении
        await execute(
            """
            INSERT INTO prediction_resolutions
            (event_id, winning_option_ids, resolution_source, resolution_data,
             total_winners, total_payout)
            VALUES (%s, %s, %s, %s, %s, %s)
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
            "UPDATE prediction_events SET status = 'resolved', updated_at = NOW() WHERE id = %s",
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


@router.post("/predictions/events/{event_id}/auto-resolve")
async def auto_resolve_prediction_event(event_id: int):
    """
    Автоматическое разрешение события через LLM-MCP.

    LLM анализирует событие, проверяет новости и определяет победителя.
    Использует облачные модели (OpenRouter/Anthropic) для точности.
    """
    if not settings.llm_mcp_enabled:
        raise HTTPException(status_code=503, detail="LLM-MCP integration disabled")

    try:
        # Получить событие с опциями
        event = await fetch_one(
            """
            SELECT
                e.*,
                (SELECT json_agg(json_build_object(
                    'id', option_id,
                    'text', text,
                    'value', value
                )) FROM prediction_options WHERE event_id = e.id) as options
            FROM prediction_events e
            WHERE e.id = %s
            """,
            [event_id]
        )

        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        if event["status"] == "resolved":
            raise HTTPException(status_code=400, detail="Event already resolved")

        # Форматирование промпта для LLM
        options_list = "\n".join([
            f"{i+1}. {opt['text']}" + (f" ({opt['value']})" if opt.get('value') else "")
            for i, opt in enumerate(event.get("options") or [])
        ])

        prompt = f"""Ты - эксперт по анализу событий и проверке фактов. Твоя задача - определить результат события для системы ставок.

Событие: {event['title']}
Описание: {event['description']}
Дата дедлайна: {event.get('deadline') or 'Не указана'}

Варианты ответов:
{options_list}

ЗАДАЧА:
1. Проверь актуальную информацию по этому событию (если нужно - поищи новости)
2. Определи какой вариант ответа правильный
3. Если есть неопределённость или спорная ситуация - верни "refund"

ФОРМАТ ОТВЕТА (строго JSON):
{{
    "decision": "option_id" или "refund",
    "reasoning": "краткое объяснение решения",
    "confidence": 0-100
}}

Примеры:
- Если вопрос "Будет ли снег?" и снег выпал → {{"decision": "yes", "reasoning": "По данным метеослужб снег выпал", "confidence": 95}}
- Если неопределённость → {{"decision": "refund", "reasoning": "Недостаточно данных", "confidence": 50}}

ВАЖНО:
- Если confidence < 70 - лучше вернуть "refund"
- Используй только option_id из списка выше или "refund"
- Отвечай только JSON, без markdown и комментариев
"""

        # Отправить запрос в LLM-MCP
        async with httpx.AsyncClient(timeout=120.0) as client:
            llm_request = {
                "task": "chat",
                "provider": "auto",  # Автоматически выберет лучшую модель
                "model": "claude-3-7-sonnet",  # Или любая облачная модель
                "prompt": prompt,
                "priority": 5,  # Высокий приоритет
                "source": "telegram-api-predictions",
                "max_attempts": 3,
                "constraints": {
                    "force_cloud": True,  # Обязательно облачная модель
                    "prefer_local": False
                }
            }

            # Создать job в LLM-MCP
            llm_response = await client.post(
                f"{settings.llm_mcp_url}/v1/llm/request",
                json=llm_request
            )
            llm_response.raise_for_status()
            llm_data = llm_response.json()
            job_id = llm_data.get("job_id")

            if not job_id:
                raise HTTPException(status_code=500, detail="LLM-MCP did not return job_id")

            logger.info(f"LLM job created: {job_id} for event {event_id}")

            # Ждать результат (polling)
            max_wait = 90  # 90 секунд
            poll_interval = 2
            elapsed = 0

            while elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                job_response = await client.get(
                    f"{settings.llm_mcp_url}/v1/jobs/{job_id}"
                )
                job_response.raise_for_status()
                job_data = job_response.json()

                status = job_data.get("status")

                if status == "done":
                    result = job_data.get("result", {})
                    break
                elif status == "error":
                    error = job_data.get("error", "Unknown error")
                    raise HTTPException(status_code=500, detail=f"LLM job failed: {error}")
            else:
                raise HTTPException(status_code=504, detail="LLM job timeout")

        # Парсить результат LLM
        import json as json_lib
        llm_text = result.get("response", result.get("content", ""))

        # Попытка извлечь JSON из ответа
        try:
            # Если ответ в markdown блоке
            if "```json" in llm_text:
                llm_text = llm_text.split("```json")[1].split("```")[0].strip()
            elif "```" in llm_text:
                llm_text = llm_text.split("```")[1].split("```")[0].strip()

            decision_data = json_lib.loads(llm_text)
        except json_lib.JSONDecodeError:
            raise HTTPException(status_code=500, detail="Failed to parse LLM response")

        decision = decision_data.get("decision")
        reasoning = decision_data.get("reasoning", "No reasoning provided")
        confidence = decision_data.get("confidence", 0)

        logger.info(f"LLM decision for event {event_id}: {decision} (confidence: {confidence}%)")

        # Применить решение
        if decision == "refund":
            # Вернуть всем ставки
            resolve_payload = ResolveEventIn(
                winning_option_ids=[],  # Пустой список = возврат всем
                resolution_source="llm-auto",
                resolution_data={
                    "llm_decision": decision,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "job_id": job_id
                }
            )
        else:
            # Найти опцию с таким ID
            winning_option = None
            for opt in (event.get("options") or []):
                if opt["id"] == decision:
                    winning_option = opt
                    break

            if not winning_option:
                raise HTTPException(
                    status_code=400,
                    detail=f"LLM returned invalid option_id: {decision}"
                )

            resolve_payload = ResolveEventIn(
                winning_option_ids=[decision],
                resolution_source="llm-auto",
                resolution_data={
                    "llm_decision": decision,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "job_id": job_id
                }
            )

        # Вызвать обычное разрешение
        result = await resolve_prediction_event(event_id, resolve_payload)

        return {
            **result,
            "llm_decision": decision,
            "reasoning": reasoning,
            "confidence": confidence
        }

    except httpx.HTTPError as e:
        logger.error(f"LLM-MCP HTTP error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM-MCP connection error: {str(e)}")
    except Exception as e:
        logger.error(f"Auto-resolve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions/bets")
async def list_user_bets(
    user_id: int = Query(...),
    event_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Ставки пользователя."""
    conditions = ["user_id = %s"]
    params = [user_id]

    if event_id:
        conditions.append("event_id = %s")
        params.append(event_id)

    if status:
        conditions.append("status = %s")
        params.append(status)

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
        LIMIT %s
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

        bot_token, _ = await _resolve_bot_context(payload.bot_id)
        result = await send_invoice(telegram_payload, bot_token=bot_token)
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

        bot_token, _ = await _resolve_bot_context(payload.bot_id)
        result = await refund_star_payment(telegram_payload, bot_token=bot_token)

        # Обновление транзакции
        await execute(
            "UPDATE star_transactions SET status = 'refunded', updated_at = NOW() WHERE telegram_payment_charge_id = %s",
            [payload.telegram_payment_charge_id],
        )

        return {"ok": True, "result": result}

    except Exception as e:
        logger.error(f"Ошибка возврата платежа: {e}")
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
        # Получение из БД
        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT * FROM star_transactions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        transactions = await fetch_all(query, params)

        # Также получаем из Telegram API
        bot_token, _ = await _resolve_bot_context(bot_id)
        telegram_txs = await get_star_transactions(bot_token=bot_token)

        return {
            "ok": True,
            "transactions": transactions,
            "telegram_transactions": telegram_txs,
        }

    except Exception as e:
        logger.error(f"Ошибка получения транзакций: {e}")
        raise HTTPException(status_code=500, detail=str(e))
