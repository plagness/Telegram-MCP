-- Миграция: Prediction Markets (ставки) + Stars Payments
-- Версия: 2026.02.7

-- === Stars Payments ===

CREATE TABLE IF NOT EXISTS star_transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    transaction_type TEXT NOT NULL, -- 'invoice', 'payment', 'refund', 'payout'
    amount INT NOT NULL, -- Сумма в Stars
    currency TEXT DEFAULT 'XTR',
    telegram_payment_charge_id TEXT UNIQUE,
    payload TEXT, -- Внутренний ID для идентификации
    status TEXT DEFAULT 'pending', -- 'pending', 'success', 'failed', 'refunded'
    metadata JSONB, -- Дополнительные данные (event_id, bet_id и т.д.)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_star_transactions_user ON star_transactions(user_id);
CREATE INDEX idx_star_transactions_charge ON star_transactions(telegram_payment_charge_id);
CREATE INDEX idx_star_transactions_payload ON star_transactions(payload);

-- === Prediction Markets ===

CREATE TABLE IF NOT EXISTS prediction_events (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    chat_id BIGINT, -- NULL = личное событие
    creator_id BIGINT NOT NULL,
    deadline TIMESTAMPTZ, -- Дедлайн для ставок
    resolution_date TIMESTAMPTZ, -- Дата разрешения (если фиксированная)
    min_bet INT DEFAULT 1,
    max_bet INT DEFAULT 1000,
    is_anonymous BOOLEAN DEFAULT TRUE, -- Обезличенные ставки
    status TEXT DEFAULT 'active', -- 'active', 'closed', 'resolved', 'cancelled'
    total_pool INT DEFAULT 0, -- Общий банк в Stars
    telegram_message_id BIGINT, -- ID сообщения в чате
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prediction_events_chat ON prediction_events(chat_id);
CREATE INDEX idx_prediction_events_status ON prediction_events(status);
CREATE INDEX idx_prediction_events_creator ON prediction_events(creator_id);

-- === Варианты ответов ===

CREATE TABLE IF NOT EXISTS prediction_options (
    id SERIAL PRIMARY KEY,
    event_id INT NOT NULL REFERENCES prediction_events(id) ON DELETE CASCADE,
    option_id TEXT NOT NULL, -- Уникальный ID варианта в рамках события
    text TEXT NOT NULL,
    value TEXT, -- Числовое значение (например, "16.5%")
    total_bets INT DEFAULT 0, -- Количество ставок
    total_amount INT DEFAULT 0, -- Общая сумма ставок на этот вариант
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_id, option_id)
);

CREATE INDEX idx_prediction_options_event ON prediction_options(event_id);

-- === Ставки пользователей ===

CREATE TABLE IF NOT EXISTS prediction_bets (
    id SERIAL PRIMARY KEY,
    event_id INT NOT NULL REFERENCES prediction_events(id) ON DELETE CASCADE,
    option_id TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    amount INT NOT NULL, -- Сумма ставки в Stars
    payout INT DEFAULT 0, -- Выплата при выигрыше
    status TEXT DEFAULT 'active', -- 'active', 'won', 'lost', 'refunded'
    transaction_id INT REFERENCES star_transactions(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prediction_bets_event ON prediction_bets(event_id);
CREATE INDEX idx_prediction_bets_user ON prediction_bets(user_id);
CREATE INDEX idx_prediction_bets_option ON prediction_bets(event_id, option_id);

-- === Разрешения событий ===

CREATE TABLE IF NOT EXISTS prediction_resolutions (
    id SERIAL PRIMARY KEY,
    event_id INT NOT NULL REFERENCES prediction_events(id) ON DELETE CASCADE,
    winning_option_ids TEXT[] NOT NULL, -- Массив ID победивших вариантов
    resolution_source TEXT NOT NULL, -- 'llm-mcp', 'ollama', 'openrouter', 'manual'
    resolution_data JSONB, -- Данные от LLM/новости
    resolver_id BIGINT, -- ID пользователя (если manual)
    total_winners INT DEFAULT 0, -- Количество победителей
    total_payout INT DEFAULT 0, -- Общая выплата
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prediction_resolutions_event ON prediction_resolutions(event_id);

-- === LLM Resolution Config ===

CREATE TABLE IF NOT EXISTS prediction_llm_config (
    id SERIAL PRIMARY KEY,
    event_id INT NOT NULL REFERENCES prediction_events(id) ON DELETE CASCADE,
    provider TEXT NOT NULL, -- 'llm-mcp', 'ollama', 'openrouter'
    model TEXT, -- Модель (например, "llama3.3:70b" для Ollama)
    check_dates TIMESTAMPTZ[], -- Даты для проверки новостей (если событие без фиксированной даты)
    news_sources TEXT[], -- Источники новостей для агрегации (через channel-mcp)
    resolution_prompt TEXT, -- Промпт для LLM
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prediction_llm_config_event ON prediction_llm_config(event_id);
