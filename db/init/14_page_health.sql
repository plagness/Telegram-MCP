-- История health-check'ов веб-страниц
CREATE TABLE IF NOT EXISTS web_page_health (
    id BIGSERIAL PRIMARY KEY,
    page_id BIGINT NOT NULL REFERENCES web_pages(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    status TEXT NOT NULL,          -- 'ok', 'error', 'timeout'
    status_code INT,
    response_time_ms INT,
    error_message TEXT,
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wph_slug
    ON web_page_health(slug, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_wph_status
    ON web_page_health(status) WHERE status != 'ok';
