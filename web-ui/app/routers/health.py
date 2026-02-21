"""Healthcheck для web-ui + метрики страниц."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import fetch_one
from ..handlers.registry import get_all_handlers
from ..services.health import (
    check_all_pages,
    check_page_health,
    get_health_summary,
    get_page_health_history,
)

router = APIRouter()


@router.get("/health")
async def health():
    """Healthcheck с метриками страниц."""
    handlers = get_all_handlers()

    # Быстрая статистика из БД (может быть недоступна при старте)
    pages_total = 0
    pages_active = 0
    try:
        row = await fetch_one(
            "SELECT COUNT(*) AS total, "
            "COUNT(*) FILTER (WHERE is_active) AS active "
            "FROM web_pages",
        )
        if row:
            pages_total = row["total"]
            pages_active = row["active"]
    except Exception:
        pass

    # Последняя сводка health check'ов
    health_summary = None
    try:
        health_summary = await get_health_summary()
    except Exception:
        pass

    result = {
        "status": "ok",
        "service": "tgweb",
        "handler_types": len(handlers),
        "pages_total": pages_total,
        "pages_active": pages_active,
    }
    if health_summary:
        result["health"] = health_summary

    return result


@router.get("/api/v1/pages/health")
async def pages_health_summary():
    """Сводка health-статуса всех страниц."""
    summary = await get_health_summary()
    return {"ok": True, **summary}


@router.get("/api/v1/pages/{slug}/health")
async def page_health_detail(slug: str, limit: int = Query(20, ge=1, le=100)):
    """История health-check'ов одной страницы."""
    history = await get_page_health_history(slug, limit=limit)
    return {"ok": True, "slug": slug, "history": history}


@router.post("/api/v1/pages/health/check")
async def run_health_check():
    """Запустить проверку всех страниц прямо сейчас."""
    results = await check_all_pages()
    ok_count = sum(1 for r in results if r["status"] == "ok")
    return {
        "ok": True,
        "total": len(results),
        "healthy": ok_count,
        "errors": len(results) - ok_count,
        "results": results,
    }


@router.post("/api/v1/pages/{slug}/health/check")
async def run_single_health_check(slug: str):
    """Запустить проверку одной страницы."""
    result = await check_page_health(slug)
    return {"ok": True, **result}
