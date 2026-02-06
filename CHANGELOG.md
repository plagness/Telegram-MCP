# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат версий: `[год].[месяц].[версия]`

---

## [2026.02.6] - 2026-02-06

### Добавлено

#### Bot API 9.x — Чеклисты, Звёзды, Подарки, Истории

**Checklists (Bot API 9.1)**
- Интерактивные чек-листы с задачами (до 30 элементов с галочками)
- Endpoints: `POST /v1/checklists/send`, `PUT /v1/messages/{id}/checklist`
- Модели: `ChecklistTask`, `SendChecklistIn`, `EditChecklistIn`
- SDK-методы: `api.send_checklist()`, `api.edit_checklist()`
- MCP-инструменты: `checklists.send`, `checklists.edit`
- Функции: `send_checklist()`, `edit_message_checklist()` в `telegram_client.py`

**Stars & Gifts (Bot API 9.1+)**
- Баланс звёзд бота: `GET /v1/stars/balance` → `api.get_star_balance()`
- Подарки премиум-подписок: `POST /v1/gifts/premium` → `api.gift_premium()`
- Список подарков: `GET /v1/gifts/user/{user_id}`, `/gifts/chat/{chat_id}`
- SDK-методы: `api.get_user_gifts()`, `api.get_chat_gifts()`
- MCP-инструменты: `stars.balance`, `gifts.premium`, `gifts.user`, `gifts.chat`
- Модели: `GiftPremiumIn`
- Функции: `get_my_star_balance()`, `gift_premium_subscription()`, `get_user_gifts()`, `get_chat_gifts()`

**Stories (Bot API 9.3)**
- Репост историй между каналами: `POST /v1/stories/repost`
- Модель: `RepostStoryIn`
- SDK-метод: `api.repost_story(chat_id, from_chat_id, story_id)`
- MCP-инструмент: `stories.repost`
- Функция: `repost_story()` в `telegram_client.py`

#### Инфраструктура
- Новый роутер: `api/app/routers/checklists.py` (чеклисты, stars, gifts, stories)
- Зарегистрирован в `main.py`
- Расширен MCP с +7 инструментов (теперь 31 всего)

---

## [2026.02.5] - 2026-02-06

### Добавлено

#### Расширенные медиа (Animation, Audio, Voice, Sticker)
- Endpoints: `POST /v1/media/send-animation`, `/send-audio`, `/send-voice`, `/send-sticker`
- Модели: `SendAnimationIn`, `SendAudioIn`, `SendVoiceIn`, `SendStickerIn`
- Функция `send_audio()` в `telegram_client.py` (другие уже были)
- Поддержка URL и file_id для всех типов медиа
- Метаданные для аудио: performer, title, duration

#### Chat Management (управление участниками)
- **Бан/разбан**: `POST /v1/chats/{chat_id}/members/{user_id}/ban` и `/unban`
  - Параметры: until_date, revoke_messages, only_if_banned
- **Ограничение прав**: `POST /v1/chats/{chat_id}/members/{user_id}/restrict`
  - Настройка permissions: can_send_messages, can_send_media_messages и др.
- **Повышение до админа**: `POST /v1/chats/{chat_id}/members/{user_id}/promote`
  - Настройка прав: can_delete_messages, can_restrict_members, can_pin_messages и др.
- Функции в `telegram_client.py`: `ban_chat_member`, `unban_chat_member`, `restrict_chat_member`, `promote_chat_member`
- Роутер `chats.py` расширен Chat Management endpoints

---

## [2026.02.4] - 2026-02-06

### Добавлено

#### sendMediaGroup (альбомы фото/видео)
- Метод `api.send_media_group()` в SDK для отправки альбомов (2-10 элементов)
- API endpoint: `POST /v1/media/send-media-group`
- Модели: `InputMedia`, `SendMediaGroupIn` в `api/app/models.py`
- Функция `send_media_group()` в `telegram_client.py`
- Поддержка фото, видео, документов в одном альбоме
- Caption только для первого элемента (ограничение Telegram)
- Dry-run режим для тестирования без отправки
- Тестовый скрипт: `scripts/test_media_group.py`

---

## [2026.02.3] - 2026-02-06

### Добавлено

