# Web-UI (Telegram Mini App)

Модуль `tgweb` предоставляет веб-интерфейс для создания интерактивных страниц, открываемых внутри Telegram как Mini App (TWA).

## Возможности

- **Веб-страницы**: создание HTML-страниц с кнопками и контентом
- **Опросники**: динамические формы с полями из конфигурации
- **Prediction Markets**: интерфейс для предсказаний (Polymarket-style) с коэффициентами и суммой
- **Индивидуальные ссылки**: уникальные токены для персонализации доступа
- **Telegram initData**: автоматическая авторизация через HMAC-SHA256
- **TON Connect**: подключение кошелька для TON-платежей
- **Stars Payments**: оплата через `Telegram.WebApp.openInvoice()`

## Архитектура

```
┌────────────────────┐     ┌──────────────────┐
│  Telegram Mini App │────▶│  tgweb           │
│  (в чате бота)     │     │  (FastAPI :8090) │
└────────────────────┘     └──────┬───────────┘
                                  │ direct DB
┌────────────────────┐     ┌──────▼───────────┐
│  tgapi (proxy)     │────▶│  PostgreSQL      │
│  /v1/web/*         │     │  (:5436)         │
└────────────────────┘     └──────────────────┘
```

| Компонент | Порт | Назначение |
|-----------|------|------------|
| **tgweb** | 8090 | Рендеринг страниц, приём форм, авторизация |
| **tgapi** | 8081 | Proxy `/v1/web/*` → `tgweb/api/v1/*` |
| **tgmcp** | 3335 | MCP инструменты `webui.*` |

## Быстрый старт

### 1. Настройка .env

```bash
WEBUI_ENABLED=true
WEBUI_PUBLIC_URL=https://tg.plag.space:8090
PORT_WEBUI=8090
```

### 2. Авторизация домена в BotFather

Для работы Mini App домен должен быть авторизован:
1. Откройте @BotFather → `/mybots` → выберите бота
2. **Bot Settings** → **Menu Button** или **Domain**
3. Добавьте домен `tg.plag.space`

### 3. Запуск

```bash
docker compose up -d tgdb tgapi tgweb tgmcp
curl http://localhost:8090/health
```

## API endpoints

### Управление (через tgapi proxy)

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/v1/web/pages` | Создать страницу |
| `GET` | `/v1/web/pages` | Список страниц |
| `GET` | `/v1/web/pages/{slug}` | Конфигурация страницы |
| `DELETE` | `/v1/web/pages/{slug}` | Удалить страницу |
| `POST` | `/v1/web/pages/{slug}/links` | Создать индивидуальную ссылку |
| `GET` | `/v1/web/pages/{slug}/submissions` | Ответы формы |

### Публичные (tgweb напрямую)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/p/{slug}` | Рендеринг HTML-страницы |
| `GET` | `/l/{token}` | Редирект по индивидуальной ссылке |
| `POST` | `/p/{slug}/submit` | Отправка формы (с initData) |
| `GET` | `/health` | Healthcheck |

## Типы страниц

### page — Обычная страница

```bash
curl -X POST http://localhost:8081/v1/web/pages \
  -H 'content-type: application/json' \
  -d '{
    "title": "Добро пожаловать",
    "page_type": "page",
    "config": {
      "content_html": "<h2>Привет!</h2><p>Это демо-страница.</p>",
      "buttons": [
        {"text": "Перейти", "url": "https://example.com"}
      ]
    }
  }'
```

### survey — Опросник

```bash
curl -X POST http://localhost:8081/v1/web/pages \
  -H 'content-type: application/json' \
  -d '{
    "title": "Обратная связь",
    "page_type": "survey",
    "config": {
      "fields": [
        {"name": "rating", "type": "select", "label": "Оценка", "options": ["1", "2", "3", "4", "5"]},
        {"name": "comment", "type": "textarea", "label": "Комментарий"}
      ]
    }
  }'
```

### prediction — Рынок предсказаний

```bash
curl -X POST http://localhost:8081/v1/web/pages \
  -H 'content-type: application/json' \
  -d '{
    "title": "Кто выиграет?",
    "page_type": "prediction",
    "event_id": 42,
    "config": {}
  }'
```

При `WEBUI_ENABLED=true` предсказания автоматически создают страницу с slug `predict-{event_id}`.

## Индивидуальные ссылки

Персональные ссылки позволяют привязать доступ к конкретному пользователю:

```bash
curl -X POST http://localhost:8081/v1/web/pages/my-survey/links \
  -H 'content-type: application/json' \
  -d '{"user_id": 777, "metadata": {"source": "private_message"}}'

# Ответ:
# {
#   "token": "a1b2c3d4...",
#   "url": "https://tg.plag.space:8090/l/a1b2c3d4..."
# }
```

