# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат версий: `[год].[месяц].[версия]`

---

## [2025.03.1] - 2025-02-06

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