#### Pin/Unpin сообщений с автопином
- Методы `api.pin_message()` и `api.unpin_message()` в SDK
- API endpoints: `POST /v1/messages/{id}/pin`, `DELETE /v1/messages/{id}/pin`
- Тихое закрепление по умолчанию (`disable_notification=True`)
- **Автопин для прогресс-баров**: параметр `auto_pin=True` в `api.progress()`
  - Автоматическое закрепление при старте процесса (без уведомления)
  - Автоматическое открепление по завершению
  - Удобно для мониторинга 3-4 параллельных долгих процессов
- Модели: `PinMessageIn`, `UnpinMessageIn` в `api/app/models.py`
- Функции: `pin_chat_message()`, `unpin_chat_message()` в `telegram_client.py`
- Обновлён `ProgressContext` с поддержкой автопина
- Тестовый скрипт: `scripts/test_pin.py`

---

## [2026.02.2] - 2026-02-06

### Добавлено

#### CommandHandler Pattern в SDK
- Декоратор `@api.command("name")` для регистрации обработчиков команд
- Guard-фильтры: `chat_id`, `user_id` для ограничения доступа к командам
- Long polling механизм через `api.start_polling()` и `api.stop_polling()`
- Класс `CommandRegistry` для управления зарегистрированными командами
- Класс `PollingManager` для автоматической обработки обновлений
- Парсинг аргументов команд: `/test arg1 arg2` → `handler(update, ["arg1", "arg2"])`
- Метод `api.list_commands()` для просмотра зарегистрированных команд
- Модули: `sdk/telegram_api_client/commands.py`, обновления в `client.py`
- Тестовый скрипт: `scripts/test_command_handler.py`

#### Синхронизация команд с Telegram
- Поддержка `setMyCommands` через `api.sync_commands(command_set_id)`
- Автоматические подсказки при вводе "/" в чатах
- Тестовый скрипт: `scripts/test_commands.py --sync`

### Исправлено
- SQL синтаксис: зарезервированное слово `offset` теперь в кавычках во всех запросах
- API endpoint `/v1/updates/ack` теперь принимает JSON body с Pydantic моделью
- Экспорты `CommandRegistry` и `PollingManager` в `sdk/telegram_api_client/__init__.py`
- Применена миграция `04_updates_and_threads.sql` (таблица `update_offset`)

---

## [2026.02.1] - 2026-02-06

### Добавлено

#### Система форматирования
- Универсальная система прогресс-баров (6 стилей: classic, blocks, circles, squares, dots, minimal)
- Система градаций эмодзи (health, status, priority, zone, sentiment, connection)
- Блоки состояния железа: CPU, RAM, GPU, Disk, Network
- Готовые Jinja2 шаблоны: `hardware_status.j2`, `hardware_fleet.j2`, `macros.j2`
- Утилиты форматирования: duration, timestamp, bytes, trim, escape_html
- Модуль: `api/app/formatters.py`

#### Updates/Polling (Bot API getUpdates)
- Long polling механизм `GET /v1/updates/poll`
- Подтверждение обработки `POST /v1/updates/ack`
- Получение текущего offset `GET /v1/updates/offset`
- Обработка входящих обновлений `POST /v1/updates/process`
- История обновлений `GET /v1/updates/history`
- Таблицы БД: `update_offset`, расширение `updates` (processed, processed_at)

#### Chat Actions (индикаторы активности)
- Отправка chat action `POST /v1/chats/{chat_id}/action`
- Поддержка всех типов: typing, upload_photo, record_video, upload_voice, upload_document, choose_sticker, find_location, record_video_note, upload_video_note
- Таблица БД: `chat_actions` с автоматическим истечением через 5 секунд
- Аудит всех отправленных actions

#### Message Threading (топики/форумы)
- Добавлен параметр `message_thread_id` во все send/edit методы
- Индексы для быстрого поиска по топикам
- Поддержка приватных чатов с форумами (Bot API 9.3)

#### Priority Queue (приоритизация запросов)
- Таблица `request_queue` с приоритетами 1-5
- Функция `get_next_request()` для обработки в порядке приоритета
- Поддержка метаданных: source (llm-mcp, channel-mcp, jobs), метод, payload
- Статусы: pending, processing, completed, failed

