"""
Сервис для работы с состояниями пользователей (Finite State Machine).

Управление состояниями в процессе размещения ставок и других интерактивных операций.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from ..db import execute, fetch_one

logger = logging.getLogger(__name__)


async def get_user_state(user_id: int) -> dict[str, Any] | None:
    """
    Получить текущее состояние пользователя.

    Returns:
        Словарь с state, data, expires_at или None
    """
    result = await fetch_one(
        "SELECT * FROM user_states WHERE user_id = %s",
        [user_id]
    )

    if not result:
        return None

    # Проверить истечение
    if result.get("expires_at") and result["expires_at"] < datetime.now():
        await clear_user_state(user_id)
        return None

    return dict(result)


async def set_user_state(
    user_id: int,
    state: str,
    data: dict[str, Any] | None = None,
    expires_in_seconds: int = 300,  # 5 минут по умолчанию
) -> None:
    """
    Установить состояние пользователя.

    Args:
        user_id: ID пользователя
        state: Название состояния
        data: Данные состояния (JSON)
        expires_in_seconds: Время жизни состояния в секундах (None = без истечения)
    """
    expires_at = None
    if expires_in_seconds:
        expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)

    await execute(
        """
        INSERT INTO user_states (user_id, state, data, expires_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET state = EXCLUDED.state,
            data = EXCLUDED.data,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
        """,
        [user_id, state, data or {}, expires_at]
    )

    logger.debug(f"Set state '{state}' for user {user_id} (expires in {expires_in_seconds}s)")


async def update_user_state_data(user_id: int, data: dict[str, Any]) -> None:
    """
    Обновить данные состояния пользователя (не меняя само состояние).

    Args:
        user_id: ID пользователя
        data: Новые данные для слияния
    """
    current_state = await get_user_state(user_id)

    if not current_state:
        logger.warning(f"Cannot update state data for user {user_id}: no active state")
        return

    merged_data = {**current_state.get("data", {}), **data}

    await execute(
        """
        UPDATE user_states
        SET data = %s, updated_at = NOW()
        WHERE user_id = %s
        """,
        [merged_data, user_id]
    )


async def clear_user_state(user_id: int) -> None:
    """
    Очистить состояние пользователя.

    Args:
        user_id: ID пользователя
    """
    await execute(
        "DELETE FROM user_states WHERE user_id = %s",
        [user_id]
    )

    logger.debug(f"Cleared state for user {user_id}")


async def cleanup_expired_states() -> int:
    """
    Очистить все истекшие состояния.

    Returns:
        Количество удалённых записей
    """
    result = await execute(
        """
        DELETE FROM user_states
        WHERE expires_at IS NOT NULL AND expires_at < NOW()
        """
    )

    # В psycopg3 execute не возвращает rowcount напрямую, поэтому просто логируем
    logger.info("Cleaned up expired user states")
    return 0  # TODO: получить rowcount если нужно


# Состояния для FSM
class UserStates:
    """Константы состояний пользователей."""

    WAITING_BET_AMOUNT = "waiting_bet_amount"
    WAITING_WITHDRAWAL_AMOUNT = "waiting_withdrawal_amount"
    WAITING_CONFIRMATION = "waiting_confirmation"
    WAITING_PAYMENT = "waiting_payment"  # Ожидание оплаты Stars invoice
