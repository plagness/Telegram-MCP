"""Handler'ы для простых типов страниц без proxy-маршрутов.

Типы: page, prediction, survey, dashboard, leaderboard.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import Request

from ..config import get_settings
from . import PageTypeHandler

logger = logging.getLogger(__name__)
settings = get_settings()


class PageHandler(PageTypeHandler):
    """Статическая страница (контент + кнопки)."""

    page_type = "page"
    template = "page.html"


class PredictionHandler(PageTypeHandler):
    """Страница предсказания (ставки, опции)."""

    page_type = "prediction"
    template = "prediction.html"

    async def load_data(
        self, page: dict, user: dict | None, request: Request
    ) -> dict[str, Any]:
        event_data: dict[str, Any] = {}
        if page.get("event_id"):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(
                        f"{settings.tgapi_url}/v1/predictions/events/{page['event_id']}"
                    )
                    if r.status_code == 200:
                        event_data = r.json().get("event", {})
            except Exception as e:
                logger.warning("Не удалось загрузить данные события: %s", e)
        return {"event": event_data}


class SurveyHandler(PageTypeHandler):
    """Опрос / веб-форма."""

    page_type = "survey"
    template = "survey.html"


class DashboardHandler(PageTypeHandler):
    """Дашборд с метриками."""

    page_type = "dashboard"
    template = "dashboard.html"
    scripts = ["echarts"]


class LeaderboardHandler(PageTypeHandler):
    """Рейтинг пользователей."""

    page_type = "leaderboard"
    template = "leaderboard.html"
