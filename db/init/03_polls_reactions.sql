-- Миграция: Опросы и реакции

-- Таблица опросов
CREATE TABLE IF NOT EXISTS polls (
    id BIGSERIAL PRIMARY KEY,
    poll_id TEXT UNIQUE NOT NULL,
    message_id BIGINT REFERENCES messages(id) ON DELETE CASCADE,
    chat_id TEXT NOT NULL,
    telegram_message_id BIGINT,
    question TEXT NOT NULL,
    options JSONB NOT NULL,
    type TEXT NOT NULL DEFAULT 'regular',
    is_anonymous BOOLEAN DEFAULT TRUE,
    allows_multiple_answers BOOLEAN DEFAULT FALSE,
    correct_option_id INT,
    explanation TEXT,
    explanation_entities JSONB,
    open_period INT,
    close_date TIMESTAMPTZ,
    is_closed BOOLEAN DEFAULT FALSE,
    total_voter_count INT DEFAULT 0,
    results JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS polls_poll_id_idx ON polls (poll_id);
CREATE INDEX IF NOT EXISTS polls_message_id_idx ON polls (message_id);
CREATE INDEX IF NOT EXISTS polls_chat_id_idx ON polls (chat_id);

-- Таблица ответов на опросы
CREATE TABLE IF NOT EXISTS poll_answers (
    id BIGSERIAL PRIMARY KEY,
    poll_id TEXT NOT NULL REFERENCES polls(poll_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    option_ids INT[] NOT NULL,
    answered_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS poll_answers_poll_id_idx ON poll_answers (poll_id);
CREATE INDEX IF NOT EXISTS poll_answers_user_id_idx ON poll_answers (user_id);

-- Таблица реакций на сообщения
CREATE TABLE IF NOT EXISTS message_reactions (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL,
    chat_id TEXT NOT NULL,
    telegram_message_id BIGINT NOT NULL,
    user_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL,
    reaction_emoji TEXT,
    reaction_custom_emoji_id TEXT,
    date TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (chat_id, telegram_message_id, user_id, reaction_type, reaction_emoji, reaction_custom_emoji_id)
);

CREATE INDEX IF NOT EXISTS message_reactions_message_idx ON message_reactions (message_id);
CREATE INDEX IF NOT EXISTS message_reactions_chat_msg_idx ON message_reactions (chat_id, telegram_message_id);
CREATE INDEX IF NOT EXISTS message_reactions_user_idx ON message_reactions (user_id);
