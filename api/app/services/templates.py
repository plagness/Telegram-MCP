from __future__ import annotations

from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one
from ..templates import list_template_files, read_template_file, render_from_string


async def create_template(
    name: str,
    body: str,
    parse_mode: str | None,
    description: str | None,
) -> dict:
    row = await execute_returning(
        """
        INSERT INTO templates (name, body, parse_mode, description)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        [name, body, parse_mode, description],
    )
    return row or {}


async def upsert_template(
    name: str,
    body: str,
    parse_mode: str | None,
    description: str | None,
) -> dict:
    row = await execute_returning(
        """
        INSERT INTO templates (name, body, parse_mode, description)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE
        SET body = EXCLUDED.body,
            parse_mode = EXCLUDED.parse_mode,
            description = EXCLUDED.description,
            updated_at = NOW()
        RETURNING *
        """,
        [name, body, parse_mode, description],
    )
    return row or {}


async def get_template(name: str) -> dict | None:
    return await fetch_one("SELECT * FROM templates WHERE name = %s", [name])


async def list_templates() -> list[dict]:
    return await fetch_all("SELECT * FROM templates ORDER BY name")


async def render_template(name: str, variables: dict[str, Any] | None = None) -> dict:
    tpl = await get_template(name)
    if not tpl:
        raise KeyError("template not found")
    rendered = render_from_string(tpl["body"], variables or {})
    return {"name": name, "parse_mode": tpl.get("parse_mode"), "text": rendered}


async def seed_templates_from_files() -> list[dict]:
    results: list[dict] = []
    for filename in list_template_files():
        body = read_template_file(filename)
        name = filename.rsplit(".", 1)[0]
        tpl = await upsert_template(name=name, body=body, parse_mode="HTML", description="seeded")
        results.append(tpl)
    return results
