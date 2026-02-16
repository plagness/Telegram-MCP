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
- **Календарь**: полнофункциональный календарь событий с поиском, фильтрами, эмодзи и аватарками создателей
- **Owner-only дашборды**: LLM, Metrics, Arena, Planner, Infra, BCS, Channel, K8s — мониторинг модулей
- **Bee Design System**: UI toolkit (BeeKit) + визуальные эффекты (BeeFX) + skeleton loading + ECharts
- **Тесты**: 33 функциональных теста + 6 перформанс-бенчмарков (test-fx.html)

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

## Hub (главный экран)

При открытии Mini App без `start_param`, пользователь видит hub — каталог всех доступных страниц.

**Как работает:**
1. `twa.js` определяет отсутствие `start_param`
2. Редирект на `/?initData=...` для серверного рендеринга
3. Сервер валидирует initData, получает `user_id`
4. `get_accessible_pages(user_id)` фильтрует страницы через `check_page_access()`
5. `group_pages_for_hub(pages)` группирует: по чатам → системные → публичные
6. Jinja2 рендерит `hub.html` с карточками

**Элементы hub:**
- Профиль пользователя (аватарка, имя, бейджи ролей)
- Поиск по названиям страниц
- Карточки страниц с иконками типов и описаниями
- Группировка по категориям

**Шаблон:** `web-ui/app/templates/hub.html`

---

## Контроль доступа

Подробная документация: [access-control.md](access-control.md)

Каждая страница может иметь `access_rules` в config:

```json
{
  "access_rules": {
    "public": false,
    "allowed_users": [123456789],
    "allowed_roles": ["project_owner", "tester"],
    "allowed_chats": [-1001234567890]
  }
}
```

**OR-логика:** доступ если хотя бы одно условие выполняется.

### API ролей (через tgapi proxy)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/v1/web/roles` | Список ролей |
| `GET` | `/v1/web/roles/{user_id}` | Роли пользователя |
| `POST` | `/v1/web/roles` | Назначить роль |
| `DELETE` | `/v1/web/roles/{user_id}/{role}` | Отозвать роль |
| `POST` | `/v1/web/roles/check-access` | Проверить доступ |

---

## Реестр нод

Подробная документация: [network.md](network.md)

Реестр публичных серверов хранится в `config/nodes.json` и монтируется в tgweb как volume.

**API:** `GET /v1/web/nodes` — реестр нод (проксируется через tgapi).

**Автоматика прокси:** `scripts/setup/vds_proxy.sh` — деплой socat systemd units на VDS.

---

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
| `GET` | `/v1/web/roles` | Список ролей |
| `POST` | `/v1/web/roles` | Назначить роль |
| `DELETE` | `/v1/web/roles/{user_id}/{role}` | Отозвать роль |
| `POST` | `/v1/web/roles/check-access` | Проверить доступ |
| `GET` | `/v1/web/nodes` | Реестр нод |

### Публичные (tgweb напрямую)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/` | Hub (каталог страниц) или start_param redirect |
| `GET` | `/p/{slug}` | Рендеринг HTML-страницы |
| `GET` | `/l/{token}` | Редирект по индивидуальной ссылке |
| `POST` | `/p/{slug}/submit` | Отправка формы (с initData) |
| `GET` | `/health` | Healthcheck |

## Типы страниц

### calendar -- Календарь событий

Тип `calendar` предоставляет интерактивный календарь с месячной сеткой, списком событий, полноэкранной детализацией, поиском и фильтрами.

```bash
curl -X POST http://localhost:8081/v1/web/pages \
  -H 'content-type: application/json' \
  -d '{
    "title": "Рабочий календарь",
    "page_type": "calendar",
    "slug": "cal-covenant",
    "config": {
      "calendar_id": 1,
      "admin_ids": [123456789],
      "chat_id": -1001234567890
    }
  }'
```

**Конфигурация (`config`)**:

| Поле | Тип | Описание |
|------|-----|----------|
| `calendar_id` | `int` | ID календаря в `calendars` таблице (обязательно) |
| `admin_ids` | `list[int]` | Telegram user IDs с правами управления |
| `chat_id` | `int` | ID чата (для отображения аватарки и названия в шапке) |

**Возможности**:

