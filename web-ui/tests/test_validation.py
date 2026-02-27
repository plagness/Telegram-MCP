"""Тесты validate_layout(): 3-tier layout validation для Mini App страниц.

3-tier структура: profile_buttons → banner → content.
Базовый handler не требует layout (обратная совместимость).
Подклассы могут переопределять validate_layout() для строгих проверок.
"""

from __future__ import annotations

import os

os.environ.setdefault("DB_DSN", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")

from app.handlers import PageTypeHandler
from app.handlers.registry import discover_handlers, get_handler

# Убедиться что handlers обнаружены
discover_handlers()


# ── Базовый validate_layout (всегда пусто для обратной совместимости) ──


def test_base_handler_validate_layout_returns_empty():
    """Базовый PageTypeHandler.validate_layout() не возвращает ошибок."""
    handler = PageTypeHandler()
    assert handler.validate_layout({}) == []
    assert handler.validate_layout({"layout": {}}) == []
    assert handler.validate_layout({"anything": "value"}) == []


def test_base_handler_validate_layout_with_valid_3tier():
    """Базовый handler пропускает полный layout без ошибок."""
    config = {
        "layout": {
            "profile_buttons": {"buttons": [{"label": "Share"}]},
            "banner": {"image": "/img/banner.png"},
            "content": {"blocks": [{"type": "text", "text": "Hello"}]},
        }
    }
    handler = PageTypeHandler()
    assert handler.validate_layout(config) == []


# ── Кастомный handler с strict 3-tier validation ──


class Strict3TierHandler(PageTypeHandler):
    """Handler с обязательной 3-tier структурой (для теста)."""

    page_type = "test_strict_3tier"
    template = "page.html"

    def validate_layout(self, config: dict) -> list[str]:
        errors = []
        layout = config.get("layout")
        if layout is None or not isinstance(layout, dict):
            errors.append("config.layout is required")
            return errors

        required_tiers = ["profile_buttons", "banner", "content"]
        for tier in required_tiers:
            if tier not in layout:
                errors.append(f"Missing required tier: {tier}")

        return errors


def test_strict_handler_missing_layout():
    """Strict handler требует config.layout."""
    handler = Strict3TierHandler()
    errors = handler.validate_layout({})
    assert len(errors) == 1
    assert "config.layout is required" in errors[0]


def test_strict_handler_empty_layout():
    """Strict handler ловит пустой layout — все 3 тира отсутствуют."""
    handler = Strict3TierHandler()
    errors = handler.validate_layout({"layout": {}})
    assert len(errors) == 3
    assert any("profile_buttons" in e for e in errors)
    assert any("banner" in e for e in errors)
    assert any("content" in e for e in errors)


def test_strict_handler_layout_missing_tiers():
    """Strict handler проверяет каждый тир если layout не пуст."""
    handler = Strict3TierHandler()
    errors = handler.validate_layout({"layout": {"extra": True}})
    assert len(errors) == 3
    assert any("profile_buttons" in e for e in errors)
    assert any("banner" in e for e in errors)
    assert any("content" in e for e in errors)


def test_strict_handler_partial_layout():
    """Strict handler ловит отсутствующие тиры."""
    handler = Strict3TierHandler()
    errors = handler.validate_layout({
        "layout": {
            "profile_buttons": {},
            "content": {},
        }
    })
    assert len(errors) == 1
    assert "banner" in errors[0]


def test_strict_handler_valid_layout():
    """Strict handler пропускает полный layout."""
    handler = Strict3TierHandler()
    errors = handler.validate_layout({
        "layout": {
            "profile_buttons": {"buttons": []},
            "banner": {"image": "test.png"},
            "content": {"blocks": []},
        }
    })
    assert errors == []


# ── Все зарегистрированные handlers — validate_layout не ломается ──


def test_all_registered_handlers_validate_layout_exists():
    """Все зарегистрированные handlers имеют метод validate_layout()."""
    from app.handlers.registry import get_all_handlers

    handlers = get_all_handlers()
    assert len(handlers) >= 10

    for pt, handler in handlers.items():
        assert hasattr(handler, "validate_layout"), (
            f"Handler '{pt}' не имеет validate_layout()"
        )
        # Вызов с пустым config не должен падать
        result = handler.validate_layout({})
        assert isinstance(result, list), (
            f"Handler '{pt}'.validate_layout({{}}) вернул {type(result)}, ожидался list"
        )


def test_all_handlers_validate_layout_accepts_full_config():
    """validate_layout() принимает config с layout без ошибок."""
    from app.handlers.registry import get_all_handlers

    config = {
        "layout": {
            "profile_buttons": {"buttons": [{"label": "Test"}]},
            "banner": {"image": "/img/test.png"},
            "content": {"blocks": [{"type": "text", "text": "Hello"}]},
        }
    }
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        result = handler.validate_layout(config)
        assert isinstance(result, list), (
            f"Handler '{pt}'.validate_layout() вернул {type(result)}"
        )
