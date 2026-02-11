# Python SDK

Python-клиент для telegram-api (~95 методов, полная поддержка Bot API 9.4). Заменяет прямые вызовы Telegram Bot API через python-telegram-bot, httpx или urllib.

## Установка

```bash
# Из директории sdk/
pip install -e sdk/

# Или добавить в requirements.txt:
# telegram-api-client @ file:///path/to/telegram-api/sdk
```

Зависимости: `httpx>=0.25.0`, Python 3.10+.

## Быстрый старт

```python
from telegram_api_client import TelegramAPI

async with TelegramAPI("http://localhost:8081") as api:
    # Проверка здоровья
    health = await api.health()

    # Отправка сообщения
    msg = await api.send_message(chat_id=-100123456, text="Привет!")

    # Редактирование по внутреннему ID
    await api.edit_message(msg["id"], text="Обновлено!")

    # Удаление
    await api.delete_message(msg["id"])
```

## Справочник методов

### Сообщения

#### `send_message(chat_id, text, **kwargs) -> dict`

```python
msg = await api.send_message(
    chat_id=-100123456,
    text="<b>Заголовок</b>\nТекст",
    parse_mode="HTML",
    reply_to_message_id=42,
    reply_markup={"inline_keyboard": [[{"text": "OK", "callback_data": "ok"}]]},
    live=True,       # пометка live для прогресс-сообщений
    dry_run=False,   # True — не отправлять в Telegram
    request_id="abc" # внешний ID
)
# msg["id"] — внутренний ID для edit/delete
```

#### `edit_message(message_id, text, **kwargs) -> dict`

```python
await api.edit_message(msg["id"], text="Новый текст", parse_mode="HTML")
```

#### `delete_message(message_id) -> dict`

```python
await api.delete_message(msg["id"])
```

#### `get_message(message_id) -> dict`

```python
msg = await api.get_message(42)
```

#### `list_messages(chat_id, status, limit, offset) -> list[dict]`

```python
messages = await api.list_messages(chat_id="-100123456", status="sent", limit=10)
```

#### `forward_message(chat_id, from_chat_id, message_id) -> dict`

```python
await api.forward_message(chat_id=-100123456, from_chat_id=-100654321, message_id=42)
```

#### `copy_message(chat_id, from_chat_id, message_id, **kwargs) -> dict`

```python
await api.copy_message(
    chat_id=-100123456,
    from_chat_id=-100654321,
    message_id=42,
    caption="Новая подпись",
)
```

### Медиа

#### `send_photo(chat_id, photo, **kwargs) -> dict`

Поддерживает три типа `photo`:
- **str** — URL или file_id (отправка через JSON)
- **bytes** — загрузка файла (multipart)
- **BinaryIO** — файловый объект (multipart)

```python
# По URL
await api.send_photo(chat_id=-100123456, photo="https://example.com/img.jpg")

# Загрузка файла
with open("chart.png", "rb") as f:
    await api.send_photo(
        chat_id=-100123456,
        photo=f,
        caption="<b>График</b>",
        parse_mode="HTML",
        filename="chart.png",
    )

# Из bytes
png_data = generate_chart()
await api.send_photo(chat_id=-100123456, photo=png_data, filename="report.png")
```

#### `send_document(chat_id, document, **kwargs) -> dict`

```python
await api.send_document(
    chat_id=-100123456,
    document="https://example.com/report.pdf",
    caption="Отчёт",
)
```

### Опросы

#### `send_poll(chat_id, question, options, **kwargs) -> dict`

Создание опроса или викторины.

```python
# Обычный опрос
poll = await api.send_poll(
    chat_id=-100123456,
    question="Какие языки программирования вы используете?",
    options=["Python", "JavaScript", "Go", "Rust"],
    allows_multiple_answers=True,
    is_anonymous=True,
    open_period=300,  # 5 минут
)

# Викторина с правильным ответом
quiz = await api.send_poll(
    chat_id=-100123456,
    question="Какой язык был выпущен первым?",
    options=["Python", "Java", "C", "Fortran"],
    type="quiz",
    correct_option_id=3,  # Fortran
    explanation="<b>Fortran</b> был создан в 1957 году.",
    explanation_parse_mode="HTML",
    is_anonymous=False,
)

# poll["poll_id"] — ID опроса от Telegram
# poll["telegram_message_id"] — ID сообщения для stop_poll()
```

