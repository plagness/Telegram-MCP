"""Сервисный слой для модуля «Календарь».

Содержит CRUD для календарей и записей, историю изменений,
цепочки связанных записей и вспомогательные функции.
"""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from ..db import execute, execute_returning, fetch_all, fetch_one

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

# Цвета для тегов (детерминированный выбор)
_TAG_COLORS: dict[str, str] = {
    "work": "#4A90D9",
    "personal": "#9B59B6",
    "meeting": "#2ECC71",
    "deadline": "#E74C3C",
    "idea": "#F39C12",
}

# Цвета для приоритетов (5 = критичный, 1 = низкий)
_PRIORITY_COLORS: dict[int, str] = {
    5: "#E74C3C",
    4: "#E67E22",
    3: "#FFC107",
    2: "#2ECC71",
    1: "#95A5A6",
}


def _auto_color(tags: list[str] | None, priority: int) -> str:
    """Детерминированный выбор цвета: первый тег с цветом, иначе по приоритету."""
    if tags:
        for tag in tags:
            color = _TAG_COLORS.get(tag.lower())
            if color:
                return color
    return _PRIORITY_COLORS.get(priority, "#FFC107")


async def _record_history(
    entry_id: int,
    action: str,
    changes: dict[str, Any] | None = None,
    performed_by: str | None = None,
) -> None:
    """Запись в лог изменений calendar_entry_history."""
    await execute(
        """
        INSERT INTO calendar_entry_history (entry_id, action, changes, performed_by)
        VALUES (%s, %s, %s, %s)
        """,
        [entry_id, action, Json(changes or {}), performed_by],
    )


# ---------------------------------------------------------------------------
# Календари — CRUD
# ---------------------------------------------------------------------------

