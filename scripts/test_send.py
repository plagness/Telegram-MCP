#!/usr/bin/env python3
"""
Тестовый скрипт: отправка, редактирование и удаление текстового сообщения.

Использование:
    python scripts/test_send.py --chat-id -100123456789
    python scripts/test_send.py --chat-id -100123456789 --dry-run
    python scripts/test_send.py --chat-id -100123456789 --base-url http://localhost:8081

Переменные окружения:
    TELEGRAM_API_URL — базовый URL (по умолчанию http://localhost:8081)
    TEST_CHAT_ID     — chat_id для тестов (вместо --chat-id)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# SDK может быть установлен через pip или лежать рядом
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI, TelegramAPIError


async def main(base_url: str, chat_id: int | str, dry_run: bool = False) -> None:
    async with TelegramAPI(base_url) as api:
        # 1. Проверка здоровья
        print("1. Проверка /health ...")
        health = await api.health()
        print(f"   Статус: {health}")

        # 2. Информация о боте
        print("\n2. Информация о боте ...")
        try:
            bot = await api.get_bot_info()
            print(f"   Бот: @{bot.get('username', '???')} ({bot.get('first_name', '')})")
        except TelegramAPIError as e:
            print(f"   Ошибка: {e}")

        # 3. Отправка сообщения
        print(f"\n3. Отправка сообщения в {chat_id} (dry_run={dry_run}) ...")
        try:
            msg = await api.send_message(
                chat_id=chat_id,
                text="<b>Тест telegram-api</b>\n\nЭто тестовое сообщение, отправленное через SDK.",
                parse_mode="HTML",
                dry_run=dry_run,
            )
            msg_id = msg.get("id")
            print(f"   Сообщение создано: id={msg_id}, status={msg.get('status')}")
        except TelegramAPIError as e:
            print(f"   Ошибка отправки: {e}")
            return

        if dry_run:
            print("\n   dry_run=True — сообщение не отправлено в Telegram.")
            return

        # 4. Получение сообщения
        print(f"\n4. Получение сообщения id={msg_id} ...")
        fetched = await api.get_message(msg_id)
        print(f"   telegram_message_id={fetched.get('telegram_message_id')}")
        print(f"   status={fetched.get('status')}")

        # 5. Редактирование сообщения
        print(f"\n5. Редактирование сообщения id={msg_id} ...")
        try:
            edited = await api.edit_message(
                msg_id,
                text="<b>Тест telegram-api</b>\n\nСообщение отредактировано через SDK.",
                parse_mode="HTML",
            )
            print(f"   status={edited.get('status')}")
        except TelegramAPIError as e:
            print(f"   Ошибка редактирования: {e}")

        # 6. Список сообщений
        print("\n6. Список последних сообщений ...")
        messages = await api.list_messages(limit=5)
        for m in messages:
            print(f"   [{m.get('id')}] {m.get('status'):10s} {(m.get('text') or '')[:40]}")

        # 7. Удаление сообщения
        print(f"\n7. Удаление сообщения id={msg_id} ...")
        try:
            deleted = await api.delete_message(msg_id)
            print(f"   status={deleted.get('status')}")
        except TelegramAPIError as e:
            print(f"   Ошибка удаления: {e}")

        # 8. Отправка с inline-кнопками
        print("\n8. Отправка сообщения с inline-кнопками ...")
        try:
            msg2 = await api.send_message(
                chat_id=chat_id,
                text="Сообщение с кнопками",
                reply_markup={
                    "inline_keyboard": [
                        [
                            {"text": "Кнопка 1", "callback_data": "btn_1"},
                            {"text": "Кнопка 2", "callback_data": "btn_2"},
                        ],
                        [
                            {"text": "Ссылка", "url": "https://example.com"},
                        ],
                    ]
                },
            )
            print(f"   id={msg2.get('id')}, status={msg2.get('status')}")
        except TelegramAPIError as e:
            print(f"   Ошибка: {e}")

        print("\nГотово.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест отправки сообщений через telegram-api SDK")
    parser.add_argument(
        "--chat-id",
        default=os.environ.get("TEST_CHAT_ID"),
        help="Telegram chat_id для отправки (или TEST_CHAT_ID из окружения)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TELEGRAM_API_URL", "http://localhost:8081"),
        help="Базовый URL telegram-api (по умолчанию http://localhost:8081)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Не отправлять в Telegram (dry run)")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    asyncio.run(main(args.base_url, args.chat_id, args.dry_run))
