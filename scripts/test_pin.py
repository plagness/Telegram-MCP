#!/usr/bin/env python3
"""
Тестовый скрипт: Pin/Unpin и автопин для прогресс-баров.

Демонстрирует:
  - Ручной pin/unpin отдельных сообщений
  - Автопин для долгих процессов (auto_pin=True)
  - Тихое закрепление без уведомлений (disable_notification=True)

Использование:
    python scripts/test_pin.py --chat-id -1001455291970
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI


async def test_manual_pin(api: TelegramAPI, chat_id: int | str):
    """Тест ручного pin/unpin."""
    print("\n🧪 Тест 1: Ручной pin/unpin")

    # Отправляем сообщение
    msg = await api.send_message(
        chat_id,
        text="📌 <b>Это сообщение будет закреплено</b>\n\nПин через 2 секунды...",
        parse_mode="HTML"
    )
    message_id = msg["id"]
    print(f"✅ Сообщение {message_id} отправлено")
    await asyncio.sleep(2)

    # Закрепляем (тихо, без уведомления)
    await api.pin_message(message_id, disable_notification=True)
    print(f"📌 Сообщение {message_id} закреплено (тихо)")
    await asyncio.sleep(3)

    # Открепляем
    await api.unpin_message(message_id)
    print(f"📍 Сообщение {message_id} откреплено")
    await asyncio.sleep(1)


async def test_auto_pin_progress(api: TelegramAPI, chat_id: int | str):
    """Тест автопина для прогресс-бара."""
    print("\n🧪 Тест 2: Автопин для прогресс-бара (3 параллельных процесса)")

    # Симулируем 3 параллельные загрузки с автопином
    tasks = []
    for i in range(1, 4):
        tasks.append(simulate_long_process(api, chat_id, process_id=i))

    await asyncio.gather(*tasks)
    print("✅ Все процессы завершены, все сообщения откреплены")


async def simulate_long_process(api: TelegramAPI, chat_id: int | str, process_id: int):
    """Симуляция долгого процесса с автопином."""
    steps = 8
    step_duration = 0.6

    async with api.progress(chat_id, auto_pin=True) as p:
        # Процесс автоматически закреплён (без уведомления)
        for step in range(1, steps + 1):
            await p.update(
                step,
                steps,
                f"<b>Процесс #{process_id}</b>: Шаг {step}/{steps}"
            )
            await asyncio.sleep(step_duration)

        # Финальное сообщение (остаётся в чате, но открепляется)
        await p.done(final_text=f"✅ <b>Процесс #{process_id}</b> завершён успешно!")
    # При выходе из контекста сообщение автоматически откреплено


async def test_regular_progress(api: TelegramAPI, chat_id: int | str):
    """Тест обычного прогресса БЕЗ автопина (для сравнения)."""
    print("\n🧪 Тест 3: Обычный прогресс БЕЗ автопина (удаляется по завершению)")

    async with api.progress(chat_id, auto_pin=False) as p:
        for step in range(1, 6):
            await p.update(step, 5, f"Обычный прогресс: {step}/5 (не закреплён)")
            await asyncio.sleep(0.5)
        # Сообщение удалится при выходе из контекста

    print("✅ Прогресс завершён и удалён")


async def main(base_url: str, chat_id: int | str):
    """Запуск всех тестов pin/unpin."""
    async with TelegramAPI(base_url) as api:
        print(f"🚀 Тестирование Pin/Unpin в чате {chat_id}\n")

        # Тест 1: Ручной pin/unpin
        await test_manual_pin(api, chat_id)
        await asyncio.sleep(2)

        # Тест 2: Автопин для параллельных процессов
        await test_auto_pin_progress(api, chat_id)
        await asyncio.sleep(2)

        # Тест 3: Обычный прогресс без пина
        await test_regular_progress(api, chat_id)

        print("\n✅ Все тесты завершены!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест Pin/Unpin и автопина")
    parser.add_argument(
        "--chat-id",
        default=os.environ.get("TEST_CHAT_ID"),
        help="Telegram chat_id",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TELEGRAM_API_URL", "http://localhost:8081"),
        help="Базовый URL telegram-api",
    )
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    asyncio.run(main(args.base_url, args.chat_id))
