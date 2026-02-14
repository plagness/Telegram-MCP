"""Вычисление data-driven параметров орбитальной анимации.

OrbitalConfig генерируется для каждой карточки Hub на основе метаданных:
  activity   → скорость орбит (0.0–1.0)
  urgency    → яркость свечения (0.0–1.0)
  star_scale → размер звезды (1.0–1.3)
  glow_color → цвет шлейфа (rgba строка)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .templates import get_emoji_template

# Цвета свечения по типу карточки (шаблон с {a} для alpha)
GLOW_COLORS: dict[str, str] = {
    "prediction":  "rgba(255, 152, 0, {a})",
    "calendar":    "rgba(255, 87, 34, {a})",
    "survey":      "rgba(76, 175, 80, {a})",
    "dashboard":   "rgba(156, 39, 176, {a})",
    "leaderboard": "rgba(255, 193, 7, {a})",
    "llm":         "rgba(103, 58, 183, {a})",
    "infra":       "rgba(96, 125, 139, {a})",
    "page":        "rgba(158, 158, 158, {a})",
}


@dataclass
class OrbitalConfig:
    """Конфигурация орбитальной анимации для одной карточки."""

    emojis: dict[str, str] = field(default_factory=dict)
    is_binary: bool = False
    activity: float = 0.1
    urgency: float = 0.0
    glow_color: str = "rgba(158, 158, 158, 0.35)"
    star_scale: float = 1.0
    orbit_phase: int = 0
    chat_photo_url: str = ""


def _calc_activity(meta: dict) -> float:
    """Уровень активности карточки (0.0–1.0). Влияет на скорость орбит."""
    pool = meta.get("total_pool") or 0
    bets = meta.get("bet_count") or 0
    subs = meta.get("submission_count") or 0
    entries = meta.get("entry_count") or 0
    popularity = bets or subs or entries

    # popularity: 0→0, 5→0.17, 15→0.5, 30+→1.0
    pop_score = min(popularity / 30, 1.0)
    # pool: 0→0, 500→0.25, 2000+→1.0
    pool_score = min(pool / 2000, 1.0)

    return round(min((pop_score + pool_score) / 2 + 0.1, 1.0), 2)


def _calc_urgency(meta: dict) -> float:
    """Уровень срочности (0.0–1.0). Влияет на яркость свечения."""
    deadline = meta.get("deadline")
    if not deadline:
        return 0.0

    if isinstance(deadline, str):
        try:
            dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return 0.0
    elif isinstance(deadline, datetime):
        dt = deadline
    else:
        return 0.0

    now = datetime.now(timezone.utc)
    remaining = (dt - now).total_seconds()

    if remaining <= 0:
        return 0.0
    if remaining < 3600:       # < 1ч
        return 1.0
    if remaining < 86400:      # < 24ч
        return round(0.3 + 0.7 * (1 - remaining / 86400), 2)
    return 0.1


def _calc_star_scale(meta: dict) -> float:
    """Масштаб звезды (1.0–1.3). Популярные/весомые карточки крупнее."""
    pool = meta.get("total_pool") or 0
    bets = meta.get("bet_count") or 0
    popularity = bets or meta.get("submission_count") or 0

    raw = pool / 5000 + popularity / 50
    return round(min(1.0 + raw * 0.15, 1.3), 2)


def _calc_glow_color(page_type: str, urgency: float) -> str:
    """Цвет свечения (rgba) с alpha зависящей от urgency."""
    template = GLOW_COLORS.get(page_type, GLOW_COLORS["page"])
    alpha = round(0.35 + urgency * 0.4, 2)
    return template.format(a=alpha)


def compute_orbital(
    page_type: str,
    meta: dict,
    index: int = 0,
    config: dict | None = None,
    chat_photo_url: str = "",
) -> OrbitalConfig:
    """Вычислить полную орбитальную конфигурацию для карточки.

    Args:
        page_type: Тип страницы (prediction, calendar, survey, ...)
        meta: Метаданные карточки (_meta dict из enrich_pages_for_hub)
        index: Порядковый номер карточки (для десинхронизации фаз)
        config: page.config JSONB (содержит emojis от LLM/админки)
        chat_photo_url: URL аватарки чата (если есть)

    Returns:
        OrbitalConfig с эмодзи, параметрами анимации и CSS-переменными.
    """
    status = meta.get("status") or ""
    emojis = get_emoji_template(page_type, status, meta)

    # Override: LLM-сгенерированные или ручные эмодзи из config
    config_emojis = (config or {}).get("emojis")
    if config_emojis:
        emojis.update(config_emojis)

    activity = _calc_activity(meta)
    urgency = _calc_urgency(meta)
    star_scale = _calc_star_scale(meta)
    glow_color = _calc_glow_color(page_type, urgency)

    return OrbitalConfig(
        emojis=emojis,
        is_binary="star2" in emojis,
        activity=activity,
        urgency=urgency,
        glow_color=glow_color,
        star_scale=star_scale,
        orbit_phase=index,
        chat_photo_url=chat_photo_url,
    )
