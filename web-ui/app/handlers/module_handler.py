"""Handler'ы для модулей, чьи proxy-маршруты уже в module_proxy.py.

Типы: channel, bcs, arena, planner.
Эти handler'ы только определяют шаблон — proxy-маршруты остаются
в module_proxy.py (уже вынесены ранее).
"""

from __future__ import annotations

from . import PageTypeHandler


class ChannelHandler(PageTypeHandler):
    """Integrat плагин Channel."""

    page_type = "channel"
    template = "channel.html"


class BCSHandler(PageTypeHandler):
    """Trading/BCS маркетплейс."""

    page_type = "bcs"
    template = "bcs.html"
    scripts = ["echarts"]


class ArenaHandler(PageTypeHandler):
    """Arena LLM."""

    page_type = "arena"
    template = "arena.html"
    scripts = ["echarts"]


class PlannerHandler(PageTypeHandler):
    """Планер задач."""

    page_type = "planner"
    template = "planner.html"
