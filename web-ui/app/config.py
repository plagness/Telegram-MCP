"""Конфигурация web-ui модуля."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки web-ui.

    Переменные окружения:
      PUBLIC_URL — публичный URL для ссылок (авторизованный в BotFather)
      TGAPI_URL — внутренний URL telegram-api (для проксирования запросов)
      BOT_TOKEN — токен бота для валидации initData
      DB_DSN — PostgreSQL connection string (та же БД что у tgapi)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    public_url: str = "https://tg.plag.space:8090"
    tgapi_url: str = "http://tgapi:8000"
    bot_token: str = ""
    db_dsn: str = "postgresql://telegram:telegram@tgdb:5432/telegram"
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
