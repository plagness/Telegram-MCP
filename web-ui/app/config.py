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

    public_url: str = "https://tg.example.com:8443"
    tgapi_url: str = "http://tgapi:8000"
    llm_core_url: str = "http://llmcore:8080"
    arena_core_url: str = "http://arenacore:8082"
    planner_core_url: str = "http://plannercore:8085"
    metrics_api_url: str = "http://metricsapi-service:8083"
    channel_mcp_url: str = "http://chmcp-service:3333"
    bcs_mcp_url: str = "http://bcsmcp:3333"
    datesale_url: str = "http://datesalecore.ns-datesale.svc.cluster.local:8086"
    democracy_url: str = "http://democracycore.ns-democracy.svc.cluster.local:8087"
    mcp_http_token: str = ""
    bot_token: str = ""
    telegram_bot_token: str = ""
    db_dsn: str = "postgresql://telegram:telegram@tgdb:5432/telegram"
    log_level: str = "info"
    nodes_config_path: str = "/app/config/nodes.json"
    miniapp_url: str = ""  # https://t.me/BotUsername/AppShortName (для deep link кнопок)

    def get_bot_token(self) -> str:
        """Токен бота: BOT_TOKEN или TELEGRAM_BOT_TOKEN (fallback)."""
        return self.bot_token or self.telegram_bot_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
