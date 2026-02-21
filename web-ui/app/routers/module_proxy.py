"""Прокси-эндпоинты для данных модулей NeuronSwarm.

Каждый модуль получает свой /p/{slug}/<module>/data endpoint,
который проверяет доступ и проксирует данные из соответствующего сервиса.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..services import pages as pages_svc
from ..services.access import check_page_access

router = APIRouter(tags=["module_proxy"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Общий паттерн проверки доступа ──────────────────────────────────────


async def _proxy_module_data(
    slug: str,
    page_type: str,
    request: Request,
    fetch_fn: Callable[[], Any],
) -> JSONResponse:
    """Проверка доступа → загрузка данных → ответ JSON."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != page_type:
        raise HTTPException(status_code=404, detail="Page not found")

    init_data = request.headers.get("X-Init-Data", "")
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

    try:
        data = await fetch_fn()
    except Exception as e:
        logger.warning("module_proxy %s: fetch failed: %s", page_type, e)
        raise HTTPException(status_code=502, detail=f"{page_type} unavailable")
    return JSONResponse(data)


# ── Helpers ─────────────────────────────────────────────────────────────


def _safe_result(r: Any) -> dict | list:
    """Приводим результат gather к dict/list; исключения → пустой dict."""
    if isinstance(r, Exception):
        return {}
    if isinstance(r, (dict, list)):
        return r
    return {}


async def _http_get(url: str, timeout: float = 5.0, headers: dict | None = None) -> dict | list:
    """GET-запрос с обработкой ошибок."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, headers=headers or {})
        if r.status_code != 200:
            return {}
        return r.json()


async def _http_post(url: str, body: dict, timeout: float = 5.0, headers: dict | None = None) -> dict:
    """POST-запрос с JSON body."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=body, headers=headers or {})
        if r.status_code not in (200, 201):
            return {}
        return r.json()


