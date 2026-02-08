"""Точка входа web-ui (FastAPI + Jinja2 + static)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from .config import get_settings
from .db import close_pool, init_pool
from .routers import health, pages, render

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл: открытие/закрытие пула БД."""
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="telegram-mcp web-ui",
    version="2026.02.14",
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

# Роутеры
app.include_router(health.router)
app.include_router(pages.router)
app.include_router(render.router)


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
