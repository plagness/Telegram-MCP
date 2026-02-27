"""Пользовательские view-страницы: профиль, чат-хаб, chat data."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ..auth import validate_init_data
from ..config import get_settings
from ..db import fetch_all, fetch_one
from ..icons import resolve_icon
from ..orbital import compute_orbital
from ..services.access import (
    check_page_access,
    enrich_pages_for_hub,
    filter_pages_by_chat,
    get_accessible_pages,
    get_user_roles,
)
from ..services.telegram import resolve_tg_file_url
from ..handlers import proxy_delete, proxy_get, proxy_post
from .pins import _make_service_init_data
from .render import _build_bar_context, _HUB_TYPE_ICONS, _ROLE_LABELS, _viewer_has_any_chats

logger = logging.getLogger(__name__)

# Множество юзеров, для которых уже запущен enrich в этом процессе
_enriching_users: set[str] = set()


async def _enrich_user_from_initdata(user: dict[str, Any]) -> None:
    """Фоновое обогащение профиля из WebApp initData (allows_write_to_pm, photo_url)."""
    user_id = str(user.get("id"))
    if not user_id or user_id in _enriching_users:
        return
    _enriching_users.add(user_id)
    try:
        body: dict[str, Any] = {}
        if user.get("allows_write_to_pm") is not None:
            body["allows_write_to_pm"] = user["allows_write_to_pm"]
        if user.get("photo_url"):
            body["photo_url"] = user["photo_url"]
        if not body:
            return
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.tgapi_url}/v1/sync/user/{user_id}/enrich",
                json=body,
            )
    except Exception:
        logger.debug("enrich user %s из initData не удался", user_id, exc_info=True)

router = APIRouter(tags=["views"])
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/profile")
async def profile_redirect(request: Request):
    """Редирект /profile → /u/{user_id} (обратная совместимость)."""
    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None
    if user and user.get("id"):
        qs = f"?initData={init_data}" if init_data else ""
        return RedirectResponse(url=f"/u/{user['id']}{qs}", status_code=302)
    templates = request.app.state.templates
    return HTMLResponse(templates.get_template("base.html").render())


def _rewrite_api_avatar_urls(data: dict) -> None:
    """Переписать avatar_url из tgapi (/v1/avatars/.../file) в web proxy URL (/api/avatars/...)."""
    def _fix(url: str) -> str:
        # /v1/avatars/user/123/file → /api/avatars/user/123
        if url.startswith("/v1/"):
            url = "/api" + url[3:]
        if url.endswith("/file"):
            url = url[:-5]
        return url

    if data.get("avatar_url"):
        data["avatar_url"] = _fix(data["avatar_url"])
    if data.get("emoji_status_url"):
        # /v1/emoji/123/file → /api/emoji/123
        data["emoji_status_url"] = _fix(data["emoji_status_url"])
    for chat in data.get("chats") or []:
        if chat.get("chat_avatar_url"):
            chat["chat_avatar_url"] = _fix(chat["chat_avatar_url"])
    for chat in data.get("common_chats") or []:
        if chat.get("chat_avatar_url"):
            chat["chat_avatar_url"] = _fix(chat["chat_avatar_url"])


@router.get("/u/{target_user_id}", response_class=HTMLResponse)
async def user_profile_page(target_user_id: str, request: Request):
    """Страница профиля пользователя."""
    templates = request.app.state.templates

    init_data = request.query_params.get("initData", "")
    viewer = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not viewer or not viewer.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())

    viewer_id = viewer["id"]
    is_own = str(viewer_id) == str(target_user_id)

    # Проверка: viewer должен состоять хотя бы в одном чате
    if not await _viewer_has_any_chats(viewer_id):
        html = templates.get_template("stub.html").render(
            bar_user=viewer,
            mode="no_chats",
        )
        return HTMLResponse(html)

    # Фоновое обогащение профиля из initData
    asyncio.create_task(_enrich_user_from_initdata(viewer))

    # Загрузить профиль из tgapi
    try:
        params = {} if is_own else {"viewer_id": str(viewer_id)}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/users/{target_user_id}/profile",
                params=params,
            )
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail="User not found")
            r.raise_for_status()
            target = r.json()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Ошибка загрузки профиля %s: %s", target_user_id, exc)
        raise HTTPException(status_code=502, detail="Profile unavailable")

    _rewrite_api_avatar_urls(target)

    # Для чужого профиля: проверить наличие общих чатов
    if not is_own:
        common_chats_list = target.get("common_chats") or []
        if not common_chats_list:
            html = templates.get_template("stub.html").render(
                bar_user=viewer,
                mode="no_access",
            )
            return HTMLResponse(html)

    roles = await get_user_roles(int(target_user_id)) if target_user_id.lstrip("-").isdigit() else set()

    # Рейтинг — процент для прогресс-бара (условно level*10, max 100)
    rating_pct = min((target.get("rating_level") or 0) * 10, 100)

    # Данные для bar
    bar_ctx = await _build_bar_context(viewer_id, await get_user_roles(viewer_id))

    # Данные, доступные только владельцу профиля
    balance = None
    recent_tx: list = []
    system_pages: list[dict] = []
    is_privileged = False
    if is_own:
        balance_row = await fetch_one(
            "SELECT balance, total_deposited, total_won, total_lost, total_withdrawn "
            "FROM user_balances WHERE user_id = %s",
            [str(viewer_id)],
        )
        balance = balance_row or {
            "balance": 0, "total_deposited": 0, "total_won": 0,
            "total_lost": 0, "total_withdrawn": 0,
        }
        recent_tx = await fetch_all(
            "SELECT amount, transaction_type, description, created_at "
            "FROM balance_transactions WHERE user_id = %s "
            "ORDER BY created_at DESC LIMIT 5",
            [str(viewer_id)],
        )
        is_privileged = bool(roles & {"project_owner", "backend_dev", "tester"})
        if is_privileged:
            all_pages = await get_accessible_pages(viewer_id)
            enriched = await enrich_pages_for_hub(all_pages, viewer_id)
            system_pages = [p for p in enriched if p.get("_source_type") == "system"]
            for p in system_pages:
                icon_name = (p.get("config") or {}).get("icon") or _HUB_TYPE_ICONS.get(p["page_type"])
                p["_icon"] = resolve_icon(icon_name) if icon_name else None

    html = templates.get_template("user_profile.html").render(
        target=target,
        is_own=is_own,
        viewer=viewer,
        bar_user=viewer,
        **bar_ctx,
        roles=sorted(roles),
        role_labels=_ROLE_LABELS,
        rating_pct=rating_pct,
        balance=balance,
        recent_tx=recent_tx,
        user_chats=target.get("chats") or [],
        common_chats=target.get("common_chats") or [],
        system_pages=system_pages,
        is_privileged=is_privileged,
        miniapp_url=settings.miniapp_url or "",
    )
    return HTMLResponse(html)


# ── Обратная совместимость: /chat/{id} → /c/{id} ──

@router.get("/chat/{chat_id}")
async def chat_redirect(chat_id: str, request: Request):
    """Редирект со старого URL на новый чат-хаб."""
    qs = str(request.query_params) if request.query_params else ""
    target = f"/c/{chat_id}"
    if qs:
        target += f"?{qs}"
    return RedirectResponse(url=target, status_code=301)


# ── Чат-хаб: командный центр чата ──


async def _fetch_chat_info(chat_id: str) -> dict | None:
    """Загрузка расширенной информации о чате из tgapi."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.tgapi_url}/v1/chat-data/{chat_id}/info")
            if r.status_code == 200:
                data = r.json()
                _rewrite_avatar_urls(data)
                return data
    except Exception as e:
        logger.debug("chat info unavailable for %s: %s", chat_id, e)
    return None


