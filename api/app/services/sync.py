"""Активная синхронизация данных из Telegram Bot API.

Включает:
- sync_chat_info() — обновление метаданных чата (getChat + getChatMemberCount)
- sync_chat_admins() — список администраторов (getChatAdministrators)
- fetch_and_save_avatar() — скачивание аватарки на диск
- sync_chat() — комплексная синхронизация чата
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from ..db import execute, execute_returning, fetch_all, fetch_one
from ..telegram_client import (
    get_chat,
    get_chat_administrators,
    get_chat_member_count,
    get_custom_emoji_stickers,
    get_file,
    get_user_profile_photos,
)
from ..utils import resolve_bot_context

logger = logging.getLogger(__name__)

# Директория для аватарок (создаётся при первом использовании)
AVATAR_DIR = Path("/app/data/avatars")

# Rate-limit: макс. параллельных запросов к Telegram API
_semaphore = asyncio.Semaphore(5)


async def _tg_call_throttled(coro):
    """Обёртка для rate-limiting запросов к Telegram API."""
    async with _semaphore:
        result = await coro
        await asyncio.sleep(0.05)
        return result


async def sync_chat_info(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Синхронизация метаданных чата: getChat + getChatMemberCount."""
    bot_token, resolved_bot_id = await resolve_bot_context(bot_id)

    chat_data = await _tg_call_throttled(
        get_chat({"chat_id": chat_id}, bot_token=bot_token)
    )

    member_count = None
    try:
        count_result = await _tg_call_throttled(
            get_chat_member_count({"chat_id": chat_id}, bot_token=bot_token)
        )
        if isinstance(count_result, int):
            member_count = count_result
        elif isinstance(count_result, dict):
            member_count = count_result.get("result", count_result)
    except Exception as exc:
        logger.warning("getChatMemberCount failed for %s: %s", chat_id, exc)

    photo = chat_data.get("photo") or {}
    photo_file_id = photo.get("big_file_id") or photo.get("small_file_id")

    await execute(
        """
        INSERT INTO chats (chat_id, type, title, username, description,
                           is_forum, member_count, invite_link, photo_file_id, bot_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chat_id) DO UPDATE
        SET type = EXCLUDED.type,
            title = EXCLUDED.title,
            username = EXCLUDED.username,
            description = COALESCE(EXCLUDED.description, chats.description),
            is_forum = COALESCE(EXCLUDED.is_forum, chats.is_forum),
            member_count = COALESCE(EXCLUDED.member_count, chats.member_count),
            invite_link = COALESCE(EXCLUDED.invite_link, chats.invite_link),
            photo_file_id = COALESCE(EXCLUDED.photo_file_id, chats.photo_file_id),
            bot_id = COALESCE(EXCLUDED.bot_id, chats.bot_id),
            updated_at = NOW()
        """,
        [
            str(chat_data.get("id", chat_id)),
            chat_data.get("type"),
            chat_data.get("title"),
            chat_data.get("username"),
            chat_data.get("description"),
            chat_data.get("is_forum"),
            member_count if isinstance(member_count, int) else chat_data.get("member_count"),
            chat_data.get("invite_link"),
            photo_file_id,
            resolved_bot_id,
        ],
    )

    return {
        "chat_id": str(chat_data.get("id", chat_id)),
        "title": chat_data.get("title"),
        "member_count": member_count,
        "photo_file_id": photo_file_id,
    }


