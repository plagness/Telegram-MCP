# Создание веб-страниц — Руководство для разработчика

Как добавить новую веб-страницу (Telegram Mini App) с нуля. Шаг за шагом.

---

## Быстрый старт (5 минут)

Чтобы добавить страницу нового типа, нужно **3 файла**:

1. **Handler** — `app/handlers/my_handler.py` (Python-класс)
2. **Шаблон** — `app/templates/mytype.html` (Jinja2)
3. **Запись в БД** — через API или SQL

Всё остальное (маршрутизация, template_map, access control) **работает автоматически**.

---

## Шаг 1: Создать Handler

Файл: `web-ui/app/handlers/my_handler.py`

### Простая страница (без серверных данных)

```python
from . import PageTypeHandler


class MyTypeHandler(PageTypeHandler):
    """Описание типа страницы."""

    page_type = "mytype"        # Уникальный идентификатор
    template = "mytype.html"    # Шаблон в app/templates/
```

Готово. Handler автоматически обнаруживается при старте приложения (auto-discovery).

### Страница с серверными данными (SSR)

```python
from typing import Any
from fastapi import Request
from . import PageTypeHandler


class MyTypeHandler(PageTypeHandler):
    page_type = "mytype"
    template = "mytype.html"

    async def load_data(
        self, page: dict, user: dict | None, request: Request
    ) -> dict[str, Any]:
        """Данные, доступные в шаблоне как {{ items }}, {{ total }} и т.д."""
        return {
            "items": ["a", "b", "c"],
            "total": 42,
        }
```

Метод `load_data()` вызывается после проверки доступа. Результат мержится в Jinja2 контекст шаблона.

### Страница с proxy-маршрутами (dashboard с live-обновлением)

```python
from typing import Any
from fastapi import APIRouter, Request
from ..config import get_settings
from . import PageTypeHandler, proxy_get, validate_page_request

settings = get_settings()


class MyTypeHandler(PageTypeHandler):
    page_type = "mytype"
    template = "mytype.html"
    scripts = ["echarts"]  # Подключить ECharts (если нужны графики)

    def register_routes(self, router: APIRouter) -> None:
        @router.get("/p/{slug}/mytype/data")
        async def mytype_data(slug: str, request: Request):
            """JSON endpoint для BeeKit.poll()."""
            await validate_page_request(slug, "mytype", request)
            return await proxy_get(f"{settings.my_service_url}/v1/data")
```

Маршрут `/p/{slug}/mytype/data` автоматически регистрируется при старте.

---

## Шаг 2: Создать шаблон

Файл: `web-ui/app/templates/mytype.html`

### Минимальный шаблон (SSR)

```html
{% extends "base.html" %}

{% block title %}{{ page.title }}{% endblock %}
{% block bar_left %}<a class="bee-bar__back" href="/">&#8249;</a>{% endblock %}

{% block context %}
<div class="bee-card bee-hex-bg">
    <div class="bee-title">{{ page.title }}</div>
    {% if config.get('description') %}
    <div class="bee-subtitle">{{ config['description'] }}</div>
    {% endif %}
</div>
{% endblock %}

{% block content %}
<div class="bee-card">
    <div class="bee-card-title">Контент</div>
    <!-- Здесь основное содержимое -->
</div>
{% endblock %}
```

### Dashboard шаблон (client-side fetch)

```html
{% extends "base.html" %}

{% block title %}{{ page.title }}{% endblock %}
{% block bar_left %}<a class="bee-bar__back" href="/">&#8249;</a>{% endblock %}

{% block head_libs %}
<script src="/static/echarts.min.js"></script>
{% endblock %}

{% block content %}
<div id="mod-loading">
    <div class="bee-card bee-skel-card">
        <div class="bee-skel bee-skel--title" style="width:40%"></div>
        <div class="bee-stat-grid">
            <div class="bee-stat">
                <div class="bee-skel bee-skel--value"></div>
                <div class="bee-skel bee-skel--label"></div>
            </div>
        </div>
    </div>
</div>
<div id="mod-error" class="bee-card" style="display:none">
    <div class="bee-card-title" style="color:var(--error)">Ошибка загрузки</div>
</div>
<div id="mod-content" style="display:none">
    <div class="bee-card">
        <div class="bee-stat-grid">
            <div class="bee-stat">
                <div class="bee-stat-value" id="s-total">-</div>
                <div class="bee-stat-label">total</div>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
(function() {
    var tg = window.Telegram && window.Telegram.WebApp;
    var initData = tg ? tg.initData : '';
    function $(id) { return document.getElementById(id); }

    BeeKit.poll('/p/{{ page.slug }}/mytype/data', 15000, {
        onData: function(data) {
            $('s-total').textContent = data.total || 0;
        },
        initData: initData,
        staleAfter: 3
    });
})();
</script>
{% endblock %}
```

