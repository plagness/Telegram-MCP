CREATE TABLE IF NOT EXISTS chats (
  chat_id TEXT PRIMARY KEY,
  type TEXT,
  title TEXT,
  username TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  is_bot BOOLEAN,
  first_name TEXT,
  last_name TEXT,
  username TEXT,
  language_code TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
  id BIGSERIAL PRIMARY KEY,
  external_id TEXT UNIQUE,
  chat_id TEXT NOT NULL,
  telegram_message_id BIGINT,
  direction TEXT NOT NULL,
  text TEXT,
  parse_mode TEXT,
  status TEXT NOT NULL,
  error TEXT,
  payload_json JSONB,
  is_live BOOLEAN DEFAULT FALSE,
  reply_to_message_id BIGINT,
  message_thread_id BIGINT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  sent_at TIMESTAMPTZ,
  edited_at TIMESTAMPTZ,
  deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS messages_chat_message_idx
  ON messages (chat_id, telegram_message_id)
  WHERE telegram_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS message_events (
  id BIGSERIAL PRIMARY KEY,
  message_id BIGINT REFERENCES messages(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload_json JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS templates (
  id BIGSERIAL PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  body TEXT NOT NULL,
  parse_mode TEXT,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_updates (
  id BIGSERIAL PRIMARY KEY,
  update_id BIGINT UNIQUE,
  update_type TEXT,
  chat_id TEXT,
  user_id TEXT,
  message_id BIGINT,
  payload_json JSONB,
  received_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_commands (
  id BIGSERIAL PRIMARY KEY,
  scope_type TEXT NOT NULL,
  chat_id TEXT,
  user_id TEXT,
  language_code TEXT,
  commands_json JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS bot_commands_scope_idx
  ON bot_commands (scope_type, chat_id, user_id, language_code);