async def _http_put(url: str, body: dict, timeout: float = 5.0, headers: dict | None = None) -> dict:
    """PUT-запрос с JSON body."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.put(url, json=body, headers=headers or {})
        if r.status_code != 200:
            return {}
        return r.json()


async def _call_mcp_tool(
    base_url: str,
    tool_name: str,
    params: dict | None = None,
) -> dict | list:
    """Вызов MCP инструмента через HTTP bridge. Может вернуть list."""
    headers: dict[str, str] = {}
    if settings.mcp_http_token:
        headers["Authorization"] = f"Bearer {settings.mcp_http_token}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{base_url}/tools/{tool_name}",
            json=params or {},
            headers=headers,
        )
        if r.status_code != 200:
            logger.warning("MCP tool %s/%s: status %d", base_url, tool_name, r.status_code)
            return {}
        return r.json()


# ── Channel-MCP ─────────────────────────────────────────────────────────


async def _fetch_channel_data() -> dict:
    """Данные из Channel-MCP: здоровье, каналы, теги."""
    health_task = _http_get(f"{settings.channel_mcp_url}/health")
    channels_task = _call_mcp_tool(settings.channel_mcp_url, "channels.list")
    tags_task = _call_mcp_tool(
        settings.channel_mcp_url, "tags.top",
        {"period": "7d", "limit": 20},
    )

    health, channels, tags = await asyncio.gather(
        health_task, channels_task, tags_task,
        return_exceptions=True,
    )

    return {
        "health": _safe_result(health),
        "channels": _safe_result(channels),
        "tags": _safe_result(tags),
    }


@router.get("/p/{slug}/channel/data")
async def channel_data_proxy(slug: str, request: Request):
    """Прокси: данные Channel-MCP."""
    return await _proxy_module_data(slug, "channel", request, _fetch_channel_data)


# ── LLM-Core (infra + llm dashboards) ──────────────────────────────────


async def _fetch_llm_data() -> dict:
    """Данные из LLM-Core: dashboard snapshot + costs breakdown."""
    base = settings.llm_core_url
    results = await asyncio.gather(
        _http_get(f"{base}/v1/dashboard", timeout=8.0),
        _http_get(f"{base}/v1/costs/summary?period=month"),
        return_exceptions=True,
    )

    keys = ["dashboard", "costs_breakdown"]
    return {k: _safe_result(r) for k, r in zip(keys, results)}


@router.get("/p/{slug}/llm/data")
async def llm_data_proxy(slug: str, request: Request):
    """Прокси: данные LLM-Core."""
    return await _proxy_module_data(slug, "llm", request, _fetch_llm_data)


# ── Arena-LLM ───────────────────────────────────────────────────────────


async def _fetch_arena_data() -> dict:
    """Данные из Arena-LLM: матчи, лидерборд, виды, пресеты, предсказания, здоровье."""
    base = settings.arena_core_url
    results = await asyncio.gather(
        _http_get(f"{base}/v1/matches?limit=20"),
        _http_get(f"{base}/v1/leaderboard"),
        _http_get(f"{base}/v1/species"),
        _http_get(f"{base}/v1/dependencies/health"),
        _http_get(f"{base}/health"),
        _http_get(f"{base}/v1/presets?all=1"),
        _http_get(f"{base}/v1/predictions/pending?limit=20"),
        return_exceptions=True,
    )

    keys = ["matches", "leaderboard", "species", "dependencies", "health",
            "presets", "predictions"]
    return {k: _safe_result(r) for k, r in zip(keys, results)}


@router.get("/p/{slug}/arena/data")
async def arena_data_proxy(slug: str, request: Request):
    """Прокси: данные Arena-LLM."""
    return await _proxy_module_data(slug, "arena", request, _fetch_arena_data)


# ── Planner ──────────────────────────────────────────────────────────────


async def _fetch_planner_data() -> dict:
    """Данные из Planner: задачи, бюджет, speed mode, модули, расписания, триггеры, лог."""
    base = settings.planner_core_url
    results = await asyncio.gather(
        _http_get(f"{base}/v1/tasks?limit=20"),
        _http_get(f"{base}/v1/budget"),
        _http_get(f"{base}/v1/speed"),
        _http_get(f"{base}/v1/modules"),
        _http_get(f"{base}/v1/schedules"),
        _http_get(f"{base}/health"),
        _http_get(f"{base}/v1/triggers"),
        _http_get(f"{base}/v1/log?limit=50"),
        return_exceptions=True,
    )

    keys = ["tasks", "budget", "speed", "modules", "schedules", "health",
            "triggers", "log"]
    return {k: _safe_result(r) for k, r in zip(keys, results)}


@router.get("/p/{slug}/planner/data")
async def planner_data_proxy(slug: str, request: Request):
    """Прокси: данные Planner."""
    return await _proxy_module_data(slug, "planner", request, _fetch_planner_data)


# ── Metrics API ──────────────────────────────────────────────────────────


async def _fetch_metrics_data() -> dict:
    """Данные из Metrics API: рыночные метрики (snapshot), индексы, инфра."""
    base = settings.metrics_api_url
    results = await asyncio.gather(
        _http_get(f"{base}/v1/metrics/snapshot"),
        _http_get(f"{base}/v1/indices/latest"),
        _http_get(f"{base}/v1/infra/latest"),
        _http_get(f"{base}/health"),
        return_exceptions=True,
    )

    keys = ["metrics", "indices", "infra", "health"]
    return {k: _safe_result(r) for k, r in zip(keys, results)}


@router.get("/p/{slug}/metrics/data")
async def metrics_data_proxy(slug: str, request: Request):
    """Прокси: данные Metrics API."""
    return await _proxy_module_data(slug, "metrics", request, _fetch_metrics_data)


# ── BCS-MCP ──────────────────────────────────────────────────────────────


async def _fetch_bcs_data() -> dict:
    """Данные из BCS-MCP: здоровье, портфель, заявки."""
    base = settings.bcs_mcp_url
    results = await asyncio.gather(
        _http_get(f"{base}/health"),
        _call_mcp_tool(base, "bcs.portfolio.get", {"cache_ttl": 60}),
        _call_mcp_tool(base, "bcs.orders.search", {"status": "active", "limit": 20}),
        return_exceptions=True,
    )

    keys = ["health", "portfolio", "orders"]
    return {k: _safe_result(r) for k, r in zip(keys, results)}


@router.get("/p/{slug}/bcs/data")
async def bcs_data_proxy(slug: str, request: Request):
    """Прокси: данные BCS-MCP (owner-only)."""
    return await _proxy_module_data(slug, "bcs", request, _fetch_bcs_data)


# ── Datesale (Integrat) ──────────────────────────────────────────────────

# In-memory кеш Datesale-токенов: tg_id → itg_xxx
_datesale_tokens: dict[int, str] = {}


async def _get_datesale_token(tg_id: int, username: str = "") -> str:
    """Получить/создать Datesale API-токен для пользователя."""
    if tg_id in _datesale_tokens:
        return _datesale_tokens[tg_id]
    resp = await _http_post(
        f"{settings.datesale_url}/v1/auth/token",
        {"tg_id": tg_id, "username": username},
    )
    token = resp.get("token", "")
    if token:
        _datesale_tokens[tg_id] = token
    return token


async def _datesale_get(path: str, tg_id: int, username: str = "") -> dict | list:
    """GET к Datesale API с Bearer-авторизацией."""
    token = await _get_datesale_token(tg_id, username)
    if not token:
        return {}
    return await _http_get(
        f"{settings.datesale_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _datesale_post(path: str, body: dict, tg_id: int, username: str = "") -> dict:
    """POST к Datesale API с Bearer-авторизацией."""
    token = await _get_datesale_token(tg_id, username)
    if not token:
        return {}
    return await _http_post(
        f"{settings.datesale_url}{path}",
        body,
        headers={"Authorization": f"Bearer {token}"},
    )


async def _datesale_put(path: str, body: dict, tg_id: int, username: str = "") -> dict:
    """PUT к Datesale API с Bearer-авторизацией."""
    token = await _get_datesale_token(tg_id, username)
    if not token:
        return {}
    return await _http_put(
        f"{settings.datesale_url}{path}",
        body,
        headers={"Authorization": f"Bearer {token}"},
    )


async def _datesale_delete(path: str, tg_id: int, username: str = "") -> bool:
    """DELETE к Datesale API с Bearer-авторизацией. Возвращает True при 204."""
    token = await _get_datesale_token(tg_id, username)
    if not token:
        return False
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.delete(
            f"{settings.datesale_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
    return r.status_code == 204


def _extract_datesale_user(request: Request) -> dict | None:
    """Извлекает и валидирует пользователя из initData."""
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data:
        return None
    user = validate_init_data(init_data, settings.get_bot_token())
    if not user or not user.get("id"):
        return None
    return user


@router.get("/p/{slug}/datesale/data")
async def datesale_data_proxy(slug: str, request: Request):
    """Прокси: основные данные Integrat (здоровье + чаты пользователя)."""
    from ..db import fetch_all

    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "datesale":
        raise HTTPException(status_code=404, detail="Page not found")

    user = _extract_datesale_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not await check_page_access(user["id"], page):
        raise HTTPException(status_code=403, detail="Access denied")

    # Параллельно: здоровье Datesale + список чатов пользователя из tgweb DB
    health_task = _http_get(f"{settings.datesale_url}/health", timeout=3.0)
    chats_task = fetch_all(
        """
        SELECT c.chat_id, c.title, c.username, c.member_count, c.photo_file_id, c.type
        FROM chat_members cm
        JOIN chats c ON c.chat_id = cm.chat_id
        WHERE cm.user_id = %s AND cm.status NOT IN ('left', 'kicked')
        ORDER BY cm.updated_at DESC NULLS LAST
        """,
        [str(user["id"])],
    )

    health, chats = await asyncio.gather(health_task, chats_task, return_exceptions=True)

    return JSONResponse({
        "health": _safe_result(health),
        "chats": _safe_result(chats) if not isinstance(chats, Exception) else [],
    })


@router.get("/p/{slug}/datesale/chats/{tg_chat_id}/plugins")
async def datesale_chat_plugins_proxy(slug: str, tg_chat_id: str, request: Request):
    """Прокси: плагины для конкретного чата."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "datesale":
        raise HTTPException(status_code=404, detail="Page not found")

    user = _extract_datesale_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not await check_page_access(user["id"], page):
        raise HTTPException(status_code=403, detail="Access denied")

    tg_id = user["id"]
    username = user.get("username", "")

    # Получаем плагины чата из Datesale
    plugins = await _datesale_get(
        f"/v1/chats/tg/{tg_chat_id}/plugins",
        tg_id, username,
    )
    if not isinstance(plugins, list):
        plugins = []

    return JSONResponse({"plugins": plugins})


