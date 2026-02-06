"""
Сервис для работы с виртуальными балансами пользователей.

Управление Stars балансами, транзакциями и историей.
"""

from __future__ import annotations

import logging
from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one

logger = logging.getLogger(__name__)


async def get_user_balance(user_id: int) -> int:
    """
    Получить текущий баланс пользователя.

    Args:
        user_id: ID пользователя Telegram

    Returns:
        Баланс в Stars (0 если пользователь не найден)
    """
    result = await fetch_one(
        "SELECT balance FROM user_balances WHERE user_id = %s",
        [user_id]
    )
    return result["balance"] if result else 0


async def get_user_balance_info(user_id: int) -> dict[str, Any]:
    """
    Получить полную информацию о балансе пользователя.

    Returns:
        Словарь с балансом и статистикой
    """
    result = await fetch_one(
        "SELECT * FROM user_balances WHERE user_id = %s",
        [user_id]
    )

    if not result:
        return {
            "user_id": user_id,
            "balance": 0,
            "total_deposited": 0,
            "total_won": 0,
            "total_lost": 0,
            "total_withdrawn": 0,
        }

    return dict(result)


async def add_to_balance(
    user_id: int,
    amount: int,
    transaction_type: str = "win",
    reference_type: str | None = None,
    reference_id: int | None = None,
    description: str | None = None,
) -> int:
    """
    Добавить к балансу пользователя.

    Args:
        user_id: ID пользователя
        amount: Сумма для добавления
        transaction_type: Тип транзакции (deposit, win, refund)
        reference_type: Тип ссылки (bet, event, payment)
        reference_id: ID связанной записи
        description: Описание транзакции

    Returns:
        Новый баланс
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")

    # Получить текущий баланс
    current_balance = await get_user_balance(user_id)

    # Обновить или создать запись баланса
    if current_balance > 0 or await fetch_one("SELECT 1 FROM user_balances WHERE user_id = %s", [user_id]):
        # Обновить существующий
        update_fields = ["balance = balance + %s"]
        params = [amount]

        if transaction_type == "deposit":
            update_fields.append("total_deposited = total_deposited + %s")
            params.append(amount)
        elif transaction_type == "win":
            update_fields.append("total_won = total_won + %s")
            params.append(amount)

        params.append(user_id)

        await execute(
            f"""
            UPDATE user_balances
            SET {', '.join(update_fields)}, updated_at = NOW()
            WHERE user_id = %s
            """,
            params
        )
    else:
        # Создать новый
        total_deposited = amount if transaction_type == "deposit" else 0
        total_won = amount if transaction_type == "win" else 0

        await execute(
            """
            INSERT INTO user_balances (user_id, balance, total_deposited, total_won)
            VALUES (%s, %s, %s, %s)
            """,
            [user_id, amount, total_deposited, total_won]
        )

    new_balance = current_balance + amount

    # Записать транзакцию
    await execute(
        """
        INSERT INTO balance_transactions
        (user_id, amount, balance_before, balance_after, transaction_type, reference_type, reference_id, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [user_id, amount, current_balance, new_balance, transaction_type, reference_type, reference_id, description]
    )

    logger.info(f"Added {amount}⭐ to user {user_id} balance ({transaction_type}). New balance: {new_balance}⭐")

    return new_balance


async def deduct_from_balance(
    user_id: int,
    amount: int,
    transaction_type: str = "bet",
    reference_type: str | None = None,
    reference_id: int | None = None,
    description: str | None = None,
) -> bool:
    """
    Списать с баланса пользователя.

    Args:
        user_id: ID пользователя
        amount: Сумма для списания
        transaction_type: Тип транзакции (bet, withdrawal)
        reference_type: Тип ссылки
        reference_id: ID связанной записи
        description: Описание транзакции

    Returns:
        True если успешно, False если недостаточно средств
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")

    current_balance = await get_user_balance(user_id)

    if current_balance < amount:
        return False

    # Списать
    update_fields = ["balance = balance - %s"]
    params = [amount]

    if transaction_type == "bet":
        # При ставке не обновляем total_lost (это сделаем при проигрыше)
        pass
    elif transaction_type == "withdrawal":
        update_fields.append("total_withdrawn = total_withdrawn + %s")
        params.append(amount)

    params.append(user_id)
    params.append(amount)  # Для WHERE

    await execute(
        f"""
        UPDATE user_balances
        SET {', '.join(update_fields)}, updated_at = NOW()
        WHERE user_id = %s AND balance >= %s
        """,
        params
    )

    new_balance = current_balance - amount

    # Записать транзакцию
    await execute(
        """
        INSERT INTO balance_transactions
        (user_id, amount, balance_before, balance_after, transaction_type, reference_type, reference_id, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [user_id, -amount, current_balance, new_balance, transaction_type, reference_type, reference_id, description]
    )

    logger.info(f"Deducted {amount}⭐ from user {user_id} balance ({transaction_type}). New balance: {new_balance}⭐")

    return True


async def record_loss(user_id: int, amount: int) -> None:
    """
    Записать проигрыш (обновить total_lost).

    Args:
        user_id: ID пользователя
        amount: Сумма проигрыша
    """
    await execute(
        """
        INSERT INTO user_balances (user_id, total_lost)
        VALUES (%s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET total_lost = user_balances.total_lost + EXCLUDED.total_lost,
            updated_at = NOW()
        """,
        [user_id, amount]
    )


async def get_balance_history(
    user_id: int,
    limit: int = 50,
    offset: int = 0
) -> list[dict[str, Any]]:
    """
    Получить историю транзакций баланса.

    Returns:
        Список транзакций
    """
    transactions = await fetch_all(
        """
        SELECT * FROM balance_transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        [user_id, limit, offset]
    )

    return [dict(tx) for tx in transactions]


async def get_top_balances(limit: int = 10) -> list[dict[str, Any]]:
    """
    Получить топ пользователей по балансу.

    Returns:
        Список пользователей с балансами
    """
    results = await fetch_all(
        """
        SELECT user_id, balance, total_won, total_lost
        FROM user_balances
        WHERE balance > 0
        ORDER BY balance DESC
        LIMIT %s
        """,
        [limit]
    )

    return [dict(r) for r in results]
