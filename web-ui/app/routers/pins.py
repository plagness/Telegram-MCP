"""API управления закрепами (живые баннеры в Telegram-чатах).

Закреп — бесшумное закреплённое сообщение с динамическим контентом
(текст + картинка + inline keyboard), обновляемое по cron или событиям.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Json

from ..config import get_settings
from ..db import execute, fetch_all, fetch_one
from ..services.pin_renderer import render_pin_image

router = APIRouter(prefix="/api/v1/pins", tags=["pins"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ── Вспомогательные функции ──


async def _collect_pin_data(chat_id: str, pin_type: str) -> dict[str, Any]:
    """Собрать данные для рендера закрепа по типу."""
    chat = await fetch_one(
        "SELECT chat_id, title, username, member_count, description, photo_file_id "
        "FROM chats WHERE chat_id = %s",
        [str(chat_id)],
    )
    if not chat:
        return {}

    # member_count: из chats (Telegram API), fallback — подсчёт из chat_members
    member_count = chat.get("member_count") or 0
    if not member_count:
        mc_row = await fetch_one(
            "SELECT COUNT(*) AS cnt FROM chat_members "
            "WHERE chat_id = %s AND status NOT IN ('left', 'kicked')",
            [str(chat_id)],
        )
        member_count = (mc_row or {}).get("cnt", 0)

    data: dict[str, Any] = {
        "title": chat.get("title") or "Чат",
        "description": chat.get("description") or "",
        "member_count": member_count,
        "initial": (chat.get("title") or "?")[0].upper(),
        "photo_url": "",
    }

    # Количество активных страниц
    page_count = await fetch_one(
        """
        SELECT COUNT(*) AS cnt FROM web_pages
        WHERE is_active = TRUE
          AND config->'access_rules'->'allowed_chats' @> %s::jsonb
        """,
        [f"[{chat_id}]"],
    )
    data["active_pages"] = (page_count or {}).get("cnt", 0)

    if pin_type == "democracy":
        data.update(await _collect_democracy_data(chat_id))
    elif pin_type == "chart":
        data.update(await _collect_chart_data(chat_id))

    return data


def _make_service_init_data() -> str:
    """Сгенерировать server-to-server initData (HMAC-SHA256 подпись)."""
    import hashlib
    import hmac as _hmac
    import json as _json
    import time as _time

    bot_token = settings.get_bot_token()
    if not bot_token:
        return ""
    user_json = _json.dumps({"id": 1, "first_name": "System"}, separators=(",", ":"))
    auth_date = str(int(_time.time()))
    data = {"auth_date": auth_date, "user": user_json}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = _hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = _hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    data["hash"] = h
    return "&".join(f"{k}={v}" for k, v in data.items())


async def _collect_democracy_data(chat_id: str) -> dict[str, Any]:
    """Собрать данные Democracy для баннера governance."""
    if not settings.democracy_url:
        return {}
    try:
        init_data = _make_service_init_data()
        headers = {"X-Init-Data": init_data} if init_data else {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.democracy_url}/v1/dashboard/{chat_id}",
                headers=headers,
            )
            if r.status_code != 200:
                logger.debug("democracy API %s for chat %s", r.status_code, chat_id)
                return {}
            gov = r.json()
            # Democracy API возвращает {dashboard: {regime, stats, treasury}}
            dash = gov.get("dashboard") or {}
            regime = dash.get("regime") or {}
            stats = dash.get("stats") or {}
            treasury = dash.get("treasury") or {}
            proposals = gov.get("active_proposals") or []
            top = proposals[0] if proposals else None
            return {
                "regime_type": regime.get("type", "democracy"),
                "citizens": stats.get("citizen_count", 0),
                "active_proposals": stats.get("active_proposals", 0),
                "treasury": treasury.get("balance", 0),
                "total_votes": stats.get("total_votes", 0),
                "proposal_title": top.get("title") if top else None,
                "proposal_status": top.get("status") if top else None,
                "proposal_votes": top.get("votes_count", 0) if top else 0,
            }
    except Exception as e:
        logger.debug("democracy data unavailable for pin %s: %s", chat_id, e)
        return {}


async def _collect_chart_data(chat_id: str) -> dict[str, Any]:
    """Собрать данные для графика (заглушка — расширяется плагинами)."""
    return {
        "subtitle": "Данные чата",
        "value": "—",
        "change": None,
        "change_positive": True,
        "bars": [],
    }


def _build_pin_text(chat: dict, pin_type: str, data: dict) -> str:
    """Сформировать текст закрепа."""
    title = data.get("title") or "Чат"
    members = data.get("member_count") or 0
    active = data.get("active_pages") or 0

    lines = [f"<b>{title}</b>"]

    if pin_type == "democracy":
        regime = data.get("regime_type", "democracy")
        citizens = data.get("citizens", 0)
        proposals = data.get("active_proposals", 0)
        lines.append(f"🏛 {regime.capitalize()} · {citizens} граждан")
        if proposals:
            lines.append(f"📋 {proposals} активных предложений")
    else:
        lines.append(f"👥 {members} участников · 📄 {active} активных")

    return "\n".join(lines)


def _build_reply_markup(chat_id: str) -> dict:
    """Inline keyboard с кнопкой на чат-хаб.

    Если MINIAPP_URL задан — используем deep link (открывает Mini App).
    Иначе — обычная URL-кнопка (открывает браузер).
    """
    if settings.miniapp_url:
        # Deep link формат: https://t.me/Bot/App?startapp=c_CHATID
        url = f"{settings.miniapp_url}?startapp=c_{chat_id}"
    else:
        url = f"{settings.public_url}/c/{chat_id}"
    return {
        "inline_keyboard": [
            [{"text": "🐝 Открыть хаб", "url": url}],
        ],
    }


async def _send_photo_and_pin(
    chat_id: str,
    png_bytes: bytes | None,
    caption: str,
    reply_markup: dict,
) -> dict[str, int] | None:
    """Отправить фото через tgapi и закрепить бесшумно.

    Returns:
        {"telegram_message_id": ..., "internal_message_id": ...} или None
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if png_bytes:
                # Отправляем фото через multipart upload
                r = await client.post(
                    f"{settings.tgapi_url}/v1/media/upload-photo",
                    data={
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "HTML",
                    },
                    files={"file": ("pin.png", png_bytes, "image/png")},
                )
            else:
                # Fallback: текстовое сообщение (если Playwright недоступен)
                r = await client.post(
                    f"{settings.tgapi_url}/v1/messages/send",
                    json={
                        "chat_id": chat_id,
                        "text": caption,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                    },
                )

            if r.status_code not in (200, 201):
                logger.error("send pin message failed: %s", r.text)
                return None

            resp = r.json()
            msg_row = resp.get("message") or resp
            internal_id = msg_row.get("id")
            tg_msg_id = (
                msg_row.get("telegram_message_id")
                or resp.get("result", {}).get("message_id")
            )
            if not tg_msg_id:
                logger.error("no telegram_message_id in response: %s", resp)
                return None

            # Добавляем inline keyboard (non-fatal: фото уже отправлено)
            if internal_id:
                try:
                    edit_url = (
                        f"{settings.tgapi_url}/v1/messages/{internal_id}/edit-caption"
                        if png_bytes
                        else f"{settings.tgapi_url}/v1/messages/{internal_id}/edit"
                    )
                    payload = {"reply_markup": reply_markup}
                    if png_bytes:
                        payload["caption"] = caption
                        payload["parse_mode"] = "HTML"
                    else:
                        payload["text"] = caption
                        payload["parse_mode"] = "HTML"
                    er = await client.post(edit_url, json=payload)
                    if er.status_code not in (200, 201):
                        logger.warning("edit keyboard failed (%s), continuing", er.status_code)
                except Exception as edit_err:
                    logger.warning("edit keyboard error: %s", edit_err)

            # Закрепляем бесшумно через chats endpoint
            try:
                await client.post(
                    f"{settings.tgapi_url}/v1/chats/{chat_id}/pin/{tg_msg_id}",
                )
            except Exception as pin_err:
                logger.warning("pin message failed: %s", pin_err)

            return {
                "telegram_message_id": tg_msg_id,
                "internal_message_id": internal_id,
            }
    except Exception as e:
        logger.error("send+pin failed for chat %s: %s", chat_id, e)
        return None


