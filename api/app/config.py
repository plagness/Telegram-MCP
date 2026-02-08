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
    telegram_bot_tokens: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    default_chat_id: str = ""

    templates_dir: str = "templates"
    template_autoseed: bool = True

    # LLM-MCP для автоматического разрешения событий
    llm_mcp_url: str = "http://llm-mcp-core:8080"
    llm_mcp_enabled: bool = True

    # Web-UI (Telegram Mini App)
    webui_enabled: bool = False
    webui_public_url: str = ""
    webui_bot_username: str = ""
    webui_app_name: str = "app"

    def __init__(self, **kwargs):
        # Подхватываем fallback-переменные из корневого .env интегрированного проекта.
        root_env = Path(__file__).parent.parent.parent.parent.parent / ".env"
        if root_env.exists():
            root_vars: dict[str, str] = {}
            with open(root_env, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    root_vars[key.strip()] = value.strip()

            if not kwargs.get("telegram_bot_token") and not os.getenv("TELEGRAM_BOT_TOKEN"):
                token = root_vars.get("BOT_TOKEN")
                if token:
                    os.environ["TELEGRAM_BOT_TOKEN"] = token

            if not kwargs.get("telegram_bot_tokens") and not os.getenv("TELEGRAM_BOT_TOKENS"):
                tokens = root_vars.get("BOT_TOKENS")
                if tokens:
                    os.environ["TELEGRAM_BOT_TOKENS"] = tokens

            if not kwargs.get("default_chat_id") and not os.getenv("DEFAULT_CHAT_ID"):
                default_chat_id = root_vars.get("DEFAULT_CHAT_ID")
                if default_chat_id:
                    os.environ["DEFAULT_CHAT_ID"] = default_chat_id

        super().__init__(**kwargs)

    def get_all_tokens(self) -> list[str]:
        tokens: list[str] = []
        if self.telegram_bot_tokens:
            tokens.extend(part.strip() for part in self.telegram_bot_tokens.split(","))
        if self.telegram_bot_token:
            tokens.append(self.telegram_bot_token.strip())
        # Dedupe с сохранением порядка.
        return list(dict.fromkeys(token for token in tokens if token))


@lru_cache
def get_settings() -> Settings:
    # Cached settings for app lifetime.
    return Settings()
