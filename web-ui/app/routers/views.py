"""Пользовательские view-страницы: профиль, чат."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..db import fetch_all, fetch_one
from ..icons import resolve_icon
from ..services.access import (
    check_page_access,
    enrich_pages_for_hub,
    filter_pages_by_chat,
    get_accessible_pages,
    get_user_roles,
)
from ..services.telegram import resolve_tg_file_url
from .render import _build_bar_context, _HUB_TYPE_ICONS, _ROLE_LABELS

router = APIRouter(tags=["views"])
logger = logging.getLogger(__name__)
settings = get_settings()


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

    # Системные страницы для привилегированных пользователей
    system_pages: list[dict] = []
    is_privileged = bool(roles & {"project_owner", "backend_dev", "tester"})
    if is_privileged:
        all_pages = await get_accessible_pages(user_id)
        enriched = await enrich_pages_for_hub(all_pages, user_id)
        system_pages = [p for p in enriched if p.get("_source_type") == "system"]
        for p in system_pages:
            icon_name = (p.get("config") or {}).get("icon") or _HUB_TYPE_ICONS.get(p["page_type"])
            p["_icon"] = resolve_icon(icon_name) if icon_name else None

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
        system_pages=system_pages,
        is_privileged=is_privileged,
    )
    return HTMLResponse(html)


@router.get("/chat/{chat_id}", response_class=HTMLResponse)
async def chat_detail(chat_id: str, request: Request):
    """Детальная страница чата: привязанные страницы + Integrat-плагины."""
    templates = request.app.state.templates

    init_data = request.query_params.get("initData", "")
    user = validate_init_data(init_data, settings.get_bot_token()) if init_data else None

    if not user or not user.get("id"):
        return HTMLResponse(templates.get_template("base.html").render())

    user_id = user["id"]
    roles = await get_user_roles(user_id)

    # Проверяем что user — member чата
    member_row = await fetch_one(
        """
        SELECT 1 FROM chat_members
        WHERE user_id = %s AND chat_id = %s
          AND status NOT IN ('left', 'kicked')
        """,
        [str(user_id), str(chat_id)],
    )
    if not member_row:
        raise HTTPException(status_code=403, detail="Not a chat member")

    # Загружаем информацию о чате
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
    if chat.get("photo_file_id"):
        try:
            chat["_photo_url"] = await resolve_tg_file_url(chat["photo_file_id"])
        except Exception:
            chat["_photo_url"] = ""
    else:
        chat["_photo_url"] = ""

    # Страницы, привязанные к этому чату
    all_pages = await get_accessible_pages(user_id)
    enriched = await enrich_pages_for_hub(all_pages, user_id)
    chat_pages = filter_pages_by_chat(enriched, chat_id)

    for p in chat_pages:
        icon_name = (p.get("config") or {}).get("icon") or _HUB_TYPE_ICONS.get(p["page_type"])
        p["_icon"] = resolve_icon(icon_name) if icon_name else None

    bar_ctx = await _build_bar_context(user_id, roles)

    # Governance данные (из Democracy, если доступен)
    governance = None
    if settings.democracy_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{settings.democracy_url}/v1/dashboard/{chat_id}",
                    headers={"X-Init-Data": init_data} if init_data else {},
                )
                if r.status_code == 200:
                    governance = r.json()
        except Exception as e:
            logger.debug("governance data unavailable for chat %s: %s", chat_id, e)

    html = templates.get_template("chat.html").render(
        user=user,
        bar_user=user,
        **bar_ctx,
        roles=sorted(roles),
        chat=chat,
        pages=chat_pages,
        governance=governance,
        public_url=settings.public_url,
    )
    return HTMLResponse(html)