---

## Шаг 3: Создать страницу в БД

### Через API (рекомендуется)

```bash
curl -X POST https://tg.example.com:8443/api/v1/pages \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "my-page",
    "title": "Моя страница",
    "page_type": "mytype",
    "config": {
        "description": "Описание для шапки"
    }
  }'
```

### Через SQL

```sql
INSERT INTO web_pages (slug, title, page_type, config, creator_id)
VALUES ('my-page', 'Моя страница', 'mytype', '{"description":"..."}', 123456789);
```

После создания страница доступна по `/p/my-page`.

---

## Шаг 4: Настроить доступ (опционально)

По умолчанию страница **публичная** (доступна всем). Чтобы ограничить:

```bash
# Доступ только по ролям
curl -X PUT https://tg.example.com:8443/api/v1/pages/my-page/access \
  -H "Content-Type: application/json" \
  -d '{"access_rules": {"allowed_roles": ["project_owner", "tester"]}}'

# Доступ участникам чата
curl -X POST https://tg.example.com:8443/api/v1/pages/my-page/access/grant \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "chat", "value": -1001455291970}'

# Доступ конкретному пользователю
curl -X POST https://tg.example.com:8443/api/v1/pages/my-page/access/grant \
  -H "Content-Type: application/json" \
  -d '{"grant_type": "user", "value": 123456789}'
```

Логика доступа — **OR**: достаточно выполнения хотя бы одного условия.

---

## Шаг 5: Deploy

```bash
cd /home/plag/NeuronSwarm/telegram-mcp

# Собрать образ
docker compose build tgweb

# Импортировать в K3s
sudo k3s ctr images rm docker.io/library/telegram-mcp-tgweb:latest 2>/dev/null
docker save telegram-mcp-tgweb:latest | sudo k3s ctr images import -

# Перезапустить pod
kubectl -n ns-telegram rollout restart deployment tgweb
```

Или через Makefile из корня NeuronSwarm:

```bash
make k8s-import   # Пересобрать и импортировать все образы
make k8s-prod-up  # Применить манифесты
```

---

## Проверка

```bash
# Тесты (handler обнаружен, шаблон существует)
cd web-ui && python -m pytest tests/ -v

# Health endpoint
curl -sk https://localhost:8443/health | python -m json.tool

# Страница рендерится
curl -sk -o /dev/null -w "%{http_code}" https://localhost:8443/p/my-page
# 200 — публичная, или 200 (base.html) для приватной
```

---

## Что уже настроено (не нужно трогать)

| Компонент | Статус | Описание |
|-----------|--------|----------|
| Auto-discovery handler'ов | Работает | Любой `PageTypeHandler` подкласс в `handlers/` обнаруживается автоматически |
| Маршрутизация `/p/{slug}` | Работает | render.py автоматически находит handler по `page_type` |
| template_map | Не нужен | Генерируется из registry, не надо нигде прописывать |
| Proxy-маршруты | Работают | `register_routes()` вызывается при старте для каждого handler'а |
| Access control | Работает | OR-логика: public / allowed_users / allowed_roles / allowed_chats |
| 3-tier layout | Работает | base.html: bar (sticky header) → banners → context → content |
| Health monitoring | Работает | Cron каждые 5 минут проверяет все страницы, пишет в `web_page_health` |
| Тесты | Работают | `make web-test` — 29 тестов (handler registry + access + smoke) |

---

## Архитектура: как это устроено

```
Запрос GET /p/{slug}
        │
        ▼
   render.py: render_page()
        │
        ├── Загрузить page из БД (по slug)
        ├── Проверить access (initData → user → check_page_access)
        ├── Найти handler: get_handler(page_type) → PageTypeHandler
        ├── Вызвать handler.load_data(page, user, request) → extra_data
        └── Рендер: templates.get_template(handler.template).render(page=page, **extra_data)
```

