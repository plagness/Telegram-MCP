#!/usr/bin/env python3
"""
Тестовый скрипт: паттерн прогресс-сообщений (send → edit → delete).

Демонстрирует ProgressContext из SDK — аналог ProgressNotifier из монолита.
Сообщение создаётся, обновляется с прогресс-баром, затем удаляется.

Использование:
    python scripts/test_progress.py --chat-id -100123456789
    python scripts/test_progress.py --chat-id -100123456789 --steps 10 --delay 0.5
    python scripts/test_progress.py --chat-id -100123456789 --keep

Переменные окружения:
    TELEGRAM_API_URL — базовый URL (по умолчанию http://localhost:8081)
    TEST_CHAT_ID     — chat_id
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI, TelegramAPIError


STAGE_LABELS = [
    "Инициализация",
    "Загрузка данных",
    "Обработка записей",
    "Анализ метрик",
    "Генерация отчёта",
    "Построение графиков",
    "Оптимизация",
    "Валидация результатов",
    "Сохранение в БД",
    "Финализация",
]


async def main(
    base_url: str,
    chat_id: int | str,
    steps: int = 5,
    delay: float = 1.0,
    keep: bool = False,
) -> None:
    async with TelegramAPI(base_url) as api:
        print(f"Запуск прогресс-теста: {steps} шагов, задержка {delay}с, keep={keep}\n")

        # Вариант 1: Используем ProgressContext (автоматическое удаление)
        if not keep:
            print("--- Вариант 1: ProgressContext (auto-delete) ---")
            async with api.progress(chat_id) as p:
                for i in range(1, steps + 1):
                    label = STAGE_LABELS[(i - 1) % len(STAGE_LABELS)]
                    print(f"  [{i}/{steps}] {label}")
                    await p.update(i, steps, label)
                    await asyncio.sleep(delay)
            print("  Сообщение удалено автоматически.\n")
        else:
            # Вариант 2: Оставляем финальное сообщение
            print("--- Вариант 2: ProgressContext с финальным сообщением ---")
            async with api.progress(chat_id) as p:
                for i in range(1, steps + 1):
                    label = STAGE_LABELS[(i - 1) % len(STAGE_LABELS)]
                    print(f"  [{i}/{steps}] {label}")
                    await p.update(i, steps, label)
                    await asyncio.sleep(delay)
                await p.done(final_text="Готово! Все этапы завершены.")
            print("  Финальное сообщение оставлено.\n")

        # Вариант 3: Ручное управление (без контекстного менеджера)
        print("--- Вариант 3: ручной send → edit → delete ---")
        try:
            msg = await api.send_message(
                chat_id=chat_id,
                text="Ручной прогресс: начало...",
                live=True,
            )
            msg_id = msg.get("id")
            print(f"  Отправлено: id={msg_id}")

            for i in range(1, 4):
                await asyncio.sleep(delay)
                await api.edit_message(
                    msg_id,
                    text=f"Ручной прогресс: этап {i}/3",
                )
                print(f"  Обновлено: этап {i}/3")

            await asyncio.sleep(delay)
            await api.delete_message(msg_id)
            print("  Удалено.")
        except TelegramAPIError as e:
            print(f"  Ошибка: {e}")

        print("\nГотово.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест прогресс-сообщений через telegram-api SDK")
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
    parser.add_argument("--steps", type=int, default=5, help="Количество шагов прогресса (по умолчанию 5)")
    parser.add_argument("--delay", type=float, default=1.0, help="Задержка между шагами в секундах (по умолчанию 1.0)")
    parser.add_argument("--keep", action="store_true", help="Оставить финальное сообщение вместо удаления")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    asyncio.run(main(args.base_url, args.chat_id, args.steps, args.delay, args.keep))