@router.get("/p/{slug}/datesale/plugins/{plugin_id}/config")
async def datesale_plugin_config_proxy(slug: str, plugin_id: int, request: Request):
    """Прокси: схема config_fields + текущие значения."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "datesale":
        raise HTTPException(status_code=404, detail="Page not found")

    user = _extract_datesale_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not await check_page_access(user["id"], page):
        raise HTTPException(status_code=403, detail="Access denied")

    tg_chat_id = request.query_params.get("tg_chat_id", "0")
    config = await _datesale_get(
        f"/v1/plugins/{plugin_id}/config?tg_chat_id={tg_chat_id}",
        user["id"], user.get("username", ""),
    )

    return JSONResponse(config if isinstance(config, dict) else {})


def _validate_chat_user(request: Request) -> dict:
    """Извлекает и валидирует пользователя из X-Init-Data для chat endpoints."""
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = validate_init_data(init_data, settings.get_bot_token())
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid initData")
    return user


@router.get("/chat/{chat_id}/plugins")
async def chat_plugins_proxy(chat_id: str, request: Request):
    """Прокси: включённые Integrat-плагины для чата."""
    user = _validate_chat_user(request)
    plugins = await _datesale_get(
        f"/v1/chats/tg/{chat_id}/plugins",
        user["id"], user.get("username", ""),
    )
    if not isinstance(plugins, list):
        plugins = []
    return JSONResponse({"plugins": plugins})


@router.get("/chat/{chat_id}/marketplace")
async def chat_marketplace_proxy(chat_id: str, request: Request):
    """Прокси: все доступные плагины + статус включения для чата."""
    user = _validate_chat_user(request)
    tg_id = user["id"]
    username = user.get("username", "")

    # Параллельно: все плагины (глобально) + включённые для этого чата
    all_task = _datesale_get("/v1/plugins?all=1", tg_id, username)
    enabled_task = _datesale_get(f"/v1/chats/tg/{chat_id}/plugins", tg_id, username)

    all_plugins, enabled_plugins = await asyncio.gather(
        all_task, enabled_task, return_exceptions=True,
    )

    if isinstance(all_plugins, Exception) or not isinstance(all_plugins, list):
        all_plugins = []
    if isinstance(enabled_plugins, Exception) or not isinstance(enabled_plugins, list):
        enabled_plugins = []

    enabled_ids = {p.get("id") for p in enabled_plugins if isinstance(p, dict)}

    for p in all_plugins:
        if isinstance(p, dict):
            p["enabled"] = p.get("id") in enabled_ids

    return JSONResponse({"plugins": all_plugins, "enabled_ids": list(enabled_ids)})


@router.post("/chat/{chat_id}/plugins/{plugin_id}/enable")
async def chat_enable_plugin_proxy(chat_id: str, plugin_id: int, request: Request):
    """Прокси: включить плагин для чата."""
    user = _validate_chat_user(request)
    result = await _datesale_post(
        f"/v1/chats/tg/{chat_id}/plugins",
        {"plugin_id": plugin_id},
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"status": "error"})


@router.get("/chat/{chat_id}/plugins/{plugin_id}/config")
async def chat_plugin_config_proxy(chat_id: str, plugin_id: int, request: Request):
    """Прокси: схема config_fields + текущие значения для чата."""
    user = _validate_chat_user(request)
    config = await _datesale_get(
        f"/v1/plugins/{plugin_id}/config?tg_chat_id={chat_id}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(config if isinstance(config, dict) else {})


@router.put("/chat/{chat_id}/plugins/{plugin_id}/config")
async def chat_plugin_config_save_proxy(chat_id: str, plugin_id: int, request: Request):
    """Прокси: сохранить конфигурацию плагина для чата."""
    user = _validate_chat_user(request)
    body = await request.json()
    body["tg_chat_id"] = int(chat_id)
    result = await _datesale_put(
        f"/v1/plugins/{plugin_id}/config",
        body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"status": "error"})


@router.put("/p/{slug}/datesale/plugins/{plugin_id}/config")
async def datesale_plugin_config_save(slug: str, plugin_id: int, request: Request):
    """Прокси: сохранить конфигурацию плагина."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "datesale":
        raise HTTPException(status_code=404, detail="Page not found")

    user = _extract_datesale_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not await check_page_access(user["id"], page):
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.json()
    result = await _datesale_put(
        f"/v1/plugins/{plugin_id}/config",
        body,
        user["id"], user.get("username", ""),
    )

    return JSONResponse(result if isinstance(result, dict) else {"status": "error"})


