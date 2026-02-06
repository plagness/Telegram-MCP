-- Миграция: Виртуальные балансы и состояния пользователей для Prediction Markets

-- Таблица балансов пользователей
CREATE TABLE IF NOT EXISTS user_balances (
    user_id BIGINT PRIMARY KEY,
    balance INTEGER DEFAULT 0 CHECK (balance >= 0),
    total_deposited INTEGER DEFAULT 0,
    total_won INTEGER DEFAULT 0,
    total_lost INTEGER DEFAULT 0,
    total_withdrawn INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_user_balances_balance ON user_balances(balance DESC);
CREATE INDEX idx_user_balances_updated ON user_balances(updated_at DESC);

COMMENT ON TABLE user_balances IS 'Виртуальные балансы пользователей в Stars';
COMMENT ON COLUMN user_balances.balance IS 'Текущий баланс в Stars';
COMMENT ON COLUMN user_balances.total_deposited IS 'Всего внесено через платежи';
COMMENT ON COLUMN user_balances.total_won IS 'Всего выиграно';
COMMENT ON COLUMN user_balances.total_lost IS 'Всего проиграно';


-- Таблица состояний пользователей (для FSM)
CREATE TABLE IF NOT EXISTS user_states (
    user_id BIGINT PRIMARY KEY,
    state TEXT NOT NULL,
    data JSONB DEFAULT '{}',
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_user_states_expires ON user_states(expires_at) WHERE expires_at IS NOT NULL;

COMMENT ON TABLE user_states IS 'Состояния пользователей для Finite State Machine';
COMMENT ON COLUMN user_states.state IS 'Текущее состояние (waiting_bet_amount, etc)';
COMMENT ON COLUMN user_states.data IS 'Данные состояния в JSON';
COMMENT ON COLUMN user_states.expires_at IS 'Время истечения состояния';


-- Добавить колонки в prediction_events для комиссии
ALTER TABLE prediction_events ADD COLUMN IF NOT EXISTS commission_rate DECIMAL(4,3) DEFAULT 0.05;
ALTER TABLE prediction_events ADD COLUMN IF NOT EXISTS bot_commission INTEGER DEFAULT 0;

COMMENT ON COLUMN prediction_events.commission_rate IS 'Процент комиссии бота (0.05 = 5%)';
COMMENT ON COLUMN prediction_events.bot_commission IS 'Накопленная комиссия бота с этого события';


-- Изменить минимальную ставку по умолчанию на 10
ALTER TABLE prediction_events ALTER COLUMN min_bet SET DEFAULT 10;


-- Добавить source в prediction_bets (balance/payment)
ALTER TABLE prediction_bets ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'payment';

COMMENT ON COLUMN prediction_bets.source IS 'Источник ставки: balance (с баланса) или payment (через invoice)';


-- Таблица истории транзакций баланса
CREATE TABLE IF NOT EXISTS balance_transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    balance_before INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,  -- deposit, win, loss, refund, withdrawal
    reference_type TEXT,  -- bet, event, payment, etc
    reference_id INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_balance_tx_user ON balance_transactions(user_id, created_at DESC);
CREATE INDEX idx_balance_tx_type ON balance_transactions(transaction_type);
CREATE INDEX idx_balance_tx_reference ON balance_transactions(reference_type, reference_id);

COMMENT ON TABLE balance_transactions IS 'История всех операций с балансом пользователей';


-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггеры для updated_at
DROP TRIGGER IF EXISTS update_user_balances_updated_at ON user_balances;
CREATE TRIGGER update_user_balances_updated_at
    BEFORE UPDATE ON user_balances
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_states_updated_at ON user_states;
CREATE TRIGGER update_user_states_updated_at
    BEFORE UPDATE ON user_states
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