#### `stop_poll(chat_id, message_id) -> dict`

Остановка опроса с показом результатов.

```python
# Остановить опрос через 60 секунд
await asyncio.sleep(60)
results = await api.stop_poll(
    chat_id=-100123456,
    message_id=poll["telegram_message_id"]
)
print(f"Всего голосов: {results['total_voter_count']}")
```

#### `list_polls(chat_id, type, is_closed, limit, offset) -> list[dict]`

Список опросов с фильтрацией.

```python
polls = await api.list_polls(chat_id="-100123456", limit=10)
for p in polls:
    print(f"{p['question']} (type={p['type']}, closed={p['is_closed']})")
```

### Реакции

#### `set_reaction(chat_id, message_id, reaction, is_big) -> dict`

Установка эмодзи-реакции на сообщение.

```python
# Одна реакция
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=[{"type": "emoji", "emoji": "👍"}],
)

# Несколько реакций
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=[
        {"type": "emoji", "emoji": "🔥"},
        {"type": "emoji", "emoji": "❤️"},
    ],
)

# Большая анимация
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=[{"type": "emoji", "emoji": "👏"}],
    is_big=True,
)

# Удалить все реакции
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=None,
)
```

#### `list_reactions(chat_id, user_id, reaction_type, limit, offset) -> list[dict]`

Список реакций с фильтрацией.

```python
reactions = await api.list_reactions(chat_id="-100123456", limit=20)
```

### Прогресс-сообщения (ProgressContext)

Паттерн send → edit → delete для отображения прогресса длительных операций.

```python
async with api.progress(chat_id=-100123456) as p:
    await p.update(1, 5, "Загрузка данных...")
    # [1/5] Загрузка данных...
    # ▓▓░░░░░░░░

    await p.update(2, 5, "Обработка записей...")
    # [2/5] Обработка записей...
    # ▓▓▓▓░░░░░░

    await p.update(5, 5, "Готово!")
# При выходе из контекста — сообщение автоматически удаляется
```

С финальным сообщением (без удаления):
```python
async with api.progress(chat_id) as p:
    await p.update(1, 3, "Работаю...")
    await p.update(3, 3, "Завершено")
    await p.done(final_text="Отчёт сформирован за 42 секунды")
# Сообщение остаётся с финальным текстом
```

Параметры `ProgressContext`:
- `min_interval` (float, по умолчанию 0.8) — минимальный интервал между edit (throttle)
- `parse_mode` (str, по умолчанию `"HTML"`)

### Шаблоны

```python
# Список шаблонов
templates = await api.list_templates()

# Рендеринг (без отправки)
rendered = await api.render_template("report", {"title": "Отчёт", "date": "2025-01-01"})
# rendered["text"] — готовый текст

# Создание/обновление шаблона
await api.create_template(
    name="report",
    body="<b>{{ title }}</b>\nДата: {{ date }}",
    parse_mode="HTML",
    description="Шаблон отчёта",
)
```

### Команды бота

```python
# Глобальные команды
await api.set_commands([
    {"command": "start", "description": "Начать"},
    {"command": "help", "description": "Справка"},
])

# Per-user команды (расширенное меню для админа)
await api.set_commands(
    commands=[
        {"command": "start", "description": "Начать"},
        {"command": "help", "description": "Справка"},
        {"command": "cleanup", "description": "Очистка (админ)"},
        {"command": "report", "description": "Отчёт (админ)"},
    ],
    scope_type="chat_member",
    chat_id=-100123456,
    user_id=777,
)

# Синхронизация с Telegram
await api.sync_commands(command_set_id=1)

# Список наборов
sets = await api.list_command_sets()
```

