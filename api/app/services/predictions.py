"""Сервисный слой для Prediction Markets.

Содержит SQL-запросы, бизнес-логику расчёта выплат и
форматирование уведомлений. Роутер вызывает эти функции,
не содержа SQL напрямую.
"""

from __future__ import annotations

import asyncio
import json as json_lib
import logging
from typing import Any

import httpx
from psycopg.types.json import Json

from ..config import get_settings
from ..db import execute, execute_returning, fetch_all, fetch_one
from ..telegram_client import (
    get_star_transactions,
    refund_star_payment,
    send_invoice,
    send_message,
)
from ..utils import escape_html, resolve_bot_context
from . import balance
from .keyboards import bet_event_button, bet_options_keyboard

logger = logging.getLogger(__name__)
settings = get_settings()

# Символы валют для отображения в сообщениях
CURRENCY_SYMBOLS: dict[str, str] = {
    "XTR": "⭐",
    "AC": "🪙",
    "TON": "💎",
}

# Виртуальные валюты (оплата через баланс, без invoice)
VIRTUAL_CURRENCIES = {"AC"}

# Начальный баланс для виртуальных валют
INITIAL_BALANCE: dict[str, int] = {
    "AC": 100,
}


def currency_symbol(currency: str) -> str:
    """Символ валюты для отображения."""
    return CURRENCY_SYMBOLS.get(currency, currency)


def is_virtual(currency: str) -> bool:
    """Виртуальная ли валюта (оплата с баланса, не Stars invoice)."""
    return currency in VIRTUAL_CURRENCIES


# ---------------------------------------------------------------------------
# Создание события
# ---------------------------------------------------------------------------

async def create_event(
    *,
    title: str,
    description: str | None,
    chat_id: int | None,
    creator_id: int | None,
    deadline: str | None,
    resolution_date: str | None,
    min_bet: int,
    max_bet: int,
    is_anonymous: bool,
    bot_id: int | None,
    currency: str,
    options: list[Any],
) -> dict:
    """Создать событие и варианты, отправить анонс и личное сообщение."""
    bot_token, resolved_bot_id = await resolve_bot_context(bot_id)

    currency = currency.upper()
    if currency not in CURRENCY_SYMBOLS:
        raise ValueError(
            f"Неподдерживаемая валюта: {currency}. Доступны: {', '.join(CURRENCY_SYMBOLS)}"
        )
    sym = currency_symbol(currency)

    # Вставка события
    event_id = await execute_returning(
        """
        INSERT INTO prediction_events
        (title, description, chat_id, creator_id, deadline, resolution_date,
         min_bet, max_bet, is_anonymous, status, bot_id, currency)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
        RETURNING id
        """,
        [title, description, chat_id, creator_id, deadline, resolution_date,
         min_bet, max_bet, is_anonymous, resolved_bot_id, currency],
    )

    # Создание вариантов
    for opt in options:
        await execute(
            """
            INSERT INTO prediction_options (event_id, option_id, text, value)
            VALUES (%s, %s, %s, %s)
            """,
            [event_id["id"], opt.id, opt.text, opt.value],
        )

    eid = event_id["id"]

    # Публичный анонс в чат
    if chat_id:
        await _send_public_announcement(
            bot_token=bot_token,
            event_id=eid,
            chat_id=chat_id,
            title=title,
            description=description or "",
            options=options,
            min_bet=min_bet,
            max_bet=max_bet,
            deadline=deadline,
            currency=currency,
            sym=sym,
        )

    # Персональное сообщение создателю
    if creator_id:
        await _send_creator_message(
            bot_token=bot_token,
            event_id=eid,
            creator_id=creator_id,
            title=title,
            description=description or "",
            options=options,
            min_bet=min_bet,
            max_bet=max_bet,
            sym=sym,
        )

    return {"ok": True, "event_id": eid}


