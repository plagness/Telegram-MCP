"""Роутер профилей пользователей."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..db import fetch_one, fetch_all

router = APIRouter(prefix="/v1/users", tags=["users"])
emoji_router = APIRouter(prefix="/v1/emoji", tags=["emoji"])
logger = logging.getLogger(__name__)

# ── Оценка даты создания аккаунта ──────────────────────────

_BREAKPOINTS: list[tuple[int, float]] = [
    (1,             2013.58),  # ~авг 2013, запуск Telegram
    (100_000_000,   2014.0),
    (300_000_000,   2015.0),
    (600_000_000,   2016.0),
    (1_000_000_000, 2017.0),
    (1_500_000_000, 2018.0),
    (2_000_000_000, 2019.0),
    (3_000_000_000, 2020.0),
    (4_000_000_000, 2021.0),
    (5_000_000_000, 2022.0),
    (6_000_000_000, 2023.0),
    (7_000_000_000, 2024.0),
    (8_000_000_000, 2025.5),
]


def _estimate_creation_date(user_id: int) -> str | None:
    """Оценочная дата создания аккаунта Telegram (линейная интерполяция по user_id)."""
    if user_id <= 0:
        return None
    for i in range(len(_BREAKPOINTS) - 1):
        id_lo, year_lo = _BREAKPOINTS[i]
        id_hi, year_hi = _BREAKPOINTS[i + 1]
        if user_id < id_hi:
            frac = (user_id - id_lo) / (id_hi - id_lo)
            year_frac = year_lo + frac * (year_hi - year_lo)
            year = int(year_frac)
            month = int((year_frac - year) * 12) + 1
            month = max(1, min(12, month))
            return date(year, month, 1).isoformat()
    return date(2025, 1, 1).isoformat()


# ── Профиль пользователя ───────────────────────────────────


@router.get("/{user_id}/profile")
async def get_user_profile(user_id: str, viewer_id: str | None = None) -> dict[str, Any]:
    """Полный профиль пользователя с enriched данными и чатами.

    viewer_id — ID просматривающего (для общих чатов).
    """
    row = await fetch_one(
        """
        SELECT u.user_id, u.first_name, u.last_name, u.username,
               u.is_bot, u.is_premium, u.language_code,
               u.bio, u.birthdate_day, u.birthdate_month, u.birthdate_year,
               u.rating_level, u.rating_value,
               u.accent_color_id, u.profile_accent_color_id,
               u.emoji_status_custom_emoji_id, u.emoji_status_expiration_date,
               u.photo_url, u.allows_write_to_pm,
               u.has_private_forwards, u.personal_chat_id,
               u.added_to_attachment_menu,
               u.message_count, u.first_seen_at, u.last_seen_at,
               u.created_at,
               u.business_intro, u.business_location, u.business_work_hours,
               a.local_path AS avatar_local_path
        FROM users u
        LEFT JOIN avatars a ON a.entity_type = 'user' AND a.entity_id = u.user_id
        WHERE u.user_id = %s
        """,
        [str(user_id)],
    )

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    profile = dict(row)

    # Аватар URL
    if profile.get("avatar_local_path"):
        profile["avatar_url"] = f"/v1/avatars/user/{user_id}/file"
    else:
        profile["avatar_url"] = None
    profile.pop("avatar_local_path", None)

    # Birthdate как объект
    if profile.get("birthdate_day"):
        profile["birthdate"] = {
            "day": profile["birthdate_day"],
            "month": profile["birthdate_month"],
            "year": profile.get("birthdate_year"),
        }
    else:
        profile["birthdate"] = None

    # Оценочная дата создания аккаунта
    try:
        profile["estimated_creation_date"] = _estimate_creation_date(int(user_id))
    except (ValueError, TypeError):
        profile["estimated_creation_date"] = None

    # URL кастомного эмодзи-статуса
    if profile.get("emoji_status_custom_emoji_id"):
        profile["emoji_status_url"] = f"/v1/emoji/{profile['emoji_status_custom_emoji_id']}/file"
    else:
        profile["emoji_status_url"] = None

    # Чаты пользователя
    chat_rows = await fetch_all(
        """
        SELECT cm.chat_id, cm.status, cm.custom_title, cm.message_count AS chat_message_count,
               cm.first_seen_at AS member_since,
               c.title, c.username AS chat_username, c.member_count, c.type AS chat_type,
               ca.local_path AS chat_avatar_path
        FROM chat_members cm
        JOIN chats c ON c.chat_id = cm.chat_id
        LEFT JOIN avatars ca ON ca.entity_type = 'chat' AND ca.entity_id = cm.chat_id
        WHERE cm.user_id = %s AND cm.status NOT IN ('left', 'kicked')
        ORDER BY cm.last_seen_at DESC NULLS LAST
        """,
        [str(user_id)],
    )

    chats = []
    for cr in chat_rows:
        chat = dict(cr)
        if chat.get("chat_avatar_path"):
            chat["chat_avatar_url"] = f"/v1/avatars/chat/{chat['chat_id']}/file"
        else:
            chat["chat_avatar_url"] = None
        chat.pop("chat_avatar_path", None)
        chats.append(chat)
    profile["chats"] = chats

    # Общие чаты (если viewer_id указан и != user_id)
    if viewer_id and str(viewer_id) != str(user_id):
        common_rows = await fetch_all(
            """
            SELECT cm1.chat_id, cm2.status AS target_status, cm2.custom_title,
                   c.title, c.username AS chat_username, c.member_count,
                   ca.local_path AS chat_avatar_path
            FROM chat_members cm1
            JOIN chat_members cm2 ON cm1.chat_id = cm2.chat_id
            JOIN chats c ON c.chat_id = cm1.chat_id
            LEFT JOIN avatars ca ON ca.entity_type = 'chat' AND ca.entity_id = cm1.chat_id
            WHERE cm1.user_id = %s AND cm2.user_id = %s
              AND cm1.status NOT IN ('left', 'kicked')
              AND cm2.status NOT IN ('left', 'kicked')
            ORDER BY c.title
            """,
            [str(viewer_id), str(user_id)],
        )
        common_chats = []
        for cr in common_rows:
            chat = dict(cr)
            if chat.get("chat_avatar_path"):
                chat["chat_avatar_url"] = f"/v1/avatars/chat/{chat['chat_id']}/file"
            else:
                chat["chat_avatar_url"] = None
            chat.pop("chat_avatar_path", None)
            common_chats.append(chat)
        profile["common_chats"] = common_chats
    else:
        profile["common_chats"] = None

    # Публичная активность (ставки, ответы)
    bets_row = await fetch_one(
        "SELECT COUNT(*) AS total FROM prediction_bets WHERE user_id = %s",
        [str(user_id)],
    )
    surveys_row = await fetch_one(
        "SELECT COUNT(*) AS total FROM web_form_submissions WHERE user_id = %s",
        [str(user_id)],
    )
    profile["bets_count"] = bets_row["total"] if bets_row else 0
    profile["surveys_count"] = surveys_row["total"] if surveys_row else 0

    return profile


# ── Кастомные эмодзи ────────────────────────────────────────


@emoji_router.get("/{emoji_id}/file")
async def emoji_file(emoji_id: str):
    """Отдать файл кастомного эмодзи (из кеша или resolve на лету)."""
    # Проверяем кеш
    cached = await fetch_one(
        "SELECT local_path FROM custom_emoji_cache WHERE custom_emoji_id = %s",
        [emoji_id],
    )
    if cached and cached.get("local_path"):
        abs_path = Path("/app") / cached["local_path"].lstrip("/")
        if abs_path.exists():
            media_type = "image/webp"
            if abs_path.suffix == ".tgs":
                media_type = "application/gzip"
            elif abs_path.suffix == ".webm":
                media_type = "video/webm"
            return FileResponse(
                abs_path,
                media_type=media_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )

    # Resolve на лету
    from ..services.sync import resolve_custom_emoji
    result = await resolve_custom_emoji(emoji_id)
    if not result or not result.get("local_path"):
        raise HTTPException(status_code=404, detail="Emoji not found")

    abs_path = Path("/app") / result["local_path"].lstrip("/")
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Emoji file missing")

    media_type = "image/webp"
    if abs_path.suffix == ".tgs":
        media_type = "application/gzip"
    elif abs_path.suffix == ".webm":
        media_type = "video/webm"
    return FileResponse(
        abs_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