async def create_calendar(
    *,
    slug: str,
    title: str,
    description: str | None = None,
    owner_id: int | None = None,
    chat_id: int | str | None = None,
    bot_id: int | None = None,
    timezone: str = "UTC",
    is_public: bool = True,
    config: dict[str, Any] | None = None,
) -> dict:
    """Создание нового календаря."""
    return await execute_returning(
        """
        INSERT INTO calendars
            (slug, title, description, owner_id, chat_id, bot_id,
             timezone, is_public, config)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [
            slug,
            title,
            description,
            owner_id,
            str(chat_id) if chat_id is not None else None,
            bot_id,
            timezone,
            is_public,
            Json(config or {}),
        ],
    )


async def get_calendar(calendar_id: int) -> dict | None:
    """Получение календаря по id."""
    return await fetch_one("SELECT * FROM calendars WHERE id = %s", [calendar_id])


async def get_calendar_by_slug(slug: str) -> dict | None:
    """Получение календаря по slug."""
    return await fetch_one("SELECT * FROM calendars WHERE slug = %s", [slug])


async def list_calendars(
    *,
    owner_id: int | None = None,
    chat_id: int | str | None = None,
    bot_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Список календарей с фильтрацией."""
    where: list[str] = []
    values: list[Any] = []

    if owner_id is not None:
        where.append("owner_id = %s")
        values.append(owner_id)
    if chat_id is not None:
        where.append("chat_id = %s")
        values.append(str(chat_id))
    if bot_id is not None:
        where.append("bot_id = %s")
        values.append(bot_id)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"SELECT * FROM calendars {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s"
    values.extend([limit, offset])

    return await fetch_all(sql, values)


async def update_calendar(calendar_id: int, **kwargs: Any) -> None:
    """Обновление календаря — динамический SET (только переданные поля)."""
    updates: list[str] = []
    values: list[Any] = []

    field_map: dict[str, str] = {
        "slug": "slug",
        "title": "title",
        "description": "description",
        "owner_id": "owner_id",
        "chat_id": "chat_id",
        "bot_id": "bot_id",
        "timezone": "timezone",
        "is_public": "is_public",
        "config": "config",
    }

    for key, column in field_map.items():
        if key in kwargs and kwargs[key] is not None:
            if key == "config":
                updates.append(f"{column} = %s")
                values.append(Json(kwargs[key]))
            elif key == "chat_id":
                updates.append(f"{column} = %s")
                values.append(str(kwargs[key]))
            else:
                updates.append(f"{column} = %s")
                values.append(kwargs[key])

    if not updates:
        return

    values.append(calendar_id)
    sql = f"UPDATE calendars SET {', '.join(updates)} WHERE id = %s"
    await execute(sql, values)


async def delete_calendar(calendar_id: int) -> None:
    """Полное удаление календаря (hard delete)."""
    await execute("DELETE FROM calendars WHERE id = %s", [calendar_id])


# ---------------------------------------------------------------------------
# Записи календаря — CRUD
# ---------------------------------------------------------------------------

async def create_entry(
    *,
    calendar_id: int,
    title: str,
    description: str | None = None,
    emoji: str | None = None,
    start_at: str,
    end_at: str | None = None,
    all_day: bool = False,
    status: str = "active",
    priority: int = 3,
    color: str | None = None,
    tags: list[str] | None = None,
    attachments: list[dict] | None = None,
    metadata: dict[str, Any] | None = None,
    series_id: str | None = None,
    repeat: str | None = None,
    repeat_until: str | None = None,
    position: int = 0,
    parent_id: int | None = None,
    created_by: str | None = None,
    ai_actionable: bool = True,
    performed_by: str | None = None,
) -> dict:
    """Создание записи в календаре + запись в историю."""
    resolved_color = color or _auto_color(tags, priority)

    row = await execute_returning(
        """
        INSERT INTO calendar_entries
            (calendar_id, parent_id, title, description, emoji,
             start_at, end_at, all_day, status, priority, color,
             tags, attachments, metadata,
             series_id, repeat, repeat_until, position,
             created_by, ai_actionable)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        [
            calendar_id,
            parent_id,
            title,
            description,
            emoji,
            start_at,
            end_at,
            all_day,
            status,
            priority,
            resolved_color,
            tags or [],
            Json(attachments or []),
            Json(metadata or {}),
            series_id,
            repeat,
            repeat_until,
            position,
            created_by,
            ai_actionable,
        ],
    )

    await _record_history(row["id"], "created", performed_by=performed_by)
    return row


async def get_entry(entry_id: int) -> dict | None:
    """Получение записи по id."""
    return await fetch_one("SELECT * FROM calendar_entries WHERE id = %s", [entry_id])


_SENTINEL = object()


async def list_entries(
    *,
    calendar_id: int,
    start: str | None = None,
    end: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    priority: int | None = None,
    parent_id: int | _SENTINEL.__class__ = _SENTINEL,
    ai_actionable: bool | None = None,
    series_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Список записей с динамическими фильтрами.

    Если parent_id передан явно (в том числе None) — фильтруем по нему.
    Если не передан (sentinel) — не фильтруем.
    """
    where: list[str] = ["calendar_id = %s"]
    values: list[Any] = [calendar_id]

    if start is not None:
        where.append("start_at >= %s")
        values.append(start)
    if end is not None:
        where.append("start_at <= %s")
        values.append(end)
    if tags is not None:
        where.append("tags @> %s::text[]")
        values.append(tags)
    if status is not None:
        where.append("status = %s")
        values.append(status)
    if priority is not None:
        where.append("priority = %s")
        values.append(priority)
    if parent_id is not _SENTINEL:
        if parent_id is None:
            where.append("parent_id IS NULL")
        else:
            where.append("parent_id = %s")
            values.append(parent_id)
    if ai_actionable is not None:
        where.append("ai_actionable = %s")
        values.append(ai_actionable)
    if series_id is not None:
        where.append("series_id = %s")
        values.append(series_id)

    where_sql = " AND ".join(where)
    sql = (
        f"SELECT * FROM calendar_entries WHERE {where_sql} "
        f"ORDER BY start_at ASC, position ASC LIMIT %s OFFSET %s"
    )
    values.extend([limit, offset])

    return await fetch_all(sql, values)


async def get_linked_chain(entry_id: int) -> list[dict]:
    """Получение цепочки связанных записей (вверх до корня + все потомки).

    Рекурсивный CTE: сначала идём вверх по parent_id до корня,
    затем собираем всех потомков от корня вниз.
    """
    sql = """
        WITH RECURSIVE
        -- Поднимаемся до корня
        ancestors AS (
            SELECT * FROM calendar_entries WHERE id = %s
            UNION ALL
            SELECT ce.* FROM calendar_entries ce
            JOIN ancestors a ON ce.id = a.parent_id
        ),
        root AS (
            SELECT id FROM ancestors WHERE parent_id IS NULL
            LIMIT 1
        ),
        -- От корня вниз собираем всех потомков
        chain AS (
            SELECT ce.* FROM calendar_entries ce
            JOIN root r ON ce.id = r.id
            UNION ALL
            SELECT ce.* FROM calendar_entries ce
            JOIN chain c ON ce.parent_id = c.id
        )
        SELECT * FROM chain ORDER BY start_at ASC
    """
    return await fetch_all(sql, [entry_id])


async def update_entry(
    entry_id: int,
    *,
    performed_by: str | None = None,
    **kwargs: Any,
) -> None:
    """Обновление записи — вычисляем diff, обновляем, пишем в историю."""
    old = await get_entry(entry_id)
    if not old:
        return

    updates: list[str] = []
    values: list[Any] = []
    changes: dict[str, Any] = {}

    # Поля, допустимые для обновления
    field_map: dict[str, str] = {
        "title": "title",
        "description": "description",
        "emoji": "emoji",
        "start_at": "start_at",
        "end_at": "end_at",
        "all_day": "all_day",
        "status": "status",
        "priority": "priority",
        "color": "color",
        "tags": "tags",
        "attachments": "attachments",
        "metadata": "metadata",
        "series_id": "series_id",
        "repeat": "repeat",
        "repeat_until": "repeat_until",
        "position": "position",
        "parent_id": "parent_id",
        "created_by": "created_by",
        "ai_actionable": "ai_actionable",
    }

    for key, column in field_map.items():
        if key not in kwargs:
            continue
        new_val = kwargs[key]

        # Сериализуем для сравнения
        old_val = old.get(key)
        if old_val == new_val:
            continue

        # Записываем diff
        changes[key] = {"old": old_val, "new": new_val}

        if key == "attachments":
            updates.append(f"{column} = %s")
            values.append(Json(new_val or []))
        elif key == "metadata":
            updates.append(f"{column} = %s")
            values.append(Json(new_val or {}))
        elif key == "tags":
            updates.append(f"{column} = %s")
            values.append(new_val or [])
        else:
            updates.append(f"{column} = %s")
            values.append(new_val)

    if not updates:
        return

    values.append(entry_id)
    sql = f"UPDATE calendar_entries SET {', '.join(updates)} WHERE id = %s"
    await execute(sql, values)

    await _record_history(entry_id, "updated", changes=changes, performed_by=performed_by)


async def move_entry(
    entry_id: int,
    *,
    start_at: str,
    end_at: str | None = None,
    performed_by: str | None = None,
) -> None:
    """Перемещение записи во времени + запись в историю."""
    old = await get_entry(entry_id)
    if not old:
        return

    changes: dict[str, Any] = {
        "start_at": {"old": str(old["start_at"]) if old["start_at"] else None, "new": start_at},
        "end_at": {"old": str(old["end_at"]) if old["end_at"] else None, "new": end_at},
    }

    await execute(
        "UPDATE calendar_entries SET start_at = %s, end_at = %s WHERE id = %s",
        [start_at, end_at, entry_id],
    )

    await _record_history(entry_id, "moved", changes=changes, performed_by=performed_by)


async def set_status(
    entry_id: int,
    *,
    status: str,
    performed_by: str | None = None,
) -> None:
    """Изменение статуса записи + запись в историю."""
    old = await get_entry(entry_id)
    if not old:
        return

    changes: dict[str, Any] = {
        "status": {"old": old["status"], "new": status},
    }

    await execute(
        "UPDATE calendar_entries SET status = %s WHERE id = %s",
        [status, entry_id],
    )

    await _record_history(entry_id, "status_changed", changes=changes, performed_by=performed_by)


async def delete_entry(
    entry_id: int,
    *,
    performed_by: str | None = None,
) -> None:
    """Удаление записи (hard delete) + запись в историю с информацией о записи."""
    old = await get_entry(entry_id)
    if not old:
        return

    changes: dict[str, Any] = {
        "id": old["id"],
        "title": old["title"],
        "calendar_id": old["calendar_id"],
        "start_at": str(old["start_at"]) if old["start_at"] else None,
        "end_at": str(old["end_at"]) if old["end_at"] else None,
        "status": old["status"],
    }

    # Записываем историю ДО удаления (ON DELETE CASCADE удалит и историю,
    # но entry_id сохранится для аудита, если каскад настроен иначе)
    await _record_history(entry_id, "deleted", changes=changes, performed_by=performed_by)
    await execute("DELETE FROM calendar_entries WHERE id = %s", [entry_id])


# ---------------------------------------------------------------------------
# Массовые операции
# ---------------------------------------------------------------------------

async def bulk_create_entries(
    *,
    calendar_id: int,
    entries: list[dict],
) -> list[dict]:
    """Массовое создание записей — вызывает create_entry для каждой."""
    results: list[dict] = []
    for entry in entries:
        row = await create_entry(calendar_id=calendar_id, **entry)
        results.append(row)
    return results


async def bulk_delete_entries(
    *,
    ids: list[int],
    performed_by: str | None = None,
) -> None:
    """Массовое удаление записей — вызывает delete_entry для каждой."""
    for entry_id in ids:
        await delete_entry(entry_id, performed_by=performed_by)


# ---------------------------------------------------------------------------
# История и предстоящие
# ---------------------------------------------------------------------------

async def get_entry_history(
    entry_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Лог изменений записи."""
    return await fetch_all(
        """
        SELECT * FROM calendar_entry_history
        WHERE entry_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        [entry_id, limit, offset],
    )


async def get_upcoming(
    calendar_id: int,
    *,
    limit: int = 3,
) -> list[dict]:
    """Ближайшие активные записи в календаре."""
    return await fetch_all(
        """
        SELECT * FROM calendar_entries
        WHERE calendar_id = %s AND status = 'active' AND start_at >= NOW()
        ORDER BY start_at ASC
        LIMIT %s
        """,
        [calendar_id, limit],
    )