async def _send_public_announcement(
    *,
    bot_token: str,
    event_id: int,
    chat_id: int,
    title: str,
    description: str,
    options: list[Any],
    min_bet: int,
    max_bet: int,
    deadline: str | None,
    currency: str,
    sym: str,
) -> None:
    """Анонс события в публичный чат."""
    options_lines = []
    for opt in options:
        value_str = f" <code>({escape_html(opt.value)})</code>" if opt.value else ""
        options_lines.append(
            f"  • {opt.text}{value_str}\n    0 ставок, 0 {sym}"
        )

    formatted_options = "\n\n".join(options_lines)

    text = (
        f"<b>🎯 Новое событие для предсказаний</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{description}\n\n"
        f"<b>Варианты:</b>\n{formatted_options}\n\n"
        f"<b>Общий банк:</b> 0 {sym}\n"
        f"<b>Ставка:</b> {min_bet}-{max_bet} {sym}\n"
        f"<b>Валюта:</b> {currency}\n"
        f"<b>Дедлайн:</b> {deadline or 'Не указан'}\n"
        f"<b>Статус:</b> active"
    )

    keyboard = bet_event_button(event_id)

    try:
        msg_result = await send_message(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": keyboard},
            },
            bot_token=bot_token,
        )
        await execute(
            "UPDATE prediction_events SET telegram_message_id = %s WHERE id = %s",
            [msg_result["message_id"], event_id],
        )
    except Exception as e:
        logger.warning("Не удалось отправить анонс события в чат: %s", e)


async def _send_creator_message(
    *,
    bot_token: str,
    event_id: int,
    creator_id: int,
    title: str,
    description: str,
    options: list[Any],
    min_bet: int,
    max_bet: int,
    sym: str,
) -> None:
    """Личное сообщение создателю с кнопками выбора варианта."""
    opts_for_kb = [{"text": opt.text, "id": opt.id} for opt in options]
    keyboard = bet_options_keyboard(event_id, opts_for_kb)

    options_text = "\n".join(
        f"  • {opt.text}"
        + (f" <code>({escape_html(opt.value)})</code>" if opt.value else "")
        for opt in options
    )

    text = (
        f"<b>✅ Событие создано!</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{description}\n\n"
        f"<b>Варианты:</b>\n{options_text}\n\n"
        f"<b>Ставка:</b> {min_bet}-{max_bet} {sym}\n\n"
        f"<i>Выберите вариант для предсказания:</i>"
    )

    try:
        await send_message(
            {
                "chat_id": creator_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": keyboard},
            },
            bot_token=bot_token,
        )
    except Exception as e:
        logger.warning("Не удалось отправить личное сообщение создателю: %s", e)


# ---------------------------------------------------------------------------
# Список / детали событий
# ---------------------------------------------------------------------------