### Структура файлов

```
web-ui/app/
├── handlers/                    # <-- Сюда добавлять handler'ы
│   ├── __init__.py              # PageTypeHandler базовый класс + утилиты
│   ├── registry.py              # Auto-discovery + registration
│   ├── generic.py               # page, prediction, survey, dashboard, leaderboard
│   ├── calendar_handler.py      # calendar (CRUD proxy, enrichment)
│   ├── governance_handler.py    # governance (Democracy proxy, 8 endpoints)
│   ├── infra_handler.py         # llm, infra, metrics, k8s, datesale
│   └── module_handler.py        # channel, bcs, arena, planner
├── templates/                   # <-- Сюда добавлять шаблоны
│   ├── base.html                # Базовый layout (3-tier: bar → banners → content)
│   ├── page.html, prediction.html, calendar.html, ...
│   └── mytype.html              # Ваш новый шаблон
├── routers/
│   ├── render.py                # Тонкий диспетчер (hub, profile, /p/{slug})
│   ├── pages.py                 # REST API: CRUD страниц, access, types
│   ├── health.py                # /health + /api/v1/pages/health/*
│   ├── banners_api.py           # /api/v1/banners
│   ├── marketplace.py           # /marketplace, /developer
│   ├── admin.py                 # /admin/banners
│   └── module_proxy.py          # Legacy proxy (channel, bcs, arena, planner)
├── services/
│   ├── access.py                # check_page_access, grant/revoke, enrichment
│   ├── pages.py                 # CRUD операции с web_pages
│   ├── health.py                # Health check cron + alerts
│   ├── banner.py                # Промо-баннеры для hub
│   └── telegram.py              # resolve_tg_file_url()
├── static/
│   ├── style.css                # Bee Design System (~4000 строк)
│   ├── bee-kit.js               # BeeKit: poll, sheet, accordion, banner, stale
│   ├── bee-fx.js                # BeeFX: countUp, revealText, clickSpark
│   └── twa.js                   # Telegram WebApp init
└── config.py                    # Settings (env vars)
```

---

## API для управления страницами

### CRUD

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/pages` | Список страниц (?page_type=, ?bot_id=, ?limit=, ?offset=) |
| POST | `/api/v1/pages` | Создать страницу |
| GET | `/api/v1/pages/{slug}` | Получить одну страницу |
| DELETE | `/api/v1/pages/{slug}` | Деактивировать страницу |
| POST | `/api/v1/pages/validate` | Валидировать config без создания |

### Типы страниц (handler registry)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/pages/types` | Все зарегистрированные page_types |
| GET | `/api/v1/pages/types/{type}/schema` | JSON Schema конфига |

### Доступ

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/pages/{slug}/access` | Текущие правила + resolved users |
| PUT | `/api/v1/pages/{slug}/access` | Обновить access_rules целиком |
| POST | `/api/v1/pages/{slug}/access/grant` | Добавить правило (user/role/chat) |
| POST | `/api/v1/pages/{slug}/access/revoke` | Убрать правило |
| GET | `/api/v1/pages/user/{user_id}/accessible` | Страницы, доступные пользователю |

### Health

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/health` | Healthcheck сервиса |
| GET | `/api/v1/pages/health` | Сводка: healthy/errors/avg_time |
| GET | `/api/v1/pages/{slug}/health` | История проверок одной страницы |
| POST | `/api/v1/pages/health/check` | Запустить проверку всех страниц |

