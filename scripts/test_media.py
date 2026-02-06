#!/usr/bin/env python3
"""
Тестовый скрипт: отправка фото и документов.

Использование:
    python scripts/test_media.py --chat-id -100123456789
    python scripts/test_media.py --chat-id -100123456789 --photo /path/to/image.jpg
    python scripts/test_media.py --chat-id -100123456789 --photo-url https://example.com/img.jpg

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


async def main(
    base_url: str,
    chat_id: int | str,
    photo_path: str | None = None,
    photo_url: str | None = None,
) -> None:
    async with TelegramAPI(base_url) as api:
        # 1. Отправка фото по URL
        if photo_url:
            print(f"1. Отправка фото по URL: {photo_url} ...")
            try:
                msg = await api.send_photo(
                    chat_id=chat_id,
                    photo=photo_url,
                    caption="<b>Тест</b>: фото по URL через SDK",
                    parse_mode="HTML",
                )
                print(f"   id={msg.get('id')}, status={msg.get('status')}")
                print(f"   media_file_id={msg.get('media_file_id', 'N/A')}")
            except TelegramAPIError as e:
                print(f"   Ошибка: {e}")
        else:
            print("1. Пропуск отправки по URL (не указан --photo-url)")

        # 2. Отправка фото файлом (multipart upload)
        if photo_path:
            print(f"\n2. Загрузка фото файлом: {photo_path} ...")
            if not os.path.isfile(photo_path):
                print(f"   Файл не найден: {photo_path}")
                return
            try:
                with open(photo_path, "rb") as f:
                    msg = await api.send_photo(
                        chat_id=chat_id,
                        photo=f,
                        caption="<b>Тест</b>: фото загружено через SDK (multipart)",
                        parse_mode="HTML",
                        filename=os.path.basename(photo_path),
                    )
                print(f"   id={msg.get('id')}, status={msg.get('status')}")
                print(f"   media_file_id={msg.get('media_file_id', 'N/A')}")
            except TelegramAPIError as e:
                print(f"   Ошибка: {e}")
        else:
            print("\n2. Пропуск загрузки файла (не указан --photo)")

        # 3. Генерация и отправка простого изображения (без внешних зависимостей)
        print("\n3. Генерация тестового PNG и отправка ...")
        try:
            png_data = _make_test_png()
            msg = await api.send_photo(
                chat_id=chat_id,
                photo=png_data,
                caption="Тестовый PNG (1x1 красный пиксель), сгенерирован скриптом",
                filename="test_pixel.png",
            )
            print(f"   id={msg.get('id')}, status={msg.get('status')}")
        except TelegramAPIError as e:
            print(f"   Ошибка: {e}")

        # 4. Отправка документа по URL
        print("\n4. Отправка документа по URL ...")
        try:
            doc_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
            msg = await api.send_document(
                chat_id=chat_id,
                document=doc_url,
                caption="Тестовый PDF-документ",
            )
            print(f"   id={msg.get('id')}, status={msg.get('status')}")
        except TelegramAPIError as e:
            print(f"   Ошибка: {e}")

        print("\nГотово.")


def _make_test_png() -> bytes:
    """Минимальный PNG: 1x1 красный пиксель. Без зависимостей."""
    import struct
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    # Красный пиксель: filter=0, R=255, G=0, B=0
    raw = zlib.compress(b"\x00\xff\x00\x00")
    idat = _chunk(b"IDAT", raw)
    iend = _chunk(b"IEND", b"")
    return header + ihdr + idat + iend


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест отправки медиа через telegram-api SDK")
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
    parser.add_argument("--photo", dest="photo_path", help="Путь к фото-файлу для загрузки")
    parser.add_argument("--photo-url", help="URL фото для отправки")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    asyncio.run(main(args.base_url, args.chat_id, args.photo_path, args.photo_url))
