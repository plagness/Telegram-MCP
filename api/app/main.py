"""Точка сборки FastAPI-приложения. Подключает роутеры и lifecycle-хуки."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
import logging

from fastapi import FastAPI

from .config import get_settings
from .db import init_pool, close_pool, execute
from .telegram_client import close_client
from .services import templates as template_service
from .services.bots import BotRegistry, auto_register_from_env
from .routers import health, messages, media, templates, commands, callbacks, chats, webhook, polls, reactions, updates, actions, checklists, predictions, balance, bots, webui

settings = get_settings()
logger = logging.getLogger(__name__)


async def _apply_default_chat(chat_id: str) -> None:
    await execute("UPDATE chats SET is_default = FALSE WHERE is_default = TRUE")
    await execute(
        """
        INSERT INTO chats (chat_id, is_default)
        VALUES (%s, TRUE)
        ON CONFLICT (chat_id) DO UPDATE
        SET is_default = TRUE,
            updated_at = NOW()
        """,
        [str(chat_id)],
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown хуки."""
    await init_pool()
    try:
        await BotRegistry.initialize()
        await auto_register_from_env()
    except Exception as exc:
        logger.warning("Bot registry initialization failed: %s", exc)

    if settings.default_chat_id:
        try:
            await _apply_default_chat(settings.default_chat_id)
        except Exception as exc:
            logger.warning("Failed to apply DEFAULT_CHAT_ID=%s: %s", settings.default_chat_id, exc)

    if settings.template_autoseed:
        try:
            await template_service.seed_templates_from_files()
        except Exception:
            pass
    yield
    await close_client()
    await close_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# --- Роутеры ---
app.include_router(health.router)
app.include_router(messages.router)
app.include_router(templates.router)
app.include_router(commands.router)
app.include_router(media.router)
app.include_router(callbacks.router)
app.include_router(chats.router)
app.include_router(webhook.router)
app.include_router(polls.router)
app.include_router(reactions.router)
app.include_router(updates.router)
app.include_router(actions.router)
app.include_router(checklists.router)
app.include_router(predictions.router)
app.include_router(balance.router)
app.include_router(bots.router)
app.include_router(webui.router)
