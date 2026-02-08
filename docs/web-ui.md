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
- **Direct Link Mini App**: кнопки в групповых чатах открывают Mini App внутри Telegram

## Архитектура

```
┌─────────────────────┐     ┌──────────────────────┐
│  Telegram Mini App  │────▶│  VPS (TCP proxy)     │
│  (t.me/Bot/app)     │     │  socat :8443         │
└─────────────────────┘     └──────┬───────────────┘
                                   │ Tailscale
┌─────────────────────┐     ┌──────▼───────────────┐
│  tgapi (proxy)      │────▶│  tgweb (FastAPI)     │
│  /v1/web/*          │     │  uvicorn + TLS :8443 │
└─────────────────────┘     └──────┬───────────────┘
                                   │ direct DB
┌─────────────────────┐     ┌──────▼───────────────┐
│  tgmcp              │     │  PostgreSQL          │
│  MCP webui.*        │     │  (:5436)             │
└─────────────────────┘     └──────────────────────┘
```

| Компонент | Порт | Назначение |
|-----------|------|------------|
| **tgweb** | 8443 | Рендеринг страниц, приём форм, авторизация (TLS) |
| **tgapi** | 8081 | Proxy `/v1/web/*` -> `tgweb/api/v1/*` |
| **tgmcp** | 3335 | MCP инструменты `webui.*` |

## Развёртывание

### 1. SSL-сертификат (Let's Encrypt)

Web-UI требует HTTPS. Получение сертификата через DNS-01 challenge:

```bash
# Установка certbot
pip install certbot

# Получение сертификата (DNS-01 — ручная валидация)
certbot certonly \
  --manual \
  --preferred-challenges dns \
  --config-dir ~/.certbot/config \
  --work-dir ~/.certbot/work \
  --logs-dir ~/.certbot/logs \
  -d tg.example.com \
  -d telegram.example.com

# certbot покажет TXT-запись для добавления в DNS:
#   _acme-challenge.tg.example.com -> <значение>
# Добавьте запись у вашего DNS-провайдера, подтвердите.

# Сертификаты сохраняются в ~/.certbot/config/live/tg.example.com/
# Symlinks не работают в Docker — копируем с разрешением:
mkdir -p ~/.certbot/flat
cp -L ~/.certbot/config/live/tg.example.com/fullchain.pem ~/.certbot/flat/
cp -L ~/.certbot/config/live/tg.example.com/privkey.pem ~/.certbot/flat/
chmod 644 ~/.certbot/flat/*.pem
```

**Продление**: сертификаты действуют 90 дней. Повторите `certbot renew` и `cp -L`.

### 2. Настройка .env

```bash
# Web-UI
WEBUI_ENABLED=true
WEBUI_PUBLIC_URL=https://tg.example.com:8443
WEBUI_BOT_USERNAME=YourBotUsername
WEBUI_APP_NAME=app
PORT_WEBUI=8443
```

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `WEBUI_ENABLED` | Включить web-ui (Mini App кнопки вместо callback) | `false` |
| `WEBUI_PUBLIC_URL` | Публичный HTTPS URL web-ui | -- |
| `WEBUI_BOT_USERNAME` | Username бота (для Direct Link `t.me/Bot/app`) | -- |
| `WEBUI_APP_NAME` | Short name Mini App из BotFather | `app` |
| `PORT_WEBUI` | Внешний порт web-ui | `8443` |
| `BOT_TOKEN` / `TELEGRAM_BOT_TOKEN` | Токен бота (для валидации initData) | -- |
| `DB_DSN` | PostgreSQL connection string | -- |
| `TGAPI_URL` | URL tgapi для обратных вызовов | `http://tgapi:8000` |

### 3. Регистрация Mini App в BotFather

Для открытия Mini App **внутри Telegram** (а не во внешнем браузере):

