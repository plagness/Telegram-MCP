"""Smoke-тесты: базовая проверка что приложение стартует и маршруты отвечают."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_DSN", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")


def test_app_import():
    """Приложение импортируется без ошибок."""
    from app.main import app
    assert app is not None
    assert app.title == "telegram-mcp web-ui"


def test_handlers_registered():
    """Handler registry заполнен при импорте app."""
    from app.handlers.registry import get_all_handlers
    handlers = get_all_handlers()
    assert len(handlers) >= 10


def test_routes_exist():
    """Основные маршруты зарегистрированы."""
    from app.main import app

    paths = {r.path for r in app.routes if hasattr(r, "path")}

    # Рендер-маршруты
    assert "/" in paths
    assert "/profile" in paths
    assert "/p/{slug}" in paths
    assert "/l/{token}" in paths
    assert "/marketplace" in paths
    assert "/developer" in paths

    # API маршруты
    assert "/api/v1/pages" in paths
    assert "/api/v1/pages/types" in paths
    assert "/api/v1/pages/validate" in paths
    assert "/api/v1/pages/{slug}/access" in paths
    assert "/api/v1/banners" in paths

    # Health API маршруты
    assert "/api/v1/pages/health" in paths
    assert "/api/v1/pages/health/check" in paths
    assert "/api/v1/pages/{slug}/health" in paths

    # Handler proxy маршруты
    assert "/p/{slug}/calendar/entries" in paths
    assert "/p/{slug}/governance/data" in paths


def test_api_types_endpoint():
    """GET /api/v1/pages/types работает без БД (синхронный тест)."""
    from app.handlers.registry import list_types
    types = list_types()
    assert isinstance(types, list)
    assert len(types) >= 10
    page_types = {t["page_type"] for t in types}
    assert "page" in page_types
    assert "calendar" in page_types
    assert "governance" in page_types
