"""
telegram-api-client — Python SDK для telegram-api микросервиса.

Использование:
    from telegram_api_client import TelegramAPI

    api = TelegramAPI("http://localhost:8081")
    result = await api.send_message(chat_id=123, text="Привет!")
"""

from .client import TelegramAPI, ProgressContext
from .exceptions import TelegramAPIError

__all__ = ["TelegramAPI", "ProgressContext", "TelegramAPIError"]