### Callback Queries

```python
await api.answer_callback(
    callback_query_id="123456789",
    text="Принято!",
    show_alert=False,
)
```

### Чаты

```python
chat = await api.get_chat(chat_id="-100123456")
member = await api.get_chat_member(chat_id="-100123456", user_id=777)
```

### Вебхуки и обновления

```python
updates = await api.list_updates(limit=50, update_type="message", bot_id=123456789)

await api.set_webhook(url="https://example.com/telegram/webhook", bot_id=123456789)
info = await api.get_webhook_info(bot_id=123456789)
await api.delete_webhook(bot_id=123456789)
```

### CommandHandler polling (мультибот)

```python
@api.command("start", chat_id=-100123456)
async def start(update, args):
    await api.send_message(chat_id=update["message"]["chat"]["id"], text="pong", bot_id=123456789)

await api.start_polling(timeout=30, limit=100, bot_id=123456789)
```

### Мониторинг

```python
health = await api.health()       # {"status": "ok", ...}
metrics = await api.metrics()     # {"sent": 42, "error": 1, ...}
bot = await api.get_bot_info()    # {"username": "my_bot", ...}
```

### Web-UI

#### `create_web_page(title, page_type, slug, config, ...) -> dict`

Создание веб-страницы.

```python
page = await api.create_web_page(
    title="Обратная связь",
    page_type="survey",
    config={"fields": [
        {"name": "rating", "type": "select", "label": "Оценка", "options": ["1", "2", "3", "4", "5"]},
        {"name": "text", "type": "textarea", "label": "Комментарий"}
    ]}
)
```

#### `list_web_pages(page_type, is_active, limit, offset) -> list[dict]`

Список страниц.

```python
pages = await api.list_web_pages(page_type="survey", is_active=True)
```

#### `create_web_link(slug, user_id, chat_id, metadata, expires_at) -> dict`

Создание индивидуальной ссылки.

```python
link = await api.create_web_link("my-survey", user_id=777)
print(link["url"])  # https://tg.example.com:8090/l/a1b2c3d4...
```

#### `get_web_submissions(slug, limit, offset) -> list[dict]`

Ответы на форму.

```python
submissions = await api.get_web_submissions("my-survey")
for s in submissions:
    print(s["data"])
```

#### `create_prediction_page(event_id, slug, bot_id) -> dict`

Создание страницы предсказания (shortcut).

```python
page = await api.create_prediction_page(event_id=42)
```

#### `create_survey_page(title, fields, slug, bot_id) -> dict`

Создание опросника (shortcut).

```python
survey = await api.create_survey_page(
    title="Фидбэк",
    fields=[
        {"name": "q1", "type": "text", "label": "Как вас зовут?"},
        {"name": "q2", "type": "textarea", "label": "Отзыв"}
    ]
)
```

### Bot API 9.x — новые методы

#### Боты и профиль (Bot API 9.4)

```python
# Список ботов
bots = await api.list_bots(include_inactive=False)

# Регистрация нового бота
bot = await api.register_bot(token="123456:ABC-DEF", is_default=True)

# Бот по умолчанию
default = await api.get_default_bot()
await api.set_default_bot(bot_id=123)

# Фото профиля бота
await api.set_my_profile_photo(photo={"type": "static", "sticker": "..."}, is_public=True)
await api.remove_my_profile_photo()

# Аудио профиля пользователя (Bot API 9.4)
audios = await api.get_user_profile_audios(user_id=987654321)

# Star-подписки
await api.edit_user_star_subscription(
    user_id=777,
    telegram_payment_charge_id="...",
    is_canceled=True,
)
```

#### Форум-топики (Bot API 9.3)

