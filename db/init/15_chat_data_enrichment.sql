-- Обогащение данных чатов: метаданные сообщений, системные события, аватарки, Hub настройки

-- === Расширение messages метаданными ===
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS media_type TEXT;
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS caption TEXT;
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS forward_origin JSONB;
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS sender_chat_id TEXT;
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS entities JSONB;
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS has_media BOOLEAN DEFAULT FALSE;
ALTER TABLE IF EXISTS messages ADD COLUMN IF NOT EXISTS is_topic_message BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_messages_media_type
    ON messages (media_type, created_at DESC) WHERE media_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_sender_chat
    ON messages (sender_chat_id, created_at DESC) WHERE sender_chat_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_messages_has_media
    ON messages (chat_id, created_at DESC) WHERE has_media = TRUE;

-- === Системные события чата ===
CREATE TABLE IF NOT EXISTS chat_events (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL,
    bot_id BIGINT,
    event_type TEXT NOT NULL,
    actor_user_id TEXT,
    target_user_id TEXT,
    telegram_message_id BIGINT,
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_events_chat
    ON chat_events (chat_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_events_type
    ON chat_events (event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_events_actor
    ON chat_events (actor_user_id, created_at DESC)
    WHERE actor_user_id IS NOT NULL;

-- === Аватарки (локальное хранение) ===
CREATE TABLE IF NOT EXISTS avatars (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    file_id TEXT,
    local_path TEXT,
    is_custom BOOLEAN DEFAULT FALSE,
    fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_avatars_entity
    ON avatars (entity_type, entity_id);

-- === Расширение users: photo_file_id ===
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS photo_file_id TEXT;

-- === Hub настройки чата ===
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS hub_description TEXT;
ALTER TABLE IF EXISTS chats ADD COLUMN IF NOT EXISTS hub_links JSONB DEFAULT '[]';

-- === Backfill: парсинг метаданных из payload_json для существующих сообщений ===
UPDATE messages SET
    media_type = CASE
        WHEN payload_json ? 'photo' THEN 'photo'
        WHEN payload_json ? 'video' THEN 'video'
        WHEN payload_json ? 'document' THEN 'document'
        WHEN payload_json ? 'audio' THEN 'audio'
        WHEN payload_json ? 'voice' THEN 'voice'
        WHEN payload_json ? 'sticker' THEN 'sticker'
        WHEN payload_json ? 'animation' THEN 'animation'
        WHEN payload_json ? 'video_note' THEN 'video_note'
        WHEN payload_json ? 'contact' THEN 'contact'
        WHEN payload_json ? 'location' THEN 'location'
        WHEN payload_json ? 'venue' THEN 'venue'
        WHEN payload_json ? 'poll' THEN 'poll'
        WHEN payload_json ? 'dice' THEN 'dice'
        ELSE NULL
    END,
    caption = payload_json ->> 'caption',
    forward_origin = CASE
        WHEN payload_json ? 'forward_origin' THEN payload_json -> 'forward_origin'
        WHEN payload_json ? 'forward_from' THEN jsonb_build_object('type', 'user', 'sender_user', payload_json -> 'forward_from')
        WHEN payload_json ? 'forward_from_chat' THEN jsonb_build_object('type', 'channel', 'chat', payload_json -> 'forward_from_chat')
        ELSE NULL
    END,
    sender_chat_id = CASE
        WHEN payload_json -> 'sender_chat' IS NOT NULL THEN (payload_json -> 'sender_chat' ->> 'id')
        ELSE NULL
    END,
    entities = CASE
        WHEN payload_json ? 'entities' THEN payload_json -> 'entities'
        WHEN payload_json ? 'caption_entities' THEN payload_json -> 'caption_entities'
        ELSE NULL
    END,
    has_media = (
        payload_json ? 'photo' OR payload_json ? 'video' OR payload_json ? 'document' OR
        payload_json ? 'audio' OR payload_json ? 'voice' OR payload_json ? 'sticker' OR
        payload_json ? 'animation' OR payload_json ? 'video_note'
    ),
    is_topic_message = COALESCE((payload_json ->> 'is_topic_message')::boolean, FALSE)
WHERE media_type IS NULL AND payload_json IS NOT NULL;
