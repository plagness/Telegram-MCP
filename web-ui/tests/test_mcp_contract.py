"""MCP Tools Contract Tests: проверяем контракт всех page_type handlers.

Каждый handler должен:
- Иметь непустой page_type
- Указывать на существующий template
- Возвращать валидный JSON Schema из get_config_schema()
- describe() содержит все обязательные поля
- validate_layout() возвращает list[str]
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("DB_DSN", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")

from app.handlers import PageTypeHandler
from app.handlers.registry import discover_handlers, get_all_handlers

discover_handlers()

TEMPLATES_DIR = Path(__file__).parent.parent / "app" / "templates"


# ── Контрактные тесты для всех handlers ──


def test_all_handlers_have_page_type():
    """Все handlers имеют непустой page_type."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        assert handler.page_type, f"Handler {type(handler).__name__} has empty page_type"
        assert handler.page_type == pt, (
            f"Handler key '{pt}' != handler.page_type '{handler.page_type}'"
        )


def test_all_handlers_have_template_file():
    """Все handlers указывают на существующий Jinja2 шаблон."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        assert handler.template, f"Handler '{pt}' has empty template"
        template_path = TEMPLATES_DIR / handler.template
        assert template_path.exists(), (
            f"Handler '{pt}' template '{handler.template}' not found at {template_path}"
        )


def test_all_handlers_config_schema_is_valid_json_schema():
    """get_config_schema() возвращает валидный JSON Schema (минимум type: object)."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        schema = handler.get_config_schema()
        assert isinstance(schema, dict), (
            f"Handler '{pt}' config_schema is {type(schema)}, expected dict"
        )
        assert "type" in schema, (
            f"Handler '{pt}' config_schema missing 'type' key"
        )
        # Schema должна сериализоваться в JSON
        try:
            json.dumps(schema)
        except (TypeError, ValueError) as e:
            raise AssertionError(
                f"Handler '{pt}' config_schema is not JSON-serializable: {e}"
            )


def test_all_handlers_describe_contract():
    """describe() возвращает dict с обязательными полями."""
    required_keys = {"page_type", "template", "scripts", "config_schema"}
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        desc = handler.describe()
        assert isinstance(desc, dict), (
            f"Handler '{pt}' describe() returned {type(desc)}"
        )
        missing = required_keys - set(desc.keys())
        assert not missing, (
            f"Handler '{pt}' describe() missing keys: {missing}"
        )
        assert isinstance(desc["scripts"], list), (
            f"Handler '{pt}' scripts is {type(desc['scripts'])}, expected list"
        )


def test_all_handlers_scripts_are_strings():
    """scripts — список строк (JS-библиотеки для загрузки)."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        for script in handler.scripts:
            assert isinstance(script, str), (
                f"Handler '{pt}' has non-string script: {script!r}"
            )


def test_all_handlers_subclass_base():
    """Все handler'ы — подклассы PageTypeHandler."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        assert isinstance(handler, PageTypeHandler), (
            f"Handler '{pt}' ({type(handler).__name__}) is not a PageTypeHandler subclass"
        )


def test_all_handlers_validate_layout_returns_list():
    """validate_layout() всегда возвращает list[str]."""
    handlers = get_all_handlers()
    test_configs = [
        {},
        {"layout": {}},
        {"layout": {"profile_buttons": {}, "banner": {}, "content": {}}},
        {"random_key": 42},
    ]
    for pt, handler in handlers.items():
        for config in test_configs:
            result = handler.validate_layout(config)
            assert isinstance(result, list), (
                f"Handler '{pt}'.validate_layout({config}) returned {type(result)}"
            )
            for item in result:
                assert isinstance(item, str), (
                    f"Handler '{pt}' validate_layout error is not str: {item!r}"
                )


def test_handler_count_minimum():
    """В системе зарегистрировано минимум 15 page_types."""
    handlers = get_all_handlers()
    assert len(handlers) >= 15, (
        f"Expected >= 15 handlers, got {len(handlers)}: {list(handlers.keys())}"
    )


def test_core_page_types_exist():
    """Основные page_types существуют."""
    handlers = get_all_handlers()
    core_types = [
        "page", "prediction", "survey", "dashboard", "leaderboard",
        "calendar", "governance",
    ]
    for pt in core_types:
        assert pt in handlers, f"Core page_type '{pt}' not registered"


def test_module_page_types_exist():
    """Page types для модулей NeuronSwarm существуют."""
    handlers = get_all_handlers()
    module_types = ["llm", "infra", "channel", "bcs", "arena", "planner", "datesale"]
    for pt in module_types:
        assert pt in handlers, f"Module page_type '{pt}' not registered"


def test_describe_serializable():
    """describe() каждого handler'а полностью сериализуема в JSON."""
    handlers = get_all_handlers()
    for pt, handler in handlers.items():
        desc = handler.describe()
        try:
            json.dumps(desc)
        except (TypeError, ValueError) as e:
            raise AssertionError(
                f"Handler '{pt}' describe() not JSON-serializable: {e}"
            )
