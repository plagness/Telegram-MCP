"""Handler для calendar — серверный рендеринг + proxy CRUD к tgapi.

Извлечён из render.py (713 строк calendar subsystem).
"""

from __future__ import annotations

import calendar as cal_mod
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..auth import validate_init_data
from ..config import get_settings
from ..db import fetch_one
from ..icons import resolve_icon, adjusted_color, get_display_name, get_fallback_emoji
from ..services import pages as pages_svc
from ..services.telegram import resolve_tg_file_url
from . import PageTypeHandler

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Константы ─────────────────────────────────────────────────────────────

_MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
_MONTH_NAMES_GEN = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_TAG_COLORS = {
    "work": "#4A90D9", "personal": "#9B59B6", "meeting": "#2ECC71",
    "deadline": "#E74C3C", "idea": "#F39C12",
}
_PRIORITY_COLORS = {5: "#E74C3C", 4: "#E67E22", 3: "#FFC107", 2: "#2ECC71", 1: "#95A5A6"}
_PRIORITY_LABELS = {5: "Критичный", 4: "Высокий", 3: "Средний", 2: "Обычный", 1: "Низкий"}

_ENTRY_TYPE_ICONS: dict[str, str] = {
    "event": "\U0001f4c5",      # 📅
    "task": "\U0001f4dd",        # 📝
    "trigger": "\U0001f514",     # 🔔
    "monitor": "\U0001f4e1",     # 📡
    "vote": "\U0001f5f3",        # 🗳
    "routine": "\U0001f504",     # 🔄
}
_ENTRY_TYPE_LABELS: dict[str, str] = {
    "event": "Событие", "task": "Задача", "trigger": "Триггер",
    "monitor": "Монитор", "vote": "Голосование", "routine": "Рутина",
}
_TRIGGER_STATUS_ICONS: dict[str, str] = {
    "pending": "\u23f3",         # ⏳
    "scheduled": "\U0001f4cb",   # 📋
    "fired": "\u25b6",           # ▶
    "success": "\u2705",         # ✅
    "failed": "\u274c",          # ❌
    "skipped": "\u23ed",         # ⏭
    "expired": "\U0001f4a4",     # 💤
}
_SOURCE_LABELS: dict[str, str] = {
    "planner": "Планер", "arena": "Арена", "channel": "Каналы",
    "bcs": "Биржа", "trade": "Трейдинг", "user": "Пользователь",
    "video": "Видео", "metrics": "Метрики",
}
_ENTRY_TYPE_COLORS: dict[str, str] = {
    "event": "#FFC107", "task": "#10B981", "trigger": "#F59E0B",
    "monitor": "#3B82F6", "vote": "#8B5CF6", "routine": "#6B7280",
}


# ── Helper'ы ──────────────────────────────────────────────────────────────


def _auto_color(entry: dict) -> str:
    """Детерминированный цвет записи."""
    if entry.get("color"):
        return entry["color"]
    tags = entry.get("tags") or []
    for tag in tags:
        c = _TAG_COLORS.get(tag.lower())
        if c:
            return c
    return _PRIORITY_COLORS.get(entry.get("priority", 3), "#FFC107")


