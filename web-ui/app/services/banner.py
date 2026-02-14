"""Сервис промо-баннеров для Hub.

CRUD операции + загрузка аватарок через Telegram Bot API.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings
from ..db import execute, execute_returning, fetch_all, fetch_one

logger = logging.getLogger(__name__)

# Директория для сохранённых аватарок
_AVATAR_DIR = Path(__file__).resolve().parent.parent / "static" / "banners"


async def get_active_banners(user_roles: set[str] | None = None) -> list[dict[str, Any]]:
    """Получить активные баннеры, отфильтрованные по ролям пользователя."""
    rows = await fetch_all(
        """
        SELECT id, tg_username, title, description, link, avatar_file,
               priority, target_roles, created_at
        FROM hub_banners
        WHERE is_active = TRUE
        ORDER BY priority DESC, created_at DESC
        """,
    )
    if not rows or not user_roles:
        return rows or []

    # Фильтрация по target_roles (пустой массив = всем)
    result: list[dict[str, Any]] = []
    for row in rows:
        target = row.get("target_roles") or []
        if not target or (user_roles & set(target)):
            result.append(row)
    return result


async def get_all_banners() -> list[dict[str, Any]]:
    """Все баннеры для админки."""
    return await fetch_all(
        """
        SELECT id, tg_username, title, description, link, avatar_file,
               is_active, priority, target_roles, created_by, created_at, updated_at
        FROM hub_banners
        ORDER BY priority DESC, created_at DESC
        """,
    )


async def create_banner(
    tg_username: str,
    title: str,
    link: str,
    created_by: int,
    description: str = "",
    priority: int = 0,
    target_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Создать баннер и попытаться загрузить аватарку."""
    row = await execute_returning(
        """
        INSERT INTO hub_banners (tg_username, title, description, link, priority,
                                 target_roles, created_by)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
        RETURNING id, tg_username, title, description, link, avatar_file, priority,
                  target_roles, is_active, created_at
        """,
        [
            tg_username.lstrip("@"),
            title,
            description,
            link,
            priority,
            json.dumps(target_roles or []),
            str(created_by),
        ],
    )

    # Попытка загрузить аватарку
    avatar_path = await fetch_and_save_avatar(tg_username.lstrip("@"))
    if avatar_path:
        await execute(
            "UPDATE hub_banners SET avatar_file = %s WHERE id = %s",
            [avatar_path, row["id"]],
        )
        row["avatar_file"] = avatar_path

    return row


async def update_banner_avatar(banner_id: int) -> str | None:
    """Обновить аватарку существующего баннера."""
    banner = await fetch_one(
        "SELECT tg_username FROM hub_banners WHERE id = %s",
        [banner_id],
    )
    if not banner:
        return None

    avatar_path = await fetch_and_save_avatar(banner["tg_username"])
    if avatar_path:
        await execute(
            "UPDATE hub_banners SET avatar_file = %s, updated_at = NOW() WHERE id = %s",
            [avatar_path, banner_id],
        )
    return avatar_path


async def delete_banner(banner_id: int) -> bool:
    """Мягкое удаление баннера."""
    await execute(
        "UPDATE hub_banners SET is_active = FALSE, updated_at = NOW() WHERE id = %s",
        [banner_id],
    )
    return True


async def toggle_banner(banner_id: int, active: bool) -> bool:
    """Переключить активность баннера."""
    await execute(
        "UPDATE hub_banners SET is_active = %s, updated_at = NOW() WHERE id = %s",
        [active, banner_id],
    )
    return True


async def fetch_and_save_avatar(username: str) -> str | None:
    """Загрузить аватарку пользователя через Telegram Bot API.

    1. getChat(@username) → photo.big_file_id
    2. getFile(file_id) → file_path
    3. Скачать → /static/banners/{username}.jpg

    Возвращает относительный путь для URL или None.
    """
    settings = get_settings()
    token = settings.get_bot_token()
    if not token:
        logger.warning("BOT_TOKEN не задан, пропускаю загрузку аватарки")
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # getChat
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": f"@{username}"},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("getChat failed for @%s: %s", username, data)
                return None

            photo = data.get("result", {}).get("photo")
            if not photo:
                logger.info("Нет аватарки у @%s", username)
                return None

            file_id = photo.get("big_file_id") or photo.get("small_file_id")
            if not file_id:
                return None

            # getFile
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file_id},
            )
            file_data = resp.json()
            if not file_data.get("ok"):
                logger.warning("getFile failed: %s", file_data)
                return None

            file_path = file_data["result"]["file_path"]

            # Скачивание файла
            resp = await client.get(
                f"https://api.telegram.org/file/bot{token}/{file_path}",
            )
            resp.raise_for_status()

            # Сохраняем
            _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
            save_path = _AVATAR_DIR / f"{username}.jpg"
            save_path.write_bytes(resp.content)

            logger.info("Аватарка @%s сохранена: %s", username, save_path)
            return f"/static/banners/{username}.jpg"

    except Exception:
        logger.exception("Ошибка загрузки аватарки @%s", username)
        return None