# ── Marketplace (глобальный каталог плагинов) ────────────────────────────


@router.get("/marketplace/plugins")
async def marketplace_all_plugins(request: Request):
    """Все плагины для глобального маркетплейса."""
    user = _validate_chat_user(request)
    plugins = await _datesale_get(
        "/v1/plugins?all=1", user["id"], user.get("username", ""),
    )
    if not isinstance(plugins, list):
        plugins = []
    return JSONResponse({"plugins": plugins})


@router.get("/marketplace/plugins/{plugin_id}")
async def marketplace_plugin_detail(plugin_id: int, request: Request):
    """Детали плагина + его эндпоинты."""
    user = _validate_chat_user(request)
    tg_id, username = user["id"], user.get("username", "")
    plugin_task = _datesale_get(f"/v1/plugins/{plugin_id}", tg_id, username)
    endpoints_task = _datesale_get(
        f"/v1/plugins/{plugin_id}/endpoints", tg_id, username,
    )
    plugin, endpoints = await asyncio.gather(
        plugin_task, endpoints_task, return_exceptions=True,
    )
    ep = _safe_result(endpoints)
    return JSONResponse({
        "plugin": _safe_result(plugin),
        "endpoints": ep if isinstance(ep, list) else [],
    })


# ── Marketplace v2 (расширенный каталог) ─────────────────────────────────


@router.get("/marketplace/v2/search")
async def marketplace_v2_search(request: Request):
    """Поиск плагинов в маркетплейсе с фильтрами."""
    user = _validate_chat_user(request)
    qs = str(request.url.query)
    data = await _datesale_get(
        f"/v1/marketplace?{qs}", user["id"], user.get("username", ""),
    )
    return JSONResponse(_safe_result(data) if isinstance(data, dict) else {"plugins": [], "total": 0})


@router.get("/marketplace/v2/featured")
async def marketplace_v2_featured(request: Request):
    """Featured-плагины."""
    user = _validate_chat_user(request)
    qs = str(request.url.query)
    data = await _datesale_get(
        f"/v1/marketplace/featured?{qs}", user["id"], user.get("username", ""),
    )
    return JSONResponse(_safe_result(data) if isinstance(data, dict) else {"plugins": []})


@router.get("/marketplace/v2/top")
async def marketplace_v2_top(request: Request):
    """Топ плагинов по установкам."""
    user = _validate_chat_user(request)
    qs = str(request.url.query)
    data = await _datesale_get(
        f"/v1/marketplace/top?{qs}", user["id"], user.get("username", ""),
    )
    return JSONResponse(_safe_result(data) if isinstance(data, dict) else {"plugins": []})


@router.get("/marketplace/v2/categories")
async def marketplace_v2_categories(request: Request):
    """Категории с подсчётом плагинов."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        "/v1/marketplace/categories", user["id"], user.get("username", ""),
    )
    return JSONResponse(data if isinstance(data, list) else [])


@router.get("/marketplace/v2/plugin/{slug}")
async def marketplace_v2_plugin(slug: str, request: Request):
    """Детальная страница плагина (v2)."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        f"/v1/marketplace/{slug}", user["id"], user.get("username", ""),
    )
    return JSONResponse(_safe_result(data) if isinstance(data, dict) else {"error": "not found"})


