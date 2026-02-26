"""
Общие утилиты для Telegram FastMCP субмодулей.
"""

import os
import re
import logging

import httpx
from fastmcp import FastMCP

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:30081")

# Паттерн для очистки operationId от FastAPI суффиксов
# "send_message_api_v1_messages_send_post" → "send_message"
STRIP_PATTERN = re.compile(r"_api_v1_.*$|_v1_.*$")


def clean_operation_ids(spec: dict) -> dict:
    """Убрать суффиксы _api_v1_* из operationId."""
    seen: set[str] = set()
    for _path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method in ("parameters",) or not isinstance(details, dict):
                continue
            oid = details.get("operationId", "")
            if not oid:
                continue
            clean = STRIP_PATTERN.sub("", oid)
            if clean in seen:
                clean = f"{clean}_{method}"
            seen.add(clean)
            details["operationId"] = clean
    return spec


def create_openapi_mcp(
    name: str,
    route_prefixes: list[str],
    backend_url: str | None = None,
) -> FastMCP:
    """Создать FastMCP сервер из OpenAPI spec с фильтрацией роутов.

    Args:
        name: Имя MCP сервера (например "tg-chat")
        route_prefixes: Список префиксов путей (например ["/v1/messages", "/v1/chats"])
        backend_url: URL бэкенда (по умолчанию из BACKEND_URL env)
    """
    url = backend_url or BACKEND_URL
    log = logging.getLogger(name)

    log.info(f"Loading OpenAPI spec from {url}/openapi.json")
    spec = httpx.get(f"{url}/openapi.json", timeout=15).json()

    # Фильтрация путей
    filtered = {}
    for path, methods in spec.get("paths", {}).items():
        if any(path.startswith(p) for p in route_prefixes):
            filtered[path] = methods
    spec["paths"] = filtered
    log.info(f"Filtered to {len(filtered)} paths for {name}")

    # Чистка operationId
    spec = clean_operation_ids(spec)

    client = httpx.AsyncClient(base_url=url, timeout=30.0)
    mcp = FastMCP.from_openapi(openapi_spec=spec, client=client, name=name)
    log.info(f"Created {name} FastMCP server")
    return mcp
