# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат версий: `[год].[месяц].[версия]`

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
