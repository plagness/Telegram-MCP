"""Proxy-роутер для web-ui модуля.

Проксирует запросы к tgweb (web-ui сервису) через единую точку tgapi.
Это позволяет MCP и SDK работать только с tgapi.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from ..config import get_settings

router = APIRouter(prefix="/v1/web", tags=["web-ui"])
logger = logging.getLogger(__name__)
settings = get_settings()


def _webui_url() -> str:
    """URL web-ui сервиса."""
    return settings.webui_public_url.rstrip("/") if settings.webui_enabled else ""


async def _proxy(method: str, path: str, body: dict | None = None) -> dict:
    """Проксировать запрос к tgweb."""
    if not settings.webui_enabled:
        raise HTTPException(status_code=503, detail="Web-UI module is disabled")

    # Внутренний URL (Docker network, TLS без проверки — внутренняя сеть)
    base = "https://tgweb:8000"

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            if method == "GET":
                r = await client.get(f"{base}{path}")
            elif method == "POST":
                r = await client.post(f"{base}{path}", json=body or {})
            elif method == "DELETE":
                r = await client.delete(f"{base}{path}")
            else:
                raise ValueError(f"Unsupported method: {method}")

            if r.status_code >= 400:
                detail = r.text
                try:
                    detail = r.json().get("detail", r.text)
                except Exception:
                    pass
                raise HTTPException(status_code=r.status_code, detail=detail)

            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Web-UI service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Web-UI proxy error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/pages")
async def create_page(request: Request):
    """Создать веб-страницу."""
    body = await request.json()
    return await _proxy("POST", "/api/v1/pages", body)


@router.get("/pages")
async def list_pages(
    page_type: str | None = Query(None),
    bot_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список страниц."""
    qs = f"?limit={limit}&offset={offset}"
    if page_type:
        qs += f"&page_type={page_type}"
    if bot_id is not None:
        qs += f"&bot_id={bot_id}"
    return await _proxy("GET", f"/api/v1/pages{qs}")


@router.get("/pages/{slug}")
async def get_page(slug: str):
    """Конфигурация страницы."""
    return await _proxy("GET", f"/api/v1/pages/{slug}")


@router.delete("/pages/{slug}")
async def delete_page(slug: str):
    """Удалить страницу."""
    return await _proxy("DELETE", f"/api/v1/pages/{slug}")


@router.post("/pages/{slug}/links")
async def create_link(slug: str, request: Request):
    """Создать индивидуальную ссылку."""
    body = await request.json()
    return await _proxy("POST", f"/api/v1/pages/{slug}/links", body)


@router.get("/pages/{slug}/submissions")
async def get_submissions(
    slug: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Ответы на форму."""
    return await _proxy("GET", f"/api/v1/pages/{slug}/submissions?limit={limit}&offset={offset}")
