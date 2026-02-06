"""Роутер для получения обновлений (Updates/Polling)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..db import fetch_all, fetch_one, execute
from ..models import UpdatesAckIn
from ..services.bots import BotRegistry
from ..telegram_client import call_api

router = APIRouter(prefix="/v1/updates", tags=["updates"])


async def _default_offset_value() -> int:
    row = await fetch_one(
        """
        SELECT "offset"
        FROM update_offset
        WHERE bot_id IS NULL
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 1
        """
    )
    return int(row["offset"]) if row else 0


async def _get_or_create_offset(bot_id: int | None) -> int:
    if bot_id is None:
        row = await fetch_one(
            """
            SELECT "offset"
            FROM update_offset
            WHERE bot_id IS NULL
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        )
        if row:
            return int(row["offset"])

        await execute(
            """
            INSERT INTO update_offset ("offset", bot_id, updated_at)
            VALUES (0, NULL, NOW())
            """
        )
        return 0

    row = await fetch_one(
        """
        SELECT "offset"
        FROM update_offset
        WHERE bot_id = %s
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        [bot_id],
    )
    if row:
        return int(row["offset"])

    fallback_offset = await _default_offset_value()
    await execute(
        """
        INSERT INTO update_offset ("offset", bot_id, updated_at)
        VALUES (%s, %s, NOW())
        """,
        [fallback_offset, bot_id],
    )
    return fallback_offset


async def _save_offset(bot_id: int | None, offset: int) -> None:
    if bot_id is None:
        row = await fetch_one(
            """
            SELECT id
            FROM update_offset
            WHERE bot_id IS NULL
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        )
        if row:
            await execute(
                """
                UPDATE update_offset
                SET "offset" = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                [offset, row["id"]],
            )
            return

        await execute(
            """
            INSERT INTO update_offset ("offset", bot_id, updated_at)
            VALUES (%s, NULL, NOW())
            """,
            [offset],
        )
        return

    row = await fetch_one(
        """
        SELECT id
        FROM update_offset
        WHERE bot_id = %s
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        [bot_id],
    )
    if row:
        await execute(
            """
            UPDATE update_offset
            SET "offset" = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            [offset, row["id"]],
        )
        return

    await execute(
        """
        INSERT INTO update_offset ("offset", bot_id, updated_at)
        VALUES (%s, %s, NOW())
        """,
        [offset, bot_id],
    )


@router.get("/poll")
async def poll_updates(
    bot_id: int | None = Query(None, description="ID бота для мультибот-поллинга"),
    offset: int | None = Query(None, description="Update ID для начала (None = текущий offset из БД для bot_id)"),
    limit: int = Query(100, ge=1, le=100, description="Максимум обновлений за раз"),
    timeout: int = Query(30, ge=0, le=60, description="Long polling timeout (секунды)"),
    allowed_updates: list[str] | None = Query(
        None,
        description="Типы обновлений для получения (message, callback_query, poll, inline_query, etc.)",
    ),
) -> dict[str, Any]:
    """
    Long polling: получение обновлений от Telegram.

    Использует getUpdates API. Если обновлений нет, блокирует запрос до timeout секунд.

    **Параметры**:
    - offset: Update ID для начала (если None — берётся из БД)
    - limit: Максимум обновлений за раз (1-100)
    - timeout: Таймаут long polling (0-60 секунд)
    - allowed_updates: Фильтр типов (message, callback_query, poll, и т.д.)

    **Возвращает**:
    ```json
    {
      "ok": true,
      "result": [
        {
          "update_id": 123456,
          "message": {...},
          // или callback_query, poll, etc.
        }
      ],
      "new_offset": 123457
    }
    ```

    **Примечание**: После получения обновлений, обновите offset в БД через POST /v1/updates/ack
    """
    # Получаем текущий offset из БД если не передан
    if offset is None:
        offset = await _get_or_create_offset(bot_id)

    # Вызываем getUpdates
    params = {
        "offset": offset,
        "limit": limit,
        "timeout": timeout,
    }
    if allowed_updates:
        params["allowed_updates"] = allowed_updates

    try:
        bot_token = await BotRegistry.get_bot_token(bot_id)
        response = await call_api("getUpdates", params, bot_token=bot_token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get updates: {str(e)}")

    if not response.get("ok"):
        raise HTTPException(status_code=500, detail=response.get("description", "Unknown error"))

    updates = response.get("result", [])

    # Вычисляем новый offset
    new_offset = offset
    if updates:
        max_update_id = max(u["update_id"] for u in updates)
        new_offset = max_update_id + 1

    return {
        "ok": True,
        "result": updates,
        "new_offset": new_offset,
        "count": len(updates),
    }


@router.post("/ack")
async def acknowledge_updates(request: UpdatesAckIn) -> dict[str, Any]:
    """
    Подтверждение обработки обновлений (обновление offset).

    **Body**:
    ```json
    {
      "offset": 123457
    }
    ```

    После успешной обработки обновлений, вызовите этот эндпоинт с новым offset.
    """
    await _save_offset(request.bot_id, request.offset)
    return {"ok": True, "offset": request.offset, "bot_id": request.bot_id}


@router.get("/offset")
async def get_current_offset(bot_id: int | None = Query(None, description="ID бота для отдельного offset")) -> dict[str, Any]:
    """
    Получение текущего offset.

    **Возвращает**:
    ```json
    {
      "offset": 123456,
      "updated_at": "2025-02-06T14:30:45Z"
    }
    ```
    """
    if bot_id is None:
        row = await fetch_one(
            """
            SELECT "offset", updated_at, bot_id
            FROM update_offset
            WHERE bot_id IS NULL
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        )
        if not row:
            await execute('INSERT INTO update_offset ("offset", bot_id, updated_at) VALUES (0, NULL, NOW())')
            return {"offset": 0, "updated_at": None, "bot_id": None}
        return {
            "offset": row["offset"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "bot_id": None,
        }

    row = await fetch_one(
        """
        SELECT "offset", updated_at, bot_id
        FROM update_offset
        WHERE bot_id = %s
        ORDER BY updated_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        [bot_id],
    )
    if not row:
        fallback_offset = await _default_offset_value()
        await execute(
            """
            INSERT INTO update_offset ("offset", bot_id, updated_at)
            VALUES (%s, %s, NOW())
            """,
            [fallback_offset, bot_id],
        )
        return {"offset": fallback_offset, "updated_at": None, "bot_id": bot_id}

    return {
        "offset": row["offset"],
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "bot_id": row["bot_id"],
    }


@router.post("/process")
async def process_update(update: dict[str, Any]) -> dict[str, Any]:
    """
    Обработка одного обновления (из вебхука или polling).

    Сохраняет обновление в БД и маркирует его как обработанное.

    **Body**: Telegram Update object
    ```json
    {
      "update_id": 123456,
      "message": {...}
    }
    ```
    """
    update_id = update.get("update_id")
    if not update_id:
        raise HTTPException(status_code=400, detail="update_id is required")

    # Сохраняем в updates таблице (если ещё нет)
    existing = await fetch_one("SELECT id FROM updates WHERE update_id = %s", [update_id])
    if not existing:
        await execute(
            "INSERT INTO updates (update_id, update_data, processed) VALUES (%s, %s::jsonb, TRUE)",
            [update_id, update],
        )
    else:
        # Маркируем как обработанное
        await execute(
            "UPDATE updates SET processed = TRUE, processed_at = NOW() WHERE update_id = %s",
            [update_id],
        )

    return {"ok": True, "update_id": update_id}


@router.get("/history")
async def get_update_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    processed: bool | None = Query(None, description="Фильтр по статусу обработки"),
) -> dict[str, Any]:
    """
    История обновлений из БД.

    **Параметры**:
    - limit: Количество обновлений
    - offset: Смещение
    - processed: True (обработанные), False (необработанные), None (все)

    **Возвращает**:
    ```json
    {
      "updates": [...],
      "total": 150,
      "limit": 50,
      "offset": 0
    }
    ```
    """
    where_clause = ""
    params: list[Any] = []

    if processed is not None:
        where_clause = "WHERE processed = %s"
        params.append(processed)

    # Получаем total
    count_sql = f"SELECT COUNT(*) as total FROM updates {where_clause}"
    count_row = await fetch_one(count_sql, params if params else None)
    total = count_row["total"] if count_row else 0

    # Получаем updates
    sql = f"""
        SELECT id, update_id, update_data, processed, processed_at, created_at
        FROM updates
        {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    rows = await fetch_all(sql, params)

    return {
        "updates": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