async def _fetch_chat_stats(chat_id: str) -> dict | None:
    """Загрузка статистики чата за 30 дней из tgapi."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/chat-data/{chat_id}/stats",
                params={"period": "30d"},
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("stats") or data
    except Exception as e:
        logger.debug("chat stats unavailable for %s: %s", chat_id, e)
    return None


async def _fetch_governance(chat_id: str, init_data: str) -> dict | None:
    """Загрузка governance данных из Democracy.

    Нормализуем ответ Democracy API (dashboard.regime.type → regime.regime_type)
    чтобы шаблоны могли использовать простые пути.
    Используем service initData как fallback если пользовательский не работает.
    """
    if not settings.democracy_url:
        return None

    url = f"{settings.democracy_url}/v1/dashboard/{chat_id}"

    # Пробуем user initData, потом service initData
    tokens = [init_data, _make_service_init_data()]
    raw = None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for token in tokens:
                if not token:
                    continue
                r = await client.get(url, headers={"X-Init-Data": token})
                if r.status_code == 200:
                    raw = r.json()
                    break
                logger.debug("governance %s status=%s for token type", chat_id, r.status_code)
    except Exception as e:
        logger.debug("governance data unavailable for chat %s: %s", chat_id, e)
        return None

    if not raw:
        return None

    dash = raw.get("dashboard") or {}
    regime_raw = dash.get("regime") or {}
    stats_raw = dash.get("stats") or {}
    treasury_raw = dash.get("treasury") or {}

    # Резолвим ruler_id → username через таблицу users
    ruler_id = regime_raw.get("ruler_id")
    leader_username = ""
    if ruler_id:
        user_row = await fetch_one(
            "SELECT username FROM users WHERE user_id = %s",
            [str(ruler_id)],
        )
        if user_row and user_row.get("username"):
            leader_username = user_row["username"]

    return {
        "regime": {
            "regime_type": regime_raw.get("type", ""),
            "ruler_id": ruler_id,
            "leader_username": leader_username,
        },
        "stats": {
            "citizens": stats_raw.get("citizen_count", 0),
            "active_proposals": stats_raw.get("active_proposals", 0),
            "treasury": treasury_raw.get("balance", 0),
        },
        "dashboard": dash,
        "constitution": raw.get("constitution"),
        "top_citizens": raw.get("top_citizens"),
        "council": raw.get("council"),
        "petitions": raw.get("petitions"),
        "delegations": raw.get("delegations"),
        "engine_info": raw.get("engine_info"),
        "_raw": raw,
    }


async def _fetch_upcoming_events(calendar_id: int, limit: int = 3) -> list:
    """Загрузить ближайшие события из календаря чата.

    Если нет будущих событий — fallback на последние прошедшие.
    Возвращает list[dict] с флагом _past=True для прошедших.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Пробуем будущие события
            r = await client.get(
                f"{settings.tgapi_url}/v1/calendar/entries",
                params={"calendar_id": calendar_id, "start": now, "limit": limit},
            )
            if r.status_code == 200:
                data = r.json()
                entries = (data.get("items") or data.get("entries") or [])[:limit]
                if entries:
                    return entries

            # Fallback: последние прошедшие события
            r2 = await client.get(
                f"{settings.tgapi_url}/v1/calendar/entries",
                params={
                    "calendar_id": calendar_id,
                    "end": now,
                    "limit": limit,
                    "order": "desc",
                },
            )
            if r2.status_code == 200:
                data2 = r2.json()
                past = (data2.get("items") or data2.get("entries") or [])[:limit]
                for e in past:
                    e["_past"] = True
                return past
    except Exception as e:
        logger.debug("calendar entries unavailable for cal %s: %s", calendar_id, e)
    return []


