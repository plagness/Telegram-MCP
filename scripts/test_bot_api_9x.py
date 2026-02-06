#!/usr/bin/env python3
"""
Тестовый скрипт: Bot API 9.x — Checklists, Stars, Gifts, Stories.

Демонстрирует:
  - Отправка и редактирование чек-листов (Bot API 9.1)
  - Проверка баланса звёзд (Bot API 9.1)
  - Подарки премиум-подписок (Bot API 9.3)
  - Репост историй (Bot API 9.3)

Использование:
    python scripts/test_bot_api_9x.py --chat-id -1001455291970
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI


async def test_checklist(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None):
    """Тест отправки и редактирования чек-листа."""
    print("\n🧪 Тест 1: Чек-листы (Bot API 9.1)")

    # Отправка чек-листа
    tasks = [
        {"text": "Подготовить данные", "is_completed": False},
        {"text": "Запустить обработку", "is_completed": False},
        {"text": "Проверить результаты", "is_completed": False},
        {"text": "Отправить отчёт", "is_completed": False},
    ]

    try:
        result = await api.send_checklist(
            chat_id=chat_id,
            bot_id=bot_id,
            title="🚀 План развёртывания v2026.02.6",
            tasks=tasks,
        )
        message_id = result.get("result", {}).get("message_id")
        print(f"✅ Чек-лист отправлен (message_id={message_id})")

        await asyncio.sleep(3)

        # Редактирование чек-листа (отметим первые 2 задачи как выполненные)
        # ВАЖНО: внутренний ID (из БД) нужен для edit, а не telegram_message_id
        # В реальном кейсе получаем его из api.list_messages()
        print("⏩ Редактирование чек-листа пропущено (требуется внутренний ID из БД)")
        # updated_tasks = tasks.copy()
        # updated_tasks[0]["is_completed"] = True
        # updated_tasks[1]["is_completed"] = True
        # await api.edit_checklist(internal_message_id, updated_tasks)
        # print(f"✅ Чек-лист обновлён (2 задачи выполнены)")
    except Exception as e:
        print(f"❌ Ошибка чек-листа: {e}")


async def test_stars_balance(api: TelegramAPI, bot_id: int | None = None):
    """Тест получения баланса звёзд."""
    print("\n🧪 Тест 2: Баланс звёзд (Bot API 9.1)")

    try:
        balance = await api.get_star_balance(bot_id=bot_id)
        star_count = balance.get("result", {}).get("star_count", 0)
        print(f"⭐ Баланс звёзд бота: {star_count}")
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")


async def test_gifts(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None):
    """Тест подарков (примерный, требуется реальный user_id)."""
    print("\n🧪 Тест 3: Подарки (Bot API 9.3)")

    # Примечание: giftPremiumSubscription требует:
    # 1. Достаточно звёзд на балансе
    # 2. Валидный user_id
    # 3. Может не работать в тестовом режиме

    try:
        # Проверка подарков в чате
        gifts = await api.get_chat_gifts(chat_id, bot_id=bot_id)
        print(f"🎁 Подарки в чате: {len(gifts)} шт.")

        # Подарить премиум (закомментировано для безопасности)
        # await api.gift_premium(user_id=123456789, duration_months=1, star_count=100)
        # print("✅ Премиум подарен!")
    except Exception as e:
        print(f"❌ Ошибка подарков: {e}")


async def test_repost_story(api: TelegramAPI, chat_id: int | str):
    """Тест репоста истории (требуется реальный story_id)."""
    print("\n🧪 Тест 4: Репост историй (Bot API 9.3)")

    # Примечание: repostStory требует:
    # 1. Валидный story_id из канала-источника
    # 2. Права на репост в канале-получателе
    # 3. Может не работать в тестовом режиме

    print("⏩ Репост истории пропущен (требуется валидный story_id)")
    # try:
    #     result = await api.repost_story(
    #         chat_id=chat_id,
    #         from_chat_id="@source_channel",
    #         story_id=12345,
    #     )
    #     print("✅ История репостнута!")
    # except Exception as e:
    #     print(f"❌ Ошибка репоста: {e}")


async def main(base_url: str, chat_id: int | str, bot_id: int | None = None):
    """Запуск всех тестов Bot API 9.x."""
    async with TelegramAPI(base_url) as api:
        print(f"🚀 Тестирование Bot API 9.x функций (v2026.02.6)\n")

        # Тест 1: Чек-листы
        await test_checklist(api, chat_id, bot_id=bot_id)
        await asyncio.sleep(2)

        # Тест 2: Баланс звёзд
        await test_stars_balance(api, bot_id=bot_id)
        await asyncio.sleep(1)

        # Тест 3: Подарки
        await test_gifts(api, chat_id, bot_id=bot_id)
        await asyncio.sleep(1)

        # Тест 4: Репост историй
        await test_repost_story(api, chat_id)

        print("\n✅ Все тесты завершены!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест Bot API 9.x функций")
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
    parser.add_argument("--bot-id", type=int, default=None, help="Явный bot_id для мультибот-теста")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    bot_id = args.bot_id or (int(os.environ["TEST_BOT_ID"]) if os.environ.get("TEST_BOT_ID") else None)
    asyncio.run(main(args.base_url, args.chat_id, bot_id=bot_id))
