"""Simple Icons — программный резолвер имён в SVG-иконки.

Загружает индекс simple_icons_index.json (slug → hex) при импорте.
Предоставляет resolve_icon(name) для автоматического маппинга
произвольных имён (claude, btc, telegram) в локальные SVG-иконки.

SVG-файлы раздаются из /static/icons/{slug}.svg (FastAPI StaticFiles).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_ICONS_URL_PREFIX = "/static/icons"

# ── Alias-маппинг: наши доменные термины → Simple Icons slug ──
# Позволяет резолвить "claude" → "claude", "gpt" → пустой (нет в SI),
# "btc" → "bitcoin" и т.д. без знания пользователем точных slug-ов.
_ALIASES: dict[str, str] = {
    # AI модели / компании
    "anthropic": "anthropic",
    "claude": "claude",
    "claude-3": "claude",
    "claude-3.5": "claude",
    "claude-4": "claude",
    "gpt": "openai",
    "gpt-4": "openai",
    "gpt-4o": "openai",
    "chatgpt": "openai",
    "openai": "openai",
    "gemini": "googlegemini",
    "gemini-pro": "googlegemini",
    "google": "google",
    "llama": "meta",
    "llama3": "meta",
    "ollama": "ollama",
    "mistral": "mistralai",
    "deepseek": "deepseek",
    "perplexity": "perplexity",
    "copilot": "githubcopilot",
    "huggingface": "huggingface",
    "hf": "huggingface",
    # Криптовалюты
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "биткоин": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "эфир": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "usdt": "tether",
    "tether": "tether",
    # Платформы
    "tg": "telegram",
    "телеграм": "telegram",
    "telegram": "telegram",
    "yt": "youtube",
    "ютуб": "youtube",
    "youtube": "youtube",
    "gh": "github",
    "github": "github",
}

# ── Имена для отображения (AI модели) ──
_AI_DISPLAY_NAMES: dict[str, str] = {
    "claude": "Claude",
    "anthropic": "Claude",
    "gpt": "GPT",
    "gpt-4": "GPT-4",
    "gpt-4o": "GPT-4o",
    "chatgpt": "ChatGPT",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "gemini-pro": "Gemini Pro",
    "llama": "Llama",
    "llama3": "Llama 3",
    "ollama": "Ollama",
    "mistral": "Mistral",
    "deepseek": "DeepSeek",
    "perplexity": "Perplexity",
    "copilot": "Copilot",
    "huggingface": "HuggingFace",
    "hf": "HuggingFace",
}

# ── Emoji fallback для AI моделей (когда нет иконки или CDN недоступен) ──
_AI_FALLBACK_EMOJI: dict[str, str] = {
    "claude": "🤖",
    "gpt": "🧠",
    "gemini": "✨",
    "llama": "🦙",
    "ollama": "🦙",
    "mistral": "🌬",
    "deepseek": "🔍",
    "perplexity": "🔮",
    "copilot": "👨‍✈️",
}

# Порог яркости для коррекции тёмных цветов
_DARK_LUMINANCE_THRESHOLD = 80

# ── Индекс: slug → hex (загружается из JSON) ──
_SLUG_TO_HEX: dict[str, str] = {}


def _load_index() -> None:
    """Загрузить индекс Simple Icons из JSON при импорте модуля."""
    global _SLUG_TO_HEX
    json_path = Path(__file__).parent / "simple_icons_index.json"
    if not json_path.exists():
        logger.warning("Simple Icons индекс не найден: %s", json_path)
        return
    try:
        with open(json_path, encoding="utf-8") as f:
            _SLUG_TO_HEX = json.load(f)
        logger.info("Simple Icons: загружено %d иконок", len(_SLUG_TO_HEX))
    except Exception as e:
        logger.error("Ошибка загрузки Simple Icons индекса: %s", e)


# Загружаем при импорте
_load_index()


def resolve_icon(name: str) -> dict | None:
    """Резолв произвольного имени в иконку Simple Icons.

    Алгоритм:
    1. Нормализация: lowercase, strip
    2. Поиск в _ALIASES → slug
    3. Если нет алиаса → пробуем имя как slug напрямую
    4. Проверяем slug в _SLUG_TO_HEX (валидация)
    5. Если найден → локальный URL + brand hex
    6. Если нет → None (вызывающий код использует emoji fallback)

    Returns:
        {"slug", "hex", "color", "icon_url"} или None
    """
    if not name:
        return None

    normalized = name.lower().strip()

    # Убираем префиксы типа "ai:" если есть
    for prefix in ("ai:", "admin:", "user:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    # 1. Ищем в alias-маппинге (точное совпадение)
    slug = _ALIASES.get(normalized)

    # 2. Keyword matching: проверяем, содержит ли имя ключ из алиасов
    # Это позволяет резолвить "claude-opus-4-6" через ключ "claude"
    if not slug:
        for alias_key, alias_slug in _ALIASES.items():
            if alias_key in normalized:
                slug = alias_slug
                break

    # 3. Если нет алиаса, пробуем имя напрямую как slug
    if not slug:
        # Нормализуем: убираем пробелы, дефисы, подчёркивания
        candidate = normalized.replace(" ", "").replace("-", "").replace("_", "")
        if candidate in _SLUG_TO_HEX:
            slug = candidate
        elif normalized in _SLUG_TO_HEX:
            slug = normalized

    if not slug:
        return None

    # 3. Проверяем что slug валидный
    hex_color = _SLUG_TO_HEX.get(slug)
    if not hex_color:
        return None

    return {
        "slug": slug,
        "hex": hex_color,
        "color": f"#{hex_color}",
        "icon_url": f"{_ICONS_URL_PREFIX}/{slug}.svg",
    }


def get_display_name(model_name: str) -> str:
    """Получить человекочитаемое имя AI модели."""
    normalized = model_name.lower().strip()
    # Точное совпадение
    name = _AI_DISPLAY_NAMES.get(normalized)
    if name:
        return name
    # Keyword matching: "claude-opus-4-6" → "Claude"
    for key, display_name in _AI_DISPLAY_NAMES.items():
        if key in normalized:
            return display_name
    # Fallback: capitalize last part after /
    return normalized.split("/")[-1].capitalize()


def get_fallback_emoji(model_name: str) -> str:
    """Получить emoji fallback для AI модели."""
    normalized = model_name.lower().strip()
    emoji = _AI_FALLBACK_EMOJI.get(normalized)
    if emoji:
        return emoji
    # Keyword matching
    for key, fallback_emoji in _AI_FALLBACK_EMOJI.items():
        if key in normalized:
            return fallback_emoji
    return "🤖"


def adjusted_color(hex_color: str) -> str:
    """Корректирует слишком тёмные брендовые цвета для видимости.

    В Telegram Mini App фон карточки может быть тёмным.
    Слишком тёмные цвета (Anthropic #191919, Ollama #000000)
    осветляются для видимости кружка аватарки.
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return hex_color

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Яркость по формуле ITU-R BT.601
    luminance = 0.299 * r + 0.587 * g + 0.114 * b

    if luminance < _DARK_LUMINANCE_THRESHOLD:
        # Осветляем на 40% к белому
        r = r + int((255 - r) * 0.4)
        g = g + int((255 - g) * 0.4)
        b = b + int((255 - b) * 0.4)
        return f"{r:02x}{g:02x}{b:02x}"

    return hex_color


def get_icon_count() -> int:
    """Количество доступных иконок в индексе."""
    return len(_SLUG_TO_HEX)


def get_all_aliases() -> dict[str, str]:
    """Все зарегистрированные алиасы (копия для API)."""
    return dict(_ALIASES)