async def _fetch_chat_extensions(chat_id: str) -> list:
    """Загрузить расширения (MCP-инструменты) активные в чате."""
    if not settings.datesale_url:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.datesale_url}/v1/chats/tg/{chat_id}/plugins",
            )
            if r.status_code == 200:
                return r.json().get("plugins", [])
    except Exception as e:
        logger.debug("chat extensions unavailable for %s: %s", chat_id, e)
    return []


def _compute_hotness(page: dict, meta: dict) -> float:
    """Вычислить \"горячесть\" temporal элемента (0.0–1.0).

    Формула: recency*0.25 + engagement*0.35 + urgency*0.30 + type_weight*0.10
    """
    now = datetime.now(timezone.utc)

    # Recency: свежее = выше (на основе created_at страницы)
    created_str = page.get("created_at") or ""
    recency = 0.5
    if created_str:
        try:
            if isinstance(created_str, datetime):
                created = created_str
            else:
                created = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_hours = max((now - created).total_seconds() / 3600, 0)
            recency = max(1.0 - age_hours / 168, 0)  # неделя = 0
        except (ValueError, TypeError):
            pass

    # Engagement: ставки/голоса/ответы
    pool = float(meta.get("total_pool") or 0)
    bet_count = int(meta.get("bet_count") or 0)
    submission_count = int(meta.get("submission_count") or 0)
    votes_count = int(meta.get("votes_count") or 0)
    popularity = bet_count + submission_count + votes_count
    engagement = min((popularity / 30 + pool / 2000) / 2 + 0.05, 1.0)

    # Urgency: время до дедлайна
    urgency = 0.0
    deadline_str = meta.get("deadline") or ""
    if deadline_str:
        try:
            if isinstance(deadline_str, datetime):
                dl = deadline_str
            else:
                dl = datetime.fromisoformat(str(deadline_str).replace("Z", "+00:00"))
            if dl.tzinfo is None:
                dl = dl.replace(tzinfo=timezone.utc)
            remaining = (dl - now).total_seconds()
            if remaining > 0:
                hours_left = remaining / 3600
                if hours_left < 1:
                    urgency = 1.0
                elif hours_left < 24:
                    urgency = 0.8 - 0.5 * math.log10(hours_left + 1)
                elif hours_left < 168:
                    urgency = 0.3 * (1 - hours_left / 168)
        except (ValueError, TypeError):
            pass

    # Type weight
    pt = page.get("page_type", "")
    type_weights = {
        "prediction": 1.0, "governance": 0.9, "survey": 0.7, "calendar": 0.6,
    }
    type_weight = type_weights.get(pt, 0.5)

    return recency * 0.25 + engagement * 0.35 + urgency * 0.30 + type_weight * 0.10


def _build_search_index(
    chat_pages: list[dict], chat_id: str,
    governance: dict | None, governance_slug: str | None,
) -> list[dict]:
    """Собрать JSON-индекс для клиентского поиска."""
    index: list[dict] = []

    # Иконки по типу страниц
    type_icons = {
        "prediction": "\U0001f3af", "calendar": "\U0001f4c5",
        "survey": "\U0001f4dd", "leaderboard": "\U0001f3c6",
        "dashboard": "\U0001f4ca", "llm": "\U0001f916",
        "governance": "\U0001f3db", "page": "\U0001f4c4",
    }

    # Страницы
    for p in chat_pages:
        pt = p.get("page_type", "page")
        desc = ""
        if p.get("config") and p["config"].get("description"):
            desc = p["config"]["description"]
        index.append({
            "type": "page",
            "title": p.get("title", ""),
            "url": f"/p/{p['slug']}",
            "icon": type_icons.get(pt, "\U0001f4c4"),
            "keywords": f"{p.get('title', '')} {pt} {desc}".lower(),
        })

    # Governance действия
    if governance and governance_slug:
        index.append({
            "type": "action", "title": "Предложить закон",
            "url": f"/p/{governance_slug}",
            "icon": "\U0001f4dc",
            "keywords": "предложить закон proposal governance предложение",
        })
        index.append({
            "type": "action", "title": "Голосовать",
            "url": f"/p/{governance_slug}",
            "icon": "\U0001f5f3",
            "keywords": "голосовать vote голосование",
        })

    # Навигация
    index.append({
        "type": "nav", "title": "Управление чатом",
        "url": f"/c/{chat_id}/manage",
        "icon": "\u2699",
        "keywords": "данные участники сообщения статистика управление настройки manage",
    })

    return index


