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
    bot_id: int | None = None
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
    bot_id: int | None = None
    text: str | None = None
    template: str | None = None
    variables: dict[str, Any] | None = None
    parse_mode: ParseMode | None = None
    reply_markup: dict[str, Any] | None = None


# === Медиа ===


class SendPhotoIn(BaseModel):
    """Отправка фото по URL или file_id (JSON-режим)."""
    bot_id: int | None = None
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
    bot_id: int | None = None
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
    bot_id: int | None = None
    chat_id: int | str
    video: str  # URL или file_id
    caption: str | None = None
    parse_mode: ParseMode | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    reply_markup: dict[str, Any] | None = None
    request_id: str | None = None
    dry_run: bool = False


class SendAnimationIn(BaseModel):
    """Отправка анимации/GIF по URL или file_id."""
    bot_id: int | None = None
    chat_id: int | str
    animation: str
    caption: str | None = None
    parse_mode: ParseMode | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    request_id: str | None = None
    dry_run: bool = False


class SendAudioIn(BaseModel):
    """Отправка аудио по URL или file_id."""
    bot_id: int | None = None
    chat_id: int | str
    audio: str
    caption: str | None = None
    parse_mode: ParseMode | None = None
    duration: int | None = None
    performer: str | None = None
    title: str | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    request_id: str | None = None
    dry_run: bool = False


class SendVoiceIn(BaseModel):
    """Отправка голосового сообщения по URL или file_id."""
    bot_id: int | None = None
    chat_id: int | str
    voice: str
    caption: str | None = None
    parse_mode: ParseMode | None = None
    duration: int | None = None
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    request_id: str | None = None
    dry_run: bool = False


class SendStickerIn(BaseModel):
    """Отправка стикера по file_id."""
    bot_id: int | None = None
    chat_id: int | str
    sticker: str  # file_id (стикеры обычно только по file_id)
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    request_id: str | None = None
    dry_run: bool = False


# === Media Groups (альбомы) ===


class InputMedia(BaseModel):
    """Базовый класс для InputMedia элементов."""
    type: Literal["photo", "video", "document", "audio"]
    media: str  # file_id или URL
    caption: str | None = None
    parse_mode: ParseMode | None = None


class SendMediaGroupIn(BaseModel):
    """Отправка альбома (группы медиа)."""
    bot_id: int | None = None
    chat_id: int | str
    media: list[InputMedia] = Field(..., min_length=2, max_length=10)
    reply_to_message_id: int | None = None
    message_thread_id: int | None = None
    request_id: str | None = None
    dry_run: bool = False


# === Callback Query ===


class AnswerCallbackIn(BaseModel):
    """Ответ на callback_query (нажатие inline-кнопки)."""
    bot_id: int | None = None
    callback_query_id: str
    text: str | None = None
    show_alert: bool = False
    url: str | None = None
    cache_time: int | None = None


# === Forward / Copy ===


class ForwardMessageIn(BaseModel):
    """Пересылка сообщения."""
    bot_id: int | None = None
    chat_id: int | str
    from_chat_id: int | str
    message_id: int


class CopyMessageIn(BaseModel):
    """Копирование сообщения."""
    bot_id: int | None = None
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
    bot_id: int | None = None
    url: str
    secret_token: str | None = None
    max_connections: int | None = None
    allowed_updates: list[str] | None = None


# === Bots / Chats ===


class RegisterBotIn(BaseModel):
    """Регистрация нового бота по токену."""
    token: str = Field(..., min_length=10)
    is_default: bool | None = None


class SetChatAliasIn(BaseModel):
    """Установка короткого алиаса для чата."""
    alias: str = Field(..., min_length=2, max_length=120)


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
    bot_id: int | None = None
    scope_type: str = "default"
    chat_id: int | None = None
    user_id: int | None = None
    language_code: str | None = None
    commands: list[CommandDefinition]


class CommandSyncIn(BaseModel):
    """Синхронизация набора команд с Telegram."""
    command_set_id: int | None = None
    bot_id: int | None = None


# === Updates ===


class UpdatesAckIn(BaseModel):
    """Подтверждение обработанного offset для polling."""
    offset: int
    bot_id: int | None = None