1. Откройте @BotFather -> `/newapp`
2. Выберите бота
3. **Title**: название приложения
4. **Description**: описание
5. **Web App URL**: `https://tg.example.com:8443`
6. **Short Name**: `app` (или другое — укажите в `WEBUI_APP_NAME`)

После регистрации кнопки в сообщениях будут вести на `https://t.me/BotUsername/app?startapp=...` — Telegram откроет Mini App внутри приложения.

> **Важно**: `web_app` тип InlineKeyboardButton работает только в **личных чатах**.
> Для **групповых чатов** используется Direct Link (`t.me/Bot/app?startapp=...`),
> который передаётся как обычный `url` в InlineKeyboardButton.

### 4. DNS

Домен Mini App должен быть публично доступен. Добавьте A-запись:

```
tg.example.com  A  <ваш_публичный_IP>
```

### 5. Сетевой доступ (TCP proxy через Tailscale)

Если сервер за NAT (например, Raspberry Pi дома), а публичный IP — на VPS в Tailscale сети:

```bash
# На VPS с публичным IP:
apt install -y socat

# TCP proxy: VPS:8443 -> Pi:8443 (через Tailscale)
nohup socat TCP-LISTEN:8443,fork,reuseaddr TCP:<tailscale_ip>:8443 &

# Для автозапуска — systemd unit:
cat > /etc/systemd/system/tgweb-proxy.service << 'EOF'
[Unit]
Description=TCP proxy for tgweb Mini App
After=network.target tailscaled.service

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:8443,fork,reuseaddr TCP:<tailscale_ip>:8443
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now tgweb-proxy
```

### 6. Docker Compose

```yaml
tgweb:
  build:
    context: ./telegram-mcp
    dockerfile: web-ui/Dockerfile
  container_name: tgweb
  env_file: ./telegram-mcp/.env
  depends_on:
    tgapi:
      condition: service_healthy
    tgdb:
      condition: service_healthy
  environment:
    DB_DSN: postgresql://${DB_USER}:${DB_PASSWORD}@tgdb:5432/${DB_NAME}
    TGAPI_URL: http://tgapi:8000
    PUBLIC_URL: ${WEBUI_PUBLIC_URL}
    BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
  volumes:
    - /path/to/certs:/certs:ro
  command: >
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    --ssl-certfile /certs/fullchain.pem
    --ssl-keyfile /certs/privkey.pem
  ports:
    - "${PORT_WEBUI:-8443}:8000"
```

### 7. Запуск и проверка

```bash
docker compose up -d tgdb tgapi tgweb tgmcp

# Проверка локально:
curl -sk https://localhost:8443/health

# Проверка публично:
curl -sk https://tg.example.com:8443/health
```

## Как работает Direct Link Mini App

1. Бот отправляет сообщение с inline-кнопкой:
   ```
   url: https://t.me/BotUsername/app?startapp=predict-42
   ```
2. Пользователь нажимает кнопку -> Telegram открывает Mini App
3. Telegram загружает зарегистрированный URL (`https://tg.example.com:8443/`)
4. `twa.js` читает `Telegram.WebApp.initDataUnsafe.start_param` = `"predict-42"`
5. JavaScript редиректит на `/p/predict-42`
6. Сервер рендерит страницу предсказания с данными события

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
| `GET` | `/` | Точка входа Mini App (start_param redirect) |
| `GET` | `/p/{slug}` | Рендеринг HTML-страницы |
| `GET` | `/l/{token}` | Редирект по индивидуальной ссылке |
| `POST` | `/p/{slug}/submit` | Отправка формы (с initData) |
| `GET` | `/health` | Healthcheck |

## Типы страниц

### page -- Обычная страница

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

### survey -- Опросник

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

Поддерживаемые типы полей: `text`, `textarea`, `number`, `select`, `radio`, `checkbox`.

### prediction -- Рынок предсказаний

```bash
curl -X POST http://localhost:8081/v1/web/pages \
  -H 'content-type: application/json' \
  -d '{
    "title": "Кто выиграет?",
    "page_type": "prediction",
    "slug": "predict-42",
    "event_id": 42,
    "config": {}
  }'
```

