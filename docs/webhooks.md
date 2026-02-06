# Вебхуки и обновления

telegram-api принимает обновления от Telegram через вебхук, сохраняет их в БД и предоставляет доступ через API.

## Настройка вебхука

### 1. Установка

```bash
curl -X POST http://127.0.0.1:8081/v1/webhook/set \
  -H 'content-type: application/json' \
  -d '{
    "url": "https://your-domain.com/telegram/webhook",
    "secret_token": "my-secret-token",
    "allowed_updates": ["message", "callback_query", "edited_message"]
  }'
```

| Параметр | Описание |
|----------|----------|
| `url` | HTTPS-адрес для приёма обновлений (обязательно) |
| `secret_token` | Секретный токен для верификации (опционально) |
| `max_connections` | Максимум соединений (по умолчанию 40) |
| `allowed_updates` | Типы обновлений для получения |

### 2. Проверка текущей конфигурации

```bash
curl http://127.0.0.1:8081/v1/webhook/info
```

### 3. Удаление

```bash
curl -X DELETE http://127.0.0.1:8081/v1/webhook
```

## Приём обновлений

Вебхук Telegram отправляет POST-запросы на:

```
POST https://your-domain.com/telegram/webhook
```

telegram-api автоматически:
1. Сохраняет обновление в таблицу `webhook_updates`
2. Извлекает и сохраняет информацию о чате → таблица `chats`
3. Извлекает и сохраняет информацию о пользователе → таблица `users`
4. Сохраняет callback queries → таблица `callback_queries`

## Просмотр обновлений

```bash
# Все обновления (последние 100)
curl http://127.0.0.1:8081/v1/updates

# С фильтром по типу
curl "http://127.0.0.1:8081/v1/updates?update_type=message&limit=50"

# Только callback queries
curl "http://127.0.0.1:8081/v1/updates?update_type=callback_query"
```

### Типы обновлений

| update_type | Описание |
|-------------|----------|
| `message` | Новое сообщение |
| `edited_message` | Отредактированное сообщение |
| `callback_query` | Нажатие inline-кнопки |
| `channel_post` | Публикация в канале |
| `edited_channel_post` | Редактирование в канале |
| `my_chat_member` | Изменение статуса бота в чате |
| `chat_member` | Изменение статуса участника |

## Python SDK

```python
from telegram_api_client import TelegramAPI

async with TelegramAPI("http://localhost:8081") as api:
    # Настройка
    await api.set_webhook(
        url="https://your-domain.com/telegram/webhook",
        secret_token="my-secret",
    )

    # Проверка
    info = await api.get_webhook_info()
    print(info)

    # Последние обновления
    updates = await api.list_updates(limit=50, update_type="message")
    for u in updates:
        print(f"[{u['update_type']}] chat={u['chat_id']} user={u['user_id']}")

    # Удаление
    await api.delete_webhook()
```

## Структура обновления в БД

Таблица `webhook_updates`:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial | Внутренний ID |
| `update_id` | bigint | ID обновления от Telegram (unique) |
| `update_type` | text | Тип обновления |
| `chat_id` | text | ID чата |
| `user_id` | text | ID пользователя |
| `message_id` | bigint | ID сообщения |
| `payload_json` | jsonb | Полный JSON обновления |
| `received_at` | timestamptz | Время получения |

## Callback Queries

Callback queries (нажатия inline-кнопок) дополнительно сохраняются в таблицу `callback_queries`:

```bash
# Просмотр
curl "http://127.0.0.1:8081/v1/callbacks?answered=false"

# Ответ на callback
curl -X POST http://127.0.0.1:8081/v1/callbacks/answer \
  -H 'content-type: application/json' \
  -d '{
    "callback_query_id": "123456789",
    "text": "Принято!",
    "show_alert": false
  }'
```

## Примечания

- Telegram требует HTTPS для вебхуков (кроме localhost для тестов)
- Обновления с одинаковым `update_id` не дублируются (UNIQUE constraint)
- Информация о чатах и пользователях обновляется при каждом обновлении (upsert)