@router.get("/marketplace/v2/author/{tg_id}")
async def marketplace_v2_author(tg_id: int, request: Request):
    """Профиль автора."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        f"/v1/marketplace/authors/{tg_id}", user["id"], user.get("username", ""),
    )
    return JSONResponse(_safe_result(data) if isinstance(data, dict) else {"error": "not found"})


# ── Marketplace v2: Subscribe (Telegram Stars) ──────────────────────────


@router.post("/marketplace/v2/subscribe/{listing_id}")
async def marketplace_v2_subscribe(listing_id: int, request: Request):
    """Создать Telegram Stars invoice для подписки.

    1. Получаем listing из datesale
    2. Создаём invoice через Telegram Bot API (createInvoiceLink)
    3. Возвращаем {invoice_url} — клиент вызывает WebApp.openInvoice()
    """
    user = _validate_chat_user(request)
    tg_id = user["id"]
    username = user.get("username", "")

    # Получаем listing
    listing = await _datesale_get(
        f"/v1/listings/{listing_id}", tg_id, username,
    )
    if not listing or not isinstance(listing, dict) or not listing.get("id"):
        raise HTTPException(status_code=404, detail="Listing not found")

    price = listing.get("price_stars", 0)
    if price <= 0:
        raise HTTPException(status_code=400, detail="Invalid listing price")

    ep_name = listing.get("endpoint_name") or listing.get("endpoint_slug") or "Endpoint"
    billing = listing.get("billing_type", "subscription")
    period = listing.get("period_days", 0)

    title = f"Подписка: {ep_name}"
    description = f"{billing}"
    if period > 0:
        description += f" на {period} дн."

    # Payload для webhook-обработки
    payload = f"listing:{listing_id}:buyer:{tg_id}"

    # Создаём invoice через Telegram Bot API
    bot_token = settings.get_bot_token()
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{bot_token}/createInvoiceLink",
            json={
                "title": title,
                "description": description,
                "payload": payload,
                "currency": "XTR",
                "prices": [{"label": title, "amount": price}],
            },
        )
        data = r.json()
        if not data.get("ok"):
            logger.error("createInvoiceLink failed: %s", data)
            raise HTTPException(status_code=502, detail="Failed to create invoice")

        return JSONResponse({"invoice_url": data["result"]})


@router.get("/marketplace/v2/listings/{listing_id}")
async def marketplace_v2_listing(listing_id: int, request: Request):
    """Получить информацию о листинге."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        f"/v1/listings/{listing_id}", user["id"], user.get("username", ""),
    )
    return JSONResponse(_safe_result(data) if isinstance(data, dict) else {"error": "not found"})


# ── Developer (кабинет разработчика) ─────────────────────────────────────


@router.get("/developer/token")
async def developer_get_token(request: Request):
    """Получить/создать API-токен разработчика."""
    user = _validate_chat_user(request)
    resp = await _http_post(
        f"{settings.datesale_url}/v1/auth/token",
        {"tg_id": user["id"], "username": user.get("username", "")},
    )
    return JSONResponse(resp if isinstance(resp, dict) else {})


@router.get("/developer/plugins")
async def developer_list_plugins(request: Request):
    """Плагины текущего пользователя (без ?all=1 → фильтр по owner)."""
    user = _validate_chat_user(request)
    plugins = await _datesale_get(
        "/v1/plugins", user["id"], user.get("username", ""),
    )
    return JSONResponse({"plugins": plugins if isinstance(plugins, list) else []})


@router.post("/developer/plugins")
async def developer_create_plugin(request: Request):
    """Создать плагин."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_post(
        "/v1/plugins", body, user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.put("/developer/plugins/{plugin_id}")
async def developer_update_plugin(plugin_id: int, request: Request):
    """Обновить плагин."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_put(
        f"/v1/plugins/{plugin_id}", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.delete("/developer/plugins/{plugin_id}")