def _build_categories(
    chat_pages: list[dict], governance: dict | None,
) -> dict[str, int]:
    """Подсчёт элементов по категориям."""
    cats: dict[str, int] = {
        "predictions": 0, "surveys": 0, "calendars": 0,
        "governance": 1 if governance else 0,
        "leaderboards": 0, "data": 1,
    }
    for p in chat_pages:
        pt = p.get("page_type", "")
        if pt == "prediction":
            cats["predictions"] += 1
        elif pt == "survey":
            cats["surveys"] += 1
        elif pt == "calendar":
            cats["calendars"] += 1
        elif pt == "leaderboard":
            cats["leaderboards"] += 1
    return cats


@router.get("/c/{chat_id}", response_class=HTMLResponse)
async def chat_hub(chat_id: str, request: Request):
    """Чат-хаб: командный центр чата с hero, поиском, hot items, категориями."""
    templates = request.app.state.templates

    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())

    user_id = user["id"]
    roles = await get_user_roles(user_id)

    # Фоновое обогащение профиля из initData (allows_write_to_pm, photo_url)
    asyncio.create_task(_enrich_user_from_initdata(user))

    # Проверяем членство + загружаем чат (необходимо до parallel gather)
    member_row = await fetch_one(
        """
        SELECT cm.status FROM chat_members cm
        WHERE cm.user_id = %s AND cm.chat_id = %s
          AND cm.status NOT IN ('left', 'kicked')
        """,
        [str(user_id), str(chat_id)],
    )
    if not member_row:
        raise HTTPException(status_code=403, detail="Not a chat member")

    chat = await fetch_one(
        """
        SELECT c.chat_id, c.title, c.username, c.member_count,
               c.photo_file_id, c.type, c.description,
               a.local_path AS avatar_local_path
        FROM chats c
        LEFT JOIN avatars a ON a.entity_type = 'chat' AND a.entity_id = c.chat_id
        WHERE c.chat_id = %s
        """,
        [str(chat_id)],
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = dict(chat)
    # Аватар: avatars (local) → Telegram CDN → пусто
    if chat.get("avatar_local_path"):
        chat["_photo_url"] = f"/api/avatars/chat/{chat_id}"
    elif chat.get("photo_file_id"):
        try:
            chat["_photo_url"] = await resolve_tg_file_url(chat["photo_file_id"])
        except Exception:
            chat["_photo_url"] = ""
    else:
        chat["_photo_url"] = ""

    # Является ли пользователь админом чата
    is_admin = member_row.get("status") in ("administrator", "creator")

    # ── Параллельная загрузка данных ──
    chat_info, stats, governance, (chat_pages, temporal_pages, regular_pages), chat_extensions = (
        await asyncio.gather(
            _fetch_chat_info(chat_id),
            _fetch_chat_stats(chat_id),
            _fetch_governance(chat_id, init_data),
            _load_chat_pages(user_id, chat_id, chat),
            _fetch_chat_extensions(chat_id),
        )
    )

    bar_ctx = await _build_bar_context(user_id, roles)

    # Hotness scoring для temporal pages + обогащение meta
    for p in temporal_pages:
        meta = p.get("_meta") or {}
        p["_hotness"] = _compute_hotness(p, meta)
        # top_option_pct для predictions (pie chart)
        if p.get("page_type") == "prediction":
            options = meta.get("options") or []
            total_pool = float(meta.get("total_pool") or 0)
            if options and total_pool > 0:
                top = max(options, key=lambda o: float(o.get("total_amount", 0)))
                meta["top_option_pct"] = round(
                    float(top.get("total_amount", 0)) / total_pool * 100
                )
        # icon_slug для SVG-иконок
        p["_icon_slug"] = _HUB_TYPE_ICONS.get(p.get("page_type", ""), "readme")
    temporal_pages.sort(key=lambda x: x.get("_hotness", 0), reverse=True)
    temporal_pages = temporal_pages[:5]  # max 5 hot items

    # Governance slug + Calendar slug/events
    governance_slug = None
    calendar_slug = None
    calendar_id = None
    for p in chat_pages:
        pt = p.get("page_type")
        if pt == "governance" and not governance_slug:
            governance_slug = p.get("slug")
        elif pt == "calendar" and not calendar_slug:
            calendar_slug = p.get("slug")
            calendar_id = (p.get("config") or {}).get("calendar_id")

    # Загрузить ближайшие события из календаря
    upcoming_events: list = []
    if calendar_id:
        upcoming_events = await _fetch_upcoming_events(calendar_id, limit=3)

    # Search index + Categories
    search_index = _build_search_index(chat_pages, chat_id, governance, governance_slug)
    categories = _build_categories(chat_pages, governance)

    # Icon slugs для категорий (search dropdown)
    cat_icon_slugs = {
        "prediction": _HUB_TYPE_ICONS.get("prediction", "target"),
        "survey": _HUB_TYPE_ICONS.get("survey", "googleforms"),
        "calendar": _HUB_TYPE_ICONS.get("calendar", "googlecalendar"),
        "leaderboard": _HUB_TYPE_ICONS.get("leaderboard", "openbadges"),
        "governance": _HUB_TYPE_ICONS.get("governance", "civicrm"),
    }

    # Filter view (категорийная навигация)
    filter_type = request.query_params.get("filter", "")
    filtered_pages: list[dict] = []
    if filter_type:
        filtered_pages = [p for p in chat_pages if p.get("page_type") == filter_type]

    html = templates.get_template("chat.html").render(
        user=user,
        bar_user=user,
        **bar_ctx,
        roles=sorted(roles),
        chat=chat,
        chat_info=chat_info or {},
        stats=stats or {},
        pages=regular_pages,
        temporal_pages=temporal_pages,
        governance=governance,
        governance_slug=governance_slug,
        categories=categories,
        cat_icon_slugs=cat_icon_slugs,
        search_index_json=json.dumps(search_index, ensure_ascii=False).replace("</", "<\\/"),
        public_url=settings.public_url,
        is_admin=is_admin,
        filter_type=filter_type,
        filtered_pages=filtered_pages,
        upcoming_events=upcoming_events,
        calendar_slug=calendar_slug,
        chat_extensions=chat_extensions,
    )
    return HTMLResponse(html)


async def _load_chat_pages(
    user_id: int, chat_id: str, chat: dict,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Загрузка и обработка страниц чата.

    Возвращает (all_chat_pages, temporal_pages, regular_pages).
    """
    all_pages = await get_accessible_pages(user_id)
    enriched = await enrich_pages_for_hub(all_pages, user_id)
    chat_pages = filter_pages_by_chat(enriched, chat_id)

    for p in chat_pages:
        icon_name = (p.get("config") or {}).get("icon") or _HUB_TYPE_ICONS.get(p["page_type"])
        p["_icon"] = resolve_icon(icon_name) if icon_name else None

    # Temporal events
    temporal_pages: list[dict] = []
    for i, p in enumerate(chat_pages):
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
            is_temporal = True

        if is_temporal:
            p["_chat_photo_url"] = chat.get("_photo_url", "")
            p["_orbital"] = compute_orbital(
                pt, meta, index=i,
                config=p.get("config"),
                chat_photo_url=p.get("_chat_photo_url", ""),
            )
            temporal_pages.append(p)

    regular_pages = [
        p for p in chat_pages
        if p not in temporal_pages and p.get("page_type") != "calendar"
    ]
    return chat_pages, temporal_pages, regular_pages


# ── Chat Data: страница + proxy API ──


async def _require_chat_member(user_id: int, chat_id: str) -> None:
    """Проверяем, что пользователь — участник чата."""
    row = await fetch_one(
        """
        SELECT 1 FROM chat_members
        WHERE user_id = %s AND chat_id = %s
          AND status NOT IN ('left', 'kicked')
        """,
        [str(user_id), str(chat_id)],
    )
    if not row:
        raise HTTPException(status_code=403, detail="Not a chat member")


async def _resolve_chat_for_data(chat_id: str, request: Request) -> tuple[dict, dict]:
    """Аутентификация + загрузка данных чата для chat data pages."""
    init_data = request.query_params.get("initData", "") or request.headers.get("X-Init-Data", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Auth required")

    await _require_chat_member(user["id"], chat_id)

    chat = await fetch_one(
        """
        SELECT chat_id, title, username, member_count,
               photo_file_id, type, description
        FROM chats WHERE chat_id = %s
        """,
        [str(chat_id)],
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = dict(chat)
    # Аватарка: avatars → CDN → пусто
    avatar_row = await fetch_one(
        "SELECT local_path FROM avatars WHERE entity_type = 'chat' AND entity_id = %s",
        [str(chat_id)],
    )
    if avatar_row and avatar_row.get("local_path"):
        chat["_photo_url"] = f"/api/avatars/chat/{chat_id}"
    elif chat.get("photo_file_id"):
        try:
            chat["_photo_url"] = await resolve_tg_file_url(chat["photo_file_id"])
        except Exception:
            chat["_photo_url"] = ""
    else:
        chat["_photo_url"] = ""

    return chat, user


@router.get("/c/{chat_id}/manage", response_class=HTMLResponse)
async def chat_manage_base(chat_id: str, request: Request):
    """Управление чатом — корневой маршрут."""
    return await _chat_manage_impl(chat_id, request, section="")


@router.get("/c/{chat_id}/manage/{section:path}", response_class=HTMLResponse)
async def chat_manage_section(chat_id: str, request: Request, section: str = ""):
    """Управление чатом — маршрут с секцией."""
    return await _chat_manage_impl(chat_id, request, section=section)


async def _chat_manage_impl(chat_id: str, request: Request, section: str = ""):
    """Управление чатом — объединённая страница (governance + chat data)."""
    templates = request.app.state.templates

    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())

    user_id = user["id"]

    # Членство + статус (admin)
    member_row = await fetch_one(
        """
        SELECT cm.status FROM chat_members cm
        WHERE cm.user_id = %s AND cm.chat_id = %s
          AND cm.status NOT IN ('left', 'kicked')
        """,
        [str(user_id), str(chat_id)],
    )
    if not member_row:
        raise HTTPException(status_code=403, detail="Not a chat member")

    is_admin = member_row.get("status") in ("administrator", "creator")

    chat = await fetch_one(
        """
        SELECT c.chat_id, c.title, c.username, c.member_count,
               c.photo_file_id, c.type, c.description,
               a.local_path AS avatar_local_path
        FROM chats c
        LEFT JOIN avatars a ON a.entity_type = 'chat' AND a.entity_id = c.chat_id
        WHERE c.chat_id = %s
        """,
        [str(chat_id)],
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = dict(chat)
    if chat.get("avatar_local_path"):
        chat["_photo_url"] = f"/api/avatars/chat/{chat_id}"
    elif chat.get("photo_file_id"):
        try:
            chat["_photo_url"] = await resolve_tg_file_url(chat["photo_file_id"])
        except Exception:
            chat["_photo_url"] = ""
    else:
        chat["_photo_url"] = ""

    # Параллельная загрузка
    roles = await get_user_roles(user_id)
    chat_info, stats, governance, chat_extensions = await asyncio.gather(
        _fetch_chat_info(chat_id),
        _fetch_chat_stats(chat_id),
        _fetch_governance(chat_id, init_data),
        _fetch_chat_extensions(chat_id),
    )

    bar_ctx = await _build_bar_context(user_id, roles)

    # Governance slug
    all_pages = await get_accessible_pages(user_id)
    enriched = await enrich_pages_for_hub(all_pages, user_id)
    chat_pages = filter_pages_by_chat(enriched, chat_id)
    governance_slug = None
    for p in chat_pages:
        if p.get("page_type") == "governance":
            governance_slug = p.get("slug")
            break

    html = templates.get_template("chat_manage.html").render(
        user=user,
        bar_user=user,
        **bar_ctx,
        roles=sorted(roles),
        chat=chat,
        chat_info=chat_info or {},
        stats=stats or {},
        governance=governance,
        governance_slug=governance_slug,
        chat_extensions=chat_extensions,
        public_url=settings.public_url,
        is_admin=is_admin,
        active_section=section,
    )
    return HTMLResponse(html)


@router.get("/c/{chat_id}/data")
async def chat_data_redirect(chat_id: str, request: Request):
    """Редирект со старого Chat Data на manage."""
    qs = str(request.query_params) if request.query_params else ""
    target = f"/c/{chat_id}/manage"
    if qs:
        target += f"?{qs}"
    return RedirectResponse(url=target, status_code=301)


# ── Chat Data API proxy (tgweb → tgapi) ──


async def _proxy_chatdata(chat_id: str, endpoint: str, request: Request) -> JSONResponse:
    """Proxy запрос к tgapi /v1/chat-data/{chat_id}/{endpoint}."""
    init_data = request.headers.get("X-Init-Data", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return JSONResponse({"error": "Auth required"}, status_code=401)

    await _require_chat_member(user["id"], chat_id)

    # Передаём query params
    params = dict(request.query_params)
    params.pop("initData", None)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/chat-data/{chat_id}/{endpoint}",
                params=params,
            )
            data = r.json()
            # Подменяем avatar_url (локальный путь) на proxy URL
            if isinstance(data, dict) and endpoint in ("members", "info"):
                _rewrite_avatar_urls(data)
            return JSONResponse(content=data, status_code=r.status_code)
    except Exception as e:
        logger.exception("chatdata proxy error: %s/%s", chat_id, endpoint)
        return JSONResponse({"error": str(e)}, status_code=502)


def _rewrite_avatar_urls(data: dict) -> None:
    """Заменить локальные пути аватарок на proxy URL."""
    # info: avatar_url → /api/avatars/chat/{id}
    if data.get("avatar_url") and data["avatar_url"].startswith("/data/avatars/"):
        entity_id = data.get("chat_id", "")
        data["avatar_url"] = f"/api/avatars/chat/{entity_id}"

    # members: items[].avatar_url → /api/avatars/user/{id}
    for item in data.get("items", []):
        if item.get("avatar_url") and item["avatar_url"].startswith("/data/avatars/"):
            uid = item.get("user_id", "")
            item["avatar_url"] = f"/api/avatars/user/{uid}"


@router.get("/api/chatdata/{chat_id}/info")
async def chatdata_info(chat_id: str, request: Request):
    return await _proxy_chatdata(chat_id, "info", request)


@router.get("/api/chatdata/{chat_id}/members")
async def chatdata_members(chat_id: str, request: Request):
    return await _proxy_chatdata(chat_id, "members", request)


@router.get("/api/chatdata/{chat_id}/messages")
async def chatdata_messages(chat_id: str, request: Request):
    return await _proxy_chatdata(chat_id, "messages", request)


@router.get("/api/chatdata/{chat_id}/reactions")
async def chatdata_reactions(chat_id: str, request: Request):
    return await _proxy_chatdata(chat_id, "reactions", request)


@router.get("/api/chatdata/{chat_id}/events")
async def chatdata_events(chat_id: str, request: Request):
    return await _proxy_chatdata(chat_id, "events", request)


@router.get("/api/chatdata/{chat_id}/stats")
async def chatdata_stats(chat_id: str, request: Request):
    return await _proxy_chatdata(chat_id, "stats", request)


@router.get("/api/chatdata/{chat_id}/citizens")
async def chatdata_citizens(chat_id: str, request: Request):
    """Proxy граждан → Democracy /v1/citizens/{chatID}."""
    init_data = request.headers.get("X-Init-Data", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return JSONResponse({"error": "Auth required"}, status_code=401)

    await _require_chat_member(user["id"], chat_id)

    if not settings.democracy_url:
        return JSONResponse({"items": [], "total": 0})

    # Параметры пагинации
    params: dict = {}
    for key in ("status", "limit", "offset"):
        val = request.query_params.get(key)
        if val:
            params[key] = val

    service_init = _make_service_init_data()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.democracy_url}/v1/citizens/{chat_id}",
                params=params,
                headers={"X-Init-Data": service_init},
            )
            if r.status_code == 200:
                data = r.json()
                # Нормализуем: citizens → items для единообразия с members API
                items = data.get("citizens") or data.get("items") or []
                return JSONResponse({
                    "items": items,
                    "total": data.get("total", len(items)),
                })
            return JSONResponse(
                {"items": [], "total": 0, "error": f"Democracy API: {r.status_code}"},
                status_code=r.status_code,
            )
    except Exception as e:
        logger.exception("citizens proxy error: %s", chat_id)
        return JSONResponse({"error": str(e)}, status_code=502)


@router.post("/api/chatdata/{chat_id}/sync")
async def chatdata_sync(chat_id: str, request: Request):
    """Proxy синхронизации → tgapi /v1/sync/chat/{chat_id}."""
    init_data = request.headers.get("X-Init-Data", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return JSONResponse({"error": "Auth required"}, status_code=401)

    await _require_chat_member(user["id"], chat_id)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{settings.tgapi_url}/v1/sync/chat/{chat_id}",
            )
            return JSONResponse(content=r.json(), status_code=r.status_code)
    except Exception as e:
        logger.exception("chatdata sync proxy error: %s", chat_id)
        return JSONResponse({"error": str(e)}, status_code=502)


# ── Governance API proxy (tgweb → democracycore) ──
# Chat-id-based routes для GovernanceModule на chat_manage.html


async def _gov_auth(chat_id: str, request: Request, require_init: bool = False) -> str:
    """Авторизация + проверка членства для governance proxy.

    Возвращает initData строку.
    """
    init_data = request.headers.get("X-Init-Data", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Auth required")

    if require_init and not init_data:
        raise HTTPException(status_code=401, detail="initData required")

    await _require_chat_member(user["id"], chat_id)
    return init_data


@router.get("/api/governance/{chat_id}/data")
async def gov_data(chat_id: str, request: Request):
    """Dashboard данные из Democracy."""
    init_data = await _gov_auth(chat_id, request)
    headers = {"X-Init-Data": init_data} if init_data else {}
    return await proxy_get(f"{settings.democracy_url}/v1/dashboard/{chat_id}", headers=headers)


@router.post("/api/governance/{chat_id}/vote")
async def gov_vote(chat_id: str, request: Request):
    """Голосование."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    pid = body.get("proposal_id")
    if not pid:
        raise HTTPException(status_code=400, detail="proposal_id required")
    return await proxy_post(
        f"{settings.democracy_url}/v1/proposals/{pid}/vote",
        json_body={"choice": body.get("choice", "")},
        headers={"X-Init-Data": init_data},
    )


@router.delete("/api/governance/{chat_id}/vote")
async def gov_vote_delete(chat_id: str, request: Request):
    """Отмена голоса."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    pid = body.get("proposal_id")
    if not pid:
        raise HTTPException(status_code=400, detail="proposal_id required")
    return await proxy_delete(
        f"{settings.democracy_url}/v1/proposals/{pid}/vote",
        headers={"X-Init-Data": init_data},
    )


@router.get("/api/governance/{chat_id}/proposal/{proposal_id}")
async def gov_proposal_detail(chat_id: str, proposal_id: int, request: Request):
    """Детали предложения."""
    init_data = await _gov_auth(chat_id, request)
    headers = {"X-Init-Data": init_data} if init_data else {}
    return await proxy_get(
        f"{settings.democracy_url}/v1/proposals/{proposal_id}", headers=headers,
    )


@router.post("/api/governance/{chat_id}/proposal")
async def gov_proposal_create(chat_id: str, request: Request):
    """Создание предложения."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    return await proxy_post(
        f"{settings.democracy_url}/v1/proposals",
        json_body=body,
        headers={"X-Init-Data": init_data},
    )


@router.post("/api/governance/{chat_id}/argument")
async def gov_argument(chat_id: str, request: Request):
    """Добавление аргумента."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    pid = body.get("proposal_id")
    if not pid:
        raise HTTPException(status_code=400, detail="proposal_id required")
    return await proxy_post(
        f"{settings.democracy_url}/v1/proposals/{pid}/arguments",
        json_body={"side": body.get("side", ""), "text": body.get("text", "")},
        headers={"X-Init-Data": init_data},
    )


@router.post("/api/governance/{chat_id}/setup")
async def gov_setup(chat_id: str, request: Request):
    """Установка режима правления."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    return await proxy_post(
        f"{settings.democracy_url}/v1/governance/{chat_id}/setup",
        json_body=body,
        headers={"X-Init-Data": init_data},
    )


