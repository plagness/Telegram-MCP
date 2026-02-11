# Simple Icons — Система иконок

Система иконок на базе [Simple Icons](https://simpleicons.org/) (3300+ брендовых SVG-иконок).
Позволяет автоматически резолвить произвольные имена (claude, btc, telegram) в SVG-иконки
с официальными брендовыми цветами.

## Архитектура

```
npm simple-icons ──► extract-icons.js ──► app/static/icons/*.svg   (3393 файла)
                                      └─► app/simple_icons_index.json (slug→hex)
                                              │
                                              ▼
                                         icons.py (Python-резолвер)
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                   Jinja2 шаблоны      API /api/icons/*    render.py (аватарки, виджеты)
```

## Быстрый старт

### Использование в Python

```python
from app.icons import resolve_icon, adjusted_color, get_display_name

# Резолв имени → иконка
icon = resolve_icon("claude")
# {"slug": "claude", "hex": "D97757", "color": "#D97757", "icon_url": "/static/icons/claude.svg"}

icon = resolve_icon("btc")
# {"slug": "bitcoin", "hex": "F7931A", "color": "#F7931A", "icon_url": "/static/icons/bitcoin.svg"}

icon = resolve_icon("claude-opus-4-6")  # keyword matching
# {"slug": "claude", ...}

icon = resolve_icon("несуществующее")
# None

# Коррекция тёмных цветов для UI
adjusted_color("191919")  # Anthropic → осветлённый
adjusted_color("F7931A")  # Bitcoin → без изменений

# Человекочитаемое имя
get_display_name("claude-opus-4-6")  # "Claude"
```

### Использование в HTML/Jinja2

```html
<!-- Аватарка: белая иконка на цветном фоне -->
<div class="bee-cal-event-ava" style="background:#D97757">
    <img src="/static/icons/claude.svg" alt="" width="14" height="14" loading="lazy"
         onerror="this.style.display='none';this.nextElementSibling.style.display=''">
    <span style="display:none">🤖</span>
</div>
```

CSS для белой иконки:
```css
.bee-cal-event-ava img {
    filter: brightness(0) invert(1);
}
```

### Использование через API

```bash
# Резолв имени
curl https://tg.example.com:8443/api/icons/resolve?name=claude
# {"found":true,"slug":"claude","hex":"D97757","icon_url":"/static/icons/claude.svg",...}

# Редирект на SVG (для <img src>)
curl -L https://tg.example.com:8443/api/icons/redirect?name=btc
# → 302 → /static/icons/bitcoin.svg

# Статистика
curl https://tg.example.com:8443/api/icons/info
# {"total_icons":3393,"aliases":{"claude":"claude","btc":"bitcoin",...}}
```

### Прямой доступ к SVG

```
/static/icons/{slug}.svg
```

Примеры:
- `/static/icons/claude.svg`
- `/static/icons/bitcoin.svg`
- `/static/icons/telegram.svg`
- `/static/icons/ethereum.svg`

SVG-файлы используют `fill="currentColor"` — цвет наследуется от CSS.

## Алгоритм резолва

`resolve_icon(name)` работает в 3 шага:

1. **Точное совпадение алиаса** — `"btc"` → `"bitcoin"`, `"claude"` → `"claude"`
2. **Keyword matching** — `"claude-opus-4-6"` содержит `"claude"` → `"claude"`
3. **Прямой slug** — `"fastapi"` → проверяем в индексе → найден

Если ни один шаг не дал результат → `None` (emoji fallback).

## Алиасы

Зарегистрированные алиасы (наши доменные термины → Simple Icons slug):

| Термин | Slug | Категория |
|--------|------|-----------|
| `claude`, `claude-3`, `claude-4` | `claude` | AI |
| `gpt`, `gpt-4`, `chatgpt`, `openai` | `openai` | AI |
| `gemini`, `gemini-pro` | `googlegemini` | AI |
| `llama`, `llama3` | `meta` | AI |
| `ollama` | `ollama` | AI |
| `mistral` | `mistralai` | AI |
| `deepseek` | `deepseek` | AI |
| `perplexity` | `perplexity` | AI |
| `copilot` | `githubcopilot` | AI |
| `huggingface`, `hf` | `huggingface` | AI |
| `btc`, `bitcoin`, `биткоин` | `bitcoin` | Крипта |
| `eth`, `ethereum`, `эфир` | `ethereum` | Крипта |
| `sol`, `solana` | `solana` | Крипта |
| `usdt`, `tether` | `tether` | Крипта |
| `tg`, `телеграм`, `telegram` | `telegram` | Платформы |
| `yt`, `ютуб`, `youtube` | `youtube` | Платформы |
| `gh`, `github` | `github` | Платформы |

Полный список: `GET /api/icons/info`.

## Обновление иконок

При выходе новой версии Simple Icons:

```bash
cd web-ui/scripts

# Через Docker (рекомендуется, Node.js не нужен на хосте):
docker run --rm \
  -v "$(pwd):/scripts" \
  -v "$(pwd)/../app:/app" \
  -w /scripts node:22-slim \
  sh -c "npm install && node extract-icons.js"

# Или локально (нужен Node.js 18+):
npm install
npm run extract
```

Результат:
- `app/simple_icons_index.json` — обновлённый индекс (66 KB)
- `app/static/icons/*.svg` — обновлённые SVG-файлы (3393 файла, ~15 MB)

После обновления — пересобрать Docker-образ.

## Файлы

| Путь | Описание |
|------|----------|
| `web-ui/app/icons.py` | Python-резолвер (ядро системы) |
| `web-ui/app/routers/icons.py` | API эндпоинты `/api/icons/*` |
| `web-ui/app/simple_icons_index.json` | Индекс slug→hex (генерируется) |
| `web-ui/app/static/icons/` | SVG-файлы (генерируются) |
| `web-ui/scripts/extract-icons.js` | Скрипт извлечения |
| `web-ui/scripts/package.json` | npm-зависимости |
| `mcp/src/tools/icons.ts` | MCP-инструмент `icons.resolve` |

## Коррекция цветов

`adjusted_color(hex)` осветляет слишком тёмные брендовые цвета для видимости в UI:

| Бренд | Оригинал | Скорректированный |
|-------|----------|-------------------|
| Anthropic | `#191919` | `#747474` |
| Ollama | `#000000` | `#666666` |
| GitHub | `#181717` | `#747373` |
| Bitcoin | `#F7931A` | без изменений |
| Claude | `#D97757` | без изменений |

Порог: luminance < 80 (по ITU-R BT.601). Осветление: 40% к белому.

## Использование через MCP

MCP-инструмент `icons.resolve` позволяет LLM проверить доступность иконки перед использованием:

```
icons.resolve({name: "bitcoin"})
→ {found: true, slug: "bitcoin", hex: "F7931A", icon_url: "/static/icons/bitcoin.svg", ...}

icons.resolve({name: "несуществующее"})
→ {found: false, name: "несуществующее", ...}
```

### Поле `icon` в записях календаря

Записи календаря поддерживают поле `icon` — Simple Icons slug. SVG-иконка отображается в заголовке записи (приоритет над emoji):

```
calendar.create_entry({
  calendar_id: 1,
  title: "Мониторинг BTC",
  icon: "bitcoin",          // SVG-иконка в заголовке
  emoji: "₿",               // fallback если icon не резолвится
  start_at: "2026-02-09T12:00:00Z",
  ...
})
```

Поле `icon` доступно в: `calendar.create_entry`, `calendar.update_entry`, `calendar.create_trigger`, `calendar.create_monitor`, `calendar.bulk_create`.

### Кастомные виджеты

Виджеты с иконками можно задавать через `metadata.widgets`:

```json
{
  "metadata": {
    "widgets": [
      {"label": "ETH", "value": "$3,500", "icon": "ethereum"},
      {"label": "SOL", "value": "$180", "icon": "solana", "change": 5.2}
    ]
  }
}
```

### Использование через SDK

```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://localhost:8081")
entry = await api.create_calendar_entry(
    calendar_id=1,
    title="Мониторинг Bitcoin",
    start_at="2026-02-09T12:00:00Z",
    icon="bitcoin",
    emoji="₿",
)
```

## Интеграция в Calendar v4

| Компонент | Иконки | Fallback |
|-----------|--------|----------|
| Entry icon (поле `icon`) | `/static/icons/{slug}.svg` (цветной фон) | emoji / entry_type icon |
| AI аватарки (Claude, Gemini...) | `/static/icons/{slug}.svg` (белая) | emoji 🤖 |
| Participant аватарки | `/static/icons/{slug}.svg` (белая) | emoji |
| BTC виджет | `/static/icons/bitcoin.svg` | emoji ₿ |
| Кастомные виджеты (`metadata.widgets`) | `/static/icons/{icon}.svg` | emoji |
| Тикеры (BCS) | `/static/icons/{ticker}.svg` | emoji 📈 |
| USD/RUB, ставка ЦБ | — | emoji 💱 🏦 |
