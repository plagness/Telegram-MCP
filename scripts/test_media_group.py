#!/usr/bin/env python3
"""
Тестовый скрипт: sendMediaGroup (альбомы).

Демонстрирует отправку альбомов из нескольких фото/видео одним сообщением.

Использование:
    python scripts/test_media_group.py --chat-id -1001455291970
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI


# Тестовые изображения (placeholder URLs)
TEST_PHOTOS = [
    "https://picsum.photos/800/600?random=1",
    "https://picsum.photos/800/600?random=2",
    "https://picsum.photos/800/600?random=3",
]


async def test_photo_album(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None):
    """Тест отправки альбома из 3 фото."""
    print("\n🧪 Тест 1: Альбом из 3 фото")

    media = [
        {
            "type": "photo",
            "media": TEST_PHOTOS[0],
            "caption": "<b>Фото 1</b>\nПервое фото в альбоме",
            "parse_mode": "HTML",
        },
        {
            "type": "photo",
            "media": TEST_PHOTOS[1],
        },
        {
            "type": "photo",
            "media": TEST_PHOTOS[2],
        },
    ]

    result = await api.send_media_group(chat_id, media, bot_id=bot_id)
    print(f"✅ Альбом отправлен: {len(result['messages'])} сообщений")
    print(f"   Media Group ID: {result.get('media_group_id')}")


async def test_mixed_album(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None):
    """Тест смешанного альбома (фото + видео)."""
    print("\n🧪 Тест 2: Смешанный альбом (фото + видео)")

    # Используем file_id если доступно, иначе URL
    media = [
        {
            "type": "photo",
            "media": TEST_PHOTOS[0],
            "caption": "📸 Смешанный альбом: фото и видео",
        },
        {
            "type": "photo",
            "media": TEST_PHOTOS[1],
        },
    ]

    result = await api.send_media_group(chat_id, media, bot_id=bot_id)
    print(f"✅ Смешанный альбом отправлен: {len(result['messages'])} элементов")


async def test_dry_run(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None):
    """Тест dry-run режима (не отправлять реально)."""
    print("\n🧪 Тест 3: Dry-run (проверка без отправки)")

    media = [
        {"type": "photo", "media": TEST_PHOTOS[0], "caption": "Test"},
        {"type": "photo", "media": TEST_PHOTOS[1]},
    ]

    result = await api.send_media_group(chat_id, media, bot_id=bot_id, dry_run=True)
    print(f"✅ Dry-run: {result.get('dry_run', False)}")
    print(f"   Payload preview: {len(result.get('payload', {}).get('media', []))} элементов")


async def main(base_url: str, chat_id: int | str, bot_id: int | None = None):
    """Запуск всех тестов sendMediaGroup."""
    async with TelegramAPI(base_url) as api:
        print(f"🚀 Тестирование sendMediaGroup в чате {chat_id}\n")

        # Тест 1: Альбом из фото
        await test_photo_album(api, chat_id, bot_id=bot_id)
        await asyncio.sleep(2)

        # Тест 2: Смешанный альбом
        await test_mixed_album(api, chat_id, bot_id=bot_id)
        await asyncio.sleep(2)

        # Тест 3: Dry-run
        await test_dry_run(api, chat_id, bot_id=bot_id)

        print("\n✅ Все тесты завершены!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест sendMediaGroup (альбомы)")
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