async def developer_delete_plugin(plugin_id: int, request: Request):
    """Удалить плагин."""
    user = _validate_chat_user(request)
    ok = await _datesale_delete(
        f"/v1/plugins/{plugin_id}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"ok": ok})


@router.get("/developer/plugins/{plugin_id}/endpoints")
async def developer_list_endpoints(plugin_id: int, request: Request):
    """Эндпоинты плагина."""
    user = _validate_chat_user(request)
    endpoints = await _datesale_get(
        f"/v1/plugins/{plugin_id}/endpoints",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(
        {"endpoints": endpoints if isinstance(endpoints, list) else []},
    )


@router.post("/developer/plugins/{plugin_id}/endpoints")
async def developer_create_endpoint(plugin_id: int, request: Request):
    """Создать эндпоинт плагина."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_post(
        f"/v1/plugins/{plugin_id}/endpoints", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.put("/developer/plugins/{plugin_id}/endpoints/{endpoint_id}")
async def developer_update_endpoint(plugin_id: int, endpoint_id: int, request: Request):
    """Обновить эндпоинт плагина."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_put(
        f"/v1/plugins/{plugin_id}/endpoints/{endpoint_id}", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.delete("/developer/plugins/{plugin_id}/endpoints/{endpoint_id}")
async def developer_delete_endpoint(plugin_id: int, endpoint_id: int, request: Request):
    """Удалить эндпоинт плагина."""
    user = _validate_chat_user(request)
    ok = await _datesale_delete(
        f"/v1/plugins/{plugin_id}/endpoints/{endpoint_id}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"ok": ok})


# ── Access Control (запросы и гранты доступа) ────────────────────────────


@router.post("/marketplace/plugins/{plugin_id}/endpoints/{endpoint_id}/request")
async def marketplace_request_access(plugin_id: int, endpoint_id: int, request: Request):
    """Запросить доступ к gated-эндпоинту."""
    user = _validate_chat_user(request)
    body = await request.json() if request.headers.get("content-length", "0") != "0" else {}
    result = await _datesale_post(
        f"/v1/endpoints/{endpoint_id}/request", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.get("/developer/plugins/{plugin_id}/requests")
async def developer_list_access_requests(plugin_id: int, request: Request):
    """Входящие запросы доступа к плагину (для владельца)."""
    user = _validate_chat_user(request)
    status_filter = request.query_params.get("status", "")
    path = f"/v1/plugins/{plugin_id}/requests"
    if status_filter:
        path += f"?status={status_filter}"
    data = await _datesale_get(path, user["id"], user.get("username", ""))
    return JSONResponse({"requests": data if isinstance(data, list) else []})


@router.put("/developer/requests/{request_id}/approve")
async def developer_approve_request(request_id: int, request: Request):
    """Одобрить запрос доступа."""
    user = _validate_chat_user(request)
    result = await _datesale_put(
        f"/v1/requests/{request_id}/approve", {},
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.put("/developer/requests/{request_id}/deny")
async def developer_deny_request(request_id: int, request: Request):
    """Отклонить запрос доступа."""
    user = _validate_chat_user(request)
    result = await _datesale_put(
        f"/v1/requests/{request_id}/deny", {},
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.get("/developer/plugins/{plugin_id}/grants")
async def developer_list_grants(plugin_id: int, request: Request):
    """Список выданных доступов к плагину."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        f"/v1/plugins/{plugin_id}/grants",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"grants": data if isinstance(data, list) else []})


@router.post("/developer/plugins/{plugin_id}/grants")
async def developer_create_grant(plugin_id: int, request: Request):
    """Ручная выдача доступа (owner → user/chat)."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_post(
        f"/v1/plugins/{plugin_id}/grants", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.delete("/developer/grants/{grant_id}")
async def developer_revoke_grant(grant_id: int, request: Request):
    """Отозвать доступ."""
    user = _validate_chat_user(request)
    ok = await _datesale_delete(
        f"/v1/grants/{grant_id}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"ok": ok})


@router.get("/developer/access")
async def developer_my_access(request: Request):
    """Мои полученные доступы."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        "/v1/users/me/access",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"grants": data if isinstance(data, list) else []})


# ── Monetization (листинги, подписки, revenue) ──────────────────────────


@router.get("/developer/plugins/{plugin_id}/listings")
async def developer_list_listings(plugin_id: int, request: Request):
    """Листинги плагина (для владельца)."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        f"/v1/plugins/{plugin_id}/listings",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"listings": data if isinstance(data, list) else []})


@router.post("/developer/plugins/{plugin_id}/listings")
async def developer_create_listing(plugin_id: int, request: Request):
    """Создать листинг для эндпоинта."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_post(
        f"/v1/plugins/{plugin_id}/listings", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.put("/developer/listings/{listing_id}")
async def developer_update_listing(listing_id: int, request: Request):
    """Обновить листинг."""
    user = _validate_chat_user(request)
    body = await request.json()
    result = await _datesale_put(
        f"/v1/listings/{listing_id}", body,
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"error": "failed"})


@router.delete("/developer/listings/{listing_id}")
async def developer_deactivate_listing(listing_id: int, request: Request):
    """Деактивировать листинг."""
    user = _validate_chat_user(request)
    ok = await _datesale_delete(
        f"/v1/listings/{listing_id}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"ok": ok})


@router.get("/developer/plugins/{plugin_id}/revenue")
async def developer_plugin_revenue(plugin_id: int, request: Request):
    """Доход плагина за период."""
    user = _validate_chat_user(request)
    days = request.query_params.get("days", "30")
    data = await _datesale_get(
        f"/v1/plugins/{plugin_id}/revenue?days={days}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(data if isinstance(data, dict) else {})


@router.get("/developer/subscriptions")
async def developer_my_subscriptions(request: Request):
    """Мои подписки (как покупатель)."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        "/v1/users/me/subscriptions",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"subscriptions": data if isinstance(data, list) else []})


@router.get("/developer/transactions")
async def developer_my_transactions(request: Request):
    """Мои транзакции."""
    user = _validate_chat_user(request)
    limit = request.query_params.get("limit", "50")
    offset = request.query_params.get("offset", "0")
    data = await _datesale_get(
        f"/v1/users/me/transactions?limit={limit}&offset={offset}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"transactions": data if isinstance(data, list) else []})


# ── Statistics (статистика использования) ─────────────────────────────────


@router.get("/developer/plugins/{plugin_id}/stats")
async def developer_plugin_stats(plugin_id: int, request: Request):
    """Агрегированная статистика плагина."""
    user = _validate_chat_user(request)
    period = request.query_params.get("period", "7d")
    data = await _datesale_get(
        f"/v1/plugins/{plugin_id}/stats?period={period}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(data if isinstance(data, dict) else {})


@router.get("/developer/endpoints/{endpoint_id}/stats")
async def developer_endpoint_stats(endpoint_id: int, request: Request):
    """Статистика эндпоинта."""
    user = _validate_chat_user(request)
    period = request.query_params.get("period", "7d")
    data = await _datesale_get(
        f"/v1/endpoints/{endpoint_id}/stats?period={period}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(data if isinstance(data, dict) else {})


@router.get("/developer/my-stats")
async def developer_my_consumption_stats(request: Request):
    """Статистика моего потребления."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        "/v1/users/me/stats",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"stats": data if isinstance(data, list) else []})


# ── Notifications (уведомления) ──────────────────────────────────────────


@router.get("/notifications")
async def list_notifications(request: Request):
    """Список уведомлений пользователя."""
    user = _validate_chat_user(request)
    limit = request.query_params.get("limit", "50")
    offset = request.query_params.get("offset", "0")
    data = await _datesale_get(
        f"/v1/notifications?limit={limit}&offset={offset}",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"notifications": data if isinstance(data, list) else []})


@router.get("/notifications/unread")
async def unread_notification_count(request: Request):
    """Количество непрочитанных уведомлений."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        "/v1/notifications/unread",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(data if isinstance(data, dict) else {"count": 0})


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: int, request: Request):
    """Пометить уведомление прочитанным."""
    user = _validate_chat_user(request)
    result = await _datesale_put(
        f"/v1/notifications/{notification_id}/read", {},
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"ok": False})


@router.put("/notifications/read-all")
async def mark_all_notifications_read(request: Request):
    """Пометить все уведомления прочитанными."""
    user = _validate_chat_user(request)
    result = await _datesale_put(
        "/v1/notifications/read-all", {},
        user["id"], user.get("username", ""),
    )
    return JSONResponse(result if isinstance(result, dict) else {"ok": False})


# ── Users / Profile ──────────────────────────────────────────────────────


@router.get("/developer/profile")
async def developer_profile(request: Request):
    """Профиль текущего пользователя."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        "/v1/users/me",
        user["id"], user.get("username", ""),
    )
    return JSONResponse(data if isinstance(data, dict) else {})


@router.get("/user/{tg_id}/plugins")
async def user_public_plugins(tg_id: int, request: Request):
    """Публичные плагины пользователя."""
    user = _validate_chat_user(request)
    data = await _datesale_get(
        f"/v1/users/{tg_id}/plugins",
        user["id"], user.get("username", ""),
    )
    return JSONResponse({"plugins": data if isinstance(data, list) else []})


# ── K8s Pods ─────────────────────────────────────────────────────────────

# Пути к ServiceAccount token (монтируются автоматически K8s)
_SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
_K8S_API = "https://kubernetes.default.svc"


async def _fetch_k8s_data() -> dict:
    """Данные K8s кластера через K8s API + ServiceAccount token."""
    import ssl
    from pathlib import Path

    token_path = Path(_SA_TOKEN_PATH)
    ca_path = Path(_SA_CA_PATH)

    if not token_path.exists():
        return {"error": "ServiceAccount token not found", "pods": [], "summary": {}}

    token = token_path.read_text().strip()

    # SSL с CA сертификатом кластера
    ssl_ctx = ssl.create_default_context(cafile=str(ca_path)) if ca_path.exists() else False

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            verify=ssl_ctx,
        ) as client:
            r = await client.get(
                f"{_K8S_API}/api/v1/pods",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code == 403:
                return {"error": "RBAC: нет прав на list pods", "pods": [], "summary": {}}
            if r.status_code != 200:
                return {"error": f"K8s API: {r.status_code}", "pods": [], "summary": {}}
            raw = r.json()
    except Exception as e:
        return {"error": f"K8s API error: {e}", "pods": [], "summary": {}}

    pods: list[dict] = []
    issues: list[dict] = []
    ns_counts: dict[str, int] = {}
    status_counts = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0, "Unknown": 0}

    for item in raw.get("items", []):
        meta = item.get("metadata", {})
        spec = item.get("spec", {})
        status = item.get("status", {})
        phase = status.get("phase", "Unknown")
        ns = meta.get("namespace", "")
        name = meta.get("name", "")

        # Рестарты и статус контейнеров
        restarts = 0
        container_statuses = []
        ready_count = 0
        total_count = 0
        for cs in status.get("containerStatuses", []):
            restarts += cs.get("restartCount", 0)
            total_count += 1
            if cs.get("ready"):
                ready_count += 1
            waiting = cs.get("state", {}).get("waiting", {})
            if waiting.get("reason"):
                container_statuses.append(waiting["reason"])

        # Вычисляемый статус
        display_status = phase
        if container_statuses:
            display_status = container_statuses[0]

        # Возраст
        created = meta.get("creationTimestamp", "")

        pod_info = {
            "namespace": ns,
            "name": name,
            "status": display_status,
            "phase": phase,
            "ready": f"{ready_count}/{total_count}" if total_count else "0/0",
            "restarts": restarts,
            "node": spec.get("nodeName", ""),
            "created": created,
        }
        pods.append(pod_info)

        # Счётчики
        ns_counts[ns] = ns_counts.get(ns, 0) + 1
        status_counts[phase] = status_counts.get(phase, 0) + 1

        # Issues
        if display_status in ("CrashLoopBackOff", "Error", "OOMKilled", "ImagePullBackOff"):
            issues.append({"namespace": ns, "name": name, "reason": display_status, "restarts": restarts})
        elif restarts > 10:
            issues.append({"namespace": ns, "name": name, "reason": f"{restarts} restarts", "restarts": restarts})

    return {
        "pods": pods,
        "issues": issues,
        "summary": {
            "total": len(pods),
            "namespaces": len(ns_counts),
            "by_namespace": ns_counts,
            "by_status": status_counts,
        },
    }


@router.get("/p/{slug}/k8s/data")
async def k8s_data_proxy(slug: str, request: Request):
    """Прокси: данные K8s кластера."""
    return await _proxy_module_data(slug, "k8s", request, _fetch_k8s_data)


# ── Hub Mini-Metrics ────────────────────────────────────────────────────


async def _mini_k8s() -> dict:
    """Лёгкие метрики K8s для hub card."""
    data = await _fetch_k8s_data()
    s = data.get("summary", {})
    by_status = s.get("by_status", {})
    return {"total": s.get("total", 0), "running": by_status.get("Running", 0)}


async def _mini_llm() -> dict:
    """Лёгкие метрики LLM для hub card."""
    data = await _http_get(f"{settings.llm_core_url}/v1/dashboard", timeout=3.0)
    if not data or isinstance(data, Exception):
        return {}
    return {
        "models": data.get("models_count", 0),
        "running": (data.get("jobs") or {}).get("running", 0),
    }


async def _mini_planner() -> dict:
    """Лёгкие метрики Planner для hub card."""
    data = await _http_get(f"{settings.planner_core_url}/v1/budget", timeout=3.0)
    if not data or isinstance(data, Exception):
        return {}
    monthly = data.get("monthly", {})
    return {
        "spent": round(monthly.get("spent_usd", 0), 4),
        "limit": round(monthly.get("limit_usd", 0), 2),
    }


async def _mini_arena() -> dict:
    """Лёгкие метрики Arena для hub card."""
    data = await _http_get(f"{settings.arena_core_url}/v1/matches?limit=1", timeout=3.0)
    if not data or isinstance(data, Exception):
        return {}
    items = data.get("items", [])
    return {"matches": len(items)}


async def _mini_channel() -> dict:
    """Лёгкие метрики Channel для hub card."""
    data = await _call_mcp_tool(settings.channel_mcp_url, "channels.list")
    if isinstance(data, list):
        return {"count": len(data)}
    if isinstance(data, dict):
        channels = data.get("channels", data.get("content", []))
        if isinstance(channels, list):
            return {"count": len(channels)}
    return {"count": 0}


async def _mini_metrics() -> dict:
    """Лёгкие метрики Metrics для hub card."""
    data = await _http_get(f"{settings.metrics_api_url}/v1/metrics/snapshot", timeout=3.0)
    if not data or isinstance(data, Exception):
        return {}
    return {"usd_rub": data.get("usd_rub")}


async def _mini_infra() -> dict:
    """Лёгкие метрики Infra для hub card."""
    data = await _http_get(f"{settings.llm_core_url}/v1/dashboard", timeout=3.0)
    if not data or isinstance(data, Exception):
        return {}
    hosts = data.get("hosts", [])
    online = sum(1 for h in hosts if h.get("status") == "online")
    return {"online": online, "total": len(hosts)}


async def _mini_datesale() -> dict:
    """Лёгкие метрики Datesale для hub card."""
    data = await _http_get(f"{settings.datesale_url}/health", timeout=3.0)
    if not data or isinstance(data, Exception):
        return {}
    return {"status": data.get("status", "unknown")}


@router.get("/hub/mini-metrics")
async def hub_mini_metrics(request: Request):
    """Агрегированные мини-метрики для hub cards (owner-only)."""
    init_data = request.headers.get("X-Init-Data", "")
    if not init_data:
        return JSONResponse({})

    user = validate_init_data(init_data, settings.get_bot_token())
    if not user or not user.get("id"):
        return JSONResponse({})

    results = await asyncio.gather(
        _mini_k8s(),
        _mini_llm(),
        _mini_planner(),
        _mini_arena(),
        _mini_channel(),
        _mini_metrics(),
        _mini_infra(),
        _mini_datesale(),
        return_exceptions=True,
    )

    keys = ["k8s", "llm", "planner", "arena", "channel", "metrics", "infra", "datesale"]
    return JSONResponse({k: _safe_result(r) for k, r in zip(keys, results)})
