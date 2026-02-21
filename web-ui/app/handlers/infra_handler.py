"""Handler'ы для инфраструктурных страниц — proxy к llmcore/metricsapi."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from ..config import get_settings
from . import PageTypeHandler, proxy_get, validate_page_request

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMHandler(PageTypeHandler):
    """LLM инфраструктура + smart routing."""

    page_type = "llm"
    template = "llm.html"
    scripts = ["echarts"]

    def register_routes(self, router: APIRouter) -> None:
        @router.get("/p/{slug}/llm/data")
        async def llm_data_proxy(slug: str, request: Request):
            """Данные LLM dashboard из llmcore."""
            await validate_page_request(slug, "llm", request)
            return await proxy_get(f"{settings.llm_core_url}/v1/dashboard")


class InfraHandler(PageTypeHandler):
    """K8s + Ollama инфраструктура."""

    page_type = "infra"
    template = "infra.html"
    scripts = ["echarts"]

    def register_routes(self, router: APIRouter) -> None:
        @router.get("/p/{slug}/infra/data")
        async def infra_data_proxy(slug: str, request: Request):
            """Данные LLM-инфраструктуры (с проверкой доступа)."""
            await validate_page_request(slug, "infra", request)
            return await proxy_get(f"{settings.llm_core_url}/v1/dashboard")


class MetricsHandler(PageTypeHandler):
    """Метрики системы."""

    page_type = "metrics"
    template = "metrics.html"
    scripts = ["echarts"]


class K8sHandler(PageTypeHandler):
    """K8s кластер + Portainer."""

    page_type = "k8s"
    template = "k8s.html"
    scripts = ["echarts"]


class DatesaleHandler(PageTypeHandler):
    """Datesale маркетплейс."""

    page_type = "datesale"
    template = "datesale.html"
