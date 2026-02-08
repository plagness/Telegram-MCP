"""
Роутер для работы с виртуальными балансами пользователей.

Endpoints:
  - GET /v1/balance/{user_id} — получить баланс
  - POST /v1/balance/{user_id}/deposit — начислить средства
  - GET /v1/balance/{user_id}/history — история транзакций
  - GET /v1/balance/top — топ пользователей по балансу
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..services import balance as balance_service

router = APIRouter(prefix="/v1/balance", tags=["balance"])
logger = logging.getLogger(__name__)


class DepositIn(BaseModel):
    """Начисление средств на баланс."""
    amount: int = Field(..., ge=1, description="Сумма начисления")
    description: str = Field(default="Начисление", description="Описание транзакции")
    source: str = Field(default="manual", description="Источник: manual, arena, reward, initial")


@router.get("/{user_id}")
async def get_user_balance(user_id: int):
    """
    Получить баланс пользователя.

    Returns:
        {
            "ok": True,
            "user_id": 123456789,
            "balance": 150,
            "total_deposited": 200,
            "total_won": 100,
            "total_lost": 50,
            "total_withdrawn": 100
        }
    """
    try:
        info = await balance_service.get_user_balance_info(user_id)
        return {"ok": True, **info}

    except Exception as e:
        logger.error(f"Ошибка получения баланса: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_id}/deposit")
async def deposit_to_balance(user_id: int, payload: DepositIn):
    """
    Начислить средства на баланс пользователя.

    Используется для:
    - Начального баланса ACoin (source='initial')
    - Наград за арену (source='arena')
    - Ручных начислений (source='manual')
    """
    try:
        new_balance = await balance_service.add_to_balance(
            user_id=user_id,
            amount=payload.amount,
            transaction_type="deposit",
            reference_type=payload.source,
            description=payload.description,
        )

        return {
            "ok": True,
            "user_id": user_id,
            "deposited": payload.amount,
            "balance": new_balance,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка начисления: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/history")
async def get_balance_history(
    user_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Получить историю транзакций баланса.

    Returns:
        {
            "ok": True,
            "transactions": [...]
        }
    """
    try:
        transactions = await balance_service.get_balance_history(user_id, limit, offset)
        return {"ok": True, "transactions": transactions}

    except Exception as e:
        logger.error(f"Ошибка получения истории: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top")
async def get_top_balances(limit: int = Query(10, ge=1, le=100)):
    """
    Получить топ пользователей по балансу.

    Returns:
        {
            "ok": True,
            "top": [...]
        }
    """
    try:
        top = await balance_service.get_top_balances(limit)
        return {"ok": True, "top": top}

    except Exception as e:
        logger.error(f"Ошибка получения топа: {e}")
        raise HTTPException(status_code=500, detail=str(e))
