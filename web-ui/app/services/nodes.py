"""Сервис реестра публичных нод (VDS, K3s).

Загружает конфигурацию из JSON-файла (ConfigMap в K8s, локальный файл в Docker Compose).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config import get_settings

logger = logging.getLogger(__name__)

# Кэш (загружается один раз при первом запросе)
_nodes_cache: dict[str, Any] | None = None


def _load_nodes() -> dict[str, Any]:
    """Загрузить реестр нод из файла."""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache

    settings = get_settings()
    config_path = Path(settings.nodes_config_path)

    if not config_path.exists():
        logger.warning("Файл реестра нод не найден: %s", config_path)
        _nodes_cache = {"nodes": [], "routes": []}
        return _nodes_cache

    try:
        with open(config_path) as f:
            _nodes_cache = json.load(f)
        logger.info("Загружен реестр нод: %d нод, %d маршрутов",
                     len(_nodes_cache.get("nodes", [])),
                     len(_nodes_cache.get("routes", [])))
    except Exception as e:
        logger.error("Ошибка загрузки реестра нод: %s", e)
        _nodes_cache = {"nodes": [], "routes": []}

    return _nodes_cache


def get_nodes() -> list[dict[str, Any]]:
    """Список всех нод."""
    data = _load_nodes()
    return data.get("nodes", [])


def get_active_nodes() -> list[dict[str, Any]]:
    """Список активных нод."""
    return [n for n in get_nodes() if n.get("active")]


def get_routes() -> list[dict[str, Any]]:
    """Список маршрутов (прокси-правил)."""
    data = _load_nodes()
    return data.get("routes", [])


def get_node_by_name(name: str) -> dict[str, Any] | None:
    """Найти ноду по имени."""
    for node in get_nodes():
        if node.get("name") == name:
            return node
    return None


def get_full_config() -> dict[str, Any]:
    """Полный конфиг нод + маршруты."""
    return _load_nodes()


def reload_config() -> None:
    """Сбросить кэш (перечитать файл при следующем запросе)."""
    global _nodes_cache
    _nodes_cache = None
