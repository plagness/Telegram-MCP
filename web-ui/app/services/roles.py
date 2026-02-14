"""CRUD для глобальных ролей пользователей (user_roles)."""

from __future__ import annotations

from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one


async def list_roles(
    *,
    user_id: int | None = None,
    role: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Список ролей с фильтрацией."""
    conditions = []
    params: list[Any] = []

    if user_id is not None:
        conditions.append("user_id = %s")
        params.append(user_id)
    if role:
        conditions.append("role = %s")
        params.append(role)

    where = " AND ".join(conditions) if conditions else "TRUE"
    params.extend([limit, offset])

    return await fetch_all(
        f"""
        SELECT id, user_id, role, granted_by, note, created_at
        FROM user_roles
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        params,
    )


async def get_user_roles(user_id: int) -> list[dict[str, Any]]:
    """Все роли конкретного пользователя."""
    return await fetch_all(
        "SELECT id, user_id, role, granted_by, note, created_at "
        "FROM user_roles WHERE user_id = %s ORDER BY created_at",
        [user_id],
    )


async def grant_role(
    *,
    user_id: int,
    role: str,
    granted_by: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Назначить роль пользователю.

    При конфликте (user_id + role уже есть) обновляет granted_by и note.
    """
    return await execute_returning(
        """
        INSERT INTO user_roles (user_id, role, granted_by, note)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id, role) DO UPDATE
            SET granted_by = EXCLUDED.granted_by,
                note = EXCLUDED.note
        RETURNING *
        """,
        [user_id, role, granted_by, note],
    )


async def revoke_role(user_id: int, role: str) -> bool:
    """Отозвать роль у пользователя."""
    existing = await fetch_one(
        "SELECT id FROM user_roles WHERE user_id = %s AND role = %s",
        [user_id, role],
    )
    if not existing:
        return False
    await execute(
        "DELETE FROM user_roles WHERE user_id = %s AND role = %s",
        [user_id, role],
    )
    return True
