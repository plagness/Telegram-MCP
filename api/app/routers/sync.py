"""Роутер для активной синхронизации данных из Telegram Bot API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from ..db import execute, fetch_one
from ..services.sync import (
    sync_chat,
    sync_chat_admins,
    sync_chat_avatar,
    sync_chat_info,
    sync_user_avatar,
    sync_user_profile,
    get_avatar,
    fetch_and_save_avatar,
    AVATAR_DIR,
)

router = APIRouter(prefix="/v1/sync", tags=["sync"])

_avatar_router = APIRouter(prefix="/v1/avatars", tags=["avatars"])


# === Sync endpoints ===


@router.post("/chat/{chat_id}")
async def sync_chat_full(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Полная синхронизация чата: метаданные, админы, аватарки."""
    try:
        return await sync_chat(chat_id, bot_id=bot_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/chat/{chat_id}/info")
async def sync_chat_info_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Синхронизация метаданных чата."""
    try:
        return await sync_chat_info(chat_id, bot_id=bot_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/chat/{chat_id}/admins")
async def sync_chat_admins_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Синхронизация администраторов чата."""
    try:
        admins = await sync_chat_admins(chat_id, bot_id=bot_id)
        return {"items": admins, "count": len(admins)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/chat/{chat_id}/avatar")
async def sync_chat_avatar_api(chat_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Синхронизация аватарки чата."""
    path = await sync_chat_avatar(chat_id, bot_id=bot_id)
    return {"local_path": path, "synced": path is not None}


@router.post("/user/{user_id}/avatar")
async def sync_user_avatar_api(user_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Синхронизация аватарки пользователя."""
    path = await sync_user_avatar(user_id, bot_id=bot_id)
    return {"local_path": path, "synced": path is not None}


@router.post("/user/{user_id}/profile")
async def sync_user_profile_api(user_id: str, bot_id: int | None = None) -> dict[str, Any]:
    """Обогащение профиля: bio, birthdate, rating, accent_color, emoji_status."""
    try:
        return await sync_user_profile(user_id, bot_id=bot_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/user/{user_id}/enrich")
async def enrich_user_api(user_id: str, body: dict[str, Any] = {}) -> dict[str, Any]:
    """Обновить поля из WebApp initData: allows_write_to_pm, photo_url."""
    allows_write = body.get("allows_write_to_pm")
    photo_url = body.get("photo_url")

    if allows_write is None and photo_url is None:
        return {"updated": False, "reason": "no fields to update"}

    sets: list[str] = []
    vals: list[Any] = []
    if allows_write is not None:
        sets.append("allows_write_to_pm = %s")
        vals.append(bool(allows_write))
    if photo_url is not None:
        sets.append("photo_url = %s")
        vals.append(str(photo_url))
    sets.append("updated_at = NOW()")
    vals.append(str(user_id))

    await execute(
        f"UPDATE users SET {', '.join(sets)} WHERE user_id = %s",
        vals,
    )
    return {"updated": True, "user_id": user_id}


# === Avatar endpoints ===


@_avatar_router.get("/{entity_type}/{entity_id}")
async def get_avatar_api(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Получить информацию об аватарке."""
    if entity_type not in ("user", "chat"):
        raise HTTPException(status_code=400, detail="entity_type must be 'user' or 'chat'")

    avatar = await get_avatar(entity_type, entity_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return avatar


@_avatar_router.get("/{entity_type}/{entity_id}/file")
async def get_avatar_file(entity_type: str, entity_id: str):
    """Получить файл аватарки."""
    if entity_type not in ("user", "chat"):
        raise HTTPException(status_code=400, detail="entity_type must be 'user' or 'chat'")

    avatar = await get_avatar(entity_type, entity_id)
    if not avatar or not avatar.get("local_path"):
        raise HTTPException(status_code=404, detail="Avatar file not found")

    file_path = AVATAR_DIR / f"{entity_type}_{entity_id}.jpg"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Avatar file missing from disk")

    return FileResponse(file_path, media_type="image/jpeg")


@_avatar_router.post("/{entity_type}/{entity_id}/upload")
async def upload_custom_avatar(
    entity_type: str,
    entity_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Загрузить кастомную аватарку (is_custom=TRUE)."""
    if entity_type not in ("user", "chat"):
        raise HTTPException(status_code=400, detail="entity_type must be 'user' or 'chat'")

    if file.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=400, detail="Supported formats: JPEG, PNG, WebP")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    local_filename = f"{entity_type}_{entity_id}.jpg"
    save_path = AVATAR_DIR / local_filename
    save_path.write_bytes(content)

    local_path = f"/data/avatars/{local_filename}"

    await execute(
        """
        INSERT INTO avatars (entity_type, entity_id, local_path, is_custom, fetched_at)
        VALUES (%s, %s, %s, TRUE, NOW())
        ON CONFLICT (entity_type, entity_id) DO UPDATE
        SET local_path = EXCLUDED.local_path,
            is_custom = TRUE,
            fetched_at = NOW(),
            updated_at = NOW()
        """,
        [entity_type, str(entity_id), local_path],
    )

    return {"local_path": local_path, "is_custom": True}


@_avatar_router.delete("/{entity_type}/{entity_id}")
async def delete_custom_avatar(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Удалить кастомную аватарку (вернуться к Telegram-аватарке)."""
    if entity_type not in ("user", "chat"):
        raise HTTPException(status_code=400, detail="entity_type must be 'user' or 'chat'")

    avatar = await get_avatar(entity_type, entity_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="Avatar not found")

    if not avatar.get("is_custom"):
        raise HTTPException(status_code=400, detail="Avatar is not custom")

    # Удаляем запись, потом можно пере-синхронизировать из Telegram
    await execute(
        "DELETE FROM avatars WHERE entity_type = %s AND entity_id = %s",
        [entity_type, str(entity_id)],
    )

    # Удаляем файл с диска
    file_path = AVATAR_DIR / f"{entity_type}_{entity_id}.jpg"
    if file_path.exists():
        file_path.unlink()

    return {"deleted": True}


# Экспортируем оба роутера для подключения в main.py
avatar_router = _avatar_router