async def list_events(
    *,
    status: str | None = None,
    chat_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Список событий с агрегированной статистикой."""
    conditions: list[str] = []
    params: list[Any] = []

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
                'id', option_id, 'text', text, 'value', value,
                'total_bets', total_bets, 'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    events = await fetch_all(query, params)
    return {"ok": True, "events": events, "total": len(events)}


async def get_event(event_id: int) -> dict | None:
    """Детали события с полной информацией."""
    return await fetch_one(
        """
        SELECT
            e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id, 'text', text, 'value', value,
                'total_bets', total_bets, 'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options,
            (SELECT COUNT(*) FROM prediction_bets WHERE event_id = e.id) as bet_count,
            (SELECT json_agg(json_build_object(
                'user_id', user_id, 'option_id', option_id,
                'amount', amount, 'status', status
            )) FROM prediction_bets WHERE event_id = e.id AND e.is_anonymous = FALSE) as bets
        FROM prediction_events e
        WHERE e.id = %s
        """,
        [event_id],
    )


# ---------------------------------------------------------------------------
# Размещение ставки
# ---------------------------------------------------------------------------

async def place_bet(
    *,
    event_id: int,
    option_id: str,
    user_id: int,
    amount: int,
    source: str = "auto",
    bot_id: int | None = None,
) -> dict:
    """Разместить ставку: через баланс (AC) или Stars invoice (XTR)."""
    event = await fetch_one(
        "SELECT * FROM prediction_events WHERE id = %s", [event_id]
    )
    if not event:
        raise ValueError("Событие не найдено")
    if event["status"] != "active":
        raise ValueError("Событие не активно")

    currency = event.get("currency") or "XTR"
    sym = currency_symbol(currency)

    if amount < event["min_bet"] or amount > event["max_bet"]:
        raise ValueError(
            f"Сумма ставки должна быть от {event['min_bet']} до {event['max_bet']} {sym}"
        )

    option = await fetch_one(
        "SELECT * FROM prediction_options WHERE event_id = %s AND option_id = %s",
        [event_id, option_id],
    )
    if not option:
        raise ValueError("Вариант не найден")

    resolved_source = source
    if resolved_source == "auto":
        resolved_source = "balance" if is_virtual(currency) else "payment"

    event_bot_id = int(event["bot_id"]) if event.get("bot_id") is not None else None
    event_bot_token, _ = await resolve_bot_context(event_bot_id)

    if resolved_source == "balance":
        return await _place_balance_bet(
            event=event,
            option=option,
            user_id=user_id,
            amount=amount,
            currency=currency,
            sym=sym,
            bot_token=event_bot_token,
        )
    else:
        return await _place_payment_bet(
            event=event,
            option=option,
            user_id=user_id,
            amount=amount,
            currency=currency,
            bot_token=event_bot_token,
        )


async def _place_balance_bet(
    *,
    event: dict,
    option: dict,
    user_id: int,
    amount: int,
    currency: str,
    sym: str,
    bot_token: str,
) -> dict:
    """Ставка с виртуального баланса (AC)."""
    initial = INITIAL_BALANCE.get(currency, 0)
    if initial > 0:
        await fetch_one("SELECT ensure_user_balance(%s, %s)", [user_id, initial])

    deducted = await balance.deduct_from_balance(
        user_id=user_id,
        amount=amount,
        transaction_type="bet",
        reference_type="prediction_event",
        reference_id=event["id"],
        description=f"Ставка {amount} {sym} на '{option['text']}' ({event['title'][:50]})",
    )
    if not deducted:
        user_bal = await balance.get_user_balance(user_id)
        raise ValueError(
            f"Недостаточно средств. Баланс: {user_bal} {sym}, ставка: {amount} {sym}"
        )

    bet = await execute_returning(
        """
        INSERT INTO prediction_bets
        (event_id, option_id, user_id, amount, status, source, currency)
        VALUES (%s, %s, %s, %s, 'active', 'balance', %s)
        RETURNING id
        """,
        [event["id"], option["option_id"], user_id, amount, currency],
    )

    await _update_pool_stats(event["id"], option["option_id"], amount)

    new_bal = await balance.get_user_balance(user_id)
    try:
        await send_message(
            {
                "chat_id": user_id,
                "text": (
                    f"✅ <b>Ставка принята!</b>\n\n"
                    f"<b>Событие:</b> {event['title']}\n"
                    f"<b>Вариант:</b> {option['text']}\n"
                    f"<b>Сумма:</b> {amount} {sym}\n"
                    f"<b>Остаток:</b> {new_bal} {sym}"
                ),
                "parse_mode": "HTML",
            },
            bot_token=bot_token,
        )
    except Exception as e:
        logger.warning("Не удалось отправить подтверждение ставки: %s", e)

    return {
        "ok": True,
        "bet_id": bet["id"],
        "source": "balance",
        "currency": currency,
        "balance_after": new_bal,
    }


async def _place_payment_bet(
    *,
    event: dict,
    option: dict,
    user_id: int,
    amount: int,
    currency: str,
    bot_token: str,
) -> dict:
    """Ставка через Stars invoice (XTR)."""
    sym = currency_symbol(currency)

    transaction = await execute_returning(
        """
        INSERT INTO star_transactions
        (user_id, transaction_type, amount, payload, status, metadata)
        VALUES (%s, 'payment', %s, %s, 'pending', %s)
        RETURNING id
        """,
        [
            user_id,
            amount,
            f"bet_{event['id']}_{option['option_id']}",
            {"event_id": event["id"], "option_id": option["option_id"]},
        ],
    )

    bet = await execute_returning(
        """
        INSERT INTO prediction_bets
        (event_id, option_id, user_id, amount, status, transaction_id, source, currency)
        VALUES (%s, %s, %s, %s, 'active', %s, 'payment', %s)
        RETURNING id
        """,
        [event["id"], option["option_id"], user_id, amount, transaction["id"], currency],
    )

    invoice_payload = {
        "chat_id": user_id,
        "title": f"Ставка: {event['title'][:30]}",
        "description": f"Ставка {amount} {sym} на вариант '{option['text']}'",
        "payload": f"bet_{bet['id']}_{transaction['id']}",
        "currency": "XTR",
        "prices": [{"label": "Ставка", "amount": amount}],
    }

    invoice_result = await send_invoice(invoice_payload, bot_token=bot_token)

    return {
        "ok": True,
        "bet_id": bet["id"],
        "transaction_id": transaction["id"],
        "source": "payment",
        "currency": currency,
        "invoice": invoice_result,
    }


async def _update_pool_stats(event_id: int, option_id: str, amount: int) -> None:
    """Обновить статистику банка и варианта после ставки."""
    await execute(
        """
        UPDATE prediction_options
        SET total_bets = total_bets + 1, total_amount = total_amount + %s
        WHERE event_id = %s AND option_id = %s
        """,
        [amount, event_id, option_id],
    )
    await execute(
        "UPDATE prediction_events SET total_pool = total_pool + %s WHERE id = %s",
        [amount, event_id],
    )


# ---------------------------------------------------------------------------
# Разрешение события
# ---------------------------------------------------------------------------

async def resolve_event(
    event_id: int,
    *,
    winning_option_ids: list[str],
    resolution_source: str = "manual",
    resolution_data: dict | None = None,
) -> dict:
    """Разрешить событие: рассчитать выплаты, уведомить участников."""
    event = await fetch_one(
        "SELECT * FROM prediction_events WHERE id = %s", [event_id]
    )
    if not event:
        raise ValueError("Event not found")
    if event["status"] == "resolved":
        raise ValueError("Event already resolved")

    event_bot_id = int(event["bot_id"]) if event.get("bot_id") is not None else None
    event_bot_token, _ = await resolve_bot_context(event_bot_id)

    currency = event.get("currency") or "XTR"
    sym = currency_symbol(currency)

    all_bets = await fetch_all(
        "SELECT * FROM prediction_bets WHERE event_id = %s AND status = 'active'",
        [event_id],
    )

    total_pool = event["total_pool"]
    winning_bets = [b for b in all_bets if b["option_id"] in winning_option_ids]
    losing_bets = [b for b in all_bets if b["option_id"] not in winning_option_ids]

    payouts_summary: list[dict] = []

    if not winning_bets:
        # Нет победителей → возврат всем
        for bet in all_bets:
            await execute(
                "UPDATE prediction_bets SET status = 'refunded', payout = amount WHERE id = %s",
                [bet["id"]],
            )
            await balance.add_to_balance(
                user_id=bet["user_id"],
                amount=bet["amount"],
                transaction_type="refund",
                reference_type="prediction_bet",
                reference_id=bet["id"],
                description=f"Возврат ставки ({currency}): '{event['title']}'",
            )
            payouts_summary.append({
                "user_id": bet["user_id"],
                "amount": bet["amount"],
                "type": "refund",
            })
    else:
        total_winning_amount = sum(b["amount"] for b in winning_bets)
        for bet in winning_bets:
            payout = int((bet["amount"] / total_winning_amount) * total_pool)
            await execute(
                "UPDATE prediction_bets SET status = 'won', payout = %s WHERE id = %s",
                [payout, bet["id"]],
            )
            await balance.add_to_balance(
                user_id=bet["user_id"],
                amount=payout,
                transaction_type="win",
                reference_type="prediction_bet",
                reference_id=bet["id"],
                description=f"Выигрыш ({currency}) в '{event['title']}'",
            )
            profit = payout - bet["amount"]
            payouts_summary.append({
                "user_id": bet["user_id"],
                "bet_amount": bet["amount"],
                "payout": payout,
                "profit": profit,
                "type": "win",
            })

        for bet in losing_bets:
            await execute(
                "UPDATE prediction_bets SET status = 'lost' WHERE id = %s",
                [bet["id"]],
            )
            await balance.record_loss(bet["user_id"], bet["amount"])
            payouts_summary.append({
                "user_id": bet["user_id"],
                "bet_amount": bet["amount"],
                "type": "loss",
            })

    # Уведомления
    await _send_resolution_notifications(
        payouts=payouts_summary,
        event_title=event["title"],
        sym=sym,
        bot_token=event_bot_token,
    )

    # Запись разрешения
    await execute(
        """
        INSERT INTO prediction_resolutions
        (event_id, winning_option_ids, resolution_source, resolution_data,
         total_winners, total_payout)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [
            event_id,
            winning_option_ids,
            resolution_source,
            Json(resolution_data) if resolution_data else None,
            len(winning_bets),
            sum(item.get("payout", 0) for item in payouts_summary if item["type"] == "win"),
        ],
    )

    await execute(
        "UPDATE prediction_events SET status = 'resolved', updated_at = NOW() WHERE id = %s",
        [event_id],
    )

    return {
        "ok": True,
        "event_id": event_id,
        "currency": currency,
        "winners": len(winning_bets),
        "total_payout": sum(b["payout"] for b in winning_bets) if winning_bets else 0,
    }


