from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Настройки telegram-api.

    Поддерживает два режима:
    1. Автономный: использует .env в telegram-api/
    2. Интегрированный: использует ../../../.env (корневой .env проекта)

    Приоритет переменных:
    - Переменные окружения (highest)
    - telegram-api/.env (если есть)
    - ../../../.env (fallback на корневой проект)
    - Дефолтные значения
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # игнорируем лишние переменные из корневого .env
    )

    app_name: str = "telegram-api"
    env: str = "dev"
    log_level: str = "info"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    db_dsn: str = "postgresql://telegram:telegram@telegram-db:5432/telegram"

    # Telegram Bot Token с fallback на BOT_TOKEN из корневого .env
    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    templates_dir: str = "templates"
    template_autoseed: bool = True

    def __init__(self, **kwargs):
        # Попытка загрузить токен из корневого .env, если не задан
        if not kwargs.get("telegram_bot_token") and not os.getenv("TELEGRAM_BOT_TOKEN"):
            root_env = Path(__file__).parent.parent.parent.parent.parent / ".env"
            if root_env.exists():
                # Читаем BOT_TOKEN из корневого .env
                with open(root_env, "r") as f:
                    for line in f:
                        if line.startswith("BOT_TOKEN="):
                            token = line.split("=", 1)[1].strip()
                            os.environ["TELEGRAM_BOT_TOKEN"] = token
                            break

        super().__init__(**kwargs)


@lru_cache
def get_settings() -> Settings:
    # Cached settings for app lifetime.
    return Settings()
