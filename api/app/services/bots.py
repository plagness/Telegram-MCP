"""Registry and management for multiple Telegram bots."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from ..config import get_settings
from ..db import execute, execute_returning, fetch_all, fetch_one

logger = logging.getLogger(__name__)
_settings = get_settings()


class BotRegistry:
    """In-memory registry backed by bots table."""

    _lock = asyncio.Lock()
    _initialized = False
    _bots_by_id: dict[int, dict[str, Any]] = {}
    _bot_id_by_token: dict[str, int] = {}
    _default_bot_id: int | None = None

    @classmethod
    async def initialize(cls, force: bool = False) -> None:
        async with cls._lock:
            if cls._initialized and not force:
                return

            try:
                rows = await fetch_all(
                    """
                    SELECT *
                    FROM bots
                    WHERE is_active = TRUE
                    ORDER BY is_default DESC, id ASC
                    """
                )
            except Exception as exc:
                logger.warning("Bot registry table is not ready: %s", exc)
                cls._bots_by_id = {}
                cls._bot_id_by_token = {}
                cls._default_bot_id = None
                cls._initialized = True
                return

            cls._bots_by_id = {}
            cls._bot_id_by_token = {}
            cls._default_bot_id = None

            for row in rows:
                bot_id = int(row["bot_id"])
                cls._bots_by_id[bot_id] = row
                token = row.get("token")
                if token:
                    cls._bot_id_by_token[token] = bot_id
                if row.get("is_default"):
                    cls._default_bot_id = bot_id

            if cls._default_bot_id is None and len(cls._bots_by_id) == 1:
                cls._default_bot_id = next(iter(cls._bots_by_id.keys()))

            cls._initialized = True

    @classmethod
    async def _ensure_initialized(cls) -> None:
        if not cls._initialized:
            await cls.initialize()

    @staticmethod
    async def _fetch_me_for_token(token: str) -> dict[str, Any]:
        url = f"{_settings.telegram_api_base.rstrip('/')}/bot{token}/getMe"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json={})
        try:
            data = response.json()
        except Exception as exc:  # pragma: no cover - defensive branch
            raise RuntimeError(f"invalid Telegram response for getMe: {exc}") from exc
        if not data.get("ok"):
            description = data.get("description") or f"HTTP {response.status_code}"
            raise RuntimeError(f"failed to validate bot token: {description}")
        result = data.get("result")
        if not isinstance(result, dict) or "id" not in result:
            raise RuntimeError("invalid getMe payload")
        return result

    @staticmethod
    def _sanitize_row(row: dict[str, Any], include_token: bool = False) -> dict[str, Any]:
        result = dict(row)
        if not include_token:
            result.pop("token", None)
        metadata = result.get("metadata")
        if isinstance(metadata, str):
            try:
                result["metadata"] = json.loads(metadata)
            except Exception:
                pass
        return result

    @classmethod
    async def list_bots(cls, include_inactive: bool = False, include_token: bool = False) -> list[dict[str, Any]]:
        where = "" if include_inactive else "WHERE is_active = TRUE"
        try:
            rows = await fetch_all(
                f"""
                SELECT *
                FROM bots
                {where}
                ORDER BY is_default DESC, is_active DESC, id ASC
                """
            )
        except Exception:
            return []
        return [cls._sanitize_row(row, include_token=include_token) for row in rows]

    @classmethod
    async def get_bot(cls, bot_id: int, include_token: bool = False) -> dict[str, Any] | None:
        try:
            row = await fetch_one("SELECT * FROM bots WHERE bot_id = %s", [bot_id])
        except Exception:
            return None
        if not row:
            return None
        return cls._sanitize_row(row, include_token=include_token)

    @classmethod
    async def get_bot_by_token(cls, token: str) -> dict[str, Any] | None:
        await cls._ensure_initialized()
        bot_id = cls._bot_id_by_token.get(token)
        if bot_id is not None:
            row = cls._bots_by_id.get(bot_id)
            if row:
                return row
        try:
            row = await fetch_one(
                "SELECT * FROM bots WHERE token = %s AND is_active = TRUE",
                [token],
            )
            return row
        except Exception:
            return None

    @classmethod
    async def get_bot_token(cls, bot_id: int | None = None) -> str:
        await cls._ensure_initialized()

        if bot_id is not None:
            row = cls._bots_by_id.get(bot_id)
            if row and row.get("is_active") and row.get("token"):
                return str(row["token"])
            try:
                db_row = await fetch_one(
                    "SELECT token FROM bots WHERE bot_id = %s AND is_active = TRUE",
                    [bot_id],
                )
            except Exception:
                db_row = None
            if db_row and db_row.get("token"):
                return str(db_row["token"])
            raise RuntimeError(f"bot {bot_id} is not registered or inactive")

        if cls._default_bot_id is not None:
            default_row = cls._bots_by_id.get(cls._default_bot_id)
            if default_row and default_row.get("token"):
                return str(default_row["token"])

        if len(cls._bots_by_id) == 1:
            row = next(iter(cls._bots_by_id.values()))
            token = row.get("token")
            if token:
                return str(token)

        fallback_tokens = _settings.get_all_tokens()
        if len(fallback_tokens) == 1:
            return fallback_tokens[0]

        if _settings.telegram_bot_token:
            return _settings.telegram_bot_token

        raise RuntimeError("default bot is not configured")

    @classmethod
    async def set_default(cls, bot_id: int) -> dict[str, Any]:
        existing = await fetch_one(
            "SELECT bot_id FROM bots WHERE bot_id = %s AND is_active = TRUE",
            [bot_id],
        )
        if not existing:
            raise KeyError(f"bot {bot_id} not found")

        await execute(
            """
            UPDATE bots
            SET is_default = CASE WHEN bot_id = %s THEN TRUE ELSE FALSE END,
                updated_at = NOW()
            WHERE is_active = TRUE
            """,
            [bot_id],
        )
        await cls.initialize(force=True)

        row = await fetch_one("SELECT * FROM bots WHERE bot_id = %s", [bot_id])
        return cls._sanitize_row(row or {}, include_token=False)

    @classmethod
    async def _ensure_default_exists(cls) -> None:
        row = await fetch_one(
            """
            SELECT bot_id
            FROM bots
            WHERE is_active = TRUE AND is_default = TRUE
            LIMIT 1
            """
        )
        if row:
            return

        candidate = await fetch_one(
            """
            SELECT bot_id
            FROM bots
            WHERE is_active = TRUE
            ORDER BY id ASC
            LIMIT 1
            """
        )
        if not candidate:
            return

        await execute(
            "UPDATE bots SET is_default = TRUE, updated_at = NOW() WHERE bot_id = %s",
            [candidate["bot_id"]],
        )

    @classmethod
    async def register_bot(cls, token: str, set_default: bool | None = None) -> dict[str, Any]:
        token = token.strip()
        if not token:
            raise ValueError("token must not be empty")

        me = await cls._fetch_me_for_token(token)
        bot_id = int(me["id"])

        active_count_row = await fetch_one("SELECT COUNT(*) AS count FROM bots WHERE is_active = TRUE")
        active_count = int(active_count_row["count"]) if active_count_row else 0

        existing = await fetch_one(
            "SELECT id, is_default FROM bots WHERE bot_id = %s OR token = %s ORDER BY id ASC LIMIT 1",
            [bot_id, token],
        )

        make_default = bool(set_default) if set_default is not None else active_count == 0
        if make_default:
            await execute("UPDATE bots SET is_default = FALSE WHERE is_default = TRUE")

        metadata = json.dumps(me)
        username = me.get("username")
        first_name = me.get("first_name")
        can_join_groups = me.get("can_join_groups")
        can_read_all_group_messages = me.get("can_read_all_group_messages")
        supports_inline_queries = me.get("supports_inline_queries")

        if existing:
            row = await execute_returning(
                """
                UPDATE bots
                SET bot_id = %s,
                    token = %s,
                    username = %s,
                    first_name = %s,
                    is_default = %s,
                    is_active = TRUE,
                    can_join_groups = %s,
                    can_read_all_group_messages = %s,
                    supports_inline_queries = %s,
                    metadata = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                [
                    bot_id,
                    token,
                    username,
                    first_name,
                    make_default if set_default is not None or active_count == 0 else bool(existing.get("is_default")),
                    can_join_groups,
                    can_read_all_group_messages,
                    supports_inline_queries,
                    metadata,
                    existing["id"],
                ],
            )
        else:
            row = await execute_returning(
                """
                INSERT INTO bots (
                    bot_id,
                    token,
                    username,
                    first_name,
                    is_default,
                    is_active,
                    can_join_groups,
                    can_read_all_group_messages,
                    supports_inline_queries,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s::jsonb)
                RETURNING *
                """,
                [
                    bot_id,
                    token,
                    username,
                    first_name,
                    make_default,
                    can_join_groups,
                    can_read_all_group_messages,
                    supports_inline_queries,
                    metadata,
                ],
            )

        if not row:
            raise RuntimeError("failed to register bot")

        await cls._ensure_default_exists()
        await cls.initialize(force=True)
        return cls._sanitize_row(row, include_token=False)

    @classmethod
    async def deactivate_bot(cls, bot_id: int) -> None:
        await execute(
            """
            UPDATE bots
            SET is_active = FALSE,
                is_default = FALSE,
                updated_at = NOW()
            WHERE bot_id = %s
            """,
            [bot_id],
        )
        await cls._ensure_default_exists()
        await cls.initialize(force=True)

    @classmethod
    async def get_default_bot(cls) -> dict[str, Any] | None:
        try:
            row = await fetch_one(
                """
                SELECT *
                FROM bots
                WHERE is_default = TRUE AND is_active = TRUE
                LIMIT 1
                """
            )
        except Exception:
            return None
        if row:
            return cls._sanitize_row(row, include_token=False)

        try:
            row = await fetch_one(
                """
                SELECT *
                FROM bots
                WHERE is_active = TRUE
                ORDER BY id ASC
                LIMIT 1
                """
            )
        except Exception:
            return None
        if not row:
            return None
        return cls._sanitize_row(row, include_token=False)


async def auto_register_from_env() -> None:
    """Best-effort auto-registration of bots from env vars."""
    tokens = _settings.get_all_tokens()
    if not tokens:
        logger.warning("No TELEGRAM_BOT_TOKEN(S) found; bot registry remains empty")
        return

    for token in tokens:
        try:
            bot = await BotRegistry.register_bot(token)
            logger.info("Registered bot @%s (%s)", bot.get("username") or "unknown", bot.get("bot_id"))
        except Exception as exc:
            suffix = token[-6:] if len(token) >= 6 else token
            logger.warning("Failed to register bot *%s: %s", suffix, exc)

    await BotRegistry.initialize(force=True)
