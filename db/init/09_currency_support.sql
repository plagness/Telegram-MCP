-- Миграция: Мультивалютная поддержка ставок
-- Версия: 2026.02.8
--
-- Добавляет поддержку нескольких валют в системе ставок:
-- - XTR (Stars) — реальная валюта Telegram
-- - AC (Arena Coin) — виртуальная валюта для игровых арен
-- - TON — криптовалюта (будущее)

-- ---------------------------------------------------------------------------
-- 1. Валюта в prediction_events
-- ---------------------------------------------------------------------------

ALTER TABLE prediction_events
    ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'XTR';

COMMENT ON COLUMN prediction_events.currency
    IS 'Валюта ставок события: XTR (Stars), AC (виртуальная), TON (будущее)';

-- ---------------------------------------------------------------------------
-- 2. Валюта в prediction_bets (для истории)
-- ---------------------------------------------------------------------------

ALTER TABLE prediction_bets
    ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'XTR';

COMMENT ON COLUMN prediction_bets.currency
    IS 'Валюта конкретной ставки (наследуется от события)';

-- ---------------------------------------------------------------------------
-- 3. Начальный баланс AC: автоматическое создание при первой ставке
-- ---------------------------------------------------------------------------

-- Функция для автоматического создания баланса с начальными AC
CREATE OR REPLACE FUNCTION ensure_user_balance(p_user_id BIGINT, p_initial_balance INTEGER DEFAULT 100)
RETURNS INTEGER AS $$
DECLARE
    v_balance INTEGER;
BEGIN
    SELECT balance INTO v_balance FROM user_balances WHERE user_id = p_user_id;

    IF NOT FOUND THEN
        INSERT INTO user_balances (user_id, balance, total_deposited)
        VALUES (p_user_id, p_initial_balance, p_initial_balance)
        ON CONFLICT (user_id) DO NOTHING
        RETURNING balance INTO v_balance;

        -- Записать транзакцию начального баланса
        IF v_balance IS NOT NULL THEN
            INSERT INTO balance_transactions
                (user_id, amount, balance_before, balance_after,
                 transaction_type, description)
            VALUES
                (p_user_id, p_initial_balance, 0, p_initial_balance,
                 'initial', 'Начальный баланс AC');
        END IF;
    END IF;

    RETURN COALESCE(v_balance, 0);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION ensure_user_balance IS 'Создаёт баланс пользователя с начальными AC, если его ещё нет';

-- ---------------------------------------------------------------------------
-- 4. Справочная таблица валют
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS currencies (
    code TEXT PRIMARY KEY,           -- 'XTR', 'AC', 'TON'
    display_name TEXT NOT NULL,
    symbol TEXT NOT NULL,             -- '⭐', '🪙', '💎'
    is_virtual BOOLEAN NOT NULL DEFAULT TRUE,
    initial_balance INTEGER NOT NULL DEFAULT 0,  -- стартовый баланс при регистрации
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Начальные валюты
INSERT INTO currencies (code, display_name, symbol, is_virtual, initial_balance, active)
VALUES
    ('XTR', 'Telegram Stars', '⭐', FALSE, 0, TRUE),
    ('AC', 'Arena Coin', '🪙', TRUE, 100, TRUE),
    ('TON', 'Toncoin', '💎', FALSE, 0, FALSE)
ON CONFLICT (code) DO NOTHING;

COMMENT ON TABLE currencies IS 'Справочник поддерживаемых валют для ставок';
