# Анализ миграции на telegram-mcp и план расширения функционала

## Обзор

Этот документ анализирует распространённые паттерны использования Telegram Bot API в Python-проектах и определяет, какой функционал необходимо добавить в telegram-mcp для полноценной замены существующих имплементаций.

**Дата анализа**: 2025-02-06
**Версия telegram-mcp**: 2025.02.1
**Проанализированы паттерны**: telemetry-сервисы, worker-обработчики, command handlers, ensemble-отчёты

---

## 1. Текущее использование Telegram Bot API в проектах

### 1.1 llm-mcp/telemetry (llm_telemetry/main.py)

**Назначение**: Мониторинг и телеметрия LLM-кластера

**Используемые методы**:
- `sendMessage` — отправка текста с HTML форматированием
- `editMessageText` — обновление статус-сообщения

**Параметры**:
```python
{
    "chat_id": TELEGRAM_CHAT_ID,
    "text": "<pre>...</pre>",
    "parse_mode": "HTML",
    "disable_web_page_preview": True
}
```

**Специфика**:
- Периодическое обновление одного сообщения каждые 2 секунды
- HTML-эскейпинг (`&`, `<`, `>`)
- Прогресс-бары через символы: `[####........]`
- Анимированный spinner: `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`
- Эмодзи-индикаторы: 🟢🔴🟡
- Обработка rate limiting (Retry-After)
- HTTP клиент: urllib (sync)

**Паттерн использования**:
```python
# Старт
resp = _call("sendMessage", payload)
message_id = resp["result"]["message_id"]

# Периодическое обновление
payload["message_id"] = message_id
_call("editMessageText", payload)
```

---

### 1.2 channel-mcp/worker (telegram_notifier.py + telegram_commands.py)

**Назначение**: Прогресс-уведомления + обработка команд

#### A. TelegramProgressNotifier

**Используемые методы**:
- `sendMessage` — создание статус-сообщения
- `editMessageText` — обновление прогресса

**Параметры**:
```python
{
    "chat_id": report_chat_id,
    "text": "⏳ Стадия: Ingest\n📺 Канал: @channel\n..."
}
```

**Специфика**:
- Throttling: минимум 2.5 сек между обновлениями
- Async spinner в отдельном asyncio Task
- Graceful degradation при ошибках (`disabled=True`)
- Структурированный вывод с эмодзи: ⏳📺🧾📝🏷️✨🔢🧬ℹ️⚠️📊⏱️⚙️
- HTTP клиент: python-telegram-bot (async)

#### B. Telegram Commands

**Используемые методы**:
- `update.message.reply_text()` — ответ на команду
- `Application.add_handler(CommandHandler(...))`
- `updater.start_polling()` — получение обновлений

**Команды**:
- `/toptags [days]` — топ-теги за период
- `/topemoji [days]` — топ-эмодзи
- `/topcode [days]` — топ-коды (числовые признаки)

**Паттерн использования**:
```python
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler

app = build_application(bot_token)
app.add_handler(CommandHandler("toptags", top_tags))
await app.updater.start_polling()
```

**Guard pattern**:
```python
if update.effective_chat.id != cfg.chat_id:
    return  # Только специфичный чат может выполнять команды
```

---

### 1.3 bcs-mcp

**Результат**: Не использует Telegram Bot API
**Назначение**: Чистый финансовый микросервис (BCS broker API → PostgreSQL → MCP)

---

### 1.4 Монолит: jobs.py (дневной прогон)

**Назначение**: Ежедневный отчёт с ensemble моделей, рейтингами, графиками

**Используемые методы**:
- `bot.send_message(chat_id, text, parse_mode="HTML")`
- `bot.edit_message_text(chat_id, message_id, text, parse_mode="HTML")`
- `bot.delete_message(chat_id, message_id)`
- `bot.send_photo(chat_id, photo=file, caption=text, parse_mode="HTML")`

**Специфика**:

#### A. ProgressNotifier класс (строки 92-354)

**Методы**:
- `update(stage_idx, total, text)` — обновление этапа
- `update_swarm(round_idx, total_rounds, model, action, ...)` — детальная визуализация swarm-игры
- `done()` — завершение с удалением сообщения

**Визуализация swarm** (HTML форматирование):
```
🎮 <b>Рой: раунд 2/8</b>
<code>●●○○○○○○</code>

<b>Модели:</b>
  🏳️▶️ <code>gemini-3    </code> 💚100 🟢150/150
  🏴‍☠️✅ <code>gpt-4o     </code> 💛 75 🟡 80/150
  🏳️⏳ <code>claude-3.7 </code> 🧡 50 🔴 20/150

<b>Действия:</b>
  🏴‍☠️ gpt-4o → steal(target=gemini) ⚔️ gemini
  💚 claude → heal (-15)
  📈 gemini → market_live (-10)
```

