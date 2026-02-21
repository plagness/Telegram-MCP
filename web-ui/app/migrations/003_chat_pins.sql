-- Таблица chat_pins: живые закрепы в Telegram-чатах
-- Каждый чат может иметь один закреп с динамическим контентом (текст + картинка)
-- Обновляется по cron или по событиям от модулей (Democracy, плагины)

CREATE TABLE IF NOT EXISTS chat_pins (
    chat_id         TEXT PRIMARY KEY REFERENCES chats(chat_id),
    message_id      BIGINT,                         -- telegram_message_id закрепа
    pin_type        TEXT NOT NULL DEFAULT 'default', -- 'default', 'democracy', 'chart', 'custom'
    pin_data        JSONB NOT NULL DEFAULT '{}',     -- данные для шаблона
    image_url       TEXT,                            -- путь к сгенерированной картинке
    last_text       TEXT,                            -- последний отправленный текст
    last_updated    TIMESTAMPTZ,
    auto_update     BOOLEAN NOT NULL DEFAULT TRUE,   -- автообновление через cron
    update_interval INT NOT NULL DEFAULT 3600,       -- интервал обновления в секундах
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE chat_pins IS 'Живые закрепы (pinned messages) в Telegram-чатах с динамическим контентом';
COMMENT ON COLUMN chat_pins.pin_type IS 'Тип шаблона: default (базовый), democracy (governance), chart (график), custom';
COMMENT ON COLUMN chat_pins.pin_data IS 'JSON-данные для рендера: зависят от pin_type (заголовок, метрики, граждане и т.д.)';
COMMENT ON COLUMN chat_pins.update_interval IS 'Интервал автообновления в секундах (минимум 60)';
