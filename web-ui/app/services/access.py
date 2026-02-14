"""Сервис контроля доступа к веб-страницам.

Единая точка проверки: chat-based, role-based, user-based доступы.
Логика OR — доступ если выполняется хотя бы одно условие.
Enrichment: обогащение страниц live-данными из БД для hub.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import get_settings
from ..db import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)

_SYSTEM_ROLES = {"project_owner", "backend_dev", "tester", "moderator"}
_CURRENCY_SYMBOLS: dict[str, str] = {
    "XTR": "\u2b50",   # ⭐
    "AC": "\U0001fa99",  # 🪙
    "TON": "\U0001f48e",  # 💎
}
_SOURCE_ICONS: dict[str, str] = {
    "chat": "\U0001f4cc",     # 📌
    "system": "\U0001f527",   # 🔧
    "public": "\U0001f4cb",   # 📋
}


async def get_user_roles(user_id: int) -> set[str]:
    """Получить глобальные роли пользователя."""
    rows = await fetch_all(
        "SELECT role FROM user_roles WHERE user_id = %s",
        [user_id],
    )
    return {r["role"] for r in rows}


async def is_chat_member(user_id: int, chat_ids: list[int]) -> bool:
    """Проверить членство пользователя хотя бы в одном чате.

    1. Проверка в БД (кэш)
    2. Если нет записи — live-проверка через Telegram getChatMember API
    3. Результат кэшируется в chat_members
    """
    if not chat_ids:
        return False

    # Шаг 1: проверка кэша в БД
    row = await fetch_one(
        """
        SELECT 1 FROM chat_members
        WHERE user_id = %s AND chat_id = ANY(%s)
          AND status NOT IN ('left', 'kicked')
        LIMIT 1
        """,
        [str(user_id), [str(c) for c in chat_ids]],
    )
    if row is not None:
        return True

    # Шаг 2: live-проверка через Telegram API
    return await _live_check_membership(user_id, chat_ids)


_ACTIVE_STATUSES = {"member", "administrator", "creator", "restricted"}


async def _live_check_membership(
    user_id: int, chat_ids: list[int],
) -> bool:
    """Проверить членство через Telegram Bot API getChatMember.

    Вызывается когда в chat_members нет записи. Результат кэшируется.
    """
    settings = get_settings()
    token = settings.get_bot_token()
    if not token:
        logger.warning("BOT_TOKEN не задан — live-проверка невозможна")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in chat_ids:
                try:
                    resp = await client.get(
                        f"https://api.telegram.org/bot{token}/getChatMember",
                        params={
                            "chat_id": str(chat_id),
                            "user_id": str(user_id),
                        },
                    )
                    data = resp.json()
                    if not data.get("ok"):
                        logger.debug(
                            "getChatMember failed chat=%s user=%s: %s",
                            chat_id, user_id, data.get("description"),
                        )
                        continue

                    status = (data.get("result") or {}).get("status", "left")

                    # Кэшируем результат в БД
                    await _cache_membership(chat_id, user_id, status)

                    if status in _ACTIVE_STATUSES:
                        return True
                except httpx.HTTPError:
                    logger.debug(
                        "getChatMember HTTP error chat=%s user=%s",
                        chat_id, user_id, exc_info=True,
                    )
    except Exception:
        logger.warning(
            "Live membership check failed user=%s", user_id, exc_info=True,
        )
    return False


async def _cache_membership(
    chat_id: int, user_id: int, status: str,
) -> None:
    """Закэшировать результат getChatMember в таблицу chat_members."""
    try:
        await execute(
            """
            INSERT INTO chat_members (chat_id, user_id, status, last_seen_at, metadata)
            VALUES (%s, %s, %s, NOW(), '{}'::jsonb)
            ON CONFLICT (chat_id, user_id) DO UPDATE
            SET status = EXCLUDED.status,
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            [str(chat_id), str(user_id), status],
        )
    except Exception:
        logger.warning(
            "Не удалось закэшировать membership chat=%s user=%s",
            chat_id, user_id, exc_info=True,
        )


