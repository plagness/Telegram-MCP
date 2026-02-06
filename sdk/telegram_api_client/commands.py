"""
CommandHandler pattern для Telegram-MCP SDK.

Паттерн использования:
    api = TelegramAPI("http://localhost:8081")

    @api.command("start")
    async def start_command(update, args):
        await api.send_message(
            chat_id=update["message"]["chat"]["id"],
            text="Привет! Я бот.",
            reply_to_message_id=update["message"]["message_id"]
        )

    @api.command("help", chat_id=-100123456)  # Guard: только этот чат
    async def help_command(update, args):
        await api.send_message(
            chat_id=update["message"]["chat"]["id"],
            text="Доступные команды: /start, /help"
        )

    await api.start_polling()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Type aliases
UpdateHandler = Callable[[dict[str, Any], list[str]], Awaitable[None]]


class CommandRegistry:
    """
    Реестр обработчиков команд.

    Поддерживает:
    - Регистрацию команд через декоратор
    - Guard pattern (фильтрация по chat_id, user_id)
    - Парсинг аргументов команды
    """

    def __init__(self):
        self._handlers: dict[str, dict[str, Any]] = {}

    def register(
        self,
        command: str,
        handler: UpdateHandler,
        chat_id: int | str | None = None,
        user_id: int | str | None = None,
    ) -> None:
        """
        Регистрация обработчика команды.

        Args:
            command: Имя команды (без /)
            handler: Async функция-обработчик
            chat_id: Фильтр по chat_id (опционально)
            user_id: Фильтр по user_id (опционально)
        """
        self._handlers[command.lower()] = {
            "handler": handler,
            "chat_id": chat_id,
            "user_id": user_id,
        }
        logger.info(
            f"Registered command /{command}"
            + (f" for chat_id={chat_id}" if chat_id else "")
            + (f" for user_id={user_id}" if user_id else "")
        )

    async def handle_update(self, update: dict[str, Any]) -> bool:
        """
        Обработка Update.

        Возвращает True если обработано, False если пропущено.
        """
        # Проверяем что это сообщение с текстом
        message = update.get("message")
        if not message or not message.get("text"):
            return False

        text = message["text"]
        if not text.startswith("/"):
            return False

        # Парсим команду и аргументы
        parts = text.split(maxsplit=1)
        command_full = parts[0][1:]  # Убираем "/"

        # Убираем @botname если есть
        if "@" in command_full:
            command_full = command_full.split("@")[0]

        command = command_full.lower()
        args = parts[1].split() if len(parts) > 1 else []

        # Ищем обработчик
        handler_info = self._handlers.get(command)
        if not handler_info:
            return False

        # Guard: проверяем chat_id
        if handler_info["chat_id"] is not None:
            chat_id = message.get("chat", {}).get("id")
            if str(chat_id) != str(handler_info["chat_id"]):
                logger.debug(
                    f"Command /{command} blocked: chat_id {chat_id} != {handler_info['chat_id']}"
                )
                return False

        # Guard: проверяем user_id
        if handler_info["user_id"] is not None:
            user_id = message.get("from", {}).get("id")
            if str(user_id) != str(handler_info["user_id"]):
                logger.debug(
                    f"Command /{command} blocked: user_id {user_id} != {handler_info['user_id']}"
                )
                return False

        # Вызываем обработчик
        try:
            await handler_info["handler"](update, args)
            logger.info(f"Command /{command} handled successfully")
            return True
        except Exception as e:
            logger.exception(f"Error handling command /{command}: {e}")
            return False

    def list_commands(self) -> list[str]:
        """Список зарегистрированных команд."""
        return list(self._handlers.keys())


class PollingManager:
    """
    Менеджер long polling для получения обновлений от Telegram.

    Использует /v1/updates/poll эндпоинт telegram-api.
    """

    def __init__(self, api_client: Any, command_registry: CommandRegistry):
        """
        Args:
            api_client: Экземпляр TelegramAPI
            command_registry: Реестр команд
        """
        self._api = api_client
        self._registry = command_registry
        self._running = False
        self._current_offset = 0

    async def start(
        self,
        timeout: int = 30,
        limit: int = 100,
        allowed_updates: list[str] | None = None,
        bot_id: int | None = None,
    ) -> None:
        """
        Запуск long polling.

        Args:
            timeout: Таймаут long polling (секунды)
            limit: Максимум обновлений за раз
            allowed_updates: Фильтр типов обновлений
            bot_id: Явный bot_id для мультибот polling
        """
        self._running = True
        logger.info("Polling started")

        # Получаем начальный offset из API
        offset_params = {"bot_id": bot_id} if bot_id is not None else None
        offset_data = await self._api._get("/v1/updates/offset", params=offset_params)
        self._current_offset = offset_data.get("offset", 0)
        logger.info(f"Starting from offset {self._current_offset}")

        while self._running:
            try:
                # Получаем обновления
                params = {
                    "offset": self._current_offset,
                    "limit": limit,
                    "timeout": timeout,
                }
                if bot_id is not None:
                    params["bot_id"] = bot_id
                if allowed_updates:
                    params["allowed_updates"] = allowed_updates

                data = await self._api._get("/v1/updates/poll", params=params)

                updates = data.get("result", [])
                if updates:
                    logger.info(f"Received {len(updates)} updates")

                    # Обрабатываем каждое обновление
                    for update in updates:
                        try:
                            handled = await self._registry.handle_update(update)
                            if handled:
                                logger.debug(f"Update {update.get('update_id')} handled")
                        except Exception as e:
                            logger.exception(f"Error processing update: {e}")

                    # Обновляем offset
                    new_offset = data.get("new_offset", self._current_offset)
                    if new_offset > self._current_offset:
                        self._current_offset = new_offset
                        # Подтверждаем обработку
                        ack_payload = {"offset": new_offset}
                        if bot_id is not None:
                            ack_payload["bot_id"] = bot_id
                        await self._api._post("/v1/updates/ack", ack_payload)
                        logger.debug(f"Offset updated to {new_offset}")

            except asyncio.CancelledError:
                logger.info("Polling cancelled")
                break
            except Exception as e:
                logger.exception(f"Polling error: {e}")
                # Ждём перед повторной попыткой
                await asyncio.sleep(5)

        logger.info("Polling stopped")

    def stop(self) -> None:
        """Остановка polling."""
        self._running = False
