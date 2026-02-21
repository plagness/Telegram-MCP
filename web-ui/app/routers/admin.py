"""Админские маршруты: управление баннерами (project_owner)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..services.access import get_user_roles
from ..services.banner import (
    create_banner,
    delete_banner,
    get_all_banners,
    toggle_banner,
    update_banner_avatar,
)

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(tags=["admin"])


async def _require_owner(request: Request) -> dict[str, Any]:
    """Проверка project_owner для доступа к админке."""
    init_data = (
        request.query_params.get("initData", "")
        or request.headers.get("X-Init-Data", "")
    )
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Auth required")
    roles = await get_user_roles(user["id"])
    if "project_owner" not in roles:
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


@router.get("/admin/banners", response_class=HTMLResponse)
async def admin_banners(request: Request):
    """Страница управления промо-баннерами (project_owner)."""
    from ..routers.render import _build_bar_context

    user = await _require_owner(request)
    templates = request.app.state.templates
    banners = await get_all_banners()

    bar_ctx = await _build_bar_context(user["id"])
    html = templates.get_template("banner_admin.html").render(
        request=request,
        user=user,
        bar_user=user,
        **bar_ctx,
        banners=banners,
    )
    return HTMLResponse(html)


@router.post("/admin/banners/create")
async def admin_banner_create(request: Request):
    """Создать новый баннер."""
    user = await _require_owner(request)
    form = await request.form()

    tg_username = form.get("tg_username", "").strip()
    title = form.get("title", "").strip()
    link = form.get("link", "").strip()
    description = form.get("description", "").strip()
    priority = int(form.get("priority", 0))
    target_roles_raw = form.get("target_roles", "").strip()
    target_roles = [r.strip() for r in target_roles_raw.split(",") if r.strip()] if target_roles_raw else []

    if not tg_username or not title or not link:
        raise HTTPException(status_code=400, detail="username, title, link required")

    init_data = request.query_params.get("initData", "")
    await create_banner(
        tg_username=tg_username,
        title=title,
        link=link,
        created_by=user["id"],
        description=description,
        priority=priority,
        target_roles=target_roles,
    )
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )


@router.post("/admin/banners/{banner_id}/refresh-avatar")
async def admin_banner_refresh_avatar(banner_id: int, request: Request):
    """Обновить аватарку баннера."""
    await _require_owner(request)
    await update_banner_avatar(banner_id)
    init_data = request.query_params.get("initData", "")
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )


@router.post("/admin/banners/{banner_id}/toggle")
async def admin_banner_toggle(banner_id: int, request: Request):
    """Включить/выключить баннер."""
    await _require_owner(request)
    form = await request.form()
    active = form.get("active", "1") == "1"
    await toggle_banner(banner_id, active)
    init_data = request.query_params.get("initData", "")
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )


@router.post("/admin/banners/{banner_id}/delete")
async def admin_banner_delete(banner_id: int, request: Request):
    """Удалить баннер (мягкое удаление)."""
    await _require_owner(request)
    await delete_banner(banner_id)
    init_data = request.query_params.get("initData", "")
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )
