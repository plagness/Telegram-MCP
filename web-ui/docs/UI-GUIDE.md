# Bee UI — Руководство разработчика

Полное руководство по UI-системе Telegram Mini App. Покрывает архитектуру, CSS-систему, компоненты BeeKit и BeeFX, паттерны backend-proxy, и пошаговое создание новых страниц.

---

## 1. Архитектура

### Стек

| Слой | Технология | Описание |
|------|------------|----------|
| Backend | FastAPI (Python) | Роутеры, рендеринг, proxy к модулям |
| Шаблоны | Jinja2 | SSR HTML с блочным наследованием |
| JS | Vanilla ES5 | Без React, без npm, без bundler |
| CSS | Custom Design System | CSS переменные + Telegram theme |
| Графики | Apache ECharts 6.0 | SVG renderer, lazy-load |
| Эффекты | BeeFX | Портировано из react-bits в vanilla JS |

### Файловая структура

```
web-ui/
├── app/
│   ├── templates/          # Jinja2 шаблоны
│   │   ├── base.html       # Базовый layout (наследуется всеми)
│   │   ├── hub.html         # Главная: карточки модулей (SSR)
│   │   ├── llm.html         # LLM Dashboard (client-side fetch)
│   │   ├── metrics.html     # Market Data Dashboard
│   │   ├── arena.html       # Arena LLM Dashboard
│   │   ├── planner.html     # Planner Dashboard
│   │   ├── infra.html       # Infrastructure Dashboard
│   │   └── ...              # prediction, calendar, survey, etc.
│   ├── static/
│   │   ├── style.css        # Bee Design System (~3900 строк)
│   │   ├── bee-kit.js       # UI toolkit: poll, sheet, accordion, stale
│   │   ├── bee-fx.js        # Визуальные эффекты (из react-bits)
│   │   ├── bee-glass.js     # Liquid glass morphism для sticky bar
│   │   ├── twa.js           # Telegram WebApp init + haptic
│   │   ├── echarts.min.js   # Apache ECharts 6.0.0 (lazy-load)
│   │   └── icons/           # SVG-иконки (brand logos)
│   └── routers/
│       ├── render.py        # Рендеринг шаблонов по page_type
│       └── module_proxy.py  # Proxy-запросы к backend модулям
├── docs/
│   ├── UI-GUIDE.md          # ← Вы здесь
│   └── CHANGELOG.md
└── Dockerfile
```

### Порядок загрузки скриптов

```
1. telegram-web-app.js     — Telegram WebApp SDK (CDN)
2. style.css               — Bee Design System
3. [ECharts — lazy, только если {% block head_libs %} подключает]
4. lottie-player            — Загрузочная анимация (CDN)
5. bee-glass.js             — Liquid glass morphism
6. twa.js                   — Telegram init, haptic, theme, expand
7. bee-kit.js               — BeeKit: poll, sheet, accordion, stale
8. bee-fx.js                — BeeFX: countUp, fadeIn, ripple, spotlight
9. {% block scripts %}      — Скрипт конкретной страницы (inline)
```

### Два типа рендеринга

| Тип | Пример | Данные | Обновление |
|-----|--------|--------|------------|
| **SSR** | hub.html | Jinja2 контекст (render.py) | Перезагрузка страницы |
| **Client-side** | llm.html, metrics.html | BeeKit.poll() → fetch JSON | Авто-обновление каждые N секунд |

---

## 2. Quick Start: Создание новой страницы

### Минимальная страница (SSR)

```html
{% extends "base.html" %}

{% block title %}Моя страница{% endblock %}
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
    <div class="bee-card-title">Hello World</div>
    <div class="bee-list">
        <div class="bee-list-item">
            <div class="bee-list-icon">&#128640;</div>
            <div class="bee-list-content">
                <div class="bee-list-title">Элемент</div>
                <div class="bee-list-subtitle">Описание элемента</div>
            </div>
            <div class="bee-list-right">
                <span class="bee-badge">ok</span>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

### Dashboard страница (client-side fetch)

```html
{% extends "base.html" %}

