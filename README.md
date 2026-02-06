# Telegram-MCP

Автономный микросервис для стандартизации работы с Telegram Bot API через MCP (Model Context Protocol).

Централизует отправку сообщений, медиа, управление командами, приём вебхуков и предоставляет 25 MCP-инструментов для интеграции с LLM (Claude, ChatGPT и др.).

## Возможности

- **Сообщения** — отправка, редактирование, удаление текстовых сообщений с аудит-трейлом
- **Медиа** — отправка фото (URL, file_id, загрузка файла), документов, видео
- **Опросы** — создание опросов и викторин (quiz) с правильными ответами и пояснениями
- **Реакции** — установка эмодзи-реакций на сообщения (👍/🔥/❤️ и др.)
- **Шаблоны** — Jinja2-шаблоны с переменными, хранение в PostgreSQL
- **Команды** — управление командами бота по скоупам (глобальные, для чата, для конкретного пользователя)
- **Вебхуки** — приём и хранение обновлений от Telegram
- **Callback queries** — обработка нажатий inline-кнопок
- **Чаты** — информация о чатах и участниках
- **Reply markup** — расширенные inline-кнопки (web_app, switch_inline_query, copy_text, login_url)
- **Rate limiting** — token-bucket ограничение по chat_id
- **Retry** — автоматический retry при 429 (Retry-After) и 5xx
- **MCP** — 25 инструментов для интеграции с LLM
- **Python SDK** — готовый клиент для подключения из других сервисов

## Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│   Потребители    │────▶│  telegram-api     │────▶│ Telegram Bot  │
│  (SDK / curl)   │     │  (FastAPI :8081)  │     │     API       │
└─────────────────┘     └──────┬───────────┘     └──────────────┘
                               │
┌─────────────────┐     ┌──────▼───────────┐
│   LLM / Claude  │────▶│  telegram-mcp     │
│                 │     │  (Node.js :3335)  │
└─────────────────┘     └──────────────────┘
                               │
                        ┌──────▼───────────┐
                        │   PostgreSQL      │
                        │   (:5436)         │
                        └──────────────────┘
```

| Компонент | Технология | Порт | Назначение |
|-----------|-----------|------|------------|
| **telegram-api** | Python / FastAPI | 8081 | HTTP API, вебхуки, шаблоны |
| **telegram-mcp** | Node.js / TypeScript | 3335 | MCP-тулзы + HTTP-мост |
| **telegram-db** | PostgreSQL 16 | 5436 | Сообщения, шаблоны, обновления, команды |

## Быстрый старт

```bash
# 1. Создать .env с токеном бота
cp .env.example .env
# Установить TELEGRAM_BOT_TOKEN в .env

# 2. Запустить
docker compose -f compose.yml up -d

# 3. Проверить
curl http://127.0.0.1:8081/health
curl http://127.0.0.1:3335/health
```

## Примеры использования

### curl

```bash
# Отправка сообщения
curl -X POST http://127.0.0.1:8081/v1/messages/send \
  -H 'content-type: application/json' \
  -d '{"chat_id": -100123456, "text": "<b>Привет!</b>", "parse_mode": "HTML"}'

# Отправка фото по URL
curl -X POST http://127.0.0.1:8081/v1/media/send-photo \
  -H 'content-type: application/json' \
  -d '{"chat_id": -100123456, "photo": "https://example.com/img.jpg", "caption": "Описание"}'

# Загрузка фото файлом
curl -X POST http://127.0.0.1:8081/v1/media/upload-photo \
  -F "chat_id=-100123456" \
  -F "caption=Загруженное фото" \
  -F "file=@/path/to/photo.jpg"

# Сообщение с inline-кнопками
curl -X POST http://127.0.0.1:8081/v1/messages/send \
  -H 'content-type: application/json' \
  -d '{
    "chat_id": -100123456,
    "text": "Выберите действие:",
    "reply_markup": {
      "inline_keyboard": [[
        {"text": "Да", "callback_data": "yes"},
        {"text": "Нет", "callback_data": "no"}
      ]]
    }
  }'
```

### Python SDK

```python
from telegram_api_client import TelegramAPI