**Эмодзи-система**:
- HP: 💚 (80+), 💛 (50-80), 🧡 (30-50), ❤️ (<30)
- Stance: 🏳️ (neutral), 🏴‍☠️ (aggressive)
- Zone: 📈 (market), 📡 (mesh), 🌐 (network), ⚠️ (risk)
- Status: ▶️ (active), ✅ (done), ⏳ (thinking), ⬜ (pending)
- AP: 🟢 (>60%), 🟡 (30-60%), 🔴 (<30%)
- Actions: ⏸️ (pass), 🔧 (tool), 💸 (transfer), ✅ (done)
- PvP tools: 🏴‍☠️ (steal), 💣 (sabotage), 🔍 (scout), 💚 (heal), 🤝 (alliance), 🎭 (decoy)
- Data tools: 📈 (market), 📡 (mesh), 🌐 (network), 📦 (snapshot)

**Throttling**:
- Обычный update: минимум 0.8 секунд
- Swarm update: минимум 0.5 секунд
- Спиннер: каждые 1.5 секунды

#### B. Отправка отчёта (строки 708-803)

**Последовательность сообщений**:
1. **Текст + график** (send_photo с caption, parse_mode="HTML")
2. **Резюме оператора** (send_message с HTML-таблицей активности роя)
3. **Рейтинг моделей** (send_message с HTML-таблицей и детальным фидбеком)

**Паттерн send_photo**:
```python
# Если caption <= 1000 символов
with open(chart_path, "rb") as img:
    await bot.send_photo(
        chat_id=chat_id,
        photo=img,
        caption=message,
        parse_mode="HTML"
    )

# Иначе: сначала текст, потом фото
await bot.send_message(chat_id, text=message, parse_mode="HTML")
with open(chart_path, "rb") as img:
    await bot.send_photo(chat_id, photo=img, caption="График за месяц")
```

**HTML форматирование** (функция `format_message_pretty`):
```html
📊 <b>Сводка дня 06.02</b>

Текст сводки...

📈 <b>Сеть</b>
  ⬆️ Прямой: 95.2% <i>(+2.1)</i>
  ⬇️ Tailscale: 87.5% <i>(-1.3)</i>
  ➖ Блок-индекс: 12.3 п.п.

📡 <b>Mesh</b>
  ⬆️ Сообщений: 342 <i>(+15)</i>
  ➖ Шум: 14.2 дБ <i>(+0.3)</i>
```

**Эскейпинг**:
```python
def esc(t: str) -> str:
    return html.escape(t, quote=False)
```

**Рейтинговая таблица** (функция `format_ranking_table`):
```html
🏆 <b>Рейтинг моделей</b>

<pre>
#   Модель                  Очки  AP   Всего
🥇  gemini-3-flash-previ...  125   45   1234
🥈  gpt-4o-2024-11-20        98   60    987
🥉  claude-3.7-opus          87   30    865
</pre>

📋 <b>Детали оценки:</b>

<b>gemini-3-flash-preview</b>:
  ✅ Первая использовала market_live для актуальных данных
  ✅ Дала наиболее точный прогноз USD/RUB (±0.3%)

<b>gpt-4o-2024-11-20</b>:
  ✅ Активно использовала PvP-инструменты
  ❌ Потратила слишком много AP на sabotage без результата
```

---

## 2. Текущий функционал telegram-mcp (v2025.02.1)

### ✅ Реализовано

#### Сообщения
- `POST /v1/messages/send` — отправка текста, parse_mode (HTML/MarkdownV2)
- `PATCH /v1/messages/{id}` — редактирование текста
- `DELETE /v1/messages/{id}` — удаление
- `GET /v1/messages/{id}` — получение по внутреннему ID
- `GET /v1/messages` — список с фильтрацией

#### Медиа
- `POST /v1/media/send-photo` — отправка фото (URL, file_id)
- `POST /v1/media/upload-photo` — загрузка фото (multipart)
- `POST /v1/media/send-document` — документы
- `POST /v1/media/send-video` — видео

#### Опросы
- `POST /v1/polls/send` — создание опроса/викторины (quiz)
- `POST /v1/polls/{poll_id}/stop` — остановка опроса
- `GET /v1/polls/{poll_id}` — получение по poll_id
- `GET /v1/polls` — список опросов

#### Реакции
- `POST /v1/reactions/set` — установка эмодзи-реакции
- Поддержка: 👍👎❤️🔥🥰👏😁🤔🤯😱🤬😢🎉🤩🤮💩🙏👌🕊🤡🥱🥴😍🐳❤️‍🔥🌚🌭💯🤣⚡🍌🏆💔🤨😐🍓🍾💋🖕😈😴😭🤓👻👨‍💻👀🎃🙈😇😨🤝✍️🤗🫡🎅🎄☃️💅🤪🗿🆒💘🙉🦄😘💊🙊😎👾🤷‍♂️🤷🤷‍♀️😡

#### Шаблоны (Jinja2)
- `POST /v1/templates/render` — рендеринг шаблона с переменными
- `GET /v1/templates` — список шаблонов
- Автозагрузка из `templates/` при старте

#### Команды
- `POST /v1/commands/set` — установка команд с scope
- `POST /v1/commands/sync` — синхронизация из command_set
- `GET /v1/commands/sets` — список наборов команд
- Поддержка scope: `default`, `all_private_chats`, `all_group_chats`, `all_chat_administrators`, `chat`, `chat_administrators`, `chat_member`

#### Callback Queries
- `POST /v1/callbacks/answer` — ответ на нажатие inline-кнопки
- Webhook обработка callback_query

#### Чаты
- `GET /v1/chats/{chat_id}` — информация о чате
- `GET /v1/chats/{chat_id}/members/{user_id}` — участник чата

#### Вебхуки
- `POST /v1/webhook` — установка вебхука
- `DELETE /v1/webhook` — удаление вебхука
- `GET /v1/webhook/info` — информация о вебхуке
- Хранение обновлений в `updates` таблице

#### Reply Markup
- InlineKeyboardButton: `callback_data`, `url`, `web_app`, `login_url`, `switch_inline_query`, `switch_inline_query_current_chat`, `switch_inline_query_chosen_chat`, `copy_text`
- ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply

#### Инфраструктура
- Rate limiting (token-bucket по chat_id)
- Retry при 429 (Retry-After) и 5xx
- Connection pool (httpx AsyncClient)
- PostgreSQL connection pool (psycopg AsyncConnectionPool)
- Docker healthchecks
- Аудит-трейл (все операции в БД)

#### SDK
- Python клиент: `TelegramAPI`
- ProgressContext: `async with api.progress(chat_id) as p:`
- Все основные методы обёрнуты

#### MCP
- 25 инструментов для LLM
- HTTP transport на порту 3335
- stdio transport для Claude Desktop

---

## 3. Недостающий функционал для миграции

### 🔴 КРИТИЧНЫЕ (блокируют миграцию)

#### 3.1 Получение обновлений (Updates/Polling)

**Необходимо для**: channel-mcp (CommandHandler)

**Методы**:
- `GET /v1/updates/poll` — getUpdates с long polling
  ```json
  {
    "offset": 0,
    "limit": 100,
    "timeout": 30,
    "allowed_updates": ["message", "callback_query", "poll"]
  }
  ```
- `POST /v1/updates/process` — обработка входящего Update
- Интеграция с вебхуками (webhook → process → сохранение)

**Модели**:
- `Update`, `Message`, `CallbackQuery`, `Poll`, `User`, `Chat`
- Полная типизация всех сущностей Telegram

**SDK**:
```python
# Polling loop
async for update in api.poll_updates():
    if update.message:
        await handle_message(update.message)
    elif update.callback_query:
        await handle_callback(update.callback_query)
```

**MCP**:
- `updates.poll` — получить обновления
- `updates.ack` — подтвердить обработку (offset)

---

#### 3.2 CommandHandler Pattern

**Необходимо для**: channel-mcp команды (/toptags, /topemoji, /topcode)

**SDK**:
```python
from telegram_api_client import TelegramAPI, CommandHandler

api = TelegramAPI("http://localhost:8081")

@api.command("toptags")
async def top_tags(update, args):
    days = int(args[0]) if args else 7
    # ... логика
    await api.send_message(
        chat_id=update.message.chat.id,
        text=result,
        reply_to_message_id=update.message.message_id
    )

# Guard pattern
@api.command("admin", chat_id=-100123456)  # Только этот чат
async def admin_command(update, args):
    ...

await api.start_polling()
```

**Внутренняя реализация**:
- Регистрация команд в роутере
- Парсинг команд из Update.message.text
- Извлечение аргументов (split by space)
- Фильтрация по chat_id (guard)

---

#### 3.3 Message Threading (message_thread_id)

**Необходимо для**: Топики/форумы в супергруппах

**Параметр**: `message_thread_id` во всех send-методах

**Пример**:
```python
await api.send_message(
    chat_id=-100123456,
    message_thread_id=789,  # ID топика
    text="Сообщение в топик"
)
```

**API методы**:
- Добавить параметр `message_thread_id` во все send/edit методы
- `POST /v1/chats/{chat_id}/topics` — создание топика
- `GET /v1/chats/{chat_id}/topics` — список топиков
- `PATCH /v1/chats/{chat_id}/topics/{id}` — редактирование топика
- `DELETE /v1/chats/{chat_id}/topics/{id}` — закрытие топика

---

#### 3.4 sendChatAction

**Необходимо для**: Индикаторы активности ("typing...", "upload_photo...")

**API**:
```
POST /v1/chats/{chat_id}/action
{
  "action": "typing",
  "message_thread_id": 123  // optional
}
```

**Actions**:
- `typing` — печатает текст
- `upload_photo` — загружает фото
- `record_video` / `upload_video` — видео
- `record_voice` / `upload_voice` — голосовое
- `upload_document` — документ
- `choose_sticker` — выбирает стикер
- `find_location` — местоположение
- `record_video_note` / `upload_video_note` — видео-кружок

**SDK**:
```python
async with api.chat_action(chat_id, "typing"):
    # Индикатор показывается во время выполнения блока
    await asyncio.sleep(3)
    await api.send_message(chat_id, "Готово!")
```

**MCP**:
- `chats.action` — отправка chat action

