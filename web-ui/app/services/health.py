"""Health check сервис: проверка работоспособности страниц + cron."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from ..config import get_settings
from ..db import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)
settings = get_settings()

# Интервал между проверками (секунды)
HEALTH_CHECK_INTERVAL = 300  # 5 минут


async def check_page_health(slug: str) -> dict[str, Any]:
    """Проверить здоровье одной страницы (GET /p/{slug}).

    Возвращает: slug, status, status_code, response_time_ms, error_message.
    """
    url = f"{settings.public_url}/p/{slug}"
    start = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)

            if r.status_code == 200:
                status = "ok"
                error = None
            elif r.status_code in (401, 403):
                # Страница с доступом — без initData ожидается base.html redirect
                status = "ok"
                error = None
            else:
                status = "error"
                error = f"HTTP {r.status_code}"

            return {
                "slug": slug,
                "status": status,
                "status_code": r.status_code,
                "response_time_ms": elapsed_ms,
                "error_message": error,
            }
    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "slug": slug,
            "status": "timeout",
            "status_code": None,
            "response_time_ms": elapsed_ms,
            "error_message": "Request timeout (10s)",
        }
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "slug": slug,
            "status": "error",
            "status_code": None,
            "response_time_ms": elapsed_ms,
            "error_message": str(e),
        }


async def check_all_pages() -> list[dict[str, Any]]:
    """Проверить все активные страницы, записать результаты в БД."""
    pages = await fetch_all(
        "SELECT id, slug FROM web_pages WHERE is_active = TRUE ORDER BY slug",
    )

    results: list[dict[str, Any]] = []
    for page in pages:
        result = await check_page_health(page["slug"])
        result["page_id"] = page["id"]
        results.append(result)

        # Записать в web_page_health
        try:
            await execute(
                """
                INSERT INTO web_page_health
                    (page_id, slug, status, status_code, response_time_ms, error_message)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    page["id"],
                    result["slug"],
                    result["status"],
                    result["status_code"],
                    result["response_time_ms"],
                    result["error_message"],
                ],
            )
        except Exception:
            logger.debug("Failed to save health result for %s", result["slug"])

        logger.debug(
            "health check %s: %s (%dms)",
            result["slug"], result["status"], result["response_time_ms"],
        )

    return results


async def get_health_summary() -> dict[str, Any]:
    """Сводка: total, healthy, errors, avg_response_time из последней проверки."""
    row = await fetch_one(
        """
        SELECT
            COUNT(DISTINCT slug) AS total,
            COUNT(DISTINCT slug) FILTER (WHERE status = 'ok') AS healthy,
            COUNT(DISTINCT slug) FILTER (WHERE status != 'ok') AS errors,
            AVG(response_time_ms)::int AS avg_response_time,
            MAX(checked_at) AS last_check
        FROM web_page_health
        WHERE checked_at > NOW() - INTERVAL '10 minutes'
        """,
    )
    if row and row["total"]:
        return {
            "total_pages": row["total"],
            "healthy": row["healthy"],
            "errors": row["errors"],
            "avg_response_time_ms": row["avg_response_time"],
            "last_check": row["last_check"].isoformat() if row["last_check"] else None,
        }
    # Нет свежих данных — fallback
    count = await fetch_one(
        "SELECT COUNT(*) AS total FROM web_pages WHERE is_active = TRUE",
    )
    return {
        "total_pages": count["total"] if count else 0,
        "healthy": None,
        "errors": None,
        "avg_response_time_ms": None,
        "last_check": None,
    }


async def get_page_health_history(slug: str, limit: int = 20) -> list[dict[str, Any]]:
    """История health-check'ов для одной страницы."""
    return await fetch_all(
        """
        SELECT status, status_code, response_time_ms, error_message, checked_at
        FROM web_page_health
        WHERE slug = %s
        ORDER BY checked_at DESC
        LIMIT %s
        """,
        [slug, limit],
    )


async def send_alert(page_slug: str, error: str) -> None:
    """Отправить алерт в чат Ковенант через tgapi."""
    try:
        alert_chat = settings.__dict__.get("alert_chat_id", "")
        if not alert_chat:
            logger.debug("alert_chat_id not configured, skipping alert")
            return

        message = f"Page health alert: /{page_slug}\nError: {error}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.tgapi_url}/v1/messages/send",
                json={
                    "chat_id": alert_chat,
                    "text": message,
                },
            )
    except Exception as e:
        logger.warning("Failed to send health alert: %s", e)


async def cleanup_health_history(retention_days: int = 7) -> int:
    """Удалить записи health старше retention_days дней.

    Возвращает количество удалённых строк.
    """
    row = await fetch_one(
        """
        WITH deleted AS (
            DELETE FROM web_page_health
            WHERE checked_at < NOW() - make_interval(days => %s)
            RETURNING 1
        )
        SELECT COUNT(*) AS cnt FROM deleted
        """,
        [retention_days],
    )
    return row["cnt"] if row else 0


async def health_check_loop() -> None:
    """Фоновый цикл: проверка страниц каждые HEALTH_CHECK_INTERVAL секунд."""
    # Подождать 30 секунд после старта (дать приложению прогреться)
    await asyncio.sleep(30)
    logger.info("Health check loop started (interval=%ds)", HEALTH_CHECK_INTERVAL)

    # Предыдущие статусы для детекции перехода ok→error
    prev_statuses: dict[str, str] = {}
    cleanup_counter = 0

    while True:
        try:
            results = await check_all_pages()

            # Проверить переходы ok→error для алертов
            for r in results:
                slug = r["slug"]
                new_status = r["status"]
                old_status = prev_statuses.get(slug, "ok")

                if old_status == "ok" and new_status != "ok":
                    await send_alert(slug, r.get("error_message") or new_status)

                prev_statuses[slug] = new_status

            ok_count = sum(1 for r in results if r["status"] == "ok")
            logger.info(
                "Health check complete: %d/%d ok",
                ok_count, len(results),
            )

            # Retention cleanup: каждые 12 циклов (~1 час)
            cleanup_counter += 1
            if cleanup_counter >= 12:
                cleanup_counter = 0
                try:
                    deleted = await cleanup_health_history()
                    if deleted:
                        logger.info("Health retention: deleted %d old records", deleted)
                except Exception:
                    logger.debug("Health retention cleanup failed", exc_info=True)

        except Exception:
            logger.exception("Health check loop error")

        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
