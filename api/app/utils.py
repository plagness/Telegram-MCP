"""Общие утилиты для telegram-api.

Вынесено из роутеров, чтобы убрать дублирование.
"""

from __future__ import annotations

from .services.bots import BotRegistry


def escape_html(text: str) -> str:
    """Экранирование HTML-спецсимволов для Telegram parse_mode=HTML."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def resolve_bot_context(bot_id: int | None) -> tuple[str, int | None]:
    """Определить bot_token и фактический bot_id.

    Используется во всех роутерах для разрешения контекста бота:
    если bot_id=None — берёт дефолтного бота из реестра,
    иначе — ищет по bot_id и возвращает подтверждённый ID из БД.

    Returns:
        (bot_token, resolved_bot_id)
    """
    bot_token = await BotRegistry.get_bot_token(bot_id)
    resolved_bot_id = bot_id
    bot_row = await BotRegistry.get_bot_by_token(bot_token)
    if bot_row and bot_row.get("bot_id") is not None:
        resolved_bot_id = int(bot_row["bot_id"])
    return bot_token, resolved_bot_id