async def check_page_access(user_id: int, page: dict) -> bool:
    """Единая точка проверки доступа к странице (OR-логика).

    Порядок проверки:
    1. access_rules.public == true → всем
    2. user_id в access_rules.allowed_users → да
    3. Роль пользователя в access_rules.allowed_roles → да
    4. Участник чата из access_rules.allowed_chats → да
    5. Обратная совместимость: config.allowed_users (без access_rules)
    6. Нет правил → публичная страница
    """
    config = page.get("config") or {}
    rules = config.get("access_rules") or {}

    # Обратная совместимость: старый формат allowed_users
    if not rules:
        old_allowed = config.get("allowed_users")
        if old_allowed:
            return user_id in old_allowed
        # Нет правил → публичная
        return True

    # 1. Публичная страница
    if rules.get("public"):
        return True

    # 2. Прямой доступ по user_id
    allowed_users = rules.get("allowed_users") or []
    if user_id in allowed_users:
        return True

    # 3. Доступ по глобальной роли
    allowed_roles = rules.get("allowed_roles") or []
    if allowed_roles:
        user_roles = await get_user_roles(user_id)
        if user_roles & set(allowed_roles):
            return True

    # 4. Доступ через членство в чате
    allowed_chats = rules.get("allowed_chats") or []
    if allowed_chats:
        if await is_chat_member(user_id, allowed_chats):
            return True

    return False


async def get_access_reasons(user_id: int, page: dict) -> list[str]:
    """Получить причины доступа (для диагностики)."""
    config = page.get("config") or {}
    rules = config.get("access_rules") or {}
    reasons: list[str] = []

    if not rules:
        old_allowed = config.get("allowed_users")
        if old_allowed:
            if user_id in old_allowed:
                reasons.append("allowed_users (legacy)")
        else:
            reasons.append("public (no rules)")
        return reasons

    if rules.get("public"):
        reasons.append("public")

    allowed_users = rules.get("allowed_users") or []
    if user_id in allowed_users:
        reasons.append("allowed_users")

    allowed_roles = rules.get("allowed_roles") or []
    if allowed_roles:
        user_roles = await get_user_roles(user_id)
        matched = user_roles & set(allowed_roles)
        if matched:
            reasons.append(f"allowed_roles: {', '.join(matched)}")

    allowed_chats = rules.get("allowed_chats") or []
    if allowed_chats:
        if await is_chat_member(user_id, allowed_chats):
            reasons.append("allowed_chats")

    return reasons


async def get_accessible_pages(user_id: int) -> list[dict[str, Any]]:
    """Все доступные пользователю активные страницы.

    Загружает все активные страницы и фильтрует по check_page_access().
    """
    pages = await fetch_all(
        "SELECT * FROM web_pages WHERE is_active = TRUE ORDER BY created_at DESC"
    )

    accessible: list[dict[str, Any]] = []
    for page in pages:
        if await check_page_access(user_id, page):
            accessible.append(page)
    return accessible


