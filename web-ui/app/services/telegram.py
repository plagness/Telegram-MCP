"""Утилиты для работы с Telegram Bot API (file resolver, webhook proxy)."""

from __future__ import annotations

import logging
import time

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Кэш Telegram file URL (file_id -> (url, timestamp)), TTL 1 час
_tg_file_cache: dict[str, tuple[str, float]] = {}
_TG_FILE_CACHE_TTL = 3600


async def resolve_tg_file_url(file_id: str) -> str:
    """Получить прямой URL файла через Telegram Bot API (с кэшем)."""
    now = time.time()
    cached = _tg_file_cache.get(file_id)
    if cached and now - cached[1] < _TG_FILE_CACHE_TTL:
        return cached[0]

    token = settings.get_bot_token()
    if not token:
        return ""

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
            )
            if r.status_code == 200:
                data = r.json()
                file_path = data.get("result", {}).get("file_path", "")
                if file_path:
                    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                    _tg_file_cache[file_id] = (url, now)
                    return url
    except Exception as e:
        logger.warning("Не удалось получить file URL из Telegram: %s", e)
    return ""
