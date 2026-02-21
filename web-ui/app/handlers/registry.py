"""Реестр handler'ов: auto-discovery и lookup.

При старте приложения discover_handlers() импортирует все модули
из handlers/, находит подклассы PageTypeHandler и регистрирует их.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

from . import PageTypeHandler

logger = logging.getLogger(__name__)

# Глобальный реестр: page_type → экземпляр handler'а
_registry: dict[str, PageTypeHandler] = {}


def discover_handlers() -> dict[str, PageTypeHandler]:
    """Импортировать все модули из handlers/, зарегистрировать handler'ы.

    Ищет все подклассы PageTypeHandler с непустым page_type.
    Если handler обслуживает несколько page_type — регистрирует каждый.
    """
    import app.handlers as handlers_pkg

    for _importer, modname, _ispkg in pkgutil.iter_modules(handlers_pkg.__path__):
        if modname.startswith("_") or modname == "registry":
            continue
        try:
            importlib.import_module(f"app.handlers.{modname}")
        except Exception:
            logger.exception("Не удалось загрузить handler-модуль: %s", modname)

    # Рекурсивный обход подклассов PageTypeHandler
    for cls in _all_subclasses(PageTypeHandler):
        if not cls.page_type:
            continue
        handler = cls()
        _register(handler)

    logger.info(
        "Handler registry: %d типов зарегистрировано: %s",
        len(_registry),
        ", ".join(sorted(_registry)),
    )
    return _registry


def _all_subclasses(cls: type) -> set[type]:
    """Все подклассы (рекурсивно)."""
    result = set()
    for sub in cls.__subclasses__():
        result.add(sub)
        result.update(_all_subclasses(sub))
    return result


def _register(handler: PageTypeHandler) -> None:
    """Зарегистрировать один handler."""
    pt = handler.page_type
    if pt in _registry:
        logger.warning(
            "Handler для page_type '%s' уже зарегистрирован (%s), перезаписываем на %s",
            pt,
            type(_registry[pt]).__name__,
            type(handler).__name__,
        )
    _registry[pt] = handler


def get_handler(page_type: str) -> PageTypeHandler | None:
    """Получить handler по page_type. None если не найден."""
    return _registry.get(page_type)


def get_template_map() -> dict[str, str]:
    """Сгенерировать template_map из реестра: {page_type: template_name}."""
    return {pt: h.template for pt, h in _registry.items()}


def get_all_handlers() -> dict[str, PageTypeHandler]:
    """Все зарегистрированные handler'ы."""
    return dict(_registry)


def register_all_routes(router: APIRouter) -> None:
    """Вызвать register_routes() для всех handler'ов."""
    for pt, handler in _registry.items():
        try:
            handler.register_routes(router)
        except Exception:
            logger.exception("Ошибка регистрации маршрутов для handler '%s'", pt)


def list_types() -> list[dict]:
    """Список типов для API /pages/types."""
    return [h.describe() for h in _registry.values()]
