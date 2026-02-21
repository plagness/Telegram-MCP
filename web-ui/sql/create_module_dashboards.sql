-- Создание owner-only дашбордов для всех подключённых модулей.
-- Запускать после деплоя web-ui с новыми шаблонами.
-- Все страницы доступны только пользователям с ролью project_owner.

INSERT INTO web_pages (slug, page_type, title, config, is_active, created_at, updated_at)
VALUES
(
    'channel-dashboard',
    'channel',
    'Channel Monitor',
    '{"description": "Мониторинг Telegram-каналов: свежесть данных, теги, объём сообщений", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "telegram"}'::jsonb,
    true,
    NOW(),
    NOW()
),
(
    'bcs-dashboard',
    'bcs',
    'Trading Dashboard',
    '{"description": "Портфель BCS, активные заявки, рыночные котировки", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "tradingview"}'::jsonb,
    true,
    NOW(),
    NOW()
),
(
    'arena-dashboard',
    'arena',
    'Arena LLM',
    '{"description": "Матчи моделей, лидерборд, виды, зависимости", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "probot"}'::jsonb,
    true,
    NOW(),
    NOW()
),
(
    'planner-dashboard',
    'planner',
    'Planner',
    '{"description": "Задачи, бюджет, speed mode, расписания, модули", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "todoist"}'::jsonb,
    true,
    NOW(),
    NOW()
),
(
    'metrics-dashboard',
    'metrics',
    'Market & Infra',
    '{"description": "Курсы валют, биржевые индексы, здоровье инфраструктуры", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "grafana"}'::jsonb,
    true,
    NOW(),
    NOW()
),
(
    'k8s-dashboard',
    'k8s',
    'K8s Cluster',
    '{"description": "Поды кластера, статусы, рестарты, Neurobot", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "kubernetes"}'::jsonb,
    true,
    NOW(),
    NOW()
),
(
    'integrat-dashboard',
    'datesale',
    'Integrat',
    '{"description": "Маркетплейс данных: плагины, настройка, подключение к чатам", "access_rules": {"allowed_roles": ["project_owner"]}, "icon": "zapier"}'::jsonb,
    true,
    NOW(),
    NOW()
)
ON CONFLICT (slug) DO UPDATE SET
    page_type = EXCLUDED.page_type,
    title = EXCLUDED.title,
    config = EXCLUDED.config,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();
