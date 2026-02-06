-- Миграция: Мультибот + обогащение данных чатов/пользователей + аудит API
-- Версия: 2026.02.8

-- === Bots registry ===

CREATE TABLE IF NOT EXISTS bots (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT UNIQUE NOT NULL,
    token TEXT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    can_join_groups BOOLEAN,
    can_read_all_group_messages BOOLEAN,
    supports_inline_queries BOOLEAN,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS bots_single_default_idx
    ON bots (is_default)
    WHERE is_default;

CREATE INDEX IF NOT EXISTS bots_active_idx
    ON bots (is_active, updated_at DESC);

CREATE INDEX IF NOT EXISTS bots_username_idx
    ON bots (username)
    WHERE username IS NOT NULL;

-- === Chat members (кто состоит в каких чатах) ===

CREATE TABLE IF NOT EXISTS chat_members (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    bot_id BIGINT,
    status TEXT,
    last_seen_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chat_id, user_id)
);

DO $$
BEGIN
    IF to_regclass('public.chat_members') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'chat_members_bot_id_fkey'
       ) THEN
        ALTER TABLE chat_members
            ADD CONSTRAINT chat_members_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS chat_members_chat_idx
    ON chat_members (chat_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS chat_members_user_idx
    ON chat_members (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS chat_members_bot_idx
    ON chat_members (bot_id, updated_at DESC)
    WHERE bot_id IS NOT NULL;

-- === API activity log ===

CREATE TABLE IF NOT EXISTS api_activity_log (
    id BIGSERIAL PRIMARY KEY,
    bot_id BIGINT,
    bot_username TEXT,
    action TEXT NOT NULL,
    chat_id TEXT,
    user_id TEXT,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

DO $$
BEGIN
    IF to_regclass('public.api_activity_log') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'api_activity_log_bot_id_fkey'
       ) THEN
        ALTER TABLE api_activity_log
            ADD CONSTRAINT api_activity_log_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS api_activity_log_bot_idx
    ON api_activity_log (bot_id, created_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS api_activity_log_chat_idx
    ON api_activity_log (chat_id, created_at DESC)
    WHERE chat_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS api_activity_log_action_idx
    ON api_activity_log (action, created_at DESC);

CREATE INDEX IF NOT EXISTS api_activity_log_status_idx
    ON api_activity_log (status, created_at DESC);

CREATE OR REPLACE FUNCTION cleanup_old_activity_logs(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM api_activity_log
    WHERE created_at < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- === Обогащение существующих таблиц ===

ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS alias TEXT;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS member_count INTEGER;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS invite_link TEXT;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS is_forum BOOLEAN;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS photo_file_id TEXT;

ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS alias TEXT;

ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS webhook_updates ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS bot_commands ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS callback_queries ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS polls ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS checklists ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS prediction_events ADD COLUMN IF NOT EXISTS bot_id BIGINT;
ALTER TABLE IF EXISTS webhook_config ADD COLUMN IF NOT EXISTS bot_id BIGINT;

DO $$
BEGIN
    IF to_regclass('public.chats') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'chats_bot_id_fkey'
       ) THEN
        ALTER TABLE chats
            ADD CONSTRAINT chats_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.messages') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'messages_bot_id_fkey'
       ) THEN
        ALTER TABLE messages
            ADD CONSTRAINT messages_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.webhook_updates') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'webhook_updates_bot_id_fkey'
       ) THEN
        ALTER TABLE webhook_updates
            ADD CONSTRAINT webhook_updates_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.bot_commands') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'bot_commands_bot_id_fkey'
       ) THEN
        ALTER TABLE bot_commands
            ADD CONSTRAINT bot_commands_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.callback_queries') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'callback_queries_bot_id_fkey'
       ) THEN
        ALTER TABLE callback_queries
            ADD CONSTRAINT callback_queries_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.polls') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'polls_bot_id_fkey'
       ) THEN
        ALTER TABLE polls
            ADD CONSTRAINT polls_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.checklists') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'checklists_bot_id_fkey'
       ) THEN
        ALTER TABLE checklists
            ADD CONSTRAINT checklists_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.prediction_events') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'prediction_events_bot_id_fkey'
       ) THEN
        ALTER TABLE prediction_events
            ADD CONSTRAINT prediction_events_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;

    IF to_regclass('public.webhook_config') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint WHERE conname = 'webhook_config_bot_id_fkey'
       ) THEN
        ALTER TABLE webhook_config
            ADD CONSTRAINT webhook_config_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE SET NULL;
    END IF;
END $$;

-- Уникальные алиасы и дефолты
CREATE UNIQUE INDEX IF NOT EXISTS chats_alias_unique_idx
    ON chats (alias)
    WHERE alias IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS users_alias_unique_idx
    ON users (alias)
    WHERE alias IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS chats_single_default_idx
    ON chats (is_default)
    WHERE is_default;

-- Индексы для bot_id-фильтрации
CREATE INDEX IF NOT EXISTS chats_bot_id_idx
    ON chats (bot_id, updated_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS messages_bot_id_idx
    ON messages (bot_id, created_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS webhook_updates_bot_id_idx
    ON webhook_updates (bot_id, received_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS bot_commands_bot_id_idx
    ON bot_commands (bot_id, updated_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS callback_queries_bot_id_idx
    ON callback_queries (bot_id, received_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS polls_bot_id_idx
    ON polls (bot_id, created_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS checklists_bot_id_idx
    ON checklists (bot_id, created_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS prediction_events_bot_id_idx
    ON prediction_events (bot_id, created_at DESC)
    WHERE bot_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS webhook_config_bot_id_idx
    ON webhook_config (bot_id, updated_at DESC)
    WHERE bot_id IS NOT NULL;

-- updated_at-триггеры
DROP TRIGGER IF EXISTS update_bots_updated_at ON bots;
CREATE TRIGGER update_bots_updated_at
    BEFORE UPDATE ON bots
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_chat_members_updated_at ON chat_members;
CREATE TRIGGER update_chat_members_updated_at
    BEFORE UPDATE ON chat_members
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