#### Per-User Commands (расширенные команды)
- Таблица `user_command_visibility` для видимости команд по юзерам
- Поддержка scope `chat_member` с user_id
- Индивидуальные наборы команд для каждого пользователя

#### Расширенные медиа (подготовка)
- Таблица `media_groups` для альбомов (sendMediaGroup)
- Поля для новых типов медиа: animation, audio, voice, video_note, sticker
- Структура для inline queries: `inline_queries` таблица

#### Checklists (Bot API 9.2)
- Таблица `checklists` для чек-листов
- Поддержка title, tasks (JSONB), completed статус
- Связь с messages через foreign key

### Изменено
- Миграция БД: новый файл `03_updates_and_threads.sql`
- main.py: подключены новые роутеры `updates`, `actions`
- VERSION: 2025.02.1 → 2025.03.1

### Документация
- `MIGRATION_ANALYSIS.md` — полный анализ паттернов использования Telegram API и план миграции на telegram-mcp
- Документация системы форматирования в docstrings `formatters.py`
- Комментарии к новым таблицам БД

---

## [2025.02.1] - 2025-02-06

### Добавлено

#### Опросы (Polls)
- Создание опросов и викторин через `POST /v1/polls/send`
- Остановка опросов с показом результатов `POST /v1/polls/{chat_id}/{message_id}/stop`
- Список опросов с фильтрацией `GET /v1/polls`
- Получение ответов пользователей `GET /v1/polls/{poll_id}/answers`
- Поддержка quiz-режима с правильным ответом и пояснением
- Таблицы БД: `polls`, `poll_answers`
- SDK методы: `send_poll()`, `stop_poll()`, `list_polls()`
- MCP инструменты: `polls.send`, `polls.stop`, `polls.list`
- Тестовый скрипт: `scripts/test_polls.py`

#### Реакции (Reactions)
- Установка эмодзи-реакций на сообщения `POST /v1/reactions/set`
- Поддержка обычных эмодзи, кастомных эмодзи (Premium) и платных реакций (Stars)
- Список реакций с фильтрацией `GET /v1/reactions`
- Таблица БД: `message_reactions`
- SDK методы: `set_reaction()`, `list_reactions()`
- MCP инструмент: `reactions.set`
- Тестовый скрипт: `scripts/test_reactions.py`

#### Расширенные inline-кнопки
- `web_app` — запуск Telegram Mini Apps
- `login_url` — OAuth авторизация через бота
- `switch_inline_query` / `switch_inline_query_current_chat` / `switch_inline_query_chosen_chat` — inline-режим
- `callback_game` — запуск игр
- `pay` — кнопки оплаты
- `copy_text` — копирование текста в буфер

#### Инфраструктура
- Fallback конфигурации `.env`: автоматическое чтение `BOT_TOKEN` из корневого проекта
- Поддержка как автономного, так и встроенного использования

### Документация
- `docs/POLLS_AND_REACTIONS.md` — полное руководство по опросам и реакциям
- Обновлены `docs/api.md`, `docs/sdk.md`, `docs/mcp.md`
- Обновлен `README.md` с новыми возможностями
- MCP инструментов: 21 → **25**

---

## [2025.01.1] - 2025-01-XX (Initial Release)

### Добавлено
- HTTP API (FastAPI) на порту 8081
- MCP-сервер (Node.js) на порту 3335
- PostgreSQL 16 для хранения сообщений, шаблонов, команд
- Отправка, редактирование, удаление текстовых сообщений
- Отправка медиа: фото, документы, видео (URL, file_id, upload)
- Jinja2-шаблоны с переменными
- Управление командами бота по скоупам (глобальные, per-chat, per-user)
- Приём вебхуков от Telegram
- Обработка callback queries
- Информация о чатах и участниках
- Rate limiting (token-bucket по chat_id)
- Автоматический retry при 429 и 5xx
- Python SDK с async/await
- 21 MCP-инструмент для интеграции с LLM
- Docker Compose с healthchecks
- Тестовые скрипты: `test_send.py`, `test_media.py`, `test_commands.py`, `test_progress.py`
- Документация: API, SDK, MCP, схема БД, форматирование, команды, вебхуки
