#!/usr/bin/env python3
"""
Тестовый скрипт: управление командами бота (BotCommandScope).

Демонстрирует:
  - Создание глобального набора команд
  - Создание набора для конкретного чата
  - Создание per-user набора (chat_member)
  - Синхронизацию с Telegram (setMyCommands)

Использование:
    python scripts/test_commands.py --chat-id -100123456789
    python scripts/test_commands.py --chat-id -100123456789 --user-id 12345 --sync

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


async def main(
    base_url: str,
    chat_id: int | str,
    user_id: int | None = None,
    do_sync: bool = False,
    bot_id: int | None = None,
) -> None:
    async with TelegramAPI(base_url) as api:
        # 1. Глобальные команды (scope=default)
        print("1. Создание глобального набора команд (scope=default) ...")
        try:
            cs1 = await api.set_commands(
                bot_id=bot_id,
                commands=[
                    {"command": "start", "description": "Начать работу с ботом"},
                    {"command": "help", "description": "Справка по командам"},
                    {"command": "ping", "description": "Проверка связи"},
                ],
                scope_type="default",
            )
            cs1_id = cs1.get("id")
            print(f"   command_set id={cs1_id}")
        except TelegramAPIError as e:
            print(f"   Ошибка: {e}")
            cs1_id = None

        # 2. Команды для чата (scope=chat)
        print(f"\n2. Набор команд для чата {chat_id} (scope=chat) ...")
        try:
            cs2 = await api.set_commands(
                bot_id=bot_id,
                commands=[
                    {"command": "start", "description": "Начать работу с ботом"},
                    {"command": "help", "description": "Справка"},
                    {"command": "summary", "description": "Сводка по чату"},
                    {"command": "toppoint", "description": "Рейтинг участников"},
                ],
                scope_type="chat",
                chat_id=int(chat_id),
            )
            cs2_id = cs2.get("id")
            print(f"   command_set id={cs2_id}")
        except TelegramAPIError as e:
            print(f"   Ошибка: {e}")
            cs2_id = None

        # 3. Per-user команды (scope=chat_member)
        if user_id:
            print(f"\n3. Per-user набор для user_id={user_id} в чате {chat_id} ...")
            try:
                cs3 = await api.set_commands(
                    bot_id=bot_id,
                    commands=[
                        {"command": "start", "description": "Начать работу с ботом"},
                        {"command": "help", "description": "Справка"},
                        {"command": "summary", "description": "Сводка по чату"},
                        {"command": "toppoint", "description": "Рейтинг участников"},
                        {"command": "cleanup", "description": "Запуск очистки (админ)"},
                        {"command": "report", "description": "Сформировать отчёт (админ)"},
                    ],
                    scope_type="chat_member",
                    chat_id=int(chat_id),
                    user_id=user_id,
                )
                cs3_id = cs3.get("id")
                print(f"   command_set id={cs3_id}")
            except TelegramAPIError as e:
                print(f"   Ошибка: {e}")
                cs3_id = None
        else:
            print("\n3. Пропуск per-user набора (не указан --user-id)")
            cs3_id = None

        # 4. Список всех наборов
        print("\n4. Список наборов команд ...")
        sets = await api.list_command_sets()
        for s in sets:
            cmds = s.get("commands", [])
            cmd_names = ", ".join(c.get("command", "") for c in cmds) if isinstance(cmds, list) else str(cmds)
            print(f"   [{s.get('id')}] scope={s.get('scope_type'):15s} commands=[{cmd_names}]")

        # 5. Синхронизация с Telegram
        if do_sync:
            for label, cs_id in [("default", cs1_id), ("chat", cs2_id), ("chat_member", cs3_id)]:
                if cs_id is None:
                    continue
                print(f"\n5. Синхронизация набора id={cs_id} (scope={label}) ...")
                try:
                    result = await api.sync_commands(cs_id, bot_id=bot_id)
                    print(f"   Результат: {result}")
                except TelegramAPIError as e:
                    print(f"   Ошибка синхронизации: {e}")
        else:
            print("\n5. Пропуск синхронизации (--sync не указан)")

        print("\nГотово.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест управления командами через telegram-api SDK")
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
    parser.add_argument("--user-id", type=int, help="user_id для per-user команд (scope=chat_member)")
    parser.add_argument("--sync", action="store_true", dest="do_sync", help="Синхронизировать с Telegram (setMyCommands)")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    bot_id = args.bot_id or (int(os.environ["TEST_BOT_ID"]) if os.environ.get("TEST_BOT_ID") else None)
    asyncio.run(main(args.base_url, args.chat_id, args.user_id, args.do_sync, bot_id=bot_id))
