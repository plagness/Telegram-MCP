#!/usr/bin/env python3
"""Тестирование системы форматирования."""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к SDK
sys.path.insert(0, str(Path(__file__).parent.parent / "sdk"))

from telegram_api_client import TelegramAPI


async def test_formatters():
    """Тестирование прогресс-баров и эмодзи через шаблоны."""
    api = TelegramAPI("http://localhost:8081")
    chat_id = -1001455291970

    print("🧪 Тест 1: Прогресс-бары (разные стили)")
    message = """<b>📊 Прогресс-бары</b>

<b>Classic:</b>
[####......] 40%

<b>Blocks:</b>
▓▓▓▓░░░░░░ 40%

<b>Circles:</b>
●●●●○○○○○○ 40%

<b>Squares:</b>
■■■■□□□□□□ 40%

<b>Dots:</b>
⣿⣿⣿⣿⣀⣀⣀⣀⣀⣀ 40%"""

    msg = await api.send_message(chat_id, message, parse_mode="HTML")
    print(f"✅ Отправлено сообщение {msg['id']}")
    await asyncio.sleep(3)

    print("\n🧪 Тест 2: Эмодзи-градации")
    message2 = """<b>🎨 Эмодзи-градации</b>

<b>Health (HP):</b>
💚 100% | 💛 70% | 🧡 50% | ❤️ 30% | 💔 10%

<b>Status (загрузка):</b>
🟢 20% | 🟡 50% | 🟠 70% | 🔴 90% | ⚫ 100%

<b>Priority:</b>
⬇️ Lowest | ➡️ Low | ⬆️ Medium | 🔺 High | 🔴 Critical

<b>Connection:</b>
🟢 Online | 🟡 Degraded | 🟠 Maintenance | 🔴 Offline | ⚪ Unknown

<b>Sentiment:</b>
😊 Very positive | 🙂 Positive | 😐 Neutral | 😠 Negative | 😡 Very negative"""

    msg2 = await api.send_message(chat_id, message2, parse_mode="HTML")
    print(f"✅ Отправлено сообщение {msg2['id']}")
    await asyncio.sleep(3)

    print("\n🧪 Тест 3: Блоки состояния железа (через шаблон)")
    # Используем готовый шаблон hardware_fleet
    response = await api.render_template(
        "hardware_fleet",
        {
            "title": "Test Fleet",
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

    msg3 = await api.send_message(chat_id, response["text"], parse_mode="HTML")
    print(f"✅ Отправлено сообщение {msg3['id']} (hardware fleet)")
    await asyncio.sleep(3)

    print("\n🧪 Тест 4: Chat Action (typing indicator)")
    # Отправляем typing action
    import httpx

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"http://localhost:8081/v1/chats/{chat_id}/action",
            json={"action": "typing"},
        )
        print(f"✅ Отправлен typing action: {r.json()}")

    await asyncio.sleep(2)
    msg4 = await api.send_message(chat_id, "Finished typing! 🎉")
    print(f"✅ Отправлено сообщение {msg4['id']}")

    print("\n✅ Все тесты форматирования пройдены!")


if __name__ == "__main__":
    asyncio.run(test_formatters())
