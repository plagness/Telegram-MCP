-- 10_web_ui.sql — Таблицы для модуля web-ui (Telegram Mini App)

-- Веб-страницы (prediction, survey, page)
CREATE TABLE IF NOT EXISTS web_pages (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    page_type TEXT NOT NULL DEFAULT 'page',  -- page | survey | prediction
    title TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}',
    template TEXT,
    creator_id BIGINT,
    bot_id BIGINT REFERENCES bots(bot_id),
    event_id BIGINT REFERENCES prediction_events(id),
    is_active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Индивидуальные ссылки на страницы
CREATE TABLE IF NOT EXISTS web_page_links (
    id BIGSERIAL PRIMARY KEY,
    page_id BIGINT NOT NULL REFERENCES web_pages(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    user_id BIGINT,
    chat_id BIGINT,
    metadata JSONB DEFAULT '{}',
    used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Ответы на формы / предсказания
CREATE TABLE IF NOT EXISTS web_form_submissions (
    id BIGSERIAL PRIMARY KEY,
    page_id BIGINT NOT NULL REFERENCES web_pages(id) ON DELETE CASCADE,
    link_id BIGINT REFERENCES web_page_links(id),
    user_id BIGINT NOT NULL,
    data JSONB NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Привязка TON-кошельков к Telegram-аккаунтам
CREATE TABLE IF NOT EXISTS web_wallet_links (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    wallet_address TEXT NOT NULL,
    chain TEXT DEFAULT 'ton-mainnet',
    linked_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, wallet_address)
);

CREATE INDEX IF NOT EXISTS idx_web_pages_slug ON web_pages(slug);
CREATE INDEX IF NOT EXISTS idx_web_pages_event ON web_pages(event_id);
CREATE INDEX IF NOT EXISTS idx_web_page_links_token ON web_page_links(token);
CREATE INDEX IF NOT EXISTS idx_web_form_submissions_page ON web_form_submissions(page_id);
CREATE INDEX IF NOT EXISTS idx_web_wallet_links_user ON web_wallet_links(user_id);