@router.post("/api/governance/{chat_id}/change-regime")
async def gov_change_regime(chat_id: str, request: Request):
    """Смена режима правления."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    return await proxy_post(
        f"{settings.democracy_url}/v1/governance/{chat_id}/change-regime",
        json_body=body,
        headers={"X-Init-Data": init_data},
    )


@router.post("/api/governance/{chat_id}/sync")
async def gov_sync(chat_id: str, request: Request):
    """Синхронизация участников."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    return await proxy_post(
        f"{settings.democracy_url}/v1/governance/{chat_id}/sync",
        json_body=None,
        headers={"X-Init-Data": init_data},
        timeout=15.0,
    )


@router.post("/api/governance/{chat_id}/petition")
async def gov_petition_create(chat_id: str, request: Request):
    """Создание петиции."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    return await proxy_post(
        f"{settings.democracy_url}/v1/petitions/{chat_id}",
        json_body=body,
        headers={"X-Init-Data": init_data},
    )


@router.get("/api/governance/{chat_id}/petition/{petition_id}")
async def gov_petition_detail(chat_id: str, petition_id: int, request: Request):
    """Детали петиции."""
    init_data = await _gov_auth(chat_id, request)
    headers = {"X-Init-Data": init_data} if init_data else {}
    return await proxy_get(
        f"{settings.democracy_url}/v1/petitions/{chat_id}/{petition_id}",
        headers=headers,
    )


@router.post("/api/governance/{chat_id}/petition/{petition_id}/sign")
async def gov_petition_sign(chat_id: str, petition_id: int, request: Request):
    """Подписать петицию."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    return await proxy_post(
        f"{settings.democracy_url}/v1/petitions/{chat_id}/{petition_id}/sign",
        json_body=None,
        headers={"X-Init-Data": init_data},
    )


