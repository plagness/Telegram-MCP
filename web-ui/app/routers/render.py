"""Публичные эндпоинты: рендер страниц, индивидуальные ссылки, сабмит форм."""

from __future__ import annotations

import calendar as cal_mod
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..db import execute_returning, fetch_one, fetch_all
from ..services import links as links_svc
from ..services import pages as pages_svc

router = APIRouter(tags=["render"])
logger = logging.getLogger(__name__)
settings = get_settings()

# Кэш Telegram file URL (file_id → (url, timestamp)), TTL 1 час
_tg_file_cache: dict[str, tuple[str, float]] = {}
_TG_FILE_CACHE_TTL = 3600

# ── Константы календаря ──────────────────────────────────────────────────
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


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Точка входа Mini App (Direct Link).

    Telegram открывает зарегистрированный URL, start_param
    обрабатывается в twa.js (клиентский редирект на /p/{slug}).
    """
    templates = request.app.state.templates
    template = templates.get_template("base.html")
    return HTMLResponse(template.render())


@router.get("/p/{slug}", response_class=HTMLResponse)
async def render_page(slug: str, request: Request):
    """Рендер веб-страницы (Telegram Mini App)."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    templates = request.app.state.templates

    # Определяем шаблон по типу страницы
    template_map = {
        "prediction": "prediction.html",
        "survey": "survey.html",
        "dashboard": "dashboard.html",
        "leaderboard": "leaderboard.html",
        "calendar": "calendar.html",
    }
    template_name = template_map.get(page["page_type"], "page.html")

    # Для prediction — загружаем данные события
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

    # Для calendar — полный серверный рендеринг (сетка, события, всё в Jinja2)
    cal_ctx: dict[str, Any] = {}
    calendar_data: dict[str, Any] = {}
    calendar_id: int | None = None
    is_admin = False
    if page["page_type"] == "calendar":
        calendar_id = page.get("config", {}).get("calendar_id")
        cal_ctx = await _build_calendar_context(
            calendar_id=calendar_id,
            request=request,
        )
        calendar_data = cal_ctx.get("calendar", {})
        is_admin = cal_ctx.get("is_admin", False)

    template = templates.get_template(template_name)
    html = template.render(
        page=page,
        event=event_data,
        config=page.get("config", {}),
        public_url=settings.public_url,
        # Календарь
        calendar=calendar_data,
        calendar_id=calendar_id or 0,
        is_admin=is_admin,
        **{k: v for k, v in cal_ctx.items() if k not in ("calendar", "is_admin")},
    )
    return HTMLResponse(html)


@router.get("/l/{token}")
async def resolve_link(token: str):
    """Редирект по индивидуальной ссылке."""
    link = await links_svc.get_link_by_token(token)
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    if not link.get("page_active"):
        raise HTTPException(status_code=410, detail="Page is no longer active")

    await links_svc.mark_used(link["id"])

    return RedirectResponse(
        url=f"/p/{link['slug']}?link_token={token}",
        status_code=302,
    )


@router.post("/p/{slug}/submit")
async def submit_form(slug: str, request: Request):
    """Отправка формы / предсказания из TWA."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    body = await request.json()

    # Валидация initData
    init_data = body.get("init_data", "")
    user = validate_init_data(init_data, settings.get_bot_token())
    if not user:
        raise HTTPException(status_code=401, detail="Invalid initData")

    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user ID in initData")

    # Данные формы
    form_data = body.get("data", {})
    link_token = body.get("link_token")

    # Найти link_id если есть токен
    link_id = None
    if link_token:
        link = await links_svc.get_link_by_token(link_token)
        if link:
            link_id = link["id"]

    # Для предсказаний — проксировать ставку в tgapi
    if page["page_type"] == "prediction" and page.get("event_id"):
        result = await _submit_prediction(
            event_id=page["event_id"],
            user_id=user_id,
            form_data=form_data,
        )
        # Также сохраняем сабмит
        await _save_submission(
            page_id=page["id"],
            link_id=link_id,
            user_id=user_id,
            data={**form_data, "prediction_result": result},
            request=request,
        )
        return {"ok": True, "result": result}

    # Для обычных форм / опросов — сохраняем
    submission = await _save_submission(
        page_id=page["id"],
        link_id=link_id,
        user_id=user_id,
        data=form_data,
        request=request,
    )
    return {"ok": True, "submission_id": submission["id"]}


async def _submit_prediction(
    *,
    event_id: int,
    user_id: int,
    form_data: dict,
) -> dict:
    """Проксировать предсказание в tgapi."""
    option_id = form_data.get("option_id")
    amount = form_data.get("amount", 1)
    source = form_data.get("source", "auto")

    if not option_id:
        raise HTTPException(status_code=400, detail="option_id required")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.tgapi_url}/v1/predictions/bets",
                json={
                    "event_id": event_id,
                    "option_id": option_id,
                    "user_id": user_id,
                    "amount": amount,
                    "source": source,
                },
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        detail = "Ошибка размещения предсказания"
        try:
            detail = e.response.json().get("detail", detail)
        except Exception:
            pass
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


async def _save_submission(
    *,
    page_id: int,
    link_id: int | None,
    user_id: int,
    data: dict,
    request: Request,
) -> dict:
    """Сохранить ответ формы."""
    from psycopg.types.json import Json

    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:500]

    return await execute_returning(
        """
        INSERT INTO web_form_submissions (page_id, link_id, user_id, data, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [page_id, link_id, user_id, Json(data), ip, ua],
    )


