# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат версий: `[год].[месяц].[версия]`

---

## [2026.02.21] - 2026-02-16

### Добавлено

#### Bee Design System — UI toolkit + визуальные эффекты

Полная система переиспользуемых компонентов для Telegram Mini App. Два JS-модуля, набор CSS-эффектов, skeleton loading, Apache ECharts.

**bee-kit.js** — UI toolkit:
- `BeeKit.poll()` — data polling с skeleton crossfade, stale detection, auto-retry
- `BeeKit.sheet` — bottom sheet с toolbar (фильтры, сортировка)
- `BeeKit.stale` — stale data indicator banner
- `BeeKit.initAccordions()` — auto-init для `[data-bee-accordion]`
- `[data-haptic]` — автоматический haptic feedback

**bee-fx.js** — визуальные эффекты (портировано из react-bits в vanilla JS):
- `BeeFX.countUp()` — анимация чисел (из CountUp.jsx)
- `BeeFX.revealText()` — посимвольное раскрытие (из BlurText + SplitText)
- `BeeFX.initFadeIn()` — каскадное появление с IntersectionObserver
- `BeeFX.initSpotlight()` — подсветка за пальцем (из SpotlightCard.jsx)
- `BeeFX.clickSpark()` — Canvas искры при тапе (из ClickSpark.jsx)
- `BeeFX.initRipple()` — Material Design ripple feedback

**CSS-эффекты** (портированы из react-bits в чистый CSS):
- `.bee-shiny` — shimmer на тексте (из ShinyText.jsx)
- `.bee-gradient-text` — градиентный текст (из GradientText.jsx)
- `.bee-star-border` — анимированная рамка (из StarBorder.jsx)
- `.bee-glare` — блик при касании
- `.bee-glitch` — glitch эффект для ошибок (из GlitchText.jsx)
- `.bee-fade-in` — entry animations с авто-стаггером
- `.bee-ripple` — touch ripple container

**Skeleton Loading**:
- Анимированные shimmer-плейсхолдеры вместо текста загрузки
- Компоненты: `--title`, `--line`, `--value`, `--label`, `--chart`, `--avatar`
- Плавный crossfade skeleton → content (double rAF)
- Стаггер для нескольких skeleton-карточек

**Apache ECharts 6.0.0**:
- Lazy-load через `{% block head_libs %}`
- SVG renderer для мобильных
- Графики: costs bar chart (LLM), stock indices bar chart (Metrics)

#### 6 owner-only дашбордов (Mini App)

- **Metrics** (`metrics.html`) — FX & Crypto headlines, market data list, stock indices ECharts
- **Arena** (`arena.html`) — health, matches, leaderboard, species, predictions, presets (accordion)
- **Planner** (`planner.html`) — speed mode, budget, tasks, modules, schedules, triggers, task log (sheet + chips)
- **BCS** (`bcs.html`) — портфели, позиции, P&L
- **Channel** (`channel.html`) — каналы, статистика, последние посты
- **K8s** (`k8s.html`) — кластер, namespace'ы, поды

**Визуальные эффекты на дашбордах:**
- `bee-shiny` на BTC-цене и month cost
- `countUp` на costs/budget при первой загрузке (`_fxDone` паттерн)
- `bee-star-border` на активных триггерах
- `bee-fade-in` на карточках hub
- Crossfade skeleton → content на infra dashboard

#### Module Proxy (module_proxy.py)

- Новый роутер для cross-namespace запросов к backend-модулям (llm-mcp, metrics, arena, planner, bcs, channel)
- `_fetch_*_data()` + `GET /p/{slug}/*/data` endpoint pattern
- Owner-only access через initData проверку

#### Тесты (test-fx.html)

- Самодостаточная HTML-страница с встроенным micro test runner
- 33 функциональных теста (countUp, revealText, initFadeIn, initRipple, initSpotlight, sheet, stale)
- 6 перформанс-бенчмарков с порогами (countUp×50, revealText×10, initFadeIn×100, Ripple×100, Skeleton×20, querySelectorAll×500)
- Touch event simulation для мобильных эффектов
- Console + visual output

#### Документация

- **`web-ui/docs/UI-GUIDE.md`** — полное руководство разработчика Bee UI системы
- **`web-ui/docs/CHANGELOG.md`** — лог изменений web-ui

### Изменено

- `hub.html` → mini-metrics на карточках модулей, bee-fade-in каскад
- `llm.html` → client-side fetch+render вместо server-side reload
- `metrics.html` → /v1/metrics/snapshot через module_proxy
- `infra.html` → crossfade skeleton → content
- `base.html` → bee-kit.js + bee-fx.js в порядке загрузки скриптов
- `style.css` → skeleton, все CSS-эффекты, bee-kit/fx стили
- VERSION: `2026.02.20` → `2026.02.21`

