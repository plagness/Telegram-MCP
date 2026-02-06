#!/usr/bin/env python3
"""Тестирование Updates/Polling."""

import asyncio
import httpx


async def test_updates():
    """Тестирование long polling."""
    base_url = "http://localhost:8081"

    print("🧪 Тест 1: Получение текущего offset")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base_url}/v1/updates/offset")
        print(f"Текущий offset: {r.json()}")

    print("\n🧪 Тест 2: Polling обновлений (timeout=5s)")
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{base_url}/v1/updates/poll",
            params={"limit": 10, "timeout": 5},
        )
        data = r.json()
        print(f"Получено обновлений: {data['count']}")
        print(f"Новый offset: {data['new_offset']}")

        if data["result"]:
            print(f"\nПример обновления:")
            print(data["result"][0])

            # Подтверждаем обработку
            ack_r = await client.post(
                f"{base_url}/v1/updates/ack",
                params={"offset": data["new_offset"]},
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
    asyncio.run(test_updates())
