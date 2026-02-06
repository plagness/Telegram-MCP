-- Миграция: Offset для updates в разрезе bot_id (мультибот polling)
-- Версия: 2026.02.9

ALTER TABLE IF EXISTS update_offset
    ADD COLUMN IF NOT EXISTS bot_id BIGINT;

DO $$
BEGIN
    IF to_regclass('public.update_offset') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'update_offset_bot_id_fkey'
       ) THEN
        ALTER TABLE update_offset
            ADD CONSTRAINT update_offset_bot_id_fkey
            FOREIGN KEY (bot_id) REFERENCES bots(bot_id) ON DELETE CASCADE;
    END IF;
END $$;

-- Удаляем дубликаты строк offset в рамках одного bot_id (включая NULL-контекст),
-- оставляя запись с максимальным offset и самым свежим updated_at.
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY bot_id
            ORDER BY "offset" DESC, updated_at DESC NULLS LAST, id DESC
        ) AS rn
    FROM update_offset
)
DELETE FROM update_offset
WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

-- Гарантируем наличие default-контекста (bot_id IS NULL) для обратной совместимости.
INSERT INTO update_offset ("offset", updated_at, bot_id)
SELECT
    COALESCE((SELECT MAX("offset") FROM update_offset), 0),
    NOW(),
    NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM update_offset
    WHERE bot_id IS NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS update_offset_bot_unique_idx
    ON update_offset (bot_id)
    WHERE bot_id IS NOT NULL;

-- В PostgreSQL NULL значения не уникальны, поэтому ограничиваем default-контекст выражением.
CREATE UNIQUE INDEX IF NOT EXISTS update_offset_default_unique_idx
    ON update_offset ((1))
    WHERE bot_id IS NULL;

CREATE INDEX IF NOT EXISTS update_offset_updated_idx
    ON update_offset (updated_at DESC);
