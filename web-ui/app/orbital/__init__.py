"""Orbital Emoji — модуль орбитальной визуализации.

Определяет маппинг эмодзи по ролям (star, orbit1, orbit2, star2)
и вычисляет data-driven параметры анимации из метаданных карточки.
"""

from .config import OrbitalConfig, compute_orbital
from .templates import ORBITAL_TEMPLATES, get_emoji_template

__all__ = [
    "OrbitalConfig",
    "compute_orbital",
    "ORBITAL_TEMPLATES",
    "get_emoji_template",
]
