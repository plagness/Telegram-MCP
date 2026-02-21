"""Маркетплейс Integrat + кабинет разработчика."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..routers.render import _build_bar_context

router = APIRouter(tags=["marketplace"])
settings = get_settings()


@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace(request: Request):
    """Глобальный магазин плагинов Integrat."""
    templates = request.app.state.templates
    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())
    bar_ctx = await _build_bar_context(user["id"])
    html = templates.get_template("marketplace.html").render(
        user=user, bar_user=user, **bar_ctx,
    )
    return HTMLResponse(html)


@router.get("/marketplace/{slug}", response_class=HTMLResponse)
async def marketplace_plugin(slug: str, request: Request):
    """Детальная страница плагина в маркетплейсе."""
    templates = request.app.state.templates
    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())
    bar_ctx = await _build_bar_context(user["id"])
    html = templates.get_template("marketplace_plugin.html").render(
        user=user, bar_user=user, plugin_slug=slug, **bar_ctx,
    )
    return HTMLResponse(html)


@router.get("/marketplace/author/{tg_id}", response_class=HTMLResponse)
async def marketplace_author(tg_id: int, request: Request):
    """Профиль автора в маркетплейсе."""
    templates = request.app.state.templates
    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())
    bar_ctx = await _build_bar_context(user["id"])
    html = templates.get_template("marketplace_author.html").render(
        user=user, bar_user=user, author_tg_id=tg_id, **bar_ctx,
    )
    return HTMLResponse(html)


@router.get("/developer", response_class=HTMLResponse)
async def developer(request: Request):
    """Кабинет разработчика Integrat."""
    templates = request.app.state.templates
    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())
    bar_ctx = await _build_bar_context(user["id"])
    html = templates.get_template("developer.html").render(
        user=user, bar_user=user, **bar_ctx,
    )
    return HTMLResponse(html)