При `WEBUI_ENABLED=true` предсказания автоматически получают кнопку Mini App вместо callback.

## Индивидуальные ссылки

Персональные ссылки привязывают доступ к конкретному пользователю:

```bash
curl -X POST http://localhost:8081/v1/web/pages/my-survey/links \
  -H 'content-type: application/json' \
  -d '{"user_id": 777, "metadata": {"source": "private_message"}}'

# Ответ: {"token": "a1b2c3d4...", "url": "https://tg.example.com:8443/l/a1b2c3d4..."}
```

## Авторизация

### Telegram initData (автоматическая)

При открытии как Mini App, Telegram передает `initData` -- подписанные данные пользователя.

Алгоритм валидации:
1. Парсинг `init_data` как query string
2. Извлечение `hash`, формирование `data_check_string` (sorted `key=value`, разделенные `\n`)
3. `secret_key = HMAC-SHA256("WebAppData", bot_token)`
4. Сравнение `HMAC-SHA256(data_check_string, secret_key)` с `hash`
5. Проверка `auth_date` не старше 24 часов

> Токен бота берется из `BOT_TOKEN` или `TELEGRAM_BOT_TOKEN` (fallback).
> В мультибот-системе initData подписывается токеном того бота,
> через которого открыт Mini App.

### TON Connect (кошелек)

Для TON-предсказаний пользователь подключает кошелёк через TON Connect UI.

### Stars Payments

Оплата через Telegram Stars:
1. Бэкенд создает invoice через `tgapi /v1/stars/invoice`
2. Фронтенд вызывает `Telegram.WebApp.openInvoice(url, callback)`
3. При `status === 'paid'` -- отправка формы с подтверждением

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
        title="Мой опрос", page_type="survey",
        config={"fields": [{"name": "q1", "type": "text", "label": "Вопрос"}]}
    )

    # Список страниц
    pages = await api.list_web_pages()

    # Индивидуальная ссылка
    link = await api.create_web_link("my-survey", user_id=777)

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
| `web_page_links` | Индивидуальные ссылки (token -> page + user) |
| `web_form_submissions` | Ответы на формы (data JSONB) |
| `web_wallet_links` | Привязка TON-кошельков к Telegram-аккаунтам |

> Миграция выполняется автоматически при первом создании БД.
> Для существующей БД: `psql -U telegram -d telegram < db/init/10_web_ui.sql`

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
│   │   └── render.py    # GET /, GET /p/{slug}, GET /l/{token}, POST submit
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
│       ├── twa.js       # TWA bootstrap + start_param redirect + TON Connect
│       └── tonconnect-manifest.json
├── Dockerfile
└── requirements.txt
```

## Troubleshooting

### Mini App открывает внешний браузер вместо Telegram

- Проверьте что Mini App зарегистрирован через `/newapp` в BotFather
- URL кнопки должен быть `https://t.me/BotUsername/app?startapp=...` (не прямой URL)
- `web_app` тип InlineKeyboardButton работает **только в личных чатах**

### Бесконечная загрузка Mini App

- Домен не доступен из интернета. Проверьте DNS (A-запись) и порт (firewall, NAT)
- Сертификат невалидный. Telegram требует доверенный HTTPS (Let's Encrypt подходит)
- Порт занят. Проверьте `ss -tlnp | grep 8443` на сервере

### "Invalid initData" при отправке формы

- `BOT_TOKEN` / `TELEGRAM_BOT_TOKEN` пуст или не соответствует боту Mini App
- В мультибот-системе initData подписывается токеном конкретного бота
- Проверьте: `docker exec tgweb printenv TELEGRAM_BOT_TOKEN`

### "Page not found" при открытии предсказания

- Страница `predict-{event_id}` не создана в `web_pages`
- Создайте вручную или через API: `POST /v1/web/pages {"slug": "predict-42", "page_type": "prediction", "event_id": 42, ...}`