async def _send_resolution_notifications(
    *,
    payouts: list[dict],
    event_title: str,
    sym: str,
    bot_token: str,
) -> None:
    """Уведомить каждого участника о результате."""
    for item in payouts:
        user_id = item["user_id"]

        if item["type"] == "win":
            text = (
                f"🎉 <b>Поздравляем! Вы выиграли!</b>\n\n"
                f"<b>Событие:</b> {event_title}\n\n"
                f"<b>Ваша ставка:</b> {item['bet_amount']} {sym}\n"
                f"<b>Выплата:</b> {item['payout']} {sym}\n"
                f"<b>Чистая прибыль:</b> +{item['profit']} {sym}\n\n"
                f"<i>Выигрыш зачислен на ваш баланс.</i>"
            )
        elif item["type"] == "loss":
            text = (
                f"😔 <b>К сожалению, вы проиграли</b>\n\n"
                f"<b>Событие:</b> {event_title}\n\n"
                f"<b>Ваша ставка:</b> {item['bet_amount']} {sym}\n\n"
                f"<i>Попробуйте в следующий раз!</i>"
            )
        else:
            text = (
                f"↩️ <b>Ставка возвращена</b>\n\n"
                f"<b>Событие:</b> {event_title}\n\n"
                f"<b>Возвращено:</b> {item['amount']} {sym}\n\n"
                f"<i>Событие завершилось без победителей, ставка полностью возвращена.</i>"
            )

        try:
            await send_message(
                {"chat_id": user_id, "text": text, "parse_mode": "HTML"},
                bot_token=bot_token,
            )
        except Exception as e:
            logger.warning("Не удалось отправить уведомление пользователю %s: %s", user_id, e)


