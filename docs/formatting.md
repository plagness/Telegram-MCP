# Форматирование сообщений Telegram

Telegram Bot API поддерживает три режима форматирования: `HTML`, `MarkdownV2` и устаревший `Markdown`.

## HTML (рекомендуется)

```python
await api.send_message(
    chat_id=-100123456,
    text="<b>Жирный</b> и <i>курсив</i>",
    parse_mode="HTML",
)
```

### Поддерживаемые теги

| Тег | Результат |
|-----|-----------|
| `<b>текст</b>` | **Жирный** |
| `<strong>текст</strong>` | **Жирный** |
| `<i>текст</i>` | *Курсив* |
| `<em>текст</em>` | *Курсив* |
| `<u>текст</u>` | Подчёркнутый |
| `<ins>текст</ins>` | Подчёркнутый |
| `<s>текст</s>` | ~~Зачёркнутый~~ |
| `<strike>текст</strike>` | ~~Зачёркнутый~~ |
| `<del>текст</del>` | ~~Зачёркнутый~~ |
| `<tg-spoiler>текст</tg-spoiler>` | Спойлер |
| `<code>код</code>` | `Моноширинный` |
| `<pre>блок кода</pre>` | Блок кода |
| `<pre><code class="language-python">...</code></pre>` | Код с подсветкой |
| `<a href="https://example.com">текст</a>` | Ссылка |
| `<tg-emoji emoji-id="ID">emoji</tg-emoji>` | Кастомный эмодзи |
| `<blockquote>цитата</blockquote>` | Цитата |

### Экранирование в HTML

Необходимо экранировать внутри текстовых узлов:
- `<` → `&lt;`
- `>` → `&gt;`
- `&` → `&amp;`

```html
<b>Итого:</b> 5 &lt; 10 &amp; 10 &gt; 3
```

## MarkdownV2

```python
await api.send_message(
    chat_id=-100123456,
    text="*Жирный* и _курсив_",
    parse_mode="MarkdownV2",
)
```

### Синтаксис

| Разметка | Результат |
|----------|-----------|
| `*жирный*` | **Жирный** |
| `_курсив_` | *Курсив* |
| `__подчёркнутый__` | Подчёркнутый |
| `~зачёркнутый~` | ~~Зачёркнутый~~ |
| `\|\|спойлер\|\|` | Спойлер |
| `` `код` `` | `Моноширинный` |
| ```` ```python\nкод\n``` ```` | Блок кода |
| `[текст](https://example.com)` | Ссылка |
| `>цитата` | Цитата (в начале строки) |

### Экранирование в MarkdownV2

Все спецсимволы вне разметки нужно экранировать обратным слэшем `\`:

```
_ * [ ] ( ) ~ ` > # + - = | { } . !
```

Пример:
```
*Итого:* 5 \> 3 \& всё ОК\!
```

## Лимиты

| Тип | Лимит |
|-----|-------|
| Текст сообщения (`sendMessage`) | 1–4096 символов |
| Подпись медиа (`caption`) | 0–1024 символов |
| Текст кнопки (`callback_data`) | 1–64 байт |
| Текст callback-ответа | 0–200 символов |

## Inline-кнопки (Reply Markup)

### InlineKeyboardMarkup

```json
{
  "reply_markup": {
    "inline_keyboard": [
      [
        {"text": "Кнопка 1", "callback_data": "btn_1"},
        {"text": "Кнопка 2", "callback_data": "btn_2"}
      ],
      [
        {"text": "Ссылка", "url": "https://example.com"}
      ]
    ]
  }
}
```

Типы кнопок:
- `callback_data` — нажатие генерирует callback_query
- `url` — открывает URL
- `switch_inline_query` — переключает в inline-режим

### ReplyKeyboardMarkup

```json
{
  "reply_markup": {
    "keyboard": [
      [{"text": "Вариант A"}, {"text": "Вариант B"}],
      [{"text": "Отмена"}]
    ],
    "resize_keyboard": true,
    "one_time_keyboard": true
  }
}
```

### ReplyKeyboardRemove

```json
{
  "reply_markup": {
    "remove_keyboard": true
  }
}
```

## Примеры шаблонов

### Отчёт с таблицей (HTML)

```html
<b>{{ title }}</b>

{% for item in items %}
{{ loop.index }}. {{ item.name }} — <code>{{ item.value }}</code>
{% endfor %}

<i>Обновлено: {{ time }}</i>
```

### Прогресс-бар (HTML)

```html
<b>[{{ stage }}/{{ total }}]</b> {{ description }}
{{ bar }}
```

## Рекомендации

1. Используйте `HTML` — проще экранирование, надёжнее парсинг
2. Не забывайте `parse_mode` — без него теги отобразятся как текст
3. Для длинных сообщений разбивайте на части по 4096 символов
4. Для подписей медиа — лимит 1024 символов
5. Проверяйте через `dry_run=true` перед отправкой в продакшн
