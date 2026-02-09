"""API для Simple Icons — программный резолв имён в SVG-иконки.

Эндпоинты:
- GET /api/icons/resolve?name=claude  — резолв произвольного имени
- GET /api/icons/info                 — статистика и список алиасов
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse

from ..icons import (
    resolve_icon,
    adjusted_color,
    get_display_name,
    get_fallback_emoji,
    get_icon_count,
    get_all_aliases,
)

router = APIRouter(prefix="/api/icons", tags=["icons"])


@router.get("/resolve")
async def resolve(name: str = Query(..., description="Имя для резолва (claude, btc, telegram...)")):
    """Резолв произвольного имени в SVG-иконку.

    Возвращает slug, hex-цвет, URL иконки, display name и emoji fallback.
    Если иконка не найдена — 200 с found=false.
    """
    icon = resolve_icon(name)
    if not icon:
        return {
            "found": False,
            "name": name,
            "display_name": get_display_name(name),
            "emoji": get_fallback_emoji(name),
        }
    return {
        "found": True,
        "name": name,
        "slug": icon["slug"],
        "hex": icon["hex"],
        "color": icon["color"],
        "adjusted_color": "#" + adjusted_color(icon["hex"]),
        "icon_url": icon["icon_url"],
        "display_name": get_display_name(name),
        "emoji": get_fallback_emoji(name),
    }


@router.get("/redirect")
async def redirect_to_svg(name: str = Query(..., description="Имя для редиректа на SVG")):
    """Редирект на SVG-файл по имени (удобно для <img src>)."""
    icon = resolve_icon(name)
    if not icon:
        return {"error": "not_found", "name": name}
    return RedirectResponse(url=icon["icon_url"], status_code=302)


@router.get("/info")
async def info():
    """Статистика: количество иконок, список алиасов."""
    return {
        "total_icons": get_icon_count(),
        "aliases": get_all_aliases(),
    }
