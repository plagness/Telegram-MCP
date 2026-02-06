"""Исключения SDK."""

from __future__ import annotations


class TelegramAPIError(Exception):
    """Ошибка при вызове telegram-api."""

    def __init__(self, message: str, status_code: int | None = None, detail: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