Ссылка `GET /l/{token}` редиректит на `GET /p/{slug}?token={token}`.

## Авторизация

### Telegram initData (автоматическая)

При открытии страницы как Mini App, Telegram передаёт `initData` — подписанные данные пользователя.

Алгоритм валидации (RFC от Telegram):
1. Парсинг `init_data` как query string
2. Извлечение `hash`, формирование `data_check_string` (sorted `key=value`, разделённые `\n`)
3. `secret_key = HMAC-SHA256("WebAppData", bot_token)`
4. Сравнение `HMAC-SHA256(data_check_string, secret_key)` с `hash`
5. Проверка `auth_date` не старше `max_age` (по умолчанию 24 часа)

### TON Connect (кошелёк)

Для TON-предсказаний пользователь подключает кошелёк через TON Connect:

1. Страница загружает `@tonconnect/ui`
2. Показывается кнопка «Connect Wallet»
3. После подключения адрес кошелька сохраняется в `web_wallet_links`

### Stars Payments

Оплата через Telegram Stars:

1. Бэкенд создаёт invoice через `tgapi /v1/stars/invoice`
2. Фронтенд вызывает `Telegram.WebApp.openInvoice(url, callback)`
3. При `status === 'paid'` — отправка формы с подтверждением

## MCP инструменты

| Инструмент | Описание |
|------------|----------|
| `webui.create_page` | Создать страницу (page/survey/prediction) |
| `webui.list_pages` | Список страниц |
| `webui.create_link` | Создать индивидуальную ссылку |
| `webui.get_submissions` | Получить ответы формы |
| `webui.create_prediction` | Создать страницу предсказания (shortcut) |
| `webui.create_survey` | Создать опросник (shortcut) |

## SDK методы

```python
from telegram_api_client import TelegramAPI

async with TelegramAPI("http://localhost:8081") as api:
    # Создать страницу
    page = await api.create_web_page(
        title="Мой опрос",
        page_type="survey",
        config={"fields": [{"name": "q1", "type": "text", "label": "Вопрос"}]}
    )

    # Список страниц
    pages = await api.list_web_pages()

    # Индивидуальная ссылка
    link = await api.create_web_link("my-survey", user_id=777)
    print(link["url"])

    # Ответы
    submissions = await api.get_web_submissions("my-survey")

    # Shortcut: предсказание
    pred_page = await api.create_prediction_page(event_id=42)

    # Shortcut: опросник
    survey = await api.create_survey_page(
        title="Фидбэк",
        fields=[
            {"name": "rating", "type": "select", "label": "Оценка", "options": ["1-5"]},
            {"name": "text", "type": "textarea", "label": "Текст"}
        ]
    )
```

## База данных

Миграция: `db/init/10_web_ui.sql`

| Таблица | Назначение |
|---------|------------|
| `web_pages` | Страницы (slug, type, config, template) |
| `web_page_links` | Индивидуальные ссылки (token → page + user) |
| `web_form_submissions` | Ответы на формы (data JSONB) |
| `web_wallet_links` | Привязка TON-кошельков к Telegram-аккаунтам |

## Структура файлов

```
web-ui/
├── app/
│   ├── main.py          # FastAPI + Jinja2 + static + lifespan
│   ├── config.py        # Settings: PUBLIC_URL, TGAPI_URL, BOT_TOKEN
│   ├── db.py            # PostgreSQL pool (psycopg)
│   ├── auth.py          # Telegram initData HMAC-SHA256 валидация
│   ├── routers/
│   │   ├── health.py    # GET /health
│   │   ├── pages.py     # CRUD API для страниц
│   │   └── render.py    # GET /p/{slug}, GET /l/{token}, POST submit
│   ├── services/
│   │   ├── pages.py     # CRUD web_pages в БД
│   │   └── links.py     # Генерация токенов, создание ссылок
│   ├── templates/
│   │   ├── base.html    # Base с telegram-web-app.js SDK
│   │   ├── prediction.html  # Polymarket UI
│   │   ├── survey.html      # Динамические формы
│   │   └── page.html        # Универсальная страница
│   └── static/
│       ├── style.css    # Telegram theme (--tg-theme-* CSS vars)
│       ├── twa.js       # TWA bootstrap + TON Connect + Stars
│       └── tonconnect-manifest.json
├── Dockerfile
└── requirements.txt
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `WEBUI_ENABLED` | Включить web-ui (web_app кнопки вместо callback) | `false` |
| `WEBUI_PUBLIC_URL` | Публичный URL web-ui для Mini App кнопок | — |
| `PORT_WEBUI` | Внешний порт web-ui | `8090` |
| `BOT_TOKEN` | Токен бота (для валидации initData) | — |
| `DB_DSN` | PostgreSQL connection string | — |
| `TGAPI_URL` | URL tgapi для обратных вызовов | `http://tgapi:8000` |