async def sync_chat_admins(chat_id: str, bot_id: int | None = None) -> list[dict[str, Any]]:
    """Синхронизация администраторов чата: getChatAdministrators → upsert."""
    bot_token, resolved_bot_id = await resolve_bot_context(bot_id)

    admins = await _tg_call_throttled(
        get_chat_administrators({"chat_id": chat_id}, bot_token=bot_token)
    )

    # Результат может быть list или dict с ключом result
    if isinstance(admins, dict):
        admins = admins.get("result", admins)
    if not isinstance(admins, list):
        admins = []

    synced: list[dict[str, Any]] = []

    for admin in admins:
        user = admin.get("user", {})
        user_id = user.get("id")
        if not user_id:
            continue

        # Upsert пользователя
        await execute(
            """
            INSERT INTO users (user_id, is_bot, first_name, last_name, username,
                               language_code, is_premium, added_to_attachment_menu,
                               last_seen_at, first_seen_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET is_bot = EXCLUDED.is_bot,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                username = EXCLUDED.username,
                language_code = EXCLUDED.language_code,
                is_premium = EXCLUDED.is_premium,
                added_to_attachment_menu = COALESCE(EXCLUDED.added_to_attachment_menu, users.added_to_attachment_menu),
                last_seen_at = NOW(),
                updated_at = NOW()
            """,
            [
                str(user_id),
                bool(user.get("is_bot")),
                user.get("first_name"),
                user.get("last_name"),
                user.get("username"),
                user.get("language_code"),
                bool(user.get("is_premium")) if user.get("is_premium") is not None else None,
                bool(user.get("added_to_attachment_menu")) if user.get("added_to_attachment_menu") is not None else None,
            ],
        )

        # Upsert членства с расширенными полями
        status = admin.get("status", "administrator")
        custom_title = admin.get("custom_title")
        is_anonymous = admin.get("is_anonymous")
        permissions = {k: v for k, v in admin.items() if k.startswith("can_") and isinstance(v, bool)} or None
        metadata = {
            k: v for k, v in admin.items()
            if k not in ("user", "status", "is_anonymous", "custom_title")
            and not k.startswith("can_")
            and isinstance(v, (bool, int, str))
        }

        await execute(
            """
            INSERT INTO chat_members (chat_id, user_id, bot_id, status, custom_title,
                                      is_anonymous, permissions, last_seen_at,
                                      first_seen_at, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW(), %s::jsonb)
            ON CONFLICT (chat_id, user_id) DO UPDATE
            SET bot_id = COALESCE(EXCLUDED.bot_id, chat_members.bot_id),
                status = EXCLUDED.status,
                custom_title = COALESCE(EXCLUDED.custom_title, chat_members.custom_title),
                is_anonymous = COALESCE(EXCLUDED.is_anonymous, chat_members.is_anonymous),
                permissions = COALESCE(EXCLUDED.permissions, chat_members.permissions),
                last_seen_at = NOW(),
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            """,
            [
                str(chat_id), str(user_id), resolved_bot_id, status,
                custom_title, is_anonymous,
                json.dumps(permissions) if permissions else None,
                json.dumps(metadata),
            ],
        )

        synced.append({
            "user_id": str(user_id),
            "username": user.get("username"),
            "status": status,
        })

    return synced


async def fetch_and_save_avatar(
    entity_type: str,
    entity_id: str,
    file_id: str,
    bot_id: int | None = None,
) -> str | None:
    """Скачать файл по file_id и сохранить на диск.

    Возвращает локальный путь или None.
    """
    bot_token, _ = await resolve_bot_context(bot_id)

    try:
        file_result = await _tg_call_throttled(
            get_file({"file_id": file_id}, bot_token=bot_token)
        )

        file_path = file_result.get("file_path") if isinstance(file_result, dict) else None
        if not file_path:
            logger.warning("getFile вернул пустой file_path для %s_%s", entity_type, entity_id)
            return None

        # Скачивание
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()

        # Сохранение на диск
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        local_filename = f"{entity_type}_{entity_id}.jpg"
        save_path = AVATAR_DIR / local_filename
        save_path.write_bytes(resp.content)

        local_path = f"/data/avatars/{local_filename}"

        # Upsert в таблицу avatars
        await execute(
            """
            INSERT INTO avatars (entity_type, entity_id, file_id, local_path, fetched_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (entity_type, entity_id) DO UPDATE
            SET file_id = EXCLUDED.file_id,
                local_path = EXCLUDED.local_path,
                fetched_at = NOW(),
                updated_at = NOW()
            WHERE avatars.is_custom = FALSE
            """,
            [entity_type, str(entity_id), file_id, local_path],
        )

        logger.info("Аватарка %s_%s сохранена: %s", entity_type, entity_id, save_path)
        return local_path

    except Exception:
        logger.exception("Ошибка загрузки аватарки %s_%s", entity_type, entity_id)
        return None


async def sync_chat_avatar(chat_id: str, bot_id: int | None = None) -> str | None:
    """Синхронизировать аватарку чата (из chats.photo_file_id)."""
    row = await fetch_one(
        "SELECT photo_file_id FROM chats WHERE chat_id = %s",
        [str(chat_id)],
    )
    file_id = row.get("photo_file_id") if row else None
    if not file_id:
        logger.info("Нет photo_file_id для чата %s", chat_id)
        return None

    return await fetch_and_save_avatar("chat", str(chat_id), file_id, bot_id=bot_id)


async def sync_user_avatar(user_id: str, bot_id: int | None = None) -> str | None:
    """Синхронизировать аватарку пользователя (getUserProfilePhotos)."""
    bot_token, _ = await resolve_bot_context(bot_id)

    try:
        result = await _tg_call_throttled(
            get_user_profile_photos(
                {"user_id": int(user_id), "limit": 1},
                bot_token=bot_token,
            )
        )

        photos = result.get("photos", []) if isinstance(result, dict) else []
        if not photos or not photos[0]:
            return None

        # Берём самую большую версию первого фото
        best_photo = photos[0][-1]
        file_id = best_photo.get("file_id")
        if not file_id:
            return None

        # Обновить users.photo_file_id
        await execute(
            "UPDATE users SET photo_file_id = %s, updated_at = NOW() WHERE user_id = %s",
            [file_id, str(user_id)],
        )

        return await fetch_and_save_avatar("user", str(user_id), file_id, bot_id=bot_id)

    except Exception:
        logger.exception("Ошибка синхронизации аватарки user %s", user_id)
        return None


