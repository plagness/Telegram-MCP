"""Pydantic-модели для входящих запросов и reply markup."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ParseMode = Literal["HTML", "MarkdownV2", "Markdown"]


# === Reply Markup ===


class WebAppInfo(BaseModel):
    """Информация о Web App (Mini App)."""
    url: str


class LoginUrl(BaseModel):
    """OAuth-логин через бота."""
    url: str
    forward_text: str | None = None
    bot_username: str | None = None
    request_write_access: bool | None = None


class SwitchInlineQueryChosenChat(BaseModel):
    """Выбор чата для inline-запроса."""
    query: str | None = None
    allow_user_chats: bool | None = None
    allow_bot_chats: bool | None = None
    allow_group_chats: bool | None = None
    allow_channel_chats: bool | None = None


class CallbackGame(BaseModel):
    """Запуск игры (пустой объект)."""
    pass


class CopyTextButton(BaseModel):
    """Копирование текста в буфер."""
    text: str


class InlineKeyboardButton(BaseModel):
    """
    Кнопка в inline-клавиатуре.

    Поддерживаемые типы (только один из параметров):
    - url: открыть ссылку
    - callback_data: отправить callback_query
    - web_app: запустить Mini App
    - login_url: OAuth-авторизация
    - switch_inline_query: переключить в inline-режим в другом чате
    - switch_inline_query_current_chat: inline-режим в текущем чате
    - switch_inline_query_chosen_chat: выбор чата для inline-запроса
    - callback_game: запуск игры
    - pay: кнопка оплаты
    - copy_text: копирование текста
    """
    text: str
    url: str | None = None
    callback_data: str | None = None
    web_app: WebAppInfo | None = None
    login_url: LoginUrl | None = None
    switch_inline_query: str | None = None
    switch_inline_query_current_chat: str | None = None
    switch_inline_query_chosen_chat: SwitchInlineQueryChosenChat | None = None
    callback_game: CallbackGame | None = None
    pay: bool | None = None
    copy_text: CopyTextButton | None = None


class InlineKeyboardMarkup(BaseModel):
    """Inline-клавиатура (кнопки под сообщением)."""
    inline_keyboard: list[list[InlineKeyboardButton]]


class KeyboardButton(BaseModel):
    """Кнопка в reply-клавиатуре."""
    text: str
    request_contact: bool | None = None
    request_location: bool | None = None


class ReplyKeyboardMarkup(BaseModel):
    """Reply-клавиатура (замена стандартной клавиатуры)."""
    keyboard: list[list[KeyboardButton]]
    resize_keyboard: bool | None = None
    one_time_keyboard: bool | None = None
    selective: bool | None = None


class ReplyKeyboardRemove(BaseModel):
    """Убрать reply-клавиатуру."""
    remove_keyboard: bool = True
    selective: bool | None = None


class ForceReply(BaseModel):
    """Принудительный ответ (reply)."""
    force_reply: bool = True
    selective: bool | None = None


# Объединённый тип для reply_markup
ReplyMarkup = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | ForceReply


# === Сообщения ===


class SendMessageIn(BaseModel):
    """Входящий запрос на отправку текстового сообщения."""
    chat_id: int | str
    text: str | None = None
    template: str | None = None
    variables: dict[str, Any] | None = None
    parse_mode: ParseMode | None = None
    disable_web_page_preview: bool | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    request_id: str | None = None
    live: bool = False
    dry_run: bool = False


class EditMessageIn(BaseModel):
    """Входящий запрос на редактирование сообщения."""
    text: str | None = None
    template: str | None = None
    variables: dict[str, Any] | None = None
    parse_mode: ParseMode | None = None
    reply_markup: dict[str, Any] | None = None


# === Медиа ===


class SendPhotoIn(BaseModel):
    """Отправка фото по URL или file_id (JSON-режим)."""
    chat_id: int | str
    photo: str  # URL или file_id
    caption: str | None = None
    parse_mode: ParseMode | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    request_id: str | None = None
    dry_run: bool = False


class SendDocumentIn(BaseModel):
    """Отправка документа по URL или file_id (JSON-режим)."""
    chat_id: int | str
    document: str  # URL или file_id
    caption: str | None = None
    parse_mode: ParseMode | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    request_id: str | None = None
    dry_run: bool = False


class SendVideoIn(BaseModel):
    """Отправка видео по URL или file_id (JSON-режим)."""
    chat_id: int | str
    video: str  # URL или file_id
    caption: str | None = None
    parse_mode: ParseMode | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    request_id: str | None = None
    dry_run: bool = False


# === Callback Query ===


class AnswerCallbackIn(BaseModel):
    """Ответ на callback_query (нажатие inline-кнопки)."""
    callback_query_id: str
    text: str | None = None
    show_alert: bool = False
    url: str | None = None
    cache_time: int | None = None


# === Forward / Copy ===


class ForwardMessageIn(BaseModel):
    """Пересылка сообщения."""
    chat_id: int | str
    from_chat_id: int | str
    message_id: int


class CopyMessageIn(BaseModel):
    """Копирование сообщения."""
    chat_id: int | str
    from_chat_id: int | str
    message_id: int
    caption: str | None = None
    parse_mode: ParseMode | None = None
    reply_markup: dict[str, Any] | None = None


class PinMessageIn(BaseModel):
    """Закрепление сообщения в чате."""
    disable_notification: bool = Field(
        default=True,
        description="Не отправлять уведомление о закреплении (по умолчанию True для тихого пина)"
    )


class UnpinMessageIn(BaseModel):
    """Открепление сообщения в чате (опционально)."""
    pass  # Пустая модель, все параметры берутся из URL


# === Вебхуки ===


class SetWebhookIn(BaseModel):
    """Настройка вебхука."""
    url: str
    secret_token: str | None = None
    max_connections: int | None = None
    allowed_updates: list[str] | None = None


# === Шаблоны ===


class TemplateCreateIn(BaseModel):
    """Создание или обновление шаблона."""
    name: str = Field(..., min_length=2, max_length=120)
    parse_mode: ParseMode | None = None
    description: str | None = None
    body: str


class TemplateRenderIn(BaseModel):
    """Рендеринг шаблона с переменными."""
    variables: dict[str, Any] | None = None


# === Команды ===


class CommandDefinition(BaseModel):
    """Определение одной команды бота."""
    command: str
    description: str


class CommandSetIn(BaseModel):
    """Создание набора команд по скоупу."""
    scope_type: str = "default"
    chat_id: int | None = None
    user_id: int | None = None
    language_code: str | None = None
    commands: list[CommandDefinition]


class CommandSyncIn(BaseModel):
    """Синхронизация набора команд с Telegram."""
    command_set_id: int | None = None


# === Опросы ===


class PollOption(BaseModel):
    """Вариант ответа в опросе."""
    text: str
    text_entities: list[dict[str, Any]] | None = None


class SendPollIn(BaseModel):
    """Создание опроса или викторины."""
    chat_id: int | str
    question: str = Field(..., min_length=1, max_length=300)
    options: list[str | PollOption] = Field(..., min_length=2, max_length=10)
    is_anonymous: bool = True
    type: Literal["quiz", "regular"] = "regular"
    allows_multiple_answers: bool = False
    correct_option_id: int | None = None
    explanation: str | None = Field(None, max_length=200)
    explanation_parse_mode: ParseMode | None = None
    explanation_entities: list[dict[str, Any]] | None = None
    open_period: int | None = Field(None, ge=5, le=600)
    close_date: int | None = None
    is_closed: bool = False
    disable_notification: bool = False
    protect_content: bool = False
    message_thread_id: int | None = None
    reply_to_message_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    request_id: str | None = None
    dry_run: bool = False


# === Реакции ===


class ReactionTypeEmoji(BaseModel):
    """Реакция обычным эмодзи."""
    type: Literal["emoji"] = "emoji"
    emoji: str


class ReactionTypeCustomEmoji(BaseModel):
    """Реакция кастомным эмодзи."""
    type: Literal["custom_emoji"] = "custom_emoji"
    custom_emoji_id: str


class ReactionTypePaid(BaseModel):
    """Платная Star-реакция."""
    type: Literal["paid"] = "paid"


ReactionType = ReactionTypeEmoji | ReactionTypeCustomEmoji | ReactionTypePaid


class SetMessageReactionIn(BaseModel):
    """Установка реакции на сообщение."""
    chat_id: int | str
    message_id: int  # telegram_message_id (не внутренний ID)
    reaction: list[ReactionType] | None = None
    is_big: bool = False
