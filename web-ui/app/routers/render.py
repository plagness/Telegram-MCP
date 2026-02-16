"""Публичные эндпоинты: рендер страниц, индивидуальные ссылки, сабмит форм."""

from __future__ import annotations

import calendar as cal_mod
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..db import execute_returning, fetch_one, fetch_all
from ..icons import resolve_icon, adjusted_color, get_display_name, get_fallback_emoji
from ..orbital import compute_orbital
from ..services import links as links_svc
from ..services import pages as pages_svc
from ..services.access import (
    check_page_access,
    enrich_pages_for_hub,
    get_accessible_pages,
    get_user_roles,
    group_pages_for_hub,
)
from ..services.banner import (
    create_banner,
    delete_banner,
    get_active_banners,
    get_all_banners,
    toggle_banner,
    update_banner_avatar,
)

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

_ROLE_LABELS: dict[str, str] = {
    "project_owner": "Владелец",
    "backend_dev": "Разработчик",
    "tester": "Тестер",
    "moderator": "Модератор",
}

# Маппинг page_type → имя иконки для resolve_icon() (Simple Icons SVG)
_HUB_TYPE_ICONS: dict[str, str] = {
    "prediction": "target",
    "calendar": "googlecalendar",
    "survey": "googleforms",
    "leaderboard": "openbadges",
    "dashboard": "grafana",
    "llm": "huggingface",
    "infra": "serverfault",
    "channel": "telegram",
    "bcs": "tradingview",
    "arena": "probot",
    "planner": "todoist",
    "metrics": "grafana",
    "k8s": "kubernetes",
    "page": "readme",
}


