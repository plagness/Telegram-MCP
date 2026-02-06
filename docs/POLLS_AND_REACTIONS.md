# Опросы и реакции

Руководство по использованию опросов, викторин и реакций в telegram-api.

---

## Опросы (Polls)

### Обычный опрос

```python
from telegram_api_client import TelegramAPI

async with TelegramAPI("http://localhost:8081") as api:
    poll = await api.send_poll(
        chat_id=-100123456,
        question="Какой язык программирования вы используете?",
        options=["Python", "JavaScript", "Go", "Rust"],
        is_anonymous=True,
        allows_multiple_answers=True,
        open_period=300,  # 5 минут
    )
    print(f"Опрос создан: {poll['id']}")
```

### Викторина (Quiz)

```python
quiz = await api.send_poll(
    chat_id=-100123456,
    question="Сколько планет в Солнечной системе?",
    options=["7", "8", "9", "10"],
    type="quiz",
    correct_option_id=1,  # 8 планет
    explanation="После 2006 года Плутон больше не считается планетой.",
    explanation_parse_mode="HTML",
    open_period=60,
)
```

### Параметры sendPoll

| Параметр | Тип | Описание |
|----------|-----|----------|
| `chat_id` | int/str | ID чата |
| `question` | str | Вопрос (1-300 символов) |
| `options` | list[str] | Варианты ответов (2-10) |
| `is_anonymous` | bool | Анонимное голосование (по умолчанию True) |
| `type` | str | `"regular"` или `"quiz"` |
| `allows_multiple_answers` | bool | Множественный выбор (только для regular) |
| `correct_option_id` | int | Индекс правильного ответа (только для quiz, 0-based) |
| `explanation` | str | Пояснение для quiz (до 200 символов) |
| `explanation_parse_mode` | str | `HTML` / `MarkdownV2` |
| `open_period` | int | Время жизни опроса в секундах (5-600) |
| `message_thread_id` | int | ID топика (для форумов) |
| `reply_to_message_id` | int | Ответ на сообщение |

### Остановка опроса

```python
# Остановить и показать результаты
stopped = await api.stop_poll(
    chat_id=-100123456,
    message_id=42,  # telegram_message_id
)
print(f"Всего голосов: {stopped['total_voter_count']}")
```

### Список опросов

```python
polls = await api.list_polls(chat_id="-100123456", limit=10)
for p in polls:
    print(f"{p['question']} - {p['type']}, closed={p['is_closed']}")
```

---

## Реакции (Reactions)

### Установка реакции

```python
# Одна реакция
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,  # telegram_message_id
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
```

### Большая анимация

```python
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=[{"type": "emoji", "emoji": "👏"}],
    is_big=True,  # Большая анимация
)
```

### Кастомные эмодзи

```python
# Требует купленный username на Fragment
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=[{"type": "custom_emoji", "custom_emoji_id": "5312536423851630001"}],
)
```

### Удаление реакций

```python
# Удалить все реакции бота
await api.set_reaction(
    chat_id=-100123456,
    message_id=42,
    reaction=None,
)
```

### Список реакций

```python
reactions = await api.list_reactions(chat_id="-100123456", limit=100)
for r in reactions:
    print(f"{r['reaction_emoji']} от user_id={r['user_id']}")
```

---

## Расширенные inline-кнопки

Теперь поддерживаются все типы inline-кнопок Telegram.

### Mini App (Web App)

```python
await api.send_message(
    chat_id=-100123456,
    text="Запустить приложение",
    reply_markup={
        "inline_keyboard": [[
            {
                "text": "Открыть App",
                "web_app": {"url": "https://example.com/app"}
            }
        ]]
    },
)
```

### Inline-режим

```python
# Переключение в inline-режим в другом чате
{
    "text": "Поделиться",
    "switch_inline_query": "поиск"
}

# Inline-режим в текущем чате
{
    "text": "Поиск здесь",
    "switch_inline_query_current_chat": "поиск"
}
```

### Копирование текста

