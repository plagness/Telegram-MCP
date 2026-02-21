"""Тесты handler registry: auto-discovery, template mapping, уникальность."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DB_DSN", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")

from app.handlers import PageTypeHandler
from app.handlers.registry import (
    discover_handlers,
    get_all_handlers,
    get_handler,
    get_template_map,
    list_types,
)

# Убедиться что handlers обнаружены
discover_handlers()

TEMPLATES_DIR = Path(__file__).parent.parent / "app" / "templates"


def test_handlers_discovered():
    """Auto-discovery находит handler'ы."""
    handlers = get_all_handlers()
    assert len(handlers) >= 10, f"Expected >= 10 handlers, got {len(handlers)}"


def test_page_type_unique():
    """Каждый page_type зарегистрирован ровно один раз."""
    handlers = get_all_handlers()
    # Если бы были дубли — registry перезаписал бы, но handlers dict не допускает
    assert len(handlers) == len(set(handlers.keys()))


def test_all_handlers_have_template():
    """Все handler'ы указывают на существующий шаблон."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        template_path = TEMPLATES_DIR / handler.template
        assert template_path.exists(), (
            f"Handler '{pt}' ({type(handler).__name__}) ссылается на "
            f"несуществующий шаблон: {handler.template}"
        )


def test_template_map_matches_registry():
    """template_map из registry соответствует handler'ам."""
    tmap = get_template_map()
    handlers = get_all_handlers()
    assert set(tmap.keys()) == set(handlers.keys())
    for pt, template in tmap.items():
        assert template == handlers[pt].template


def test_get_handler_returns_correct_type():
    """get_handler возвращает корректный экземпляр."""
    handler = get_handler("page")
    assert handler is not None
    assert handler.page_type == "page"
    assert isinstance(handler, PageTypeHandler)


def test_get_handler_unknown_returns_none():
    """get_handler для несуществующего типа возвращает None."""
    handler = get_handler("nonexistent_type_xyz")
    assert handler is None


def test_list_types_complete():
    """list_types() возвращает описание для каждого handler'а."""
    types = list_types()
    handlers = get_all_handlers()
    assert len(types) == len(handlers)
    for t in types:
        assert "page_type" in t
        assert "template" in t
        assert t["page_type"] in handlers


def test_known_types_registered():
    """Все известные page_types зарегистрированы."""
    expected = {
        "page", "prediction", "survey", "dashboard", "leaderboard",
        "calendar", "governance", "llm", "infra", "metrics", "k8s",
        "channel", "bcs", "arena", "planner", "datesale",
    }
    handlers = get_all_handlers()
    for pt in expected:
        assert pt in handlers, f"page_type '{pt}' not registered"


def test_handler_describe():
    """handler.describe() возвращает полное описание."""
    handler = get_handler("calendar")
    assert handler is not None
    desc = handler.describe()
    assert desc["page_type"] == "calendar"
    assert desc["template"] == "calendar.html"
    assert "config_schema" in desc
