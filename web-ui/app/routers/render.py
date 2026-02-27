"""Публичные эндпоинты: рендер страниц, индивидуальные ссылки, сабмит форм."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..db import execute_returning, fetch_one, fetch_all
from ..handlers.registry import get_handler
from ..services import links as links_svc
from ..services import pages as pages_svc
from ..services.access import (
    check_page_access,
    get_user_roles,
)
from ..services.banner import get_active_banners
from ..services.telegram import resolve_tg_file_url

router = APIRouter(tags=["render"])
logger = logging.getLogger(__name__)
settings = get_settings()

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
    "datesale": "zapier",
    "governance": "civicrm",
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


async def _get_user_chats(user_id: int) -> list[dict[str, Any]]:
    """Чаты пользователя из chat_members + chats, с resolve фото.

    Приоритет аватарки: avatars (custom/local) → resolve_tg_file_url(file_id) → пусто.
    """
    rows = await fetch_all(
        """
        SELECT c.chat_id, c.title, c.username, c.member_count,
               c.photo_file_id, c.type, c.description,
               a.local_path AS avatar_local_path
        FROM chat_members cm
        JOIN chats c ON c.chat_id = cm.chat_id
        LEFT JOIN avatars a ON a.entity_type = 'chat' AND a.entity_id = c.chat_id
        WHERE cm.user_id = %s AND cm.status NOT IN ('left', 'kicked')
        ORDER BY cm.updated_at DESC NULLS LAST
        """,
        [str(user_id)],
    )
    chats: list[dict[str, Any]] = []
    for r in rows:
        chat = dict(r)
        # Приоритет: локальная аватарка → Telegram CDN → пусто
        if chat.get("avatar_local_path"):
            chat["_photo_url"] = f"/api/avatars/chat/{chat['chat_id']}"
        elif chat.get("photo_file_id"):
            try:
                chat["_photo_url"] = await resolve_tg_file_url(chat["photo_file_id"])
            except Exception:
                chat["_photo_url"] = ""
        else:
            chat["_photo_url"] = ""
        chats.append(chat)
    return chats


async def _build_chat_summaries(
    chats: list[dict], user_id: int,
) -> dict[str, dict[str, Any]]:
    """Лёгкий enrichment чатов: количество активных страниц + наличие governance."""
    if not chats:
        return {}

    chat_ids = [str(c["chat_id"]) for c in chats]

    # Количество активных страниц per-chat (через allowed_chats в config)
    page_rows = await fetch_all(
        """
        SELECT config->'access_rules'->'allowed_chats' AS chats,
               page_type
        FROM web_pages
        WHERE is_active = TRUE
          AND config->'access_rules'->'allowed_chats' IS NOT NULL
        """,
        [],
    )

    sums: dict[str, dict[str, Any]] = {}
    for row in page_rows:
        raw_chats = row.get("chats") or []
        if isinstance(raw_chats, str):
            import json as _json
            try:
                raw_chats = _json.loads(raw_chats)
            except Exception:
                raw_chats = []
        for cid in raw_chats:
            key = str(abs(int(cid)))
            if key not in sums:
                sums[key] = {"active_count": 0, "has_governance": False}
            sums[key]["active_count"] += 1
            if row.get("page_type") == "governance":
                sums[key]["has_governance"] = True

    return sums


async def _viewer_has_any_chats(user_id: int) -> bool:
    """Проверить что пользователь состоит хотя бы в одном чате."""
    row = await fetch_one(
        "SELECT 1 FROM chat_members WHERE user_id = %s AND status NOT IN ('left', 'kicked') LIMIT 1",
        [str(user_id)],
    )
    return row is not None


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Точка входа Mini App (Direct Link).

    Если есть start_param → twa.js делает клиентский редирект на /p/{slug}.
    Если есть initData (без start_param) → рендерим hub с чатами.
    Иначе → base.html (twa.js перенаправит с initData).
    """
    templates = request.app.state.templates

    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user:
        return HTMLResponse(templates.get_template("base.html").render())

    user_id = user.get("id")

    # Проверка: состоит ли пользователь хотя бы в одном чате
    if user_id and not await _viewer_has_any_chats(user_id):
        html = templates.get_template("stub.html").render(
            bar_user=user,
            mode="no_chats",
        )
        return HTMLResponse(html)

    roles = await get_user_roles(user_id) if user_id else set()

    # Чаты пользователя
    chats = await _get_user_chats(user_id) if user_id else []

    # Лёгкая сводка по чатам (активные страницы, governance)
    chat_summaries = await _build_chat_summaries(chats, user_id)

    # Контекст для sticky header
    bar_ctx = await _build_bar_context(user_id, roles) if user_id else {}

    # Промо-баннеры
    banners: list[dict] = []
    try:
        banners = await get_active_banners(roles)
    except Exception:
        logger.exception("Failed to load banners")

    html = templates.get_template("hub.html").render(
        user=user,
        bar_user=user,
        **bar_ctx,
        roles=sorted(roles),
        chats=chats,
        chat_summaries=chat_summaries,
        banners=banners,
        public_url=settings.public_url,
    )
    return HTMLResponse(html)


@router.get("/p/{slug}", response_class=HTMLResponse)
async def render_page(slug: str, request: Request):
    """Рендер веб-страницы (Telegram Mini App).

    Тонкий диспетчер: auth → access → handler.load_data → render.
    Конкретная логика каждого page_type — в handlers/.
    """
    page = await pages_svc.get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Governance pages → redirect в manage
    if page.get("page_type") == "governance":
        cfg = page.get("config") or {}
        chat_id = cfg.get("chat_id", "")
        if chat_id:
            qs = str(request.query_params)
            target = f"/c/{chat_id}/manage/governance"
            if qs:
                target += f"?{qs}"
            return RedirectResponse(target, status_code=302)

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

    # Контекст для sticky header (Tier 1)
    bar_ctx: dict[str, Any] = {}
    if user and user.get("id"):
        bar_ctx = await _build_bar_context(user["id"])

    templates = request.app.state.templates

    # Делегируем загрузку данных handler'у
    handler = get_handler(page["page_type"])
    template_name = handler.template if handler else "page.html"
    extra_data: dict[str, Any] = {}
    if handler:
        extra_data = await handler.load_data(page, user, request)

    template = templates.get_template(template_name)
    html = template.render(
        page=page,
        bar_user=user,
        **bar_ctx,
        config=page.get("config", {}),
        public_url=settings.public_url,
        **extra_data,
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