---

## [2026.02.20] - 2026-02-14

### Добавлено

#### Hub v2 — переработка главного экрана

- **Orbital emoji system** — динамические иконки модулей
- **Access control** — проверка доступа к страницам через access_rules
- **3-tier layout** — стандартизация структуры (context → content → scripts)

### Изменено

- Санитизация кода — удаление реальных доменов, ID, путей
- VERSION: `2026.02.19` → `2026.02.20`

---

## [2026.02.19] - 2026-02-10

### Добавлено

#### LLM Infrastructure Dashboard (Mini App)

- **Новый шаблон `infra.html`** — страница мониторинга LLM-инфраструктуры
  - Cluster Overview: устройства, модели, running jobs, статус
  - Fleet: карточки устройств с иконками (Simple Icons), статусом, latency
  - Performance gauges: CPU Load, Capacity
  - Job Queue: статистика очереди + progress bar
  - Running Jobs: текущие задачи в реальном времени
  - Costs: расходы за день/неделю/месяц (USD)
  - Auto-refresh каждые 10 сек (без мерцания)
- **All Models sheet** — каталог всех моделей кластера
  - Агрегация моделей по устройствам с device tags
  - Сортировка: Popular, A-Z, Size, Devices
  - Фильтр по устройству через чипы
  - Bottom sheet UI (native Telegram Mini App feel)
- **Иконки производителей моделей** через Simple Icons:
  - Alibaba Cloud → Qwen, Meta → Llama/TinyLlama, Google → Gemma
  - Microsoft (.NET) → Phi, HuggingFace → SmolLM/Nomic, Mistral AI → Mistral
  - Text fallback для отсутствующих: Yi (01.AI), IBM (Granite), LG (ExaOne)
- **Прокси-эндпоинт** `GET /p/{slug}/infra/data` с проверкой `allowed_users`
- **page_type `infra`** в template_map

#### Документация

- **`docs/access-control.md`** — design doc будущей системы доступов
  - Два уровня: chat-based + global roles
  - Текущая инфраструктура и план расширения
  - access_rules schema (allowed_users, allowed_roles, allowed_chats)

### Изменено

- VERSION: `2026.02.18` → `2026.02.19`

---

## [2026.02.18] - 2026-02-10

### Добавлено

- K8s миграция: hostPort для SSL, webhook proxy, исправления деплоя

---

## [2026.02.17] - 2026-02-09

### Добавлено

#### 🚀 Bot API 9.1–9.4 — полная поддержка

Масштабная реализация всех методов Bot API 9.1–9.4 по всем 5 слоям архитектуры: Telegram Client, Pydantic Models, FastAPI Routers, MCP Tools (TypeScript), Python SDK.

**Итого:** 128 MCP-инструментов, 173 API-эндпоинта, ~95 SDK-методов.

##### Bot API 9.4

- **setMyProfilePhoto / removeMyProfilePhoto** — установка и удаление фото профиля бота
  - Эндпоинты: `POST /v1/bots/profile-photo`, `DELETE /v1/bots/profile-photo`
  - MCP: `bots.set_profile_photo`, `bots.remove_profile_photo`
  - SDK: `set_my_profile_photo()`, `remove_my_profile_photo()`
- **getUserProfileAudios** — получение аудио профиля пользователя
  - Эндпоинт: `GET /v1/bots/users/{user_id}/profile-audios`
  - MCP: `bots.user_profile_audios`
  - SDK: `get_user_profile_audios()`
- **editUserStarSubscription** — редактирование Star-подписки пользователя
  - Эндпоинт: `POST /v1/bots/star-subscription/edit`
  - MCP: `stars.edit_subscription`
  - SDK: `edit_user_star_subscription()`
- **Стилизованные кнопки**: параметр `button_style` (primary, danger, success) + `icon_custom_emoji_id` для inline-кнопок — проксируются через существующие send-методы

##### Bot API 9.3

- **sendMessageDraft** — отправка черновиков в бизнес-чаты
  - Эндпоинт: `POST /v1/messages/draft`
  - MCP: `messages.draft`
  - SDK: `send_message_draft()`
- **getUserGifts / getChatGifts** — подарки пользователя и чата
  - Эндпоинты: `GET /v1/gifts/user/{user_id}`, `GET /v1/gifts/chat/{chat_id}`
  - MCP: `stars.gifts_user`, `stars.gifts_chat`
  - SDK: `get_user_gifts()`, `get_chat_gifts()`
- **repostStory** — репост историй между каналами
  - Эндпоинт: `POST /v1/stories/repost`
  - MCP: `stories.repost`
  - SDK: `repost_story()`