{% block title %}{{ page.title }}{% endblock %}
{% block bar_left %}<a class="bee-bar__back" href="/">&#8249;</a>{% endblock %}

{# Подключить ECharts если нужны графики #}
{% block head_libs %}
<script src="/static/echarts.min.js"></script>
{% endblock %}

{% block context %}
<div class="bee-card bee-hex-bg">
    <div class="bee-title">{{ page.title }}</div>
</div>
{% endblock %}

{% block content %}
{# 1. Skeleton loading — повторяет layout контента #}
<div id="mod-loading">
    <div class="bee-card bee-skel-card">
        <div class="bee-skel bee-skel--title" style="width:40%"></div>
        <div class="bee-stat-grid">
            <div class="bee-stat">
                <div class="bee-skel bee-skel--value"></div>
                <div class="bee-skel bee-skel--label"></div>
            </div>
            <div class="bee-stat">
                <div class="bee-skel bee-skel--value"></div>
                <div class="bee-skel bee-skel--label"></div>
            </div>
        </div>
    </div>
</div>

{# 2. Ошибка (скрыто) #}
<div id="mod-error" class="bee-card" style="display:none">
    <div class="bee-card-title" style="color:var(--error)">Ошибка загрузки</div>
    <div class="bee-subtitle" id="mod-error-text"></div>
</div>

{# 3. Контент (скрыто до загрузки) #}
<div id="mod-content" style="display:none">
    <div class="bee-card">
        <div class="bee-card-title">Overview</div>
        <div class="bee-stat-grid">
            <div class="bee-stat">
                <div class="bee-stat-value" id="s-total">-</div>
                <div class="bee-stat-label">total</div>
            </div>
            <div class="bee-stat">
                <div class="bee-stat-value" style="color:var(--success)" id="s-active">-</div>
                <div class="bee-stat-label">active</div>
            </div>
        </div>
    </div>
</div>

<div style="text-align:center;padding:8px;opacity:0.5;font-size:12px" id="updated-at"></div>
{% endblock %}

{% block scripts %}
<script>
(function() {
    var tg = window.Telegram && window.Telegram.WebApp;
    var initData = tg ? tg.initData : '';
    var SLUG = '{{ page.slug }}';

    function $(id) { return document.getElementById(id); }

    function render(data) {
        $('s-total').textContent = data.total || 0;
        $('s-active').textContent = data.active || 0;
        $('updated-at').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    }

    // BeeKit.poll: skeleton → crossfade → content
    BeeKit.poll('/p/' + SLUG + '/mymodule/data', 15000, {
        onData: render,
        onAccessDenied: function() {
            $('mod-loading').style.display = 'none';
            $('mod-error').style.display = '';
            $('mod-error-text').textContent = 'Доступ ограничен';
        },
        initData: initData,
        staleAfter: 3
    });
})();
</script>
{% endblock %}
```

### Чеклист добавления нового дашборда

1. **pages.py** — зарегистрировать `page_type="mymodule"`
2. **module_proxy.py** — добавить `_fetch_mymodule_data()` + endpoint `GET /p/{slug}/mymodule/data`
3. **templates/mymodule.html** — создать шаблон (skeleton + BeeKit.poll + render)
4. **render.py** — добавить в `template_map`: `'mymodule': 'mymodule.html'`
5. **Docker build → K3s deploy** — пересобрать и задеплоить

---

## 3. CSS Design System

### Переменные

#### Telegram Theme (автоматически из WebApp)

```css
--tg-bg           /* Основной фон */
--tg-text         /* Цвет текста */
--tg-hint         /* Подсказки, вторичный текст */
--tg-link         /* Ссылки */
--tg-button       /* Кнопки */
--tg-button-text  /* Текст кнопок */
--tg-secondary-bg /* Фон карточек, вторичных элементов */
```

#### Brand / Bee Design

```css
--accent: #FFC107      /* Основной акцент (янтарный) */
--success: #4CAF50     /* Успех, online, ok */
--error: #F44336       /* Ошибка, offline, fail */
--warning: #FF9800     /* Предупреждение */
--radius: 14px         /* Скругление карточек */
--bar-h: 48px          /* Высота sticky bar */
--card-pad: 16px       /* Padding карточек */
```

### Компоненты

#### Cards

```html
<div class="bee-card">
    <div class="bee-card-title">Заголовок</div>
    <div class="bee-card-subtitle">Подзаголовок</div>
    <!-- контент -->
</div>

<!-- Карточка с hex-фоном (для шапки) -->
<div class="bee-card bee-hex-bg">
    <div class="bee-title">Большой заголовок</div>
    <div class="bee-subtitle">Описание</div>
</div>
```

#### Lists

```html
<div class="bee-list">
    <div class="bee-list-item">
        <div class="bee-list-icon" style="color:var(--success)">&#9679;</div>
        <div class="bee-list-content">
            <div class="bee-list-title">Название</div>
            <div class="bee-list-subtitle">Описание · метаданные</div>
        </div>
        <div class="bee-list-right">
            <span class="bee-badge">ok</span>
        </div>
    </div>
</div>
```

#### Stat Grid

```html
<!-- 4 колонки (по умолчанию) -->
<div class="bee-stat-grid">
    <div class="bee-stat">
        <div class="bee-stat-value" style="color:var(--accent)">42</div>
        <div class="bee-stat-label">total</div>
    </div>
    <!-- ... -->
</div>

<!-- 3 колонки -->
<div class="bee-stat-grid bee-stat-grid--three">
    <!-- ... -->
</div>
```

#### Badges

```html
<span class="bee-badge">active</span>                    <!-- Заполненный (accent) -->
<span class="bee-badge bee-badge--outline">inactive</span> <!-- Контурный -->
```

#### Progress Bar

```html
<div class="bee-progress bee-progress--lg">
    <div class="bee-progress-fill" id="my-progress" style="width:65%"></div>
</div>
```

#### Tables

```html
<table class="bee-table">
    <thead><tr><th>#</th><th>Name</th><th>Value</th></tr></thead>
    <tbody>
        <tr><td>1</td><td>Item</td><td class="value">123</td></tr>
    </tbody>
</table>
```

#### Chips (фильтры)

```html
<div class="bee-chip active" data-val="all">Все</div>
<div class="bee-chip" data-val="active">Активные</div>
```

### Skeleton Loading

Skeleton — анимированные плейсхолдеры, повторяющие layout контента. Показываются пока данные загружаются, затем crossfade к реальному контенту.

```html
<div id="mod-loading">
    <div class="bee-card bee-skel-card">
        <!-- Заголовок карточки -->
        <div class="bee-skel bee-skel--title" style="width:40%"></div>

        <!-- Stat grid -->
        <div class="bee-stat-grid">
            <div class="bee-stat">
                <div class="bee-skel bee-skel--value"></div>
                <div class="bee-skel bee-skel--label"></div>
            </div>
        </div>

        <!-- Chart placeholder -->
        <div class="bee-skel bee-skel--chart"></div>

        <!-- Text lines -->
        <div class="bee-skel bee-skel--line" style="width:60%"></div>
        <div class="bee-skel bee-skel--line-sm"></div>

        <!-- Avatar + text (list item) -->
        <div style="display:flex;align-items:center;gap:12px;padding:8px 0">
            <div class="bee-skel bee-skel--avatar"></div>
            <div style="flex:1">
                <div class="bee-skel bee-skel--line" style="width:50%"></div>
                <div class="bee-skel bee-skel--line-sm"></div>
            </div>
        </div>
    </div>
</div>
```

**Доступные размеры:**

| Класс | Размер | Назначение |
|-------|--------|------------|
| `bee-skel--title` | 18px × 45% | Заголовок карточки |
| `bee-skel--line` | 13px × 100% | Строка текста |
| `bee-skel--line-sm` | 13px × 70% | Короткая строка |
| `bee-skel--value` | 28px × 60px | Значение в stat-grid |
| `bee-skel--label` | 11px × 40px | Подпись в stat-grid |
| `bee-skel--chart` | 180px × 100% | График-плейсхолдер |
| `bee-skel--avatar` | 36px круг | Аватар/иконка |

**Стаггер:** второй `bee-skel-card` получает `animation-delay: 80ms`, третий — `160ms`.

---

## 4. BeeKit API (bee-kit.js)

Переиспользуемый UI toolkit. Подключается автоматически через base.html.

### BeeKit.poll(url, intervalMs, opts)

Основной механизм загрузки и обновления данных на дашбордах.

```javascript
BeeKit.poll('/p/' + SLUG + '/llm/data', 5000, {
    onData: function(data) { /* рендер */ },
    onAccessDenied: function(status) { /* 401/403 */ },
    onError: function(status) { /* другие ошибки */ },
    initData: tg.initData,  // Telegram auth
    staleAfter: 3            // кол-во fail до stale-banner
});
```

**Lifecycle:**
1. Показывает `#mod-loading` (skeleton)
2. Первый fetch → при успехе crossfade: skeleton fade-out (0.2s) → content fade-in (0.3s)
3. Вызывает `onData(json)` с полученными данными
4. Повторяет fetch каждые `intervalMs` мс
5. После `staleAfter` неудачных запросов подряд показывает stale-banner

**Важно:** Crossfade использует double `requestAnimationFrame` для гарантии что браузер разделит `display:''` и `opacity:1` в разные paint cycles.

### BeeKit.sheet.open(title, bodyHtml, toolbarHtml?)

Bottom sheet для детальной информации.

```javascript
// Простой sheet
BeeKit.sheet.open('Details', '<div>Content here</div>');

// Sheet с toolbar (фильтры/сортировка)
var toolbar = '<div class="bee-chip active" data-filter="">All</div>' +
              '<div class="bee-chip" data-filter="active">Active</div>';
BeeKit.sheet.open('Models', modelsHtml, toolbar);

// Закрыть
BeeKit.sheet.close();
```

### BeeKit.stale.show(msg?) / .hide()

Баннер "данные могут быть устаревшими". Вставляется после sticky bar.

```javascript
BeeKit.stale.show('Нет связи с сервером');
BeeKit.stale.hide();
```

### BeeKit.initAccordions()

Автоинициализация аккордеонов. Вызывается автоматически при DOMContentLoaded и через MutationObserver при динамическом добавлении.

```html
<div data-bee-accordion>
    <div class="bee-accordion__header">
        Заголовок
        <span class="bee-accordion__arrow">&#9656;</span>
    </div>
    <div class="bee-accordion__body">
        Скрытый контент
    </div>
</div>
```

### Auto-Haptic

Автоматический haptic feedback при клике на элементы с `data-haptic`:

```html
<button data-haptic="impact">Нажми</button>
<div data-haptic="selection">Выбери</div>
```

---

## 5. BeeFX API (bee-fx.js)

Визуальные эффекты портированные из [react-bits](https://github.com/DavidHDev/react-bits) в vanilla JS/CSS. Подключается автоматически через base.html.

### JS Functions

#### BeeFX.countUp(el, from, to, opts)

Анимированный счётчик с easeOut easing. Портировано из react-bits `CountUp.jsx`.

```javascript
// Простое использование
BeeFX.countUp(document.getElementById('total'), 0, 42);

// С опциями
BeeFX.countUp(el, 0, 1234.56, {
    duration: 1500,   // мс (default: 1500)
    decimals: 2,      // дробные знаки (default: 0)
    prefix: '$',      // префикс (default: '')
    suffix: ' pods',  // суффикс (default: '')
    separator: ' '    // разделитель тысяч (default: ' ')
});
```

- Запускается только когда элемент видим (IntersectionObserver)
- Easing: `t * (2 - t)` (ease-out quad)
- **Паттерн для дашбордов:** использовать только при первой загрузке, затем обычный textContent:

```javascript
var _fxDone = false;
function render(data) {
    if (!_fxDone) {
        _fxDone = true;
        BeeFX.countUp($('cost'), 0, data.cost, {prefix: '$', decimals: 4});
    } else {
        $('cost').textContent = '$' + data.cost.toFixed(4);
    }
}
```

#### BeeFX.revealText(el, opts)

Посимвольное раскрытие текста. Портировано из react-bits `BlurText.jsx` + `SplitText.jsx`.

```javascript
BeeFX.revealText(document.querySelector('.bee-title'), {
    mode: 'blur',   // 'blur' (BlurText) | 'slide' (SplitText)
    by: 'char',     // 'char' | 'word'
    delay: 40,      // мс между символами (default: 40)
    once: true      // анимировать только первый раз (default: true)
});
```

#### BeeFX.clickSpark(container, opts)

Искры при тапе (Canvas API). Портировано из react-bits `ClickSpark.jsx`.

```javascript
BeeFX.clickSpark(document.getElementById('my-card'), {
    count: 8,       // количество лучей (default: 8)
    size: 10,       // начальная длина (default: 10)
    radius: 15,     // радиус разлёта (default: 15)
    duration: 400,  // мс (default: 400)
    color: '#FFC107' // цвет (default: var(--accent))
});
```

#### BeeFX.initFadeIn()

Автоинициализация IntersectionObserver для `.bee-fade-in` элементов. Вызывается автоматически.

```html
<!-- Базовый fade-in снизу -->
<div class="bee-fade-in">Контент</div>

<!-- Fade-in с блюром -->
<div class="bee-fade-in bee-fade-in--blur">Контент</div>

<!-- Fade-in с масштабом -->
<div class="bee-fade-in bee-fade-in--scale">Контент</div>

<!-- Кастомная задержка -->
<div class="bee-fade-in" data-fade-delay="200">Контент</div>
```

**Авто-стаггер:** если `.bee-fade-in` элементы — соседи (siblings), каждый следующий получает +50ms задержку автоматически. Не нужно вручную расставлять data-fade-delay.

#### BeeFX.initSpotlight()

Подсветка за пальцем на touch-устройствах. Портировано из react-bits `SpotlightCard.jsx`.

```html
<!-- Добавить data-spotlight к любому элементу -->
<div class="bee-card" data-spotlight>
    Карточка с подсветкой при касании
</div>
```

#### BeeFX.initRipple()

Material Design ripple эффект при касании.

```html
<!-- По CSS-классу -->
<a class="bee-hub-card bee-ripple" href="/page">Card</a>

<!-- По data-атрибуту -->
<button data-ripple>Кнопка</button>
```

### CSS Classes

Чистые CSS-эффекты без JS. Просто добавьте класс.

#### .bee-shiny — Shimmer текста

Портировано из react-bits `ShinyText.jsx`. Блеск проходит по тексту.

```html
<div class="bee-stat-value bee-shiny" id="btc-price">$97,000</div>
```

**Важно:** Эффект работает за счёт контраста `currentColor` → accent highlight. Если текст уже окрашен в `var(--accent)`, shimmer не будет виден (одинаковые цвета).

#### .bee-gradient-text — Градиентный текст

Портировано из react-bits `GradientText.jsx`.

```html
<div class="bee-title bee-gradient-text">Bee Hub</div>
```

#### .bee-star-border — Анимированная рамка

Портировано из react-bits `StarBorder.jsx`. Два gradient-блоба двигаются по рамке элемента.

```html
<div class="bee-list-item bee-star-border">
    Выделенный элемент (hot prediction, active trigger)
</div>
```

#### .bee-glare — Блик при касании

```html
<div class="bee-card bee-glare">
    Карточка с бликом при нажатии
</div>
```

#### .bee-glitch[data-text] — Глитч-эффект

Портировано из react-bits `GlitchText.jsx`. Для текста ошибок/предупреждений.

```html
<span class="bee-glitch" data-text="Connection lost">Connection lost</span>
```

### Accessibility

Все анимации уважают `prefers-reduced-motion`:

```css
@media (prefers-reduced-motion: reduce) {
    /* Все анимации отключаются */
    .bee-fade-in, .bee-char { opacity: 1; transform: none; transition: none; }
    .bee-shiny, .bee-gradient-text { animation: none; }
    .bee-star-border::before, ::after { animation: none; }
    .bee-skel { animation: none; }
    .bee-ripple__wave { animation: none; }
}
```

---

## 6. ECharts Patterns

### Подключение (lazy-load)

```html
{% block head_libs %}
<script src="/static/echarts.min.js"></script>
{% endblock %}
```

ECharts загружается только на страницах, которые используют графики. Не влияет на вес других страниц.

### Инициализация

```javascript
var myChart = null;

function renderChart(data) {
    if (!myChart) {
        var dom = document.getElementById('my-chart');
        if (!dom || typeof echarts === 'undefined') return;
        myChart = echarts.init(dom, null, {renderer: 'svg'});
        window.addEventListener('resize', function() { if (myChart) myChart.resize(); });
    }

    var tgHint = getComputedStyle(document.body).getPropertyValue('--tg-hint').trim() || '#999';

    myChart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: 8, right: 8, top: 8, bottom: 24, containLabel: true },
        xAxis: {
            type: 'category',
            data: data.labels,
            axisLabel: { color: tgHint, fontSize: 10 },
            axisLine: { show: false },
            axisTick: { show: false }
        },
        yAxis: { type: 'value', show: false },
        series: [{
            type: 'bar',
            data: data.values,
            itemStyle: { color: '#FFC107', borderRadius: [3, 3, 0, 0] },
            barMaxWidth: 28,
            label: { show: true, position: 'top', fontSize: 9, color: tgHint }
        }]
    });
}
```

### HTML контейнер

```html
<div class="bee-echart" id="my-chart" style="min-height:260px"></div>
```

Класс `bee-echart` задаёт `width:100%; min-height:200px`.

---

## 7. Backend: Module Proxy Pattern

### Структура endpoint'а

```python
# module_proxy.py

async def _fetch_mymodule_data(base_url: str) -> dict:
    """Агрегация данных из backend-модуля."""
    health, items = await asyncio.gather(
        _http_get(f"{base_url}/v1/health", timeout=5),
        _call_mcp_tool(base_url, "list_items", {}),
        return_exceptions=True,
    )
    return {
        "health": health if not isinstance(health, Exception) else {"status": "error"},
        "items": items if not isinstance(items, Exception) else [],
    }

@router.get("/p/{slug}/mymodule/data")
async def mymodule_data(slug: str, request: Request):
    """JSON endpoint для BeeKit.poll()."""
    page = _get_page(slug)
    if not page:
        raise HTTPException(404)

    # Проверка доступа (owner-only)
    if not await _check_owner_access(request):
        raise HTTPException(403)

    config = page.get("config", {})
    base_url = config.get("api_url", "http://mymodule-service:8080")
    data = await _fetch_mymodule_data(base_url)
    return JSONResponse(data)
```

### Утилиты

```python
async def _http_get(url: str, timeout: int = 10) -> dict:
    """GET запрос с таймаутом. Возвращает JSON или пустой dict."""

async def _call_mcp_tool(base_url: str, tool: str, args: dict) -> Any:
    """Вызов MCP tool через HTTP."""
```

### Проверка доступа

```python
async def _check_owner_access(request: Request) -> bool:
    """Проверяет X-Init-Data header — owner-only доступ."""
```

---

## 8. Пошаговый пример: новый дашборд «Monitoring»

### 1. Регистрация page_type

В `pages.py` (или через API):
```python
page_type = "monitoring"
```

### 2. Backend proxy

В `module_proxy.py`:

```python
async def _fetch_monitoring_data(base_url: str) -> dict:
    health, metrics, alerts = await asyncio.gather(
        _http_get(f"{base_url}/v1/health"),
        _http_get(f"{base_url}/v1/metrics"),
        _http_get(f"{base_url}/v1/alerts"),
        return_exceptions=True,
    )
    return {
        "health": health if not isinstance(health, Exception) else {},
        "metrics": metrics if not isinstance(metrics, Exception) else {},
        "alerts": alerts if not isinstance(alerts, Exception) else [],
    }

@router.get("/p/{slug}/monitoring/data")
async def monitoring_data(slug: str, request: Request):
    page = _get_page(slug)
    if not page:
        raise HTTPException(404)
    if not await _check_owner_access(request):
        raise HTTPException(403)
    config = page.get("config", {})
    base_url = config.get("api_url", "http://monitoring-service:8080")
    return JSONResponse(await _fetch_monitoring_data(base_url))
```

### 3. Шаблон

Создать `templates/monitoring.html` по шаблону из раздела 2 (Quick Start: Dashboard).

### 4. Render mapping

В `render.py`:
```python
template_map = {
    # ...existing...
    'monitoring': 'monitoring.html',
}
```

### 5. Deploy

```bash
cd /home/plag/NeuronSwarm/telegram-mcp/web-ui
docker build -t telegram-mcp-tgweb:latest .
sudo k3s ctr images rm docker.io/library/telegram-mcp-tgweb:latest 2>/dev/null
docker save telegram-mcp-tgweb:latest | sudo k3s ctr images import -
kubectl -n ns-telegram rollout restart deployment tgweb
```

---

## 9. Краткая шпаргалка

### Часто используемые CSS-классы

| Класс | Что делает |
|-------|------------|
| `.bee-card` | Карточка с padding и background |
| `.bee-card-title` | Заголовок внутри карточки |
| `.bee-stat-grid` | Grid для метрик (4 колонки) |
| `.bee-stat-grid--three` | Grid для метрик (3 колонки) |
| `.bee-list` | Контейнер для списка |
| `.bee-list-item` | Элемент списка (flex) |
| `.bee-badge` | Бейдж (filled) |
| `.bee-badge--outline` | Бейдж (outline) |
| `.bee-table` | Стилизованная таблица |
| `.bee-chip` | Фильтр-чип |
| `.bee-progress` | Progress bar |
| `.bee-hex-bg` | Hex-паттерн фон |
| `.bee-skel` | Skeleton shimmer |
| `.bee-shiny` | Shimmer на тексте |
| `.bee-gradient-text` | Градиентный текст |
| `.bee-star-border` | Анимированная рамка |
| `.bee-fade-in` | Fade-in при скролле |
| `.bee-ripple` | Material ripple |
| `[data-spotlight]` | Spotlight за пальцем |
| `[data-haptic]` | Auto-haptic feedback |
| `[data-bee-accordion]` | Аккордеон |

### BeeKit API

| Метод | Описание |
|-------|----------|
| `BeeKit.poll(url, ms, opts)` | Polling с skeleton crossfade |
| `BeeKit.sheet.open(title, body, toolbar?)` | Открыть bottom sheet |
| `BeeKit.sheet.close()` | Закрыть bottom sheet |
| `BeeKit.stale.show(msg?)` | Показать stale-banner |
| `BeeKit.stale.hide()` | Скрыть stale-banner |
| `BeeKit.initAccordions()` | Переинициализировать аккордеоны |

### BeeFX API

| Метод | Описание |
|-------|----------|
| `BeeFX.countUp(el, from, to, opts)` | Анимация числа |
| `BeeFX.revealText(el, opts)` | Посимвольное раскрытие |
| `BeeFX.clickSpark(container, opts)` | Искры при тапе |
| `BeeFX.initFadeIn()` | Init IntersectionObserver для .bee-fade-in |
| `BeeFX.initSpotlight()` | Init touch tracking для [data-spotlight] |
| `BeeFX.initRipple()` | Init Material ripple |