async def _update_pin_message(
    chat_id: str,
    internal_message_id: int | None,
    caption: str,
    reply_markup: dict,
) -> bool:
    """Обновить подпись закрепа (editMessageCaption для фото)."""
    if not internal_message_id:
        logger.warning("no internal_message_id for chat %s, skip edit", chat_id)
        return False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.tgapi_url}/v1/messages/{internal_message_id}/edit-caption",
                json={
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup,
                },
            )
            if r.status_code not in (200, 201):
                logger.warning("edit-caption failed (%s), trying edit-text", r.status_code)
                # Fallback для текстовых закрепов (без фото)
                r = await client.post(
                    f"{settings.tgapi_url}/v1/messages/{internal_message_id}/edit",
                    json={
                        "text": caption,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                    },
                )
            return r.status_code in (200, 201)
    except Exception as e:
        logger.error("edit pin failed for chat %s: %s", chat_id, e)
        return False


# ── API endpoints ──


@router.post("/{chat_id}/init")
async def init_pin(chat_id: str):
    """Инициализировать закреп: генерация + отправка + pin.

    Если закреп уже существует — обновляет.
    """
    # Проверяем что чат существует
    chat = await fetch_one("SELECT chat_id FROM chats WHERE chat_id = %s", [str(chat_id)])
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Проверяем существующий pin
    existing = await fetch_one(
        "SELECT message_id, pin_type FROM chat_pins WHERE chat_id = %s",
        [str(chat_id)],
    )

    pin_type = "default"
    if existing and existing.get("pin_type"):
        pin_type = existing["pin_type"]

    # Собираем данные
    data = await _collect_pin_data(chat_id, pin_type)
    template = f"pin_{pin_type}.html"

    # Генерируем картинку
    try:
        png_bytes = await render_pin_image(template, data)
    except Exception as e:
        logger.error("render pin image failed: %s", e)
        png_bytes = None

    # Текст и клавиатура
    caption = _build_pin_text(chat, pin_type, data)
    reply_markup = _build_reply_markup(chat_id)

    # Отправляем и закрепляем
    result = await _send_photo_and_pin(chat_id, png_bytes, caption, reply_markup)
    if not result:
        raise HTTPException(status_code=502, detail="Failed to send pin message")

    tg_msg_id = result["telegram_message_id"]
    internal_id = result.get("internal_message_id")

    # Сохраняем internal_message_id в pin_data для будущих edit-caption
    data["_internal_message_id"] = internal_id

    # Сохраняем в БД
    await execute(
        """
        INSERT INTO chat_pins (chat_id, message_id, pin_type, pin_data, last_text, last_updated)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (chat_id) DO UPDATE SET
            message_id = EXCLUDED.message_id,
            pin_data = EXCLUDED.pin_data,
            last_text = EXCLUDED.last_text,
            last_updated = now()
        """,
        [str(chat_id), tg_msg_id, pin_type, Json(data), caption],
    )

    return {"ok": True, "message_id": tg_msg_id, "pin_type": pin_type}