async def sync_chat(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Комплексная синхронизация чата: метаданные + админы + аватарки."""
    result: dict[str, Any] = {"chat_id": chat_id}

    # 1. Метаданные чата
    info = await sync_chat_info(chat_id, bot_id=bot_id)
    result["info"] = info

    # 2. Администраторы
    admins = await sync_chat_admins(chat_id, bot_id=bot_id)
    result["admins"] = admins
    result["admins_count"] = len(admins)

    # 3. Аватарка чата
    chat_avatar = await sync_chat_avatar(chat_id, bot_id=bot_id)
    result["chat_avatar"] = chat_avatar

    # 4. Аватарки известных участников (с rate-limiting)
    members = await fetch_all(
        """
        SELECT cm.user_id FROM chat_members cm
        LEFT JOIN avatars a ON a.entity_type = 'user' AND a.entity_id = cm.user_id
        WHERE cm.chat_id = %s AND cm.status NOT IN ('left', 'kicked')
          AND a.id IS NULL
        LIMIT 50
        """,
        [str(chat_id)],
    )

    avatars_synced = 0
    for member in members:
        uid = member["user_id"]
        try:
            path = await sync_user_avatar(uid, bot_id=bot_id)
            if path:
                avatars_synced += 1
        except Exception:
            logger.debug("Пропускаю аватарку user %s", uid)

    result["user_avatars_synced"] = avatars_synced
    result["known_members"] = len(members)

    return result


async def sync_user_profile(user_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Обогащение профиля пользователя через getChat (bio, birthdate, rating и т.д.).

    Работает только для пользователей, у которых есть личный чат с ботом.
    """
    bot_token, _ = await resolve_bot_context(bot_id)
    result: dict[str, Any] = {"user_id": user_id, "enriched": False}

    try:
        chat_data = await _tg_call_throttled(
            get_chat({"chat_id": int(user_id)}, bot_token=bot_token)
        )
    except Exception as exc:
        logger.debug("getChat для user %s не удался (нет ЛС с ботом?): %s", user_id, exc)
        return result

    if not isinstance(chat_data, dict):
        return result

    # Извлекаем данные
    bio = chat_data.get("bio")
    birthdate = chat_data.get("birthdate") or {}
    accent_color_id = chat_data.get("accent_color_id")
    profile_accent_color_id = chat_data.get("profile_accent_color_id")
    emoji_status_id = chat_data.get("emoji_status_custom_emoji_id")
    emoji_status_exp = chat_data.get("emoji_status_expiration_date")
    personal_chat = chat_data.get("personal_chat") or {}
    personal_chat_id = personal_chat.get("id")
    has_private_forwards = chat_data.get("has_private_forwards")
    rating = chat_data.get("rating") or {}
    rating_level = rating.get("level")
    rating_value = rating.get("rating")

    # Бизнес-данные
    business_intro = chat_data.get("business_intro")
    business_location = chat_data.get("business_location")
    business_opening_hours = chat_data.get("business_opening_hours")

    # Конвертация emoji_status_expiration_date из unix timestamp
    emoji_status_exp_ts = None
    if emoji_status_exp and isinstance(emoji_status_exp, (int, float)):
        from datetime import datetime, timezone
        emoji_status_exp_ts = datetime.fromtimestamp(emoji_status_exp, tz=timezone.utc).isoformat()

    from psycopg.types.json import Json

    await execute(
        """
        UPDATE users SET
            bio = COALESCE(%s, bio),
            birthdate_day = COALESCE(%s, birthdate_day),
            birthdate_month = COALESCE(%s, birthdate_month),
            birthdate_year = COALESCE(%s, birthdate_year),
            accent_color_id = COALESCE(%s, accent_color_id),
            profile_accent_color_id = COALESCE(%s, profile_accent_color_id),
            emoji_status_custom_emoji_id = %s,
            emoji_status_expiration_date = %s,
            personal_chat_id = COALESCE(%s, personal_chat_id),
            has_private_forwards = COALESCE(%s, has_private_forwards),
            rating_level = COALESCE(%s, rating_level),
            rating_value = COALESCE(%s, rating_value),
            business_intro = COALESCE(%s, business_intro),
            business_location = COALESCE(%s, business_location),
            business_work_hours = COALESCE(%s, business_work_hours),
            updated_at = NOW()
        WHERE user_id = %s
        """,
        [
            bio,
            birthdate.get("day"), birthdate.get("month"), birthdate.get("year"),
            accent_color_id, profile_accent_color_id,
            emoji_status_id, emoji_status_exp_ts,
            personal_chat_id, has_private_forwards,
            rating_level, rating_value,
            Json(business_intro) if business_intro else None,
            Json(business_location) if business_location else None,
            Json(business_opening_hours) if business_opening_hours else None,
            str(user_id),
        ],
    )

    result["enriched"] = True
    result["bio"] = bio
    result["birthdate"] = birthdate if birthdate else None
    result["rating_level"] = rating_level
    result["rating_value"] = rating_value
    result["accent_color_id"] = accent_color_id
    result["emoji_status"] = emoji_status_id
    result["has_private_forwards"] = has_private_forwards

    logger.info(
        "Профиль user %s обогащён: bio=%s, birthdate=%s, rating=%s",
        user_id, bool(bio), bool(birthdate), rating_level,
    )
    return result


# Директория для кеша кастомных эмодзи
EMOJI_DIR = Path("/app/data/emoji")


async def resolve_custom_emoji(
    custom_emoji_id: str, bot_id: int | None = None,
) -> dict[str, Any] | None:
    """Получить миниатюру кастомного эмодзи (кеш → Telegram API → файл).

    Возвращает {'local_path': ..., 'emoji': ...} или None.
    """
    # Проверяем кеш
    cached = await fetch_one(
        "SELECT local_path, emoji FROM custom_emoji_cache WHERE custom_emoji_id = %s",
        [custom_emoji_id],
    )
    if cached and cached.get("local_path"):
        local = Path(cached["local_path"])
        if local.exists():
            return dict(cached)

    bot_token, _ = await resolve_bot_context(bot_id)

    try:
        result = await _tg_call_throttled(
            get_custom_emoji_stickers(
                {"custom_emoji_ids": [custom_emoji_id]}, bot_token=bot_token,
            )
        )
    except Exception:
        logger.debug("getCustomEmojiStickers не удался для %s", custom_emoji_id)
        return None

    stickers = result if isinstance(result, list) else []
    if not stickers:
        return None

    sticker = stickers[0]
    emoji_char = sticker.get("emoji", "")
    is_animated = sticker.get("is_animated", False) or sticker.get("is_video", False)

    # Ищем thumbnail (static WebP) → file_id
    thumb = sticker.get("thumbnail") or {}
    file_id = thumb.get("file_id")
    if not file_id:
        # Если нет thumbnail — используем сам стикер
        file_id = sticker.get("file_id")
    if not file_id:
        return None

    # Скачиваем файл
    try:
        file_result = await _tg_call_throttled(
            get_file({"file_id": file_id}, bot_token=bot_token)
        )
        file_path = file_result.get("file_path") if isinstance(file_result, dict) else None
        if not file_path:
            return None

        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()
    except Exception:
        logger.debug("Скачивание эмодзи %s не удалось", custom_emoji_id)
        return None

    # Сохраняем на диск
    EMOJI_DIR.mkdir(parents=True, exist_ok=True)
    ext = "webp"
    if file_path.endswith(".tgs"):
        ext = "tgs"
    elif file_path.endswith(".webm"):
        ext = "webm"
    local_filename = f"{custom_emoji_id}.{ext}"
    save_path = EMOJI_DIR / local_filename
    save_path.write_bytes(resp.content)

    local_path_str = f"/data/emoji/{local_filename}"

    # Upsert в кеш
    await execute(
        """
        INSERT INTO custom_emoji_cache (custom_emoji_id, emoji, file_id, local_path, is_animated, fetched_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (custom_emoji_id) DO UPDATE
        SET emoji = EXCLUDED.emoji,
            file_id = EXCLUDED.file_id,
            local_path = EXCLUDED.local_path,
            is_animated = EXCLUDED.is_animated,
            fetched_at = NOW()
        """,
        [custom_emoji_id, emoji_char, file_id, local_path_str, is_animated],
    )

    logger.info("Кастомный эмодзи %s (%s) кеширован: %s", custom_emoji_id, emoji_char, save_path)
    return {"local_path": local_path_str, "emoji": emoji_char}


async def get_avatar(entity_type: str, entity_id: str) -> dict[str, Any] | None:
    """Получить информацию об аватарке из БД."""
    return await fetch_one(
        """
        SELECT entity_type, entity_id, file_id, local_path, is_custom,
               fetched_at, updated_at
        FROM avatars
        WHERE entity_type = %s AND entity_id = %s
        """,
        [entity_type, str(entity_id)],
    )