# ---------------------------------------------------------------------------
# Авто-разрешение (LLM)
# ---------------------------------------------------------------------------

async def auto_resolve_event(event_id: int) -> dict:
    """Автоматическое разрешение через LLM-MCP."""
    if not settings.llm_mcp_enabled:
        raise ValueError("LLM-MCP integration disabled")

    event = await fetch_one(
        """
        SELECT e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id, 'text', text, 'value', value
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        WHERE e.id = %s
        """,
        [event_id],
    )
    if not event:
        raise ValueError("Event not found")
    if event["status"] == "resolved":
        raise ValueError("Event already resolved")

    options_list = "\n".join(
        f"{i+1}. {opt['text']}" + (f" ({opt['value']})" if opt.get("value") else "")
        for i, opt in enumerate(event.get("options") or [])
    )

    prompt = f"""Ты - эксперт по анализу событий и проверке фактов. Твоя задача - определить результат события для системы предсказаний.

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
{{"decision": "option_id" или "refund", "reasoning": "краткое объяснение решения", "confidence": 0-100}}

ВАЖНО:
- Если confidence < 70 - лучше вернуть "refund"
- Используй только option_id из списка выше или "refund"
- Отвечай только JSON, без markdown и комментариев
"""

    async with httpx.AsyncClient(timeout=120.0) as client:
        llm_response = await client.post(
            f"{settings.llm_mcp_url}/v1/llm/request",
            json={
                "task": "chat",
                "provider": "auto",
                "model": "claude-3-7-sonnet",
                "prompt": prompt,
                "priority": 5,
                "source": "telegram-api-predictions",
                "max_attempts": 3,
                "constraints": {"force_cloud": True, "prefer_local": False},
            },
        )
        llm_response.raise_for_status()
        job_id = llm_response.json().get("job_id")
        if not job_id:
            raise RuntimeError("LLM-MCP did not return job_id")

        logger.info("LLM job created: %s for event %s", job_id, event_id)

        # Polling
        for _ in range(45):
            await asyncio.sleep(2)
            job_resp = await client.get(f"{settings.llm_mcp_url}/v1/jobs/{job_id}")
            job_resp.raise_for_status()
            job_data = job_resp.json()
            status = job_data.get("status")

            if status == "done":
                result = job_data.get("result", {})
                break
            elif status == "error":
                raise RuntimeError(f"LLM job failed: {job_data.get('error')}")
        else:
            raise TimeoutError("LLM job timeout")

    llm_text = result.get("response", result.get("content", ""))
    if "```json" in llm_text:
        llm_text = llm_text.split("```json")[1].split("```")[0].strip()
    elif "```" in llm_text:
        llm_text = llm_text.split("```")[1].split("```")[0].strip()

    decision_data = json_lib.loads(llm_text)
    decision = decision_data.get("decision")
    reasoning = decision_data.get("reasoning", "No reasoning provided")
    confidence = decision_data.get("confidence", 0)

    logger.info("LLM decision for event %s: %s (confidence: %s%%)", event_id, decision, confidence)

    if decision == "refund":
        winning_ids: list[str] = []
    else:
        valid = any(opt["id"] == decision for opt in (event.get("options") or []))
        if not valid:
            raise ValueError(f"LLM returned invalid option_id: {decision}")
        winning_ids = [decision]

    res = await resolve_event(
        event_id,
        winning_option_ids=winning_ids,
        resolution_source="llm-auto",
        resolution_data={
            "llm_decision": decision,
            "reasoning": reasoning,
            "confidence": confidence,
            "job_id": job_id,
        },
    )

    return {
        **res,
        "llm_decision": decision,
        "reasoning": reasoning,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Список ставок пользователя
# ---------------------------------------------------------------------------

async def list_user_bets(
    *,
    user_id: int,
    event_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    """Ставки пользователя с информацией о событии и варианте."""
    conditions = ["user_id = %s"]
    params: list[Any] = [user_id]

    if event_id:
        conditions.append("event_id = %s")
        params.append(event_id)
    if status:
        conditions.append("status = %s")
        params.append(status)

    where_clause = " AND ".join(conditions)

    bets = await fetch_all(
        f"""
        SELECT b.*, e.title as event_title, o.text as option_text
        FROM prediction_bets b
        JOIN prediction_events e ON b.event_id = e.id
        JOIN prediction_options o ON b.event_id = o.event_id AND b.option_id = o.option_id
        WHERE {where_clause}
        ORDER BY b.created_at DESC
        LIMIT %s
        """,
        [*params, limit],
    )
    return {"ok": True, "bets": bets}


# ---------------------------------------------------------------------------
# Stars payments
# ---------------------------------------------------------------------------

async def create_invoice(
    *,
    chat_id: int,
    title: str,
    description: str,
    payload: str,
    currency: str,
    prices: list[dict],
    message_thread_id: int | None = None,
    reply_to_message_id: int | None = None,
    bot_id: int | None = None,
) -> dict:
    """Создать счёт на оплату Stars."""
    telegram_payload: dict[str, Any] = {
        "chat_id": chat_id,
        "title": title,
        "description": description,
        "payload": payload,
        "currency": currency,
        "prices": prices,
    }
    if message_thread_id:
        telegram_payload["message_thread_id"] = message_thread_id
    if reply_to_message_id:
        telegram_payload["reply_to_message_id"] = reply_to_message_id

    bot_token, _ = await resolve_bot_context(bot_id)
    result = await send_invoice(telegram_payload, bot_token=bot_token)
    return {"ok": True, "result": result}


async def refund_payment(
    *,
    user_id: int,
    telegram_payment_charge_id: str,
    bot_id: int | None = None,
) -> dict:
    """Возврат Stars платежа."""
    bot_token, _ = await resolve_bot_context(bot_id)
    result = await refund_star_payment(
        {"user_id": user_id, "telegram_payment_charge_id": telegram_payment_charge_id},
        bot_token=bot_token,
    )
    await execute(
        "UPDATE star_transactions SET status = 'refunded', updated_at = NOW() WHERE telegram_payment_charge_id = %s",
        [telegram_payment_charge_id],
    )
    return {"ok": True, "result": result}


async def list_star_transactions(
    *,
    user_id: int | None = None,
    bot_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """История транзакций Stars."""
    conditions: list[str] = []
    params: list[Any] = []
    if user_id:
        conditions.append("user_id = %s")
        params.append(user_id)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    transactions = await fetch_all(
        f"SELECT * FROM star_transactions {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params,
    )

    bot_token, _ = await resolve_bot_context(bot_id)
    telegram_txs = await get_star_transactions(bot_token=bot_token)

    return {
        "ok": True,
        "transactions": transactions,
        "telegram_transactions": telegram_txs,
    }


async def list_currencies() -> dict:
    """Список доступных валют."""
    currencies = await fetch_all(
        "SELECT * FROM currencies WHERE active = TRUE ORDER BY code", []
    )
    if not currencies:
        return {
            "ok": True,
            "currencies": [
                {"code": "XTR", "display_name": "Telegram Stars", "symbol": "⭐",
                 "is_virtual": False, "initial_balance": 0},
                {"code": "AC", "display_name": "Arena Coin", "symbol": "🪙",
                 "is_virtual": True, "initial_balance": 100},
            ],
        }
    return {"ok": True, "currencies": [dict(c) for c in currencies]}
