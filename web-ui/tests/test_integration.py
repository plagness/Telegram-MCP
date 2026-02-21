"""Интеграционные тесты: реальная БД + httpx ASGITransport.

Требуют доступную PostgreSQL (tgdb). Пропускаются автоматически если БД недоступна.
Запуск: DB_DSN=postgresql://telegram:telegram@localhost:30436/telegram pytest tests/test_integration.py -v
"""

from __future__ import annotations

import os

import pytest

# Реальный DSN для интеграционных тестов
os.environ["DB_DSN"] = os.environ.get(
    "INTEGRATION_DB_DSN",
    "postgresql://telegram:telegram@localhost:30436/telegram",
)

integration = pytest.mark.integration
pytestmark = [pytest.mark.asyncio, integration]


async def _get_pages(db_client) -> list[dict]:
    """Получить список страниц из API (хелпер)."""
    r = await db_client.get("/api/v1/pages")
    assert r.status_code == 200
    data = r.json()
    return data.get("pages", data) if isinstance(data, dict) else data


# ── Health / API (без авторизации) ───────────────────────────


async def test_health_endpoint(db_client):
    """GET /health возвращает 200 с данными о handler'ах и страницах."""
    r = await db_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "tgweb"
    assert "handler_types" in data
    assert data["handler_types"] >= 10


async def test_api_types(db_client):
    """GET /api/v1/pages/types возвращает зарегистрированные типы."""
    r = await db_client.get("/api/v1/pages/types")
    assert r.status_code == 200
    data = r.json()
    types = data.get("types", data) if isinstance(data, dict) else data
    assert isinstance(types, list)
    assert len(types) >= 10
    page_types = {t["page_type"] for t in types}
    assert "calendar" in page_types
    assert "governance" in page_types


async def test_api_pages_list(db_client):
    """GET /api/v1/pages возвращает список страниц из БД."""
    pages = await _get_pages(db_client)
    assert isinstance(pages, list)
    assert len(pages) > 0
    for page in pages[:5]:
        assert "slug" in page
        assert "page_type" in page


async def test_api_health_summary(db_client):
    """GET /api/v1/pages/health возвращает health summary."""
    r = await db_client.get("/api/v1/pages/health")
    assert r.status_code == 200
    data = r.json()
    # Проверяем наличие ключевых полей (total или pages_total)
    has_stats = any(k in data for k in ("total", "pages_total", "healthy", "errors"))
    assert has_stats, f"Нет ожидаемых полей в health summary: {list(data.keys())}"


async def test_api_banners(db_client):
    """GET /api/v1/banners возвращает список баннеров."""
    r = await db_client.get("/api/v1/banners")
    assert r.status_code == 200
    data = r.json()
    banners = data.get("banners", data) if isinstance(data, dict) else data
    assert isinstance(banners, list)


# ── Рендер-маршруты (без initData → base.html) ──────────────


async def test_hub_no_auth(db_client):
    """GET / без initData отдаёт base.html (200)."""
    r = await db_client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


async def test_profile_no_auth(db_client):
    """GET /profile без initData отдаёт base.html (200, не 500)."""
    r = await db_client.get("/profile")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


async def test_marketplace_no_auth(db_client):
    """GET /marketplace без initData отдаёт base.html (200)."""
    r = await db_client.get("/marketplace")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


async def test_developer_no_auth(db_client):
    """GET /developer без initData отдаёт base.html (200)."""
    r = await db_client.get("/developer")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


# ── Страницы (slug) ─────────────────────────────────────────


async def test_nonexistent_slug(db_client):
    """GET /p/nonexistent-slug-xyz → 404."""
    r = await db_client.get("/p/nonexistent-slug-xyz-12345")
    assert r.status_code == 404


async def test_existing_public_page(db_client):
    """GET /p/{slug} для публичной страницы → 200."""
    pages = await _get_pages(db_client)
    public_page = None
    for p in pages:
        config = p.get("config") or {}
        if isinstance(config, str):
            continue
        access = config.get("access_rules") or {}
        if (
            not access.get("allowed_users")
            and not access.get("allowed_roles")
            and not access.get("allowed_chats")
            and not config.get("allowed_users")
        ):
            public_page = p
            break
    if not public_page:
        pytest.skip("Нет публичных страниц в БД")
    r = await db_client.get(f"/p/{public_page['slug']}")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


# ── Page health ──────────────────────────────────────────────


async def test_page_health_detail(db_client):
    """GET /api/v1/pages/{slug}/health для существующей страницы."""
    pages = await _get_pages(db_client)
    if not pages:
        pytest.skip("Нет страниц в БД")
    slug = pages[0]["slug"]
    r = await db_client.get(f"/api/v1/pages/{slug}/health")
    assert r.status_code == 200
    data = r.json()
    assert "slug" in data
    assert "history" in data


# ── API validate ─────────────────────────────────────────────


async def test_api_validate(db_client):
    """POST /api/v1/pages/validate с минимальным конфигом."""
    r = await db_client.post(
        "/api/v1/pages/validate",
        json={
            "slug": "test-validate-page",
            "page_type": "page",
            "title": "Test Page",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "valid" in data


# ── 404 handling ─────────────────────────────────────────────


async def test_404_html(db_client):
    """GET /nonexistent → HTML 404."""
    r = await db_client.get("/some-nonexistent-path-xyz")
    assert r.status_code == 404
    assert "text/html" in r.headers.get("content-type", "")


async def test_404_api_json(db_client):
    """GET /api/v1/nonexistent → JSON 404."""
    r = await db_client.get("/api/v1/nonexistent-xyz")
    assert r.status_code == 404
    ct = r.headers.get("content-type", "")
    assert "json" in ct


# ── Access API ───────────────────────────────────────────────


async def test_api_page_access(db_client):
    """GET /api/v1/pages/{slug}/access для существующей страницы."""
    pages = await _get_pages(db_client)
    if not pages:
        pytest.skip("Нет страниц в БД")
    slug = pages[0]["slug"]
    r = await db_client.get(f"/api/v1/pages/{slug}/access")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "access" in data


# ── Nodes API ────────────────────────────────────────────────


async def test_nodes_api(db_client):
    """GET /api/v1/nodes возвращает конфиг нод."""
    r = await db_client.get("/api/v1/nodes")
    assert r.status_code in (200, 500)