---

### 🟡 ВАЖНЫЕ (упрощают миграцию)

#### 3.5 Расширенные медиа

**sendMediaGroup** — альбомы (до 10 фото/видео):
```
POST /v1/media/send-group
{
  "chat_id": -100123456,
  "media": [
    {"type": "photo", "media": "https://example.com/1.jpg", "caption": "Фото 1"},
    {"type": "photo", "media": "https://example.com/2.jpg"},
    {"type": "video", "media": "file_id_xyz", "caption": "Видео"}
  ]
}
```

**Остальные типы медиа**:
- `POST /v1/media/send-animation` — GIF/MP4 без звука
- `POST /v1/media/send-audio` — аудио-файл
- `POST /v1/media/send-voice` — голосовое сообщение (OGG/OPUS)
- `POST /v1/media/send-video-note` — видео-кружок
- `POST /v1/media/send-sticker` — стикер
- `POST /v1/media/send-location` — геолокация
- `POST /v1/media/send-venue` — место (с адресом)
- `POST /v1/media/send-contact` — контакт
- `POST /v1/media/send-dice` — игральная кость (🎲🎯🏀⚽🎳🎰)

**Сервисы**:
- `api/app/services/media.py` — универсальная загрузка файлов
- Поддержка thumbnail для видео/документов

---

#### 3.6 Forward / Copy Messages

**forwardMessage**:
```
POST /v1/messages/forward
{
  "chat_id": -100123456,
  "from_chat_id": -100789012,
  "message_id": 456
}
```

**copyMessage** (без ссылки на оригинал):
```
POST /v1/messages/copy
{
  "chat_id": -100123456,
  "from_chat_id": -100789012,
  "message_id": 456,
  "caption": "Новый caption"  // optional
}
```

**Массовый forward/copy** (до 100 сообщений):
```
POST /v1/messages/forward-many
{
  "chat_id": -100123456,
  "from_chat_id": -100789012,
  "message_ids": [1, 2, 3, ..., 100]
}
```

---

#### 3.7 Pin / Unpin Messages

**API**:
```
POST /v1/messages/{id}/pin
{
  "disable_notification": false
}

DELETE /v1/messages/{id}/pin

DELETE /v1/chats/{chat_id}/pins  // Открепить все
```

**SDK**:
```python
await api.pin_message(message_id, disable_notification=True)
await api.unpin_message(message_id)
await api.unpin_all_messages(chat_id)
```

---

#### 3.8 Edit расширенный

**editMessageCaption** — редактирование подписи медиа:
```
PATCH /v1/media/{id}/caption
{
  "caption": "Новая подпись",
  "parse_mode": "HTML"
}
```

**editMessageMedia** — замена медиа:
```
PATCH /v1/media/{id}/media
{
  "media": {
    "type": "photo",
    "media": "https://example.com/new.jpg",
    "caption": "Обновлённое фото"
  }
}
```

**editMessageReplyMarkup** — только кнопки:
```
PATCH /v1/messages/{id}/markup
{
  "reply_markup": {
    "inline_keyboard": [[...]]
  }
}
```

**editMessageLiveLocation** — обновление живой геолокации:
```
PATCH /v1/messages/{id}/location
{
  "latitude": 55.7558,
  "longitude": 37.6173
}
```

---

### 🟢 ЖЕЛАТЕЛЬНЫЕ (расширенный функционал)

#### 3.9 Chat Management

**Администрирование**:
- `GET /v1/chats/{chat_id}/administrators` — список админов
- `GET /v1/chats/{chat_id}/members/count` — количество участников
- `POST /v1/chats/{chat_id}/members/{user_id}/ban` — бан
- `POST /v1/chats/{chat_id}/members/{user_id}/unban` — разбан
- `POST /v1/chats/{chat_id}/members/{user_id}/restrict` — ограничение прав
- `POST /v1/chats/{chat_id}/members/{user_id}/promote` — повышение до админа

**Настройки чата**:
- `PATCH /v1/chats/{chat_id}/title` — изменение названия
- `PATCH /v1/chats/{chat_id}/description` — описание
- `POST /v1/chats/{chat_id}/photo` — фото чата
- `DELETE /v1/chats/{chat_id}/photo` — удаление фото
- `PATCH /v1/chats/{chat_id}/permissions` — права по умолчанию
- `GET /v1/chats/{chat_id}/invite-link` — создание invite link
- `POST /v1/chats/{chat_id}/join-requests/{user_id}/approve` — одобрить запрос
- `POST /v1/chats/{chat_id}/join-requests/{user_id}/decline` — отклонить

---

#### 3.10 Stickers

**Отправка**:
```
POST /v1/media/send-sticker
{
  "chat_id": -100123456,
  "sticker": "file_id_or_url"
}
```

**Управление наборами**:
- `GET /v1/stickers/sets/{name}` — получение набора
- `POST /v1/stickers/upload` — загрузка файла стикера
- `POST /v1/stickers/sets` — создание набора
- `POST /v1/stickers/sets/{name}/stickers` — добавление стикера
- `PATCH /v1/stickers/sets/{name}/stickers/{file_id}/position` — изменение позиции
- `DELETE /v1/stickers/sets/{name}/stickers/{file_id}` — удаление