@router.post("/api/governance/{chat_id}/delegate")
async def gov_delegate_create(chat_id: str, request: Request):
    """Делегировать голос."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    return await proxy_post(
        f"{settings.democracy_url}/v1/delegations/{chat_id}",
        json_body=body,
        headers={"X-Init-Data": init_data},
    )


@router.delete("/api/governance/{chat_id}/delegate")
async def gov_delegate_delete(chat_id: str, request: Request):
    """Отозвать делегирование."""
    init_data = await _gov_auth(chat_id, request, require_init=True)
    body = await request.json()
    qs = "&".join(f"{k}={v}" for k, v in body.items())
    url = f"{settings.democracy_url}/v1/delegations/{chat_id}"
    if qs:
        url += f"?{qs}"
    return await proxy_delete(url, headers={"X-Init-Data": init_data})


@router.get("/api/avatars/{entity_type}/{entity_id}")
async def avatar_proxy(entity_type: str, entity_id: str):
    """Proxy аватарки → tgapi /v1/avatars/{entity_type}/{entity_id}/file."""
    if entity_type not in ("user", "chat"):
        return Response(status_code=400)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/avatars/{entity_type}/{entity_id}/file",
            )
            if r.status_code != 200:
                return Response(status_code=r.status_code)
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=3600"},
            )
    except Exception:
        return Response(status_code=502)


@router.get("/api/emoji/{emoji_id}")
async def emoji_proxy(emoji_id: str):
    """Proxy кастомного эмодзи → tgapi /v1/emoji/{emoji_id}/file."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{settings.tgapi_url}/v1/emoji/{emoji_id}/file",
            )
            if r.status_code != 200:
                return Response(status_code=r.status_code)
            return Response(
                content=r.content,
                media_type=r.headers.get("content-type", "image/webp"),
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        return Response(status_code=502)