- **postStory / editStory / deleteStory** — управление историями каналов
  - Эндпоинты: `POST /v1/stories/post`, `PUT /v1/stories/{story_id}`, `DELETE /v1/stories/{story_id}`
  - MCP: `stories.post`, `stories.edit`, `stories.delete`
  - SDK: `post_story()`, `edit_story()`, `delete_story()`
- **Форум-топики** — полное управление топиками (вкл. личные чаты)
  - Эндпоинты: `POST /v1/forums/topics`, `PUT /v1/forums/topics/{id}`, `POST /v1/forums/topics/{id}/close`, `POST /v1/forums/topics/{id}/reopen`, `DELETE /v1/forums/topics/{id}`, `POST /v1/forums/general/hide`, `POST /v1/forums/general/unhide`
  - MCP: `forums.create_topic`, `forums.edit_topic`, `forums.close_topic`, `forums.reopen_topic`, `forums.delete_topic`, `forums.hide_general`, `forums.unhide_general`
  - SDK: `create_forum_topic()`, `edit_forum_topic()`, `close_forum_topic()`, `reopen_forum_topic()`, `delete_forum_topic()`, `hide_general_forum_topic()`, `unhide_general_forum_topic()`

##### Bot API 9.2

- **approveSuggestedPost / declineSuggestedPost** — управление предложенными постами в бизнес-каналах
  - Эндпоинты: `POST /v1/suggested-posts/approve`, `POST /v1/suggested-posts/decline`
  - MCP: `suggested_posts.approve`, `suggested_posts.decline`
  - SDK: `approve_suggested_post()`, `decline_suggested_post()`
  - Новый роутер: `api/app/routers/suggested_posts.py`
  - Новый MCP-модуль: `mcp/src/tools/suggested_posts.ts`
- **direct_messages_topic_id** — маршрутизация сообщений в топики через Direct Messages
  - Добавлен в ~22 Send*In модели + ForwardMessageIn, CopyMessageIn
  - Проброс в роутерах: messages.py (~5 функций), media.py (~14 функций), checklists.py
  - SDK: kwargs в ~20 методах
- **suggested_post_parameters** — параметры для предложенных постов
  - Добавлен в ~22 Send*In модели + forward/copy
  - Проброс в тех же роутерах и SDK

##### Bot API 9.1

- **sendChecklist / editMessageChecklist** — интерактивные чек-листы с задачами
  - Эндпоинты: `POST /v1/checklists/send`, `PUT /v1/messages/{id}/checklist`
  - MCP: `checklists.send`, `checklists.edit`
  - SDK: `send_checklist()`, `edit_checklist()`
- **getMyStarBalance** — баланс звёзд бота
  - Эндпоинт: `GET /v1/stars/balance`
  - MCP: `stars.balance`
  - SDK: `get_star_balance()`
- **giftPremiumSubscription** — подарок премиум-подписки
  - Эндпоинт: `POST /v1/gifts/premium`
  - MCP: `stars.gifts_premium`
  - SDK: `gift_premium()`

#### 🤖 Мультибот-архитектура

Полная поддержка нескольких ботов с единым реестром и маршрутизацией.

- Реестр ботов: `GET/POST /v1/bots`, `GET /v1/bots/default`, `PUT /v1/bots/{id}/default`, `DELETE /v1/bots/{id}`
- Авто-регистрация из `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BOT_TOKENS`
- `bot_id` параметр во всех send/webhook/commands/stars/checklists эндпоинтах
- MCP: `bots.list`, `bots.register`, `bots.default`, `bot.info`
- SDK: `list_bots()`, `register_bot()`, `get_default_bot()`, `set_default_bot()`
- Базовая информация о боте: `GET /v1/bot/me`

#### 📡 Расширенные медиа, сообщения и чаты

- **sendAnimation, sendAudio, sendVoice, sendSticker** — полная поддержка всех типов медиа
- **sendMediaGroup** — альбомы (2-10 фото/видео)
- **sendVenue, sendContact, sendDice, sendLocation** — специальные типы сообщений
- **forwardMessages / copyMessages** — пакетная пересылка/копирование
- **message_effect_id** — эффекты на сообщениях
- **show_caption_above_media** — подпись над медиа
- **Chat Management**: ban/unban/restrict/promote участников
- **Chat Info**: расширенная информация о чатах, alias, history
- **MCP**: `media.send_video`, `media.send_audio`, `media.send_voice`, `media.send_sticker`, `media.send_animation`, `media.send_venue`, `media.send_contact`, `media.send_dice`, `media.send_location`, `media.send_media_group`, `messages.forward_bulk`, `messages.copy_bulk`, `messages.pin`, `messages.unpin`, `chats.list`, `chats.alias`, `chats.history`, `chats.ban`, `chats.unban`, `chats.restrict`, `chats.promote`, `chats.create_invite_link`