# === Опросы ===


class PollOption(BaseModel):
    """Вариант ответа в опросе."""
    text: str
    text_entities: list[dict[str, Any]] | None = None


class SendPollIn(BaseModel):
    """Создание опроса или викторины."""
    bot_id: int | None = None
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
    bot_id: int | None = None
    chat_id: int | str
    message_id: int  # telegram_message_id (не внутренний ID)
    reaction: list[ReactionType] | None = None
    is_big: bool = False


# === Checklists (Bot API 9.1) ===


class ChecklistTask(BaseModel):
    """Задача в чек-листе."""
    text: str = Field(..., max_length=256)
    is_completed: bool = False


class InputChecklist(BaseModel):
    """Чек-лист (Bot API 9.1)."""
    title: str = Field(..., max_length=128)
    tasks: list[ChecklistTask] = Field(..., min_length=1, max_length=30)


class SendChecklistIn(BaseModel):
    """Отправка чек-листа (Bot API 9.1)."""
    bot_id: int | None = None
    chat_id: int | str
    checklist: InputChecklist
    business_connection_id: str | None = None
    message_thread_id: int | None = None
    reply_to_message_id: int | None = None
    request_id: str | None = None


class EditChecklistIn(BaseModel):
    """Редактирование чек-листа."""
    bot_id: int | None = None
    checklist: InputChecklist
    business_connection_id: str | None = None


# === Stars & Gifts (Bot API 9.1+) ===


class GiftPremiumIn(BaseModel):
    """Подарить премиум-подписку за звёзды."""
    bot_id: int | None = None
    user_id: int
    duration_months: int = Field(..., ge=1, le=12)
    star_count: int


class RepostStoryIn(BaseModel):
    """Репост истории (Bot API 9.3)."""
    bot_id: int | None = None
    chat_id: int | str
    from_chat_id: int | str
    story_id: int


# === Stars Payments ===


class LabeledPrice(BaseModel):
    """Цена с описанием."""
    label: str
    amount: int  # Сумма в минимальных единицах (для Stars = количество звёзд)


class SendInvoiceIn(BaseModel):
    """Создание счёта на оплату Stars."""
    bot_id: int | None = None
    chat_id: int | str
    title: str = Field(..., max_length=32)
    description: str = Field(..., max_length=255)
    payload: str = Field(..., max_length=128, description="Внутренний ID для идентификации платежа")
    currency: str = Field(default="XTR", description="Валюта (XTR для Stars)")
    prices: list[LabeledPrice] = Field(..., min_length=1)
    message_thread_id: int | None = None
    reply_to_message_id: int | None = None


class RefundStarPaymentIn(BaseModel):
    """Возврат Stars платежа."""
    bot_id: int | None = None
    user_id: int
    telegram_payment_charge_id: str


# === Prediction Markets (Betting) ===


class PredictionOption(BaseModel):
    """Вариант ответа в событии."""
    id: str = Field(..., description="Уникальный ID варианта")
    text: str = Field(..., max_length=100, description="Текст варианта")
    value: str | None = Field(None, description="Числовое значение (например, '16.5%')")


class CreatePredictionEventIn(BaseModel):
    """Создание события для ставок."""
    bot_id: int | None = None
    title: str = Field(..., max_length=200)
    description: str = Field(..., max_length=1000)
    options: list[PredictionOption] = Field(..., min_length=2, max_length=10)
    deadline: str | None = Field(None, description="ISO datetime дедлайна события")
    resolution_date: str | None = Field(None, description="ISO datetime разрешения (если без фиксированной даты, нейронка решит)")
    currency: str = Field(default="XTR", description="Валюта ставок: XTR (Stars), AC (виртуальная), TON")
    min_bet: int = Field(default=1, ge=1, description="Минимальная ставка")
    max_bet: int = Field(default=1000, ge=1, description="Максимальная ставка")
    is_anonymous: bool = Field(default=True, description="Обезличенные ставки")
    chat_id: int | str | None = Field(None, description="Чат для публикации (если None, личное событие)")
    creator_id: int = Field(..., description="ID создателя события")