### Баннеры

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/v1/banners` | Список баннеров |
| POST | `/api/v1/banners` | Создать баннер |
| POST | `/api/v1/banners/{id}/toggle` | Вкл/выкл |
| DELETE | `/api/v1/banners/{id}` | Удалить |

---

## Зарегистрированные page_types (16 штук)

| page_type | Handler | Шаблон | Proxy | Описание |
|-----------|---------|--------|-------|----------|
| `page` | PageHandler | page.html | — | Статическая страница |
| `prediction` | PredictionHandler | prediction.html | — | Ставки/предсказания |
| `survey` | SurveyHandler | survey.html | — | Опросы/веб-формы |
| `dashboard` | DashboardHandler | dashboard.html | — | Произвольный дашборд |
| `leaderboard` | LeaderboardHandler | leaderboard.html | — | Рейтинг |
| `calendar` | CalendarHandler | calendar.html | 5 CRUD endpoints | Календарь событий |
| `governance` | GovernanceHandler | governance.html | 8 endpoints | Голосования (Democracy) |
| `llm` | LLMHandler | llm.html | 1 endpoint | LLM smart routing |
| `infra` | InfraHandler | infra.html | 1 endpoint | K8s + Ollama |
| `metrics` | MetricsHandler | metrics.html | — | Метрики |
| `k8s` | K8sHandler | k8s.html | — | Kubernetes дашборд |
| `datesale` | DatesaleHandler | datesale.html | — | Integrat маркетплейс |
| `channel` | ChannelHandler | channel.html | module_proxy | Channel MCP |
| `bcs` | BCSHandler | bcs.html | module_proxy | BCS MCP |
| `arena` | ArenaHandler | arena.html | module_proxy | Arena LLM |
| `planner` | PlannerHandler | planner.html | module_proxy | Planner |

---

## Утилиты handler'ов

Импорт из `app/handlers/__init__.py`:

```python
from . import (
    PageTypeHandler,           # Базовый класс
    validate_page_request,     # Валидация slug + page_type + initData + access
    proxy_get,                 # GET-прокси к сервису → JSONResponse
    proxy_post,                # POST-прокси к сервису → JSONResponse
    proxy_delete,              # DELETE-прокси к сервису → JSONResponse
)
```

### validate_page_request(slug, expected_type, request)

Проверяет:
- Страница существует и имеет правильный `page_type`
- `X-Init-Data` header валиден (если есть)
- Пользователь имеет доступ

Возвращает `(page, user)`. Бросает `HTTPException` при ошибках.

### proxy_get / proxy_post / proxy_delete

Универсальные прокси к внешним сервисам. Обрабатывают таймауты, ошибки соединения, возвращают `JSONResponse`.

---

## Доступ: как работает

Правила хранятся в `web_pages.config → access_rules`:

```json
{
  "access_rules": {
    "public": false,
    "allowed_users": [123456789],
    "allowed_roles": ["project_owner", "tester"],
    "allowed_chats": [-1001455291970]
  }
}
```

**Логика OR** — доступ если:
1. `public: true` — всем
2. `user_id` в `allowed_users`
3. Роль пользователя в `allowed_roles`
4. Пользователь — участник чата из `allowed_chats`
5. Нет `access_rules` вообще — публичная страница

Проверка членства в чате: сначала кэш в БД (`chat_members`), потом Telegram Bot API `getChatMember`.

---

## Page Manager (локальный дашборд)

```bash
cd web-ui && python -m manager.manager
# → http://localhost:8088
```

Или: `make web-manager` из корня NeuronSwarm.

Показывает:
- **Dashboard** — все страницы, статистика, handler'ы
- **Access** — матрица доступов (pages × users/roles/chats)
- **Types** — зарегистрированные handler'ы и JSON Schema

---

## Расширенная документация

| Документ | Путь | Описание |
|----------|------|----------|
| **UI Guide** | [docs/UI-GUIDE.md](docs/UI-GUIDE.md) | CSS Design System, BeeKit API, BeeFX, ECharts, skeleton loading |
| **Changelog** | [docs/CHANGELOG.md](docs/CHANGELOG.md) | История изменений |
| **DB Schema** | [../docs/schema.md](../docs/schema.md) | Структура БД (таблицы, индексы) |
| **API Commands** | [../docs/commands.md](../docs/commands.md) | Команды бота и API |

---

## Чеклист новой страницы

- [ ] Создать handler в `app/handlers/` (подкласс `PageTypeHandler`)
- [ ] Создать шаблон в `app/templates/` (extends `base.html`)
- [ ] Создать запись в БД через API (`POST /api/v1/pages`)
- [ ] Настроить доступ если нужно (`POST .../access/grant`)
- [ ] Запустить тесты: `make web-test` (handler обнаружен, шаблон существует)
- [ ] Собрать и задеплоить: `docker compose build tgweb` → K3s import → rollout
- [ ] Проверить: `curl https://localhost:8443/p/{slug}` → 200
