"""Система handler'ов для page_type: базовый класс и интерфейс.

Каждый page_type реализуется как подкласс PageTypeHandler.
Handler определяет шаблон, загрузку данных и proxy-маршруты.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import httpx

from ..auth import validate_init_data
from ..config import get_settings
from ..services import pages as pages_svc
from ..services.access import check_page_access

logger = logging.getLogger(__name__)
settings = get_settings()


class PageTypeHandler:
    """Базовый handler для типа страницы.

    Подклассы определяют:
    - page_type: str — идентификатор типа ("governance", "calendar", ...)
    - template: str — имя Jinja2 шаблона
    - scripts: list[str] — дополнительные JS-библиотеки (["echarts"])
    """

    page_type: str = ""
    template: str = "page.html"
    scripts: list[str] = []

    async def load_data(
        self, page: dict, user: dict | None, request: Request
    ) -> dict[str, Any]:
        """Загрузить данные для рендера страницы.

        Вызывается из render_page() после проверки доступа.
        Возвращает dict, который мержится в Jinja2 контекст.
        """
        return {}

    def get_bar_extra(
        self, page: dict, user: dict | None, data: dict
    ) -> dict[str, Any] | None:
        """Дополнительный контекст для sticky header (Tier 1).

        Возвращает dict с type, text, class для badge в bar.
        None — без дополнений.
        """
        return None

    def register_routes(self, router: APIRouter) -> None:
        """Зарегистрировать proxy-маршруты для этого page_type.

        Вызывается один раз при старте приложения.
        Маршруты должны быть вида /p/{slug}/governance/data и т.д.
        """

    def get_config_schema(self) -> dict[str, Any]:
        """JSON Schema для config этого page_type (для валидации)."""
        return {"type": "object"}

    def describe(self) -> dict[str, Any]:
        """Описание handler'а для API /pages/types."""
        return {
            "page_type": self.page_type,
            "template": self.template,
            "scripts": self.scripts,
            "config_schema": self.get_config_schema(),
        }


# ── Утилиты для proxy-маршрутов ──────────────────────────────────────────


async def validate_page_request(
    slug: str, expected_type: str, request: Request
) -> tuple[dict, dict | None]:
    """Общая валидация для proxy-эндпоинтов.

    Возвращает (page, user). Бросает HTTPException при ошибках.
    """
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != expected_type:
        raise HTTPException(status_code=404, detail="Page not found")

    init_data = request.headers.get("X-Init-Data", "")
    user = None
    if init_data:
        user = validate_init_data(init_data, settings.get_bot_token())
        if not user or not user.get("id"):
            raise HTTPException(status_code=401, detail="Invalid initData")
        if not await check_page_access(user["id"], page):
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        config = page.get("config") or {}
        if config.get("access_rules") or config.get("allowed_users"):
            raise HTTPException(status_code=401, detail="Authentication required")

    return page, user


async def proxy_get(
    url: str, headers: dict | None = None, timeout: float = 10.0
) -> JSONResponse:
    """Универсальный GET-прокси к внешнему сервису."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, headers=headers or {})
            return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as e:
        logger.warning("proxy_get %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Service unavailable")


async def proxy_post(
    url: str,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: float = 10.0,
) -> JSONResponse:
    """Универсальный POST-прокси к внешнему сервису."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                url,
                json=json_body,
                headers={**(headers or {}), "Content-Type": "application/json"},
            )
            return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as e:
        logger.warning("proxy_post %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Service unavailable")


async def proxy_delete(
    url: str, headers: dict | None = None, timeout: float = 10.0
) -> JSONResponse:
    """Универсальный DELETE-прокси к внешнему сервису."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.delete(url, headers=headers or {})
            return JSONResponse(r.json(), status_code=r.status_code)
    except Exception as e:
        logger.warning("proxy_delete %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Service unavailable")
