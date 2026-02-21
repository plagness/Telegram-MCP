"""Pytest fixtures для web-ui тестов."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

# Фейковые env vars для unit-тестов (до импорта приложения)
os.environ.setdefault("DB_DSN", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")


def _db_reachable() -> bool:
    """Проверка что БД доступна (синхронно, для маркировки тестов)."""
    try:
        import socket

        dsn = os.environ.get("DB_DSN", "")
        host, port = "localhost", 5432
        if "@" in dsn and "/" in dsn.split("@")[-1]:
            addr = dsn.split("@")[-1].split("/")[0]
            parts = addr.rsplit(":", 1)
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 5432
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


_HAS_DB = _db_reachable()


def pytest_collection_modifyitems(config, items):
    """Пропустить integration-тесты если БД недоступна."""
    if _HAS_DB:
        return
    skip = pytest.mark.skip(reason="БД недоступна (integration tests)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def app():
    """FastAPI application instance."""
    from app.main import app as _app
    return _app


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client для тестирования FastAPI (без БД)."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_client(app):
    """Async HTTP client с инициализированным DB pool (для интеграционных тестов)."""
    from httpx import ASGITransport, AsyncClient

    from app.db import close_pool, init_pool

    await init_pool()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await close_pool()