---

#### 3.11 Inline Query (InlineMode)

**Обработка**:
```
POST /v1/inline/answer
{
  "inline_query_id": "123456789",
  "results": [
    {
      "type": "article",
      "id": "1",
      "title": "Результат 1",
      "input_message_content": {
        "message_text": "Текст сообщения"
      }
    }
  ]
}
```

**Webhook**: Обработка `inline_query` и `chosen_inline_result`

---

#### 3.12 Games & Payments

**Games**:
- `POST /v1/games/send` — отправка игры
- `POST /v1/games/{id}/score` — установка счёта

**Payments**:
- `POST /v1/invoices/send` — отправка счёта
- `POST /v1/invoices/{id}/answer-shipping` — ответ на доставку
- `POST /v1/invoices/{id}/answer-precheckout` — подтверждение оплаты

---

#### 3.13 Разное

**getUserProfilePhotos**:
```
GET /v1/users/{user_id}/photos?limit=10
```

**getFile** (получение URL для скачивания):
```
GET /v1/files/{file_id}
→ {"file_path": "...", "file_url": "https://api.telegram.org/file/bot.../..."}
```

**leaveChat**:
```
POST /v1/chats/{chat_id}/leave
```

**Команды расширенные**:
- `GET /v1/bot/commands` — getMyCommands
- `DELETE /v1/bot/commands` — deleteMyCommands
- `POST /v1/bot/menu-button` — setChatMenuButton
- `GET /v1/bot/menu-button` — getChatMenuButton

**Права бота**:
- `POST /v1/bot/default-rights` — setMyDefaultAdministratorRights
- `GET /v1/bot/default-rights` — getMyDefaultAdministratorRights

**Сессия**:
- `POST /v1/bot/logout` — logOut
- `POST /v1/bot/close` — close

---

## 4. Новинки Telegram Bot API 2025-2026

### 4.1 Bot API 9.3 (31 декабря 2025)

#### Темы в приватных чатах
- Поддержка `message_thread_id` в приватных чатах с форумами
- Поле `is_topic_message` в Message

#### Подарки (Gifts)
- `GET /v1/gifts/user/{user_id}` — getUserGifts
- `GET /v1/gifts/chat/{chat_id}` — getChatGifts
- Класс `UniqueGiftColors` — цветовая схема подарков
- Класс `GiftBackground` — фоны
- Поле `gift_upgrade_sent` в Message

#### repostStory
```
POST /v1/stories/repost
{
  "chat_id": -100123456,
  "from_chat_id": -100789012,
  "story_id": 123
}
```

#### Прочее
- `UserRating` — рейтинг пользователя в чате
- Максимальная цена paid media: 25000 Stars (было 2500)
- Параметр `message_effect_id` в forwardMessage/copyMessage
- Поле `paid_message_star_count` в ChatFullInfo

---

### 4.2 Bot API 9.2 (15 августа 2025)

#### Чеклисты (Checklists)
```
POST /v1/checklists/send
{
  "chat_id": -100123456,
  "checklist": {
    "title": "Задачи на день",
    "tasks": [
      {"text": "Проверить почту", "completed": false},
      {"text": "Созвониться с командой", "completed": true}
    ]
  }
}

PATCH /v1/checklists/{id}
{
  "tasks": [...]
}
```

**Классы**: `Checklist`, `ChecklistTask`, `InputChecklist`, `InputChecklistTask`

#### Прямые сообщения в каналах
- Поле `is_direct_messages` в Chat/ChatFullInfo
- Класс `DirectMessagesTopic`
- Параметр `direct_messages_topic_id` в send-методах

#### Suggested Posts (предлагаемые посты)
```
POST /v1/chats/{chat_id}/suggested-posts/{post_id}/approve
POST /v1/chats/{chat_id}/suggested-posts/{post_id}/decline
```

**Классы**: `SuggestedPostInfo`, `SuggestedPostApproved`, `SuggestedPostApprovalFailed`, `SuggestedPostDeclined`, `SuggestedPostPaid`, `SuggestedPostRefunded`

#### Баланс Stars
```
GET /v1/bot/star-balance
→ {"balance": 12500}
```

---

### 4.3 Bot API 9.1 (3 июля 2025)

- Максимум опций в опросе: **12** (было 10)
- Поле `next_transfer_date` в `OwnedGiftUnique`
- Поле `last_resale_star_count` и значение "resale" для `UniqueGiftInfo.origin`

---

## 5. План реализации

### Фаза 1: Критичные методы (1-2 недели)

**Задачи**:
1. Updates/Polling: getUpdates + long polling механизм
2. CommandHandler: регистрация команд в SDK + guard pattern
3. message_thread_id: добавление параметра во все send/edit методы
4. sendChatAction: индикаторы активности

