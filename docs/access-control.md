# Access Control

## Статус: Реализовано (v2026.02.19)

Система контроля доступа для Telegram Mini App страниц.

---

## Архитектура

Единая точка проверки — `check_page_access(user_id, page)` в `web-ui/app/services/access.py`.

**Логика (OR):** доступ если выполняется ХОТЯ БЫ одно условие:

1. `access_rules.public == true` → доступно всем
2. `user_id` в `access_rules.allowed_users` → прямой доступ
3. У пользователя есть роль из `access_rules.allowed_roles` → проверка `user_roles`
4. Пользователь — участник чата из `access_rules.allowed_chats` → проверка `chat_members`
5. **Обратная совместимость:** `config.allowed_users` (старый формат) → проверка по нему
6. Если правил нет совсем → страница публичная

---

## Формат access_rules

Расширение `web_pages.config`:

```json
{
  "access_rules": {
    "public": false,
    "allowed_users": [123456789],
    "allowed_roles": ["project_owner", "tester"],
    "allowed_chats": [-1001234567890]
  }
}
```

Старый формат продолжает работать:

```json
{
  "allowed_users": [123456789]
}
```

---

## Глобальные роли

Роли не привязаны к чатам — проектные/системные.

| Роль | Описание | Типичные доступы |
|------|----------|------------------|
| `project_owner` | Владелец проекта | Все страницы, infra, admin |
| `tester` | Тестировщик | Отладочные страницы, логи |
| `backend_dev` | Бэкенд-разработчик | Infra, API docs, метрики |
| `moderator` | Модератор чатов | Календари, контент |

### Таблица БД

Миграция: `db/init/12_access_control.sql`

```sql
CREATE TABLE user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    granted_by BIGINT,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, role)
);
```

---

## REST API (через tgapi proxy)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/v1/web/roles` | Список ролей (фильтр: `?user_id=`, `?role=`) |
| `GET` | `/v1/web/roles/{user_id}` | Роли конкретного пользователя |
| `POST` | `/v1/web/roles` | Назначить роль `{user_id, role, granted_by, note}` |
| `DELETE` | `/v1/web/roles/{user_id}/{role}` | Отозвать роль |
| `POST` | `/v1/web/roles/check-access` | Проверить доступ `{user_id, slug}` |

### Примеры

```bash
# Назначить роль
curl -X POST http://localhost:8081/v1/web/roles \
  -H 'content-type: application/json' \
  -d '{"user_id": 123456789, "role": "project_owner"}'

# Проверить доступ
curl -X POST http://localhost:8081/v1/web/roles/check-access \
  -H 'content-type: application/json' \
  -d '{"user_id": 123456789, "slug": "infra-dashboard"}'
# → {"user_id": 123456789, "slug": "infra-dashboard", "has_access": true, "reasons": ["role:project_owner"]}
```

---

## MCP инструменты

| Инструмент | Описание |
|------------|----------|
| `webui.list_roles` | Список ролей (опционально `user_id`) |
| `webui.grant_role` | Назначить роль `{user_id, role, granted_by, note}` |
| `webui.revoke_role` | Отозвать роль `{user_id, role}` |
| `webui.check_access` | Проверить доступ `{user_id, slug}` → `{has_access, reasons}` |

---

## Chat-based доступ

Пользователь — участник чата → видит страницы привязанные к этому чату.

**Зависимости:**
- Таблица `chat_members(chat_id, user_id, status)` — обновляется из Telegram updates
- Проверка: `user_id IN (SELECT user_id FROM chat_members WHERE chat_id = ANY(allowed_chats))`

**Примеры:**
- Чат «Ковенант» → страницы с календарём → доступ только участникам чата
- Чат «Трейдинг» → страницы с аналитикой → доступ участникам

---

## Интеграция

### render.py

- `render_page()` — проверяет доступ через initData из `X-Init-Data` header
- `infra_data_proxy()` — использует единую `check_page_access()` вместо хардкода
- `index()` — рендерит hub с доступными страницами для текущего пользователя

### Hub (главный экран)

При открытии Mini App без `start_param`, показывается hub:
- Загружаются все активные страницы
- Фильтруются через `check_page_access()` для текущего пользователя
- Группируются: по чатам → системные (по ролям) → публичные
- Отображаются карточками с иконками и бейджами типов

---

## Файлы

| Файл | Назначение |
|------|------------|
| `db/init/12_access_control.sql` | SQL миграция: таблица user_roles |
| `web-ui/app/services/access.py` | check_page_access(), get_accessible_pages(), group_pages_for_hub() |
| `web-ui/app/services/roles.py` | CRUD для user_roles |
| `web-ui/app/routers/roles.py` | REST API управления ролями |
| `api/app/routers/webui.py` | Проксирование roles API через tgapi |
| `mcp/src/tools/webui.ts` | MCP инструменты для ролей |