```python
# Создание топика
topic = await api.create_forum_topic(
    chat_id=-100123456,
    name="Обсуждение",
    icon_color=7322096,
)

# Управление топиками
await api.edit_forum_topic(chat_id=-100123456, message_thread_id=42, name="Новое имя")
await api.close_forum_topic(chat_id=-100123456, message_thread_id=42)
await api.reopen_forum_topic(chat_id=-100123456, message_thread_id=42)
await api.delete_forum_topic(chat_id=-100123456, message_thread_id=42)
await api.hide_general_forum_topic(chat_id=-100123456)
await api.unhide_general_forum_topic(chat_id=-100123456)
```

#### Истории (Bot API 9.0–9.3)

```python
# Публикация истории
await api.post_story(chat_id=-100123456, content={"type": "photo", "photo": "..."})

# Редактирование / удаление
await api.edit_story(chat_id=-100123456, story_id=42, content={"type": "photo", "photo": "..."})
await api.delete_story(chat_id=-100123456, story_id=42)

# Репост (Bot API 9.3)
await api.repost_story(chat_id=-100123456, from_chat_id=-100654321, story_id=42)
```

#### Предложенные посты (Bot API 9.2)

```python
# Одобрить / отклонить
await api.approve_suggested_post(
    business_connection_id="abc123",
    message_id=42,
    is_scheduled=False,
)
await api.decline_suggested_post(
    business_connection_id="abc123",
    message_id=42,
)
```

#### Чек-листы (Bot API 9.1)

```python
# Отправка чек-листа
await api.send_checklist(
    chat_id=-100123456,
    title="Задачи",
    tasks=[
        {"id": 1, "text": "Первая задача"},
        {"id": 2, "text": "Вторая задача", "checked": True},
    ],
)

# Редактирование
await api.edit_checklist(message_id=42, title="Обновлённый список", tasks=[...])
```

#### Звёзды и подарки (Bot API 9.1–9.3)

```python
# Баланс звёзд
balance = await api.get_star_balance()

# Подарок премиум-подписки
await api.gift_premium(user_id=777, month_count=3, star_count=1000)

# Подарки пользователя / чата
gifts = await api.get_user_gifts(user_id=777)
chat_gifts = await api.get_chat_gifts(chat_id=-100123456)
```

#### Черновики (Bot API 9.3)

```python
await api.send_message_draft(
    business_connection_id="abc123",
    chat_id=123456789,
    text="Текст черновика",
)
```

#### Cross-cutting параметры (Bot API 9.2)

Все send-методы поддерживают новые kwargs:

```python
# direct_messages_topic_id — маршрутизация в топик
await api.send_message(
    chat_id=-100123456,
    text="Сообщение в топик",
    direct_messages_topic_id=42,
)

# suggested_post_parameters — параметры предложенного поста
await api.send_photo(
    chat_id=-100123456,
    photo="https://example.com/img.jpg",
    suggested_post_parameters={"send_date": 1234567890},
)
```

## Обработка ошибок

```python
from telegram_api_client import TelegramAPI, TelegramAPIError

try:
    await api.send_message(chat_id=123, text="Test")
except TelegramAPIError as e:
    print(f"Ошибка: {e}")
    print(f"HTTP-код: {e.status_code}")
    print(f"Детали: {e.detail}")
```

## Миграция с python-telegram-bot

| python-telegram-bot | SDK |
|---------------------|-----|
| `bot.send_message(chat_id, text)` | `await api.send_message(chat_id, text)` |
| `bot.send_photo(chat_id, photo=f)` | `await api.send_photo(chat_id, photo=f)` |
| `bot.edit_message_text(text, chat_id, msg_id)` | `await api.edit_message(internal_id, text=text)` |
| `bot.delete_message(chat_id, msg_id)` | `await api.delete_message(internal_id)` |
| `update.message.reply_text(text)` | `await api.send_message(chat_id, text, reply_to_message_id=msg_id)` |
| `ProgressNotifier(bot, chat_id)` | `async with api.progress(chat_id) as p:` |

Отличие: SDK оперирует **внутренними ID** из telegram-api, а не telegram_message_id. Это обеспечивает единообразный доступ ко всем операциям через хранилище.
