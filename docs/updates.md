# Updates / Polling (мультибот)

Этот документ описывает polling-контур `telegram-mcp` в режиме мультибота.

## Эндпоинты

- `GET /v1/updates/poll`
- `POST /v1/updates/ack`
- `GET /v1/updates/offset`
- `GET /v1/updates` (история из БД)

## Контекст offset

`update_offset` хранится отдельно по `bot_id`:

- `bot_id = NULL` — default context (обратная совместимость).
- `bot_id = <id>` — контекст конкретного бота.

Если polling вызывается без `offset`, API берёт offset из таблицы:

- при `bot_id` в query — из этого bot context;
- без `bot_id` — из default context.

## Ack контракт

```json
{
  "offset": 123457,
  "bot_id": 123456789
}
```

`bot_id` опционален.

## SDK пример

```python
from telegram_api_client import TelegramAPI

api = TelegramAPI("http://localhost:8081")

@api.command("start", chat_id=-100123456)
async def start(update, args):
    await api.send_message(
        chat_id=update["message"]["chat"]["id"],
        text="hello",
        bot_id=123456789,
    )

await api.start_polling(timeout=30, limit=100, bot_id=123456789)
```