@router.post("/{chat_id}/update")
async def update_pin(chat_id: str):
    """Обновить существующий закреп (перегенерировать данные + текст)."""
    pin = await fetch_one(
        "SELECT * FROM chat_pins WHERE chat_id = %s",
        [str(chat_id)],
    )
    if not pin or not pin.get("message_id"):
        raise HTTPException(status_code=404, detail="Pin not found. Use /init first.")

    pin_type = pin.get("pin_type") or "default"
    old_pin_data = pin.get("pin_data") or {}
    data = await _collect_pin_data(chat_id, pin_type)
    caption = _build_pin_text({}, pin_type, data)
    reply_markup = _build_reply_markup(chat_id)

    # Извлекаем internal_message_id из сохранённых pin_data
    internal_id = old_pin_data.get("_internal_message_id")
    ok = await _update_pin_message(chat_id, internal_id, caption, reply_markup)

    # Сохраняем internal_id в новых данных
    data["_internal_message_id"] = internal_id

    # Обновляем БД
    await execute(
        """
        UPDATE chat_pins SET pin_data = %s, last_text = %s, last_updated = now()
        WHERE chat_id = %s
        """,
        [Json(data), caption, str(chat_id)],
    )

    return {"ok": ok, "pin_type": pin_type}


@router.get("/{chat_id}")
async def get_pin(chat_id: str):
    """Получить текущее состояние закрепа."""
    pin = await fetch_one(
        "SELECT * FROM chat_pins WHERE chat_id = %s",
        [str(chat_id)],
    )
    if not pin:
        return {"exists": False, "chat_id": chat_id}
    return {"exists": True, **pin}


@router.put("/{chat_id}")
async def set_pin_config(chat_id: str, request: Request):
    """Установить тип и данные закрепа (модули вызывают для обновления контента).

    Body: {"pin_type": "democracy", "pin_data": {...}, "auto_update": true}
    """
    body = await request.json()
    pin_type = body.get("pin_type")
    pin_data = body.get("pin_data")
    auto_update = body.get("auto_update")
    update_interval = body.get("update_interval")

    updates = []
    params = []

    if pin_type is not None:
        updates.append("pin_type = %s")
        params.append(pin_type)
    if pin_data is not None:
        updates.append("pin_data = %s")
        params.append(Json(pin_data))
    if auto_update is not None:
        updates.append("auto_update = %s")
        params.append(auto_update)
    if update_interval is not None:
        updates.append("update_interval = %s")
        params.append(update_interval)

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")

    params.append(str(chat_id))
    await execute(
        f"UPDATE chat_pins SET {', '.join(updates)} WHERE chat_id = %s",
        params,
    )

    # Триггерим обновление если pin существует
    pin = await fetch_one(
        "SELECT message_id FROM chat_pins WHERE chat_id = %s",
        [str(chat_id)],
    )
    if pin and pin.get("message_id"):
        # Асинхронное обновление (не блокируем ответ)
        try:
            await update_pin(chat_id)
        except Exception as e:
            logger.warning("auto-update pin after config change failed: %s", e)

    return {"ok": True}


@router.get("")
async def list_pins():
    """Список всех настроенных закрепов."""
    pins = await fetch_all(
        "SELECT chat_id, message_id, pin_type, auto_update, update_interval, "
        "last_updated, created_at FROM chat_pins ORDER BY created_at DESC",
    )
    return {"pins": pins}