```python
{
    "text": "Скопировать API ключ",
    "copy_text": {"text": "your_api_key_12345"}
}
```

### OAuth-авторизация

```python
{
    "text": "Войти",
    "login_url": {
        "url": "https://example.com/auth",
        "forward_text": "Войти в сервис",
        "request_write_access": True
    }
}
```

---

## MCP-инструменты

### polls.send

```bash
curl -X POST http://127.0.0.1:3335/tools/polls.send \
  -H 'content-type: application/json' \
  -d '{
    "chat_id": -100123456,
    "question": "Выберите технологию",
    "options": ["FastAPI", "Flask", "Django"],
    "type": "regular",
    "allows_multiple_answers": true
  }'
```

### polls.stop

```bash
curl -X POST http://127.0.0.1:3335/tools/polls.stop \
  -H 'content-type: application/json' \
  -d '{
    "chat_id": -100123456,
    "message_id": 42
  }'
```

### reactions.set

```bash
curl -X POST http://127.0.0.1:3335/tools/reactions.set \
  -H 'content-type: application/json' \
  -d '{
    "chat_id": -100123456,
    "message_id": 42,
    "reaction": [{"type": "emoji", "emoji": "🔥"}],
    "is_big": false
  }'
```

---

## Use case для LLM

### Опрос команды

```
LLM: "Давайте спросим команду, какой фреймворк использовать для нового проекта?"

→ Вызывает polls.send через MCP
→ Создаёт опрос с вариантами: FastAPI, Flask, Django, Sanic
→ Ждёт 5 минут (open_period=300)
→ Вызывает polls.stop
→ Анализирует результаты
→ Предлагает решение на основе голосования
```

### Реакции на прогресс

```
LLM: "Начинаю анализ данных..."

→ Отправляет сообщение
→ Ставит реакцию ⏳ (в процессе)
→ Выполняет анализ
→ Меняет реакцию на ✅ (готово)
→ Отправляет результаты
```

### Викторина для обучения

```
LLM: "Проверим знания по Python"

→ Создаёт quiz с вопросом
→ Указывает correct_option_id
→ Добавляет explanation с подробным пояснением
→ Пользователи учатся, получая feedback
```

---

## Тестирование

```bash
# Опросы
python scripts/test_polls.py --chat-id -100123456789

# Только викторина
python scripts/test_polls.py --chat-id -100123456789 --quiz

# Реакции (создаст тестовое сообщение)
python scripts/test_reactions.py --chat-id -100123456789

# Реакции на существующее сообщение
python scripts/test_reactions.py --chat-id -100123456789 --message-id 42
```

---

## База данных

### Таблица polls

```sql
polls (
    poll_id TEXT UNIQUE,
    message_id BIGINT,
    question TEXT,
    options JSONB,
    type TEXT,  -- 'regular' или 'quiz'
    is_anonymous BOOLEAN,
    allows_multiple_answers BOOLEAN,
    correct_option_id INT,
    explanation TEXT,
    open_period INT,
    is_closed BOOLEAN,
    total_voter_count INT,
    results JSONB
)
```

### Таблица poll_answers

```sql
poll_answers (
    poll_id TEXT,
    user_id TEXT,
    option_ids INT[],
    answered_at TIMESTAMPTZ
)
```

### Таблица message_reactions

```sql
message_reactions (
    message_id BIGINT,
    chat_id TEXT,
    telegram_message_id BIGINT,
    user_id TEXT,
    reaction_type TEXT,
    reaction_emoji TEXT,
    reaction_custom_emoji_id TEXT,
    UNIQUE (chat_id, telegram_message_id, user_id, reaction_type, ...)
)
```

---

## Ограничения

- **Опросы**: максимум 10 вариантов ответа, вопрос до 300 символов
- **Викторины**: explanation до 200 символов
- **Время жизни**: open_period от 5 до 600 секунд
- **Кастомные эмодзи**: только для ботов с купленным username на Fragment
- **Реакции**: количество зависит от типа чата и прав бота
