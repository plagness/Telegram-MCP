"""REST API для управления глобальными ролями пользователей."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import roles as roles_svc
from ..services.access import check_page_access, get_access_reasons

router = APIRouter(prefix="/api/v1/roles", tags=["roles"])


class GrantRoleRequest(BaseModel):
    user_id: int
    role: str
    granted_by: int | None = None
    note: str | None = None


class CheckAccessRequest(BaseModel):
    user_id: int
    slug: str


# ── CRUD ────────────────────────────────────────────────


@router.get("")
async def list_roles(
    user_id: int | None = None,
    role: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    """Список ролей с фильтрацией по user_id и/или role."""
    rows = await roles_svc.list_roles(
        user_id=user_id, role=role, limit=limit, offset=offset,
    )
    return {"roles": rows, "count": len(rows)}


@router.get("/{user_id}")
async def get_user_roles(user_id: int):
    """Все роли конкретного пользователя."""
    rows = await roles_svc.get_user_roles(user_id)
    return {"user_id": user_id, "roles": rows}


@router.post("")
async def grant_role(body: GrantRoleRequest):
    """Назначить роль пользователю."""
    row = await roles_svc.grant_role(
        user_id=body.user_id,
        role=body.role,
        granted_by=body.granted_by,
        note=body.note,
    )
    return {"ok": True, "role": row}


@router.delete("/{user_id}/{role}")
async def revoke_role(user_id: int, role: str):
    """Отозвать роль у пользователя."""
    ok = await roles_svc.revoke_role(user_id, role)
    if not ok:
        raise HTTPException(status_code=404, detail="Role not found")
    return {"ok": True}


# ── Проверка доступа ────────────────────────────────────


@router.post("/check-access")
async def check_access(body: CheckAccessRequest):
    """Проверить доступ пользователя к странице."""
    from ..services import pages as pages_svc

    page = await pages_svc.get_page(body.slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    has_access = await check_page_access(body.user_id, page)
    reasons = await get_access_reasons(body.user_id, page) if has_access else []

    return {
        "user_id": body.user_id,
        "slug": body.slug,
        "has_access": has_access,
        "reasons": reasons,
    }