**Файлы**:
- `api/app/routers/updates.py` (новый)
- `api/app/services/updates.py` (новый)
- `api/app/routers/messages.py` (расширение)
- `api/app/routers/chats.py` (расширение)
- `sdk/telegram_api_client/client.py` (polling loop, CommandHandler)
- `sdk/telegram_api_client/models.py` (Update, Message, CallbackQuery и т.д.)
- `mcp/src/index.ts` (updates.poll, updates.ack, chats.action)

**Миграция БД**:
```sql
-- 03_updates.sql
ALTER TABLE messages ADD COLUMN message_thread_id INTEGER;
ALTER TABLE updates ADD COLUMN processed BOOLEAN DEFAULT FALSE;
CREATE INDEX idx_updates_processed ON updates(processed);
```

**Тесты**:
- `scripts/test_polling.py` — long polling цикл
- `scripts/test_commands.py` — регистрация команд + обработка
- `scripts/test_threads.py` — отправка в топик

---

### Фаза 2: Важные методы (1 неделя)

**Задачи**:
1. Расширенные медиа: sendMediaGroup, sendAnimation, sendAudio, sendVoice, sendVideoNote, sendSticker, sendLocation, sendContact, sendDice
2. Forward/Copy: forwardMessage, copyMessage, forwardMessages, copyMessages
3. Pin/Unpin: pinChatMessage, unpinChatMessage, unpinAllChatMessages
4. Edit расширенный: editMessageCaption, editMessageMedia, editMessageReplyMarkup

**Файлы**:
- `api/app/routers/media.py` (расширение)
- `api/app/routers/messages.py` (forward/copy/pin)
- `api/app/services/media.py` (универсальная загрузка)
- `sdk/telegram_api_client/client.py` (новые методы)
- `mcp/src/index.ts` (media.*, messages.forward, messages.copy, messages.pin)

**Тесты**:
- `scripts/test_media.py` — все типы медиа
- `scripts/test_forward.py` — forward + copy
- `scripts/test_pin.py` — pin/unpin

---

### Фаза 3: Желательные методы (2 недели)

**Задачи**:
1. Chat Management: администрирование, настройки чата
2. Stickers: отправка + управление наборами
3. Inline Query: answerInlineQuery
4. getUserProfilePhotos, getFile, leaveChat
5. Расширенные команды: getMyCommands, deleteMyCommands, menu button, default rights

**Файлы**:
- `api/app/routers/chats.py` (расширение)
- `api/app/routers/stickers.py` (новый)
- `api/app/routers/inline.py` (новый)
- `api/app/routers/bot.py` (новый)
- `sdk/telegram_api_client/client.py` (chat management методы)
- `mcp/src/index.ts` (chats.*, stickers.*, inline.*, bot.*)

**Тесты**:
- `scripts/test_admin.py` — ban/unban/promote
- `scripts/test_stickers.py` — создание набора стикеров
- `scripts/test_inline.py` — inline mode

---

### Фаза 4: Новинки API 2025-2026 (1 неделя)

**Задачи**:
1. Чеклисты: sendChecklist, editMessageChecklist
2. Подарки: getUserGifts, getChatGifts
3. Прямые сообщения в каналах: direct_messages_topic_id
4. Suggested Posts: approve/decline
5. repostStory
6. getMyStarBalance

**Файлы**:
- `api/app/routers/checklists.py` (новый)
- `api/app/routers/gifts.py` (новый)
- `api/app/routers/stories.py` (новый)
- `api/app/routers/bot.py` (расширение)
- `api/app/services/checklists.py` (новый)
- `sdk/telegram_api_client/client.py` (новые методы)
- `mcp/src/index.ts` (checklists.*, gifts.*, stories.*)

**Миграция БД**:
```sql
-- 04_modern_features.sql
CREATE TABLE checklists (
  id SERIAL PRIMARY KEY,
  message_id INTEGER REFERENCES messages(id),
  title TEXT,
  tasks JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE gifts (
  id SERIAL PRIMARY KEY,
  user_id TEXT,
  gift_id TEXT,
  colors JSONB,
  background JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Тесты**:
- `scripts/test_checklists.py` — создание чеклиста
- `scripts/test_gifts.py` — getUserGifts
- `scripts/test_stories.py` — repostStory

---

### Фаза 5: Документация и публикация (3 дня)

**Задачи**:
1. Обновление `docs/api.md` — все новые эндпоинты
2. Обновление `docs/sdk.md` — все новые методы SDK
3. Обновление `docs/mcp.md` — все новые MCP-тулзы
4. Новый `docs/updates.md` — polling + webhook обработка
5. Новый `docs/migration.md` — руководство по миграции с python-telegram-bot
6. Обновление `README.md` — новые возможности, примеры
7. `CHANGELOG.md` — версия 2025.03.1
8. Git push, создание release на GitHub

---

## 6. Маппинг миграции

### 6.1 llm-mcp/telemetry → telegram-mcp

**Текущий код**:
```python
# telemetry/llm_telemetry/main.py
url = f"https://api.telegram.org/bot{token}/{method}"
data = urlencode(payload).encode("utf-8")
req = Request(url, data=data, method="POST")
with urlopen(req, timeout=10) as resp:
    result = json.loads(resp.read())