#### 💰 Баланс и виртуальные валюты

- Внутренняя система балансов: пополнение, списание, история транзакций
- Поддержка множественных валют
- MCP: `balance.get`, `balance.credit`, `balance.debit`, `balance.currencies`

### Исправлено

- **SDK**: параметр `is_personal` переименован в `is_public` в `set_my_profile_photo()` (соответствие Bot API)

### Изменено
- VERSION: `2026.02.16` → `2026.02.17`
- MCP tools: 78 → 128 (+50 инструментов)
- API endpoints: ~92 → 173 (+81 эндпоинт)
- SDK methods: ~77 → ~95 (+18 методов)
- Новые роутеры: `bots.py`, `forums.py`, `stories.py`, `suggested_posts.py`
- Новые MCP-модули: `bots.ts`, `forums.ts`, `stories.ts`, `suggested_posts.ts`
- README: бейдж Bot API 9.4, обновлённые счётчики

### Документация
- `README.md` — бейдж Bot API 9.4, секция Bot API 9.1–9.4, обновлённая структура
- `CHANGELOG.md` — подробный лог всех изменений
- `docs/mcp.md` — обновлён: 128 инструментов, новые секции
- `docs/api.md` — обновлён: новые эндпоинты Bot API 9.x
- `docs/sdk.md` — обновлён: новые методы SDK

---

## [2026.02.16] - 2026-02-09

### Добавлено

#### 📅 Календарь v3 — Триггеры, Действия, Бюджет

Календарь становится бэкендом расписания для будущего Planner-модуля. Записи теперь поддерживают триггеры, мониторы, действия и отслеживание стоимости.

**База данных (`db/init/11_calendar.sql`):**
- 12 новых колонок: `entry_type`, `trigger_at`, `trigger_status`, `action` (JSONB), `result` (JSONB), `source_module`, `cost_estimate`, `tick_interval`, `next_tick_at`, `tick_count`, `max_ticks`, `expires_at`
- Колонка `icon TEXT` — Simple Icons slug для SVG-иконки записи
- 3 CHECK-ограничения: entry_type (event/task/trigger/monitor/vote/routine), trigger_status (7 состояний), tick_interval (формат "Nm/h/d")
- 5 индексов: due entries, next tick, type, source, expires

**API:**
- Типы записей: event, task, trigger, monitor, vote, routine
- Жизненный цикл триггеров: pending → scheduled → fired → success/failed/skipped/expired
- Action JSONB: mcp_call, webhook, notify, create_entry, vote, noop — с цепочками on_success/on_failure
- Result JSONB: status, duration_ms, actual_cost, output, error, next_action
- 5 новых эндпоинтов: `GET /entries/due`, `POST /entries/{id}/fire`, `POST /entries/{id}/tick`, `GET /budget`, `POST /entries/expire`
- 3 новых фильтра в `GET /entries`: entry_type, trigger_status, source_module
- Бюджет: SUM cost_estimate с GROUP BY source_module за день/неделю/месяц
- 4 новые Pydantic-модели: `FireEntryIn`, `TickEntryIn`, `CreateTriggerIn`, `CreateMonitorIn`
- Поля `emoji` и `icon` во всех entry-моделях

**MCP (+7 инструментов, теперь 78 всего):**
- `calendar.get_due` — записи, готовые к исполнению
- `calendar.fire` — записать результат триггера
- `calendar.tick` — продвинуть тик монитора
- `calendar.budget` — сводка бюджета за период
- `calendar.create_trigger` — шорткат создания триггера
- `calendar.create_monitor` — шорткат создания монитора
- `icons.resolve` — проверка доступности SVG-иконки по имени (3300+ брендовых иконок)
- Поля `emoji` и `icon` в calendar.create_entry, update_entry, create_trigger, create_monitor, bulk_create

#### 🎨 Simple Icons — система SVG-иконок

