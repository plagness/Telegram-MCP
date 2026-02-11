#!/usr/bin/env python3
"""
Тестовый скрипт: CommandHandler pattern с декораторами @api.command().

Демонстрирует:
  - Регистрацию обработчиков команд через декораторы
  - Guard-фильтры (chat_id, user_id)
  - Обработку аргументов команд
  - Long polling для получения обновлений
  - Использование шаблонов в обработчиках

Использование:
    python scripts/test_command_handler.py --chat-id -1001234567890
    python scripts/test_command_handler.py --chat-id -1001234567890 --user-id 123456

Переменные окружения:
    TELEGRAM_API_URL — базовый URL (по умолчанию http://localhost:8081)
    TEST_CHAT_ID     — chat_id
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI, TelegramAPIError


async def main(
    base_url: str,
    chat_id: int | str,
    user_id: int | None = None,
    bot_id: int | None = None,
) -> None:
    """Запуск CommandHandler с тестовыми командами."""
    api = TelegramAPI(base_url)

    # Команда 1: /start — доступна всем
    @api.command("start")
    async def start_command(update, args):
        """Приветствие при запуске бота."""
        user = update["message"]["from"]
        username = user.get("username", user.get("first_name", "Аноним"))
        reply_chat_id = update["message"]["chat"]["id"]

        text = f"👋 Привет, @{username}!\n\nЯ тестовый бот для проверки CommandHandler."

        try:
            await api.send_message(
                chat_id=reply_chat_id,
                bot_id=bot_id,
                text=text,
                reply_to_message_id=update["message"]["message_id"]
            )
            print(f"✅ /start обработан для @{username}")
        except Exception as e:
            print(f"❌ Ошибка /start: {e}")

    # Команда 2: /test — только для указанного чата (guard)
    @api.command("test", chat_id=int(chat_id))
    async def test_command(update, args):
        """Тестовая команда с аргументами (только для указанного чата)."""
        reply_chat_id = update["message"]["chat"]["id"]
        args_str = " ".join(args) if args else "(нет аргументов)"

        text = f"🧪 Тест выполнен!\n\n<b>Аргументы:</b> <code>{args_str}</code>\n<b>Время:</b> {datetime.now().strftime('%H:%M:%S')}"

        try:
            await api.send_message(
                chat_id=reply_chat_id,
                bot_id=bot_id,
                text=text,
                parse_mode="HTML",
                reply_to_message_id=update["message"]["message_id"]
            )
            print(f"✅ /test обработан с аргументами: {args_str}")
        except Exception as e:
            print(f"❌ Ошибка /test: {e}")

    # Команда 3: /status — hardware fleet через шаблон
    @api.command("status", chat_id=int(chat_id))
    async def status_command(update, args):
        """Статус железа (через шаблон hardware_fleet)."""
        reply_chat_id = update["message"]["chat"]["id"]

        # Рендерим шаблон
        try:
            response = await api.render_template(
                "hardware_fleet",
                {
                    "title": "Compute Fleet",
                    "devices": [
                        {
                            "name": "server1",
                            "status": "online",
                            "cpu": 45.2,
                            "ram_used": 12.5,
                            "ram_total": 32.0,
                            "gpu": 78,
                            "temp": 58,
                            "load": 3,
                        },
                        {
                            "name": "steamdeck",
                            "status": "online",
                            "cpu": 67.8,
                            "ram_used": 5.2,
                            "ram_total": 16.0,
                            "temp": 72,
                            "load": 1,
                        },
                        {
                            "name": "pi5",
                            "status": "offline",
                            "cpu": 0,
                            "ram_used": 0,
                            "ram_total": 8.0,
                        },
                    ],
                    "summary": {
                        "online": 2,
                        "offline": 1,
                        "avg_cpu": 56.5,
                        "avg_ram": 44.2,
                    },
                },
            )

            await api.send_message(
                chat_id=reply_chat_id,
                bot_id=bot_id,
                text=response["text"],
                parse_mode="HTML",
                reply_to_message_id=update["message"]["message_id"]
            )
            print(f"✅ /status обработан (hardware fleet)")
        except Exception as e:
            print(f"❌ Ошибка /status: {e}")

    # Команда 4: /help — список команд
    @api.command("help")
    async def help_command(update, args):
        """Справка по командам."""
        reply_chat_id = update["message"]["chat"]["id"]

        text = """<b>📚 Доступные команды:</b>

/start — Начать работу с ботом
/test [аргументы] — Тестовая команда с аргументами
/status — Статус железа (через шаблон)
/help — Эта справка

<i>CommandHandler работает через long polling</i>"""

        try:
            await api.send_message(
                chat_id=reply_chat_id,
                bot_id=bot_id,
                text=text,
                parse_mode="HTML",
                reply_to_message_id=update["message"]["message_id"]
            )
            print(f"✅ /help обработан")
        except Exception as e:
            print(f"❌ Ошибка /help: {e}")

    # Список зарегистрированных команд
    commands = api.list_commands()
    print(f"\n📋 Зарегистрировано команд: {len(commands)}")
    for cmd in commands:
        if isinstance(cmd, str):
            print(f"   /{cmd}")
        else:
            guard_info = ""
            if cmd.get("chat_id"):
                guard_info += f" [chat_id={cmd['chat_id']}]"
            if cmd.get("user_id"):
                guard_info += f" [user_id={cmd['user_id']}]"
            print(f"   /{cmd.get('command', cmd)}{guard_info}")

    print(f"\n🔄 Запуск long polling (chat_id={chat_id})...\n")

    # Запуск polling
    try:
        await api.start_polling(timeout=30, limit=10, bot_id=bot_id)
    except KeyboardInterrupt:
        print("\n⚠️  Остановка по Ctrl+C")
        await api.stop_polling()
    except Exception as e:
        print(f"\n❌ Ошибка polling: {e}")
        await api.stop_polling()
    finally:
        await api.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест CommandHandler pattern")
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
    parser.add_argument("--user-id", type=int, help="user_id для guard-фильтра")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    bot_id = args.bot_id or (int(os.environ["TEST_BOT_ID"]) if os.environ.get("TEST_BOT_ID") else None)
    asyncio.run(main(args.base_url, args.chat_id, args.user_id, bot_id=bot_id))