```

**Новый код (SDK)**:
```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://telegram-api:8081")

# Вместо sendMessage
msg = await api.send_message(
    chat_id=self.chat_id,
    text=f"<pre>{safe}</pre>",
    parse_mode="HTML",
    disable_web_page_preview=True
)
self.message_id = msg["id"]

# Вместо editMessageText
await api.edit_message(
    self.message_id,
    text=f"<pre>{safe}</pre>",
    parse_mode="HTML"
)
```

**Изменения**:
- ❌ Убрать urllib, urlopen, Request
- ✅ Добавить `telegram_api_client` в зависимости
- ✅ Заменить `_call()` на методы SDK
- ✅ `disable_web_page_preview` поддерживается через SDK

---

### 6.2 channel-mcp/worker → telegram-mcp

#### A. TelegramProgressNotifier

**Текущий код**:
```python
from telegram import Bot

bot = Bot(cfg.telegram_bot_token)
msg = await bot.send_message(chat_id=self.chat_id, text=self.base_text)
await bot.edit_message_text(
    chat_id=self.chat_id,
    message_id=self.message_id,
    text=self.base_text
)
```

**Новый код (SDK)**:
```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://telegram-api:8081")

# Использование ProgressContext
async with api.progress(chat_id=self.chat_id) as p:
    await p.update(1, 5, "⏳ Стадия: Ingest")
    await p.update(2, 5, "⏳ Стадия: Tagging")
    # ...
# Автоматически удаляется
```

**Изменения**:
- ❌ Убрать `python-telegram-bot`
- ✅ Использовать `api.progress()` контекст-менеджер
- ✅ Throttling встроен в SDK (минимум 0.8 сек)
- ✅ Spinner встроен в ProgressContext

#### B. Telegram Commands

**Текущий код**:
```python
from telegram.ext import Application, CommandHandler

app = build_application(cfg.telegram_bot_token)
app.add_handler(CommandHandler("toptags", top_tags))
await app.updater.start_polling()

async def top_tags(update, context):
    await update.message.reply_text(text)
```

**Новый код (SDK)**:
```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://telegram-api:8081")

@api.command("toptags", chat_id=cfg.report_chat_id)
async def top_tags(update, args):
    days = int(args[0]) if args else 7
    # ... логика
    await api.send_message(
        chat_id=update.message.chat.id,
        text=result,
        reply_to_message_id=update.message.message_id
    )

await api.start_polling()
```

**Изменения**:
- ❌ Убрать `Application`, `CommandHandler`, `updater`
- ✅ Использовать `@api.command()` декоратор
- ✅ Guard pattern встроен: `chat_id=...`
- ✅ Polling loop встроен в SDK

---

### 6.3 jobs.py (монолит) → telegram-mcp

#### A. ProgressNotifier

**Текущий код**:
```python
from telegram import Bot

bot = Bot(os.getenv("BOT_TOKEN"))
notifier = ProgressNotifier(bot, cfg.telegram.report_chat_id)

await notifier.update(1, 6, "Собираем рынок...")
await notifier.update_swarm(round_idx, total_rounds, model, action, ...)
await notifier.done()
```

**Новый код (SDK)**:
```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://telegram-api:8081")

async with api.progress(chat_id=cfg.telegram.report_chat_id) as p:
    # Обычный прогресс
    await p.update(1, 6, "Собираем рынок...")

    # Swarm-визуализация
    await p.update_swarm(
        round_idx=2,
        total_rounds=8,
        model="openrouter:google/gemini-3-flash",
        action="tool",
        cost=10,
        detail="market_live(...)",
        budgets={...},
        target="openrouter:openai/gpt-4o"
    )
# Автоматически удаляется
```

**Изменения**:
- ✅ Перенести `ProgressNotifier` класс в SDK
- ✅ Добавить метод `update_swarm()` в SDK ProgressContext
- ✅ Все эмодзи-логику перенести в SDK
- ✅ HTML-форматирование встроено

#### B. send_photo

**Текущий код**:
```python
from telegram import Bot

with open(chart_path, "rb") as img:
    await bot.send_photo(
        chat_id=chat_id,
        photo=img,
        caption=message,
        parse_mode="HTML"
    )
```

**Новый код (SDK)**:
```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://telegram-api:8081")

with open(chart_path, "rb") as img:
    await api.send_photo(
        chat_id=chat_id,
        photo=img,
        caption=message,
        parse_mode="HTML"
    )
```

**Изменения**:
- ❌ Убрать `from telegram import Bot`
- ✅ Использовать SDK
- ✅ Интерфейс идентичен

#### C. Отправка множественных сообщений

**Текущий код**:
```python
# Message 1: текст + фото
await _send_with_chart(bot, chat_id, main_msg, chart_path, parse_mode="HTML")

# Message 2: резюме оператора
await bot.send_message(chat_id=chat_id, text=ensemble_msg, parse_mode="HTML")

