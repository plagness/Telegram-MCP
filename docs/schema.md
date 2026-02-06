# Схема базы данных

PostgreSQL 16. Схема определена в `db/init/01_schema.sql` и `db/init/02_extensions.sql`.

## Таблицы

### messages

Все исходящие и входящие сообщения с полным аудит-трейлом.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | Внутренний ID |
| `external_id` | text UNIQUE | Внешний ID (request_id) |
| `chat_id` | text NOT NULL | ID чата |
| `telegram_message_id` | bigint | ID сообщения в Telegram |
| `direction` | text NOT NULL | `outbound` / `inbound` |
| `text` | text | Текст сообщения |
| `parse_mode` | text | `HTML` / `MarkdownV2` |
| `status` | text NOT NULL | `queued`, `sent`, `edited`, `deleted`, `error`, `dry_run` |
| `error` | text | Описание ошибки |
| `message_type` | text NOT NULL | `text`, `photo`, `document`, `video`, `forward` |
| `media_file_id` | text | file_id медиа от Telegram |
| `caption` | text | Подпись медиа |
| `payload_json` | jsonb | Полный payload запроса |
| `is_live` | boolean | Прогресс-сообщение |
| `reply_to_message_id` | bigint | ID сообщения для ответа |
| `message_thread_id` | bigint | ID топика (форумы) |
| `created_at` | timestamptz | Время создания |
| `updated_at` | timestamptz | Время обновления |
| `sent_at` | timestamptz | Время отправки |
| `edited_at` | timestamptz | Время редактирования |
| `deleted_at` | timestamptz | Время удаления |

Индексы:
- `messages_chat_message_idx` — UNIQUE по `(chat_id, telegram_message_id)` WHERE NOT NULL
- `messages_type_idx` — по `message_type`

### message_events

Аудит-трейл для каждой операции над сообщением.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | ID события |
| `message_id` | bigint FK | Ссылка на `messages.id` (CASCADE) |
| `event_type` | text NOT NULL | `send_attempt`, `send_success`, `send_error`, `edit_attempt`, `edit_success`, `edit_error`, `delete_attempt`, `delete_success`, `delete_error` |
| `payload_json` | jsonb | Данные события |
| `created_at` | timestamptz | Время события |

### templates

Jinja2-шаблоны для сообщений.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | ID шаблона |
| `name` | text UNIQUE NOT NULL | Имя шаблона |
| `body` | text NOT NULL | Тело шаблона (Jinja2) |
| `parse_mode` | text | Режим форматирования |
| `description` | text | Описание |
| `created_at` | timestamptz | Время создания |
| `updated_at` | timestamptz | Время обновления |

### webhook_updates

Все входящие обновления от Telegram.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | Внутренний ID |
| `update_id` | bigint UNIQUE | ID обновления от Telegram |
| `update_type` | text | `message`, `callback_query`, `edited_message` и т.д. |
| `chat_id` | text | ID чата |
| `user_id` | text | ID пользователя |
| `message_id` | bigint | ID сообщения |
| `payload_json` | jsonb | Полный JSON обновления |
| `received_at` | timestamptz | Время получения |

### chats

Нормализованные данные о чатах (извлекаются из обновлений).

| Поле | Тип | Описание |
|------|-----|----------|
| `chat_id` | text PK | ID чата |
| `type` | text | `private`, `group`, `supergroup`, `channel` |
| `title` | text | Название чата |
| `username` | text | Username чата |
| `created_at` | timestamptz | Первое появление |
| `updated_at` | timestamptz | Последнее обновление |

### users

Нормализованные данные о пользователях (извлекаются из обновлений).

| Поле | Тип | Описание |
|------|-----|----------|
| `user_id` | text PK | ID пользователя |
| `is_bot` | boolean | Бот или человек |
| `first_name` | text | Имя |
| `last_name` | text | Фамилия |
| `username` | text | Username |
| `language_code` | text | Код языка |
| `created_at` | timestamptz | Первое появление |
| `updated_at` | timestamptz | Последнее обновление |

### bot_commands

Наборы команд бота по скоупам (BotCommandScope).

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | ID набора |
| `scope_type` | text NOT NULL | `default`, `chat`, `chat_member` и т.д. |
| `chat_id` | text | ID чата (для chat/chat_member) |
| `user_id` | text | ID пользователя (для chat_member) |
| `language_code` | text | Код языка |
| `commands_json` | jsonb NOT NULL | Массив `[{command, description}]` |
| `created_at` | timestamptz | Время создания |
| `updated_at` | timestamptz | Время обновления |

Индекс: `bot_commands_scope_idx` — UNIQUE по `(scope_type, chat_id, user_id, language_code)`

### callback_queries

Callback queries от нажатий inline-кнопок.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | Внутренний ID |
| `callback_query_id` | text UNIQUE NOT NULL | ID от Telegram |
| `chat_id` | text | ID чата |
| `user_id` | text | ID пользователя |
| `message_id` | bigint | ID сообщения с кнопкой |
| `inline_message_id` | text | ID inline-сообщения |
| `data` | text | Данные кнопки (callback_data) |
| `answered` | boolean | Отвечен ли |
| `answer_text` | text | Текст ответа |
| `answer_show_alert` | boolean | Alert или toast |
| `payload_json` | jsonb | Полный JSON |
| `received_at` | timestamptz | Время получения |
| `answered_at` | timestamptz | Время ответа |

Индексы: по `chat_id` и `user_id`.

### webhook_config

Конфигурация вебхука.

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigserial PK | ID |
| `url` | text | URL вебхука |
| `secret_token` | text | Секретный токен |
| `max_connections` | int | Максимум соединений (40) |
| `allowed_updates` | jsonb | Типы обновлений |
| `is_active` | boolean | Активен ли |
| `set_at` | timestamptz | Время установки |
| `created_at` | timestamptz | Время создания |
| `updated_at` | timestamptz | Время обновления |

## ER-диаграмма

```
messages ─────┐
  │            │
  │ FK         │
  ▼            │
message_events │
               │
               │  chat_id    chat_id
chats ◄────────┼──────────── webhook_updates
               │
users ◄────────┤  user_id
               │
bot_commands   │
               │
callback_queries
               │
webhook_config
               │
templates ─────┘
```
