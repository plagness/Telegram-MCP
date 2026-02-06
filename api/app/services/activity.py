"""Non-blocking activity log helpers for Telegram API calls."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ..db import execute

logger = logging.getLogger(__name__)


async def log_activity(
    *,
    action: str,
    status: str,
    bot_id: int | None = None,
    bot_username: str | None = None,
    chat_id: str | int | None = None,
    user_id: str | int | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write one record to api_activity_log. Errors are swallowed by design."""
    try:
        await execute(
            """
            INSERT INTO api_activity_log (
                bot_id,
                bot_username,
                action,
                chat_id,
                user_id,
                status,
                error,
                duration_ms,
                metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            [
                bot_id,
                bot_username,
                action,
                str(chat_id) if chat_id is not None else None,
                str(user_id) if user_id is not None else None,
                status,
                error,
                duration_ms,
                json.dumps(metadata or {}),
            ],
        )
    except Exception as exc:  # pragma: no cover - best effort logging
        logger.warning("Failed to write api_activity_log: %s", exc)


def log_activity_background(**kwargs: Any) -> None:
    """Fire-and-forget wrapper around log_activity."""
    try:
        asyncio.create_task(log_activity(**kwargs))
    except RuntimeError:
        # No running loop (can happen during shutdown). Ignore safely.
        pass
