"""REST API для управления баннерами (/api/v1/banners)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.banner import (
    create_banner,
    delete_banner,
    get_all_banners,
    toggle_banner,
    update_banner_avatar,
)

router = APIRouter(prefix="/api/v1/banners", tags=["banners"])
logger = logging.getLogger(__name__)


class CreateBannerIn(BaseModel):
    tg_username: str = Field(..., max_length=100)
    title: str = Field(..., max_length=200)
    link: str = Field(..., max_length=500)
    description: str = Field("", max_length=500)
    priority: int = Field(0, ge=0, le=100)
    target_roles: list[str] = Field(default_factory=list)
    created_by: int | None = None


class ToggleBannerIn(BaseModel):
    active: bool


@router.get("")
async def list_banners():
    """Список всех баннеров."""
    banners = await get_all_banners()
    return {"ok": True, "banners": banners}


@router.post("")
async def api_create_banner(payload: CreateBannerIn):
    """Создать баннер."""
    await create_banner(
        tg_username=payload.tg_username,
        title=payload.title,
        link=payload.link,
        created_by=payload.created_by or 0,
        description=payload.description,
        priority=payload.priority,
        target_roles=payload.target_roles,
    )
    return {"ok": True}


@router.post("/{banner_id}/toggle")
async def api_toggle_banner(banner_id: int, payload: ToggleBannerIn):
    """Включить/выключить баннер."""
    await toggle_banner(banner_id, payload.active)
    return {"ok": True}


@router.post("/{banner_id}/refresh-avatar")
async def api_refresh_avatar(banner_id: int):
    """Обновить аватарку баннера."""
    await update_banner_avatar(banner_id)
    return {"ok": True}


@router.delete("/{banner_id}")
async def api_delete_banner(banner_id: int):
    """Удалить баннер (мягкое удаление)."""
    await delete_banner(banner_id)
    return {"ok": True}
