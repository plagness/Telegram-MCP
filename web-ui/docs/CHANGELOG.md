# Changelog — Bee Web UI

## [2026.02.21] — 2026-02-16 — Фаза «Фундамент» + «FX + Документация»

### Новое

#### Тесты (test-fx.html)
- Самодостаточная HTML-страница с micro test runner (ноль зависимостей)
- 33 функциональных теста: countUp (7), revealText (6), initFadeIn (5), initRipple (4), initSpotlight (3), BeeKit.sheet (4), BeeKit.stale (4)
- 6 перформанс-бенчмарков с порогами: countUp×50, revealText×10, initFadeIn×100, Ripple×100, Skeleton×20, querySelectorAll×500
- Touch event simulation для тестирования мобильных эффектов
- Console + visual output, совместимость с Puppeteer/Playwright

#### UI Toolkit
- **bee-kit.js** — переиспользуемый UI toolkit:
  - `BeeKit.poll()` — data polling с skeleton crossfade, stale detection, auto-retry
  - `BeeKit.sheet` — bottom sheet с toolbar (фильтры, сортировка)
  - `BeeKit.stale` — stale data indicator banner
  - `BeeKit.initAccordions()` — auto-init для `[data-bee-accordion]`
  - `[data-haptic]` — автоматический haptic feedback

#### Визуальные эффекты (BeeFX — портировано из react-bits)
- **bee-fx.js** — vanilla JS порт эффектов из react-bits:
  - `BeeFX.countUp()` — анимация чисел (из CountUp.jsx)
  - `BeeFX.revealText()` — посимвольное раскрытие (из BlurText + SplitText)
  - `BeeFX.initFadeIn()` — каскадное появление с IntersectionObserver
  - `BeeFX.initSpotlight()` — подсветка за пальцем (из SpotlightCard.jsx)
  - `BeeFX.clickSpark()` — Canvas искры при тапе (из ClickSpark.jsx)
  - `BeeFX.initRipple()` — Material Design ripple feedback
- **CSS-эффекты** (из react-bits, портированы в чистый CSS):
  - `.bee-shiny` — shimmer на тексте (из ShinyText.jsx)
  - `.bee-gradient-text` — градиентный текст (из GradientText.jsx)
  - `.bee-star-border` — анимированная рамка (из StarBorder.jsx)
  - `.bee-glare` — блик при касании (из GlareHover)
  - `.bee-glitch` — glitch эффект для ошибок (из GlitchText.jsx)
  - `.bee-fade-in` — entry animations (из FadeContent + AnimatedList)
  - `.bee-ripple` — touch ripple container

#### Skeleton Loading
- Анимированные shimmer-плейсхолдеры вместо «Загрузка данных...»
- Skeleton matching layout для каждого дашборда
- Плавный crossfade skeleton → content (double rAF)
- Компоненты: `--title`, `--line`, `--value`, `--label`, `--chart`, `--avatar`

#### Apache ECharts 6.0.0
- Lazy-load через `{% block head_libs %}`
- SVG renderer (лучше для мобильных)
- Графики: costs bar chart (LLM), stock indices bar chart (Metrics)

#### Дашборды
- **LLM Dashboard** — job queue, costs bar chart, fleet hierarchy, running jobs, issues
  - `bee-shiny` на month cost, `countUp` на costs при первой загрузке
- **Metrics Dashboard** — FX & Crypto headlines, market data list, stock indices ECharts
  - `bee-shiny` на BTC цене, `countUp` на headlines при первой загрузке
  - Skeleton вместо «Загрузка данных...»
- **Arena Dashboard** — health, matches, leaderboard, species, predictions, presets (accordion)
  - Skeleton loading
- **Planner Dashboard** — speed mode, budget, tasks, modules, schedules, triggers, task log (sheet + chips)
  - `bee-star-border` на active triggers, `countUp` на budget
  - Skeleton loading
- **Infra Dashboard** — performance gauges, cluster overview, fleet (host→node hierarchy), jobs, costs
  - Skeleton loading + crossfade в showContent()

#### Hub
- **Mini-metrics** — live данные на карточках модулей (fetch `/hub/mini-metrics`)
- **bee-fade-in** — каскадное появление карточек при скролле

#### Документация
- **docs/UI-GUIDE.md** — полное руководство разработчика по Bee UI системе
- **docs/CHANGELOG.md** — лог изменений

### Изменено
- **infra.html** → BeeKit.sheet вместо inline infra-sheet
- **llm.html** → client-side fetch+render вместо server-side reload каждые 5с
- **metrics.html** → /v1/metrics/snapshot вместо /v1/metrics/latest
- **BeeKit.poll()** → crossfade вместо мгновенного display toggle
- **render.py** → убран server-side LLM fetch

### Архитектура
- `{% block head_libs %}` — ленивая загрузка тяжёлых библиотек (ECharts)
- `prefers-reduced-motion` — все анимации уважают accessibility
- Порядок скриптов: telegram-web-app.js → lottie → bee-glass.js → twa.js → bee-kit.js → bee-fx.js
- MutationObserver для динамически добавленных элементов (аккордеоны, fade-in)
