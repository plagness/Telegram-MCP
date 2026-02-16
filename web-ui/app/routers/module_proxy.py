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


async def _http_get(url: str, timeout: float = 5.0) -> dict | list:
    """GET-запрос с обработкой ошибок."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
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
        return_exceptions=True,
    )

    keys = ["k8s", "llm", "planner", "arena", "channel", "metrics", "infra"]
    return JSONResponse({k: _safe_result(r) for k, r in zip(keys, results)})
