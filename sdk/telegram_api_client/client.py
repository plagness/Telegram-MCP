"""
Основной класс TelegramAPI — HTTP-клиент к telegram-api микросервису.

Заменяет прямые вызовы python-telegram-bot / urllib / httpx к Telegram Bot API.
Все операции проходят через telegram-api, обеспечивая:
  - аудит-трейл всех сообщений
  - хранение в БД
  - шаблоны и форматирование
  - rate limiting и retry
"""

from __future__ import annotations

import asyncio
from typing import Any, BinaryIO, Callable, Awaitable

import httpx

from .exceptions import TelegramAPIError
from .commands import CommandRegistry, PollingManager


class TelegramAPI:
    """
    HTTP-клиент к telegram-api.

    Пример:
        api = TelegramAPI("http://localhost:8081")
        msg = await api.send_message(chat_id=-100123, text="Привет!", parse_mode="HTML")
        await api.edit_message(msg["id"], text="Обновлено!")
        await api.delete_message(msg["id"])
    """

    def __init__(self, base_url: str = "http://localhost:8081", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._command_registry = CommandRegistry()
        self._polling_manager: PollingManager | None = None

    async def close(self) -> None:
        """Закрыть HTTP-клиент."""
        if not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> TelegramAPI:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    # --- Внутренние методы ---

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Базовый HTTP-запрос с обработкой ошибок."""
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            try:
                data = resp.json()
                detail = data.get("detail", str(data))
            except Exception:
                detail = resp.text
            raise TelegramAPIError(
                f"HTTP {resp.status_code}: {detail}",
                status_code=resp.status_code,
                detail=detail,
            )
        return resp.json()

    async def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json=payload or {})

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def _delete(self, path: str) -> dict[str, Any]:
        return await self._request("DELETE", path)

    # === Сообщения ===

    async def send_message(
        self,
        chat_id: int | str,
        text: str | None = None,
        *,
        bot_id: int | None = None,
        parse_mode: str | None = None,
        template: str | None = None,
        variables: dict[str, Any] | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool | None = None,
        live: bool = False,
        dry_run: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Отправить текстовое сообщение.

        Возвращает dict с ключом "message" (данные из БД) и "result" (ответ Telegram).
        Из result["message"]["id"] получаем внутренний ID для edit/delete.
        """
        payload: dict[str, Any] = {"chat_id": chat_id}
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if text is not None:
            payload["text"] = text
        if template:
            payload["template"] = template
        if variables:
            payload["variables"] = variables
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        if live:
            payload["live"] = True
        if dry_run:
            payload["dry_run"] = True
        if request_id:
            payload["request_id"] = request_id

        data = await self._post("/v1/messages/send", payload)
        return data.get("message", data)

    async def edit_message(
        self,
        message_id: int,
        text: str | None = None,
        *,
        bot_id: int | None = None,
        template: str | None = None,
        variables: dict[str, Any] | None = None,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Редактировать сообщение по внутреннему ID."""
        payload: dict[str, Any] = {}
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if text is not None:
            payload["text"] = text
        if template:
            payload["template"] = template
        if variables:
            payload["variables"] = variables
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup

        data = await self._post(f"/v1/messages/{message_id}/edit", payload)
        return data.get("message", data)

    async def delete_message(self, message_id: int) -> dict[str, Any]:
        """Удалить сообщение по внутреннему ID."""
        data = await self._post(f"/v1/messages/{message_id}/delete")
        return data.get("message", data)

    async def get_message(self, message_id: int) -> dict[str, Any]:
        """Получить сообщение по внутреннему ID."""
        data = await self._get(f"/v1/messages/{message_id}")
        return data.get("message", data)

    async def list_messages(
        self,
        chat_id: str | None = None,
        bot_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Список сообщений с фильтрацией."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if chat_id:
            params["chat_id"] = chat_id
        if bot_id is not None:
            params["bot_id"] = bot_id
        if status:
            params["status"] = status
        data = await self._get("/v1/messages", params)
        return data.get("items", [])

    async def pin_message(self, message_id: int, disable_notification: bool = True) -> dict[str, Any]:
        """
        Закрепить сообщение в чате.

        Args:
            message_id: Внутренний ID сообщения
            disable_notification: Не отправлять уведомление (по умолчанию True для тихого пина)

        Returns:
            Результат операции от Telegram API
        """
        payload = {"disable_notification": disable_notification}
        data = await self._post(f"/v1/messages/{message_id}/pin", payload)
        return data

    async def unpin_message(self, message_id: int) -> dict[str, Any]:
        """
        Открепить сообщение в чате.

        Args:
            message_id: Внутренний ID сообщения

        Returns:
            Результат операции от Telegram API
        """
        data = await self._delete(f"/v1/messages/{message_id}/pin")
        return data

    # === Медиа ===

    async def send_photo(
        self,
        chat_id: int | str,
        photo: str | bytes | BinaryIO,
        *,
        bot_id: int | None = None,
        caption: str | None = None,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
        request_id: str | None = None,
        dry_run: bool = False,
        filename: str = "photo.jpg",
    ) -> dict[str, Any]:
        """
        Отправить фото.

        photo: URL (str), file_id (str), bytes или BinaryIO объект.
        Если photo — строка, отправляется через JSON (URL или file_id).
        Если photo — bytes/BinaryIO, загружается через multipart.
        """
        if isinstance(photo, str):
            # URL или file_id — через JSON-эндпоинт
            payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
            if bot_id is not None:
                payload["bot_id"] = bot_id
            if caption:
                payload["caption"] = caption
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            if reply_markup:
                payload["reply_markup"] = reply_markup
            if request_id:
                payload["request_id"] = request_id
            if dry_run:
                payload["dry_run"] = True
            data = await self._post("/v1/media/send-photo", payload)
            return data.get("message", data)
        else:
            # Файл — через multipart upload
            if isinstance(photo, bytes):
                file_data = photo
            else:
                file_data = photo.read()

            form: dict[str, Any] = {"chat_id": str(chat_id)}
            if bot_id is not None:
                form["bot_id"] = str(bot_id)
            if caption:
                form["caption"] = caption
            if parse_mode:
                form["parse_mode"] = parse_mode
            if reply_to_message_id:
                form["reply_to_message_id"] = str(reply_to_message_id)
            if message_thread_id:
                form["message_thread_id"] = str(message_thread_id)
            if request_id:
                form["request_id"] = request_id
            if dry_run:
                form["dry_run"] = "true"

            files = {"file": (filename, file_data, "image/jpeg")}
            resp = await self._client.post("/v1/media/upload-photo", data=form, files=files)
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                raise TelegramAPIError(
                    f"HTTP {resp.status_code}: {detail}",
                    status_code=resp.status_code,
                    detail=detail,
                )
            result = resp.json()
            return result.get("message", result)

    async def send_document(
        self,
        chat_id: int | str,
        document: str,
        *,
        bot_id: int | None = None,
        caption: str | None = None,
        parse_mode: str | None = None,
        request_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Отправить документ по URL или file_id."""
        payload: dict[str, Any] = {"chat_id": chat_id, "document": document}
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if request_id:
            payload["request_id"] = request_id
        if dry_run:
            payload["dry_run"] = True
        data = await self._post("/v1/media/send-document", payload)
        return data.get("message", data)

    async def send_media_group(
        self,
        chat_id: int | str,
        media: list[dict[str, Any]],
        *,
        bot_id: int | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        request_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Отправить медиа-группу (альбом из 2-10 фото/видео).

        Args:
            chat_id: ID чата
            media: Список InputMedia элементов (2-10 штук)
                   Каждый элемент: {"type": "photo", "media": "file_id_or_url", "caption": "..."}
            reply_to_message_id: ID сообщения для ответа
            message_thread_id: ID топика (для форумов)
            request_id: ID запроса для трекинга
            dry_run: Сухой прогон (не отправлять реально)

        Returns:
            {"ok": True, "messages": [...], "media_group_id": "..."}

        Example:
            media = [
                {"type": "photo", "media": "https://example.com/1.jpg", "caption": "Фото 1"},
                {"type": "photo", "media": "https://example.com/2.jpg"},
                {"type": "video", "media": "file_id_here"},
            ]
            result = await api.send_media_group(chat_id, media)
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "media": media,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if request_id:
            payload["request_id"] = request_id
        if dry_run:
            payload["dry_run"] = True

        data = await self._post("/v1/media/send-media-group", payload)
        return data

    # === Forward / Copy ===

    async def forward_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        *,
        bot_id: int | None = None,
    ) -> dict[str, Any]:
        """Переслать сообщение."""
        data = await self._post("/v1/messages/forward", {
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "message_id": message_id,
            "bot_id": bot_id,
        })
        return data.get("message", data)

    async def copy_message(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        message_id: int,
        *,
        bot_id: int | None = None,
        caption: str | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        """Копировать сообщение (без пометки 'Переслано')."""
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "message_id": message_id,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if caption:
            payload["caption"] = caption
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = await self._post("/v1/messages/copy", payload)
        return data

    # === Прогресс-нотификатор ===

    def progress(
        self,
        chat_id: int | str,
        parse_mode: str | None = "HTML",
        auto_pin: bool = False,
    ) -> ProgressContext:
        """
        Контекстный менеджер для прогресс-сообщений (send → edit → delete).

        Использование:
            async with api.progress(chat_id) as p:
                await p.update(1, 5, "Загрузка данных...")
                await p.update(2, 5, "Обработка...")
            # Сообщение автоматически удаляется при выходе

        Автопин (для мониторинга долгих процессов):
            async with api.progress(chat_id, auto_pin=True) as p:
                await p.update(1, 10, "Загрузка большого файла...")
            # Сообщение закреплено (без уведомления) пока идёт процесс,
            # автоматически открепляется при завершении
        """
        return ProgressContext(self, chat_id, parse_mode=parse_mode, auto_pin=auto_pin)

    # === Шаблоны ===

    async def list_templates(self) -> list[dict[str, Any]]:
        """Список шаблонов."""
        data = await self._get("/v1/templates")
        return data.get("items", [])

    async def get_template(self, name: str) -> dict[str, Any]:
        """Получить шаблон по имени."""
        data = await self._get(f"/v1/templates/{name}")
        return data.get("template", data)

    async def render_template(self, name: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Отрендерить шаблон (без отправки)."""
        return await self._post(f"/v1/templates/{name}/render", {"variables": variables or {}})

    async def create_template(
        self,
        name: str,
        body: str,
        parse_mode: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Создать или обновить шаблон."""
        payload: dict[str, Any] = {"name": name, "body": body}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if description:
            payload["description"] = description
        data = await self._post("/v1/templates", payload)
        return data.get("template", data)

    # === Команды ===

    async def set_commands(
        self,
        commands: list[dict[str, str]],
        bot_id: int | None = None,
        scope_type: str = "default",
        chat_id: int | None = None,
        user_id: int | None = None,
        language_code: str | None = None,
    ) -> dict[str, Any]:
        """Создать набор команд."""
        payload: dict[str, Any] = {
            "scope_type": scope_type,
            "commands": commands,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if chat_id is not None:
            payload["chat_id"] = chat_id
        if user_id is not None:
            payload["user_id"] = user_id
        if language_code:
            payload["language_code"] = language_code
        data = await self._post("/v1/commands", payload)
        return data.get("command_set", data)

    async def sync_commands(self, command_set_id: int, bot_id: int | None = None) -> dict[str, Any]:
        """Синхронизировать набор команд с Telegram."""
        return await self._post("/v1/commands/sync", {"command_set_id": command_set_id, "bot_id": bot_id})

    async def list_command_sets(self) -> list[dict[str, Any]]:
        """Список наборов команд."""
        data = await self._get("/v1/commands")
        return data.get("items", [])

    # === Callback Queries ===

    async def answer_callback(
        self,
        callback_query_id: str,
        bot_id: int | None = None,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        """Ответить на callback_query."""
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True
        return await self._post("/v1/callbacks/answer", payload)

    # === Чаты ===

    async def get_chat(self, chat_id: int | str, bot_id: int | None = None) -> dict[str, Any]:
        """Информация о чате от Telegram API."""
        params = {"bot_id": bot_id} if bot_id is not None else None
        data = await self._get(f"/v1/chats/{chat_id}", params=params)
        return data.get("chat", data)

    async def get_chat_member(self, chat_id: int | str, user_id: int, bot_id: int | None = None) -> dict[str, Any]:
        """Информация об участнике чата."""
        params = {"bot_id": bot_id} if bot_id is not None else None
        data = await self._get(f"/v1/chats/{chat_id}/members/{user_id}", params=params)
        return data.get("member", data)

    async def list_chats(
        self,
        bot_id: int | None = None,
        chat_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Список чатов из локальной БД."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if bot_id is not None:
            params["bot_id"] = bot_id
        if chat_type:
            params["chat_type"] = chat_type
        data = await self._get("/v1/chats", params)
        return data.get("items", [])

    async def set_chat_alias(self, chat_id: int | str, alias: str) -> dict[str, Any]:
        """Установить алиас чата."""
        data = await self._request("PUT", f"/v1/chats/{chat_id}/alias", json={"alias": alias})
        return data.get("chat", data)

    async def get_chat_by_alias(self, alias: str) -> dict[str, Any]:
        """Получить чат по алиасу."""
        data = await self._get(f"/v1/chats/by-alias/{alias}")
        return data.get("chat", data)

    async def get_chat_history(
        self,
        chat_id: int | str,
        bot_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """История сообщений чата из локальной БД."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if bot_id is not None:
            params["bot_id"] = bot_id
        data = await self._get(f"/v1/chats/{chat_id}/history", params)
        return data.get("items", [])

    # === Вебхук / Обновления ===

    async def list_updates(
        self,
        limit: int = 100,
        update_type: str | None = None,
        bot_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Список входящих обновлений."""
        params: dict[str, Any] = {"limit": limit}
        if update_type:
            params["update_type"] = update_type
        if bot_id is not None:
            params["bot_id"] = bot_id
        data = await self._get("/v1/updates", params)
        return data.get("items", [])

    async def set_webhook(self, url: str, bot_id: int | None = None, **kwargs: Any) -> dict[str, Any]:
        """Настроить вебхук."""
        payload = {"url": url, **kwargs}
        if bot_id is not None:
            payload["bot_id"] = bot_id
        return await self._post("/v1/webhook/set", payload)

    async def delete_webhook(self, bot_id: int | None = None) -> dict[str, Any]:
        """Удалить вебхук."""
        if bot_id is None:
            return await self._delete("/v1/webhook")
        return await self._request("DELETE", "/v1/webhook", params={"bot_id": bot_id})

    async def get_webhook_info(self, bot_id: int | None = None) -> dict[str, Any]:
        """Текущая конфигурация вебхука."""
        params = {"bot_id": bot_id} if bot_id is not None else None
        data = await self._get("/v1/webhook/info", params=params)
        return data.get("webhook_info", data)

    # === Опросы ===

    async def send_poll(
        self,
        chat_id: int | str,
        question: str,
        options: list[str],
        *,
        bot_id: int | None = None,
        is_anonymous: bool = True,
        type: str = "regular",
        allows_multiple_answers: bool = False,
        correct_option_id: int | None = None,
        explanation: str | None = None,
        explanation_parse_mode: str | None = None,
        open_period: int | None = None,
        close_date: int | None = None,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
        dry_run: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Создание опроса или викторины.

        type: "regular" или "quiz"
        correct_option_id: индекс правильного ответа (для quiz)
        explanation: пояснение для quiz (до 200 символов)
        open_period: время жизни опроса в секундах (5-600)
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "question": question,
            "options": options,
            "is_anonymous": is_anonymous,
            "type": type,
            "allows_multiple_answers": allows_multiple_answers,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if correct_option_id is not None:
            payload["correct_option_id"] = correct_option_id
        if explanation:
            payload["explanation"] = explanation
        if explanation_parse_mode:
            payload["explanation_parse_mode"] = explanation_parse_mode
        if open_period is not None:
            payload["open_period"] = open_period
        if close_date:
            payload["close_date"] = close_date
        if message_thread_id:
            payload["message_thread_id"] = message_thread_id
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if dry_run:
            payload["dry_run"] = True
        if request_id:
            payload["request_id"] = request_id

        data = await self._post("/v1/polls/send", payload)
        return data.get("message", data)

    async def stop_poll(self, chat_id: int | str, message_id: int, bot_id: int | None = None) -> dict[str, Any]:
        """
        Остановить опрос с показом результатов.

        message_id: telegram_message_id (не внутренний ID).
        """
        if bot_id is None:
            data = await self._post(f"/v1/polls/{chat_id}/{message_id}/stop")
        else:
            data = await self._post(f"/v1/polls/{chat_id}/{message_id}/stop?bot_id={bot_id}")
        return data.get("poll", data)

    async def list_polls(
        self,
        chat_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Список опросов."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if chat_id:
            params["chat_id"] = chat_id
        data = await self._get("/v1/polls", params)
        return data.get("items", [])

    async def get_poll(self, poll_id: str) -> dict[str, Any]:
        """Получить опрос по poll_id."""
        data = await self._get(f"/v1/polls/{poll_id}")
        return data.get("poll", data)

    # === Реакции ===

    async def set_reaction(
        self,
        chat_id: int | str,
        message_id: int,
        bot_id: int | None = None,
        reaction: list[dict[str, Any]] | None = None,
        is_big: bool = False,
    ) -> dict[str, Any]:
        """
        Установить реакцию на сообщение.

        message_id: telegram_message_id (не внутренний ID).
        reaction: список реакций, например:
            [{"type": "emoji", "emoji": "👍"}]
            [{"type": "custom_emoji", "custom_emoji_id": "12345"}]
            None — удалить все реакции бота
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "is_big": is_big,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if reaction is not None:
            payload["reaction"] = reaction
        return await self._post("/v1/reactions/set", payload)

    async def list_reactions(
        self,
        message_id: int | None = None,
        chat_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Список реакций с фильтрацией."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if message_id is not None:
            params["message_id"] = message_id
        if chat_id:
            params["chat_id"] = chat_id
        if user_id:
            params["user_id"] = user_id
        data = await self._get("/v1/reactions", params)
        return data.get("items", [])

    # === Checklists (Bot API 9.1) ===

    async def send_checklist(
        self,
        chat_id: int | str,
        title: str,
        tasks: list[dict[str, Any]],
        *,
        bot_id: int | None = None,
        business_connection_id: str | None = None,
        message_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Отправить чек-лист (Bot API 9.1).

        Args:
            chat_id: ID чата
            title: Заголовок чек-листа (до 128 символов)
            tasks: Список задач [{"text": "...", "is_completed": False}, ...]
            business_connection_id: ID бизнес-подключения (для бизнес-аккаунтов)
            message_thread_id: ID топика (для супергрупп с топиками)
            reply_to_message_id: ID сообщения для ответа
            request_id: Произвольный ID запроса для трекинга

        Returns:
            Ответ с данными сообщения
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "checklist": {
                "title": title,
                "tasks": tasks,
            },
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if business_connection_id is not None:
            payload["business_connection_id"] = business_connection_id
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if request_id is not None:
            payload["request_id"] = request_id
        return await self._post("/v1/checklists/send", payload)

    async def edit_checklist(
        self,
        message_id: int,
        title: str,
        tasks: list[dict[str, Any]],
        bot_id: int | None = None,
        business_connection_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Редактировать чек-лист.

        Args:
            message_id: Внутренний ID сообщения
            title: Заголовок чек-листа
            tasks: Обновлённый список задач
            business_connection_id: ID бизнес-подключения

        Returns:
            Ответ с обновлённым сообщением
        """
        payload: dict[str, Any] = {
            "checklist": {
                "title": title,
                "tasks": tasks,
            },
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        if business_connection_id is not None:
            payload["business_connection_id"] = business_connection_id
        return await self._request("PUT", f"/v1/messages/{message_id}/checklist", json=payload)

    # === Stars & Gifts (Bot API 9.1+) ===

    async def get_star_balance(self, bot_id: int | None = None) -> dict[str, Any]:
        """
        Получить баланс звёзд бота (Bot API 9.1).

        Returns:
            {"star_count": N}
        """
        params = {"bot_id": bot_id} if bot_id is not None else None
        return await self._get("/v1/stars/balance", params=params)

    async def gift_premium(
        self,
        user_id: int,
        duration_months: int,
        star_count: int,
        bot_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Подарить премиум-подписку пользователю за звёзды (Bot API 9.3).

        Args:
            user_id: ID пользователя
            duration_months: Длительность (1-12 месяцев)
            star_count: Стоимость в звёздах

        Returns:
            Подтверждение операции
        """
        payload = {
            "user_id": user_id,
            "duration_months": duration_months,
            "star_count": star_count,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        return await self._post("/v1/gifts/premium", payload)

    async def get_user_gifts(self, user_id: int, bot_id: int | None = None) -> list[dict[str, Any]]:
        """
        Получить подарки пользователя (Bot API 9.3).

        Args:
            user_id: ID пользователя

        Returns:
            Список подарков
        """
        params = {"bot_id": bot_id} if bot_id is not None else None
        data = await self._get(f"/v1/gifts/user/{user_id}", params=params)
        return data.get("result", [])

    async def get_chat_gifts(self, chat_id: int | str, bot_id: int | None = None) -> list[dict[str, Any]]:
        """
        Получить подарки в чате (Bot API 9.3).

        Args:
            chat_id: ID чата

        Returns:
            Список подарков
        """
        params = {"bot_id": bot_id} if bot_id is not None else None
        data = await self._get(f"/v1/gifts/chat/{chat_id}", params=params)
        return data.get("result", [])

    # === Stories (Bot API 9.3) ===

    async def repost_story(
        self,
        chat_id: int | str,
        from_chat_id: int | str,
        story_id: int,
        bot_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Репостнуть историю в канал (Bot API 9.3).

        Args:
            chat_id: ID канала-получателя
            from_chat_id: ID канала-источника
            story_id: ID истории

        Returns:
            Данные репостнутой истории
        """
        payload = {
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "story_id": story_id,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        return await self._post("/v1/stories/repost", payload)

    # === Prediction Markets (Betting) ===

    async def create_prediction_event(
        self,
        title: str,
        description: str,
        options: list[dict[str, Any]],
        creator_id: int,
        *,
        bot_id: int | None = None,
        chat_id: int | str | None = None,
        deadline: str | None = None,
        resolution_date: str | None = None,
        min_bet: int = 1,
        max_bet: int = 1000,
        is_anonymous: bool = True,
    ) -> dict[str, Any]:
        """
        Создать событие для ставок (Polymarket-style).

        Args:
            title: Заголовок события
            description: Описание
            options: Варианты ответов [{"id": "1", "text": "16%", "value": "16"}, ...]
            creator_id: ID создателя
            chat_id: ID чата для публикации (None = личное)
            deadline: ISO datetime дедлайна ставок
            resolution_date: ISO datetime разрешения
            min_bet: Минимальная ставка в Stars
            max_bet: Максимальная ставка в Stars
            is_anonymous: Обезличенные ставки (default: True)

        Returns:
            {"event_id": N}
        """
        payload = {
            "bot_id": bot_id,
            "title": title,
            "description": description,
            "options": options,
            "creator_id": creator_id,
            "chat_id": chat_id,
            "deadline": deadline,
            "resolution_date": resolution_date,
            "min_bet": min_bet,
            "max_bet": max_bet,
            "is_anonymous": is_anonymous,
        }
        return await self._post("/v1/predictions/events", payload)

    async def place_bet(
        self,
        event_id: int,
        option_id: str,
        amount: int,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Разместить ставку на событие.

        Args:
            event_id: ID события
            option_id: ID варианта
            amount: Сумма ставки в Stars
            user_id: ID пользователя

        Returns:
            {"bet_id": N, "transaction_id": M, "invoice": {...}}
        """
        payload = {
            "event_id": event_id,
            "option_id": option_id,
            "amount": amount,
            "user_id": user_id,
        }
        return await self._post("/v1/predictions/bets", payload)

    async def resolve_prediction_event(
        self,
        event_id: int,
        winning_option_ids: list[str],
        resolution_source: str,
        resolution_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Разрешить событие и выплатить выигрыши.

        Args:
            event_id: ID события
            winning_option_ids: ID победивших вариантов
            resolution_source: Источник решения (llm-mcp/ollama/openrouter/manual)
            resolution_data: Данные от LLM/новости

        Returns:
            {"winners": N, "total_payout": M}
        """
        payload = {
            "event_id": event_id,
            "winning_option_ids": winning_option_ids,
            "resolution_source": resolution_source,
            "resolution_data": resolution_data,
        }
        return await self._post(f"/v1/predictions/events/{event_id}/resolve", payload)

    async def list_prediction_events(
        self,
        status: str | None = None,
        chat_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Список событий для ставок."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if chat_id:
            params["chat_id"] = chat_id
        data = await self._get("/v1/predictions/events", params)
        return data.get("events", [])

    async def get_prediction_event(self, event_id: int) -> dict[str, Any]:
        """Детали события."""
        data = await self._get(f"/v1/predictions/events/{event_id}")
        return data.get("event", {})

    async def list_user_bets(
        self,
        user_id: int,
        event_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Ставки пользователя."""
        params: dict[str, Any] = {"user_id": user_id, "limit": limit}
        if event_id:
            params["event_id"] = event_id
        if status:
            params["status"] = status
        data = await self._get("/v1/predictions/bets", params)
        return data.get("bets", [])

    # === Stars Payments ===

    async def create_star_invoice(
        self,
        chat_id: int | str,
        title: str,
        description: str,
        amount: int,
        payload: str,
        bot_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Создать счёт на оплату Stars.

        Args:
            chat_id: ID чата
            title: Заголовок счёта
            description: Описание
            amount: Сумма в Stars
            payload: Внутренний ID для идентификации

        Returns:
            Invoice данные
        """
        invoice_payload = {
            "chat_id": chat_id,
            "title": title,
            "description": description,
            "payload": payload,
            "currency": "XTR",
            "prices": [{"label": title, "amount": amount}],
        }
        if bot_id is not None:
            invoice_payload["bot_id"] = bot_id
        return await self._post("/v1/stars/invoice", invoice_payload)

    async def refund_star_payment(
        self,
        user_id: int,
        telegram_payment_charge_id: str,
        bot_id: int | None = None,
    ) -> dict[str, Any]:
        """Возврат Stars платежа."""
        payload = {
            "user_id": user_id,
            "telegram_payment_charge_id": telegram_payment_charge_id,
        }
        if bot_id is not None:
            payload["bot_id"] = bot_id
        return await self._post("/v1/stars/refund", payload)

    async def get_star_transactions(
        self,
        bot_id: int | None = None,
        user_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """История транзакций Stars."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if bot_id is not None:
            params["bot_id"] = bot_id
        if user_id:
            params["user_id"] = user_id
        data = await self._get("/v1/stars/transactions", params)
        return data.get("transactions", [])

    # === Мониторинг ===

    async def health(self) -> dict[str, Any]:
        """Проверка здоровья сервиса."""
        return await self._get("/health")

    async def metrics(self) -> dict[str, Any]:
        """Метрики сообщений по статусам."""
        return await self._get("/v1/metrics")

    async def get_bot_info(self, bot_id: int | None = None) -> dict[str, Any]:
        """Информация о боте (getMe)."""
        params = {"bot_id": bot_id} if bot_id is not None else None
        data = await self._get("/v1/bot/me", params=params)
        return data.get("bot", data)

    async def list_bots(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        """Список зарегистрированных ботов."""
        data = await self._get("/v1/bots", {"include_inactive": include_inactive})
        return data.get("items", [])

    async def register_bot(self, token: str, is_default: bool | None = None) -> dict[str, Any]:
        """Зарегистрировать бота по токену."""
        payload: dict[str, Any] = {"token": token}
        if is_default is not None:
            payload["is_default"] = is_default
        data = await self._post("/v1/bots", payload)
        return data.get("bot", data)

    async def get_default_bot(self) -> dict[str, Any]:
        """Получить дефолтного бота."""
        data = await self._get("/v1/bots/default")
        return data.get("bot", data)

    async def set_default_bot(self, bot_id: int) -> dict[str, Any]:
        """Установить дефолтного бота."""
        data = await self._request("PUT", f"/v1/bots/{bot_id}/default", json={})
        return data.get("bot", data)

    # === CommandHandler Pattern ===

    def command(
        self,
        command: str,
        chat_id: int | str | None = None,
        user_id: int | str | None = None,
    ) -> Callable[[Callable[[dict, list[str]], Awaitable[None]]], Callable[[dict, list[str]], Awaitable[None]]]:
        """
        Декоратор для регистрации обработчика команды.

        Args:
            command: Имя команды (без /)
            chat_id: Фильтр по chat_id (guard pattern)
            user_id: Фильтр по user_id (guard pattern)

        Пример:
            @api.command("start")
            async def start_handler(update, args):
                chat_id = update["message"]["chat"]["id"]
                await api.send_message(chat_id, "Привет!")

            @api.command("admin", chat_id=-100123456)  # Только этот чат
            async def admin_handler(update, args):
                # Доступно только в чате -100123456
                await api.send_message(update["message"]["chat"]["id"], "Admin panel")
        """
        def decorator(handler: Callable[[dict, list[str]], Awaitable[None]]) -> Callable[[dict, list[str]], Awaitable[None]]:
            self._command_registry.register(command, handler, chat_id=chat_id, user_id=user_id)
            return handler
        return decorator

    async def start_polling(
        self,
        timeout: int = 30,
        limit: int = 100,
        allowed_updates: list[str] | None = None,
        bot_id: int | None = None,
    ) -> None:
        """
        Запуск long polling для получения обновлений и обработки команд.

        Args:
            timeout: Таймаут long polling (секунды)
            limit: Максимум обновлений за раз
            allowed_updates: Фильтр типов обновлений (["message", "callback_query", ...])
            bot_id: Явный bot_id для мультибот polling

        Пример:
            api = TelegramAPI("http://localhost:8081")

            @api.command("start")
            async def start(update, args):
                await api.send_message(
                    chat_id=update["message"]["chat"]["id"],
                    text="Привет! Я бот."
                )

            # Запуск polling (блокирующий вызов)
            await api.start_polling()
        """
        if self._polling_manager is None:
            self._polling_manager = PollingManager(self, self._command_registry)

        await self._polling_manager.start(
            timeout=timeout,
            limit=limit,
            allowed_updates=allowed_updates,
            bot_id=bot_id,
        )

    def stop_polling(self) -> None:
        """Остановка long polling."""
        if self._polling_manager:
            self._polling_manager.stop()

    def list_commands(self) -> list[str]:
        """Список зарегистрированных команд."""
        return self._command_registry.list_commands()


class ProgressContext:
    """
    Контекстный менеджер для прогресс-сообщений.

    Паттерн send → edit → delete:
    - Первый вызов update() отправляет сообщение
    - Последующие вызовы редактируют его
    - При выходе из контекста — удаляет сообщение

    Аналог ProgressNotifier из монолита, но через telegram-api.

    Поддержка автопина:
    - При auto_pin=True сообщение автоматически закрепляется (без уведомления)
    - При завершении — автоматически открепляется
    """

    def __init__(
        self,
        api: TelegramAPI,
        chat_id: int | str,
        parse_mode: str | None = "HTML",
        min_interval: float = 0.8,
        auto_pin: bool = False,
    ):
        self._api = api
        self._chat_id = chat_id
        self._parse_mode = parse_mode
        self._min_interval = min_interval
        self._auto_pin = auto_pin
        self._message_id: int | None = None
        self._last_edit_ts: float = 0.0
        self._is_pinned: bool = False

    async def __aenter__(self) -> ProgressContext:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.done()

    async def update(self, stage: int, total: int, text: str) -> None:
        """
        Обновить прогресс-сообщение.

        stage: текущий этап (1-based)
        total: всего этапов
        text: описание текущего этапа
        """
        progress_bar = self._bar(stage, total)
        full_text = f"[{stage}/{total}] {text}\n{progress_bar}"

        loop = asyncio.get_event_loop()
        now = loop.time()

        if self._message_id is None:
            # Первый вызов — отправляем новое сообщение
            msg = await self._api.send_message(
                self._chat_id,
                full_text,
                parse_mode=self._parse_mode,
                live=True,
            )
            self._message_id = msg.get("id")
            self._last_edit_ts = now

            # Автопин (тихий, без уведомления)
            if self._auto_pin and self._message_id:
                try:
                    await self._api.pin_message(self._message_id, disable_notification=True)
                    self._is_pinned = True
                except Exception:
                    pass  # Игнорируем ошибки пина (могут быть права доступа)
        else:
            # Throttle — не чаще min_interval
            if now - self._last_edit_ts < self._min_interval:
                return
            try:
                await self._api.edit_message(self._message_id, text=full_text, parse_mode=self._parse_mode)
                self._last_edit_ts = now
            except Exception:
                pass

    async def done(self, final_text: str | None = None) -> None:
        """Завершить прогресс: показать финальный текст или удалить сообщение."""
        if self._message_id is None:
            return

        # Автоанпин перед завершением
        if self._is_pinned:
            try:
                await self._api.unpin_message(self._message_id)
                self._is_pinned = False
            except Exception:
                pass

        if final_text:
            try:
                await self._api.edit_message(self._message_id, text=final_text, parse_mode=self._parse_mode)
            except Exception:
                pass
        else:
            try:
                await self._api.delete_message(self._message_id)
            except Exception:
                pass
        self._message_id = None

    @staticmethod
    def _bar(current: int, total: int, width: int = 10) -> str:
        filled = int(width * current / total) if total > 0 else 0
        return "\u2593" * filled + "\u2591" * (width - filled)