class PlaceBetIn(BaseModel):
    """Размещение ставки."""
    event_id: int
    option_id: str
    amount: int = Field(..., ge=1, description="Сумма ставки")
    user_id: int
    source: str = Field(default="auto", description="Источник оплаты: auto (по валюте события), balance, payment")


class ResolveEventIn(BaseModel):
    """Разрешение события (определение победителя)."""
    event_id: int
    winning_option_ids: list[str] = Field(default_factory=list, description="ID победивших вариантов (может быть несколько, пустой = возврат всем)")
    resolution_source: str = Field(..., description="Источник решения (llm-mcp/ollama/openrouter/manual)")
    resolution_data: dict[str, Any] | None = Field(None, description="Данные от LLM/новости")


# === Calendar ===


class CreateCalendarIn(BaseModel):
    """Создание календаря."""
    slug: str = Field(..., max_length=100)
    title: str = Field(..., max_length=200)
    description: str | None = None
    owner_id: int | None = None
    chat_id: str | int | None = None
    bot_id: int | None = None
    timezone: str = "UTC"
    is_public: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateCalendarIn(BaseModel):
    """Обновление календаря."""
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    chat_id: str | int | None = None
    timezone: str | None = None
    is_public: bool | None = None
    config: dict[str, Any] | None = None


class CreateEntryIn(BaseModel):
    """Создание записи в календаре."""
    calendar_id: int
    parent_id: int | None = None
    title: str = Field(..., max_length=300)
    description: str | None = None
    emoji: str | None = None
    start_at: str
    end_at: str | None = None
    all_day: bool = False
    status: str = Field("active", pattern="^(active|done|cancelled|archived)$")
    priority: int = Field(3, ge=1, le=5)
    color: str | None = None
    tags: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    series_id: str | None = None
    repeat: str | None = Field(None, pattern="^(daily|weekly|biweekly|monthly|yearly|weekdays)$")
    repeat_until: str | None = None
    position: int = 0
    created_by: str | None = None
    ai_actionable: bool = True
    performed_by: str | None = None


class UpdateEntryIn(BaseModel):
    """Обновление записи календаря."""
    parent_id: int | None = None
    title: str | None = Field(None, max_length=300)
    description: str | None = None
    emoji: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    all_day: bool | None = None
    status: str | None = Field(None, pattern="^(active|done|cancelled|archived)$")
    priority: int | None = Field(None, ge=1, le=5)
    color: str | None = None
    tags: list[str] | None = None
    attachments: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    series_id: str | None = None
    repeat: str | None = None
    repeat_until: str | None = None
    position: int | None = None
    ai_actionable: bool | None = None
    performed_by: str | None = None


class MoveEntryIn(BaseModel):
    """Перемещение записи на новое время."""
    start_at: str
    end_at: str | None = None
    performed_by: str | None = None


class SetStatusIn(BaseModel):
    """Смена статуса записи."""
    status: str = Field(..., pattern="^(active|done|cancelled|archived)$")
    performed_by: str | None = None


class BulkEntryIn(BaseModel):
    """Одна запись в массовом создании (calendar_id задаётся на уровне запроса)."""
    parent_id: int | None = None
    title: str = Field(..., max_length=300)
    description: str | None = None
    emoji: str | None = None
    start_at: str
    end_at: str | None = None
    all_day: bool = False
    status: str = Field("active", pattern="^(active|done|cancelled|archived)$")
    priority: int = Field(3, ge=1, le=5)
    color: str | None = None
    tags: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    series_id: str | None = None
    repeat: str | None = Field(None, pattern="^(daily|weekly|biweekly|monthly|yearly|weekdays)$")
    repeat_until: str | None = None
    position: int = 0
    created_by: str | None = None
    ai_actionable: bool = True
    performed_by: str | None = None


class BulkCreateEntriesIn(BaseModel):
    """Массовое создание записей."""
    calendar_id: int
    entries: list[BulkEntryIn] = Field(..., min_length=1, max_length=100)


class BulkDeleteEntriesIn(BaseModel):
    """Массовое удаление записей."""
    ids: list[int] = Field(..., min_length=1, max_length=100)
    performed_by: str | None = None
