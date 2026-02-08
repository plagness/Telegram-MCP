"""Публичные эндпоинты: рендер страниц, индивидуальные ссылки, сабмит форм."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..auth import validate_init_data
from ..config import get_settings
from ..db import execute_returning
from ..services import links as links_svc
from ..services import pages as pages_svc

router = APIRouter(tags=["render"])
logger = logging.getLogger(__name__)
settings = get_settings()


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

    # Определяем шаблон
    if page["page_type"] == "prediction":
        template_name = "prediction.html"
    elif page["page_type"] == "survey":
        template_name = "survey.html"
    else:
        template_name = "page.html"

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

    template = templates.get_template(template_name)
    html = template.render(
        page=page,
        event=event_data,
        config=page.get("config", {}),
        public_url=settings.public_url,
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