async def _build_bar_context(user_id: int, roles: set[str] | None = None) -> dict[str, Any]:
    """Контекст для sticky header (bar_tag, bar_tag_type)."""
    if roles is None:
        roles = await get_user_roles(user_id)

    for role in ("project_owner", "backend_dev", "moderator", "tester"):
        if role in roles:
            return {"bar_tag": _ROLE_LABELS[role], "bar_tag_type": "role"}

    chat_row = await fetch_one(
        """
        SELECT c.title FROM chat_members cm
        JOIN chats c ON c.chat_id = cm.chat_id
        WHERE cm.user_id = %s AND cm.status NOT IN ('left', 'kicked')
        ORDER BY cm.updated_at DESC NULLS LAST LIMIT 1
        """,
        [str(user_id)],
    )
    if chat_row and chat_row.get("title"):
        return {"bar_tag": chat_row["title"], "bar_tag_type": "chat"}

    return {"bar_tag": None, "bar_tag_type": None}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Точка входа Mini App (Direct Link).

    Если есть start_param → twa.js делает клиентский редирект на /p/{slug}.
    Если есть initData (без start_param) → рендерим hub с доступными страницами.
    Иначе → base.html (twa.js перенаправит с initData).
    """
    templates = request.app.state.templates

    # Пробуем получить initData для hub-рендера
    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user:
        # Без initData — показываем base.html (twa.js обработает start_param или
        # перенаправит обратно с initData для hub)
        return HTMLResponse(templates.get_template("base.html").render())

    # С initData — рендерим hub с доступными страницами
    user_id = user.get("id")
    pages = await get_accessible_pages(user_id) if user_id else []
    roles = await get_user_roles(user_id) if user_id else set()

    # Обогащаем страницы live-данными (пул ставок, события, ответы)
    pages = await enrich_pages_for_hub(pages, user_id)

    # Резолвим SVG-иконки для карточек (Simple Icons)
    for p in pages:
        icon_name = (p.get("config") or {}).get("icon") or _HUB_TYPE_ICONS.get(p["page_type"])
        p["_icon"] = resolve_icon(icon_name) if icon_name else None

    # Резолвим chat photo URLs для hub
    for p in pages:
        fid = p.get("_chat_photo_file_id")
        if fid:
            try:
                p["_chat_photo_url"] = await _resolve_tg_file_url(fid)
            except Exception:
                p["_chat_photo_url"] = ""

    # Орбитальная конфигурация для визуальных панелей
    for i, p in enumerate(pages):
        p["_orbital"] = compute_orbital(
            p.get("page_type", "page"),
            p.get("_meta") or {},
            index=i,
            config=p.get("config"),
            chat_photo_url=p.get("_chat_photo_url", ""),
        )

    # Классификация: временные (активные события) vs постоянные
    temporal_pages: list[dict] = []
    permanent_pages: list[dict] = []
    for p in pages:
        meta = p.get("_meta") or {}
        pt = p.get("page_type", "")
        is_temporal = False
        if pt == "prediction":
            if meta.get("status") in ("open", "active") and meta.get("deadline"):
                is_temporal = True
        elif pt == "calendar":
            if meta.get("next_entry"):
                is_temporal = True
        elif pt == "survey":
            is_temporal = True  # опросы/формы — всегда временные
        p["_is_temporal"] = is_temporal
        (temporal_pages if is_temporal else permanent_pages).append(p)

    # Контекст для sticky header
    bar_ctx = await _build_bar_context(user_id, roles) if user_id else {}

    # Промо-баннеры для hub
    banners: list[dict] = []
    try:
        banners = await get_active_banners(roles)
    except Exception:
        logger.exception("Failed to load banners")

    # Уникальные источники для фильтра
    sources: dict[str, str] = {}
    for page in pages:
        sl = page.get("_source_label", "Общие")
        st = page.get("_source_type", "public")
        if sl not in sources:
            sources[sl] = st

    html = templates.get_template("hub.html").render(
        user=user,
        bar_user=user,
        **bar_ctx,
        roles=sorted(roles),
        pages=pages,
        temporal_pages=temporal_pages,
        permanent_pages=permanent_pages,
        banners=banners,
        sources=sources,
        total_pages=len(pages),
        public_url=settings.public_url,
    )
    return HTMLResponse(html)


@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    """Профиль пользователя (баланс, роли, активность)."""
    templates = request.app.state.templates

    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())

    user_id = user["id"]
    roles = await get_user_roles(user_id)

    # Баланс
    balance_row = await fetch_one(
        "SELECT balance, total_deposited, total_won, total_lost, total_withdrawn "
        "FROM user_balances WHERE user_id = %s",
        [str(user_id)],
    )
    balance = balance_row or {
        "balance": 0, "total_deposited": 0, "total_won": 0,
        "total_lost": 0, "total_withdrawn": 0,
    }

    # Количество ставок
    bets_row = await fetch_one(
        "SELECT COUNT(*) AS total FROM prediction_bets WHERE user_id = %s",
        [str(user_id)],
    )

    # Количество ответов на опросы
    surveys_row = await fetch_one(
        "SELECT COUNT(*) AS total FROM web_form_submissions WHERE user_id = %s",
        [str(user_id)],
    )

    # Последние транзакции (5 штук)
    recent_tx = await fetch_all(
        "SELECT amount, transaction_type, description, created_at "
        "FROM balance_transactions WHERE user_id = %s "
        "ORDER BY created_at DESC LIMIT 5",
        [str(user_id)],
    )

    bar_ctx = await _build_bar_context(user_id, roles)

    html = templates.get_template("profile.html").render(
        user=user,
        bar_user=user,
        **bar_ctx,
        roles=sorted(roles),
        balance=balance,
        bets_count=bets_row["total"] if bets_row else 0,
        surveys_count=surveys_row["total"] if surveys_row else 0,
        recent_tx=recent_tx,
        role_labels=_ROLE_LABELS,
    )
    return HTMLResponse(html)


@router.get("/p/{slug}", response_class=HTMLResponse)
async def render_page(slug: str, request: Request):
    """Рендер веб-страницы (Telegram Mini App)."""
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Проверка доступа (initData из query param или header)
    init_data = (
        request.query_params.get("initData", "")
        or request.headers.get("X-Init-Data", "")
    )
    config = page.get("config") or {}
    has_access_rules = bool(config.get("access_rules") or config.get("allowed_users"))

    user = None
    if init_data:
        user = validate_init_data(init_data, settings.get_bot_token())
        if user and user.get("id"):
            has_access = await check_page_access(user["id"], page)
            if not has_access:
                raise HTTPException(status_code=403, detail="Access denied")
    elif has_access_rules:
        # Страница защищена, но нет initData → отдаём base.html
        # twa.js обнаружит /p/{slug} без initData и перезагрузит с initData
        templates = request.app.state.templates
        return HTMLResponse(templates.get_template("base.html").render())

    # Контекст для sticky header (Блок 1)
    bar_ctx: dict[str, Any] = {}
    if user and user.get("id"):
        bar_ctx = await _build_bar_context(user["id"])

    templates = request.app.state.templates

    # Определяем шаблон по типу страницы
    template_map = {
        "prediction": "prediction.html",
        "survey": "survey.html",
        "dashboard": "dashboard.html",
        "leaderboard": "leaderboard.html",
        "calendar": "calendar.html",
        "llm": "llm.html",
        "infra": "infra.html",
        "channel": "channel.html",
        "bcs": "bcs.html",
        "arena": "arena.html",
        "planner": "planner.html",
        "metrics": "metrics.html",
        "k8s": "k8s.html",
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
        bar_user=user,
        **bar_ctx,
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
    - "ai:{model}" → нейросеть (Simple Icons если доступна)
    - None → неизвестно

    Возвращает дополнительные поля если найдена иконка:
    - has_icon: bool — есть ли SVG-иконка из Simple Icons
    - icon_url: str — CDN URL белой SVG-иконки
    - icon_slug: str — slug для data-атрибутов
    """
    _no_icon = {"has_icon": False, "icon_url": "", "icon_slug": ""}

    if not created_by:
        return {"type": "unknown", "name": "", "emoji": "👤", "color": "#9E9E9E", **_no_icon}

    if created_by.startswith("ai:"):
        model = created_by[3:]
        icon = resolve_icon(model)
        if icon:
            return {
                "type": "ai",
                "name": get_display_name(model),
                "emoji": get_fallback_emoji(model),
                "color": "#" + adjusted_color(icon["hex"]),
                "has_icon": True,
                "icon_url": icon["icon_url"],
                "icon_slug": icon["slug"],
            }
        # Нет иконки в Simple Icons — emoji fallback
        return {
            "type": "ai",
            "name": get_display_name(model),
            "emoji": get_fallback_emoji(model),
            "color": "#6B7280",
            **_no_icon,
        }

    if created_by.startswith("admin:"):
        uid = created_by[6:]
        return {"type": "user", "name": "", "user_id": uid, "emoji": "👤", "color": "#4A90D9", **_no_icon}

    return {"type": "unknown", "name": created_by, "emoji": "👤", "color": "#9E9E9E", **_no_icon}


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


