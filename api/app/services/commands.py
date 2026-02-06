from __future__ import annotations

import json
from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one
from ..telegram_client import set_my_commands


async def upsert_command_set(
    *,
    scope_type: str,
    chat_id: int | None,
    user_id: int | None,
    language_code: str | None,
    commands: list[dict[str, Any]],
) -> dict:
    row = await execute_returning(
        """
        INSERT INTO bot_commands (scope_type, chat_id, user_id, language_code, commands_json)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (scope_type, chat_id, user_id, language_code) DO UPDATE
        SET commands_json = EXCLUDED.commands_json,
            updated_at = NOW()
        RETURNING *
        """,
        [scope_type, chat_id, user_id, language_code, json.dumps(commands)],
    )
    return row or {}


async def list_command_sets() -> list[dict]:
    return await fetch_all(
        "SELECT * FROM bot_commands ORDER BY scope_type, chat_id NULLS FIRST, user_id NULLS FIRST"
    )


async def get_command_set(command_set_id: int) -> dict | None:
    return await fetch_one("SELECT * FROM bot_commands WHERE id = %s", [command_set_id])


def _build_scope(row: dict) -> dict[str, Any] | None:
    scope_type = row.get("scope_type")
    if not scope_type or scope_type == "default":
        return None
    scope: dict[str, Any] = {"type": scope_type}
    if scope_type in {"chat", "chat_administrators", "chat_member"}:
        scope["chat_id"] = int(row.get("chat_id")) if row.get("chat_id") is not None else None
    if scope_type == "chat_member":
        scope["user_id"] = int(row.get("user_id")) if row.get("user_id") is not None else None
    return scope


async def sync_command_set(command_set_id: int) -> dict:
    row = await get_command_set(command_set_id)
    if not row:
        raise KeyError("command set not found")
    payload: dict[str, Any] = {
        "commands": row.get("commands_json") or [],
    }
    scope = _build_scope(row)
    if scope:
        payload["scope"] = scope
    if row.get("language_code"):
        payload["language_code"] = row.get("language_code")
    result = await set_my_commands(payload)
    return {"ok": True, "result": result}
