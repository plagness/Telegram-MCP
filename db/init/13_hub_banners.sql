-- Промо-баннеры для Hub
CREATE TABLE IF NOT EXISTS hub_banners (
    id BIGSERIAL PRIMARY KEY,
    tg_username TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    link TEXT NOT NULL,
    avatar_file TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    target_roles JSONB DEFAULT '[]',
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hub_banners_active
    ON hub_banners (is_active, priority DESC)
    WHERE is_active = TRUE;
