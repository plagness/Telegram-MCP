"""Точка входа web-ui (FastAPI + Jinja2 + static)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from .config import get_settings
from .db import close_pool, init_pool
from .handlers.registry import discover_handlers, register_all_routes
from .routers import admin, banners_api, health, icons, marketplace, module_proxy, pages, pins, render, roles, views

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл: открытие/закрытие пула БД + health cron + pin cron."""
    from .services.health import health_check_loop
    from .services.pin_cron import start_pin_cron, stop_pin_cron

    await init_pool()
    task = asyncio.create_task(health_check_loop())
    start_pin_cron()
    yield
    stop_pin_cron()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # Закрываем Playwright browser если был инициализирован
    try:
        from .services.pin_renderer import close_browser
        await close_browser()
    except Exception:
        pass
    await close_pool()


app = FastAPI(
    title="telegram-mcp web-ui",
    version="2026.02.22",
    lifespan=lifespan,
)

# Jinja2 шаблоны
templates_dir = BASE_DIR / "templates"
app.state.templates = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=True,
)

# Статика
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Handler auto-discovery (только Python-импорты, не требует БД)
discover_handlers()

# Proxy-маршруты от handler'ов (calendar CRUD, governance, infra, llm и т.д.)
_handler_router = APIRouter(tags=["handlers"])
register_all_routes(_handler_router)

# Роутеры
app.include_router(health.router)
app.include_router(icons.router)
app.include_router(pages.router)
app.include_router(render.router)
app.include_router(views.router)
app.include_router(_handler_router)
app.include_router(module_proxy.router)
app.include_router(roles.router)
app.include_router(marketplace.router)
app.include_router(admin.router)
app.include_router(banners_api.router)
app.include_router(pins.router)


# Error handler — HTML-страница для веб-роутов, JSON для API
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404: HTML для браузера, JSON для API."""
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        detail = getattr(exc, "detail", "Not found")
        return JSONResponse({"detail": detail}, status_code=404)
    template = app.state.templates.get_template("error.html")
    html = template.render(error_code=404, error_message="Страница не найдена", config={})
    return HTMLResponse(html, status_code=404)
