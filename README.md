# Telegram-MCP

[![Version](https://img.shields.io/badge/version-2026.02.12-blue.svg)](https://github.com/plagness/Telegram-MCP/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node.js](https://img.shields.io/badge/node.js-18+-green.svg)](https://nodejs.org/)
[![MCP Tools](https://img.shields.io/badge/MCP%20tools-57-orange.svg)](docs/mcp.md)

Автономный микросервис для стандартизации работы с Telegram Bot API через MCP (Model Context Protocol).

Централизует отправку сообщений, медиа, управление командами, приём вебхуков, **prediction markets**, **web-ui (Telegram Mini App)** и предоставляет **57 MCP-инструментов** для интеграции с LLM (Claude, ChatGPT и др.).

## ✨ Возможности

### 📨 Сообщения
- Отправка, редактирование, удаление с аудит-трейлом
- HTML/MarkdownV2 форматирование
- Reply-to-message, message threading (топики)
- Pin/Unpin сообщений с тихим закреплением
- Forward/Copy сообщений между чатами
- Live сообщения (автоудаление через 30с)

### 🖼️ Медиа
- **Фото**: URL, file_id, multipart upload
- **Видео**: URL, file_id с preview
- **Документы**: любые файлы с caption
- **Анимация/GIF**: send_animation
- **Аудио**: с метаданными (performer, title, duration)
- **Голосовые сообщения**: voice messages
- **Стикеры**: отправка по file_id
- **Медиа-группы (альбомы)**: 2-10 фото/видео одним сообщением

### 🎯 CommandHandler pattern (SDK)
- Декоратор `@api.command()` для регистрации обработчиков
- Guard-фильтры: `chat_id`, `user_id` для ограничения доступа
- Long polling с автоматической обработкой обновлений
- Парсинг аргументов команд
- Синхронизация с Telegram (setMyCommands)

### 📊 Форматирование и шаблоны
- **Прогресс-бары**: 6 стилей (classic, blocks, circles, squares, dots, minimal)
- **Emoji-градации**: health (💚→💛→🧡→❤️→💔), status, priority, connection
- **Hardware state blocks**: CPU, RAM, GPU, Disk, Network
- **Jinja2 шаблоны**: хранение в БД, рендеринг на сервере
- **Auto-pin для прогресс-баров**: автоматическое закрепление долгих процессов

### 👥 Chat Management
- **Ban/Unban**: блокировка участников с опциями revoke_messages, until_date
- **Restrict**: ограничение прав (can_send_messages, can_send_media, etc.)
- **Promote**: повышение до админа с настройкой прав
- Информация о чатах и участниках

### 🔔 Updates & Webhooks
- **Long polling**: getUpdates с offset tracking
- **Webhooks**: приём и хранение обновлений
- **Chat Actions**: typing индикаторы (typing, upload_photo, record_video, etc.)
- История обновлений с фильтрацией

### 🎨 Дополнительно
- **Опросы**: создание polls и quiz с правильными ответами
- **Реакции**: setMessageReaction (👍/🔥/❤️ и др.)
- **Callback queries**: обработка inline-кнопок
- **Reply markup**: inline/reply клавиатуры с расширенными кнопками
- **Rate limiting**: token-bucket по chat_id
- **Retry**: автоматический retry при 429/5xx
- **Python SDK**: готовый клиент для интеграции
- **MCP**: 46 инструментов для LLM

### 🚀 Bot API 9.x (2025-2026)
- **Чек-листы** (Bot API 9.1): интерактивные списки задач с галочками (до 30 элементов)
- **Звёзды** (Bot API 9.1): проверка баланса звёзд бота
- **Подарки** (Bot API 9.3): подарки премиум-подписок за звёзды, просмотр подарков
- **Истории** (Bot API 9.3): репост историй между каналами
- **Расширенные опросы**: до 12 вариантов ответа (Bot API 9.1)

### 🎯 Prediction Markets (Polymarket-style)
- **Предсказания Stars** с мультипликатором (непопулярный вариант = больший выигрыш)
- **Создание событий**: фиксированная дата или автоматическое разрешение через LLM
- **Два режима**: обезличенные (по умолчанию) или публичные (с именами)
- **LLM для принятия решений**: интеграция с llm-mcp, Ollama, OpenRouter
- **Stars Payments**: полная поддержка invoice, refund, transactions
- **Web-UI**: интерфейс предсказаний в Telegram Mini App (при `WEBUI_ENABLED=true`)
- **MCP tools**: 7 инструментов для автоматизации через LLM

### 🌐 Web-UI (Telegram Mini App)
- **Страницы**: создание HTML-страниц, открываемых как Mini App в Telegram
- **Опросники**: динамические формы с конфигурируемыми полями
- **Prediction Markets**: Polymarket-style интерфейс с коэффициентами и суммой
- **Индивидуальные ссылки**: уникальные токены для персонализации
- **Telegram initData**: автоматическая авторизация через HMAC-SHA256
- **TON Connect**: подключение кошелька для TON-платежей
- **Stars Payments**: оплата через `Telegram.WebApp.openInvoice()`
- **MCP tools**: 6 инструментов для управления через LLM

## Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────┐
│   Потребители    │────▶│  tgapi            │────▶│ Telegram Bot  │
│  (SDK / curl)   │     │  (FastAPI :8081)  │     │     API       │
└─────────────────┘     └──────┬───────────┘     └──────────────┘
                               │
┌─────────────────┐     ┌──────▼───────────┐
│   LLM / Claude  │────▶│  tgmcp            │
│                 │     │  (Node.js :3335)  │
└─────────────────┘     └──────────────────┘
                               │
┌─────────────────┐     ┌──────▼───────────┐
│  Telegram TWA   │────▶│  tgweb            │
│  (Mini App)     │     │  (FastAPI :8090)  │
└─────────────────┘     └──────────────────┘
                               │
                        ┌──────▼───────────┐
                        │   PostgreSQL      │
                        │   (:5436)         │
                        └──────────────────┘
```

| Компонент | Технология | Порт | Назначение |
|-----------|-----------|------|------------|
| **tgapi** | Python / FastAPI | 8081 | HTTP API, вебхуки, шаблоны |
| **tgmcp** | Node.js / TypeScript | 3335 | MCP-тулзы + HTTP-мост |
| **tgweb** | Python / FastAPI | 8090 | Web-UI (Telegram Mini App) |
| **tgdb** | PostgreSQL 16 | 5436 | Сообщения, шаблоны, обновления, команды |

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
curl http://127.0.0.1:8090/health
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
│   │   ├── utils.py        # Общие хелперы (escape_html, resolve_bot_context)
│   │   ├── telegram_client.py  # httpx-клиент к Telegram Bot API
│   │   ├── rate_limiter.py     # Token-bucket rate limiter
│   │   ├── templates.py    # Jinja2-рендеринг
│   │   ├── models.py       # Pydantic-модели
│   │   ├── routers/        # Эндпоинты
│   │   │   ├── messages.py     # Сообщения
│   │   │   ├── media.py        # Фото, документы, видео
│   │   │   ├── polls.py        # Опросы и викторины
│   │   │   ├── reactions.py    # Реакции
│   │   │   ├── predictions.py  # Рынки предсказаний
│   │   │   ├── templates.py    # Шаблоны
│   │   │   ├── commands.py     # Команды бота
│   │   │   ├── callbacks.py    # Callback queries
│   │   │   ├── chats.py        # Чаты и участники
│   │   │   ├── webhook.py      # Вебхуки
│   │   │   ├── webui.py        # Proxy → tgweb
│   │   │   └── health.py       # Healthcheck, метрики
│   │   └── services/       # Бизнес-логика
│   │       ├── predictions.py  # Сервис предсказаний
│   │       ├── keyboards.py    # Билдеры inline-клавиатур
│   │       └── ...
│   └── Dockerfile
├── mcp/                    # MCP-сервер (Node.js)
│   ├── src/
│   │   ├── index.ts        # Регистрация модулей
│   │   ├── types.ts        # Общие типы (ToolDef, ApiRequestFn)
│   │   └── tools/          # Модули по доменам
│   │       ├── messages.ts, media.ts, chats.ts, ...
│   │       ├── predictions.ts, balance.ts, stars.ts
│   │       └── webui.ts    # Web-UI инструменты
│   └── Dockerfile
├── web-ui/                 # Web-UI (Telegram Mini App)
│   ├── app/
│   │   ├── main.py         # FastAPI + Jinja2 + static
│   │   ├── config.py       # Settings
│   │   ├── db.py           # PostgreSQL pool
│   │   ├── auth.py         # Telegram initData HMAC-SHA256
│   │   ├── routers/        # health, pages, render
│   │   ├── services/       # pages, links
│   │   ├── templates/      # base, prediction, survey, page
│   │   └── static/         # style.css, twa.js, tonconnect-manifest.json
│   └── Dockerfile
├── sdk/                    # Python SDK
│   └── telegram_api_client/
│       ├── client.py       # TelegramAPI + ProgressContext
│       └── exceptions.py   # TelegramAPIError
├── db/init/                # SQL-миграции
│   ├── 01_schema.sql       # Основная схема
│   ├── 02_extensions.sql   # Медиа, callbacks, webhook config
│   └── 10_web_ui.sql       # Web-UI таблицы
├── templates/              # Jinja2-шаблоны (auto-seed)
├── scripts/                # Тестовые скрипты
├── docs/                   # Документация
└── compose.yml             # Docker Compose (tgdb, tgapi, tgmcp, tgweb)
```

## Документация

- [docs/api.md](docs/api.md) — справочник HTTP API
- [docs/sdk.md](docs/sdk.md) — Python SDK
- [docs/commands.md](docs/commands.md) — управление командами бота
- [docs/webhooks.md](docs/webhooks.md) — вебхуки и обновления
- [docs/mcp.md](docs/mcp.md) — MCP-инструменты
- [docs/web-ui.md](docs/web-ui.md) — Web-UI (Telegram Mini App)
- [docs/formatting.md](docs/formatting.md) — форматирование сообщений Telegram
- [docs/schema.md](docs/schema.md) — схема базы данных

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Токен бота из @BotFather | — (обязательно) |
| `DB_USER` | Пользователь БД | `telegram` |
| `DB_PASSWORD` | Пароль БД | `telegram` |
| `DB_NAME` | Имя БД | `telegram` |
| `PORT_DB_TG` | Внешний порт PostgreSQL | `5436` |
| `PORT_HTTP_TGAPI` | Внешний порт API | `8081` |
| `PORT_MCP_TG` | Внешний порт MCP | `3335` |
| `TELEGRAM_API_URL` | Явный URL API для MCP bridge | `http://tgapi:8000` |
| `TELEGRAM_API_BASE` | Legacy alias для URL API | `http://tgapi:8000` |
| `API_PORT` | Legacy fallback для порта API | `8081` |
| `MCP_HTTP_PORT` | Legacy fallback для порта MCP | `3335` |
| `MCP_HTTP_TOKEN` | Bearer-токен для MCP HTTP | — (опционально) |
| `TEMPLATE_AUTOSEED` | Автозагрузка шаблонов из `templates/` | `true` |
| `WEBUI_ENABLED` | Включить web-ui (web_app кнопки) | `false` |
| `WEBUI_PUBLIC_URL` | Публичный URL для Mini App | — |
| `PORT_WEBUI` | Внешний порт web-ui | `8090` |

Если `TELEGRAM_API_URL`/`TELEGRAM_API_BASE` не заданы, MCP сначала использует `http://tgapi:8000`.
Для обратной совместимости на 1 релиз при ошибке сети выполняется retry на legacy `http://telegram-api:8000`.

## Лицензия

MIT