- **Месячная сетка** с цветными точками событий + переключение на список
- **Полноэкранная детализация** события: эмодзи, бейджи (приоритет, статус, AI), время, описание, теги, информация о создателе
- **Поиск и фильтры**: текстовый поиск, фильтр по статусу / приоритету / тегам / создателю / типу записи (клиентская фильтрация по `data-*` атрибутам)
- **Типы записей (v3)**: событие, задача, триггер, монитор, голосование, рутина — каждый с иконкой и цветом
- **Триггеры и мониторы**: отображение trigger_status (pending/success/failed), tick_count, cost_estimate, source_module
- **Детализация v3**: секции «Тип + триггер», «Действие» (action JSON), «Результат» (result JSON)
- **Эмодзи**: каждому событию можно назначить эмодзи (64 эмодзи в 8 категориях)
- **Аватарки создателей**: AI-модели (Claude, GPT, Gemini, Llama) отображаются с цветными иконками, пользователи — с инициалами
- **Аватарка чата**: загружается через Telegram Bot API `getFile` (кэш 1 час)
- **Профиль пользователя**: фото и имя из `Telegram.WebApp.initDataUnsafe.user`
- **Админ-панель**: FAB-кнопка, форма создания/редактирования, действия «Выполнено» / «Удалить»
- **XSS-защита**: пользовательские данные экранируются через `escapeHtml()`

**Формат `created_by`**:

| Значение | Тип | Отображение |
|----------|-----|-------------|
| `admin:{user_id}` | Пользователь | 👤 синий (#4A90D9) |
| `ai:claude` | Нейросеть | 🤖 фиолетовый (#7C3AED) |
| `ai:gpt` | Нейросеть | 🧠 зелёный (#10A37F) |
| `ai:gemini` | Нейросеть | ✨ синий (#4285F4) |
| `ai:llama` | Нейросеть | 🦙 синий (#0084FF) |
| `null` | Неизвестно | 👤 серый (#9E9E9E) |

**Проксированные эндпоинты** (через tgweb, с initData авторизацией):

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/p/{slug}/calendar/entries` | Создать событие |
| `PUT` | `/p/{slug}/calendar/entries/{id}` | Обновить событие |
| `POST` | `/p/{slug}/calendar/entries/{id}/status` | Изменить статус |
| `DELETE` | `/p/{slug}/calendar/entries/{id}` | Удалить событие |

**БД миграция**: `db/init/11_calendar.sql`

| Таблица | Назначение |
|---------|------------|
| `calendars` | Календари (name, owner, metadata) |
| `calendar_entries` | События (title, description, emoji, start_at, end_at, priority, status, tags, created_by, ai_actionable, entry_type, trigger_at, trigger_status, action, result, source_module, cost_estimate, tick_interval, next_tick_at, tick_count, max_ticks, expires_at) |
| `calendar_history` | История изменений (action, changes, performed_by) |

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

### llm -- LLM Dashboard

Тип страницы `llm` для мониторинга llm-mcp системы.

```json
{
  "page_type": "llm",
  "title": "LLM",
  "slug": "llm",
  "config": {
    "llm_core_url": "http://llmcore:8080",
    "description": "Мониторинг LLM-кластера"
  }
}
```

Секции дашборда:
- **Job Queue** — queued/running/done/failed с progress bar
- **Costs** — расходы за today/week/month (USD)
- **Fleet** — иерархия Host→Node с моделями, latency, stats, circuit breaker
- **Running Jobs** — текущие активные задачи с моделью и устройством
- **Issues** — проблемы на человеческом языке (offline hosts, stuck queue)

Клиентский JS загружает данные через `BeeKit.poll()` с skeleton crossfade. Эффекты: `bee-shiny` на month cost, `countUp` на costs при первой загрузке.

### infra -- Infrastructure Monitor

Тип страницы `infra` — общий мониторинг кластера с интерактивным клиентским рендером.

```json
{
  "page_type": "infra",
  "title": "Infra",
  "slug": "infra",
  "config": {
    "llm_core_url": "http://llmcore:8080",
    "description": "Инфраструктура"
  }
}
```

Секции:
- **Gauges** — Fleet availability (online/total), Load (jobs/capacity)
- **Issues** — баннер с проблемами (offline hosts, circuit breakers, low success rate)
- **Fleet** — иерархия Host→Node с expand/collapse, capacity bars, device stats
- **Job Queue** — queued/running/done/failed
- **Running Jobs** — активные задачи
- **Costs** — расходы по периодам

Клиентский JS загружает данные через fetch API и рендерит DOM. Bottom sheet показывает список моделей при клике на устройство. Автообновление каждые 5с.

### metrics -- Market Data Dashboard

```json
{
  "page_type": "metrics",
  "title": "Metrics",
  "slug": "metrics",
  "config": {
    "metrics_api_url": "http://metricsapi-service:8080",
    "description": "Рыночные данные"
  }
}
```

Секции: FX & Crypto headlines (USD/RUB, EUR/RUB, BTC, Gold), Market Data list, Stock Indices ECharts bar chart + таблица, Infrastructure status.

### arena -- Arena LLM Dashboard

```json
{
  "page_type": "arena",
  "title": "Arena",
  "slug": "arena",
  "config": {
    "arena_core_url": "http://arenacore-service:8080"
  }
}
```

Секции: Health, Matches (total/today), Leaderboard, Species, Predictions, Presets (accordion).

### planner -- Planner Dashboard

```json
{
  "page_type": "planner",
  "title": "Planner",
  "slug": "planner",
  "config": {
    "planner_core_url": "http://plannercore-service:8080"
  }
}
```

Секции: Speed Mode, Budget (countUp), Tasks, Connected Modules, Schedules, Active Triggers (bee-star-border), Task Log (bottom sheet + chips).

### bcs / channel / k8s -- Прочие дашборды

Аналогичная структура. Каждый дашборд имеет свой `page_type`, `*_url` в config, шаблон и proxy-endpoint в `module_proxy.py`.

---

## Bee Design System

Подробная документация: [web-ui/docs/UI-GUIDE.md](../web-ui/docs/UI-GUIDE.md)

### Компоненты

| Модуль | Файл | Описание |
|--------|------|----------|
| **BeeKit** | `bee-kit.js` | UI toolkit: poll (skeleton crossfade), sheet, stale, accordion, haptic |
| **BeeFX** | `bee-fx.js` | Эффекты: countUp, revealText, fadeIn, spotlight, clickSpark, ripple |
| **CSS** | `style.css` | Design system + skeleton + CSS-эффекты (shiny, gradient, star-border, glare, glitch) |
| **ECharts** | `echarts.min.js` | Apache ECharts 6.0.0 (lazy-load, SVG renderer) |

### Тесты

Файл: `static/test-fx.html` — самодостаточный browser test runner.

- 33 функциональных теста по 7 модулям
- 6 перформанс-бенчмарков с порогами
- Доступ: `https://<host>:8443/static/test-fx.html`

---

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
| `webui.create_page` | Создать страницу (page/survey/prediction/calendar) |
| `webui.list_pages` | Список страниц |
| `webui.create_link` | Создать индивидуальную ссылку |
| `webui.get_submissions` | Получить ответы формы |
| `webui.create_prediction` | Создать страницу предсказания (shortcut) |
| `webui.create_survey` | Создать опросник (shortcut) |
| `webui.list_roles` | Список ролей (опционально `user_id`) |
| `webui.grant_role` | Назначить роль |
| `webui.revoke_role` | Отозвать роль |
| `webui.check_access` | Проверить доступ к странице |

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

Миграции: `db/init/10_web_ui.sql`, `db/init/11_calendar.sql`, `db/init/12_access_control.sql`

| Таблица | Назначение |
|---------|------------|
| `web_pages` | Страницы (slug, type, config, template) |
| `web_page_links` | Индивидуальные ссылки (token -> page + user) |
| `web_form_submissions` | Ответы на формы (data JSONB) |
| `web_wallet_links` | Привязка TON-кошельков к Telegram-аккаунтам |
| `calendars` | Календари (11_calendar.sql) |
| `calendar_entries` | События календаря (11_calendar.sql) |
| `calendar_history` | История изменений календаря (11_calendar.sql) |
| `user_roles` | Глобальные роли пользователей (12_access_control.sql) |

> Миграция выполняется автоматически при первом создании БД.
> Для существующей БД: `psql -U telegram -d telegram < db/init/12_access_control.sql`

## Структура файлов

```
web-ui/
├── app/
│   ├── main.py              # FastAPI + Jinja2 + static + lifespan
│   ├── config.py            # Settings: PUBLIC_URL, TGAPI_URL, BOT_TOKEN
│   ├── db.py                # PostgreSQL pool (psycopg)
│   ├── auth.py              # Telegram initData HMAC-SHA256 валидация
│   ├── routers/
│   │   ├── health.py        # GET /health
│   │   ├── icons.py         # SVG иконки (3300+ брендов)
│   │   ├── pages.py         # CRUD API для страниц
│   │   ├── render.py        # GET /, GET /p/{slug}, GET /l/{token}, POST submit, hub
│   │   ├── roles.py         # REST API управления ролями
│   │   └── module_proxy.py  # Proxy к backend-модулям (llm, metrics, arena, planner, ...)
│   ├── services/
│   │   ├── access.py        # check_page_access(), get_accessible_pages()
│   │   ├── links.py         # Генерация токенов, создание ссылок
│   │   ├── nodes.py         # Загрузка и кэш реестра нод
│   │   ├── pages.py         # CRUD web_pages в БД
│   │   └── roles.py         # CRUD для user_roles
│   ├── templates/
│   │   ├── base.html           # Base layout (bee-kit, bee-fx, lottie)
│   │   ├── hub.html            # Главный экран (каталог, mini-metrics, fade-in)
│   │   ├── llm.html            # LLM Dashboard (costs, fleet, jobs)
│   │   ├── metrics.html        # Market Data (FX, crypto, indices ECharts)
│   │   ├── arena.html          # Arena LLM (matches, leaderboard)
│   │   ├── planner.html        # Planner (budget, triggers, task log)
│   │   ├── infra.html          # Infrastructure (gauges, fleet, crossfade)
│   │   ├── bcs.html            # BCS (портфели, P&L)
│   │   ├── channel.html        # Channel (каналы, статистика)
│   │   ├── k8s.html            # K8s (кластер, поды)
│   │   ├── calendar.html       # Календарь (сетка, поиск, детализация)
│   │   ├── prediction.html     # Polymarket UI
│   │   ├── survey.html         # Динамические формы
│   │   ├── error.html          # Ошибки (404, 403)
│   │   └── page.html           # Универсальная страница
│   └── static/
│       ├── style.css           # Bee Design System (~3900 строк)
│       ├── bee-kit.js          # UI toolkit: poll, sheet, stale, accordion
│       ├── bee-fx.js           # Визуальные эффекты (из react-bits)
│       ├── bee-glass.js        # Liquid glass morphism
│       ├── echarts.min.js      # Apache ECharts 6.0.0
│       ├── twa.js              # TWA bootstrap + start_param + haptic
│       ├── test-fx.html        # Тесты BeeFX + BeeKit (33 + 6 perf)
│       ├── tonconnect-manifest.json
│       └── icons/              # SVG-иконки (3300+ брендов)
├── docs/
│   ├── UI-GUIDE.md             # Bee Design System — руководство разработчика
│   └── CHANGELOG.md            # Лог изменений web-ui
├── Dockerfile
└── requirements.txt
```

## Troubleshooting

### Mini App открывает внешний браузер вместо Telegram

- Проверьте что Mini App зарегистрирован через `/newapp` в BotFather
- URL кнопки должен быть `https://t.me/BotUsername/app?startapp=...` (не прямой URL)
- `web_app` тип InlineKeyboardButton работает **только в личных чатах**

### Бесконечная загрузка Mini App

- **Порт не совпадает с socat на VPS**. socat пробрасывает на `<tailscale_ip>:8443`,
  а `compose.yml` маппит другой порт (например 8090). Проверьте:
  ```bash
  ss -tlnp | grep 8443   # должен слушать
  docker port tgweb       # должен показать 8443
  ```
  Если не совпадает — в `compose.yml` должно быть `"${PORT_WEBUI:-8443}:8000"`
  с `command` включающим `--ssl-certfile` и `--ssl-keyfile`.

- **SSL отсутствует в compose.yml**. tgweb **обязан** запускаться с TLS,
  иначе socat пробросит TCP, но TLS handshake провалится (ошибка `unexpected eof`).
  Обязательные элементы в compose.yml:
  ```yaml
  volumes:
    - ${HOME}/.certbot/flat:/certs:ro
  command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000",
            "--ssl-certfile", "/certs/fullchain.pem", "--ssl-keyfile", "/certs/privkey.pem"]
  ports:
    - "${PORT_WEBUI:-8443}:8000"
  ```

- **Домен не доступен из интернета**. Проверьте DNS (A-запись) и порт (firewall, NAT)
- **Сертификат невалидный**. Telegram требует доверенный HTTPS (Let's Encrypt подходит)
- **Диагностика**: `curl -sk -v https://tg.example.com:8443/health` — должен вернуть
  `{"status":"ok","service":"tgweb"}`. Если `unexpected eof` — нет TLS на tgweb.
  Если `Connection refused` — порт не слушает.

### "Invalid initData" при отправке формы

- `BOT_TOKEN` / `TELEGRAM_BOT_TOKEN` пуст или не соответствует боту Mini App
- В мультибот-системе initData подписывается токеном конкретного бота
- Проверьте: `docker exec tgweb printenv TELEGRAM_BOT_TOKEN`

### "Page not found" при открытии предсказания

- Страница `predict-{event_id}` не создана в `web_pages`
- Создайте вручную или через API: `POST /v1/web/pages {"slug": "predict-42", "page_type": "prediction", "event_id": 42, ...}`