def _format_time(iso: str) -> str:
    """'2026-02-09T07:00:00+00:00' -> '07:00'."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.hour:02d}:{dt.minute:02d}"
    except (ValueError, AttributeError):
        return ""


def _format_date_label(dk: str) -> str:
    """'2026-02-09' -> '9 февраля 2026'."""
    try:
        parts = dk.split("-")
        return f"{int(parts[2])} {_MONTH_NAMES_GEN[int(parts[1]) - 1]} {parts[0]}"
    except (ValueError, IndexError):
        return dk


def _resolve_creator(created_by: str | None) -> dict[str, Any]:
    """Резолв created_by в словарь для отображения."""
    _no_icon = {"has_icon": False, "icon_url": "", "icon_slug": ""}

    if not created_by:
        return {"type": "unknown", "name": "", "emoji": "\U0001f464", "color": "#9E9E9E", **_no_icon}

    if created_by.startswith("ai:"):
        model = created_by[3:]
        icon = resolve_icon(model)
        if icon:
            return {
                "type": "ai", "name": get_display_name(model),
                "emoji": get_fallback_emoji(model),
                "color": "#" + adjusted_color(icon["hex"]),
                "has_icon": True, "icon_url": icon["icon_url"], "icon_slug": icon["slug"],
            }
        return {
            "type": "ai", "name": get_display_name(model),
            "emoji": get_fallback_emoji(model), "color": "#6B7280", **_no_icon,
        }

    if created_by.startswith("admin:"):
        uid = created_by[6:]
        return {"type": "user", "name": "", "user_id": uid, "emoji": "\U0001f464", "color": "#4A90D9", **_no_icon}

    return {"type": "unknown", "name": created_by, "emoji": "\U0001f464", "color": "#9E9E9E", **_no_icon}


def _build_widgets(entry: dict) -> list[dict]:
    """Собирает динамические виджеты из metadata/result/tags для карточки."""
    widgets: list[dict] = []
    meta = entry.get("metadata") or {}
    result = entry.get("result") or {}
    tags_lower = [t.lower() for t in (entry.get("tags") or [])]
    _no_icon = {"has_icon": False, "icon_url": ""}

    # BTC
    btc = meta.get("btc_price")
    if btc and any(t in tags_lower for t in ("крипта", "btc", "crypto", "биткоин", "bitcoin")):
        change = meta.get("btc_change_24h")
        btc_icon = resolve_icon("bitcoin")
        widgets.append({
            "type": "price", "label": "BTC",
            "value": f"${btc:,.0f}", "change": change, "icon": "\u20bf",
            "has_icon": bool(btc_icon),
            "icon_url": btc_icon["icon_url"] if btc_icon else "",
        })

    # Ключевая ставка ЦБ
    kr = meta.get("key_rate_pct")
    if kr and any(t in tags_lower for t in ("цб", "цб рф", "ставка", "ключевая ставка", "cbr")):
        widgets.append({
            "type": "rate", "label": "Ставка ЦБ",
            "value": f"{kr}%", "change": None, "icon": "\U0001f3e6", **_no_icon,
        })

    # USD/RUB
    rub = meta.get("rub_usd")
    if rub and any(t in tags_lower for t in ("доллар", "usd", "валюта", "рубль", "forex")):
        widgets.append({
            "type": "rate", "label": "USD/RUB",
            "value": f"\u20bd{rub:.2f}", "change": meta.get("rub_usd_change"),
            "icon": "\U0001f4b1", **_no_icon,
        })

    # Тикер BCS
    ticker = meta.get("ticker")
    price = meta.get("price")
    if ticker and price and entry.get("source_module") == "bcs":
        ticker_icon = resolve_icon(ticker)
        widgets.append({
            "type": "price", "label": ticker,
            "value": f"{price:,.2f}", "change": meta.get("price_change_pct"),
            "icon": "\U0001f4c8",
            "has_icon": bool(ticker_icon),
            "icon_url": ticker_icon["icon_url"] if ticker_icon else "",
        })

    # Результат триггера
    if result and result.get("status"):
        rs = result["status"]
        icon = "\u2705" if rs == "success" else "\u274c" if rs == "failed" else "\u23f3"
        widgets.append({
            "type": "result", "label": "Результат",
            "value": rs, "change": None, "icon": icon, **_no_icon,
        })

    # Кастомные виджеты
    custom_widgets = meta.get("widgets")
    if isinstance(custom_widgets, list):
        for cw in custom_widgets[:10]:
            if not isinstance(cw, dict) or not cw.get("label") or not cw.get("value"):
                continue
            cw_icon_name = cw.get("icon")
            cw_icon = resolve_icon(cw_icon_name) if cw_icon_name else None
            widgets.append({
                "type": cw.get("type", "custom"),
                "label": str(cw["label"]), "value": str(cw["value"]),
                "change": cw.get("change"), "icon": cw.get("emoji", ""),
                "has_icon": bool(cw_icon),
                "icon_url": cw_icon["icon_url"] if cw_icon else "",
            })

    return widgets


def _enrich_entry(entry: dict) -> dict:
    """Добавляет вычисленные поля для шаблона."""
    entry["_color"] = _auto_color(entry)
    start_at = entry.get("start_at", "")
    end_at = entry.get("end_at")
    if entry.get("all_day"):
        entry["_time"] = "весь день"
    elif start_at:
        t = _format_time(start_at)
        if end_at:
            t += " — " + _format_time(end_at)
        entry["_time"] = t
    else:
        entry["_time"] = ""
    pri = entry.get("priority", 3)
    entry["_priority_label"] = _PRIORITY_LABELS.get(pri, "")
    entry["_priority_color"] = _PRIORITY_COLORS.get(pri, "#FFC107")
    entry["_tags_lower"] = ",".join(t.lower() for t in (entry.get("tags") or []))
    entry["_creator"] = _resolve_creator(entry.get("created_by"))
    et = entry.get("entry_type", "event")
    entry["_entry_type_icon"] = _ENTRY_TYPE_ICONS.get(et, "")
    entry["_entry_type_label"] = _ENTRY_TYPE_LABELS.get(et, et)
    ts = entry.get("trigger_status", "pending")
    entry["_trigger_status_icon"] = _TRIGGER_STATUS_ICONS.get(ts, "")
    sm = entry.get("source_module") or ""
    entry["_source_label"] = _SOURCE_LABELS.get(sm, sm)
    ce = float(entry.get("cost_estimate") or 0)
    entry["_cost_display"] = f"${ce:.2f}" if ce > 0 else ""
    entry["_entry_type_color"] = _ENTRY_TYPE_COLORS.get(et, "#FFC107")
    action = entry.get("action") or {}
    entry["_action_json"] = json.dumps(action, ensure_ascii=False, indent=2) if action else ""
    result = entry.get("result")
    entry["_result_json"] = json.dumps(result, ensure_ascii=False, indent=2) if result else ""
    trigger_at = entry.get("trigger_at") or ""
    if trigger_at:
        entry["_trigger_at_display"] = _format_time(trigger_at)
        try:
            dt = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
            entry["_trigger_at_full"] = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            entry["_trigger_at_full"] = trigger_at[:16].replace("T", " ")
    else:
        entry["_trigger_at_display"] = ""
        entry["_trigger_at_full"] = ""
    tick_count = entry.get("tick_count", 0)
    max_ticks = entry.get("max_ticks")
    tick_interval = entry.get("tick_interval") or ""
    next_tick = entry.get("next_tick_at") or ""
    if et == "monitor" and tick_interval:
        parts = [f"тик {tick_count}"]
        if max_ticks:
            parts[0] += f"/{max_ticks}"
        parts.append(f"инт. {tick_interval}")
        if next_tick:
            parts.append(f"след. {_format_time(next_tick)}")
        entry["_tick_info"] = " · ".join(parts)
    else:
        entry["_tick_info"] = ""
    icon_name = entry.get("icon")
    if icon_name:
        icon_data = resolve_icon(icon_name)
        if icon_data:
            entry["_icon"] = {
                "has_icon": True, "icon_url": icon_data["icon_url"],
                "icon_slug": icon_data["slug"],
                "icon_color": "#" + adjusted_color(icon_data["hex"]),
            }
        else:
            entry["_icon"] = None
    else:
        entry["_icon"] = None
    meta = entry.get("metadata") or {}
    participant_raw = meta.get("participant")
    if participant_raw:
        entry["_participant"] = _resolve_creator(participant_raw)
        entry["_has_participant"] = True
    else:
        entry["_participant"] = None
        entry["_has_participant"] = False
    entry["_widgets"] = _build_widgets(entry)
    entry["_widgets_json"] = json.dumps(entry["_widgets"], ensure_ascii=False) if entry["_widgets"] else ""
    entry["_urgent"] = False
    if trigger_at and entry.get("trigger_status") == "pending":
        try:
            ta = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
            delta = (ta - datetime.now(timezone.utc)).total_seconds()
            entry["_urgent"] = 0 < delta < 3600
        except Exception:
            pass
    return entry


# ── Основной контекст ─────────────────────────────────────────────────────


async def _build_calendar_context(
    *,
    calendar_id: int | None,
    request: Request,
) -> dict[str, Any]:
    """Полный серверный контекст для calendar.html."""
    now = datetime.now(timezone.utc)
    ctx: dict[str, Any] = {
        "calendar": {},
        "is_admin": False,
        "weekdays": _WEEKDAYS,
        "month_title": "",
        "prev_month_param": "",
        "next_month_param": "",
        "grid_weeks": [],
        "entries_grouped": [],
        "day_panels": {},
        "tag_colors": _TAG_COLORS,
        "priority_labels": _PRIORITY_LABELS,
        "priority_colors": _PRIORITY_COLORS,
        "selected_day": None,
        "all_tags": [],
        "chat_info": None,
        "chat_photo_url": "",
    }
    if not calendar_id:
        return ctx

    # Определяем месяц из query-параметра
    month_param = request.query_params.get("month")
    if month_param:
        try:
            parts = month_param.split("-")
            cal_year, cal_month = int(parts[0]), int(parts[1])
            if not (1 <= cal_month <= 12 and 2000 <= cal_year <= 2100):
                cal_year, cal_month = now.year, now.month
        except (ValueError, IndexError):
            cal_year, cal_month = now.year, now.month
    else:
        cal_year, cal_month = now.year, now.month

    # Загружаем данные календаря
    calendar_data: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/calendar/calendars/{calendar_id}"
            )
            if r.status_code == 200:
                calendar_data = r.json().get("calendar", {})
    except Exception as e:
        logger.warning("Не удалось загрузить данные календаря: %s", e)
    ctx["calendar"] = calendar_data

    # Загружаем информацию о чате для заголовка
    chat_id = calendar_data.get("chat_id")
    if chat_id:
        try:
            chat_info = await fetch_one(
                "SELECT chat_id, title, username, description, member_count, "
                "photo_file_id, type FROM chats WHERE chat_id = %s",
                [str(chat_id)],
            )
            ctx["chat_info"] = chat_info
            if chat_info and chat_info.get("photo_file_id"):
                photo_url = await resolve_tg_file_url(chat_info["photo_file_id"])
                ctx["chat_photo_url"] = photo_url
        except Exception as e:
            logger.warning("Не удалось загрузить информацию о чате: %s", e)

    # Загружаем записи за выбранный месяц
    entries: list[dict[str, Any]] = []
    month_start = datetime(cal_year, cal_month, 1, tzinfo=timezone.utc)
    if cal_month == 12:
        month_end = datetime(cal_year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(cal_year, cal_month + 1, 1, tzinfo=timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/calendar/entries",
                params={
                    "calendar_id": calendar_id,
                    "start": month_start.isoformat(),
                    "end": month_end.isoformat(),
                    "limit": 500,
                },
            )
            if r.status_code == 200:
                entries = r.json().get("entries", [])
    except Exception as e:
        logger.warning("Не удалось загрузить записи календаря: %s", e)

    for entry in entries:
        _enrich_entry(entry)

    # Уникальные теги для фильтра
    tag_set: set[str] = set()
    all_tags: list[str] = []
    for entry in entries:
        for tag in entry.get("tags") or []:
            t_lower = tag.lower()
            if t_lower not in tag_set:
                tag_set.add(t_lower)
                all_tags.append(tag)
    ctx["all_tags"] = all_tags

    # Группируем по дате
    entries_by_day: dict[str, list] = {}
    for entry in entries:
        start_at = entry.get("start_at", "")
        if isinstance(start_at, str) and len(start_at) >= 10:
            dk = start_at[:10]
            entries_by_day.setdefault(dk, []).append(entry)

    # Навигация по месяцам
    ctx["month_title"] = f"{_MONTH_NAMES[cal_month - 1]} {cal_year}"
    if cal_month == 1:
        ctx["prev_month_param"] = f"{cal_year - 1}-12"
    else:
        ctx["prev_month_param"] = f"{cal_year}-{cal_month - 1:02d}"
    if cal_month == 12:
        ctx["next_month_param"] = f"{cal_year + 1}-01"
    else:
        ctx["next_month_param"] = f"{cal_year}-{cal_month + 1:02d}"

    # Сетка месяца
    first_dow = datetime(cal_year, cal_month, 1).weekday()
    days_in_month = cal_mod.monthrange(cal_year, cal_month)[1]
    if cal_month == 1:
        prev_days = cal_mod.monthrange(cal_year - 1, 12)[1]
    else:
        prev_days = cal_mod.monthrange(cal_year, cal_month - 1)[1]
    today_key = now.strftime("%Y-%m-%d")

    cells: list[dict] = []
    for p in range(first_dow):
        d = prev_days - first_dow + 1 + p
        cells.append({"day": d, "other": True, "date_key": "", "events": [], "is_today": False})
    for d in range(1, days_in_month + 1):
        dk = f"{cal_year}-{cal_month:02d}-{d:02d}"
        day_events = entries_by_day.get(dk, [])
        cells.append({
            "day": d, "other": False, "date_key": dk,
            "events": day_events, "is_today": dk == today_key,
        })
    total = len(cells)
    remaining = (35 - total) if total <= 35 else (42 - total)
    for n in range(1, remaining + 1):
        cells.append({"day": n, "other": True, "date_key": "", "events": [], "is_today": False})

    grid_weeks = []
    for i in range(0, len(cells), 7):
        grid_weeks.append(cells[i : i + 7])
    ctx["grid_weeks"] = grid_weeks

    ctx["day_panels"] = {
        dk: {"date_label": _format_date_label(dk), "entries": evts}
        for dk, evts in entries_by_day.items()
    }

    seen_dates: list[str] = []
    for entry in sorted(entries, key=lambda e: e.get("start_at", "")):
        dk = entry.get("start_at", "")[:10]
        if dk and dk not in seen_dates:
            seen_dates.append(dk)
    ctx["entries_grouped"] = [
        {"date_key": dk, "date_label": _format_date_label(dk), "entries": entries_by_day.get(dk, [])}
        for dk in seen_dates
    ]

    selected = request.query_params.get("day")
    if selected and selected in entries_by_day:
        ctx["selected_day"] = selected

    # Проверка админа
    init_data_raw = request.query_params.get("initData", "")
    if init_data_raw and calendar_data.get("chat_id"):
        user = validate_init_data(init_data_raw, settings.get_bot_token())
        if user and user.get("id"):
            ctx["is_admin"] = await _check_chat_admin(
                user["id"], calendar_data["chat_id"]
            )

    return ctx


async def _check_chat_admin(user_id: int, chat_id: str) -> bool:
    """Проверить, является ли user_id админом чата."""
    row = await fetch_one(
        """
        SELECT status FROM chat_members
        WHERE user_id = %s AND chat_id = %s
          AND status IN ('administrator', 'creator')
        """,
        [str(user_id), str(chat_id)],
    )
    return row is not None


async def _validate_calendar_admin(body: dict, calendar_id: int) -> int:
    """Валидация initData + проверка прав админа. Возвращает user_id."""
    init_data = body.get("init_data", "")
    user = validate_init_data(init_data, settings.get_bot_token())
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid initData")

    cal = await fetch_one("SELECT chat_id FROM calendars WHERE id = %s", [calendar_id])
    if not cal or not cal.get("chat_id"):
        raise HTTPException(status_code=404, detail="Calendar not found")

    if not await _check_chat_admin(user["id"], cal["chat_id"]):
        raise HTTPException(status_code=403, detail="Not a chat admin")

    return user["id"]


# ── Handler ───────────────────────────────────────────────────────────────


class CalendarHandler(PageTypeHandler):
    """Календарь месяца с полным серверным рендерингом."""

    page_type = "calendar"
    template = "calendar.html"

    async def load_data(
        self, page: dict, user: dict | None, request: Request
    ) -> dict[str, Any]:
        """Загрузить контекст календаря (сетка, записи, чат)."""
        calendar_id = (page.get("config") or {}).get("calendar_id")
        cal_ctx = await _build_calendar_context(
            calendar_id=calendar_id,
            request=request,
        )
        calendar_data = cal_ctx.get("calendar", {})
        is_admin = cal_ctx.get("is_admin", False)
        return {
            "calendar": calendar_data,
            "calendar_id": calendar_id or 0,
            "is_admin": is_admin,
            **{k: v for k, v in cal_ctx.items() if k not in ("calendar", "is_admin")},
        }

    def register_routes(self, router: APIRouter) -> None:
        """Proxy-маршруты для CRUD записей календаря."""

        @router.get("/p/{slug}/calendar/entries")
        async def calendar_entries_proxy(slug: str, request: Request):
            """Записи календаря (чтение — без авторизации)."""
            page = await pages_svc.get_page(slug)
            if not page or page["page_type"] != "calendar":
                raise HTTPException(status_code=404, detail="Page not found")

            calendar_id = page.get("config", {}).get("calendar_id")
            if not calendar_id:
                raise HTTPException(status_code=400, detail="No calendar_id in config")

            qs = str(request.query_params)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        f"{settings.tgapi_url}/v1/calendar/entries?calendar_id={calendar_id}&{qs}"
                    )
                    return r.json()
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))

        @router.post("/p/{slug}/calendar/entries")
        async def calendar_create_entry_proxy(slug: str, request: Request):
            """Создание записи (только админ)."""
            page = await pages_svc.get_page(slug)
            if not page or page["page_type"] != "calendar":
                raise HTTPException(status_code=404, detail="Page not found")

            calendar_id = page.get("config", {}).get("calendar_id")
            if not calendar_id:
                raise HTTPException(status_code=400, detail="No calendar_id in config")

            body = await request.json()
            user_id = await _validate_calendar_admin(body, calendar_id)

            body.pop("init_data", None)
            body["calendar_id"] = calendar_id
            body["created_by"] = f"admin:{user_id}"
            body["performed_by"] = f"admin:{user_id}"

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.post(
                        f"{settings.tgapi_url}/v1/calendar/entries", json=body,
                    )
                    return r.json()
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))

        @router.put("/p/{slug}/calendar/entries/{entry_id}")
        async def calendar_update_entry_proxy(slug: str, entry_id: int, request: Request):
            """Обновление записи (только админ)."""
            page = await pages_svc.get_page(slug)
            if not page or page["page_type"] != "calendar":
                raise HTTPException(status_code=404, detail="Page not found")

            calendar_id = page.get("config", {}).get("calendar_id")
            if not calendar_id:
                raise HTTPException(status_code=400, detail="No calendar_id in config")

            body = await request.json()
            user_id = await _validate_calendar_admin(body, calendar_id)
            body.pop("init_data", None)
            body["performed_by"] = f"admin:{user_id}"

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.put(
                        f"{settings.tgapi_url}/v1/calendar/entries/{entry_id}", json=body,
                    )
                    return r.json()
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))

        @router.post("/p/{slug}/calendar/entries/{entry_id}/status")
        async def calendar_status_entry_proxy(slug: str, entry_id: int, request: Request):
            """Изменение статуса (только админ)."""
            page = await pages_svc.get_page(slug)
            if not page or page["page_type"] != "calendar":
                raise HTTPException(status_code=404, detail="Page not found")

            calendar_id = page.get("config", {}).get("calendar_id")
            if not calendar_id:
                raise HTTPException(status_code=400, detail="No calendar_id in config")

            body = await request.json()
            user_id = await _validate_calendar_admin(body, calendar_id)
            body.pop("init_data", None)
            body["performed_by"] = f"admin:{user_id}"

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.post(
                        f"{settings.tgapi_url}/v1/calendar/entries/{entry_id}/status",
                        json=body,
                    )
                    return r.json()
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))

        @router.delete("/p/{slug}/calendar/entries/{entry_id}")
        async def calendar_delete_entry_proxy(slug: str, entry_id: int, request: Request):
            """Удаление записи (только админ)."""
            page = await pages_svc.get_page(slug)
            if not page or page["page_type"] != "calendar":
                raise HTTPException(status_code=404, detail="Page not found")

            calendar_id = page.get("config", {}).get("calendar_id")
            if not calendar_id:
                raise HTTPException(status_code=400, detail="No calendar_id in config")

            body = await request.json()
            user_id = await _validate_calendar_admin(body, calendar_id)

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.delete(
                        f"{settings.tgapi_url}/v1/calendar/entries/{entry_id}",
                        params={"performed_by": f"admin:{user_id}"},
                    )
                    return r.json()
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))
