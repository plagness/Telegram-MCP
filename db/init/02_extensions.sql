-- Расширение схемы: медиа, callback queries, webhook config

-- Расширение таблицы messages
ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_type TEXT NOT NULL DEFAULT 'text';
ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_file_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS caption TEXT;

-- Индекс по типу сообщения
CREATE INDEX IF NOT EXISTS messages_type_idx ON messages (message_type);

-- Callback queries от пользователей
CREATE TABLE IF NOT EXISTS callback_queries (
    id BIGSERIAL PRIMARY KEY,
    callback_query_id TEXT UNIQUE NOT NULL,
    chat_id TEXT,
    user_id TEXT,
    message_id BIGINT,
    inline_message_id TEXT,
    data TEXT,
    answered BOOLEAN DEFAULT FALSE,
    answer_text TEXT,
    answer_show_alert BOOLEAN DEFAULT FALSE,
    payload_json JSONB,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    answered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS callback_queries_chat_idx ON callback_queries (chat_id);
CREATE INDEX IF NOT EXISTS callback_queries_user_idx ON callback_queries (user_id);

-- Конфигурация вебхука
CREATE TABLE IF NOT EXISTS webhook_config (
    id BIGSERIAL PRIMARY KEY,
    url TEXT,
    secret_token TEXT,
    max_connections INT DEFAULT 40,
    allowed_updates JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    set_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
