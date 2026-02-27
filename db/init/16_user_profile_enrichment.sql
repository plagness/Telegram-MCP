-- Обогащение профилей пользователей: новые поля из Telegram Bot API v9.4

-- === users: поля из User object (webhook) ===
ALTER TABLE users ADD COLUMN IF NOT EXISTS added_to_attachment_menu BOOLEAN;

-- === users: поля из WebAppUser (initData) ===
ALTER TABLE users ADD COLUMN IF NOT EXISTS allows_write_to_pm BOOLEAN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url TEXT;

-- === users: поля из ChatFullInfo (getChat API) ===
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate_day SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate_month SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate_year SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS accent_color_id SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_accent_color_id SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS emoji_status_custom_emoji_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS emoji_status_expiration_date TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS personal_chat_id BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS has_private_forwards BOOLEAN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_level SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_value INTEGER;

-- === users: собственные метрики ===
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0;

-- Backfill first_seen_at из created_at
UPDATE users SET first_seen_at = created_at WHERE first_seen_at IS NULL;

-- === chat_members: расширенные поля из ChatMember ===
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS custom_title TEXT;
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS is_anonymous BOOLEAN;
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS until_date TIMESTAMPTZ;
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS permissions JSONB;
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0;
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ;

-- Backfill first_seen_at из created_at
UPDATE chat_members SET first_seen_at = created_at WHERE first_seen_at IS NULL;

-- Индекс для поиска по дню рождения (поздравления)
CREATE INDEX IF NOT EXISTS idx_users_birthdate
    ON users (birthdate_month, birthdate_day)
    WHERE birthdate_day IS NOT NULL;

-- Индекс для рейтинга
CREATE INDEX IF NOT EXISTS idx_users_rating
    ON users (rating_level DESC NULLS LAST, rating_value DESC NULLS LAST)
    WHERE rating_level IS NOT NULL;

-- Backfill message_count из существующих сообщений (user_id извлекается из payload_json)
UPDATE users u SET message_count = sub.cnt
FROM (
    SELECT (payload_json->'from'->>'id')::text AS uid, COUNT(*) AS cnt
    FROM messages
    WHERE direction = 'inbound' AND payload_json->'from'->>'id' IS NOT NULL
    GROUP BY (payload_json->'from'->>'id')::text
) sub
WHERE u.user_id = sub.uid AND u.message_count = 0;

UPDATE chat_members cm SET message_count = sub.cnt
FROM (
    SELECT chat_id, (payload_json->'from'->>'id')::text AS uid, COUNT(*) AS cnt
    FROM messages
    WHERE direction = 'inbound' AND payload_json->'from'->>'id' IS NOT NULL
    GROUP BY chat_id, (payload_json->'from'->>'id')::text
) sub
WHERE cm.chat_id = sub.chat_id AND cm.user_id = sub.uid AND cm.message_count = 0;