Локальная система иконок на базе [Simple Icons](https://simpleicons.org/) (3393 брендовых SVG-иконки). Доступна через MCP, API, SDK и Web-UI.

**Ядро (`web-ui/app/icons.py`):**
- Python-резолвер с алиасами (btc→bitcoin, claude→claude) и keyword matching
- Коррекция тёмных цветов для UI (luminance-based)
- 3393 локальных SVG-файла (`/static/icons/{slug}.svg`)

**API (`web-ui/app/routers/icons.py`):**
- `GET /api/icons/resolve?name=claude` — резолв имени в SVG-иконку с hex-цветом
- `GET /api/icons/redirect?name=btc` — 302 редирект на SVG-файл
- `GET /api/icons/info` — статистика и список алиасов

**MCP → tgweb (`mcp/src/tools/icons.ts`):**
- `icons.resolve` — LLM может проверить доступность иконки перед использованием
- Отдельный `webApiRequest` для обращения к tgweb (HTTPS)

**Web-UI:**
- Entry-level icon: поле `icon` → SVG в заголовке записи (приоритет над emoji)
- Кастомные виджеты через `metadata.widgets: [{label, value, icon}]`
- CSS: `.bee-cal-event-icon-inline` — цветной фон + белая SVG-иконка

**SDK (`sdk/telegram_api_client/client.py`):**
- Новые методы: `create_calendar_entry()`, `update_calendar_entry()`, `list_calendar_entries()`, `get_calendar_entry()`, `delete_calendar_entry()`
- Поддержка `icon` и `emoji` через `**kwargs`

### Изменено
- VERSION: `2026.02.15` → `2026.02.16`
- MCP tools: 71 → 78
- compose.yml: `TGWEB_URL` и `NODE_TLS_REJECT_UNAUTHORIZED` для tgmcp
- MCP config: `webBase` для обращения к tgweb

### Документация
- `docs/icons.md` — **новый**: архитектура, Python/API/MCP/SDK использование, алиасы, обновление
- `docs/mcp.md` — 7 новых инструментов, секция «Иконки»
- `docs/web-ui.md` — типы записей, триггеры, поля calendar_entries
- `README.md` — Calendar v3 + Simple Icons, бейдж 78 инструментов

---

## [2026.02.15] - 2026-02-09

### Добавлено

#### 📅 Календарь (Calendar v2) — полнофункциональный модуль

**База данных:**
- Миграция `db/init/11_calendar.sql`
- Таблицы: `calendars`, `calendar_entries` (с emoji, priority, tags, ai_actionable), `calendar_history`
- Колонка `emoji TEXT` для визуального обозначения событий

**API:**
- Роутер `api/app/routers/calendar.py` — полный CRUD для календарей и записей
- Сервис `api/app/services/calendar.py` — бизнес-логика, history tracking, bulk операции
- Превью `api/app/services/calendar_preview.py` — предпросмотр записей для LLM
- Pydantic-модели: `CreateEntryIn`, `UpdateEntryIn`, `BulkEntryIn` с полем `emoji`

**Web-UI (Telegram Mini App):**
- Тип страницы `calendar` с интерактивной месячной сеткой
- Полноэкранная детализация события (эмодзи, бейджи, теги, создатель)
- Поиск и фильтры: текст, статус, приоритет, теги, создатель (клиентская фильтрация)
- Эмодзи-пикер: 64 эмодзи в 8 категориях
- Аватарки создателей: AI-модели (Claude 🤖, GPT 🧠, Gemini ✨, Llama 🦙) + пользователи
- Аватарка чата через Telegram Bot API `getFile` (кэш 1 час)
- Профиль пользователя из `Telegram.WebApp.initDataUnsafe.user`
- Админ-панель: FAB, форма создания/редактирования, действия
- Proxy-эндпоинты с initData авторизацией: CRUD + status

**MCP (+14 инструментов, теперь 71 всего):**
- `calendar.create`, `calendar.list` — CRUD календарей
- `calendar.create_entry`, `calendar.list_entries`, `calendar.get_entry` — записи
- `calendar.get_chain`, `calendar.update_entry`, `calendar.move_entry` — навигация
- `calendar.set_status`, `calendar.delete_entry` — управление
- `calendar.entry_history`, `calendar.bulk_create`, `calendar.bulk_delete` — массовые операции
- `calendar.upcoming` — предстоящие события

**Безопасность:**
- XSS-защита: `escapeHtml()` для пользовательских данных в JS
- HMAC-SHA256 валидация initData на всех proxy-эндпоинтах
- `created_by` атрибуция: `admin:{user_id}` / `ai:{model}`
- Эмодзи-пикер ограничен `{% if is_admin %}` (убран лишний DOM для не-админов)

### Изменено
- Порт `tgweb` по умолчанию: `8090` → `8443` (TLS обязателен)
- VERSION: `2026.02.14` → `2026.02.15`

### Документация
- `docs/web-ui.md` — секция «calendar» с конфигурацией, возможностями, форматом `created_by`, эндпоинтами, таблицами БД
- `docs/mcp.md` — секция «Календарь» с 14 инструментами
- `README.md` — бейдж версии, секция Calendar v2, обновлённая архитектура и структура

---

## [2026.02.14] - 2026-02-08

### Добавлено

#### Mini App: Direct Link + TLS + публичный доступ
- **Direct Link Mini App**: кнопки в групповых чатах ведут на
  `t.me/BotUsername/app?startapp=...` — открывается как Mini App внутри Telegram
- Настройки `WEBUI_BOT_USERNAME` и `WEBUI_APP_NAME` в `api/app/config.py`
- `keyboards.py`: приоритет Direct Link > url > callback_data
- Корневой маршрут `GET /` в web-ui — точка входа, `twa.js` парсит
  `start_param` и редиректит на `/p/{slug}`
- TLS: uvicorn с `--ssl-certfile`/`--ssl-keyfile` (Let's Encrypt)
- HTTPS-прокси: `webui.py` -> `https://tgweb:8000` с `verify=False`
- `get_bot_token()` с fallback `BOT_TOKEN` -> `TELEGRAM_BOT_TOKEN`
- Порт по умолчанию: `8443`

### Исправлено
- `web_app` InlineKeyboardButton только в личных чатах — для групп `url` (Direct Link)
- HTTPS proxy: `webui.py` использовал HTTP после включения TLS
- Пустой `BOT_TOKEN` из-за перезаписи compose environment — fallback на `TELEGRAM_BOT_TOKEN`

### Документация
- `docs/web-ui.md` — полная документация: SSL, DNS, BotFather, Tailscale proxy, troubleshooting
- `.env.example` — обновлён с новыми переменными, порт 8443

---

## [2026.02.13] - 2026-02-08

### Исправлено
- Регенерация контрактных манифестов после рефакторинга:
  - `api_endpoints_manifest.json` — 92 эндпоинта (было 84)
  - `mcp_tools_manifest.json` — 57 инструментов (было 21, сканировал только index.ts)
  - `sdk_methods_manifest.json` — 77 методов (было 74)
- MCP-тест (`test_tool_to_endpoint_mapping.py`) — сканирование `tools/*.ts` вместо `index.ts`
- API-тест (`test_contract_endpoints.py`) — уникальность по `(method, path, file)` вместо `(method, path)`

---

## [2026.02.12] - 2026-02-08

### Добавлено

#### 🌐 Web-UI (Telegram Mini App)
- Новый модуль `web-ui/` — веб-интерфейс для создания интерактивных страниц внутри Telegram
- Типы страниц: `page` (обычная), `survey` (опросник), `prediction` (рынок предсказаний)
- Авторизация через Telegram initData (HMAC-SHA256 валидация)
- TON Connect — подключение кошелька для TON-платежей
- Stars Payments — оплата через `Telegram.WebApp.openInvoice()`
- Индивидуальные ссылки с уникальными токенами
- Jinja2 шаблоны: `base.html`, `prediction.html`, `survey.html`, `page.html`
- CSS тема с Telegram CSS variables (`--tg-theme-*`)
- Docker-сервис `tgweb` на порту 8090

#### 🔧 Рефакторинг
- **predictions.py**: разбит с 1077 строк на тонкий роутер (~170 строк) + сервисный слой
  - `api/app/services/predictions.py` — SQL-запросы и бизнес-логика
  - `api/app/services/keyboards.py` — билдеры inline-клавиатур
- **MCP index.ts**: разбит с 1023 строк на 12 модулей в `mcp/src/tools/`
  - Каждый модуль экспортирует `register(apiRequest): ToolDef[]`
  - Общие типы вынесены в `mcp/src/types.ts`
- **utils.py**: вынесены `escape_html()` и `resolve_bot_context()` из дублирования в 8 роутерах
- Шаблоны: `prediction_public.j2`, `prediction_prompt.j2` для предсказаний
- При `WEBUI_ENABLED=true` предсказания используют `web_app` кнопки вместо `callback_data`

#### 📡 API
- Proxy роутер `api/app/routers/webui.py`: `/v1/web/*` → `tgweb/api/v1/*`
- Endpoints: CRUD страниц, индивидуальные ссылки, ответы форм

#### 🧩 MCP (+6 инструментов, теперь 57 всего)
- `webui.create_page` — создать страницу
- `webui.list_pages` — список страниц
- `webui.create_link` — индивидуальная ссылка
- `webui.get_submissions` — ответы формы
- `webui.create_prediction` — страница предсказания (shortcut)
- `webui.create_survey` — опросник (shortcut)

#### 📦 SDK (+6 методов)
- `create_web_page()`, `list_web_pages()`, `create_web_link()`
- `get_web_submissions()`, `create_prediction_page()`, `create_survey_page()`

#### 🗄️ База данных
- Миграция `db/init/10_web_ui.sql`
- Таблицы: `web_pages`, `web_page_links`, `web_form_submissions`, `web_wallet_links`

---

## [2026.02.11] - 2026-02-07

### Изменено

#### 🔀 MCP API base: tgapi + legacy compat fallback
- `mcp/src/config.ts`:
  - основной default API base переключен на `http://tgapi:8000`;
  - добавлена поддержка `TELEGRAM_API_BASE` как alias к `TELEGRAM_API_URL`;
  - добавлены служебные флаги `apiBaseExplicit`, `defaultApiBase`, `legacyApiBase`.
- `mcp/src/index.ts`:
  - добавлен сетевой compat fallback: если API base не задан явно и запрос к `tgapi` не прошёл,
    MCP делает retry на legacy `http://telegram-api:8000`;
  - добавлено warning-логирование `api.base.fallback_legacy`.

#### 📚 Документация
- `README.md` и `docs/mcp.md` синхронизированы:
  - `TELEGRAM_API_URL` / `TELEGRAM_API_BASE` описаны как каноничные переменные;
  - обновлены примеры путей/контейнеров (`tgmcp`, `tgapi`);
  - зафиксировано compat-window поведение fallback на legacy host.
- Добавлены governance-файлы публичного репозитория:
  - `SECURITY.md`, `CODE_OF_CONDUCT.md`;
  - `.github/ISSUE_TEMPLATE/*`, `.github/pull_request_template.md`, `.github/CODEOWNERS`.
- Добавлен pragmatic CI: `.github/workflows/ci.yml` (compose config, markdown links, Python compile, MCP TS build).


## [2026.02.10] - 2026-02-06

### Добавлено

#### 🧱 Стандартизация инфраструктуры
- `compose.yml` приведён к единой схеме имен:
  - сервисы/контейнеры: `tgdb`, `tgapi`, `tgmcp`.
- Добавлены системные labels для compose-сервисов:
  - `ns.module`, `ns.component`, `ns.db_owner`.
- Порты вынесены в канонические переменные:
  - `PORT_DB_TG`, `PORT_HTTP_TGAPI`, `PORT_MCP_TG`.
- Сохранена обратная совместимость через legacy fallback (`DB_PORT`, `API_PORT`, `MCP_HTTP_PORT`).

#### 📦 Образы
- В `api/Dockerfile` и `mcp/Dockerfile` добавлены OCI labels и `ns.module/ns.component`.

#### 📚 Документация
- `.env.example` и `README.md` синхронизированы с новыми именами контейнеров и портовым контрактом.

## [2026.02.9] - 2026-02-06

### Добавлено

#### 🔁 Updates/Polling в разрезе bot_id
- Миграция `db/init/08_updates_offset_per_bot.sql`.
- `update_offset` расширен полем `bot_id` и индексами уникальности для:
  - default context (`bot_id IS NULL`),
  - контекста конкретного бота (`bot_id=<id>`).
- Backfill/нормализация `update_offset` при миграции: удаление дубликатов по bot context.

#### 📡 API контракт для polling
- `GET /v1/updates/offset` поддерживает optional `bot_id`.
- `POST /v1/updates/ack` принимает `{offset, bot_id?}`.
- `GET /v1/updates/poll` при отсутствии `offset` берёт offset из bot context.
- В `api/app/models.py` добавлена модель `UpdatesAckIn`.

#### 🧩 SDK polling (мультибот)
- `TelegramAPI.start_polling(..., bot_id=None)`.
- `PollingManager.start(..., bot_id=None)` прокидывает `bot_id` в:
  - `/v1/updates/offset`,
  - `/v1/updates/poll`,
  - `/v1/updates/ack`.

#### ✅ Контрактная верификация
- Добавлены manifest-файлы покрытия:
  - `docs/testing/api_endpoints_manifest.json`
  - `docs/testing/mcp_tools_manifest.json`
  - `docs/testing/sdk_methods_manifest.json`
- Добавлены contract tests:
  - `tests/api/test_contract_endpoints.py`
  - `tests/api/test_updates_per_bot_offset.py`
  - `tests/sdk/test_client_contract.py`
  - `tests/sdk/test_polling_bot_id.py`
  - `tests/mcp/test_tool_to_endpoint_mapping.py`
- Добавлен единый запуск: `scripts/test_all.sh`.

#### 🧪 Smoke scripts
- Тестовые скрипты в `scripts/` расширены поддержкой `--bot-id` для мультибот-сценариев там, где это применимо.
- `scripts/test_updates.py` обновлён под `bot_id`-aware polling/ack.

## [2026.02.8] - 2026-02-06

### Добавлено

#### 🤖 Мультибот-архитектура
- Новый реестр ботов: таблица `bots` + API `GET/POST /v1/bots`, `GET /v1/bots/default`, `PUT /v1/bots/{bot_id}/default`, `DELETE /v1/bots/{bot_id}`
- Авто-регистрация ботов из `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BOT_TOKENS` при старте приложения
- Поддержка выбора бота через `bot_id` в ключевых send/webhook/chats/commands/stars/reactions/checklists endpoint'ах
- Контекстный выбор бота для webhook-обработки (`POST /telegram/webhook/{bot_id}`) без ломки обратной совместимости

#### 🗄️ База данных и хранение контекста
- Миграция `db/init/07_multi_bot_and_enrichment.sql`
- Новые таблицы:
  - `chat_members` — локальный кэш участников чатов
  - `api_activity_log` — аудит исходящих Telegram API вызовов
- Обогащение таблиц:
  - `chats`: `alias`, `is_default`, `description`, `member_count`, `bot_id`, `invite_link`, `is_forum`, `photo_file_id`
  - `users`: `alias`, `is_premium`, `last_seen_at`
  - `messages`, `webhook_updates`, `bot_commands`, `callback_queries`, `polls`, `checklists`, `prediction_events`, `webhook_config`: `bot_id`
- Индексы для быстрых выборок по `bot_id`, alias и activity log

#### 📡 Трассировка и логирование
- `telegram_client.py` переведён на bot-aware вызовы (`bot_token`/default/context override)
- Удалены отладочные `print`-выводы из send flow
- Добавлено структурное логирование Telegram вызовов (метод, бот, чат, статус, длительность)
- Неблокирующая запись активности в `api_activity_log` через background-task

#### 🧩 API, MCP и SDK
- Новые chat endpoint'ы:
  - `GET /v1/chats` (локальный список)
  - `PUT /v1/chats/{chat_id}/alias`
  - `GET /v1/chats/by-alias/{alias}`
  - `GET /v1/chats/{chat_id}/history`
  - `GET /v1/chats/{chat_id}/members` (из БД)
- MCP расширен инструментами:
  - `bots.list`, `bots.register`, `bots.default`
  - `chats.list`, `chats.alias`, `chats.history`
- MCP/SDK send-инструменты и методы дополнены `bot_id` для маршрутизации на конкретного бота
- SDK дополнен методами:
  - `list_bots()`, `register_bot()`, `get_default_bot()`, `set_default_bot()`
  - `list_chats()`, `set_chat_alias()`, `get_chat_by_alias()`, `get_chat_history()`

## [2026.02.7] - 2026-02-06

### Добавлено

#### 🎯 Prediction Markets (Polymarket-style Betting System)

**Основная функциональность:**
- Создание событий для ставок Stars с мультипликатором
- Размещение ставок через invoice (автоматическое списание Stars)
- Разрешение событий с выплатой выигрышей
- Обезличенные и публичные ставки
- Работа в каналах и личных чатах

**API Endpoints:**
- `POST /v1/predictions/events` — создание события
- `GET /v1/predictions/events` — список событий
- `GET /v1/predictions/events/{id}` — детали события
- `POST /v1/predictions/bets` — размещение ставки
- `POST /v1/predictions/events/{id}/resolve` — разрешение события
- `GET /v1/predictions/bets` — ставки пользователя

**Stars Payments (полная поддержка):**
- `POST /v1/stars/invoice` — создание счёта на оплату
- `POST /v1/stars/refund` — возврат платежа
- `GET /v1/stars/transactions` — история транзакций
- Функции: `send_invoice()`, `create_invoice_link()`, `answer_pre_checkout_query()`, `refund_star_payment()`, `get_star_transactions()`

**SDK методы:**
- `api.create_prediction_event()` — создание события
- `api.place_bet()` — размещение ставки
- `api.resolve_prediction_event()` — разрешение
- `api.list_prediction_events()`, `api.get_prediction_event()`, `api.list_user_bets()`
- `api.create_star_invoice()`, `api.refund_star_payment()`, `api.get_star_transactions()`

**MCP tools (+9 инструментов, теперь 40 всего):**
- `predictions.create_event`, `predictions.place_bet`, `predictions.resolve`, `predictions.list`, `predictions.get`, `predictions.user_bets`
- `stars.invoice`, `stars.refund`, `stars.transactions`

**LLM Integration для принятия решений:**
- Модуль `llm_resolver.py` с поддержкой llm-mcp, Ollama, OpenRouter
- Автоматическое разрешение событий через LLM
- Агрегация новостей через channel-mcp для событий без фиксированной даты
- Обработка граничных случаев (нет правильного ответа → полный возврат, между вариантами → распределение)

**База данных:**
- Таблицы: `star_transactions`, `prediction_events`, `prediction_options`, `prediction_bets`, `prediction_resolutions`, `prediction_llm_config`
- Миграция: `db/init/05_predictions_and_payments.sql`

**Jinja2 шаблон:**
- `templates/prediction_event.j2` — красивое отображение событий с коэффициентами

**Инфраструктура:**
- Новый роутер: `api/app/routers/predictions.py`
- Модуль LLM: `api/app/llm_resolver.py`
- Модели: `PredictionOption`, `CreatePredictionEventIn`, `PlaceBetIn`, `ResolveEventIn`, `SendInvoiceIn`, `RefundStarPaymentIn`, `LabeledPrice`

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
