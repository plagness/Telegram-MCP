-- Расширение профилей v2: бизнес-поля + кеш кастомных эмодзи

-- === users: бизнес-поля из ChatFullInfo (getChat) ===
ALTER TABLE users ADD COLUMN IF NOT EXISTS business_intro JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS business_location JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS business_work_hours JSONB;

-- === Кеш кастомных эмодзи (для emoji_status) ===
CREATE TABLE IF NOT EXISTS custom_emoji_cache (
    custom_emoji_id TEXT PRIMARY KEY,
    emoji TEXT,
    file_id TEXT,
    local_path TEXT,
    is_animated BOOLEAN DEFAULT FALSE,
    fetched_at TIMESTAMPTZ DEFAULT NOW()
);
