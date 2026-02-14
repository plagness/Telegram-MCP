"""Шаблоны эмодзи для орбитальной системы визуальных панелей.

Маппинг (page_type, status) → набор ролей:
  star   — ядро/звезда (всегда есть)
  star2  — бинарный партнёр (два объекта вращаются друг вокруг друга)
  orbit1 — планета (внутреннее кольцо)
  orbit2 — спутник (среднее кольцо)
  orbit3 — 2-й на среднем кольце (+180° сдвиг)
  orbit4 — 1-й на внешнем кольце
"""

from __future__ import annotations

# (page_type, status) → dict ролей
# Порядок lookup: точное совпадение → (type, "") как fallback
ORBITAL_TEMPLATES: dict[tuple[str, str], dict[str, str]] = {
    # ── Prediction ──
    ("prediction", "open"):      {"star": "🎯", "orbit1": "🔥", "orbit2": "💰", "orbit3": "📊", "orbit4": "⚡"},
    ("prediction", "active"):    {"star": "🎯", "orbit1": "🔥", "orbit2": "💰", "orbit3": "📊", "orbit4": "⚡"},
    ("prediction", "resolved"):  {"star": "🏆", "star2": "✨", "orbit1": "✨", "orbit2": "🎉"},
    ("prediction", "cancelled"): {"star": "🚫"},
    ("prediction", ""):          {"star": "🎯", "orbit1": "💭"},

    # ── Calendar ──
    ("calendar", "events"):      {"star": "📅", "orbit1": "⏰", "orbit2": "📌", "orbit3": "🔔", "orbit4": "👥"},
    ("calendar", ""):            {"star": "📅", "orbit1": "🏁", "orbit2": "📋"},

    # ── Survey ──
    ("survey", "submitted"):     {"star": "📝", "orbit1": "✅", "orbit2": "📊"},
    ("survey", ""):              {"star": "📝", "orbit1": "✏️", "orbit2": "📋", "orbit3": "💬"},

    # ── Dashboard ──
    ("dashboard", ""):           {"star": "📊", "orbit1": "📈", "orbit2": "🔍", "orbit3": "⚙️"},

    # ── Leaderboard ──
    ("leaderboard", ""):         {"star": "🏆", "star2": "🥇", "orbit1": "⭐", "orbit2": "🔥"},

    # ── LLM ──
    ("llm", ""):                 {"star": "🤖", "orbit1": "🧠", "orbit2": "💡", "orbit3": "⚡"},

    # ── Infra ──
    ("infra", ""):               {"star": "🖥️", "orbit1": "⚙️", "orbit2": "📡", "orbit3": "🔧"},

    # ── Page (fallback) ──
    ("page", ""):                {"star": "📄", "orbit1": "✨"},
}


def get_emoji_template(page_type: str, status: str, meta: dict | None = None) -> dict[str, str]:
    """Получить шаблон эмодзи для типа/статуса.

    Логика lookup:
    1. Точное совпадение (page_type, status)
    2. Для calendar: (calendar, "events") если есть next_entry в meta
    3. Для survey: (survey, "submitted") если user_submitted в meta
    4. Fallback: (page_type, "")
    5. Финальный fallback: (page, "")
    """
    meta = meta or {}

    # Специальная логика для calendar: status определяется наличием next_entry
    if page_type == "calendar":
        effective_status = "events" if meta.get("next_entry") else ""
        key = (page_type, effective_status)
        if key in ORBITAL_TEMPLATES:
            return dict(ORBITAL_TEMPLATES[key])

    # Специальная логика для survey: status определяется user_submitted
    if page_type == "survey":
        effective_status = "submitted" if meta.get("user_submitted") else ""
        key = (page_type, effective_status)
        if key in ORBITAL_TEMPLATES:
            return dict(ORBITAL_TEMPLATES[key])

    # Точное совпадение
    key = (page_type, status)
    if key in ORBITAL_TEMPLATES:
        return dict(ORBITAL_TEMPLATES[key])

    # Fallback по типу
    key = (page_type, "")
    if key in ORBITAL_TEMPLATES:
        return dict(ORBITAL_TEMPLATES[key])

    # Финальный fallback
    return dict(ORBITAL_TEMPLATES[("page", "")])
