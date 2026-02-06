"""Точка сборки FastAPI-приложения. Подключает роутеры и lifecycle-хуки."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .config import get_settings
from .db import init_pool, close_pool
from .telegram_client import close_client
from .services import templates as template_service
from .routers import health, messages, media, templates, commands, callbacks, chats, webhook, polls, reactions, updates, actions, checklists, predictions

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown хуки."""
    await init_pool()
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
