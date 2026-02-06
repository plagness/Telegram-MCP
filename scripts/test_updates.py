#!/usr/bin/env python3
"""Тестирование Updates/Polling."""

import asyncio
import argparse
import os
import httpx


async def test_updates(base_url: str, bot_id: int | None = None):
    """Тестирование long polling."""
    bot_params = {"bot_id": bot_id} if bot_id is not None else {}

    print("🧪 Тест 1: Получение текущего offset")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base_url}/v1/updates/offset", params=bot_params)
        print(f"Текущий offset: {r.json()}")

    print("\n🧪 Тест 2: Polling обновлений (timeout=5s)")
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"limit": 10, "timeout": 5, **bot_params}
        r = await client.get(
            f"{base_url}/v1/updates/poll",
            params=params,
        )
        data = r.json()
        print(f"Получено обновлений: {data['count']}")
        print(f"Новый offset: {data['new_offset']}")

        if data["result"]:
            print(f"\nПример обновления:")
            print(data["result"][0])

            # Подтверждаем обработку
            ack_payload = {"offset": data["new_offset"]}
            if bot_id is not None:
                ack_payload["bot_id"] = bot_id
            ack_r = await client.post(
                f"{base_url}/v1/updates/ack",
                json=ack_payload,
            )
            print(f"\nOffset обновлён: {ack_r.json()}")

    print("\n🧪 Тест 3: История обновлений")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base_url}/v1/updates/history", params={"limit": 5})
        data = r.json()
        print(f"Всего обновлений в БД: {data['total']}")
        print(f"Последние 5: {len(data['updates'])}")

    print("\n✅ Тесты Updates/Polling пройдены!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест Updates/Polling")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TELEGRAM_API_URL", "http://localhost:8081"),
        help="Базовый URL telegram-api",
    )
    parser.add_argument("--bot-id", type=int, default=None, help="Явный bot_id для мультибот polling")
    args = parser.parse_args()

    asyncio.run(test_updates(args.base_url, args.bot_id))