_ENTRY_TYPE_ICONS: dict[str, str] = {
    "event": "\U0001f4c5",      # 📅
    "task": "\U0001f4dd",        # 📝
    "trigger": "\U0001f514",     # 🔔
    "monitor": "\U0001f4e1",     # 📡
    "vote": "\U0001f5f3",        # 🗳
    "routine": "\U0001f504",     # 🔄
}

_ENTRY_TYPE_LABELS: dict[str, str] = {
    "event": "Событие",
    "task": "Задача",
    "trigger": "Триггер",
    "monitor": "Монитор",
    "vote": "Голосование",
    "routine": "Рутина",
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
    "planner": "Планер",
    "arena": "Арена",
    "channel": "Каналы",
    "bcs": "Биржа",
    "trade": "Трейдинг",
    "user": "Пользователь",
    "video": "Видео",
    "metrics": "Метрики",
}

_ENTRY_TYPE_COLORS: dict[str, str] = {
    "event": "#FFC107",
    "task": "#10B981",
    "trigger": "#F59E0B",
    "monitor": "#3B82F6",
    "vote": "#8B5CF6",
    "routine": "#6B7280",
}


def _build_widgets(entry: dict) -> list[dict]:
    """Собирает динамические виджеты из metadata/result/tags для карточки.

    Виджеты с брендовыми иконками (BTC, ETH) используют Simple Icons CDN.
    Остальные (ставка ЦБ, USD/RUB, результат) — emoji.
    """
    widgets: list[dict] = []
    meta = entry.get("metadata") or {}
    result = entry.get("result") or {}
    tags_lower = [t.lower() for t in (entry.get("tags") or [])]
    _no_icon = {"has_icon": False, "icon_url": ""}

    # Цена BTC (с Simple Icons)
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

    # Ключевая ставка ЦБ (нет бренда — emoji)
    kr = meta.get("key_rate_pct")
    if kr and any(t in tags_lower for t in ("цб", "цб рф", "ставка", "ключевая ставка", "cbr")):
        widgets.append({
            "type": "rate", "label": "Ставка ЦБ",
            "value": f"{kr}%", "change": None, "icon": "\U0001f3e6", **_no_icon,
        })

    # Курс USD/RUB (нет бренда — emoji)
    rub = meta.get("rub_usd")
    if rub and any(t in tags_lower for t in ("доллар", "usd", "валюта", "рубль", "forex")):
        widgets.append({
            "type": "rate", "label": "USD/RUB",
            "value": f"\u20bd{rub:.2f}", "change": meta.get("rub_usd_change"),
            "icon": "\U0001f4b1", **_no_icon,
        })

    # Тикер из BCS (пробуем Simple Icons по тикеру)
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

    # Результат триггера (emoji)
    if result and result.get("status"):
        rs = result["status"]
        icon = "\u2705" if rs == "success" else "\u274c" if rs == "failed" else "\u23f3"
        widgets.append({
            "type": "result", "label": "Результат",
            "value": rs, "change": None, "icon": icon, **_no_icon,
        })

    # Кастомные виджеты из metadata.widgets
    custom_widgets = meta.get("widgets")
    if isinstance(custom_widgets, list):
        for cw in custom_widgets[:10]:
            if not isinstance(cw, dict) or not cw.get("label") or not cw.get("value"):
                continue
            cw_icon_name = cw.get("icon")
            cw_icon = resolve_icon(cw_icon_name) if cw_icon_name else None
            widgets.append({
                "type": cw.get("type", "custom"),
                "label": str(cw["label"]),
                "value": str(cw["value"]),
                "change": cw.get("change"),
                "icon": cw.get("emoji", ""),
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
    # Резолв создателя
    entry["_creator"] = _resolve_creator(entry.get("created_by"))
    # v3: тип записи, статус триггера, источник, стоимость
    et = entry.get("entry_type", "event")
    entry["_entry_type_icon"] = _ENTRY_TYPE_ICONS.get(et, "")
    entry["_entry_type_label"] = _ENTRY_TYPE_LABELS.get(et, et)
    ts = entry.get("trigger_status", "pending")
    entry["_trigger_status_icon"] = _TRIGGER_STATUS_ICONS.get(ts, "")
    sm = entry.get("source_module") or ""
    entry["_source_label"] = _SOURCE_LABELS.get(sm, sm)
    ce = float(entry.get("cost_estimate") or 0)
    entry["_cost_display"] = f"${ce:.2f}" if ce > 0 else ""
    # v3: цвет типа
    entry["_entry_type_color"] = _ENTRY_TYPE_COLORS.get(et, "#FFC107")
    # v3: action/result JSON для fulldetail
    action = entry.get("action") or {}
    entry["_action_json"] = json.dumps(action, ensure_ascii=False, indent=2) if action else ""
    result = entry.get("result")
    entry["_result_json"] = json.dumps(result, ensure_ascii=False, indent=2) if result else ""
    # v3: trigger_at форматированная
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
    # v3: tick info для мониторов
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
    # v4: entry-level icon (Simple Icons)
    icon_name = entry.get("icon")
    if icon_name:
        icon_data = resolve_icon(icon_name)
        if icon_data:
            entry["_icon"] = {
                "has_icon": True,
                "icon_url": icon_data["icon_url"],
                "icon_slug": icon_data["slug"],
                "icon_color": "#" + adjusted_color(icon_data["hex"]),
            }
        else:
            entry["_icon"] = None
    else:
        entry["_icon"] = None
    # v3.1: participant из metadata
    meta = entry.get("metadata") or {}
    participant_raw = meta.get("participant")
    if participant_raw:
        entry["_participant"] = _resolve_creator(participant_raw)
        entry["_has_participant"] = True
    else:
        entry["_participant"] = None
        entry["_has_participant"] = False
    # v3.1: динамические виджеты
    entry["_widgets"] = _build_widgets(entry)
    entry["_widgets_json"] = json.dumps(entry["_widgets"], ensure_ascii=False) if entry["_widgets"] else ""
    # v3.1: urgency (триггер сработает в ближайший час)
    entry["_urgent"] = False
    if trigger_at and entry.get("trigger_status") == "pending":
        try:
            ta = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
            delta = (ta - datetime.now(timezone.utc)).total_seconds()
            entry["_urgent"] = 0 < delta < 3600
        except Exception:
            pass
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
        [str(user_id), str(chat_id)],
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


# ── Infrastructure Dashboard Proxy ──────────────────────────────


@router.get("/p/{slug}/infra/data")
async def infra_data_proxy(slug: str, request: Request):
    """Прокси для JS: данные LLM-инфраструктуры (с проверкой доступа)."""
    page = await pages_svc.get_page(slug)
    if not page or page["page_type"] != "infra":
        raise HTTPException(status_code=404, detail="Page not found")

    # Проверка доступа через единую систему
    init_data = request.headers.get("X-Init-Data", "")
    if init_data:
        user = validate_init_data(init_data, settings.get_bot_token())
        if not user or not user.get("id"):
            raise HTTPException(status_code=401, detail="Invalid initData")
        if not await check_page_access(user["id"], page):
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        # Без initData — проверяем есть ли вообще ограничения
        config = page.get("config") or {}
        if config.get("access_rules") or config.get("allowed_users"):
            raise HTTPException(status_code=401, detail="Authentication required")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.llm_core_url}/v1/dashboard")
            if r.status_code == 200:
                return JSONResponse(r.json())
    except Exception as e:
        logger.warning("infra_data_proxy: llmcore unavailable: %s", e)
    raise HTTPException(status_code=502, detail="LLM core unavailable")


# ── Nodes Registry API ────────────────────────────────────────


@router.get("/api/v1/nodes")
async def get_nodes():
    """Реестр публичных нод и маршрутов."""
    from ..services import nodes as nodes_svc
    return nodes_svc.get_full_config()


# ── Telegram Webhook Proxy ──────────────────────────────────────


@router.post("/telegram/webhook")
async def telegram_webhook_proxy(request: Request):
    """Proxy Telegram webhook → tgapi /telegram/webhook."""
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.tgapi_url}/telegram/webhook",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/telegram/webhook/{bot_id}")
async def telegram_webhook_proxy_by_bot(bot_id: int, request: Request):
    """Proxy Telegram webhook → tgapi /telegram/webhook/{bot_id}."""
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.tgapi_url}/telegram/webhook/{bot_id}",
                content=body,
                headers={"Content-Type": "application/json"},
            )
            return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Админка баннеров ──────────────────────────────────────────────────────