def group_pages_for_hub(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Группировка страниц для hub-шаблона.

    Категории:
    - По чатам (allowed_chats)
    - Системные (allowed_roles содержит project_owner/backend_dev/tester)
    - Публичные (public или без правил)
    """
    chat_groups: dict[int, list[dict]] = {}
    system_pages: list[dict] = []
    public_pages: list[dict] = []

    for page in pages:
        config = page.get("config") or {}
        rules = config.get("access_rules") or {}

        # Привязка к чатам
        allowed_chats = rules.get("allowed_chats") or []
        if allowed_chats:
            for chat_id in allowed_chats:
                chat_groups.setdefault(chat_id, []).append(page)
            continue

        # Системные (по ролям)
        allowed_roles = set(rules.get("allowed_roles") or [])
        if allowed_roles & _SYSTEM_ROLES:
            system_pages.append(page)
            continue

        # Публичные / без правил
        public_pages.append(page)

    groups: list[dict[str, Any]] = []

    # Группы чатов
    for chat_id, chat_pages in chat_groups.items():
        groups.append({
            "type": "chat",
            "chat_id": chat_id,
            "title": "",  # Заполняется при рендере (из БД chats)
            "icon": "\U0001f4cc",  # 📌
            "pages": chat_pages,
        })

    # Системные
    if system_pages:
        groups.append({
            "type": "system",
            "chat_id": None,
            "title": "Системные",
            "icon": "\U0001f527",  # 🔧
            "pages": system_pages,
        })

    # Публичные
    if public_pages:
        groups.append({
            "type": "public",
            "chat_id": None,
            "title": "Общие",
            "icon": "\U0001f4cb",  # 📋
            "pages": public_pages,
        })

    return groups


# ── Enrichment для hub v2 ───────────────────────────────────────────────


async def enrich_pages_for_hub(
    pages: list[dict[str, Any]],
    user_id: int,
) -> list[dict[str, Any]]:
    """Обогащает страницы метаданными для hub-рендера.

    Добавляет на каждую страницу:
    - ``_source_label`` / ``_source_type`` / ``_source_icon`` — метка источника
    - ``_meta`` — live-данные из БД (prediction pool, calendar events, etc.)
    """
    # Bulk-загрузка названий чатов
    all_chat_ids: set[int] = set()
    for page in pages:
        for cid in (
            (page.get("config") or {}).get("access_rules") or {}
        ).get("allowed_chats") or []:
            all_chat_ids.add(int(cid))

    chat_titles: dict[int, str] = {}
    chat_photos: dict[int, str | None] = {}
    if all_chat_ids:
        rows = await fetch_all(
            "SELECT chat_id, title, photo_file_id FROM chats WHERE chat_id = ANY(%s)",
            [[str(c) for c in all_chat_ids]],
        )
        chat_titles = {abs(int(r["chat_id"])): r["title"] for r in rows}
        chat_photos = {abs(int(r["chat_id"])): r.get("photo_file_id") for r in rows}

    enriched: list[dict[str, Any]] = []
    for page in pages:
        p = dict(page)
        config = p.get("config") or {}
        rules = config.get("access_rules") or {}

        # Метка источника
        allowed_chats = rules.get("allowed_chats") or []
        if allowed_chats:
            cid = abs(int(allowed_chats[0]))
            p["_source_label"] = chat_titles.get(cid, f"Чат {cid}")
            p["_source_type"] = "chat"
            p["_chat_photo_file_id"] = chat_photos.get(cid)
        elif set(rules.get("allowed_roles") or []) & _SYSTEM_ROLES:
            p["_source_label"] = "Системные"
            p["_source_type"] = "system"
        else:
            p["_source_label"] = "Общие"
            p["_source_type"] = "public"
        p["_source_icon"] = _SOURCE_ICONS.get(p["_source_type"], "")

        # Live-метаданные
        try:
            p["_meta"] = await _enrich_by_type(p, user_id)
        except Exception:
            logger.exception("enrichment failed for page %s", p.get("slug"))
            p["_meta"] = {}

        enriched.append(p)
    return enriched


async def _enrich_by_type(page: dict, user_id: int) -> dict[str, Any]:
    """Маршрутизация enrichment по page_type."""
    pt = page.get("page_type", "")
    if pt == "prediction":
        return await _enrich_prediction(page, user_id)
    if pt == "calendar":
        return await _enrich_calendar(page)
    if pt == "survey":
        return await _enrich_survey(page, user_id)
    return {}


async def _enrich_prediction(page: dict, user_id: int) -> dict[str, Any]:
    """Live-данные для prediction-карточки."""
    event_id = page.get("event_id")
    if not event_id:
        event_id = (page.get("config") or {}).get("event_id")
    if not event_id:
        # C3: Prediction без event_id — агрегатная (hub) страница
        return {"type": "prediction", "status": "hub"}

    event = await fetch_one(
        """
        SELECT pe.status, pe.deadline, pe.total_pool, pe.currency,
               pe.resolved_at,
               (SELECT COUNT(*) FROM prediction_bets WHERE event_id = pe.id) AS bet_count,
               (SELECT COUNT(*) FROM prediction_options WHERE event_id = pe.id) AS option_count
        FROM prediction_events pe
        WHERE pe.id = %s
        """,
        [event_id],
    )
    if not event:
        return {}

    currency = event.get("currency") or "XTR"
    meta: dict[str, Any] = {
        "type": "prediction",
        "status": event["status"],
        "deadline": event.get("deadline"),
        "total_pool": event.get("total_pool") or 0,
        "currency": currency,
        "currency_symbol": _CURRENCY_SYMBOLS.get(currency, currency),
        "bet_count": event.get("bet_count") or 0,
        "option_count": event.get("option_count") or 0,
    }

    # C1: Для resolved — получить текст победившего варианта
    if event["status"] == "resolved":
        winner = await fetch_one(
            "SELECT text FROM prediction_options WHERE event_id = %s AND is_winner = TRUE LIMIT 1",
            [event_id],
        )
        if winner:
            meta["winning_option"] = winner["text"]
        resolved_at = event.get("resolved_at")
        if resolved_at and hasattr(resolved_at, "isoformat"):
            resolved_at = resolved_at.isoformat()
        meta["resolved_at"] = resolved_at

    # Ставка пользователя
    user_bet = await fetch_one(
        """
        SELECT pb.amount, pb.currency, po.text AS option_text
        FROM prediction_bets pb
        JOIN prediction_options po
            ON po.event_id = pb.event_id AND po.option_id = pb.option_id
        WHERE pb.event_id = %s AND pb.user_id = %s
        ORDER BY pb.created_at DESC LIMIT 1
        """,
        [event_id, str(user_id)],
    )
    if user_bet:
        meta["user_bet"] = {
            "amount": user_bet["amount"],
            "option_text": user_bet["option_text"],
        }

    return meta


async def _enrich_calendar(page: dict) -> dict[str, Any]:
    """Live-данные для calendar-карточки."""
    cal_id = (page.get("config") or {}).get("calendar_id")
    if not cal_id:
        return {}

    count_row = await fetch_one(
        "SELECT COUNT(*) AS total FROM calendar_entries WHERE calendar_id = %s AND status = 'active'",
        [cal_id],
    )

    next_entry = await fetch_one(
        """
        SELECT title, start_at, entry_type
        FROM calendar_entries
        WHERE calendar_id = %s AND status = 'active'
          AND start_at > NOW()
        ORDER BY start_at ASC LIMIT 1
        """,
        [cal_id],
    )

    meta: dict[str, Any] = {
        "type": "calendar",
        "entry_count": count_row["total"] if count_row else 0,
    }
    if next_entry:
        start_at = next_entry["start_at"]
        if hasattr(start_at, "isoformat"):
            start_at = start_at.isoformat()
        meta["next_entry"] = {
            "title": next_entry["title"],
            "start_at": start_at,
            "entry_type": next_entry.get("entry_type") or "event",
        }
    else:
        # C2: Нет будущих событий — показать последнее прошедшее
        last_entry = await fetch_one(
            """
            SELECT title, start_at, entry_type
            FROM calendar_entries
            WHERE calendar_id = %s AND status = 'active'
            ORDER BY start_at DESC LIMIT 1
            """,
            [cal_id],
        )
        if last_entry:
            last_at = last_entry["start_at"]
            if hasattr(last_at, "isoformat"):
                last_at = last_at.isoformat()
            meta["last_entry"] = {
                "title": last_entry["title"],
                "start_at": last_at,
                "entry_type": last_entry.get("entry_type") or "event",
            }
    return meta


async def _enrich_survey(page: dict, user_id: int) -> dict[str, Any]:
    """Live-данные для survey-карточки."""
    page_id = page.get("id")
    if not page_id:
        return {}

    count_row = await fetch_one(
        "SELECT COUNT(DISTINCT user_id) AS total FROM web_form_submissions WHERE page_id = %s",
        [page_id],
    )

    user_sub = await fetch_one(
        "SELECT id FROM web_form_submissions WHERE page_id = %s AND user_id = %s LIMIT 1",
        [page_id, str(user_id)],
    )

    return {
        "type": "survey",
        "submission_count": count_row["total"] if count_row else 0,
        "user_submitted": user_sub is not None,
    }
