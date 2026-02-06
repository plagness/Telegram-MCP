#!/usr/bin/env python3
"""
Тестовый скрипт: работа с реакциями.

Использование:
    python scripts/test_reactions.py --chat-id -100123456789 --message-id 12345

Переменные окружения:
    TELEGRAM_API_URL — базовый URL (по умолчанию http://localhost:8081)
    TEST_CHAT_ID     — chat_id для тестов
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI, TelegramAPIError


async def test_reactions(
    api: TelegramAPI,
    chat_id: int | str,
    message_id: int | None = None,
    bot_id: int | None = None,
) -> None:
    """Тест реакций на сообщение."""
    # Если message_id не указан, отправляем тестовое сообщение
    if message_id is None:
        print("=== Создание тестового сообщения ===")
        try:
            msg = await api.send_message(
                chat_id=chat_id,
                bot_id=bot_id,
                text="<b>Тест реакций</b>\n\nБот будет ставить реакции на это сообщение.",
                parse_mode="HTML",
            )
            message_id = msg.get("telegram_message_id")
            print(f"Тестовое сообщение создано: telegram_message_id={message_id}")
        except TelegramAPIError as e:
            print(f"Ошибка создания сообщения: {e}")
            return

    if not message_id:
        print("Не удалось получить telegram_message_id")
        return

    # 1. Установка реакции 👍
    print("\n=== Установка реакции 👍 ===")
    try:
        await api.set_reaction(
            chat_id=chat_id,
            message_id=message_id,
            bot_id=bot_id,
            reaction=[{"type": "emoji", "emoji": "👍"}],
        )
        print("   Реакция 👍 установлена")
        await asyncio.sleep(2)
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")

    # 2. Изменение на 🔥
    print("\n=== Изменение реакции на 🔥 ===")
    try:
        await api.set_reaction(
            chat_id=chat_id,
            message_id=message_id,
            bot_id=bot_id,
            reaction=[{"type": "emoji", "emoji": "🔥"}],
        )
        print("   Реакция изменена на 🔥")
        await asyncio.sleep(2)
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")

    # 3. Добавление ещё одной реакции ❤️
    print("\n=== Добавление реакции ❤️ (две реакции) ===")
    try:
        await api.set_reaction(
            chat_id=chat_id,
            message_id=message_id,
            bot_id=bot_id,
            reaction=[
                {"type": "emoji", "emoji": "🔥"},
                {"type": "emoji", "emoji": "❤️"},
            ],
        )
        print("   Реакции: 🔥 ❤️")
        await asyncio.sleep(2)
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")

    # 4. Большая анимация 👏
    print("\n=== Большая анимация 👏 ===")
    try:
        await api.set_reaction(
            chat_id=chat_id,
            message_id=message_id,
            bot_id=bot_id,
            reaction=[{"type": "emoji", "emoji": "👏"}],
            is_big=True,
        )
        print("   Большая реакция 👏")
        await asyncio.sleep(2)
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")

    # 5. Удаление всех реакций
    print("\n=== Удаление всех реакций ===")
    try:
        await api.set_reaction(
            chat_id=chat_id,
            message_id=message_id,
            bot_id=bot_id,
            reaction=None,  # None удаляет все реакции бота
        )
        print("   Все реакции удалены")
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")

    # 6. Список реакций
    print("\n=== Список реакций из БД ===")
    try:
        reactions = await api.list_reactions(chat_id=str(chat_id), limit=10, bot_id=bot_id)
        print(f"   Найдено реакций в БД: {len(reactions)}")
        for r in reactions[:5]:
            emoji = r.get("reaction_emoji", "?")
            user = r.get("user_id", "unknown")
            print(f"   - {emoji} от user_id={user}")
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")


async def main(
    base_url: str,
    chat_id: int | str,
    message_id: int | None = None,
    bot_id: int | None = None,
) -> None:
    async with TelegramAPI(base_url) as api:
        print(f"Тестирование реакций")
        print(f"Chat ID: {chat_id}")
        if message_id:
            print(f"Message ID: {message_id}")
        else:
            print("Message ID: будет создано тестовое сообщение")
        print(f"API: {base_url}\n")

        await test_reactions(api, chat_id, message_id, bot_id=bot_id)

        print("\nГотово!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест реакций через telegram-api SDK")
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
    parser.add_argument(
        "--message-id",
        type=int,
        help="telegram_message_id (если не указан, создастся тестовое сообщение)",
    )
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    bot_id = args.bot_id or (int(os.environ["TEST_BOT_ID"]) if os.environ.get("TEST_BOT_ID") else None)
    asyncio.run(main(args.base_url, args.chat_id, args.message_id, bot_id=bot_id))
