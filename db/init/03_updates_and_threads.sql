-- Миграция 03: Updates/Polling + Message Threading + Priority Queue
-- Дата: 2025-02-06
-- Версия: 2025.03.1

-- ═══════════════════════════════════════════════════════════════════════════════
-- MESSAGE THREADING (поддержка топиков/форумов)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Добавляем message_thread_id во все таблицы сообщений
ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_thread_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(chat_id, message_thread_id) WHERE message_thread_id IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════════════════════
-- UPDATES PROCESSING (обработка входящих обновлений)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Добавляем флаг обработки для вебхуков
ALTER TABLE updates ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE;
ALTER TABLE updates ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_updates_processed ON updates(processed, created_at) WHERE NOT processed;

-- Таблица для offset (long polling)
CREATE TABLE IF NOT EXISTS update_offset (
    id SERIAL PRIMARY KEY,
    offset INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Инициализируем offset (если таблица пустая)
INSERT INTO update_offset (offset) VALUES (0) ON CONFLICT DO NOTHING;

-- ═══════════════════════════════════════════════════════════════════════════════
-- CHAT ACTIONS (typing индикаторы)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS chat_actions (
    id SERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    message_thread_id INTEGER,
    action TEXT NOT NULL, -- typing, upload_photo, record_video, etc.
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ -- actions expire after 5 seconds
);

CREATE INDEX IF NOT EXISTS idx_chat_actions_chat ON chat_actions(chat_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_chat_actions_expires ON chat_actions(expires_at) WHERE expires_at IS NOT NULL;

-- Автоочистка старых actions (> 1 минуты)
CREATE OR REPLACE FUNCTION cleanup_old_chat_actions() RETURNS void AS $$
BEGIN
    DELETE FROM chat_actions WHERE sent_at < NOW() - INTERVAL '1 minute';
END;
$$ LANGUAGE plpgsql;

-- ═══════════════════════════════════════════════════════════════════════════════
-- PRIORITY QUEUE (приоритизация запросов)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS request_queue (
    id SERIAL PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 3, -- 1=lowest, 5=critical
    source TEXT, -- llm-mcp, channel-mcp, jobs, etc.
    method TEXT NOT NULL, -- sendMessage, sendPhoto, etc.
    payload JSONB NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error TEXT,
    result JSONB
);

CREATE INDEX IF NOT EXISTS idx_request_queue_priority ON request_queue(priority DESC, created_at ASC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_request_queue_source ON request_queue(source, status);
CREATE INDEX IF NOT EXISTS idx_request_queue_status ON request_queue(status, created_at);

-- ═══════════════════════════════════════════════════════════════════════════════
-- COMMAND SCOPES (расширенные скоупы для per-user команд)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Добавляем user_id для chat_member scope
ALTER TABLE command_sets ADD COLUMN IF NOT EXISTS user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_command_sets_user ON command_sets(scope_type, chat_id, user_id) WHERE user_id IS NOT NULL;

-- Таблица для отслеживания видимости команд по юзерам
CREATE TABLE IF NOT EXISTS user_command_visibility (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    chat_id TEXT,
    command TEXT NOT NULL,
    visible BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, chat_id, command)
);

CREATE INDEX IF NOT EXISTS idx_user_command_visibility_user ON user_command_visibility(user_id, chat_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- MEDIA EXTENSIONS (расширенные типы медиа)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Расширяем enum message_type (если используется)
-- ALTER TYPE message_type ADD VALUE IF NOT EXISTS 'animation';
-- Поскольку это TEXT, просто документируем новые типы:
-- Поддерживаемые типы: text, photo, document, video, animation, audio, voice, video_note, sticker, location, contact, dice

ALTER TABLE messages ADD COLUMN IF NOT EXISTS animation_file_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS audio_file_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS voice_file_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS video_note_file_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sticker_file_id TEXT;

-- Для sendMediaGroup (альбомы)
CREATE TABLE IF NOT EXISTS media_groups (
    id SERIAL PRIMARY KEY,
    media_group_id TEXT NOT NULL UNIQUE, -- Telegram media_group_id
    chat_id TEXT NOT NULL,
    message_ids INTEGER[] NOT NULL, -- Массив message_id
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_media_groups_chat ON media_groups(chat_id, created_at);

-- ═══════════════════════════════════════════════════════════════════════════════
-- INLINE QUERY (для inline mode)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS inline_queries (
    id SERIAL PRIMARY KEY,
    inline_query_id TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    query TEXT,
    offset TEXT,
    chat_type TEXT,
    location_latitude DOUBLE PRECISION,
    location_longitude DOUBLE PRECISION,
    answered BOOLEAN DEFAULT FALSE,
    answered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inline_queries_user ON inline_queries(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_inline_queries_answered ON inline_queries(answered, created_at) WHERE NOT answered;

-- ═══════════════════════════════════════════════════════════════════════════════
-- CHECKLISTS (Bot API 9.2)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS checklists (
    id SERIAL PRIMARY KEY,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    title TEXT,
    tasks JSONB NOT NULL, -- [{"text": "...", "completed": false}, ...]
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checklists_message ON checklists(message_id);
CREATE INDEX IF NOT EXISTS idx_checklists_chat ON checklists(chat_id, created_at);

-- ═══════════════════════════════════════════════════════════════════════════════
-- ФУНКЦИИ И ТРИГГЕРЫ
-- ═══════════════════════════════════════════════════════════════════════════════

-- Функция для получения следующего приоритетного запроса
CREATE OR REPLACE FUNCTION get_next_request() RETURNS request_queue AS $$
DECLARE
    req request_queue;
BEGIN
    UPDATE request_queue
    SET status = 'processing', started_at = NOW()
    WHERE id = (
        SELECT id FROM request_queue
        WHERE status = 'pending'
        ORDER BY priority DESC, created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING * INTO req;

    RETURN req;
END;
$$ LANGUAGE plpgsql;

-- Автоматическое обновление updated_at
CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для checklists
DROP TRIGGER IF EXISTS checklists_updated_at ON checklists;
CREATE TRIGGER checklists_updated_at
    BEFORE UPDATE ON checklists
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Триггер для user_command_visibility
DROP TRIGGER IF EXISTS user_command_visibility_updated_at ON user_command_visibility;
CREATE TRIGGER user_command_visibility_updated_at
    BEFORE UPDATE ON user_command_visibility
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ═══════════════════════════════════════════════════════════════════════════════
-- КОММЕНТАРИИ
-- ═══════════════════════════════════════════════════════════════════════════════

COMMENT ON TABLE update_offset IS 'Offset для long polling (getUpdates)';
COMMENT ON TABLE chat_actions IS 'История sendChatAction (typing индикаторы)';
COMMENT ON TABLE request_queue IS 'Очередь запросов с приоритизацией';
COMMENT ON TABLE user_command_visibility IS 'Видимость команд по юзерам (per-user команды)';
COMMENT ON TABLE media_groups IS 'Альбомы фото/видео (sendMediaGroup)';
COMMENT ON TABLE inline_queries IS 'Inline queries для inline mode';
COMMENT ON TABLE checklists IS 'Чеклисты (Bot API 9.2)';
