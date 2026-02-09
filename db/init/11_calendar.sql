-- 11_calendar.sql — Модуль «Календарь» для ИИ-планировщика

-- Контейнеры-календари
CREATE TABLE IF NOT EXISTS calendars (
    id BIGSERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    owner_id BIGINT,
    chat_id TEXT,
    bot_id BIGINT REFERENCES bots(bot_id) ON DELETE SET NULL,
    timezone TEXT DEFAULT 'UTC',
    is_public BOOLEAN DEFAULT TRUE,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calendars_slug ON calendars(slug);
CREATE INDEX IF NOT EXISTS idx_calendars_chat ON calendars(chat_id) WHERE chat_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendars_owner ON calendars(owner_id) WHERE owner_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendars_bot ON calendars(bot_id) WHERE bot_id IS NOT NULL;

-- Записи/карточки календаря
CREATE TABLE IF NOT EXISTS calendar_entries (
    id BIGSERIAL PRIMARY KEY,
    calendar_id BIGINT NOT NULL REFERENCES calendars(id) ON DELETE CASCADE,
    parent_id BIGINT REFERENCES calendar_entries(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ,
    all_day BOOLEAN DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'active',
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    color TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    attachments JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    series_id TEXT,
    repeat TEXT CHECK (repeat IN ('daily', 'weekly', 'biweekly', 'monthly', 'yearly', 'weekdays')),
    repeat_until TIMESTAMPTZ,
    position INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    ai_actionable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cal_entries_calendar_start ON calendar_entries(calendar_id, start_at);
CREATE INDEX IF NOT EXISTS idx_cal_entries_calendar_status ON calendar_entries(calendar_id, status);
CREATE INDEX IF NOT EXISTS idx_cal_entries_tags ON calendar_entries USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_cal_entries_parent ON calendar_entries(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cal_entries_series ON calendar_entries(series_id) WHERE series_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cal_entries_sort ON calendar_entries(calendar_id, start_at, position);

-- Лог изменений записей
CREATE TABLE IF NOT EXISTS calendar_entry_history (
    id BIGSERIAL PRIMARY KEY,
    entry_id BIGINT NOT NULL REFERENCES calendar_entries(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    changes JSONB NOT NULL DEFAULT '{}',
    performed_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cal_history_entry ON calendar_entry_history(entry_id, created_at DESC);

-- Триггер автообновления updated_at
CREATE OR REPLACE FUNCTION update_cal_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_calendars_updated_at'
    ) THEN
        CREATE TRIGGER trg_calendars_updated_at
            BEFORE UPDATE ON calendars
            FOR EACH ROW EXECUTE FUNCTION update_cal_updated_at();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_cal_entries_updated_at'
    ) THEN
        CREATE TRIGGER trg_cal_entries_updated_at
            BEFORE UPDATE ON calendar_entries
            FOR EACH ROW EXECUTE FUNCTION update_cal_updated_at();
    END IF;
END $$;

-- Эмодзи для визуального обозначения события
ALTER TABLE calendar_entries ADD COLUMN IF NOT EXISTS emoji TEXT;