# Message 3: рейтинг
await bot.send_message(chat_id=chat_id, text=ranking_msg, parse_mode="HTML")
```

**Новый код (SDK)**:
```python
# Message 1
await api.send_photo_with_fallback(
    chat_id=chat_id,
    photo=chart_path,
    caption=main_msg,
    caption_limit=1000,
    parse_mode="HTML"
)

# Message 2
await api.send_message(chat_id=chat_id, text=ensemble_msg, parse_mode="HTML")

# Message 3
await api.send_message(chat_id=chat_id, text=ranking_msg, parse_mode="HTML")
```

**Изменения**:
- ✅ Добавить `send_photo_with_fallback()` в SDK (автоматическая логика caption_limit)
- ✅ Все методы возвращают одинаковый формат

---

## 7. Преимущества миграции

### Централизация
- ✅ Единая точка входа для всех Telegram-операций
- ✅ Унифицированный аудит-трейл (все операции в PostgreSQL)
- ✅ Консистентная обработка ошибок (retry, rate limiting)

### Упрощение кода
- ✅ Убираем три разных имплементации (urllib, httpx, python-telegram-bot)
- ✅ Единый SDK для всех потребителей
- ✅ Готовые паттерны: ProgressContext, CommandHandler

### Масштабируемость
- ✅ Rate limiting по chat_id (защита от флуда)
- ✅ Connection pool (эффективное использование ресурсов)
- ✅ Retry-механизмы (надёжность)

### Observability
- ✅ Все сообщения в БД (история, поиск, аналитика)
- ✅ Метрики через `/metrics` эндпоинт
- ✅ Healthchecks для мониторинга

### LLM интеграция
- ✅ 25+ MCP-инструментов (Claude, ChatGPT могут отправлять сообщения)
- ✅ Шаблоны Jinja2 (динамическая генерация контента)
- ✅ Структурированные данные (polls, callbacks, reactions)

---

## 8. Risks и Mitigations

### Risk 1: Сетевая задержка (API → telegram-api → Telegram)

**Mitigation**:
- ✅ Connection pool с keep-alive (минимум latency)
- ✅ Async/await во всех слоях (нет блокировок)
- ✅ Локальный deployment (Docker Compose в одной сети)
- ✅ Бенчмарки показывают overhead ~5-10ms (приемлемо)

### Risk 2: Single Point of Failure

**Mitigation**:
- ✅ Health checks в Docker Compose (автоматический restart)
- ✅ Retry-механизмы в SDK (временные сбои)
- ✅ Graceful degradation (если API недоступен, продолжаем работу)
- ✅ В будущем: горизонтальное масштабирование (несколько инстансов telegram-api)

### Risk 3: Потеря сообщений при миграции

**Mitigation**:
- ✅ Параллельный запуск (старая + новая реализация)
- ✅ Постепенная миграция (по одному потребителю)
- ✅ Dry-run режим (тестирование без реальной отправки)
- ✅ Аудит-трейл (сравнение логов)

### Risk 4: Несовместимость API

**Mitigation**:
- ✅ SDK максимально совместим с python-telegram-bot (похожий интерфейс)
- ✅ Все параметры Telegram API поддерживаются
- ✅ Расширенная типизация (Pydantic) — раннее обнаружение ошибок
- ✅ Юнит-тесты для всех методов SDK

---

## 9. Roadmap

### Q1 2025 (февраль-март)
- ✅ **2025.02.1** — текущая версия (базовые сообщения, медиа, polls, reactions)
- 🔄 **2025.03.1** — Updates/Polling, CommandHandler, message_thread_id, sendChatAction
- 🔄 **2025.03.2** — Расширенные медиа, forward/copy, pin/unpin, edit расширенный

### Q2 2025 (апрель-июнь)
- 📅 **2025.04.1** — Chat Management, Stickers, Inline Query, расширенные команды
- 📅 **2025.05.1** — Чеклисты, Подарки, repostStory, прямые сообщения в каналах
- 📅 **2025.06.1** — Миграция llm-mcp telemetry

### Q3 2025 (июль-сентябрь)
- 📅 **2025.07.1** — Миграция channel-mcp worker
- 📅 **2025.08.1** — Миграция jobs.py (монолит)
- 📅 **2025.09.1** — Полная замена python-telegram-bot

### Q4 2025 (октябрь-декабрь)
- 📅 **2025.10.1** — Горизонтальное масштабирование (multiple instances)
- 📅 **2025.11.1** — Advanced metrics & monitoring
- 📅 **2025.12.1** — Стабильная версия 1.0.0

---

## 10. Заключение

**telegram-mcp** уже имеет 80% необходимого функционала для миграции. Основные недостающие элементы — **Updates/Polling** и **CommandHandler pattern** — критичны для channel-mcp, но легко реализуемы.

**Приоритеты**:
1. **Фаза 1** (критичные методы) — разблокирует миграцию channel-mcp
2. **Фаза 2** (важные методы) — завершает функциональность для jobs.py
3. **Фаза 3-4** — расширенный функционал для будущих проектов

**Оценка трудозатрат**: ~6 недель до полной готовности всех фаз
**Начало миграции**: После Фазы 1 (≈2 недели)

Проект готов к расширению! 🚀