async with TelegramAPI("http://localhost:8081") as api:
    # Отправка сообщения
    msg = await api.send_message(
        chat_id=-100123456,
        text="<b>Привет!</b>",
        parse_mode="HTML",
    )

    # Редактирование
    await api.edit_message(msg["id"], text="Обновлённый текст")

    # Отправка фото (файл)
    with open("chart.png", "rb") as f:
        await api.send_photo(chat_id=-100123456, photo=f, caption="График")

    # Прогресс-сообщение (send → edit → delete)
    async with api.progress(chat_id=-100123456) as p:
        await p.update(1, 3, "Загрузка данных...")
        await p.update(2, 3, "Обработка...")
        await p.update(3, 3, "Сохранение...")
    # Сообщение автоматически удаляется
```

### MCP (для LLM)

```bash
# Список инструментов
curl http://127.0.0.1:3335/tools

# Вызов инструмента
curl -X POST http://127.0.0.1:3335/tools/messages.send \
  -H 'content-type: application/json' \
  -d '{"chat_id": -100123456, "text": "Привет от LLM"}'
```

## Структура проекта

```
Telegram-MCP/
├── api/                    # FastAPI-сервис
│   ├── app/
│   │   ├── main.py         # Точка входа, lifespan, роутеры
│   │   ├── config.py       # Настройки (pydantic-settings)
│   │   ├── db.py           # PostgreSQL connection pool
│   │   ├── telegram_client.py  # httpx-клиент к Telegram Bot API
│   │   ├── rate_limiter.py     # Token-bucket rate limiter
│   │   ├── templates.py    # Jinja2-рендеринг
│   │   ├── models.py       # Pydantic-модели
│   │   ├── routers/        # Эндпоинты
│   │   │   ├── messages.py     # Сообщения
│   │   │   ├── media.py        # Фото, документы, видео
│   │   │   ├── polls.py        # Опросы и викторины
│   │   │   ├── reactions.py    # Реакции
│   │   │   ├── templates.py    # Шаблоны
│   │   │   ├── commands.py     # Команды бота
│   │   │   ├── callbacks.py    # Callback queries
│   │   │   ├── chats.py        # Чаты и участники
│   │   │   ├── webhook.py      # Вебхуки
│   │   │   └── health.py       # Healthcheck, метрики
│   │   └── services/       # Бизнес-логика
│   └── Dockerfile
├── mcp/                    # MCP-сервер (Node.js)
│   ├── src/index.ts        # 25 MCP-инструментов
│   └── Dockerfile
├── sdk/                    # Python SDK
│   └── telegram_api_client/
│       ├── client.py       # TelegramAPI + ProgressContext
│       └── exceptions.py   # TelegramAPIError
├── db/init/                # SQL-миграции
│   ├── 01_schema.sql       # Основная схема
│   └── 02_extensions.sql   # Медиа, callbacks, webhook config
├── templates/              # Jinja2-шаблоны (auto-seed)
├── scripts/                # Тестовые скрипты
├── docs/                   # Документация
└── compose.yml             # Docker Compose
```

## Документация

- [docs/api.md](docs/api.md) — справочник HTTP API
- [docs/sdk.md](docs/sdk.md) — Python SDK
- [docs/commands.md](docs/commands.md) — управление командами бота
- [docs/webhooks.md](docs/webhooks.md) — вебхуки и обновления
- [docs/mcp.md](docs/mcp.md) — MCP-инструменты
- [docs/formatting.md](docs/formatting.md) — форматирование сообщений Telegram
- [docs/schema.md](docs/schema.md) — схема базы данных

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота из @BotFather | — (обязательно) |
| `DB_USER` | Пользователь БД | `telegram` |
| `DB_PASSWORD` | Пароль БД | `telegram` |
| `DB_NAME` | Имя БД | `telegram` |
| `DB_PORT` | Внешний порт PostgreSQL | `5436` |
| `API_PORT` | Внешний порт API | `8081` |
| `MCP_HTTP_PORT` | Внешний порт MCP | `3335` |
| `MCP_HTTP_TOKEN` | Bearer-токен для MCP HTTP | — (опционально) |
| `TEMPLATE_AUTOSEED` | Автозагрузка шаблонов из `templates/` | `true` |

## Лицензия

MIT