# ---------------------------------------------------------------------------
# Календарь — серверный рендеринг + прокси-эндпоинты для CRUD
# ---------------------------------------------------------------------------


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
    """'2026-02-09T07:00:00+00:00' → '07:00'."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return f"{dt.hour:02d}:{dt.minute:02d}"
    except (ValueError, AttributeError):
        return ""


def _format_date_label(dk: str) -> str:
    """'2026-02-09' → '9 февраля 2026'."""
    try:
        parts = dk.split("-")
        return f"{int(parts[2])} {_MONTH_NAMES_GEN[int(parts[1]) - 1]} {parts[0]}"
    except (ValueError, IndexError):
        return dk


def _resolve_creator(created_by: str | None) -> dict[str, Any]:
    """Резолв created_by в словарь для отображения.

    Формат created_by:
    - "admin:{user_id}" → пользователь
    - "ai:{model}" → нейросеть
    - None → неизвестно
    """
    if not created_by:
        return {"type": "unknown", "name": "", "emoji": "👤", "color": "#9E9E9E"}

    if created_by.startswith("ai:"):
        model = created_by[3:].lower()
        if "claude" in model:
            return {"type": "ai", "name": "Claude", "emoji": "🤖", "color": "#7C3AED"}
        if "gpt" in model:
            return {"type": "ai", "name": "GPT", "emoji": "🧠", "color": "#10A37F"}
        if "gemini" in model:
            return {"type": "ai", "name": "Gemini", "emoji": "✨", "color": "#4285F4"}
        if "ollama" in model or "llama" in model:
            return {"type": "ai", "name": "Llama", "emoji": "🦙", "color": "#0084FF"}
        return {"type": "ai", "name": model.split("/")[-1].capitalize(), "emoji": "🤖", "color": "#6B7280"}

    if created_by.startswith("admin:"):
        uid = created_by[6:]
        return {"type": "user", "name": "", "user_id": uid, "emoji": "👤", "color": "#4A90D9"}

    return {"type": "unknown", "name": created_by, "emoji": "👤", "color": "#9E9E9E"}


async def _resolve_tg_file_url(file_id: str) -> str:
    """Получить прямой URL файла через Telegram Bot API (с кэшем)."""
    now = time.time()
    cached = _tg_file_cache.get(file_id)
    if cached and now - cached[1] < _TG_FILE_CACHE_TTL:
        return cached[0]

    token = settings.get_bot_token()
    if not token:
        return ""

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
            )
            if r.status_code == 200:
                data = r.json()
                file_path = data.get("result", {}).get("file_path", "")
                if file_path:
                    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                    _tg_file_cache[file_id] = (url, now)
                    return url
    except Exception as e:
        logger.warning("Не удалось получить file URL из Telegram: %s", e)
    return ""


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
    # Резолв создателя
    entry["_creator"] = _resolve_creator(entry.get("created_by"))
    return entry


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
                # Получаем прямой URL фото через Telegram Bot API
                photo_url = await _resolve_tg_file_url(chat_info["photo_file_id"])
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

    # Обогащаем записи вычисленными полями
    for entry in entries:
        _enrich_entry(entry)

    # Собираем уникальные теги для фильтра
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
    first_dow = datetime(cal_year, cal_month, 1).weekday()  # Пн=0
    days_in_month = cal_mod.monthrange(cal_year, cal_month)[1]
    if cal_month == 1:
        prev_days = cal_mod.monthrange(cal_year - 1, 12)[1]
    else:
        prev_days = cal_mod.monthrange(cal_year, cal_month - 1)[1]
    today_key = now.strftime("%Y-%m-%d")

    cells: list[dict] = []
    # Дни предыдущего месяца
    for p in range(first_dow):
        d = prev_days - first_dow + 1 + p
        cells.append({"day": d, "other": True, "date_key": "", "events": [], "is_today": False})
    # Текущий месяц
    for d in range(1, days_in_month + 1):
        dk = f"{cal_year}-{cal_month:02d}-{d:02d}"
        day_events = entries_by_day.get(dk, [])
        cells.append({
            "day": d,
            "other": False,
            "date_key": dk,
            "events": day_events,
            "is_today": dk == today_key,
        })
    # Дни следующего месяца
    total = len(cells)
    remaining = (35 - total) if total <= 35 else (42 - total)
    for n in range(1, remaining + 1):
        cells.append({"day": n, "other": True, "date_key": "", "events": [], "is_today": False})

    # Нарезка по неделям
    grid_weeks = []
    for i in range(0, len(cells), 7):
        grid_weeks.append(cells[i : i + 7])
    ctx["grid_weeks"] = grid_weeks

    # Панели событий по дням (для клика по дню)
    ctx["day_panels"] = {
        dk: {"date_label": _format_date_label(dk), "entries": evts}
        for dk, evts in entries_by_day.items()
    }

    # Список событий (сгруппированный по дням)
    seen_dates: list[str] = []
    for entry in sorted(entries, key=lambda e: e.get("start_at", "")):
        dk = entry.get("start_at", "")[:10]
        if dk and dk not in seen_dates:
            seen_dates.append(dk)
    ctx["entries_grouped"] = [
        {"date_key": dk, "date_label": _format_date_label(dk), "entries": entries_by_day.get(dk, [])}
        for dk in seen_dates
    ]

    # Выбранный день (из query param)
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
        [user_id, str(chat_id)],
    )
    return row is not None


async def _validate_calendar_admin(
    body: dict,
    calendar_id: int,
) -> int:
    """Валидация initData + проверка прав админа. Возвращает user_id."""
    init_data = body.get("init_data", "")
    user = validate_init_data(init_data, settings.get_bot_token())
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid initData")

    # Узнаём chat_id календаря
    cal = await fetch_one("SELECT chat_id FROM calendars WHERE id = %s", [calendar_id])
    if not cal or not cal.get("chat_id"):
        raise HTTPException(status_code=404, detail="Calendar not found")

    if not await _check_chat_admin(user["id"], cal["chat_id"]):
        raise HTTPException(status_code=403, detail="Not a chat admin")

    return user["id"]


@router.get("/p/{slug}/calendar/entries")
async def calendar_entries_proxy(slug: str, request: Request):
    """Прокси для JS: записи календаря (чтение — без авторизации)."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "calendar":
        raise HTTPException(status_code=404, detail="Page not found")

    calendar_id = page.get("config", {}).get("calendar_id")
    if not calendar_id:
        raise HTTPException(status_code=400, detail="No calendar_id in config")

    # Пробрасываем query params в tgapi
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
    """Прокси для JS: создание записи (только админ)."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "calendar":
        raise HTTPException(status_code=404, detail="Page not found")

    calendar_id = page.get("config", {}).get("calendar_id")
    if not calendar_id:
        raise HTTPException(status_code=400, detail="No calendar_id in config")

    body = await request.json()
    user_id = await _validate_calendar_admin(body, calendar_id)

    # Убираем init_data из body перед проксированием
    body.pop("init_data", None)
    body["calendar_id"] = calendar_id
    body["created_by"] = f"admin:{user_id}"
    body["performed_by"] = f"admin:{user_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.tgapi_url}/v1/calendar/entries",
                json=body,
            )
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.put("/p/{slug}/calendar/entries/{entry_id}")
async def calendar_update_entry_proxy(slug: str, entry_id: int, request: Request):
    """Прокси для JS: обновление записи (только админ)."""
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
                f"{settings.tgapi_url}/v1/calendar/entries/{entry_id}",
                json=body,
            )
            return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/p/{slug}/calendar/entries/{entry_id}/status")
async def calendar_status_entry_proxy(slug: str, entry_id: int, request: Request):
    """Прокси для JS: изменение статуса (только админ)."""
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
    """Прокси для JS: удаление записи (только админ)."""
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
