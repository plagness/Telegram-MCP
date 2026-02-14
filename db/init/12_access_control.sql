-- 12_access_control.sql — Глобальные роли пользователей для контроля доступа

-- Роли: project_owner, tester, backend_dev, moderator и т.д.
-- Используются в web_pages.config.access_rules.allowed_roles
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    granted_by BIGINT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, role)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role ON user_roles(role);

COMMENT ON TABLE user_roles IS 'Глобальные роли: project_owner, tester, backend_dev, moderator';
COMMENT ON COLUMN user_roles.role IS 'Название роли (project_owner, tester, backend_dev, moderator)';
COMMENT ON COLUMN user_roles.granted_by IS 'Кто назначил роль (user_id)';
COMMENT ON COLUMN user_roles.note IS 'Комментарий к назначению';
