"""
Rate limiter для Telegram Bot API.

Token bucket по chat_id:
- Личные чаты: ~1 msg/sec
- Группы: ~20 msg/min
- Одна группа: ~3 msg/sec
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class TokenBucket:
    """Простой token bucket для одного chat_id."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate  # токенов в секунду
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_time = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_time = now

    async def acquire(self) -> None:
        """Дождаться доступного токена."""
        self._refill()
        if self.tokens < 1.0:
            # Сколько ждать до одного токена
            wait = (1.0 - self.tokens) / self.rate
            await asyncio.sleep(wait)
            self._refill()
        self.tokens -= 1.0


class RateLimiter:
    """
    Rate limiter по chat_id.

    Автоматически определяет тип чата по chat_id:
    - Отрицательные ID (группы/каналы): 20 msg/min ≈ 0.33 msg/sec
    - Положительные ID (личные): 1 msg/sec
    """

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(rate=1.0, capacity=3)
        )

    def _get_bucket(self, chat_id: int | str) -> TokenBucket:
        key = str(chat_id)
        if key not in self._buckets:
            try:
                cid = int(chat_id)
            except (ValueError, TypeError):
                cid = 0

            if cid < 0:
                # Группа/канал: более строгий лимит
                self._buckets[key] = TokenBucket(rate=0.33, capacity=3)
            else:
                # Личный чат
                self._buckets[key] = TokenBucket(rate=1.0, capacity=3)
        return self._buckets[key]

    async def acquire(self, chat_id: int | str) -> None:
        """Дождаться разрешения на отправку в данный чат."""
        bucket = self._get_bucket(chat_id)
        await bucket.acquire()


# Глобальный экземпляр
rate_limiter = RateLimiter()
