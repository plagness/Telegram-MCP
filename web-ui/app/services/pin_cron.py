"""Cron-сервис обновления закрепов.

Периодически проверяет chat_pins с auto_update=TRUE и обновляет
контент (текст + клавиатура) в Telegram, если прошло достаточно времени.
"""

from __future__ import annotations

import asyncio
import logging

from ..db import fetch_all

logger = logging.getLogger(__name__)

# Минимальный интервал между обновлениями (секунды)
_MIN_INTERVAL = 60

# Интервал проверки cron (секунды)
_CHECK_INTERVAL = 120

_task: asyncio.Task | None = None


async def _tick():
    """Один цикл обновления закрепов."""
    from ..routers.pins import update_pin

    rows = await fetch_all(
        """
        SELECT chat_id, pin_type, update_interval, last_updated
        FROM chat_pins
        WHERE auto_update = TRUE
          AND message_id IS NOT NULL
          AND (last_updated IS NULL
               OR last_updated < now() - make_interval(secs := GREATEST(update_interval, %s)))
        """,
        [_MIN_INTERVAL],
    )

    if not rows:
        return

    logger.info("pin_cron: %d pins to update", len(rows))

    for row in rows:
        chat_id = row["chat_id"]
        try:
            await update_pin(str(chat_id))
            logger.debug("pin_cron: updated %s", chat_id)
        except Exception as e:
            logger.warning("pin_cron: failed to update %s: %s", chat_id, e)

        # Пауза между обновлениями чтобы не флудить API
        await asyncio.sleep(2)


async def _loop():
    """Бесконечный цикл проверки и обновления."""
    while True:
        try:
            await _tick()
        except Exception as e:
            logger.error("pin_cron: unhandled error: %s", e)
        await asyncio.sleep(_CHECK_INTERVAL)


def start_pin_cron():
    """Запустить cron-задачу (вызывается из lifespan)."""
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_loop())
    logger.info("pin_cron started (interval=%ds)", _CHECK_INTERVAL)


def stop_pin_cron():
    """Остановить cron-задачу."""
    global _task
    if _task:
        _task.cancel()
        _task = None
        logger.info("pin_cron stopped")
