"""
Роутер для работы с виртуальными балансами пользователей.

Endpoints:
  - GET /v1/balance/{user_id} — получить баланс
  - GET /v1/balance/{user_id}/history — история транзакций
  - GET /v1/balance/top — топ пользователей по балансу
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..services import balance as balance_service

router = APIRouter(prefix="/v1/balance", tags=["balance"])
logger = logging.getLogger(__name__)


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