async def _require_owner(request: Request) -> dict[str, Any]:
    """Проверка project_owner для доступа к админке."""
    init_data = (
        request.query_params.get("initData", "")
        or request.headers.get("X-Init-Data", "")
    )
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Auth required")
    roles = await get_user_roles(user["id"])
    if "project_owner" not in roles:
        raise HTTPException(status_code=403, detail="Owner access required")
    return user


@router.get("/admin/banners", response_class=HTMLResponse)
async def admin_banners(request: Request):
    """Страница управления промо-баннерами (project_owner)."""
    user = await _require_owner(request)
    templates = request.app.state.templates
    banners = await get_all_banners()

    bar_ctx = await _build_bar_context(user["id"])
    html = templates.get_template("banner_admin.html").render(
        request=request,
        user=user,
        bar_user=user,
        **bar_ctx,
        banners=banners,
    )
    return HTMLResponse(html)


@router.post("/admin/banners/create")
async def admin_banner_create(request: Request):
    """Создать новый баннер."""
    user = await _require_owner(request)
    form = await request.form()

    tg_username = form.get("tg_username", "").strip()
    title = form.get("title", "").strip()
    link = form.get("link", "").strip()
    description = form.get("description", "").strip()
    priority = int(form.get("priority", 0))
    target_roles_raw = form.get("target_roles", "").strip()
    target_roles = [r.strip() for r in target_roles_raw.split(",") if r.strip()] if target_roles_raw else []

    if not tg_username or not title or not link:
        raise HTTPException(status_code=400, detail="username, title, link required")

    init_data = request.query_params.get("initData", "")
    await create_banner(
        tg_username=tg_username,
        title=title,
        link=link,
        created_by=user["id"],
        description=description,
        priority=priority,
        target_roles=target_roles,
    )
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )


@router.post("/admin/banners/{banner_id}/refresh-avatar")
async def admin_banner_refresh_avatar(banner_id: int, request: Request):
    """Обновить аватарку баннера."""
    await _require_owner(request)
    await update_banner_avatar(banner_id)
    init_data = request.query_params.get("initData", "")
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )


@router.post("/admin/banners/{banner_id}/toggle")
async def admin_banner_toggle(banner_id: int, request: Request):
    """Включить/выключить баннер."""
    await _require_owner(request)
    form = await request.form()
    active = form.get("active", "1") == "1"
    await toggle_banner(banner_id, active)
    init_data = request.query_params.get("initData", "")
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )


@router.post("/admin/banners/{banner_id}/delete")
async def admin_banner_delete(banner_id: int, request: Request):
    """Удалить баннер (мягкое удаление)."""
    await _require_owner(request)
    await delete_banner(banner_id)
    init_data = request.query_params.get("initData", "")
    return RedirectResponse(
        url=f"/admin/banners?initData={init_data}",
        status_code=303,
    )
