"""Эндпоинты мониторинга: health, metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from ..db import fetch_all

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/v1/metrics")
async def metrics_api() -> dict[str, Any]:
    rows = await fetch_all(
        """
        SELECT status, count(*)::int AS count
        FROM messages
        GROUP BY status
        ORDER BY status
        """
    )
    return {"message_status": rows}
