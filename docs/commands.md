# Управление командами бота

telegram-api управляет командами через BotCommandScope — механизм Telegram для показа разных меню `/` разным пользователям.

## Концепция

Когда пользователь нажимает `/` в чате, Telegram показывает список команд. Какие именно команды — зависит от **скоупа**:

```
Приоритет (от высшего к низшему):
  chat_member     — конкретный user в конкретном чате
  chat_administrators — все админы чата
  chat            — все в конкретном чате
  all_group_chats — все групповые чаты
  all_private_chats — все личные чаты
  default         — глобально
```

Telegram выбирает наиболее специфичный набор. Если для пользователя 777 в чате -100123 задан `chat_member`, он увидит именно его, а не `chat` или `default`.

## Использование

### 1. Создание наборов команд

**Глобальные команды** (видны всем по умолчанию):

```bash
curl -X POST http://127.0.0.1:8081/v1/commands \
  -H 'content-type: application/json' \
  -d '{
    "scope_type": "default",
    "commands": [
      {"command": "start", "description": "Начать работу с ботом"},
      {"command": "help", "description": "Справка по командам"},
      {"command": "ping", "description": "Проверка связи"}
    ]
  }'
```

**Команды для конкретного чата** (расширенный набор):

```bash
curl -X POST http://127.0.0.1:8081/v1/commands \
  -H 'content-type: application/json' \
  -d '{
    "scope_type": "chat",
    "chat_id": -100123456,
    "commands": [
      {"command": "start", "description": "Начать"},
      {"command": "help", "description": "Справка"},
      {"command": "summary", "description": "Сводка по чату"},
      {"command": "toppoint", "description": "Рейтинг участников"}
    ]
  }'
```

**Per-user команды** (admin-меню для конкретного пользователя):

```bash
curl -X POST http://127.0.0.1:8081/v1/commands \
  -H 'content-type: application/json' \
  -d '{
    "scope_type": "chat_member",
    "chat_id": -100123456,
    "user_id": 777,
    "commands": [
      {"command": "start", "description": "Начать"},
      {"command": "help", "description": "Справка"},
      {"command": "summary", "description": "Сводка по чату"},
      {"command": "toppoint", "description": "Рейтинг"},
      {"command": "cleanup", "description": "Запуск очистки"},
      {"command": "report", "description": "Сформировать отчёт"}
    ]
  }'
```

### 2. Синхронизация с Telegram

Созданные наборы хранятся в БД. Чтобы Telegram узнал о них, нужно синхронизировать:

```bash
curl -X POST http://127.0.0.1:8081/v1/commands/sync \
  -H 'content-type: application/json' \
  -d '{"command_set_id": 1}'
```

Для каждого набора — отдельный вызов sync.

### 3. Просмотр наборов

```bash
curl http://127.0.0.1:8081/v1/commands
```

## Python SDK

```python
from telegram_api_client import TelegramAPI

async with TelegramAPI("http://localhost:8081") as api:
    # Глобальные
    cs1 = await api.set_commands([
        {"command": "start", "description": "Начать"},
        {"command": "help", "description": "Справка"},
    ])

    # Per-user
    cs2 = await api.set_commands(
        commands=[
            {"command": "start", "description": "Начать"},
            {"command": "cleanup", "description": "Очистка (админ)"},
            {"command": "report", "description": "Отчёт (админ)"},
        ],
        scope_type="chat_member",
        chat_id=-100123456,
        user_id=777,
    )

    # Синхронизация
    await api.sync_commands(cs1["id"])
    await api.sync_commands(cs2["id"])
```

## Типичный сценарий

Бот в групповом чате. Обычные пользователи видят базовые команды, а администратор — расширенное меню:

```
Обычный пользователь нажимает /:
  /start — Начать
  /help  — Справка
  /ping  — Проверка

Админ (user_id=777) нажимает /:
  /start   — Начать
  /help    — Справка
  /ping    — Проверка
  /summary — Сводка
  /cleanup — Очистка
  /report  — Отчёт
```

Для этого создаём два набора:
1. `scope_type=chat`, `chat_id=-100123456` — для всех
2. `scope_type=chat_member`, `chat_id=-100123456`, `user_id=777` — для админа

## Типы скоупов

| scope_type | chat_id | user_id | Описание |
|------------|---------|---------|----------|
| `default` | — | — | Глобальные команды для всех |
| `all_private_chats` | — | — | Все личные чаты |
| `all_group_chats` | — | — | Все групповые чаты |
| `chat` | да | — | Конкретный чат |
| `chat_administrators` | да | — | Только админы конкретного чата |
| `chat_member` | да | да | Конкретный пользователь в конкретном чате |

## Локализация

Параметр `language_code` позволяет задать команды для конкретного языка:

```bash
curl -X POST http://127.0.0.1:8081/v1/commands \
  -H 'content-type: application/json' \
  -d '{
    "scope_type": "default",
    "language_code": "en",
    "commands": [
      {"command": "start", "description": "Start the bot"},
      {"command": "help", "description": "Show help"}
    ]
  }'
```

Telegram покажет локализованный набор пользователям с соответствующим языком интерфейса.

## Хранение

Наборы команд хранятся в таблице `bot_commands` с уникальным индексом по `(scope_type, chat_id, user_id, language_code)`. При повторном вызове с теми же параметрами — набор обновляется (upsert).
